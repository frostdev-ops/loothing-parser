"""
Character event stream models for detailed combat tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from src.parser.events import BaseEvent, DamageEvent, HealEvent, AuraEvent
from src.models.combat_periods import CombatPeriod


class ResourceType(Enum):
    """Types of character resources."""

    MANA = 0
    RAGE = 1
    FOCUS = 2
    ENERGY = 3
    COMBO_POINTS = 4
    RUNES = 5
    RUNIC_POWER = 6
    SOUL_SHARDS = 7
    LUNAR_POWER = 8
    HOLY_POWER = 9
    MAELSTROM = 10
    CHI = 11
    FURY = 12
    PAIN = 13
    INSANITY = 14


@dataclass
class TimestampedEvent:
    """
    Wrapper for events with precise timestamp and categorization.
    """

    timestamp: float  # Unix timestamp with microseconds
    datetime: datetime
    event: BaseEvent
    category: str  # damage_done, healing_done, buff_gained, etc.

    def __lt__(self, other):
        """Enable sorting by timestamp."""
        return self.timestamp < other.timestamp


@dataclass
class DeathEvent:
    """Represents a character death."""

    timestamp: float
    datetime: datetime
    killing_blow: Optional[BaseEvent] = None
    overkill: int = 0
    resurrect_time: Optional[float] = None


@dataclass
class ResourceEvent:
    """Tracks resource changes (mana, energy, etc.)."""

    timestamp: float
    datetime: datetime
    resource_type: ResourceType
    amount: int
    max_amount: int
    change: int  # Positive for gains, negative for spending


@dataclass
class CastEvent:
    """Tracks spell casts."""

    timestamp: float
    datetime: datetime
    spell_id: int
    spell_name: str
    cast_time: float  # Cast duration in seconds
    success: bool
    interrupted: bool = False


@dataclass
class CharacterEventStream:
    """
    Complete event history for a single character in an encounter.

    This class maintains separate lists for different event types
    for efficient querying while preserving precise timestamps.
    """

    # Character identification
    character_guid: str
    character_name: str
    server: Optional[str] = None
    region: Optional[str] = None
    class_name: Optional[str] = None
    spec_name: Optional[str] = None
    item_level: Optional[int] = None

    # All events in chronological order
    all_events: List[TimestampedEvent] = field(default_factory=list)

    # Categorized event lists for fast access
    damage_done: List[DamageEvent] = field(default_factory=list)
    healing_done: List[HealEvent] = field(default_factory=list)
    damage_taken: List[DamageEvent] = field(default_factory=list)
    healing_received: List[HealEvent] = field(default_factory=list)

    # Buff/Debuff tracking
    buffs_gained: List[AuraEvent] = field(default_factory=list)
    buffs_lost: List[AuraEvent] = field(default_factory=list)
    buffs_refreshed: List[AuraEvent] = field(default_factory=list)
    debuffs_gained: List[AuraEvent] = field(default_factory=list)
    debuffs_lost: List[AuraEvent] = field(default_factory=list)
    debuffs_refreshed: List[AuraEvent] = field(default_factory=list)

    # Spell casts and abilities
    casts_started: List[CastEvent] = field(default_factory=list)
    casts_succeeded: List[CastEvent] = field(default_factory=list)
    casts_failed: List[CastEvent] = field(default_factory=list)
    interrupts_done: List[BaseEvent] = field(default_factory=list)
    interrupts_received: List[BaseEvent] = field(default_factory=list)
    dispels_done: List[BaseEvent] = field(default_factory=list)

    # Deaths and resurrections
    deaths: List[DeathEvent] = field(default_factory=list)

    # Resource tracking
    resource_changes: List[ResourceEvent] = field(default_factory=list)

    # Absorption tracking
    absorption_provided: List[BaseEvent] = field(default_factory=list)  # Shields I provided
    absorption_received: List[BaseEvent] = field(default_factory=list)  # Shields that protected me

    # Aggregated metrics (calculated after all events processed)
    total_damage_done: int = 0
    total_healing_done: int = 0
    total_damage_taken: int = 0
    total_healing_received: int = 0
    total_overhealing: int = 0
    death_count: int = 0

    # Overkill tracking (separate from damage totals)
    total_overkill_done: int = 0
    total_overkill_taken: int = 0

    # Absorption tracking
    total_damage_absorbed_by_shields: int = 0  # Shields I provided for others
    total_damage_absorbed_for_me: int = 0  # Damage prevented on me

    # Active auras at any given time (for state reconstruction)
    active_buffs: Dict[int, AuraEvent] = field(default_factory=dict)  # spell_id -> event
    active_debuffs: Dict[int, AuraEvent] = field(default_factory=dict)

    # Performance metrics
    activity_percentage: float = 0.0  # Percentage of time active
    time_alive: float = 0.0  # Seconds alive during encounter
    combat_time: float = 0.0  # Seconds in combat during encounter

    def add_event(self, event: BaseEvent, category: str):
        """
        Add an event to the character's stream.

        Args:
            event: The combat log event
            category: Event category for routing
        """
        # Create timestamped wrapper
        ts_event = TimestampedEvent(
            timestamp=event.timestamp.timestamp(),
            datetime=event.timestamp,
            event=event,
            category=category,
        )

        # Add to main list
        self.all_events.append(ts_event)

        # Route to appropriate category list
        self._route_event(event, category)

    def _route_event(self, event: BaseEvent, category: str):
        """Route event to appropriate category list."""
        import logging

        logger = logging.getLogger(__name__)

        if category == "damage_done" and (
            isinstance(event, DamageEvent) or "_DAMAGE" in event.event_type
        ):
            # Ensure we have a valid DamageEvent with amount data
            if isinstance(event, DamageEvent):
                self.damage_done.append(event)
                # Only count actual damage, not overkill (matches Details addon behavior)
                amount = event.amount if hasattr(event, 'amount') else 0
                self.total_damage_done += amount
                logger.debug(
                    f"Added damage_done: {amount}, total now: {self.total_damage_done}, event_type: {event.event_type}"
                )
                # Track overkill separately
                if hasattr(event, 'overkill') and event.overkill > 0:
                    self.total_overkill_done += event.overkill
            else:
                logger.warning(
                    f"damage_done event is not DamageEvent instance: {type(event)}, event_type: {event.event_type}"
                )

        elif category == "healing_done" and (
            isinstance(event, HealEvent) or "_HEAL" in event.event_type
        ):
            # Ensure we have a valid HealEvent with amount data
            if isinstance(event, HealEvent):
                self.healing_done.append(event)
                # Use effective healing (excluding overhealing) to match WoW's "Healing Done" metric
                amount = event.amount if hasattr(event, 'amount') else 0
                overhealing = event.overhealing if hasattr(event, 'overhealing') else 0
                effective_healing = max(0, amount - overhealing)  # Ensure non-negative
                self.total_healing_done += effective_healing
                self.total_overhealing += overhealing
                logger.debug(
                    f"Added healing_done: {effective_healing} (effective), total now: {self.total_healing_done}, event_type: {event.event_type}"
                )
            else:
                logger.warning(
                    f"healing_done event is not HealEvent instance: {type(event)}, event_type: {event.event_type}"
                )

        elif category == "damage_taken" and isinstance(event, DamageEvent):
            self.damage_taken.append(event)
            # Only count actual damage, not overkill (matches Details addon behavior)
            self.total_damage_taken += event.amount
            # Track overkill separately
            if event.overkill > 0:
                self.total_overkill_taken += event.overkill

        elif category == "healing_received" and isinstance(event, HealEvent):
            self.healing_received.append(event)
            self.total_healing_received += event.effective_healing

        elif category == "buff_gained" and isinstance(event, AuraEvent):
            self.buffs_gained.append(event)
            if event.spell_id:
                self.active_buffs[event.spell_id] = event

        elif category == "buff_lost" and isinstance(event, AuraEvent):
            self.buffs_lost.append(event)
            if event.spell_id and event.spell_id in self.active_buffs:
                del self.active_buffs[event.spell_id]

        elif category == "debuff_gained" and isinstance(event, AuraEvent):
            self.debuffs_gained.append(event)
            if event.spell_id:
                self.active_debuffs[event.spell_id] = event

        elif category == "debuff_lost" and isinstance(event, AuraEvent):
            self.debuffs_lost.append(event)
            if event.spell_id and event.spell_id in self.active_debuffs:
                del self.active_debuffs[event.spell_id]

        elif category == "damage_absorbed_by_shield":
            # This character provided a shield that absorbed damage
            self.absorption_provided.append(event)
            if hasattr(event, "amount_absorbed"):
                self.total_damage_absorbed_by_shields += event.amount_absorbed

        elif category == "damage_absorbed_for_me":
            # This character received protection from a shield
            self.absorption_received.append(event)
            if hasattr(event, "amount_absorbed"):
                self.total_damage_absorbed_for_me += event.amount_absorbed
        else:
            logger.debug(
                f"Event not routed: category={category}, event_type={event.event_type}, isinstance_damage={isinstance(event, DamageEvent)}, isinstance_heal={isinstance(event, HealEvent)}"
            )

    def add_death(self, death_event: DeathEvent):
        """Record a character death."""
        self.deaths.append(death_event)
        self.death_count += 1

    def get_events_in_range(self, start: float, end: float) -> List[TimestampedEvent]:
        """
        Get all events within a time range.

        Args:
            start: Start timestamp
            end: End timestamp

        Returns:
            List of events in the time range
        """
        return [e for e in self.all_events if start <= e.timestamp <= end]

    def get_dps(self, duration: float) -> float:
        """Calculate DPS over a duration."""
        if duration <= 0:
            return 0.0
        dps = self.total_damage_done / duration
        return round(dps, 2)

    def get_hps(self, duration: float) -> float:
        """Calculate HPS over a duration."""
        if duration <= 0:
            return 0.0
        hps = self.total_healing_done / duration
        return round(hps, 2)

    def get_dtps(self, duration: float) -> float:
        """Calculate damage taken per second."""
        return self.total_damage_taken / duration if duration > 0 else 0

    def get_combat_dps(self, combat_time: Optional[float] = None) -> float:
        """Calculate DPS during combat periods only."""
        duration = combat_time if combat_time is not None else self.combat_time
        if duration <= 0:
            return 0.0
        combat_dps = self.total_damage_done / duration
        return round(combat_dps, 2)

    def get_combat_hps(self, combat_time: Optional[float] = None) -> float:
        """Calculate HPS during combat periods only."""
        duration = combat_time if combat_time is not None else self.combat_time
        if duration <= 0:
            return 0.0
        combat_hps = self.total_healing_done / duration
        return round(combat_hps, 2)

    def get_combat_dtps(self, combat_time: Optional[float] = None) -> float:
        """Calculate damage taken per second during combat periods only."""
        duration = combat_time if combat_time is not None else self.combat_time
        return self.total_damage_taken / duration if duration > 0 else 0

    def calculate_activity(self, encounter_duration: float):
        """
        Calculate activity percentage and time alive.

        Args:
            encounter_duration: Total encounter duration in seconds
        """
        if not self.all_events:
            self.activity_percentage = 0.0
            self.time_alive = 0.0
            return

        # Calculate time alive (subtract death periods)
        time_dead = 0.0
        for i, death in enumerate(self.deaths):
            if death.resurrect_time:
                time_dead += death.resurrect_time - death.timestamp
            else:
                # Dead until end of encounter
                end_time = self.all_events[-1].timestamp if self.all_events else death.timestamp
                time_dead += end_time - death.timestamp

        self.time_alive = encounter_duration - time_dead

        # Calculate activity (casting or dealing damage/healing)
        active_events = len(self.damage_done) + len(self.healing_done) + len(self.casts_succeeded)
        total_possible_gcds = self.time_alive / 1.5  # Assume 1.5s GCD

        self.activity_percentage = (
            min(100, (active_events / total_possible_gcds) * 100) if total_possible_gcds > 0 else 0
        )

    def calculate_combat_metrics(
        self, combat_periods: List[CombatPeriod], encounter_duration: float
    ):
        """
        Calculate activity and combat time using combat periods.

        This is the new preferred method for calculating activity as it only
        considers time spent in combat, not travel time or breaks.

        Args:
            combat_periods: List of combat periods for the encounter
            encounter_duration: Total encounter duration in seconds
        """
        if not self.all_events:
            self.activity_percentage = 0.0
            self.time_alive = 0.0
            self.combat_time = 0.0
            return

        # Calculate total combat time
        total_combat_time = sum(period.duration for period in combat_periods)
        self.combat_time = total_combat_time

        # Calculate time alive (subtract death periods)
        time_dead = 0.0
        for death in self.deaths:
            if death.resurrect_time:
                time_dead += death.resurrect_time - death.timestamp
            else:
                # Dead until end of encounter
                end_time = self.all_events[-1].timestamp if self.all_events else death.timestamp
                time_dead += end_time - death.timestamp

        self.time_alive = encounter_duration - time_dead

        # Count events that occurred during combat periods only
        combat_events = 0
        for event in self.all_events:
            event_time = event.datetime

            # Check if event occurred during a combat period
            for period in combat_periods:
                if period.contains_time(event_time):
                    # Only count active events (damage, healing, casts)
                    if (
                        event.category in ["damage_done", "healing_done"]
                        or "cast" in event.category
                    ):
                        combat_events += 1
                    break

        # Calculate activity based on combat time only
        # Activity = (events during combat) / (possible GCDs during combat)
        if total_combat_time > 0:
            # Adjust combat time for death periods
            combat_time_alive = total_combat_time

            # Subtract time dead during combat periods
            for death in self.deaths:
                death_start = death.timestamp
                death_end = (
                    death.resurrect_time
                    if death.resurrect_time
                    else (self.all_events[-1].timestamp if self.all_events else death.timestamp)
                )

                # Calculate overlap with combat periods
                for period in combat_periods:
                    overlap_start = max(death_start, period.start_time.timestamp())
                    overlap_end = min(death_end, period.end_time.timestamp())

                    if overlap_start < overlap_end:
                        combat_time_alive -= overlap_end - overlap_start

            possible_gcds_in_combat = max(0, combat_time_alive) / 1.5  # 1.5s GCD

            self.activity_percentage = (
                min(100, (combat_events / possible_gcds_in_combat) * 100)
                if possible_gcds_in_combat > 0
                else 0
            )
        else:
            self.activity_percentage = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of character stream
        """
        return {
            "character_guid": self.character_guid,
            "character_name": self.character_name,
            "server": self.server,
            "region": self.region,
            "class": self.class_name,
            "spec": self.spec_name,
            "item_level": self.item_level,
            "metrics": {
                "damage_done": self.total_damage_done,
                "healing_done": self.total_healing_done,
                "damage_taken": self.total_damage_taken,
                "healing_received": self.total_healing_received,
                "overhealing": self.total_overhealing,
                "overkill_done": self.total_overkill_done,
                "overkill_taken": self.total_overkill_taken,
                "deaths": self.death_count,
                "activity_percentage": round(self.activity_percentage, 1),
                "time_alive_seconds": round(self.time_alive, 1),
                "combat_time_seconds": round(self.combat_time, 1),
            },
            "event_counts": {
                "total_events": len(self.all_events),
                "damage_events": len(self.damage_done),
                "healing_events": len(self.healing_done),
                "buff_events": len(self.buffs_gained),
                "debuff_events": len(self.debuffs_gained),
                "cast_events": len(self.casts_succeeded),
            },
        }
