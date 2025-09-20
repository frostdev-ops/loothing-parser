#!/usr/bin/env python3
"""
Quick test to verify our parser fixes work.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parser.parser import CombatLogParser
from src.segmentation.enhanced import EnhancedSegmenter
from src.segmentation.encounters import EncounterSegmenter


def test_fixes():
    """Test our parser fixes on the problematic log file."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Testing parser fixes on: {log_file}")
    print("=" * 60)

    # Parse the log file using the same method as CLI
    parser = CombatLogParser()
    segmenter = EncounterSegmenter()
    enhanced_segmenter = EnhancedSegmenter()

    total_events = 0
    print("Parsing events...")

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    parsed_line = parser.tokenizer.parse_line(line)
                    event = parser.event_factory.create_event(parsed_line)
                    segmenter.process_event(event)
                    enhanced_segmenter.process_event(event)
                    total_events += 1

                    # Progress indicator
                    if total_events % 50000 == 0:
                        print(f"  Processed {total_events:,} events...")

                except Exception:
                    continue

    print(f"Parsed {total_events:,} events")

    # Finalize data
    print("Finalizing encounters...")
    fights = segmenter.finalize()
    raid_encounters, mythic_plus_runs = enhanced_segmenter.finalize()

    print(f"Found {len(mythic_plus_runs)} M+ runs")

    # Find Operation: Floodgate runs
    floodgate_runs = [run for run in mythic_plus_runs if "Floodgate" in run.dungeon_name]

    if floodgate_runs:
        # Test the last complete run
        run = floodgate_runs[-1]
        print(f"\nTesting run: {run.dungeon_name} +{run.keystone_level}")
        print(f"Duration: {run.actual_time_seconds:.1f}s")
        print(f"Characters: {len(run.overall_characters)}")

        if run.overall_characters:
            # Calculate totals
            total_damage = sum(char.total_damage_done for char in run.overall_characters.values())
            total_healing = sum(char.total_healing_done for char in run.overall_characters.values())
            total_overhealing = sum(char.total_overhealing for char in run.overall_characters.values())

            print(f"\nDamage & Healing:")
            print(f"  Total Damage: {total_damage:,}")
            print(f"  Total Healing: {total_healing:,}")
            print(f"  Total Overhealing: {total_overhealing:,}")
            print(f"  Raw Healing (healing + overhealing): {total_healing + total_overhealing:,}")

            # Check activity
            active_chars = [
                char for char in run.overall_characters.values() if char.activity_percentage > 0
            ]

            if active_chars:
                avg_activity = sum(char.activity_percentage for char in active_chars) / len(
                    active_chars
                )
                print(f"  Avg Activity: {avg_activity:.1f}%")

                # Top DPS
                top_dps = sorted(
                    run.overall_characters.values(), key=lambda x: x.total_damage_done, reverse=True
                )[:3]

                print(f"\nTop 3 DPS:")
                for i, char in enumerate(top_dps, 1):
                    dps = (
                        char.get_combat_dps()
                        if char.combat_time > 0
                        else char.get_dps(run.actual_time_seconds)
                    )
                    print(
                        f"  {i}. {char.character_name}: {char.total_damage_done:,} damage, "
                        f"{dps:,.0f} DPS, {char.activity_percentage:.1f}% activity"
                    )

            # Verification
            print(f"\n" + "=" * 40)
            print("VERIFICATION RESULTS:")

            if total_damage > 50_000_000:
                print("✓ Damage totals reasonable (>50M)")
            else:
                print(f"✗ Damage totals too low: {total_damage:,}")

            if total_healing > 1_000_000:
                print("✓ Healing data captured (>1M)")
            else:
                print(f"✗ Healing data missing/low: {total_healing:,}")

            if len(active_chars) > 0:
                print(f"✓ Activity calculation working (avg {avg_activity:.1f}%)")
            else:
                print("✗ Activity calculation broken")

            chars_with_combat_time = [
                char for char in run.overall_characters.values() if char.combat_time > 0
            ]
            if len(chars_with_combat_time) > 0:
                avg_combat_time = sum(char.combat_time for char in chars_with_combat_time) / len(
                    chars_with_combat_time
                )
                print(f"✓ Combat time calculation working (avg {avg_combat_time:.1f}s)")
            else:
                print("✗ Combat time calculation broken")

        else:
            print("✗ No character data found")
    else:
        print("✗ No Floodgate runs found")


if __name__ == "__main__":
    test_fixes()
