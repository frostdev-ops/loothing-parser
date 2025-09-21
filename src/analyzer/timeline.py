"""
Timeline analysis module with combat period awareness.

This module provides tools for analyzing event timelines within encounters,
with clear visibility into combat vs out-of-combat periods.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from src.parser.events import BaseEvent, DamageEvent, HealEvent, AuraEvent
from src.models.combat_periods import CombatPeriod, EventCategory
from src.segmentation.encounters import Fight


@dataclass
class TimelineEvent:
    """Enhanced event for timeline display."""

    timestamp: datetime
    relative_time: float  # Seconds from encounter start
    event_type: str
    category: EventCategory
    importance: int  # 1-5 scale (5 = most important)
    source: Optional[str]
    target: Optional[str]
    spell: Optional[str]
    amount: Optional[int]
    is_combat: bool  # Whether this occurred during combat
    combat_period: Optional[int]  # Which combat period (for filtering)
    description: str  # Human-readable description

    def __repr__(self) -> str:
        combat_str = f"[Combat {self.combat_period}]" if self.is_combat else "[Out of Combat]"
        return (
            f"TimelineEvent({self.relative_time:.1f}s {combat_str} "
            f"{self.category.value}: {self.description})"
        )


class TimelineBuilder:
    """Build timeline from fight data with combat period awareness."""

    def __init__(self):
        self.importance_rules = {
            # Death events are always critical
            "UNIT_DIED": 5,
            "UNIT_DESTROYED": 5,
            # Boss mechanics and encounters
            "ENCOUNTER_START": 5,
            "ENCOUNTER_END": 5,
            "CHALLENGE_MODE_START": 5,
            "CHALLENGE_MODE_END": 5,
            # Major cooldowns and interrupts
            "SPELL_INTERRUPT": 4,
            "SPELL_DISPEL": 4,
            # Damage and healing (varies by amount)
            "SPELL_DAMAGE": 2,  # Base, modified by amount
            "SWING_DAMAGE": 2,
            "SPELL_HEAL": 2,
            # Auras and buffs
            "SPELL_AURA_APPLIED": 2,
            "SPELL_AURA_REMOVED": 2,
            # Spell casts
            "SPELL_CAST_SUCCESS": 1,
            "SPELL_CAST_START": 1,
            # Default
            "default": 1,
        }

    def build(self, fight: Fight, combat_periods: List[CombatPeriod]) -> List[TimelineEvent]:
        """
        Build timeline with combat period awareness.

        Args:
            fight: Fight containing events to analyze
            combat_periods: List of combat periods for this fight

        Returns:
            List of timeline events sorted by timestamp
        """
        timeline = []

        for event in fight.events:
            # Determine if event is during combat
            is_combat = False
            period_num = None

            for i, period in enumerate(combat_periods):
                if period.contains_time(event.timestamp):
                    is_combat = True
                    period_num = i
                    break

            timeline_event = TimelineEvent(
                timestamp=event.timestamp,
                relative_time=(event.timestamp - fight.start_time).total_seconds(),
                event_type=event.event_type,
                category=self._categorize_event(event),
                importance=self._score_importance(event),
                source=getattr(event, "source_name", None),
                target=getattr(event, "dest_name", None),
                spell=getattr(event, "spell_name", None),
                amount=getattr(event, "amount", None),
                is_combat=is_combat,
                combat_period=period_num,
                description=self._create_description(event),
            )
            timeline.append(timeline_event)

        return sorted(timeline, key=lambda x: x.timestamp)

    def _categorize_event(self, event: BaseEvent) -> EventCategory:
        """Categorize event for filtering and display."""
        event_type = event.event_type

        # Death events
        if event_type in ["UNIT_DIED", "UNIT_DESTROYED"]:
            return EventCategory.DEATH

        # Boss mechanics and encounters
        if any(
            keyword in event_type
            for keyword in ["ENCOUNTER_", "CHALLENGE_MODE_", "BOSS_", "MECHANIC_"]
        ):
            return EventCategory.BOSS_MECHANIC

        # Major cooldowns (heuristic: high-impact spells)
        if hasattr(event, "spell_name") and event.spell_name:
            spell_name = event.spell_name.lower()
            if any(
                keyword in spell_name
                for keyword in [
                    "heroism",
                    "bloodlust",
                    "time warp",
                    "ancient hysteria",
                    "guardian spirit",
                    "divine hymn",
                    "tranquility",
                    "avenging wrath",
                    "metamorphosis",
                    "avatar",
                ]
            ):
                return EventCategory.MAJOR_COOLDOWN

        # Damage events
        if "_DAMAGE" in event_type:
            return EventCategory.DAMAGE

        # Healing events
        if "_HEAL" in event_type:
            return EventCategory.HEALING

        # Buff/Debuff events
        if "_AURA_" in event_type:
            return EventCategory.BUFF_DEBUFF

        # Cast events
        if "_CAST_" in event_type:
            return EventCategory.CAST

        # Interrupt events
        if "INTERRUPT" in event_type:
            return EventCategory.INTERRUPT

        # Dispel events
        if "DISPEL" in event_type or "STOLEN" in event_type:
            return EventCategory.DISPEL

        # Movement events (if any)
        if any(keyword in event_type for keyword in ["MOVE", "POSITION"]):
            return EventCategory.MOVEMENT

        return EventCategory.OTHER

    def _score_importance(self, event: BaseEvent) -> int:
        """Score event importance (1-5 scale)."""
        base_score = self.importance_rules.get(event.event_type, self.importance_rules["default"])

        # Modify score based on event details
        if hasattr(event, "amount") and event.amount:
            amount = event.amount
            # High damage/healing gets higher importance
            if "_DAMAGE" in event.event_type or "_HEAL" in event.event_type:
                if amount > 50000:  # High amount
                    base_score = min(5, base_score + 2)
                elif amount > 20000:  # Medium amount
                    base_score = min(5, base_score + 1)

        # Player events are more important than NPC events
        if hasattr(event, "source_guid") and event.source_guid:
            if event.source_guid.startswith("Player-"):
                base_score = min(5, base_score + 1)

        return base_score

    def _create_description(self, event: BaseEvent) -> str:
        """Create human-readable description of event."""
        event_type = event.event_type
        source = getattr(event, "source_name", "Unknown")
        target = getattr(event, "dest_name", "Unknown")
        spell = getattr(event, "spell_name", "Unknown")
        amount = getattr(event, "amount", 0)

        # Death events
        if event_type == "UNIT_DIED":
            return f"{target} died"

        # Damage events
        if "_DAMAGE" in event_type:
            if spell and spell != "Unknown":
                return f"{source} dealt {amount:,} damage to {target} with {spell}"
            else:
                return f"{source} dealt {amount:,} damage to {target}"

        # Healing events
        if "_HEAL" in event_type:
            if spell and spell != "Unknown":
                return f"{source} healed {target} for {amount:,} with {spell}"
            else:
                return f"{source} healed {target} for {amount:,}"

        # Aura events
        if "AURA_APPLIED" in event_type:
            return (
                f"{spell} applied to {target}"
                if spell != "Unknown"
                else f"Buff applied to {target}"
            )
        elif "AURA_REMOVED" in event_type:
            return (
                f"{spell} removed from {target}"
                if spell != "Unknown"
                else f"Buff removed from {target}"
            )

        # Cast events
        if "CAST_SUCCESS" in event_type:
            return f"{source} cast {spell}" if spell != "Unknown" else f"{source} cast spell"

        # Interrupt events
        if "INTERRUPT" in event_type:
            return f"{source} interrupted {target}"

        # Encounter events
        if event_type == "ENCOUNTER_START":
            return f"Encounter started: {getattr(event, 'encounter_name', 'Unknown')}"
        elif event_type == "ENCOUNTER_END":
            success = getattr(event, "success", None)
            status = "Success" if success else "Wipe" if success is False else "Unknown"
            return f"Encounter ended: {status}"

        # Default description
        return f"{event_type}: {source} -> {target}"


class TimelineFilter:
    """Filter timeline events based on various criteria."""

    @staticmethod
    def filter_by_combat(
        events: List[TimelineEvent], combat_only: bool = True
    ) -> List[TimelineEvent]:
        """Filter events by combat periods."""
        if combat_only:
            return [e for e in events if e.is_combat]
        else:
            return [e for e in events if not e.is_combat]

    @staticmethod
    def filter_by_category(
        events: List[TimelineEvent], category: EventCategory
    ) -> List[TimelineEvent]:
        """Filter events by category."""
        return [e for e in events if e.category == category]

    @staticmethod
    def filter_by_importance(
        events: List[TimelineEvent], min_importance: int = 3
    ) -> List[TimelineEvent]:
        """Filter events by minimum importance level."""
        return [e for e in events if e.importance >= min_importance]

    @staticmethod
    def filter_by_time_window(
        events: List[TimelineEvent], start_time: float, end_time: float
    ) -> List[TimelineEvent]:
        """Filter events by time window (relative to encounter start)."""
        return [e for e in events if start_time <= e.relative_time <= end_time]

    @staticmethod
    def filter_by_participant(
        events: List[TimelineEvent], participant_name: str, include_as_target: bool = True
    ) -> List[TimelineEvent]:
        """Filter events involving a specific participant."""
        filtered = []
        for event in events:
            if event.source == participant_name:
                filtered.append(event)
            elif include_as_target and event.target == participant_name:
                filtered.append(event)
        return filtered


class TimelineAnalyzer:
    """Analyze timeline data for insights."""

    @staticmethod
    def analyze_combat_gaps(
        timeline: List[TimelineEvent], combat_periods: List[CombatPeriod]
    ) -> Dict[str, Any]:
        """Analyze gaps between combat periods."""
        if len(combat_periods) < 2:
            return {"gap_count": 0, "gaps": []}

        gaps = []
        for i in range(len(combat_periods) - 1):
            current_end = combat_periods[i].end_time
            next_start = combat_periods[i + 1].start_time
            gap_duration = (next_start - current_end).total_seconds()

            gaps.append(
                {
                    "start_time": current_end,
                    "end_time": next_start,
                    "duration": gap_duration,
                    "events_during_gap": len(
                        [e for e in timeline if current_end <= e.timestamp <= next_start]
                    ),
                }
            )

        return {
            "gap_count": len(gaps),
            "gaps": gaps,
            "total_gap_time": sum(gap["duration"] for gap in gaps),
            "avg_gap_duration": sum(gap["duration"] for gap in gaps) / len(gaps) if gaps else 0,
        }

    @staticmethod
    def get_activity_bursts(
        timeline: List[TimelineEvent], window_size: float = 10.0
    ) -> List[Dict[str, Any]]:
        """Find periods of high activity (event density)."""
        if not timeline:
            return []

        bursts = []
        timeline = sorted(timeline, key=lambda x: x.relative_time)

        for i, event in enumerate(timeline):
            window_start = event.relative_time
            window_end = window_start + window_size

            # Count events in this window
            events_in_window = [
                e for e in timeline if window_start <= e.relative_time <= window_end
            ]

            if len(events_in_window) >= 10:  # Threshold for "burst"
                bursts.append(
                    {
                        "start_time": window_start,
                        "end_time": window_end,
                        "event_count": len(events_in_window),
                        "events_per_second": len(events_in_window) / window_size,
                        "categories": list(set(e.category for e in events_in_window)),
                    }
                )

        # Merge overlapping bursts
        merged_bursts = []
        for burst in bursts:
            if not merged_bursts or burst["start_time"] > merged_bursts[-1]["end_time"]:
                merged_bursts.append(burst)
            else:
                # Merge with previous burst
                last_burst = merged_bursts[-1]
                last_burst["end_time"] = max(last_burst["end_time"], burst["end_time"])
                last_burst["event_count"] += burst["event_count"]
                last_burst["categories"] = list(set(last_burst["categories"] + burst["categories"]))

        return merged_bursts

    @staticmethod
    def find_key_moments(timeline: List[TimelineEvent]) -> List[TimelineEvent]:
        """Find the most important moments in the timeline."""
        # Sort by importance, then by timestamp
        important_events = [e for e in timeline if e.importance >= 4]
        return sorted(important_events, key=lambda x: (-x.importance, x.timestamp))[:20]
