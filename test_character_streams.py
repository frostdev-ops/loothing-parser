#!/usr/bin/env python3
"""
Test script for per-character event streaming with enhanced segmentation.
"""

import sys
from pathlib import Path
import json
from datetime import datetime

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from parser.parser import CombatLogParser
from segmentation.enhanced import EnhancedSegmenter
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()


def test_character_streams():
    """Test the enhanced segmentation with character event streams."""

    # Find a test file
    examples_dir = Path('examples')
    log_files = sorted(examples_dir.glob('*.txt'), key=lambda f: f.stat().st_size)

    if not log_files:
        console.print("[red]No example files found![/red]")
        return

    # Use a medium-sized file for testing
    log_file = log_files[2] if len(log_files) > 2 else log_files[0]

    console.print("[bold cyan]═══ Character Event Stream Test ═══[/bold cyan]\n")
    console.print(f"Testing with: {log_file.name} ({log_file.stat().st_size / 1024 / 1024:.1f} MB)\n")

    # Create parser and enhanced segmenter
    parser = CombatLogParser()
    segmenter = EnhancedSegmenter()

    event_count = 0
    start_time = datetime.now()

    # Process events
    console.print("[yellow]Processing events...[/yellow]")
    for event in parser.parse_file(str(log_file)):
        segmenter.process_event(event)
        event_count += 1

        # Limit for testing
        if event_count >= 50000:
            console.print("  (Limited to 50k events for testing)")
            break

    # Finalize and get results
    raid_encounters, mythic_plus_runs = segmenter.finalize()
    processing_time = (datetime.now() - start_time).total_seconds()

    # Display results
    console.print(f"\n[bold green]✓ Processing Complete![/bold green]")
    console.print(f"  • Events processed: {event_count:,}")
    console.print(f"  • Processing time: {processing_time:.1f}s")
    console.print(f"  • Speed: {event_count / processing_time:.0f} events/second")

    # Get statistics
    stats = segmenter.get_stats()
    console.print(f"  • Total characters tracked: {stats['total_characters']}")
    console.print(f"  • Raid encounters: {stats['raid_encounters']}")
    console.print(f"  • Mythic+ runs: {stats['mythic_plus_runs']}")

    # Display raid encounters with character details
    if raid_encounters:
        console.print(f"\n[bold cyan]═══ Raid Encounters ═══[/bold cyan]\n")

        for encounter in raid_encounters[:2]:  # Show first 2 encounters
            display_raid_encounter(encounter)

    # Display Mythic+ runs with character details
    if mythic_plus_runs:
        console.print(f"\n[bold cyan]═══ Mythic+ Runs ═══[/bold cyan]\n")

        for run in mythic_plus_runs[:1]:  # Show first run
            display_mythic_plus_run(run)

    # Export sample data
    export_sample_data(raid_encounters, mythic_plus_runs)


def display_raid_encounter(encounter):
    """Display detailed information about a raid encounter."""

    # Create encounter tree
    tree = Tree(f"[bold red]{encounter.boss_name}[/bold red] - {encounter.difficulty.name} (Pull #{encounter.pull_number})")

    # Add metadata
    meta = tree.add("[yellow]Metadata[/yellow]")
    meta.add(f"Duration: {encounter.combat_length:.1f}s")
    meta.add(f"Result: {'Kill' if encounter.success else 'Wipe'}")
    meta.add(f"Raid Size: {encounter.raid_size}")

    # Add character performance
    chars = tree.add(f"[cyan]Characters ({len(encounter.characters)})[/cyan]")

    # Sort characters by damage done
    sorted_chars = sorted(
        encounter.characters.values(),
        key=lambda c: c.total_damage_done,
        reverse=True
    )

    for char in sorted_chars[:5]:  # Top 5 DPS
        char_branch = chars.add(f"[green]{char.character_name}[/green]")
        char_branch.add(f"Damage: {char.total_damage_done:,}")
        char_branch.add(f"DPS: {char.get_dps(encounter.combat_length):.0f}")
        char_branch.add(f"Events: {len(char.all_events)}")
        char_branch.add(f"Deaths: {char.death_count}")
        char_branch.add(f"Activity: {char.activity_percentage:.1f}%")

    console.print(tree)

    # Show character event breakdown table
    if encounter.characters:
        table = Table(title=f"Event Breakdown - {encounter.boss_name}")
        table.add_column("Character", style="cyan")
        table.add_column("Damage Done", justify="right")
        table.add_column("Healing Done", justify="right")
        table.add_column("Damage Taken", justify="right")
        table.add_column("Casts", justify="right")
        table.add_column("Buffs", justify="right")
        table.add_column("Debuffs", justify="right")

        for char in sorted_chars[:8]:
            table.add_row(
                char.character_name[:15],
                f"{len(char.damage_done):,}",
                f"{len(char.healing_done):,}",
                f"{len(char.damage_taken):,}",
                f"{len(char.casts_succeeded):,}",
                f"{len(char.buffs_gained):,}",
                f"{len(char.debuffs_gained):,}"
            )

        console.print(table)


def display_mythic_plus_run(run):
    """Display detailed information about a Mythic+ run."""

    # Create run tree
    tree = Tree(f"[bold magenta]{run.dungeon_name} +{run.keystone_level}[/bold magenta]")

    # Add metadata
    meta = tree.add("[yellow]Run Info[/yellow]")
    meta.add(f"Duration: {run.actual_time_seconds:.1f}s")
    meta.add(f"Time Limit: {run.time_limit_seconds}s")
    meta.add(f"Result: {'In Time' if run.in_time else 'Over Time'}")
    meta.add(f"Deaths: {run.num_deaths}")

    # Add segments
    segments = tree.add(f"[cyan]Segments ({len(run.segments)})[/cyan]")

    for segment in run.segments[:5]:  # First 5 segments
        seg_branch = segments.add(
            f"{segment.segment_name} ({segment.segment_type.value})"
        )
        seg_branch.add(f"Duration: {segment.duration:.1f}s")
        seg_branch.add(f"Mob Count: {segment.mob_count}")
        seg_branch.add(f"Characters: {len(segment.characters)}")

    # Add overall character performance
    if run.overall_characters:
        chars = tree.add(f"[green]Overall Performance[/green]")

        sorted_chars = sorted(
            run.overall_characters.values(),
            key=lambda c: c.total_damage_done,
            reverse=True
        )

        for char in sorted_chars[:5]:
            char_branch = chars.add(char.character_name)
            char_branch.add(f"Total Damage: {char.total_damage_done:,}")
            char_branch.add(f"Overall DPS: {char.get_dps(run.actual_time_seconds):.0f}")
            char_branch.add(f"Deaths: {char.death_count}")

    console.print(tree)


def export_sample_data(raid_encounters, mythic_plus_runs):
    """Export sample data to JSON for inspection."""

    output = {
        'export_time': datetime.now().isoformat(),
        'raid_encounters': [],
        'mythic_plus_runs': []
    }

    # Export first raid encounter
    if raid_encounters:
        encounter = raid_encounters[0]
        output['raid_encounters'].append(encounter.to_dict())

    # Export first M+ run
    if mythic_plus_runs:
        run = mythic_plus_runs[0]
        output['mythic_plus_runs'].append(run.to_dict())

    # Save to file
    output_file = 'character_streams_sample.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    console.print(f"\n[green]Sample data exported to {output_file}[/green]")

    # Show sample of character event stream
    if raid_encounters and raid_encounters[0].characters:
        first_char = list(raid_encounters[0].characters.values())[0]
        console.print(f"\n[bold]Sample Character Event Stream: {first_char.character_name}[/bold]")
        console.print(f"  • Total events: {len(first_char.all_events)}")
        console.print(f"  • Damage done events: {len(first_char.damage_done)}")
        console.print(f"  • Healing done events: {len(first_char.healing_done)}")
        console.print(f"  • Buffs gained: {len(first_char.buffs_gained)}")
        console.print(f"  • Debuffs gained: {len(first_char.debuffs_gained)}")

        if first_char.all_events:
            console.print(f"\n  First 5 events:")
            for event in first_char.all_events[:5]:
                console.print(f"    • {event.datetime.strftime('%H:%M:%S.%f')[:-3]} - {event.category}")


if __name__ == '__main__':
    test_character_streams()