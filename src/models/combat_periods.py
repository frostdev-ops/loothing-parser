"""
Combat period detection for accurate activity and DPS calculations.

This module provides tools to detect when players are actively in combat
versus out-of-combat periods (travel time, breaks, etc.).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from enum import Enum

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

    def __init__(self, gap_threshold: float = 5.0):
        """
        Initialize detector.

        Args:
            gap_threshold: Seconds of inactivity before considering combat ended
        """
        self.gap_threshold = gap_threshold

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

        periods = []
        current_period = CombatPeriod(
            start_time=combat_events[0].timestamp,
            end_time=combat_events[0].timestamp,
            event_count=1
        )

        for event in combat_events[1:]:
            gap = (event.timestamp - current_period.end_time).total_seconds()

            if gap > self.gap_threshold:
                # Combat break detected - save current period and start new one
                periods.append(current_period)
                current_period = CombatPeriod(
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    event_count=1
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

        Combat events include:
        - Damage dealt or taken
        - Healing done or received
        - Buff/debuff applications (indicates activity)
        - Spell casts
        - Interrupts and dispels

        Non-combat events include:
        - Zone changes
        - Encounter start/end markers
        - Pure informational events
        """
        event_type = event.event_type

        # Direct combat events
        if any(suffix in event_type for suffix in [
            "_DAMAGE", "_HEAL", "_CAST_SUCCESS", "_CAST_START",
            "_INTERRUPT", "_DISPEL", "_STOLEN"
        ]):
            return True

        # Aura events indicate activity
        if any(suffix in event_type for suffix in [
            "_AURA_APPLIED", "_AURA_REMOVED", "_AURA_REFRESH"
        ]):
            return True

        # Specific important events
        if event_type in [
            "UNIT_DIED", "UNIT_DESTROYED",
            "SPELL_SUMMON", "SPELL_CREATE",
            "SPELL_INSTAKILL"
        ]:
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

    def get_combat_percentage(
        self,
        periods: List[CombatPeriod],
        total_duration: float
    ) -> float:
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
        self,
        event_time: datetime,
        periods: List[CombatPeriod]
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