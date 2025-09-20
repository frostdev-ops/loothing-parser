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
from ..parser.events import BaseEvent
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
            elif self.navigation.current_view == ViewMode.SEARCH:
                return self._handle_search()
            elif self.navigation.current_view == ViewMode.EXPORT:
                return self._handle_export()
            elif self.navigation.current_view == ViewMode.TIMELINE:
                return self._handle_timeline()
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
        if self.enhanced_data:
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
                        return (
                            m_plus_run.overall_characters
                            if hasattr(m_plus_run, "overall_characters")
                            else m_plus_run.characters if hasattr(m_plus_run, "characters") else {}
                        )

            # For dungeon bosses within M+, find from segments
            elif fight.fight_type == FightType.DUNGEON_BOSS:
                for m_plus_run in mythic_plus_runs:
                    # Check if this boss is part of an M+ run
                    for segment in getattr(m_plus_run, "segments", []):
                        if (
                            hasattr(segment, "segment_name")
                            and segment.segment_name == fight.encounter_name
                            and abs((segment.start_time - fight.start_time).total_seconds())
                            < time_tolerance
                        ):
                            return getattr(segment, "characters", {})

        # Enhanced fallback: create character streams from fight events and participants
        if fight.participants:
            characters = {}
            player_count = 0
            debug_participants = []

            # First pass: use the is_player flag
            for guid, participant in fight.participants.items():
                debug_participants.append(
                    f"{guid[:20]}...={participant.get('is_player', 'No flag')}"
                )
                if participant.get("is_player", False):
                    player_count += 1
                    characters[guid] = CharacterEventStream(
                        character_guid=guid, character_name=participant["name"] or "Unknown"
                    )

            # Fallback: if no players found via flag, detect by GUID pattern
            if player_count == 0:
                for guid, participant in fight.participants.items():
                    if guid and guid.startswith("Player-"):
                        player_count += 1
                        characters[guid] = CharacterEventStream(
                            character_guid=guid, character_name=participant["name"] or "Unknown"
                        )

            # Process fight events to populate metrics
            if characters and fight.events:
                self._populate_character_metrics_from_events(characters, fight)

            return characters if characters else None

        return None

    def _populate_character_metrics_from_events(
        self, characters: Dict[str, CharacterEventStream], fight: Fight
    ):
        """
        Populate character metrics by parsing fight events.

        Args:
            characters: Dictionary of character streams to populate
            fight: Fight object containing events and duration info
        """
        from src.parser.events import DamageEvent, HealEvent
        from src.models.combat_periods import CombatPeriodDetector

        events = fight.events
        duration = fight.duration or 0

        # Detect combat periods first
        detector = CombatPeriodDetector(gap_threshold=5.0)
        combat_periods = detector.detect_periods(events)

        for event in events:
            # Track damage done (all damage event types)
            if self._is_damage_event(event) and event.source_guid in characters:
                damage_amount = self._get_total_damage(event)
                characters[event.source_guid].total_damage_done += damage_amount
                # Add to all_events for chronological tracking
                characters[event.source_guid].all_events.append(
                    (event.timestamp, "damage", damage_amount)
                )

            # Track healing done (all healing event types)
            elif self._is_heal_event(event) and event.source_guid in characters:
                heal_amount = self._get_effective_healing(event)
                characters[event.source_guid].total_healing_done += heal_amount
                characters[event.source_guid].all_events.append(
                    (event.timestamp, "heal", heal_amount)
                )

            # Track damage taken
            elif self._is_damage_event(event) and event.dest_guid in characters:
                damage_amount = self._get_total_damage(event)
                characters[event.dest_guid].total_damage_taken += damage_amount

            # Track deaths
            elif event.event_type == "UNIT_DIED" and event.dest_guid in characters:
                characters[event.dest_guid].death_count += 1
                characters[event.dest_guid].all_events.append((event.timestamp, "death", 0))

        # Calculate combat-aware activity percentages and metrics
        for character in characters.values():
            if duration > 0:
                # Sort events chronologically
                character.all_events.sort()
                # Use combat-aware activity calculation
                character.calculate_combat_metrics(combat_periods, duration)
            else:
                # No duration means no valid activity calculation
                character.activity_percentage = 0.0
                character.combat_time = 0.0
                character.time_alive = 0.0

    def _is_damage_event(self, event) -> bool:
        """Check if event represents damage."""
        if isinstance(event, DamageEvent):
            return True
        # Also check by event type for events that might not be typed as DamageEvent
        damage_types = {
            "SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "SWING_DAMAGE",
            "RANGE_DAMAGE", "ENVIRONMENTAL_DAMAGE"
        }
        return event.event_type in damage_types

    def _is_heal_event(self, event) -> bool:
        """Check if event represents healing."""
        if isinstance(event, HealEvent):
            return True
        # Also check by event type for events that might not be typed as HealEvent
        heal_types = {"SPELL_HEAL", "SPELL_PERIODIC_HEAL"}
        return event.event_type in heal_types

    def _get_total_damage(self, event) -> int:
        """Get total damage including absorbed amounts."""
        damage = 0
        if hasattr(event, 'amount') and event.amount:
            damage += event.amount
        if hasattr(event, 'absorbed') and event.absorbed:
            damage += event.absorbed
        return damage

    def _get_effective_healing(self, event) -> int:
        """Get effective healing amount."""
        if hasattr(event, 'effective_healing'):
            return event.effective_healing
        elif hasattr(event, 'amount') and hasattr(event, 'overhealing'):
            # Calculate effective healing if we have both values
            return event.amount - (event.overhealing or 0)
        elif hasattr(event, 'amount'):
            # Fallback to raw amount if no overhealing data
            return event.amount
        return 0

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

        # Create DPS rankings table using combat time for more accurate metrics
        dps_rankings = self.metrics_calculator.get_dps_rankings(
            characters, fight.duration, use_combat_time=True
        )

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

        # Create HPS rankings table using combat time for more accurate metrics
        hps_rankings = self.metrics_calculator.get_hps_rankings(
            characters, fight.duration, use_combat_time=True
        )

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

    def _generate_detailed_timeline(
        self, fight: Fight, characters: Dict[str, CharacterEventStream]
    ) -> List[Dict[str, Any]]:
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
                "start": start_time,
                "end": end_time,
                "damage": {},
                "healing": {},
                "deaths": [],
                "major_events": [],
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
                    interval_data["damage"][char.character_name] = char_damage
                if char_healing > 0:
                    interval_data["healing"][char.character_name] = char_healing

                # Check for deaths in this interval
                for death in char.deaths:
                    death_time = (death.datetime - fight.start_time).total_seconds()
                    if start_time <= death_time < end_time:
                        interval_data["deaths"].append(
                            {"player": char.character_name, "time": death_time}
                        )

            timeline.append(interval_data)

        return timeline

    def _display_timeline_segments(
        self,
        fight: Fight,
        timeline_data: List[Dict[str, Any]],
        characters: Dict[str, CharacterEventStream],
    ):
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

            table = Table(
                title=f"Detailed Timeline - {fight.encounter_name or 'Unknown'} (Page {current_page + 1}/{max_pages})"
            )
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
                top_dps = sorted(interval["damage"].items(), key=lambda x: x[1], reverse=True)[:3]
                dps_text = ", ".join([f"{name}: {dmg:,.0f}" for name, dmg in top_dps])

                # Top HPS in this interval
                top_hps = sorted(interval["healing"].items(), key=lambda x: x[1], reverse=True)[:3]
                hps_text = ", ".join([f"{name}: {heal:,.0f}" for name, heal in top_hps])

                # Events in this interval
                events = []
                for death in interval["deaths"]:
                    events.append(f"💀 {death['player']} died")
                for event in interval["major_events"]:
                    events.append(event)

                events_text = ", ".join(events) if events else "No major events"

                table.add_row(
                    time_range, dps_text or "No damage", hps_text or "No healing", events_text
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

    def _handle_search(self) -> bool:
        """Handle search functionality."""
        self.console.clear()

        # Get search query from user
        self.console.print("[bold cyan]Search Combat Log Data[/bold cyan]\n")
        self.console.print("Search for players, spells, encounters, or events.")
        self.console.print("Examples: 'Fireball', 'John', 'Mythic+', 'SPELL_DAMAGE'\n")

        query = Prompt.ask("Enter search term (or 'back' to return)", default="")

        if query.lower() in ["back", "b", ""]:
            self.navigation.go_back()
            return True

        if len(query) < 2:
            self.console.print("[red]Search term must be at least 2 characters[/red]")
            self._wait_for_key()
            return True

        # Perform search
        results = self._perform_search(query)

        if not results:
            self.console.print(f"[yellow]No results found for '{query}'[/yellow]")
            self._wait_for_key()
            return True

        # Display search results
        self._display_search_results(query, results)
        return True

    def _perform_search(self, query: str) -> Dict[str, List[Dict[str, Any]]]:
        """Perform search across all data."""
        query_lower = query.lower()
        results = {"players": [], "spells": [], "encounters": [], "events": []}

        # Search players
        all_players = set()
        for fight in self.fights:
            characters = self._get_encounter_characters(fight)
            if characters:
                for char in characters.values():
                    if char.character_name and query_lower in char.character_name.lower():
                        all_players.add(char.character_name)

        for player in all_players:
            results["players"].append(
                {"name": player, "type": "Player", "description": f"Player: {player}"}
            )

        # Search encounters
        for fight in self.fights:
            if fight.encounter_name and query_lower in fight.encounter_name.lower():
                results["encounters"].append(
                    {
                        "name": fight.encounter_name,
                        "type": fight.fight_type.value.title(),
                        "description": f"{fight.fight_type.value.title()}: {fight.encounter_name}",
                        "fight": fight,
                    }
                )

        # Search spells/abilities
        spell_matches = set()
        for fight in self.fights:
            characters = self._get_encounter_characters(fight)
            if not characters:
                continue

            for char in characters.values():
                # Search damage spells
                for damage_event in char.damage_done:
                    if hasattr(damage_event, "spell_name") and damage_event.spell_name:
                        if query_lower in damage_event.spell_name.lower():
                            spell_matches.add((damage_event.spell_name, "Damage Spell"))

                # Search healing spells
                for heal_event in char.healing_done:
                    if hasattr(heal_event, "spell_name") and heal_event.spell_name:
                        if query_lower in heal_event.spell_name.lower():
                            spell_matches.add((heal_event.spell_name, "Healing Spell"))

                # Search buffs
                for buff in char.buffs_gained:
                    if hasattr(buff, "spell_name") and buff.spell_name:
                        if query_lower in buff.spell_name.lower():
                            spell_matches.add((buff.spell_name, "Buff/Aura"))

        for spell_name, spell_type in spell_matches:
            results["spells"].append(
                {
                    "name": spell_name,
                    "type": spell_type,
                    "description": f"{spell_type}: {spell_name}",
                }
            )

        # Search event types
        if query_lower in "damage":
            results["events"].append(
                {
                    "name": "Damage Events",
                    "type": "Event Type",
                    "description": "All damage-dealing events",
                }
            )
        if query_lower in "healing":
            results["events"].append(
                {
                    "name": "Healing Events",
                    "type": "Event Type",
                    "description": "All healing events",
                }
            )
        if query_lower in "death":
            results["events"].append(
                {
                    "name": "Death Events",
                    "type": "Event Type",
                    "description": "All player death events",
                }
            )

        return results

    def _display_search_results(self, query: str, results: Dict[str, List[Dict[str, Any]]]):
        """Display search results with navigation."""
        from rich.table import Table

        self.console.clear()
        self.console.print(f"[bold cyan]Search Results for '{query}'[/bold cyan]\n")

        total_results = sum(len(category) for category in results.values())
        if total_results == 0:
            self.console.print("[yellow]No results found[/yellow]")
            self._wait_for_key()
            return

        # Create combined results table
        table = Table(title=f"Found {total_results} results")
        table.add_column("#", width=4)
        table.add_column("Category", width=15)
        table.add_column("Type", width=15)
        table.add_column("Name", width=30)
        table.add_column("Description", width=40)

        all_results = []
        result_index = 1

        # Add all results to the table
        for category_name, category_results in results.items():
            for result in category_results:
                category_color = {
                    "players": "green",
                    "spells": "blue",
                    "encounters": "yellow",
                    "events": "magenta",
                }.get(category_name, "white")

                table.add_row(
                    str(result_index),
                    f"[{category_color}]{category_name.title()}[/{category_color}]",
                    result["type"],
                    result["name"],
                    result["description"],
                )

                all_results.append(result)
                result_index += 1

        self.console.print(table)

        # Show result summary by category
        self.console.print("\n[bold]Results by Category:[/bold]")
        for category, items in results.items():
            if items:
                self.console.print(f"  {category.title()}: {len(items)}")

        # Navigation options
        choices = ["s", "b", "q"]
        nav_text = "[S]earch again | [B]ack | [Q]uit"

        if total_results <= 20:
            choices.extend([str(i) for i in range(1, min(21, total_results + 1))])
            nav_text = "Enter number to view details | " + nav_text

        self.console.print(f"\n{nav_text}")
        choice = Prompt.ask("Select option", choices=choices, default="b")

        if choice.lower() == "q":
            return False
        elif choice.lower() == "b":
            self.navigation.go_back()
            return True
        elif choice.lower() == "s":
            return self._handle_search()
        elif choice.isdigit():
            # Show details for selected result
            index = int(choice) - 1
            if 0 <= index < len(all_results):
                self._show_search_result_details(all_results[index])

        return True

    def _show_search_result_details(self, result: Dict[str, Any]):
        """Show detailed information about a search result."""
        self.console.clear()
        self.console.print(f"[bold cyan]Details: {result['name']}[/bold cyan]\n")

        if "fight" in result:
            # Encounter details
            fight = result["fight"]
            characters = self._get_encounter_characters(fight)
            if characters:
                panel = self.display_builder.create_encounter_detail(fight, characters)
                self.console.print(panel)
            else:
                self.console.print(
                    f"[yellow]No detailed data available for {result['name']}[/yellow]"
                )
        else:
            # Generic result details
            self.console.print(f"Name: {result['name']}")
            self.console.print(f"Type: {result['type']}")
            self.console.print(f"Description: {result['description']}")

            # Show usage statistics if it's a spell
            if result["type"] in ["Damage Spell", "Healing Spell", "Buff/Aura"]:
                usage_stats = self._get_spell_usage_stats(result["name"])
                if usage_stats:
                    self.console.print("\n[bold]Usage Statistics:[/bold]")
                    for stat, value in usage_stats.items():
                        self.console.print(f"  {stat}: {value}")

        self.console.print("\n[dim]Press any key to return to search results...[/dim]")
        self._wait_for_key()

    def _get_spell_usage_stats(self, spell_name: str) -> Dict[str, Any]:
        """Get usage statistics for a specific spell."""
        stats = {
            "Total Uses": 0,
            "Total Damage": 0,
            "Total Healing": 0,
            "Users": set(),
            "Encounters Used": set(),
        }

        for fight in self.fights:
            characters = self._get_encounter_characters(fight)
            if not characters:
                continue

            encounter_used = False
            for char in characters.values():
                # Check damage events
                for damage_event in char.damage_done:
                    if (
                        hasattr(damage_event, "spell_name")
                        and damage_event.spell_name == spell_name
                    ):
                        stats["Total Uses"] += 1
                        stats["Total Damage"] += damage_event.amount
                        stats["Users"].add(char.character_name)
                        encounter_used = True

                # Check healing events
                for heal_event in char.healing_done:
                    if hasattr(heal_event, "spell_name") and heal_event.spell_name == spell_name:
                        stats["Total Uses"] += 1
                        stats["Total Healing"] += heal_event.amount
                        stats["Users"].add(char.character_name)
                        encounter_used = True

                # Check buff events
                for buff in char.buffs_gained:
                    if hasattr(buff, "spell_name") and buff.spell_name == spell_name:
                        stats["Total Uses"] += 1
                        stats["Users"].add(char.character_name)
                        encounter_used = True

            if encounter_used:
                stats["Encounters Used"].add(fight.encounter_name or "Unknown")

        # Format for display
        formatted_stats = {
            "Total Uses": f"{stats['Total Uses']:,}",
            "Unique Users": len(stats["Users"]),
            "Encounters": len(stats["Encounters Used"]),
        }

        if stats["Total Damage"] > 0:
            formatted_stats["Total Damage"] = f"{stats['Total Damage']:,}"
        if stats["Total Healing"] > 0:
            formatted_stats["Total Healing"] = f"{stats['Total Healing']:,}"

        return formatted_stats if stats["Total Uses"] > 0 else {}

    def _handle_export(self) -> bool:
        """Handle export functionality."""
        self.console.clear()
        self.console.print("[bold cyan]Export Combat Log Analysis[/bold cyan]\n")

        # Export options
        from rich.table import Table

        table = Table(title="Export Formats")
        table.add_column("Option", width=8)
        table.add_column("Format", width=15)
        table.add_column("Description", width=50)

        table.add_row("1", "JSON", "Complete data structure for external analysis")
        table.add_row("2", "CSV", "Tabular data for spreadsheet applications")
        table.add_row("3", "HTML", "Interactive web report with formatting")
        table.add_row("4", "Markdown", "Documentation-friendly summary report")
        table.add_row("5", "Summary", "Text-based encounter summary")

        self.console.print(table)

        choice = Prompt.ask(
            "Select export format", choices=["1", "2", "3", "4", "5", "b", "q"], default="b"
        )

        if choice.lower() == "q":
            return False
        elif choice.lower() == "b":
            self.navigation.go_back()
            return True
        else:
            format_map = {"1": "json", "2": "csv", "3": "html", "4": "markdown", "5": "summary"}

            if choice in format_map:
                self._export_data(format_map[choice])

        return True

    def _export_data(self, format_type: str):
        """Export data in the specified format."""
        import json
        import csv
        from pathlib import Path
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"combat_log_analysis_{timestamp}"

        try:
            if format_type == "json":
                filename = f"{base_filename}.json"
                export_data = {
                    "encounters": [],
                    "players": {},
                    "summary": {
                        "total_encounters": len(self.fights),
                        "successful_encounters": sum(1 for f in self.fights if f.success),
                        "export_timestamp": timestamp,
                    },
                }

                # Add encounter data
                for fight in self.fights:
                    encounter_data = {
                        "name": fight.encounter_name,
                        "type": fight.fight_type.value,
                        "success": fight.success,
                        "duration": fight.duration,
                        "player_count": fight.get_player_count(),
                    }

                    characters = self._get_encounter_characters(fight)
                    if characters:
                        encounter_data["characters"] = {}
                        for guid, char in characters.items():
                            encounter_data["characters"][char.character_name] = {
                                "total_damage": char.total_damage_done,
                                "total_healing": char.total_healing_done,
                                "deaths": char.death_count,
                            }

                    export_data["encounters"].append(encounter_data)

                with open(filename, "w") as f:
                    json.dump(export_data, f, indent=2, default=str)

            elif format_type == "csv":
                filename = f"{base_filename}.csv"
                with open(filename, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Encounter", "Type", "Success", "Duration", "Players"])

                    for fight in self.fights:
                        writer.writerow(
                            [
                                fight.encounter_name or "Unknown",
                                fight.fight_type.value,
                                "Success" if fight.success else "Wipe",
                                fight.get_duration_str(),
                                fight.get_player_count(),
                            ]
                        )

            elif format_type == "html":
                filename = f"{base_filename}.html"
                html_content = self._generate_html_report()
                with open(filename, "w") as f:
                    f.write(html_content)

            elif format_type == "markdown":
                filename = f"{base_filename}.md"
                md_content = self._generate_markdown_report()
                with open(filename, "w") as f:
                    f.write(md_content)

            elif format_type == "summary":
                filename = f"{base_filename}.txt"
                summary_content = self._generate_text_summary()
                with open(filename, "w") as f:
                    f.write(summary_content)

            self.console.print(f"[green]✓ Data exported to: {filename}[/green]")

        except Exception as e:
            self.console.print(f"[red]Export failed: {str(e)}[/red]")

        self.console.print("\n[dim]Press any key to continue...[/dim]")
        self._wait_for_key()

    def _generate_html_report(self) -> str:
        """Generate HTML report."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Combat Log Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .success {{ color: green; }}
        .wipe {{ color: red; }}
    </style>
</head>
<body>
    <h1>Combat Log Analysis Report</h1>
    <h2>Summary</h2>
    <p>Total Encounters: {len(self.fights)}</p>
    <p>Successful: {sum(1 for f in self.fights if f.success)}</p>
    <p>Wipes: {sum(1 for f in self.fights if not f.success)}</p>

    <h2>Encounter Details</h2>
    <table>
        <tr><th>Encounter</th><th>Type</th><th>Result</th><th>Duration</th><th>Players</th></tr>
"""

        for fight in self.fights:
            result_class = "success" if fight.success else "wipe"
            result_text = "Success" if fight.success else "Wipe"

            html += f"""
        <tr>
            <td>{fight.encounter_name or 'Unknown'}</td>
            <td>{fight.fight_type.value}</td>
            <td class="{result_class}">{result_text}</td>
            <td>{fight.get_duration_str()}</td>
            <td>{fight.get_player_count()}</td>
        </tr>"""

        html += """
    </table>
</body>
</html>"""
        return html

    def _generate_markdown_report(self) -> str:
        """Generate Markdown report."""
        md = f"""# Combat Log Analysis Report

## Summary
- **Total Encounters**: {len(self.fights)}
- **Successful**: {sum(1 for f in self.fights if f.success)}
- **Wipes**: {sum(1 for f in self.fights if not f.success)}

## Encounter Details

| Encounter | Type | Result | Duration | Players |
|-----------|------|--------|----------|----------|
"""

        for fight in self.fights:
            result = "✅ Success" if fight.success else "❌ Wipe"
            md += f"| {fight.encounter_name or 'Unknown'} | {fight.fight_type.value} | {result} | {fight.get_duration_str()} | {fight.get_player_count()} |\n"

        return md

    def _generate_text_summary(self) -> str:
        """Generate text summary."""
        summary = f"""COMBAT LOG ANALYSIS SUMMARY
{'=' * 40}

Total Encounters: {len(self.fights)}
Successful: {sum(1 for f in self.fights if f.success)}
Wipes: {sum(1 for f in self.fights if not f.success)}

ENCOUNTER BREAKDOWN:
{'-' * 20}
"""

        for fight in self.fights:
            result = "SUCCESS" if fight.success else "WIPE"
            summary += f"{fight.encounter_name or 'Unknown'} ({fight.fight_type.value}) - {result} - {fight.get_duration_str()}\n"

        return summary

    def _handle_timeline(self) -> bool:
        """Interactive timeline viewer with combat period awareness."""
        from src.analyzer.timeline import TimelineBuilder, TimelineFilter, TimelineAnalyzer
        from src.models.combat_periods import CombatPeriodDetector, EventCategory
        from rich.table import Table

        self.console.clear()

        # Check if we have selected a fight
        if not self.navigation.selected_fight:
            self.console.print("[yellow]No fight selected. Please select a fight first.[/yellow]")
            self.console.print("\nAvailable options:")
            self.console.print("1. [B]ack to main menu")

            while True:
                key = self.console.input("Choice: ").strip().upper()
                if key == "B":
                    self.navigation.go_back()
                    return True
                else:
                    self.console.print("[red]Invalid choice. Try again.[/red]")

        fight = self.navigation.selected_fight

        # Initialize timeline state if needed
        if not hasattr(self, "timeline_state"):
            self.timeline_state = {
                "window_start": 0,
                "window_size": 30,  # 30 second window
                "show_combat_only": True,
                "category_filter": None,
                "importance_threshold": 3,
                "current_page": 0,
            }

        # Build timeline
        detector = CombatPeriodDetector(gap_threshold=5.0)
        combat_periods = detector.detect_periods(fight.events)

        builder = TimelineBuilder()
        timeline_events = builder.build(fight, combat_periods)

        # Apply filters
        filtered_events = timeline_events

        if self.timeline_state["show_combat_only"]:
            filtered_events = TimelineFilter.filter_by_combat(filtered_events, combat_only=True)

        if self.timeline_state["category_filter"]:
            filtered_events = TimelineFilter.filter_by_category(
                filtered_events, self.timeline_state["category_filter"]
            )

        filtered_events = TimelineFilter.filter_by_importance(
            filtered_events, self.timeline_state["importance_threshold"]
        )

        # Display timeline header
        self.console.print(
            f"[bold cyan]Timeline: {fight.encounter_name or 'Unknown Encounter'}[/bold cyan]"
        )

        # Combat period summary
        total_combat_time = sum(p.duration for p in combat_periods)
        combat_percentage = (total_combat_time / fight.duration * 100) if fight.duration else 0

        self.console.print(
            f"Duration: {fight.duration:.1f}s | Combat: {total_combat_time:.1f}s ({combat_percentage:.1f}%)"
        )
        self.console.print(
            f"Combat Periods: {len(combat_periods)} | Events: {len(filtered_events)}\n"
        )

        # Combat periods visualization
        if combat_periods:
            self.console.print("[bold green]Combat Periods:[/bold green]")
            for i, period in enumerate(combat_periods):
                start_relative = (period.start_time - fight.start_time).total_seconds()
                end_relative = (period.end_time - fight.start_time).total_seconds()
                self.console.print(
                    f"  {i+1}. {start_relative:.1f}s - {end_relative:.1f}s "
                    f"({period.duration:.1f}s, {period.event_count} events)"
                )
            self.console.print()

        # Timeline events (paginated)
        events_per_page = 15
        total_pages = (len(filtered_events) + events_per_page - 1) // events_per_page

        if total_pages > 0:
            start_idx = self.timeline_state["current_page"] * events_per_page
            end_idx = min(start_idx + events_per_page, len(filtered_events))
            page_events = filtered_events[start_idx:end_idx]

            # Events table
            events_table = Table(
                title=f"Timeline Events (Page {self.timeline_state['current_page'] + 1} of {total_pages})"
            )
            events_table.add_column("Time", width=8)
            events_table.add_column("Combat", width=8)
            events_table.add_column("Importance", width=10)
            events_table.add_column("Category", width=12)
            events_table.add_column("Description", width=50)

            for event in page_events:
                time_str = f"{event.relative_time:.1f}s"
                combat_str = "Yes" if event.is_combat else "No"
                importance_str = "★" * event.importance
                category_str = event.category.value.replace("_", " ").title()

                # Truncate long descriptions
                description = event.description
                if len(description) > 45:
                    description = description[:42] + "..."

                events_table.add_row(
                    time_str, combat_str, importance_str, category_str, description
                )

            self.console.print(events_table)
        else:
            self.console.print("[yellow]No events match current filters.[/yellow]")

        # Display current filters
        self.console.print(f"\n[bold]Current Filters:[/bold]")
        self.console.print(f"Combat Only: {self.timeline_state['show_combat_only']}")
        self.console.print(
            f"Category: {self.timeline_state['category_filter'].value if self.timeline_state['category_filter'] else 'All'}"
        )
        self.console.print(f"Min Importance: {self.timeline_state['importance_threshold']}")

        # Navigation options
        self.console.print("\n[bold]Navigation:[/bold]")

        options = []
        if self.timeline_state["current_page"] > 0:
            options.append("[P]revious page")
        if self.timeline_state["current_page"] < total_pages - 1:
            options.append("[N]ext page")

        options.extend(
            [
                "[C]ombat filter toggle",
                "[I]mportance threshold",
                "[A]nalyze gaps",
                "[K]ey moments",
                "[B]ack",
            ]
        )

        for option in options:
            self.console.print(f"  {option}")

        # Handle input
        while True:
            choice = self.console.input("\nChoice: ").strip().upper()

            if choice == "P" and self.timeline_state["current_page"] > 0:
                self.timeline_state["current_page"] -= 1
                return True
            elif choice == "N" and self.timeline_state["current_page"] < total_pages - 1:
                self.timeline_state["current_page"] += 1
                return True
            elif choice == "C":
                self.timeline_state["show_combat_only"] = not self.timeline_state[
                    "show_combat_only"
                ]
                self.timeline_state["current_page"] = 0  # Reset to first page
                return True
            elif choice == "I":
                self.console.print("Set minimum importance (1-5):")
                try:
                    threshold = int(self.console.input("Threshold: "))
                    if 1 <= threshold <= 5:
                        self.timeline_state["importance_threshold"] = threshold
                        self.timeline_state["current_page"] = 0
                        return True
                    else:
                        self.console.print("[red]Invalid threshold. Must be 1-5.[/red]")
                except ValueError:
                    self.console.print("[red]Invalid input. Must be a number.[/red]")
            elif choice == "A":
                # Analyze combat gaps
                analyzer = TimelineAnalyzer()
                gap_analysis = analyzer.analyze_combat_gaps(timeline_events, combat_periods)

                self.console.clear()
                self.console.print("[bold cyan]Combat Gap Analysis[/bold cyan]\n")

                if gap_analysis["gap_count"] > 0:
                    self.console.print(f"Total Gaps: {gap_analysis['gap_count']}")
                    self.console.print(f"Total Gap Time: {gap_analysis['total_gap_time']:.1f}s")
                    self.console.print(
                        f"Average Gap Duration: {gap_analysis['avg_gap_duration']:.1f}s\n"
                    )

                    gaps_table = Table(title="Combat Gaps")
                    gaps_table.add_column("Gap #", width=6)
                    gaps_table.add_column("Start", width=10)
                    gaps_table.add_column("End", width=10)
                    gaps_table.add_column("Duration", width=10)
                    gaps_table.add_column("Events", width=8)

                    for i, gap in enumerate(gap_analysis["gaps"][:10]):  # Show first 10
                        start_time = (gap["start_time"] - fight.start_time).total_seconds()
                        end_time = (gap["end_time"] - fight.start_time).total_seconds()

                        gaps_table.add_row(
                            str(i + 1),
                            f"{start_time:.1f}s",
                            f"{end_time:.1f}s",
                            f"{gap['duration']:.1f}s",
                            str(gap["events_during_gap"]),
                        )

                    self.console.print(gaps_table)
                else:
                    self.console.print("[yellow]No combat gaps found.[/yellow]")

                self._wait_for_key()
                return True
            elif choice == "K":
                # Show key moments
                analyzer = TimelineAnalyzer()
                key_moments = analyzer.find_key_moments(timeline_events)

                self.console.clear()
                self.console.print("[bold cyan]Key Moments[/bold cyan]\n")

                if key_moments:
                    moments_table = Table(title="Most Important Events")
                    moments_table.add_column("Time", width=8)
                    moments_table.add_column("Importance", width=10)
                    moments_table.add_column("Description", width=60)

                    for moment in key_moments[:15]:  # Show top 15
                        time_str = f"{moment.relative_time:.1f}s"
                        importance_str = "★" * moment.importance

                        moments_table.add_row(time_str, importance_str, moment.description)

                    self.console.print(moments_table)
                else:
                    self.console.print("[yellow]No key moments found.[/yellow]")

                self._wait_for_key()
                return True
            elif choice == "B":
                self.navigation.go_back()
                return True
            else:
                self.console.print("[red]Invalid choice.[/red]")

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
