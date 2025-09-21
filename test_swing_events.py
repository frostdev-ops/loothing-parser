#!/usr/bin/env python3
"""
Test to see which swing events are being processed.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory, DamageEvent
from src.parser.categorizer import EventCategorizer
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

def test_swing_events():
    """Test which swing events are being processed."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print(f"Testing swing events with: {log_path.name}")
    print("-" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()
    categorizer = EventCategorizer()

    # Track events by type
    counts = {
        "SWING_DAMAGE_found": 0,
        "SWING_DAMAGE_LANDED_found": 0,
        "SWING_DAMAGE_damage_event": 0,
        "SWING_DAMAGE_LANDED_damage_event": 0,
        "SWING_DAMAGE_categorized": 0,
        "SWING_DAMAGE_LANDED_categorized": 0,
    }

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line_num > 100000:  # Test first 100k lines
                break

            if line_num % 25000 == 0:
                print(f"Processing line {line_num}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed and parsed.event_type in ["SWING_DAMAGE", "SWING_DAMAGE_LANDED"]:
                    event_type = parsed.event_type
                    counts[f"{event_type}_found"] += 1

                    # Try to create the event via EventFactory
                    event = event_factory.create_event(parsed)
                    if isinstance(event, DamageEvent):
                        counts[f"{event_type}_damage_event"] += 1

                        # Show first example of each type
                        if counts[f"{event_type}_damage_event"] == 1:
                            print(f"\nFirst {event_type} DamageEvent:")
                            print(f"  Amount: {event.amount:,}")
                            print(f"  Source: {event.source_name}")
                            print(f"  Dest: {event.dest_name}")

                    # Try categorizing the event
                    categories = categorizer.categorize_event(event)
                    if categories:
                        counts[f"{event_type}_categorized"] += 1

            except Exception as e:
                continue  # Ignore parse errors

    print(f"\n{'='*80}")
    print("SWING EVENT PROCESSING VERIFICATION")
    print(f"{'='*80}")

    for event_type in ["SWING_DAMAGE", "SWING_DAMAGE_LANDED"]:
        found = counts[f"{event_type}_found"]
        damage_events = counts[f"{event_type}_damage_event"]
        categorized = counts[f"{event_type}_categorized"]

        print(f"\n{event_type}:")
        print(f"  Found in log: {found:,}")
        print(f"  Converted to DamageEvent: {damage_events:,}")
        print(f"  Successfully categorized: {categorized:,}")

if __name__ == "__main__":
    test_swing_events()