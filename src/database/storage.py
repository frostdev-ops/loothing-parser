"""
Storage layer for WoW combat log events with time-series streaming.

Handles efficient storage of character event streams directly into InfluxDB
for time-series native operations with metadata in PostgreSQL.
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
from .influxdb_direct_manager import InfluxDBDirectManager
from src.models.character_events import CharacterEventStream, TimestampedEvent
from src.models.encounter_models import RaidEncounter, MythicPlusRun
from src.models.unified_encounter import UnifiedEncounter, EncounterType

logger = logging.getLogger(__name__)


def safe_param(value):
    """
    Convert parameter to SQLite-safe type.

    This function ensures all parameters passed to SQLite are of supported types.
    Lists tuples dicts and other collection types are converted to None.
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
    High-performance storage layer for combat log events using time-series database.

    Features:
    - Direct event streaming to InfluxDB for time-series queries
    - Metadata storage in PostgreSQL for relational data
    - Duplicate detection via file hashing
    - Character/encounter metadata caching
    - Time-window based encounter definitions
    """

    def __init__(self, db: DatabaseManager):
        """
        Initialize event storage.

        Args:
            db: Database manager instance (hybrid manager with InfluxDB)
        """
        self.db = db

        # Initialize time-series manager if available
        if hasattr(db, 'influxdb') and db.influxdb:
            self.influxdb_manager = InfluxDBDirectManager(
                url=db.influxdb.url,
                token=db.influxdb.token,
                org=db.influxdb.org,
                bucket=db.influxdb.bucket
            )
        else:
            self.influxdb_manager = None
            logger.warning("No InfluxDB connection available events will not be stored in time-series format")

        # Caches for fast lookups
        self.character_cache: Dict[str, int] = {}  # guid -> character_id
        self.file_cache: Set[str] = set()  # processed file hashes

        # Performance tracking
        self.stats = {
            "encounters_stored": 0,
            "characters_stored": 0,
            "events_stored": 0,
            "storage_time": 0.0
        }

        # Load existing caches
        self._load_caches()

    def store_encounters(
        self,
        raids: List[RaidEncounter],
        mythic_plus: List[MythicPlusRun],
        log_file_path: str,
        guild_id: Optional[int] = None
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
                logger.info(f"File {log_file_path} already processed skipping")
                return {"status": "skipped", "reason": "already_processed"}

            # Begin transaction
            total_events = 0
            total_encounters = len(raids) + len(mythic_plus)

            logger.info(f"Storing {total_encounters} encounters from {log_file_path}")

            # Register log file
            log_file_id = self._register_log_file(log_file_path, file_hash, total_encounters, guild_id)

            # Store raid encounters
            for raid in raids:
                encounter_id = self._store_encounter(raid, log_file_id, "raid")
                total_events += self._store_character_streams(encounter_id raid.characters)

            # Store M+ runs
            for mplus in mythic_plus:
                encounter_id = self._store_encounter(mplus log_file_id "mythic_plus")
                total_events += self._store_character_streams(
                    encounter_id mplus.overall_characters
                )
                self._store_mythic_plus_metadata(encounter_id mplus)

            # Update log file with final counts
            self.db.execute(
                "UPDATE log_files SET event_count = %s encounter_count = %s WHERE file_id = %s" 
                (total_events total_encounters log_file_id) 
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
                f"({total_events: } events) in {storage_time:.2f}s"
            )

            return {
                "status": "success" 
                "encounters_stored": total_encounters 
                "events_stored": total_events 
                "storage_time": storage_time 
                "file_hash": file_hash 
            }

        except Exception as e:
            logger.error(f"Error storing encounters: {e}")
            self.db.rollback()
            raise

    def store_unified_encounters(
        self 
        encounters: List[UnifiedEncounter] 
        log_file_path: str 
        guild_id: Optional[int] = None 
    ) -> Dict[str Any]:
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
                logger.info(f"File {log_file_path} already processed skipping")
                return {"status": "skipped", "reason": "already_processed"}

            # Begin transaction
            total_events = 0
            total_encounters = len(encounters)

            logger.info(f"Storing {total_encounters} unified encounters from {log_file_path}")

            # Register log file
            log_file_id = self._register_log_file(log_file_path, file_hash, total_encounters, guild_id)

            # Store encounters
            for encounter in encounters:
                encounter_id = self._store_unified_encounter(encounter log_file_id guild_id or 1)
                total_events += self._store_unified_character_streams(encounter_id encounter guild_id or 1)

            # Update log file with final counts
            self.db.execute(
                "UPDATE log_files SET event_count = %s encounter_count = %s WHERE file_id = %s" 
                (total_events total_encounters log_file_id) 
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
                f"({total_events: } events) in {storage_time:.2f}s"
            )

            return {
                "status": "success" 
                "encounters_stored": total_encounters 
                "events_stored": total_events 
                "storage_time": storage_time 
                "file_hash": file_hash 
                "characters_stored": len(
                    set(
                        char.character_guid
                        for enc in encounters
                        for char in enc.characters.values()
                    )
                ) 
            }

        except Exception as e:
            logger.error(f"Error storing unified encounters: {e}")
            self.db.rollback()
            raise

    def _store_encounter(
        self 
        encounter: Union[RaidEncounter MythicPlusRun] 
        log_file_id: int 
        encounter_type: str 
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
                INSERT INTO combat_encounters (
                    log_file_id encounter_type boss_name difficulty 
                    instance_id instance_name pull_number start_time end_time 
                    success combat_length raid_size wipe_percentage 
                    bloodlust_used bloodlust_time battle_resurrections
                ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s)
            """ 
                (
                    safe_param(log_file_id) 
                    safe_param(encounter_type) 
                    safe_param(encounter.boss_name) 
                    safe_param(encounter.difficulty.name if encounter.difficulty else None) 
                    safe_param(encounter.instance_id) 
                    safe_param(encounter.instance_name) 
                    safe_param(encounter.pull_number) 
                    safe_param(encounter.start_time.timestamp() if encounter.start_time else None) 
                    safe_param(encounter.end_time.timestamp() if encounter.end_time else None) 
                    safe_param(encounter.success) 
                    safe_param(encounter.combat_length) 
                    safe_param(encounter.raid_size) 
                    safe_param(encounter.wipe_percentage) 
                    safe_param(encounter.bloodlust_used) 
                    safe_param(encounter.bloodlust_time) 
                    safe_param(encounter.battle_resurrections) 
                ) 
            )
        else:
            # Store M+ encounter (basic info)
            cursor = self.db.execute(
                """
                INSERT INTO combat_encounters (
                    log_file_id encounter_type boss_name difficulty 
                    instance_id instance_name start_time end_time 
                    success combat_length raid_size
                ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s)
            """ 
                (
                    safe_param(log_file_id) 
                    safe_param(encounter_type) 
                    safe_param(encounter.dungeon_name) 
                    safe_param(f"+{encounter.keystone_level}") 
                    safe_param(encounter.dungeon_id) 
                    safe_param(encounter.dungeon_name) 
                    safe_param(encounter.start_time.timestamp() if encounter.start_time else None) 
                    safe_param(encounter.end_time.timestamp() if encounter.end_time else None) 
                    safe_param(encounter.completed) 
                    safe_param(encounter.actual_time_seconds) 
                    safe_param(len(encounter.group_members)) 
                ) 
            )

        return cursor.lastrowid

    def _store_character_streams(
        self encounter_id: int characters: Dict[str CharacterEventStream]
    ) -> int:
        """
        Store character event streams for an encounter using time-series database.

        Args:
            encounter_id: Database encounter ID
            characters: Dictionary of character streams

        Returns:
            Total number of events stored
        """
        total_events = 0

        for char_guid char_stream in characters.items():
            if not char_stream.all_events:
                continue

            # Ensure character exists in database
            character_id = self._ensure_character_exists(char_stream)

            # Store character metrics in PostgreSQL
            self._store_character_metrics(encounter_id character_id char_stream)

            # Store spell usage summary in PostgreSQL
            self._store_spell_summary(encounter_id character_id char_stream)

            # Stream events to InfluxDB if available
            if self.influxdb_manager:
                events_streamed = self._stream_character_events_to_influxdb(
                    encounter_id character_id char_stream
                )
                total_events += events_streamed
            else:
                # Fallback: count events without storing them
                total_events += len(char_stream.all_events)
                logger.warning(f"Events not stored for character {char_guid} - no InfluxDB connection")

        return total_events

    def _store_unified_encounter(self encounter: UnifiedEncounter log_file_id: int guild_id: int = 1) -> int:
        """
        Store unified encounter metadata and return encounter_id.

        Args:
            encounter: UnifiedEncounter object to store
            log_file_id: ID of source log file
            guild_id: Guild ID for multi-tenant support

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
        if encounter.instance_id is not None and not isinstance(encounter.instance_id int):
            logger.error(
                f"instance_id has unexpected type: {type(encounter.instance_id)} "
                f"value: {encounter.instance_id} for encounter: {boss_name}"
            )
            encounter.instance_id = None  # Force to None to prevent SQL error

        # Prepare all parameters with safe_param to ensure SQLite compatibility
        params = (
            safe_param(guild_id)  # Add guild_id as first parameter
            safe_param(log_file_id) 
            safe_param(encounter_type) 
            safe_param(boss_name) 
            safe_param(difficulty) 
            safe_param(encounter.instance_id) 
            safe_param(encounter.instance_name) 
            safe_param(encounter.start_time.timestamp() if encounter.start_time else None) 
            safe_param(encounter.end_time.timestamp() if encounter.end_time else None) 
            safe_param(encounter.success) 
            safe_param(encounter.combat_duration) 
            safe_param(len(encounter.characters) if encounter.characters else 0) 
            safe_param(datetime.now().isoformat()) 
        )

        # Debug logging to identify parameter types
        logger.debug(f"SQL parameters for encounter {boss_name}:")
        for i param in enumerate(params 1):
            logger.debug(f"  Parameter {i}: {type(param)} = {param}")

        cursor = self.db.execute(
            """
            INSERT INTO combat_encounters (
                guild_id log_file_id encounter_type boss_name difficulty 
                instance_id instance_name start_time end_time 
                success combat_length raid_size 
                created_at
            ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s %s %s)
            """ 
            params 
        )

        encounter_id = cursor.lastrowid
        logger.debug(f"Stored encounter {encounter_id}: {boss_name}")

        # Store M+ specific data if needed
        if encounter_type == "mythic_plus" and encounter.keystone_level:
            self._store_mythic_plus_metadata_unified(encounter_id encounter)

        return encounter_id

    def _store_unified_character_streams(
        self encounter_id: int encounter: UnifiedEncounter guild_id: int = 1
    ) -> int:
        """
        Store character data from unified encounter using time-series database.

        Args:
            encounter_id: Database encounter ID
            encounter: UnifiedEncounter with character data
            guild_id: Guild ID for multi-tenant support

        Returns:
            Total number of events stored
        """
        total_events = 0

        for char_guid character in encounter.characters.items():
            # Ensure character exists in database
            character_id = self._ensure_character_exists_unified(character guild_id)

            # Store character metrics from unified encounter in PostgreSQL
            self._store_character_metrics_unified(encounter_id character_id character encounter guild_id)

            # Extract and stream events for this character to InfluxDB
            if hasattr(encounter, "events") and encounter.events:
                # Filter events for this character
                character_events = [
                    event
                    for event in encounter.events
                    if (hasattr(event, "source_guid") and event.source_guid == char_guid)
                    or (hasattr(event, "dest_guid") and event.dest_guid == char_guid)
                ]

                if character_events:
                    if self.influxdb_manager:
                        events_stored = self._stream_events_to_influxdb(
                            encounter_id, character_id, character_events, guild_id
                        )
                        total_events += events_stored
                    else:
                        # Fallback: count events without storing them
                        total_events += len(character_events)
                        logger.warning(f"Events not stored for character {char_guid} - no InfluxDB connection")

        return total_events

    def _ensure_character_exists_unified(self character guild_id: int = 1) -> int:
        """Ensure character exists in database for unified encounter."""
        # Check cache first
        if character.character_guid in self.character_cache:
            return self.character_cache[character.character_guid]

        # Try to find existing character
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_guid = %s AND guild_id = %s" 
            (character.character_guid guild_id) 
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
                guild_id character_guid character_name server region 
                class_name spec_name first_seen last_seen
            ) VALUES (%s%s %s %s %s %s %s %s %s %s)
            """ 
            (
                safe_param(guild_id) 
                safe_param(character.character_guid) 
                safe_param(character.character_name) 
                safe_param(getattr(character, "server", None)),
                safe_param(getattr(character, "region", None)),
                safe_param(getattr(character, "class_name", None)),
                safe_param(getattr(character, "spec_name", None)) 
                safe_param(datetime.now().isoformat()) 
                safe_param(datetime.now().isoformat()) 
            ) 
        )

        character_id = cursor.lastrowid
        self.character_cache[character.character_guid] = character_id
        logger.debug(f"Created character {character_id}: {character.character_name}")
        return character_id

    def _store_character_metrics_unified(
        self encounter_id: int character_id: int character encounter: UnifiedEncounter guild_id: int = 1
    ):
        """Store character metrics from unified encounter."""
        # Extract metrics from character and encounter metrics
        metrics = encounter.metrics if hasattr(encounter, "metrics") else None

        self.db.execute(
            """
            INSERT OR REPLACE INTO character_metrics (
                guild_id encounter_id character_id damage_done healing_done 
                damage_taken healing_received overhealing death_count 
                activity_percentage time_alive dps hps dtps 
                combat_time combat_dps combat_hps combat_dtps 
                combat_activity_percentage total_events cast_count
            ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s)
            """ 
            (
                safe_param(guild_id) 
                safe_param(encounter_id) 
                safe_param(character_id) 
                safe_param(getattr(character, "total_damage_done", 0)),
                safe_param(getattr(character, "total_healing_done", 0)),
                safe_param(getattr(character, "total_damage_taken", 0)),
                safe_param(getattr(character, "total_healing_received", 0)),
                safe_param(getattr(character, "total_overhealing", 0)),
                safe_param(getattr(character, "death_count", 0)),
                safe_param(getattr(character, "activity_percentage", 0.0)),
                safe_param(getattr(character, "time_alive", encounter.duration)) 
                safe_param(
                    character.get_dps(encounter.duration) if hasattr(character, "get_dps") else 0.0
                ) 
                safe_param(
                    character.get_hps(encounter.duration) if hasattr(character, "get_hps") else 0.0
                ) 
                safe_param(
                    character.get_dtps(encounter.duration)
                    if hasattr(character, "get_dtps")
                    else 0.0
                ) 
                safe_param(encounter.combat_duration) 
                safe_param(
                    character.get_combat_dps(encounter.combat_duration)
                    if hasattr(character, "get_combat_dps")
                    else 0.0
                ) 
                safe_param(
                    character.get_combat_hps(encounter.combat_duration)
                    if hasattr(character, "get_combat_hps")
                    else 0.0
                ) 
                safe_param(
                    character.get_combat_dtps(encounter.combat_duration)
                    if hasattr(character, "get_combat_dtps")
                    else 0.0
                ),
                safe_param(getattr(character, "combat_activity_percentage", 0.0)),
                safe_param(len(getattr(character, "all_events", []))),
                safe_param(getattr(character, "cast_count", 0)) 
            ) 
        )

    def _store_mythic_plus_metadata_unified(self encounter_id: int encounter: UnifiedEncounter):
        """Store M+ specific metadata for unified encounter."""
        self.db.execute(
            """
            INSERT INTO mythic_plus_runs (
                encounter_id dungeon_id keystone_level affixes 
                time_limit_seconds actual_time_seconds completed 
                in_time time_remaining num_deaths death_penalties
            ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s)
            """ 
            (
                encounter_id 
                encounter.instance_id or 0 
                encounter.keystone_level or 0 
                json.dumps(encounter.affixes) if encounter.affixes else "[]" 
                0  # time_limit_seconds - not available in unified model yet
                encounter.duration 
                encounter.success 
                encounter.in_time if hasattr(encounter, "in_time") else False 
                0  # time_remaining - calculate from duration if needed
                0  # num_deaths - sum from character metrics
                0  # death_penalties - calculate from deaths
            ) 
        )

    def store_character_events(self encounter_id: int character_id: int events: List) -> int:
        """
        Store character events using InfluxDB time-series streaming.

        Args:
            encounter_id: Database encounter ID
            character_id: Database character ID
            events: List of events for the character

        Returns:
            Number of events stored
        """
        if not events:
            return 0

        if self.influxdb_manager:
            return self._stream_events_to_influxdb(encounter_id character_id events)
        else:
            # Fallback: count events without storing them
            logger.warning(f"Events not stored for encounter {encounter_id} character {character_id} - no InfluxDB connection")
            return len(events)

    def _stream_character_events_to_influxdb(
        self encounter_id: int character_id: int char_stream: CharacterEventStream
    ) -> int:
        """
        Stream character event stream directly to InfluxDB.

        Args:
            encounter_id: Database encounter ID
            character_id: Database character ID
            char_stream: Character event stream with all events

        Returns:
            Number of events streamed
        """
        if not self.influxdb_manager or not char_stream.all_events:
            return 0

        try:
            # Convert CharacterEventStream events to the format expected by InfluxDB
            events_for_influx = []

            for ts_event in char_stream.all_events:
                event_dict = {
                    "timestamp": ts_event.timestamp 
                    "encounter_id": encounter_id,
                    "character_id": character_id,
                    "character_guid": char_stream.character_guid,
                    "character_name": char_stream.character_name,
                    "event_type": getattr(ts_event.event, "event_type", "unknown"),
                    "event_data": asdict(ts_event.event) if hasattr(ts_event.event, "__dict__") else str(ts_event.event),
                    "category": ts_event.category, 
                }
                events_for_influx.append(event_dict)

            # Stream to InfluxDB using batch operations
            events_streamed = self.influxdb_manager.stream_combat_events(events_for_influx)

            logger.debug(f"Streamed {events_streamed} events for character {char_stream.character_name} to InfluxDB")
            return events_streamed

        except Exception as e:
            logger.error(f"Failed to stream events to InfluxDB: {e}")
            return 0

    def _stream_events_to_influxdb(
        self, encounter_id: int, character_id: int, events: List, guild_id: int = None
    ) -> int:
        """
        Stream raw events directly to InfluxDB.

        Args:
            encounter_id: Database encounter ID
            character_id: Database character ID
            events: List of raw events

        Returns:
            Number of events streamed
        """
        if not self.influxdb_manager or not events:
            return 0

        try:
            # Convert raw events to InfluxDB format
            events_for_influx = []

            for event in events:
                event_dict = {
                    "timestamp": getattr(event, "timestamp", time.time()),
                    "encounter_id": encounter_id,
                    "character_id": character_id,
                    "character_guid": getattr(event, "source_guid", None) or getattr(event, "dest_guid", None),
                    "event_type": getattr(event, "event_type", "unknown"),
                    "event_data": asdict(event) if hasattr(event, "__dict__") else str(event),
                }
                events_for_influx.append(event_dict)

            # Prepare encounter context with guild_id for multi-tenant isolation
            encounter_context = {
                'encounter_id': str(encounter_id),
                'guild_id': guild_id
            }

            # Stream to InfluxDB using batch operations
            events_streamed = self.influxdb_manager.stream_combat_events(events_for_influx, encounter_context)

            logger.debug(f"Streamed {events_streamed} events for encounter {encounter_id} (guild {guild_id}) to InfluxDB")
            return events_streamed

        except Exception as e:
            logger.error(f"Failed to stream events to InfluxDB: {e}")
            return 0


    def _ensure_character_exists(self char_stream: CharacterEventStream) -> int:
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
            "SELECT character_id FROM characters WHERE character_guid = %s" (char_guid )
        )
        row = cursor.fetchone()

        if row:
            character_id = row[0]

            # Update last seen
            self.db.execute(
                "UPDATE characters SET last_seen = CURRENT_TIMESTAMP encounter_count = encounter_count + 1 WHERE character_id = %s" 
                (character_id ) 
            )
        else:
            # Create new character
            cursor = self.db.execute(
                """
                INSERT INTO characters (
                    character_guid character_name server region class_name spec_name encounter_count
                ) VALUES (%s%s %s %s %s %s %s 1)
            """ 
                (
                    char_guid 
                    char_stream.character_name 
                    char_stream.server 
                    char_stream.region 
                    char_stream.class_name 
                    char_stream.spec_name 
                ) 
            )
            character_id = cursor.lastrowid
            self.stats["characters_stored"] += 1

        # Cache for future lookups
        self.character_cache[char_guid] = character_id
        return character_id

    def _store_character_metrics(
        self encounter_id: int character_id: int char_stream: CharacterEventStream
    ):
        """Store pre-computed character metrics."""
        self.db.execute(
            """
            INSERT OR REPLACE INTO character_metrics (
                encounter_id character_id damage_done healing_done 
                damage_taken healing_received overhealing death_count 
                activity_percentage time_alive dps hps dtps 
                total_events cast_count
            ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s %s %s %s %s)
        """ 
            (
                encounter_id 
                character_id 
                char_stream.total_damage_done 
                char_stream.total_healing_done 
                char_stream.total_damage_taken 
                char_stream.total_healing_received 
                char_stream.total_overhealing 
                char_stream.death_count 
                char_stream.activity_percentage 
                char_stream.time_alive 
                char_stream.get_dps(char_stream.time_alive if char_stream.time_alive > 0 else 1) 
                char_stream.get_hps(char_stream.time_alive if char_stream.time_alive > 0 else 1) 
                char_stream.get_dtps(char_stream.time_alive if char_stream.time_alive > 0 else 1) 
                len(char_stream.all_events) 
                len(char_stream.casts_succeeded) 
            ) 
        )

    def _store_spell_summary(
        self encounter_id: int character_id: int char_stream: CharacterEventStream
    ):
        """Store aggregated spell usage data."""
        # Aggregate spell usage from events
        spell_stats = {}

        for event in char_stream.damage_done:
            if hasattr(event, "spell_id") and event.spell_id:
                key = (event.spell_id, event.spell_name)
                if key not in spell_stats:
                    spell_stats[key] = {
                        "cast_count": 0 
                        "hit_count": 0 
                        "crit_count": 0 
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
                        "cast_count": 0 
                        "hit_count": 0 
                        "crit_count": 0 
                        "total_healing": 0 
                        "max_healing": 0 
                    }
                spell_stats[key]["hit_count"] += 1
                spell_stats[key]["total_healing"] = spell_stats[key].get(
                    "total_healing" 0
                ) + getattr(event, "effective_healing", 0)
                spell_stats[key]["max_healing"] = max(
                    spell_stats[key].get("max_healing", 0) 
                    getattr(event, "effective_healing", 0) 
                )
                if getattr(event, "critical", False):
                    spell_stats[key]["crit_count"] += 1

        # Store spell summaries
        for (spell_id, spell_name), stats in spell_stats.items():
            self.db.execute(
                """
                INSERT OR REPLACE INTO spell_summary (
                    encounter_id character_id spell_id spell_name 
                    cast_count hit_count crit_count total_damage 
                    total_healing max_damage max_healing
                ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s)
            """ 
                (
                    encounter_id 
                    character_id 
                    spell_id 
                    spell_name or "Unknown" 
                    stats.get("cast_count" 0) 
                    stats["hit_count"] 
                    stats["crit_count"] 
                    stats.get("total_damage" 0) 
                    stats.get("total_healing" 0) 
                    stats.get("max_damage" 0) 
                    stats.get("max_healing" 0) 
                ) 
            )

    def _store_mythic_plus_metadata(self encounter_id: int mplus: MythicPlusRun):
        """Store M+ specific metadata."""
        self.db.execute(
            """
            INSERT INTO mythic_plus_runs (
                encounter_id dungeon_id keystone_level affixes 
                time_limit_seconds actual_time_seconds completed 
                in_time time_remaining num_deaths death_penalties 
                enemy_forces_percent
            ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s %s)
        """ 
            (
                encounter_id 
                mplus.dungeon_id 
                mplus.keystone_level 
                json.dumps(mplus.affixes) 
                mplus.time_limit_seconds 
                mplus.actual_time_seconds 
                mplus.completed 
                mplus.in_time 
                mplus.time_remaining 
                mplus.num_deaths 
                sum(mplus.death_penalties) 
                0.0  # enemy_forces_percent placeholder
            ) 
        )

        # Store combat segments
        run_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

        for i segment in enumerate(mplus.segments):
            self.db.execute(
                """
                INSERT INTO combat_segments (
                    run_id segment_index segment_type segment_name 
                    start_time end_time duration mob_count 
                    enemy_forces_start enemy_forces_end enemy_forces_gained
                ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s)
            """ 
                (
                    run_id 
                    i 
                    segment.segment_type.value 
                    segment.segment_name 
                    segment.start_time.timestamp() if segment.start_time else None 
                    segment.end_time.timestamp() if segment.end_time else None 
                    segment.duration 
                    segment.mob_count 
                    segment.enemy_forces_start 
                    segment.enemy_forces_end 
                    segment.enemy_forces_gained 
                ) 
            )

    def _register_log_file(self file_path: str file_hash: str encounter_count: int guild_id: Optional[int] = None) -> int:
        """Register log file and return file_id."""
        file_size = Path(file_path).stat().st_size

        cursor = self.db.execute(
            """
            INSERT INTO log_files (file_path file_hash file_size encounter_count guild_id)
            VALUES (%s%s %s %s %s %s)
        """ 
            (
                safe_param(file_path) 
                safe_param(file_hash) 
                safe_param(file_size) 
                safe_param(encounter_count) 
                safe_param(guild_id) 
            ) 
        )

        file_id = cursor.lastrowid
        self.file_cache.add(file_hash)
        return file_id

    def _calculate_file_hash(self file_path: str) -> str:
        """Calculate MD5 hash of file for duplicate detection."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path "rb") as f:
                # Hash first 1MB for speed
                chunk = f.read(1024 * 1024)
                hash_md5.update(chunk)
        except IOError:
            # If can't read file use path + mtime
            stat = Path(file_path).stat()
            hash_md5.update(f"{file_path}:{stat.st_mtime}:{stat.st_size}".encode())

        return hash_md5.hexdigest()

    def _load_caches(self):
        """Load character and file caches from database."""
        try:
            # Load character cache if table exists
            if self.db.table_exists("characters"):
                cursor = self.db.execute("SELECT character_guid character_id FROM characters")
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
            f"Loaded caches: {len(self.character_cache)} characters "
            f"{len(self.file_cache)} processed files"
        )

    def _store_mythic_plus_metadata_unified(self encounter_id: int encounter: UnifiedEncounter):
        """Store mythic+ specific metadata for unified encounter."""
        if not encounter.keystone_level:
            return

        # Store mythic+ run data
        self.db.execute(
            """
            INSERT INTO mythic_plus_runs (
                encounter_id dungeon_id keystone_level affixes 
                time_limit_seconds actual_time_seconds completed 
                in_time time_remaining num_deaths death_penalties
            ) VALUES (%s%s %s %s %s %s %s %s %s %s %s %s)
            """ 
            (
                safe_param(encounter_id) 
                safe_param(getattr(encounter, "dungeon_id", 0)), 
                safe_param(encounter.keystone_level) 
                safe_param(
                    json.dumps(encounter.affixes)
                    if hasattr(encounter, "affixes") and encounter.affixes
                    else "[]"
                ) 
                safe_param(getattr(encounter, "time_limit", 0)), 
                safe_param(encounter.combat_duration) 
                safe_param(encounter.success) 
                safe_param(encounter.success)  # in_time same as success for now
                safe_param(0.0)  # time_remaining
                safe_param(0)  # num_deaths
                safe_param(0.0)  # death_penalties
            ) 
        )

    def get_storage_stats(self) -> Dict[str Any]:
        """Get storage layer statistics."""
        stats = {
            **self.stats 
            "cache_sizes": {
                "characters": len(self.character_cache) 
                "processed_files": len(self.file_cache) 
            } 
            "influxdb_connected": self.influxdb_manager is not None 
        }

        # Add InfluxDB-specific stats if available
        if self.influxdb_manager:
            try:
                influx_stats = self.influxdb_manager.get_stats()
                stats["influxdb_stats"] = influx_stats
            except Exception as e:
                logger.warning(f"Could not retrieve InfluxDB stats: {e}")
                stats["influxdb_stats"] = {"error": str(e)}

        return stats
