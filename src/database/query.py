"""
High-speed query API for WoW combat log database.

Provides optimized queries with caching and efficient decompression
for instant data retrieval from the compressed event storage.
"""

import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import threading

from .schema import DatabaseManager
from .compression import EventCompressor, compression_stats
from models.character_events import TimestampedEvent, CharacterEventStream
from models.encounter_models import RaidEncounter, MythicPlusRun

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
    High-performance query interface for combat log database.

    Provides optimized queries with automatic caching, parallel decompression,
    and efficient data retrieval patterns for common use cases.
    """

    def __init__(self, db: DatabaseManager, cache_size: int = 1000):
        """
        Initialize query API.

        Args:
            db: Database manager instance
            cache_size: Maximum number of cached query results
        """
        self.db = db
        self.cache = QueryCache(max_size=cache_size)
        self.decompressor = EventCompressor()

        # Thread pool for parallel decompression
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="query")

        # Query statistics
        self.stats = {
            "queries_executed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_query_time": 0.0,
            "events_decompressed": 0,
        }

    def get_encounter(self, encounter_id: int) -> Optional[EncounterSummary]:
        """
        Get encounter summary by ID.

        Args:
            encounter_id: Database encounter ID

        Returns:
            EncounterSummary or None if not found
        """
        cache_key = f"encounter:{encounter_id}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        cursor = self.db.execute("""
            SELECT
                encounter_id, encounter_type, boss_name, difficulty,
                start_time, end_time, success, combat_length, raid_size,
                (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
            FROM encounters e
            WHERE encounter_id = ?
        """, (encounter_id,))

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
            character_count=row[9]
        )

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, encounter)
        return encounter

    def get_recent_encounters(self, limit: int = 10) -> List[EncounterSummary]:
        """
        Get recent encounters ordered by creation time.

        Args:
            limit: Maximum number of encounters to return

        Returns:
            List of EncounterSummary objects
        """
        cache_key = f"recent_encounters:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        cursor = self.db.execute("""
            SELECT
                encounter_id, encounter_type, boss_name, difficulty,
                start_time, end_time, success, combat_length, raid_size,
                (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
            FROM encounters e
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

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
                character_count=row[9]
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
        limit: int = 50
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

        Returns:
            List of matching encounters
        """
        # Build cache key from parameters
        cache_key = f"search:{boss_name}:{difficulty}:{encounter_type}:{success}:{start_date}:{end_date}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build dynamic query
        conditions = []
        params = []

        if boss_name:
            conditions.append("boss_name LIKE ?")
            params.append(f"%{boss_name}%")

        if difficulty:
            conditions.append("difficulty = ?")
            params.append(difficulty)

        if encounter_type:
            conditions.append("encounter_type = ?")
            params.append(encounter_type)

        if success is not None:
            conditions.append("success = ?")
            params.append(success)

        if start_date:
            conditions.append("start_time >= ?")
            params.append(start_date.timestamp())

        if end_date:
            conditions.append("start_time <= ?")
            params.append(end_date.timestamp())

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        cursor = self.db.execute(f"""
            SELECT
                encounter_id, encounter_type, boss_name, difficulty,
                start_time, end_time, success, combat_length, raid_size,
                (SELECT COUNT(*) FROM character_metrics WHERE encounter_id = e.encounter_id) as character_count
            FROM encounters e
            {where_clause}
            ORDER BY start_time DESC
            LIMIT ?
        """, params)

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
                character_count=row[9]
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
        character_name: Optional[str] = None
    ) -> List[CharacterMetrics]:
        """
        Get character performance metrics for an encounter.

        Args:
            encounter_id: Database encounter ID
            character_name: Optional filter by character name

        Returns:
            List of CharacterMetrics
        """
        cache_key = f"metrics:{encounter_id}:{character_name}"
        cached = self.cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        start_time = time.time()
        self.stats["queries_executed"] += 1

        # Build query with optional character filter
        query = """
            SELECT
                c.character_name, c.character_guid, c.class_name, c.spec_name,
                m.damage_done, m.healing_done, m.damage_taken, m.death_count,
                m.dps, m.hps, m.activity_percentage, m.time_alive, m.total_events
            FROM character_metrics m
            JOIN characters c ON m.character_id = c.character_id
            WHERE m.encounter_id = ?
        """
        params = [encounter_id]

        if character_name:
            query += " AND c.character_name LIKE ?"
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
                total_events=row[12]
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
        limit: int = 10
    ) -> List[CharacterMetrics]:
        """
        Get top performing characters by metric.

        Args:
            metric: Metric to rank by ('dps', 'hps', 'damage_done', etc.)
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
        valid_metrics = {"dps", "hps", "damage_done", "healing_done", "activity_percentage"}
        if metric not in valid_metrics:
            raise ValueError(f"Invalid metric: {metric}")

        # Build query with filters
        conditions = []
        params = []

        # Date filter
        cutoff_date = datetime.now() - timedelta(days=days)
        conditions.append("e.created_at >= ?")
        params.append(cutoff_date)

        if encounter_type:
            conditions.append("e.encounter_type = ?")
            params.append(encounter_type)

        if boss_name:
            conditions.append("e.boss_name LIKE ?")
            params.append(f"%{boss_name}%")

        where_clause = "WHERE " + " AND ".join(conditions)
        params.append(limit)

        cursor = self.db.execute(f"""
            SELECT
                c.character_name, c.character_guid, c.class_name, c.spec_name,
                m.damage_done, m.healing_done, m.damage_taken, m.death_count,
                m.dps, m.hps, m.activity_percentage, m.time_alive, m.total_events
            FROM character_metrics m
            JOIN characters c ON m.character_id = c.character_id
            JOIN encounters e ON m.encounter_id = e.encounter_id
            {where_clause}
            ORDER BY m.{metric} DESC
            LIMIT ?
        """, params)

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
                total_events=row[12]
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
        event_types: Optional[List[str]] = None
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
            "SELECT character_id FROM characters WHERE character_name = ?",
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
            WHERE encounter_id = ? AND character_id = ?
        """
        params = [encounter_id, character_id]

        if start_time is not None:
            query += " AND end_time >= ?"
            params.append(start_time)

        if end_time is not None:
            query += " AND start_time <= ?"
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
                e for e in filtered_events
                if (start_time is None or e.timestamp >= start_time) and
                   (end_time is None or e.timestamp <= end_time)
            ]

        if event_types:
            filtered_events = [
                e for e in filtered_events
                if e.event.event_type in event_types
            ]

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
        days: int = 30
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
        conditions = ["c.character_name = ?"]
        params = [character_name]

        if encounter_id:
            conditions.append("s.encounter_id = ?")
            params.append(encounter_id)
        else:
            # Date range filter
            cutoff_date = datetime.now() - timedelta(days=days)
            query += " JOIN encounters e ON s.encounter_id = e.encounter_id"
            conditions.append("e.created_at >= ?")
            params.append(cutoff_date)

        if spell_name:
            conditions.append("s.spell_name LIKE ?")
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
                crit_percentage=crit_percentage
            )
            spell_usages.append(usage)

        query_time = time.time() - start_time
        self.stats["total_query_time"] += query_time
        self.stats["cache_misses"] += 1

        self.cache.put(cache_key, spell_usages)
        return spell_usages

    def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database and query statistics."""
        cursor = self.db.execute("""
            SELECT
                (SELECT COUNT(*) FROM encounters) as total_encounters,
                (SELECT COUNT(*) FROM characters) as total_characters,
                (SELECT COUNT(*) FROM event_blocks) as total_blocks,
                (SELECT SUM(event_count) FROM event_blocks) as total_events,
                (SELECT SUM(compressed_size) FROM event_blocks) as total_compressed_bytes,
                (SELECT SUM(uncompressed_size) FROM event_blocks) as total_uncompressed_bytes
        """)
        row = cursor.fetchone()

        compression_ratio = 0.0
        if row[5] > 0:  # total_uncompressed_bytes
            compression_ratio = row[4] / row[5]  # compressed / uncompressed

        return {
            "database": {
                "total_encounters": row[0],
                "total_characters": row[1],
                "total_blocks": row[2],
                "total_events": row[3],
                "total_compressed_bytes": row[4],
                "total_uncompressed_bytes": row[5],
                "compression_ratio": compression_ratio,
                "space_saved_mb": (row[5] - row[4]) / (1024 * 1024) if row[5] else 0,
            },
            "query_api": self.stats,
            "cache": self.cache.stats(),
        }

    def clear_cache(self):
        """Clear all cached query results."""
        self.cache.clear()

    def close(self):
        """Close query API and cleanup resources."""
        self.executor.shutdown(wait=True)