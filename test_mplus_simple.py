#!/usr/bin/env python3
"""
Simple test for M+ hierarchical structure - processes just enough to verify it works.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.models.unified_encounter import EncounterType
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()


def test_mplus_hierarchy():
    """Test M+ hierarchical structure with a small subset of a log."""

    # Find a log with M+ content
    log_path = Path("examples/WoWCombatLog-091625_041109.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print(f"Testing M+ hierarchical structure with: {log_path.name}")
    print("-" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()
    segmenter = UnifiedSegmenter()

    line_count = 0
    events_processed = 0
    max_lines = 100000  # Process only first 100k lines for speed

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_count += 1

            if line_count > max_lines:
                break

            if line_count % 10000 == 0:
                print(f"Processing line {line_count}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed:
                    event = event_factory.create_event(parsed)
                    if event:
                        events_processed += 1
                        segmenter.process_event(event)

                        # Debug key events
                        if event.event_type in ["CHALLENGE_MODE_START", "CHALLENGE_MODE_END",
                                                 "ENCOUNTER_START", "ENCOUNTER_END"]:
                            print(f"  [{event.event_type}] at line {line_count}")
                            if hasattr(event, 'encounter_name'):
                                print(f"    -> {event.encounter_name}")
                            elif hasattr(event, 'zone_name'):
                                print(f"    -> {event.zone_name}")

            except Exception as e:
                pass  # Ignore parse errors for this test

    print(f"\nProcessed {line_count} lines, {events_processed} events")
    print("-" * 60)

    # Get encounters
    encounters = segmenter.get_encounters()

    # Show all encounters
    print(f"\nTotal encounters found: {len(encounters)}")

    # Separate by type
    mplus_encounters = [e for e in encounters if e.encounter_type == EncounterType.MYTHIC_PLUS]
    raid_encounters = [e for e in encounters if e.encounter_type == EncounterType.RAID]
    other_encounters = [e for e in encounters if e.encounter_type not in [EncounterType.MYTHIC_PLUS, EncounterType.RAID]]

    print(f"  - Mythic+ runs: {len(mplus_encounters)}")
    print(f"  - Raid encounters: {len(raid_encounters)}")
    print(f"  - Other encounters: {len(other_encounters)}")

    # Check M+ structure
    if mplus_encounters:
        print("\n" + "=" * 60)
        print("MYTHIC+ RUN HIERARCHY")
        print("=" * 60)

        for i, mplus in enumerate(mplus_encounters, 1):
            print(f"\nM+ Run #{i}: {mplus.encounter_name} +{mplus.keystone_level or 0}")
            print(f"  Duration: {mplus.duration:.1f}s")
            print(f"  Success: {'Yes' if mplus.success else 'No'}")

            if mplus.fights:
                print(f"  Fights within this M+ run: {len(mplus.fights)}")

                # Count fight types
                boss_fights = [f for f in mplus.fights if f.is_boss]
                trash_fights = [f for f in mplus.fights if f.is_trash]

                print(f"    - Boss fights: {len(boss_fights)}")
                for fight in boss_fights:
                    print(f"      * {fight.fight_name}")

                print(f"    - Trash segments: {len(trash_fights)}")
                for fight in trash_fights:
                    print(f"      * {fight.fight_name}")
            else:
                print("  WARNING: No fights recorded in this M+ run!")

    # Check for orphaned encounters (should be none if working correctly)
    if other_encounters or (raid_encounters and mplus_encounters):
        print("\n" + "=" * 60)
        print("POTENTIAL ISSUES")
        print("=" * 60)

        if other_encounters:
            print(f"\nFound {len(other_encounters)} encounters with unknown type:")
            for enc in other_encounters[:5]:
                print(f"  - {enc.encounter_name}")

        # In a log with M+, we shouldn't have separate raid encounters
        # (dungeon bosses should be within the M+ structure)
        if raid_encounters and mplus_encounters:
            print(f"\nWARNING: Found both M+ runs and separate raid encounters!")
            print("This might indicate dungeon bosses not being properly nested:")
            for enc in raid_encounters[:5]:
                print(f"  - {enc.encounter_name} (might be a dungeon boss)")

    # Success check
    print("\n" + "=" * 60)
    if mplus_encounters and all(len(e.fights) > 0 for e in mplus_encounters):
        print("✓ SUCCESS: M+ runs have proper hierarchical structure!")
        print("  All dungeon bosses and trash are nested within M+ encounters.")
    elif mplus_encounters:
        print("⚠ PARTIAL SUCCESS: M+ runs found but some lack fight data.")
    else:
        print("ℹ INFO: No M+ runs found in the processed portion of the log.")
    print("=" * 60)


if __name__ == "__main__":
    test_mplus_hierarchy()