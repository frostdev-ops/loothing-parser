#!/usr/bin/env python3
"""
Integration test script for WoW combat log streaming system.

Tests end-to-end functionality including:
- Real-time log streaming to server
- Database persistence and querying
- WebSocket connection stability
- Concurrent client connections
"""

import asyncio
import json
import time
import tempfile
import subprocess
import signal
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.streaming.client import CombatLogStreamer
from src.database.schema import DatabaseManager, create_tables
from src.database.query import QueryAPI
from src.api.streaming_server import StreamingServer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntegrationTestRunner:
    """Manages integration tests for the combat log streaming system."""

    def __init__(self, server_url: str = "ws://localhost:8000", api_key: str = "test-key"):
        self.server_url = server_url
        self.api_key = api_key
        self.server_process: Optional[subprocess.Popen] = None
        self.test_db_path: Optional[str] = None
        self.temp_files: List[str] = []

    async def setup_test_environment(self):
        """Set up test database and start streaming server."""
        logger.info("Setting up test environment...")

        # Create temporary database
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.test_db_path = temp_db.name
        temp_db.close()
        self.temp_files.append(self.test_db_path)

        # Initialize database
        db_manager = DatabaseManager(self.test_db_path)
        create_tables(db_manager.engine)
        db_manager.close()

        logger.info(f"Test database created: {self.test_db_path}")

    def start_server(self, port: int = 8000):
        """Start the streaming server in a subprocess."""
        logger.info(f"Starting streaming server on port {port}...")

        # Set environment variables for the server
        env = os.environ.copy()
        env["DB_PATH"] = self.test_db_path
        env["API_KEY"] = self.api_key

        # Start server process
        server_script = project_root / "src" / "api" / "streaming_server.py"
        self.server_process = subprocess.Popen(
            [sys.executable, "-m", "src.api.streaming_server", "--port", str(port)],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Wait for server to start
        time.sleep(3)

        if self.server_process.poll() is not None:
            stdout, stderr = self.server_process.communicate()
            logger.error(f"Server failed to start: {stderr.decode()}")
            raise RuntimeError("Failed to start streaming server")

        logger.info("Streaming server started successfully")

    def stop_server(self):
        """Stop the streaming server."""
        if self.server_process:
            logger.info("Stopping streaming server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()
            self.server_process = None

    async def test_basic_streaming(self) -> bool:
        """Test basic log streaming functionality."""
        logger.info("Testing basic log streaming...")

        try:
            # Find a small example file
            examples_dir = project_root / "examples"
            log_files = list(examples_dir.glob("WoWCombatLog*.txt"))
            if not log_files:
                logger.warning("No example log files found, skipping streaming test")
                return True

            # Use the smallest file for testing
            test_file = min(log_files, key=lambda x: x.stat().st_size)
            logger.info(f"Using test file: {test_file.name}")

            # Create streamer and stream first 100 lines
            streamer = CombatLogStreamer(self.server_url, self.api_key)
            lines_streamed = 0

            with open(test_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= 100:  # Limit to 100 lines for test
                        break

                    line = line.strip()
                    if line:
                        await streamer.stream_line(line)
                        lines_streamed += 1

            await streamer.close()

            logger.info(f"Successfully streamed {lines_streamed} lines")
            return True

        except Exception as e:
            logger.error(f"Basic streaming test failed: {e}")
            return False

    async def test_database_persistence(self) -> bool:
        """Test that streamed data is persisted to database."""
        logger.info("Testing database persistence...")

        try:
            # Connect to test database
            db_manager = DatabaseManager(self.test_db_path)
            query_api = QueryAPI(db_manager)

            # Check for stored data
            stats = query_api.get_database_stats()
            logger.info(f"Database stats: {stats}")

            # Should have some events stored from previous test
            if stats.get('total_events', 0) > 0:
                logger.info("✓ Data successfully persisted to database")
                result = True
            else:
                logger.warning("! No events found in database")
                result = False

            query_api.close()
            db_manager.close()

            return result

        except Exception as e:
            logger.error(f"Database persistence test failed: {e}")
            return False

    async def test_concurrent_connections(self, num_clients: int = 3) -> bool:
        """Test multiple concurrent client connections."""
        logger.info(f"Testing {num_clients} concurrent connections...")

        try:
            # Create multiple streamers
            streamers = []
            for i in range(num_clients):
                streamer = CombatLogStreamer(
                    self.server_url,
                    self.api_key,
                    client_id=f"test-client-{i}"
                )
                streamers.append(streamer)

            # Stream data concurrently
            tasks = []
            for i, streamer in enumerate(streamers):
                task = asyncio.create_task(
                    self._stream_test_data(streamer, f"concurrent-test-{i}")
                )
                tasks.append(task)

            # Wait for all streams to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Close all streamers
            for streamer in streamers:
                await streamer.close()

            # Check results
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Concurrent test results: {success_count}/{num_clients} successful")

            return success_count == num_clients

        except Exception as e:
            logger.error(f"Concurrent connections test failed: {e}")
            return False

    async def _stream_test_data(self, streamer: CombatLogStreamer, session_id: str) -> bool:
        """Helper method to stream test data."""
        try:
            # Stream some test events
            test_events = [
                "9/18/2025 17:29:04.791-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1,BUILD_VERSION,11.2.0,PROJECT_ID,1",
                "9/18/2025 17:29:27.343-4  ZONE_CHANGE,2441,\"Tazavesh, the Veiled Market\",23",
                "9/18/2025 17:29:06.409-4  SPELL_AURA_APPLIED,Player-3723-0AAC293B,\"Test-Player\",0x512,0x80000000,Player-3723-0AAC293B,\"Test-Player\",0x512,0x80000000,408,\"Kidney Shot\",0x1,DEBUFF",
            ]

            for event in test_events:
                await streamer.stream_line(event)
                await asyncio.sleep(0.1)  # Small delay between events

            return True

        except Exception as e:
            logger.error(f"Error streaming test data for {session_id}: {e}")
            return False

    async def test_query_api(self) -> bool:
        """Test the query API functionality."""
        logger.info("Testing query API...")

        try:
            # Connect to database
            db_manager = DatabaseManager(self.test_db_path)
            query_api = QueryAPI(db_manager)

            # Test basic queries
            stats = query_api.get_database_stats()
            logger.info(f"Database contains {stats.get('total_events', 0)} events")

            # Test encounter queries
            encounters = query_api.get_recent_encounters(limit=10)
            logger.info(f"Found {len(encounters)} recent encounters")

            # Test character metrics (if any players found)
            try:
                metrics = query_api.get_character_metrics(limit=5)
                logger.info(f"Found metrics for {len(metrics)} characters")
            except Exception as e:
                logger.info(f"No character metrics available: {e}")

            query_api.close()
            db_manager.close()

            logger.info("✓ Query API tests completed successfully")
            return True

        except Exception as e:
            logger.error(f"Query API test failed: {e}")
            return False

    async def test_connection_recovery(self) -> bool:
        """Test client recovery after connection drops."""
        logger.info("Testing connection recovery...")

        try:
            # Create streamer
            streamer = CombatLogStreamer(self.server_url, self.api_key)

            # Stream some initial data
            await streamer.stream_line("9/18/2025 17:29:04.791-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1")

            # Simulate connection drop by restarting server
            logger.info("Simulating connection drop...")
            self.stop_server()
            time.sleep(1)
            self.start_server()

            # Wait for server to be ready
            time.sleep(3)

            # Try to stream more data (should reconnect automatically)
            await streamer.stream_line("9/18/2025 17:29:05.000-4  ZONE_CHANGE,123,\"Test Zone\",1")

            await streamer.close()

            logger.info("✓ Connection recovery test completed")
            return True

        except Exception as e:
            logger.error(f"Connection recovery test failed: {e}")
            return False

    def cleanup(self):
        """Clean up test resources."""
        logger.info("Cleaning up test environment...")

        # Stop server
        self.stop_server()

        # Remove temporary files
        for temp_file in self.temp_files:
            try:
                os.unlink(temp_file)
            except OSError:
                pass

    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all integration tests."""
        logger.info("Starting integration test suite...")

        # Set up environment
        await self.setup_test_environment()
        self.start_server()

        # Wait for server to be ready
        await asyncio.sleep(2)

        # Run tests
        test_results = {}

        try:
            test_results["basic_streaming"] = await self.test_basic_streaming()
            test_results["database_persistence"] = await self.test_database_persistence()
            test_results["concurrent_connections"] = await self.test_concurrent_connections()
            test_results["query_api"] = await self.test_query_api()
            test_results["connection_recovery"] = await self.test_connection_recovery()

        finally:
            self.cleanup()

        return test_results


async def main():
    """Main entry point for integration tests."""
    parser = argparse.ArgumentParser(description="WoW Combat Log Integration Tests")
    parser.add_argument("--server-url", default="ws://localhost:8000", help="Server URL")
    parser.add_argument("--api-key", default="test-integration-key", help="API key")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run integration tests
    test_runner = IntegrationTestRunner(args.server_url, args.api_key)

    try:
        results = await test_runner.run_all_tests()

        # Print results
        print("\n" + "="*60)
        print("INTEGRATION TEST RESULTS")
        print("="*60)

        passed = 0
        total = len(results)

        for test_name, success in results.items():
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"{test_name:30} {status}")
            if success:
                passed += 1

        print("-"*60)
        print(f"TOTAL: {passed}/{total} tests passed")

        if passed == total:
            print("🎉 All integration tests passed!")
            return 0
        else:
            print("❌ Some integration tests failed!")
            return 1

    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        test_runner.cleanup()
        return 130

    except Exception as e:
        logger.error(f"Integration tests failed with error: {e}")
        test_runner.cleanup()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)