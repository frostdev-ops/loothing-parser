#!/usr/bin/env python3
"""
Debug SPELL_HEAL_ABSORBED events specifically.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parser.parser import CombatLogParser

def debug_absorbed():
    """Debug SPELL_HEAL_ABSORBED events."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Debugging SPELL_HEAL_ABSORBED events on: {log_file}")
    print("=" * 60)

    parser = CombatLogParser()

    absorbed_count = 0

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip() and absorbed_count < 5:  # Only process first 5 SPELL_HEAL_ABSORBED events
                try:
                    parsed_line = parser.tokenizer.parse_line(line)
                    event = parser.event_factory.create_event(parsed_line)

                    # Check for SPELL_HEAL_ABSORBED events
                    if event.event_type == "SPELL_HEAL_ABSORBED":
                        absorbed_count += 1
                        print(f"\nSPELL_HEAL_ABSORBED Event #{absorbed_count}:")
                        print(f"  Raw line: {line.strip()}")
                        print(f"  Event class: {type(event)}")

                        # Check basic fields
                        print(f"  Source: {event.source_name}")
                        print(f"  Target: {event.dest_name}")

                        # Check for healing fields
                        if hasattr(event, 'amount'):
                            print(f"  Amount: {event.amount}")
                        else:
                            print(f"  Amount: NOT FOUND")

                        if hasattr(event, 'overhealing'):
                            print(f"  Overhealing: {event.overhealing}")
                        else:
                            print(f"  Overhealing: NOT FOUND")

                        if hasattr(event, 'absorbed'):
                            print(f"  Absorbed: {event.absorbed}")
                        else:
                            print(f"  Absorbed: NOT FOUND")

                        if hasattr(event, 'effective_healing'):
                            print(f"  Effective Healing: {event.effective_healing}")
                        else:
                            print(f"  Effective Healing: NOT FOUND")

                        # Look at all attributes
                        print(f"  All attributes: {[attr for attr in dir(event) if not attr.startswith('_') and not callable(getattr(event, attr))]}")

                except Exception as e:
                    if absorbed_count < 5:
                        print(f"Error parsing line {line_num}: {e}")
                    continue

            if absorbed_count >= 5:
                break

    print(f"\nFound {absorbed_count} SPELL_HEAL_ABSORBED events")

if __name__ == "__main__":
    debug_absorbed()