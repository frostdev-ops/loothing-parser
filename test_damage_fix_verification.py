#!/usr/bin/env python3
"""
Verification script to confirm DAMAGE_SPLIT, RANGE_DAMAGE, and SWING_DAMAGE_LANDED
events are now being processed correctly after the fix.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

def test_damage_event_processing():
    """Test that previously missing damage events are now processed correctly."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print(f"Testing damage event processing with: {log_path.name}")
    print("-" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()

    # Track events by type
    event_counts = {
        "DAMAGE_SPLIT": 0,
        "RANGE_DAMAGE": 0,
        "SWING_DAMAGE_LANDED": 0,
        "DAMAGE_SPLIT_processed": 0,
        "RANGE_DAMAGE_processed": 0,
        "SWING_DAMAGE_LANDED_processed": 0
    }

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 100000 == 0:
                print(f"Processing line {line_num}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed and parsed.event_type in ["DAMAGE_SPLIT", "RANGE_DAMAGE", "SWING_DAMAGE_LANDED"]:
                    event_counts[parsed.event_type] += 1

                    # Try to create the event
                    event = event_factory.create_event(parsed)
                    if event and hasattr(event, 'amount') and event.amount is not None:
                        event_counts[f"{parsed.event_type}_processed"] += 1

                        # Show first example of each type
                        if event_counts[f"{parsed.event_type}_processed"] == 1:
                            print(f"\nFirst {parsed.event_type} event processed successfully:")
                            print(f"  Damage amount: {event.amount:,}")
                            print(f"  Source: {event.source_name}")
                            print(f"  Dest: {event.dest_name}")

            except Exception as e:
                continue  # Ignore parse errors

    print(f"\n{'='*60}")
    print("DAMAGE EVENT PROCESSING VERIFICATION")
    print(f"{'='*60}")

    for event_type in ["DAMAGE_SPLIT", "RANGE_DAMAGE", "SWING_DAMAGE_LANDED"]:
        found = event_counts[event_type]
        processed = event_counts[f"{event_type}_processed"]
        percentage = (processed / found * 100) if found > 0 else 0

        print(f"\n{event_type}:")
        print(f"  Found in log: {found:,}")
        print(f"  Successfully processed: {processed:,}")
        print(f"  Processing rate: {percentage:.1f}%")

    total_found = sum(event_counts[t] for t in ["DAMAGE_SPLIT", "RANGE_DAMAGE", "SWING_DAMAGE_LANDED"])
    total_processed = sum(event_counts[f"{t}_processed"] for t in ["DAMAGE_SPLIT", "RANGE_DAMAGE", "SWING_DAMAGE_LANDED"])
    overall_percentage = (total_processed / total_found * 100) if total_found > 0 else 0

    print(f"\nOVERALL SUMMARY:")
    print(f"  Total missing events found: {total_found:,}")
    print(f"  Total successfully processed: {total_processed:,}")
    print(f"  Overall success rate: {overall_percentage:.1f}%")

    if overall_percentage >= 95:
        print("\n✅ FIX SUCCESSFUL: Missing damage events are now being processed!")
    else:
        print("\n❌ FIX INCOMPLETE: Some events are still not being processed correctly.")

if __name__ == "__main__":
    test_damage_event_processing()