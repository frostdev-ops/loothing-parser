#!/usr/bin/env python3
"""Simple test of damage calculation fix."""

from src.models.character_events import CharacterEventStream, DamageEvent
from datetime import datetime


def test_simple_damage():
    """Test our damage calculation fix directly."""
    print("Testing damage calculation fix...")

    # Create a character stream
    char = CharacterEventStream(character_guid="Player-123", character_name="TestPlayer")

    # Create a mock damage event with overkill
    damage_event = DamageEvent(
        timestamp=datetime.now(),
        event_type="SPELL_DAMAGE",
        raw_line="test",
        amount=1000000,  # 1M base damage
        overkill=500000,  # 500K overkill
    )

    print(f"Damage event: {damage_event.amount:,} base + {damage_event.overkill:,} overkill")

    # Add the event to the character stream
    char.add_event(damage_event, "damage_done")

    print(f"Character total damage: {char.total_damage_done:,}")
    print(f"Character overkill damage: {char.total_overkill_done:,}")

    # Test calculation - overkill should now be separate from total damage
    expected_damage = damage_event.amount  # Only actual damage
    expected_overkill = damage_event.overkill  # Overkill tracked separately

    damage_correct = char.total_damage_done == expected_damage
    overkill_correct = char.total_overkill_done == expected_overkill

    if damage_correct and overkill_correct:
        print("✅ Overkill damage fix working correctly!")
        print(f"  ✓ Damage: {char.total_damage_done:,} (excludes overkill)")
        print(f"  ✓ Overkill: {char.total_overkill_done:,} (tracked separately)")
    else:
        print("❌ Overkill damage fix NOT working:")
        if not damage_correct:
            print(f"  ❌ Damage: got {char.total_damage_done:,}, expected {expected_damage:,}")
        if not overkill_correct:
            print(f"  ❌ Overkill: got {char.total_overkill_done:,}, expected {expected_overkill:,}")


if __name__ == "__main__":
    test_simple_damage()
