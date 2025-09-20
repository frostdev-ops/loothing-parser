#!/usr/bin/env python3
"""Test overkill damage inclusion fix."""

from src.parser.parser import CombatLogParser
from src.segmentation.encounters import EncounterSegmenter
from src.models.character_events import CharacterEventStream
from src.parser.categorizer import EventCategorizer


def test_overkill_fix():
    """Test if overkill damage is being properly included."""
    print("Testing overkill damage inclusion...")

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    # Process events
    event_count = 0
    damage_events_with_overkill = 0
    total_base_damage = 0
    total_overkill = 0

    print("Processing events...")
    for event in parser.parse_file("examples/WoWCombatLog-091925_190638.txt"):
        segmenter.process_event(event)
        event_count += 1

        # Track damage events with overkill
        if hasattr(event, "amount") and hasattr(event, "overkill"):
            if "DAMAGE" in event.event_type:
                total_base_damage += event.amount
                if event.overkill > 0:
                    damage_events_with_overkill += 1
                    total_overkill += event.overkill

        # Limit for testing
        if event_count >= 50000:
            break

    print(f"Processed {event_count:,} events")
    print(f"Damage events with overkill: {damage_events_with_overkill:,}")
    print(f"Total base damage: {total_base_damage:,}")
    print(f"Total overkill damage: {total_overkill:,}")
    print(f"Combined damage (should match our fix): {total_base_damage + total_overkill:,}")

    # Get encounters and test character damage
    fights = segmenter.finalize()
    if fights:
        fight = fights[0]
        print(f"\nTesting character damage calculation:")
        print(f"Fight: {fight.encounter_name}")

        # Create character streams and categorizer
        characters = {}
        categorizer = EventCategorizer()

        for guid, participant in fight.participants.items():
            if participant.get("is_player", False):
                characters[guid] = CharacterEventStream(
                    character_guid=guid, character_name=participant["name"]
                )

        categorizer.set_character_streams(characters)

        # Process fight events
        for event in fight.events:
            categorizer.route_event(event)

        # Show results
        print(f"\nCharacter damage totals (with overkill fix):")
        total_player_damage = 0
        for guid, char in characters.items():
            if char.total_damage_done > 0:
                print(f"{char.character_name}: {char.total_damage_done:,}")
                total_player_damage += char.total_damage_done

        print(f"\nTotal player damage: {total_player_damage:,}")


if __name__ == "__main__":
    test_overkill_fix()