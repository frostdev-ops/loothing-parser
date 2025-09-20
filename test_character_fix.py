#!/usr/bin/env python3
"""Test character data fix in parallel processing."""

from pathlib import Path
from src.processing.parallel_processor import ParallelLogProcessor

def test_character_data_fix():
    """Test that character damage data is properly populated after parallel processing."""
    print("Testing character data fix in parallel processing...")

    # Use one of the available example files
    log_path = Path("examples/WoWCombatLog-091925_190638.txt")

    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    # Process with parallel processor
    processor = ParallelLogProcessor(max_workers=4)
    fights, enhanced_data = processor.process_file(log_path)

    print(f"Processing completed:")
    print(f"- {len(fights)} fights found")
    print(f"- {len(enhanced_data.get('mythic_plus_runs', []))} M+ runs")
    print(f"- {len(enhanced_data.get('raid_encounters', []))} raid encounters")

    # Check M+ character data
    mythic_plus_runs = enhanced_data.get("mythic_plus_runs", [])
    if mythic_plus_runs:
        print("\nM+ character data:")
        for i, m_plus_run in enumerate(mythic_plus_runs[:2]):  # Check first 2
            print(f"\n  M+ Run {i+1}: {m_plus_run.dungeon_name} +{m_plus_run.keystone_level}")
            print(f"    Characters: {len(m_plus_run.overall_characters)}")

            # Show damage data for characters
            damage_found = False
            for char_guid, char_stream in m_plus_run.overall_characters.items():
                if char_stream.total_damage_done > 0:
                    print(f"    {char_stream.character_name}: {char_stream.total_damage_done:,} damage")
                    damage_found = True
                    break

            if not damage_found:
                print("    ❌ No damage data found")
            else:
                print("    ✅ Damage data populated correctly")

    # Check raid character data
    raid_encounters = enhanced_data.get("raid_encounters", [])
    if raid_encounters:
        print("\nRaid character data:")
        for i, raid_encounter in enumerate(raid_encounters[:2]):  # Check first 2
            print(f"\n  Raid {i+1}: {raid_encounter.boss_name}")
            print(f"    Characters: {len(raid_encounter.characters)}")

            # Show damage data for characters
            damage_found = False
            for char_guid, char_stream in raid_encounter.characters.items():
                if char_stream.total_damage_done > 0:
                    print(f"    {char_stream.character_name}: {char_stream.total_damage_done:,} damage")
                    damage_found = True
                    break

            if not damage_found:
                print("    ❌ No damage data found")
            else:
                print("    ✅ Damage data populated correctly")

    # Show processor stats
    stats = processor.get_stats()
    print(f"\nProcessor stats:")
    print(f"- Max workers: {stats['max_workers']}")
    print(f"- Parse errors: {stats['parse_errors']}")

    if stats['parse_errors'] > 0:
        print("- First few errors:")
        for error in stats['errors'][:3]:
            print(f"  {error}")

if __name__ == "__main__":
    test_character_data_fix()