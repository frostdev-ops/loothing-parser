"""
Unified encounter model for both Raid and Mythic+ encounters.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum

from src.parser.events import BaseEvent
from src.models.enhanced_character import EnhancedCharacter
from src.models.combat_periods import CombatPeriod


class EncounterType(Enum):
    """Type of encounter."""

    RAID = "raid"
    MYTHIC_PLUS = "mythic_plus"
    DUNGEON = "dungeon"
    UNKNOWN = "unknown"


@dataclass
class NPCCombatant:
    """Non-player combatant (NPC/Enemy) tracking."""

    guid: str
    name: str
    npc_id: Optional[int] = None

    # Combat metrics
    damage_done: int = 0
    healing_done: int = 0
    damage_taken: int = 0
    deaths: int = 0

    # Abilities used
    abilities_used: Dict[int, str] = field(default_factory=dict)  # spell_id -> spell_name

    # First and last seen
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    # Boss/Elite status
    is_boss: bool = False
    is_elite: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "npc_id": self.npc_id,
            "damage_done": self.damage_done,
            "healing_done": self.healing_done,
            "damage_taken": self.damage_taken,
            "deaths": self.deaths,
            "abilities_count": len(self.abilities_used),
            "is_boss": self.is_boss,
            "is_elite": self.is_elite,
        }


@dataclass
class Fight:
    """
    A fight represents a discrete combat segment within an encounter.

    For raid encounters, typically one fight = entire encounter.
    For M+ dungeons, multiple fights (boss fights + trash segments).
    """

    fight_id: int
    fight_name: str

    # Participants
    players: Dict[str, EnhancedCharacter] = field(default_factory=dict)
    enemy_forces: Dict[str, NPCCombatant] = field(default_factory=dict)

    # Timing
    start_time: datetime = None
    end_time: Optional[datetime] = None
    duration: float = 0.0
    combat_time: float = 0.0  # Time actually in combat

    # Combat periods (active combat vs downtime)
    combat_periods: List[CombatPeriod] = field(default_factory=list)

    # Fight type
    is_boss: bool = False  # True for dungeon bosses in M+
    is_trash: bool = False  # True for trash segments in M+

    # Fight outcome
    success: Optional[bool] = None
    wipe_percentage: Optional[float] = None  # Boss health % at wipe

    def add_player(self, guid: str, character: EnhancedCharacter):
        """Add a player to the fight."""
        self.players[guid] = character

    def add_enemy(self, guid: str, name: str) -> NPCCombatant:
        """Add an enemy to the fight."""
        if guid not in self.enemy_forces:
            self.enemy_forces[guid] = NPCCombatant(guid=guid, name=name)
        return self.enemy_forces[guid]

    def calculate_metrics(self):
        """Calculate fight metrics."""
        if self.start_time and self.end_time:
            self.duration = (self.end_time - self.start_time).total_seconds()

        # Calculate total combat time from periods
        if self.combat_periods:
            self.combat_time = sum(period.duration for period in self.combat_periods)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "fight_id": self.fight_id,
            "fight_name": self.fight_name,
            "fight_type": "boss" if self.is_boss else ("trash" if self.is_trash else "normal"),
            "players_count": len(self.players),
            "enemy_count": len(self.enemy_forces),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": round(self.duration, 1),
            "combat_time": round(self.combat_time, 1),
            "success": self.success,
            "players": {guid: char.to_dict() for guid, char in self.players.items()},
            "enemy_forces": {guid: npc.to_dict() for guid, npc in self.enemy_forces.items()},
        }


@dataclass
class EncounterMetrics:
    """Aggregated metrics for an entire encounter."""

    # Total metrics
    total_damage: int = 0
    total_healing: int = 0
    total_overhealing: int = 0
    total_deaths: int = 0

    # Raid-wide rates
    raid_dps: float = 0.0
    raid_hps: float = 0.0
    combat_raid_dps: float = 0.0  # DPS during combat periods only
    combat_raid_hps: float = 0.0  # HPS during combat periods only

    # Player counts
    player_count: int = 0
    tanks_count: int = 0
    healers_count: int = 0
    dps_count: int = 0

    # Activity metrics
    avg_activity: float = 0.0
    avg_item_level: float = 0.0

    # Mythic+ specific
    enemy_forces_percent: Optional[float] = None
    time_remaining: Optional[float] = None
    keystone_upgrades: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_damage": self.total_damage,
            "total_healing": self.total_healing,
            "total_overhealing": self.total_overhealing,
            "total_deaths": self.total_deaths,
            "raid_dps": round(self.raid_dps),
            "raid_hps": round(self.raid_hps),
            "combat_raid_dps": round(self.combat_raid_dps),
            "combat_raid_hps": round(self.combat_raid_hps),
            "player_count": self.player_count,
            "composition": {
                "tanks": self.tanks_count,
                "healers": self.healers_count,
                "dps": self.dps_count,
            },
            "avg_activity": round(self.avg_activity, 1),
            "avg_item_level": round(self.avg_item_level, 1) if self.avg_item_level else None,
        }


@dataclass
class UnifiedEncounter:
    """
    Unified encounter model for both Raid and Mythic+ encounters.

    This provides a consistent interface for all encounter types while
    maintaining type-specific data where needed.
    """

    # Core identification
    encounter_type: EncounterType
    encounter_id: int
    encounter_name: str
    instance_id: Optional[int] = None
    instance_name: Optional[str] = None

    # Difficulty/Level
    difficulty: Optional[str] = None  # "Normal", "Heroic", "Mythic" for raids
    keystone_level: Optional[int] = None  # For M+
    affixes: List[int] = field(default_factory=list)  # M+ affixes

    # Timing
    start_time: datetime = None
    end_time: Optional[datetime] = None
    duration: float = 0.0
    combat_duration: float = 0.0

    # Pull tracking (for raids)
    pull_number: int = 1

    # Participants - using EnhancedCharacter for comprehensive tracking
    characters: Dict[str, EnhancedCharacter] = field(default_factory=dict)

    # Fights (combat segments)
    fights: List[Fight] = field(default_factory=list)
    current_fight: Optional[Fight] = None

    # All events (for detailed analysis)
    events: List[BaseEvent] = field(default_factory=list)

    # Combat periods
    combat_periods: List[CombatPeriod] = field(default_factory=list)

    # Aggregated metrics
    metrics: EncounterMetrics = field(default_factory=EncounterMetrics)

    # Success/Completion
    success: bool = False
    in_time: Optional[bool] = None  # For M+

    def add_character(self, guid: str, name: str) -> EnhancedCharacter:
        """Add or get a character."""
        if guid not in self.characters:
            from src.models.character import parse_character_name

            parsed = parse_character_name(name)

            self.characters[guid] = EnhancedCharacter(
                character_guid=guid,
                character_name=parsed["name"],
                server=parsed["server"],
                region=parsed["region"],
            )
        return self.characters[guid]

    def add_event(self, event: BaseEvent):
        """Add an event to the encounter."""
        self.events.append(event)

        # Route to current fight if exists
        if self.current_fight:
            # Track participants
            if event.source_guid and event.is_player_source():
                char = self.add_character(event.source_guid, event.source_name)
                if char.character_guid not in self.current_fight.players:
                    self.current_fight.add_player(char.character_guid, char)
            elif event.source_guid and not event.source_guid.startswith("0000"):
                self.current_fight.add_enemy(event.source_guid, event.source_name or "Unknown")

            if event.dest_guid and event.is_player_dest():
                char = self.add_character(event.dest_guid, event.dest_name)
                if char.character_guid not in self.current_fight.players:
                    self.current_fight.add_player(char.character_guid, char)
            elif event.dest_guid and not event.dest_guid.startswith("0000"):
                self.current_fight.add_enemy(event.dest_guid, event.dest_name or "Unknown")

    def start_fight(self, fight_name: str, start_time: datetime) -> Fight:
        """Start a new fight segment."""
        fight_id = len(self.fights) + 1
        fight = Fight(fight_id=fight_id, fight_name=fight_name, start_time=start_time)

        # Copy current characters to the fight
        for guid, char in self.characters.items():
            fight.add_player(guid, char)

        self.fights.append(fight)
        self.current_fight = fight
        return fight

    def end_fight(self, end_time: datetime, success: bool = None):
        """End the current fight."""
        if self.current_fight:
            self.current_fight.end_time = end_time
            self.current_fight.success = success
            self.current_fight.calculate_metrics()
            self.current_fight = None

    def calculate_metrics(self):
        """Calculate all encounter metrics."""
        # Calculate timing
        if self.start_time and self.end_time:
            self.duration = (self.end_time - self.start_time).total_seconds()

        # Calculate combat duration from periods
        self.combat_duration = sum(period.duration for period in self.combat_periods)

        # Calculate character metrics
        for character in self.characters.values():
            character.calculate_ability_metrics(self.duration)
            character.calculate_combat_metrics(self.combat_periods, self.duration)
            character.detect_role()

        # Aggregate encounter metrics
        self.metrics.player_count = len(self.characters)
        self.metrics.total_damage = sum(c.total_damage_done for c in self.characters.values())
        self.metrics.total_healing = sum(c.total_healing_done for c in self.characters.values())
        self.metrics.total_overhealing = sum(c.total_overhealing for c in self.characters.values())
        self.metrics.total_deaths = sum(c.death_count for c in self.characters.values())

        # Calculate DPS/HPS
        if self.duration > 0:
            self.metrics.raid_dps = self.metrics.total_damage / self.duration
            self.metrics.raid_hps = self.metrics.total_healing / self.duration

        if self.combat_duration > 0:
            self.metrics.combat_raid_dps = self.metrics.total_damage / self.combat_duration
            self.metrics.combat_raid_hps = self.metrics.total_healing / self.combat_duration

        # Role counts
        self.metrics.tanks_count = sum(1 for c in self.characters.values() if c.role == "tank")
        self.metrics.healers_count = sum(1 for c in self.characters.values() if c.role == "healer")
        self.metrics.dps_count = sum(1 for c in self.characters.values() if c.role == "dps")

        # Average metrics
        if self.metrics.player_count > 0:
            active_chars = [c for c in self.characters.values() if c.activity_percentage > 0]
            if active_chars:
                self.metrics.avg_activity = sum(c.activity_percentage for c in active_chars) / len(
                    active_chars
                )

            chars_with_ilvl = [c for c in self.characters.values() if c.item_level]
            if chars_with_ilvl:
                self.metrics.avg_item_level = sum(c.item_level for c in chars_with_ilvl) / len(
                    chars_with_ilvl
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "encounter_type": self.encounter_type.value,
            "encounter_id": self.encounter_id,
            "encounter_name": self.encounter_name,
            "instance_name": self.instance_name,
            "difficulty": self.difficulty,
            "keystone_level": self.keystone_level,
            "affixes": self.affixes,
            "pull_number": self.pull_number,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": round(self.duration, 1),
            "combat_duration": round(self.combat_duration, 1),
            "success": self.success,
            "in_time": self.in_time,
            "metrics": self.metrics.to_dict(),
            "fights": [fight.to_dict() for fight in self.fights],
            "characters": {guid: char.to_dict() for guid, char in self.characters.items()},
        }
