"""
Encounter models for raid bosses and Mythic+ dungeons.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum

from .character_events import CharacterEventStream


class Difficulty(Enum):
    """Raid difficulty levels."""

    LFR = 17
    NORMAL = 14
    HEROIC = 15
    MYTHIC = 16


class SegmentType(Enum):
    """Types of combat segments in M+."""

    BOSS = "boss"
    TRASH = "trash"
    MINIBOSS = "miniboss"
    TEEMING = "teeming"  # Extra trash from affixes


@dataclass
class Phase:
    """
    Represents a boss phase or combat transition.
    """

    phase_number: int
    phase_name: str
    start_time: float
    end_time: Optional[float] = None
    health_percentage: Optional[float] = None  # Boss health % at phase start

    @property
    def duration(self) -> float:
        """Calculate phase duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return 0.0


@dataclass
class RaidEvent:
    """
    Represents a raid-wide mechanic or event.
    """

    timestamp: float
    event_name: str
    spell_id: Optional[int] = None
    affected_players: List[str] = field(default_factory=list)


@dataclass
class RaidEncounter:
    """
    Single raid boss encounter with complete character tracking.

    This represents one pull attempt on a raid boss, containing
    all character event streams and encounter-specific data.
    """

    # Encounter identification
    encounter_id: int
    boss_name: str
    difficulty: Difficulty
    instance_id: int
    instance_name: Optional[str] = None

    # Pull information
    pull_number: int = 1  # Which attempt this is
    start_time: datetime = None
    end_time: Optional[datetime] = None
    success: bool = False
    wipe_percentage: Optional[float] = None  # Boss health % at wipe

    # Character data - the main focus
    characters: Dict[str, CharacterEventStream] = field(default_factory=dict)

    # Encounter mechanics
    phases: List[Phase] = field(default_factory=list)
    raid_events: List[RaidEvent] = field(default_factory=list)

    # Raid composition
    raid_size: int = 0
    tanks: List[str] = field(default_factory=list)
    healers: List[str] = field(default_factory=list)
    dps: List[str] = field(default_factory=list)

    # Metadata
    combat_length: float = 0.0  # Duration in seconds
    bloodlust_used: bool = False
    bloodlust_time: Optional[float] = None
    battle_resurrections: int = 0

    def add_character(self, character_guid: str, character_name: str) -> CharacterEventStream:
        """
        Add or get a character stream.

        Args:
            character_guid: Character's GUID
            character_name: Character's name

        Returns:
            CharacterEventStream for this character
        """
        if character_guid not in self.characters:
            self.characters[character_guid] = CharacterEventStream(
                character_guid=character_guid, character_name=character_name
            )
        return self.characters[character_guid]

    def calculate_metrics(self):
        """Calculate encounter-wide metrics."""
        if self.start_time and self.end_time:
            self.combat_length = (self.end_time - self.start_time).total_seconds()

        # Calculate raid composition
        self.raid_size = len(
            [c for c in self.characters.values() if not c.character_guid.startswith("Pet-")]
        )

        # Calculate per-character metrics
        for character in self.characters.values():
            character.calculate_activity(self.combat_length)

    def get_phase_at_time(self, timestamp: float) -> Optional[Phase]:
        """Get the phase active at a given timestamp."""
        for phase in self.phases:
            if phase.start_time <= timestamp:
                if phase.end_time is None or timestamp <= phase.end_time:
                    return phase
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "encounter_id": self.encounter_id,
            "boss_name": self.boss_name,
            "difficulty": self.difficulty.name,
            "pull_number": self.pull_number,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "success": self.success,
            "wipe_percentage": self.wipe_percentage,
            "combat_length": round(self.combat_length, 1),
            "raid_size": self.raid_size,
            "composition": {
                "tanks": len(self.tanks),
                "healers": len(self.healers),
                "dps": len(self.dps),
            },
            "characters": {guid: char.to_dict() for guid, char in self.characters.items()},
            "phases": len(self.phases),
            "raid_events": len(self.raid_events),
        }


@dataclass
class CombatSegment:
    """
    Individual combat section in Mythic+.

    Represents a continuous combat period - could be a boss,
    a trash pack, or multiple packs pulled together.
    """

    segment_id: int
    segment_type: SegmentType
    segment_name: Optional[str] = None  # Boss name or "Trash Pack"

    # Timing
    start_time: datetime = None
    end_time: Optional[datetime] = None
    duration: float = 0.0

    # Combat data
    characters: Dict[str, CharacterEventStream] = field(default_factory=dict)
    mob_count: int = 0
    mob_deaths: List[str] = field(default_factory=list)  # List of killed mob GUIDs

    # Progress tracking
    enemy_forces_start: float = 0.0  # % at segment start
    enemy_forces_end: float = 0.0  # % at segment end
    enemy_forces_gained: float = 0.0  # % gained in this segment

    def add_character(self, character_guid: str, character_name: str) -> CharacterEventStream:
        """Add or get a character stream for this segment."""
        if character_guid not in self.characters:
            self.characters[character_guid] = CharacterEventStream(
                character_guid=character_guid, character_name=character_name
            )
        return self.characters[character_guid]

    def calculate_metrics(self):
        """Calculate segment metrics."""
        if self.start_time and self.end_time:
            self.duration = (self.end_time - self.start_time).total_seconds()

        self.enemy_forces_gained = self.enemy_forces_end - self.enemy_forces_start

        # Calculate per-character metrics
        for character in self.characters.values():
            character.calculate_activity(self.duration)


@dataclass
class MythicPlusRun:
    """
    Complete Mythic+ dungeon run with all segments.

    Contains all combat segments (boss and trash) with
    character tracking throughout the entire dungeon.
    """

    # Dungeon information
    dungeon_id: int
    dungeon_name: str
    keystone_level: int

    # Affixes (as IDs)
    affixes: List[int] = field(default_factory=list)
    affix_names: List[str] = field(default_factory=list)

    # Timing
    start_time: datetime = None
    end_time: Optional[datetime] = None
    time_limit_seconds: int = 0
    actual_time_seconds: float = 0.0

    # Success criteria
    completed: bool = False
    in_time: bool = False
    num_deaths: int = 0
    time_remaining: float = 0.0  # Negative if over time

    # Combat segments (bosses and trash)
    segments: List[CombatSegment] = field(default_factory=list)
    boss_segments: List[CombatSegment] = field(default_factory=list)
    trash_segments: List[CombatSegment] = field(default_factory=list)

    # Overall character performance (aggregate across all segments)
    overall_characters: Dict[str, CharacterEventStream] = field(default_factory=dict)

    # Group composition
    group_members: List[str] = field(default_factory=list)
    group_classes: Dict[str, str] = field(default_factory=dict)  # guid -> class

    # Key depletion events
    death_penalties: List[float] = field(default_factory=list)  # Time penalties from deaths

    def add_segment(self, segment: CombatSegment):
        """Add a combat segment to the run."""
        self.segments.append(segment)

        if segment.segment_type == SegmentType.BOSS:
            self.boss_segments.append(segment)
        else:
            self.trash_segments.append(segment)

    def aggregate_character_data(self):
        """
        Aggregate character data across all segments.

        Creates overall character streams combining all segments.
        """
        for segment in self.segments:
            for char_guid, char_stream in segment.characters.items():
                if char_guid not in self.overall_characters:
                    self.overall_characters[char_guid] = CharacterEventStream(
                        character_guid=char_guid,
                        character_name=char_stream.character_name,
                        class_name=char_stream.class_name,
                        spec_name=char_stream.spec_name,
                    )

                # Combine data from segment into overall
                overall = self.overall_characters[char_guid]
                overall.total_damage_done += char_stream.total_damage_done
                overall.total_healing_done += char_stream.total_healing_done
                overall.total_damage_taken += char_stream.total_damage_taken
                overall.death_count += char_stream.death_count

                # Add all events
                overall.all_events.extend(char_stream.all_events)

        # Sort events chronologically
        for char_stream in self.overall_characters.values():
            char_stream.all_events.sort()

    def calculate_metrics(self):
        """Calculate run-wide metrics."""
        if self.start_time and self.end_time:
            self.actual_time_seconds = (self.end_time - self.start_time).total_seconds()

        self.time_remaining = self.time_limit_seconds - self.actual_time_seconds
        self.in_time = self.time_remaining >= 0

        # Count total deaths
        self.num_deaths = sum(char.death_count for char in self.overall_characters.values())

        # Calculate death penalties (5 seconds per death in most seasons)
        self.death_penalties = [5.0] * self.num_deaths

        # Calculate metrics for each segment
        for segment in self.segments:
            segment.calculate_metrics()

        # Calculate overall character metrics using combat periods
        from ..models.combat_periods import CombatPeriodDetector

        # Collect all events from all segments to detect combat periods
        all_events = []
        for segment in self.segments:
            for character in segment.characters.values():
                all_events.extend([ts_event.event for ts_event in character.all_events])

        # Sort events by timestamp
        all_events.sort(key=lambda e: e.timestamp)

        # Detect combat periods for the entire run
        if all_events:
            detector = CombatPeriodDetector(gap_threshold=5.0)
            combat_periods = detector.detect_periods(all_events)
        else:
            combat_periods = []

        # Use combat-aware activity calculation
        for character in self.overall_characters.values():
            character.calculate_combat_metrics(combat_periods, self.actual_time_seconds)

    @property
    def characters(self) -> Dict[str, CharacterEventStream]:
        """Provide access to overall character data via 'characters' property."""
        return self.overall_characters

    def get_segment_at_time(self, timestamp: float) -> Optional[CombatSegment]:
        """Get the segment active at a given timestamp."""
        for segment in self.segments:
            if segment.start_time:
                start = segment.start_time.timestamp()
                end = segment.end_time.timestamp() if segment.end_time else float("inf")
                if start <= timestamp <= end:
                    return segment
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "dungeon_id": self.dungeon_id,
            "dungeon_name": self.dungeon_name,
            "keystone_level": self.keystone_level,
            "affixes": self.affix_names,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "time_limit": self.time_limit_seconds,
            "actual_time": round(self.actual_time_seconds, 1),
            "completed": self.completed,
            "in_time": self.in_time,
            "time_remaining": round(self.time_remaining, 1),
            "deaths": self.num_deaths,
            "segments": {
                "total": len(self.segments),
                "bosses": len(self.boss_segments),
                "trash": len(self.trash_segments),
            },
            "characters": {guid: char.to_dict() for guid, char in self.overall_characters.items()},
        }
