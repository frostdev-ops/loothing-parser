"""
Event classes and factory for WoW combat log events.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass, field
from enum import Enum

try:
    from src.config.wow_data import is_flask_buff, is_food_buff, get_spec_name
except ImportError:
    # Fallback if config module not available
    def is_flask_buff(spell_id):
        return False

    def is_food_buff(spell_id):
        return False

    def get_spec_name(spec_id):
        return f"Spec {spec_id}"


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

    # Environmental and other damage types
    ENVIRONMENTAL_DAMAGE = "ENVIRONMENTAL_DAMAGE"
    DAMAGE_SPLIT = "DAMAGE_SPLIT"
    RANGE_DAMAGE = "RANGE_DAMAGE"
    SWING_DAMAGE_LANDED = "SWING_DAMAGE_LANDED"

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
    source_server: Optional[str] = None
    source_region: Optional[str] = None
    source_flags: Optional[int] = None
    source_raid_flags: Optional[int] = None
    dest_guid: Optional[str] = None
    dest_name: Optional[str] = None
    dest_server: Optional[str] = None
    dest_region: Optional[str] = None
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

    def _parse_character_names(self) -> None:
        """Parse source and destination names into components."""
        from src.models.character import parse_character_name

        # Parse source name if it's a player
        if self.source_name and self.is_player_source():
            parsed = parse_character_name(self.source_name)
            # Keep original name and add parsed components
            self.source_name = parsed["name"]
            self.source_server = parsed["server"]
            self.source_region = parsed["region"]

        # Parse destination name if it's a player
        if self.dest_name and self.is_player_dest():
            parsed = parse_character_name(self.dest_name)
            # Keep original name and add parsed components
            self.dest_name = parsed["name"]
            self.dest_server = parsed["server"]
            self.dest_region = parsed["region"]

    def get_source_full_name(self) -> Optional[str]:
        """Get the full source name with server and region."""
        if not self.source_name:
            return None

        parts = [self.source_name]
        if self.source_server:
            parts.append(self.source_server)
        if self.source_region:
            parts.append(self.source_region)
        return "-".join(parts)

    def get_dest_full_name(self) -> Optional[str]:
        """Get the full destination name with server and region."""
        if not self.dest_name:
            return None

        parts = [self.dest_name]
        if self.dest_server:
            parts.append(self.dest_server)
        if self.dest_region:
            parts.append(self.dest_region)
        return "-".join(parts)

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
        # Ensure effective healing is never negative (protect against parsing errors)
        return max(0, self.amount - self.overhealing)


@dataclass
class AuraEvent(SpellEvent):
    """Event for buff/debuff application or removal."""

    aura_type: Optional[str] = None  # BUFF or DEBUFF
    stacks: int = 1


@dataclass
class AbsorbEvent(BaseEvent):
    """Event for damage absorption by shields."""

    # Original damage event info
    attacker_guid: str = ""
    attacker_name: str = ""
    target_guid: str = ""
    target_name: str = ""

    # Absorber info (who provided the shield)
    absorber_guid: str = ""
    absorber_name: str = ""

    # Shield spell info
    shield_spell_id: int = 0
    shield_spell_name: str = ""
    shield_spell_school: int = 0

    # Amount absorbed
    amount_absorbed: int = 0


@dataclass
class EncounterEvent(BaseEvent):
    """Event for raid encounter start/end."""

    encounter_id: int = 0
    encounter_name: str = ""
    difficulty_id: int = 0
    group_size: int = 0
    instance_id: int = 0
    success: Optional[bool] = None  # Only for ENCOUNTER_END
    duration: Optional[int] = None  # Only for ENCOUNTER_END (in ms)


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
class EquippedItem:
    """Represents an equipped item with full details."""

    item_id: int = 0
    item_level: int = 0
    gems: tuple = field(default_factory=tuple)
    enchants: tuple = field(default_factory=tuple)
    bonus_ids: tuple = field(default_factory=tuple)

    def has_enchant(self) -> bool:
        """Check if item has any enchants."""
        return bool(self.enchants and any(e for e in self.enchants if e != 0))

    def get_gem_count(self) -> int:
        """Get number of gems socketed."""
        return len([g for g in self.gems if g != 0]) if self.gems else 0


@dataclass
class Talent:
    """Represents a single talent choice."""

    talent_id: int = 0
    spell_id: int = 0
    rank: int = 1


@dataclass
class ActiveAura:
    """Represents an active buff/debuff."""

    source_guid: str = ""
    spell_id: int = 0
    stacks: int = 1


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
    versatility_healing: float = 0.0
    versatility_taken: float = 0.0
    armor: int = 0
    spec_id: int = 0

    # Comprehensive talent data
    talents_raw: List[tuple] = field(default_factory=list)
    talents: List[Talent] = field(default_factory=list)
    pvp_talents: tuple = field(default_factory=tuple)

    # Equipment with full details
    equipped_items: List[EquippedItem] = field(default_factory=list)

    # Active buffs/consumables/auras
    active_auras: List[ActiveAura] = field(default_factory=list)

    # Raw arrays for debugging
    talents_array: List[Any] = field(default_factory=list)
    items_array: List[Any] = field(default_factory=list)
    auras_array: List[Any] = field(default_factory=list)

    def get_flask(self) -> Optional[ActiveAura]:
        """Get active flask if any."""
        for aura in self.active_auras:
            if is_flask_buff(aura.spell_id):
                return aura
        return None

    def get_food_buff(self) -> Optional[ActiveAura]:
        """Get active food buff if any."""
        for aura in self.active_auras:
            if is_food_buff(aura.spell_id):
                return aura
        return None

    def get_weapon_enchants(self) -> List[int]:
        """Get enchant IDs from weapons."""
        enchants = []
        # Weapons are typically in first few slots
        for item in self.equipped_items[:2]:  # Main hand and off hand
            if item.has_enchant():
                enchants.extend([e for e in item.enchants if e != 0])
        return enchants

    def get_total_gems(self) -> int:
        """Get total number of gems across all equipment."""
        return sum(item.get_gem_count() for item in self.equipped_items)

    def get_average_item_level(self) -> float:
        """Calculate average item level of equipped gear."""
        if not self.equipped_items:
            return 0.0
        valid_items = [item for item in self.equipped_items if item.item_level > 0]
        if not valid_items:
            return 0.0
        return sum(item.item_level for item in valid_items) / len(valid_items)

    def has_consumables(self) -> bool:
        """Check if player has any consumables active."""
        return bool(self.get_flask() or self.get_food_buff())

    def get_talent_build_string(self) -> str:
        """Get a compact representation of talent choices."""
        if not self.talents:
            return ""
        return ",".join(str(talent.talent_id) for talent in self.talents[:10])  # First 10 talents

    def is_fully_enchanted(self) -> bool:
        """Check if all enchantable items have enchants."""
        # Check main hand, off hand, rings, cloak, etc.
        enchantable_slots = self.equipped_items[:8]  # First 8 slots typically enchantable
        if not enchantable_slots:
            return False
        return all(item.has_enchant() for item in enchantable_slots if item.item_id > 0)


class EventFactory:
    """Factory for creating specific event objects from parsed lines."""

    _event_classes: Dict[str, Type[BaseEvent]] = {}

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Safely convert a value to int, returning default on failure."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

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
        elif event_type == "SPELL_ABSORBED":
            return cls._create_absorb_event(parsed_line)

        # Handle combat events - create correct base type first
        if event_type.startswith("SPELL_"):
            event = cls._create_spell_base_event(parsed_line)
        else:
            event = cls._create_base_event(parsed_line)

        # Add suffix-specific data
        # When ACL is enabled, prefer SWING_DAMAGE_LANDED over SWING_DAMAGE for accuracy
        if ("_DAMAGE" in event_type or event_type in ["RANGE_DAMAGE"]) and event_type not in [
            "DAMAGE_SPLIT",
            "SWING_DAMAGE",  # Exclude SWING_DAMAGE in favor of SWING_DAMAGE_LANDED when ACL is enabled
        ]:
            event = cls._add_damage_info(event, parsed_line.suffix_params)
        elif "_HEAL" in event_type and event_type != "SPELL_HEAL_ABSORBED":
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
            raw_line=parsed_line.raw_line,
        )

        # Add base parameters if available
        # Standard combat events have 8 core parameters (no hide_caster):
        # sourceGUID, sourceName, sourceFlags, sourceRaidFlags,
        # destGUID, destName, destFlags, destRaidFlags
        if len(parsed_line.base_params) >= 8:
            event.source_guid = parsed_line.base_params[0]
            event.source_name = parsed_line.base_params[1]
            event.source_flags = cls._safe_int(parsed_line.base_params[2])
            event.source_raid_flags = cls._safe_int(parsed_line.base_params[3])
            event.dest_guid = parsed_line.base_params[4]
            event.dest_name = parsed_line.base_params[5]
            event.dest_flags = cls._safe_int(parsed_line.base_params[6])
            event.dest_raid_flags = cls._safe_int(parsed_line.base_params[7])

        # Parse character names into components
        event._parse_character_names()

        return event

    @classmethod
    def _create_spell_base_event(cls, parsed_line) -> SpellEvent:
        """Create spell event with common and spell-specific parameters."""
        event = SpellEvent(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line,
        )

        # Add base parameters if available
        if len(parsed_line.base_params) >= 8:
            event.source_guid = parsed_line.base_params[0]
            event.source_name = parsed_line.base_params[1]
            event.source_flags = cls._safe_int(parsed_line.base_params[2])
            event.source_raid_flags = cls._safe_int(parsed_line.base_params[3])
            event.dest_guid = parsed_line.base_params[4]
            event.dest_name = parsed_line.base_params[5]
            event.dest_flags = cls._safe_int(parsed_line.base_params[6])
            event.dest_raid_flags = cls._safe_int(parsed_line.base_params[7])

        # Add spell parameters if present
        if parsed_line.prefix_params and len(parsed_line.prefix_params) >= 3:
            event.spell_id = cls._safe_int(parsed_line.prefix_params[0])
            event.spell_name = parsed_line.prefix_params[1]
            event.spell_school = cls._safe_int(parsed_line.prefix_params[2])

        # Parse character names into components
        event._parse_character_names()

        return event

    @classmethod
    def _create_encounter_event(cls, parsed_line) -> EncounterEvent:
        """Create encounter start/end event."""
        event = EncounterEvent(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line,
        )

        params = parsed_line.suffix_params
        if len(params) >= 4:
            event.encounter_id = cls._safe_int(params[0])
            event.encounter_name = params[1]
            event.difficulty_id = cls._safe_int(params[2])
            event.group_size = cls._safe_int(params[3])

        # ENCOUNTER_START has instance_id parameter
        if parsed_line.event_type == "ENCOUNTER_START" and len(params) > 4:
            event.instance_id = cls._safe_int(params[4])

        # ENCOUNTER_END has additional parameters
        if parsed_line.event_type == "ENCOUNTER_END" and len(params) >= 6:
            event.success = cls._safe_int(params[4]) == 1  # params[4] is the success field
            event.duration = cls._safe_int(params[5])  # params[5] is the duration_ms field

        return event

    @classmethod
    def _create_challenge_mode_event(cls, parsed_line) -> ChallengeModeEvent:
        """Create Mythic+ start/end event."""
        event = ChallengeModeEvent(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line,
        )

        params = parsed_line.suffix_params

        if parsed_line.event_type == "CHALLENGE_MODE_START":
            if len(params) >= 4:
                event.zone_name = params[0]
                event.instance_id = cls._safe_int(params[1])
                event.challenge_id = cls._safe_int(params[2])
                event.keystone_level = cls._safe_int(params[3])
                # Affix IDs are in an array at params[4]
                if len(params) > 4 and isinstance(params[4], list):
                    event.affix_ids = [cls._safe_int(affix_id) for affix_id in params[4]]

        elif parsed_line.event_type == "CHALLENGE_MODE_END":
            if len(params) >= 6:
                event.instance_id = cls._safe_int(params[0])
                event.success = cls._safe_int(params[1]) == 1
                event.keystone_level = cls._safe_int(params[2])
                event.duration = cls._safe_int(params[3]) / 1000.0  # Convert to seconds

        return event

    @classmethod
    def _create_combatant_info(cls, parsed_line) -> CombatantInfo:
        """Create combatant info event with comprehensive character data."""
        event = CombatantInfo(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line,
        )

        # COMBATANT_INFO format: playerGUID, faction, strength, agility, stamina, intelligence,
        # dodge, parry, block, crit_melee, crit_ranged, crit_spell, speed, lifesteal,
        # haste_melee, haste_ranged, haste_spell, avoidance, mastery, versatility_damage,
        # versatility_heal, versatility_taken, armor, spec_id, talents[], pvp_talents[],
        # items[], interesting_auras[], unknown_fields...
        params = parsed_line.suffix_params

        if len(params) >= 24:
            event.player_guid = params[0] or ""
            event.faction = params[1] or 0
            event.strength = params[2] or 0
            event.agility = params[3] or 0
            event.stamina = params[4] or 0
            event.intelligence = params[5] or 0
            event.dodge = params[6] or 0.0
            event.parry = params[7] or 0.0
            event.block = params[8] or 0.0
            event.crit_melee = params[9] or 0.0
            event.crit_ranged = params[10] or 0.0
            event.crit_spell = params[11] or 0.0
            event.speed = params[12] or 0.0
            event.lifesteal = params[13] or 0.0
            event.haste_melee = params[14] or 0.0
            event.haste_ranged = params[15] or 0.0
            event.haste_spell = params[16] or 0.0
            event.avoidance = params[17] or 0.0
            event.mastery = params[18] or 0.0
            event.versatility_damage = params[19] or 0.0
            event.versatility_healing = params[20] or 0.0
            event.versatility_taken = params[21] or 0.0
            event.armor = params[22] or 0
            event.spec_id = params[23] or 0

            # Parse complex arrays if present
            if len(params) >= 27:
                # Talents array: [(talent_id, spell_id, rank), ...]
                if isinstance(params[24], list):
                    event.talents_array = params[24]
                    event.talents_raw = params[24]
                    event.talents = []
                    for talent_tuple in params[24]:
                        if isinstance(talent_tuple, tuple) and len(talent_tuple) >= 3:
                            event.talents.append(
                                Talent(
                                    talent_id=talent_tuple[0],
                                    spell_id=talent_tuple[1],
                                    rank=talent_tuple[2],
                                )
                            )

                # PvP talents tuple: (talent1, talent2, talent3, talent4)
                if len(params) > 25:
                    if isinstance(params[25], tuple):
                        event.pvp_talents = params[25]
                    elif isinstance(params[25], list):
                        event.pvp_talents = tuple(params[25])

                # Items array: [(item_id, item_level, gems_tuple, enchants_tuple, bonus_ids_tuple), ...]
                if len(params) > 26 and isinstance(params[26], list):
                    event.items_array = params[26]
                    event.equipped_items = []
                    for item_data in params[26]:
                        if isinstance(item_data, tuple) and len(item_data) >= 5:
                            item = EquippedItem(
                                item_id=item_data[0] or 0,
                                item_level=item_data[1] or 0,
                                gems=item_data[2] if isinstance(item_data[2], tuple) else (),
                                enchants=item_data[3] if isinstance(item_data[3], tuple) else (),
                                bonus_ids=item_data[4] if isinstance(item_data[4], tuple) else (),
                            )
                            event.equipped_items.append(item)

                # Active auras/buffs: [source_guid, spell_id, stacks, ...]
                if len(params) > 27:
                    auras_data = params[27]
                    if isinstance(auras_data, list):
                        event.auras_array = auras_data
                        event.active_auras = []
                        # Parse auras in groups of 3: source_guid, spell_id, stacks
                        for i in range(0, len(auras_data), 3):
                            if i + 2 < len(auras_data):
                                aura = ActiveAura(
                                    source_guid=str(auras_data[i] or ""),
                                    spell_id=auras_data[i + 1] or 0,
                                    stacks=auras_data[i + 2] or 1,
                                )
                                event.active_auras.append(aura)

        # Extract player name from other sources if needed
        if event.player_guid and not event.player_name:
            event.player_name = "Unknown"

        return event

    @classmethod
    def _create_absorb_event(cls, parsed_line) -> AbsorbEvent:
        """Create absorption event from SPELL_ABSORBED line."""
        event = AbsorbEvent(
            timestamp=parsed_line.timestamp,
            event_type=parsed_line.event_type,
            raw_line=parsed_line.raw_line,
        )

        # SPELL_ABSORBED structure from our analysis:
        # Standard base params first (8 params), then suffix params:
        # absorber_guid,absorber_name,absorber_flags,absorber_raid_flags,
        # shield_spell_id,shield_spell_name,shield_spell_school,
        # amount_absorbed,total_absorbed

        # Base parameters for SPELL_ABSORBED have extended format:
        # attacker_guid, attacker_name, attacker_flags, attacker_raid_flags,
        # target_guid, target_name, target_flags, target_raid_flags,
        # absorber_guid, absorber_name, absorber_flags, absorber_raid_flags
        if len(parsed_line.base_params) >= 8:
            event.attacker_guid = parsed_line.base_params[0]
            event.attacker_name = parsed_line.base_params[1]
            event.target_guid = parsed_line.base_params[4]
            event.target_name = parsed_line.base_params[5]

        if len(parsed_line.base_params) >= 12:
            event.absorber_guid = parsed_line.base_params[8]
            event.absorber_name = parsed_line.base_params[9]

        # Suffix parameters (SPELL_ABSORBED specific)
        params = parsed_line.suffix_params
        if len(params) >= 5:
            # Shield spell info (corrected positions based on actual log format)
            event.shield_spell_id = cls._safe_int(params[1])
            event.shield_spell_name = params[2]
            event.shield_spell_school = cls._safe_int(params[3])

            # Amount absorbed
            event.amount_absorbed = cls._safe_int(params[4])

            # Note: Absorber GUID/name would need to be extracted from the main absorber info
            # in the base params, not the suffix params

        return event

    @classmethod
    def _add_damage_info(cls, event: BaseEvent, params: List[Any]) -> DamageEvent:
        """Add damage-specific information to event."""
        import logging

        logger = logging.getLogger(__name__)

        # Handle different event types properly
        if event.event_type.startswith("SWING_"):
            # SWING events use BaseEvent as base, create DamageEvent manually
            damage_event = DamageEvent(
                timestamp=event.timestamp,
                event_type=event.event_type,
                raw_line=event.raw_line,
                source_guid=event.source_guid,
                source_name=event.source_name,
                source_flags=event.source_flags,
                source_raid_flags=event.source_raid_flags,
                dest_guid=event.dest_guid,
                dest_name=event.dest_name,
                dest_flags=event.dest_flags,
                dest_raid_flags=event.dest_raid_flags,
            )
            logger.debug(
                f"Created SWING DamageEvent: {event.event_type}, source: {event.source_guid}, dest: {event.dest_guid}"
            )
        else:
            # SPELL_ events and others use event.__dict__
            damage_event = DamageEvent(**event.__dict__)
            logger.debug(
                f"Created SPELL DamageEvent: {event.event_type}, source: {event.source_guid}, dest: {event.dest_guid}"
            )

        # Detect Advanced Combat Logging by parameter count
        # Advanced Combat Logging inserts unit info (19 fields) before damage parameters
        damage_offset = 0
        if len(params) >= 25:  # Advanced Combat Logging detected
            # Skip unit info fields: target_guid, info_guid, current_hp, max_hp, attack_power,
            # spell_power, armor, resources, position, etc. (19 fields total)
            damage_offset = 19

        # Damage parameters: amount, overkill, school, resisted, blocked, absorbed, critical, glancing, crushing
        # For Advanced Combat Logging, these come after the 19 unit info fields
        min_params_needed = damage_offset + 9
        if len(params) >= min_params_needed:
            damage_event.amount = cls._safe_int(params[damage_offset])  # Actual damage amount
            damage_event.overkill = cls._safe_int(params[damage_offset + 1])  # Overkill amount
            damage_event.school = cls._safe_int(params[damage_offset + 2])
            damage_event.resisted = cls._safe_int(params[damage_offset + 3])
            damage_event.blocked = cls._safe_int(params[damage_offset + 4])
            damage_event.absorbed = cls._safe_int(params[damage_offset + 5])
            damage_event.critical = bool(params[damage_offset + 6])
            damage_event.glancing = bool(params[damage_offset + 7])
            damage_event.crushing = bool(params[damage_offset + 8])
        elif len(params) >= damage_offset + 6:
            # Fallback for shorter parameter lists
            damage_event.amount = cls._safe_int(params[damage_offset])
            damage_event.overkill = cls._safe_int(params[damage_offset + 1])
            damage_event.school = cls._safe_int(params[damage_offset + 2])
            damage_event.resisted = cls._safe_int(params[damage_offset + 3])
            damage_event.blocked = cls._safe_int(params[damage_offset + 4])
            damage_event.absorbed = cls._safe_int(params[damage_offset + 5])

        logger.debug(
            f"Returning DamageEvent type: {type(damage_event).__name__}, amount: {damage_event.amount}"
        )
        return damage_event

    @classmethod
    def _add_heal_info(cls, event: BaseEvent, params: List[Any]) -> HealEvent:
        """Add heal-specific information to event."""
        # Handle different event types properly
        if event.event_type.startswith("SWING_"):
            # SWING events use BaseEvent as base, create HealEvent manually
            heal_event = HealEvent(
                timestamp=event.timestamp,
                event_type=event.event_type,
                raw_line=event.raw_line,
                source_guid=event.source_guid,
                source_name=event.source_name,
                source_flags=event.source_flags,
                source_raid_flags=event.source_raid_flags,
                dest_guid=event.dest_guid,
                dest_name=event.dest_name,
                dest_flags=event.dest_flags,
                dest_raid_flags=event.dest_raid_flags,
            )
        else:
            # SPELL_ events and others use event.__dict__
            heal_event = HealEvent(**event.__dict__)

        # Detect Advanced Combat Logging by parameter count
        # Advanced Combat Logging inserts unit info (19 fields) before heal parameters
        heal_offset = 0
        if len(params) >= 25:  # Advanced Combat Logging detected
            # Skip unit info fields: target_guid, info_guid, current_hp, max_hp, attack_power,
            # spell_power, armor, resources, position, etc. (19 fields total)
            heal_offset = 19

        # Debug logging for heal parsing
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Healing params count: {len(params)}, heal_offset: {heal_offset}")
        if len(params) > heal_offset:
            logger.debug(f"Heal params at offset {heal_offset}: {params[heal_offset:heal_offset+5]}")

        # Heal parameters: amount, overhealing, absorbed, critical
        # For Advanced Combat Logging, these come after the 19 unit info fields
        min_params_needed = heal_offset + 4
        if len(params) >= min_params_needed:
            heal_event.amount = cls._safe_int(
                params[heal_offset]
            )  # Total healing including overheal
            heal_event.overhealing = cls._safe_int(params[heal_offset + 1])  # Overhealing amount
            heal_event.absorbed = cls._safe_int(params[heal_offset + 2])  # Absorbed healing
            heal_event.critical = bool(params[heal_offset + 3])  # Critical heal flag
        elif len(params) >= heal_offset + 2:
            # Fallback for shorter parameter lists
            heal_event.amount = cls._safe_int(params[heal_offset])
            heal_event.overhealing = (
                cls._safe_int(params[heal_offset + 1]) if len(params) > heal_offset + 1 else 0
            )

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
