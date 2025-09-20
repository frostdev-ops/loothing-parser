#!/usr/bin/env python3
"""
Debug script to examine character names and GUIDs.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

def debug_arakara_characters():
    """Debug character tracking for Ara-Kara encounter."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print(f"Debugging character names for: {log_path.name}")
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

    print(f"\nCharacter Analysis for Ara-Kara:")
    print(f"Total characters tracked: {len(arakara_encounter.characters)}")
    print("-" * 60)

    for guid, char in arakara_encounter.characters.items():
        print(f"GUID: {guid}")
        print(f"Name: {char.character_name}")
        print(f"Damage: {char.total_damage_done:,}")
        print(f"Events: {len(char.events)}")
        print()

    # Also check pet owner mappings
    print("Pet Owner Mappings:")
    print("-" * 60)
    for pet_guid, owner_info in segmenter.pet_owners.items():
        if isinstance(owner_info, tuple):
            owner_guid, owner_name = owner_info
            print(f"Pet: {pet_guid} -> Owner: {owner_guid} ({owner_name})")
        else:
            print(f"Pet: {pet_guid} -> Owner: {owner_info} (old format)")
    print()

if __name__ == "__main__":
    debug_arakara_characters()