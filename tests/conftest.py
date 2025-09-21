"""
Pytest configuration and shared fixtures for the test suite.

This file provides common configuration and fixtures used across
all test modules in the streaming system test suite.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.schema import DatabaseManager, create_tables


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = DatabaseManager(db_path)
    create_tables(db)
    yield db
    db.close()

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_log_lines():
    """Sample combat log lines for testing."""
    return [
        "9/15/2025 21:30:21.462-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1,BUILD_VERSION,11.2.0,PROJECT_ID,1",
        '9/15/2025 21:30:21.463-4  ZONE_CHANGE,2649,"Hallowfall",23',
        '9/15/2025 21:30:21.463-4  MAP_CHANGE,2215,"Hallowfall",4939.580078,-593.750000,4397.919922,-3902.080078',
        '9/15/2025 21:30:22.123-4  ENCOUNTER_START,2902,"Ulgrax the Devourer",16,20,2657',
        '9/15/2025 21:30:22.124-4  SPELL_CAST_START,Player-1234,"Testplayer",0x512,0x0,Player-1234,"Testplayer",0x512,0x0,1234,"Test Spell",0x1',
        '9/15/2025 21:30:23.456-4  SPELL_DAMAGE,Player-1234,"Testplayer",0x512,0x0,Creature-5678,"Ulgrax the Devourer",0x10a28,0x0,1234,"Test Spell",0x1,5678,0,0,0,0,0,0,0',
        '9/15/2025 21:30:24.789-4  UNIT_DIED,nil,nil,0x0,0x0,Creature-5678,"Ulgrax the Devourer",0x10a28,0x0',
        '9/15/2025 21:30:25.000-4  ENCOUNTER_END,2902,"Ulgrax the Devourer",16,20,1,180000',
    ]


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "auth: mark test as authentication related")
    config.addinivalue_line("markers", "websocket: mark test as WebSocket related")
    config.addinivalue_line("markers", "compression: mark test as compression related")
    config.addinivalue_line("markers", "query: mark test as query API related")


# Pytest collection configuration
def pytest_collection_modifyitems(config, items):
    """Modify collected test items with markers."""
    for item in items:
        # Auto-mark tests based on file names
        if "test_streaming_pipeline" in item.fspath.basename:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)

        if "test_authentication" in item.fspath.basename:
            item.add_marker(pytest.mark.auth)

        if "test_websocket" in item.fspath.basename:
            item.add_marker(pytest.mark.websocket)

        if "test_compression" in item.fspath.basename:
            item.add_marker(pytest.mark.compression)

        if "test_query_api" in item.fspath.basename:
            item.add_marker(pytest.mark.query)
