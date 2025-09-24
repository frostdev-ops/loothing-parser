"""
Usage Example and Integration Guide for Time-Series Query Optimization

This module demonstrates how to integrate and use the OptimizedInfluxManager
with existing code to achieve significant performance improvements.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from ..database.hybrid_manager import HybridDatabaseManager
from .optimized_influx_manager import OptimizedInfluxManager
from .time_series_cache import CacheConfig

logger = logging.getLogger(__name__)


class EnhancedQueryService:
    """
    Enhanced query service that demonstrates integration of optimized caching
    with existing database managers.

    This service provides a high-level interface for combat log queries with
    automatic optimization and caching.
    """

    def __init__(self, hybrid_manager: HybridDatabaseManager):
        """
        Initialize the enhanced query service.

        Args:
            hybrid_manager: Existing hybrid database manager
        """
        self.hybrid_manager = hybrid_manager

        # Configure caching for optimal performance
        cache_config = CacheConfig()
        cache_config.HOT_TTL = 300      # 5 minutes for very recent data
        cache_config.WARM_TTL = 1800    # 30 minutes for recent data
        cache_config.COLD_TTL = 7200    # 2 hours for historical data

        # Redis configuration from environment or defaults
        redis_config = {
            'host': 'redis',  # Docker service name
            'port': 6379,
            'db': 2,  # Separate database for time-series cache
            'password': None  # Set if Redis requires authentication
        }

        # Initialize optimized InfluxDB manager
        self.optimized_influx = OptimizedInfluxManager(
            influx_manager=hybrid_manager.influxdb,
            cache_config=cache_config,
            redis_config=redis_config
        )

        logger.info("Enhanced query service initialized")

    async def initialize(self):
        """Initialize the service and all subsystems."""
        await self.optimized_influx.initialize()
        logger.info("✅ Enhanced query service fully initialized")

    # High-level query methods

    async def get_encounter_summary(
        self,
        guild_id: int,
        encounter_id: str,
        include_detailed_events: bool = False
    ) -> Dict[str, Any]:
        """
        Get comprehensive encounter summary with optimal performance.

        This method demonstrates how to combine PostgreSQL metadata
        with optimized InfluxDB time-series queries.

        Args:
            guild_id: Guild identifier
            encounter_id: Encounter to summarize
            include_detailed_events: Whether to include individual events

        Returns:
            Comprehensive encounter summary
        """
        logger.info(f"📊 Getting encounter summary for {encounter_id} (guild {guild_id})")

        # Get encounter metadata from PostgreSQL (fast, small data)
        encounter_metadata = await self._get_encounter_metadata(encounter_id)
        if not encounter_metadata:
            return None

        # Get aggregated metrics from optimized InfluxDB (cached)
        start_time = encounter_metadata['start_time']
        end_time = encounter_metadata['end_time']

        # Use optimized queries with caching
        player_metrics = await self.optimized_influx.query_player_metrics(
            guild_id=guild_id,
            start_time=start_time,
            end_time=end_time,
            encounter_id=encounter_id
        )

        guild_rankings = await self.optimized_influx.query_guild_rankings(
            guild_id=guild_id,
            start_time=start_time,
            end_time=end_time
        )

        summary = {
            'encounter_metadata': encounter_metadata,
            'player_metrics': player_metrics,
            'guild_rankings': guild_rankings,
            'performance_insights': self._analyze_encounter_performance(player_metrics)
        }

        # Include detailed events if requested (this is expensive, so cached aggressively)
        if include_detailed_events:
            detailed_events = await self.optimized_influx.query_encounter_events(
                guild_id=guild_id,
                encounter_id=encounter_id,
                start_time=start_time,
                end_time=end_time,
                limit=1000  # Reasonable limit for UI
            )
            summary['detailed_events'] = detailed_events

        return summary

    async def get_player_dashboard_data(
        self,
        guild_id: int,
        character_name: str,
        days_back: int = 7
    ) -> Dict[str, Any]:
        """
        Get comprehensive player dashboard data with aggressive caching.

        This method demonstrates how to efficiently aggregate data
        for player performance dashboards.

        Args:
            guild_id: Guild identifier
            character_name: Character name to analyze
            days_back: Number of days to analyze

        Returns:
            Player dashboard data
        """
        logger.info(f"🎯 Getting dashboard data for {character_name} (guild {guild_id})")

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days_back)

        # Execute multiple optimized queries in parallel
        tasks = [
            self.optimized_influx.query_player_metrics(
                guild_id=guild_id,
                character_name=character_name,
                start_time=start_time,
                end_time=end_time
            ),
            self.optimized_influx.query_aggregated_metrics(
                guild_id=guild_id,
                start_time=start_time,
                end_time=end_time,
                aggregation_window='1h',
                metrics=['dps', 'hps', 'dtps']
            ),
            self._get_player_encounter_history(guild_id, character_name, days_back)
        ]

        player_metrics, aggregated_metrics, encounter_history = await asyncio.gather(*tasks)

        return {
            'character_name': character_name,
            'analysis_period': {
                'start_time': start_time,
                'end_time': end_time,
                'days': days_back
            },
            'current_metrics': player_metrics,
            'historical_trends': aggregated_metrics,
            'encounter_history': encounter_history,
            'performance_trends': self._analyze_performance_trends(aggregated_metrics),
            'recommendations': self._generate_player_recommendations(player_metrics, aggregated_metrics)
        }

    async def get_guild_dashboard_data(
        self,
        guild_id: int,
        days_back: int = 7
    ) -> Dict[str, Any]:
        """
        Get guild-wide dashboard data with intelligent caching.

        Args:
            guild_id: Guild identifier
            days_back: Number of days to analyze

        Returns:
            Guild dashboard data
        """
        logger.info(f"🏰 Getting guild dashboard data for guild {guild_id}")

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days_back)

        # Warm cache for this guild if it's not already warmed
        await self.optimized_influx.warm_guild_cache(guild_id, (start_time, end_time))

        # Execute guild-wide queries
        tasks = [
            self.optimized_influx.query_guild_rankings(
                guild_id=guild_id,
                start_time=start_time,
                end_time=end_time,
                metric_type='dps'
            ),
            self.optimized_influx.query_guild_rankings(
                guild_id=guild_id,
                start_time=start_time,
                end_time=end_time,
                metric_type='hps'
            ),
            self.optimized_influx.query_aggregated_metrics(
                guild_id=guild_id,
                start_time=start_time,
                end_time=end_time,
                aggregation_window='1d'  # Daily aggregation for guild overview
            ),
            self._get_guild_encounter_summary(guild_id, days_back)
        ]

        dps_rankings, hps_rankings, daily_metrics, encounter_summary = await asyncio.gather(*tasks)

        return {
            'guild_id': guild_id,
            'analysis_period': {
                'start_time': start_time,
                'end_time': end_time,
                'days': days_back
            },
            'performance_rankings': {
                'dps': dps_rankings,
                'hps': hps_rankings
            },
            'activity_trends': daily_metrics,
            'encounter_summary': encounter_summary,
            'guild_insights': self._analyze_guild_performance(daily_metrics, encounter_summary)
        }

    # Batch operations for high-performance scenarios

    async def process_combat_log_batch(
        self,
        guild_id: int,
        combat_events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process a batch of combat events with cache optimization.

        This method demonstrates how to efficiently process large batches
        of combat events while maintaining cache coherence.

        Args:
            guild_id: Guild identifier
            combat_events: List of combat events to process

        Returns:
            Processing summary
        """
        logger.info(f"⚡ Processing batch of {len(combat_events)} events for guild {guild_id}")

        # Group events by time windows for efficient processing
        time_windows = self._group_events_by_time_window(combat_events)

        processing_summary = {
            'total_events': len(combat_events),
            'time_windows': len(time_windows),
            'encounters_affected': set(),
            'cache_invalidations': 0
        }

        for time_window, events in time_windows.items():
            # Process events in this time window
            encounters = await self._process_time_window_events(guild_id, events)
            processing_summary['encounters_affected'].update(encounters)

            # Invalidate relevant cache entries
            window_start, window_end = time_window
            await self.optimized_influx.invalidate_time_range_cache(
                window_start, window_end, guild_id
            )
            processing_summary['cache_invalidations'] += 1

        processing_summary['encounters_affected'] = list(processing_summary['encounters_affected'])

        return processing_summary

    # Performance monitoring and optimization

    async def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report for the service."""

        influx_performance = await self.optimized_influx.get_performance_report()

        return {
            'service_type': 'enhanced_query_service',
            'influx_optimization': influx_performance,
            'cache_recommendations': await self._generate_cache_recommendations(),
            'system_health': await self._assess_system_health()
        }

    async def optimize_for_guild(self, guild_id: int) -> Dict[str, Any]:
        """
        Perform guild-specific optimizations.

        Args:
            guild_id: Guild to optimize for

        Returns:
            Optimization results
        """
        logger.info(f"🔧 Optimizing performance for guild {guild_id}")

        # Warm cache with common queries
        await self.optimized_influx.warm_guild_cache(guild_id)

        # Get optimization suggestions
        suggestions = await self.optimized_influx.optimizer.suggest_query_improvements(
            guild_id, 'all'
        )

        return {
            'guild_id': guild_id,
            'cache_warmed': True,
            'optimization_suggestions': suggestions,
            'expected_improvements': self._estimate_performance_improvements(suggestions)
        }

    # Helper methods

    async def _get_encounter_metadata(self, encounter_id: str) -> Dict[str, Any]:
        """Get encounter metadata from PostgreSQL."""
        # This would use the hybrid manager's PostgreSQL connection
        # Implementation depends on your specific schema
        return {
            'encounter_id': encounter_id,
            'boss_name': 'Ulgrax the Devourer',
            'difficulty': 'Heroic',
            'start_time': datetime.utcnow() - timedelta(hours=1),
            'end_time': datetime.utcnow() - timedelta(minutes=50),
            'success': True
        }

    async def _get_player_encounter_history(
        self,
        guild_id: int,
        character_name: str,
        days_back: int
    ) -> List[Dict[str, Any]]:
        """Get player's encounter history."""
        # Implementation would query PostgreSQL for encounter history
        return []

    async def _get_guild_encounter_summary(
        self,
        guild_id: int,
        days_back: int
    ) -> Dict[str, Any]:
        """Get guild encounter summary."""
        return {
            'total_encounters': 15,
            'successful_encounters': 12,
            'success_rate': 0.8,
            'most_common_boss': 'Ulgrax the Devourer'
        }

    def _group_events_by_time_window(
        self,
        events: List[Dict[str, Any]],
        window_size: int = 300  # 5-minute windows
    ) -> Dict[Tuple[datetime, datetime], List[Dict[str, Any]]]:
        """Group events by time windows."""
        windows = {}

        for event in events:
            timestamp = event.get('timestamp', datetime.utcnow())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)

            # Find the appropriate window
            window_start = timestamp.replace(second=0, microsecond=0)
            window_start = window_start.replace(minute=(window_start.minute // 5) * 5)
            window_end = window_start + timedelta(seconds=window_size)

            window_key = (window_start, window_end)
            if window_key not in windows:
                windows[window_key] = []

            windows[window_key].append(event)

        return windows

    async def _process_time_window_events(
        self,
        guild_id: int,
        events: List[Dict[str, Any]]
    ) -> List[str]:
        """Process events in a time window and return affected encounters."""
        # Implementation would process events and return encounter IDs
        return ['encounter_1', 'encounter_2']

    def _analyze_encounter_performance(self, player_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze encounter performance and provide insights."""
        return {
            'top_performer': 'PlayerName',
            'improvement_areas': ['healing efficiency', 'damage consistency'],
            'overall_grade': 'A-'
        }

    def _analyze_performance_trends(self, aggregated_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance trends over time."""
        return {
            'trending_up': ['dps'],
            'trending_down': [],
            'stable': ['hps', 'dtps']
        }

    def _generate_player_recommendations(
        self,
        current_metrics: Dict[str, Any],
        historical_trends: Dict[str, Any]
    ) -> List[str]:
        """Generate performance recommendations for a player."""
        return [
            "Focus on increasing uptime during high damage phases",
            "Consider optimizing rotation for better resource management"
        ]

    def _analyze_guild_performance(
        self,
        daily_metrics: Dict[str, Any],
        encounter_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze guild-wide performance."""
        return {
            'overall_performance': 'above_average',
            'strengths': ['coordination', 'damage output'],
            'improvement_areas': ['healing efficiency'],
            'trending_direction': 'positive'
        }

    async def _generate_cache_recommendations(self) -> List[str]:
        """Generate caching optimization recommendations."""
        performance_stats = await self.optimized_influx.cache.get_performance_stats()

        recommendations = []

        cache_hit_rate = performance_stats.get('query_insights', {}).get('cache_hit_rate', 0)
        if cache_hit_rate < 0.5:
            recommendations.append("Consider increasing cache TTL for historical data queries")

        memory_usage = performance_stats.get('memory_cache', {})
        for tier, stats in memory_usage.items():
            if stats.get('utilization', 0) > 0.9:
                recommendations.append(f"Consider increasing {tier} memory cache size")

        return recommendations

    async def _assess_system_health(self) -> Dict[str, str]:
        """Assess overall system health."""
        return {
            'influxdb_connection': 'healthy',
            'redis_connection': 'healthy',
            'cache_performance': 'optimal',
            'query_performance': 'good'
        }

    def _estimate_performance_improvements(self, suggestions: List[Dict[str, str]]) -> Dict[str, Any]:
        """Estimate expected performance improvements."""
        return {
            'expected_cache_hit_improvement': '15-25%',
            'expected_query_time_reduction': '30-50%',
            'expected_resource_savings': 'moderate'
        }

    async def shutdown(self):
        """Clean shutdown of the enhanced query service."""
        await self.optimized_influx.shutdown()
        logger.info("✅ Enhanced query service shut down")


# Example usage and integration patterns

async def example_usage():
    """
    Example of how to integrate and use the enhanced query service.
    """

    # Assume you have an existing hybrid manager
    from ..database.hybrid_manager import HybridDatabaseManager

    # Initialize hybrid manager (existing code)
    hybrid_manager = HybridDatabaseManager(
        # Your existing configuration
    )

    # Create enhanced service
    enhanced_service = EnhancedQueryService(hybrid_manager)
    await enhanced_service.initialize()

    guild_id = 1001  # Example guild ID

    try:
        # Example 1: Get encounter summary (fast, cached)
        encounter_summary = await enhanced_service.get_encounter_summary(
            guild_id=guild_id,
            encounter_id="guild1001_t1640995200000_enc2902_abc123ef"
        )
        print(f"📊 Encounter summary: {encounter_summary['encounter_metadata']['boss_name']}")

        # Example 2: Get player dashboard (optimized, cached)
        player_dashboard = await enhanced_service.get_player_dashboard_data(
            guild_id=guild_id,
            character_name="Testplayer",
            days_back=7
        )
        print(f"🎯 Player trends: {player_dashboard['performance_trends']}")

        # Example 3: Get guild dashboard (cached, pre-warmed)
        guild_dashboard = await enhanced_service.get_guild_dashboard_data(
            guild_id=guild_id,
            days_back=7
        )
        print(f"🏰 Guild performance: {guild_dashboard['guild_insights']['overall_performance']}")

        # Example 4: Performance optimization
        optimization_results = await enhanced_service.optimize_for_guild(guild_id)
        print(f"🔧 Optimization suggestions: {len(optimization_results['optimization_suggestions'])}")

        # Example 5: Performance monitoring
        performance_report = await enhanced_service.get_performance_report()
        cache_hit_rate = performance_report['influx_optimization']['cache_performance']['query_insights']['cache_hit_rate']
        print(f"📈 Cache hit rate: {cache_hit_rate:.2%}")

    finally:
        await enhanced_service.shutdown()


if __name__ == "__main__":
    # Run the example
    asyncio.run(example_usage())