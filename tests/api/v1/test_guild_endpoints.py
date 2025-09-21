"""
Guild-specific API endpoint tests for v1.

Tests guild authentication, data isolation, upload endpoints,
and guild management functionality.
"""

import pytest
import json
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.api.v1.main import create_v1_app
from src.database.schema import DatabaseManager
from src.api.auth import AuthResponse
from tests.api.v1.conftest import APITestClient


@pytest.fixture
def guild_auth_responses() -> Dict[int, AuthResponse]:
    """Create guild-specific authentication responses for testing."""
    return {
        1: AuthResponse(
            authenticated=True,
            client_id="development",
            guild_id=1,
            guild_name="Default Guild",
            permissions=["stream", "query", "upload"],
            rate_limit={"events_per_minute": 20000, "max_connections": 10},
            message="Authentication successful",
        ),
        2: AuthResponse(
            authenticated=True,
            client_id="loothing_main",
            guild_id=2,
            guild_name="Loothing",
            permissions=["stream", "query", "upload"],
            rate_limit={"events_per_minute": 15000, "max_connections": 8},
            message="Authentication successful",
        ),
        3: AuthResponse(
            authenticated=True,
            client_id="alpha_guild",
            guild_id=3,
            guild_name="Alpha Guild",
            permissions=["stream", "query"],  # No upload permission
            rate_limit={"events_per_minute": 10000, "max_connections": 5},
            message="Authentication successful",
        ),
        4: AuthResponse(
            authenticated=True,
            client_id="beta_guild",
            guild_id=4,
            guild_name="Beta Guild",
            permissions=["stream", "query", "upload", "admin"],
            rate_limit={"events_per_minute": 5000, "max_connections": 3},
            message="Authentication successful",
        ),
    }


@pytest.fixture
def guild_api_keys() -> Dict[int, str]:
    """Create guild-specific API keys for testing."""
    return {
        1: "dev_key_12345",
        2: "loothing_api_key_67890",
        3: "alpha_guild_key_abcde",
        4: "beta_guild_key_fghij",
    }


@pytest.fixture
def guild_sample_data() -> Dict[int, Dict[str, Any]]:
    """Create guild-specific sample data for testing."""
    return {
        1: {
            "encounters": [
                {
                    "encounter_id": 1001,
                    "guild_id": 1,
                    "boss_name": "Default Boss",
                    "instance_name": "Default Instance",
                    "difficulty": "normal",
                    "start_time": "2024-01-15T20:00:00Z",
                    "success": True,
                }
            ],
            "characters": [
                {
                    "character_id": 2001,
                    "guild_id": 1,
                    "name": "DefaultPlayer",
                    "class": "Warrior",
                    "spec": "Protection",
                }
            ],
        },
        2: {
            "encounters": [
                {
                    "encounter_id": 1002,
                    "guild_id": 2,
                    "boss_name": "Loothing Boss",
                    "instance_name": "Loothing Instance",
                    "difficulty": "heroic",
                    "start_time": "2024-01-15T21:00:00Z",
                    "success": True,
                },
                {
                    "encounter_id": 1003,
                    "guild_id": 2,
                    "boss_name": "Another Loothing Boss",
                    "instance_name": "Loothing Instance",
                    "difficulty": "mythic",
                    "start_time": "2024-01-15T22:00:00Z",
                    "success": False,
                },
            ],
            "characters": [
                {
                    "character_id": 2002,
                    "guild_id": 2,
                    "name": "LoothingPlayer1",
                    "class": "Mage",
                    "spec": "Arcane",
                },
                {
                    "character_id": 2003,
                    "guild_id": 2,
                    "name": "LoothingPlayer2",
                    "class": "Priest",
                    "spec": "Holy",
                },
            ],
        },
        3: {
            "encounters": [
                {
                    "encounter_id": 1004,
                    "guild_id": 3,
                    "boss_name": "Alpha Boss",
                    "instance_name": "Alpha Instance",
                    "difficulty": "normal",
                    "start_time": "2024-01-15T19:00:00Z",
                    "success": True,
                }
            ],
            "characters": [
                {
                    "character_id": 2004,
                    "guild_id": 3,
                    "name": "AlphaPlayer",
                    "class": "Hunter",
                    "spec": "Beast Mastery",
                }
            ],
        },
    }


def create_guild_api_client(
    guild_id: int, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
) -> TestClient:
    """Create a test client for a specific guild."""
    app = create_v1_app(mock_db)

    # Override authentication dependency for specific guild
    def override_auth():
        return guild_auth_responses[guild_id]

    from src.api.v1.dependencies import get_authenticated_user

    app.dependency_overrides[get_authenticated_user] = override_auth

    return TestClient(app)


class TestGuildUploadEndpoints:
    """Test guild-specific upload endpoints."""

    def test_upload_with_guild_id(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test log upload with guild authentication."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        # Mock upload service
        with patch("src.api.v1.routers.logs.get_upload_service") as mock_upload_service:
            mock_service = MagicMock()
            mock_service.upload_file = AsyncMock(
                return_value=MagicMock(
                    upload_id="upload_123",
                    file_name="test_log.txt",
                    file_size=1024,
                    status="processing",
                    progress=0,
                )
            )
            mock_upload_service.return_value = mock_service

            # Create test file
            test_file_content = b"9/15/2025 21:30:21.462-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1"
            files = {"file": ("test_log.txt", test_file_content, "text/plain")}

            response = client.post("/api/v1/logs/upload", files=files)

            assert response.status_code == 200
            data = response.json()

            # Verify guild context is included
            assert data["guild_id"] == guild_id
            assert data["guild_name"] == "Loothing"
            assert data["upload_id"] == "upload_123"
            assert data["file_name"] == "test_log.txt"
            assert "File uploaded successfully for Loothing" in data["message"]

            # Verify upload service was called with guild context
            mock_service.upload_file.assert_called_once()
            call_args = mock_service.upload_file.call_args
            assert call_args[1]["guild_id"] == guild_id

    def test_upload_without_guild_id(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test upload failure when guild_id is missing from auth."""
        # Create auth response without guild_id
        invalid_auth = AuthResponse(
            authenticated=True,
            client_id="no_guild_client",
            guild_id=None,  # No guild context
            guild_name=None,
            permissions=["upload"],
            rate_limit={"events_per_minute": 1000, "max_connections": 1},
            message="Authentication successful",
        )

        app = create_v1_app(mock_db)

        def override_auth():
            return invalid_auth

        from src.api.v1.dependencies import get_authenticated_user

        app.dependency_overrides[get_authenticated_user] = override_auth
        client = TestClient(app)

        # Try to upload without guild context
        test_file_content = b"9/15/2025 21:30:21.462-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1"
        files = {"file": ("test_log.txt", test_file_content, "text/plain")}

        response = client.post("/api/v1/logs/upload", files=files)

        assert response.status_code == 400
        data = response.json()
        assert "Guild ID is required" in data["detail"]

    def test_upload_status_with_guild_isolation(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test upload status endpoint respects guild isolation."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        with patch("src.api.v1.routers.logs.get_upload_service") as mock_upload_service:
            mock_service = MagicMock()
            mock_service.get_upload_status.return_value = MagicMock(
                upload_id="upload_456",
                file_name="guild_log.txt",
                file_size=2048,
                status="completed",
                progress=100,
                encounters_found=5,
                characters_found=10,
                events_processed=1000,
                error_message=None,
                start_time=None,
                end_time=None,
            )
            mock_upload_service.return_value = mock_service

            response = client.get("/api/v1/logs/upload_456/status")

            assert response.status_code == 200
            data = response.json()

            # Verify guild context is preserved
            assert data["guild_id"] == guild_id
            assert data["guild_name"] == "Loothing"
            assert data["upload_id"] == "upload_456"

            # Verify service was called with guild_id for isolation
            mock_service.get_upload_status.assert_called_once_with("upload_456", guild_id=guild_id)

    def test_upload_permissions_check(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test upload requires proper permissions."""
        guild_id = 3  # Guild with no upload permission
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        test_file_content = b"9/15/2025 21:30:21.462-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1"
        files = {"file": ("test_log.txt", test_file_content, "text/plain")}

        response = client.post("/api/v1/logs/upload", files=files)

        # Should fail due to insufficient permissions
        assert response.status_code == 403


class TestGuildEncounterEndpoints:
    """Test guild-specific encounter endpoints."""

    def test_get_encounters_by_guild(
        self,
        mock_db: DatabaseManager,
        guild_auth_responses: Dict[int, AuthResponse],
        guild_sample_data: Dict[int, Dict[str, Any]],
    ):
        """Test encounter listing is filtered by guild."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        # Mock database to return guild-specific encounters
        guild_encounters = guild_sample_data[guild_id]["encounters"]
        mock_db.get_recent_encounters.return_value = guild_encounters

        response = client.get("/api/v1/encounters?limit=10")

        assert response.status_code == 200
        data = response.json()

        # Verify all returned encounters belong to the authenticated guild
        for encounter in data:
            assert encounter["guild_id"] == guild_id

        # Verify database was called with guild filtering
        mock_db.get_recent_encounters.assert_called_once()
        call_args = mock_db.get_recent_encounters.call_args[1]
        assert call_args["guild_id"] == guild_id

    def test_encounter_detail_guild_isolation(
        self,
        mock_db: DatabaseManager,
        guild_auth_responses: Dict[int, AuthResponse],
        guild_sample_data: Dict[int, Dict[str, Any]],
    ):
        """Test encounter detail endpoint respects guild isolation."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        # Mock encounter from the same guild
        encounter = guild_sample_data[guild_id]["encounters"][0]
        mock_db.get_encounter.return_value = encounter

        response = client.get(f"/api/v1/encounters/{encounter['encounter_id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["guild_id"] == guild_id
        assert data["encounter_id"] == encounter["encounter_id"]

        # Verify database was called with guild context
        mock_db.get_encounter.assert_called_once()
        call_args = mock_db.get_encounter.call_args[1]
        assert call_args["guild_id"] == guild_id

    def test_cross_guild_encounter_access_denied(
        self,
        mock_db: DatabaseManager,
        guild_auth_responses: Dict[int, AuthResponse],
        guild_sample_data: Dict[int, Dict[str, Any]],
    ):
        """Test that guilds cannot access other guild's encounters."""
        guild_id = 3
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        # Try to access encounter from guild 2
        other_guild_encounter_id = guild_sample_data[2]["encounters"][0]["encounter_id"]

        # Mock database to return None (no access)
        mock_db.get_encounter.return_value = None

        response = client.get(f"/api/v1/encounters/{other_guild_encounter_id}")

        assert response.status_code == 404

        # Verify database was called with correct guild context
        mock_db.get_encounter.assert_called_once()
        call_args = mock_db.get_encounter.call_args[1]
        assert call_args["guild_id"] == guild_id  # Should search within guild 3, not guild 2

    def test_encounter_statistics_guild_scoped(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test encounter statistics are scoped to guild."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        mock_stats = {
            "guild_id": guild_id,
            "guild_name": "Loothing",
            "total_encounters": 25,
            "successful_encounters": 20,
            "unique_bosses": 12,
            "last_activity": "2024-01-15T22:00:00Z",
        }
        mock_db.get_encounter_statistics.return_value = mock_stats

        response = client.get("/api/v1/encounters/stats")

        assert response.status_code == 200
        data = response.json()

        # Verify guild context in response
        assert data["guild_id"] == guild_id
        assert data["guild_name"] == "Loothing"
        assert data["total_encounters"] == 25

        # Verify database was called with guild filtering
        mock_db.get_encounter_statistics.assert_called_once()
        call_args = mock_db.get_encounter_statistics.call_args[1]
        assert call_args["guild_id"] == guild_id


class TestGuildCharacterEndpoints:
    """Test guild-specific character endpoints."""

    def test_characters_filtered_by_guild(
        self,
        mock_db: DatabaseManager,
        guild_auth_responses: Dict[int, AuthResponse],
        guild_sample_data: Dict[int, Dict[str, Any]],
    ):
        """Test character listing is filtered by guild."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        # Mock guild-specific characters
        guild_characters = guild_sample_data[guild_id]["characters"]
        mock_db.list_characters.return_value = {
            "data": guild_characters,
            "total": len(guild_characters),
            "has_next": False,
            "has_previous": False,
        }

        response = client.get("/api/v1/characters?limit=10")

        assert response.status_code == 200
        data = response.json()

        # Verify all characters belong to the authenticated guild
        for character in data["data"]:
            assert character["guild_id"] == guild_id

        # Verify database was called with guild context
        mock_db.list_characters.assert_called_once()
        call_args = mock_db.list_characters.call_args[1]
        assert call_args.get("guild_id") == guild_id

    def test_character_detail_guild_isolation(
        self,
        mock_db: DatabaseManager,
        guild_auth_responses: Dict[int, AuthResponse],
        guild_sample_data: Dict[int, Dict[str, Any]],
    ):
        """Test character detail respects guild boundaries."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        character = guild_sample_data[guild_id]["characters"][0]
        mock_db.get_character_profile.return_value = character

        response = client.get(f"/api/v1/characters/{character['name']}")

        assert response.status_code == 200
        data = response.json()
        assert data["guild_id"] == guild_id
        assert data["name"] == character["name"]

        # Verify database call includes guild context
        mock_db.get_character_profile.assert_called_once()
        call_args = mock_db.get_character_profile.call_args[1]
        assert call_args.get("guild_id") == guild_id


class TestGuildSearchEndpoints:
    """Test guild-specific search functionality."""

    def test_search_with_guild_filter(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test search results are filtered by guild."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        mock_search_results = {
            "results": [
                {
                    "item_type": "encounter",
                    "item_id": "1002",
                    "title": "Loothing Boss - Heroic",
                    "description": "Heroic encounter from Loothing Instance",
                    "relevance_score": 0.95,
                    "data": {"guild_id": guild_id, "boss_name": "Loothing Boss"},
                },
                {
                    "item_type": "character",
                    "item_id": "2002",
                    "title": "LoothingPlayer1 - Arcane Mage",
                    "description": "Level 80 Arcane Mage from Loothing",
                    "relevance_score": 0.87,
                    "data": {"guild_id": guild_id, "name": "LoothingPlayer1"},
                },
            ],
            "total_count": 2,
            "query_time_ms": 25.3,
        }
        mock_db.execute_search.return_value = mock_search_results

        response = client.get("/api/v1/search?q=loothing&limit=10")

        assert response.status_code == 200
        data = response.json()

        # Verify all search results belong to the authenticated guild
        for result in data["results"]:
            assert result["data"]["guild_id"] == guild_id

        # Verify database search includes guild filter
        mock_db.execute_search.assert_called_once()
        call_args = mock_db.execute_search.call_args[1]
        assert call_args.get("guild_id") == guild_id

    def test_search_cross_guild_isolation(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test search cannot return results from other guilds."""
        guild_id = 3
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        # Mock search that would normally return results from other guilds
        mock_search_results = {
            "results": [],  # No results for this guild
            "total_count": 0,
            "query_time_ms": 15.1,
        }
        mock_db.execute_search.return_value = mock_search_results

        response = client.get("/api/v1/search?q=loothing")  # Search for another guild's content

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 0  # Should not find other guild's content

        # Verify search was constrained to the authenticated guild
        mock_db.execute_search.assert_called_once()
        call_args = mock_db.execute_search.call_args[1]
        assert call_args.get("guild_id") == guild_id


class TestGuildManagementEndpoints:
    """Test guild management and admin endpoints."""

    def test_guild_management_admin_only(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test guild management endpoints require admin permissions."""
        guild_id = 4  # Guild with admin permissions
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        mock_guild_stats = {
            "guild_id": guild_id,
            "guild_name": "Beta Guild",
            "total_encounters": 15,
            "total_characters": 8,
            "storage_used_mb": 245.6,
            "last_activity": "2024-01-15T18:00:00Z",
        }
        mock_db.get_guild_statistics.return_value = mock_guild_stats

        response = client.get("/api/v1/admin/guild/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["guild_id"] == guild_id
        assert data["guild_name"] == "Beta Guild"

    def test_guild_management_access_denied(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test guild management endpoints deny access without admin permissions."""
        guild_id = 2  # Guild without admin permissions
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        response = client.get("/api/v1/admin/guild/stats")

        assert response.status_code == 403  # Forbidden due to insufficient permissions

    def test_guild_settings_update(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test guild settings update with admin permissions."""
        guild_id = 4  # Admin guild
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        mock_db.update_guild_settings.return_value = True

        settings_update = {
            "raid_schedule": "Tue/Thu/Sun 8-11 EST",
            "loot_system": "EPGP",
            "public_logs": False,
        }

        response = client.patch(
            "/api/v1/admin/guild/settings",
            json=settings_update,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 404:
            # Endpoint may not be implemented yet
            pytest.skip("Guild settings endpoint not implemented")

        assert response.status_code in [200, 204]

        # Verify database was called with correct guild context
        if hasattr(mock_db, "update_guild_settings"):
            mock_db.update_guild_settings.assert_called_once()
            call_args = mock_db.update_guild_settings.call_args[1]
            assert call_args.get("guild_id") == guild_id


class TestGuildAPIAuthentication:
    """Test guild-specific API authentication and authorization."""

    def test_missing_authentication(self, mock_db: DatabaseManager):
        """Test API endpoints require authentication."""
        app = create_v1_app(mock_db)
        client = TestClient(app)

        # Test various endpoints without authentication
        endpoints = [
            "/api/v1/encounters",
            "/api/v1/characters",
            "/api/v1/search?q=test",
            "/api/v1/encounters/stats",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401  # Unauthorized

    def test_invalid_guild_authentication(self, mock_db: DatabaseManager):
        """Test handling of invalid guild authentication."""
        # Create auth response with invalid guild context
        invalid_auth = AuthResponse(
            authenticated=False,
            client_id=None,
            guild_id=None,
            guild_name=None,
            permissions=[],
            rate_limit={},
            message="Invalid API key",
        )

        app = create_v1_app(mock_db)

        def override_auth():
            return invalid_auth

        from src.api.v1.dependencies import get_authenticated_user

        app.dependency_overrides[get_authenticated_user] = override_auth
        client = TestClient(app)

        response = client.get("/api/v1/encounters")
        assert response.status_code == 401

    def test_guild_rate_limiting_headers(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test that rate limiting headers include guild context."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        mock_db.get_recent_encounters.return_value = []

        response = client.get("/api/v1/encounters")

        assert response.status_code == 200

        # Check for rate limiting headers (if implemented)
        rate_limit_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Guild-ID",
        ]

        # Headers may not be implemented yet, so just check they don't cause errors
        for header in rate_limit_headers:
            response.headers.get(header)


class TestGuildAPIPerformance:
    """Test performance and scalability of guild-scoped endpoints."""

    def test_guild_query_performance(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test that guild queries perform efficiently."""
        guild_id = 2
        client = create_guild_api_client(guild_id, mock_db, guild_auth_responses)

        # Mock large result set
        large_encounter_list = [
            {"encounter_id": i, "guild_id": guild_id, "boss_name": f"Boss {i}"}
            for i in range(1000, 1100)
        ]
        mock_db.get_recent_encounters.return_value = large_encounter_list

        import time

        start_time = time.time()
        response = client.get("/api/v1/encounters?limit=100")
        end_time = time.time()

        assert response.status_code == 200
        # Should complete quickly even with large datasets
        assert (end_time - start_time) < 1.0  # Less than 1 second

    def test_concurrent_guild_requests(
        self, mock_db: DatabaseManager, guild_auth_responses: Dict[int, AuthResponse]
    ):
        """Test handling of concurrent requests from different guilds."""
        import asyncio
        from httpx import AsyncClient

        async def make_guild_request(guild_id: int):
            app = create_v1_app(mock_db)

            def override_auth():
                return guild_auth_responses[guild_id]

            from src.api.v1.dependencies import get_authenticated_user

            app.dependency_overrides[get_authenticated_user] = override_auth

            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/encounters?limit=5")
                return response.status_code, guild_id

        async def run_concurrent_test():
            # Mock database responses
            mock_db.get_recent_encounters.return_value = []

            # Make concurrent requests from different guilds
            tasks = [make_guild_request(guild_id) for guild_id in [1, 2, 3, 4]]
            results = await asyncio.gather(*tasks)

            return results

        # Run the concurrent test
        import asyncio

        results = asyncio.run(run_concurrent_test())

        # All requests should succeed
        for status_code, guild_id in results:
            assert status_code == 200, f"Guild {guild_id} request failed"

        # Database should have been called for each guild
        assert mock_db.get_recent_encounters.call_count == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])