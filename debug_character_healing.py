#!/usr/bin/env python3
"""
Debug healing totals in character streams.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parser.parser import CombatLogParser
from src.segmentation.enhanced import EnhancedSegmenter

def debug_character_healing():
    """Debug character healing totals."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Debugging character healing totals on: {log_file}")
    print("=" * 60)

    parser = CombatLogParser()
    enhanced_segmenter = EnhancedSegmenter()

    total_events = 0

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    parsed_line = parser.tokenizer.parse_line(line)
                    event = parser.event_factory.create_event(parsed_line)
                    enhanced_segmenter.process_event(event)
                    total_events += 1

                    # Progress indicator
                    if total_events % 200000 == 0:
                        print(f"  Processed {total_events:,} events...")

                except Exception:
                    continue

    print(f"Parsed {total_events:,} events")

    # Finalize data
    print("Finalizing encounters...")
    raid_encounters, mythic_plus_runs = enhanced_segmenter.finalize()

    print(f"Found {len(mythic_plus_runs)} M+ runs")

    # Find Operation: Floodgate runs
    floodgate_runs = [run for run in mythic_plus_runs if "Floodgate" in run.dungeon_name]

    if floodgate_runs:
        run = floodgate_runs[-1]
        print(f"\nAnalyzing run: {run.dungeon_name} +{run.keystone_level}")

        healers = []
        for char in run.overall_characters.values():
            if char.total_healing_done > 1000000:  # More than 1M healing
                healers.append(char)

        print(f"\nFound {len(healers)} potential healers:")
        for char in healers:
            print(f"  {char.character_name}: {char.total_healing_done:,} healing")

        # Look at a specific character in detail
        if healers:
            healer = healers[0]
            print(f"\nDetailed analysis of {healer.character_name}:")
            print(f"  Total healing done: {healer.total_healing_done:,}")
            print(f"  Total overhealing: {healer.total_overhealing:,}")
            print(f"  Raw healing: {healer.total_healing_done + healer.total_overhealing:,}")

            # Count heal events
            heal_events = [event for event in healer.all_events
                          if hasattr(event.event, 'event_type') and
                          ('HEAL' in event.event.event_type and
                           event.event.event_type != 'SPELL_HEAL_ABSORBED')]

            print(f"  Number of heal events: {len(heal_events)}")

            if heal_events:
                # Sample first few heal events
                print(f"\nFirst 5 heal events:")
                for i, ts_event in enumerate(heal_events[:5]):
                    event = ts_event.event
                    effective = event.amount - event.overhealing if hasattr(event, 'amount') else 0
                    print(f"    {i+1}. {event.event_type}: amount={getattr(event, 'amount', 0)}, "
                          f"overheal={getattr(event, 'overhealing', 0)}, effective={effective}")

        # Summary of all characters
        total_healing = sum(char.total_healing_done for char in run.overall_characters.values())
        total_overhealing = sum(char.total_overhealing for char in run.overall_characters.values())

        print(f"\nOverall totals:")
        print(f"  Total healing done: {total_healing:,}")
        print(f"  Total overhealing: {total_overhealing:,}")
        print(f"  Raw healing: {total_healing + total_overhealing:,}")

        # Check if any characters have negative healing
        negative_healers = [char for char in run.overall_characters.values() if char.total_healing_done < 0]
        if negative_healers:
            print(f"\nCharacters with NEGATIVE healing:")
            for char in negative_healers:
                print(f"  {char.character_name}: {char.total_healing_done:,}")

if __name__ == "__main__":
    debug_character_healing()