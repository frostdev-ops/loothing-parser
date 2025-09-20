#!/usr/bin/env python3
"""
Simple test to verify our fixes work by just checking one encounter.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.cli import parse_log_file

def quick_test():
    """Quick test of our parser fixes."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Quick test of parser fixes on: {log_file}")
    print("=" * 60)

    try:
        # Use the CLI's parse function which should now work with our fixes
        parser_data = parse_log_file(log_file)

        # Check if we have enhanced data
        enhanced_data = parser_data.get('enhanced_data', {})
        if enhanced_data:
            mythic_runs = enhanced_data.get('mythic_plus_runs', [])

            print(f"✓ Enhanced segmenter working: {len(mythic_runs)} M+ runs detected")

            # Find Operation: Floodgate runs
            floodgate_runs = [run for run in mythic_runs if 'Floodgate' in run.dungeon_name]

            if floodgate_runs:
                # Test the last complete run
                run = floodgate_runs[-1]
                print(f"✓ Found Floodgate run: +{run.keystone_level}")
                print(f"  Duration: {run.actual_time_seconds:.1f}s")
                print(f"  Characters: {len(run.overall_characters)}")

                # Check damage and healing totals
                if run.overall_characters:
                    total_damage = sum(char.total_damage_done for char in run.overall_characters.values())
                    total_healing = sum(char.total_healing_done for char in run.overall_characters.values())

                    print(f"  Total Damage: {total_damage:,}")
                    print(f"  Total Healing: {total_healing:,}")

                    # Check activity
                    active_chars = [char for char in run.overall_characters.values()
                                   if char.activity_percentage > 0]
                    if active_chars:
                        avg_activity = sum(char.activity_percentage for char in active_chars) / len(active_chars)
                        print(f"  Avg Activity: {avg_activity:.1f}%")

                        # Sample top DPS
                        top_dps = sorted(run.overall_characters.values(),
                                       key=lambda x: x.total_damage_done, reverse=True)[:3]

                        print("\n  Top 3 DPS:")
                        for i, char in enumerate(top_dps, 1):
                            dps = char.get_combat_dps() if char.combat_time > 0 else char.get_dps(run.actual_time_seconds)
                            print(f"    {i}. {char.character_name}: {char.total_damage_done:,} damage, "
                                  f"{dps:,.0f} DPS, {char.activity_percentage:.1f}% activity")

                    # Verify our fixes worked
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

                    chars_with_combat_time = [char for char in run.overall_characters.values()
                                             if char.combat_time > 0]
                    if len(chars_with_combat_time) > 0:
                        avg_combat_time = sum(char.combat_time for char in chars_with_combat_time) / len(chars_with_combat_time)
                        print(f"✓ Combat time calculation working (avg {avg_combat_time:.1f}s)")
                    else:
                        print("✗ Combat time calculation broken")

                else:
                    print("✗ No character data found")
            else:
                print("✗ No Floodgate runs found")
        else:
            print("✗ Enhanced segmenter not working")

    except Exception as e:
        print(f"✗ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    quick_test()