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
            efficiency = (char.total_healing_done / (char.total_healing_done + char.total_overhealing) * 100) if (char.total_healing_done + char.total_overhealing) > 0 else 0
            efficiency_color = "green" if efficiency >= 80 else "yellow" if efficiency >= 60 else "red"
            death_color = "red" if char.death_count > 0 else "green"

            table.add_row(
                f"[{rank_color}]{i}[/{rank_color}]",
                f"[{rank_color}]{name}[/{rank_color}]",
                f"[{rank_color}]{hps:,.0f}[/{rank_color}]",
                f"[{rank_color}]{char.total_healing_done:,}[/{rank_color}]",
                f"[{rank_color}]{char.total_overhealing:,}[/{rank_color}]",
                f"[{efficiency_color}]{efficiency:.1f}%[/{efficiency_color}]",
                f"[{death_color}]{char.death_count}[/{death_color}]"
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
            overall_efficiency = (encounter_metrics['total_healing'] / (encounter_metrics['total_healing'] + encounter_metrics['total_overhealing']) * 100) if (encounter_metrics['total_healing'] + encounter_metrics['total_overhealing']) > 0 else 0
            self.console.print(f"  Overall Efficiency: {overall_efficiency:.1f}%")

        self.console.print("\n[dim]Press any key to return...[/dim]")
        self._wait_for_key()

    def _show_events_timeline(
        self, fight: Fight, characters: Optional[Dict[str, CharacterEventStream]]
    ):
        """Show events timeline."""
        self.console.print("[yellow]Events timeline not yet implemented[/yellow]")
        self._wait_for_key()

    def _show_timeline_detail(
        self, fight: Fight, characters: Optional[Dict[str, CharacterEventStream]]
    ):
        """Show detailed timeline view."""
        self.console.print("[yellow]Timeline details not yet implemented[/yellow]")
        self._wait_for_key()

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
