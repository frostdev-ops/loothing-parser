"""
Session management for streaming clients.

Tracks client connections, authentication state, and processing context.
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional, Set, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..api.models import SessionStart, StreamStats

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """Client session status."""

    CONNECTING = "connecting"
    ACTIVE = "active"
    IDLE = "idle"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class SessionMetrics:
    """Performance metrics for a client session."""

    total_events: int = 0
    events_per_second: float = 0.0
    buffer_utilization: float = 0.0
    lag_ms: float = 0.0
    last_event_time: Optional[float] = None
    uptime_seconds: float = 0.0
    bytes_received: int = 0
    lines_processed: int = 0
    parse_errors: int = 0
    reconnection_count: int = 0

    def update_events_per_second(self, window_seconds: float = 60.0):
        """Update EPS calculation."""
        if self.uptime_seconds > window_seconds:
            self.events_per_second = self.total_events / window_seconds
        else:
            self.events_per_second = self.total_events / max(self.uptime_seconds, 1.0)


@dataclass
class StreamSession:
    """
    Represents an active streaming session from a client.

    Tracks authentication, connection state, processing context,
    and performance metrics for each connected client.
    """

    # Core identification
    client_id: str
    session_id: str
    api_key: str
    created_at: float = field(default_factory=time.time)

    # Session metadata
    client_version: Optional[str] = None
    character_name: Optional[str] = None
    server: Optional[str] = None
    region: Optional[str] = None
    user_agent: Optional[str] = None
    remote_address: Optional[str] = None

    # State tracking
    status: SessionStatus = SessionStatus.CONNECTING
    last_activity: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)

    # Processing context
    encounter_context: Optional[Dict[str, Any]] = field(default_factory=dict)
    character_context: Set[str] = field(default_factory=set)  # Active character GUIDs

    # Performance metrics
    metrics: SessionMetrics = field(default_factory=SessionMetrics)

    # Rate limiting
    events_this_minute: int = 0
    minute_window_start: float = field(default_factory=time.time)
    rate_limit_events_per_minute: int = 10000

    # Connection management
    websocket_connected: bool = False
    last_sequence_ack: int = 0
    pending_sequences: Set[int] = field(default_factory=set)

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()
        self.metrics.uptime_seconds = self.last_activity - self.created_at

    def update_heartbeat(self):
        """Update last heartbeat timestamp."""
        self.last_heartbeat = time.time()
        self.update_activity()

    def add_event(self, sequence: int, line_length: int = 0):
        """Record a processed event."""
        current_time = time.time()

        # Update metrics
        self.metrics.total_events += 1
        self.metrics.last_event_time = current_time
        self.metrics.bytes_received += line_length
        self.metrics.lines_processed += 1

        # Update rate limiting
        if current_time - self.minute_window_start >= 60.0:
            # Reset rate limiting window
            self.events_this_minute = 0
            self.minute_window_start = current_time

        self.events_this_minute += 1

        # Track pending sequence
        self.pending_sequences.add(sequence)

        # Update general activity
        self.update_activity()

        # Update EPS calculation
        self.metrics.update_events_per_second()

    def acknowledge_sequence(self, sequence: int):
        """Acknowledge processing of a sequence."""
        self.pending_sequences.discard(sequence)
        self.last_sequence_ack = max(self.last_sequence_ack, sequence)

    def add_parse_error(self):
        """Record a parse error."""
        self.metrics.parse_errors += 1

    def set_lag(self, lag_ms: float):
        """Update latency measurement."""
        self.metrics.lag_ms = lag_ms

    def set_buffer_utilization(self, utilization_percent: float):
        """Update buffer utilization metric."""
        self.metrics.buffer_utilization = utilization_percent

    def check_rate_limit(self) -> bool:
        """Check if client is within rate limits."""
        current_time = time.time()

        # Reset window if needed
        if current_time - self.minute_window_start >= 60.0:
            self.events_this_minute = 0
            self.minute_window_start = current_time

        return self.events_this_minute < self.rate_limit_events_per_minute

    def is_idle(self, idle_threshold_seconds: float = 300.0) -> bool:
        """Check if session is idle."""
        return time.time() - self.last_activity > idle_threshold_seconds

    def is_stale(self, stale_threshold_seconds: float = 3600.0) -> bool:
        """Check if session is stale and should be cleaned up."""
        return time.time() - self.last_heartbeat > stale_threshold_seconds

    def get_stats(self) -> StreamStats:
        """Get current session statistics."""
        current_time = time.time()

        return StreamStats(
            total_events=self.metrics.total_events,
            events_per_second=self.metrics.events_per_second,
            buffer_size=len(self.pending_sequences),
            lag_ms=self.metrics.lag_ms,
            encounters_active=1 if self.encounter_context else 0,
            characters_tracked=len(self.character_context),
            uptime_seconds=current_time - self.created_at,
            last_event_time=self.metrics.last_event_time,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "client_id": self.client_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "status": self.status.value,
            "last_activity": self.last_activity,
            "last_heartbeat": self.last_heartbeat,
            "client_version": self.client_version,
            "character_name": self.character_name,
            "realm": self.realm,
            "remote_address": self.remote_address,
            "websocket_connected": self.websocket_connected,
            "rate_limit": {
                "events_per_minute": self.rate_limit_events_per_minute,
                "events_this_minute": self.events_this_minute,
                "within_limit": self.check_rate_limit(),
            },
            "metrics": {
                "total_events": self.metrics.total_events,
                "events_per_second": self.metrics.events_per_second,
                "lag_ms": self.metrics.lag_ms,
                "uptime_seconds": self.metrics.uptime_seconds,
                "parse_errors": self.metrics.parse_errors,
                "bytes_received": self.metrics.bytes_received,
                "pending_sequences": len(self.pending_sequences),
            },
            "context": {
                "encounter_active": bool(self.encounter_context),
                "characters_tracked": len(self.character_context),
            },
        }


class SessionManager:
    """
    Manages multiple client sessions.

    Provides session lifecycle management, cleanup, and monitoring
    for all connected streaming clients.
    """

    def __init__(self, max_sessions: int = 100):
        """
        Initialize session manager.

        Args:
            max_sessions: Maximum concurrent sessions
        """
        self.max_sessions = max_sessions
        self._sessions: Dict[str, StreamSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start session manager and cleanup task."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"Session manager started (max_sessions={self.max_sessions})")

    async def stop(self):
        """Stop session manager and cleanup all sessions."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Clean up all sessions
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.remove_session(session_id)

        logger.info("Session manager stopped")

    def create_session(
        self,
        client_id: str,
        session_id: str,
        api_key: str,
        metadata: Optional[SessionStart] = None,
    ) -> StreamSession:
        """
        Create a new streaming session.

        Args:
            client_id: Unique client identifier
            session_id: Unique session identifier
            api_key: Client API key
            metadata: Optional session metadata

        Returns:
            New StreamSession

        Raises:
            ValueError: If session limit reached
        """
        if len(self._sessions) >= self.max_sessions:
            raise ValueError(f"Maximum session limit reached ({self.max_sessions})")

        if session_id in self._sessions:
            # Remove existing session
            logger.warning(f"Session {session_id} already exists, replacing")
            del self._sessions[session_id]

        session = StreamSession(
            client_id=client_id, session_id=session_id, api_key=api_key
        )

        if metadata:
            session.client_version = metadata.client_version
            session.character_name = metadata.character_name
            session.realm = metadata.realm

        self._sessions[session_id] = session
        logger.info(f"Created session {session_id} for client {client_id}")

        return session

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def remove_session(self, session_id: str) -> bool:
        """
        Remove a session.

        Args:
            session_id: Session to remove

        Returns:
            True if session was removed
        """
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.status = SessionStatus.DISCONNECTED
            del self._sessions[session_id]
            logger.info(f"Removed session {session_id}")
            return True
        return False

    def get_all_sessions(self) -> Dict[str, StreamSession]:
        """Get all active sessions."""
        return self._sessions.copy()

    def get_sessions_by_client(self, client_id: str) -> List[StreamSession]:
        """Get all sessions for a specific client."""
        return [s for s in self._sessions.values() if s.client_id == client_id]

    async def _cleanup_loop(self):
        """Background task for cleaning up stale sessions."""
        cleanup_interval = 60.0  # Check every minute

        while self._running:
            try:
                await asyncio.sleep(cleanup_interval)
                if not self._running:
                    break

                await self._cleanup_stale_sessions()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")

    async def _cleanup_stale_sessions(self):
        """Remove stale and disconnected sessions."""
        current_time = time.time()
        stale_sessions = []

        for session_id, session in self._sessions.items():
            if session.is_stale() or session.status == SessionStatus.DISCONNECTED:
                stale_sessions.append(session_id)
            elif session.is_idle():
                session.status = SessionStatus.IDLE

        for session_id in stale_sessions:
            await self.remove_session(session_id)

        if stale_sessions:
            logger.info(f"Cleaned up {len(stale_sessions)} stale sessions")

    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics."""
        sessions = list(self._sessions.values())

        status_counts = {}
        for status in SessionStatus:
            status_counts[status.value] = sum(1 for s in sessions if s.status == status)

        total_events = sum(s.metrics.total_events for s in sessions)
        active_sessions = [s for s in sessions if s.status == SessionStatus.ACTIVE]
        avg_events_per_second = (
            sum(s.metrics.events_per_second for s in active_sessions)
            / len(active_sessions)
            if active_sessions
            else 0.0
        )

        return {
            "total_sessions": len(sessions),
            "max_sessions": self.max_sessions,
            "status_counts": status_counts,
            "total_events_processed": total_events,
            "average_events_per_second": round(avg_events_per_second, 2),
            "active_clients": len(set(s.client_id for s in sessions)),
        }
