#!/usr/bin/env python3
"""Test what types of events are being created."""

from src.parser.parser import CombatLogParser
from src.parser.events import DamageEvent, HealEvent, BaseEvent
from src.segmentation.encounters import EncounterSegmenter

def test_event_types():
    """Test event types and damage/healing tracking."""
    print("Testing event type creation...")

    parser = CombatLogParser()
    events = list(parser.parse_file("examples/WoWCombatLog-091625_041109.txt"))
    print(f"Total events parsed: {len(events)}")

    # Count event types
    damage_events = 0
    heal_events = 0
    base_events = 0
    damage_amount_total = 0
    heal_amount_total = 0

    for event in events[:1000]:  # Check first 1000 events
        if isinstance(event, DamageEvent):
            damage_events += 1
            damage_amount_total += event.amount
        elif isinstance(event, HealEvent):
            heal_events += 1
            heal_amount_total += event.amount
        elif isinstance(event, BaseEvent):
            base_events += 1

    print(f"DamageEvent instances: {damage_events}")
    print(f"HealEvent instances: {heal_events}")
    print(f"BaseEvent instances: {base_events}")
    print(f"Total damage amount in first 1000: {damage_amount_total:,}")
    print(f"Total heal amount in first 1000: {heal_amount_total:,}")

    # Now test the segmenter and fight events
    print("\nTesting fight event types...")
    segmenter = EncounterSegmenter()
    for event in events:
        segmenter.process_event(event)

    if segmenter.fights:
        fight = segmenter.fights[0]
        print(f"First fight has {len(fight.events)} events")
        print(f"First fight has {len(fight.participants)} participants")

        # Check types in the fight
        fight_damage = 0
        fight_heal = 0
        for event in fight.events[:100]:  # First 100 events in fight
            if isinstance(event, DamageEvent):
                fight_damage += 1
            elif isinstance(event, HealEvent):
                fight_heal += 1

        print(f"DamageEvents in first 100 fight events: {fight_damage}")
        print(f"HealEvents in first 100 fight events: {fight_heal}")

if __name__ == "__main__":
    test_event_types()