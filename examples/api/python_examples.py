#!/usr/bin/env python3
"""
WoW Combat Log Analysis API - Python Examples

This script demonstrates various ways to use the API for combat log analysis,
including basic queries, advanced analytics, and real-time monitoring.

Requirements:
    pip install requests matplotlib pandas asyncio websockets

Usage:
    python python_examples.py
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import requests
import pandas as pd
import matplotlib.pyplot as plt
import websockets


class WoWAnalyticsAPI:
    """Python client for WoW Combat Log Analysis API."""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize the API client.

        Args:
            base_url: Base URL for the API (e.g., 'https://api.example.com/api/v1')
            api_key: Your API authentication key
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "WoW-Analytics-Python-Client/1.0",
            }
        )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request to the API."""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                # Handle rate limiting
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                return self._make_request(method, endpoint, **kwargs)
            else:
                print(f"HTTP Error {response.status_code}: {response.text}")
                raise
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            raise

    def get_character(self, name: str, server: Optional[str] = None) -> Dict[str, Any]:
        """Get character profile information."""
        params = {}
        if server:
            params["server"] = server

        return self._make_request("GET", f"/characters/{name}", params=params)

    def get_character_performance(
        self,
        name: str,
        days: int = 30,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get character performance data."""
        params = {"days": days}
        if encounter_type:
            params["encounter_type"] = encounter_type
        if difficulty:
            params["difficulty"] = difficulty

        return self._make_request("GET", f"/characters/{name}/performance", params=params)

    def get_encounters(
        self,
        limit: int = 50,
        boss_name: Optional[str] = None,
        success_only: Optional[bool] = None,
        days: int = 7,
    ) -> Dict[str, Any]:
        """Get encounter list with filtering."""
        params = {"limit": limit, "days": days}
        if boss_name:
            params["boss_name"] = boss_name
        if success_only is not None:
            params["success_only"] = success_only

        return self._make_request("GET", "/encounters", params=params)

    def get_performance_trends(
        self,
        metric: str,
        character_name: Optional[str] = None,
        class_name: Optional[str] = None,
        days: int = 90,
    ) -> Dict[str, Any]:
        """Get performance trends over time."""
        params = {"days": days}
        if character_name:
            params["character_name"] = character_name
        if class_name:
            params["class_name"] = class_name

        return self._make_request("GET", f"/analytics/trends/{metric}", params=params)

    def search(self, query: str, scope: str = "all", fuzzy: bool = False) -> Dict[str, Any]:
        """Search across combat log data."""
        search_request = {"query": query, "scope": scope, "fuzzy_matching": fuzzy, "limit": 20}

        return self._make_request("POST", "/search", json=search_request)

    def custom_aggregation(
        self,
        metrics: List[str],
        group_by: List[str],
        filters: Dict[str, Any],
        percentiles: List[float] = [50, 75, 90, 95, 99],
    ) -> Dict[str, Any]:
        """Perform custom aggregation query."""
        aggregation_request = {
            "metrics": metrics,
            "group_by": group_by,
            "filters": filters,
            "percentiles": percentiles,
        }

        return self._make_request("POST", "/aggregations/custom", json=aggregation_request)


def example_1_basic_character_analysis(api: WoWAnalyticsAPI):
    """Example 1: Basic character analysis and performance tracking."""
    print("=== Example 1: Basic Character Analysis ===")

    # Get character information
    character = api.get_character("Thrall", "Stormrage")
    print(f"Character: {character['name']} - {character['class_name']} ({character['spec_name']})")
    print(f"Guild: {character['guild_name']}")
    print(f"Item Level: {character.get('avg_item_level', 'Unknown')}")
    print(f"Total Encounters: {character['total_encounters']}")

    # Get recent performance
    performance = api.get_character_performance("Thrall", days=30, encounter_type="raid")

    if performance:
        # Calculate statistics
        dps_values = [p["dps"] for p in performance]
        avg_dps = sum(dps_values) / len(dps_values)
        max_dps = max(dps_values)

        print(f"\nPerformance (Last 30 days):")
        print(f"  Average DPS: {avg_dps:,.0f}")
        print(f"  Best DPS: {max_dps:,.0f}")
        print(f"  Encounters: {len(performance)}")

        # Show recent encounters
        print(f"\nRecent Encounters:")
        for encounter in performance[:5]:
            date = encounter["date"][:10]  # Just the date part
            print(f"  {date}: {encounter['encounter_name']} - {encounter['dps']:,.0f} DPS")

    print()


def example_2_guild_raid_analysis(api: WoWAnalyticsAPI):
    """Example 2: Guild raid analysis and progression tracking."""
    print("=== Example 2: Guild Raid Analysis ===")

    # Get recent successful raids
    encounters = api.get_encounters(limit=20, success_only=True, days=14)

    print(f"Recent Successful Raids ({len(encounters['data'])} encounters):")

    # Group by boss and difficulty
    boss_kills = {}
    for encounter in encounters["data"]:
        boss = encounter["boss_name"]
        difficulty = encounter["difficulty"]
        key = f"{boss} ({difficulty})"

        if key not in boss_kills:
            boss_kills[key] = {"count": 0, "total_duration": 0, "best_time": float("inf")}

        boss_kills[key]["count"] += 1
        duration = encounter["duration"]
        boss_kills[key]["total_duration"] += duration
        boss_kills[key]["best_time"] = min(boss_kills[key]["best_time"], duration)

    # Display results
    for boss, stats in boss_kills.items():
        avg_time = stats["total_duration"] / stats["count"]
        best_time = stats["best_time"]
        print(
            f"  {boss}: {stats['count']} kills, avg {avg_time/60:.1f}min, best {best_time/60:.1f}min"
        )

    print()


def example_3_class_performance_comparison(api: WoWAnalyticsAPI):
    """Example 3: Compare DPS performance across classes."""
    print("=== Example 3: Class Performance Comparison ===")

    # Get DPS aggregation by class
    aggregation = api.custom_aggregation(
        metrics=["dps"],
        group_by=["class_name"],
        filters={"encounter_type": "raid", "difficulty": "heroic", "days": 30},
    )

    print("Heroic Raid DPS by Class (Last 30 days):")

    # Sort by median DPS
    class_data = sorted(aggregation["data"], key=lambda x: x.get("dps_p50", 0), reverse=True)

    for class_stats in class_data:
        class_name = class_stats["class_name"]
        median_dps = class_stats.get("dps_p50", 0)
        p95_dps = class_stats.get("dps_p95", 0)
        count = class_stats.get("dps_count", 0)

        print(
            f"  {class_name:15}: {median_dps:7,.0f} (median), {p95_dps:7,.0f} (95th%), {count} samples"
        )

    print()


def example_4_performance_trends_visualization(api: WoWAnalyticsAPI):
    """Example 4: Create performance trend visualizations."""
    print("=== Example 4: Performance Trends Visualization ===")

    # Get DPS trends for a character
    trends = api.get_performance_trends(metric="dps", character_name="Thrall", days=90)

    if not trends["data_points"]:
        print("No trend data available")
        return

    # Prepare data for plotting
    dates = [
        datetime.fromisoformat(dp["timestamp"].replace("Z", "+00:00"))
        for dp in trends["data_points"]
    ]
    values = [dp["value"] for dp in trends["data_points"]]

    # Create plot
    plt.figure(figsize=(12, 6))
    plt.plot(dates, values, marker="o", linewidth=2, markersize=4)
    plt.title(f"DPS Trend for {trends.get('character_name', 'Character')} (90 days)")
    plt.xlabel("Date")
    plt.ylabel("DPS")
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)

    # Add trend line
    if len(values) > 1:
        z = np.polyfit(range(len(values)), values, 1)
        trend_line = np.poly1d(z)
        plt.plot(dates, trend_line(range(len(values))), "--", alpha=0.8, color="red")

    plt.tight_layout()
    plt.savefig("dps_trend.png", dpi=300, bbox_inches="tight")
    plt.show()

    print(f"Trend Direction: {trends['trend_direction']}")
    print(f"Average DPS: {trends['average_value']:,.0f}")
    print(f"Trend Strength: {trends['trend_strength']:.2f}")
    print("Chart saved as 'dps_trend.png'")
    print()


def example_5_advanced_search(api: WoWAnalyticsAPI):
    """Example 5: Advanced search with fuzzy matching."""
    print("=== Example 5: Advanced Search ===")

    # Search for enhancement shamans
    results = api.search("enhancement shaman", scope="characters")

    print(f"Search Results: {results['total_count']} found in {results['query_time_ms']:.1f}ms")

    for result in results["results"][:5]:
        print(f"  {result['title']} (relevance: {result['relevance_score']:.2f})")
        if "highlights" in result:
            for field, highlights in result["highlights"].items():
                print(f"    {field}: {highlights[0]}")

    # Try fuzzy search with typos
    print("\nFuzzy Search (with typos):")
    fuzzy_results = api.search("enhancment shamn", scope="characters", fuzzy=True)

    print(f"Fuzzy Results: {fuzzy_results['total_count']} found")
    for result in fuzzy_results["results"][:3]:
        print(f"  {result['title']} (relevance: {result['relevance_score']:.2f})")

    print()


def example_6_encounter_analysis(api: WoWAnalyticsAPI):
    """Example 6: Detailed encounter analysis."""
    print("=== Example 6: Encounter Analysis ===")

    # Get encounters for a specific boss
    encounters = api.get_encounters(boss_name="Fyrakk the Blazing", days=30)

    if not encounters["data"]:
        print("No encounters found for this boss")
        return

    print(f"Fyrakk the Blazing Encounters (Last 30 days): {len(encounters['data'])}")

    # Analyze success rate by difficulty
    difficulty_stats = {}

    for encounter in encounters["data"]:
        diff = encounter["difficulty"]
        if diff not in difficulty_stats:
            difficulty_stats[diff] = {"total": 0, "successful": 0, "durations": []}

        difficulty_stats[diff]["total"] += 1
        if encounter["success"]:
            difficulty_stats[diff]["successful"] += 1
            difficulty_stats[diff]["durations"].append(encounter["duration"])

    # Display statistics
    for difficulty, stats in difficulty_stats.items():
        success_rate = (stats["successful"] / stats["total"]) * 100

        if stats["durations"]:
            avg_duration = sum(stats["durations"]) / len(stats["durations"])
            best_duration = min(stats["durations"])
            print(
                f"  {difficulty.capitalize():10}: {success_rate:5.1f}% success rate, "
                f"avg {avg_duration/60:.1f}min, best {best_duration/60:.1f}min"
            )
        else:
            print(f"  {difficulty.capitalize():10}: {success_rate:5.1f}% success rate (no kills)")

    print()


async def example_7_real_time_monitoring(api_key: str):
    """Example 7: Real-time encounter monitoring via WebSocket."""
    print("=== Example 7: Real-time Monitoring ===")

    # Note: This is a simplified example of WebSocket usage
    # In practice, you'd need to handle authentication and error recovery

    websocket_url = "wss://api.example.com/api/v1/stream"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with websockets.connect(websocket_url, extra_headers=headers) as websocket:
            print("Connected to real-time stream...")

            # Subscribe to encounter updates
            subscribe_message = {
                "action": "subscribe",
                "topics": ["encounters", "performance_alerts"],
            }
            await websocket.send(json.dumps(subscribe_message))

            print("Listening for real-time updates... (Press Ctrl+C to stop)")

            async for message in websocket:
                try:
                    data = json.loads(message)

                    if data.get("type") == "encounter_update":
                        encounter = data["data"]
                        print(
                            f"🔥 Live Encounter: {encounter['boss_name']} "
                            f"({encounter['duration']:.0f}s, {encounter['raid_size']} players)"
                        )

                    elif data.get("type") == "performance_alert":
                        alert = data["data"]
                        print(
                            f"⚡ Performance Alert: {alert['character']} "
                            f"{alert['metric']} = {alert['value']:,.0f}"
                        )

                except json.JSONDecodeError:
                    print(f"Invalid JSON received: {message}")

    except Exception as e:
        print(f"WebSocket connection failed: {e}")
        print("Note: This example requires a live WebSocket endpoint")

    print()


def example_8_data_export_and_analysis(api: WoWAnalyticsAPI):
    """Example 8: Export data for advanced analysis with pandas."""
    print("=== Example 8: Data Export and Analysis ===")

    # Get performance data for multiple characters
    characters = ["Thrall", "Jaina", "Varian", "Sylvanas"]
    all_performance = []

    for char_name in characters:
        try:
            performance = api.get_character_performance(char_name, days=30)
            for perf in performance:
                perf["character"] = char_name
                all_performance.append(perf)
        except Exception as e:
            print(f"Failed to get data for {char_name}: {e}")

    if not all_performance:
        print("No performance data available")
        return

    # Create DataFrame
    df = pd.DataFrame(all_performance)

    # Basic statistics
    print("Performance Statistics by Character:")
    stats = df.groupby("character")["dps"].agg(["count", "mean", "std", "min", "max"]).round(0)
    print(stats)

    # Class comparison
    if "class_name" in df.columns:
        print("\nPerformance by Class:")
        class_stats = df.groupby("class_name")["dps"].agg(["count", "mean", "std"]).round(0)
        print(class_stats)

    # Export to CSV
    df.to_csv("performance_data.csv", index=False)
    print("\nData exported to 'performance_data.csv'")

    # Create comparison chart
    if len(characters) > 1:
        plt.figure(figsize=(10, 6))
        df.boxplot(column="dps", by="character", ax=plt.gca())
        plt.title("DPS Distribution by Character")
        plt.suptitle("")  # Remove default title
        plt.ylabel("DPS")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig("dps_comparison.png", dpi=300, bbox_inches="tight")
        plt.show()
        print("Comparison chart saved as 'dps_comparison.png'")

    print()


def main():
    """Run all examples."""
    # Configuration - Replace with your actual values
    API_BASE_URL = os.getenv("API_BASE_URL", "https://localhost:8000/api/v1")
    API_KEY = os.getenv("API_KEY")  # Set your API key in environment variables

    if not API_KEY:
        print("❌ Error: API_KEY environment variable is required")
        print("Set it with: export API_KEY=your_actual_api_key")
        return

    # Initialize API client
    api = WoWAnalyticsAPI(API_BASE_URL, API_KEY)

    print("WoW Combat Log Analysis API - Python Examples")
    print("=" * 50)

    try:
        # Test API connection
        response = api._make_request("GET", "/health")
        print(f"API Status: {response.get('status', 'unknown')}")
        print()

        # Run examples
        example_1_basic_character_analysis(api)
        example_2_guild_raid_analysis(api)
        example_3_class_performance_comparison(api)

        # Examples requiring matplotlib/numpy
        try:
            import numpy as np

            example_4_performance_trends_visualization(api)
        except ImportError:
            print("Skipping visualization example (matplotlib/numpy not available)")

        example_5_advanced_search(api)
        example_6_encounter_analysis(api)

        # Real-time monitoring example
        # asyncio.run(example_7_real_time_monitoring(API_KEY))

        # Data analysis example
        try:
            example_8_data_export_and_analysis(api)
        except ImportError:
            print("Skipping pandas example (pandas not available)")

        print("All examples completed successfully! 🎉")

    except Exception as e:
        print(f"Error running examples: {e}")
        print("Make sure you have a valid API key and the API is accessible.")


if __name__ == "__main__":
    main()
