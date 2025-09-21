"""
Event aggregator for grouping and analyzing combat events.
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field

from src.parser.events import BaseEvent, DamageEvent, HealEvent


@dataclass
class CombatantMetrics:
    """Metrics for a single combatant in a fight."""

    guid: str
    name: str
    damage_done: int = 0
    healing_done: int = 0
    damage_taken: int = 0
    healing_taken: int = 0
    deaths: int = 0
    casts: int = 0
    interrupts: int = 0
    dispels: int = 0


class EventAggregator:
    """
    Aggregates combat events to calculate metrics and statistics.
    """

    def __init__(self):
        self.combatants: Dict[str, CombatantMetrics] = {}
        self.spell_usage: Dict[int, Dict[str, Any]] = defaultdict(
            lambda: {"name": "", "casts": 0, "damage": 0, "healing": 0, "hits": 0}
        )

    def process_events(self, events: List[BaseEvent]):
        """
        Process a list of events and aggregate metrics.

        Args:
            events: List of combat events
        """
        for event in events:
            self._process_event(event)

    def _process_event(self, event: BaseEvent):
        """Process a single event."""
        # Ensure combatants exist
        if event.source_guid and event.source_guid != "0000000000000000":
            self._ensure_combatant(event.source_guid, event.source_name)

        if event.dest_guid and event.dest_guid != "0000000000000000":
            self._ensure_combatant(event.dest_guid, event.dest_name)

        # Process based on event type
        if isinstance(event, DamageEvent):
            self._process_damage(event)
        elif isinstance(event, HealEvent):
            self._process_heal(event)
        elif "CAST_SUCCESS" in event.event_type:
            self._process_cast(event)
        elif "INTERRUPT" in event.event_type:
            self._process_interrupt(event)
        elif "DISPEL" in event.event_type:
            self._process_dispel(event)
        elif event.event_type == "UNIT_DIED":
            self._process_death(event)

    def _ensure_combatant(self, guid: str, name: Optional[str]):
        """Ensure a combatant exists in our tracking."""
        if guid not in self.combatants:
            self.combatants[guid] = CombatantMetrics(guid=guid, name=name or "Unknown")

    def _process_damage(self, event: DamageEvent):
        """Process damage event."""
        if event.source_guid in self.combatants:
            self.combatants[event.source_guid].damage_done += event.amount

        if event.dest_guid in self.combatants:
            self.combatants[event.dest_guid].damage_taken += event.amount

        # Track spell usage
        if hasattr(event, "spell_id") and event.spell_id:
            spell = self.spell_usage[event.spell_id]
            spell["name"] = event.spell_name or f"Spell {event.spell_id}"
            spell["damage"] += event.amount
            spell["hits"] += 1

    def _process_heal(self, event: HealEvent):
        """Process healing event."""
        effective = event.effective_healing

        if event.source_guid in self.combatants:
            self.combatants[event.source_guid].healing_done += effective

        if event.dest_guid in self.combatants:
            self.combatants[event.dest_guid].healing_taken += effective

        # Track spell usage
        if hasattr(event, "spell_id") and event.spell_id:
            spell = self.spell_usage[event.spell_id]
            spell["name"] = event.spell_name or f"Spell {event.spell_id}"
            spell["healing"] += effective
            spell["hits"] += 1

    def _process_cast(self, event: BaseEvent):
        """Process spell cast."""
        if event.source_guid in self.combatants:
            self.combatants[event.source_guid].casts += 1

        # Track spell usage
        if hasattr(event, "spell_id") and event.spell_id:
            spell = self.spell_usage[event.spell_id]
            spell["name"] = event.spell_name or f"Spell {event.spell_id}"
            spell["casts"] += 1

    def _process_interrupt(self, event: BaseEvent):
        """Process interrupt."""
        if event.source_guid in self.combatants:
            self.combatants[event.source_guid].interrupts += 1

    def _process_dispel(self, event: BaseEvent):
        """Process dispel."""
        if event.source_guid in self.combatants:
            self.combatants[event.source_guid].dispels += 1

    def _process_death(self, event: BaseEvent):
        """Process death event."""
        if event.dest_guid in self.combatants:
            self.combatants[event.dest_guid].deaths += 1

    def get_top_damage_dealers(self, limit: int = 10) -> List[CombatantMetrics]:
        """Get top damage dealers."""
        sorted_combatants = sorted(
            self.combatants.values(), key=lambda c: c.damage_done, reverse=True
        )
        return sorted_combatants[:limit]

    def get_top_healers(self, limit: int = 10) -> List[CombatantMetrics]:
        """Get top healers."""
        sorted_combatants = sorted(
            self.combatants.values(), key=lambda c: c.healing_done, reverse=True
        )
        return sorted_combatants[:limit]

    def get_top_spells(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most used/damaging spells."""
        sorted_spells = sorted(
            self.spell_usage.values(),
            key=lambda s: s["damage"] + s["healing"],
            reverse=True,
        )
        return sorted_spells[:limit]

    def get_summary(self) -> Dict[str, Any]:
        """Get aggregation summary."""
        total_damage = sum(c.damage_done for c in self.combatants.values())
        total_healing = sum(c.healing_done for c in self.combatants.values())
        total_deaths = sum(c.deaths for c in self.combatants.values())

        return {
            "total_damage": total_damage,
            "total_healing": total_healing,
            "total_deaths": total_deaths,
            "combatant_count": len(self.combatants),
            "unique_spells": len(self.spell_usage),
            "top_dps": self.get_top_damage_dealers(5),
            "top_hps": self.get_top_healers(5),
        }
