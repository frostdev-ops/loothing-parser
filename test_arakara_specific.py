#!/usr/bin/env python3
"""
Test script to verify damage/healing calculations for the specific Ara-Kara encounter.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.models.unified_encounter import EncounterType
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()


def test_arakara_encounter():
    """Test damage/healing for the Ara-Kara encounter specifically."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print(f"Testing Ara-Kara encounter with: {log_path.name}")
    print("-" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()
    segmenter = UnifiedSegmenter()

    line_count = 0
    events_processed = 0

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_count += 1

            if line_count % 50000 == 0:
                print(f"Processing line {line_count}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed:
                    event = event_factory.create_event(parsed)
                    if event:
                        events_processed += 1
                        segmenter.process_event(event)

            except Exception as e:
                pass  # Ignore parse errors

    print(f"\nProcessed {line_count} lines, {events_processed} events")
    print("-" * 60)

    # Get encounters
    encounters = segmenter.get_encounters()

    # Find the Ara-Kara encounter
    arakara_encounter = None
    for encounter in encounters:
        if "Ara-Kara" in encounter.encounter_name:
            arakara_encounter = encounter
            break

    if not arakara_encounter:
        print("Ara-Kara encounter not found!")
        return

    print(f"\nFound Ara-Kara encounter:")
    print(f"  Name: {arakara_encounter.encounter_name}")
    print(f"  Duration: {arakara_encounter.duration:.1f}s")
    print(f"  Success: {arakara_encounter.success}")
    print(f"  Characters: {len(arakara_encounter.characters)}")

    # Show individual character stats
    print(f"\n{'='*80}")
    print(f"INDIVIDUAL CHARACTER STATS - ARA-KARA ENCOUNTER")
    print(f"{'='*80}")

    # Sort characters by damage done
    sorted_chars = sorted(
        arakara_encounter.characters.values(),
        key=lambda c: c.total_damage_done,
        reverse=True
    )

    print(f"\nDAMAGE DONE:")
    print(f"{'Rank':<4} {'Player':<15} {'Total Damage':<15} {'DPS':<12}")
    print("-" * 50)

    for i, char in enumerate(sorted_chars, 1):
        dps = char.total_damage_done / arakara_encounter.duration if arakara_encounter.duration > 0 else 0
        print(f"{i:<4} {char.character_name:<15} {char.total_damage_done:<15,} {dps:<12,.0f}")

    # Sort by healing done
    healing_chars = sorted(
        arakara_encounter.characters.values(),
        key=lambda c: c.total_healing_done,
        reverse=True
    )

    print(f"\nHEALING DONE:")
    print(f"{'Rank':<4} {'Player':<15} {'Total Healing':<15} {'HPS':<12}")
    print("-" * 50)

    for i, char in enumerate(healing_chars, 1):
        if char.total_healing_done > 0:
            hps = char.total_healing_done / arakara_encounter.duration if arakara_encounter.duration > 0 else 0
            print(f"{i:<4} {char.character_name:<15} {char.total_healing_done:<15,} {hps:<12,.0f}")

    print(f"\n{'='*80}")
    print(f"COMPARISON TO GAME SCREENSHOT:")
    print(f"Game showed: Nootlay 12.25B, Felica 11.15B, Nyloz 10.83B, Ivanovich 6.55B, Nootloops 1.08B")
    print(f"{'='*80}")


if __name__ == "__main__":
    test_arakara_encounter()