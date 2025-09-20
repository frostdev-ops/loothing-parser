#!/usr/bin/env python3
"""
Test hierarchical M+ encounter structure.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich.panel import Panel
from rich import print as rprint

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.parser import CombatLogParser
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.models.unified_encounter import EncounterType
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

console = Console()


def display_encounter_hierarchy(encounter):
    """Display encounter hierarchy as a tree."""
    tree = Tree(f"[bold cyan]{encounter.encounter_name}[/bold cyan] +{encounter.keystone_level or 0}")

    # Add encounter info
    info_branch = tree.add("[yellow]Info[/yellow]")
    info_branch.add(f"Type: {encounter.encounter_type.value}")
    info_branch.add(f"Duration: {encounter.duration:.1f}s")
    info_branch.add(f"Success: {'✓' if encounter.success else '✗'}")
    if encounter.affixes:
        from src.config.wow_data import get_affix_name
        affix_names = [get_affix_name(affix) for affix in encounter.affixes]
        info_branch.add(f"Affixes: {', '.join(affix_names)}")

    # Add fights hierarchy
    if encounter.fights:
        fights_branch = tree.add(f"[green]Fights ({len(encounter.fights)})[/green]")

        boss_fights = [f for f in encounter.fights if f.is_boss]
        trash_fights = [f for f in encounter.fights if f.is_trash]

        # Show boss fights
        if boss_fights:
            boss_branch = fights_branch.add(f"[red]Bosses ({len(boss_fights)})[/red]")
            for fight in boss_fights:
                boss_info = f"{fight.fight_name}"
                if fight.duration > 0:
                    boss_info += f" - {fight.duration:.1f}s"
                if fight.success is not None:
                    boss_info += f" - {'✓' if fight.success else '✗'}"
                boss_branch.add(boss_info)

        # Show trash segments
        if trash_fights:
            trash_branch = fights_branch.add(f"[blue]Trash Segments ({len(trash_fights)})[/blue]")
            for fight in trash_fights:
                trash_info = f"{fight.fight_name}"
                if fight.duration > 0:
                    trash_info += f" - {fight.duration:.1f}s"
                trash_branch.add(trash_info)

    # Add character summary
    if encounter.characters:
        chars_branch = tree.add(f"[magenta]Characters ({len(encounter.characters)})[/magenta]")
        for char in list(encounter.characters.values())[:5]:  # Show first 5
            char_info = f"{char.character_name}"
            if char.spec_name:
                char_info += f" ({char.spec_name})"
            if char.dps > 0:
                char_info += f" - DPS: {char.dps:.0f}"
            chars_branch.add(char_info)
        if len(encounter.characters) > 5:
            chars_branch.add(f"... and {len(encounter.characters) - 5} more")

    return tree


def test_with_log_file(log_path):
    """Test with a specific log file."""
    console.print(f"\n[bold]Testing with: {log_path.name}[/bold]")
    console.print(f"File size: {log_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Parse the log
    parser = CombatLogParser()
    segmenter = UnifiedSegmenter()

    line_count = 0
    parse_start = datetime.now()

    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line_count += 1
            try:
                event = parser.parse_line(line.strip())
                if event:
                    segmenter.process_event(event)
            except Exception as e:
                if line_count < 10:  # Only show first few errors
                    console.print(f"[red]Parse error on line {line_count}: {e}[/red]")

    parse_time = (datetime.now() - parse_start).total_seconds()
    console.print(f"Parsed {line_count:,} lines in {parse_time:.1f}s ({line_count/parse_time:.0f} lines/sec)")

    # Get encounters
    encounters = segmenter.get_encounters()

    # Filter for M+ encounters
    mplus_encounters = [e for e in encounters if e.encounter_type == EncounterType.MYTHIC_PLUS]

    console.print(f"\n[bold]Found {len(mplus_encounters)} Mythic+ runs[/bold]")

    # Display each M+ run hierarchy
    for i, encounter in enumerate(mplus_encounters, 1):
        console.print(f"\n[bold cyan]Mythic+ Run #{i}[/bold cyan]")
        console.print(display_encounter_hierarchy(encounter))

        # Show fight breakdown
        if encounter.fights:
            table = Table(title="Fight Breakdown")
            table.add_column("Fight ID", style="cyan")
            table.add_column("Name", style="yellow")
            table.add_column("Type", style="magenta")
            table.add_column("Duration", style="green")
            table.add_column("Enemies", style="red")
            table.add_column("Success", style="blue")

            for fight in encounter.fights:
                table.add_row(
                    str(fight.fight_id),
                    fight.fight_name[:40],  # Truncate long names
                    "Boss" if fight.is_boss else ("Trash" if fight.is_trash else "Normal"),
                    f"{fight.duration:.1f}s" if fight.duration else "-",
                    str(len(fight.enemy_forces)),
                    "✓" if fight.success else ("✗" if fight.success is False else "-")
                )

            console.print(table)

    # Also show any standalone dungeon/raid encounters (should be none if working correctly)
    other_encounters = [e for e in encounters if e.encounter_type != EncounterType.MYTHIC_PLUS]
    if other_encounters:
        console.print(f"\n[yellow]WARNING: Found {len(other_encounters)} non-M+ encounters that might be dungeon bosses:[/yellow]")
        for enc in other_encounters[:5]:
            console.print(f"  - {enc.encounter_name} ({enc.encounter_type.value})")

    return mplus_encounters


def main():
    """Main test function."""
    console.print(Panel.fit("[bold]Hierarchical M+ Encounter Structure Test[/bold]", border_style="green"))

    # Find example logs
    examples_dir = Path("examples")
    if not examples_dir.exists():
        console.print("[red]Examples directory not found![/red]")
        return

    log_files = list(examples_dir.glob("WoWCombatLog*.txt"))
    if not log_files:
        console.print("[red]No combat log files found in examples/[/red]")
        return

    console.print(f"\nFound {len(log_files)} log files to test")

    # Test each file
    all_mplus = []
    for log_file in log_files:
        try:
            mplus_encounters = test_with_log_file(log_file)
            all_mplus.extend(mplus_encounters)
        except Exception as e:
            console.print(f"[red]Error processing {log_file.name}: {e}[/red]")

    # Summary
    console.print(f"\n[bold green]Summary:[/bold green]")
    console.print(f"Total M+ runs found: {len(all_mplus)}")

    if all_mplus:
        total_fights = sum(len(e.fights) for e in all_mplus)
        total_bosses = sum(len([f for f in e.fights if f.is_boss]) for e in all_mplus)
        total_trash = sum(len([f for f in e.fights if f.is_trash]) for e in all_mplus)

        console.print(f"Total fights in M+ runs: {total_fights}")
        console.print(f"  - Boss fights: {total_bosses}")
        console.print(f"  - Trash segments: {total_trash}")

        # Check structure integrity
        console.print(f"\n[bold]Structure Integrity Check:[/bold]")
        issues = []

        for enc in all_mplus:
            if not enc.fights:
                issues.append(f"M+ run '{enc.encounter_name}' has no fights")
            else:
                boss_count = len([f for f in enc.fights if f.is_boss])
                trash_count = len([f for f in enc.fights if f.is_trash])
                if boss_count == 0:
                    issues.append(f"M+ run '{enc.encounter_name}' has no boss fights marked")
                if trash_count == 0:
                    issues.append(f"M+ run '{enc.encounter_name}' has no trash segments marked")

        if issues:
            console.print("[yellow]Issues found:[/yellow]")
            for issue in issues:
                console.print(f"  - {issue}")
        else:
            console.print("[green]✓ All M+ runs have proper hierarchical structure![/green]")


if __name__ == "__main__":
    main()