#!/usr/bin/env python3
"""Test DPS/HPS calculations after ACL fix."""

from src.parser.parser import CombatLogParser
from src.segmentation.encounters import EncounterSegmenter
from src.models.character_events import CharacterEventStream


def test_dps_hps():
    """Test DPS/HPS calculations."""

    # Parse a small portion of the log
    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    # Process first 1000 events
    event_count = 0
    damage_events = 0
    heal_events = 0
    total_damage = 0
    total_healing = 0

    for event in parser.parse_file("examples/WoWCombatLog-091525_213021.txt"):
        event_count += 1
        if event_count > 1000:
            break

        segmenter.process_event(event)

        # Check damage events
        if hasattr(event, "amount") and "DAMAGE" in event.event_type:
            damage_events += 1
            total_damage += event.amount
            if damage_events <= 5:
                print(f"Damage event {damage_events}: {event.event_type}, amount: {event.amount}")

        # Check heal events
        if hasattr(event, "amount") and "HEAL" in event.event_type:
            heal_events += 1
            total_healing += event.amount
            if heal_events <= 5:
                print(f"Heal event {heal_events}: {event.event_type}, amount: {event.amount}")

    print(f"\nSummary:")
    print(f"Total events processed: {event_count}")
    print(f"Damage events: {damage_events}")
    print(f"Heal events: {heal_events}")
    print(f"Total damage: {total_damage:,}")
    print(f"Total healing: {total_healing:,}")
    print(f"Average damage per event: {total_damage/max(damage_events, 1):.0f}")
    print(f"Average healing per event: {total_healing/max(heal_events, 1):.0f}")

    # Test fight segmentation
    fights = segmenter.finalize()
    print(f"\nFights detected: {len(fights)}")

    if fights:
        fight = fights[0]
        print(f"First fight duration: {fight.get_duration_str()}")
        print(f"Participants: {len(fight.participants)}")

        # Create character streams for players
        characters = {}
        for guid, participant in fight.participants.items():
            if participant.get("is_player", False):
                characters[guid] = CharacterEventStream(
                    player_name=participant["name"], player_guid=guid
                )

        # Add events to character streams
        for event in fight.events:
            if hasattr(event, "source_guid") and event.source_guid in characters:
                characters[event.source_guid].add_event(event)

        # Calculate DPS/HPS using fight duration
        fight_duration = fight.duration
        print(f"\nPlayer performance (fight duration: {fight_duration:.1f}s):")
        for guid, char in characters.items():
            # Use encounter DPS/HPS (total time based)
            encounter_dps = char.get_dps(fight_duration)
            encounter_hps = char.get_hps(fight_duration)
            # Use combat DPS/HPS (combat time only)
            combat_dps = char.get_combat_dps()
            combat_hps = char.get_combat_hps()
            print(f"{char.player_name}: Encounter DPS={encounter_dps:.0f}, HPS={encounter_hps:.0f}")
            print(f"  Combat DPS={combat_dps:.0f}, HPS={combat_hps:.0f} (combat time: {char.combat_time:.1f}s)")


if __name__ == "__main__":
    test_dps_hps()
