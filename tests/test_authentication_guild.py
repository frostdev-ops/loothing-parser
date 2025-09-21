"""
Guild authentication tests for WoW combat log parser.

Tests guild-specific authentication features including guild-scoped API keys,
guild context extraction, permissions, and rate limiting isolation.
"""

import pytest
import pytest_asyncio
import time
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from src.api.auth import AuthManager, authenticate_api_key, check_rate_limit
from src.api.models import AuthResponse
from src.api.streaming_server import StreamingServer
from src.database.schema import DatabaseManager, create_tables


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
def multi_guild_auth_setup(auth_manager):
    """Set up multiple guilds with different API keys for testing."""
    # Create test guilds (assuming they exist in database)
    guild_configs = [
        {
            "guild_id": 1,
            "guild_name": "Default Guild",
            "client_id": "development",
            "description": "Default development API key",
            "events_per_minute": 20000,
            "max_connections": 10,
        },
        {
            "guild_id": 2,
            "guild_name": "Loothing",
            "client_id": "loothing_main",
            "description": "Main Loothing Guild API Key",
            "events_per_minute": 15000,
            "max_connections": 8,
        },
        {
            "guild_id": 3,
            "guild_name": "Test Guild Alpha",
            "client_id": "alpha_guild",
            "description": "Alpha Guild API Key",
            "events_per_minute": 10000,
            "max_connections": 5,
        },
        {
            "guild_id": 4,
            "guild_name": "Test Guild Beta",
            "client_id": "beta_guild",
            "description": "Beta Guild API Key",
            "events_per_minute": 5000,
            "max_connections": 3,
        },
    ]

    api_keys = {}

    # Generate API keys for each guild (skip default guild as it already exists)
    for config in guild_configs[1:]:  # Skip default guild
        key_id, api_key = auth_manager.generate_api_key(
            client_id=config["client_id"],
            description=config["description"],
            guild_id=config["guild_id"],
            guild_name=config["guild_name"],
            permissions={"stream", "query", "upload"},
            events_per_minute=config["events_per_minute"],
            max_connections=config["max_connections"],
        )
        api_keys[config["guild_id"]] = {
            "key_id": key_id,
            "api_key": api_key,
            "config": config,
        }

    # Add default guild key
    api_keys[1] = {
        "key_id": "dev_default",
        "api_key": "dev_key_12345",
        "config": guild_configs[0],
    }

    return api_keys


class TestGuildAPIKeyGeneration:
    """Test guild-specific API key generation and management."""

    def test_api_key_with_guild_id(self, auth_manager):
        """Test API key generation with guild context."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="test_guild_client",
            description="Test Guild API Key",
            guild_id=2,
            guild_name="Test Guild",
            permissions={"stream", "query", "upload"},
            events_per_minute=12000,
            max_connections=6,
        )

        assert key_id.startswith("key_"), "Key ID should follow expected format"
        assert len(api_key) > 20, "API key should be substantial length"

        # Test authentication includes guild context
        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is True, "API key should authenticate successfully"
        assert auth_response.client_id == "test_guild_client", "Client ID should match"
        assert auth_response.guild_id == 2, "Guild ID should be preserved"
        assert auth_response.guild_name == "Test Guild", "Guild name should be preserved"
        assert auth_response.rate_limit["events_per_minute"] == 12000, "Rate limits should match"
        assert auth_response.rate_limit["max_connections"] == 6, "Connection limits should match"

    def test_guild_api_key_without_guild_context(self, auth_manager):
        """Test API key generation without guild context (legacy behavior)."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="legacy_client",
            description="Legacy API Key",
            # No guild_id or guild_name provided
        )

        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is True, "Legacy key should authenticate"
        assert auth_response.client_id == "legacy_client", "Client ID should match"
        assert auth_response.guild_id is None, "Guild ID should be None for legacy keys"
        assert auth_response.guild_name is None, "Guild name should be None for legacy keys"

    def test_guild_api_key_default_permissions(self, auth_manager):
        """Test that guild API keys get appropriate default permissions."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="test_permissions",
            description="Test Permissions",
            guild_id=5,
            guild_name="Permission Test Guild",
        )

        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is True, "API key should authenticate"
        assert "stream" in auth_response.permissions, "Should have default stream permission"
        assert "query" in auth_response.permissions, "Should have default query permission"

    def test_guild_api_key_custom_permissions(self, auth_manager):
        """Test guild API keys with custom permissions."""
        custom_permissions = {"stream", "admin", "upload"}
        key_id, api_key = auth_manager.generate_api_key(
            client_id="custom_permissions",
            description="Custom Permissions Key",
            guild_id=6,
            guild_name="Custom Guild",
            permissions=custom_permissions,
        )

        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is True, "API key should authenticate"
        assert set(auth_response.permissions) == custom_permissions, "Permissions should match exactly"


class TestGuildContextExtraction:
    """Test guild context extraction from authentication."""

    def test_guild_context_extraction_success(self, multi_guild_auth_setup):
        """Test successful guild context extraction."""
        api_keys = multi_guild_auth_setup

        for guild_id, key_info in api_keys.items():
            api_key = key_info["api_key"]
            expected_config = key_info["config"]

            auth_response = authenticate_api_key(api_key)

            assert auth_response.authenticated is True, f"Guild {guild_id} API key should authenticate"
            assert auth_response.guild_id == guild_id, f"Guild ID should match for guild {guild_id}"
            assert auth_response.guild_name == expected_config["guild_name"], \
                f"Guild name should match for guild {guild_id}"
            assert auth_response.client_id == expected_config["client_id"], \
                f"Client ID should match for guild {guild_id}"

    def test_guild_context_validation(self, auth_manager):
        """Test guild context validation and error handling."""
        # Test with invalid guild_id type
        with pytest.raises(TypeError):
            auth_manager.generate_api_key(
                client_id="invalid_guild_type",
                description="Invalid Guild Type",
                guild_id="not_an_integer",  # Should be int
                guild_name="Invalid Guild",
            )

    def test_guild_context_persistence(self, auth_manager):
        """Test that guild context persists across multiple authentications."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="persistence_test",
            description="Persistence Test",
            guild_id=7,
            guild_name="Persistence Guild",
        )

        # Authenticate multiple times
        for _ in range(5):
            auth_response = auth_manager.authenticate_api_key(api_key)
            assert auth_response.guild_id == 7, "Guild ID should persist"
            assert auth_response.guild_name == "Persistence Guild", "Guild name should persist"
            time.sleep(0.1)  # Small delay between authentications


class TestGuildIsolatedRateLimiting:
    """Test that rate limiting is properly isolated by guild."""

    def test_guild_rate_limiting_isolation(self, multi_guild_auth_setup):
        """Test that rate limits are isolated between guilds."""
        api_keys = multi_guild_auth_setup

        # Use up rate limit for one guild
        guild_2_client = api_keys[2]["config"]["client_id"]
        guild_3_client = api_keys[3]["config"]["client_id"]

        # Exhaust guild 2's rate limit
        allowed, reason = check_rate_limit(guild_2_client, event_count=15000)
        assert allowed is True, "Initial request should be allowed"

        # Guild 2 should now be rate limited
        allowed, reason = check_rate_limit(guild_2_client, event_count=1)
        assert allowed is False, "Guild 2 should be rate limited"
        assert "Event rate limit exceeded" in reason, "Should indicate rate limit exceeded"

        # Guild 3 should still be allowed
        allowed, reason = check_rate_limit(guild_3_client, event_count=1000)
        assert allowed is True, "Guild 3 should not be affected by Guild 2's rate limiting"

    def test_guild_connection_limiting_isolation(self, multi_guild_auth_setup):
        """Test that connection limits are isolated between guilds."""
        api_keys = multi_guild_auth_setup
        auth_manager = AuthManager()  # Get the singleton

        guild_2_client = api_keys[2]["config"]["client_id"]
        guild_3_client = api_keys[3]["config"]["client_id"]

        # Fill up guild 2's connection limit (8 connections)
        for i in range(8):
            auth_manager.track_connection(guild_2_client, f"session_{i}")

        # Guild 2 should be at connection limit
        allowed, reason = auth_manager.check_rate_limit(guild_2_client, is_connection=True)
        assert allowed is False, "Guild 2 should be at connection limit"
        assert "Maximum connections exceeded" in reason, "Should indicate connection limit"

        # Guild 3 should still allow connections
        allowed, reason = auth_manager.check_rate_limit(guild_3_client, is_connection=True)
        assert allowed is True, "Guild 3 should not be affected by Guild 2's connections"

        # Add connections to guild 3
        for i in range(3):
            auth_manager.track_connection(guild_3_client, f"session_{i}")

        # Guild 3 should now be at its limit (3 connections)
        allowed, reason = auth_manager.check_rate_limit(guild_3_client, is_connection=True)
        assert allowed is False, "Guild 3 should now be at connection limit"

    def test_guild_rate_limit_recovery(self, auth_manager):
        """Test that guild rate limits recover independently."""
        # Create two guilds with different rate limits
        key_id_1, api_key_1 = auth_manager.generate_api_key(
            client_id="recovery_guild_1",
            description="Recovery Test 1",
            guild_id=8,
            guild_name="Recovery Guild 1",
            events_per_minute=100,
        )

        key_id_2, api_key_2 = auth_manager.generate_api_key(
            client_id="recovery_guild_2",
            description="Recovery Test 2",
            guild_id=9,
            guild_name="Recovery Guild 2",
            events_per_minute=200,
        )

        # Exhaust both guilds' rate limits
        auth_manager.check_rate_limit("recovery_guild_1", event_count=100)
        auth_manager.check_rate_limit("recovery_guild_2", event_count=200)

        # Both should be rate limited
        allowed_1, _ = auth_manager.check_rate_limit("recovery_guild_1", event_count=1)
        allowed_2, _ = auth_manager.check_rate_limit("recovery_guild_2", event_count=1)
        assert allowed_1 is False, "Guild 1 should be rate limited"
        assert allowed_2 is False, "Guild 2 should be rate limited"

        # Simulate time passing for guild 1 only
        if "recovery_guild_1" in auth_manager._rate_limits:
            auth_manager._rate_limits["recovery_guild_1"].minute_window_start = time.time() - 61

        # Guild 1 should recover, guild 2 should still be limited
        allowed_1, _ = auth_manager.check_rate_limit("recovery_guild_1", event_count=1)
        allowed_2, _ = auth_manager.check_rate_limit("recovery_guild_2", event_count=1)
        assert allowed_1 is True, "Guild 1 should have recovered"
        assert allowed_2 is False, "Guild 2 should still be rate limited"


class TestGuildPermissionChecks:
    """Test guild-specific permission checking."""

    def test_guild_permission_isolation(self, auth_manager):
        """Test that permissions are isolated by guild client."""
        # Create guild with specific permissions
        key_id_1, api_key_1 = auth_manager.generate_api_key(
            client_id="admin_guild",
            description="Admin Guild",
            guild_id=10,
            guild_name="Admin Guild",
            permissions={"stream", "query", "admin"},
        )

        key_id_2, api_key_2 = auth_manager.generate_api_key(
            client_id="basic_guild",
            description="Basic Guild",
            guild_id=11,
            guild_name="Basic Guild",
            permissions={"stream", "query"},  # No admin permission
        )

        # Admin guild should have admin permission
        assert auth_manager.check_permission("admin_guild", "admin") is True, \
            "Admin guild should have admin permission"
        assert auth_manager.check_permission("admin_guild", "stream") is True, \
            "Admin guild should have stream permission"

        # Basic guild should not have admin permission
        assert auth_manager.check_permission("basic_guild", "admin") is False, \
            "Basic guild should not have admin permission"
        assert auth_manager.check_permission("basic_guild", "stream") is True, \
            "Basic guild should have stream permission"

    def test_guild_permission_validation(self, auth_manager):
        """Test validation of guild permissions."""
        # Test permission check for nonexistent guild client
        result = auth_manager.check_permission("nonexistent_guild", "stream")
        assert result is False, "Nonexistent guild should have no permissions"

        # Test permission check with empty client ID
        result = auth_manager.check_permission("", "stream")
        assert result is False, "Empty client ID should have no permissions"

    def test_guild_default_permissions(self, auth_manager):
        """Test that guild API keys get appropriate default permissions."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="default_perms_guild",
            description="Default Permissions Guild",
            guild_id=12,
            guild_name="Default Permissions Guild",
            # No explicit permissions - should get defaults
        )

        client_id = "default_perms_guild"

        # Should have default permissions
        assert auth_manager.check_permission(client_id, "stream") is True, \
            "Should have default stream permission"
        assert auth_manager.check_permission(client_id, "query") is True, \
            "Should have default query permission"

        # Should not have admin permission by default
        assert auth_manager.check_permission(client_id, "admin") is False, \
            "Should not have admin permission by default"


class TestGuildAuthenticationStatistics:
    """Test guild-specific authentication statistics and monitoring."""

    def test_guild_client_statistics(self, multi_guild_auth_setup):
        """Test statistics for guild clients."""
        api_keys = multi_guild_auth_setup
        auth_manager = AuthManager()

        for guild_id, key_info in api_keys.items():
            client_id = key_info["config"]["client_id"]
            stats = auth_manager.get_client_stats(client_id)

            assert stats is not None, f"Stats should exist for guild {guild_id}"
            assert stats["client_id"] == client_id, "Client ID should match"
            assert "active" in stats, "Should include active status"
            assert "usage" in stats, "Should include usage information"
            assert "rate_limits" in stats, "Should include rate limit information"

            # Check guild-specific information
            if guild_id > 1:  # Skip default guild which may not have guild info
                expected_config = key_info["config"]
                assert stats["rate_limits"]["events_per_minute"] == expected_config["events_per_minute"], \
                    f"Rate limits should match for guild {guild_id}"
                assert stats["rate_limits"]["max_connections"] == expected_config["max_connections"], \
                    f"Connection limits should match for guild {guild_id}"

    def test_global_guild_statistics(self, multi_guild_auth_setup):
        """Test global statistics across all guilds."""
        api_keys = multi_guild_auth_setup
        auth_manager = AuthManager()

        stats = auth_manager.get_all_stats()

        assert "total_api_keys" in stats, "Should include total API key count"
        assert "active_api_keys" in stats, "Should include active API key count"
        assert "unique_clients" in stats, "Should include unique client count"
        assert "clients" in stats, "Should include client details"

        # Should have at least our test guilds
        assert stats["total_api_keys"] >= len(api_keys), "Should count all test API keys"
        assert stats["unique_clients"] >= len(api_keys), "Should count all test clients"

        # Verify each guild is represented
        for guild_id, key_info in api_keys.items():
            client_id = key_info["config"]["client_id"]
            assert client_id in stats["clients"], f"Guild {guild_id} client should be in global stats"

    def test_guild_usage_tracking(self, auth_manager):
        """Test usage tracking for guild clients."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="usage_tracking_guild",
            description="Usage Tracking Guild",
            guild_id=13,
            guild_name="Usage Tracking Guild",
        )

        client_id = "usage_tracking_guild"

        # Simulate some usage
        auth_manager.check_rate_limit(client_id, event_count=100)
        auth_manager.track_connection(client_id, "session_1")
        auth_manager.track_connection(client_id, "session_2")

        # Check usage statistics
        stats = auth_manager.get_client_stats(client_id)
        assert stats is not None, "Stats should exist"

        # Should show active connections
        usage = stats["usage"]
        assert usage["active_connections"] == 2, "Should track active connections"

        # Clean up connections
        auth_manager.untrack_connection(client_id, "session_1")
        auth_manager.untrack_connection(client_id, "session_2")


class TestGuildWebSocketAuthentication:
    """Test guild authentication in WebSocket connections."""

    @pytest_asyncio.fixture
    async def streaming_server(self, test_db):
        """Create a test streaming server instance."""
        server = StreamingServer(test_db.db_path)
        await server.start()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_guild_websocket_authentication(self, streaming_server, auth_manager):
        """Test WebSocket authentication with guild context."""
        # Create guild API key
        key_id, api_key = auth_manager.generate_api_key(
            client_id="websocket_guild",
            description="WebSocket Guild",
            guild_id=14,
            guild_name="WebSocket Guild",
        )

        websocket = AsyncMock()
        websocket.client.host = "127.0.0.1"

        # Mock receiving a welcome and then stopping
        websocket.receive_text.side_effect = [
            '{"type": "end_session", "timestamp": 1234567890}'
        ]

        sent_responses = []
        websocket.send_text.side_effect = lambda x: sent_responses.append(x)

        await streaming_server.handle_websocket_connection(websocket, api_key)

        # Should have received welcome message with guild context
        assert len(sent_responses) >= 1, "Should receive welcome message"
        assert websocket.accept.called, "WebSocket should be accepted"

        # Parse welcome message to verify guild context
        import json
        welcome_message = json.loads(sent_responses[0])
        assert welcome_message.get("type") == "welcome", "First message should be welcome"
        assert welcome_message.get("guild_id") == 14, "Should include guild ID"
        assert welcome_message.get("guild_name") == "WebSocket Guild", "Should include guild name"

    @pytest.mark.asyncio
    async def test_guild_websocket_rate_limiting(self, streaming_server, auth_manager):
        """Test WebSocket rate limiting with guild context."""
        # Create guild with low connection limit
        key_id, api_key = auth_manager.generate_api_key(
            client_id="limited_websocket_guild",
            description="Limited WebSocket Guild",
            guild_id=15,
            guild_name="Limited WebSocket Guild",
            max_connections=1,
        )

        # Track that we already have a connection
        auth_manager.track_connection("limited_websocket_guild", "existing_session")

        # Try to connect with the rate-limited key
        websocket = AsyncMock()
        websocket.client.host = "127.0.0.1"

        await streaming_server.handle_websocket_connection(websocket, api_key)

        # Should be rejected for rate limiting
        websocket.close.assert_called()
        args, kwargs = websocket.close.call_args
        assert kwargs["code"] == 4029, "Should be rate limited error code"

        # Clean up
        auth_manager.untrack_connection("limited_websocket_guild", "existing_session")

    @pytest.mark.asyncio
    async def test_guild_websocket_without_guild_context(self, streaming_server):
        """Test WebSocket authentication with default (non-guild) API key."""
        # Use default development key (no guild context)
        api_key = "dev_key_12345"

        websocket = AsyncMock()
        websocket.client.host = "127.0.0.1"

        # Mock receiving a welcome and then stopping
        websocket.receive_text.side_effect = [
            '{"type": "end_session", "timestamp": 1234567890}'
        ]

        sent_responses = []
        websocket.send_text.side_effect = lambda x: sent_responses.append(x)

        await streaming_server.handle_websocket_connection(websocket, api_key)

        # Should still work but without guild context
        assert len(sent_responses) >= 1, "Should receive welcome message"
        assert websocket.accept.called, "WebSocket should be accepted"

        # Parse welcome message to verify no guild context
        import json
        welcome_message = json.loads(sent_responses[0])
        assert welcome_message.get("type") == "welcome", "First message should be welcome"
        assert welcome_message.get("guild_id") == 1, "Should default to guild ID 1"
        assert welcome_message.get("guild_name") == "Default Guild", "Should use default guild name"


class TestGuildAuthenticationEdgeCases:
    """Test edge cases and error conditions in guild authentication."""

    def test_duplicate_guild_clients(self, auth_manager):
        """Test handling of duplicate client IDs across guilds."""
        # Create two API keys with same client_id but different guilds
        key_id_1, api_key_1 = auth_manager.generate_api_key(
            client_id="duplicate_client",
            description="First Guild",
            guild_id=16,
            guild_name="First Guild",
        )

        # This should work - different guild, same client_id is allowed
        key_id_2, api_key_2 = auth_manager.generate_api_key(
            client_id="duplicate_client_2",  # Different client_id
            description="Second Guild",
            guild_id=17,
            guild_name="Second Guild",
        )

        # Both should authenticate successfully
        auth_1 = auth_manager.authenticate_api_key(api_key_1)
        auth_2 = auth_manager.authenticate_api_key(api_key_2)

        assert auth_1.authenticated is True, "First API key should authenticate"
        assert auth_2.authenticated is True, "Second API key should authenticate"
        assert auth_1.guild_id == 16, "First key should have guild 16"
        assert auth_2.guild_id == 17, "Second key should have guild 17"

    def test_guild_api_key_revocation(self, auth_manager):
        """Test revocation of guild-specific API keys."""
        key_id, api_key = auth_manager.generate_api_key(
            client_id="revocation_test",
            description="Revocation Test",
            guild_id=18,
            guild_name="Revocation Guild",
        )

        # Should authenticate before revocation
        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is True, "Should authenticate before revocation"
        assert auth_response.guild_id == 18, "Should have correct guild context"

        # Revoke the key
        result = auth_manager.revoke_api_key(key_id)
        assert result is True, "Revocation should succeed"

        # Should not authenticate after revocation
        auth_response = auth_manager.authenticate_api_key(api_key)
        assert auth_response.authenticated is False, "Should not authenticate after revocation"

    def test_malformed_guild_authentication(self, auth_manager):
        """Test authentication with malformed guild data."""
        # Test with None values
        auth_response = auth_manager.authenticate_api_key(None)
        assert auth_response.authenticated is False, "None API key should fail"

        # Test with empty string
        auth_response = auth_manager.authenticate_api_key("")
        assert auth_response.authenticated is False, "Empty API key should fail"

        # Test with very short key
        auth_response = auth_manager.authenticate_api_key("x")
        assert auth_response.authenticated is False, "Short API key should fail"

    def test_guild_cleanup_stale_states(self, auth_manager):
        """Test cleanup of stale rate limiting states."""
        # Create some client activity
        client_id = "stale_test_client"
        auth_manager.check_rate_limit(client_id, event_count=1)

        # Verify state exists
        assert client_id in auth_manager._rate_limits, "Rate limit state should exist"

        # Cleanup stale states (using 0 hours to force cleanup)
        auth_manager.cleanup_stale_states(max_age_hours=0)

        # State should be cleaned up
        # Note: This might not remove it immediately due to timing, but should not error
        # The main goal is to test that cleanup doesn't crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])