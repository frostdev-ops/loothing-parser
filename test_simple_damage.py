#!/usr/bin/env python3
"""Simple test of damage calculation fix."""

from src.models.character_events import CharacterEventStream, DamageEvent
from datetime import datetime


def test_simple_damage():
    """Test our damage calculation fix directly."""
    print("Testing damage calculation fix...")

    # Create a character stream
    char = CharacterEventStream(
        character_guid="Player-123",
        character_name="TestPlayer"
    )

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
    print(f"Expected (with overkill): {damage_event.amount + damage_event.overkill:,}")

    # Test calculation
    expected = damage_event.amount + (damage_event.overkill if damage_event.overkill > 0 else 0)
    if char.total_damage_done == expected:
        print("✅ Overkill damage fix working correctly!")
    else:
        print(f"❌ Overkill damage fix NOT working - got {char.total_damage_done}, expected {expected}")


if __name__ == "__main__":
    test_simple_damage()