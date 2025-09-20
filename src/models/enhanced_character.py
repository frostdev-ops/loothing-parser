"""
Enhanced character model with comprehensive ability tracking and death analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Deque
from collections import deque, defaultdict
from enum import Enum

from src.parser.events import BaseEvent, DamageEvent, HealEvent, AuraEvent, CombatantInfo
from src.models.character_events import CharacterEventStream, DeathEvent
from src.config.wow_data import (
    get_spec_name,
    is_tank_spec,
    is_healer_spec,
    is_flask_buff,
    is_food_buff,
)


@dataclass
class AbilityMetrics:
    """Detailed metrics for a single ability."""

    spell_id: int
    spell_name: str
    total_damage: int = 0
    total_healing: int = 0
    total_absorbed: int = 0
    cast_count: int = 0
    hit_count: int = 0
    crit_count: int = 0
    miss_count: int = 0
    percentage_of_total: float = 0.0
    average_hit: float = 0.0
    crit_rate: float = 0.0

    def calculate_metrics(self, total_damage: int = 0, total_healing: int = 0):
        """Calculate derived metrics."""
        # Calculate percentage of total
        if self.total_damage > 0 and total_damage > 0:
            self.percentage_of_total = (self.total_damage / total_damage) * 100
        elif self.total_healing > 0 and total_healing > 0:
            self.percentage_of_total = (self.total_healing / total_healing) * 100

        # Calculate average hit
        if self.hit_count > 0:
            total = self.total_damage + self.total_healing
            self.average_hit = total / self.hit_count

        # Calculate crit rate
        if self.hit_count > 0:
            self.crit_rate = (self.crit_count / self.hit_count) * 100


@dataclass
class EnhancedDeathEvent:
    """Enhanced death event with contributing damage and healing."""

    timestamp: float
    datetime: datetime
    killing_blow: Optional[DamageEvent] = None
    overkill: int = 0
    resurrect_time: Optional[float] = None

    # Recent events leading to death
    recent_damage_taken: List[DamageEvent] = field(default_factory=list)
    recent_healing_received: List[HealEvent] = field(default_factory=list)

    # Damage sources that contributed to death
    damage_sources: Dict[str, int] = field(default_factory=dict)

    # Healing sources that tried to prevent death
    healing_sources: Dict[str, int] = field(default_factory=dict)

    def analyze_death_contributors(self):
        """Analyze what contributed to this death."""
        # Aggregate damage sources
        for event in self.recent_damage_taken:
            source_name = event.source_name or "Unknown"
            if event.spell_name:
                key = f"{source_name}: {event.spell_name}"
            else:
                key = f"{source_name}: Melee"
            self.damage_sources[key] = self.damage_sources.get(key, 0) + event.amount

        # Aggregate healing sources
        for event in self.recent_healing_received:
            source_name = event.source_name or "Unknown"
            if event.spell_name:
                key = f"{source_name}: {event.spell_name}"
            else:
                key = source_name
            self.healing_sources[key] = self.healing_sources.get(key, 0) + event.effective_healing


@dataclass
class EnhancedCharacter(CharacterEventStream):
    """
    Enhanced character model with comprehensive tracking.

    Extends CharacterEventStream with:
    - Ability breakdowns with percentages
    - Death analysis with recent events
    - Talent and equipment data
    - Enhanced metrics calculation
    """

    # Talent and equipment data from COMBATANT_INFO
    talent_data: Optional[CombatantInfo] = None
    item_level: Optional[float] = None

    # Ability tracking by spell ID
    ability_damage: Dict[int, AbilityMetrics] = field(default_factory=dict)
    ability_healing: Dict[int, AbilityMetrics] = field(default_factory=dict)
    ability_damage_taken: Dict[int, AbilityMetrics] = field(default_factory=dict)

    # Recent event tracking for death analysis (max 10 events)
    recent_damage_taken: Deque[DamageEvent] = field(default_factory=lambda: deque(maxlen=10))
    recent_healing_received: Deque[HealEvent] = field(default_factory=lambda: deque(maxlen=10))

    # Enhanced death tracking
    enhanced_deaths: List[EnhancedDeathEvent] = field(default_factory=list)

    # Computed metrics
    dps_by_ability: Dict[int, float] = field(default_factory=dict)
    hps_by_ability: Dict[int, float] = field(default_factory=dict)

    # Role detection
    role: Optional[str] = None  # "tank", "healer", "dps"

    def add_event(self, event: BaseEvent, category: str):
        """Override to add ability tracking."""
        # Call parent implementation
        super().add_event(event, category)

        # Track abilities
        if isinstance(event, DamageEvent):
            self._track_damage_ability(event, category)
        elif isinstance(event, HealEvent):
            self._track_healing_ability(event, category)

        # Track recent events for death analysis
        if category == "damage_taken" and isinstance(event, DamageEvent):
            self.recent_damage_taken.append(event)
        elif category == "healing_received" and isinstance(event, HealEvent):
            self.recent_healing_received.append(event)

    def _track_damage_ability(self, event: DamageEvent, category: str):
        """Track damage abilities."""
        spell_id = event.spell_id if event.spell_id else 0  # 0 for melee
        spell_name = event.spell_name if event.spell_name else "Melee"

        if category == "damage_done":
            if spell_id not in self.ability_damage:
                self.ability_damage[spell_id] = AbilityMetrics(
                    spell_id=spell_id, spell_name=spell_name
                )

            ability = self.ability_damage[spell_id]
            ability.total_damage += event.amount
            ability.hit_count += 1
            if event.critical:
                ability.crit_count += 1

        elif category == "damage_taken":
            if spell_id not in self.ability_damage_taken:
                self.ability_damage_taken[spell_id] = AbilityMetrics(
                    spell_id=spell_id, spell_name=spell_name
                )

            ability = self.ability_damage_taken[spell_id]
            ability.total_damage += event.amount
            ability.hit_count += 1

    def _track_healing_ability(self, event: HealEvent, category: str):
        """Track healing abilities."""
        spell_id = event.spell_id if event.spell_id else 0
        spell_name = event.spell_name if event.spell_name else "Unknown"

        if category == "healing_done" and spell_id:
            if spell_id not in self.ability_healing:
                self.ability_healing[spell_id] = AbilityMetrics(
                    spell_id=spell_id, spell_name=spell_name
                )

            ability = self.ability_healing[spell_id]
            ability.total_healing += event.amount  # Total healing including overheal
            ability.hit_count += 1
            if event.critical:
                ability.crit_count += 1

    def add_enhanced_death(self, death_event: DeathEvent):
        """Add a death with enhanced tracking."""
        # Create enhanced death event
        enhanced_death = EnhancedDeathEvent(
            timestamp=death_event.timestamp,
            datetime=death_event.datetime,
            killing_blow=death_event.killing_blow,
            overkill=death_event.overkill,
            resurrect_time=death_event.resurrect_time,
            recent_damage_taken=list(self.recent_damage_taken),
            recent_healing_received=list(self.recent_healing_received),
        )

        # Analyze death contributors
        enhanced_death.analyze_death_contributors()

        # Add to enhanced deaths
        self.enhanced_deaths.append(enhanced_death)

        # Also track in parent class
        self.deaths.append(death_event)
        self.death_count += 1

    def set_talent_data(self, combatant_info: CombatantInfo):
        """Set talent and equipment data from COMBATANT_INFO event."""
        self.talent_data = combatant_info

        # Calculate average item level
        if combatant_info.equipped_items:
            valid_items = [item for item in combatant_info.equipped_items if item.item_level > 0]
            if valid_items:
                self.item_level = sum(item.item_level for item in valid_items) / len(valid_items)

        # Set spec name if available
        if combatant_info.spec_id:
            self.spec_name = self._get_spec_name(combatant_info.spec_id)

    def calculate_ability_metrics(self, encounter_duration: float):
        """Calculate ability percentages and DPS/HPS."""
        # Calculate damage ability metrics
        for ability in self.ability_damage.values():
            ability.calculate_metrics(total_damage=self.total_damage_done)
            if encounter_duration > 0:
                self.dps_by_ability[ability.spell_id] = ability.total_damage / encounter_duration

        # Calculate healing ability metrics
        for ability in self.ability_healing.values():
            ability.calculate_metrics(total_healing=self.total_healing_done)
            if encounter_duration > 0:
                self.hps_by_ability[ability.spell_id] = ability.total_healing / encounter_duration

        # Calculate damage taken metrics
        total_damage_taken = sum(a.total_damage for a in self.ability_damage_taken.values())
        for ability in self.ability_damage_taken.values():
            ability.calculate_metrics(total_damage=total_damage_taken)

    def detect_role(self):
        """Detect player role based on spec ID or activity."""
        # First try to detect by spec ID if available
        if self.talent_data and self.talent_data.spec_id:
            spec_id = self.talent_data.spec_id
            if is_tank_spec(spec_id):
                self.role = "tank"
            elif is_healer_spec(spec_id):
                self.role = "healer"
            else:
                self.role = "dps"
        # Fallback to activity-based detection
        elif self.total_healing_done > self.total_damage_done * 2:
            self.role = "healer"
        else:
            self.role = "dps"

    def get_top_abilities(
        self, ability_type: str = "damage", limit: int = 10
    ) -> List[AbilityMetrics]:
        """Get top abilities by damage or healing."""
        if ability_type == "damage":
            abilities = sorted(
                self.ability_damage.values(), key=lambda a: a.total_damage, reverse=True
            )
        elif ability_type == "healing":
            abilities = sorted(
                self.ability_healing.values(), key=lambda a: a.total_healing, reverse=True
            )
        elif ability_type == "damage_taken":
            abilities = sorted(
                self.ability_damage_taken.values(), key=lambda a: a.total_damage, reverse=True
            )
        else:
            abilities = []

        return abilities[:limit]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        base_dict = super().to_dict()

        # Add enhanced data
        base_dict.update(
            {
                "item_level": round(self.item_level, 1) if self.item_level else None,
                "role": self.role,
                "talent_build": (
                    self.talent_data.get_talent_build_string() if self.talent_data else None
                ),
                "has_flask": bool(self.talent_data.get_flask()) if self.talent_data else False,
                "has_food": bool(self.talent_data.get_food_buff()) if self.talent_data else False,
                "ability_breakdown": {
                    "damage": [
                        {
                            "spell_name": a.spell_name,
                            "total": a.total_damage,
                            "percentage": round(a.percentage_of_total, 1),
                            "hits": a.hit_count,
                            "avg_hit": round(a.average_hit),
                            "crit_rate": round(a.crit_rate, 1),
                        }
                        for a in self.get_top_abilities("damage", 5)
                    ],
                    "healing": [
                        {
                            "spell_name": a.spell_name,
                            "total": a.total_healing,
                            "percentage": round(a.percentage_of_total, 1),
                            "hits": a.hit_count,
                            "avg_hit": round(a.average_hit),
                            "crit_rate": round(a.crit_rate, 1),
                        }
                        for a in self.get_top_abilities("healing", 5)
                    ],
                },
                "deaths": [
                    {
                        "timestamp": death.timestamp,
                        "damage_sources": sorted(
                            death.damage_sources.items(), key=lambda x: x[1], reverse=True
                        )[
                            :5
                        ],  # Top 5 damage sources
                        "total_recent_damage": sum(death.damage_sources.values()),
                        "healing_attempted": sum(death.healing_sources.values()),
                    }
                    for death in self.enhanced_deaths
                ],
            }
        )

        return base_dict

    def _get_spec_name(self, spec_id: int) -> str:
        """Get spec name from spec ID using configurable mapping."""
        return get_spec_name(spec_id)
