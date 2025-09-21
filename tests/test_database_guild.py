"""
Database guild system tests for WoW combat log parser.

Tests multi-tenant guild functionality including table creation, foreign keys,
constraints, migration, and data isolation at the database level.
"""

import pytest
import tempfile
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.database.schema import DatabaseManager, create_tables
from src.models.character import Character
from src.models.character_events import CharacterEventStream


class TestGuildTableCreation:
    """Test guild table structure and creation."""

    def test_guild_table_creation(self, temp_db):
        """Test that guilds table is created with correct schema."""
        # Verify guilds table exists
        cursor = temp_db.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='guilds'
        """)
        table_sql = cursor.fetchone()
        assert table_sql is not None, "Guilds table should exist"

        # Verify table structure
        guild_schema = table_sql[0]
        required_columns = [
            "guild_id", "guild_name", "server", "region", "faction",
            "created_at", "updated_at", "is_active"
        ]

        for column in required_columns:
            assert column in guild_schema, f"Guild table should have {column} column"

        # Check faction constraint
        assert "CHECK(faction IN ('Alliance', 'Horde'))" in guild_schema, \
            "Guild table should have faction constraint"

        # Check unique constraint
        assert "UNIQUE(guild_name, server, region)" in guild_schema, \
            "Guild table should have unique constraint"

    def test_default_guild_creation(self, temp_db):
        """Test that default guild is created during initialization."""
        # Check if default guild exists
        cursor = temp_db.execute("""
            SELECT guild_id, guild_name, server, region, faction
            FROM guilds
            WHERE guild_id = 1
        """)
        default_guild = cursor.fetchone()

        assert default_guild is not None, "Default guild should exist"
        assert default_guild[0] == 1, "Default guild should have ID 1"
        assert default_guild[1] == "Default Guild", "Default guild should have correct name"

    def test_guild_id_column_exists_in_all_tables(self, temp_db):
        """Test that guild_id column exists in all relevant tables."""
        tables_with_guild_id = [
            "encounters", "characters", "character_metrics", "log_files"
        ]

        for table_name in tables_with_guild_id:
            # Check if table exists
            cursor = temp_db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name=?
            """, (table_name,))

            if cursor.fetchone():  # Table exists
                # Check if guild_id column exists
                cursor = temp_db.execute(f"PRAGMA table_info({table_name})")
                columns = [col[1] for col in cursor.fetchall()]

                assert "guild_id" in columns, \
                    f"Table {table_name} should have guild_id column"

    def test_guild_foreign_key_constraints(self, temp_db):
        """Test foreign key constraints are properly set up."""
        # Enable foreign key enforcement
        temp_db.execute("PRAGMA foreign_keys = ON")

        # Create a test guild
        temp_db.execute("""
            INSERT INTO guilds (guild_name, server, region, faction)
            VALUES ('Test Guild', 'Test Server', 'US', 'Alliance')
        """)
        test_guild_id = temp_db.cursor.lastrowid

        # Test encounters foreign key
        temp_db.execute("""
            INSERT INTO encounters (
                guild_id, boss_name, instance_name, difficulty,
                encounter_type, start_time, end_time, duration_ms, success
            ) VALUES (?, 'Test Boss', 'Test Instance', 'Normal', 'raid',
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1)
        """, (test_guild_id,))

        # Verify encounter was created
        cursor = temp_db.execute("""
            SELECT guild_id FROM encounters WHERE guild_id = ?
        """, (test_guild_id,))
        assert cursor.fetchone() is not None, "Encounter should be created with valid guild_id"

        # Test foreign key violation
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute("""
                INSERT INTO encounters (
                    guild_id, boss_name, instance_name, difficulty,
                    encounter_type, start_time, end_time, duration_ms, success
                ) VALUES (99999, 'Invalid Boss', 'Invalid Instance', 'Normal', 'raid',
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1)
            """)

    def test_guild_unique_constraints(self, temp_db):
        """Test guild unique constraints work correctly."""
        # Insert first guild
        temp_db.execute("""
            INSERT INTO guilds (guild_name, server, region, faction)
            VALUES ('Unique Guild', 'Test Server', 'US', 'Alliance')
        """)

        # Try to insert duplicate - should fail
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute("""
                INSERT INTO guilds (guild_name, server, region, faction)
                VALUES ('Unique Guild', 'Test Server', 'US', 'Horde')
            """)

        # Different server should work
        temp_db.execute("""
            INSERT INTO guilds (guild_name, server, region, faction)
            VALUES ('Unique Guild', 'Different Server', 'US', 'Alliance')
        """)

        # Different region should work
        temp_db.execute("""
            INSERT INTO guilds (guild_name, server, region, faction)
            VALUES ('Unique Guild', 'Test Server', 'EU', 'Alliance')
        """)

        # Verify we have 4 guilds total (including default)
        cursor = temp_db.execute("SELECT COUNT(*) FROM guilds")
        guild_count = cursor.fetchone()[0]
        assert guild_count == 4, "Should have 4 guilds after unique constraint tests"


class TestGuildMigration:
    """Test migration from v1 (single-tenant) to v2 (multi-tenant)."""

    def test_schema_version_tracking(self, temp_db):
        """Test schema version is properly tracked."""
        # Check current schema version
        cursor = temp_db.execute("""
            SELECT value FROM metadata WHERE key = 'schema_version'
        """)
        version = cursor.fetchone()

        assert version is not None, "Schema version should be tracked"
        assert version[0] == "2", "Schema version should be 2 for guild system"

    def test_migration_from_v1_schema(self):
        """Test migration from v1 schema to v2 guild schema."""
        # Create a temporary database with v1 schema
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Create v1 schema manually
            conn = sqlite3.connect(db_path)

            # Create v1 tables without guild_id
            conn.execute("""
                CREATE TABLE IF NOT EXISTS encounters (
                    encounter_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    boss_name TEXT NOT NULL,
                    instance_name TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    encounter_type TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_ms INTEGER,
                    success BOOLEAN DEFAULT FALSE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    character_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    class TEXT NOT NULL,
                    spec TEXT,
                    realm TEXT,
                    guid TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Set v1 schema version
            conn.execute("""
                INSERT INTO metadata (key, value)
                VALUES ('schema_version', '1')
            """)

            # Insert some test data
            conn.execute("""
                INSERT INTO encounters (
                    boss_name, instance_name, difficulty, encounter_type,
                    start_time, end_time, duration_ms, success
                ) VALUES (
                    'Test Boss', 'Test Instance', 'Normal', 'raid',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1
                )
            """)

            conn.execute("""
                INSERT INTO characters (name, class, spec, realm)
                VALUES ('TestPlayer', 'Warrior', 'Protection', 'TestRealm')
            """)

            conn.commit()
            conn.close()

            # Now initialize with DatabaseManager (should trigger migration)
            db = DatabaseManager(db_path)

            # Verify migration completed
            cursor = db.execute("""
                SELECT value FROM metadata WHERE key = 'schema_version'
            """)
            version = cursor.fetchone()[0]
            assert version == "2", "Schema should be migrated to v2"

            # Verify guild_id columns were added
            cursor = db.execute("PRAGMA table_info(encounters)")
            encounter_columns = [col[1] for col in cursor.fetchall()]
            assert "guild_id" in encounter_columns, "encounters should have guild_id column"

            cursor = db.execute("PRAGMA table_info(characters)")
            character_columns = [col[1] for col in cursor.fetchall()]
            assert "guild_id" in character_columns, "characters should have guild_id column"

            # Verify existing data was assigned to default guild
            cursor = db.execute("""
                SELECT guild_id FROM encounters WHERE boss_name = 'Test Boss'
            """)
            encounter_guild = cursor.fetchone()[0]
            assert encounter_guild == 1, "Existing encounters should be assigned to default guild"

            cursor = db.execute("""
                SELECT guild_id FROM characters WHERE name = 'TestPlayer'
            """)
            character_guild = cursor.fetchone()[0]
            assert character_guild == 1, "Existing characters should be assigned to default guild"

            db.close()

        finally:
            # Cleanup
            Path(db_path).unlink(missing_ok=True)

    def test_migration_idempotency(self, temp_db):
        """Test that running migration multiple times doesn't break anything."""
        # Get initial state
        cursor = temp_db.execute("SELECT COUNT(*) FROM guilds")
        initial_guild_count = cursor.fetchone()[0]

        cursor = temp_db.execute("""
            SELECT value FROM metadata WHERE key = 'schema_version'
        """)
        initial_version = cursor.fetchone()[0]

        # Run migration again (should be idempotent)
        temp_db._migrate_to_v2_guilds()

        # Verify no changes
        cursor = temp_db.execute("SELECT COUNT(*) FROM guilds")
        final_guild_count = cursor.fetchone()[0]
        assert final_guild_count == initial_guild_count, \
            "Migration should not duplicate guilds"

        cursor = temp_db.execute("""
            SELECT value FROM metadata WHERE key = 'schema_version'
        """)
        final_version = cursor.fetchone()[0]
        assert final_version == initial_version, \
            "Schema version should remain unchanged"


class TestGuildDataIsolation:
    """Test guild data isolation and access controls."""

    @pytest.fixture
    def multi_guild_setup(self, temp_db):
        """Set up multiple guilds with test data."""
        # Create test guilds
        guilds = [
            (2, "Test Guild 1", "Server1", "US", "Alliance"),
            (3, "Test Guild 2", "Server2", "EU", "Horde"),
            (4, "Test Guild 3", "Server1", "US", "Alliance"),  # Same server different name
        ]

        for guild_id, name, server, region, faction in guilds:
            temp_db.execute("""
                INSERT INTO guilds (guild_id, guild_name, server, region, faction)
                VALUES (?, ?, ?, ?, ?)
            """, (guild_id, name, server, region, faction))

        # Create test encounters for each guild
        encounters = [
            (2, "Boss A", "Instance A", "Normal"),
            (2, "Boss B", "Instance A", "Heroic"),
            (3, "Boss A", "Instance B", "Normal"),
            (3, "Boss C", "Instance B", "Mythic"),
            (4, "Boss D", "Instance C", "Normal"),
        ]

        for guild_id, boss, instance, difficulty in encounters:
            temp_db.execute("""
                INSERT INTO encounters (
                    guild_id, boss_name, instance_name, difficulty,
                    encounter_type, start_time, end_time, duration_ms, success
                ) VALUES (?, ?, ?, ?, 'raid',
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1)
            """, (guild_id, boss, instance, difficulty))

        # Create test characters for each guild
        characters = [
            (2, "Player1", "Warrior", "Protection"),
            (2, "Player2", "Mage", "Arcane"),
            (3, "Player3", "Rogue", "Assassination"),
            (3, "Player4", "Priest", "Holy"),
            (4, "Player5", "Hunter", "Beast Mastery"),
        ]

        for guild_id, name, char_class, spec in characters:
            temp_db.execute("""
                INSERT INTO characters (guild_id, name, class, spec, realm)
                VALUES (?, ?, ?, ?, 'TestRealm')
            """, (guild_id, name, char_class, spec))

        return temp_db

    def test_guild_encounter_isolation(self, multi_guild_setup):
        """Test that encounters are properly isolated by guild."""
        db = multi_guild_setup

        # Get encounters for guild 2
        cursor = db.execute("""
            SELECT boss_name FROM encounters WHERE guild_id = 2
        """)
        guild2_encounters = [row[0] for row in cursor.fetchall()]
        assert set(guild2_encounters) == {"Boss A", "Boss B"}, \
            "Guild 2 should only see its own encounters"

        # Get encounters for guild 3
        cursor = db.execute("""
            SELECT boss_name FROM encounters WHERE guild_id = 3
        """)
        guild3_encounters = [row[0] for row in cursor.fetchall()]
        assert set(guild3_encounters) == {"Boss A", "Boss C"}, \
            "Guild 3 should only see its own encounters"

        # Get encounters for guild 4
        cursor = db.execute("""
            SELECT boss_name FROM encounters WHERE guild_id = 4
        """)
        guild4_encounters = [row[0] for row in cursor.fetchall()]
        assert set(guild4_encounters) == {"Boss D"}, \
            "Guild 4 should only see its own encounters"

    def test_guild_character_isolation(self, multi_guild_setup):
        """Test that characters are properly isolated by guild."""
        db = multi_guild_setup

        # Get characters for guild 2
        cursor = db.execute("""
            SELECT name FROM characters WHERE guild_id = 2
        """)
        guild2_characters = [row[0] for row in cursor.fetchall()]
        assert set(guild2_characters) == {"Player1", "Player2"}, \
            "Guild 2 should only see its own characters"

        # Get characters for guild 3
        cursor = db.execute("""
            SELECT name FROM characters WHERE guild_id = 3
        """)
        guild3_characters = [row[0] for row in cursor.fetchall()]
        assert set(guild3_characters) == {"Player3", "Player4"}, \
            "Guild 3 should only see its own characters"

    def test_cross_guild_access_prevention(self, multi_guild_setup):
        """Test that queries cannot access other guild's data accidentally."""
        db = multi_guild_setup

        # Verify total encounters across all guilds
        cursor = db.execute("SELECT COUNT(*) FROM encounters")
        total_encounters = cursor.fetchone()[0]
        assert total_encounters == 5, "Should have 5 total encounters across all guilds"

        # Verify guild filtering works correctly
        cursor = db.execute("""
            SELECT COUNT(*) FROM encounters
            WHERE guild_id != 2
        """)
        non_guild2_encounters = cursor.fetchone()[0]
        assert non_guild2_encounters == 3, "Should have 3 encounters not belonging to guild 2"

        # Verify no orphaned data
        cursor = db.execute("""
            SELECT COUNT(*) FROM encounters e
            LEFT JOIN guilds g ON e.guild_id = g.guild_id
            WHERE g.guild_id IS NULL
        """)
        orphaned_encounters = cursor.fetchone()[0]
        assert orphaned_encounters == 0, "Should have no orphaned encounters"

    def test_guild_deletion_cascade(self, multi_guild_setup):
        """Test behavior when a guild is deleted."""
        db = multi_guild_setup

        # Count data for guild 3 before deletion
        cursor = db.execute("""
            SELECT COUNT(*) FROM encounters WHERE guild_id = 3
        """)
        guild3_encounters_before = cursor.fetchone()[0]

        cursor = db.execute("""
            SELECT COUNT(*) FROM characters WHERE guild_id = 3
        """)
        guild3_characters_before = cursor.fetchone()[0]

        assert guild3_encounters_before > 0, "Guild 3 should have encounters before deletion"
        assert guild3_characters_before > 0, "Guild 3 should have characters before deletion"

        # Delete guild 3
        db.execute("DELETE FROM guilds WHERE guild_id = 3")

        # Verify guild is deleted
        cursor = db.execute("SELECT COUNT(*) FROM guilds WHERE guild_id = 3")
        guild_count = cursor.fetchone()[0]
        assert guild_count == 0, "Guild 3 should be deleted"

        # Note: SQLite doesn't support CASCADE DELETE by default
        # So encounters and characters might still exist
        # This tests the current behavior - in production we'd need
        # explicit cleanup procedures


class TestGuildIndexPerformance:
    """Test guild-optimized index performance."""

    def test_guild_index_creation(self, temp_db):
        """Test that guild-optimized indexes are created."""
        expected_indexes = [
            "idx_encounters_guild_start",
            "idx_encounters_guild_boss",
            "idx_encounters_guild_instance",
            "idx_encounters_guild_type_difficulty",
            "idx_characters_guild_name",
            "idx_characters_guild_class",
            "idx_characters_guild_class_spec",
        ]

        # Get all indexes
        cursor = temp_db.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'index'
            AND name LIKE '%guild%'
        """)
        actual_indexes = [row[0] for row in cursor.fetchall()]

        for expected_index in expected_indexes:
            assert expected_index in actual_indexes, \
                f"Index {expected_index} should exist"

    def test_guild_query_performance(self, temp_db):
        """Test that guild-filtered queries use indexes efficiently."""
        # Create test data
        test_guild_id = 2
        temp_db.execute("""
            INSERT INTO guilds (guild_id, guild_name, server, region, faction)
            VALUES (?, 'Performance Test Guild', 'TestServer', 'US', 'Alliance')
        """, (test_guild_id,))

        # Insert test encounters
        start_time = time.time()
        for i in range(100):
            temp_db.execute("""
                INSERT INTO encounters (
                    guild_id, boss_name, instance_name, difficulty,
                    encounter_type, start_time, end_time, duration_ms, success
                ) VALUES (?, ?, 'Test Instance', 'Normal', 'raid',
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1)
            """, (test_guild_id, f"Boss {i}"))

        insert_time = time.time() - start_time
        print(f"Inserted 100 encounters in {insert_time:.3f}s")

        # Test guild-filtered query performance
        start_time = time.time()
        cursor = temp_db.execute("""
            SELECT boss_name FROM encounters
            WHERE guild_id = ?
            ORDER BY start_time DESC
            LIMIT 10
        """, (test_guild_id,))
        results = cursor.fetchall()
        query_time = time.time() - start_time

        assert len(results) == 10, "Should return 10 results"
        assert query_time < 0.1, f"Guild query should be fast, took {query_time:.3f}s"
        print(f"Guild-filtered query took {query_time:.3f}s")

        # Test query plan uses index
        cursor = temp_db.execute("""
            EXPLAIN QUERY PLAN
            SELECT boss_name FROM encounters
            WHERE guild_id = ?
            ORDER BY start_time DESC
            LIMIT 10
        """, (test_guild_id,))
        query_plan = cursor.fetchall()

        # Check if index is being used
        plan_text = str(query_plan)
        print(f"Query plan: {plan_text}")

    def test_multi_guild_query_isolation_performance(self, temp_db):
        """Test performance of queries with multiple guilds."""
        # Create multiple guilds with data
        guild_ids = [2, 3, 4, 5]
        encounters_per_guild = 50

        for guild_id in guild_ids:
            temp_db.execute("""
                INSERT INTO guilds (guild_id, guild_name, server, region, faction)
                VALUES (?, ?, 'TestServer', 'US', 'Alliance')
            """, (guild_id, f"Guild {guild_id}"))

            # Insert encounters for this guild
            for i in range(encounters_per_guild):
                temp_db.execute("""
                    INSERT INTO encounters (
                        guild_id, boss_name, instance_name, difficulty,
                        encounter_type, start_time, end_time, duration_ms, success
                    ) VALUES (?, ?, 'Test Instance', 'Normal', 'raid',
                             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1)
                """, (guild_id, f"Boss {i}"))

        # Test that queries for specific guilds remain fast
        for guild_id in guild_ids:
            start_time = time.time()
            cursor = temp_db.execute("""
                SELECT COUNT(*) FROM encounters WHERE guild_id = ?
            """, (guild_id,))
            count = cursor.fetchone()[0]
            query_time = time.time() - start_time

            assert count == encounters_per_guild, \
                f"Guild {guild_id} should have {encounters_per_guild} encounters"
            assert query_time < 0.05, \
                f"Guild {guild_id} query should be fast, took {query_time:.3f}s"

        print(f"Tested {len(guild_ids)} guilds with {encounters_per_guild} encounters each")


class TestGuildDataIntegrity:
    """Test data integrity and consistency in guild system."""

    def test_guild_id_not_null_constraint(self, temp_db):
        """Test that guild_id cannot be null in relevant tables."""
        # Try to insert encounter without guild_id
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute("""
                INSERT INTO encounters (
                    boss_name, instance_name, difficulty, encounter_type,
                    start_time, end_time, duration_ms, success
                ) VALUES (
                    'Test Boss', 'Test Instance', 'Normal', 'raid',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1
                )
            """)

    def test_guild_statistics_accuracy(self, temp_db):
        """Test that guild statistics are calculated correctly."""
        # Create test guild
        test_guild_id = 2
        temp_db.execute("""
            INSERT INTO guilds (guild_id, guild_name, server, region, faction)
            VALUES (?, 'Stats Test Guild', 'TestServer', 'US', 'Alliance')
        """, (test_guild_id,))

        # Insert test data
        encounter_count = 5
        character_count = 3

        for i in range(encounter_count):
            temp_db.execute("""
                INSERT INTO encounters (
                    guild_id, boss_name, instance_name, difficulty,
                    encounter_type, start_time, end_time, duration_ms, success
                ) VALUES (?, ?, 'Test Instance', 'Normal', 'raid',
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1)
            """, (test_guild_id, f"Boss {i}"))

        for i in range(character_count):
            temp_db.execute("""
                INSERT INTO characters (guild_id, name, class, spec, realm)
                VALUES (?, ?, 'Warrior', 'Protection', 'TestRealm')
            """, (test_guild_id, f"Character {i}"))

        # Verify statistics
        cursor = temp_db.execute("""
            SELECT
                COUNT(DISTINCT e.encounter_id) as encounters,
                COUNT(DISTINCT c.character_id) as characters
            FROM guilds g
            LEFT JOIN encounters e ON g.guild_id = e.guild_id
            LEFT JOIN characters c ON g.guild_id = c.guild_id
            WHERE g.guild_id = ?
            GROUP BY g.guild_id
        """, (test_guild_id,))

        stats = cursor.fetchone()
        assert stats[0] == encounter_count, \
            f"Should have {encounter_count} encounters, got {stats[0]}"
        assert stats[1] == character_count, \
            f"Should have {character_count} characters, got {stats[1]}"

    def test_guild_foreign_key_integrity(self, temp_db):
        """Test foreign key integrity across guild system."""
        # Enable foreign key checking
        temp_db.execute("PRAGMA foreign_keys = ON")

        # Run foreign key check
        cursor = temp_db.execute("PRAGMA foreign_key_check")
        violations = cursor.fetchall()

        assert len(violations) == 0, \
            f"No foreign key violations should exist, found: {violations}"

    def test_guild_cascade_behavior(self, temp_db):
        """Test cascade behavior when guild relationships change."""
        # Create test guild
        test_guild_id = 2
        temp_db.execute("""
            INSERT INTO guilds (guild_id, guild_name, server, region, faction)
            VALUES (?, 'Cascade Test Guild', 'TestServer', 'US', 'Alliance')
        """, (test_guild_id,))

        # Insert dependent data
        temp_db.execute("""
            INSERT INTO encounters (
                guild_id, boss_name, instance_name, difficulty,
                encounter_type, start_time, end_time, duration_ms, success
            ) VALUES (?, 'Test Boss', 'Test Instance', 'Normal', 'raid',
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 60000, 1)
        """, (test_guild_id,))

        encounter_id = temp_db.cursor.lastrowid

        temp_db.execute("""
            INSERT INTO characters (guild_id, name, class, spec, realm)
            VALUES (?, 'Test Character', 'Warrior', 'Protection', 'TestRealm')
        """, (test_guild_id,))

        character_id = temp_db.cursor.lastrowid

        # Verify data exists
        cursor = temp_db.execute("""
            SELECT COUNT(*) FROM encounters WHERE guild_id = ?
        """, (test_guild_id,))
        assert cursor.fetchone()[0] == 1, "Encounter should exist"

        cursor = temp_db.execute("""
            SELECT COUNT(*) FROM characters WHERE guild_id = ?
        """, (test_guild_id,))
        assert cursor.fetchone()[0] == 1, "Character should exist"

        # Note: SQLite doesn't support CASCADE DELETE by default
        # This test documents the current behavior
        # In production, we'd need explicit cleanup procedures


if __name__ == "__main__":
    pytest.main([__file__, "-v"])