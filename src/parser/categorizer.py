"""
Event categorization system for routing events to character streams.
"""

from typing import Dict, Optional, Set
import logging

from .events import BaseEvent, DamageEvent, HealEvent, AuraEvent, CombatantInfo
from src.models.character_events import CharacterEventStream, DeathEvent, CastEvent

logger = logging.getLogger(__name__)


class EventCategorizer:
    """
    Categorizes and routes combat log events to appropriate character streams.

    This class is responsible for:
    1. Determining which characters are affected by each event
    2. Categorizing events (damage_done, healing_done, buff_gained, etc.)
    3. Routing events to the correct character streams
    """

    # Event types that represent damage
    DAMAGE_EVENTS = {
        "SWING_DAMAGE",
        "SWING_DAMAGE_LANDED",
        "SPELL_DAMAGE",
        "SPELL_PERIODIC_DAMAGE",
        "RANGE_DAMAGE",
        "ENVIRONMENTAL_DAMAGE",
        "DAMAGE_SPLIT",
    }

    # Event types that represent healing
    HEALING_EVENTS = {"SPELL_HEAL", "SPELL_PERIODIC_HEAL"}

    # Event types for damage absorption
    ABSORPTION_EVENTS = {"SPELL_ABSORBED"}

    # Event types for aura application
    AURA_APPLY_EVENTS = {
        "SPELL_AURA_APPLIED",
        "SPELL_AURA_APPLIED_DOSE",
        "SPELL_AURA_REFRESH",
    }

    # Event types for aura removal
    AURA_REMOVE_EVENTS = {"SPELL_AURA_REMOVED", "SPELL_AURA_REMOVED_DOSE"}

    # Event types for spell casts
    CAST_EVENTS = {"SPELL_CAST_START", "SPELL_CAST_SUCCESS", "SPELL_CAST_FAILED"}

    # Common buff spell IDs (heroism, power infusion, etc.)
    MAJOR_BUFFS = {
        32182,  # Heroism
        80353,  # Time Warp
        2825,  # Bloodlust
        90355,  # Ancient Hysteria
        160452,  # Netherwinds
        264667,  # Primal Rage
        390386,  # Fury of the Aspects
        10060,  # Power Infusion
    }

    def __init__(self):
        """Initialize the event categorizer."""
        self.character_streams: Dict[str, CharacterEventStream] = {}
        self.pet_owners: Dict[str, str] = {}  # pet_guid -> owner_guid
        self.processed_count = 0
        self.categorization_errors = 0

    def set_character_streams(self, streams: Dict[str, CharacterEventStream]):
        """
        Set the character streams to route events to.

        Args:
            streams: Dictionary of character_guid -> CharacterEventStream
        """
        self.character_streams = streams

    def categorize_event(self, event: BaseEvent) -> Dict[str, str]:
        """
        Categorize an event and return affected characters with categories.

        Args:
            event: The combat log event to categorize

        Returns:
            Dictionary of character_guid -> category
        """
        categories = {}

        try:
            # Handle different event types
            if event.event_type in self.DAMAGE_EVENTS:
                categories.update(self._categorize_damage(event))

            elif event.event_type in self.HEALING_EVENTS:
                categories.update(self._categorize_healing(event))

            elif event.event_type in self.ABSORPTION_EVENTS:
                categories.update(self._categorize_absorption(event))

            elif event.event_type in self.AURA_APPLY_EVENTS:
                categories.update(self._categorize_aura_apply(event))

            elif event.event_type in self.AURA_REMOVE_EVENTS:
                categories.update(self._categorize_aura_remove(event))

            elif event.event_type in self.CAST_EVENTS:
                categories.update(self._categorize_cast(event))

            elif event.event_type == "SPELL_SUMMON":
                self._handle_summon(event)

            elif event.event_type == "UNIT_DIED":
                categories.update(self._categorize_death(event))

            elif event.event_type == "SPELL_RESURRECT":
                categories.update(self._categorize_resurrect(event))

            elif event.event_type == "SPELL_INTERRUPT":
                categories.update(self._categorize_interrupt(event))

            elif event.event_type == "SPELL_DISPEL":
                categories.update(self._categorize_dispel(event))

            elif event.event_type == "COMBATANT_INFO":
                self._handle_combatant_info(event)

            self.processed_count += 1

        except Exception as e:
            logger.debug(f"Error categorizing event {event.event_type}: {e}")
            self.categorization_errors += 1

        return categories

    def route_event(self, event: BaseEvent):
        """
        Route an event to appropriate character streams.

        Args:
            event: The event to route
        """
        categories = self.categorize_event(event)

        for char_guid, category in categories.items():
            if char_guid in self.character_streams:
                self.character_streams[char_guid].add_event(event, category)

    def _categorize_damage(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize damage events."""
        categories = {}

        # Source deals damage
        source_guid = self._resolve_pet_owner(event.source_guid)
        if source_guid and self._is_tracked_character(source_guid):
            categories[source_guid] = "damage_done"

        # Destination takes damage
        dest_guid = self._resolve_pet_owner(event.dest_guid)
        if dest_guid and self._is_tracked_character(dest_guid):
            categories[dest_guid] = "damage_taken"

        return categories

    def _categorize_healing(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize healing events."""
        categories = {}

        # Source does healing
        source_guid = self._resolve_pet_owner(event.source_guid)
        if source_guid and self._is_tracked_character(source_guid):
            categories[source_guid] = "healing_done"

        # Destination receives healing
        dest_guid = self._resolve_pet_owner(event.dest_guid)
        if dest_guid and self._is_tracked_character(dest_guid):
            categories[dest_guid] = "healing_received"

        return categories

    def _categorize_aura_apply(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize aura application events."""
        categories = {}

        dest_guid = self._resolve_pet_owner(event.dest_guid)
        if not dest_guid or not self._is_tracked_character(dest_guid):
            return categories

        # Determine if buff or debuff
        if isinstance(event, AuraEvent):
            if event.aura_type == "BUFF" or self._is_buff(event):
                if event.event_type == "SPELL_AURA_REFRESH":
                    categories[dest_guid] = "buff_refreshed"
                else:
                    categories[dest_guid] = "buff_gained"
            else:
                if event.event_type == "SPELL_AURA_REFRESH":
                    categories[dest_guid] = "debuff_refreshed"
                else:
                    categories[dest_guid] = "debuff_gained"

        return categories

    def _categorize_aura_remove(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize aura removal events."""
        categories = {}

        dest_guid = self._resolve_pet_owner(event.dest_guid)
        if not dest_guid or not self._is_tracked_character(dest_guid):
            return categories

        # Determine if buff or debuff
        if isinstance(event, AuraEvent):
            if event.aura_type == "BUFF" or self._is_buff(event):
                categories[dest_guid] = "buff_lost"
            else:
                categories[dest_guid] = "debuff_lost"

        return categories

    def _categorize_cast(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize spell cast events."""
        categories = {}

        source_guid = self._resolve_pet_owner(event.source_guid)
        if not source_guid or not self._is_tracked_character(source_guid):
            return categories

        if event.event_type == "SPELL_CAST_START":
            categories[source_guid] = "cast_started"
        elif event.event_type == "SPELL_CAST_SUCCESS":
            categories[source_guid] = "cast_succeeded"
        elif event.event_type == "SPELL_CAST_FAILED":
            categories[source_guid] = "cast_failed"

        return categories

    def _categorize_death(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize death events."""
        categories = {}

        dest_guid = self._resolve_pet_owner(event.dest_guid)
        if dest_guid and self._is_tracked_character(dest_guid):
            categories[dest_guid] = "death"

            # Create and add death event
            if dest_guid in self.character_streams:
                death = DeathEvent(
                    timestamp=event.timestamp.timestamp(),
                    datetime=event.timestamp,
                    killing_blow=event,
                )
                self.character_streams[dest_guid].add_death(death)

        return categories

    def _categorize_resurrect(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize resurrection events."""
        categories = {}

        dest_guid = self._resolve_pet_owner(event.dest_guid)
        if dest_guid and self._is_tracked_character(dest_guid):
            categories[dest_guid] = "resurrected"

            # Update last death with resurrect time
            if dest_guid in self.character_streams:
                char_stream = self.character_streams[dest_guid]
                if char_stream.deaths:
                    char_stream.deaths[-1].resurrect_time = event.timestamp.timestamp()

        return categories

    def _categorize_interrupt(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize interrupt events."""
        categories = {}

        source_guid = self._resolve_pet_owner(event.source_guid)
        if source_guid and self._is_tracked_character(source_guid):
            categories[source_guid] = "interrupt_done"

        dest_guid = self._resolve_pet_owner(event.dest_guid)
        if dest_guid and self._is_tracked_character(dest_guid):
            categories[dest_guid] = "interrupt_received"

        return categories

    def _categorize_dispel(self, event: BaseEvent) -> Dict[str, str]:
        """Categorize dispel events."""
        categories = {}

        source_guid = self._resolve_pet_owner(event.source_guid)
        if source_guid and self._is_tracked_character(source_guid):
            categories[source_guid] = "dispel_done"

        return categories

    def _handle_summon(self, event: BaseEvent):
        """Handle pet summon events to track ownership."""
        if event.source_guid and event.dest_guid:
            # Source summons dest - track pet ownership
            if event.source_guid.startswith("Player-"):
                self.pet_owners[event.dest_guid] = event.source_guid
                logger.debug(f"Tracked pet {event.dest_name} -> owner {event.source_name}")

    def _handle_combatant_info(self, event: BaseEvent):
        """Handle combatant info events for character metadata."""
        if isinstance(event, CombatantInfo):
            if event.player_guid in self.character_streams:
                stream = self.character_streams[event.player_guid]
                # Could extract class/spec info here if available
                # stream.class_name = ...
                # stream.spec_name = ...

    def _resolve_pet_owner(self, guid: Optional[str]) -> Optional[str]:
        """
        Resolve a GUID to its owner if it's a pet.

        Args:
            guid: The GUID to resolve

        Returns:
            Owner GUID if pet, original GUID if player, None otherwise
        """
        if not guid or guid == "0000000000000000":
            return None

        # If it's a pet and we know the owner, return owner
        if guid.startswith("Pet-") and guid in self.pet_owners:
            return self.pet_owners[guid]

        # Return original GUID if it's a player
        if guid.startswith("Player-"):
            return guid

        return None

    def _is_tracked_character(self, guid: str) -> bool:
        """Check if a GUID is a tracked character."""
        return guid in self.character_streams

    def _is_buff(self, event: BaseEvent) -> bool:
        """
        Determine if an aura is a buff or debuff.

        Args:
            event: The aura event

        Returns:
            True if buff, False if debuff
        """
        # Check aura_type field if available
        if isinstance(event, AuraEvent) and event.aura_type:
            return event.aura_type == "BUFF"

        # Check if it's a known major buff
        if hasattr(event, "spell_id") and event.spell_id in self.MAJOR_BUFFS:
            return True

        # Check source/dest relationship
        # Buffs are usually friendly (source and dest on same side)
        # Debuffs are usually hostile (source and dest on opposite sides)
        if event.source_guid and event.dest_guid:
            source_player = event.source_guid.startswith("Player-")
            dest_player = event.dest_guid.startswith("Player-")

            # If both are players, it's likely a buff
            if source_player and dest_player:
                return True

        # Default to debuff for safety
        return False

    def get_stats(self) -> Dict[str, int]:
        """Get categorization statistics."""
        return {
            "events_processed": self.processed_count,
            "categorization_errors": self.categorization_errors,
            "tracked_characters": len(self.character_streams),
            "tracked_pets": len(self.pet_owners),
        }
