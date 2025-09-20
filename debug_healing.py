#!/usr/bin/env python3
"""
Debug healing calculation issues.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parser.parser import CombatLogParser
from src.segmentation.enhanced import EnhancedSegmenter

def debug_healing():
    """Debug healing calculation issues."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Debugging healing calculation on: {log_file}")
    print("=" * 60)

    parser = CombatLogParser()
    segmenter = EnhancedSegmenter()

    total_events = 0
    heal_events_count = 0

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip() and heal_events_count < 10:  # Only process first 10 heal events
                try:
                    parsed_line = parser.tokenizer.parse_line(line)
                    event = parser.event_factory.create_event(parsed_line)

                    # Check for healing events
                    if "HEAL" in event.event_type:
                        heal_events_count += 1
                        print(f"\nHeal Event #{heal_events_count}:")
                        print(f"  Event Type: {event.event_type}")
                        print(f"  Raw line: {line.strip()}")

                        if hasattr(event, 'amount'):
                            print(f"  Amount: {event.amount}")
                        else:
                            print(f"  Amount: NOT FOUND")

                        if hasattr(event, 'overhealing'):
                            print(f"  Overhealing: {event.overhealing}")
                        else:
                            print(f"  Overhealing: NOT FOUND")

                        if hasattr(event, 'effective_healing'):
                            print(f"  Effective Healing: {event.effective_healing}")
                        else:
                            print(f"  Effective Healing: NOT FOUND")

                        print(f"  Source: {event.source_name}")
                        print(f"  Target: {event.dest_name}")

                    segmenter.process_event(event)
                    total_events += 1

                except Exception as e:
                    if heal_events_count < 10:
                        print(f"Error parsing line {line_num}: {e}")
                    continue

            if heal_events_count >= 10:
                break

    print(f"\nProcessed {total_events:,} events to find {heal_events_count} heal events")

if __name__ == "__main__":
    debug_healing()