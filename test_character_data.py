#!/usr/bin/env python3
"""
Quick test script to verify character data is properly populated.
"""

import sys
from src.parser.parser import CombatLogParser
from src.segmentation.enhanced import EnhancedSegmenter
from src.analyzer.interactive import InteractiveAnalyzer


def test_character_data():
    """Test that character data is properly populated and accessible."""
    print("Testing character data population...")

    # Parse the log
    parser = CombatLogParser()
    events = list(parser.parse_file("examples/WoWCombatLog-091625_041109.txt"))
    print(f"Parsed {len(events)} events")

    # Segment encounters
    segmenter = EnhancedSegmenter()
    for event in events:
        segmenter.process_event(event)
    enhanced_data = segmenter.finalize()
    print(f"Found {len(enhanced_data.get('raid_encounters', []))} raid encounters")
    print(f"Found {len(enhanced_data.get('mythic_plus_runs', []))} M+ runs")

    # Create analyzer and get fights
    analyzer = InteractiveAnalyzer()
    analyzer.load_data(events, enhanced_data)

    print(f"\nTesting {len(analyzer.fights)} fights for character data:")

    for i, fight in enumerate(analyzer.fights):
        print(f"\nFight {i+1}: {fight.encounter_name} ({fight.fight_type.value})")
        print(f"  Success: {fight.success}")
        print(f"  Duration: {fight.get_duration_str()}")
        print(f"  Participants: {fight.get_player_count()}")

        # Test character data access
        characters = analyzer._get_encounter_characters(fight)
        if characters:
            print(f"  Characters found: {len(characters)}")
            for guid, char in list(characters.items())[:3]:  # Show first 3
                print(
                    f"    {char.character_name}: {char.total_damage_done:,} damage, {char.total_healing_done:,} healing, {char.death_count} deaths"
                )
        else:
            print("  No character data available")

    print("\nTest completed!")


if __name__ == "__main__":
    test_character_data()
