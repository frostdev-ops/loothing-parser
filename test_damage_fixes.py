#!/usr/bin/env python3
"""Quick test of damage accuracy fixes."""

from src.parser.parser import CombatLogParser
from src.segmentation.encounters import EncounterSegmenter
from src.models.character_events import CharacterEventStream
from src.parser.categorizer import EventCategorizer


def test_damage_fixes():
    """Test the damage accuracy fixes."""
    print("Testing damage accuracy fixes...")

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    # Process events
    event_count = 0
    spell_absorbed_count = 0
    total_absorbed_damage = 0
    overkill_total = 0

    print("Processing events...")
    for event in parser.parse_file("examples/WoWCombatLog-091925_190638.txt"):
        segmenter.process_event(event)
        event_count += 1

        # Track SPELL_ABSORBED events
        if event.event_type == "SPELL_ABSORBED":
            spell_absorbed_count += 1
            if hasattr(event, "amount_absorbed"):
                total_absorbed_damage += event.amount_absorbed
                if spell_absorbed_count <= 3:  # Debug first few
                    print(
                        f"SPELL_ABSORBED #{spell_absorbed_count}: type={type(event)}, amount={event.amount_absorbed}"
                    )
                    print(f"  attacker_guid={getattr(event, 'attacker_guid', 'MISSING')}")
                    print(f"  absorber_guid={getattr(event, 'absorber_guid', 'MISSING')}")
                    print(f"  target_guid={getattr(event, 'target_guid', 'MISSING')}")

        # Track overkill in damage events
        if hasattr(event, "overkill") and event.overkill > 0:
            overkill_total += event.overkill

        # Limit for testing
        if event_count >= 100000:
            break

    print(f"Processed {event_count:,} events")
    print(f"SPELL_ABSORBED events: {spell_absorbed_count:,}")
    print(f"Total absorbed damage: {total_absorbed_damage:,}")
    print(f"Total overkill damage: {overkill_total:,}")

    # Get encounters
    fights = segmenter.finalize()
    print(f"Fights detected: {len(fights)}")

    if fights:
        fight = fights[0]  # Use first fight
        print(f"\nAnalyzing fight: {fight.encounter_name}")
        print(f"Duration: {fight.duration:.1f}s")

        # Create character streams
        characters = {}
        categorizer = EventCategorizer()

        # Create character streams for players
        for guid, participant in fight.participants.items():
            if participant.get("is_player", False):
                characters[guid] = CharacterEventStream(
                    character_guid=guid, character_name=participant["name"]
                )

        print(f"Created {len(characters)} character streams:")
        for guid, char in characters.items():
            print(f"  {guid}: {char.character_name}")

        categorizer.set_character_streams(characters)

        # Process events through categorizer
        absorbed_damage_credited = 0
        damage_events_processed = 0

        for event in fight.events:
            categorizer.route_event(event)

            if event.event_type == "SPELL_ABSORBED" and hasattr(event, "amount_absorbed"):
                absorbed_damage_credited += event.amount_absorbed

            if "DAMAGE" in event.event_type:
                damage_events_processed += 1

        print(f"\nEvent processing results:")
        print(f"Damage events processed: {damage_events_processed:,}")
        print(f"Absorbed damage credited to attackers: {absorbed_damage_credited:,}")

        # Show character damage totals
        print(f"\nCharacter damage totals:")
        for guid, char in characters.items():
            if char.total_damage_done > 0:
                print(f"{char.character_name}: {char.total_damage_done:,} damage")


if __name__ == "__main__":
    test_damage_fixes()
