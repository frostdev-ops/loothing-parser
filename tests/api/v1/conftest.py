"""
Pytest configuration for API v1 tests.

Provides fixtures for database setup, authentication, and test data
for comprehensive API testing.
"""

import pytest
import asyncio
from typing import Dict, Any, Generator
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.api.v1.main import create_v1_app
from src.database.schema import DatabaseManager
from src.api.auth import AuthResponse


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db() -> DatabaseManager:
    """Create a mock database manager for testing."""
    db_mock = MagicMock(spec=DatabaseManager)

    # Mock async methods
    db_mock.get_character_profile = AsyncMock()
    db_mock.list_characters = AsyncMock()
    db_mock.get_character_performance = AsyncMock()
    db_mock.get_encounter_details = AsyncMock()
    db_mock.list_encounters = AsyncMock()
    db_mock.get_encounter_summary = AsyncMock()
    db_mock.get_performance_trends = AsyncMock()
    db_mock.execute_search = AsyncMock()
    db_mock.execute_aggregation = AsyncMock()

    return db_mock


@pytest.fixture
def mock_auth() -> AuthResponse:
    """Create a mock authentication response for testing."""
    return AuthResponse(
        authenticated=True,
        user_id="test_user_123",
        permissions=["read", "write", "admin"],
        rate_limit_tier="premium",
        message="Authentication successful"
    )


@pytest.fixture
def api_client(mock_db: DatabaseManager) -> TestClient:
    """Create a test client for the API with mocked dependencies."""
    app = create_v1_app(mock_db)

    # Override authentication dependency for testing
    def override_auth():
        return AuthResponse(
            authenticated=True,
            user_id="test_user_123",
            permissions=["read", "write", "admin"],
            rate_limit_tier="premium"
        )

    from src.api.v1.dependencies import get_authenticated_user
    app.dependency_overrides[get_authenticated_user] = override_auth

    return TestClient(app)


@pytest.fixture
async def async_client(mock_db: DatabaseManager) -> AsyncClient:
    """Create an async test client for testing async endpoints."""
    app = create_v1_app(mock_db)

    # Override authentication
    def override_auth():
        return AuthResponse(
            authenticated=True,
            user_id="test_user_123",
            permissions=["read", "write", "admin"],
            rate_limit_tier="premium"
        )

    from src.api.v1.dependencies import get_authenticated_user
    app.dependency_overrides[get_authenticated_user] = override_auth

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_character_data() -> Dict[str, Any]:
    """Provide sample character data for testing."""
    return {
        "id": 1,
        "name": "Thrall",
        "server": "Stormrage",
        "class_name": "Shaman",
        "spec_name": "Enhancement",
        "level": 80,
        "guild_name": "Earthen Ring",
        "faction": "Horde",
        "race": "Orc",
        "gender": "Male",
        "first_seen": "2024-01-01T10:00:00Z",
        "last_seen": "2024-01-15T22:30:00Z",
        "total_encounters": 45,
        "avg_item_level": 489.5,
        "is_active": True,
        "performance_summary": {
            "avg_dps": 125000.5,
            "avg_hps": 15000.2,
            "avg_dtps": 8500.1,
            "best_dps": 180000.0,
            "best_hps": 25000.0,
            "survival_rate": 92.5,
            "activity_percentage": 87.3,
            "parse_percentile": 75.2
        }
    }


@pytest.fixture
def sample_encounter_data() -> Dict[str, Any]:
    """Provide sample encounter data for testing."""
    return {
        "id": 12345,
        "boss_name": "Fyrakk the Blazing",
        "encounter_type": "raid",
        "difficulty": "heroic",
        "start_time": "2024-01-15T20:30:00Z",
        "end_time": "2024-01-15T20:38:25Z",
        "duration": 505.0,
        "success": True,
        "wipe_percentage": None,
        "raid_size": 20,
        "guild_name": "Earthen Ring",
        "zone_name": "Amirdrassil, the Dream's Hope",
        "keystone_level": None,
        "affixes": [],
        "total_damage": 125000000,
        "total_healing": 35000000,
        "participants": [
            {
                "character_name": "Thrall",
                "class_name": "Shaman",
                "spec_name": "Enhancement",
                "role": "dps",
                "dps": 142500.5,
                "hps": 12000.2,
                "dtps": 8500.1,
                "damage_done": 71963752,
                "healing_done": 6060101,
                "damage_taken": 4292551,
                "deaths": 0,
                "interrupts": 3,
                "dispels": 1,
                "activity_percentage": 89.5,
                "item_level": 489.5
            }
        ]
    }


@pytest.fixture
def sample_performance_data() -> Dict[str, Any]:
    """Provide sample performance data for testing."""
    return {
        "character_name": "Thrall",
        "encounter_id": 12345,
        "encounter_name": "Fyrakk the Blazing",
        "difficulty": "heroic",
        "date": "2024-01-15T20:30:00Z",
        "duration": 505.0,
        "dps": 142500.5,
        "hps": 12000.2,
        "dtps": 8500.1,
        "damage_done": 71963752,
        "healing_done": 6060101,
        "damage_taken": 4292551,
        "deaths": 0,
        "interrupts": 3,
        "dispels": 1,
        "activity_percentage": 89.5,
        "parse_percentile": 75.2,
        "item_level": 489.5
    }


@pytest.fixture
def sample_search_data() -> Dict[str, Any]:
    """Provide sample search results for testing."""
    return {
        "results": [
            {
                "item_type": "character",
                "item_id": "1",
                "title": "Thrall - Enhancement Shaman",
                "description": "Level 80 Enhancement Shaman from Earthen Ring on Stormrage",
                "relevance_score": 0.95,
                "highlights": {
                    "name": ["<mark>Thrall</mark>"],
                    "class_name": ["<mark>Shaman</mark>"]
                },
                "data": {
                    "name": "Thrall",
                    "class_name": "Shaman",
                    "guild_name": "Earthen Ring"
                }
            }
        ],
        "total_count": 1,
        "query_time_ms": 15.5,
        "suggestions": [],
        "facets": {
            "class_name": {"Shaman": 1},
            "guild_name": {"Earthen Ring": 1}
        }
    }


@pytest.fixture
def sample_aggregation_data() -> Dict[str, Any]:
    """Provide sample aggregation results for testing."""
    return {
        "data": [
            {
                "class_name": "Shaman",
                "dps_avg": 125000.5,
                "dps_min": 80000.0,
                "dps_max": 180000.0,
                "dps_count": 45,
                "dps_p50": 120000.0,
                "dps_p75": 140000.0,
                "dps_p90": 160000.0,
                "dps_p95": 170000.0,
                "dps_p99": 175000.0
            }
        ],
        "metadata": {
            "total_rows": 1,
            "metrics": ["dps"],
            "group_by": ["class_name"],
            "functions": ["avg", "min", "max", "count"],
            "generated_at": "2024-01-15T10:30:00Z"
        }
    }


@pytest.fixture
def valid_headers() -> Dict[str, str]:
    """Provide valid authentication headers for API requests."""
    return {
        "Authorization": "Bearer test_api_key_123",
        "Content-Type": "application/json"
    }


@pytest.fixture
def invalid_headers() -> Dict[str, str]:
    """Provide invalid authentication headers for testing auth failures."""
    return {
        "Authorization": "Bearer invalid_key",
        "Content-Type": "application/json"
    }


@pytest.fixture
def rate_limited_headers() -> Dict[str, str]:
    """Provide headers that will trigger rate limiting for testing."""
    return {
        "Authorization": "Bearer rate_limited_key",
        "Content-Type": "application/json"
    }


@pytest.fixture
def pagination_params() -> Dict[str, Any]:
    """Provide standard pagination parameters for testing."""
    return {
        "limit": 20,
        "offset": 0
    }


@pytest.fixture
def time_range_params() -> Dict[str, Any]:
    """Provide time range parameters for testing."""
    return {
        "days": 30,
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-01-31T23:59:59Z"
    }


@pytest.fixture
def filter_params() -> Dict[str, Any]:
    """Provide filter parameters for testing."""
    return {
        "class_name": "Shaman",
        "guild": "Earthen Ring",
        "encounter_type": "raid",
        "difficulty": "heroic",
        "server": "Stormrage"
    }


@pytest.fixture(autouse=True)
def reset_mocks(mock_db: DatabaseManager):
    """Reset all mocks after each test."""
    yield
    mock_db.reset_mock()


class APITestClient:
    """Helper class for API testing with common methods."""

    def __init__(self, client: TestClient):
        self.client = client

    def assert_success_response(self, response, expected_status=200):
        """Assert that response is successful with expected format."""
        assert response.status_code == expected_status
        data = response.json()
        assert isinstance(data, dict)
        return data

    def assert_error_response(self, response, expected_status):
        """Assert that response is an error with expected format."""
        assert response.status_code == expected_status
        data = response.json()
        assert "error" in data
        assert "message" in data
        assert "code" in data
        return data

    def assert_paginated_response(self, response, expected_status=200):
        """Assert that response is a properly formatted paginated response."""
        data = self.assert_success_response(response, expected_status)
        assert "data" in data
        assert "pagination" in data
        assert isinstance(data["data"], list)

        pagination = data["pagination"]
        assert "total" in pagination
        assert "limit" in pagination
        assert "offset" in pagination
        assert "has_next" in pagination
        assert "has_previous" in pagination

        return data


@pytest.fixture
def api_test_client(api_client: TestClient) -> APITestClient:
    """Provide helper test client with assertion methods."""
    return APITestClient(api_client)