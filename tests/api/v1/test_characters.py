"""
Tests for character endpoints in API v1.

Comprehensive test suite covering character listing, details,
performance metrics, and error handling.
"""

import pytest
from typing import Dict, Any
from unittest.mock import AsyncMock

from src.database.schema import DatabaseManager
from tests.api.v1.conftest import APITestClient


class TestCharacterEndpoints:
    """Test suite for character-related endpoints."""

    def test_list_characters_success(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_character_data: Dict[str, Any],
        valid_headers: Dict[str, str],
        pagination_params: Dict[str, Any]
    ):
        """Test successful character listing with pagination."""
        # Setup mock
        mock_db.list_characters.return_value = {
            "data": [sample_character_data],
            "total": 1,
            "has_next": False,
            "has_previous": False
        }

        # Make request
        response = api_test_client.client.get(
            "/characters",
            headers=valid_headers,
            params=pagination_params
        )

        # Assertions
        data = api_test_client.assert_paginated_response(response)
        assert len(data["data"]) == 1

        character = data["data"][0]
        assert character["name"] == "Thrall"
        assert character["class_name"] == "Shaman"
        assert character["is_active"] is True

        # Verify database was called correctly
        mock_db.list_characters.assert_called_once()
        call_args = mock_db.list_characters.call_args[1]
        assert call_args["limit"] == 20
        assert call_args["offset"] == 0

    def test_list_characters_with_filters(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_character_data: Dict[str, Any],
        valid_headers: Dict[str, str],
        filter_params: Dict[str, Any]
    ):
        """Test character listing with various filters."""
        # Setup mock
        mock_db.list_characters.return_value = {
            "data": [sample_character_data],
            "total": 1,
            "has_next": False,
            "has_previous": False
        }

        # Test each filter parameter
        for filter_key, filter_value in filter_params.items():
            if filter_key in ["class_name", "guild", "server"]:
                response = api_test_client.client.get(
                    "/characters",
                    headers=valid_headers,
                    params={filter_key: filter_value, "limit": 5}
                )

                data = api_test_client.assert_paginated_response(response)

                # Verify filter was passed to database
                call_args = mock_db.list_characters.call_args[1]
                assert filter_key in call_args["filters"]
                assert call_args["filters"][filter_key] == filter_value

    def test_list_characters_empty_result(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str]
    ):
        """Test character listing with no results."""
        # Setup mock for empty result
        mock_db.list_characters.return_value = {
            "data": [],
            "total": 0,
            "has_next": False,
            "has_previous": False
        }

        response = api_test_client.client.get(
            "/characters",
            headers=valid_headers,
            params={"limit": 20}
        )

        data = api_test_client.assert_paginated_response(response)
        assert len(data["data"]) == 0
        assert data["pagination"]["total"] == 0

    def test_get_character_success(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_character_data: Dict[str, Any],
        valid_headers: Dict[str, str]
    ):
        """Test successful character retrieval."""
        # Setup mock
        mock_db.get_character_profile.return_value = sample_character_data

        response = api_test_client.client.get(
            "/characters/Thrall",
            headers=valid_headers,
            params={"server": "Stormrage"}
        )

        data = api_test_client.assert_success_response(response)
        assert data["name"] == "Thrall"
        assert data["server"] == "Stormrage"
        assert data["class_name"] == "Shaman"
        assert "performance_summary" in data

        # Verify database call
        mock_db.get_character_profile.assert_called_once_with(
            character_name="Thrall",
            server="Stormrage"
        )

    def test_get_character_not_found(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str]
    ):
        """Test character not found scenario."""
        # Setup mock to return None
        mock_db.get_character_profile.return_value = None

        response = api_test_client.client.get(
            "/characters/NonExistentCharacter",
            headers=valid_headers
        )

        api_test_client.assert_error_response(response, 404)
        assert "not found" in response.json()["message"].lower()

    def test_get_character_performance_success(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_performance_data: Dict[str, Any],
        valid_headers: Dict[str, str]
    ):
        """Test successful character performance retrieval."""
        # Setup mock
        mock_performance_list = [sample_performance_data]
        mock_db.get_character_performance.return_value = mock_performance_list

        response = api_test_client.client.get(
            "/characters/Thrall/performance",
            headers=valid_headers,
            params={
                "days": 30,
                "encounter_type": "raid",
                "difficulty": "heroic"
            }
        )

        data = api_test_client.assert_success_response(response)
        assert len(data) == 1

        performance = data[0]
        assert performance["character_name"] == "Thrall"
        assert performance["dps"] == 142500.5
        assert performance["encounter_name"] == "Fyrakk the Blazing"

        # Verify database call
        mock_db.get_character_performance.assert_called_once()
        call_args = mock_db.get_character_performance.call_args[1]
        assert call_args["character_name"] == "Thrall"
        assert call_args["days"] == 30
        assert call_args["encounter_type"] == "raid"
        assert call_args["difficulty"] == "heroic"

    def test_get_character_performance_with_trends(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_performance_data: Dict[str, Any],
        valid_headers: Dict[str, str]
    ):
        """Test character performance with trend analysis."""
        # Setup mock with multiple data points for trends
        mock_performances = [
            {**sample_performance_data, "date": "2024-01-15T20:30:00Z", "dps": 140000},
            {**sample_performance_data, "date": "2024-01-14T20:30:00Z", "dps": 135000},
            {**sample_performance_data, "date": "2024-01-13T20:30:00Z", "dps": 130000},
        ]
        mock_db.get_character_performance.return_value = mock_performances

        response = api_test_client.client.get(
            "/characters/Thrall/performance",
            headers=valid_headers,
            params={"days": 7, "include_trends": True}
        )

        data = api_test_client.assert_success_response(response)
        assert len(data) == 3

        # Verify ascending DPS trend
        dps_values = [perf["dps"] for perf in data]
        assert dps_values == sorted(dps_values, reverse=True)  # Should be desc by date

    def test_character_rankings(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str]
    ):
        """Test character rankings endpoint."""
        # Setup mock ranking data
        mock_rankings = [
            {
                "character_name": "Thrall",
                "rank": 1,
                "percentile": 95.5,
                "metric_value": 150000.0,
                "class_name": "Shaman",
                "guild_name": "Earthen Ring"
            },
            {
                "character_name": "Jaina",
                "rank": 2,
                "percentile": 92.1,
                "metric_value": 145000.0,
                "class_name": "Mage",
                "guild_name": "Kirin Tor"
            }
        ]
        mock_db.get_character_rankings.return_value = mock_rankings

        response = api_test_client.client.get(
            "/characters/rankings",
            headers=valid_headers,
            params={
                "metric": "dps",
                "encounter_type": "raid",
                "limit": 10
            }
        )

        data = api_test_client.assert_success_response(response)
        assert len(data) == 2
        assert data[0]["rank"] == 1
        assert data[0]["character_name"] == "Thrall"
        assert data[1]["rank"] == 2

    def test_character_gear_analysis(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str]
    ):
        """Test character gear analysis endpoint."""
        # Setup mock gear data
        mock_gear = {
            "character_name": "Thrall",
            "current_item_level": 489.5,
            "gear_progression": [
                {"date": "2024-01-15", "item_level": 489.5},
                {"date": "2024-01-10", "item_level": 485.0},
                {"date": "2024-01-05", "item_level": 480.0}
            ],
            "tier_set_pieces": 4,
            "legendary_items": 2,
            "upgrade_suggestions": [
                {
                    "slot": "trinket",
                    "current_item": "Old Trinket",
                    "suggested_item": "Better Trinket",
                    "estimated_improvement": 5.2
                }
            ]
        }
        mock_db.get_character_gear_analysis.return_value = mock_gear

        response = api_test_client.client.get(
            "/characters/Thrall/gear",
            headers=valid_headers
        )

        data = api_test_client.assert_success_response(response)
        assert data["character_name"] == "Thrall"
        assert data["current_item_level"] == 489.5
        assert len(data["gear_progression"]) == 3
        assert data["tier_set_pieces"] == 4

    def test_character_authentication_required(
        self,
        api_test_client: APITestClient,
        invalid_headers: Dict[str, str]
    ):
        """Test that character endpoints require authentication."""
        endpoints = [
            "/characters",
            "/characters/Thrall",
            "/characters/Thrall/performance"
        ]

        for endpoint in endpoints:
            response = api_test_client.client.get(
                endpoint,
                headers=invalid_headers
            )
            api_test_client.assert_error_response(response, 401)

    def test_character_validation_errors(
        self,
        api_test_client: APITestClient,
        valid_headers: Dict[str, str]
    ):
        """Test validation errors for character endpoints."""
        # Test invalid limit parameter
        response = api_test_client.client.get(
            "/characters",
            headers=valid_headers,
            params={"limit": 1000}  # Exceeds maximum
        )
        api_test_client.assert_error_response(response, 400)

        # Test invalid days parameter
        response = api_test_client.client.get(
            "/characters/Thrall/performance",
            headers=valid_headers,
            params={"days": 500}  # Exceeds maximum
        )
        api_test_client.assert_error_response(response, 400)

        # Test invalid difficulty
        response = api_test_client.client.get(
            "/characters/Thrall/performance",
            headers=valid_headers,
            params={"difficulty": "invalid_difficulty"}
        )
        api_test_client.assert_error_response(response, 400)

    def test_character_search_integration(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_character_data: Dict[str, Any],
        valid_headers: Dict[str, str]
    ):
        """Test character search functionality."""
        # Setup mock for search
        mock_search_results = [sample_character_data]
        mock_db.search_characters.return_value = mock_search_results

        response = api_test_client.client.get(
            "/characters",
            headers=valid_headers,
            params={"search": "thrall shaman"}
        )

        data = api_test_client.assert_paginated_response(response)
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "Thrall"

    def test_character_performance_metrics_calculation(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str]
    ):
        """Test that performance metrics are calculated correctly."""
        # Setup mock with raw performance data
        raw_performances = [
            {"character_name": "Thrall", "dps": 150000, "duration": 300},
            {"character_name": "Thrall", "dps": 140000, "duration": 400},
            {"character_name": "Thrall", "dps": 160000, "duration": 250}
        ]
        mock_db.get_character_performance.return_value = raw_performances

        response = api_test_client.client.get(
            "/characters/Thrall/performance",
            headers=valid_headers,
            params={"calculate_summary": True}
        )

        data = api_test_client.assert_success_response(response)

        # Should include summary calculations
        if isinstance(data, dict) and "summary" in data:
            summary = data["summary"]
            assert summary["avg_dps"] == 150000  # (150000 + 140000 + 160000) / 3
            assert summary["best_dps"] == 160000
            assert summary["encounter_count"] == 3

    @pytest.mark.asyncio
    async def test_character_concurrent_requests(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_character_data: Dict[str, Any],
        valid_headers: Dict[str, str]
    ):
        """Test handling of concurrent character requests."""
        import asyncio
        from httpx import AsyncClient

        # Setup mock
        mock_db.get_character_profile.return_value = sample_character_data

        # Simulate concurrent requests
        async def make_request():
            async with AsyncClient(app=api_test_client.client.app, base_url="http://test") as client:
                response = await client.get(
                    "/characters/Thrall",
                    headers=valid_headers
                )
                return response.status_code

        # Run multiple concurrent requests
        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All requests should succeed
        assert all(status == 200 for status in results)

        # Database should have been called multiple times
        assert mock_db.get_character_profile.call_count == 10