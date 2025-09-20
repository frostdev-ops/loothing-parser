"""
Unified segmenter using the new enhanced data models.
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
    CombatantInfo,
)
from src.models.unified_encounter import UnifiedEncounter, EncounterType, Fight, NPCCombatant
from src.models.enhanced_character import EnhancedCharacter, DeathEvent
from src.models.combat_periods import CombatPeriodDetector
from src.analyzer.death_analyzer import DeathAnalyzer
from src.config.wow_data import get_difficulty_name, is_bloodlust_spell, is_battle_res_spell

logger = logging.getLogger(__name__)


class UnifiedSegmenter:
    """
    Unified segmenter that creates comprehensive encounter objects.

    This segmenter builds UnifiedEncounter objects with:
    - Enhanced character tracking with ability breakdowns
    - Death analysis with recent events
    - Fight segmentation (players vs NPCs)
    - Combat period detection
    """

    def __init__(self):
        """Initialize the unified segmenter."""
        # Current encounters
        self.current_encounter: Optional[UnifiedEncounter] = None
        self.encounters: List[UnifiedEncounter] = []

        # Pull tracking for raids
        self.raid_pull_counts: Dict[int, int] = {}

        # Combat tracking
        self.combat_detector = CombatPeriodDetector(gap_threshold=5.0)
        self.death_analyzer = DeathAnalyzer()

        # Pet ownership mapping
        self.pet_owners: Dict[str, str] = {}  # pet_guid -> owner_guid

        # Statistics
        self.total_events = 0
        self.parse_errors = 0

    def process_event(self, event: BaseEvent):
        """
        Process an event and update segmentation.

        Args:
            event: The combat log event to process
        """
        self.total_events += 1

        try:
            # Handle encounter boundaries
            if event.event_type == "ENCOUNTER_START":
                self._start_raid_encounter(event)
            elif event.event_type == "ENCOUNTER_END":
                self._end_raid_encounter(event)
            elif event.event_type == "CHALLENGE_MODE_START":
                self._start_mythic_plus(event)
            elif event.event_type == "CHALLENGE_MODE_END":
                self._end_mythic_plus(event)
            else:
                # Process combat events
                self._process_combat_event(event)
        except Exception as e:
            logger.error(f"Error processing event {event.event_type}: {e}")
            self.parse_errors += 1

    def _process_combat_event(self, event: BaseEvent):
        """Process combat events and route to character streams."""
        if not self.current_encounter:
            return

        # Handle special events first
        if event.event_type == "SPELL_SUMMON":
            self._handle_summon(event)
        elif event.event_type == "COMBATANT_INFO":
            self._handle_combatant_info(event)
        elif event.event_type == "UNIT_DIED":
            self._handle_death(event)

        # Add event to encounter
        self.current_encounter.add_event(event)

        # Route to character streams
        self._route_to_characters(event)

        # Track NPC abilities
        self._track_npc_abilities(event)

    def _route_to_characters(self, event: BaseEvent):
        """Route events to appropriate character streams."""
        # Handle source character
        if event.source_guid:
            source_guid = self._resolve_pet_owner(event.source_guid)
            if source_guid and source_guid.startswith("Player-"):
                char = self.current_encounter.add_character(source_guid, event.source_name)
                self._add_event_to_character(char, event, "source")

        # Handle destination character
        if event.dest_guid:
            dest_guid = self._resolve_pet_owner(event.dest_guid)
            if dest_guid and dest_guid.startswith("Player-"):
                char = self.current_encounter.add_character(dest_guid, event.dest_name)
                self._add_event_to_character(char, event, "dest")

    def _add_event_to_character(self, char: EnhancedCharacter, event: BaseEvent, role: str):
        """Add event to character with proper categorization."""
        # Determine category based on event type and role
        category = None

        if isinstance(event, DamageEvent):
            if role == "source":
                category = "damage_done"
            elif role == "dest":
                category = "damage_taken"
        elif isinstance(event, HealEvent):
            if role == "source":
                category = "healing_done"
            elif role == "dest":
                category = "healing_received"
        elif isinstance(event, AuraEvent):
            if role == "dest":
                if event.event_type == "SPELL_AURA_APPLIED":
                    category = "buff_gained" if self._is_buff(event) else "debuff_gained"
                elif event.event_type == "SPELL_AURA_REMOVED":
                    category = "buff_lost" if self._is_buff(event) else "debuff_lost"

        if category:
            char.add_event(event, category)

    def _track_npc_abilities(self, event: BaseEvent):
        """Track NPC abilities for fight analysis."""
        if not self.current_encounter or not self.current_encounter.current_fight:
            return

        # Track NPC damage/healing
        if (
            event.source_guid
            and not event.is_player_source()
            and not event.source_guid.startswith("Pet-")
        ):
            npc = self.current_encounter.current_fight.add_enemy(
                event.source_guid, event.source_name or "Unknown"
            )

            if isinstance(event, DamageEvent):
                npc.damage_done += event.amount
                if event.spell_id:
                    npc.abilities_used[event.spell_id] = event.spell_name
            elif isinstance(event, HealEvent):
                npc.healing_done += event.amount

        # Track damage to NPCs
        if (
            event.dest_guid
            and not event.is_player_dest()
            and not event.dest_guid.startswith("Pet-")
        ):
            if self.current_encounter.current_fight:
                npc = self.current_encounter.current_fight.add_enemy(
                    event.dest_guid, event.dest_name or "Unknown"
                )
                if isinstance(event, DamageEvent):
                    npc.damage_taken += event.amount

    def _handle_summon(self, event: BaseEvent):
        """Handle pet summon events for ownership mapping."""
        if hasattr(event, "dest_guid") and hasattr(event, "source_guid"):
            self.pet_owners[event.dest_guid] = event.source_guid
            logger.debug(f"Mapped pet {event.dest_guid} to owner {event.source_guid}")

    def _handle_combatant_info(self, event: CombatantInfo):
        """Handle combatant info events for talent/equipment data."""
        if event.player_guid and self.current_encounter:
            if event.player_guid in self.current_encounter.characters:
                char = self.current_encounter.characters[event.player_guid]
                char.set_talent_data(event)
                logger.debug(f"Set talent data for {char.character_name}")

    def _handle_death(self, event: BaseEvent):
        """Handle death events."""
        if event.dest_guid and self.current_encounter:
            dest_guid = self._resolve_pet_owner(event.dest_guid)

            # Handle player death
            if dest_guid in self.current_encounter.characters:
                char = self.current_encounter.characters[dest_guid]

                # Create death event
                death = DeathEvent(
                    timestamp=event.timestamp.timestamp(),
                    datetime=event.timestamp,
                    killing_blow=event if isinstance(event, DamageEvent) else None,
                    overkill=event.overkill if isinstance(event, DamageEvent) else 0,
                )

                # Add enhanced death tracking
                char.add_enhanced_death(death)

                # Analyze death
                self.death_analyzer.analyze_character_death(
                    char, event.timestamp, event if isinstance(event, DamageEvent) else None
                )

            # Handle NPC death
            elif self.current_encounter.current_fight:
                if event.dest_guid in self.current_encounter.current_fight.enemy_forces:
                    npc = self.current_encounter.current_fight.enemy_forces[event.dest_guid]
                    npc.deaths += 1

    def _start_raid_encounter(self, event: EncounterEvent):
        """Start a new raid encounter."""
        # End any existing encounter
        if self.current_encounter:
            self._finalize_encounter()

        # Track pull count
        encounter_id = event.encounter_id
        self.raid_pull_counts[encounter_id] = self.raid_pull_counts.get(encounter_id, 0) + 1

        # Create new unified encounter
        self.current_encounter = UnifiedEncounter(
            encounter_type=EncounterType.RAID,
            encounter_id=encounter_id,
            encounter_name=event.encounter_name,
            instance_id=event.instance_id,
            difficulty=self._get_difficulty_name(event.difficulty_id),
            pull_number=self.raid_pull_counts[encounter_id],
            start_time=event.timestamp,
        )

        # Start the main fight
        self.current_encounter.start_fight(
            f"{event.encounter_name} - Pull {self.current_encounter.pull_number}", event.timestamp
        )

        logger.info(
            f"Started raid encounter: {event.encounter_name} (Pull #{self.current_encounter.pull_number})"
        )

    def _end_raid_encounter(self, event: EncounterEvent):
        """End the current raid encounter."""
        if not self.current_encounter or self.current_encounter.encounter_id != event.encounter_id:
            return

        self.current_encounter.end_time = event.timestamp
        self.current_encounter.success = event.success

        # End the fight
        if self.current_encounter.current_fight:
            self.current_encounter.end_fight(event.timestamp, event.success)

        logger.info(
            f"Ended raid encounter: {self.current_encounter.encounter_name} ({'Success' if event.success else 'Wipe'})"
        )

        self._finalize_encounter()

    def _start_mythic_plus(self, event: ChallengeModeEvent):
        """Start a new Mythic+ run."""
        if self.current_encounter:
            self._finalize_encounter()

        self.current_encounter = UnifiedEncounter(
            encounter_type=EncounterType.MYTHIC_PLUS,
            encounter_id=event.challenge_id,
            encounter_name=event.zone_name,
            instance_id=event.instance_id,
            instance_name=event.zone_name,
            keystone_level=event.keystone_level,
            affixes=event.affix_ids,
            start_time=event.timestamp,
        )

        logger.info(f"Started M+ run: {event.zone_name} +{event.keystone_level}")

    def _end_mythic_plus(self, event: ChallengeModeEvent):
        """End the current Mythic+ run."""
        if not self.current_encounter:
            return

        self.current_encounter.end_time = event.timestamp
        self.current_encounter.success = event.success
        self.current_encounter.in_time = event.success

        # End any open fight
        if self.current_encounter.current_fight:
            self.current_encounter.end_fight(event.timestamp, event.success)

        logger.info(
            f"Ended M+ run: {self.current_encounter.encounter_name} ({'In time' if event.success else 'Depleted'})"
        )

        self._finalize_encounter()

    def _finalize_encounter(self):
        """Finalize the current encounter and calculate metrics."""
        if not self.current_encounter:
            return

        # Detect combat periods
        if self.current_encounter.events:
            self.current_encounter.combat_periods = self.combat_detector.detect_periods(
                self.current_encounter.events
            )

        # Calculate all metrics
        self.current_encounter.calculate_metrics()

        # Add to completed encounters
        self.encounters.append(self.current_encounter)
        self.current_encounter = None

    def _resolve_pet_owner(self, guid: str) -> str:
        """Resolve pet GUIDs to their owner's GUID."""
        if guid and guid.startswith("Pet-"):
            return self.pet_owners.get(guid, guid)
        return guid

    def _is_buff(self, event: AuraEvent) -> bool:
        """Determine if an aura is a buff or debuff."""
        if event.aura_type == "BUFF":
            return True
        elif event.aura_type == "DEBUFF":
            return False

        # Check source - if from friendly, likely a buff
        if event.source_guid and event.dest_guid:
            if event.source_guid.startswith("Player-") and event.dest_guid.startswith("Player-"):
                return True

        return False

    def _get_difficulty_name(self, difficulty_id: int) -> str:
        """Get difficulty name from ID."""
        difficulties = {14: "Normal", 15: "Heroic", 16: "Mythic", 17: "LFR"}
        return difficulties.get(difficulty_id, f"Unknown ({difficulty_id})")

    def get_encounters(self) -> List[UnifiedEncounter]:
        """Get all completed encounters."""
        # Finalize any open encounter
        if self.current_encounter:
            self._finalize_encounter()

        return self.encounters

    def get_stats(self) -> Dict[str, Any]:
        """Get segmentation statistics."""
        raid_encounters = [e for e in self.encounters if e.encounter_type == EncounterType.RAID]
        mythic_plus_runs = [
            e for e in self.encounters if e.encounter_type == EncounterType.MYTHIC_PLUS
        ]

        return {
            "total_events": self.total_events,
            "parse_errors": self.parse_errors,
            "total_encounters": len(self.encounters),
            "raid_encounters": len(raid_encounters),
            "mythic_plus_runs": len(mythic_plus_runs),
            "total_characters": sum(len(e.characters) for e in self.encounters),
            "total_fights": sum(len(e.fights) for e in self.encounters),
        }
