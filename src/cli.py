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
from .segmentation.encounters import EncounterSegmenter, FightType


# Set up rich console for pretty output
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)


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
def parse(log_file, output, format):
    """Parse a combat log file and extract encounters."""
    log_path = Path(log_file)
    console.print(f"[bold green]Parsing combat log:[/bold green] {log_path.name}")

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    # Statistics tracking
    event_types = Counter()
    total_events = 0
    start_time = datetime.now()

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
        task = progress.add_task(
            f"[cyan]Processing {file_size / 1024 / 1024:.1f} MB...", total=file_size
        )

        def update_progress(prog, bytes_read, total_bytes):
            progress.update(task, completed=bytes_read)

        # Process events
        for event in parser.parse_file(str(log_path), update_progress):
            total_events += 1
            event_types[event.event_type] += 1

            # Segment into encounters
            completed_fight = segmenter.process_event(event)
            if completed_fight:
                console.print(
                    f"[yellow]Fight completed:[/yellow] {completed_fight.encounter_name or 'Trash'} "
                    f"({'Success' if completed_fight.success else 'Wipe' if completed_fight.success is False else 'Unknown'})"
                )

    # Finalize remaining fights
    fights = segmenter.finalize()

    # Calculate processing time
    processing_time = (datetime.now() - start_time).total_seconds()

    # Display results
    if format == "summary":
        display_summary(parser, segmenter, fights, event_types, total_events, processing_time)
    elif format == "json":
        export_json(fights, output or "output.json")
    elif format == "csv":
        export_csv(fights, output or "output.csv")


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
@click.option("--lines", "-n", default=100, help="Number of lines to analyze")
def analyze(log_file, lines):
    """Analyze the structure of a combat log file."""
    log_path = Path(log_file)
    console.print(f"[bold cyan]Analyzing:[/bold cyan] {log_path.name}")

    parser = CombatLogParser()
    event_types = Counter()

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        sample_lines = []
        for i, line in enumerate(f):
            if i >= lines:
                break
            sample_lines.append(line)

    # Parse sample
    events = parser.parse_lines(sample_lines)

    # Analyze events
    for event in events:
        event_types[event.event_type] += 1

    # Display analysis
    table = Table(title="Event Type Distribution")
    table.add_column("Event Type", width=30)
    table.add_column("Count", width=10)

    for event_type, count in event_types.most_common():
        table.add_row(event_type, str(count))

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
                console.print(f"[cyan]Total Encounters:[/cyan] {db_stats.get('total_encounters', 0)}")
                console.print(f"[cyan]Total Events:[/cyan] {db_stats.get('total_events', 0)}")

                # Processing stats
                proc_stats = stats.get("processing", {})
                console.print(f"[cyan]Events/sec:[/cyan] {proc_stats.get('events_per_second', 0):.1f}")

            else:
                console.print(f"[red]✗ Failed to get status: HTTP {response.getcode()}[/red]")
    except Exception as e:
        console.print(f"[red]✗ Failed to connect: {e}[/red]")


def main():
    """Entry point for the loothing-parser command."""
    cli()


if __name__ == "__main__":
    main()
