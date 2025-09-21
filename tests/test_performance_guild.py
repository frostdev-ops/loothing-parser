"""
Performance benchmarks for guild multi-tenancy system.

This module tests the performance characteristics of guild-based queries,
indexing effectiveness, and multi-tenant data isolation performance.
"""

import pytest
import sqlite3
import tempfile
import os
import time
import random
import threading
from typing import Generator, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.database.schema import DatabaseSchema
from src.database.query import QueryManager


class TestGuildPerformance:
    """Performance benchmarks for guild multi-tenancy system."""

    @pytest.fixture
    def performance_db(self) -> Generator[str, None, None]:
        """Create a database with large dataset for performance testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
            db_path = f.name

        # Initialize schema
        schema = DatabaseSchema(db_path)

        # Create test data
        conn = sqlite3.connect(db_path)

        # Create multiple guilds
        guilds_data = [
            (1, "Performance Guild Alpha", "Stormrage", "US", "Alliance"),
            (2, "Performance Guild Beta", "Tichondrius", "US", "Horde"),
            (3, "Performance Guild Gamma", "Mal'Ganis", "US", "Horde"),
            (4, "Performance Guild Delta", "Area-52", "US", "Horde"),
            (5, "Performance Guild Epsilon", "Illidan", "US", "Horde"),
        ]

        for guild_data in guilds_data:
            conn.execute("""
                INSERT OR REPLACE INTO guilds (guild_id, guild_name, server, region, faction)
                VALUES (?, ?, ?, ?, ?)
            """, guild_data)

        # Create large dataset of encounters (1000 per guild)
        encounters_data = []
        for guild_id in range(1, 6):
            for i in range(1000):
                encounters_data.append((
                    guild_id,
                    f"Test Instance {i % 10}",
                    f"Boss {i % 20}",
                    random.choice(['Normal', 'Heroic', 'Mythic']),
                    f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d} {random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00",
                    f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d} {random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00",
                    random.randint(60, 1800),
                    random.choice([True, False]),
                    random.randint(0, 10)
                ))

        conn.executemany("""
            INSERT INTO encounters (guild_id, instance_name, encounter_name, difficulty, start_time, end_time, duration_seconds, success, wipe_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, encounters_data)

        # Create characters for each encounter (5 per encounter avg)
        characters_data = []
        character_id = 1
        for guild_id in range(1, 6):
            for encounter_id in range((guild_id - 1) * 1000 + 1, guild_id * 1000 + 1):
                for i in range(random.randint(3, 8)):  # 3-8 characters per encounter
                    characters_data.append((
                        guild_id,
                        encounter_id,
                        f"Player{character_id}",
                        random.choice(['Warrior', 'Mage', 'Hunter', 'Priest', 'Rogue']),
                        random.choice(['Tank', 'Healer', 'DPS']),
                        80,
                        random.randint(600, 700),
                        random.choice(['Stormrage', 'Tichondrius', 'Mal\'Ganis'])
                    ))
                    character_id += 1

        conn.executemany("""
            INSERT INTO characters (guild_id, encounter_id, character_name, character_class, specialization, level, item_level, realm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, characters_data)

        # Create character events (10 per character avg)
        events_data = []
        for character_id in range(1, len(characters_data) + 1):
            guild_id = ((character_id - 1) // 5000) + 1  # Approximate guild assignment
            for i in range(random.randint(5, 15)):  # 5-15 events per character
                events_data.append((
                    guild_id,
                    character_id,
                    random.choice(['SPELL_DAMAGE', 'SPELL_HEAL', 'SPELL_CAST_SUCCESS']),
                    f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d} {random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00",
                    f'{{"damage": {random.randint(10000, 100000)}}}'
                ))

        conn.executemany("""
            INSERT INTO character_events (guild_id, character_id, event_type, timestamp, event_data)
            VALUES (?, ?, ?, ?, ?)
        """, events_data)

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)

    def benchmark_query_time(self, func, *args, **kwargs) -> float:
        """Benchmark a function and return execution time in milliseconds."""
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        return (end_time - start_time) * 1000  # Convert to milliseconds

    def test_guild_filtered_vs_unfiltered_queries(self, performance_db: str):
        """Test performance difference between guild-filtered and unfiltered queries."""
        query_manager = QueryManager(performance_db)

        # Test encounter queries
        # Guild-filtered query
        guild_filtered_time = self.benchmark_query_time(
            lambda: query_manager.get_encounters(guild_id=1, limit=100)
        )

        # Unfiltered query (should be slower due to larger dataset)
        unfiltered_time = self.benchmark_query_time(
            lambda: query_manager.get_encounters(limit=100)
        )

        print(f"Guild-filtered encounter query: {guild_filtered_time:.2f}ms")
        print(f"Unfiltered encounter query: {unfiltered_time:.2f}ms")

        # Guild filtering should be reasonably fast
        assert guild_filtered_time < 100, f"Guild-filtered queries should be fast (<100ms), got {guild_filtered_time:.2f}ms"

        # Test character queries
        guild_character_time = self.benchmark_query_time(
            lambda: query_manager.get_characters_for_encounter(1, guild_id=1)
        )

        unfiltered_character_time = self.benchmark_query_time(
            lambda: query_manager.get_characters_for_encounter(1)
        )

        print(f"Guild-filtered character query: {guild_character_time:.2f}ms")
        print(f"Unfiltered character query: {unfiltered_character_time:.2f}ms")

        assert guild_character_time < 50, f"Guild-filtered character queries should be fast (<50ms), got {guild_character_time:.2f}ms"

    def test_index_effectiveness(self, performance_db: str):
        """Test that guild indexes are effective for query performance."""
        conn = sqlite3.connect(performance_db)

        # Test encounter lookup with guild index
        start_time = time.perf_counter()
        cursor = conn.execute("""
            SELECT * FROM encounters
            WHERE guild_id = 1 AND difficulty = 'Mythic'
            ORDER BY start_time DESC
            LIMIT 50
        """)
        results = cursor.fetchall()
        indexed_time = (time.perf_counter() - start_time) * 1000

        print(f"Indexed guild query: {indexed_time:.2f}ms ({len(results)} results)")

        # Test query explain plan to verify index usage
        cursor = conn.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM encounters
            WHERE guild_id = 1 AND difficulty = 'Mythic'
            ORDER BY start_time DESC
            LIMIT 50
        """)
        query_plan = cursor.fetchall()
        print(f"Query plan: {query_plan}")

        # Verify index is being used (should mention idx_guild_encounters_lookup)
        plan_text = ' '.join([str(row) for row in query_plan])
        assert 'idx_guild_encounters_lookup' in plan_text or 'USING INDEX' in plan_text.upper(), "Guild index should be used in query plan"

        # Index-based queries should be fast
        assert indexed_time < 50, f"Indexed queries should be fast (<50ms), got {indexed_time:.2f}ms"

        conn.close()

    def test_concurrent_guild_access(self, performance_db: str):
        """Test performance under concurrent access from multiple guilds."""
        def guild_worker(guild_id: int, query_count: int) -> List[float]:
            """Worker function for concurrent testing."""
            query_manager = QueryManager(performance_db)
            times = []

            for _ in range(query_count):
                start_time = time.perf_counter()
                encounters = query_manager.get_encounters(guild_id=guild_id, limit=20)
                end_time = time.perf_counter()
                times.append((end_time - start_time) * 1000)

            return times

        # Test concurrent access with multiple threads
        num_threads = 5
        queries_per_thread = 20

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            # Submit tasks for different guilds
            futures = []
            for guild_id in range(1, num_threads + 1):
                future = executor.submit(guild_worker, guild_id, queries_per_thread)
                futures.append((guild_id, future))

            # Collect results
            all_times = []
            for guild_id, future in futures:
                try:
                    times = future.result(timeout=30)
                    all_times.extend(times)
                    avg_time = sum(times) / len(times)
                    print(f"Guild {guild_id} average query time: {avg_time:.2f}ms")
                except Exception as e:
                    pytest.fail(f"Concurrent access failed for guild {guild_id}: {e}")

        # Verify performance under concurrent load
        overall_avg = sum(all_times) / len(all_times)
        max_time = max(all_times)

        print(f"Overall average query time: {overall_avg:.2f}ms")
        print(f"Maximum query time: {max_time:.2f}ms")

        assert overall_avg < 100, f"Average concurrent query time should be reasonable (<100ms), got {overall_avg:.2f}ms"
        assert max_time < 500, f"No single query should be extremely slow (<500ms), got {max_time:.2f}ms"

    def test_bulk_operations_performance(self, performance_db: str):
        """Test performance of bulk operations with guild isolation."""
        conn = sqlite3.connect(performance_db)

        # Test bulk insert with guild context
        bulk_data = []
        for i in range(1000):
            bulk_data.append((
                1,  # guild_id
                f"Bulk Instance {i}",
                f"Bulk Boss {i}",
                'Normal',
                '2024-09-21 12:00:00',
                '2024-09-21 12:05:00',
                300,
                True,
                0
            ))

        start_time = time.perf_counter()
        conn.executemany("""
            INSERT INTO encounters (guild_id, instance_name, encounter_name, difficulty, start_time, end_time, duration_seconds, success, wipe_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, bulk_data)
        conn.commit()
        bulk_insert_time = (time.perf_counter() - start_time) * 1000

        print(f"Bulk insert (1000 records): {bulk_insert_time:.2f}ms")

        # Test bulk update with guild filtering
        start_time = time.perf_counter()
        conn.execute("""
            UPDATE encounters
            SET success = 0
            WHERE guild_id = 1 AND instance_name LIKE 'Bulk Instance%'
        """)
        conn.commit()
        bulk_update_time = (time.perf_counter() - start_time) * 1000

        print(f"Bulk update with guild filter: {bulk_update_time:.2f}ms")

        # Test bulk delete with guild filtering
        start_time = time.perf_counter()
        conn.execute("""
            DELETE FROM encounters
            WHERE guild_id = 1 AND instance_name LIKE 'Bulk Instance%'
        """)
        conn.commit()
        bulk_delete_time = (time.perf_counter() - start_time) * 1000

        print(f"Bulk delete with guild filter: {bulk_delete_time:.2f}ms")

        # Bulk operations should be reasonably fast
        assert bulk_insert_time < 2000, f"Bulk insert should be fast (<2s), got {bulk_insert_time:.2f}ms"
        assert bulk_update_time < 500, f"Bulk update should be fast (<500ms), got {bulk_update_time:.2f}ms"
        assert bulk_delete_time < 500, f"Bulk delete should be fast (<500ms), got {bulk_delete_time:.2f}ms"

        conn.close()

    def test_complex_join_performance(self, performance_db: str):
        """Test performance of complex joins with guild filtering."""
        conn = sqlite3.connect(performance_db)

        # Complex query joining multiple tables with guild filtering
        complex_query = """
            SELECT
                e.encounter_name,
                e.difficulty,
                COUNT(c.character_id) as character_count,
                COUNT(ce.event_id) as event_count,
                AVG(c.item_level) as avg_item_level
            FROM encounters e
            LEFT JOIN characters c ON e.encounter_id = c.encounter_id AND e.guild_id = c.guild_id
            LEFT JOIN character_events ce ON c.character_id = ce.character_id AND c.guild_id = ce.guild_id
            WHERE e.guild_id = 1
            GROUP BY e.encounter_id, e.encounter_name, e.difficulty
            HAVING character_count > 0
            ORDER BY event_count DESC
            LIMIT 50
        """

        start_time = time.perf_counter()
        cursor = conn.execute(complex_query)
        results = cursor.fetchall()
        complex_join_time = (time.perf_counter() - start_time) * 1000

        print(f"Complex join query: {complex_join_time:.2f}ms ({len(results)} results)")

        # Complex joins should still be reasonable with proper indexing
        assert complex_join_time < 1000, f"Complex joins should be reasonable (<1s), got {complex_join_time:.2f}ms"
        assert len(results) > 0, "Complex join should return results"

        # Test query plan for complex join
        cursor = conn.execute(f"EXPLAIN QUERY PLAN {complex_query}")
        plan = cursor.fetchall()
        print(f"Complex join query plan: {plan}")

        conn.close()

    def test_memory_usage_guild_isolation(self, performance_db: str):
        """Test memory efficiency of guild-isolated queries."""
        import psutil
        import os

        process = psutil.Process(os.getpid())

        # Baseline memory usage
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        query_manager = QueryManager(performance_db)

        # Perform multiple guild-isolated queries
        for guild_id in range(1, 6):
            encounters = query_manager.get_encounters(guild_id=guild_id, limit=500)
            for encounter in encounters[:10]:  # Process first 10
                characters = query_manager.get_characters_for_encounter(
                    encounter.encounter_id, guild_id=guild_id
                )

        # Check memory usage after operations
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - baseline_memory

        print(f"Baseline memory: {baseline_memory:.2f}MB")
        print(f"Final memory: {final_memory:.2f}MB")
        print(f"Memory increase: {memory_increase:.2f}MB")

        # Memory increase should be reasonable
        assert memory_increase < 100, f"Memory increase should be reasonable (<100MB), got {memory_increase:.2f}MB"

    def test_cache_effectiveness_guild_context(self, performance_db: str):
        """Test that caching works effectively with guild context."""
        query_manager = QueryManager(performance_db)

        # First query (cold cache)
        first_time = self.benchmark_query_time(
            lambda: query_manager.get_encounter(1, guild_id=1)
        )

        # Second query (warm cache) - should be significantly faster
        second_time = self.benchmark_query_time(
            lambda: query_manager.get_encounter(1, guild_id=1)
        )

        # Third query with different guild (should not use cache)
        third_time = self.benchmark_query_time(
            lambda: query_manager.get_encounter(1, guild_id=2)
        )

        print(f"First query (cold cache): {first_time:.2f}ms")
        print(f"Second query (warm cache): {second_time:.2f}ms")
        print(f"Third query (different guild): {third_time:.2f}ms")

        # Cache should provide significant speedup
        if first_time > 1:  # Only test if first query takes measurable time
            cache_speedup = first_time / second_time
            assert cache_speedup > 1.5, f"Cache should provide speedup (>1.5x), got {cache_speedup:.2f}x"

        # Different guild should not benefit from cache
        assert abs(third_time - first_time) < first_time * 0.5, "Different guild queries should have similar performance"

    def test_database_size_impact(self, performance_db: str):
        """Test how database size affects guild query performance."""
        import os

        # Get database file size
        db_size = os.path.getsize(performance_db) / 1024 / 1024  # MB
        print(f"Database size: {db_size:.2f}MB")

        conn = sqlite3.connect(performance_db)

        # Test table sizes
        for table in ['encounters', 'characters', 'character_events', 'combat_periods']:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"{table}: {count:,} records")

        # Test query performance with large dataset
        query_manager = QueryManager(performance_db)

        # Test various query patterns
        queries = [
            ("Recent encounters", lambda: query_manager.get_encounters(guild_id=1, limit=50)),
            ("Specific encounter", lambda: query_manager.get_encounter(1, guild_id=1)),
            ("Characters for encounter", lambda: query_manager.get_characters_for_encounter(1, guild_id=1)),
        ]

        for query_name, query_func in queries:
            query_time = self.benchmark_query_time(query_func)
            print(f"{query_name}: {query_time:.2f}ms")

            # Even with large dataset, guild queries should remain fast
            assert query_time < 200, f"{query_name} should be fast even with large dataset (<200ms), got {query_time:.2f}ms"

        conn.close()

    def test_scalability_stress_test(self, performance_db: str):
        """Stress test to verify system can handle high load."""
        def stress_worker(worker_id: int, iterations: int) -> Tuple[int, List[float]]:
            """Worker for stress testing."""
            query_manager = QueryManager(performance_db)
            times = []
            errors = 0

            for i in range(iterations):
                try:
                    # Vary the guild ID and query type
                    guild_id = (worker_id % 5) + 1

                    if i % 3 == 0:
                        start_time = time.perf_counter()
                        query_manager.get_encounters(guild_id=guild_id, limit=10)
                        times.append((time.perf_counter() - start_time) * 1000)
                    elif i % 3 == 1:
                        start_time = time.perf_counter()
                        query_manager.get_encounter(((worker_id * iterations + i) % 1000) + 1, guild_id=guild_id)
                        times.append((time.perf_counter() - start_time) * 1000)
                    else:
                        start_time = time.perf_counter()
                        query_manager.get_characters_for_encounter(((worker_id * iterations + i) % 1000) + 1, guild_id=guild_id)
                        times.append((time.perf_counter() - start_time) * 1000)

                except Exception as e:
                    errors += 1
                    print(f"Worker {worker_id} error at iteration {i}: {e}")

            return errors, times

        # Run stress test with multiple workers
        num_workers = 10
        iterations_per_worker = 50

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for worker_id in range(num_workers):
                future = executor.submit(stress_worker, worker_id, iterations_per_worker)
                futures.append(future)

            total_errors = 0
            all_times = []

            for future in as_completed(futures, timeout=60):
                try:
                    errors, times = future.result()
                    total_errors += errors
                    all_times.extend(times)
                except Exception as e:
                    pytest.fail(f"Stress test worker failed: {e}")

        # Analyze results
        if all_times:
            avg_time = sum(all_times) / len(all_times)
            max_time = max(all_times)
            min_time = min(all_times)

            print(f"Stress test results:")
            print(f"  Total queries: {len(all_times)}")
            print(f"  Total errors: {total_errors}")
            print(f"  Average time: {avg_time:.2f}ms")
            print(f"  Min time: {min_time:.2f}ms")
            print(f"  Max time: {max_time:.2f}ms")

            # Verify system handles stress well
            error_rate = total_errors / (num_workers * iterations_per_worker)
            assert error_rate < 0.01, f"Error rate should be low (<1%), got {error_rate:.2%}"
            assert avg_time < 150, f"Average response time under stress should be reasonable (<150ms), got {avg_time:.2f}ms"
            assert max_time < 1000, f"Maximum response time should be acceptable (<1s), got {max_time:.2f}ms"