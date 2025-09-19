#!/usr/bin/env python3
"""Test that DPS/HPS calculations are working after fixes."""

from src.parser.parser import CombatLogParser
from src.parser.events import DamageEvent, HealEvent
from src.segmentation.encounters import EncounterSegmenter
from src.analyzer.interactive import InteractiveAnalyzer

def test_dps_hps_fixes():
    """Test that event types and DPS/HPS calculations work."""
    print("Testing DPS/HPS fixes...")

    # Parse a small subset of events for quick testing
    parser = CombatLogParser()
    events = list(parser.parse_file("examples/WoWCombatLog-091625_041109.txt"))
    print(f"Parsed {len(events)} events")

    # Check event types in first 500 events
    damage_events = 0
    heal_events = 0
    total_damage = 0
    total_healing = 0

    for event in events[:500]:
        if isinstance(event, DamageEvent):
            damage_events += 1
            total_damage += event.amount
        elif isinstance(event, HealEvent):
            heal_events += 1
            total_healing += event.amount

    print(f"Event type analysis (first 500 events):")
    print(f"  DamageEvents: {damage_events}")
    print(f"  HealEvents: {heal_events}")
    print(f"  Total damage: {total_damage:,}")
    print(f"  Total healing: {total_healing:,}")

    # Test fight segmentation and character data
    segmenter = EncounterSegmenter()
    for event in events:
        segmenter.process_event(event)

    print(f"\nFound {len(segmenter.fights)} fights")

    # Test analyzer with improved character detection
    analyzer = InteractiveAnalyzer(segmenter.fights, None)

    # Test first boss fight for character data
    boss_fights = [f for f in analyzer.fights if f.fight_type.value == "dungeon_boss"]
    if boss_fights:
        fight = boss_fights[0]
        print(f"\nTesting character data for: {fight.encounter_name}")
        print(f"  Fight has {len(fight.participants)} participants")
        print(f"  Fight has {len(fight.events)} events")

        characters = analyzer._get_encounter_characters(fight)
        if characters:
            print(f"  Character data found: {len(characters)} players")
            for i, (guid, char) in enumerate(characters.items()):
                if i >= 3:  # Show first 3 players
                    break
                dps = char.get_dps(fight.duration) if fight.duration else 0
                hps = char.get_hps(fight.duration) if fight.duration else 0
                print(f"    {char.character_name}: {dps:,.0f} DPS, {hps:,.0f} HPS, {char.death_count} deaths")
        else:
            print("  No character data available")

            # Debug the participant data
            print("  Debug participant info:")
            for i, (guid, participant) in enumerate(fight.participants.items()):
                if i >= 3:  # Show first 3
                    break
                print(f"    {guid[:30]}... = is_player: {participant.get('is_player', 'Missing')}, name: {participant.get('name', 'No name')}")

    # Test detailed player data (should now have avg DPS/HPS)
    if characters:
        first_player_name = list(characters.values())[0].character_name
        player_data = analyzer._get_player_detailed_data(first_player_name)
        if player_data:
            print(f"\nPlayer detailed data for {first_player_name}:")
            print(f"  Encounters: {len(player_data['encounters'])}")
            print(f"  Average DPS: {player_data['avg_dps']:,.0f}")
            print(f"  Average HPS: {player_data['avg_hps']:,.0f}")
        else:
            print(f"No detailed data found for {first_player_name}")

    print("\nTest completed!")

if __name__ == "__main__":
    test_dps_hps_fixes()