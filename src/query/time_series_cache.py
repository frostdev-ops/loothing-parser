"""
Time-Series Query Optimization with Advanced Caching

This module provides comprehensive caching and optimization for InfluxDB time-series queries,
including guild-aware caching, time-window optimization, and query result aggregation.
"""

import json
import hashlib
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict
import redis.asyncio as redis
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for different cache tiers and query types."""

    # Time-based cache tiers
    HOT_TTL = 300      # 5 minutes - very recent data
    WARM_TTL = 1800    # 30 minutes - recent data
    COLD_TTL = 7200    # 2 hours - historical data

    # Memory cache sizes
    HOT_MEMORY_SIZE = 1000    # Keep 1000 hot queries in memory
    WARM_MEMORY_SIZE = 500    # Keep 500 warm queries in memory
    COLD_MEMORY_SIZE = 100    # Keep 100 cold queries in memory

    # Query type specific TTLs
    ENCOUNTER_EVENTS_TTL = 600     # 10 minutes
    PLAYER_METRICS_TTL = 300       # 5 minutes
    GUILD_RANKINGS_TTL = 1800      # 30 minutes
    AGGREGATED_METRICS_TTL = 3600  # 1 hour


@dataclass
class CacheEntry:
    """Cache entry with metadata for intelligent eviction."""

    data: Any
    timestamp: float
    ttl: int
    guild_id: int
    query_type: str
    time_range: Optional[Tuple[datetime, datetime]]
    access_count: int = 0
    last_access: float = 0.0
    size_bytes: int = 0

    def __post_init__(self):
        self.last_access = self.timestamp
        if isinstance(self.data, (list, dict)):
            self.size_bytes = len(json.dumps(self.data, default=str))


@dataclass
class QueryProfile:
    """Profiling information for query optimization."""

    query_hash: str
    guild_id: int
    query_type: str
    time_range_duration: Optional[float]
    execution_time: float
    result_size: int
    cache_hit: bool
    optimization_applied: List[str]
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class TimeSeriesQueryCache:
    """
    Advanced time-series query cache with multi-level storage and optimization.

    Features:
    - Guild-aware cache partitioning
    - Time-window based cache invalidation
    - Multi-tier storage (memory + Redis)
    - Query result pre-aggregation
    - Intelligent cache warming
    - Performance profiling and optimization
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 2,  # Separate DB for time-series cache
        redis_password: Optional[str] = None,
        config: Optional[CacheConfig] = None
    ):
        self.config = config or CacheConfig()

        # Multi-tier cache storage
        self.memory_cache = {
            'hot': {},      # Most recent queries
            'warm': {},     # Recent queries
            'cold': {}      # Historical queries
        }

        # Redis connection for persistent caching
        self.redis = None
        self.redis_config = {
            'host': redis_host,
            'port': redis_port,
            'db': redis_db,
            'password': redis_password,
            'decode_responses': True
        }

        # Guild-specific cache partitioning
        self.guild_caches = defaultdict(dict)

        # Query profiling and optimization
        self.query_profiles = []
        self.optimization_stats = {
            'total_queries': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'total_saved_time': 0.0,
            'optimization_applications': defaultdict(int)
        }

        # Background tasks
        self.cleanup_task = None
        self.warmup_task = None

        # Thread pool for async operations
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

        logger.info("TimeSeriesQueryCache initialized")

    async def initialize(self):
        """Initialize Redis connection and background tasks."""
        try:
            self.redis = redis.Redis(**self.redis_config)
            await self.redis.ping()
            logger.info("✅ Connected to Redis for time-series caching")

            # Start background cleanup task
            self.cleanup_task = asyncio.create_task(self._background_cleanup())

            # Start cache warming task
            self.warmup_task = asyncio.create_task(self._background_warmup())

        except Exception as e:
            logger.warning(f"⚠️  Could not connect to Redis: {e}")
            logger.info("🔄 Continuing with memory-only caching")

    def _generate_cache_key(
        self,
        guild_id: int,
        query_type: str,
        filters: Dict[str, Any],
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> str:
        """Generate a consistent cache key for queries."""
        key_data = {
            'guild_id': guild_id,
            'query_type': query_type,
            'filters': sorted(filters.items()) if filters else None,
            'time_range': [
                time_range[0].isoformat(),
                time_range[1].isoformat()
            ] if time_range else None
        }

        key_json = json.dumps(key_data, sort_keys=True, default=str)
        key_hash = hashlib.md5(key_json.encode()).hexdigest()[:16]

        return f"ts_cache:{guild_id}:{query_type}:{key_hash}"

    def _determine_cache_tier(
        self,
        query_type: str,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> str:
        """Determine which cache tier to use based on query characteristics."""

        if not time_range:
            return 'hot'  # Recent data queries

        start_time, end_time = time_range
        now = datetime.utcnow()

        # Determine age of the most recent data point
        data_age = (now - end_time).total_seconds()

        if data_age < 3600:  # Less than 1 hour old
            return 'hot'
        elif data_age < 86400:  # Less than 24 hours old
            return 'warm'
        else:
            return 'cold'

    def _get_ttl_for_query(
        self,
        query_type: str,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        tier: str = 'hot'
    ) -> int:
        """Get appropriate TTL based on query type and data age."""

        # Query type specific TTLs
        type_ttls = {
            'encounter_events': self.config.ENCOUNTER_EVENTS_TTL,
            'player_metrics': self.config.PLAYER_METRICS_TTL,
            'guild_rankings': self.config.GUILD_RANKINGS_TTL,
            'aggregated_metrics': self.config.AGGREGATED_METRICS_TTL
        }

        base_ttl = type_ttls.get(query_type, self.config.WARM_TTL)

        # Adjust TTL based on data tier
        tier_multipliers = {
            'hot': 1.0,    # Normal TTL
            'warm': 2.0,   # 2x TTL for older data
            'cold': 4.0    # 4x TTL for historical data
        }

        return int(base_ttl * tier_multipliers.get(tier, 1.0))

    async def get_or_execute(
        self,
        guild_id: int,
        query_type: str,
        filters: Dict[str, Any],
        query_executor: callable,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        force_refresh: bool = False
    ) -> Tuple[Any, bool]:  # Returns (result, was_cached)
        """
        Get cached result or execute query with comprehensive optimization.

        Args:
            guild_id: Guild identifier for cache partitioning
            query_type: Type of query for optimization
            filters: Query filters for cache key generation
            query_executor: Async function to execute if cache miss
            time_range: Time range for the query
            force_refresh: Force cache refresh

        Returns:
            Tuple of (result, was_cached)
        """
        start_time = time.time()
        self.optimization_stats['total_queries'] += 1

        # Generate cache key
        cache_key = self._generate_cache_key(guild_id, query_type, filters, time_range)

        # Determine cache tier
        tier = self._determine_cache_tier(query_type, time_range)

        # Check cache unless forced refresh
        if not force_refresh:
            cached_result = await self._get_from_cache(cache_key, tier, guild_id)
            if cached_result is not None:
                self.optimization_stats['cache_hits'] += 1
                execution_time = time.time() - start_time

                # Profile the cache hit
                await self._profile_query(
                    cache_key, guild_id, query_type, time_range,
                    execution_time, len(str(cached_result)), True, ['cache_hit']
                )

                return cached_result, True

        # Cache miss - execute query
        self.optimization_stats['cache_misses'] += 1

        try:
            # Apply query optimizations
            optimizations_applied = []

            # Time-window optimization
            if time_range and self._should_optimize_time_window(time_range):
                optimizations_applied.append('time_window_optimization')

            # Guild-specific optimization
            if self._should_apply_guild_optimization(guild_id, query_type):
                optimizations_applied.append('guild_partitioning')

            # Execute the query
            result = await query_executor()

            execution_time = time.time() - start_time
            result_size = len(str(result))

            # Cache the result
            ttl = self._get_ttl_for_query(query_type, time_range, tier)
            await self._set_in_cache(
                cache_key, result, tier, guild_id, query_type,
                time_range, ttl, result_size
            )

            # Profile the query
            await self._profile_query(
                cache_key, guild_id, query_type, time_range,
                execution_time, result_size, False, optimizations_applied
            )

            # Track optimization applications
            for opt in optimizations_applied:
                self.optimization_stats['optimization_applications'][opt] += 1

            return result, False

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    async def _get_from_cache(
        self,
        cache_key: str,
        tier: str,
        guild_id: int
    ) -> Optional[Any]:
        """Get result from multi-tier cache."""

        # Level 1: Memory cache (fastest)
        if cache_key in self.memory_cache[tier]:
            entry = self.memory_cache[tier][cache_key]
            if time.time() - entry.timestamp < entry.ttl:
                entry.access_count += 1
                entry.last_access = time.time()
                return entry.data
            else:
                # Expired
                del self.memory_cache[tier][cache_key]

        # Level 2: Redis cache (fast)
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    result = json.loads(cached_data)

                    # Promote to memory cache
                    await self._promote_to_memory(cache_key, result, tier, guild_id)

                    return result

            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

        return None

    async def _set_in_cache(
        self,
        cache_key: str,
        result: Any,
        tier: str,
        guild_id: int,
        query_type: str,
        time_range: Optional[Tuple[datetime, datetime]],
        ttl: int,
        result_size: int
    ):
        """Set result in multi-tier cache."""

        # Create cache entry
        entry = CacheEntry(
            data=result,
            timestamp=time.time(),
            ttl=ttl,
            guild_id=guild_id,
            query_type=query_type,
            time_range=time_range,
            size_bytes=result_size
        )

        # Level 1: Memory cache
        max_memory_size = getattr(self.config, f'{tier.upper()}_MEMORY_SIZE')
        if len(self.memory_cache[tier]) >= max_memory_size:
            await self._evict_from_memory(tier)

        self.memory_cache[tier][cache_key] = entry

        # Level 2: Redis cache
        if self.redis and result_size < 1024 * 1024:  # Don't cache results > 1MB
            try:
                await self.redis.setex(
                    cache_key,
                    ttl,
                    json.dumps(result, default=str)
                )
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")

    async def _promote_to_memory(
        self,
        cache_key: str,
        result: Any,
        tier: str,
        guild_id: int
    ):
        """Promote frequently accessed Redis entries to memory cache."""

        entry = CacheEntry(
            data=result,
            timestamp=time.time(),
            ttl=self._get_ttl_for_query('default', None, tier),
            guild_id=guild_id,
            query_type='promoted',
            time_range=None,
            access_count=1
        )

        max_size = getattr(self.config, f'{tier.upper()}_MEMORY_SIZE')
        if len(self.memory_cache[tier]) >= max_size:
            await self._evict_from_memory(tier)

        self.memory_cache[tier][cache_key] = entry

    async def _evict_from_memory(self, tier: str):
        """Evict least recently used entries from memory cache."""

        if not self.memory_cache[tier]:
            return

        # Sort by last access time (LRU)
        sorted_entries = sorted(
            self.memory_cache[tier].items(),
            key=lambda x: x[1].last_access
        )

        # Remove oldest 25% of entries
        entries_to_remove = len(sorted_entries) // 4
        for i in range(entries_to_remove):
            cache_key, _ = sorted_entries[i]
            del self.memory_cache[tier][cache_key]

    async def _profile_query(
        self,
        query_hash: str,
        guild_id: int,
        query_type: str,
        time_range: Optional[Tuple[datetime, datetime]],
        execution_time: float,
        result_size: int,
        cache_hit: bool,
        optimizations_applied: List[str]
    ):
        """Profile query performance for optimization insights."""

        time_range_duration = None
        if time_range:
            time_range_duration = (time_range[1] - time_range[0]).total_seconds()

        profile = QueryProfile(
            query_hash=query_hash,
            guild_id=guild_id,
            query_type=query_type,
            time_range_duration=time_range_duration,
            execution_time=execution_time,
            result_size=result_size,
            cache_hit=cache_hit,
            optimization_applied=optimizations_applied
        )

        self.query_profiles.append(profile)

        # Keep only recent profiles
        if len(self.query_profiles) > 10000:
            self.query_profiles = self.query_profiles[-5000:]  # Keep last 5k

        # Update saved time statistics
        if cache_hit:
            # Estimate saved time based on similar queries
            avg_execution_time = self._get_average_execution_time(query_type)
            self.optimization_stats['total_saved_time'] += avg_execution_time

    def _get_average_execution_time(self, query_type: str) -> float:
        """Get average execution time for a query type."""

        relevant_profiles = [
            p for p in self.query_profiles[-1000:]  # Last 1000 queries
            if p.query_type == query_type and not p.cache_hit
        ]

        if not relevant_profiles:
            return 0.1  # Default estimate

        total_time = sum(p.execution_time for p in relevant_profiles)
        return total_time / len(relevant_profiles)

    def _should_optimize_time_window(
        self,
        time_range: Tuple[datetime, datetime]
    ) -> bool:
        """Determine if time-window optimization should be applied."""

        duration = (time_range[1] - time_range[0]).total_seconds()

        # Apply optimization for queries longer than 1 hour
        return duration > 3600

    def _should_apply_guild_optimization(
        self,
        guild_id: int,
        query_type: str
    ) -> bool:
        """Determine if guild-specific optimization should be applied."""

        # Apply for frequently queried guilds
        guild_query_count = len([
            p for p in self.query_profiles[-100:]
            if p.guild_id == guild_id and p.query_type == query_type
        ])

        return guild_query_count > 5

    async def invalidate_guild_cache(self, guild_id: int):
        """Invalidate all cache entries for a specific guild."""

        # Clear memory cache entries for guild
        for tier in self.memory_cache:
            to_remove = []
            for cache_key, entry in self.memory_cache[tier].items():
                if entry.guild_id == guild_id:
                    to_remove.append(cache_key)

            for cache_key in to_remove:
                del self.memory_cache[tier][cache_key]

        # Clear Redis cache entries for guild
        if self.redis:
            try:
                pattern = f"ts_cache:{guild_id}:*"
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self.redis.delete(*keys)
                    if cursor == 0:
                        break

            except Exception as e:
                logger.warning(f"Redis cache invalidation error: {e}")

        logger.info(f"✅ Invalidated cache for guild {guild_id}")

    async def invalidate_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        guild_id: Optional[int] = None
    ):
        """Invalidate cache entries that overlap with a time range."""

        for tier in self.memory_cache:
            to_remove = []
            for cache_key, entry in self.memory_cache[tier].items():
                if entry.time_range:
                    entry_start, entry_end = entry.time_range

                    # Check for time range overlap
                    if (entry_start < end_time and entry_end > start_time):
                        if guild_id is None or entry.guild_id == guild_id:
                            to_remove.append(cache_key)

            for cache_key in to_remove:
                del self.memory_cache[tier][cache_key]

        logger.info(f"✅ Invalidated cache for time range {start_time} - {end_time}")

    async def warm_cache_for_guild(
        self,
        guild_id: int,
        common_queries: List[Dict[str, Any]]
    ):
        """Pre-warm cache with common queries for a guild."""

        logger.info(f"🔥 Warming cache for guild {guild_id} with {len(common_queries)} queries")

        for query_config in common_queries:
            try:
                # Extract query parameters
                query_type = query_config.get('query_type')
                filters = query_config.get('filters', {})
                time_range = query_config.get('time_range')
                executor = query_config.get('executor')

                if not executor:
                    continue

                # Execute and cache the query
                await self.get_or_execute(
                    guild_id=guild_id,
                    query_type=query_type,
                    filters=filters,
                    query_executor=executor,
                    time_range=time_range
                )

                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.warning(f"Cache warming failed for query: {e}")

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance and optimization statistics."""

        stats = dict(self.optimization_stats)

        # Add cache utilization stats
        memory_stats = {}
        for tier in self.memory_cache:
            memory_stats[tier] = {
                'entries': len(self.memory_cache[tier]),
                'max_size': getattr(self.config, f'{tier.upper()}_MEMORY_SIZE'),
                'utilization': len(self.memory_cache[tier]) / getattr(self.config, f'{tier.upper()}_MEMORY_SIZE')
            }

        stats['memory_cache'] = memory_stats

        # Add Redis stats
        if self.redis:
            try:
                redis_info = await self.redis.info('memory')
                stats['redis'] = {
                    'memory_usage': redis_info.get('used_memory_human'),
                    'keys': await self.redis.dbsize()
                }
            except:
                stats['redis'] = {'error': 'Could not retrieve Redis stats'}
        else:
            stats['redis'] = {'status': 'not_connected'}

        # Add query profiling insights
        if self.query_profiles:
            recent_profiles = self.query_profiles[-1000:]  # Last 1000 queries

            stats['query_insights'] = {
                'total_profiles': len(self.query_profiles),
                'cache_hit_rate': sum(1 for p in recent_profiles if p.cache_hit) / len(recent_profiles),
                'avg_execution_time': sum(p.execution_time for p in recent_profiles if not p.cache_hit) /
                                    max(1, sum(1 for p in recent_profiles if not p.cache_hit)),
                'most_common_query_types': self._get_top_query_types(recent_profiles),
                'most_active_guilds': self._get_top_guilds(recent_profiles)
            }

        return stats

    def _get_top_query_types(self, profiles: List[QueryProfile]) -> List[Dict[str, Any]]:
        """Get most common query types from profiles."""

        query_type_counts = defaultdict(int)
        for profile in profiles:
            query_type_counts[profile.query_type] += 1

        return sorted(
            [{'query_type': qt, 'count': count} for qt, count in query_type_counts.items()],
            key=lambda x: x['count'],
            reverse=True
        )[:10]

    def _get_top_guilds(self, profiles: List[QueryProfile]) -> List[Dict[str, Any]]:
        """Get most active guilds from profiles."""

        guild_counts = defaultdict(int)
        for profile in profiles:
            guild_counts[profile.guild_id] += 1

        return sorted(
            [{'guild_id': guild_id, 'queries': count} for guild_id, count in guild_counts.items()],
            key=lambda x: x['queries'],
            reverse=True
        )[:10]

    async def _background_cleanup(self):
        """Background task to clean up expired cache entries."""

        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes

                current_time = time.time()

                # Clean up memory cache
                for tier in self.memory_cache:
                    expired_keys = []
                    for cache_key, entry in self.memory_cache[tier].items():
                        if current_time - entry.timestamp > entry.ttl:
                            expired_keys.append(cache_key)

                    for cache_key in expired_keys:
                        del self.memory_cache[tier][cache_key]

                # Clean up old query profiles
                if len(self.query_profiles) > 5000:
                    self.query_profiles = self.query_profiles[-2500:]  # Keep last 2.5k

                logger.debug("🧹 Background cache cleanup completed")

            except Exception as e:
                logger.error(f"Background cleanup error: {e}")

    async def _background_warmup(self):
        """Background task to warm cache with popular queries."""

        # Wait for initial startup
        await asyncio.sleep(60)

        while True:
            try:
                await asyncio.sleep(1800)  # Run every 30 minutes

                # Identify popular query patterns from profiles
                if len(self.query_profiles) < 100:
                    continue

                recent_profiles = self.query_profiles[-500:]  # Last 500 queries

                # Find frequently executed query patterns
                query_patterns = defaultdict(int)
                for profile in recent_profiles:
                    if not profile.cache_hit:  # Only actual executions
                        pattern = f"{profile.guild_id}:{profile.query_type}"
                        query_patterns[pattern] += 1

                # TODO: Implement smart cache warming based on patterns
                logger.debug("🔥 Background cache warming evaluation completed")

            except Exception as e:
                logger.error(f"Background warmup error: {e}")

    async def shutdown(self):
        """Clean shutdown of the cache system."""

        if self.cleanup_task:
            self.cleanup_task.cancel()

        if self.warmup_task:
            self.warmup_task.cancel()

        if self.redis:
            await self.redis.close()

        if self.thread_pool:
            self.thread_pool.shutdown(wait=True)

        logger.info("✅ TimeSeriesQueryCache shut down")


class TimeSeriesQueryOptimizer:
    """
    Query optimization engine for time-series queries.

    Provides intelligent query planning, execution optimization,
    and performance monitoring for InfluxDB queries.
    """

    def __init__(self, cache: TimeSeriesQueryCache):
        self.cache = cache
        self.query_patterns = defaultdict(list)

    async def optimize_flux_query(
        self,
        base_query: str,
        guild_id: int,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        expected_result_size: Optional[int] = None
    ) -> str:
        """
        Optimize a Flux query for better performance.

        Args:
            base_query: Base Flux query to optimize
            guild_id: Guild ID for partitioning optimization
            time_range: Query time range for window optimization
            expected_result_size: Expected result size for limit optimization

        Returns:
            Optimized Flux query string
        """

        optimized_query = base_query
        optimizations_applied = []

        # Guild partitioning optimization
        if guild_id and 'filter(fn: (r) => r.guild_id' not in optimized_query:
            # Add guild filter early in the pipeline
            optimized_query = optimized_query.replace(
                'from(bucket:',
                f'from(bucket:'
            ).replace(
                '|> range(',
                f'|> filter(fn: (r) => r.guild_id == "{guild_id}")\n  |> range('
            )
            optimizations_applied.append('guild_partitioning')

        # Time window optimization
        if time_range:
            start_time, end_time = time_range
            duration = (end_time - start_time).total_seconds()

            # For long time ranges, add downsampling
            if duration > 86400:  # More than 24 hours
                # Add aggregation windows for better performance
                if '|> aggregateWindow(' not in optimized_query:
                    window_size = '1h' if duration > 604800 else '10m'  # 1h for >7days, 10m otherwise

                    optimized_query = optimized_query.replace(
                        '|> sort(columns:',
                        f'|> aggregateWindow(every: {window_size}, fn: mean, createEmpty: false)\n  |> sort(columns:'
                    )
                    optimizations_applied.append('time_window_aggregation')

        # Result size optimization
        if expected_result_size and expected_result_size > 10000:
            # Add limit to prevent very large result sets
            if '|> limit(' not in optimized_query:
                optimized_query = optimized_query.replace(
                    '|> sort(columns:',
                    '|> limit(n: 10000)\n  |> sort(columns:'
                )
                optimizations_applied.append('result_size_limiting')

        # Field selection optimization
        if '|> keep(columns:' not in optimized_query:
            # Add field selection to reduce data transfer
            essential_fields = ['_time', '_value', '_field', 'guild_id', 'encounter_id']
            field_list = '", "'.join(essential_fields)

            optimized_query = optimized_query.replace(
                '|> sort(columns:',
                f'|> keep(columns: ["{field_list}"])\n  |> sort(columns:'
            )
            optimizations_applied.append('field_selection')

        if optimizations_applied:
            logger.debug(f"Applied optimizations: {optimizations_applied}")

        return optimized_query

    async def suggest_query_improvements(
        self,
        guild_id: int,
        query_type: str
    ) -> List[Dict[str, str]]:
        """
        Analyze query patterns and suggest improvements.

        Args:
            guild_id: Guild ID to analyze
            query_type: Type of queries to analyze

        Returns:
            List of improvement suggestions
        """

        suggestions = []

        # Analyze cache performance
        stats = await self.cache.get_performance_stats()
        cache_hit_rate = stats.get('query_insights', {}).get('cache_hit_rate', 0)

        if cache_hit_rate < 0.5:
            suggestions.append({
                'type': 'caching',
                'suggestion': 'Low cache hit rate detected. Consider implementing query result pre-aggregation.',
                'impact': 'high'
            })

        # Analyze query patterns for this guild
        guild_profiles = [
            p for p in self.cache.query_profiles[-1000:]
            if p.guild_id == guild_id and p.query_type == query_type
        ]

        if guild_profiles:
            avg_execution_time = sum(p.execution_time for p in guild_profiles if not p.cache_hit) / \
                               max(1, sum(1 for p in guild_profiles if not p.cache_hit))

            if avg_execution_time > 2.0:  # More than 2 seconds
                suggestions.append({
                    'type': 'performance',
                    'suggestion': f'Average query time of {avg_execution_time:.2f}s is high. Consider adding more specific filters or time ranges.',
                    'impact': 'medium'
                })

            # Check for repeated similar queries
            query_hashes = [p.query_hash for p in guild_profiles]
            unique_queries = len(set(query_hashes))
            total_queries = len(query_hashes)

            if unique_queries < total_queries * 0.3:  # Less than 30% unique queries
                suggestions.append({
                    'type': 'optimization',
                    'suggestion': 'Many repeated queries detected. Cache warming might improve performance.',
                    'impact': 'medium'
                })

        return suggestions