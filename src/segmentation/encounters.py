"""
Encounter detection and segmentation for combat logs.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum

from src.parser.events import BaseEvent, EncounterEvent, ChallengeModeEvent


class FightType(Enum):
    """Type of combat encounter."""
    RAID_BOSS = "raid_boss"
    MYTHIC_PLUS = "mythic_plus"
    DUNGEON_BOSS = "dungeon_boss"
    TRASH = "trash"
    PVP = "pvp"
    UNKNOWN = "unknown"


@dataclass
class Fight:
    """
    Represents a single combat encounter or segment.
    """
    fight_id: int
    fight_type: FightType
    start_time: datetime
    end_time: Optional[datetime] = None
    encounter_id: Optional[int] = None
    encounter_name: Optional[str] = None
    difficulty: Optional[int] = None
    keystone_level: Optional[int] = None
    success: Optional[bool] = None
    duration: Optional[float] = None  # In seconds
    events: List[BaseEvent] = field(default_factory=list)
    participants: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_event(self, event: BaseEvent):
        """Add an event to this fight."""
        self.events.append(event)

        # Track participants
        if event.source_guid and event.source_guid != "0000000000000000":
            if event.source_guid not in self.participants:
                self.participants[event.source_guid] = {
                    'name': event.source_name,
                    'first_seen': event.timestamp,
                    'last_seen': event.timestamp,
                    'is_player': event.is_player_source(),
                    'is_pet': event.is_pet_source()
                }
            else:
                self.participants[event.source_guid]['last_seen'] = event.timestamp

    def finalize(self):
        """Finalize the fight with calculated metrics."""
        if self.events:
            self.start_time = self.events[0].timestamp
            self.end_time = self.events[-1].timestamp
            self.duration = (self.end_time - self.start_time).total_seconds()

    def is_complete(self) -> bool:
        """Check if the fight has ended properly."""
        return self.end_time is not None

    def get_player_count(self) -> int:
        """Get the number of players in this fight."""
        return sum(1 for p in self.participants.values() if p['is_player'])

    def get_duration_str(self) -> str:
        """Get human-readable duration string."""
        if not self.duration:
            return "Unknown"

        minutes = int(self.duration // 60)
        seconds = int(self.duration % 60)
        return f"{minutes}:{seconds:02d}"


class EncounterSegmenter:
    """
    Segments combat log events into discrete encounters and fights.
    """

    def __init__(self, trash_timeout: float = 10.0):
        """
        Initialize the encounter segmenter.

        Args:
            trash_timeout: Seconds of inactivity before ending trash segments
        """
        self.trash_timeout = trash_timeout
        self.current_fight: Optional[Fight] = None
        self.current_challenge_mode: Optional[Fight] = None
        self.fights: List[Fight] = []
        self.fight_counter = 0
        self.last_combat_time: Optional[datetime] = None

    def process_event(self, event: BaseEvent) -> Optional[Fight]:
        """
        Process an event and update fight segmentation.

        Args:
            event: The event to process

        Returns:
            Completed fight if one just ended, None otherwise
        """
        completed_fight = None

        # Handle encounter start/end
        if event.event_type == "ENCOUNTER_START":
            completed_fight = self._handle_encounter_start(event)
        elif event.event_type == "ENCOUNTER_END":
            completed_fight = self._handle_encounter_end(event)
        elif event.event_type == "CHALLENGE_MODE_START":
            completed_fight = self._handle_challenge_mode_start(event)
        elif event.event_type == "CHALLENGE_MODE_END":
            completed_fight = self._handle_challenge_mode_end(event)
        else:
            # Regular combat event
            self._handle_combat_event(event)

        return completed_fight

    def _handle_encounter_start(self, event: EncounterEvent) -> Optional[Fight]:
        """Handle ENCOUNTER_START event."""
        # End any current fight
        completed_fight = None
        if self.current_fight:
            self.current_fight.finalize()
            completed_fight = self.current_fight
            self.fights.append(self.current_fight)

        # Start new encounter
        self.fight_counter += 1
        fight_type = FightType.RAID_BOSS if event.difficulty_id >= 14 else FightType.DUNGEON_BOSS

        self.current_fight = Fight(
            fight_id=self.fight_counter,
            fight_type=fight_type,
            start_time=event.timestamp,
            encounter_id=event.encounter_id,
            encounter_name=event.encounter_name,
            difficulty=event.difficulty_id,
            metadata={'group_size': event.group_size, 'instance_id': event.instance_id}
        )
        self.current_fight.add_event(event)

        return completed_fight

    def _handle_encounter_end(self, event: EncounterEvent) -> Optional[Fight]:
        """Handle ENCOUNTER_END event."""
        if self.current_fight and self.current_fight.encounter_id == event.encounter_id:
            self.current_fight.add_event(event)
            self.current_fight.end_time = event.timestamp
            self.current_fight.success = event.success
            self.current_fight.duration = event.duration / 1000.0 if event.duration else None
            self.current_fight.finalize()

            # Store and clear current fight
            completed_fight = self.current_fight
            self.fights.append(self.current_fight)
            self.current_fight = None

            return completed_fight

        return None

    def _handle_challenge_mode_start(self, event: ChallengeModeEvent) -> Optional[Fight]:
        """Handle CHALLENGE_MODE_START event."""
        # End any current fight
        completed_fight = None
        if self.current_fight:
            self.current_fight.finalize()
            completed_fight = self.current_fight
            self.fights.append(self.current_fight)
            self.current_fight = None

        # Start Mythic+ dungeon tracking
        self.fight_counter += 1
        self.current_challenge_mode = Fight(
            fight_id=self.fight_counter,
            fight_type=FightType.MYTHIC_PLUS,
            start_time=event.timestamp,
            encounter_name=event.zone_name,
            keystone_level=event.keystone_level,
            metadata={
                'instance_id': event.instance_id,
                'challenge_id': event.challenge_id,
                'affix_ids': event.affix_ids
            }
        )
        self.current_challenge_mode.add_event(event)

        return completed_fight

    def _handle_challenge_mode_end(self, event: ChallengeModeEvent) -> Optional[Fight]:
        """Handle CHALLENGE_MODE_END event."""
        if self.current_challenge_mode:
            self.current_challenge_mode.add_event(event)
            self.current_challenge_mode.end_time = event.timestamp
            self.current_challenge_mode.success = event.success
            self.current_challenge_mode.duration = event.duration
            self.current_challenge_mode.finalize()

            # Store and clear challenge mode
            completed_fight = self.current_challenge_mode
            self.fights.append(self.current_challenge_mode)
            self.current_challenge_mode = None

            return completed_fight

        return None

    def _handle_combat_event(self, event: BaseEvent):
        """Handle regular combat events."""
        # Skip non-combat events
        if event.event_type in ['COMBAT_LOG_VERSION', 'ZONE_CHANGE', 'MAP_CHANGE']:
            return

        # Add to current encounter if active
        if self.current_fight:
            self.current_fight.add_event(event)
        elif self.current_challenge_mode:
            # We're in a M+ but not in a boss fight - this is trash
            self._handle_trash_combat(event)

        # Track last combat time for trash segmentation
        if self._is_combat_event(event):
            self.last_combat_time = event.timestamp

    def _handle_trash_combat(self, event: BaseEvent):
        """Handle trash combat outside of boss encounters."""
        # Check if we should start a new trash segment
        if self.current_fight and self.current_fight.fight_type == FightType.TRASH:
            # Check for timeout
            if (self.last_combat_time and
                    event.timestamp - self.last_combat_time > timedelta(seconds=self.trash_timeout)):
                # End current trash segment and start new one
                self.current_fight.finalize()
                self.fights.append(self.current_fight)
                self.current_fight = None

        # Start new trash segment if needed
        if not self.current_fight:
            self.fight_counter += 1
            self.current_fight = Fight(
                fight_id=self.fight_counter,
                fight_type=FightType.TRASH,
                start_time=event.timestamp
            )

        self.current_fight.add_event(event)

    def _is_combat_event(self, event: BaseEvent) -> bool:
        """Check if an event represents active combat."""
        combat_keywords = ['DAMAGE', 'HEAL', 'CAST', 'AURA', 'SUMMON']
        return any(keyword in event.event_type for keyword in combat_keywords)

    def finalize(self) -> List[Fight]:
        """
        Finalize any open fights and return all fights.

        Returns:
            List of all fights detected
        """
        # Finalize any open fight
        if self.current_fight:
            self.current_fight.finalize()
            self.fights.append(self.current_fight)
            self.current_fight = None

        if self.current_challenge_mode:
            self.current_challenge_mode.finalize()
            self.fights.append(self.current_challenge_mode)
            self.current_challenge_mode = None

        return self.fights

    def get_stats(self) -> Dict[str, Any]:
        """
        Get segmentation statistics.

        Returns:
            Dictionary with segmentation stats
        """
        fight_types = {}
        for fight in self.fights:
            fight_types[fight.fight_type.value] = fight_types.get(fight.fight_type.value, 0) + 1

        return {
            'total_fights': len(self.fights),
            'fight_types': fight_types,
            'successful_kills': sum(1 for f in self.fights if f.success is True),
            'wipes': sum(1 for f in self.fights if f.success is False),
            'incomplete': sum(1 for f in self.fights if not f.is_complete())
        }