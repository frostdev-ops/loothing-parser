"""
Interactive combat log analyzer implementation.
"""

import sys
from typing import List, Dict, Optional, Any
from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt
from rich.panel import Panel

from .navigation import NavigationState, ViewMode
from .displays import DisplayBuilder
from .metrics import MetricsCalculator
from ..segmentation.encounters import Fight, FightType
from ..models.encounter_models import RaidEncounter, MythicPlusRun
from ..models.character_events import CharacterEventStream


class InteractiveAnalyzer:
    """
    Interactive terminal interface for analyzing combat log data.

    Provides a menu-driven interface to explore encounters, player performance,
    and detailed combat statistics.
    """

    def __init__(self, fights: List[Fight], enhanced_data: Optional[Dict[str, Any]] = None):
        """
        Initialize the interactive analyzer.

        Args:
            fights: List of parsed fight encounters
            enhanced_data: Optional enhanced data from EnhancedSegmenter
        """
        self.console = Console()
        self.fights = fights
        self.enhanced_data = enhanced_data or {}
        self.navigation = NavigationState()
        self.display_builder = DisplayBuilder()
        self.metrics_calculator = MetricsCalculator()

        # Filter state
        self.filtered_fights = fights.copy()
        self.current_filters = {}

        # Data caches
        self._character_cache = {}

        # Display configuration
        self.console.clear()

    def run(self):
        """Start the interactive session."""
        try:
            self.console.print(
                "[bold green]Starting Interactive Combat Log Analyzer...[/bold green]"
            )
            self.console.print(f"[dim]Loaded {len(self.fights)} encounters[/dim]\n")

            while True:
                if not self._handle_current_view():
                    break

        except KeyboardInterrupt:
            self._quit()
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            self._quit()

    def _handle_current_view(self) -> bool:
        """
        Handle the current view state.

        Returns:
            False if user wants to quit, True to continue
        """
        try:
            if self.navigation.current_view == ViewMode.MAIN_MENU:
                return self._handle_main_menu()
            elif self.navigation.current_view == ViewMode.OVERVIEW:
                return self._handle_overview()
            elif self.navigation.current_view == ViewMode.ENCOUNTERS:
                return self._handle_encounters_list()
            elif self.navigation.current_view == ViewMode.ENCOUNTER_DETAIL:
                return self._handle_encounter_detail()
            elif self.navigation.current_view == ViewMode.PLAYERS:
                return self._handle_players_list()
            elif self.navigation.current_view == ViewMode.PLAYER_DETAIL:
                return self._handle_player_detail()
            else:
                # Not implemented views
                self.console.print("[yellow]This feature is not yet implemented.[/yellow]")
                self.console.print("Press any key to return to main menu...")
                self._wait_for_key()
                self.navigation.navigate_to(ViewMode.MAIN_MENU)
                return True

        except Exception as e:
            self.console.print(f"[red]Error in view handler: {e}[/red]")
            return True

    def _handle_main_menu(self) -> bool:
        """Handle main menu interaction."""
        self.console.clear()
        panel = self.display_builder.create_main_menu()

        # Add summary info
        summary_text = f"\n{len(self.fights)} encounters found"
        if self.fights:
            raid_count = sum(1 for f in self.fights if f.fight_type == FightType.RAID_BOSS)
            mythic_count = sum(1 for f in self.fights if f.fight_type == FightType.MYTHIC_PLUS)
            if raid_count:
                summary_text += f" | {raid_count} raid bosses"
            if mythic_count:
                summary_text += f" | {mythic_count} M+ dungeons"

        self.console.print(panel)
        self.console.print(f"[dim]{summary_text}[/dim]\n")

        # Get user input
        choice = Prompt.ask(
            "Select option", choices=["1", "2", "3", "4", "5", "6", "q", "Q"], default="q"
        )

        if choice.lower() == "q":
            return False
        elif choice == "1":
            self.navigation.navigate_to(ViewMode.OVERVIEW)
        elif choice == "2":
            self._reset_encounter_filters()
            self.navigation.navigate_to(ViewMode.ENCOUNTERS)
        elif choice == "3":
            self.navigation.navigate_to(ViewMode.PLAYERS)
        elif choice == "4":
            self.navigation.navigate_to(ViewMode.TIMELINE)
        elif choice == "5":
            self.navigation.navigate_to(ViewMode.SEARCH)
        elif choice == "6":
            self.navigation.navigate_to(ViewMode.EXPORT)

        return True

    def _handle_overview(self) -> bool:
        """Handle overview display."""
        self.console.clear()
        panel = self.display_builder.create_overview(self.fights)
        self.console.print(panel)

        self._wait_for_key()
        self.navigation.go_back()
        return True

    def _handle_encounters_list(self) -> bool:
        """Handle encounters list view."""
        if not self.filtered_fights:
            self.console.clear()
            self.console.print("[yellow]No encounters match the current filters.[/yellow]")
            self.console.print("Press any key to return to main menu...")
            self._wait_for_key()
            self.navigation.go_back()
            return True

        # Calculate pagination
        total_items = len(self.filtered_fights)
        total_pages = max(0, (total_items - 1) // self.navigation.items_per_page)
        start, end = self.navigation.get_page_slice(total_items)

        # Display encounters list
        self.console.clear()
        panel = self.display_builder.create_encounters_list(
            self.filtered_fights, start, end, self.navigation.current_page, total_pages
        )
        self.console.print(panel)

        # Show filter info if any filters active
        if self.current_filters:
            filter_info = " | ".join(
                f"{k}: {v}" for k, v in self.current_filters.items() if v is not None
            )
            self.console.print(f"[dim]Active filters: {filter_info}[/dim]")

        # Get user input
        self.console.print()
        choice = Prompt.ask(
            "Enter choice",
            choices=["n", "p", "f", "b", "h", "q"]
            + [str(i) for i in range(1, min(21, end - start + 1))],
            default="b",
        )

        if choice.lower() == "q":
            return False
        elif choice.lower() == "b":
            self.navigation.go_back()
        elif choice.lower() == "n":
            if not self.navigation.next_page(total_items):
                self.console.print("[yellow]Already on last page[/yellow]")
                self._wait_for_key()
        elif choice.lower() == "p":
            if not self.navigation.prev_page():
                self.console.print("[yellow]Already on first page[/yellow]")
                self._wait_for_key()
        elif choice.lower() == "f":
            self._handle_filter_menu()
        elif choice.lower() == "h":
            self._show_help()
        elif choice.isdigit():
            # Select encounter
            selected_index = int(choice) - 1 + start
            if 0 <= selected_index < len(self.filtered_fights):
                self.navigation.selected_encounter_index = selected_index
                self.navigation.navigate_to(ViewMode.ENCOUNTER_DETAIL)

        return True

    def _handle_encounter_detail(self) -> bool:
        """Handle detailed encounter view."""
        if (
            self.navigation.selected_encounter_index >= len(self.filtered_fights)
            or self.navigation.selected_encounter_index < 0
        ):
            self.console.print("[red]Invalid encounter selection[/red]")
            self.navigation.go_back()
            return True

        fight = self.filtered_fights[self.navigation.selected_encounter_index]

        # Try to get enhanced character data
        characters = self._get_encounter_characters(fight)

        self.console.clear()
        panel = self.display_builder.create_encounter_detail(fight, characters)
        self.console.print(panel)

        # Get user input
        choice = Prompt.ask("Select action", choices=["d", "h", "e", "t", "b", "q"], default="b")

        if choice.lower() == "q":
            return False
        elif choice.lower() == "b":
            self.navigation.go_back()
        elif choice.lower() == "d":
            self._show_dps_details(fight, characters)
        elif choice.lower() == "h":
            self._show_hps_details(fight, characters)
        elif choice.lower() == "e":
            self._show_events_timeline(fight, characters)
        elif choice.lower() == "t":
            self._show_timeline_detail(fight, characters)

        return True

    def _handle_filter_menu(self):
        """Handle filter menu interaction."""
        self.console.clear()
        panel = self.display_builder.create_filter_panel(self.current_filters)
        self.console.print(panel)

        choice = Prompt.ask(
            "Filter option", choices=["r", "m", "d", "t", "a", "s", "w", "e", "b"], default="b"
        )

        if choice.lower() == "b":
            return
        elif choice.lower() == "r":
            self._apply_type_filter(FightType.RAID_BOSS)
        elif choice.lower() == "m":
            self._apply_type_filter(FightType.MYTHIC_PLUS)
        elif choice.lower() == "d":
            self._apply_type_filter(FightType.DUNGEON_BOSS)
        elif choice.lower() == "t":
            self._apply_type_filter(FightType.TRASH)
        elif choice.lower() == "a":
            self._clear_type_filter()
        elif choice.lower() == "s":
            self._apply_result_filter(True)
        elif choice.lower() == "w":
            self._apply_result_filter(False)
        elif choice.lower() == "e":
            self._clear_result_filter()

        self.navigation.reset_pagination()

    def _apply_type_filter(self, fight_type: FightType):
        """Apply fight type filter."""
        self.current_filters["type"] = fight_type.value
        self.filtered_fights = [f for f in self.fights if f.fight_type == fight_type]

    def _apply_result_filter(self, success: bool):
        """Apply result filter."""
        self.current_filters["result"] = "Success" if success else "Wipe"
        self.filtered_fights = [f for f in self.filtered_fights if f.success == success]

    def _clear_type_filter(self):
        """Clear type filter."""
        self.current_filters.pop("type", None)
        self._rebuild_filtered_fights()

    def _clear_result_filter(self):
        """Clear result filter."""
        self.current_filters.pop("result", None)
        self._rebuild_filtered_fights()

    def _reset_encounter_filters(self):
        """Reset all encounter filters."""
        self.current_filters = {}
        self.filtered_fights = self.fights.copy()
        self.navigation.reset_pagination()

    def _rebuild_filtered_fights(self):
        """Rebuild filtered fights list based on current filters."""
        self.filtered_fights = self.fights.copy()

        if "type" in self.current_filters:
            fight_type = FightType(self.current_filters["type"])
            self.filtered_fights = [f for f in self.filtered_fights if f.fight_type == fight_type]

        if "result" in self.current_filters:
            success = self.current_filters["result"] == "Success"
            self.filtered_fights = [f for f in self.filtered_fights if f.success == success]

    def _get_encounter_characters(self, fight: Fight) -> Optional[Dict[str, CharacterEventStream]]:
        """Get character data for an encounter if available."""
        if not self.enhanced_data:
            return None

        # Get enhanced data from raid encounters or mythic plus runs
        raid_encounters = self.enhanced_data.get("raid_encounters", [])
        mythic_plus_runs = self.enhanced_data.get("mythic_plus_runs", [])

        # First try to match by encounter type and timing
        time_tolerance = 60  # seconds

        # For raid bosses, find matching raid encounter
        if fight.fight_type == FightType.RAID_BOSS:
            for raid_encounter in raid_encounters:
                if (
                    raid_encounter.encounter_id == fight.encounter_id
                    and abs((raid_encounter.start_time - fight.start_time).total_seconds())
                    < time_tolerance
                ):
                    return raid_encounter.characters

        # For mythic plus dungeons, find matching run
        elif fight.fight_type == FightType.MYTHIC_PLUS:
            for m_plus_run in mythic_plus_runs:
                if abs(
                    (m_plus_run.start_time - fight.start_time).total_seconds()
                ) < time_tolerance and m_plus_run.dungeon_name in (fight.encounter_name or ""):
                    return m_plus_run.characters if hasattr(m_plus_run, "characters") else {}

        # For dungeon bosses within M+, find from segments
        elif fight.fight_type == FightType.DUNGEON_BOSS:
            for m_plus_run in mythic_plus_runs:
                # Check if this boss is part of an M+ run
                for segment in getattr(m_plus_run, "segments", []):
                    if (
                        hasattr(segment, "boss_name")
                        and segment.boss_name == fight.encounter_name
                        and abs((segment.start_time - fight.start_time).total_seconds())
                        < time_tolerance
                    ):
                        return getattr(segment, "characters", {})

        # Fallback: create basic character streams from fight participants
        if fight.participants:
            characters = {}
            for guid, participant in fight.participants.items():
                if participant["is_player"]:
                    characters[guid] = CharacterEventStream(
                        character_guid=guid, character_name=participant["name"] or "Unknown"
                    )
            return characters if characters else None

        return None

    def _show_help(self):
        """Show help panel."""
        self.console.clear()
        panel = self.display_builder.create_help_panel()
        self.console.print(panel)
        self._wait_for_key()

    def _show_dps_details(
        self, fight: Fight, characters: Optional[Dict[str, CharacterEventStream]]
    ):
        """Show detailed DPS breakdown."""
        self.console.clear()

        if not characters or not fight.duration:
            self.console.print("[red]No character data available for DPS analysis[/red]")
            self._wait_for_key()
            return

        # Create DPS rankings table
        dps_rankings = self.metrics_calculator.get_dps_rankings(characters, fight.duration)

        # Main DPS table
        from rich.table import Table

        table = Table(title=f"DPS Breakdown - {fight.encounter_name or 'Unknown'}")
        table.add_column("Rank", width=4)
        table.add_column("Player", width=20)
        table.add_column("DPS", width=12, justify="right")
        table.add_column("Total Damage", width=15, justify="right")
        table.add_column("Activity %", width=10, justify="right")
        table.add_column("Deaths", width=7, justify="center")

        for i, (name, dps, char) in enumerate(dps_rankings[:10], 1):
            rank_color = "gold1" if i <= 3 else "white"
            activity_color = (
                "green"
                if char.activity_percentage >= 90
                else "yellow" if char.activity_percentage >= 75 else "red"
            )
            death_color = "red" if char.death_count > 0 else "green"

            table.add_row(
                f"[{rank_color}]{i}[/{rank_color}]",
                f"[{rank_color}]{name}[/{rank_color}]",
                f"[{rank_color}]{dps:,.0f}[/{rank_color}]",
                f"[{rank_color}]{char.total_damage_done:,}[/{rank_color}]",
                f"[{activity_color}]{char.activity_percentage:.1f}%[/{activity_color}]",
                f"[{death_color}]{char.death_count}[/{death_color}]",
            )

        self.console.print(table)

        # Top abilities breakdown
        if dps_rankings:
            top_abilities = self.metrics_calculator.get_top_abilities(characters, "damage")
            if top_abilities:
                self.console.print("\n[bold cyan]Top Damage Abilities:[/bold cyan]")
                abilities_table = Table()
                abilities_table.add_column("Player", width=20)
                abilities_table.add_column("Ability", width=25)
                abilities_table.add_column("Total Damage", width=15, justify="right")

                for char_name, spell_name, total in top_abilities[:10]:
                    abilities_table.add_row(char_name, spell_name, f"{total:,}")

                self.console.print(abilities_table)

        # Overall stats
        encounter_metrics = self.metrics_calculator.calculate_encounter_metrics(fight, characters)
        if encounter_metrics:
            self.console.print(f"\n[bold]Encounter Summary:[/bold]")
            self.console.print(f"  Raid DPS: {encounter_metrics['raid_dps']:,.0f}")
            self.console.print(f"  Total Damage: {encounter_metrics['total_damage']:,}")
            self.console.print(f"  Average Activity: {encounter_metrics['activity_avg']:.1f}%")
            self.console.print(f"  Total Deaths: {encounter_metrics['total_deaths']}")

        self.console.print("\n[dim]Press any key to return...[/dim]")
        self._wait_for_key()

    def _show_hps_details(
        self, fight: Fight, characters: Optional[Dict[str, CharacterEventStream]]
    ):
        """Show detailed HPS breakdown."""
        self.console.clear()

        if not characters or not fight.duration:
            self.console.print("[red]No character data available for HPS analysis[/red]")
            self._wait_for_key()
            return

        # Create HPS rankings table
        hps_rankings = self.metrics_calculator.get_hps_rankings(characters, fight.duration)

        if not hps_rankings:
            self.console.print("[yellow]No healing data found for this encounter[/yellow]")
            self._wait_for_key()
            return

        # Main HPS table
        from rich.table import Table

        table = Table(title=f"HPS Breakdown - {fight.encounter_name or 'Unknown'}")
        table.add_column("Rank", width=4)
        table.add_column("Player", width=20)
        table.add_column("HPS", width=12, justify="right")
        table.add_column("Total Healing", width=15, justify="right")
        table.add_column("Overhealing", width=12, justify="right")
        table.add_column("Efficiency %", width=12, justify="right")
        table.add_column("Deaths", width=7, justify="center")

        for i, (name, hps, char) in enumerate(hps_rankings[:10], 1):
            rank_color = "gold1" if i <= 3 else "white"
            efficiency = (
                (char.total_healing_done / (char.total_healing_done + char.total_overhealing) * 100)
                if (char.total_healing_done + char.total_overhealing) > 0
                else 0
            )
            efficiency_color = (
                "green" if efficiency >= 80 else "yellow" if efficiency >= 60 else "red"
            )
            death_color = "red" if char.death_count > 0 else "green"

            table.add_row(
                f"[{rank_color}]{i}[/{rank_color}]",
                f"[{rank_color}]{name}[/{rank_color}]",
                f"[{rank_color}]{hps:,.0f}[/{rank_color}]",
                f"[{rank_color}]{char.total_healing_done:,}[/{rank_color}]",
                f"[{rank_color}]{char.total_overhealing:,}[/{rank_color}]",
                f"[{efficiency_color}]{efficiency:.1f}%[/{efficiency_color}]",
                f"[{death_color}]{char.death_count}[/{death_color}]",
            )

        self.console.print(table)

        # Top healing abilities breakdown
        top_abilities = self.metrics_calculator.get_top_abilities(characters, "healing")
        if top_abilities:
            self.console.print("\n[bold green]Top Healing Abilities:[/bold green]")
            abilities_table = Table()
            abilities_table.add_column("Player", width=20)
            abilities_table.add_column("Ability", width=25)
            abilities_table.add_column("Total Healing", width=15, justify="right")

            for char_name, spell_name, total in top_abilities[:10]:
                abilities_table.add_row(char_name, spell_name, f"{total:,}")

            self.console.print(abilities_table)

        # Overall healing stats
        encounter_metrics = self.metrics_calculator.calculate_encounter_metrics(fight, characters)
        if encounter_metrics:
            self.console.print(f"\n[bold]Healing Summary:[/bold]")
            self.console.print(f"  Raid HPS: {encounter_metrics['raid_hps']:,.0f}")
            self.console.print(f"  Total Healing: {encounter_metrics['total_healing']:,}")
            self.console.print(f"  Total Overhealing: {encounter_metrics['total_overhealing']:,}")
            overall_efficiency = (
                (
                    encounter_metrics["total_healing"]
                    / (encounter_metrics["total_healing"] + encounter_metrics["total_overhealing"])
                    * 100
                )
                if (encounter_metrics["total_healing"] + encounter_metrics["total_overhealing"]) > 0
                else 0
            )
            self.console.print(f"  Overall Efficiency: {overall_efficiency:.1f}%")

        self.console.print("\n[dim]Press any key to return...[/dim]")
        self._wait_for_key()

    def _handle_players_list(self) -> bool:
        """Handle players list view."""
        self.console.clear()

        # Aggregate player data across all encounters
        player_stats = self._aggregate_player_data()

        if not player_stats:
            self.console.print("[yellow]No player data found across encounters.[/yellow]")
            self.console.print("Press any key to return to main menu...")
            self._wait_for_key()
            self.navigation.go_back()
            return True

        # Create players summary table
        from rich.table import Table

        table = Table(title="Player Performance Summary")
        table.add_column("Player", width=20)
        table.add_column("Encounters", width=10, justify="center")
        table.add_column("Avg DPS", width=12, justify="right")
        table.add_column("Avg HPS", width=12, justify="right")
        table.add_column("Total Deaths", width=12, justify="center")
        table.add_column("Success Rate", width=12, justify="right")
        table.add_column("Avg iLevel", width=10, justify="right")

        # Sort by average DPS
        sorted_players = sorted(player_stats.items(), key=lambda x: x[1]["avg_dps"], reverse=True)

        for player_name, stats in sorted_players:
            success_rate = (
                (stats["successful_encounters"] / stats["total_encounters"] * 100)
                if stats["total_encounters"] > 0
                else 0
            )
            success_color = (
                "green" if success_rate >= 80 else "yellow" if success_rate >= 60 else "red"
            )
            death_color = (
                "red"
                if stats["total_deaths"] > 5
                else "yellow" if stats["total_deaths"] > 2 else "green"
            )

            table.add_row(
                player_name,
                str(stats["total_encounters"]),
                f"{stats['avg_dps']:,.0f}",
                f"{stats['avg_hps']:,.0f}",
                f"[{death_color}]{stats['total_deaths']}[/{death_color}]",
                f"[{success_color}]{success_rate:.1f}%[/{success_color}]",
                f"{stats['avg_item_level']:.0f}" if stats["avg_item_level"] > 0 else "N/A",
            )

        self.console.print(table)

        # Summary stats
        total_players = len(player_stats)
        avg_success_rate = (
            sum(
                stats["successful_encounters"] / stats["total_encounters"]
                for stats in player_stats.values()
                if stats["total_encounters"] > 0
            )
            / total_players
            if total_players > 0
            else 0
        )

        self.console.print(f"\n[bold]Summary:[/bold]")
        self.console.print(f"  Total unique players: {total_players}")
        self.console.print(f"  Average success rate: {avg_success_rate * 100:.1f}%")

        # Get user input
        choice = Prompt.ask("Select action", choices=["1", "2", "3", "s", "b", "q"], default="b")

        if choice.lower() == "q":
            return False
        elif choice.lower() == "b":
            self.navigation.go_back()
        elif choice.isdigit():
            # Select specific player for detailed view
            player_index = int(choice) - 1
            if 0 <= player_index < len(sorted_players):
                selected_player = sorted_players[player_index][0]
                self.navigation.selected_player_guid = selected_player
                self.navigation.navigate_to(ViewMode.PLAYER_DETAIL)

        return True

    def _handle_player_detail(self) -> bool:
        """Handle individual player detail view."""
        self.console.clear()

        if not self.navigation.selected_player_guid:
            self.console.print("[red]No player selected[/red]")
            self.navigation.go_back()
            return True

        # Get detailed player data
        player_data = self._get_player_detailed_data(self.navigation.selected_player_guid)

        if not player_data:
            self.console.print(
                f"[red]No data found for player: {self.navigation.selected_player_guid}[/red]"
            )
            self.navigation.go_back()
            return True

        # Display detailed player information
        self.console.print(f"[bold cyan]Player Details: {player_data['name']}[/bold cyan]\n")

        # Performance across encounters
        from rich.table import Table

        encounters_table = Table(title="Performance by Encounter")
        encounters_table.add_column("Encounter", width=25)
        encounters_table.add_column("Result", width=10)
        encounters_table.add_column("DPS", width=12, justify="right")
        encounters_table.add_column("HPS", width=12, justify="right")
        encounters_table.add_column("Deaths", width=8, justify="center")
        encounters_table.add_column("Duration", width=10)

        for encounter in player_data["encounters"]:
            result_color = "green" if encounter["success"] else "red"
            death_color = "red" if encounter["deaths"] > 0 else "green"

            encounters_table.add_row(
                encounter["name"],
                f"[{result_color}]{'Kill' if encounter['success'] else 'Wipe'}[/{result_color}]",
                f"{encounter['dps']:,.0f}",
                f"{encounter['hps']:,.0f}",
                f"[{death_color}]{encounter['deaths']}[/{death_color}]",
                encounter["duration"],
            )

        self.console.print(encounters_table)

        # Overall stats
        self.console.print(f"\n[bold]Overall Statistics:[/bold]")
        self.console.print(f"  Total encounters: {len(player_data['encounters'])}")
        self.console.print(f"  Success rate: {player_data['success_rate']:.1f}%")
        self.console.print(f"  Average DPS: {player_data['avg_dps']:,.0f}")
        self.console.print(f"  Average HPS: {player_data['avg_hps']:,.0f}")
        self.console.print(f"  Total deaths: {player_data['total_deaths']}")

        self.console.print("\n[dim]Press any key to return...[/dim]")
        self._wait_for_key()
        self.navigation.go_back()
        return True

    def _aggregate_player_data(self) -> Dict[str, Dict[str, Any]]:
        """Aggregate player performance data across all encounters."""
        player_stats = {}

        for fight in self.fights:
            characters = self._get_encounter_characters(fight)
            if not characters:
                continue

            for guid, char in characters.items():
                if not char.character_name:
                    continue

                if char.character_name not in player_stats:
                    player_stats[char.character_name] = {
                        "total_encounters": 0,
                        "successful_encounters": 0,
                        "total_dps": 0,
                        "total_hps": 0,
                        "total_deaths": 0,
                        "total_item_level": 0,
                        "encounters_with_gear": 0,
                        "avg_dps": 0,
                        "avg_hps": 0,
                        "avg_item_level": 0,
                    }

                stats = player_stats[char.character_name]
                stats["total_encounters"] += 1

                if fight.success:
                    stats["successful_encounters"] += 1

                if fight.duration and fight.duration > 0:
                    dps = char.total_damage_done / fight.duration
                    hps = char.total_healing_done / fight.duration
                    stats["total_dps"] += dps
                    stats["total_hps"] += hps

                stats["total_deaths"] += char.death_count

                if char.item_level and char.item_level > 0:
                    stats["total_item_level"] += char.item_level
                    stats["encounters_with_gear"] += 1

        # Calculate averages
        for stats in player_stats.values():
            if stats["total_encounters"] > 0:
                stats["avg_dps"] = stats["total_dps"] / stats["total_encounters"]
                stats["avg_hps"] = stats["total_hps"] / stats["total_encounters"]
            if stats["encounters_with_gear"] > 0:
                stats["avg_item_level"] = stats["total_item_level"] / stats["encounters_with_gear"]

        return player_stats

    def _get_player_detailed_data(self, player_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed data for a specific player."""
        encounters = []
        total_dps = 0
        total_hps = 0
        total_deaths = 0
        successful = 0

        for fight in self.fights:
            characters = self._get_encounter_characters(fight)
            if not characters:
                continue

            # Find this player in the encounter
            player_char = None
            for char in characters.values():
                if char.character_name == player_name:
                    player_char = char
                    break

            if not player_char:
                continue

            dps = (
                player_char.total_damage_done / fight.duration
                if fight.duration and fight.duration > 0
                else 0
            )
            hps = (
                player_char.total_healing_done / fight.duration
                if fight.duration and fight.duration > 0
                else 0
            )

            encounters.append(
                {
                    "name": fight.encounter_name or "Unknown",
                    "success": fight.success or False,
                    "dps": dps,
                    "hps": hps,
                    "deaths": player_char.death_count,
                    "duration": fight.get_duration_str(),
                }
            )

            total_dps += dps
            total_hps += hps
            total_deaths += player_char.death_count
            if fight.success:
                successful += 1

        if not encounters:
            return None

        return {
            "name": player_name,
            "encounters": encounters,
            "success_rate": (successful / len(encounters) * 100) if encounters else 0,
            "avg_dps": total_dps / len(encounters) if encounters else 0,
            "avg_hps": total_hps / len(encounters) if encounters else 0,
            "total_deaths": total_deaths,
        }

    def _show_events_timeline(
        self, fight: Fight, characters: Optional[Dict[str, CharacterEventStream]]
    ):
        """Show events timeline."""
        self.console.clear()

        if not characters:
            self.console.print("[red]No character data available for timeline[/red]")
            self._wait_for_key()
            return

        # Generate timeline events
        timeline_events = self._generate_timeline_events(fight, characters)

        if not timeline_events:
            self.console.print("[yellow]No notable events found in this encounter[/yellow]")
            self._wait_for_key()
            return

        # Display timeline
        from rich.table import Table

        table = Table(title=f"Events Timeline - {fight.encounter_name or 'Unknown'}")
        table.add_column("Time", width=8)
        table.add_column("Event Type", width=15)
        table.add_column("Player", width=20)
        table.add_column("Description", width=40)
        table.add_column("Impact", width=15)

        for event in timeline_events[:50]:  # Show first 50 events
            time_color = "cyan"
            type_color = {
                "Death": "red",
                "Resurrection": "green",
                "Major Cooldown": "yellow",
                "Damage Spike": "orange",
                "Healing Spike": "blue",
                "Boss Ability": "magenta",
                "Phase Change": "cyan",
            }.get(event["type"], "white")

            impact_color = {
                "Critical": "red",
                "High": "yellow",
                "Medium": "blue",
                "Low": "dim",
            }.get(event["impact"], "white")

            table.add_row(
                f"[{time_color}]{event['time']}[/{time_color}]",
                f"[{type_color}]{event['type']}[/{type_color}]",
                event["player"],
                event["description"],
                f"[{impact_color}]{event['impact']}[/{impact_color}]",
            )

        self.console.print(table)

        # Summary of key events
        deaths = [e for e in timeline_events if e["type"] == "Death"]
        resurrections = [e for e in timeline_events if e["type"] == "Resurrection"]
        major_cds = [e for e in timeline_events if e["type"] == "Major Cooldown"]

        self.console.print(f"\n[bold]Timeline Summary:[/bold]")
        self.console.print(f"  Deaths: {len(deaths)}")
        self.console.print(f"  Battle Resurrections: {len(resurrections)}")
        self.console.print(f"  Major Cooldowns Used: {len(major_cds)}")
        self.console.print(
            f"  Total events shown: {min(50, len(timeline_events))} / {len(timeline_events)}"
        )

        self.console.print("\n[dim]Press any key to return...[/dim]")
        self._wait_for_key()

    def _generate_timeline_events(
        self, fight: Fight, characters: Dict[str, CharacterEventStream]
    ) -> List[Dict[str, Any]]:
        """Generate a chronological list of important events."""
        events = []
        fight_start = fight.start_time

        # Major cooldown spell IDs
        major_cooldowns = {
            32182: "Heroism",
            80353: "Time Warp",
            2825: "Bloodlust",
            90355: "Ancient Hysteria",
            264667: "Primal Rage",
            10060: "Power Infusion",
            47536: "Rapture",
            31821: "Aura Mastery",
            64843: "Divine Favor",
            498: "Divine Protection",
            642: "Divine Shield",
        }

        for guid, char in characters.items():
            # Track deaths
            for death in char.deaths:
                relative_time = death.datetime - fight_start
                minutes = int(relative_time.total_seconds() // 60)
                seconds = int(relative_time.total_seconds() % 60)

                events.append(
                    {
                        "timestamp": death.timestamp,
                        "time": f"{minutes}:{seconds:02d}",
                        "type": "Death",
                        "player": char.character_name,
                        "description": f"{char.character_name} died",
                        "impact": "Critical",
                    }
                )

            # Track major damage spikes (top 10% of damage events)
            if char.damage_done:
                damage_amounts = [event.amount for event in char.damage_done]
                if damage_amounts:
                    high_damage_threshold = sorted(damage_amounts, reverse=True)[
                        min(len(damage_amounts) // 10, len(damage_amounts) - 1)
                    ]
                    for damage_event in char.damage_done:
                        if (
                            damage_event.amount >= high_damage_threshold
                            and damage_event.amount > 50000
                        ):
                            try:
                                relative_time = damage_event.timestamp - fight_start
                                minutes = int(relative_time.total_seconds() // 60)
                                seconds = int(relative_time.total_seconds() % 60)

                                events.append(
                                    {
                                        "timestamp": damage_event.timestamp.timestamp(),
                                        "time": f"{minutes}:{seconds:02d}",
                                        "type": "Damage Spike",
                                        "player": char.character_name,
                                        "description": f"{damage_event.spell_name or 'Unknown'}: {damage_event.amount:,} damage",
                                        "impact": "High",
                                    }
                                )
                            except:
                                continue

            # Track major healing spikes
            if char.healing_done:
                healing_amounts = [event.amount for event in char.healing_done]
                if healing_amounts:
                    high_healing_threshold = sorted(healing_amounts, reverse=True)[
                        min(len(healing_amounts) // 10, len(healing_amounts) - 1)
                    ]
                    for heal_event in char.healing_done:
                        if (
                            heal_event.amount >= high_healing_threshold
                            and heal_event.amount > 30000
                        ):
                            try:
                                relative_time = heal_event.timestamp - fight_start
                                minutes = int(relative_time.total_seconds() // 60)
                                seconds = int(relative_time.total_seconds() % 60)

                                events.append(
                                    {
                                        "timestamp": heal_event.timestamp.timestamp(),
                                        "time": f"{minutes}:{seconds:02d}",
                                        "type": "Healing Spike",
                                        "player": char.character_name,
                                        "description": f"{heal_event.spell_name or 'Unknown'}: {heal_event.amount:,} healing",
                                        "impact": "Medium",
                                    }
                                )
                            except:
                                continue

            # Track major cooldown usage
            for buff in char.buffs_gained:
                if hasattr(buff, "spell_id") and buff.spell_id in major_cooldowns:
                    try:
                        relative_time = buff.timestamp - fight_start
                        minutes = int(relative_time.total_seconds() // 60)
                        seconds = int(relative_time.total_seconds() % 60)

                        events.append(
                            {
                                "timestamp": buff.timestamp.timestamp(),
                                "time": f"{minutes}:{seconds:02d}",
                                "type": "Major Cooldown",
                                "player": char.character_name,
                                "description": f"Used {major_cooldowns[buff.spell_id]}",
                                "impact": "High",
                            }
                        )
                    except:
                        continue

        # Sort events by timestamp
        events.sort(key=lambda x: x["timestamp"])

        return events

    def _show_timeline_detail(
        self, fight: Fight, characters: Optional[Dict[str, CharacterEventStream]]
    ):
        """Show detailed timeline view."""
        self.console.clear()

        if not characters or not fight.duration:
            self.console.print("[red]No character data available for detailed timeline[/red]")
            self._wait_for_key()
            return

        # Generate detailed timeline with second-by-second breakdown
        timeline_data = self._generate_detailed_timeline(fight, characters)

        if not timeline_data:
            self.console.print("[yellow]No timeline data available[/yellow]")
            self._wait_for_key()
            return

        # Display detailed timeline in segments
        self._display_timeline_segments(fight, timeline_data, characters)

    def _generate_detailed_timeline(self, fight: Fight, characters: Dict[str, CharacterEventStream]) -> List[Dict[str, Any]]:
        """Generate detailed second-by-second timeline data."""
        timeline = []
        fight_duration = int(fight.duration) if fight.duration else 0

        if fight_duration == 0:
            return timeline

        # Create timeline buckets (5-second intervals)
        interval = 5  # seconds
        num_intervals = (fight_duration // interval) + 1

        for i in range(num_intervals):
            start_time = i * interval
            end_time = min((i + 1) * interval, fight_duration)

            interval_data = {
                'start': start_time,
                'end': end_time,
                'damage': {},
                'healing': {},
                'deaths': [],
                'major_events': []
            }

            # Aggregate data for this interval
            for guid, char in characters.items():
                char_damage = 0
                char_healing = 0

                # Calculate damage in this interval
                for damage_event in char.damage_done:
                    try:
                        event_time = (damage_event.timestamp - fight.start_time).total_seconds()
                        if start_time <= event_time < end_time:
                            char_damage += damage_event.amount
                    except:
                        continue

                # Calculate healing in this interval
                for heal_event in char.healing_done:
                    try:
                        event_time = (heal_event.timestamp - fight.start_time).total_seconds()
                        if start_time <= event_time < end_time:
                            char_healing += heal_event.amount
                    except:
                        continue

                if char_damage > 0:
                    interval_data['damage'][char.character_name] = char_damage
                if char_healing > 0:
                    interval_data['healing'][char.character_name] = char_healing

                # Check for deaths in this interval
                for death in char.deaths:
                    death_time = (death.datetime - fight.start_time).total_seconds()
                    if start_time <= death_time < end_time:
                        interval_data['deaths'].append({
                            'player': char.character_name,
                            'time': death_time
                        })

            timeline.append(interval_data)

        return timeline

    def _display_timeline_segments(self, fight: Fight, timeline_data: List[Dict[str, Any]], characters: Dict[str, CharacterEventStream]):
        """Display timeline in manageable segments."""
        from rich.table import Table
        from rich.progress import Progress, SpinnerColumn, TextColumn

        segments_per_page = 10
        total_segments = len(timeline_data)
        current_page = 0
        max_pages = (total_segments - 1) // segments_per_page + 1

        while True:
            self.console.clear()

            start_idx = current_page * segments_per_page
            end_idx = min(start_idx + segments_per_page, total_segments)

            table = Table(title=f"Detailed Timeline - {fight.encounter_name or 'Unknown'} (Page {current_page + 1}/{max_pages})")
            table.add_column("Time", width=10)
            table.add_column("Top DPS", width=25)
            table.add_column("Top HPS", width=25)
            table.add_column("Events", width=30)

            for i in range(start_idx, end_idx):
                if i >= len(timeline_data):
                    break

                interval = timeline_data[i]
                time_range = f"{interval['start']}-{interval['end']}s"

                # Top DPS in this interval
                top_dps = sorted(interval['damage'].items(), key=lambda x: x[1], reverse=True)[:3]
                dps_text = ", ".join([f"{name}: {dmg:,.0f}" for name, dmg in top_dps])

                # Top HPS in this interval
                top_hps = sorted(interval['healing'].items(), key=lambda x: x[1], reverse=True)[:3]
                hps_text = ", ".join([f"{name}: {heal:,.0f}" for name, heal in top_hps])

                # Events in this interval
                events = []
                for death in interval['deaths']:
                    events.append(f"💀 {death['player']} died")
                for event in interval['major_events']:
                    events.append(event)

                events_text = ", ".join(events) if events else "No major events"

                table.add_row(
                    time_range,
                    dps_text or "No damage",
                    hps_text or "No healing",
                    events_text
                )

            self.console.print(table)

            # Navigation controls
            choices = ["b"]
            nav_text = "[B]ack"

            if current_page > 0:
                choices.append("p")
                nav_text += " | [P]revious"

            if current_page < max_pages - 1:
                choices.append("n")
                nav_text += " | [N]ext"

            choices.append("q")
            nav_text += " | [Q]uit"

            self.console.print(f"\n{nav_text}")
            choice = Prompt.ask("Navigate", choices=choices, default="b")

            if choice.lower() == "q":
                return
            elif choice.lower() == "b":
                self._wait_for_key()
                return
            elif choice.lower() == "p" and current_page > 0:
                current_page -= 1
            elif choice.lower() == "n" and current_page < max_pages - 1:
                current_page += 1

    def _wait_for_key(self):
        """Wait for user to press any key."""
        try:
            self.console.input("Press Enter to continue...")
        except KeyboardInterrupt:
            pass

    def _quit(self):
        """Clean exit."""
        self.console.clear()
        self.console.print("[bold cyan]Thanks for using the Combat Log Analyzer![/bold cyan]")
        sys.exit(0)
