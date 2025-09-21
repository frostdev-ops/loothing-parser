"""
Authentication and rate limiting for streaming API.

Provides API key authentication, rate limiting, and client authorization
for the combat log streaming endpoints.
"""

import time
import hashlib
import secrets
import logging
from typing import Dict, Optional, Set, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json

from .models import AuthResponse

logger = logging.getLogger(__name__)


@dataclass
class ApiKey:
    """API key configuration."""

    key_id: str
    key_hash: str  # SHA256 hash of the actual key
    client_id: str
    description: str
    permissions: Set[str] = field(default_factory=set)

    # Multi-tenancy
    guild_id: Optional[int] = None  # Guild ID for multi-tenant access
    guild_name: Optional[str] = None  # Guild name for display

    # Rate limiting
    events_per_minute: int = 10000
    max_connections: int = 5

    # Metadata
    created_at: float = field(default_factory=time.time)
    last_used: Optional[float] = None
    active: bool = True

    # Usage tracking
    total_events: int = 0
    total_connections: int = 0


@dataclass
class RateLimitState:
    """Rate limiting state for a client."""

    events_this_minute: int = 0
    minute_window_start: float = field(default_factory=time.time)
    connections_active: int = 0
    last_request: float = field(default_factory=time.time)

    # Burst protection
    requests_this_second: int = 0
    second_window_start: float = field(default_factory=time.time)
    burst_limit: int = 100  # Max requests per second


class AuthManager:
    """
    Manages API key authentication and rate limiting.

    Features:
    - API key generation and validation
    - Per-client rate limiting
    - Permission management
    - Usage tracking and analytics
    - Automatic cleanup of expired states
    """

    def __init__(self):
        """Initialize authentication manager."""
        self._api_keys: Dict[str, ApiKey] = {}  # key_id -> ApiKey
        self._rate_limits: Dict[str, RateLimitState] = {}  # client_id -> RateLimitState
        self._active_connections: Dict[str, Set[str]] = {}  # client_id -> session_ids

        # Default permissions
        self.default_permissions = {"stream", "query"}

        # Create default API key for development
        self._create_default_key()

    def _create_default_key(self):
        """Create a default API key for development."""
        key = "dev_key_12345"
        key_id = "dev_default"

        api_key = ApiKey(
            key_id=key_id,
            key_hash=self._hash_key(key),
            client_id="development",
            description="Default development API key",
            permissions=self.default_permissions.copy(),
            guild_id=1,  # Default guild for existing data
            guild_name="Default Guild",
            events_per_minute=20000,  # Higher limit for dev
            max_connections=10,
        )

        self._api_keys[key_id] = api_key
        logger.info(f"Created default API key: {key}")

    def generate_api_key(
        self,
        client_id: str,
        description: str,
        guild_id: Optional[int] = None,
        guild_name: Optional[str] = None,
        permissions: Optional[Set[str]] = None,
        events_per_minute: int = 10000,
        max_connections: int = 5,
    ) -> tuple[str, str]:
        """
        Generate a new API key.

        Args:
            client_id: Unique client identifier
            description: Human-readable description
            guild_id: Guild ID for multi-tenant access
            guild_name: Guild name for display
            permissions: Set of permissions (defaults to default_permissions)
            events_per_minute: Rate limit for events
            max_connections: Maximum concurrent connections

        Returns:
            Tuple of (key_id, actual_key)
        """
        # Generate secure key
        key = secrets.token_urlsafe(32)
        key_id = f"key_{int(time.time())}_{secrets.token_hex(4)}"

        if permissions is None:
            permissions = self.default_permissions.copy()

        api_key = ApiKey(
            key_id=key_id,
            key_hash=self._hash_key(key),
            client_id=client_id,
            description=description,
            guild_id=guild_id,
            guild_name=guild_name,
            permissions=permissions,
            events_per_minute=events_per_minute,
            max_connections=max_connections,
        )

        self._api_keys[key_id] = api_key
        logger.info(f"Generated API key {key_id} for client {client_id} (guild: {guild_name})")

        return key_id, key

    def revoke_api_key(self, key_id: str) -> bool:
        """
        Revoke an API key.

        Args:
            key_id: Key ID to revoke

        Returns:
            True if key was revoked
        """
        if key_id in self._api_keys:
            self._api_keys[key_id].active = False
            logger.info(f"Revoked API key {key_id}")
            return True
        return False

    def authenticate_api_key(self, api_key: str) -> AuthResponse:
        """
        Authenticate an API key.

        Args:
            api_key: The API key to validate

        Returns:
            AuthResponse with authentication result
        """
        if not api_key:
            return AuthResponse(authenticated=False, message="API key required")

        key_hash = self._hash_key(api_key)

        # Find matching key
        for key_id, stored_key in self._api_keys.items():
            if stored_key.key_hash == key_hash and stored_key.active:
                # Update usage
                stored_key.last_used = time.time()

                # Get rate limits
                rate_limit_info = {
                    "events_per_minute": stored_key.events_per_minute,
                    "max_connections": stored_key.max_connections,
                }

                return AuthResponse(
                    authenticated=True,
                    client_id=stored_key.client_id,
                    guild_id=stored_key.guild_id,
                    guild_name=stored_key.guild_name,
                    permissions=list(stored_key.permissions),
                    rate_limit=rate_limit_info,
                    message="Authentication successful",
                )

        return AuthResponse(authenticated=False, message="Invalid API key")

    def check_rate_limit(
        self, client_id: str, event_count: int = 1, is_connection: bool = False
    ) -> tuple[bool, str]:
        """
        Check if client is within rate limits.

        Args:
            client_id: Client identifier
            event_count: Number of events to check
            is_connection: Whether this is a connection attempt

        Returns:
            Tuple of (allowed, reason)
        """
        current_time = time.time()

        # Get or create rate limit state
        if client_id not in self._rate_limits:
            self._rate_limits[client_id] = RateLimitState()

        state = self._rate_limits[client_id]

        # Get client's API key config
        api_key = self._get_api_key_for_client(client_id)
        if not api_key:
            return False, "No valid API key for client"

        # Check burst protection (requests per second)
        if current_time - state.second_window_start >= 1.0:
            state.requests_this_second = 0
            state.second_window_start = current_time

        state.requests_this_second += 1
        if state.requests_this_second > state.burst_limit:
            return False, "Burst limit exceeded (requests per second)"

        # Check event rate limit (events per minute)
        if current_time - state.minute_window_start >= 60.0:
            state.events_this_minute = 0
            state.minute_window_start = current_time

        if state.events_this_minute + event_count > api_key.events_per_minute:
            return False, "Event rate limit exceeded"

        # Check connection limit
        if is_connection:
            if state.connections_active >= api_key.max_connections:
                return False, "Maximum connections exceeded"

        # Update state
        state.events_this_minute += event_count
        state.last_request = current_time

        return True, "OK"

    def track_connection(self, client_id: str, session_id: str):
        """Track a new connection for rate limiting."""
        if client_id not in self._active_connections:
            self._active_connections[client_id] = set()

        self._active_connections[client_id].add(session_id)

        # Update rate limit state
        if client_id in self._rate_limits:
            self._rate_limits[client_id].connections_active = len(
                self._active_connections[client_id]
            )

    def untrack_connection(self, client_id: str, session_id: str):
        """Remove connection tracking."""
        if client_id in self._active_connections:
            self._active_connections[client_id].discard(session_id)

            # Clean up empty sets
            if not self._active_connections[client_id]:
                del self._active_connections[client_id]

            # Update rate limit state
            if client_id in self._rate_limits:
                self._rate_limits[client_id].connections_active = len(
                    self._active_connections.get(client_id, set())
                )

    def check_permission(self, client_id: str, permission: str) -> bool:
        """Check if client has a specific permission."""
        api_key = self._get_api_key_for_client(client_id)
        if not api_key:
            return False

        return permission in api_key.permissions

    def get_client_stats(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific client."""
        api_key = self._get_api_key_for_client(client_id)
        if not api_key:
            return None

        rate_state = self._rate_limits.get(client_id)
        active_connections = len(self._active_connections.get(client_id, set()))

        return {
            "client_id": client_id,
            "api_key_id": api_key.key_id,
            "description": api_key.description,
            "permissions": list(api_key.permissions),
            "active": api_key.active,
            "created_at": api_key.created_at,
            "last_used": api_key.last_used,
            "usage": {
                "total_events": api_key.total_events,
                "total_connections": api_key.total_connections,
                "active_connections": active_connections,
            },
            "rate_limits": {
                "events_per_minute": api_key.events_per_minute,
                "max_connections": api_key.max_connections,
                "current_usage": (
                    {
                        "events_this_minute": (rate_state.events_this_minute if rate_state else 0),
                        "connections_active": active_connections,
                    }
                    if rate_state
                    else None
                ),
            },
        }

    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all clients."""
        total_keys = len(self._api_keys)
        active_keys = sum(1 for key in self._api_keys.values() if key.active)
        total_connections = sum(len(sessions) for sessions in self._active_connections.values())

        return {
            "total_api_keys": total_keys,
            "active_api_keys": active_keys,
            "total_active_connections": total_connections,
            "unique_clients": len(set(key.client_id for key in self._api_keys.values())),
            "clients": {
                client_id: self.get_client_stats(client_id)
                for client_id in set(key.client_id for key in self._api_keys.values())
            },
        }

    def cleanup_stale_states(self, max_age_hours: int = 24):
        """Clean up old rate limiting states."""
        cutoff_time = time.time() - (max_age_hours * 3600)

        stale_clients = [
            client_id
            for client_id, state in self._rate_limits.items()
            if state.last_request < cutoff_time
        ]

        for client_id in stale_clients:
            del self._rate_limits[client_id]

        if stale_clients:
            logger.info(f"Cleaned up {len(stale_clients)} stale rate limit states")

    def _get_api_key_for_client(self, client_id: str) -> Optional[ApiKey]:
        """Get the active API key for a client."""
        for api_key in self._api_keys.values():
            if api_key.client_id == client_id and api_key.active:
                return api_key
        return None

    def _hash_key(self, api_key: str) -> str:
        """Hash an API key for secure storage."""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


# Global auth manager instance
auth_manager = AuthManager()


def authenticate_api_key(api_key: str) -> AuthResponse:
    """Convenience function for API key authentication."""
    return auth_manager.authenticate_api_key(api_key)


def check_rate_limit(client_id: str, event_count: int = 1) -> tuple[bool, str]:
    """Convenience function for rate limit checking."""
    return auth_manager.check_rate_limit(client_id, event_count)


def check_permission(client_id: str, permission: str) -> bool:
    """Convenience function for permission checking."""
    return auth_manager.check_permission(client_id, permission)
