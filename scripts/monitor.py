#!/usr/bin/env python3
"""
Real-time monitoring dashboard for WoW Combat Log Streaming System.

Provides a Rich-based terminal dashboard showing:
- Active WebSocket connections
- Processing statistics
- Database metrics
- Server health
"""

import asyncio
import json
import time
import requests
import websockets
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.live import Live
from rich.text import Text
from rich.align import Align
from rich import box

console = Console()


class ServerMonitor:
    """Real-time monitoring dashboard for the streaming server."""

    def __init__(self, server_url: str = "http://localhost:8000", update_interval: float = 2.0):
        self.server_url = server_url.rstrip('/')
        self.ws_url = server_url.replace('http://', 'ws://').replace('https://', 'wss://')
        self.update_interval = update_interval
        self.stats_history = []
        self.max_history = 50  # Keep last 50 data points
        self.start_time = datetime.now()

    def get_server_stats(self) -> Optional[Dict[str, Any]]:
        """Fetch server statistics from the API."""
        try:
            response = requests.get(f"{self.server_url}/api/stats", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            return {"error": str(e)}
        return None

    def get_health_status(self) -> Dict[str, Any]:
        """Check server health status."""
        try:
            response = requests.get(f"{self.server_url}/health", timeout=5)
            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_time": response.elapsed.total_seconds(),
                "status_code": response.status_code
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "response_time": None
            }

    def create_header_panel(self) -> Panel:
        """Create the header panel with server info."""
        uptime = datetime.now() - self.start_time
        header_text = Text()
        header_text.append("🎮 WoW Combat Log Streaming Monitor\n", style="bold blue")
        header_text.append(f"Server: {self.server_url}\n", style="dim")
        header_text.append(f"Uptime: {str(uptime).split('.')[0]}\n", style="dim")
        header_text.append(f"Updated: {datetime.now().strftime('%H:%M:%S')}", style="dim")

        return Panel(
            Align.center(header_text),
            title="System Monitor",
            border_style="blue"
        )

    def create_health_panel(self, health: Dict[str, Any]) -> Panel:
        """Create health status panel."""
        status = health.get("status", "unknown")

        if status == "healthy":
            status_text = Text("🟢 HEALTHY", style="bold green")
        elif status == "unhealthy":
            status_text = Text("🟡 UNHEALTHY", style="bold yellow")
        else:
            status_text = Text("🔴 ERROR", style="bold red")

        content = Text()
        content.append("Status: ")
        content.append_text(status_text)
        content.append("\n")

        if health.get("response_time"):
            content.append(f"Response Time: {health['response_time']:.3f}s\n")

        if health.get("error"):
            content.append(f"Error: {health['error']}\n", style="red")

        return Panel(content, title="Health", border_style="green" if status == "healthy" else "red")

    def create_connections_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create WebSocket connections panel."""
        connections = stats.get("connections", {})

        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Active Connections", str(connections.get("active", 0)))
        table.add_row("Total Sessions", str(connections.get("total_sessions", 0)))
        table.add_row("Messages Received", str(connections.get("messages_received", 0)))
        table.add_row("Messages Sent", str(connections.get("messages_sent", 0)))
        table.add_row("Bytes Received", self.format_bytes(connections.get("bytes_received", 0)))
        table.add_row("Bytes Sent", self.format_bytes(connections.get("bytes_sent", 0)))

        return Panel(table, title="WebSocket Connections", border_style="cyan")

    def create_processing_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create processing statistics panel."""
        processing = stats.get("processing", {})

        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Metric", style="yellow")
        table.add_column("Value", justify="right")

        table.add_row("Events Processed", str(processing.get("events_processed", 0)))
        table.add_row("Events/Second", f"{processing.get('events_per_second', 0):.1f}")
        table.add_row("Parse Errors", str(processing.get("parse_errors", 0)))
        table.add_row("Success Rate", f"{processing.get('success_rate', 0):.1%}")
        table.add_row("Avg Processing Time", f"{processing.get('avg_processing_time', 0):.3f}s")
        table.add_row("Queue Size", str(processing.get("queue_size", 0)))

        return Panel(table, title="Processing Stats", border_style="yellow")

    def create_database_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create database statistics panel."""
        database = stats.get("database", {})

        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Metric", style="green")
        table.add_column("Value", justify="right")

        table.add_row("Total Events", str(database.get("total_events", 0)))
        table.add_row("Database Size", self.format_bytes(database.get("db_size", 0)))
        table.add_row("Compression Ratio", f"{database.get('compression_ratio', 0):.1%}")
        table.add_row("Recent Encounters", str(database.get("recent_encounters", 0)))
        table.add_row("Active Characters", str(database.get("active_characters", 0)))
        table.add_row("Queries/Minute", str(database.get("queries_per_minute", 0)))

        return Panel(table, title="Database Stats", border_style="green")

    def create_performance_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create system performance panel."""
        performance = stats.get("performance", {})

        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Metric", style="red")
        table.add_column("Value", justify="right")

        # CPU and Memory
        table.add_row("CPU Usage", f"{performance.get('cpu_percent', 0):.1f}%")
        table.add_row("Memory Usage", self.format_bytes(performance.get("memory_usage", 0)))
        table.add_row("Memory Percent", f"{performance.get('memory_percent', 0):.1f}%")

        # Disk I/O
        table.add_row("Disk Read", self.format_bytes(performance.get("disk_read", 0)))
        table.add_row("Disk Write", self.format_bytes(performance.get("disk_write", 0)))

        return Panel(table, title="Performance", border_style="red")

    def create_recent_activity_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create recent activity panel."""
        activity = stats.get("recent_activity", [])

        content = Text()
        if activity:
            for item in activity[-10:]:  # Show last 10 activities
                timestamp = item.get("timestamp", "")
                event = item.get("event", "")
                details = item.get("details", "")

                content.append(f"{timestamp} ", style="dim")
                content.append(f"{event} ", style="bold")
                content.append(f"{details}\n")
        else:
            content.append("No recent activity", style="dim")

        return Panel(content, title="Recent Activity", border_style="magenta")

    def format_bytes(self, bytes_value: int) -> str:
        """Format bytes in human readable format."""
        if bytes_value == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = abs(bytes_value)
        unit_index = 0

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        return f"{size:.1f} {units[unit_index]}"

    def create_dashboard_layout(self, stats: Dict[str, Any], health: Dict[str, Any]) -> Layout:
        """Create the complete dashboard layout."""
        layout = Layout()

        # Split into header and body
        layout.split_column(
            Layout(name="header", size=6),
            Layout(name="body")
        )

        # Header
        layout["header"].update(self.create_header_panel())

        # Body - split into rows
        layout["body"].split_column(
            Layout(name="status_row", size=8),
            Layout(name="metrics_row", size=12),
            Layout(name="activity_row")
        )

        # Status row - health and connections
        layout["status_row"].split_row(
            Layout(name="health"),
            Layout(name="connections")
        )

        layout["health"].update(self.create_health_panel(health))
        layout["connections"].update(self.create_connections_panel(stats))

        # Metrics row - processing, database, performance
        layout["metrics_row"].split_row(
            Layout(name="processing"),
            Layout(name="database"),
            Layout(name="performance")
        )

        layout["processing"].update(self.create_processing_panel(stats))
        layout["database"].update(self.create_database_panel(stats))
        layout["performance"].update(self.create_performance_panel(stats))

        # Activity row
        layout["activity_row"].update(self.create_recent_activity_panel(stats))

        return layout

    async def monitor_loop(self):
        """Main monitoring loop."""
        with Live(self.create_dashboard_layout({}, {}), refresh_per_second=1, screen=True) as live:
            while True:
                try:
                    # Fetch data
                    health = self.get_health_status()
                    stats = self.get_server_stats() or {}

                    # Store in history
                    self.stats_history.append({
                        "timestamp": datetime.now(),
                        "stats": stats,
                        "health": health
                    })

                    # Keep only recent history
                    if len(self.stats_history) > self.max_history:
                        self.stats_history = self.stats_history[-self.max_history:]

                    # Update display
                    layout = self.create_dashboard_layout(stats, health)
                    live.update(layout)

                    await asyncio.sleep(self.update_interval)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    error_stats = {"error": f"Monitor error: {str(e)}"}
                    error_health = {"status": "error", "error": str(e)}
                    layout = self.create_dashboard_layout(error_stats, error_health)
                    live.update(layout)
                    await asyncio.sleep(self.update_interval)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="WoW Combat Log Server Monitor")
    parser.add_argument("--server", default="http://localhost:8000", help="Server URL")
    parser.add_argument("--interval", type=float, default=2.0, help="Update interval in seconds")
    args = parser.parse_args()

    console.print("🎮 Starting WoW Combat Log Server Monitor...", style="bold blue")
    console.print(f"Monitoring: {args.server}")
    console.print("Press Ctrl+C to exit\n")

    monitor = ServerMonitor(args.server, args.interval)

    try:
        await monitor.monitor_loop()
    except KeyboardInterrupt:
        console.print("\n👋 Monitor stopped by user", style="bold yellow")
    except Exception as e:
        console.print(f"\n❌ Monitor error: {e}", style="bold red")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)