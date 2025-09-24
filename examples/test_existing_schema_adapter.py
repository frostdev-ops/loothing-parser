#!/usr/bin/env python3
"""
Test script for ExistingSchemaAdapter

This demonstrates how to use the adapter to work with the existing
lootbong database schema instead of creating new tables.
"""

import os
import sys

# Add the parser source to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database.existing_schema_adapter import ExistingSchemaAdapter
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockDatabaseConnection:
    """Mock database connection for testing."""

    def __init__(self):
        self.backend_type = "postgresql"

    def execute(self, query, params=(), fetch_results=True):
        """Mock execute method."""
        logger.info(f"Mock Query: {query}")
        logger.info(f"Mock Params: {params}")

        # Return mock data based on query pattern
        if "FROM guilds" in query:
            return [{
                'id': 1,
                'name': 'Test Guild',
                'icon': 'test-icon.png',
                'owner_id': '12345',
                'member_count': 25,
                'created_at': '2024-01-01 12:00:00',
                'updated_at': '2024-01-01 12:00:00'
            }]
        elif "FROM combat_encounters" in query:
            return [{
                'id': '550e8400-e29b-41d4-a716-446655440000',
                'guild_id': 1,
                'encounter_type': 'raid',
                'encounter_name': 'Test Boss',
                'instance_name': 'Test Instance',
                'difficulty': 'Heroic',
                'start_time': '2024-01-01 20:00:00',
                'end_time': '2024-01-01 20:05:00',
                'duration_ms': 300000,
                'combat_duration_ms': 270000,
                'success': True,
                'player_count': 20,
                'total_damage': 50000000,
                'total_healing': 15000000,
                'total_deaths': 2,
                'keystone_level': None,
                'created_at': '2024-01-01 20:05:00'
            }]
        elif "FROM characters" in query:
            return [{
                'id': '550e8400-e29b-41d4-a716-446655440001',
                'guild_id': 1,
                'character_name': 'TestPlayer',
                'server': 'TestServer',
                'class': 'Mage',
                'spec': 'Fire',
                'role': 'DPS',
                'created_at': '2024-01-01 12:00:00',
                'updated_at': '2024-01-01 12:00:00',
                'last_seen': '2024-01-01 20:05:00',
                'encounter_count': 5
            }]
        elif "FROM combat_performances" in query:
            return [{
                'id': '550e8400-e29b-41d4-a716-446655440002',
                'guild_id': 1,
                'encounter_id': '550e8400-e29b-41d4-a716-446655440000',
                'character_id': '550e8400-e29b-41d4-a716-446655440001',
                'character_name': 'TestPlayer',
                'class': 'Mage',
                'spec': 'Fire',
                'role': 'DPS',
                'item_level': 450.5,
                'damage_done': 5000000,
                'healing_done': 0,
                'damage_taken': 500000,
                'overhealing': 0,
                'absorb_healing': 0,
                'deaths': 0,
                'interrupts': 2,
                'dispels': 0,
                'active_time_ms': 270000,
                'dps': 18518.5,
                'hps': 0,
                'dtps': 1851.9,
                'activity_percentage': 95.5,
                'talent_build': {},
                'equipment': {},
                'metadata': {},
                'created_at': '2024-01-01 20:05:00',
                'server': 'TestServer',
                'char_uuid': '550e8400-e29b-41d4-a716-446655440001'
            }]
        else:
            return []


def test_adapter():
    """Test the ExistingSchemaAdapter functionality."""
    logger.info("Testing ExistingSchemaAdapter...")

    # Create mock database connection
    mock_db = MockDatabaseConnection()

    # Initialize adapter
    adapter = ExistingSchemaAdapter(mock_db)

    # Test guild operations
    logger.info("\n=== Testing Guild Operations ===")
    guild = adapter.get_guild(1)
    logger.info(f"Guild: {guild}")

    guilds = adapter.get_guilds(limit=5)
    logger.info(f"Guilds count: {len(guilds)}")

    # Test encounter operations
    logger.info("\n=== Testing Encounter Operations ===")
    encounters = adapter.get_encounters(guild_id=1, limit=10)
    logger.info(f"Encounters count: {len(encounters)}")
    if encounters:
        logger.info(f"First encounter: {encounters[0]}")

    # Test specific encounter
    if encounters:
        encounter_id = encounters[0]['encounter_id']
        encounter = adapter.get_encounter(encounter_id, guild_id=1)
        logger.info(f"Specific encounter: {encounter is not None}")

    # Test character operations
    logger.info("\n=== Testing Character Operations ===")
    characters = adapter.get_characters(guild_id=1, limit=10)
    logger.info(f"Characters count: {len(characters)}")
    if characters:
        logger.info(f"First character: {characters[0]}")

    # Test character lookup by name
    character = adapter.get_character_by_name("TestPlayer", guild_id=1)
    logger.info(f"Character by name: {character is not None}")

    # Test character metrics
    logger.info("\n=== Testing Character Metrics ===")
    if encounters:
        encounter_id = encounters[0]['encounter_id']
        metrics = adapter.get_character_metrics(encounter_id, guild_id=1)
        logger.info(f"Metrics count: {len(metrics)}")
        if metrics:
            logger.info(f"First metric: {metrics[0]}")

    # Test top performers
    logger.info("\n=== Testing Top Performers ===")
    performers = adapter.get_top_performers('dps', guild_id=1, limit=5)
    logger.info(f"Top performers count: {len(performers)}")

    # Test database stats
    logger.info("\n=== Testing Database Stats ===")
    stats = adapter.get_database_stats()
    logger.info(f"Database stats: {stats}")

    # Test health check
    logger.info("\n=== Testing Health Check ===")
    health = adapter.health_check()
    logger.info(f"Health check: {health}")

    logger.info("\n=== Test Complete ===")


if __name__ == "__main__":
    test_adapter()