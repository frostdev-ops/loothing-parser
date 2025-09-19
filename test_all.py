#!/usr/bin/env python3
"""
Comprehensive test of the parser on all example files.
"""

import sys
from pathlib import Path
import time
from collections import Counter

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from parser.parser import CombatLogParser
from segmentation.encounters import EncounterSegmenter, FightType
from segmentation.aggregator import EventAggregator
from rich.console import Console
from rich.table import Table

console = Console()


def test_all_files():
    """Test parser on all example files."""
    examples_dir = Path('examples')
    log_files = sorted(examples_dir.glob('*.txt'), key=lambda f: f.stat().st_size)

    console.print("[bold cyan]═══ WoW Combat Log Parser - Full Test Suite ═══[/bold cyan]\n")
    console.print(f"Found {len(log_files)} test files\n")

    results = []
    total_events = 0
    total_fights = 0
    total_time = 0
    all_event_types = Counter()

    for log_file in log_files:
        file_size = log_file.stat().st_size / 1024 / 1024  # MB
        console.print(f"[yellow]Testing:[/yellow] {log_file.name} ({file_size:.1f} MB)")

        parser = CombatLogParser()
        segmenter = EncounterSegmenter()
        aggregator = EventAggregator()

        start_time = time.time()
        event_count = 0
        event_types = Counter()
        sample_encounters = []

        # Parse file
        try:
            for event in parser.parse_file(str(log_file)):
                event_count += 1
                event_types[event.event_type] += 1
                all_event_types[event.event_type] += 1

                # Process through segmenter
                completed_fight = segmenter.process_event(event)
                if completed_fight and len(sample_encounters) < 3:
                    sample_encounters.append(completed_fight)

                # Add to aggregator for the current fight
                if segmenter.current_fight:
                    aggregator._process_event(event)

                # Limit events for very large files
                if event_count >= 100000:
                    console.print("  (Limited to 100k events)")
                    break

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            continue

        # Finalize fights
        fights = segmenter.finalize()
        elapsed = time.time() - start_time

        # Collect results
        result = {
            'file': log_file.name,
            'size_mb': file_size,
            'events': event_count,
            'fights': len(fights),
            'errors': len(parser.parse_errors),
            'time': elapsed,
            'events_per_sec': event_count / elapsed if elapsed > 0 else 0,
            'top_events': event_types.most_common(3),
            'sample_encounters': sample_encounters
        }
        results.append(result)

        total_events += event_count
        total_fights += len(fights)
        total_time += elapsed

        # Show quick summary
        console.print(f"  ✓ Events: {event_count:,} | Fights: {len(fights)} | "
                     f"Time: {elapsed:.1f}s | Speed: {result['events_per_sec']:.0f} ev/s")

        # Show sample encounters
        if sample_encounters:
            for enc in sample_encounters[:2]:
                name = enc.encounter_name or "Trash"
                result_str = "Kill" if enc.success else "Wipe" if enc.success is False else "?"
                console.print(f"    • {name} ({result_str})")

        console.print()

    # Display summary table
    console.print("[bold cyan]═══ Test Results Summary ═══[/bold cyan]\n")

    # File results table
    table = Table(title="File Processing Results")
    table.add_column("File", width=30)
    table.add_column("Size (MB)", justify="right", width=10)
    table.add_column("Events", justify="right", width=10)
    table.add_column("Fights", justify="right", width=8)
    table.add_column("Errors", justify="right", width=8)
    table.add_column("Time (s)", justify="right", width=8)
    table.add_column("Ev/s", justify="right", width=10)

    for result in results:
        table.add_row(
            result['file'][:30],
            f"{result['size_mb']:.1f}",
            f"{result['events']:,}",
            str(result['fights']),
            str(result['errors']),
            f"{result['time']:.1f}",
            f"{result['events_per_sec']:.0f}"
        )

    console.print(table)

    # Overall statistics
    console.print(f"\n[bold]Overall Statistics:[/bold]")
    console.print(f"  • Total Events Processed: {total_events:,}")
    console.print(f"  • Total Fights Found: {total_fights}")
    console.print(f"  • Total Processing Time: {total_time:.1f}s")
    console.print(f"  • Average Speed: {total_events/total_time:.0f} events/second")

    # Top event types across all files
    console.print(f"\n[bold]Top Event Types (All Files):[/bold]")
    for event_type, count in all_event_types.most_common(10):
        percentage = (count / total_events) * 100
        console.print(f"  • {event_type}: {count:,} ({percentage:.1f}%)")

    # Check for LOOT events
    loot_events = [evt for evt in all_event_types if 'LOOT' in evt]
    if loot_events:
        console.print(f"\n[bold green]Found LOOT events![/bold green]")
        for evt in loot_events:
            console.print(f"  • {evt}: {all_event_types[evt]}")
    else:
        console.print("\n[bold yellow]Note: No LOOT events found in any log files[/bold yellow]")
        console.print("  Loot tracking will need to be implemented via:")
        console.print("  • WoW API integration for item data")
        console.print("  • Addon data export")
        console.print("  • Manual loot entry")

    # Performance analysis
    console.print(f"\n[bold]Performance Analysis:[/bold]")
    if results:
        fastest = max(results, key=lambda r: r['events_per_sec'])
        slowest = min(results, key=lambda r: r['events_per_sec'])
        console.print(f"  • Fastest: {fastest['file']} @ {fastest['events_per_sec']:.0f} ev/s")
        console.print(f"  • Slowest: {slowest['file']} @ {slowest['events_per_sec']:.0f} ev/s")

        largest = max(results, key=lambda r: r['size_mb'])
        console.print(f"  • Largest file: {largest['file']} ({largest['size_mb']:.1f} MB)")
        console.print(f"    Processed in {largest['time']:.1f}s @ {largest['events_per_sec']:.0f} ev/s")


if __name__ == '__main__':
    test_all_files()