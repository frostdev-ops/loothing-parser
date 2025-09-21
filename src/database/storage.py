"""
Storage layer for WoW combat log events with compression and batching.

Handles efficient storage of character event streams into SQLite database
with automatic compression and batch operations for high performance.
"""

import hashlib
import logging
import json
import time
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

from .schema import DatabaseManager
from .compression import EventCompressor, compression_stats
from src.models.character_events import CharacterEventStream, TimestampedEvent
from src.models.encounter_models import RaidEncounter, MythicPlusRun
from src.models.unified_encounter import UnifiedEncounter, EncounterType

logger = logging.getLogger(__name__)


def safe_param(value):
    """
    Convert parameter to SQLite-safe type.

    This function ensures all parameters passed to SQLite are of supported types.
    Lists, tuples, dicts, and other collection types are converted to None.
    """
    if value is None:
        return None

    # Convert all collection types to None
    if isinstance(value, (list, tuple, dict, set)):
        logger.debug(f"Converting collection type {type(value)} to None: {value}")
        return None

    # Allow basic SQLite types
    if isinstance(value, (int, float, str, bool)):
        return value

    # Catch any other iterable types (except strings and bytes)
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        logger.debug(f"Converting iterable type {type(value)} to None: {value}")
        return None

    # Convert other types to string
    logger.debug(f"Converting {type(value)} to string: {value}")
    return str(value)


class EventStorage:
    """
    High-performance storage layer for combat log events.

    Features:
    - Automatic event compression (70-80% size reduction)
    - Batched database operations for speed
    - Duplicate detection via file hashing
    - Character/encounter metadata caching
    - Transaction safety and rollback
    """

    def __init__(self, db: DatabaseManager):
        """
        Initialize event storage.

        Args:
            db: Database manager instance
        """
        self.db = db
        self.compressor = EventCompressor()

        # Caches for fast lookups
        self.character_cache: Dict[str, int] = {}  # guid -> character_id
        self.file_cache: Set[str] = set()  # processed file hashes

        # Batch tracking
        self.pending_blocks: List[Dict[str, Any]] = []
        self.batch_size = 100  # Blocks per transaction

        # Performance tracking
        self.stats = {
            "encounters_stored": 0,
            "characters_stored": 0,
            "events_stored": 0,
            "blocks_stored": 0,
            "storage_time": 0.0,
        }

        # Load existing caches
        self._load_caches()

    def store_encounters(
        self,
        raids: List[RaidEncounter],
        mythic_plus: List[MythicPlusRun],
        log_file_path: str,
    ) -> Dict[str, Any]:
        """
        Store raid encounters and M+ runs in database.

        Args:
            raids: List of raid encounters to store
            mythic_plus: List of M+ runs to store
            log_file_path: Path to source log file

        Returns:
            Dictionary with storage statistics
        """
        start_time = time.time()

        try:
            # Check if file already processed
            file_hash = self._calculate_file_hash(log_file_path)
            if file_hash in self.file_cache:
                logger.info(f"File {log_file_path} already processed, skipping")
                return {"status": "skipped", "reason": "already_processed"}

            # Begin transaction
            total_events = 0
            total_encounters = len(raids) + len(mythic_plus)

            logger.info(f"Storing {total_encounters} encounters from {log_file_path}")

            # Register log file
            log_file_id = self._register_log_file(log_file_path, file_hash, total_encounters)

            # Store raid encounters
            for raid in raids:
                encounter_id = self._store_encounter(raid, log_file_id, "raid")
                total_events += self._store_character_streams(encounter_id, raid.characters)

            # Store M+ runs
            for mplus in mythic_plus:
                encounter_id = self._store_encounter(mplus, log_file_id, "mythic_plus")
                total_events += self._store_character_streams(
                    encounter_id, mplus.overall_characters
                )
                self._store_mythic_plus_metadata(encounter_id, mplus)

            # Flush any pending blocks
            self._flush_pending_blocks()

            # Update log file with final counts
            self.db.execute(
                "UPDATE log_files SET event_count = ?, encounter_count = ? WHERE file_id = ?",
                (total_events, total_encounters, log_file_id),
            )

            # Commit transaction
            self.db.commit()

            # Update statistics
            storage_time = time.time() - start_time
            self.stats["encounters_stored"] += total_encounters
            self.stats["events_stored"] += total_events
            self.stats["storage_time"] += storage_time

            logger.info(
                f"Successfully stored {total_encounters} encounters "
                f"({total_events:,} events) in {storage_time:.2f}s"
            )

            return {
                "status": "success",
                "encounters_stored": total_encounters,
                "events_stored": total_events,
                "storage_time": storage_time,
                "file_hash": file_hash,
            }

        except Exception as e:
            logger.error(f"Error storing encounters: {e}")
            self.db.rollback()
            raise

    def store_unified_encounters(
        self,
        encounters: List[UnifiedEncounter],
        log_file_path: str,
    ) -> Dict[str, Any]:
        """
        Store unified encounters in database.

        Args:
            encounters: List of unified encounters to store
            log_file_path: Path to source log file

        Returns:
            Dictionary with storage statistics
        """
        start_time = time.time()

        try:
            # Check if file already processed
            file_hash = self._calculate_file_hash(log_file_path)
            if file_hash in self.file_cache:
                logger.info(f"File {log_file_path} already processed, skipping")
                return {"status": "skipped", "reason": "already_processed"}

            # Begin transaction
            total_events = 0
            total_encounters = len(encounters)

            logger.info(f"Storing {total_encounters} unified encounters from {log_file_path}")

            # Register log file
            log_file_id = self._register_log_file(log_file_path, file_hash, total_encounters)

            # Store encounters
            for encounter in encounters:
                encounter_id = self._store_unified_encounter(encounter, log_file_id)
                total_events += self._store_unified_character_streams(encounter_id, encounter)

            # Flush any pending blocks
            self._flush_pending_blocks()

            # Update log file with final counts
            self.db.execute(
                "UPDATE log_files SET event_count = ?, encounter_count = ? WHERE file_id = ?",
                (total_events, total_encounters, log_file_id),
            )

            # Commit transaction
            self.db.commit()

            # Update statistics
            storage_time = time.time() - start_time
            self.stats["encounters_stored"] += total_encounters
            self.stats["events_stored"] += total_events
            self.stats["storage_time"] += storage_time

            logger.info(
                f"Successfully stored {total_encounters} unified encounters "
                f"({total_events:,} events) in {storage_time:.2f}s"
            )

            return {
                "status": "success",
                "encounters_stored": total_encounters,
                "events_stored": total_events,
                "storage_time": storage_time,
                "file_hash": file_hash,
                "characters_stored": len(
                    set(
                        char.character_guid
                        for enc in encounters
                        for char in enc.characters.values()
                    )
                ),
            }

        except Exception as e:
            logger.error(f"Error storing unified encounters: {e}")
            self.db.rollback()
            raise

    def _store_encounter(
        self,
        encounter: Union[RaidEncounter, MythicPlusRun],
        log_file_id: int,
        encounter_type: str,
    ) -> int:
        """
        Store encounter metadata and return encounter_id.

        Args:
            encounter: Encounter object to store
            log_file_id: ID of source log file
            encounter_type: 'raid' or 'mythic_plus'

        Returns:
            encounter_id from database
        """
        if encounter_type == "raid":
            # Store raid encounter
            cursor = self.db.execute(
                """
                INSERT INTO encounters (
                    log_file_id, encounter_type, boss_name, difficulty,
                    instance_id, instance_name, pull_number, start_time, end_time,
                    success, combat_length, raid_size, wipe_percentage,
                    bloodlust_used, bloodlust_time, battle_resurrections
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    safe_param(log_file_id),
                    safe_param(encounter_type),
                    safe_param(encounter.boss_name),
                    safe_param(encounter.difficulty.name if encounter.difficulty else None),
                    safe_param(encounter.instance_id),
                    safe_param(encounter.instance_name),
                    safe_param(encounter.pull_number),
                    safe_param(encounter.start_time.timestamp() if encounter.start_time else None),
                    safe_param(encounter.end_time.timestamp() if encounter.end_time else None),
                    safe_param(encounter.success),
                    safe_param(encounter.combat_length),
                    safe_param(encounter.raid_size),
                    safe_param(encounter.wipe_percentage),
                    safe_param(encounter.bloodlust_used),
                    safe_param(encounter.bloodlust_time),
                    safe_param(encounter.battle_resurrections),
                ),
            )
        else:
            # Store M+ encounter (basic info)
            cursor = self.db.execute(
                """
                INSERT INTO encounters (
                    log_file_id, encounter_type, boss_name, difficulty,
                    instance_id, instance_name, start_time, end_time,
                    success, combat_length, raid_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    safe_param(log_file_id),
                    safe_param(encounter_type),
                    safe_param(encounter.dungeon_name),
                    safe_param(f"+{encounter.keystone_level}"),
                    safe_param(encounter.dungeon_id),
                    safe_param(encounter.dungeon_name),
                    safe_param(encounter.start_time.timestamp() if encounter.start_time else None),
                    safe_param(encounter.end_time.timestamp() if encounter.end_time else None),
                    safe_param(encounter.completed),
                    safe_param(encounter.actual_time_seconds),
                    safe_param(len(encounter.group_members)),
                ),
            )

        return cursor.lastrowid

    def _store_character_streams(
        self, encounter_id: int, characters: Dict[str, CharacterEventStream]
    ) -> int:
        """
        Store character event streams for an encounter.

        Args:
            encounter_id: Database encounter ID
            characters: Dictionary of character streams

        Returns:
            Total number of events stored
        """
        total_events = 0

        for char_guid, char_stream in characters.items():
            if not char_stream.all_events:
                continue

            # Ensure character exists in database
            character_id = self._ensure_character_exists(char_stream)

            # Store character metrics
            self._store_character_metrics(encounter_id, character_id, char_stream)

            # Store spell usage summary
            self._store_spell_summary(encounter_id, character_id, char_stream)

            # Compress and store event blocks
            events_stored = self._store_event_blocks(
                encounter_id, character_id, char_stream.all_events
            )
            total_events += events_stored

        return total_events

    def _store_unified_encounter(self, encounter: UnifiedEncounter, log_file_id: int) -> int:
        """
        Store unified encounter metadata and return encounter_id.

        Args:
            encounter: UnifiedEncounter object to store
            log_file_id: ID of source log file

        Returns:
            encounter_id from database
        """
        encounter_type = encounter.encounter_type.value

        # Map encounter type for database
        if encounter_type == "mythic_plus":
            boss_name = encounter.instance_name or encounter.encounter_name
            difficulty = f"+{encounter.keystone_level}" if encounter.keystone_level else None
        else:
            boss_name = encounter.encounter_name
            difficulty = encounter.difficulty

        # Add type validation for instance_id before SQL operation
        if encounter.instance_id is not None and not isinstance(encounter.instance_id, int):
            logger.error(
                f"instance_id has unexpected type: {type(encounter.instance_id)}, "
                f"value: {encounter.instance_id} for encounter: {boss_name}"
            )
            encounter.instance_id = None  # Force to None to prevent SQL error

        # Prepare all parameters with safe_param to ensure SQLite compatibility
        params = (
            safe_param(log_file_id),
            safe_param(encounter_type),
            safe_param(boss_name),
            safe_param(difficulty),
            safe_param(encounter.instance_id),
            safe_param(encounter.instance_name),
            safe_param(encounter.start_time.timestamp() if encounter.start_time else None),
            safe_param(encounter.end_time.timestamp() if encounter.end_time else None),
            safe_param(encounter.success),
            safe_param(encounter.combat_duration),
            safe_param(len(encounter.characters) if encounter.characters else 0),
            safe_param(datetime.now().isoformat()),
        )

        # Debug logging to identify parameter types
        logger.debug(f"SQL parameters for encounter {boss_name}:")
        for i, param in enumerate(params, 1):
            logger.debug(f"  Parameter {i}: {type(param)} = {param}")

        cursor = self.db.execute(
            """
            INSERT INTO encounters (
                log_file_id, encounter_type, boss_name, difficulty,
                instance_id, instance_name, start_time, end_time,
                success, combat_length, raid_size,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )

        encounter_id = cursor.lastrowid
        logger.debug(f"Stored encounter {encounter_id}: {boss_name}")

        # Store M+ specific data if needed
        if encounter_type == "mythic_plus" and encounter.keystone_level:
            self._store_mythic_plus_metadata_unified(encounter_id, encounter)

        return encounter_id

    def _store_unified_character_streams(
        self, encounter_id: int, encounter: UnifiedEncounter
    ) -> int:
        """
        Store character data from unified encounter.

        Args:
            encounter_id: Database encounter ID
            encounter: UnifiedEncounter with character data

        Returns:
            Total number of events stored
        """
        total_events = 0

        for char_guid, character in encounter.characters.items():
            # Ensure character exists in database
            character_id = self._ensure_character_exists_unified(character)

            # Store character metrics from unified encounter
            self._store_character_metrics_unified(encounter_id, character_id, character, encounter)

            # Extract and store events for this character from the unified encounter
            if hasattr(encounter, "events") and encounter.events:
                # Filter events for this character
                character_events = [
                    event
                    for event in encounter.events
                    if (hasattr(event, "source_guid") and event.source_guid == char_guid)
                    or (hasattr(event, "dest_guid") and event.dest_guid == char_guid)
                ]

                if character_events:
                    events_stored = self.store_character_events(
                        encounter_id, character_id, character_events
                    )
                    total_events += events_stored

        return total_events

    def _ensure_character_exists_unified(self, character) -> int:
        """Ensure character exists in database for unified encounter."""
        # Check cache first
        if character.character_guid in self.character_cache:
            return self.character_cache[character.character_guid]

        # Try to find existing character
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_guid = ?",
            (character.character_guid,),
        )
        result = cursor.fetchone()

        if result:
            character_id = result[0]
            self.character_cache[character.character_guid] = character_id
            return character_id

        # Create new character
        cursor = self.db.execute(
            """
            INSERT INTO characters (
                character_guid, character_name, server, region,
                class_name, spec_name, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe_param(character.character_guid),
                safe_param(character.character_name),
                safe_param(getattr(character, "server", None)),
                safe_param(getattr(character, "region", None)),
                safe_param(getattr(character, "class_name", None)),
                safe_param(getattr(character, "spec_name", None)),
                safe_param(datetime.now().isoformat()),
                safe_param(datetime.now().isoformat()),
            ),
        )

        character_id = cursor.lastrowid
        self.character_cache[character.character_guid] = character_id
        logger.debug(f"Created character {character_id}: {character.character_name}")
        return character_id

    def _store_character_metrics_unified(
        self, encounter_id: int, character_id: int, character, encounter: UnifiedEncounter
    ):
        """Store character metrics from unified encounter."""
        # Extract metrics from character and encounter metrics
        metrics = encounter.metrics if hasattr(encounter, "metrics") else None

        self.db.execute(
            """
            INSERT OR REPLACE INTO character_metrics (
                encounter_id, character_id, damage_done, healing_done,
                damage_taken, healing_received, overhealing, death_count,
                activity_percentage, time_alive, dps, hps, dtps,
                combat_time, combat_dps, combat_hps, combat_dtps,
                combat_activity_percentage, total_events, cast_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe_param(encounter_id),
                safe_param(character_id),
                safe_param(getattr(character, "total_damage", 0)),
                safe_param(getattr(character, "total_healing", 0)),
                safe_param(getattr(character, "damage_taken", 0)),
                safe_param(getattr(character, "healing_received", 0)),
                safe_param(getattr(character, "overhealing", 0)),
                safe_param(getattr(character, "death_count", 0)),
                safe_param(getattr(character, "activity_percentage", 0.0)),
                safe_param(getattr(character, "time_alive", encounter.duration)),
                safe_param(getattr(character, "dps", 0.0)),
                safe_param(getattr(character, "hps", 0.0)),
                safe_param(getattr(character, "dtps", 0.0)),
                safe_param(encounter.combat_duration),
                safe_param(getattr(character, "combat_dps", 0.0)),
                safe_param(getattr(character, "combat_hps", 0.0)),
                safe_param(getattr(character, "combat_dtps", 0.0)),
                safe_param(getattr(character, "combat_activity_percentage", 0.0)),
                safe_param(len(getattr(character, "events", []))),
                safe_param(getattr(character, "cast_count", 0)),
            ),
        )

    def _store_mythic_plus_metadata_unified(self, encounter_id: int, encounter: UnifiedEncounter):
        """Store M+ specific metadata for unified encounter."""
        self.db.execute(
            """
            INSERT INTO mythic_plus_runs (
                encounter_id, dungeon_id, keystone_level, affixes,
                time_limit_seconds, actual_time_seconds, completed,
                in_time, time_remaining, num_deaths, death_penalties
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                encounter_id,
                encounter.instance_id or 0,
                encounter.keystone_level or 0,
                json.dumps(encounter.affixes) if encounter.affixes else "[]",
                0,  # time_limit_seconds - not available in unified model yet
                encounter.duration,
                encounter.success,
                encounter.in_time if hasattr(encounter, "in_time") else False,
                0,  # time_remaining - calculate from duration if needed
                0,  # num_deaths - sum from character metrics
                0,  # death_penalties - calculate from deaths
            ),
        )

    def store_character_events(self, encounter_id: int, character_id: int, events: List) -> int:
        """
        Store character events using the event blocks storage system.

        Args:
            encounter_id: Database encounter ID
            character_id: Database character ID
            events: List of events for the character

        Returns:
            Number of events stored
        """
        if not events:
            return 0

        # Import TimestampedEvent here to avoid circular imports
        from ..models.character_events import TimestampedEvent

        # Wrap raw events in TimestampedEvent objects
        timestamped_events = []
        for event in events:
            if hasattr(event, 'timestamp'):
                # Determine basic category based on event type
                category = "other"
                if hasattr(event, 'event_type'):
                    if "_DAMAGE" in event.event_type:
                        category = "damage"
                    elif "_HEAL" in event.event_type:
                        category = "healing"
                    elif "_AURA_" in event.event_type:
                        category = "aura"

                ts_event = TimestampedEvent(
                    timestamp=event.timestamp.timestamp(),
                    datetime=event.timestamp,
                    event=event,
                    category=category,
                )
                timestamped_events.append(ts_event)

        return self._store_event_blocks(encounter_id, character_id, timestamped_events)

    def _store_event_blocks(
        self, encounter_id: int, character_id: int, events: List[TimestampedEvent]
    ) -> int:
        """
        Compress and store events in blocks.

        Args:
            encounter_id: Database encounter ID
            character_id: Database character ID
            events: List of timestamped events

        Returns:
            Number of events stored
        """
        if not events:
            return 0

        # Split events into blocks for compression
        block_size = self.compressor.BLOCK_SIZE
        blocks_created = 0
        total_events = len(events)

        for i in range(0, len(events), block_size):
            block_events = events[i : i + block_size]
            block_index = blocks_created

            # Compress events
            compressed_data, metadata = self.compressor.compress_events(block_events)

            # Add to pending blocks (will be flushed in batches)
            block_record = {
                "encounter_id": encounter_id,
                "character_id": character_id,
                "block_index": block_index,
                "start_time": metadata["start_time"],
                "end_time": metadata["end_time"],
                "event_count": metadata["event_count"],
                "compressed_data": compressed_data,
                "uncompressed_size": metadata["uncompressed_size"],
                "compressed_size": metadata["compressed_size"],
                "compression_ratio": metadata["compression_ratio"],
            }

            self.pending_blocks.append(block_record)
            blocks_created += 1

            # Update global compression stats
            compression_stats.add_compression(
                metadata["uncompressed_size"],
                metadata["compressed_size"],
                metadata["event_count"],
                metadata["compression_time"],
            )

            # Flush blocks if batch is full
            if len(self.pending_blocks) >= self.batch_size:
                self._flush_pending_blocks()

        self.stats["blocks_stored"] += blocks_created
        return total_events

    def _flush_pending_blocks(self):
        """Flush pending event blocks to database in a batch."""
        if not self.pending_blocks:
            return

        start_time = time.time()

        # Batch insert all pending blocks
        block_data = [
            (
                block["encounter_id"],
                block["character_id"],
                block["block_index"],
                block["start_time"],
                block["end_time"],
                block["event_count"],
                block["compressed_data"],
                block["uncompressed_size"],
                block["compressed_size"],
                block["compression_ratio"],
            )
            for block in self.pending_blocks
        ]

        self.db.executemany(
            """
            INSERT INTO event_blocks (
                encounter_id, character_id, block_index, start_time, end_time,
                event_count, compressed_data, uncompressed_size,
                compressed_size, compression_ratio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            block_data,
        )

        flush_time = time.time() - start_time
        logger.debug(f"Flushed {len(self.pending_blocks)} blocks in {flush_time:.3f}s")

        self.pending_blocks.clear()

    def _ensure_character_exists(self, char_stream: CharacterEventStream) -> int:
        """
        Ensure character exists in database and return character_id.

        Args:
            char_stream: Character event stream

        Returns:
            character_id from database
        """
        char_guid = char_stream.character_guid

        # Check cache first
        if char_guid in self.character_cache:
            return self.character_cache[char_guid]

        # Check database
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_guid = ?", (char_guid,)
        )
        row = cursor.fetchone()

        if row:
            character_id = row[0]

            # Update last seen
            self.db.execute(
                "UPDATE characters SET last_seen = CURRENT_TIMESTAMP, encounter_count = encounter_count + 1 WHERE character_id = ?",
                (character_id,),
            )
        else:
            # Create new character
            cursor = self.db.execute(
                """
                INSERT INTO characters (
                    character_guid, character_name, server, region, class_name, spec_name, encounter_count
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
                (
                    char_guid,
                    char_stream.character_name,
                    char_stream.server,
                    char_stream.region,
                    char_stream.class_name,
                    char_stream.spec_name,
                ),
            )
            character_id = cursor.lastrowid
            self.stats["characters_stored"] += 1

        # Cache for future lookups
        self.character_cache[char_guid] = character_id
        return character_id

    def _store_character_metrics(
        self, encounter_id: int, character_id: int, char_stream: CharacterEventStream
    ):
        """Store pre-computed character metrics."""
        self.db.execute(
            """
            INSERT OR REPLACE INTO character_metrics (
                encounter_id, character_id, damage_done, healing_done,
                damage_taken, healing_received, overhealing, death_count,
                activity_percentage, time_alive, dps, hps, dtps,
                total_events, cast_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                encounter_id,
                character_id,
                char_stream.total_damage_done,
                char_stream.total_healing_done,
                char_stream.total_damage_taken,
                char_stream.total_healing_received,
                char_stream.total_overhealing,
                char_stream.death_count,
                char_stream.activity_percentage,
                char_stream.time_alive,
                char_stream.get_dps(char_stream.time_alive if char_stream.time_alive > 0 else 1),
                char_stream.get_hps(char_stream.time_alive if char_stream.time_alive > 0 else 1),
                char_stream.get_dtps(char_stream.time_alive if char_stream.time_alive > 0 else 1),
                len(char_stream.all_events),
                len(char_stream.casts_succeeded),
            ),
        )

    def _store_spell_summary(
        self, encounter_id: int, character_id: int, char_stream: CharacterEventStream
    ):
        """Store aggregated spell usage data."""
        # Aggregate spell usage from events
        spell_stats = {}

        for event in char_stream.damage_done:
            if hasattr(event, "spell_id") and event.spell_id:
                key = (event.spell_id, event.spell_name)
                if key not in spell_stats:
                    spell_stats[key] = {
                        "cast_count": 0,
                        "hit_count": 0,
                        "crit_count": 0,
                        "total_damage": 0,
                        "max_damage": 0,
                    }
                spell_stats[key]["hit_count"] += 1
                spell_stats[key]["total_damage"] += getattr(event, "amount", 0)
                spell_stats[key]["max_damage"] = max(
                    spell_stats[key]["max_damage"], getattr(event, "amount", 0)
                )
                if getattr(event, "critical", False):
                    spell_stats[key]["crit_count"] += 1

        for event in char_stream.healing_done:
            if hasattr(event, "spell_id") and event.spell_id:
                key = (event.spell_id, event.spell_name)
                if key not in spell_stats:
                    spell_stats[key] = {
                        "cast_count": 0,
                        "hit_count": 0,
                        "crit_count": 0,
                        "total_healing": 0,
                        "max_healing": 0,
                    }
                spell_stats[key]["hit_count"] += 1
                spell_stats[key]["total_healing"] = spell_stats[key].get(
                    "total_healing", 0
                ) + getattr(event, "effective_healing", 0)
                spell_stats[key]["max_healing"] = max(
                    spell_stats[key].get("max_healing", 0),
                    getattr(event, "effective_healing", 0),
                )
                if getattr(event, "critical", False):
                    spell_stats[key]["crit_count"] += 1

        # Store spell summaries
        for (spell_id, spell_name), stats in spell_stats.items():
            self.db.execute(
                """
                INSERT OR REPLACE INTO spell_summary (
                    encounter_id, character_id, spell_id, spell_name,
                    cast_count, hit_count, crit_count, total_damage,
                    total_healing, max_damage, max_healing
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    encounter_id,
                    character_id,
                    spell_id,
                    spell_name or "Unknown",
                    stats.get("cast_count", 0),
                    stats["hit_count"],
                    stats["crit_count"],
                    stats.get("total_damage", 0),
                    stats.get("total_healing", 0),
                    stats.get("max_damage", 0),
                    stats.get("max_healing", 0),
                ),
            )

    def _store_mythic_plus_metadata(self, encounter_id: int, mplus: MythicPlusRun):
        """Store M+ specific metadata."""
        self.db.execute(
            """
            INSERT INTO mythic_plus_runs (
                encounter_id, dungeon_id, keystone_level, affixes,
                time_limit_seconds, actual_time_seconds, completed,
                in_time, time_remaining, num_deaths, death_penalties,
                enemy_forces_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                encounter_id,
                mplus.dungeon_id,
                mplus.keystone_level,
                json.dumps(mplus.affixes),
                mplus.time_limit_seconds,
                mplus.actual_time_seconds,
                mplus.completed,
                mplus.in_time,
                mplus.time_remaining,
                mplus.num_deaths,
                sum(mplus.death_penalties),
                0.0,  # enemy_forces_percent placeholder
            ),
        )

        # Store combat segments
        run_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

        for i, segment in enumerate(mplus.segments):
            self.db.execute(
                """
                INSERT INTO combat_segments (
                    run_id, segment_index, segment_type, segment_name,
                    start_time, end_time, duration, mob_count,
                    enemy_forces_start, enemy_forces_end, enemy_forces_gained
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    i,
                    segment.segment_type.value,
                    segment.segment_name,
                    segment.start_time.timestamp() if segment.start_time else None,
                    segment.end_time.timestamp() if segment.end_time else None,
                    segment.duration,
                    segment.mob_count,
                    segment.enemy_forces_start,
                    segment.enemy_forces_end,
                    segment.enemy_forces_gained,
                ),
            )

    def _register_log_file(self, file_path: str, file_hash: str, encounter_count: int) -> int:
        """Register log file and return file_id."""
        file_size = Path(file_path).stat().st_size

        cursor = self.db.execute(
            """
            INSERT INTO log_files (file_path, file_hash, file_size, encounter_count)
            VALUES (?, ?, ?, ?)
        """,
            (
                safe_param(file_path),
                safe_param(file_hash),
                safe_param(file_size),
                safe_param(encounter_count),
            ),
        )

        file_id = cursor.lastrowid
        self.file_cache.add(file_hash)
        return file_id

    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of file for duplicate detection."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                # Hash first 1MB for speed
                chunk = f.read(1024 * 1024)
                hash_md5.update(chunk)
        except IOError:
            # If can't read file, use path + mtime
            stat = Path(file_path).stat()
            hash_md5.update(f"{file_path}:{stat.st_mtime}:{stat.st_size}".encode())

        return hash_md5.hexdigest()

    def _load_caches(self):
        """Load character and file caches from database."""
        try:
            # Load character cache if table exists
            if self.db.table_exists("characters"):
                cursor = self.db.execute("SELECT character_guid, character_id FROM characters")
                for row in cursor:
                    self.character_cache[row[0]] = row[1]

            # Load file cache if table exists
            if self.db.table_exists("log_files"):
                cursor = self.db.execute("SELECT file_hash FROM log_files")
                for row in cursor:
                    self.file_cache.add(row[0])
        except Exception as e:
            logger.warning(f"Failed to load caches (will continue with empty caches): {e}")

        logger.info(
            f"Loaded caches: {len(self.character_cache)} characters, "
            f"{len(self.file_cache)} processed files"
        )

    def _store_mythic_plus_metadata_unified(self, encounter_id: int, encounter: UnifiedEncounter):
        """Store mythic+ specific metadata for unified encounter."""
        if not encounter.keystone_level:
            return

        # Store mythic+ run data
        self.db.execute(
            """
            INSERT INTO mythic_plus_runs (
                encounter_id, dungeon_id, keystone_level, affixes,
                time_limit_seconds, actual_time_seconds, completed,
                in_time, time_remaining, num_deaths, death_penalties
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe_param(encounter_id),
                safe_param(getattr(encounter, "dungeon_id", 0)),
                safe_param(encounter.keystone_level),
                safe_param("[]"),  # TODO: Implement affix parsing
                safe_param(getattr(encounter, "time_limit", 0)),
                safe_param(encounter.combat_duration),
                safe_param(encounter.success),
                safe_param(encounter.success),  # in_time same as success for now
                safe_param(0.0),  # time_remaining
                safe_param(0),  # num_deaths
                safe_param(0.0),  # death_penalties
            ),
        )

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage layer statistics."""
        return {
            **self.stats,
            "compression_stats": compression_stats.get_stats(),
            "cache_sizes": {
                "characters": len(self.character_cache),
                "processed_files": len(self.file_cache),
            },
            "pending_blocks": len(self.pending_blocks),
        }
