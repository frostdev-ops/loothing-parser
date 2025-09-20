#!/usr/bin/env python3
"""
Test script for the new unified data structure with enhanced tracking.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parser.parser import CombatLogParser
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.analyzer.death_analyzer import DeathAnalyzer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich import box

console = Console()


def test_unified_structure():
    """Test the new unified data structure."""

    # Find test files
    examples_dir = Path("examples")
    log_files = sorted(examples_dir.glob("*.txt"), key=lambda f: f.stat().st_size)

    if not log_files:
        console.print("[red]No example files found![/red]")
        return

    # Use a medium-sized file for testing
    log_file = log_files[2] if len(log_files) > 2 else log_files[0]

    console.print("[bold cyan]═══ Unified Data Structure Test ═══[/bold cyan]\n")
    console.print(
        f"📁 Testing with: {log_file.name} ({log_file.stat().st_size / 1024 / 1024:.1f} MB)\n"
    )

    # Create parser and unified segmenter
    parser = CombatLogParser()
    segmenter = UnifiedSegmenter()

    event_count = 0
    start_time = datetime.now()

    # Process events
    with console.status("[yellow]Processing combat log...[/yellow]") as status:
        for event in parser.parse_file(str(log_file)):
            segmenter.process_event(event)
            event_count += 1

            if event_count % 10000 == 0:
                status.update(f"[yellow]Processing events... ({event_count:,})[/yellow]")

            # Limit for testing
            if event_count >= 100000:
                console.print("  [dim](Limited to 100k events for testing)[/dim]")
                break

    # Get encounters
    encounters = segmenter.get_encounters()
    processing_time = (datetime.now() - start_time).total_seconds()

    # Display summary
    console.print(f"\n[bold green]✓ Processing Complete![/bold green]")
    stats = segmenter.get_stats()

    summary_table = Table(box=box.ROUNDED)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", justify="right", style="yellow")

    summary_table.add_row("Events Processed", f"{event_count:,}")
    summary_table.add_row("Processing Time", f"{processing_time:.1f}s")
    summary_table.add_row("Events/Second", f"{event_count / processing_time:,.0f}")
    summary_table.add_row("Total Encounters", str(stats["total_encounters"]))
    summary_table.add_row("Raid Encounters", str(stats["raid_encounters"]))
    summary_table.add_row("Mythic+ Runs", str(stats["mythic_plus_runs"]))
    summary_table.add_row("Total Characters", str(stats["total_characters"]))
    summary_table.add_row("Total Fights", str(stats["total_fights"]))

    console.print(summary_table)

    # Display encounters
    for encounter in encounters[:2]:  # Show first 2 encounters
        display_encounter(encounter)

    # Export sample data
    if encounters:
        export_encounter_data(encounters[0])


def display_encounter(encounter):
    """Display detailed encounter information."""
    console.print(f"\n[bold magenta]═══ {encounter.encounter_name} ═══[/bold magenta]")

    # Basic info
    info_table = Table(box=box.SIMPLE)
    info_table.add_column("Property", style="dim")
    info_table.add_column("Value")

    info_table.add_row("Type", encounter.encounter_type.value)
    info_table.add_row("Difficulty", encounter.difficulty or "N/A")
    if encounter.keystone_level:
        info_table.add_row("Keystone Level", f"+{encounter.keystone_level}")
    info_table.add_row("Duration", f"{encounter.duration:.1f}s")
    info_table.add_row("Combat Duration", f"{encounter.combat_duration:.1f}s")
    info_table.add_row("Success", "✓" if encounter.success else "✗")
    info_table.add_row("Players", str(encounter.metrics.player_count))

    console.print(info_table)

    # Composition
    console.print(f"\n[yellow]Composition:[/yellow]")
    console.print(f"  Tanks: {encounter.metrics.tanks_count}")
    console.print(f"  Healers: {encounter.metrics.healers_count}")
    console.print(f"  DPS: {encounter.metrics.dps_count}")

    # Metrics
    console.print(f"\n[yellow]Performance:[/yellow]")
    console.print(f"  Raid DPS: {encounter.metrics.raid_dps:,.0f}")
    console.print(f"  Combat DPS: {encounter.metrics.combat_raid_dps:,.0f}")
    console.print(f"  Raid HPS: {encounter.metrics.raid_hps:,.0f}")
    console.print(f"  Deaths: {encounter.metrics.total_deaths}")
    console.print(f"  Avg Activity: {encounter.metrics.avg_activity:.1f}%")
    console.print(
        f"  Avg iLvl: {encounter.metrics.avg_item_level:.1f}"
        if encounter.metrics.avg_item_level
        else "  Avg iLvl: Unknown"
    )

    # Character details
    display_character_breakdown(encounter)

    # Fight breakdown
    if encounter.fights:
        display_fight_breakdown(encounter.fights[0])


def display_character_breakdown(encounter):
    """Display character performance breakdown."""
    console.print(f"\n[cyan]Character Performance:[/cyan]")

    # Create performance table
    perf_table = Table(box=box.SIMPLE)
    perf_table.add_column("Character", style="green")
    perf_table.add_column("Role", style="dim")
    perf_table.add_column("iLvl", justify="center")
    perf_table.add_column("DPS", justify="right", style="red")
    perf_table.add_column("HPS", justify="right", style="blue")
    perf_table.add_column("Deaths", justify="center")
    perf_table.add_column("Activity", justify="right")

    # Sort by DPS
    sorted_chars = sorted(
        encounter.characters.values(), key=lambda c: c.total_damage_done, reverse=True
    )

    for char in sorted_chars[:10]:  # Top 10
        dps = char.total_damage_done / encounter.duration if encounter.duration > 0 else 0
        hps = char.total_healing_done / encounter.duration if encounter.duration > 0 else 0

        perf_table.add_row(
            char.character_name[:20],
            char.role or "?",
            f"{char.item_level:.0f}" if char.item_level else "-",
            f"{dps:,.0f}",
            f"{hps:,.0f}" if hps > 100 else "-",
            str(char.death_count) if char.death_count > 0 else "-",
            f"{char.activity_percentage:.0f}%",
        )

    console.print(perf_table)

    # Display top damage dealer's abilities
    if sorted_chars:
        top_dps = sorted_chars[0]
        display_ability_breakdown(top_dps)

    # Display death analysis
    deaths_to_show = [char for char in sorted_chars if char.death_count > 0]
    if deaths_to_show:
        display_death_analysis(deaths_to_show[0])


def display_ability_breakdown(character):
    """Display ability breakdown for a character."""
    console.print(f"\n[yellow]Top Abilities - {character.character_name}:[/yellow]")

    ability_table = Table(box=box.SIMPLE)
    ability_table.add_column("Ability", style="cyan")
    ability_table.add_column("Damage", justify="right")
    ability_table.add_column("%", justify="right", style="green")
    ability_table.add_column("Hits", justify="right")
    ability_table.add_column("Avg", justify="right")
    ability_table.add_column("Crit%", justify="right", style="yellow")

    for ability in character.get_top_abilities("damage", 5):
        ability_table.add_row(
            ability.spell_name[:30],
            f"{ability.total_damage:,}",
            f"{ability.percentage_of_total:.1f}%",
            str(ability.hit_count),
            f"{ability.average_hit:,.0f}",
            f"{ability.crit_rate:.0f}%",
        )

    console.print(ability_table)


def display_death_analysis(character):
    """Display death analysis for a character."""
    if not character.enhanced_deaths:
        return

    console.print(f"\n[red]Death Analysis - {character.character_name}:[/red]")

    death = character.enhanced_deaths[0]  # Show first death

    # Recent damage
    console.print("  [dim]Recent damage taken:[/dim]")
    for source, amount in list(death.damage_sources.items())[:5]:
        console.print(f"    • {source}: {amount:,}")

    # Healing attempted
    total_healing = sum(death.healing_sources.values())
    if total_healing > 0:
        console.print(f"  [dim]Healing attempted:[/dim] {total_healing:,}")


def display_fight_breakdown(fight):
    """Display fight breakdown (players vs NPCs)."""
    console.print(f"\n[magenta]Fight Analysis:[/magenta]")

    # Player summary
    console.print(f"  [green]Players:[/green] {len(fight.players)}")
    total_player_damage = sum(p.total_damage_done for p in fight.players.values())
    console.print(f"    Total damage: {total_player_damage:,}")

    # Enemy forces summary
    console.print(f"  [red]Enemy Forces:[/red] {len(fight.enemy_forces)}")

    # Top enemies by damage done
    top_enemies = sorted(fight.enemy_forces.values(), key=lambda e: e.damage_done, reverse=True)[:5]

    if top_enemies:
        console.print("    Top threats:")
        for enemy in top_enemies:
            console.print(f"      • {enemy.name}: {enemy.damage_done:,} damage")


def export_encounter_data(encounter):
    """Export encounter data to JSON."""
    output_file = Path("encounter_data_sample.json")

    # Convert to dict
    data = encounter.to_dict()

    # Write to file
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, default=str)

    console.print(f"\n[green]✓ Sample data exported to {output_file}[/green]")


if __name__ == "__main__":
    test_unified_structure()
