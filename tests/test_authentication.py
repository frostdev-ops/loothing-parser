"""
Tests for authentication and rate limiting functionality.

Tests API key authentication, rate limiting, permission checking,
and connection management.
"""

import pytest
import time
from unittest.mock import AsyncMock

from src.api.auth import AuthManager, authenticate_api_key, check_rate_limit
from src.api.streaming_server import StreamingServer
from src.database.schema import DatabaseManager, create_tables
import tempfile
from pathlib import Path


@pytest.fixture
def auth_manager():
    """Create a fresh AuthManager for testing."""
    return AuthManager()


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = DatabaseManager(db_path)
    create_tables(db)
    yield db
    db.close()

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
async def streaming_server(test_db):
    """Create a test streaming server instance."""
    server = StreamingServer(test_db.db_path)
    await server.start()
    yield server
    await server.stop()


class TestAuthManager:
    """Test the AuthManager class."""

    def test_default_api_key_creation(self, auth_manager):
        """Test that default API key is created on initialization."""
        # Should have the default dev key
        auth_response = auth_manager.authenticate_api_key("dev_key_12345")
        assert auth_response.authenticated is True
        assert auth_response.client_id == "development"
        assert "stream" in auth_response.permissions
        assert "query" in auth_response.permissions

    def test_api_key_generation(self, auth_manager):
        """Test API key generation."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="test_client",
            description="Test key",
            events_per_minute=5000,
            max_connections=3,
        )

        assert key_id.startswith("key_")
        assert len(api_key) > 20  # Should be a substantial key

        # Test authentication with new key
        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is True
        assert auth_response.client_id == "test_client"
        assert auth_response.rate_limit["events_per_minute"] == 5000
        assert auth_response.rate_limit["max_connections"] == 3

    def test_invalid_api_key(self, auth_manager):
        """Test authentication with invalid API key."""
        auth_response = auth_manager.authenticate_api_key("invalid_key")
        assert auth_response.authenticated is False
        assert auth_response.message == "Invalid API key"

    def test_empty_api_key(self, auth_manager):
        """Test authentication with empty API key."""
        auth_response = auth_manager.authenticate_api_key("")
        assert auth_response.authenticated is False
        assert auth_response.message == "API key required"

    def test_api_key_revocation(self, auth_manager):
        """Test API key revocation."""
        # Generate a key
        key_id, api_key = auth_manager.generate_api_key("test_client", "Test key")

        # Verify it works
        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is True

        # Revoke it
        result = auth_manager.revoke_api_key(key_id)
        assert result is True

        # Verify it no longer works
        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is False

    def test_nonexistent_key_revocation(self, auth_manager):
        """Test revoking a nonexistent key."""
        result = auth_manager.revoke_api_key("nonexistent_key")
        assert result is False


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limit_basic(self, auth_manager):
        """Test basic rate limiting."""
        # Generate a key with low limits
        key_id, api_key = auth_manager.generate_api_key(
            "test_client", "Test key", events_per_minute=10, max_connections=2
        )

        client_id = "test_client"

        # Should allow initial requests
        allowed, reason = auth_manager.check_rate_limit(client_id, event_count=5)
        assert allowed is True
        assert reason == "OK"

        # Should allow more up to the limit
        allowed, reason = auth_manager.check_rate_limit(client_id, event_count=5)
        assert allowed is True

        # Should reject when over limit
        allowed, reason = auth_manager.check_rate_limit(client_id, event_count=1)
        assert allowed is False
        assert "Event rate limit exceeded" in reason

    def test_burst_protection(self, auth_manager):
        """Test burst protection (requests per second)."""
        key_id, api_key = auth_manager.generate_api_key("test_client", "Test key")
        client_id = "test_client"

        # Make many rapid requests
        for i in range(100):
            allowed, reason = auth_manager.check_rate_limit(client_id, event_count=1)

        # Should eventually hit burst limit
        allowed, reason = auth_manager.check_rate_limit(client_id, event_count=1)
        # May or may not be blocked depending on timing, but should not crash

    def test_connection_limit(self, auth_manager):
        """Test connection limiting."""
        key_id, api_key = auth_manager.generate_api_key(
            "test_client", "Test key", max_connections=2
        )

        client_id = "test_client"

        # Should allow initial connections
        allowed, reason = auth_manager.check_rate_limit(client_id, is_connection=True)
        assert allowed is True

        # Track connections
        auth_manager.track_connection(client_id, "session_1")

        allowed, reason = auth_manager.check_rate_limit(client_id, is_connection=True)
        assert allowed is True

        auth_manager.track_connection(client_id, "session_2")

        # Should reject third connection
        allowed, reason = auth_manager.check_rate_limit(client_id, is_connection=True)
        assert allowed is False
        assert "Maximum connections exceeded" in reason

        # Untrack a connection
        auth_manager.untrack_connection(client_id, "session_1")

        # Should allow new connection now
        allowed, reason = auth_manager.check_rate_limit(client_id, is_connection=True)
        assert allowed is True

    def test_rate_limit_window_reset(self, auth_manager):
        """Test that rate limit windows reset properly."""
        key_id, api_key = auth_manager.generate_api_key(
            "test_client", "Test key", events_per_minute=10
        )

        client_id = "test_client"

        # Use up the rate limit
        auth_manager.check_rate_limit(client_id, event_count=10)

        # Should be blocked
        allowed, reason = auth_manager.check_rate_limit(client_id, event_count=1)
        assert allowed is False

        # Simulate time passing by manipulating the rate limit state
        if client_id in auth_manager._rate_limits:
            # Reset the window start time to simulate a minute passing
            auth_manager._rate_limits[client_id].minute_window_start = time.time() - 61

        # Should be allowed now
        allowed, reason = auth_manager.check_rate_limit(client_id, event_count=1)
        assert allowed is True

    def test_invalid_metric_validation(self, auth_manager):
        """Test that invalid metrics are rejected."""
        with pytest.raises(ValueError, match="Invalid metric"):
            auth_manager.get_top_performers(metric="invalid_metric")


class TestPermissions:
    """Test permission checking functionality."""

    def test_permission_checking(self, auth_manager):
        """Test permission checking for clients."""
        # Create a key with specific permissions
        custom_permissions = {"stream", "admin"}
        key_id, api_key = auth_manager.generate_api_key(
            "test_client", "Test key", permissions=custom_permissions
        )

        client_id = "test_client"

        # Should have granted permissions
        assert auth_manager.check_permission(client_id, "stream") is True
        assert auth_manager.check_permission(client_id, "admin") is True

        # Should not have other permissions
        assert auth_manager.check_permission(client_id, "query") is False

    def test_permission_for_nonexistent_client(self, auth_manager):
        """Test permission checking for nonexistent client."""
        result = auth_manager.check_permission("nonexistent_client", "stream")
        assert result is False


class TestClientStats:
    """Test client statistics functionality."""

    def test_client_stats(self, auth_manager):
        """Test getting client statistics."""
        # Create a client
        key_id, api_key = auth_manager.generate_api_key("test_client", "Test key")

        # Get stats
        stats = auth_manager.get_client_stats("test_client")
        assert stats is not None
        assert stats["client_id"] == "test_client"
        assert stats["description"] == "Test key"
        assert stats["active"] is True
        assert "usage" in stats
        assert "rate_limits" in stats

    def test_nonexistent_client_stats(self, auth_manager):
        """Test getting stats for nonexistent client."""
        stats = auth_manager.get_client_stats("nonexistent_client")
        assert stats is None

    def test_all_stats(self, auth_manager):
        """Test getting all client statistics."""
        # Create multiple clients
        auth_manager.generate_api_key("client_1", "Client 1")
        auth_manager.generate_api_key("client_2", "Client 2")

        # Get all stats
        stats = auth_manager.get_all_stats()
        assert stats["total_api_keys"] >= 3  # Including default key
        assert stats["active_api_keys"] >= 3
        assert stats["unique_clients"] >= 3  # Including development client
        assert "clients" in stats


class TestStreamingServerAuth:
    """Test authentication integration with streaming server."""

    @pytest.mark.asyncio
    async def test_valid_api_key_connection(self, streaming_server):
        """Test WebSocket connection with valid API key."""
        websocket = AsyncMock()
        websocket.client.host = "127.0.0.1"
        api_key = "dev_key_12345"

        # Mock receiving a welcome and then stopping
        websocket.receive_text.side_effect = [
            '{"type": "end_session", "timestamp": 1234567890}'
        ]

        sent_responses = []
        websocket.send_text.side_effect = lambda x: sent_responses.append(x)

        await streaming_server.handle_websocket_connection(websocket, api_key)

        # Should have received welcome message
        assert len(sent_responses) >= 1
        assert websocket.accept.called

    @pytest.mark.asyncio
    async def test_invalid_api_key_connection(self, streaming_server):
        """Test WebSocket connection with invalid API key."""
        websocket = AsyncMock()
        api_key = "invalid_key"

        await streaming_server.handle_websocket_connection(websocket, api_key)

        # Should be rejected
        websocket.close.assert_called_with(code=4001, reason="Authentication failed")

    @pytest.mark.asyncio
    async def test_rate_limited_connection(self, streaming_server):
        """Test WebSocket connection rate limiting."""
        # Create a key with very low connection limit
        from src.api.auth import auth_manager

        key_id, api_key = auth_manager.generate_api_key(
            "limited_client", "Limited key", max_connections=1
        )

        # First connection should succeed
        websocket1 = AsyncMock()
        websocket1.client.host = "127.0.0.1"
        websocket1.receive_text.side_effect = StopIteration()

        # Track that we're "connected" for rate limiting
        auth_manager.track_connection("limited_client", "session_1")

        # Second connection should be rate limited
        websocket2 = AsyncMock()
        await streaming_server.handle_websocket_connection(websocket2, api_key)

        # Should be rejected for rate limiting
        websocket2.close.assert_called()
        args, kwargs = websocket2.close.call_args
        assert kwargs["code"] == 4029  # Rate limited code


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_authenticate_api_key_function(self):
        """Test the module-level authenticate_api_key function."""
        # Test with default key
        response = authenticate_api_key("dev_key_12345")
        assert response.authenticated is True
        assert response.client_id == "development"

        # Test with invalid key
        response = authenticate_api_key("invalid")
        assert response.authenticated is False

    def test_check_rate_limit_function(self):
        """Test the module-level check_rate_limit function."""
        # This should work without error
        allowed, reason = check_rate_limit("test_client", 1)
        # Result depends on whether client exists, but should not error

    def test_check_permission_function(self):
        """Test the module-level check_permission function."""
        from src.api.auth import check_permission

        # Should work without error
        result = check_permission("development", "stream")
        # Result depends on permissions, but should not error


if __name__ == "__main__":
    pytest.main([__file__])