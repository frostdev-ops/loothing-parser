#!/usr/bin/env python3
"""
Debug event routing specifically.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parser.parser import CombatLogParser
from src.parser.events import HealEvent

def debug_route_event():
    """Debug event routing and healing calculations."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Debugging event routing on: {log_file}")
    print("=" * 60)

    parser = CombatLogParser()

    healing_events = []
    spell_heal_absorbed_events = []

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip() and len(healing_events) < 20:  # Only get first 20 events
                try:
                    parsed_line = parser.tokenizer.parse_line(line)
                    event = parser.event_factory.create_event(parsed_line)

                    # Check for healing events
                    if "HEAL" in event.event_type:
                        if event.event_type == "SPELL_HEAL_ABSORBED":
                            spell_heal_absorbed_events.append(event)
                        else:
                            healing_events.append(event)

                        print(f"\nEvent: {event.event_type}")
                        print(f"  Event class: {type(event)}")
                        print(f"  Is HealEvent: {isinstance(event, HealEvent)}")

                        if hasattr(event, 'amount'):
                            print(f"  Amount: {event.amount}")
                        if hasattr(event, 'overhealing'):
                            print(f"  Overhealing: {event.overhealing}")
                        if hasattr(event, 'effective_healing'):
                            print(f"  Effective healing: {event.effective_healing}")

                except Exception as e:
                    continue

            # Stop once we have enough examples
            if len(healing_events) >= 10 and len(spell_heal_absorbed_events) >= 5:
                break

    print(f"\nFound {len(healing_events)} healing events")
    print(f"Found {len(spell_heal_absorbed_events)} SPELL_HEAL_ABSORBED events")

    # Summary of effective healing values
    if healing_events:
        effective_healings = [event.effective_healing for event in healing_events if hasattr(event, 'effective_healing')]
        if effective_healings:
            print(f"\nEffective healing values from regular heal events:")
            for i, val in enumerate(effective_healings[:10]):
                print(f"  {i+1}. {val}")
            print(f"  Sum: {sum(effective_healings)}")

    if spell_heal_absorbed_events:
        absorbed_healings = [getattr(event, 'effective_healing', 0) for event in spell_heal_absorbed_events]
        print(f"\nEffective healing values from SPELL_HEAL_ABSORBED events:")
        for i, val in enumerate(absorbed_healings[:10]):
            print(f"  {i+1}. {val}")
        print(f"  Sum: {sum(absorbed_healings)}")

if __name__ == "__main__":
    debug_route_event()