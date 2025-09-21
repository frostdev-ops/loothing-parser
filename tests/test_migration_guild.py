"""
Test suite for guild system database migration.

This module tests the migration from v1 (single-tenant) to v2 (multi-tenant) schema,
ensuring data integrity and proper foreign key relationships.
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from typing import Generator

from src.database.schema import DatabaseSchema


class TestGuildMigration:
    """Test guild system database migration functionality."""

    @pytest.fixture
    def temp_db(self) -> Generator[str, None, None]:
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
            db_path = f.name

        yield db_path

        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def v1_schema_db(self, temp_db: str) -> str:
        """Create a database with v1 schema and sample data."""
        conn = sqlite3.connect(temp_db)

        # Create v1 schema without guilds
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS encounters (
                encounter_id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                encounter_name TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                duration_seconds INTEGER,
                success BOOLEAN DEFAULT FALSE,
                wipe_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                character_id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                character_name TEXT NOT NULL,
                character_class TEXT NOT NULL,
                specialization TEXT,
                level INTEGER,
                item_level INTEGER,
                realm TEXT,
                FOREIGN KEY (encounter_id) REFERENCES encounters (encounter_id) ON DELETE CASCADE
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                event_data TEXT,
                FOREIGN KEY (character_id) REFERENCES characters (character_id) ON DELETE CASCADE
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS combat_periods (
                period_id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                period_type TEXT NOT NULL,
                FOREIGN KEY (encounter_id) REFERENCES encounters (encounter_id) ON DELETE CASCADE
            )
        """
        )

        # Insert sample v1 data
        conn.execute(
            """
            INSERT INTO encounters (instance_name, encounter_name, difficulty, start_time, end_time, duration_seconds, success)
            VALUES
                ('The War Within', 'Ulgrax the Devourer', 'Heroic', '2024-09-20 20:00:00', '2024-09-20 20:05:30', 330, 1),
                ('Mists of Tirna Scithe', 'Mythic+ Complete', 'Mythic+15', '2024-09-20 21:00:00', '2024-09-20 21:28:45', 1725, 1),
                ('The War Within', 'The Bloodbound Horror', 'Normal', '2024-09-19 19:30:00', '2024-09-19 19:45:20', 920, 1)
        """
        )

        conn.execute(
            """
            INSERT INTO characters (encounter_id, character_name, character_class, specialization, level, item_level, realm)
            VALUES
                (1, 'Testwarrior', 'Warrior', 'Protection', 80, 628, 'Stormrage'),
                (1, 'Testmage', 'Mage', 'Fire', 80, 625, 'Stormrage'),
                (2, 'Testwarrior', 'Warrior', 'Protection', 80, 628, 'Stormrage'),
                (2, 'Testhunter', 'Hunter', 'Beast Mastery', 80, 620, 'Stormrage'),
                (3, 'Testmage', 'Mage', 'Fire', 80, 625, 'Stormrage')
        """
        )

        conn.execute(
            """
            INSERT INTO character_events (character_id, event_type, timestamp, event_data)
            VALUES
                (1, 'SPELL_DAMAGE', '2024-09-20 20:01:00', '{"damage": 50000}'),
                (2, 'SPELL_CAST_SUCCESS', '2024-09-20 20:01:05', '{"spell": "Fireball"}'),
                (3, 'SPELL_DAMAGE', '2024-09-20 21:05:00', '{"damage": 45000}'),
                (4, 'SPELL_CAST_SUCCESS', '2024-09-20 21:05:10', '{"spell": "Bestial Wrath"}'),
                (5, 'SPELL_DAMAGE', '2024-09-19 19:35:00', '{"damage": 48000}')
        """
        )

        conn.execute(
            """
            INSERT INTO combat_periods (encounter_id, start_time, end_time, period_type)
            VALUES
                (1, '2024-09-20 20:00:00', '2024-09-20 20:05:30', 'boss_fight'),
                (2, '2024-09-20 21:00:00', '2024-09-20 21:28:45', 'dungeon_run'),
                (3, '2024-09-19 19:30:00', '2024-09-19 19:45:20', 'boss_fight')
        """
        )

        # Set schema version to 1
        conn.execute("PRAGMA user_version = 1")

        conn.commit()
        conn.close()

        return temp_db

    def test_migration_creates_guilds_table(self, v1_schema_db: str):
        """Test that migration creates the guilds table with proper schema."""
        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)

        # Check guilds table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='guilds'")
        assert cursor.fetchone() is not None, "Guilds table should exist after migration"

        # Check guilds table schema
        cursor = conn.execute("PRAGMA table_info(guilds)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "guild_id": "INTEGER",
            "guild_name": "TEXT",
            "server": "TEXT",
            "region": "TEXT",
            "faction": "TEXT",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
            "is_active": "BOOLEAN",
        }

        for col_name, col_type in expected_columns.items():
            assert col_name in columns, f"Column {col_name} should exist in guilds table"
            assert columns[col_name] == col_type, f"Column {col_name} should be {col_type}"

        conn.close()

    def test_migration_creates_default_guild(self, v1_schema_db: str):
        """Test that migration creates a default guild for existing data."""
        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)

        # Check default guild was created
        cursor = conn.execute("SELECT * FROM guilds WHERE guild_id = 1")
        default_guild = cursor.fetchone()

        assert default_guild is not None, "Default guild should be created"
        assert default_guild[1] == "Default Guild", "Default guild should have correct name"
        assert default_guild[2] == "Unknown", "Default guild should have placeholder server"
        assert default_guild[3] == "Unknown", "Default guild should have placeholder region"
        assert default_guild[7] == 1, "Default guild should be active"

        conn.close()

    def test_migration_adds_guild_foreign_keys(self, v1_schema_db: str):
        """Test that migration adds guild_id foreign keys to all tables."""
        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)

        # Check encounters table has guild_id
        cursor = conn.execute("PRAGMA table_info(encounters)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "guild_id" in columns, "Encounters table should have guild_id column"

        # Check characters table has guild_id
        cursor = conn.execute("PRAGMA table_info(characters)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "guild_id" in columns, "Characters table should have guild_id column"

        # Check character_events table has guild_id
        cursor = conn.execute("PRAGMA table_info(character_events)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "guild_id" in columns, "Character_events table should have guild_id column"

        # Check combat_periods table has guild_id
        cursor = conn.execute("PRAGMA table_info(combat_periods)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "guild_id" in columns, "Combat_periods table should have guild_id column"

        conn.close()

    def test_migration_assigns_default_guild_to_existing_data(self, v1_schema_db: str):
        """Test that existing data is assigned to the default guild."""
        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)

        # Check all encounters are assigned to default guild
        cursor = conn.execute("SELECT COUNT(*) FROM encounters WHERE guild_id = 1")
        encounter_count = cursor.fetchone()[0]
        assert encounter_count == 3, "All existing encounters should be assigned to default guild"

        # Check all characters are assigned to default guild
        cursor = conn.execute("SELECT COUNT(*) FROM characters WHERE guild_id = 1")
        character_count = cursor.fetchone()[0]
        assert character_count == 5, "All existing characters should be assigned to default guild"

        # Check all character_events are assigned to default guild
        cursor = conn.execute("SELECT COUNT(*) FROM character_events WHERE guild_id = 1")
        event_count = cursor.fetchone()[0]
        assert event_count == 5, "All existing character_events should be assigned to default guild"

        # Check all combat_periods are assigned to default guild
        cursor = conn.execute("SELECT COUNT(*) FROM combat_periods WHERE guild_id = 1")
        period_count = cursor.fetchone()[0]
        assert period_count == 3, "All existing combat_periods should be assigned to default guild"

        conn.close()

    def test_migration_preserves_existing_data(self, v1_schema_db: str):
        """Test that migration preserves all existing data integrity."""
        # Get pre-migration data counts
        conn = sqlite3.connect(v1_schema_db)

        cursor = conn.execute("SELECT COUNT(*) FROM encounters")
        pre_encounter_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM characters")
        pre_character_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM character_events")
        pre_event_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM combat_periods")
        pre_period_count = cursor.fetchone()[0]

        # Get sample data for verification
        cursor = conn.execute(
            "SELECT encounter_name, difficulty FROM encounters ORDER BY encounter_id"
        )
        pre_encounters = cursor.fetchall()

        cursor = conn.execute(
            "SELECT character_name, character_class FROM characters ORDER BY character_id"
        )
        pre_characters = cursor.fetchall()

        conn.close()

        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        # Check post-migration data counts
        conn = sqlite3.connect(v1_schema_db)

        cursor = conn.execute("SELECT COUNT(*) FROM encounters")
        post_encounter_count = cursor.fetchone()[0]
        assert post_encounter_count == pre_encounter_count, "Encounter count should be preserved"

        cursor = conn.execute("SELECT COUNT(*) FROM characters")
        post_character_count = cursor.fetchone()[0]
        assert post_character_count == pre_character_count, "Character count should be preserved"

        cursor = conn.execute("SELECT COUNT(*) FROM character_events")
        post_event_count = cursor.fetchone()[0]
        assert post_event_count == pre_event_count, "Character event count should be preserved"

        cursor = conn.execute("SELECT COUNT(*) FROM combat_periods")
        post_period_count = cursor.fetchone()[0]
        assert post_period_count == pre_period_count, "Combat period count should be preserved"

        # Verify specific data integrity
        cursor = conn.execute(
            "SELECT encounter_name, difficulty FROM encounters ORDER BY encounter_id"
        )
        post_encounters = cursor.fetchall()
        assert post_encounters == pre_encounters, "Encounter data should be preserved"

        cursor = conn.execute(
            "SELECT character_name, character_class FROM characters ORDER BY character_id"
        )
        post_characters = cursor.fetchall()
        assert post_characters == pre_characters, "Character data should be preserved"

        conn.close()

    def test_migration_creates_guild_indexes(self, v1_schema_db: str):
        """Test that migration creates proper indexes for guild multi-tenancy."""
        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)

        # Get all indexes
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_guild_%'"
        )
        indexes = [row[0] for row in cursor.fetchall()]

        # Check expected guild indexes exist
        expected_indexes = [
            "idx_guild_encounters_lookup",
            "idx_guild_characters_lookup",
            "idx_guild_character_events_lookup",
            "idx_guild_combat_periods_lookup",
        ]

        for expected_index in expected_indexes:
            assert expected_index in indexes, f"Index {expected_index} should exist after migration"

        conn.close()

    def test_migration_updates_schema_version(self, v1_schema_db: str):
        """Test that migration updates the schema version to 2."""
        # Verify initial version
        conn = sqlite3.connect(v1_schema_db)
        cursor = conn.execute("PRAGMA user_version")
        initial_version = cursor.fetchone()[0]
        assert initial_version == 1, "Initial schema version should be 1"
        conn.close()

        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        # Check updated version
        conn = sqlite3.connect(v1_schema_db)
        cursor = conn.execute("PRAGMA user_version")
        updated_version = cursor.fetchone()[0]
        assert updated_version == 2, "Schema version should be updated to 2"
        conn.close()

    def test_migration_is_idempotent(self, v1_schema_db: str):
        """Test that running migration multiple times doesn't cause issues."""
        # Run migration first time
        schema1 = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)

        # Get post-first-migration state
        cursor = conn.execute("SELECT COUNT(*) FROM guilds")
        guild_count_1 = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM encounters")
        encounter_count_1 = cursor.fetchone()[0]

        cursor = conn.execute("PRAGMA user_version")
        version_1 = cursor.fetchone()[0]

        conn.close()

        # Run migration second time
        schema2 = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)

        # Get post-second-migration state
        cursor = conn.execute("SELECT COUNT(*) FROM guilds")
        guild_count_2 = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM encounters")
        encounter_count_2 = cursor.fetchone()[0]

        cursor = conn.execute("PRAGMA user_version")
        version_2 = cursor.fetchone()[0]

        conn.close()

        # Verify idempotency
        assert guild_count_2 == guild_count_1, "Guild count should not change on second migration"
        assert (
            encounter_count_2 == encounter_count_1
        ), "Encounter count should not change on second migration"
        assert version_2 == version_1, "Schema version should not change on second migration"

    def test_migration_foreign_key_constraints(self, v1_schema_db: str):
        """Test that foreign key constraints work properly after migration."""
        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(v1_schema_db)

        conn = sqlite3.connect(v1_schema_db)
        conn.execute("PRAGMA foreign_keys = ON")

        # Test that we cannot insert encounter with invalid guild_id
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO encounters (guild_id, instance_name, encounter_name, difficulty, start_time)
                VALUES (999, 'Test Instance', 'Test Boss', 'Normal', '2024-09-21 12:00:00')
            """
            )

        # Test that we can insert encounter with valid guild_id
        conn.execute(
            """
            INSERT INTO encounters (guild_id, instance_name, encounter_name, difficulty, start_time)
            VALUES (1, 'Test Instance', 'Test Boss', 'Normal', '2024-09-21 12:00:00')
        """
        )

        # Verify the insert worked
        cursor = conn.execute(
            "SELECT COUNT(*) FROM encounters WHERE guild_id = 1 AND encounter_name = 'Test Boss'"
        )
        count = cursor.fetchone()[0]
        assert count == 1, "Valid guild_id insert should succeed"

        conn.close()

    def test_migration_with_empty_database(self, temp_db: str):
        """Test migration works correctly with an empty v1 database."""
        # Create empty v1 database
        conn = sqlite3.connect(temp_db)
        conn.execute("PRAGMA user_version = 1")
        conn.close()

        # Initialize schema (should trigger migration)
        schema = DatabaseSchema(temp_db)

        conn = sqlite3.connect(temp_db)

        # Check that guilds table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='guilds'")
        assert cursor.fetchone() is not None, "Guilds table should exist"

        # Check that default guild was created
        cursor = conn.execute("SELECT COUNT(*) FROM guilds WHERE guild_id = 1")
        guild_count = cursor.fetchone()[0]
        assert guild_count == 1, "Default guild should be created even in empty database"

        # Check schema version
        cursor = conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version == 2, "Schema version should be updated to 2"

        conn.close()

    def test_migration_rollback_on_error(self, v1_schema_db: str):
        """Test that migration rolls back properly if an error occurs."""
        # This test simulates migration failure by corrupting the database
        # during migration process

        # First, let's verify the database is in v1 state
        conn = sqlite3.connect(v1_schema_db)
        cursor = conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version == 1, "Database should start in v1 state"

        cursor = conn.execute("SELECT COUNT(*) FROM encounters")
        original_count = cursor.fetchone()[0]
        conn.close()

        # Mock a database corruption scenario by creating a conflicting table
        # This should cause migration to fail and rollback
        conn = sqlite3.connect(v1_schema_db)
        try:
            # Create a conflicting guilds table that would prevent proper migration
            conn.execute("CREATE TABLE guilds (conflicting_column TEXT)")
            conn.commit()

            # Now try to initialize schema - this should fail
            with pytest.raises(Exception):
                schema = DatabaseSchema(v1_schema_db)

        except Exception:
            # Expected behavior - migration should fail
            pass

        finally:
            conn.close()

        # Verify database is still in original state
        conn = sqlite3.connect(v1_schema_db)

        cursor = conn.execute("SELECT COUNT(*) FROM encounters")
        final_count = cursor.fetchone()[0]
        assert final_count == original_count, "Data should be preserved after failed migration"

        conn.close()
