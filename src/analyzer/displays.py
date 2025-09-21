"""
Display component builders for the interactive analyzer.
"""

from typing import List, Dict, Any, Optional
from rich.table import Table
from rich.panel import Panel
from rich.console import Group
from rich.text import Text
from rich.layout import Layout

from ..segmentation.encounters import Fight, FightType
from ..models.character_events import CharacterEventStream


class DisplayBuilder:
    """Builds rich display components for the analyzer."""

    @staticmethod
    def create_main_menu() -> Panel:
        """Create the main menu display."""
        menu_text = Text()
        menu_text.append("═══ COMBAT LOG ANALYZER ═══\n\n", style="bold cyan")
        menu_text.append("[1] Overview - Summary of all encounters\n", style="white")
        menu_text.append("[2] Encounters - Browse individual encounters\n", style="white")
        menu_text.append("[3] Players - Player performance rankings\n", style="white")
        menu_text.append("[4] Timeline - Chronological event viewer\n", style="white")
        menu_text.append("[5] Search - Find specific events/abilities\n", style="white")
        menu_text.append("[6] Export - Save analysis to file\n", style="white")
        menu_text.append("[Q] Quit\n\n", style="red")
        menu_text.append("Select option: ", style="yellow")

        return Panel(menu_text, border_style="cyan")

    @staticmethod
    def create_overview(fights: List[Fight]) -> Panel:
        """Create overview display of all encounters."""
        if not fights:
            return Panel("No encounters found in the log file.", style="red")

        # Count different types
        raid_bosses = sum(1 for f in fights if f.fight_type == FightType.RAID_BOSS)
        mythic_plus = sum(1 for f in fights if f.fight_type == FightType.MYTHIC_PLUS)
        dungeon_bosses = sum(1 for f in fights if f.fight_type == FightType.DUNGEON_BOSS)
        trash = sum(1 for f in fights if f.fight_type == FightType.TRASH)

        successful = sum(1 for f in fights if f.success is True)
        wipes = sum(1 for f in fights if f.success is False)

        overview_text = Text()
        overview_text.append("═══ COMBAT LOG OVERVIEW ═══\n\n", style="bold cyan")
        overview_text.append(f"Total Encounters: {len(fights)}\n\n", style="white")

        overview_text.append("Encounter Types:\n", style="bold")
        overview_text.append(f"  • Raid Bosses: {raid_bosses}\n", style="green")
        overview_text.append(f"  • Mythic+ Dungeons: {mythic_plus}\n", style="blue")
        overview_text.append(f"  • Dungeon Bosses: {dungeon_bosses}\n", style="yellow")
        overview_text.append(f"  • Trash Fights: {trash}\n\n", style="dim")

        overview_text.append("Results:\n", style="bold")
        overview_text.append(f"  • Successful: {successful}\n", style="green")
        overview_text.append(f"  • Wipes: {wipes}\n\n", style="red")

        overview_text.append("Press any key to return to menu...", style="dim")

        return Panel(overview_text, title="Overview", border_style="cyan")

    @staticmethod
    def create_encounters_list(
        fights: List[Fight], start_index: int, end_index: int, current_page: int, total_pages: int
    ) -> Panel:
        """Create encounters list display."""
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", width=3)
        table.add_column("Type", width=12)
        table.add_column("Name", width=30)
        table.add_column("Duration", width=8)
        table.add_column("Players", width=7)
        table.add_column("Result", width=10)

        for i in range(start_index, end_index):
            if i >= len(fights):
                break

            fight = fights[i]

            # Format type with color
            type_color = {
                FightType.RAID_BOSS: "green",
                FightType.MYTHIC_PLUS: "blue",
                FightType.DUNGEON_BOSS: "yellow",
                FightType.TRASH: "dim",
            }.get(fight.fight_type, "white")

            # Format result with color
            if fight.success is True:
                result = "[green]Success[/green]"
            elif fight.success is False:
                result = "[red]Wipe[/red]"
            else:
                result = "[dim]-[/dim]"

            # Truncate long names
            name = fight.encounter_name or "Unknown"
            if len(name) > 28:
                name = name[:25] + "..."

            table.add_row(
                str(i + 1),
                f"[{type_color}]{fight.fight_type.value}[/{type_color}]",
                name,
                fight.get_duration_str(),
                str(fight.get_player_count()),
                result,
            )

        title = f"Encounters (Page {current_page + 1}/{total_pages + 1})"
        footer = "Enter number to view details | [N]ext [P]rev [F]ilter [B]ack"

        content = Group(table, Text(footer, style="dim"))
        return Panel(content, title=title, border_style="cyan")

    @staticmethod
    def create_encounter_detail(
        fight: Fight, characters: Optional[Dict[str, CharacterEventStream]] = None
    ) -> Panel:
        """Create detailed encounter view."""
        detail_text = Text()

        # Header
        detail_text.append(f"═══ {fight.encounter_name or 'Unknown'} ═══\n", style="bold cyan")
        detail_text.append(f"Type: {fight.fight_type.value.title()}\n", style="white")
        detail_text.append(f"Duration: {fight.get_duration_str()}\n", style="white")

        if fight.success is True:
            detail_text.append("Result: Success\n", style="green")
        elif fight.success is False:
            detail_text.append("Result: Wipe\n", style="red")
        else:
            detail_text.append("Result: Unknown\n", style="dim")

        detail_text.append(f"Players: {fight.get_player_count()}\n\n", style="white")

        # Basic fight info
        if fight.difficulty:
            detail_text.append(f"Difficulty: {fight.difficulty}\n", style="white")

        if fight.keystone_level:
            detail_text.append(f"Keystone Level: +{fight.keystone_level}\n", style="blue")

        # Character data if available
        if characters:
            detail_text.append("\n┌─ PLAYER PERFORMANCE ─┐\n", style="bold")

            # Sort by damage done
            sorted_chars = sorted(
                characters.values(), key=lambda c: c.total_damage_done, reverse=True
            )

            detail_text.append("Top DPS:\n", style="bold yellow")
            for i, char in enumerate(sorted_chars[:5]):
                if char.total_damage_done > 0:
                    dps = char.get_dps(fight.duration) if fight.duration else 0
                    detail_text.append(
                        f"  {i+1}. {char.character_name} - {dps:,.0f} DPS\n", style="white"
                    )

            # Sort by healing done
            healing_chars = [c for c in characters.values() if c.total_healing_done > 0]
            if healing_chars:
                healing_chars.sort(key=lambda c: c.total_healing_done, reverse=True)
                detail_text.append("\nTop HPS:\n", style="bold green")
                for i, char in enumerate(healing_chars[:3]):
                    hps = char.get_hps(fight.duration) if fight.duration else 0
                    detail_text.append(
                        f"  {i+1}. {char.character_name} - {hps:,.0f} HPS\n", style="white"
                    )

            # Deaths
            deaths = [c for c in characters.values() if c.death_count > 0]
            if deaths:
                detail_text.append("\nDeaths:\n", style="bold red")
                for char in deaths:
                    detail_text.append(
                        f"  • {char.character_name} ({char.death_count}x)\n", style="red"
                    )
        else:
            detail_text.append("\n[dim]Detailed character data not available[/dim]\n", style="dim")

        detail_text.append(
            "\n[D]PS Details | [H]PS Details | [E]vents | [T]imeline | [B]ack", style="dim"
        )

        return Panel(detail_text, title="Encounter Details", border_style="cyan")

    @staticmethod
    def create_error_panel(message: str) -> Panel:
        """Create an error display panel."""
        return Panel(f"[red]Error: {message}[/red]", border_style="red")

    @staticmethod
    def create_help_panel() -> Panel:
        """Create help text panel."""
        help_text = Text()
        help_text.append("═══ KEYBOARD SHORTCUTS ═══\n\n", style="bold cyan")
        help_text.append("Navigation:\n", style="bold")
        help_text.append("  Q - Quit\n", style="white")
        help_text.append("  B - Back\n", style="white")
        help_text.append("  H - Help\n\n", style="white")

        help_text.append("Lists:\n", style="bold")
        help_text.append("  N - Next page\n", style="white")
        help_text.append("  P - Previous page\n", style="white")
        help_text.append("  F - Filter\n", style="white")
        help_text.append("  1-9 - Select item\n\n", style="white")

        help_text.append("Press any key to continue...", style="dim")

        return Panel(help_text, title="Help", border_style="yellow")

    @staticmethod
    def create_filter_panel(current_filters: Dict[str, Any]) -> Panel:
        """Create filter options panel."""
        filter_text = Text()
        filter_text.append("═══ FILTER OPTIONS ═══\n\n", style="bold cyan")

        filter_text.append("Filter by Type:\n", style="bold")
        filter_text.append("  [R] Raid Bosses\n", style="green")
        filter_text.append("  [M] Mythic+ Dungeons\n", style="blue")
        filter_text.append("  [D] Dungeon Bosses\n", style="yellow")
        filter_text.append("  [T] Trash Fights\n", style="dim")
        filter_text.append("  [A] All Types\n\n", style="white")

        filter_text.append("Filter by Result:\n", style="bold")
        filter_text.append("  [S] Successful only\n", style="green")
        filter_text.append("  [W] Wipes only\n", style="red")
        filter_text.append("  [E] All Results\n\n", style="white")

        # Show current filters
        if current_filters:
            filter_text.append("Current Filters:\n", style="bold yellow")
            for key, value in current_filters.items():
                if value is not None:
                    filter_text.append(f"  {key}: {value}\n", style="yellow")

        filter_text.append("\nPress filter key or [B]ack...", style="dim")

        return Panel(filter_text, title="Filters", border_style="yellow")
