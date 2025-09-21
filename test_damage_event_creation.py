#!/usr/bin/env python3
"""
Test to verify which events are being converted to DamageEvent objects.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory, DamageEvent
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

def test_damage_event_creation():
    """Test which events are being converted to DamageEvent objects."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print(f"Testing DamageEvent creation with: {log_path.name}")
    print("-" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()

    # Track events by type
    event_counts = {
        "SWING_DAMAGE": {"found": 0, "damage_events": 0},
        "SWING_DAMAGE_LANDED": {"found": 0, "damage_events": 0},
        "DAMAGE_SPLIT": {"found": 0, "damage_events": 0},
        "RANGE_DAMAGE": {"found": 0, "damage_events": 0},
        "SPELL_DAMAGE": {"found": 0, "damage_events": 0},
    }

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line_num > 50000:  # Test first 50k lines for speed
                break

            if line_num % 10000 == 0:
                print(f"Processing line {line_num}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed and parsed.event_type in event_counts:
                    event_type = parsed.event_type
                    event_counts[event_type]["found"] += 1

                    # Try to create the event via EventFactory
                    event = event_factory.create_event(parsed)
                    if isinstance(event, DamageEvent):
                        event_counts[event_type]["damage_events"] += 1

                        # Show first example of each type
                        if event_counts[event_type]["damage_events"] == 1:
                            print(f"\nFirst {event_type} converted to DamageEvent:")
                            print(f"  Amount: {event.amount:,}")
                            print(f"  Source: {event.source_name}")
                            print(f"  Dest: {event.dest_name}")

            except Exception as e:
                continue  # Ignore parse errors

    print(f"\n{'='*80}")
    print("DAMAGE EVENT CREATION VERIFICATION")
    print(f"{'='*80}")

    for event_type, counts in event_counts.items():
        found = counts["found"]
        damage_events = counts["damage_events"]

        print(f"\n{event_type}:")
        print(f"  Found in log: {found:,}")
        print(f"  Converted to DamageEvent: {damage_events:,}")

        if found > 0:
            conversion_rate = (damage_events / found * 100)
            print(f"  Conversion rate: {conversion_rate:.1f}%")

    print(f"\n{'='*60}")
    print("EXPECTED RESULTS AFTER FIX:")
    print("- SWING_DAMAGE: Should be converted to DamageEvent")
    print("- SWING_DAMAGE_LANDED: Should NOT be converted to DamageEvent")
    print("- DAMAGE_SPLIT: Should NOT be converted to DamageEvent")
    print("- RANGE_DAMAGE: Should be converted to DamageEvent")
    print("- SPELL_DAMAGE: Should be converted to DamageEvent")

if __name__ == "__main__":
    test_damage_event_creation()