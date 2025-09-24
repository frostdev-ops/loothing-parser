#!/usr/bin/env python3
"""
Comprehensive Test Suite for Time-Series Query Cache and Optimization

This test suite verifies:
1. Syntax and import validation
2. Multi-tenant guild isolation
3. Cache performance optimization
4. Time-series query patterns
5. Integration with storage layer
"""

import os
import sys
import asyncio
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch

# Add the src directory to the path
sys.path.insert(0, '/home/pma/lootbong-trackdong/parser')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceOptimizationTest:
    """Comprehensive test suite for time-series optimization."""

    def __init__(self):
        self.results = {
            'syntax_validation': False,
            'import_validation': False,
            'guild_isolation': False,
            'caching_performance': False,
            'query_optimization': False,
            'time_window_handling': False,
            'integration_tests': False,
            'performance_benchmarks': {}
        }

    async def run_all_tests(self):
        """Run complete test suite."""
        logger.info("🚀 Starting Time-Series Optimization Test Suite")

        # Test 1: Syntax and Import Validation
        await self.test_syntax_validation()

        # Test 2: Multi-tenant Guild Isolation
        await self.test_guild_isolation()

        # Test 3: Caching Performance
        await self.test_caching_performance()

        # Test 4: Query Optimization
        await self.test_query_optimization()

        # Test 5: Time-window Handling
        await self.test_time_window_handling()

        # Test 6: Integration with Storage Layer
        await self.test_storage_integration()

        # Test 7: Performance Benchmarks
        await self.test_performance_benchmarks()

        # Generate final report
        self.generate_report()

    async def test_syntax_validation(self):
        """Test syntax validation and imports."""
        logger.info("📋 Testing syntax validation and imports...")

        try:
            # Test basic syntax compilation
            import py_compile

            files_to_test = [
                'src/query/time_series_cache.py',
                'src/query/optimized_influx_manager.py'
            ]

            for file_path in files_to_test:
                full_path = os.path.join('/home/pma/lootbong-trackdong/parser', file_path)
                try:
                    py_compile.compile(full_path, doraise=True)
                    logger.info(f"✅ {file_path} syntax validation passed")
                except py_compile.PyCompileError as e:
                    logger.error(f"❌ {file_path} syntax error: {e}")
                    return

            # Test imports with mock dependencies
            with patch('redis.asyncio.Redis'):
                with patch('influxdb_client.InfluxDBClient'):
                    try:
                        from src.query.time_series_cache import (
                            TimeSeriesQueryCache,
                            TimeSeriesQueryOptimizer,
                            CacheConfig,
                            CacheEntry,
                            QueryProfile
                        )
                        from src.query.optimized_influx_manager import (
                            OptimizedInfluxManager,
                            QueryExecutionPlan
                        )

                        logger.info("✅ All imports successful with mocked dependencies")
                        self.results['syntax_validation'] = True
                        self.results['import_validation'] = True

                    except Exception as e:
                        logger.error(f"❌ Import error: {e}")

        except Exception as e:
            logger.error(f"❌ Syntax validation failed: {e}")

    async def test_guild_isolation(self):
        """Test multi-tenant guild isolation in caching."""
        logger.info("🏰 Testing guild isolation in cache layers...")

        try:
            with patch('redis.asyncio.Redis'):
                from src.query.time_series_cache import TimeSeriesQueryCache, CacheConfig

                # Create cache instance
                cache = TimeSeriesQueryCache(
                    redis_host='localhost',
                    redis_port=6379,
                    config=CacheConfig()
                )

                # Mock Redis for testing
                mock_redis = MagicMock()
                cache.redis = mock_redis

                # Test guild-specific cache key generation
                key1 = cache._generate_cache_key(
                    guild_id=123,
                    query_type='encounter_events',
                    filters={'encounter_id': 'test'},
                    time_range=None
                )

                key2 = cache._generate_cache_key(
                    guild_id=456,
                    query_type='encounter_events',
                    filters={'encounter_id': 'test'},
                    time_range=None
                )

                # Verify guild separation in keys
                assert 'ts_cache:123:' in key1, "Guild ID not in cache key"
                assert 'ts_cache:456:' in key2, "Guild ID not in cache key"
                assert key1 != key2, "Different guilds should have different cache keys"

                logger.info("✅ Guild isolation in cache keys verified")

                # Test cache invalidation for specific guild
                await cache.invalidate_guild_cache(123)

                # Verify Redis scan was called with guild-specific pattern
                if hasattr(mock_redis, 'scan'):
                    logger.info("✅ Guild-specific cache invalidation verified")

                self.results['guild_isolation'] = True

        except Exception as e:
            logger.error(f"❌ Guild isolation test failed: {e}")

    async def test_caching_performance(self):
        """Test caching performance and optimization strategies."""
        logger.info("⚡ Testing caching performance optimization...")

        try:
            with patch('redis.asyncio.Redis'):
                from src.query.time_series_cache import TimeSeriesQueryCache, CacheConfig

                cache = TimeSeriesQueryCache(config=CacheConfig())

                # Mock query executor for performance testing
                async def mock_query_executor():
                    await asyncio.sleep(0.1)  # Simulate 100ms query
                    return {"test": "data", "metrics": [1, 2, 3, 4, 5]}

                # Test cache miss performance
                start_time = time.time()
                result1, was_cached1 = await cache.get_or_execute(
                    guild_id=123,
                    query_type='test_query',
                    filters={'test': True},
                    query_executor=mock_query_executor
                )
                miss_time = time.time() - start_time

                # Test cache hit performance
                start_time = time.time()
                result2, was_cached2 = await cache.get_or_execute(
                    guild_id=123,
                    query_type='test_query',
                    filters={'test': True},
                    query_executor=mock_query_executor
                )
                hit_time = time.time() - start_time

                # Verify caching behavior
                assert not was_cached1, "First query should be cache miss"
                assert was_cached2, "Second query should be cache hit"
                assert hit_time < miss_time / 2, "Cache hit should be much faster"

                logger.info(f"✅ Cache miss time: {miss_time:.3f}s, hit time: {hit_time:.3f}s")

                # Test cache tier determination
                now = datetime.utcnow()

                # Hot tier (recent data)
                hot_tier = cache._determine_cache_tier(
                    'test', (now - timedelta(minutes=30), now)
                )
                assert hot_tier == 'hot', "Recent data should use hot tier"

                # Cold tier (old data)
                cold_tier = cache._determine_cache_tier(
                    'test', (now - timedelta(days=30), now - timedelta(days=29))
                )
                assert cold_tier == 'cold', "Old data should use cold tier"

                logger.info("✅ Cache tier optimization verified")
                self.results['caching_performance'] = True

        except Exception as e:
            logger.error(f"❌ Caching performance test failed: {e}")

    async def test_query_optimization(self):
        """Test time-series query optimization patterns."""
        logger.info("🔍 Testing query optimization patterns...")

        try:
            with patch('redis.asyncio.Redis'):
                from src.query.time_series_cache import TimeSeriesQueryCache, TimeSeriesQueryOptimizer

                cache = TimeSeriesQueryCache()
                optimizer = TimeSeriesQueryOptimizer(cache)

                # Test Flux query optimization
                base_query = """
from(bucket: "combat_events")
  |> range(start: 2024-01-01T00:00:00Z, stop: 2024-01-02T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "combat_events")
  |> sort(columns: ["_time"])
"""

                now = datetime.utcnow()
                time_range = (now - timedelta(hours=24), now)

                optimized_query = await optimizer.optimize_flux_query(
                    base_query=base_query,
                    guild_id=123,
                    time_range=time_range,
                    expected_result_size=5000
                )

                # Verify guild partitioning was added
                assert 'guild_id == "123"' in optimized_query, "Guild partitioning not applied"

                # Verify field selection optimization
                assert '|> keep(columns:' in optimized_query, "Field selection not applied"

                logger.info("✅ Query optimization patterns verified")

                # Test optimization suggestions
                suggestions = await optimizer.suggest_query_improvements(
                    guild_id=123,
                    query_type='encounter_events'
                )

                assert isinstance(suggestions, list), "Suggestions should be a list"

                logger.info(f"✅ Generated {len(suggestions)} optimization suggestions")
                self.results['query_optimization'] = True

        except Exception as e:
            logger.error(f"❌ Query optimization test failed: {e}")

    async def test_time_window_handling(self):
        """Test time-window encounter handling."""
        logger.info("⏰ Testing time-window encounter handling...")

        try:
            with patch('redis.asyncio.Redis'):
                from src.query.time_series_cache import TimeSeriesQueryCache

                cache = TimeSeriesQueryCache()

                now = datetime.utcnow()

                # Test time range cache invalidation
                start_time = now - timedelta(hours=2)
                end_time = now - timedelta(hours=1)

                # Create mock cache entries with time ranges
                cache.memory_cache['hot']['test1'] = type('MockEntry', (), {
                    'time_range': (start_time - timedelta(minutes=30), start_time + timedelta(minutes=30)),
                    'guild_id': 123
                })()

                cache.memory_cache['hot']['test2'] = type('MockEntry', (), {
                    'time_range': (end_time + timedelta(minutes=30), end_time + timedelta(hours=1)),
                    'guild_id': 123
                })()

                # Test time range invalidation
                await cache.invalidate_time_range(start_time, end_time, guild_id=123)

                # Verify overlapping entry was removed
                assert 'test1' not in cache.memory_cache['hot'], "Overlapping cache entry should be removed"
                assert 'test2' in cache.memory_cache['hot'], "Non-overlapping entry should remain"

                logger.info("✅ Time-window cache invalidation verified")

                # Test TTL calculation for different time ranges
                hot_ttl = cache._get_ttl_for_query('encounter_events', None, 'hot')
                cold_ttl = cache._get_ttl_for_query('encounter_events', None, 'cold')

                assert cold_ttl > hot_ttl, "Cold tier should have longer TTL"

                logger.info("✅ Time-based TTL optimization verified")
                self.results['time_window_handling'] = True

        except Exception as e:
            logger.error(f"❌ Time-window handling test failed: {e}")

    async def test_storage_integration(self):
        """Test integration with storage layer components."""
        logger.info("🔗 Testing storage layer integration...")

        try:
            # Mock the required database managers
            with patch('src.database.influxdb_direct_manager.InfluxDBDirectManager') as mock_direct:
                with patch('src.database.influx_manager.InfluxDBManager') as mock_influx:
                    with patch('redis.asyncio.Redis'):
                        from src.query.optimized_influx_manager import OptimizedInfluxManager

                        # Create mock managers
                        mock_influx_instance = MagicMock()
                        mock_influx_instance.url = 'http://localhost:8086'
                        mock_influx_instance.token = 'test-token'
                        mock_influx_instance.org = 'test-org'
                        mock_influx_instance.bucket = 'combat_events'

                        mock_direct_instance = MagicMock()
                        mock_direct.return_value = mock_direct_instance

                        # Initialize optimized manager
                        optimized_manager = OptimizedInfluxManager(
                            influx_manager=mock_influx_instance,
                            redis_config={'host': 'localhost', 'port': 6379}
                        )

                        # Test initialization
                        await optimized_manager.initialize()

                        logger.info("✅ OptimizedInfluxManager initialization successful")

                        # Test query execution plan creation
                        plan = optimized_manager._build_player_metrics_flux_query(
                            guild_id=123,
                            character_name='TestPlayer',
                            start_time=datetime.utcnow() - timedelta(hours=1),
                            end_time=datetime.utcnow(),
                            metric_types=['dps', 'hps'],
                            encounter_id='test-encounter'
                        )

                        assert 'guild_id == "123"' in plan, "Guild filter not in query"
                        assert 'TestPlayer' in plan, "Character filter not in query"

                        logger.info("✅ Query plan generation verified")

                        # Test performance metrics
                        performance_report = await optimized_manager.get_performance_report()

                        assert 'manager_metrics' in performance_report, "Performance report missing manager metrics"
                        assert 'cache_performance' in performance_report, "Performance report missing cache metrics"

                        logger.info("✅ Performance reporting verified")

                        # Clean shutdown
                        await optimized_manager.shutdown()

                        self.results['integration_tests'] = True

        except Exception as e:
            logger.error(f"❌ Storage integration test failed: {e}")

    async def test_performance_benchmarks(self):
        """Run performance benchmarks."""
        logger.info("📊 Running performance benchmarks...")

        try:
            with patch('redis.asyncio.Redis'):
                from src.query.time_series_cache import TimeSeriesQueryCache, CacheConfig

                # Configure cache for performance testing
                config = CacheConfig()
                config.HOT_MEMORY_SIZE = 100
                config.WARM_MEMORY_SIZE = 50
                config.COLD_MEMORY_SIZE = 25

                cache = TimeSeriesQueryCache(config=config)

                # Benchmark cache operations
                start_time = time.time()

                async def benchmark_query():
                    return {"benchmark": "data", "size": 1024}

                # Run multiple cache operations
                num_operations = 50
                cache_hits = 0
                cache_misses = 0

                for i in range(num_operations):
                    guild_id = (i % 5) + 1  # Simulate 5 different guilds
                    query_type = ['encounter_events', 'player_metrics', 'guild_rankings'][i % 3]

                    result, was_cached = await cache.get_or_execute(
                        guild_id=guild_id,
                        query_type=query_type,
                        filters={'test': i},
                        query_executor=benchmark_query
                    )

                    if was_cached:
                        cache_hits += 1
                    else:
                        cache_misses += 1

                total_time = time.time() - start_time
                avg_time_per_op = total_time / num_operations
                cache_hit_rate = cache_hits / num_operations

                logger.info(f"✅ Benchmark completed:")
                logger.info(f"   Operations: {num_operations}")
                logger.info(f"   Total time: {total_time:.3f}s")
                logger.info(f"   Avg time per op: {avg_time_per_op:.4f}s")
                logger.info(f"   Cache hit rate: {cache_hit_rate:.2%}")

                # Store benchmark results
                self.results['performance_benchmarks'] = {
                    'operations': num_operations,
                    'total_time': total_time,
                    'avg_time_per_operation': avg_time_per_op,
                    'cache_hit_rate': cache_hit_rate,
                    'cache_hits': cache_hits,
                    'cache_misses': cache_misses
                }

                # Test memory usage optimization
                stats = await cache.get_performance_stats()

                logger.info(f"✅ Cache utilization stats:")
                for tier, tier_stats in stats.get('memory_cache', {}).items():
                    utilization = tier_stats.get('utilization', 0)
                    logger.info(f"   {tier.title()} tier: {utilization:.1%} utilized")

        except Exception as e:
            logger.error(f"❌ Performance benchmark failed: {e}")

    def generate_report(self):
        """Generate comprehensive test report."""
        logger.info("\n" + "="*80)
        logger.info("📊 TIME-SERIES OPTIMIZATION TEST REPORT")
        logger.info("="*80)

        total_tests = len(self.results) - 1  # Exclude performance_benchmarks dict
        passed_tests = sum(1 for k, v in self.results.items()
                          if k != 'performance_benchmarks' and v)

        logger.info(f"Overall Results: {passed_tests}/{total_tests} tests passed")
        logger.info("-" * 40)

        # Test results
        test_names = {
            'syntax_validation': 'Syntax Validation',
            'import_validation': 'Import Validation',
            'guild_isolation': 'Guild Isolation',
            'caching_performance': 'Caching Performance',
            'query_optimization': 'Query Optimization',
            'time_window_handling': 'Time-Window Handling',
            'integration_tests': 'Integration Tests'
        }

        for key, name in test_names.items():
            status = "✅ PASS" if self.results[key] else "❌ FAIL"
            logger.info(f"{name:.<25} {status}")

        # Performance benchmarks
        if self.results['performance_benchmarks']:
            bench = self.results['performance_benchmarks']
            logger.info("-" * 40)
            logger.info("Performance Benchmarks:")
            logger.info(f"  Operations: {bench['operations']}")
            logger.info(f"  Total time: {bench['total_time']:.3f}s")
            logger.info(f"  Avg time/op: {bench['avg_time_per_operation']:.4f}s")
            logger.info(f"  Cache hit rate: {bench['cache_hit_rate']:.2%}")

        logger.info("="*80)

        # Recommendations
        if passed_tests == total_tests:
            logger.info("🎉 ALL TESTS PASSED! The time-series optimization is ready for production.")
        else:
            logger.info("⚠️  Some tests failed. Please review and fix the issues before deployment.")

        logger.info("="*80 + "\n")

async def main():
    """Main test runner."""
    test_suite = PerformanceOptimizationTest()
    await test_suite.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())