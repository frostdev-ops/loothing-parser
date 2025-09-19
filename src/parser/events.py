"""
Event classes and factory for WoW combat log events.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    """Enumeration of known event types."""
    # Combat events
    SWING_DAMAGE = "SWING_DAMAGE"
    SWING_MISSED = "SWING_MISSED"
    SPELL_DAMAGE = "SPELL_DAMAGE"
    SPELL_MISSED = "SPELL_MISSED"
    SPELL_HEAL = "SPELL_HEAL"
    SPELL_ABSORBED = "SPELL_ABSORBED"
    SPELL_PERIODIC_DAMAGE = "SPELL_PERIODIC_DAMAGE"
    SPELL_PERIODIC_HEAL = "SPELL_PERIODIC_HEAL"

    # Aura events
    SPELL_AURA_APPLIED = "SPELL_AURA_APPLIED"
    SPELL_AURA_REMOVED = "SPELL_AURA_REMOVED"
    SPELL_AURA_APPLIED_DOSE = "SPELL_AURA_APPLIED_DOSE"
    SPELL_AURA_REMOVED_DOSE = "SPELL_AURA_REMOVED_DOSE"
    SPELL_AURA_REFRESH = "SPELL_AURA_REFRESH"

    # Cast events
    SPELL_CAST_START = "SPELL_CAST_START"
    SPELL_CAST_SUCCESS = "SPELL_CAST_SUCCESS"
    SPELL_CAST_FAILED = "SPELL_CAST_FAILED"

    # Special events
    SPELL_SUMMON = "SPELL_SUMMON"
    SPELL_CREATE = "SPELL_CREATE"
    SPELL_ENERGIZE = "SPELL_ENERGIZE"
    SPELL_INTERRUPT = "SPELL_INTERRUPT"
    SPELL_DISPEL = "SPELL_DISPEL"

    # Environmental
    ENVIRONMENTAL_DAMAGE = "ENVIRONMENTAL_DAMAGE"

    # Meta events
    ENCOUNTER_START = "ENCOUNTER_START"
    ENCOUNTER_END = "ENCOUNTER_END"
    CHALLENGE_MODE_START = "CHALLENGE_MODE_START"
    CHALLENGE_MODE_END = "CHALLENGE_MODE_END"
    COMBATANT_INFO = "COMBATANT_INFO"
    COMBAT_LOG_VERSION = "COMBAT_LOG_VERSION"
    ZONE_CHANGE = "ZONE_CHANGE"
    MAP_CHANGE = "MAP_CHANGE"
    PARTY_KILL = "PARTY_KILL"


@dataclass
class BaseEvent:
    """Base class for all combat log events."""
    timestamp: datetime
    event_type: str
    raw_line: str

    # Base parameters (present in most combat events)
    hide_caster: Optional[bool] = None
    source_guid: Optional[str] = None
    source_name: Optional[str] = None
    source_flags: Optional[int] = None
    source_raid_flags: Optional[int] = None
    dest_guid: Optional[str] = None
    dest_name: Optional[str] = None
    dest_flags: Optional[int] = None
    dest_raid_flags: Optional[int] = None

    def is_player_source(self) -> bool:
        """Check if the source is a player."""
        if self.source_guid:
            return self.source_guid.startswith("Player-")
        return False

    def is_player_dest(self) -> bool:
        """Check if the destination is a player."""
        if self.dest_guid:
            return self.dest_guid.startswith("Player-")
        return False

    def is_pet_source(self) -> bool:
        """Check if the source is a pet."""
        if self.source_guid:
            return self.source_guid.startswith("Pet-")
        return False


@dataclass
class SpellEvent(BaseEvent):
    """Base class for spell-related events."""
    spell_id: Optional[int] = None
    spell_name: Optional[str] = None
    spell_school: Optional[int] = None


@dataclass
class DamageEvent(SpellEvent):
    """Event for damage dealing."""
    amount: int = 0
    overkill: int = 0
    school: int = 0
    resisted: int = 0
    blocked: int = 0
    absorbed: int = 0
    critical: bool = False
    glancing: bool = False
    crushing: bool = False


@dataclass
class HealEvent(SpellEvent):
    """Event for healing."""
    amount: int = 0
    overhealing: int = 0
    absorbed: int = 0
    critical: bool = False

    @property
    def effective_healing(self) -> int:
        """Calculate effective healing (excluding overhealing)."""
        return self.amount - self.overhealing


@dataclass
class AuraEvent(SpellEvent):
    """Event for buff/debuff application or removal."""
    aura_type: Optional[str] = None  # BUFF or DEBUFF
    stacks: int = 1


@dataclass
class EncounterEvent(BaseEvent):
    """Event for raid encounter start/end."""
    encounter_id: int = 0
    encounter_name: str = ""
    difficulty_id: int = 0
    group_size: int = 0
    instance_id: int = 0
    success: Optional[bool] = None  # Only for ENCOUNTER_END
    duration: Optional[int] = None   # Only for ENCOUNTER_END (in ms)


@dataclass
class ChallengeModeEvent(BaseEvent):
    """Event for Mythic+ dungeon start/end."""
    zone_name: str = ""
    instance_id: int = 0
    challenge_id: int = 0
    keystone_level: int = 0
    affix_ids: List[int] = field(default_factory=list)
    success: Optional[bool] = None  # Only for CHALLENGE_MODE_END
    duration: Optional[float] = None  # Only for CHALLENGE_MODE_END (in seconds)


@dataclass
class CombatantInfo(BaseEvent):
    """Event containing detailed combatant information."""
    player_guid: str = ""
    player_name: str = ""
    faction: int = 0
    strength: int = 0
    agility: int = 0
    stamina: int = 0
    intelligence: int = 0
    dodge: float = 0.0
    parry: float = 0.0
    block: float = 0.0
    crit_melee: float = 0.0
    crit_ranged: float = 0.0
    crit_spell: float = 0.0
    speed: float = 0.0
    lifesteal: float = 0.0
    haste_melee: float = 0.0
    haste_ranged: float = 0.0
    haste_spell: float = 0.0
    avoidance: float = 0.0
    mastery: float = 0.0
    versatility_damage: float = 0.0
    armor: int = 0
    spec_id: int = 0
    talents: List[int] = field(default_factory=list)
    pvp_talents: List[int] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)


class EventFactory:
    """Factory for creating specific event objects from parsed lines."""

    _event_classes: Dict[str, Type[BaseEvent]] = {}

    @classmethod
    def register_event_class(cls, event_type: str, event_class: Type[BaseEvent]):
        """Register an event class for a specific event type."""
        cls._event_classes[event_type] = event_class

    @classmethod
    def create_event(cls, parsed_line) -> BaseEvent:
        """
        Create a specific event object from a parsed line.

        Args:
            parsed_line: ParsedLine object from tokenizer

        Returns:
            Appropriate event object
        """
        event_type = parsed_line.event_type

        # Special handling for meta events
        if event_type == "ENCOUNTER_START" or event_type == "ENCOUNTER_END":
            return cls._create_encounter_event(parsed_line)
        elif event_type.startswith("CHALLENGE_MODE_"):
            return cls._create_challenge_mode_event(parsed_line)
        elif event_type == "COMBATANT_INFO":
            return cls._create_combatant_info(parsed_line)

        # Handle combat events
        event = cls._create_base_event(parsed_line)

        # Add spell information if present
        if parsed_line.prefix_params and event_type.startswith("SPELL_"):
            if len(parsed_line.prefix_params) >= 3:
                event.spell_id = parsed_line.prefix_params[0]
                event.spell_name = parsed_line.prefix_params[1]
                event.spell_school = parsed_line.prefix_params[2]

        # Add suffix-specific data
        if "_DAMAGE" in event_type:
            event = cls._add_damage_info(event, parsed_line.suffix_params)
        elif "_HEAL" in event_type:
            event = cls._add_heal_info(event, parsed_line.suffix_params)
        elif "_AURA_" in event_type:
            event = cls._add_aura_info(event, parsed_line.suffix_params)

        return event

    @classmethod
    def _create_base_event(cls, parsed_line) -> BaseEvent:
        """Create base event with common parameters."""
        event = BaseEvent(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line
        )

        # Add base parameters if available
        if len(parsed_line.base_params) >= 10:
            event.hide_caster = parsed_line.base_params[0]
            event.source_guid = parsed_line.base_params[1]
            event.source_name = parsed_line.base_params[2]
            event.source_flags = parsed_line.base_params[3]
            event.source_raid_flags = parsed_line.base_params[4]
            event.dest_guid = parsed_line.base_params[5]
            event.dest_name = parsed_line.base_params[6]
            event.dest_flags = parsed_line.base_params[7]
            event.dest_raid_flags = parsed_line.base_params[8]

        # Create specific event type if it has spell data
        if parsed_line.event_type.startswith("SPELL_"):
            event = SpellEvent(**event.__dict__)

        return event

    @classmethod
    def _create_encounter_event(cls, parsed_line) -> EncounterEvent:
        """Create encounter start/end event."""
        event = EncounterEvent(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line
        )

        params = parsed_line.suffix_params
        if len(params) >= 4:
            event.encounter_id = params[0]
            event.encounter_name = params[1]
            event.difficulty_id = params[2]
            event.group_size = params[3]

        # ENCOUNTER_START has instance_id parameter
        if parsed_line.event_type == "ENCOUNTER_START" and len(params) > 4:
            event.instance_id = params[4]

        # ENCOUNTER_END has additional parameters
        if parsed_line.event_type == "ENCOUNTER_END" and len(params) >= 6:
            event.success = params[4] == 1  # params[4] is the success field
            event.duration = params[5]      # params[5] is the duration_ms field

        return event

    @classmethod
    def _create_challenge_mode_event(cls, parsed_line) -> ChallengeModeEvent:
        """Create Mythic+ start/end event."""
        event = ChallengeModeEvent(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line
        )

        params = parsed_line.suffix_params

        if parsed_line.event_type == "CHALLENGE_MODE_START":
            if len(params) >= 4:
                event.zone_name = params[0]
                event.instance_id = params[1]
                event.challenge_id = params[2]
                event.keystone_level = params[3]
                # Affix IDs are in an array at params[4]
                if len(params) > 4 and isinstance(params[4], list):
                    event.affix_ids = params[4]

        elif parsed_line.event_type == "CHALLENGE_MODE_END":
            if len(params) >= 6:
                event.instance_id = params[0]
                event.success = params[1] == 1
                event.keystone_level = params[2]
                event.duration = params[3] / 1000.0  # Convert to seconds

        return event

    @classmethod
    def _create_combatant_info(cls, parsed_line) -> CombatantInfo:
        """Create combatant info event."""
        event = CombatantInfo(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line
        )

        # COMBATANT_INFO has a complex structure
        # This is a simplified version - full parsing would be more complex
        params = parsed_line.suffix_params
        if len(params) >= 2:
            event.player_guid = params[0]
            event.player_name = params[1] if params[1] else "Unknown"

        return event

    @classmethod
    def _add_damage_info(cls, event: BaseEvent, params: List[Any]) -> DamageEvent:
        """Add damage-specific information to event."""
        damage_event = DamageEvent(**event.__dict__)

        # Damage parameters: amount, overkill, school, resisted, blocked, absorbed, critical, glancing, crushing
        if len(params) >= 6:
            damage_event.amount = params[0] or 0
            damage_event.overkill = params[1] or 0
            damage_event.school = params[2] or 0
            damage_event.resisted = params[3] or 0
            damage_event.blocked = params[4] or 0
            damage_event.absorbed = params[5] or 0

        if len(params) >= 9:
            damage_event.critical = bool(params[6])
            damage_event.glancing = bool(params[7])
            damage_event.crushing = bool(params[8])

        return damage_event

    @classmethod
    def _add_heal_info(cls, event: BaseEvent, params: List[Any]) -> HealEvent:
        """Add heal-specific information to event."""
        heal_event = HealEvent(**event.__dict__)

        # Heal parameters: amount, overhealing, absorbed, critical
        if len(params) >= 3:
            heal_event.amount = params[0] or 0
            heal_event.overhealing = params[1] or 0
            heal_event.absorbed = params[2] or 0

        if len(params) >= 4:
            heal_event.critical = bool(params[3])

        return heal_event

    @classmethod
    def _add_aura_info(cls, event: BaseEvent, params: List[Any]) -> AuraEvent:
        """Add aura-specific information to event."""
        aura_event = AuraEvent(**event.__dict__)

        # Aura parameters: auraType, [amount/stacks for DOSE events]
        if len(params) >= 1:
            aura_event.aura_type = params[0]

        if "DOSE" in event.event_type and len(params) >= 2:
            aura_event.stacks = params[1] or 1

        return aura_event