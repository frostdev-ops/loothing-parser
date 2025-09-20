#!/usr/bin/env python3
"""
Command-line interface for the WoW combat log parser.
"""

import sys
import click
import logging
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.logging import RichHandler
from collections import Counter

from .parser.parser import CombatLogParser
from .parser.tokenizer import LineTokenizer
from .parser.events import EventFactory
from .segmentation.encounters import EncounterSegmenter, FightType
from .segmentation.unified_segmenter import UnifiedSegmenter
from .models.unified_encounter import UnifiedEncounter, EncounterType
from .processing.unified_parallel_processor import UnifiedParallelProcessor
from .config.loader import load_and_apply_config


# Set up rich console for pretty output
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)

# Load custom configuration if available
load_and_apply_config()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def cli(verbose):
    """WoW Combat Log Parser - Loothing Guild Tracking System"""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.command()
@click.argument("log_file", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output file for results")
@click.option("--format", type=click.Choice(["json", "csv", "summary"]), default="summary")
@click.option(
    "--threads",
    default=None,
    type=int,
    help="Number of threads for parallel processing (default: CPU count)",
)
@click.option(
    "--no-parallel",
    is_flag=True,
    help="Disable parallel processing (force sequential)",
)
def parse(log_file, output, format, threads, no_parallel):
    """Parse a combat log file and extract encounters using unified segmentation."""
    log_path = Path(log_file)
    console.print(f"[bold green]Parsing combat log:[/bold green] {log_path.name}")
    console.print(f"[cyan]File size:[/cyan] {log_path.stat().st_size / 1024 / 1024:.1f} MB")

    start_time = datetime.now()
    encounters = []
    parse_errors = []
    total_events = 0

    if no_parallel:
        # Sequential processing
        console.print("[yellow]Using sequential processing (--no-parallel)[/yellow]")

        tokenizer = LineTokenizer()
        event_factory = EventFactory()
        segmenter = UnifiedSegmenter()

        # Parse with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            file_size = log_path.stat().st_size
            task = progress.add_task(f"[cyan]Processing...", total=file_size)

            with open(log_path, "rb") as f:
                bytes_read = 0
                for line in f:
                    bytes_read += len(line)
                    if bytes_read % 10000 == 0:  # Update progress periodically
                        progress.update(task, completed=bytes_read)

                    try:
                        line_str = line.decode("utf-8", errors="ignore").strip()
                        if line_str and not line_str.startswith("#"):
                            parsed = tokenizer.parse_line(line_str)
                            if parsed:
                                event = event_factory.create_event(parsed)
                                if event:
                                    segmenter.process_event(event)
                                    total_events += 1
                    except Exception as e:
                        if len(parse_errors) < 100:
                            parse_errors.append(str(e))

                progress.update(task, completed=file_size)

        # Get encounters
        encounters = segmenter.get_encounters()

        # Calculate metrics
        console.print("[cyan]Calculating encounter metrics...[/cyan]")
        for encounter in encounters:
            encounter.calculate_metrics()

    else:
        # Parallel processing
        processor = UnifiedParallelProcessor(max_workers=threads)
        console.print(f"[cyan]Using parallel processing ({processor.max_workers} threads)[/cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Detecting encounter boundaries...", total=None)

            try:
                encounters = processor.process_file(log_path)
                total_events = processor.total_events
                parse_errors = processor.parse_errors[:100]  # Limit errors

                progress.update(task, description="[green]Parallel processing complete!")

            except Exception as e:
                console.print(f"[red]Parallel processing failed: {e}[/red]")
                console.print("[yellow]Please try with --no-parallel flag[/yellow]")
                return

    # Calculate processing time
    processing_time = (datetime.now() - start_time).total_seconds()

    # Display results
    if format == "summary":
        display_unified_summary(encounters, total_events, parse_errors, processing_time)
    elif format == "json":
        export_unified_json(encounters, output or "output.json")
    elif format == "csv":
        export_unified_csv(encounters, output or "output.csv")


def display_unified_summary(encounters, total_events, parse_errors, processing_time):
    """Display summary for unified encounters."""
    console.print("\n[bold cyan]═══ Parsing Complete ═══[/bold cyan]")

    # Overall stats
    stats_table = Table(title="Parsing Statistics", show_header=False)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="white")

    stats_table.add_row("Total Events", f"{total_events:,}")
    stats_table.add_row("Processing Time", f"{processing_time:.2f}s")
    stats_table.add_row("Events/Second", f"{total_events / max(processing_time, 0.01):,.0f}")
    stats_table.add_row("Parse Errors", str(len(parse_errors)))
    stats_table.add_row("Total Encounters", str(len(encounters)))

    # Separate by type
    raid_encounters = [e for e in encounters if e.encounter_type == EncounterType.RAID]
    mplus_encounters = [e for e in encounters if e.encounter_type == EncounterType.MYTHIC_PLUS]

    stats_table.add_row("Raid Encounters", str(len(raid_encounters)))
    stats_table.add_row("Mythic+ Runs", str(len(mplus_encounters)))

    console.print(stats_table)

    # Encounter summary
    if encounters:
        enc_table = Table(title=f"\n[bold]Encounters ({len(encounters)})[/bold]")
        enc_table.add_column("#", style="dim", width=3)
        enc_table.add_column("Type", width=10)
        enc_table.add_column("Name", width=30)
        enc_table.add_column("Duration", width=8)
        enc_table.add_column("Players", width=7)
        enc_table.add_column("Deaths", width=6)
        enc_table.add_column("DPS", width=10)
        enc_table.add_column("Result", width=10)

        for i, enc in enumerate(encounters[:20], 1):  # Show first 20
            enc_type = "M+" if enc.encounter_type == EncounterType.MYTHIC_PLUS else "Raid"
            type_color = "magenta" if enc_type == "M+" else "red"

            name = enc.encounter_name
            if enc.keystone_level:
                name = f"{name} +{enc.keystone_level}"

            duration_str = f"{enc.duration:.0f}s" if enc.duration else "-"
            player_count = len(enc.characters)
            death_count = enc.metrics.total_deaths
            raid_dps = f"{enc.metrics.raid_dps:,.0f}" if enc.metrics.raid_dps else "-"

            result = "Success" if enc.success else "Wipe" if enc.success is False else "-"
            result_color = "green" if enc.success else "red" if enc.success is False else "dim"

            enc_table.add_row(
                str(i),
                f"[{type_color}]{enc_type}[/{type_color}]",
                name[:30],  # Truncate long names
                duration_str,
                str(player_count),
                str(death_count) if death_count > 0 else "-",
                raid_dps,
                f"[{result_color}]{result}[/{result_color}]",
            )

            # Show M+ fight breakdown
            if enc.encounter_type == EncounterType.MYTHIC_PLUS and enc.fights:
                boss_fights = [f for f in enc.fights if f.is_boss]
                trash_fights = [f for f in enc.fights if f.is_trash]
                if boss_fights or trash_fights:
                    enc_table.add_row(
                        "",
                        f"[dim]→ Fights[/dim]",
                        f"[dim]Bosses: {len(boss_fights)}, Trash: {len(trash_fights)}[/dim]",
                        "",
                        "",
                        "",
                        "",
                        "",
                    )

        console.print(enc_table)

        # Top performers across all encounters
        all_characters = {}
        for enc in encounters:
            for guid, char in enc.characters.items():
                if guid not in all_characters:
                    all_characters[guid] = {
                        "name": char.character_name,
                        "total_damage": 0,
                        "total_healing": 0,
                        "encounters": 0,
                        "deaths": 0,
                    }
                all_characters[guid]["total_damage"] += char.total_damage_done
                all_characters[guid]["total_healing"] += char.total_healing_done
                all_characters[guid]["encounters"] += 1
                all_characters[guid]["deaths"] += char.death_count

        if all_characters:
            # Sort by total damage
            top_dps = sorted(
                all_characters.items(), key=lambda x: x[1]["total_damage"], reverse=True
            )[:5]

            perf_table = Table(title="\n[bold]Top Performers (by total damage)[/bold]")
            perf_table.add_column("Player", style="green")
            perf_table.add_column("Total Damage", style="red")
            perf_table.add_column("Total Healing", style="blue")
            perf_table.add_column("Encounters", style="cyan")
            perf_table.add_column("Deaths", style="yellow")

            for guid, data in top_dps:
                perf_table.add_row(
                    data["name"],
                    f"{data['total_damage']:,}",
                    f"{data['total_healing']:,}" if data["total_healing"] > 1000 else "-",
                    str(data["encounters"]),
                    str(data["deaths"]) if data["deaths"] > 0 else "-",
                )

            console.print(perf_table)


def export_unified_json(encounters, output_file):
    """Export unified encounters to JSON format."""
    import json

    data = []
    for enc in encounters:
        enc_data = {
            "encounter_type": enc.encounter_type.value,
            "encounter_id": enc.encounter_id,
            "encounter_name": enc.encounter_name,
            "instance_name": enc.instance_name,
            "difficulty": enc.difficulty,
            "keystone_level": enc.keystone_level,
            "affixes": enc.affixes,
            "start_time": enc.start_time.isoformat() if enc.start_time else None,
            "end_time": enc.end_time.isoformat() if enc.end_time else None,
            "duration": enc.duration,
            "success": enc.success,
            "metrics": {
                "total_damage": enc.metrics.total_damage,
                "total_healing": enc.metrics.total_healing,
                "total_deaths": enc.metrics.total_deaths,
                "raid_dps": enc.metrics.raid_dps,
                "raid_hps": enc.metrics.raid_hps,
                "player_count": enc.metrics.player_count,
            },
            "fight_count": len(enc.fights),
            "character_count": len(enc.characters),
        }

        # Add fight breakdown for M+
        if enc.encounter_type == EncounterType.MYTHIC_PLUS and enc.fights:
            enc_data["fights"] = [
                {
                    "name": f.fight_name,
                    "type": "boss" if f.is_boss else ("trash" if f.is_trash else "normal"),
                    "duration": f.duration,
                    "success": f.success,
                }
                for f in enc.fights
            ]

        data.append(enc_data)

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, default=str)

    console.print(f"[green]Exported {len(encounters)} encounters to {output_file}[/green]")


def export_unified_csv(encounters, output_file):
    """Export unified encounters to CSV format."""
    import csv

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Type",
                "Name",
                "Difficulty",
                "Keystone",
                "Start",
                "End",
                "Duration",
                "Success",
                "Players",
                "Deaths",
                "DPS",
                "HPS",
            ]
        )

        for enc in encounters:
            writer.writerow(
                [
                    enc.encounter_type.value,
                    enc.encounter_name,
                    enc.difficulty or "",
                    enc.keystone_level or "",
                    enc.start_time.isoformat() if enc.start_time else "",
                    enc.end_time.isoformat() if enc.end_time else "",
                    f"{enc.duration:.1f}" if enc.duration else "",
                    enc.success if enc.success is not None else "",
                    enc.metrics.player_count,
                    enc.metrics.total_deaths,
                    f"{enc.metrics.raid_dps:.0f}" if enc.metrics.raid_dps else "",
                    f"{enc.metrics.raid_hps:.0f}" if enc.metrics.raid_hps else "",
                ]
            )

    console.print(f"[green]Exported {len(encounters)} encounters to {output_file}[/green]")


def display_summary(parser, segmenter, fights, event_types, total_events, processing_time):
    """Display parsing summary."""
    console.print("\n[bold cyan]═══ Parsing Complete ═══[/bold cyan]")

    # Overall stats
    stats_table = Table(title="Parsing Statistics", show_header=False)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="white")

    stats_table.add_row("Total Events", f"{total_events:,}")
    stats_table.add_row("Processing Time", f"{processing_time:.2f}s")
    stats_table.add_row("Events/Second", f"{total_events / max(processing_time, 0.01):,.0f}")
    stats_table.add_row("Parse Errors", str(len(parser.parse_errors)))

    console.print(stats_table)

    # Fight summary
    if fights:
        fight_table = Table(title=f"\n[bold]Encounters Found ({len(fights)})[/bold]")
        fight_table.add_column("#", style="dim", width=3)
        fight_table.add_column("Type", width=12)
        fight_table.add_column("Name", width=30)
        fight_table.add_column("Duration", width=8)
        fight_table.add_column("Players", width=7)
        fight_table.add_column("Result", width=10)

        for i, fight in enumerate(fights, 1):
            fight_type_color = {
                FightType.RAID_BOSS: "red",
                FightType.MYTHIC_PLUS: "magenta",
                FightType.DUNGEON_BOSS: "yellow",
                FightType.TRASH: "dim",
            }.get(fight.fight_type, "white")

            result = "Success" if fight.success else "Wipe" if fight.success is False else "-"
            result_color = "green" if fight.success else "red" if fight.success is False else "dim"

            name = fight.encounter_name or "Trash Combat"
            if fight.keystone_level:
                name = f"{name} +{fight.keystone_level}"

            fight_table.add_row(
                str(i),
                f"[{fight_type_color}]{fight.fight_type.value}[/{fight_type_color}]",
                name,
                fight.get_duration_str(),
                str(fight.get_player_count()),
                f"[{result_color}]{result}[/{result_color}]",
            )

        console.print(fight_table)

    # Top event types
    event_table = Table(title="\n[bold]Top Event Types[/bold]")
    event_table.add_column("Event Type", width=30)
    event_table.add_column("Count", width=12)
    event_table.add_column("Percentage", width=10)

    for event_type, count in event_types.most_common(10):
        percentage = (count / total_events) * 100
        event_table.add_row(event_type, f"{count:,}", f"{percentage:.1f}%")

    console.print(event_table)

    # Segment statistics
    seg_stats = segmenter.get_stats()
    if seg_stats["total_fights"] > 0:
        console.print(f"\n[bold cyan]Fight Statistics:[/bold cyan]")
        console.print(f"  • Successful Kills: {seg_stats['successful_kills']}")
        console.print(f"  • Wipes: {seg_stats['wipes']}")
        console.print(f"  • Incomplete: {seg_stats['incomplete']}")


def export_json(fights, output_file):
    """Export fights to JSON format."""
    import json

    data = []
    for fight in fights:
        data.append(
            {
                "id": fight.fight_id,
                "type": fight.fight_type.value,
                "name": fight.encounter_name,
                "start": fight.start_time.isoformat() if fight.start_time else None,
                "end": fight.end_time.isoformat() if fight.end_time else None,
                "duration": fight.duration,
                "success": fight.success,
                "players": fight.get_player_count(),
                "event_count": len(fight.events),
            }
        )

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    console.print(f"[green]Exported {len(fights)} fights to {output_file}[/green]")


def export_csv(fights, output_file):
    """Export fights to CSV format."""
    import csv

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["ID", "Type", "Name", "Start", "End", "Duration", "Success", "Players", "Events"]
        )

        for fight in fights:
            writer.writerow(
                [
                    fight.fight_id,
                    fight.fight_type.value,
                    fight.encounter_name or "Trash",
                    fight.start_time.isoformat() if fight.start_time else "",
                    fight.end_time.isoformat() if fight.end_time else "",
                    fight.duration or "",
                    fight.success if fight.success is not None else "",
                    fight.get_player_count(),
                    len(fight.events),
                ]
            )

    console.print(f"[green]Exported {len(fights)} fights to {output_file}[/green]")


@cli.command()
@click.argument("log_file", type=click.Path(exists=True))
@click.option(
    "--interactive/--summary",
    default=True,
    help="Launch interactive analyzer (default) or show summary",
)
@click.option(
    "--threads",
    default=None,
    type=int,
    help="Number of threads for parallel processing (default: CPU count)",
)
@click.option(
    "--no-parallel",
    is_flag=True,
    help="Disable parallel processing (force sequential)",
)
def analyze(log_file, interactive, threads, no_parallel):
    """Analyze a combat log file with interactive exploration using unified segmentation."""
    from .analyzer import InteractiveAnalyzer

    log_path = Path(log_file)

    if interactive:
        # Full interactive analysis
        console.print(f"[bold green]Analyzing combat log:[/bold green] {log_path.name}")
        console.print(f"[cyan]File size:[/cyan] {log_path.stat().st_size / 1024 / 1024:.1f} MB\n")

        # Choose processing method based on options
        start_time = datetime.now()
        encounters = []
        parse_errors = []

        if no_parallel:
            # Force sequential processing
            console.print("[yellow]Using sequential processing (--no-parallel)[/yellow]")

            tokenizer = LineTokenizer()
            event_factory = EventFactory()
            segmenter = UnifiedSegmenter()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Processing events...", total=None)

                event_count = 0
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if line.strip() and not line.strip().startswith("#"):
                            try:
                                parsed_line = tokenizer.parse_line(line)
                                if parsed_line:
                                    event = event_factory.create_event(parsed_line)
                                    if event:
                                        segmenter.process_event(event)
                                        event_count += 1

                                        if event_count % 10000 == 0:
                                            progress.update(
                                                task, description=f"[cyan]Processed {event_count:,} events..."
                                            )

                            except Exception as e:
                                if len(parse_errors) < 100:
                                    parse_errors.append(f"Line {line_num}: {str(e)}")

                progress.update(task, description="[green]Finalizing encounters...")

            # Get encounters
            encounters = segmenter.get_encounters()

            # Calculate metrics
            for encounter in encounters:
                encounter.calculate_metrics()

        else:
            # Try parallel processing first
            processor = UnifiedParallelProcessor(max_workers=threads)

            console.print(
                f"[cyan]Using parallel processing ({processor.max_workers} threads)[/cyan]"
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Detecting encounter boundaries...", total=None)

                try:
                    encounters = processor.process_file(log_path)
                    parse_errors = processor.parse_errors[:100]  # Limit errors

                    progress.update(task, description="[green]Parallel processing complete!")

                except Exception as e:
                    console.print(f"[red]Parallel processing failed: {e}[/red]")
                    console.print("[yellow]Please try with --no-parallel flag[/yellow]")
                    return

        # Parsing summary
        processing_time = (datetime.now() - start_time).total_seconds()
        console.print(f"\n[bold green]✓ Parsing Complete[/bold green]")

        # Calculate total events from all encounters
        total_events = sum(len(enc.events) for enc in encounters)
        console.print(f"  Events: {total_events:,}")
        console.print(f"  Time: {processing_time:.1f}s")
        console.print(f"  Encounters: {len(encounters)}")
        if parse_errors:
            console.print(f"  [yellow]Warnings: {len(parse_errors)}[/yellow]")

        # Prepare enhanced data for analyzer
        raid_encounters = [e for e in encounters if e.encounter_type == EncounterType.RAID]
        mythic_plus_runs = [e for e in encounters if e.encounter_type == EncounterType.MYTHIC_PLUS]

        enhanced_data = {
            "encounters": encounters,
            "raid_encounters": raid_encounters,
            "mythic_plus_runs": mythic_plus_runs,
            "stats": {
                "total_encounters": len(encounters),
                "raid_count": len(raid_encounters),
                "mplus_count": len(mythic_plus_runs),
                "total_events": total_events,
                "processing_time": processing_time,
            }
        }

        # Launch interactive analyzer with unified encounters
        console.print("\n[bold cyan]Launching Interactive Analyzer...[/bold cyan]")
        analyzer = InteractiveAnalyzer(encounters, enhanced_data)
        analyzer.run()

    else:
        # Simple summary mode (old behavior but improved)
        console.print(f"[bold cyan]Analyzing:[/bold cyan] {log_path.name}")

        parser = CombatLogParser()
        event_types = Counter()
        sample_size = 1000  # Analyze more events for better summary

        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            sample_lines = []
            for i, line in enumerate(f):
                if i >= sample_size:
                    break
                sample_lines.append(line)

        # Parse sample
        events = parser.parse_lines(sample_lines)

        # Analyze events
        for event in events:
            event_types[event.event_type] += 1

        # Display analysis
        table = Table(title="Event Type Distribution (First 1,000 events)")
        table.add_column("Event Type", width=30)
        table.add_column("Count", width=10)
        table.add_column("Percentage", width=12)

        total_events = len(events)
        for event_type, count in event_types.most_common():
            percentage = (count / total_events * 100) if total_events > 0 else 0
            table.add_row(event_type, str(count), f"{percentage:.1f}%")

        console.print(table)

        # Show sample events
        if events:
            console.print(f"\n[bold]Sample Events:[/bold]")
            for event in events[:5]:
                console.print(f"  • {event.timestamp.strftime('%H:%M:%S')} - {event.event_type}")
                if hasattr(event, "spell_name") and event.spell_name:
                    console.print(f"    Spell: {event.spell_name}")
                if event.source_name and event.dest_name:
                    console.print(f"    {event.source_name} → {event.dest_name}")

        console.print(f"\n[dim]Use --interactive for full analysis and exploration[/dim]")


@cli.command()
def test():
    """Run parser tests on example files."""
    examples_dir = Path("examples")
    if not examples_dir.exists():
        console.print("[red]Examples directory not found![/red]")
        return

    log_files = list(examples_dir.glob("*.txt"))
    console.print(f"[bold cyan]Found {len(log_files)} example files[/bold cyan]\n")

    total_events = 0
    total_fights = 0
    total_errors = 0

    for log_file in log_files:
        console.print(f"[yellow]Testing:[/yellow] {log_file.name}")

        parser = CombatLogParser()
        segmenter = EncounterSegmenter()

        events_count = 0
        for event in parser.parse_file(str(log_file)):
            events_count += 1
            segmenter.process_event(event)

        fights = segmenter.finalize()
        errors = len(parser.parse_errors)

        console.print(f"  ✓ Events: {events_count:,}")
        console.print(f"  ✓ Fights: {len(fights)}")
        if errors:
            console.print(f"  [red]✗ Errors: {errors}[/red]")

        total_events += events_count
        total_fights += len(fights)
        total_errors += errors

    console.print(f"\n[bold green]Test Complete![/bold green]")
    console.print(f"Total Events: {total_events:,}")
    console.print(f"Total Fights: {total_fights}")
    console.print(f"Total Errors: {total_errors}")


@cli.group()
def stream():
    """Streaming server commands for real-time log processing."""
    pass


@stream.command("start")
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--db-path", default="data/combat_logs.db", help="Database path")
def start_server(host, port, db_path):
    """Start the streaming server."""
    console.print(f"[bold green]Starting streaming server on {host}:{port}[/bold green]")
    console.print(f"[cyan]Database:[/cyan] {db_path}")
    console.print(f"[cyan]WebSocket endpoint:[/cyan] ws://{host}:{port}/ws")
    console.print(f"[cyan]API docs:[/cyan] http://{host}:{port}/docs")
    console.print(f"[yellow]Note: Use docker-compose up for production deployment[/yellow]")


@stream.command("test")
@click.option("--host", default="localhost", help="Server host")
@click.option("--port", default=8000, help="Server port")
def test_connection(host, port):
    """Test connection to streaming server."""
    import urllib.request
    import json

    try:
        url = f"http://{host}:{port}/health"
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.getcode() == 200:
                console.print(f"[bold green]✓ Server is responding at {host}:{port}[/bold green]")
                health_data = json.loads(response.read().decode())
                console.print(f"[cyan]Status:[/cyan] {health_data.get('status', 'unknown')}")
            else:
                console.print(f"[red]✗ Server responded with status {response.getcode()}[/red]")
    except Exception as e:
        console.print(f"[red]✗ Failed to connect to {host}:{port}[/red]")
        console.print(f"[red]Error: {e}[/red]")


@stream.command("status")
@click.option("--host", default="localhost", help="Server host")
@click.option("--port", default=8000, help="Server port")
def server_status(host, port):
    """Get detailed server status and statistics."""
    import urllib.request
    import json

    try:
        url = f"http://{host}:{port}/stats"
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.getcode() == 200:
                stats = json.loads(response.read().decode())
                console.print(f"[bold green]Server Status - {host}:{port}[/bold green]")

                # Server info
                server_stats = stats.get("server", {})
                uptime = server_stats.get("uptime_seconds", 0)
                console.print(f"[cyan]Uptime:[/cyan] {uptime:.1f}s")
                console.print(
                    f"[cyan]Active WebSockets:[/cyan] {server_stats.get('active_websockets', 0)}"
                )

                # Database stats
                db_stats = stats.get("database", {}).get("database", {})
                console.print(
                    f"[cyan]Total Encounters:[/cyan] {db_stats.get('total_encounters', 0)}"
                )
                console.print(f"[cyan]Total Events:[/cyan] {db_stats.get('total_events', 0)}")

                # Processing stats
                proc_stats = stats.get("processing", {})
                console.print(
                    f"[cyan]Events/sec:[/cyan] {proc_stats.get('events_per_second', 0):.1f}"
                )

            else:
                console.print(f"[red]✗ Failed to get status: HTTP {response.getcode()}[/red]")
    except Exception as e:
        console.print(f"[red]✗ Failed to connect: {e}[/red]")


def _process_sequential(log_path, console):
    """
    Sequential processing fallback for the CLI.

    Args:
        log_path: Path to the combat log file
        console: Rich console for output

    Returns:
        Tuple of (fights, enhanced_data, parse_errors)
    """
    from .parser.parser import CombatLogParser
    from .segmentation.encounters import EncounterSegmenter
    from .segmentation.enhanced import EnhancedSegmenter
    from rich.progress import Progress, SpinnerColumn, TextColumn

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()
    enhanced_segmenter = EnhancedSegmenter()

    total_events = 0

    # Parse with progress indication
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processing events...", total=None)

        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        parsed_line = parser.tokenizer.parse_line(line)
                        event = parser.event_factory.create_event(parsed_line)
                        segmenter.process_event(event)
                        enhanced_segmenter.process_event(event)
                        total_events += 1

                        # Update progress every 10k events
                        if total_events % 10000 == 0:
                            progress.update(
                                task, description=f"[cyan]Processed {total_events:,} events..."
                            )

                    except Exception as e:
                        parser.parse_errors.append(f"Line {line_num}: {str(e)}")

        progress.update(task, description="[green]Finalizing encounters...")

    # Finalize data
    fights = segmenter.finalize()
    raid_encounters, mythic_plus_runs = enhanced_segmenter.finalize()

    enhanced_data = {
        "raid_encounters": raid_encounters,
        "mythic_plus_runs": mythic_plus_runs,
        "stats": enhanced_segmenter.get_stats(),
    }

    return fights, enhanced_data, parser.parse_errors


def main():
    """Entry point for the loothing-parser command."""
    cli()


if __name__ == "__main__":
    main()
