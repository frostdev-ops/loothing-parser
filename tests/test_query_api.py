"""
Tests for the Query API functionality.

Tests database queries, caching, performance metrics,
and data retrieval operations.
"""

import pytest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.schema import DatabaseManager, create_tables
from src.database.query import QueryAPI, CharacterMetrics, EncounterSummary, SpellUsage
from src.database.storage import EventStorage
from src.segmentation.enhanced import EnhancedSegmenter
from src.parser.parser import CombatLogParser
from src.models.encounter_models import RaidEncounter, Character, Difficulty


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = DatabaseManager(db_path)
    create_tables(db)
    yield db
    db.close()

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def query_api(test_db):
    """Create a QueryAPI instance with test data."""
    api = QueryAPI(test_db)

    # Add some test data
    _add_test_data(test_db, api)

    yield api
    api.close()


def _add_test_data(db: DatabaseManager, api: QueryAPI):
    """Add test data to the database."""

    # Add test characters
    characters_data = [
        ("Player-1234-567890AB", "Testplayer", "TestRealm", "Death Knight", "Unholy"),
        ("Player-5678-CDEF1234", "Healer", "TestRealm", "Priest", "Holy"),
        ("Player-9876-ABCD5678", "Tank", "TestRealm", "Warrior", "Protection"),
    ]

    for char_data in characters_data:
        db.execute(
            """
            INSERT OR IGNORE INTO characters
            (character_guid, character_name, realm, class_name, spec_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (*char_data, datetime.now(), datetime.now())
        )

    # Add test encounters
    encounters_data = [
        ("raid", "Ulgrax the Devourer", "HEROIC", 1, time.time() - 3600, time.time() - 3400, True, 200.0, 20),
        ("raid", "The Bloodbound Horror", "MYTHIC", 2, time.time() - 7200, time.time() - 6900, False, 300.0, 20),
        ("mythic_plus", "Ara-Kara, City of Echoes", "+15", 3, time.time() - 1800, time.time() - 600, True, 1200.0, 5),
    ]

    for enc_data in encounters_data:
        db.execute(
            """
            INSERT INTO encounters
            (encounter_type, boss_name, difficulty, instance_id, start_time, end_time,
             success, combat_length, raid_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*enc_data, datetime.now())
        )

    # Add character metrics
    db.execute("SELECT character_id FROM characters WHERE character_name = 'Testplayer'")
    testplayer_id = db.execute("SELECT character_id FROM characters WHERE character_name = 'Testplayer'").fetchone()[0]

    db.execute("SELECT character_id FROM characters WHERE character_name = 'Healer'")
    healer_id = db.execute("SELECT character_id FROM characters WHERE character_name = 'Healer'").fetchone()[0]

    metrics_data = [
        (1, testplayer_id, 1500000, 0, 200000, 0, 0, 0, 95.0, 200.0, 7500.0, 0.0, 1000.0, 150),
        (1, healer_id, 500000, 800000, 150000, 900000, 100000, 1, 98.0, 200.0, 2500.0, 4000.0, 1000.0, 200),
        (2, testplayer_id, 1200000, 0, 250000, 0, 0, 2, 90.0, 150.0, 8000.0, 0.0, 850.0, 120),
    ]

    for metric_data in metrics_data:
        db.execute(
            """
            INSERT INTO character_metrics
            (encounter_id, character_id, damage_done, healing_done, damage_taken,
             healing_received, overhealing, death_count, activity_percentage,
             time_alive, dps, hps, dtps, total_events)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            metric_data
        )

    # Add spell usage data
    spell_data = [
        (1, testplayer_id, 1234, "Death Grip", 15, 14, 3, 45000, 0, 5000, 0),
        (1, testplayer_id, 5678, "Army of the Dead", 2, 2, 1, 150000, 0, 80000, 0),
        (1, healer_id, 9999, "Greater Heal", 25, 24, 8, 0, 600000, 0, 30000),
    ]

    for spell in spell_data:
        db.execute(
            """
            INSERT INTO spell_summary
            (encounter_id, character_id, spell_id, spell_name, cast_count,
             hit_count, crit_count, total_damage, total_healing, max_damage, max_healing)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            spell
        )

    db.commit()


class TestQueryAPI:
    """Test the QueryAPI class functionality."""

    def test_get_encounter(self, query_api):
        """Test getting a specific encounter."""
        encounter = query_api.get_encounter(1)
        assert encounter is not None
        assert encounter.boss_name == "Ulgrax the Devourer"
        assert encounter.difficulty == "HEROIC"
        assert encounter.success is True
        assert encounter.encounter_type == "raid"

    def test_get_nonexistent_encounter(self, query_api):
        """Test getting a nonexistent encounter."""
        encounter = query_api.get_encounter(999)
        assert encounter is None

    def test_get_recent_encounters(self, query_api):
        """Test getting recent encounters."""
        encounters = query_api.get_recent_encounters(limit=10)
        assert len(encounters) >= 3  # We added 3 test encounters

        # Should be ordered by creation time (most recent first)
        assert encounters[0].boss_name in ["Ulgrax the Devourer", "The Bloodbound Horror", "Ara-Kara, City of Echoes"]

    def test_search_encounters_by_boss(self, query_api):
        """Test searching encounters by boss name."""
        encounters = query_api.search_encounters(boss_name="Ulgrax")
        assert len(encounters) >= 1
        assert all("Ulgrax" in enc.boss_name for enc in encounters)

    def test_search_encounters_by_difficulty(self, query_api):
        """Test searching encounters by difficulty."""
        encounters = query_api.search_encounters(difficulty="HEROIC")
        assert len(encounters) >= 1
        assert all(enc.difficulty == "HEROIC" for enc in encounters)

    def test_search_encounters_by_type(self, query_api):
        """Test searching encounters by type."""
        raid_encounters = query_api.search_encounters(encounter_type="raid")
        mplus_encounters = query_api.search_encounters(encounter_type="mythic_plus")

        assert len(raid_encounters) >= 2
        assert len(mplus_encounters) >= 1

        assert all(enc.encounter_type == "raid" for enc in raid_encounters)
        assert all(enc.encounter_type == "mythic_plus" for enc in mplus_encounters)

    def test_search_encounters_by_success(self, query_api):
        """Test searching encounters by success status."""
        successful = query_api.search_encounters(success=True)
        failed = query_api.search_encounters(success=False)

        assert len(successful) >= 2  # Should have at least 2 successful encounters
        assert len(failed) >= 1     # Should have at least 1 failed encounter

        assert all(enc.success is True for enc in successful)
        assert all(enc.success is False for enc in failed)

    def test_get_character_metrics(self, query_api):
        """Test getting character metrics for an encounter."""
        metrics = query_api.get_character_metrics(1)  # First encounter
        assert len(metrics) >= 2  # Should have metrics for multiple characters

        # Find Testplayer's metrics
        testplayer_metrics = [m for m in metrics if m.character_name == "Testplayer"]
        assert len(testplayer_metrics) == 1

        metric = testplayer_metrics[0]
        assert metric.damage_done == 1500000
        assert metric.dps == 7500.0
        assert metric.death_count == 0

    def test_get_character_metrics_filtered(self, query_api):
        """Test getting character metrics filtered by character name."""
        metrics = query_api.get_character_metrics(1, character_name="Testplayer")
        assert len(metrics) == 1
        assert metrics[0].character_name == "Testplayer"

    def test_get_top_performers_dps(self, query_api):
        """Test getting top DPS performers."""
        performers = query_api.get_top_performers(metric="dps", limit=3)
        assert len(performers) >= 2

        # Should be ordered by DPS descending
        if len(performers) > 1:
            assert performers[0].dps >= performers[1].dps

    def test_get_top_performers_hps(self, query_api):
        """Test getting top HPS performers."""
        performers = query_api.get_top_performers(metric="hps", limit=3)
        assert len(performers) >= 1

        # Find the healer
        healer_performers = [p for p in performers if p.character_name == "Healer"]
        assert len(healer_performers) >= 1
        assert healer_performers[0].hps > 0

    def test_get_top_performers_filtered(self, query_api):
        """Test getting top performers with filters."""
        # Filter by encounter type
        raid_performers = query_api.get_top_performers(
            metric="dps", encounter_type="raid", limit=5
        )
        assert len(raid_performers) >= 1

        # Filter by boss name
        ulgrax_performers = query_api.get_top_performers(
            metric="dps", boss_name="Ulgrax", limit=5
        )
        assert len(ulgrax_performers) >= 1

    def test_get_spell_usage(self, query_api):
        """Test getting spell usage statistics."""
        spells = query_api.get_spell_usage("Testplayer", encounter_id=1)
        assert len(spells) >= 2  # Should have multiple spells

        # Find Death Grip
        death_grip = [s for s in spells if s.spell_name == "Death Grip"]
        assert len(death_grip) == 1

        spell = death_grip[0]
        assert spell.cast_count == 15
        assert spell.hit_count == 14
        assert spell.crit_count == 3
        assert spell.total_damage == 45000

    def test_get_spell_usage_filtered(self, query_api):
        """Test getting spell usage with filters."""
        # Filter by spell name
        spells = query_api.get_spell_usage("Testplayer", spell_name="Death Grip")
        assert len(spells) >= 1
        assert all("Death Grip" in s.spell_name for s in spells)

    def test_get_database_stats(self, query_api):
        """Test getting database statistics."""
        stats = query_api.get_database_stats()

        assert "database" in stats
        assert "query_api" in stats
        assert "cache" in stats

        db_stats = stats["database"]
        assert db_stats["total_encounters"] >= 3
        assert db_stats["total_characters"] >= 3

        # Check query API stats
        api_stats = stats["query_api"]
        assert "queries_executed" in api_stats
        assert "cache_hits" in api_stats
        assert "cache_misses" in api_stats

    def test_invalid_metric_raises_error(self, query_api):
        """Test that invalid metrics raise ValueError."""
        with pytest.raises(ValueError, match="Invalid metric"):
            query_api.get_top_performers(metric="invalid_metric")


class TestQueryCaching:
    """Test query result caching functionality."""

    def test_cache_hit_and_miss(self, query_api):
        """Test cache hit and miss behavior."""
        # Clear cache to start fresh
        query_api.clear_cache()

        # First call should be a cache miss
        initial_misses = query_api.stats["cache_misses"]
        encounter = query_api.get_encounter(1)
        assert query_api.stats["cache_misses"] == initial_misses + 1

        # Second call should be a cache hit
        initial_hits = query_api.stats["cache_hits"]
        encounter2 = query_api.get_encounter(1)
        assert query_api.stats["cache_hits"] == initial_hits + 1

        # Results should be identical
        assert encounter.encounter_id == encounter2.encounter_id
        assert encounter.boss_name == encounter2.boss_name

    def test_cache_clear(self, query_api):
        """Test cache clearing functionality."""
        # Populate cache
        query_api.get_encounter(1)
        query_api.get_recent_encounters()

        # Clear cache
        query_api.clear_cache()

        # Next call should be a cache miss
        initial_misses = query_api.stats["cache_misses"]
        query_api.get_encounter(1)
        assert query_api.stats["cache_misses"] == initial_misses + 1

    def test_cache_stats(self, query_api):
        """Test cache statistics."""
        cache_stats = query_api.cache.stats()
        assert "size" in cache_stats
        assert "max_size" in cache_stats
        assert "ttl_seconds" in cache_stats


class TestQueryPerformance:
    """Test query performance and optimization."""

    def test_query_timing(self, query_api):
        """Test that query timing is tracked."""
        initial_time = query_api.stats["total_query_time"]

        # Execute a query
        query_api.get_encounter(1)

        # Should have added some time
        assert query_api.stats["total_query_time"] > initial_time

    def test_batch_queries_performance(self, query_api):
        """Test performance of multiple queries."""
        start_time = time.time()

        # Execute multiple queries
        for i in range(1, 4):
            query_api.get_encounter(i)
            query_api.get_character_metrics(i)

        elapsed = time.time() - start_time

        # Should complete reasonably quickly (adjust threshold as needed)
        assert elapsed < 1.0  # Should complete in under 1 second

    def test_large_result_set_handling(self, query_api):
        """Test handling of large result sets."""
        # This test might not have large data, but tests the mechanism
        encounters = query_api.search_encounters(limit=200)

        # Should handle large limits without error
        assert isinstance(encounters, list)
        # Actual length depends on test data, but should not error


class TestQueryAPIEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_results(self, query_api):
        """Test queries that return empty results."""
        # Search for non-existent boss
        encounters = query_api.search_encounters(boss_name="NonexistentBoss")
        assert encounters == []

        # Get metrics for non-existent encounter
        metrics = query_api.get_character_metrics(999)
        assert metrics == []

        # Get spells for non-existent character
        spells = query_api.get_spell_usage("NonexistentPlayer")
        assert spells == []

    def test_date_range_filters(self, query_api):
        """Test date range filtering in searches."""
        # Test with future date range (should return nothing)
        future_date = datetime.now() + timedelta(days=1)
        encounters = query_api.search_encounters(
            start_date=future_date,
            end_date=future_date + timedelta(days=1)
        )
        assert encounters == []

        # Test with past date range
        past_date = datetime.now() - timedelta(days=365)
        encounters = query_api.search_encounters(
            start_date=past_date,
            end_date=datetime.now()
        )
        assert len(encounters) >= 0  # Should not error

    def test_limit_validation(self, query_api):
        """Test query limit validation."""
        # Very small limit
        encounters = query_api.get_recent_encounters(limit=1)
        assert len(encounters) <= 1

        # Zero limit should work
        encounters = query_api.search_encounters(limit=0)
        assert encounters == []


class TestQueryAPIClose:
    """Test proper cleanup of QueryAPI resources."""

    def test_query_api_close(self, test_db):
        """Test that QueryAPI closes properly."""
        api = QueryAPI(test_db)

        # Use the API
        api.get_database_stats()

        # Close should not raise an error
        api.close()

        # Multiple closes should not raise an error
        api.close()


if __name__ == "__main__":
    pytest.main([__file__])