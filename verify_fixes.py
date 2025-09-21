#!/usr/bin/env python3
"""
Simple verification script to test that DPS/HPS parsing is working correctly.
"""
import sys
import os
sys.path.insert(0, "/app")

from datetime import datetime
from src.parser.events import EventFactory, DamageEvent, HealEvent
from src.parser.tokenizer import ParsedLine
from src.models.enhanced_character import EnhancedCharacter

def test_dps_hps_parsing():
    print("🔍 Testing DPS/HPS parsing with fixes applied...")

    # Test damage parsing
    damage_line = ParsedLine(
        timestamp=datetime.now(),
        event_type="SPELL_DAMAGE",
        raw_line="test",
        base_params=["Player-123", "TestPlayer", "0x511", "0", "Enemy-456", "TestBoss", "0xa48", "0"],
        prefix_params=[12345, "Test Spell", 4],
        suffix_params=[
            # 19 ACL fields
            "Player-123", "info", 85000, 100000, 5000, 3000, 2500, "res", 15.5, 20.0, 25.0,
            0, 0, 0, 0, 0, 0, 0, 0,
            # Damage parameters at index 19
            10000,  # amount
            500,    # overkill
            4,      # school
            0, 0, 0,  # resisted, blocked, absorbed
            True, False, False  # critical, glancing, crushing
        ],
        advanced_params={}
    )

    damage_event = EventFactory.create_event(damage_line)
    print(f"✅ Damage event parsed: {damage_event.amount} damage")

    # Test healing parsing
    heal_line = ParsedLine(
        timestamp=datetime.now(),
        event_type="SPELL_HEAL",
        raw_line="test",
        base_params=["Player-789", "TestHealer", "0x511", "0", "Player-123", "TestPlayer", "0x511", "0"],
        prefix_params=[54321, "Test Heal", 2],
        suffix_params=[
            # 19 ACL fields
            "Player-123", "info", 75000, 100000, 5000, 3000, 2500, "res", 15.5, 20.0, 25.0,
            0, 0, 0, 0, 0, 0, 0, 0,
            # Healing parameters at index 19
            6000,  # amount
            1000,  # overhealing
            0,     # absorbed
            True,  # critical
            0, 0   # padding
        ],
        advanced_params={}
    )

    heal_event = EventFactory.create_event(heal_line)
    print(f"✅ Heal event parsed: {heal_event.amount} healing, {heal_event.overhealing} overheal")
    print(f"✅ Effective healing: {heal_event.effective_healing}")

    # Test character accumulation
    character = EnhancedCharacter(
        character_guid="Player-123",
        character_name="TestPlayer"
    )

    character.add_event(damage_event, "damage_done")
    character.add_event(heal_event, "healing_done")

    print(f"✅ Character damage total: {character.total_damage_done}")
    print(f"✅ Character healing total: {character.total_healing_done}")

    # Test DPS/HPS calculation
    duration = 10.0
    dps = character.get_dps(duration)
    hps = character.get_hps(duration)

    print(f"✅ DPS over {duration}s: {dps}")
    print(f"✅ HPS over {duration}s: {hps}")

    # Verify expected values
    expected_damage = 10000
    expected_healing = 5000  # 6000 - 1000 overheal
    expected_dps = expected_damage / duration
    expected_hps = expected_healing / duration

    if (character.total_damage_done == expected_damage and
        character.total_healing_done == expected_healing and
        abs(dps - expected_dps) < 0.01 and
        abs(hps - expected_hps) < 0.01):
        print("🎉 ALL TESTS PASSED! DPS/HPS parsing is working correctly!")
        return True
    else:
        print("❌ Tests failed - values don't match expected results")
        return False

if __name__ == "__main__":
    try:
        success = test_dps_hps_parsing()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)