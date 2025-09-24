#!/usr/bin/env python3
"""
Integration test script for WoW Combat Log Parser API in Docker environment.

Tests the parser API endpoints with PostgreSQL and Redis integration to ensure
everything works correctly in the Docker Compose stack.
"""

import requests
import time
import json
import sys
import os
from typing import Dict, Any, List, Optional


class DockerIntegrationTest:
    """Integration tests for Docker-deployed parser API."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        """
        Initialize test suite.

        Args:
            base_url: Base URL for the parser API
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 30

        # Test configuration
        self.api_key = "dev_key_12345"
        self.guild_id = 1

        # Test results
        self.results: List[Dict[str, Any]] = []

    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, test_name: str, test_func) -> bool:
        """
        Run a single test and record results.

        Args:
            test_name: Name of the test
            test_func: Test function to execute

        Returns:
            True if test passed, False otherwise
        """
        self.log(f"Running test: {test_name}")
        start_time = time.time()

        try:
            test_func()
            duration = time.time() - start_time
            self.log(f"✅ PASS: {test_name} ({duration:.2f}s)", "PASS")
            self.results.append({
                "test": test_name,
                "status": "PASS",
                "duration": duration,
                "error": None
            })
            return True

        except Exception as e:
            duration = time.time() - start_time
            self.log(f"❌ FAIL: {test_name} - {str(e)} ({duration:.2f}s)", "FAIL")
            self.results.append({
                "test": test_name,
                "status": "FAIL",
                "duration": duration,
                "error": str(e)
            })
            return False

    def test_health_endpoint(self):
        """Test the health check endpoint."""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()

        data = response.json()
        assert data["status"] in ["healthy", "degraded"], f"Invalid status: {data['status']}"
        assert "services" in data, "Missing services in health response"
        assert "database" in data["services"], "Missing database service status"

        self.log(f"Health check: {data['status']}")
        for service, status in data["services"].items():
            self.log(f"  {service}: {status}")

    def test_readiness_endpoint(self):
        """Test the readiness probe endpoint."""
        response = self.session.get(f"{self.base_url}/health/ready")
        response.raise_for_status()

        data = response.json()
        assert data["status"] == "ready", f"Service not ready: {data}"
        assert "database" in data, "Missing database status in readiness"

    def test_liveness_endpoint(self):
        """Test the liveness probe endpoint."""
        response = self.session.get(f"{self.base_url}/health/live")
        response.raise_for_status()

        data = response.json()
        assert data["status"] == "alive", f"Service not alive: {data}"

    def test_api_v1_health(self):
        """Test the API v1 health endpoint."""
        response = self.session.get(f"{self.base_url}/api/v1/health")
        response.raise_for_status()

        data = response.json()
        assert "status" in data, "Missing status in API v1 health"

    def test_api_v1_status(self):
        """Test the API v1 status endpoint."""
        response = self.session.get(f"{self.base_url}/api/v1/status")
        response.raise_for_status()

        data = response.json()
        assert "api_version" in data, "Missing API version"
        assert "features" in data, "Missing features list"

    def test_openapi_docs(self):
        """Test that OpenAPI documentation is available."""
        response = self.session.get(f"{self.base_url}/openapi.json")
        response.raise_for_status()

        data = response.json()
        assert "openapi" in data, "Invalid OpenAPI spec"
        assert "info" in data, "Missing API info"

    def test_characters_endpoint(self):
        """Test the characters endpoint."""
        params = {
            "api_key": self.api_key,
            "guild_id": self.guild_id,
            "limit": 10
        }

        response = self.session.get(f"{self.base_url}/api/v1/characters", params=params)
        response.raise_for_status()

        data = response.json()
        assert "characters" in data, "Missing characters in response"
        assert "total" in data, "Missing total count"
        assert isinstance(data["characters"], list), "Characters should be a list"

    def test_guilds_endpoint(self):
        """Test the guilds endpoint."""
        params = {
            "api_key": self.api_key,
            "limit": 10
        }

        response = self.session.get(f"{self.base_url}/api/v1/guilds", params=params)
        response.raise_for_status()

        data = response.json()
        assert "guilds" in data, "Missing guilds in response"
        assert "total" in data, "Missing total count"
        assert isinstance(data["guilds"], list), "Guilds should be a list"

    def test_encounters_endpoint(self):
        """Test the encounters endpoint."""
        params = {
            "api_key": self.api_key,
            "guild_id": self.guild_id,
            "limit": 10
        }

        response = self.session.get(f"{self.base_url}/api/v1/encounters", params=params)
        response.raise_for_status()

        data = response.json()
        assert "encounters" in data, "Missing encounters in response"
        assert "total" in data, "Missing total count"
        assert isinstance(data["encounters"], list), "Encounters should be a list"

    def test_analytics_performance_trends(self):
        """Test the analytics performance trends endpoint."""
        params = {
            "api_key": self.api_key,
            "guild_id": self.guild_id,
            "days": 30
        }

        response = self.session.get(f"{self.base_url}/api/v1/analytics/performance/trends", params=params)
        response.raise_for_status()

        data = response.json()
        assert "trends" in data, "Missing trends in response"
        assert isinstance(data["trends"], list), "Trends should be a list"

    def test_database_connectivity(self):
        """Test database connectivity by checking health and making a query."""
        # Check health first
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()

        health_data = response.json()
        db_status = health_data.get("services", {}).get("database", "")

        # Should indicate the database type and status
        assert ":" in db_status, f"Invalid database status format: {db_status}"

        db_type, status = db_status.split(":", 1)
        assert db_type in ["postgresql", "sqlite"], f"Unknown database type: {db_type}"
        assert "connected" in status or "ready" in status, f"Database not connected: {status}"

        self.log(f"Database backend: {db_type}")

    def test_cache_connectivity(self):
        """Test cache connectivity."""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()

        health_data = response.json()
        cache_status = health_data.get("services", {}).get("cache", "")

        # Should indicate the cache type and status
        assert ":" in cache_status, f"Invalid cache status format: {cache_status}"

        cache_type, status = cache_status.split(":", 1)
        assert cache_type in ["redis", "memory"], f"Unknown cache type: {cache_type}"

        self.log(f"Cache backend: {cache_type}")

    def test_cors_headers(self):
        """Test that CORS headers are properly set."""
        response = self.session.options(f"{self.base_url}/health")

        # Should return OK or Method Not Allowed, but with CORS headers
        assert response.status_code in [200, 405], f"Unexpected status: {response.status_code}"

    def wait_for_service(self, max_attempts: int = 30, delay: int = 2) -> bool:
        """
        Wait for the service to become available.

        Args:
            max_attempts: Maximum number of attempts
            delay: Delay between attempts in seconds

        Returns:
            True if service is available, False otherwise
        """
        self.log(f"Waiting for service at {self.base_url}...")

        for attempt in range(max_attempts):
            try:
                response = self.session.get(f"{self.base_url}/health", timeout=5)
                if response.status_code == 200:
                    self.log("Service is available!")
                    return True
            except requests.RequestException:
                pass

            if attempt < max_attempts - 1:
                self.log(f"Attempt {attempt + 1}/{max_attempts} failed, retrying in {delay}s...")
                time.sleep(delay)

        self.log("Service did not become available in time")
        return False

    def run_all_tests(self) -> bool:
        """
        Run all integration tests.

        Returns:
            True if all tests passed, False otherwise
        """
        self.log("Starting Docker integration tests")
        self.log(f"Target URL: {self.base_url}")

        # Wait for service to be available
        if not self.wait_for_service():
            self.log("Service not available, aborting tests", "ERROR")
            return False

        # Define test cases
        test_cases = [
            ("Health Check", self.test_health_endpoint),
            ("Readiness Probe", self.test_readiness_endpoint),
            ("Liveness Probe", self.test_liveness_endpoint),
            ("API v1 Health", self.test_api_v1_health),
            ("API v1 Status", self.test_api_v1_status),
            ("OpenAPI Documentation", self.test_openapi_docs),
            ("Database Connectivity", self.test_database_connectivity),
            ("Cache Connectivity", self.test_cache_connectivity),
            ("Characters Endpoint", self.test_characters_endpoint),
            ("Guilds Endpoint", self.test_guilds_endpoint),
            ("Encounters Endpoint", self.test_encounters_endpoint),
            ("Analytics Performance Trends", self.test_analytics_performance_trends),
            ("CORS Headers", self.test_cors_headers),
        ]

        # Run all tests
        passed = 0
        total = len(test_cases)

        for test_name, test_func in test_cases:
            if self.run_test(test_name, test_func):
                passed += 1

        # Print summary
        self.log(f"\n{'='*60}")
        self.log(f"TEST SUMMARY")
        self.log(f"{'='*60}")
        self.log(f"Total tests: {total}")
        self.log(f"Passed: {passed}")
        self.log(f"Failed: {total - passed}")
        self.log(f"Success rate: {passed/total*100:.1f}%")

        if passed == total:
            self.log("🎉 All tests passed!", "SUCCESS")
            return True
        else:
            self.log("❌ Some tests failed", "ERROR")

            # Print failed tests
            failed_tests = [r for r in self.results if r["status"] == "FAIL"]
            if failed_tests:
                self.log("\nFailed tests:")
                for test in failed_tests:
                    self.log(f"  - {test['test']}: {test['error']}")

            return False

    def print_environment_info(self):
        """Print environment information for debugging."""
        self.log("Environment Information:")
        self.log(f"  Target URL: {self.base_url}")
        self.log(f"  API Key: {self.api_key}")
        self.log(f"  Guild ID: {self.guild_id}")
        self.log(f"  Python version: {sys.version}")

        # Check environment variables
        env_vars = [
            "DB_HOST", "DB_NAME", "DB_USER", "REDIS_HOST", "PARSER_HOST", "PARSER_PORT"
        ]

        self.log("  Environment variables:")
        for var in env_vars:
            value = os.getenv(var, "Not set")
            if "PASSWORD" in var or "SECRET" in var:
                value = "***" if value != "Not set" else value
            self.log(f"    {var}: {value}")


def main():
    """Main function to run integration tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Docker integration tests for WoW Combat Log Parser API")
    parser.add_argument(
        "--url",
        default="http://localhost:8001",
        help="Base URL for the parser API (default: http://localhost:8001)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--wait-time",
        type=int,
        default=60,
        help="Maximum time to wait for service (seconds)"
    )

    args = parser.parse_args()

    # Create test instance
    test_suite = DockerIntegrationTest(base_url=args.url)

    if args.verbose:
        test_suite.print_environment_info()

    # Run tests
    success = test_suite.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()