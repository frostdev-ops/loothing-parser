"""
Navigation state management for interactive analyzer.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..segmentation.encounters import Fight


class ViewMode(Enum):
    """Different view modes in the analyzer."""

    MAIN_MENU = "main_menu"
    OVERVIEW = "overview"
    ENCOUNTERS = "encounters"
    ENCOUNTER_DETAIL = "encounter_detail"
    PLAYERS = "players"
    PLAYER_DETAIL = "player_detail"
    TIMELINE = "timeline"
    SEARCH = "search"
    EXPORT = "export"


@dataclass
class NavigationState:
    """Manages the current state of navigation in the analyzer."""

    # Current view
    current_view: ViewMode = ViewMode.MAIN_MENU
    previous_view: Optional[ViewMode] = None

    # Pagination
    current_page: int = 0
    items_per_page: int = 20

    # Selection state
    selected_encounter_index: int = 0
    selected_player_guid: Optional[str] = None

    # Filtering
    filter_type: Optional[str] = None  # 'raid', 'mythic_plus', 'trash'
    filter_success: Optional[bool] = None  # True/False/None for all

    # Search
    search_query: str = ""

    # Context data
    context_data: Optional[Any] = None

    def can_go_back(self) -> bool:
        """Check if we can navigate back."""
        return self.previous_view is not None

    def navigate_to(self, new_view: ViewMode, save_current: bool = True):
        """Navigate to a new view."""
        if save_current:
            self.previous_view = self.current_view
        self.current_view = new_view

    def go_back(self):
        """Navigate back to the previous view."""
        if self.can_go_back():
            self.current_view = self.previous_view
            self.previous_view = None

    def reset_pagination(self):
        """Reset pagination to first page."""
        self.current_page = 0

    def next_page(self, total_items: int) -> bool:
        """Go to next page if possible."""
        max_page = (total_items - 1) // self.items_per_page
        if self.current_page < max_page:
            self.current_page += 1
            return True
        return False

    def prev_page(self) -> bool:
        """Go to previous page if possible."""
        if self.current_page > 0:
            self.current_page -= 1
            return True
        return False

    def get_page_slice(self, total_items: int) -> tuple[int, int]:
        """Get the start and end indices for current page."""
        start = self.current_page * self.items_per_page
        end = min(start + self.items_per_page, total_items)
        return start, end
