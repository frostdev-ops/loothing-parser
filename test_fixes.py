#!/usr/bin/env python3
"""
Test script to verify parser accuracy fixes.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.segmentation.enhanced import EnhancedSegmenter
from src.parser.events import EventParser


def test_parser_fixes():
    """Test that parser fixes work correctly."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Testing parser fixes on {log_file}")
    print("=" * 50)

    # Parse the file
    parser = EventParser()
    segmenter = EnhancedEncounterSegmenter()

    print("Parsing events...")
    event_count = 0
    with open(log_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    event = parser.parse_line(line.strip())
                    if event:
                        segmenter.process_event(event)
                        event_count += 1

                        # Progress indicator
                        if event_count % 50000 == 0:
                            print(f"  Processed {event_count:,} events...")

                except Exception as e:
                    print(f"Error parsing line {line_num}: {e}")
                    continue

    print(f"Parsed {event_count:,} events")

    # Finalize encounters
    print("Finalizing encounters...")
    results = segmenter.finalize()

    print(f"Found {len(results['mythic_plus_runs'])} M+ runs")

    # Test the Operation: Floodgate run that showed issues
    floodgate_runs = [run for run in results["mythic_plus_runs"] if "Floodgate" in run.dungeon_name]

    if not floodgate_runs:
        print("ERROR: No Operation: Floodgate runs found!")
        return

    # Get the run (should be multiple pulls of same dungeon)
    print(f"Found {len(floodgate_runs)} Floodgate runs")

    # Test the last/complete run
    run = floodgate_runs[-1]

    print(f"\nTesting run: {run.dungeon_name} +{run.keystone_level}")
    print(f"Duration: {run.actual_time_seconds:.1f}s")
    print(f"Characters: {len(run.overall_characters)}")

    # Check damage totals
    total_damage = sum(char.total_damage_done for char in run.overall_characters.values())
    total_healing = sum(char.total_healing_done for char in run.overall_characters.values())

    print(f"\nDamage & Healing Summary:")
    print(f"Total Damage: {total_damage:,}")
    print(f"Total Healing: {total_healing:,}")

    # Check individual character data
    print(f"\nTop 5 DPS:")
    dps_chars = sorted(
        run.overall_characters.values(), key=lambda x: x.total_damage_done, reverse=True
    )[:5]

    for i, char in enumerate(dps_chars, 1):
        dps = (
            char.get_combat_dps() if char.combat_time > 0 else char.get_dps(run.actual_time_seconds)
        )
        print(
            f"  {i}. {char.character_name}: {char.total_damage_done:,} damage, "
            f"{dps:,.0f} DPS, {char.activity_percentage:.1f}% activity, "
            f"{char.combat_time:.1f}s combat time"
        )

    print(f"\nTop 3 Healers:")
    heal_chars = sorted(
        run.overall_characters.values(), key=lambda x: x.total_healing_done, reverse=True
    )[:3]

    for i, char in enumerate(heal_chars, 1):
        hps = (
            char.get_combat_hps() if char.combat_time > 0 else char.get_hps(run.actual_time_seconds)
        )
        print(
            f"  {i}. {char.character_name}: {char.total_healing_done:,} healing, "
            f"{hps:,.0f} HPS, {char.activity_percentage:.1f}% activity"
        )

    # Verify fixes
    print(f"\n" + "=" * 50)
    print("VERIFICATION:")

    # Check if damage is reasonable (should be much higher than 20M total)
    if total_damage > 50_000_000:  # 50M seems reasonable for a full M+ run
        print("✓ Damage totals look reasonable")
    else:
        print(f"✗ Damage totals still too low: {total_damage:,}")

    # Check if healing is present
    if total_healing > 1_000_000:  # At least 1M healing
        print("✓ Healing data is being captured")
    else:
        print(f"✗ Healing data missing or too low: {total_healing:,}")

    # Check if activity percentages are working
    active_chars = [
        char for char in run.overall_characters.values() if char.activity_percentage > 0
    ]
    if len(active_chars) > 0:
        avg_activity = sum(char.activity_percentage for char in active_chars) / len(active_chars)
        print(f"✓ Activity percentages working: avg {avg_activity:.1f}%")
    else:
        print("✗ Activity percentages still 0%")

    # Check combat time calculation
    chars_with_combat_time = [
        char for char in run.overall_characters.values() if char.combat_time > 0
    ]
    if len(chars_with_combat_time) > 0:
        avg_combat_time = sum(char.combat_time for char in chars_with_combat_time) / len(
            chars_with_combat_time
        )
        print(f"✓ Combat time calculation working: avg {avg_combat_time:.1f}s")
    else:
        print("✗ Combat time calculation not working")


if __name__ == "__main__":
    test_parser_fixes()
