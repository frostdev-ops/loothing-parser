"""
Enhanced segmentation for per-character event stream tracking.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import logging

from src.parser.events import (
    BaseEvent,
    EncounterEvent,
    ChallengeModeEvent,
    DamageEvent,
    HealEvent,
    AuraEvent,
)
from src.parser.categorizer import EventCategorizer
from src.models.encounter_models import (
    RaidEncounter,
    MythicPlusRun,
    CombatSegment,
    Phase,
    Difficulty,
    SegmentType,
)
from src.models.character_events import CharacterEventStream

logger = logging.getLogger(__name__)


class EnhancedSegmenter:
    """
    Enhanced segmenter that creates per-character event streams.

    This segmenter builds detailed character tracking for both
    raid encounters and Mythic+ runs, maintaining complete event
    histories for each character.
    """

    def __init__(self):
        """Initialize the enhanced segmenter."""
        self.categorizer = EventCategorizer()

        # Raid tracking
        self.current_raid: Optional[RaidEncounter] = None
        self.raid_encounters: List[RaidEncounter] = []
        self.raid_pull_count: Dict[int, int] = {}  # encounter_id -> pull count

        # Mythic+ tracking
        self.current_mythic_plus: Optional[MythicPlusRun] = None
        self.current_m_plus_segment: Optional[CombatSegment] = None
        self.mythic_plus_runs: List[MythicPlusRun] = []

        # Combat tracking
        self.in_combat = False
        self.last_combat_event: Optional[datetime] = None
        self.combat_timeout = timedelta(seconds=5)  # 5 seconds of no combat = end segment

        # Statistics
        self.total_events = 0
        self.total_characters = 0

    def process_event(self, event: BaseEvent):
        """
        Process an event and update segmentation with character streams.

        Args:
            event: The combat log event to process
        """
        self.total_events += 1

        # Handle encounter boundaries
        if event.event_type == "ENCOUNTER_START":
            if self.current_mythic_plus:
                # In M+ context, start a boss segment
                self._start_m_plus_segment(event)
            else:
                # Otherwise, it's a raid encounter
                self._start_raid_encounter(event)

        elif event.event_type == "ENCOUNTER_END":
            if self.current_mythic_plus and self.current_m_plus_segment:
                # End M+ segment
                self._end_m_plus_segment(event.timestamp)
            else:
                # End raid encounter
                self._end_raid_encounter(event)

        elif event.event_type == "CHALLENGE_MODE_START":
            self._start_mythic_plus(event)

        elif event.event_type == "CHALLENGE_MODE_END":
            self._end_mythic_plus(event)

        else:
            # Route combat events to active encounter/segment
            self._process_combat_event(event)

    def _process_combat_event(self, event: BaseEvent):
        """Process combat events and route to character streams."""

        # Track combat state
        if self._is_combat_event(event):
            if not self.in_combat:
                self._enter_combat(event)
            self.last_combat_event = event.timestamp

        # Check for combat timeout in M+
        if (
            self.current_mythic_plus
            and self.last_combat_event
            and event.timestamp - self.last_combat_event > self.combat_timeout
        ):
            self._leave_combat(event)

        # Route to appropriate context
        if self.current_raid:
            self._process_raid_event(event)

        elif self.current_mythic_plus:
            self._process_mythic_plus_event(event)

    def _process_raid_event(self, event: BaseEvent):
        """Process events during a raid encounter."""
        if not self.current_raid:
            return

        # Ensure characters exist
        self._ensure_characters_exist(event, self.current_raid.characters)

        # Set up categorizer with current character streams
        self.categorizer.set_character_streams(self.current_raid.characters)

        # Route event to character streams
        self.categorizer.route_event(event)

        # Track raid-wide mechanics
        self._track_raid_mechanics(event)

    def _process_mythic_plus_event(self, event: BaseEvent):
        """Process events during a Mythic+ run."""
        if not self.current_mythic_plus:
            return

        # Ensure we have an active segment
        if not self.current_m_plus_segment and self._is_combat_event(event):
            self._start_m_plus_segment(event)

        if self.current_m_plus_segment:
            # Ensure characters exist in segment
            self._ensure_characters_exist(event, self.current_m_plus_segment.characters)

            # Set up categorizer with segment character streams
            self.categorizer.set_character_streams(self.current_m_plus_segment.characters)

            # Route event to character streams
            self.categorizer.route_event(event)

            # Track mob deaths for progress
            if (
                event.event_type == "UNIT_DIED"
                and event.dest_guid
                and not event.dest_guid.startswith("Player-")
            ):
                self.current_m_plus_segment.mob_deaths.append(event.dest_guid)
                self.current_m_plus_segment.mob_count += 1

    def _start_raid_encounter(self, event: EncounterEvent):
        """Start a new raid encounter."""
        # End any existing encounter
        if self.current_raid:
            self._finalize_raid_encounter()

        # Track pull count
        encounter_id = event.encounter_id
        self.raid_pull_count[encounter_id] = self.raid_pull_count.get(encounter_id, 0) + 1

        # Create new encounter
        self.current_raid = RaidEncounter(
            encounter_id=encounter_id,
            boss_name=event.encounter_name,
            difficulty=self._get_difficulty(event.difficulty_id),
            instance_id=event.instance_id,
            pull_number=self.raid_pull_count[encounter_id],
            start_time=event.timestamp,
        )

        logger.info(
            f"Started raid encounter: {event.encounter_name} (Pull #{self.current_raid.pull_number})"
        )

    def _end_raid_encounter(self, event: EncounterEvent):
        """End the current raid encounter."""
        if not self.current_raid or self.current_raid.encounter_id != event.encounter_id:
            return

        self.current_raid.end_time = event.timestamp
        self.current_raid.success = event.success

        if event.duration:
            self.current_raid.combat_length = event.duration / 1000.0  # Convert ms to seconds

        # Calculate wipe percentage if failed
        if not event.success:
            # This would require tracking boss health, which we'd need to extract from events
            pass

        self._finalize_raid_encounter()

        result = "Kill" if event.success else "Wipe"
        logger.info(f"Ended raid encounter: {event.encounter_name} ({result})")

    def _start_mythic_plus(self, event: ChallengeModeEvent):
        """Start a new Mythic+ run."""
        # End any existing M+ run
        if self.current_mythic_plus:
            self._finalize_mythic_plus()

        # Create new M+ run
        self.current_mythic_plus = MythicPlusRun(
            dungeon_id=event.instance_id,
            dungeon_name=event.zone_name,
            keystone_level=event.keystone_level,
            affixes=event.affix_ids,
            start_time=event.timestamp,
        )

        logger.info(f"Started Mythic+ run: {event.zone_name} +{event.keystone_level}")

    def _end_mythic_plus(self, event: ChallengeModeEvent):
        """End the current Mythic+ run."""
        if not self.current_mythic_plus:
            return

        # End any active segment
        if self.current_m_plus_segment:
            self._end_m_plus_segment(event.timestamp)

        self.current_mythic_plus.end_time = event.timestamp
        self.current_mythic_plus.completed = event.success
        self.current_mythic_plus.abandoned = not event.success  # Mark as abandoned if success=0
        # Note: actual_time_seconds will be calculated from start_time and end_time in calculate_metrics()

        self._finalize_mythic_plus()

        result = "Completed" if event.success else "Abandoned"
        logger.info(f"Ended Mythic+ run: {self.current_mythic_plus.dungeon_name} ({result})")

    def _start_m_plus_segment(self, event: BaseEvent):
        """Start a new combat segment in M+."""
        if not self.current_mythic_plus:
            return

        # Determine segment type (boss or trash)
        segment_type = SegmentType.TRASH  # Default
        segment_name = "Trash Pack"

        # Check if this is a boss encounter
        if event.event_type == "ENCOUNTER_START" and isinstance(event, EncounterEvent):
            segment_type = SegmentType.BOSS
            segment_name = event.encounter_name

        # Create new segment
        segment_id = len(self.current_mythic_plus.segments) + 1
        self.current_m_plus_segment = CombatSegment(
            segment_id=segment_id,
            segment_type=segment_type,
            segment_name=segment_name,
            start_time=event.timestamp,
        )

        logger.debug(f"Started M+ segment: {segment_name}")

    def _end_m_plus_segment(self, timestamp: datetime):
        """End the current M+ combat segment."""
        if not self.current_m_plus_segment or not self.current_mythic_plus:
            return

        self.current_m_plus_segment.end_time = timestamp
        self.current_m_plus_segment.calculate_metrics()

        # Add to M+ run
        self.current_mythic_plus.add_segment(self.current_m_plus_segment)

        logger.debug(f"Ended M+ segment: {self.current_m_plus_segment.segment_name}")
        self.current_m_plus_segment = None

    def _enter_combat(self, event: BaseEvent):
        """Handle entering combat."""
        self.in_combat = True

        # Start M+ segment if needed
        if self.current_mythic_plus and not self.current_m_plus_segment:
            self._start_m_plus_segment(event)

    def _leave_combat(self, event: BaseEvent):
        """Handle leaving combat."""
        self.in_combat = False

        # End M+ segment if active
        if self.current_m_plus_segment:
            self._end_m_plus_segment(event.timestamp)

    def _ensure_characters_exist(
        self, event: BaseEvent, character_dict: Dict[str, CharacterEventStream]
    ):
        """
        Ensure character streams exist for event participants.

        Args:
            event: The event with source/dest
            character_dict: Dictionary to add characters to
        """
        # Check source
        if event.source_guid and event.source_guid.startswith("Player-"):
            if event.source_guid not in character_dict:
                character_dict[event.source_guid] = CharacterEventStream(
                    character_guid=event.source_guid,
                    character_name=event.source_name or "Unknown",
                )
                self.total_characters = max(self.total_characters, len(character_dict))

        # Check destination
        if event.dest_guid and event.dest_guid.startswith("Player-"):
            if event.dest_guid not in character_dict:
                character_dict[event.dest_guid] = CharacterEventStream(
                    character_guid=event.dest_guid,
                    character_name=event.dest_name or "Unknown",
                )
                self.total_characters = max(self.total_characters, len(character_dict))

    def _track_raid_mechanics(self, event: BaseEvent):
        """Track raid-wide mechanics and phases."""
        if not self.current_raid:
            return

        # Track bloodlust/heroism
        if hasattr(event, "spell_id"):
            bloodlust_spells = {32182, 80353, 2825, 90355, 160452, 264667, 390386}
            if event.spell_id in bloodlust_spells and event.event_type == "SPELL_CAST_SUCCESS":
                self.current_raid.bloodlust_used = True
                self.current_raid.bloodlust_time = event.timestamp.timestamp()

        # Track battle resurrections
        if event.event_type == "SPELL_RESURRECT":
            self.current_raid.battle_resurrections += 1

    def _finalize_raid_encounter(self):
        """Finalize the current raid encounter."""
        if not self.current_raid:
            return

        # Calculate metrics
        self.current_raid.calculate_metrics()

        # Store encounter
        self.raid_encounters.append(self.current_raid)
        self.current_raid = None

    def _finalize_mythic_plus(self):
        """Finalize the current Mythic+ run."""
        if not self.current_mythic_plus:
            return

        # Ensure end_time is set (fallback logic for incomplete runs)
        if not self.current_mythic_plus.end_time:
            # For runs missing end_time (no CHALLENGE_MODE_END), use segment-based fallback
            latest_end = None
            for segment in self.current_mythic_plus.segments:
                if segment.end_time and (not latest_end or segment.end_time > latest_end):
                    latest_end = segment.end_time

            if latest_end:
                # For abandoned runs, find the last meaningful combat activity
                # Look for the last combat event from player characters
                last_combat_time = None
                for segment in self.current_mythic_plus.segments:
                    for char_stream in segment.characters.values():
                        if char_stream.all_events:
                            # Find the last damage/healing event
                            for ts_event in reversed(char_stream.all_events):
                                if ts_event.category in ["damage_done", "healing_done", "damage_taken"]:
                                    event_time = datetime.fromtimestamp(ts_event.timestamp)
                                    if not last_combat_time or event_time > last_combat_time:
                                        last_combat_time = event_time
                                    break  # Found last combat event for this character

                # Use last combat time if reasonable, otherwise use segment end
                if last_combat_time and (last_combat_time - self.current_mythic_plus.start_time).total_seconds() < 7200:  # < 2 hours
                    self.current_mythic_plus.end_time = last_combat_time
                    logger.debug(f"Set M+ run end_time to last combat: {last_combat_time}")
                else:
                    # Fall back to segment end time if combat time detection failed
                    self.current_mythic_plus.end_time = latest_end
                    logger.debug(f"Set M+ run end_time to latest segment: {latest_end}")

                self.current_mythic_plus.abandoned = True
            else:
                # No segments, set a minimal duration
                self.current_mythic_plus.end_time = self.current_mythic_plus.start_time + timedelta(
                    minutes=1
                )
                self.current_mythic_plus.abandoned = True
                logger.warning(f"M+ run has no segments, setting minimal duration")

        # Aggregate character data across segments
        self.current_mythic_plus.aggregate_character_data()

        # Calculate metrics
        self.current_mythic_plus.calculate_metrics()

        # Store run
        self.mythic_plus_runs.append(self.current_mythic_plus)
        self.current_mythic_plus = None

    def _is_combat_event(self, event: BaseEvent) -> bool:
        """Check if an event represents active combat."""
        combat_types = {
            "SWING_DAMAGE",
            "SPELL_DAMAGE",
            "SPELL_HEAL",
            "SPELL_CAST_START",
            "SPELL_CAST_SUCCESS",
            "SPELL_AURA_APPLIED",
            "SPELL_AURA_REMOVED",
        }
        return event.event_type in combat_types

    def _get_difficulty(self, difficulty_id: int) -> Difficulty:
        """Convert difficulty ID to enum."""
        difficulty_map = {
            17: Difficulty.LFR,
            14: Difficulty.NORMAL,
            15: Difficulty.HEROIC,
            16: Difficulty.MYTHIC,
        }
        return difficulty_map.get(difficulty_id, Difficulty.NORMAL)

    def finalize(self) -> Tuple[List[RaidEncounter], List[MythicPlusRun]]:
        """
        Finalize any open encounters and return all data.

        Returns:
            Tuple of (raid_encounters, mythic_plus_runs)
        """
        # Finalize any open encounters
        if self.current_raid:
            self._finalize_raid_encounter()

        if self.current_mythic_plus:
            if self.current_m_plus_segment:
                self._end_m_plus_segment(datetime.now())
            self._finalize_mythic_plus()

        return self.raid_encounters, self.mythic_plus_runs

    def get_stats(self) -> Dict[str, Any]:
        """Get segmentation statistics."""
        return {
            "total_events": self.total_events,
            "total_characters": self.total_characters,
            "raid_encounters": len(self.raid_encounters),
            "mythic_plus_runs": len(self.mythic_plus_runs),
            "categorizer_stats": self.categorizer.get_stats(),
        }
