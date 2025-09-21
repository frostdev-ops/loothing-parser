#!/usr/bin/env python3
"""
Comprehensive debugging script to verify the entire WoW combat log processing pipeline.

This script tests:
1. Event parsing (damage/healing amount extraction)
2. Character event stream accumulation
3. DPS/HPS calculation
4. Database storage field mapping
5. End-to-end data flow verification
"""

import sys
import os
import logging
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, "/app")

from src.parser.events import EventFactory, DamageEvent, HealEvent
from src.parser.tokenizer import ParsedLine
from src.models.character_events import CharacterEventStream
from src.database.schema import DatabaseManager, create_tables
from src.database.storage import EventStorage
from src.models.encounters import Encounter

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def create_sample_damage_event():
    """Create a sample damage event for testing."""
    # Simulate a parsed SPELL_DAMAGE line with Advanced Combat Logging
    parsed_line = ParsedLine(
        timestamp=datetime.now(),
        event_type="SPELL_DAMAGE",
        raw_line="test line",
        base_params=[
            "Player-1234-56789ABC",
            "TestPlayer",
            "0x511",
            "0",
            "Creature-0-5678-DEFG",
            "TestBoss",
            "0xa48",
            "0",
        ],
        prefix_params=[12345, "Test Spell", 4],  # spell_id, spell_name, spell_school
        suffix_params=[
            # Advanced Combat Logging unit info (19 fields)
            "Player-1234-56789ABC",
            "info_guid",
            85000,
            100000,
            5000,  # 0-4: target, info, hp, max_hp, ap
            3000,
            2500,
            "resource_array",
            15.5,
            20.0,
            25.0,  # 5-10: sp, armor, resources, x, y, z
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,  # 11-18: more fields
            # Damage parameters start at index 19
            12500,  # amount (actual damage)
            1200,  # overkill
            4,  # school
            0,  # resisted
            500,  # blocked
            300,  # absorbed
            True,  # critical
            False,  # glancing
            False,  # crushing
        ],
    )

    return EventFactory.create_event(parsed_line)


def create_sample_heal_event():
    """Create a sample heal event for testing."""
    parsed_line = ParsedLine(
        timestamp=datetime.now(),
        event_type="SPELL_HEAL",
        raw_line="test heal line",
        base_params=[
            "Player-1234-HEALER123",
            "TestHealer",
            "0x511",
            "0",
            "Player-1234-56789ABC",
            "TestPlayer",
            "0x511",
            "0",
        ],
        prefix_params=[54321, "Test Heal", 2],  # spell_id, spell_name, spell_school
        suffix_params=[
            # Advanced Combat Logging unit info (19 fields)
            "Player-1234-56789ABC",
            "info_guid",
            85000,
            100000,
            5000,
            3000,
            2500,
            "resource_array",
            15.5,
            20.0,
            25.0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            # Healing parameters start at index 19
            8500,  # amount (total healing)
            1500,  # overhealing
            0,  # absorbed
            True,  # critical
        ],
    )

    return EventFactory.create_event(parsed_line)


def test_event_parsing():
    """Test that events are parsed correctly with proper amounts."""
    logger.info("=== Testing Event Parsing ===")

    # Test damage event
    damage_event = create_sample_damage_event()
    logger.info(f"Damage event type: {type(damage_event)}")
    logger.info(f"Damage event amount: {getattr(damage_event, 'amount', 'NO AMOUNT ATTR')}")
    logger.info(f"Damage event overkill: {getattr(damage_event, 'overkill', 'NO OVERKILL ATTR')}")
    logger.info(f"Damage event critical: {getattr(damage_event, 'critical', 'NO CRITICAL ATTR')}")

    assert isinstance(damage_event, DamageEvent), f"Expected DamageEvent, got {type(damage_event)}"
    assert damage_event.amount == 12500, f"Expected damage 12500, got {damage_event.amount}"
    assert damage_event.overkill == 1200, f"Expected overkill 1200, got {damage_event.overkill}"

    # Test heal event
    heal_event = create_sample_heal_event()
    logger.info(f"Heal event type: {type(heal_event)}")
    logger.info(f"Heal event amount: {getattr(heal_event, 'amount', 'NO AMOUNT ATTR')}")
    logger.info(
        f"Heal event overhealing: {getattr(heal_event, 'overhealing', 'NO OVERHEALING ATTR')}"
    )
    logger.info(
        f"Heal event effective: {getattr(heal_event, 'effective_healing', 'NO EFFECTIVE ATTR')}"
    )

    assert isinstance(heal_event, HealEvent), f"Expected HealEvent, got {type(heal_event)}"
    assert heal_event.amount == 8500, f"Expected healing 8500, got {heal_event.amount}"
    assert (
        heal_event.overhealing == 1500
    ), f"Expected overhealing 1500, got {heal_event.overhealing}"
    assert (
        heal_event.effective_healing == 7000
    ), f"Expected effective healing 7000, got {heal_event.effective_healing}"

    logger.info("✓ Event parsing tests passed")
    return damage_event, heal_event


def test_character_stream_accumulation():
    """Test that character streams accumulate damage/healing correctly."""
    logger.info("=== Testing Character Stream Accumulation ===")

    # Create character stream
    character = CharacterEventStream(
        character_guid="Player-1234-56789ABC", character_name="TestPlayer"
    )

    # Create test events
    damage_event, heal_event = test_event_parsing()

    # Add events to character stream
    character.add_event(damage_event, "damage_done")
    character.add_event(heal_event, "healing_done")

    logger.info(f"Character total damage done: {character.total_damage_done}")
    logger.info(f"Character total healing done: {character.total_healing_done}")
    logger.info(f"Character damage events count: {len(character.damage_done)}")
    logger.info(f"Character healing events count: {len(character.healing_done)}")

    assert (
        character.total_damage_done == 12500
    ), f"Expected total damage 12500, got {character.total_damage_done}"
    assert (
        character.total_healing_done == 7000
    ), f"Expected total healing 7000, got {character.total_healing_done}"
    assert (
        len(character.damage_done) == 1
    ), f"Expected 1 damage event, got {len(character.damage_done)}"
    assert (
        len(character.healing_done) == 1
    ), f"Expected 1 healing event, got {len(character.healing_done)}"

    logger.info("✓ Character stream accumulation tests passed")
    return character


def test_dps_hps_calculation():
    """Test DPS/HPS calculation."""
    logger.info("=== Testing DPS/HPS Calculation ===")

    character = test_character_stream_accumulation()

    # Test DPS/HPS calculation over 10 seconds
    duration = 10.0
    dps = character.get_dps(duration)
    hps = character.get_hps(duration)

    logger.info(f"DPS over {duration}s: {dps}")
    logger.info(f"HPS over {duration}s: {hps}")

    expected_dps = 12500 / 10.0  # 1250.0
    expected_hps = 7000 / 10.0  # 700.0

    assert abs(dps - expected_dps) < 0.01, f"Expected DPS {expected_dps}, got {dps}"
    assert abs(hps - expected_hps) < 0.01, f"Expected HPS {expected_hps}, got {hps}"

    logger.info("✓ DPS/HPS calculation tests passed")
    return character


def test_database_storage():
    """Test database storage with correct field mappings."""
    logger.info("=== Testing Database Storage ===")

    # Create test database
    db = DatabaseManager("/tmp/debug_test.db")
    create_tables(db)

    # Create test encounter with character data
    character = test_dps_hps_calculation()

    encounter = Encounter(
        encounter_id=1234,
        encounter_name="Test Boss",
        difficulty=16,  # Mythic
        start_time=datetime.now(),
        duration=300.0,  # 5 minutes
        success=True,
    )

    encounter.add_character(character)

    # Store encounter data
    try:
        store_encounter_data(db, encounter)
        logger.info("✓ Database storage successful")

        # Verify stored data
        cursor = db.execute(
            """
            SELECT character_name, total_damage_done, total_healing_done,
                   dps, hps, combat_dps, combat_hps
            FROM character_metrics
            WHERE character_name = ?
        """,
            ("TestPlayer",),
        )

        row = cursor.fetchone()
        if row:
            logger.info(f"Stored character data: {dict(row)}")

            # Check that values are not zero
            assert (
                row["total_damage_done"] > 0
            ), f"total_damage_done is {row['total_damage_done']}, expected > 0"
            assert (
                row["total_healing_done"] > 0
            ), f"total_healing_done is {row['total_healing_done']}, expected > 0"
            assert row["dps"] > 0, f"dps is {row['dps']}, expected > 0"
            assert row["hps"] > 0, f"hps is {row['hps']}, expected > 0"

            logger.info("✓ Database field mapping tests passed")
        else:
            raise AssertionError("No character data found in database")

    except Exception as e:
        logger.error(f"Database storage failed: {e}")
        raise
    finally:
        db.close()


def test_field_name_consistency():
    """Test that field names are consistent between models and storage."""
    logger.info("=== Testing Field Name Consistency ===")

    character = CharacterEventStream(
        character_guid="Player-1234-56789ABC", character_name="TestPlayer"
    )

    # Check that character has expected field names
    expected_fields = [
        "total_damage_done",
        "total_healing_done",
        "total_damage_taken",
        "total_healing_received",
    ]

    for field in expected_fields:
        assert hasattr(character, field), f"Character missing field: {field}"
        logger.info(f"✓ Character has field: {field}")

    # Check that methods exist
    expected_methods = ["get_dps", "get_hps", "get_combat_dps", "get_combat_hps"]

    for method in expected_methods:
        assert hasattr(character, method), f"Character missing method: {method}"
        assert callable(getattr(character, method)), f"Character {method} is not callable"
        logger.info(f"✓ Character has callable method: {method}")

    logger.info("✓ Field name consistency tests passed")


def main():
    """Run all debugging tests."""
    logger.info("Starting comprehensive pipeline debugging...")

    try:
        # Run all tests
        test_field_name_consistency()
        test_event_parsing()
        test_character_stream_accumulation()
        test_dps_hps_calculation()
        test_database_storage()

        logger.info("🎉 ALL TESTS PASSED! Pipeline appears to be working correctly.")

    except Exception as e:
        logger.error(f"❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
