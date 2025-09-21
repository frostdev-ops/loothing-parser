"""
Tests for search endpoints in API v1.

Comprehensive test suite covering advanced search, fuzzy matching,
saved searches, and search analytics.
"""

import pytest
from typing import Dict, Any
from unittest.mock import AsyncMock

from src.database.schema import DatabaseManager
from tests.api.v1.conftest import APITestClient


class TestSearchEndpoints:
    """Test suite for search-related endpoints."""

    def test_basic_search_success(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test basic search functionality."""
        # Setup mock
        mock_db.execute_search.return_value = sample_search_data

        search_request = {"query": "thrall shaman", "scope": "characters", "limit": 10}

        response = api_test_client.client.post(
            "/search", headers=valid_headers, json=search_request
        )

        data = api_test_client.assert_success_response(response)
        assert data["total_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["item_type"] == "character"
        assert data["results"][0]["title"] == "Thrall - Enhancement Shaman"
        assert data["query_time_ms"] > 0

        # Verify database call
        mock_db.execute_search.assert_called_once()

    def test_fuzzy_search(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test fuzzy search with typos and variations."""
        # Setup mock for fuzzy search
        fuzzy_results = {
            **sample_search_data,
            "results": [
                {
                    "item_type": "character",
                    "item_id": "1",
                    "title": "Thrall - Enhancement Shaman",
                    "description": "Found via fuzzy matching",
                    "relevance_score": 0.85,
                    "highlights": {"name": ["<mark>Thrall</mark>"]},
                    "data": {"name": "Thrall", "class_name": "Shaman"},
                }
            ],
        }
        mock_db.execute_fuzzy_search.return_value = fuzzy_results

        response = api_test_client.client.post(
            "/search/fuzzy",
            headers=valid_headers,
            json={"query": "trhall shamn", "threshold": 0.8, "max_edits": 2},  # Typos
        )

        data = api_test_client.assert_success_response(response)
        assert len(data["results"]) == 1
        assert data["results"][0]["relevance_score"] == 0.85
        assert "fuzzy_search" in data["metadata"]

    def test_boolean_search(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test boolean search with complex queries."""
        # Setup mock
        mock_db.execute_boolean_search.return_value = sample_search_data

        boolean_request = {
            "boolean_query": {
                "criteria": [
                    {"field": "class_name", "operator": "equals", "value": "Shaman"},
                    {"field": "guild_name", "operator": "contains", "value": "Earthen"},
                ],
                "logic_operator": "AND",
            },
            "scope": "characters",
        }

        response = api_test_client.client.post(
            "/search", headers=valid_headers, json=boolean_request
        )

        data = api_test_client.assert_success_response(response)
        assert len(data["results"]) == 1

        # Verify boolean search was called
        mock_db.execute_boolean_search.assert_called_once()

    def test_search_suggestions(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test search suggestion functionality."""
        # Setup mock
        mock_suggestions = ["Thrall", "Thunderfury", "Thunderlord"]
        mock_db.get_search_suggestions.return_value = mock_suggestions

        response = api_test_client.client.get(
            "/search/suggestions", headers=valid_headers, params={"query": "thund", "limit": 5}
        )

        data = api_test_client.assert_success_response(response)
        assert len(data) == 3
        assert "Thunderfury" in data
        assert "Thunderlord" in data

    def test_search_facets(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test search facets for filtering."""
        # Setup mock facets
        mock_facets = {
            "class_name": {"Shaman": 15, "Mage": 12, "Warrior": 8},
            "guild_name": {"Earthen Ring": 10, "Kirin Tor": 8, "Stormwind Guard": 5},
        }
        mock_db.get_search_facets.return_value = mock_facets

        response = api_test_client.client.get(
            "/search/facets", headers=valid_headers, params={"query": "characters"}
        )

        data = api_test_client.assert_success_response(response)
        assert "class_name" in data
        assert "guild_name" in data
        assert data["class_name"]["Shaman"] == 15

    def test_saved_search_creation(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test creating and saving search configurations."""
        # Setup mock
        mock_db.save_search_configuration.return_value = 123

        saved_search = {
            "name": "My Shaman Search",
            "description": "Find all enhancement shamans",
            "search_request": {
                "query": "enhancement shaman",
                "scope": "characters",
                "fuzzy_matching": True,
            },
            "is_public": False,
        }

        response = api_test_client.client.post(
            "/search/saved", headers=valid_headers, json=saved_search
        )

        data = api_test_client.assert_success_response(response)
        assert data["id"] == 123
        assert data["name"] == "My Shaman Search"
        assert data["created_by"] == "test_user_123"

    def test_saved_search_execution(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test executing saved search configurations."""
        # Setup mocks
        saved_search_config = {
            "id": 123,
            "name": "Test Search",
            "search_request": {"query": "shaman", "scope": "characters"},
            "created_by": "test_user_123",
            "is_public": False,
        }
        mock_db.get_saved_search.return_value = saved_search_config
        mock_db.execute_search.return_value = sample_search_data
        mock_db.update_saved_search_usage.return_value = None

        response = api_test_client.client.post(
            "/search/saved/123/execute",
            headers=valid_headers,
            json={"days": 7},  # Override parameter
        )

        data = api_test_client.assert_success_response(response)
        assert len(data["results"]) == 1

        # Verify usage was updated
        mock_db.update_saved_search_usage.assert_called_once_with(123)

    def test_saved_search_list(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test listing saved searches."""
        # Setup mock
        mock_searches = [
            {
                "id": 123,
                "name": "My Search",
                "description": "Test search",
                "created_by": "test_user_123",
                "use_count": 5,
                "is_public": False,
            },
            {
                "id": 124,
                "name": "Public Search",
                "description": "Public test search",
                "created_by": "other_user",
                "use_count": 12,
                "is_public": True,
            },
        ]
        mock_db.get_saved_searches.return_value = mock_searches

        response = api_test_client.client.get(
            "/search/saved", headers=valid_headers, params={"include_public": True}
        )

        data = api_test_client.assert_success_response(response)
        assert len(data) == 2
        assert data[0]["id"] == 123
        assert data[1]["is_public"] is True

    def test_saved_search_deletion(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test deleting saved searches."""
        # Setup mock
        saved_search = {"id": 123, "created_by": "test_user_123"}
        mock_db.get_saved_search.return_value = saved_search
        mock_db.delete_saved_search.return_value = None

        response = api_test_client.client.delete("/search/saved/123", headers=valid_headers)

        data = api_test_client.assert_success_response(response)
        assert "deleted successfully" in data["message"]

        # Verify deletion was called
        mock_db.delete_saved_search.assert_called_once_with(123)

    def test_saved_search_permission_denied(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test that users can't delete others' private searches."""
        # Setup mock for search owned by different user
        saved_search = {"id": 123, "created_by": "other_user_456", "is_public": False}
        mock_db.get_saved_search.return_value = saved_search

        response = api_test_client.client.delete("/search/saved/123", headers=valid_headers)

        api_test_client.assert_error_response(response, 403)

    def test_popular_search_terms(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test popular search terms analytics."""
        # Setup mock
        mock_popular_terms = {
            "terms": [
                {"term": "shaman", "count": 150, "trend": "up"},
                {"term": "raid", "count": 120, "trend": "stable"},
                {"term": "mythic", "count": 100, "trend": "down"},
            ],
            "trending": [
                {"term": "enhancement", "growth": 25.5},
                {"term": "fyrakk", "growth": 18.2},
            ],
            "volume": {"total_searches": 1250, "unique_terms": 450},
        }
        mock_db.get_popular_search_terms.return_value = mock_popular_terms

        response = api_test_client.client.get(
            "/search/popular-terms", headers=valid_headers, params={"days": 30, "limit": 20}
        )

        data = api_test_client.assert_success_response(response)
        assert len(data["popular_terms"]) == 3
        assert len(data["trending_terms"]) == 2
        assert data["search_volume"]["total_searches"] == 1250

    def test_search_scope_filtering(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test search with different scope filters."""
        # Setup mock
        mock_db.execute_search.return_value = sample_search_data

        scopes = ["characters", "encounters", "guilds", "all"]

        for scope in scopes:
            search_request = {"query": "test", "scope": scope}

            response = api_test_client.client.post(
                "/search", headers=valid_headers, json=search_request
            )

            data = api_test_client.assert_success_response(response)
            assert data["metadata"]["scope"] == scope

    def test_search_with_highlights(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        valid_headers: Dict[str, str],
    ):
        """Test search results with text highlighting."""
        # Setup mock with highlights
        search_results = {
            "results": [
                {
                    "item_type": "character",
                    "item_id": "1",
                    "title": "Thrall - Enhancement Shaman",
                    "description": "Level 80 Enhancement Shaman",
                    "relevance_score": 0.95,
                    "highlights": {
                        "name": ["<mark>Thrall</mark>"],
                        "class_name": ["Enhancement <mark>Shaman</mark>"],
                        "description": ["Level 80 Enhancement <mark>Shaman</mark>"],
                    },
                    "data": {"name": "Thrall"},
                }
            ],
            "total_count": 1,
            "query_time_ms": 15.5,
        }
        mock_db.execute_search.return_value = search_results

        search_request = {"query": "thrall shaman", "include_highlights": True}

        response = api_test_client.client.post(
            "/search", headers=valid_headers, json=search_request
        )

        data = api_test_client.assert_success_response(response)
        result = data["results"][0]
        assert "highlights" in result
        assert "<mark>Thrall</mark>" in result["highlights"]["name"][0]
        assert "<mark>Shaman</mark>" in result["highlights"]["class_name"][0]

    def test_search_validation_errors(
        self, api_test_client: APITestClient, valid_headers: Dict[str, str]
    ):
        """Test search request validation."""
        # Test empty search request
        response = api_test_client.client.post("/search", headers=valid_headers, json={})
        api_test_client.assert_error_response(response, 400)

        # Test invalid scope
        response = api_test_client.client.post(
            "/search", headers=valid_headers, json={"query": "test", "scope": "invalid_scope"}
        )
        api_test_client.assert_error_response(response, 400)

        # Test invalid fuzzy threshold
        response = api_test_client.client.post(
            "/search/fuzzy",
            headers=valid_headers,
            json={"query": "test", "threshold": 1.5},  # > 1.0
        )
        api_test_client.assert_error_response(response, 400)

    def test_search_performance_monitoring(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test that search performance is monitored."""
        # Setup mock with timing
        search_results = {**sample_search_data, "query_time_ms": 125.7}
        mock_db.execute_search.return_value = search_results

        response = api_test_client.client.post(
            "/search", headers=valid_headers, json={"query": "test search"}
        )

        data = api_test_client.assert_success_response(response)

        # Verify performance metrics are included
        assert "query_time_ms" in data
        assert data["query_time_ms"] > 0

        # Check response headers for performance data
        assert "X-Response-Time" in response.headers

    def test_search_caching(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test search result caching."""
        # Setup mock
        mock_db.execute_search.return_value = sample_search_data

        search_request = {"query": "cached search test"}

        # First request
        response1 = api_test_client.client.post(
            "/search", headers=valid_headers, json=search_request
        )
        data1 = api_test_client.assert_success_response(response1)

        # Second identical request
        response2 = api_test_client.client.post(
            "/search", headers=valid_headers, json=search_request
        )
        data2 = api_test_client.assert_success_response(response2)

        # Results should be identical
        assert data1["results"] == data2["results"]
        assert data1["total_count"] == data2["total_count"]

    @pytest.mark.asyncio
    async def test_search_concurrent_requests(
        self,
        api_test_client: APITestClient,
        mock_db: DatabaseManager,
        sample_search_data: Dict[str, Any],
        valid_headers: Dict[str, str],
    ):
        """Test handling of concurrent search requests."""
        import asyncio
        from httpx import AsyncClient

        # Setup mock
        mock_db.execute_search.return_value = sample_search_data

        async def make_search_request(query: str):
            async with AsyncClient(
                app=api_test_client.client.app, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/search", headers=valid_headers, json={"query": query}
                )
                return response.status_code, response.json()

        # Run multiple concurrent searches
        tasks = [make_search_request(f"test query {i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        # All requests should succeed
        for status_code, data in results:
            assert status_code == 200
            assert "results" in data

    def test_search_authentication_required(
        self, api_test_client: APITestClient, invalid_headers: Dict[str, str]
    ):
        """Test that search endpoints require authentication."""
        endpoints_and_methods = [
            ("POST", "/search"),
            ("GET", "/search/suggestions"),
            ("GET", "/search/facets"),
            ("POST", "/search/fuzzy"),
            ("POST", "/search/saved"),
            ("GET", "/search/saved"),
        ]

        for method, endpoint in endpoints_and_methods:
            if method == "POST":
                response = api_test_client.client.post(
                    endpoint, headers=invalid_headers, json={"query": "test"}
                )
            else:
                response = api_test_client.client.get(endpoint, headers=invalid_headers)

            api_test_client.assert_error_response(response, 401)
