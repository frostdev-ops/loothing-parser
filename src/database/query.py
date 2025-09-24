"""
High-speed query API for WoW combat log database with time-series support.

Provides optimized queries with caching and efficient time-series queries
for instant data retrieval from InfluxDB event storage and PostgreSQL metadata.
"""

import time
import threading
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from functools import lru_cache

from .schema import DatabaseManager
from .influxdb_direct_manager import InfluxDBDirectManager
from src.models.character_events import TimestampedEvent, CharacterEventStream
from src.models.encounter_models import RaidEncounter, MythicPlusRun

# Import TimeRange from common models if not already available
try:
    from ..models.common import TimeRange
except ImportError:
    # Define locally if not available
    @dataclass
    class TimeRange:
        start: datetime
        end: datetime

logger = logging.getLogger(__name__)


@dataclass
class CharacterMetrics:
    """Character performance metrics for a single encounter."""

    character_name: str
    character_guid: str
    class_name: Optional[str]
    spec_name: Optional[str]
    damage_done: int
    healing_done: int
    damage_taken: int
    death_count: int
    dps: float
    hps: float
    activity_percentage: float
    time_alive: float
    total_events: int
    # Combat-aware metrics
    combat_time: float = 0.0
    combat_dps: float = 0.0
    combat_hps: float = 0.0
    combat_dtps: float = 0.0
    combat_activity_percentage: float = 0.0
    # Absorption tracking
    damage_absorbed_by_shields: int = 0
    damage_absorbed_for_me: int = 0


@dataclass
class EncounterSummary:
    """Summary information for an encounter."""

    encounter_id: int
    encounter_type: str
    boss_name: str
    difficulty: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    success: bool
    combat_length: float
    raid_size: int
    character_count: int


@dataclass
class SpellUsage:
    """Spell usage statistics for a character."""

    spell_id: int
    spell_name: str
    cast_count: int
    hit_count: int
    crit_count: int
    total_damage: int
    total_healing: int
    max_damage: int
    max_healing: int
    crit_percentage: float


class QueryCache:
    """LRU cache for query results with TTL support."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        Initialize query cache.

        Args:
            max_size: Maximum number of cached items
            ttl_seconds: Time-to-live for cache entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.access_order: List[str] = []
        self.lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        with self.lock:
            if key not in self.cache:
                return None

            value, timestamp = self.cache[key]
            if time.time() - timestamp > self.ttl_seconds:
                # Expired
                del self.cache[key]
                self.access_order.remove(key)
                return None

            # Move to end (most recently used)
            self.access_order.remove(key)
            self.access_order.append(key)
            return value

    def put(self, key: str, value: Any):
        """Cache a value with current timestamp."""
        with self.lock:
            # Remove if already exists
            if key in self.cache:
                self.access_order.remove(key)

            # Add new entry
            self.cache[key] = (value, time.time())
            self.access_order.append(key)

            # Evict oldest if over capacity
            while len(self.cache) > self.max_size:
                oldest_key = self.access_order.pop(0)
                del self.cache[oldest_key]

    def clear(self):
        """Clear all cached entries."""
        with self.lock:
            self.cache.clear()
            self.access_order.clear()

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
            }


class QueryAPI:
    """
    High-performance query interface for combat log database with time-series support.

    Provides optimized queries with automatic caching time-series queries from InfluxDB 
    and efficient data retrieval patterns for common use cases.
    """

    def __init__(self, db: DatabaseManager, cache_size: int = 1000):
        """
        Initialize query API.

        Args:
            db: Database manager instance (hybrid manager with InfluxDB)
            cache_size: Maximum number of cached query results
        """
        self.db = db
        self.cache = QueryCache(max_size=cache_size)

        # Initialize time-series manager if available
        if hasattr(db, 'influxdb') and db.influxdb:
            self.influxdb_manager = InfluxDBDirectManager(
                url=db.influxdb.url,
                token=db.influxdb.token,
                org=db.influxdb.org,
                bucket=db.influxdb.bucket,
            )
        else:
            self.influxdb_manager = None
            logger.warning("No InfluxDB connection available for time-series queries")

        # Query statistics
        self.stats = {
            "queries_executed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_query_time": 0.0,
            "time_series_queries": 0,
            "influxdb_query_time": 0.0,
        }

    def get_encounter(
        self, encounter_id: int, guild_id: Optional[int] = None
    ) -> Optional[EncounterSummary]:
        """
        Get encounter summary by ID.

        Args:
            encounter_id: Database encounter ID
            guild_id: Guild ID for multi-tenant filtering (optional for backward compatibility)

        Returns:
            EncounterSummary or None if not found
        """
        cache_key = f"encounter:{encounter_id}:guild:{guild_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build query with optional guild filtering
        query = """
            SELECT
                encounter_id, encounter_type, boss_name, difficulty,
                start_time, end_time, success, combat_length, raid_size,
                (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
            FROM combat_encounters e
            WHERE encounter_id = %s
        """
        params = [encounter_id]

        if guild_id is not None:
            query += " AND guild_id = %s"
            params.append(guild_id)

        cursor = self.db.execute(query, params)

        row = cursor.fetchone()
        if not row:
            return None

        encounter = EncounterSummary(
            encounter_id=row[0],
            encounter_type=row[1],
            boss_name=row[2],
            difficulty=row[3],
            start_time=datetime.fromtimestamp(row[4]) if row[4] else None,
            end_time=datetime.fromtimestamp(row[5]) if row[5] else None,
            success=bool(row[6]),
            combat_length=row[7],
            raid_size=row[8],
            character_count=row[9],
        )

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, encounter)
        return encounter

    def get_recent_encounters(
        self, limit: int = 10, guild_id: Optional[int] = None
    ) -> List[EncounterSummary]:
        """
        Get recent encounters ordered by creation time.

        Args:
            limit: Maximum number of encounters to return
            guild_id: Guild ID for multi-tenant filtering (optional for backward compatibility)

        Returns:
            List of EncounterSummary objects
        """
        cache_key = f"recent_encounters:{limit}:guild:{guild_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build query with optional guild filtering
        query = """
            SELECT
                encounter_id, encounter_type, boss_name, difficulty,
                start_time, end_time, success, combat_length, raid_size,
                (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
            FROM combat_encounters e
        """
        params = []

        if guild_id is not None:
            query += " WHERE guild_id = %s"
            params.append(guild_id)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cursor = self.db.execute(query, params)

        encounters = []
        for row in cursor:
            encounter = EncounterSummary(
                encounter_id=row[0],
                encounter_type=row[1],
                boss_name=row[2],
                difficulty=row[3],
                start_time=datetime.fromtimestamp(row[4]) if row[4] else None,
                end_time=datetime.fromtimestamp(row[5]) if row[5] else None,
                success=bool(row[6]),
                combat_length=row[7],
                raid_size=row[8],
                character_count=row[9],
            )
            encounters.append(encounter)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, encounters)
        return encounters

    def search_encounters(
        self,
        boss_name: Optional[str] = None,
        difficulty: Optional[str] = None,
        encounter_type: Optional[str] = None,
        success: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        guild_id: Optional[int] = None,
    ) -> List[EncounterSummary]:
        """
        Search encounters with filters.

        Args:
            boss_name: Filter by boss name (partial match)
            difficulty: Filter by difficulty
            encounter_type: Filter by type ('raid' or 'mythic_plus')
            success: Filter by success status
            start_date: Filter by start date range
            end_date: Filter by end date range
            limit: Maximum results
            guild_id: Guild ID for multi-tenant filtering (optional for backward compatibility)

        Returns:
            List of matching encounters
        """
        # Build cache key from parameters
        cache_key = f"search:{boss_name}:{difficulty}:{encounter_type}:{success}:{start_date}:{end_date}:{limit}:guild:{guild_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build dynamic query
        conditions = []
        params = []

        # Add guild filtering first for optimal index usage
        if guild_id is not None:
            conditions.append("guild_id = %s")
            params.append(guild_id)

        if boss_name:
            conditions.append("boss_name LIKE %s")
            params.append(f"%{boss_name}%")

        if difficulty:
            conditions.append("difficulty = %s")
            params.append(difficulty)

        if encounter_type:
            conditions.append("encounter_type = %s")
            params.append(encounter_type)

        if success is not None:
            conditions.append("success = %s")
            params.append(success)

        if start_date:
            conditions.append("start_time >= %s")
            params.append(start_date.timestamp())

        if end_date:
            conditions.append("start_time <= %s")
            params.append(end_date.timestamp())

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        cursor = self.db.execute(
            f"""
            SELECT
                encounter_id, encounter_type, boss_name, difficulty,
                start_time, end_time, success, combat_length, raid_size,
                (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
            FROM combat_encounters e
            {where_clause}
            ORDER BY start_time DESC
            LIMIT %s
        """,
            params,
        )

        encounters = []
        for row in cursor:
            encounter = EncounterSummary(
                encounter_id=row[0],
                encounter_type=row[1],
                boss_name=row[2],
                difficulty=row[3],
                start_time=datetime.fromtimestamp(row[4]) if row[4] else None,
                end_time=datetime.fromtimestamp(row[5]) if row[5] else None,
                success=bool(row[6]),
                combat_length=row[7],
                raid_size=row[8],
                character_count=row[9],
            )
            encounters.append(encounter)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, encounters)
        return encounters

    def get_character_metrics(
        self,
        encounter_id: int,
        character_name: Optional[str] = None,
        guild_id: Optional[int] = None,
    ) -> List[CharacterMetrics]:
        """
        Get character performance metrics for an encounter.

        Args:
            encounter_id: Database encounter ID
            character_name: Optional filter by character name
            guild_id: Guild ID for multi-tenant filtering (optional for backward compatibility)

        Returns:
            List of CharacterMetrics
        """
        cache_key = f"metrics:{encounter_id}:{character_name}:guild:{guild_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build query with optional character filter and guild filtering
        query = """
            SELECT
                c.character_name, c.character_guid, c.class_name, c.spec_name,
                m.damage_done, m.healing_done, m.damage_taken, m.death_count,
                m.dps, m.hps, m.activity_percentage, m.time_alive, m.total_events
            FROM character_metrics m
            JOIN characters c ON m.character_id = c.character_id
            WHERE m.encounter_id = %s
        """
        params = [encounter_id]

        # Add guild filtering for both tables
        if guild_id is not None:
            query += " AND m.guild_id = %s AND c.guild_id = %s"
            params.extend([guild_id, guild_id])

        if character_name:
            query += " AND c.character_name LIKE %s"
            params.append(f"%{character_name}%")

        query += " ORDER BY m.dps DESC"

        cursor = self.db.execute(query, params)

        metrics = []
        for row in cursor:
            metric = CharacterMetrics(
                character_name=row[0],
                character_guid=row[1],
                class_name=row[2],
                spec_name=row[3],
                damage_done=row[4],
                healing_done=row[5],
                damage_taken=row[6],
                death_count=row[7],
                dps=row[8],
                hps=row[9],
                activity_percentage=row[10],
                time_alive=row[11],
                total_events=row[12],
            )
            metrics.append(metric)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, metrics)
        return metrics

    def get_top_performers(
        self,
        metric: str = "dps",
        encounter_type: Optional[str] = None,
        boss_name: Optional[str] = None,
        days: int = 7,
        limit: int = 10,
        guild_id: Optional[int] = None,
    ) -> List[CharacterMetrics]:
        """
        Get top performing characters by metric.

        Args:
            metric: Metric to rank by ('dps' 'hps' 'damage_done' etc.)
            encounter_type: Filter by encounter type
            boss_name: Filter by boss name
            days: Look back this many days
            limit: Maximum results

        Returns:
            List of top performers
        """
        cache_key = f"top:{metric}:{encounter_type}:{boss_name}:{days}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Validate metric name for security
        valid_metrics = {
            "dps",
            "hps",
            "damage_done",
            "healing_done",
            "activity_percentage",
        }
        if metric not in valid_metrics:
            raise ValueError(f"Invalid metric: {metric}")

        # Build query with filters
        conditions = []
        params = []

        # Date filter
        cutoff_date = datetime.now() - timedelta(days=days)
        conditions.append("e.created_at >= %s")
        params.append(cutoff_date)

        if encounter_type:
            conditions.append("e.encounter_type = %s")
            params.append(encounter_type)

        if boss_name:
            conditions.append("e.boss_name LIKE %s")
            params.append(f"%{boss_name}%")

        where_clause = "WHERE " + " AND ".join(conditions)
        params.append(limit)

        cursor = self.db.execute(
            f"""
            SELECT
                c.character_name, c.character_guid, c.class_name, c.spec_name,
                m.damage_done, m.healing_done, m.damage_taken, m.death_count,
                m.dps, m.hps, m.activity_percentage, m.time_alive, m.total_events
            FROM character_metrics m
            JOIN characters c ON m.character_id = c.character_id
            JOIN encounters e ON m.encounter_id = e.encounter_id
            {where_clause}
            ORDER BY m.{metric} DESC
            LIMIT %s
        """,
            params,
        )

        performers = []
        for row in cursor:
            performer = CharacterMetrics(
                character_name=row[0],
                character_guid=row[1],
                class_name=row[2],
                spec_name=row[3],
                damage_done=row[4],
                healing_done=row[5],
                damage_taken=row[6],
                death_count=row[7],
                dps=row[8],
                hps=row[9],
                activity_percentage=row[10],
                time_alive=row[11],
                total_events=row[12],
            )
            performers.append(performer)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, performers)
        return performers

    def get_character_events(
        self,
        character_name: str,
        encounter_id: int,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        event_types: Optional[List[str]] = None,
    ) -> List[TimestampedEvent]:
        """
        Get detailed events for a character in an encounter.

        Args:
            character_name: Character name
            encounter_id: Encounter ID
            start_time: Optional start timestamp filter
            end_time: Optional end timestamp filter
            event_types: Optional filter by event types

        Returns:
            List of decompressed TimestampedEvent objects
        """
        cache_key = f"events:{character_name}:{encounter_id}:{start_time}:{end_time}:{event_types}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_query_time = time.time()
        self.stats["queries_executed"] += 1

        # Get character ID
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_name = %s",
            (character_name,)
        )
        row = cursor.fetchone()
        if not row:
            return []

        character_id = row[0]

        # Get event blocks for this character/encounter
        query = """
            SELECT block_index, start_time, end_time, compressed_data
            FROM event_blocks
            WHERE encounter_id = %s AND character_id = %s
        """
        params = [encounter_id, character_id]

        if start_time is not None:
            query += " AND end_time >= %s"
            params.append(start_time)

        if end_time is not None:
            query += " AND start_time <= %s"
            params.append(end_time)

        query += " ORDER BY block_index"

        cursor = self.db.execute(query, params)
        blocks = cursor.fetchall()

        if not blocks:
            return []

        # Decompress all blocks in parallel
        def decompress_block(block_data):
            compressed = block_data[3]  # compressed_data column
            return self.decompressor.decompress_events(compressed)

        # Use thread pool for parallel decompression
        futures = [self.executor.submit(decompress_block, block) for block in blocks]
        all_events = []

        for future in futures:
            block_events = future.result()
            all_events.extend(block_events)

        # Apply filters
        filtered_events = all_events

        if start_time is not None or end_time is not None:
            filtered_events = [
                e
                for e in filtered_events
                if (start_time is None or e.timestamp >= start_time)
                and (end_time is None or e.timestamp <= end_time)
            ]

        if event_types:
            filtered_events = [e for e in filtered_events if e.event.event_type in event_types]

        # Sort by timestamp
        filtered_events.sort(key=lambda e: e.timestamp)

        query_time = time.time() - start_query_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1
        self.stats["events_decompressed"] += len(all_events)

        # Cache smaller result sets only
        if len(filtered_events) < 10000:
            self.cache.put(cache_key, filtered_events)

        return filtered_events

    def get_spell_usage(
        self,
        character_name: str,
        encounter_id: Optional[int] = None,
        spell_name: Optional[str] = None,
        days: int = 30,
    ) -> List[SpellUsage]:
        """
        Get spell usage statistics for a character.

        Args:
            character_name: Character name
            encounter_id: Optional specific encounter
            spell_name: Optional spell name filter
            days: Look back this many days if no encounter specified

        Returns:
            List of SpellUsage statistics
        """
        cache_key = f"spells:{character_name}:{encounter_id}:{spell_name}:{days}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build query with filters
        query = """
            SELECT
                s.spell_id, s.spell_name, s.cast_count, s.hit_count, s.crit_count,
                s.total_damage, s.total_healing, s.max_damage, s.max_healing
            FROM spell_summary s
            JOIN characters c ON s.character_id = c.character_id
        """
        conditions = ["c.character_name = %s"]
        params = [character_name]

        if encounter_id:
            conditions.append("s.encounter_id = %s")
            params.append(encounter_id)
        else:
            # Date range filter
            cutoff_date = datetime.now() - timedelta(days=days)
            query += " JOIN encounters e ON s.encounter_id = e.encounter_id"
            conditions.append("e.created_at >= %s")
            params.append(cutoff_date)

        if spell_name:
            conditions.append("s.spell_name LIKE %s")
            params.append(f"%{spell_name}%")

        query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY s.total_damage + s.total_healing DESC"

        cursor = self.db.execute(query, params)

        spell_usages = []
        for row in cursor:
            crit_percentage = (row[4] / row[3] * 100) if row[3] > 0 else 0.0

            usage = SpellUsage(
                spell_id=row[0],
                spell_name=row[1],
                cast_count=row[2],
                hit_count=row[3],
                crit_count=row[4],
                total_damage=row[5],
                total_healing=row[6],
                max_damage=row[7],
                max_healing=row[8],
                crit_percentage=crit_percentage,
            )
            spell_usages.append(usage)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, spell_usages)
        return spell_usages

    def get_encounters(
        self,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        guild_id: Optional[int] = None,
    ) -> List[EncounterSummary]:
        """
        Get encounters with pagination and filtering.

        Args:
            limit: Maximum number of encounters to return
            offset: Number of encounters to skip
            filters: Optional filters (boss_name difficulty encounter_type success etc.)
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            guild_id: Guild ID for multi-tenant filtering

        Returns:
            List of EncounterSummary objects
        """
        # Use filters to determine what to search for
        if filters:
            # Delegate to search_encounters with filters
            return self.search_encounters(
                boss_name=filters.get('boss_name'),
                difficulty=filters.get('difficulty'),
                encounter_type=filters.get('encounter_type'),
                success=filters.get('success'),
                start_date=filters.get('start_date'),
                end_date=filters.get('end_date'),
                limit=limit,
                guild_id=guild_id,
            )[offset:offset+limit] if offset > 0 else self.search_encounters(
                boss_name=filters.get('boss_name'),
                difficulty=filters.get('difficulty'),
                encounter_type=filters.get('encounter_type'),
                success=filters.get('success'),
                start_date=filters.get('start_date'),
                end_date=filters.get('end_date'),
                limit=limit + offset,
                guild_id=guild_id,
            )[offset:]
        else:
            # No filters get recent encounters with offset
            cache_key = f"encounters:{limit}:{offset}:{sort_by}:{sort_order}:guild:{guild_id}"
            cached = self.cache.get(cache_key)
            if cached:
                self.stats["cache_hits"] += 1
                return cached

            start_time = time.time()
            self.stats["queries_executed"] += 1

            # Build query with optional guild filtering
            query = """
                SELECT
                    encounter_id, encounter_type, boss_name, difficulty,
                    start_time, end_time, success, combat_length, raid_size,
                    (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
                FROM combat_encounters e
            """
            params = []

            if guild_id is not None:
                query += " WHERE guild_id = %s"
                params.append(guild_id)

            # Validate sort_by column for security
            valid_sort_columns = {
                "created_at", "start_time", "end_time", "boss_name",
                "difficulty", "combat_length", "raid_size"
            }
            if sort_by not in valid_sort_columns:
                sort_by = "created_at"

            # Validate sort_order
            if sort_order.lower() not in ["asc", "desc"]:
                sort_order = "desc"

            query += f" ORDER BY {sort_by} {sort_order.upper()} LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor = self.db.execute(query, params)

            encounters = []
            for row in cursor:
                encounter = EncounterSummary(
                    encounter_id=row[0],
                    encounter_type=row[1],
                    boss_name=row[2],
                    difficulty=row[3],
                    start_time=datetime.fromtimestamp(row[4]) if row[4] else None,
                    end_time=datetime.fromtimestamp(row[5]) if row[5] else None,
                    success=bool(row[6]),
                    combat_length=row[7],
                    raid_size=row[8],
                    character_count=row[9],
                )
                encounters.append(encounter)

            query_time = time.time() - start_time
            self.stats["total_query_time"] += query_time
            self.stats["cache_misses"] += 1

            self.cache.put(cache_key, encounters)
            return encounters

    def get_encounters_count(
        self,
        filters: Optional[Dict[str, Any]] = None,
        guild_id: Optional[int] = None,
    ) -> int:
        """
        Get total count of encounters matching filters.

        Args:
            filters: Optional filters (boss_name difficulty encounter_type success etc.)
            guild_id: Guild ID for multi-tenant filtering

        Returns:
            Total count of matching encounters
        """
        cache_key = f"count:{filters}:guild:{guild_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build dynamic query
        conditions = []
        params = []

        # Add guild filtering first
        if guild_id is not None:
            conditions.append("guild_id = %s")
            params.append(guild_id)

        if filters:
            if filters.get('boss_name'):
                conditions.append("boss_name LIKE %s")
                params.append(f"%{filters['boss_name']}%")

            if filters.get('difficulty'):
                conditions.append("difficulty = %s")
                params.append(filters['difficulty'])

            if filters.get('encounter_type'):
                conditions.append("encounter_type = %s")
                params.append(filters['encounter_type'])

            if filters.get('success') is not None:
                conditions.append("success = %s")
                params.append(filters['success'])

            if filters.get('start_date'):
                conditions.append("start_time >= %s")
                params.append(filters['start_date'].timestamp())

            if filters.get('end_date'):
                conditions.append("start_time <= %s")
                params.append(filters['end_date'].timestamp())

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor = self.db.execute(
            f"SELECT COUNT(*) FROM combat_encounters {where_clause}",
            params,
        )
        count = cursor.fetchone()[0]

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, count)
        return count

    def get_encounter_detail(
        self,
        encounter_id: int,
        guild_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about an encounter.

        Args:
            encounter_id: Database encounter ID
            guild_id: Guild ID for multi-tenant filtering

        Returns:
            Detailed encounter information including metrics and events
        """
        # Get basic encounter info
        encounter = self.get_encounter(encounter_id, guild_id)
        if not encounter:
            return None

        # Get character metrics for this encounter
        metrics = self.get_character_metrics(encounter_id, guild_id=guild_id)

        # Calculate aggregates
        total_damage = sum(m.damage_done for m in metrics)
        total_healing = sum(m.healing_done for m in metrics)
        total_deaths = sum(m.death_count for m in metrics)
        participant_names = [m.character_name for m in metrics]

        # Return flat structure matching EncounterDetail model
        return {
            "encounter_id": encounter.encounter_id,
            "encounter_type": encounter.encounter_type,
            "boss_name": encounter.boss_name,
            "difficulty": encounter.difficulty or "",
            "zone_name": encounter.boss_name,  # Use boss_name as zone for now
            "start_time": encounter.start_time.isoformat() if encounter.start_time else None,
            "end_time": encounter.end_time.isoformat() if encounter.end_time else None,
            "duration": encounter.combat_length,
            "combat_duration": encounter.combat_length,
            "success": encounter.success,
            "wipe_percentage": None,
            "participants": participant_names,
            "raid_size": encounter.raid_size,
            "total_damage": total_damage,
            "total_healing": total_healing,
            "total_deaths": total_deaths,
        }

    def get_characters(
        self,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "last_seen",
        sort_order: str = "desc",
        guild_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get a list of characters with optional filtering.

        Args:
            limit: Maximum number of characters to return
            offset: Number of characters to skip
            filters: Optional filters
            sort_by: Field to sort by
            sort_order: Sort order (asc/desc)
            guild_id: Guild ID for multi-tenant filtering

        Returns:
            List of character profiles
        """
        conditions = []
        params = []

        if guild_id is not None:
            conditions.append("guild_id = %s")
            params.append(guild_id)

        if filters:
            if filters.get('server'):
                conditions.append("server = %s")
                params.append(filters['server'])

            if filters.get('class_name'):
                conditions.append("class_name = %s")
                params.append(filters['class_name'])

            if filters.get('min_encounters'):
                conditions.append("encounter_count >= %s")
                params.append(filters['min_encounters'])

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Map sort fields to database columns
        sort_map = {
            "last_seen": "last_seen",
            "total_encounters": "encounter_count",
            "average_dps": "encounter_count",  # Use encounter_count as fallback since average_dps doesn't exist
        }
        order_by = f"ORDER BY {sort_map.get(sort_by, 'last_seen')} {sort_order}"

        cursor = self.db.execute(
            f"""
            SELECT
                character_id,
                character_name,
                server,
                region,
                class_name,
                spec_name,
                encounter_count,
                last_seen,
                guild_id
            FROM characters
            {where_clause}
            {order_by}
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset]
        )

        characters = []
        for row in cursor.fetchall():
            characters.append({
                "character_id": row[0],
                "name": row[1],
                "server": row[2] or "Unknown",
                "region": row[3] or "US",
                "class_name": row[4] or "Unknown",
                "spec": row[5] or "Unknown",
                "encounter_count": row[6] or 0,
                "average_dps": 0.0,  # Not in table default value
                "average_hps": 0.0,  # Not in table default value
                "last_seen": row[7],
                "guild_id": row[8],
            })

        return characters

    def get_characters_count(
        self,
        filters: Optional[Dict[str, Any]] = None,
        guild_id: Optional[int] = None,
    ) -> int:
        """
        Get total count of characters matching filters.

        Args:
            filters: Optional filters (server class_name min_encounters etc.)
            guild_id: Guild ID for multi-tenant filtering

        Returns:
            Total count of matching characters
        """
        cache_key = f"char_count:{filters}:guild:{guild_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build dynamic query
        conditions = []
        params = []

        # Add guild filtering first
        if guild_id is not None:
            conditions.append("guild_id = %s")
            params.append(guild_id)

        if filters:
            if filters.get('server'):
                conditions.append("server = %s")
                params.append(filters['server'])

            if filters.get('region'):
                conditions.append("region = %s")
                params.append(filters['region'])

            if filters.get('class_name'):
                conditions.append("class_name = %s")
                params.append(filters['class_name'])

            if filters.get('min_encounters'):
                conditions.append("encounter_count >= %s")
                params.append(filters['min_encounters'])

            if filters.get('active_since'):
                conditions.append("last_seen >= %s")
                params.append(filters['active_since'])

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor = self.db.execute(
            f"SELECT COUNT(*) FROM characters {where_clause}",
            params,
        )
        count = cursor.fetchone()[0]

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, count)
        return count

    def get_guild(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """
        Get guild by ID.

        Args:
            guild_id: Guild database ID

        Returns:
            Guild information or None if not found
        """
        cache_key = f"guild:{guild_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        cursor = self.db.execute(
            """
            SELECT
                guild_id, guild_name, server, region, faction,
                created_at, updated_at, is_active
            FROM guilds
            WHERE guild_id = %s
            """,
            (guild_id,)
        )

        row = cursor.fetchone()
        if not row:
            return None

        guild = {
            "guild_id": row[0],
            "guild_name": row[1],
            "server": row[2],
            "region": row[3],
            "faction": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "is_active": bool(row[7]),
        }

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, guild)
        return guild

    def get_guilds(
        self,
        limit: int = 20,
        offset: int = 0,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all guilds with pagination.

        Args:
            limit: Maximum number of guilds to return
            offset: Number of guilds to skip
            is_active: Filter by active status

        Returns:
            List of guild information dictionaries
        """
        cache_key = f"guilds:{limit}:{offset}:{is_active}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        query = """
            SELECT
                guild_id, guild_name, server, region, faction,
                created_at, updated_at, is_active,
                (SELECT COUNT(*) FROM combat_encounters WHERE guild_id = g.guild_id) as encounter_count
            FROM guilds g
        """
        params = []

        if is_active is not None:
            query += " WHERE is_active = %s"
            params.append(is_active)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor = self.db.execute(query, params)

        guilds = []
        for row in cursor:
            guild = {
                "guild_id": row[0],
                "guild_name": row[1],
                "server": row[2],
                "region": row[3],
                "faction": row[4],
                "created_at": row[5],
                "updated_at": row[6],
                "is_active": bool(row[7]),
                "encounter_count": row[8],
            }
            guilds.append(guild)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, guilds)
        return guilds

    def create_guild(
        self,
        guild_name: str,
        server: str,
        region: str = "US",
        faction: Optional[str] = None,
    ) -> int:
        """
        Create new guild.

        Args:
            guild_name: Name of the guild
            server: Server name
            region: Region (default: US)
            faction: Optional faction (Alliance/Horde)

        Returns:
            New guild ID
        """
        cursor = self.db.execute(
            """
            INSERT INTO guilds (guild_name, server, region, faction)
            VALUES (%s, %s, %s, %s)
            """,
            (guild_name, server, region, faction)
        )
        self.db.commit()

        # Clear guild-related caches
        self.cache.clear()

        return cursor.lastrowid

    def update_guild(
        self,
        guild_id: int,
        guild_name: Optional[str] = None,
        server: Optional[str] = None,
        region: Optional[str] = None,
        faction: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """
        Update guild information.

        Args:
            guild_id: Guild ID to update
            guild_name: New guild name
            server: New server
            region: New region
            faction: New faction
            is_active: Active status

        Returns:
            True if successful
        """
        updates = []
        params = []

        if guild_name is not None:
            updates.append("guild_name = %s")
            params.append(guild_name)

        if server is not None:
            updates.append("server = %s")
            params.append(server)

        if region is not None:
            updates.append("region = %s")
            params.append(region)

        if faction is not None:
            updates.append("faction = %s")
            params.append(faction)

        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(guild_id)

        self.db.execute(
            f"UPDATE guilds SET {', '.join(updates)} WHERE guild_id = %s",
            params
        )
        self.db.commit()

        # Clear guild-related caches
        self.cache.clear()

        return True

    def update_guild_settings(
        self,
        guild_id: int,
        raid_schedule: Optional[str] = None,
        loot_system: Optional[str] = None,
        public_logs: Optional[bool] = None,
    ) -> bool:
        """
        Update guild settings in the JSONB settings column.

        Args:
            guild_id: Guild ID to update
            raid_schedule: Guild raid schedule
            loot_system: Loot distribution system
            public_logs: Whether logs are public

        Returns:
            True if successful
        """
        import json

        # Get current settings
        cursor = self.db.execute(
            "SELECT settings FROM guilds WHERE guild_id = %s",
            (guild_id,)
        )
        result = cursor.fetchone()

        if not result:
            return False

        # Parse current settings or use empty dict
        current_settings = {}
        if result[0]:
            try:
                current_settings = json.loads(result[0]) if isinstance(result[0], str) else result[0]
            except (json.JSONDecodeError, TypeError):
                current_settings = {}

        # Update only provided settings
        if raid_schedule is not None:
            current_settings["raid_schedule"] = raid_schedule

        if loot_system is not None:
            current_settings["loot_system"] = loot_system

        if public_logs is not None:
            current_settings["public_logs"] = public_logs

        # Update the guild with new settings
        self.db.execute(
            "UPDATE guilds SET settings = %s, updated_at = CURRENT_TIMESTAMP WHERE guild_id = %s",
            (json.dumps(current_settings), guild_id)
        )
        self.db.commit()

        # Clear guild-related caches
        self.cache.clear()

        return True

    def delete_guild(self, guild_id: int) -> bool:
        """
        Soft delete guild (set is_active to FALSE).

        Args:
            guild_id: Guild ID to delete

        Returns:
            True if successful
        """
        self.db.execute(
            """
            UPDATE guilds
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = %s
            """,
            (guild_id,)
        )
        self.db.commit()

        # Clear guild-related caches
        self.cache.clear()

        return True

    def get_guild_encounters(
        self,
        guild_id: int,
        encounter_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[EncounterSummary]:
        """
        Get encounters for specific guild.

        Args:
            guild_id: Guild ID
            encounter_type: Optional filter by type ('raid' or 'mythic_plus')
            limit: Maximum number of encounters to return

        Returns:
            List of EncounterSummary objects for the guild
        """
        cache_key = f"guild_encounters:{guild_id}:{encounter_type}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        query = """
            SELECT
                encounter_id, encounter_type, boss_name, difficulty,
                start_time, end_time, success, combat_length, raid_size,
                (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
            FROM combat_encounters e
            WHERE guild_id = %s
        """
        params = [guild_id]

        if encounter_type:
            query += " AND encounter_type = %s"
            params.append(encounter_type)

        query += " ORDER BY start_time DESC LIMIT %s"
        params.append(limit)

        cursor = self.db.execute(query, params)

        encounters = []
        for row in cursor:
            encounter = EncounterSummary(
                encounter_id=row[0],
                encounter_type=row[1],
                boss_name=row[2],
                difficulty=row[3],
                start_time=datetime.fromtimestamp(row[4]) if row[4] else None,
                end_time=datetime.fromtimestamp(row[5]) if row[5] else None,
                success=bool(row[6]),
                combat_length=row[7],
                raid_size=row[8],
                character_count=row[9],
            )
            encounters.append(encounter)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, encounters)
        return encounters

    def export_encounter_data(
        self,
        encounter_id: int,
        guild_id: Optional[int] = None,
        decompress_events: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Export full encounter data with optional event decompression.

        Args:
            encounter_id: Encounter ID to export
            guild_id: Guild ID for multi-tenant filtering
            decompress_events: Whether to decompress and include event data

        Returns:
            Complete encounter data dictionary or None if not found
        """
        # Get encounter summary
        encounter = self.get_encounter(encounter_id, guild_id)
        if not encounter:
            return None

        # Get character metrics
        metrics = self.get_character_metrics(encounter_id, guild_id=guild_id)

        # Build export data
        export_data = {
            "encounter": {
                "encounter_id": encounter.encounter_id,
                "encounter_type": encounter.encounter_type,
                "boss_name": encounter.boss_name,
                "difficulty": encounter.difficulty,
                "start_time": encounter.start_time.isoformat() if encounter.start_time else None,
                "end_time": encounter.end_time.isoformat() if encounter.end_time else None,
                "success": encounter.success,
                "combat_length": encounter.combat_length,
                "raid_size": encounter.raid_size,
                "character_count": encounter.character_count,
            },
            "character_metrics": [
                {
                    "character_name": m.character_name,
                    "character_guid": m.character_guid,
                    "class_name": m.class_name,
                    "spec_name": m.spec_name,
                    "damage_done": m.damage_done,
                    "healing_done": m.healing_done,
                    "damage_taken": m.damage_taken,
                    "death_count": m.death_count,
                    "dps": m.dps,
                    "hps": m.hps,
                    "activity_percentage": m.activity_percentage,
                    "time_alive": m.time_alive,
                    "combat_time": m.combat_time,
                    "combat_dps": m.combat_dps,
                    "combat_hps": m.combat_hps,
                }
                for m in metrics
            ],
        }

        # Optionally include decompressed events
        if decompress_events:
            # Get event blocks for this encounter
            query = """
                SELECT
                    eb.character_id 
                    c.character_name 
                    eb.block_index 
                    eb.start_time 
                    eb.end_time 
                    eb.compressed_data 
                    eb.event_count
                FROM event_blocks eb
                JOIN characters c ON eb.character_id = c.character_id
                WHERE eb.encounter_id = %s
                ORDER BY eb.character_id eb.block_index
            """
            cursor = self.db.execute(query (encounter_id ))
            blocks = cursor.fetchall()

            events_by_character = {}
            for block in blocks:
                char_name = block[1]
                if char_name not in events_by_character:
                    events_by_character[char_name] = []

                # Decompress events from this block
                compressed_data = block[5]
                decompressed = self.decompressor.decompress_events(compressed_data)

                # Add basic event info (not full event data to keep size manageable)
                for event in decompressed[:10]:  # Limit to first 10 events per block for export
                    events_by_character[char_name].append({
                        "timestamp": event.timestamp,
                        "event_type": event.event.event_type if hasattr(event.event, 'event_type') else "unknown",
                    })

            export_data["event_samples"] = events_by_character

        return export_data

    def get_character_profile(
        self, character_name: str, server: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get detailed character profile."""
        query = """
            SELECT
                character_id, character_guid, character_name, server, region,
                class_name, spec_name, first_seen, last_seen, encounter_count
            FROM characters
            WHERE character_name = %s
        """
        params = [character_name]

        if server:
            query += " AND server = %s"
            params.append(server)

        cursor = self.db.execute(query, params)
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "character_id": row[0],
            "character_guid": row[1],
            "name": row[2],
            "server": row[3] or "Unknown",
            "region": row[4] or "US",
            "class_name": row[5] or "Unknown",
            "spec": row[6] or "Unknown",
            "first_seen": row[7],
            "last_seen": row[8],
            "encounter_count": row[9] or 0,
        }

    def get_character_performance(
        self,
        character_name: str,
        encounter_id: Optional[int] = None,
        time_range: Optional[TimeRange] = None,
        difficulty: Optional[str] = None,
        encounter_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get character performance metrics."""
        # Get character ID first
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_name = %s",
            (character_name )
        )
        char_row = cursor.fetchone()
        if not char_row:
            return None

        character_id = char_row[0]

        if encounter_id:
            # Get specific encounter performance
            cursor = self.db.execute(
                """
                SELECT
                    damage_done, healing_done, damage_taken, death_count,
                    dps, hps, activity_percentage, combat_dps, combat_hps
                FROM character_metrics
                WHERE character_id = %s AND encounter_id = %s
                """,
                (character_id, encounter_id)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "damage_done": row[0],
                    "healing_done": row[1],
                    "damage_taken": row[2],
                    "death_count": row[3],
                    "dps": row[4],
                    "hps": row[5],
                    "activity_percentage": row[6],
                    "combat_dps": row[7],
                    "combat_hps": row[8],
                }
        else:
            # Get aggregate performance
            query = """
                SELECT
                    AVG(cm.dps) as avg_dps 
                    AVG(cm.hps) as avg_hps 
                    AVG(cm.activity_percentage) as avg_activity 
                    SUM(cm.death_count) as total_deaths 
                    COUNT(*) as encounter_count
                FROM character_metrics cm
                JOIN encounters e ON cm.encounter_id = e.encounter_id
                WHERE cm.character_id = %s
            """
            params = [character_id]

            if time_range:
                query += " AND e.start_time BETWEEN %s AND %s"
                params.extend([time_range.start.timestamp(), time_range.end.timestamp()])

            if difficulty:
                query += " AND e.difficulty = %s"
                params.append(difficulty)

            if encounter_type:
                query += " AND e.encounter_type = %s"
                params.append(encounter_type)

            cursor = self.db.execute(query, params)
            row = cursor.fetchone()

            if row and row[4] > 0:  # Has encounters
                return {
                    "avg_dps": row[0] or 0.0,
                    "avg_hps": row[1] or 0.0,
                    "avg_activity": row[2] or 0.0,
                    "total_deaths": row[3] or 0,
                    "encounter_count": row[4],
                }

        return None

    def get_character_history(
        self,
        character_name: str,
        time_range: TimeRange,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        limit: int = 100,
    ) -> Optional[Dict[str, Any]]:
        """Get character performance history."""
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_name = %s",
            (character_name,)
        )
        char_row = cursor.fetchone()
        if not char_row:
            return None

        character_id = char_row[0]

        query = """
            SELECT
                e.encounter_id, e.boss_name, e.difficulty, e.start_time,
                cm.dps, cm.hps, cm.death_count
            FROM character_metrics cm
            JOIN encounters e ON cm.encounter_id = e.encounter_id
            WHERE cm.character_id = %s
            AND e.start_time BETWEEN %s AND %s
        """
        params = [character_id, time_range.start.timestamp(), time_range.end.timestamp()]

        if encounter_type:
            query += " AND e.encounter_type = %s"
            params.append(encounter_type)

        if difficulty:
            query += " AND e.difficulty = %s"
            params.append(difficulty)

        query += " ORDER BY e.start_time DESC LIMIT %s"
        params.append(limit)

        cursor = self.db.execute(query, params)
        history = []

        for row in cursor:
            history.append({
                "encounter_id": row[0],
                "boss_name": row[1],
                "difficulty": row[2],
                "date": datetime.fromtimestamp(row[3]) if row[3] else None,
                "dps": row[4],
                "hps": row[5],
                "deaths": row[6],
            })

        return {"history": history} if history else None

    def get_character_ranking(
        self,
        character_name: str,
        metric: str,
        time_range: TimeRange,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get character ranking for a metric."""
        # Simplified ranking - would need more complex calculation in production
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_name = %s",
            (character_name,)
        )
        char_row = cursor.fetchone()
        if not char_row:
            return None

        character_id = char_row[0]

        # Get character's average for the metric
        query = f"""
            SELECT AVG(cm.{metric}) as avg_metric
            FROM character_metrics cm
            JOIN encounters e ON cm.encounter_id = e.encounter_id
            WHERE cm.character_id = %s
            AND e.start_time BETWEEN %s AND %s
        """
        params = [character_id, time_range.start.timestamp(), time_range.end.timestamp()]

        if encounter_type:
            query += " AND e.encounter_type = %s"
            params.append(encounter_type)

        if difficulty:
            query += " AND e.difficulty = %s"
            params.append(difficulty)

        cursor = self.db.execute(query, params)
        row = cursor.fetchone()

        if not row or row[0] is None:
            return None

        return {
            "metric": metric,
            "value": row[0],
            "percentile": 50,  # Placeholder - would need actual calculation
            "rank": 1,  # Placeholder
        }

    def get_character_gear(
        self, character_name: str, encounter_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Get character gear information."""
        try:
            # Get character ID
            cursor = self.db.execute(
                "SELECT character_id FROM characters WHERE character_name = %s",
                (character_name,)
            )
            char_row = cursor.fetchone()
            if not char_row:
                return None

            character_id = char_row[0]

            # Import gear parser here to avoid circular imports
            from ..parser.gear_parser import GearParser
            gear_parser = GearParser()

            if encounter_id:
                # Get gear for specific encounter
                snapshot = gear_parser.get_character_gear_by_encounter(self.db, character_id, encounter_id)
            else:
                # Get most recent gear snapshot
                cursor = self.db.execute(
                    """
                    SELECT snapshot_id encounter_id snapshot_time source 
                           average_item_level equipped_item_level total_items
                    FROM character_gear_snapshots
                    WHERE character_id = %s
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                    """ 
                    (character_id )
                )

                snapshot_row = cursor.fetchone()
                if not snapshot_row:
                    return {
                        "character_name": character_name 
                        "gear": [] 
                        "item_level": 0 
                        "average_item_level": 0 
                        "total_items": 0 
                        "snapshot_time": None 
                        "source": None 
                        "recommendations": [] 
                    }

                snapshot_id enc_id snapshot_time source avg_ilvl equipped_ilvl total_items = snapshot_row
                snapshot = gear_parser.get_character_gear_by_encounter(self.db character_id enc_id)

            if not snapshot:
                return {
                    "character_name": character_name 
                    "gear": [] 
                    "item_level": 0 
                    "average_item_level": 0 
                    "total_items": 0 
                    "snapshot_time": None 
                    "source": None 
                    "recommendations": [] 
                }

            # Convert gear items to dictionary format
            gear_items = []
            for item in snapshot.items:
                gear_item = {
                    "slot": item.slot_name 
                    "slot_index": item.slot_index 
                    "item_entry": item.item_entry 
                    "item_level": item.item_level 
                    "enchant_id": item.enchant_id 
                    "gems": item.gem_ids 
                    "upgrade_level": item.upgrade_level 
                    "bonus_ids": item.bonus_ids 
                }
                gear_items.append(gear_item)

            # Generate basic recommendations (placeholder for now)
            recommendations = []
            if snapshot.average_item_level > 0:
                # Find slots with below-average item levels
                below_avg_slots = [
                    item for item in snapshot.items
                    if item.item_level < snapshot.average_item_level - 10
                ]

                for item in below_avg_slots:
                    recommendations.append({
                        "type": "upgrade" 
                        "slot": item.slot_name 
                        "current_ilvl": item.item_level 
                        "recommended_ilvl": int(snapshot.average_item_level) 
                        "message": f"{item.slot_name} is significantly below average item level"
                    })

                # Check for missing enchants on enchantable slots
                enchantable_slots = ["Main_Hand" "Off_Hand" "Chest" "Legs" "Feet" "Hands" "Wrist" "Back"]
                for item in snapshot.items:
                    if item.slot_name in enchantable_slots and item.enchant_id == 0:
                        recommendations.append({
                            "type": "enchant" 
                            "slot": item.slot_name 
                            "message": f"{item.slot_name} is missing an enchant"
                        })

            return {
                "character_name": character_name 
                "gear": gear_items 
                "item_level": snapshot.average_item_level  # Legacy field
                "average_item_level": snapshot.average_item_level 
                "equipped_item_level": snapshot.equipped_item_level 
                "total_items": snapshot.total_items 
                "snapshot_time": snapshot.snapshot_time 
                "source": snapshot.source 
                "recommendations": recommendations 
            }

        except Exception as e:
            logger.error(f"Error getting character gear for {character_name}: {e}")
            return None

    def get_character_talents(
        self character_name: str encounter_id: Optional[int] = None
    ) -> Optional[Dict[str Any]]:
        """Get character talent information."""
        try:
            # Get character ID
            cursor = self.db.execute(
                "SELECT character_id FROM characters WHERE character_name = %s" 
                (character_name )
            )
            char_row = cursor.fetchone()
            if not char_row:
                return None

            character_id = char_row[0]

            # Import talent parser here to avoid circular imports
            from ..parser.talent_parser import TalentParser
            talent_parser = TalentParser()

            if encounter_id:
                # Get talents for specific encounter
                snapshot = talent_parser.get_character_talents_by_encounter(self.db character_id encounter_id)
            else:
                # Get most recent talent snapshot
                cursor = self.db.execute(
                    """
                    SELECT snapshot_id encounter_id snapshot_time source 
                           specialization talent_loadout total_talents
                    FROM character_talent_snapshots
                    WHERE character_id = %s
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                    """ 
                    (character_id )
                )

                snapshot_row = cursor.fetchone()
                if not snapshot_row:
                    return {
                        "character_name": character_name 
                        "specialization": "" 
                        "talent_loadout": "" 
                        "talents": [] 
                        "total_talents": 0 
                        "snapshot_time": None 
                        "source": None 
                        "recommendations": [] 
                    }

                snapshot_id enc_id snapshot_time source specialization talent_loadout total_talents = snapshot_row
                snapshot = talent_parser.get_character_talents_by_encounter(self.db character_id enc_id)

            if not snapshot:
                return {
                    "character_name": character_name 
                    "specialization": "" 
                    "talent_loadout": "" 
                    "talents": [] 
                    "total_talents": 0 
                    "snapshot_time": None 
                    "source": None 
                    "recommendations": [] 
                }

            # Convert talent selections to dictionary format
            talent_selections = []
            for talent in snapshot.talents:
                talent_data = {
                    "slot": talent.talent_slot 
                    "spell_id": talent.talent_spell_id 
                    "tier": talent.talent_tier 
                    "column": talent.talent_column 
                    "selected": talent.is_selected 
                }
                talent_selections.append(talent_data)

            # Generate recommendations
            # Try to determine encounter type from encounter_id
            encounter_type = None
            if encounter_id:
                cursor = self.db.execute(
                    "SELECT encounter_type FROM combat_encounters WHERE encounter_id = %s" 
                    (encounter_id )
                )
                enc_row = cursor.fetchone()
                if enc_row:
                    encounter_type = enc_row[0]

            recommendations = talent_parser.generate_talent_recommendations(snapshot encounter_type)

            return {
                "character_name": character_name 
                "specialization": snapshot.specialization 
                "talent_loadout": snapshot.talent_loadout 
                "talents": talent_selections 
                "total_talents": snapshot.total_talents 
                "snapshot_time": snapshot.snapshot_time 
                "source": snapshot.source 
                "recommendations": recommendations 
            }

        except Exception as e:
            logger.error(f"Error getting character talents for {character_name}: {e}")
            return None

    def get_character_trends(
        self 
        character_name: str 
        metric: str 
        time_range: TimeRange 
        interval: str 
        encounter_type: Optional[str] = None 
        difficulty: Optional[str] = None 
    ) -> Optional[Dict[str Any]]:
        """Get character performance trends."""
        cursor = self.db.execute(
            "SELECT character_id FROM characters WHERE character_name = %s" 
            (character_name )
        )
        char_row = cursor.fetchone()
        if not char_row:
            return None

        character_id = char_row[0]

        # Get daily averages for simplicity
        query = f"""
            SELECT
                DATE(e.start_time 'unixepoch') as date 
                AVG(cm.{metric}) as value
            FROM character_metrics cm
            JOIN encounters e ON cm.encounter_id = e.encounter_id
            WHERE cm.character_id = %s
            AND e.start_time BETWEEN %s AND %s
        """
        params = [character_id time_range.start.timestamp() time_range.end.timestamp()]

        if encounter_type:
            query += " AND e.encounter_type = %s"
            params.append(encounter_type)

        if difficulty:
            query += " AND e.difficulty = %s"
            params.append(difficulty)

        query += " GROUP BY DATE(e.start_time 'unixepoch') ORDER BY date"

        cursor = self.db.execute(query params)
        data_points = []

        for row in cursor:
            data_points.append({
                "date": row[0] 
                "value": row[1] or 0 
            })

        return {
            "metric": metric 
            "data_points": data_points 
        } if data_points else None

    def compare_characters(
        self 
        base_character: str 
        compare_characters: List[str] 
        metric: str 
        encounter_id: Optional[int] = None 
        time_range: Optional[TimeRange] = None 
    ) -> Dict[str Any]:
        """Compare characters on a specific metric."""
        all_characters = [base_character] + compare_characters
        comparisons = {}

        for char_name in all_characters:
            cursor = self.db.execute(
                "SELECT character_id FROM characters WHERE character_name = %s" 
                (char_name )
            )
            char_row = cursor.fetchone()
            if not char_row:
                continue

            character_id = char_row[0]

            if encounter_id:
                # Compare specific encounter
                cursor = self.db.execute(
                    f"SELECT {metric} FROM character_metrics WHERE character_id = %s AND encounter_id = %s" 
                    (character_id encounter_id)
                )
                row = cursor.fetchone()
                if row:
                    comparisons[char_name] = row[0] or 0
            elif time_range:
                # Compare time range average
                cursor = self.db.execute(
                    f"""
                    SELECT AVG(cm.{metric})
                    FROM character_metrics cm
                    JOIN encounters e ON cm.encounter_id = e.encounter_id
                    WHERE cm.character_id = %s
                    AND e.start_time BETWEEN %s AND %s
                    """ 
                    (character_id time_range.start.timestamp() time_range.end.timestamp())
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    comparisons[char_name] = row[0]

        return {
            "metric": metric 
            "comparisons": comparisons 
        }

    def get_database_stats(self) -> Dict[str Any]:
        """Get comprehensive database and query statistics."""
        cursor = self.db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM combat_encounters) as total_encounters 
                (SELECT COUNT(*) FROM characters) as total_characters 
                (SELECT COUNT(*) FROM character_metrics) as total_character_metrics
        """
        )
        row = cursor.fetchone()

        stats = {
            "database": {
                "total_encounters": row[0] or 0 
                "total_characters": row[1] or 0 
                "total_character_metrics": row[2] or 0 
            } 
            "query_api": self.stats 
            "cache": self.cache.stats() 
        }

        # Add InfluxDB stats if available
        if self.influxdb_manager:
            try:
                influx_stats = self.get_influxdb_stats()
                stats["influxdb"] = influx_stats
            except Exception as e:
                logger.warning(f"Could not retrieve InfluxDB stats: {e}")
                stats["influxdb"] = {"error": str(e)}
        else:
            stats["influxdb"] = {"error": "No InfluxDB connection available"}

        return stats

    def clear_cache(self):
        """Clear all cached query results."""
        self.cache.clear()

    # Time-series query methods for InfluxDB integration

    def query_encounter_events(
        self 
        encounter_id: int 
        character_id: Optional[int] = None 
        event_types: Optional[List[str]] = None 
        start_time: Optional[datetime] = None 
        end_time: Optional[datetime] = None
    ) -> List[Dict[str Any]]:
        """
        Query events for an encounter using time-window approach.

        Args:
            encounter_id: Encounter ID to query
            character_id: Optional character ID filter
            event_types: Optional list of event types to filter
            start_time: Optional start time override
            end_time: Optional end time override

        Returns:
            List of event dictionaries
        """
        if not self.influxdb_manager:
            logger.warning("Cannot query encounter events without InfluxDB connection")
            return []

        try:
            # Get encounter time window from metadata if not provided
            if not start_time or not end_time:
                encounter = self.get_encounter(encounter_id)
                if not encounter:
                    logger.error(f"Encounter {encounter_id} not found")
                    return []

                start_time = start_time or encounter.start_time
                end_time = end_time or encounter.end_time

            if not start_time or not end_time:
                logger.error(f"Cannot determine time window for encounter {encounter_id}")
                return []

            # Use InfluxDB time-window query
            return self.influxdb_manager.query_encounter_events(
                encounter_id=encounter_id 
                character_id=character_id 
                event_types=event_types 
                start_time=start_time 
                end_time=end_time 
            )

        except Exception as e:
            logger.error(f"Failed to query encounter events: {e}")
            return []

    def query_time_window_events(
        self 
        start_time: datetime 
        end_time: datetime 
        character_ids: Optional[List[int]] = None 
        event_types: Optional[List[str]] = None 
        guild_id: Optional[int] = None
    ) -> List[Dict[str Any]]:
        """
        Query events within a specific time window using InfluxDB.

        Args:
            start_time: Start of time window
            end_time: End of time window
            character_ids: Optional character ID filters
            event_types: Optional event type filters
            guild_id: Optional guild ID filter

        Returns:
            List of event dictionaries
        """
        if not self.influxdb_manager:
            logger.warning("Cannot query time window events without InfluxDB connection")
            return []

        try:
            # Use InfluxDB native time-window query
            return self.influxdb_manager.query_time_window(
                start_time=start_time 
                end_time=end_time 
                character_ids=character_ids 
                event_types=event_types 
                guild_id=guild_id
            )

        except Exception as e:
            logger.error(f"Failed to query time window events: {e}")
            return []

    def aggregate_encounter_metrics(
        self 
        encounter_id: int 
        metric_types: Optional[List[str]] = None 
        group_by_character: bool = True
    ) -> Dict[str Any]:
        """
        Aggregate metrics for an encounter using InfluxDB time-series functions.

        Args:
            encounter_id: Encounter ID to aggregate
            metric_types: Optional list of metrics to calculate
            group_by_character: Whether to group results by character

        Returns:
            Dictionary of aggregated metrics
        """
        if not self.influxdb_manager:
            logger.warning("Cannot aggregate encounter metrics without InfluxDB connection")
            return {}

        try:
            # Get encounter time window
            encounter = self.get_encounter(encounter_id)
            if not encounter:
                logger.error(f"Encounter {encounter_id} not found")
                return {}

            # Use InfluxDB aggregation functions
            return self.influxdb_manager.aggregate_encounter_metrics(
                encounter_id=encounter_id 
                start_time=encounter.start_time 
                end_time=encounter.end_time 
                metric_types=metric_types 
 
                group_by_character=group_by_character
            )

        except Exception as e:
            logger.error(f"Failed to aggregate encounter metrics: {e}")
            return {}

    def define_encounter_time_window(
        self 
        start_time: datetime 
        end_time: datetime 
        encounter_name: str 
        guild_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Define a new encounter as a time window and return its ID.

        Args:
            start_time: Start of encounter
            end_time: End of encounter
            encounter_name: Name/identifier for the encounter
            guild_id: Optional guild ID

        Returns:
            Encounter ID if successful None otherwise
        """
        if not self.influxdb_manager:
            logger.warning("Cannot define encounter time window without InfluxDB connection")
            return None

        try:
            # Create encounter metadata in PostgreSQL
            cursor = self.db.execute(
                """
                INSERT INTO combat_encounters (
                    guild_id encounter_type boss_name start_time end_time 
                    success combat_length created_at
                ) VALUES (%s%s %s %s %s %s %s %s %s)
                RETURNING encounter_id
                """ 
                (
                    guild_id 
                    "time_window" 
                    encounter_name 
                    start_time.timestamp() 
                    end_time.timestamp() 
                    True  # Assume successful for time-window definitions
                    (end_time - start_time).total_seconds() 
                    datetime.now().isoformat() 
                ) 
            )

            encounter_id = cursor.fetchone()[0]

            # Define the time window in InfluxDB
            self.influxdb_manager.define_encounter_window(
                encounter_id=encounter_id 
                start_time=start_time 
                end_time=end_time 
                encounter_name=encounter_name
            )

            return encounter_id

        except Exception as e:
            logger.error(f"Failed to define encounter time window: {e}")
            return None

    def get_influxdb_stats(self) -> Dict[str Any]:
        """Get InfluxDB connection and performance statistics."""
        if not self.influxdb_manager:
            return {"error": "No InfluxDB connection available"}

        try:
            return self.influxdb_manager.get_stats()
        except Exception as e:
            logger.error(f"Failed to get InfluxDB stats: {e}")
            return {"error": str(e)}

    def close(self):
        """Close query API and cleanup resources."""
        if self.influxdb_manager:
            self.influxdb_manager.close()
