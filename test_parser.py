#!/usr/bin/env python3
"""
Quick test script for the WoW combat log parser.
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from parser.parser import CombatLogParser
from segmentation.encounters import EncounterSegmenter
from rich.console import Console

console = Console()


def test_parser():
    """Test the parser on a small sample of a log file."""

    # Find an example file
    examples_dir = Path('examples')
    log_files = list(examples_dir.glob('*.txt'))

    if not log_files:
        console.print("[red]No example files found![/red]")
        return

    # Use the smallest file for quick testing
    log_file = min(log_files, key=lambda f: f.stat().st_size)

    console.print(f"[bold cyan]Testing parser with:[/bold cyan] {log_file.name}")
    console.print(f"File size: {log_file.stat().st_size / 1024 / 1024:.1f} MB\n")

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    event_count = 0
    encounter_count = 0
    sample_events = []

    # Process events
    console.print("[yellow]Processing events...[/yellow]")
    for event in parser.parse_file(str(log_file)):
        event_count += 1

        # Keep first 10 events as samples
        if len(sample_events) < 10:
            sample_events.append(event)

        # Segment encounters
        completed_fight = segmenter.process_event(event)
        if completed_fight:
            encounter_count += 1
            console.print(f"  Found encounter: {completed_fight.encounter_name or 'Unknown'}")

        # Stop after 10000 events for quick test
        if event_count >= 10000:
            console.print("  (Stopping after 10,000 events for quick test)")
            break

    # Finalize any remaining encounters
    fights = segmenter.finalize()

    # Display results
    console.print(f"\n[bold green]✓ Parser Test Successful![/bold green]")
    console.print(f"  • Events processed: {event_count:,}")
    console.print(f"  • Parse errors: {len(parser.parse_errors)}")
    console.print(f"  • Fights found: {len(fights)}")

    # Show sample events
    if sample_events:
        console.print(f"\n[bold]Sample Events:[/bold]")
        for event in sample_events[:5]:
            console.print(f"  {event.timestamp.strftime('%H:%M:%S')} - {event.event_type}")
            if hasattr(event, 'source_name') and event.source_name:
                console.print(f"    Source: {event.source_name}")

    # Show parser stats
    stats = parser.get_stats()
    console.print(f"\n[bold]Parser Statistics:[/bold]")
    console.print(f"  • Lines processed: {stats['tokenizer_stats']['lines_processed']}")
    console.print(f"  • Success rate: {stats['tokenizer_stats']['success_rate']:.1%}")

    # Show encounters
    if fights:
        console.print(f"\n[bold]Encounters Found:[/bold]")
        for fight in fights[:5]:
            console.print(f"  • {fight.encounter_name or 'Trash'} - {fight.get_duration_str()}")


if __name__ == '__main__':
    test_parser()