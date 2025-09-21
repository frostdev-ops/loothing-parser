"""
Combat period detection for accurate activity and DPS calculations.

This module provides tools to detect when players are actively in combat
versus out-of-combat periods (travel time, breaks, etc.). It supports
configurable and adaptive gap thresholds, dynamic event type filtering,
and advanced features like period merging and validation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set
from enum import Enum
import statistics

from src.parser.events import BaseEvent, DamageEvent, HealEvent, AuraEvent


class EventCategory(Enum):
    """Categories for timeline filtering."""

    DEATH = "death"
    BOSS_MECHANIC = "boss_mechanic"
    MAJOR_COOLDOWN = "major_cooldown"
    DAMAGE = "damage"
    HEALING = "healing"
    BUFF_DEBUFF = "buff_debuff"
    CAST = "cast"
    INTERRUPT = "interrupt"
    DISPEL = "dispel"
    MOVEMENT = "movement"
    OTHER = "other"


@dataclass
class CombatPeriod:
    """Represents a period of active combat."""

    start_time: datetime
    end_time: datetime
    event_count: int = 0

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()

    def contains_time(self, timestamp: datetime) -> bool:
        """Check if a timestamp falls within this combat period."""
        return self.start_time <= timestamp <= self.end_time

    def __repr__(self) -> str:
        return (
            f"CombatPeriod({self.start_time.strftime('%H:%M:%S')} - "
            f"{self.end_time.strftime('%H:%M:%S')}, "
            f"{self.duration:.1f}s, {self.event_count} events)"
        )


class CombatPeriodDetector:
    """
    Detect combat periods from event streams using gap analysis.

    Combat periods are identified by clustering combat events. When there's
    a gap of more than `gap_threshold` seconds between combat events, it's
    considered the end of one combat period and potentially the start of another.
    """

    def __init__(
        self,
        gap_threshold: Optional[float] = None,
        adaptive_threshold: bool = False,
        min_gap_multiplier: float = 2.0,
        custom_combat_types: Optional[Set[str]] = None,
        custom_combat_suffixes: Optional[List[str]] = None,
    ):
        """
        Initialize detector.

        Args:
            gap_threshold: Fixed seconds of inactivity before considering combat ended.
                If None and adaptive_threshold=True, threshold is calculated from data.
            adaptive_threshold: If True, calculate threshold adaptively based on event gaps.
            min_gap_multiplier: Multiplier for adaptive threshold (e.g., 2.0 means 2x median gap).
            custom_combat_types: Set of exact event types to consider as combat events.
            custom_combat_suffixes: List of suffixes for event types to consider as combat.
        """
        self.fixed_gap_threshold = gap_threshold
        self.adaptive_threshold = adaptive_threshold
        self.min_gap_multiplier = min_gap_multiplier
        self.gap_threshold = gap_threshold or 5.0  # Default fallback

        # Default combat event types and suffixes
        self.combat_types = custom_combat_types or {
            "UNIT_DIED", "UNIT_DESTROYED", "SPELL_SUMMON", "SPELL_CREATE", "SPELL_INSTAKILL"
        }
        self.combat_suffixes = custom_combat_suffixes or [
            "_DAMAGE", "_HEAL", "_CAST_SUCCESS", "_CAST_START", "_INTERRUPT", "_DISPEL", "_STOLEN",
            "_AURA_APPLIED", "_AURA_REMOVED", "_AURA_REFRESH"
        ]

    def detect_periods(self, events: List[BaseEvent]) -> List[CombatPeriod]:
        """
        Detect combat periods from event clustering.

        Args:
            events: List of combat log events

        Returns:
            List of combat periods sorted by start time
        """
        # Filter to combat events only
        combat_events = [e for e in events if self._is_combat_event(e)]

        if not combat_events:
            return []

        # Sort events by timestamp
        combat_events.sort(key=lambda e: e.timestamp)

        # Calculate gaps between events
        gaps = []
        for i in range(1, len(combat_events)):
            gap = (combat_events[i].timestamp - combat_events[i-1].timestamp).total_seconds()
            gaps.append(gap)

        # Determine gap threshold
        if self.adaptive_threshold and gaps:
            median_gap = statistics.median(gaps)
            self.gap_threshold = max(median_gap * self.min_gap_multiplier, 1.0)  # Minimum 1 second
        elif self.fixed_gap_threshold is not None:
            self.gap_threshold = self.fixed_gap_threshold
        else:
            self.gap_threshold = 5.0  # Fallback

        periods = []
        current_period = CombatPeriod(
            start_time=combat_events[0].timestamp,
            end_time=combat_events[0].timestamp,
            event_count=1,
        )

        for event in combat_events[1:]:
            gap = (event.timestamp - current_period.end_time).total_seconds()

            if gap > self.gap_threshold:
                # Combat break detected - save current period and start new one
                periods.append(current_period)
                current_period = CombatPeriod(
                    start_time=event.timestamp, end_time=event.timestamp, event_count=1
                )
            else:
                # Continue current combat period
                current_period.end_time = event.timestamp
                current_period.event_count += 1

        # Add final period
        periods.append(current_period)
        return periods

    def _is_combat_event(self, event: BaseEvent) -> bool:
        """
        Determine if an event indicates active combat.

        Uses configurable combat types and suffixes.
        """
        event_type = event.event_type

        # Check exact types
        if event_type in self.combat_types:
            return True

        # Check suffixes
        if any(suffix in event_type for suffix in self.combat_suffixes):
            return True

        return False

    def calculate_total_combat_time(self, periods: List[CombatPeriod]) -> float:
        """
        Calculate total time spent in combat.

        Args:
            periods: List of combat periods

        Returns:
            Total combat time in seconds
        """
        return sum(period.duration for period in periods)

    def get_combat_percentage(self, periods: List[CombatPeriod], total_duration: float) -> float:
        """
        Calculate what percentage of total time was spent in combat.

        Args:
            periods: List of combat periods
            total_duration: Total encounter duration in seconds

        Returns:
            Percentage of time in combat (0-100)
        """
        if total_duration <= 0:
            return 0.0

        combat_time = self.calculate_total_combat_time(periods)
        return (combat_time / total_duration) * 100

    def is_event_during_combat(
        self, event_time: datetime, periods: List[CombatPeriod]
    ) -> Optional[int]:
        """
        Check if an event occurred during combat.

        Args:
            event_time: Timestamp of the event
            periods: List of combat periods

        Returns:
            Index of combat period if during combat, None otherwise
        """
        for i, period in enumerate(periods):
            if period.contains_time(event_time):
                return i
        return None

    def merge_close_periods(self, periods: List[CombatPeriod], merge_threshold: float = 2.0) -> List[CombatPeriod]:
        """
        Merge combat periods that are closer than the merge threshold.

        Args:
            periods: List of combat periods
            merge_threshold: Seconds between periods to merge

        Returns:
            List of merged periods
        """
        if not periods:
            return periods

        merged = [periods[0]]
        for period in periods[1:]:
            last = merged[-1]
            gap = (period.start_time - last.end_time).total_seconds()
            if gap <= merge_threshold:
                # Merge
                last.end_time = max(last.end_time, period.end_time)
                last.event_count += period.event_count
            else:
                merged.append(period)
        return merged

    def validate_periods(self, periods: List[CombatPeriod]) -> bool:
        """
        Validate that periods are non-overlapping and sorted.

        Args:
            periods: List of combat periods

        Returns:
            True if valid, False otherwise
        """
        for i in range(1, len(periods)):
            if periods[i-1].end_time >= periods[i].start_time:
                return False
        return True
