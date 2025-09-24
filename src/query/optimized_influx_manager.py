"""
Optimized InfluxDB Manager with Advanced Caching

This module integrates the TimeSeriesQueryCache with the existing InfluxDB infrastructure
to provide high-performance, cache-optimized time-series queries.
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from contextlib import asynccontextmanager

from ..database.influxdb_direct_manager import InfluxDBDirectManager
from ..database.influx_manager import InfluxDBManager
from .time_series_cache import TimeSeriesQueryCache, TimeSeriesQueryOptimizer, CacheConfig

logger = logging.getLogger(__name__)


@dataclass
class QueryExecutionPlan:
    """Plan for executing optimized queries."""

    query_type: str
    guild_id: int
    filters: Dict[str, Any]
    time_range: Optional[Tuple[datetime, datetime]]
    optimized_flux_query: str
    estimated_result_size: int
    cache_strategy: str
    execution_priority: int


class OptimizedInfluxManager:
    """
    High-performance InfluxDB manager with advanced caching and query optimization.

    Features:
    - Transparent caching layer over existing InfluxDB managers
    - Intelligent query optimization and planning
    - Guild-aware query partitioning
    - Performance monitoring and adaptive optimization
    - Batch query execution
    - Query result pre-aggregation
    """

    def __init__(
        self,
        influx_manager: InfluxDBManager,
        direct_manager: Optional[InfluxDBDirectManager] = None,
        cache_config: Optional[CacheConfig] = None,
        redis_config: Optional[Dict[str, Any]] = None
    ):
        self.influx_manager = influx_manager
        self.direct_manager = direct_manager or InfluxDBDirectManager(
            url=influx_manager.url,
            token=influx_manager.token,
            org=influx_manager.org,
            bucket=influx_manager.bucket
        )

        # Initialize caching system
        redis_config = redis_config or {}
        self.cache = TimeSeriesQueryCache(
            redis_host=redis_config.get('host', 'redis'),
            redis_port=redis_config.get('port', 6379),
            redis_db=redis_config.get('db', 2),
            redis_password=redis_config.get('password'),
            config=cache_config
        )

        # Initialize query optimizer
        self.optimizer = TimeSeriesQueryOptimizer(self.cache)

        # Query execution tracking
        self.active_queries = {}
        self.query_queue = asyncio.Queue(maxsize=100)

        # Performance metrics
        self.performance_metrics = {
            'total_queries': 0,
            'cached_queries': 0,
            'optimized_queries': 0,
            'total_execution_time': 0.0,
            'total_saved_time': 0.0,
            'query_types': {},
            'guild_activity': {}
        }

        # Background tasks
        self.query_processor_task = None
        self.metrics_reporter_task = None

        logger.info("OptimizedInfluxManager initialized")

    async def initialize(self):
        """Initialize the optimized manager and all subsystems."""

        await self.cache.initialize()

        # Start background query processor
        self.query_processor_task = asyncio.create_task(self._process_query_queue())

        # Start metrics reporting
        self.metrics_reporter_task = asyncio.create_task(self._report_metrics())

        logger.info("✅ OptimizedInfluxManager fully initialized")

    # High-level query methods with caching

    async def query_encounter_events(
        self,
        guild_id: int,
        encounter_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        character_id: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query encounter events with intelligent caching and optimization.

        Args:
            guild_id: Guild identifier for multi-tenant isolation
            encounter_id: Specific encounter to query
            start_time: Start of time window
            end_time: End of time window
            character_id: Filter by specific character
            event_types: Filter by event types
            limit: Maximum number of results

        Returns:
            List of encounter events
        """

        filters = {
            'encounter_id': encounter_id,
            'character_id': character_id,
            'event_types': event_types,
            'limit': limit
        }

        time_range = (start_time, end_time) if start_time and end_time else None

        async def executor():
            return await self._execute_encounter_events_query(
                guild_id, encounter_id, start_time, end_time,
                character_id, event_types, limit
            )

        result, was_cached = await self.cache.get_or_execute(
            guild_id=guild_id,
            query_type='encounter_events',
            filters=filters,
            query_executor=executor,
            time_range=time_range
        )

        self._update_metrics('encounter_events', guild_id, was_cached)
        return result

    async def query_player_metrics(
        self,
        guild_id: int,
        character_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        metric_types: Optional[List[str]] = None,
        encounter_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query player performance metrics with caching optimization.

        Args:
            guild_id: Guild identifier
            character_name: Specific character to query
            start_time: Start of time window
            end_time: End of time window
            metric_types: Types of metrics to retrieve
            encounter_id: Specific encounter context

        Returns:
            Player metrics dictionary
        """

        filters = {
            'character_name': character_name,
            'metric_types': metric_types,
            'encounter_id': encounter_id
        }

        time_range = (start_time, end_time) if start_time and end_time else None

        async def executor():
            return await self._execute_player_metrics_query(
                guild_id, character_name, start_time, end_time,
                metric_types, encounter_id
            )

        result, was_cached = await self.cache.get_or_execute(
            guild_id=guild_id,
            query_type='player_metrics',
            filters=filters,
            query_executor=executor,
            time_range=time_range
        )

        self._update_metrics('player_metrics', guild_id, was_cached)
        return result

    async def query_guild_rankings(
        self,
        guild_id: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        boss_name: Optional[str] = None,
        difficulty: Optional[str] = None,
        metric_type: str = 'dps'
    ) -> List[Dict[str, Any]]:
        """
        Query guild rankings with aggressive caching.

        Args:
            guild_id: Guild identifier
            start_time: Start of time window
            end_time: End of time window
            boss_name: Specific boss to rank
            difficulty: Raid difficulty filter
            metric_type: Ranking metric (dps, hps, etc.)

        Returns:
            List of ranked players
        """

        filters = {
            'boss_name': boss_name,
            'difficulty': difficulty,
            'metric_type': metric_type
        }

        time_range = (start_time, end_time) if start_time and end_time else None

        async def executor():
            return await self._execute_guild_rankings_query(
                guild_id, start_time, end_time, boss_name, difficulty, metric_type
            )

        result, was_cached = await self.cache.get_or_execute(
            guild_id=guild_id,
            query_type='guild_rankings',
            filters=filters,
            query_executor=executor,
            time_range=time_range
        )

        self._update_metrics('guild_rankings', guild_id, was_cached)
        return result

    async def query_aggregated_metrics(
        self,
        guild_id: int,
        start_time: datetime,
        end_time: datetime,
        aggregation_window: str = '1h',
        metrics: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Query pre-aggregated metrics for performance dashboards.

        Args:
            guild_id: Guild identifier
            start_time: Start of time window
            end_time: End of time window
            aggregation_window: Window size for aggregation (1m, 5m, 1h, etc.)
            metrics: Specific metrics to retrieve

        Returns:
            Dictionary of aggregated metrics by type
        """

        filters = {
            'aggregation_window': aggregation_window,
            'metrics': metrics
        }

        time_range = (start_time, end_time)

        async def executor():
            return await self._execute_aggregated_metrics_query(
                guild_id, start_time, end_time, aggregation_window, metrics
            )

        result, was_cached = await self.cache.get_or_execute(
            guild_id=guild_id,
            query_type='aggregated_metrics',
            filters=filters,
            query_executor=executor,
            time_range=time_range
        )

        self._update_metrics('aggregated_metrics', guild_id, was_cached)
        return result

    # Batch query operations

    async def execute_batch_queries(
        self,
        queries: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], bool]]:  # Returns (result, was_cached) pairs
        """
        Execute multiple queries in batch with optimal scheduling.

        Args:
            queries: List of query specifications

        Returns:
            List of (result, was_cached) tuples
        """

        logger.info(f"🔄 Executing batch of {len(queries)} queries")

        # Group queries by guild for optimal execution
        guild_groups = {}
        for i, query in enumerate(queries):
            guild_id = query.get('guild_id', 1)
            if guild_id not in guild_groups:
                guild_groups[guild_id] = []
            guild_groups[guild_id].append((i, query))

        # Execute queries in parallel by guild
        tasks = []
        for guild_id, guild_queries in guild_groups.items():
            task = asyncio.create_task(
                self._execute_guild_query_batch(guild_id, guild_queries)
            )
            tasks.append(task)

        # Wait for all batches to complete
        batch_results = await asyncio.gather(*tasks)

        # Reconstruct results in original order
        results = [None] * len(queries)
        for batch_result in batch_results:
            for original_index, result in batch_result:
                results[original_index] = result

        return results

    async def _execute_guild_query_batch(
        self,
        guild_id: int,
        guild_queries: List[Tuple[int, Dict[str, Any]]]
    ) -> List[Tuple[int, Tuple[Any, bool]]]:
        """Execute a batch of queries for a specific guild."""

        results = []

        for original_index, query in guild_queries:
            try:
                query_type = query.get('type')
                if query_type == 'encounter_events':
                    result = await self.query_encounter_events(
                        guild_id=guild_id,
                        encounter_id=query.get('encounter_id'),
                        start_time=query.get('start_time'),
                        end_time=query.get('end_time'),
                        character_id=query.get('character_id'),
                        event_types=query.get('event_types'),
                        limit=query.get('limit')
                    )
                    results.append((original_index, (result, True)))  # Assume cached for simplicity

                elif query_type == 'player_metrics':
                    result = await self.query_player_metrics(
                        guild_id=guild_id,
                        character_name=query.get('character_name'),
                        start_time=query.get('start_time'),
                        end_time=query.get('end_time'),
                        metric_types=query.get('metric_types'),
                        encounter_id=query.get('encounter_id')
                    )
                    results.append((original_index, (result, True)))

                # Add other query types as needed

            except Exception as e:
                logger.error(f"Batch query execution failed: {e}")
                results.append((original_index, (None, False)))

        return results

    # Cache management operations

    async def warm_guild_cache(
        self,
        guild_id: int,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ):
        """
        Warm cache with common queries for a guild.

        Args:
            guild_id: Guild to warm cache for
            time_range: Time range to focus warming on
        """

        logger.info(f"🔥 Warming cache for guild {guild_id}")

        # Default to last 7 days if no time range specified
        if not time_range:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            time_range = (start_time, end_time)

        # Common query patterns to warm
        common_queries = [
            {
                'query_type': 'guild_rankings',
                'filters': {'metric_type': 'dps'},
                'time_range': time_range,
                'executor': lambda: self._execute_guild_rankings_query(
                    guild_id, time_range[0], time_range[1], None, None, 'dps'
                )
            },
            {
                'query_type': 'guild_rankings',
                'filters': {'metric_type': 'hps'},
                'time_range': time_range,
                'executor': lambda: self._execute_guild_rankings_query(
                    guild_id, time_range[0], time_range[1], None, None, 'hps'
                )
            },
            {
                'query_type': 'aggregated_metrics',
                'filters': {'aggregation_window': '1h'},
                'time_range': time_range,
                'executor': lambda: self._execute_aggregated_metrics_query(
                    guild_id, time_range[0], time_range[1], '1h', None
                )
            }
        ]

        await self.cache.warm_cache_for_guild(guild_id, common_queries)

    async def invalidate_guild_cache(self, guild_id: int):
        """Invalidate all cached data for a guild."""
        await self.cache.invalidate_guild_cache(guild_id)

    async def invalidate_time_range_cache(
        self,
        start_time: datetime,
        end_time: datetime,
        guild_id: Optional[int] = None
    ):
        """Invalidate cached data for a specific time range."""
        await self.cache.invalidate_time_range(start_time, end_time, guild_id)

    # Query execution implementations

    async def _execute_encounter_events_query(
        self,
        guild_id: int,
        encounter_id: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        character_id: Optional[int],
        event_types: Optional[List[str]],
        limit: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Execute the actual encounter events query."""

        # Use direct manager for time-series queries
        events = await asyncio.get_event_loop().run_in_executor(
            None,
            self.direct_manager.query_encounter_events,
            encounter_id,
            start_time,
            end_time,
            character_id,
            event_types,
            limit
        )

        # Filter by guild_id if not already filtered in the query
        if guild_id:
            events = [event for event in events if event.get('guild_id') == guild_id]

        return events

    async def _execute_player_metrics_query(
        self,
        guild_id: int,
        character_name: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        metric_types: Optional[List[str]],
        encounter_id: Optional[str]
    ) -> Dict[str, Any]:
        """Execute the actual player metrics query."""

        # Build and execute optimized Flux query
        base_query = self._build_player_metrics_flux_query(
            guild_id, character_name, start_time, end_time, metric_types, encounter_id
        )

        optimized_query = await self.optimizer.optimize_flux_query(
            base_query, guild_id, (start_time, end_time) if start_time and end_time else None
        )

        # Execute query
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            self._execute_flux_query,
            optimized_query
        )

        return self._process_player_metrics_result(result)

    async def _execute_guild_rankings_query(
        self,
        guild_id: int,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        boss_name: Optional[str],
        difficulty: Optional[str],
        metric_type: str
    ) -> List[Dict[str, Any]]:
        """Execute the actual guild rankings query."""

        base_query = self._build_guild_rankings_flux_query(
            guild_id, start_time, end_time, boss_name, difficulty, metric_type
        )

        optimized_query = await self.optimizer.optimize_flux_query(
            base_query, guild_id, (start_time, end_time) if start_time and end_time else None, 100
        )

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            self._execute_flux_query,
            optimized_query
        )

        return self._process_guild_rankings_result(result)

    async def _execute_aggregated_metrics_query(
        self,
        guild_id: int,
        start_time: datetime,
        end_time: datetime,
        aggregation_window: str,
        metrics: Optional[List[str]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Execute pre-aggregated metrics query."""

        base_query = self._build_aggregated_metrics_flux_query(
            guild_id, start_time, end_time, aggregation_window, metrics
        )

        optimized_query = await self.optimizer.optimize_flux_query(
            base_query, guild_id, (start_time, end_time)
        )

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            self._execute_flux_query,
            optimized_query
        )

        return self._process_aggregated_metrics_result(result)

    # Flux query builders

    def _build_player_metrics_flux_query(
        self,
        guild_id: int,
        character_name: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        metric_types: Optional[List[str]],
        encounter_id: Optional[str]
    ) -> str:
        """Build Flux query for player metrics."""

        time_filter = ""
        if start_time and end_time:
            time_filter = f'|> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)'

        character_filter = ""
        if character_name:
            character_filter = f'|> filter(fn: (r) => r.source_name == "{character_name}")'

        encounter_filter = ""
        if encounter_id:
            encounter_filter = f'|> filter(fn: (r) => r.encounter_id == "{encounter_id}")'

        metric_filter = ""
        if metric_types:
            metric_list = '", "'.join(metric_types)
            metric_filter = f'|> filter(fn: (r) => contains(value: r._field, set: ["{metric_list}"]))'

        return f"""
from(bucket: "combat_events")
  {time_filter}
  |> filter(fn: (r) => r._measurement == "combat_events")
  |> filter(fn: (r) => r.guild_id == "{guild_id}")
  {character_filter}
  {encounter_filter}
  {metric_filter}
  |> aggregateWindow(every: 30s, fn: sum, createEmpty: false)
  |> group(columns: ["source_name", "_field"])
  |> sum()
  |> sort(columns: ["_time"])
""".strip()

    def _build_guild_rankings_flux_query(
        self,
        guild_id: int,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        boss_name: Optional[str],
        difficulty: Optional[str],
        metric_type: str
    ) -> str:
        """Build Flux query for guild rankings."""

        time_filter = ""
        if start_time and end_time:
            time_filter = f'|> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)'

        boss_filter = ""
        if boss_name:
            boss_filter = f'|> filter(fn: (r) => r.boss_name == "{boss_name}")'

        difficulty_filter = ""
        if difficulty:
            difficulty_filter = f'|> filter(fn: (r) => r.difficulty == "{difficulty}")'

        return f"""
from(bucket: "combat_events")
  {time_filter}
  |> filter(fn: (r) => r._measurement == "combat_events")
  |> filter(fn: (r) => r.guild_id == "{guild_id}")
  |> filter(fn: (r) => r._field == "{metric_type}")
  {boss_filter}
  {difficulty_filter}
  |> group(columns: ["source_name"])
  |> sum()
  |> group()
  |> sort(columns: ["_value"], desc: true)
  |> limit(n: 50)
""".strip()

    def _build_aggregated_metrics_flux_query(
        self,
        guild_id: int,
        start_time: datetime,
        end_time: datetime,
        aggregation_window: str,
        metrics: Optional[List[str]]
    ) -> str:
        """Build Flux query for aggregated metrics."""

        metric_filter = ""
        if metrics:
            metric_list = '", "'.join(metrics)
            metric_filter = f'|> filter(fn: (r) => contains(value: r._field, set: ["{metric_list}"]))'

        return f"""
from(bucket: "combat_aggregated")
  |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
  |> filter(fn: (r) => r._measurement == "combat_hourly")
  |> filter(fn: (r) => r.guild_id == "{guild_id}")
  {metric_filter}
  |> aggregateWindow(every: {aggregation_window}, fn: mean, createEmpty: false)
  |> group(columns: ["_field"])
  |> sort(columns: ["_time"])
""".strip()

    def _execute_flux_query(self, flux_query: str) -> List[Dict[str, Any]]:
        """Execute a Flux query and return results."""

        try:
            # Use the InfluxDB client to execute the query
            query_api = self.influx_manager.client.query_api()
            result = query_api.query(org=self.influx_manager.org, query=flux_query)

            # Convert result to list of dictionaries
            data = []
            for table in result:
                for record in table.records:
                    data.append({
                        'time': record.get_time(),
                        'value': record.get_value(),
                        'field': record.get_field(),
                        **record.values
                    })

            return data

        except Exception as e:
            logger.error(f"Flux query execution failed: {e}")
            raise

    # Result processors

    def _process_player_metrics_result(self, result: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process raw query result into player metrics format."""

        metrics = {}
        for record in result:
            field = record.get('field', 'unknown')
            value = record.get('value', 0)
            source = record.get('source_name', 'unknown')

            if source not in metrics:
                metrics[source] = {}

            metrics[source][field] = value

        return metrics

    def _process_guild_rankings_result(self, result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process raw query result into guild rankings format."""

        rankings = []
        for i, record in enumerate(result):
            rankings.append({
                'rank': i + 1,
                'character_name': record.get('source_name', 'Unknown'),
                'value': record.get('value', 0),
                'field': record.get('field', 'unknown')
            })

        return rankings

    def _process_aggregated_metrics_result(self, result: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Process raw query result into aggregated metrics format."""

        metrics_by_field = {}
        for record in result:
            field = record.get('field', 'unknown')
            if field not in metrics_by_field:
                metrics_by_field[field] = []

            metrics_by_field[field].append({
                'time': record.get('time'),
                'value': record.get('value', 0)
            })

        return metrics_by_field

    # Utility methods

    def _update_metrics(self, query_type: str, guild_id: int, was_cached: bool):
        """Update internal performance metrics."""

        self.performance_metrics['total_queries'] += 1

        if was_cached:
            self.performance_metrics['cached_queries'] += 1

        if query_type not in self.performance_metrics['query_types']:
            self.performance_metrics['query_types'][query_type] = 0
        self.performance_metrics['query_types'][query_type] += 1

        if guild_id not in self.performance_metrics['guild_activity']:
            self.performance_metrics['guild_activity'][guild_id] = 0
        self.performance_metrics['guild_activity'][guild_id] += 1

    async def _process_query_queue(self):
        """Background task to process queued queries."""

        while True:
            try:
                # Process queued queries
                await asyncio.sleep(1)
                # TODO: Implement query queue processing

            except Exception as e:
                logger.error(f"Query queue processing error: {e}")

    async def _report_metrics(self):
        """Background task to report performance metrics."""

        while True:
            try:
                await asyncio.sleep(300)  # Report every 5 minutes

                cache_stats = await self.cache.get_performance_stats()

                logger.info(f"📊 OptimizedInfluxManager Performance:")
                logger.info(f"   Total Queries: {self.performance_metrics['total_queries']}")
                logger.info(f"   Cache Hit Rate: {cache_stats.get('query_insights', {}).get('cache_hit_rate', 0):.2%}")
                logger.info(f"   Active Guilds: {len(self.performance_metrics['guild_activity'])}")

            except Exception as e:
                logger.error(f"Metrics reporting error: {e}")

    # Performance and monitoring

    async def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""

        cache_stats = await self.cache.get_performance_stats()

        optimization_suggestions = []
        for guild_id in self.performance_metrics['guild_activity']:
            suggestions = await self.optimizer.suggest_query_improvements(guild_id, 'all')
            optimization_suggestions.extend(suggestions)

        return {
            'manager_metrics': self.performance_metrics,
            'cache_performance': cache_stats,
            'optimization_suggestions': optimization_suggestions,
            'active_queries': len(self.active_queries),
            'queue_size': self.query_queue.qsize() if hasattr(self.query_queue, 'qsize') else 0
        }

    @asynccontextmanager
    async def query_context(self, query_id: str):
        """Context manager for tracking query execution."""

        self.active_queries[query_id] = {
            'start_time': time.time(),
            'status': 'executing'
        }

        try:
            yield
        finally:
            if query_id in self.active_queries:
                del self.active_queries[query_id]

    async def shutdown(self):
        """Clean shutdown of the optimized manager."""

        if self.query_processor_task:
            self.query_processor_task.cancel()

        if self.metrics_reporter_task:
            self.metrics_reporter_task.cancel()

        await self.cache.shutdown()

        logger.info("✅ OptimizedInfluxManager shut down")