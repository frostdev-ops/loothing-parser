#!/usr/bin/env python3
"""
Test to verify which damage events are being processed after our fix.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory
from src.parser.categorizer import EventCategorizer
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

def test_event_processing():
    """Test which events are being processed vs ignored."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print(f"Testing event processing with: {log_path.name}")
    print("-" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()
    categorizer = EventCategorizer()

    # Track events by type
    event_counts = {
        "SWING_DAMAGE": {"found": 0, "processed": 0, "categorized": 0},
        "SWING_DAMAGE_LANDED": {"found": 0, "processed": 0, "categorized": 0},
        "DAMAGE_SPLIT": {"found": 0, "processed": 0, "categorized": 0},
        "RANGE_DAMAGE": {"found": 0, "processed": 0, "categorized": 0},
    }

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line_num > 100000:  # Test first 100k lines for speed
                break

            if line_num % 25000 == 0:
                print(f"Processing line {line_num}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed and parsed.event_type in event_counts:
                    event_type = parsed.event_type
                    event_counts[event_type]["found"] += 1

                    # Try to create the event via EventFactory
                    event = event_factory.create_event(parsed)
                    if event and hasattr(event, 'amount') and event.amount is not None:
                        event_counts[event_type]["processed"] += 1

                    # Try categorizing the event
                    categories = categorizer.categorize_event(event)
                    if categories:
                        event_counts[event_type]["categorized"] += 1

            except Exception as e:
                continue  # Ignore parse errors

    print(f"\n{'='*80}")
    print("EVENT PROCESSING VERIFICATION")
    print(f"{'='*80}")

    for event_type, counts in event_counts.items():
        found = counts["found"]
        processed = counts["processed"]
        categorized = counts["categorized"]

        print(f"\n{event_type}:")
        print(f"  Found in log: {found:,}")
        print(f"  EventFactory processed: {processed:,}")
        print(f"  Categorizer processed: {categorized:,}")

        if found > 0:
            proc_rate = (processed / found * 100)
            cat_rate = (categorized / found * 100)
            print(f"  Processing rate: {proc_rate:.1f}%")
            print(f"  Categorization rate: {cat_rate:.1f}%")

    print(f"\n{'='*60}")
    print("EXPECTED RESULTS AFTER FIX:")
    print("- SWING_DAMAGE: Should be processed and categorized")
    print("- SWING_DAMAGE_LANDED: Should NOT be categorized")
    print("- DAMAGE_SPLIT: Should NOT be categorized")
    print("- RANGE_DAMAGE: Should be processed and categorized")

if __name__ == "__main__":
    test_event_processing()