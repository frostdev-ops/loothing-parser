"""
SQLite database schema for WoW combat log storage.

Optimized for fast queries and efficient storage with aggressive compression.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import time

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite database connection and schema operations.

    Provides connection pooling, transaction management, and
    schema versioning for the combat log database.
    """

    def __init__(self, db_path: str = "combat_logs.db"):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.connection: Optional[sqlite3.Connection] = None
        self._setup_database()

    def _setup_database(self):
        """Initialize database with optimized settings."""
        try:
            # Ensure parent directory exists with proper error handling
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Test write permissions before creating database
            test_file = self.db_path.parent / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                logger.error(
                    f"No write permission to database directory {self.db_path.parent}: {e}"
                )
                raise RuntimeError(f"Cannot write to database directory: {e}")

            self.connection = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        except Exception as e:
            logger.error(f"Failed to setup database at {self.db_path}: {e}")
            raise

        # Optimize SQLite for our workload
        self.connection.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        self.connection.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        self.connection.execute("PRAGMA cache_size=10000")  # 40MB cache
        self.connection.execute("PRAGMA temp_store=MEMORY")  # Memory temp storage
        self.connection.execute("PRAGMA mmap_size=268435456")  # 256MB mmap

        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys=ON")

        # Set row factory for dict-like access
        self.connection.row_factory = sqlite3.Row

        logger.info(f"Database initialized at {self.db_path}")

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single query."""
        return self.connection.execute(query, params)

    def executemany(self, query: str, params_list: List[tuple]) -> sqlite3.Cursor:
        """Execute query with multiple parameter sets."""
        return self.connection.executemany(query, params_list)

    def commit(self):
        """Commit current transaction."""
        self.connection.commit()

    def rollback(self):
        """Rollback current transaction."""
        self.connection.rollback()

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get table schema information."""
        cursor = self.execute(f"PRAGMA table_info({table_name})")
        return [dict(row) for row in cursor.fetchall()]

    def table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        cursor = self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cursor.fetchone() is not None


def _migrate_character_schema(db: DatabaseManager) -> None:
    """
    Migrate characters table to use server/region columns instead of realm.

    Args:
        db: Database manager instance
    """
    # Only run migration if characters table exists
    if not db.table_exists("characters"):
        return

    # Check if old schema exists (has realm column but no server/region)
    cursor = db.execute("PRAGMA table_info(characters)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    if "realm" in columns and "server" not in columns:
        logger.info("Migrating characters table to new schema with server/region columns")

        # Add new columns
        db.execute("ALTER TABLE characters ADD COLUMN server TEXT")
        db.execute("ALTER TABLE characters ADD COLUMN region TEXT")

        # Migrate existing data: parse realm column for server-region format
        from src.models.character import parse_character_name

        cursor = db.execute(
            "SELECT character_id, character_name, realm FROM characters WHERE realm IS NOT NULL"
        )
        for char_id, char_name, realm in cursor.fetchall():
            # Try to parse the realm as server-region or just server
            if realm and "-" in realm:
                parts = realm.split("-")
                if len(parts) == 2:
                    server, region = parts
                    db.execute(
                        "UPDATE characters SET server = ?, region = ? WHERE character_id = ?",
                        (server, region, char_id),
                    )
                else:
                    # Just use as server
                    db.execute(
                        "UPDATE characters SET server = ? WHERE character_id = ?", (realm, char_id)
                    )
            else:
                # Use as server
                db.execute(
                    "UPDATE characters SET server = ? WHERE character_id = ?", (realm, char_id)
                )

        logger.info("Character schema migration completed")


def _migrate_to_v2_guilds(db: DatabaseManager) -> None:
    """
    Migrate database to version 2 with guild support.

    Args:
        db: Database manager instance
    """
    # Check current schema version
    cursor = db.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    current_version = cursor.fetchone()

    if current_version and current_version[0] >= 2:
        return  # Already at v2 or higher

    logger.info("Migrating database to version 2 (guild multi-tenancy)")

    # Create guilds table if it doesn't exist
    if not db.table_exists("guilds"):
        db.execute("""
            CREATE TABLE guilds (
                guild_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_name TEXT NOT NULL,
                server TEXT NOT NULL,
                region TEXT NOT NULL,
                faction TEXT CHECK(faction IN ('Alliance', 'Horde')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                UNIQUE(guild_name, server, region)
            )
        """)

        # Create default guild for existing data
        db.execute("""
            INSERT INTO guilds (guild_id, guild_name, server, region, faction)
            VALUES (1, 'Default Guild', 'Unknown', 'US', NULL)
        """)

    # Add guild_id columns to existing tables
    tables_to_migrate = ['log_files', 'encounters', 'characters', 'character_metrics']

    for table in tables_to_migrate:
        if db.table_exists(table):
            # Check if guild_id column already exists
            cursor = db.execute(f"PRAGMA table_info({table})")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            if 'guild_id' not in columns:
                logger.info(f"Adding guild_id column to {table}")
                db.execute(f"ALTER TABLE {table} ADD COLUMN guild_id INTEGER NOT NULL DEFAULT 1")

                # Add foreign key constraint (SQLite doesn't support adding FK constraints to existing tables)
                # This would need to be done manually in production or with table recreation

    # Create new multi-tenant indexes
    indexes_to_create = [
        "CREATE INDEX IF NOT EXISTS idx_guild_lookup ON guilds(guild_name, server, region)",
        "CREATE INDEX IF NOT EXISTS idx_guild_active ON guilds(is_active, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_log_guild ON log_files(guild_id, processed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_time ON encounters(guild_id, start_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_boss ON encounters(guild_id, boss_name, difficulty, start_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_type ON encounters(guild_id, encounter_type, success, start_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_instance ON encounters(guild_id, instance_name, difficulty)",
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_progression ON encounters(guild_id, difficulty, success, start_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_character_guild_name ON characters(guild_id, character_name, server)",
        "CREATE INDEX IF NOT EXISTS idx_character_guild_class ON characters(guild_id, class_name, spec_name)",
        "CREATE INDEX IF NOT EXISTS idx_character_guild_active ON characters(guild_id, last_seen DESC)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_performance ON character_metrics(guild_id, dps DESC) WHERE dps > 0",
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_healing ON character_metrics(guild_id, hps DESC) WHERE hps > 0",
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_combat_dps ON character_metrics(guild_id, combat_dps DESC) WHERE combat_dps > 0",
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_combat_hps ON character_metrics(guild_id, combat_hps DESC) WHERE combat_hps > 0",
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_character ON character_metrics(guild_id, character_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_encounter ON character_metrics(guild_id, encounter_id)",
    ]

    for index_sql in indexes_to_create:
        try:
            db.execute(index_sql)
        except Exception as e:
            logger.warning(f"Failed to create index: {index_sql} - {e}")

    # Update schema version
    db.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (2)")
    db.commit()

    logger.info("Migration to version 2 completed successfully")


def create_tables(db: DatabaseManager) -> None:
    """
    Create all tables and indices for combat log storage.

    Args:
        db: Database manager instance
    """

    # Schema version tracking
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Guild management for multi-tenancy
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS guilds (
            guild_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_name TEXT NOT NULL,
            server TEXT NOT NULL,
            region TEXT NOT NULL,
            faction TEXT CHECK(faction IN ('Alliance', 'Horde')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            UNIQUE(guild_name, server, region)
        )
    """
    )

    # Run migrations
    _migrate_character_schema(db)

    # Log files tracking (prevent duplicate processing)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS log_files (
            file_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL REFERENCES guilds(guild_id),
            file_path TEXT UNIQUE NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            file_size INTEGER NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_count INTEGER DEFAULT 0,
            encounter_count INTEGER DEFAULT 0
        )
    """
    )

    # Encounter metadata (denormalized for speed)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS encounters (
            encounter_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL REFERENCES guilds(guild_id),
            log_file_id INTEGER REFERENCES log_files(file_id),
            encounter_type TEXT NOT NULL CHECK(encounter_type IN ('raid', 'mythic_plus')),
            boss_name TEXT NOT NULL,
            difficulty TEXT,
            instance_id INTEGER,
            instance_name TEXT,
            pull_number INTEGER DEFAULT 1,
            start_time REAL NOT NULL,
            end_time REAL,
            success BOOLEAN DEFAULT FALSE,
            combat_length REAL DEFAULT 0.0,
            raid_size INTEGER DEFAULT 0,
            wipe_percentage REAL,
            bloodlust_used BOOLEAN DEFAULT FALSE,
            bloodlust_time REAL,
            battle_resurrections INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Character metadata
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS characters (
            character_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL REFERENCES guilds(guild_id),
            character_guid TEXT UNIQUE NOT NULL,
            character_name TEXT NOT NULL,
            server TEXT,
            region TEXT,
            class_name TEXT,
            spec_name TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            encounter_count INTEGER DEFAULT 0
        )
    """
    )

    # Compressed event storage (core table)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS event_blocks (
            block_id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER NOT NULL REFERENCES encounters(encounter_id),
            character_id INTEGER NOT NULL REFERENCES characters(character_id),
            block_index INTEGER NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            event_count INTEGER NOT NULL,
            compressed_data BLOB NOT NULL,
            uncompressed_size INTEGER NOT NULL,
            compressed_size INTEGER NOT NULL,
            compression_ratio REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Pre-computed character metrics (for fast dashboard queries)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS character_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL REFERENCES guilds(guild_id),
            encounter_id INTEGER NOT NULL REFERENCES encounters(encounter_id),
            character_id INTEGER NOT NULL REFERENCES characters(character_id),
            damage_done INTEGER DEFAULT 0,
            healing_done INTEGER DEFAULT 0,
            damage_taken INTEGER DEFAULT 0,
            healing_received INTEGER DEFAULT 0,
            overhealing INTEGER DEFAULT 0,
            death_count INTEGER DEFAULT 0,
            activity_percentage REAL DEFAULT 0.0,
            time_alive REAL DEFAULT 0.0,
            dps REAL DEFAULT 0.0,
            hps REAL DEFAULT 0.0,
            dtps REAL DEFAULT 0.0,
            combat_time REAL DEFAULT 0.0,
            combat_dps REAL DEFAULT 0.0,
            combat_hps REAL DEFAULT 0.0,
            combat_dtps REAL DEFAULT 0.0,
            combat_activity_percentage REAL DEFAULT 0.0,
            damage_absorbed_by_shields INTEGER DEFAULT 0,
            damage_absorbed_for_me INTEGER DEFAULT 0,
            total_events INTEGER DEFAULT 0,
            cast_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(encounter_id, character_id)
        )
    """
    )

    # Spell usage summary (aggregated for analysis)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS spell_summary (
            summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER NOT NULL REFERENCES encounters(encounter_id),
            character_id INTEGER NOT NULL REFERENCES characters(character_id),
            spell_id INTEGER NOT NULL,
            spell_name TEXT NOT NULL,
            cast_count INTEGER DEFAULT 0,
            hit_count INTEGER DEFAULT 0,
            crit_count INTEGER DEFAULT 0,
            total_damage INTEGER DEFAULT 0,
            total_healing INTEGER DEFAULT 0,
            max_damage INTEGER DEFAULT 0,
            max_healing INTEGER DEFAULT 0,
            UNIQUE(encounter_id, character_id, spell_id)
        )
    """
    )

    # Mythic+ specific data
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS mythic_plus_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER UNIQUE REFERENCES encounters(encounter_id),
            dungeon_id INTEGER NOT NULL,
            keystone_level INTEGER NOT NULL,
            affixes TEXT,  -- JSON array of affix IDs
            time_limit_seconds INTEGER NOT NULL,
            actual_time_seconds REAL NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            in_time BOOLEAN DEFAULT FALSE,
            time_remaining REAL DEFAULT 0.0,
            num_deaths INTEGER DEFAULT 0,
            death_penalties REAL DEFAULT 0.0,
            enemy_forces_percent REAL DEFAULT 0.0
        )
    """
    )

    # Combat segments for M+ (bosses and trash)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS combat_segments (
            segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES mythic_plus_runs(run_id),
            segment_index INTEGER NOT NULL,
            segment_type TEXT NOT NULL CHECK(segment_type IN ('boss', 'trash', 'miniboss')),
            segment_name TEXT,
            start_time REAL NOT NULL,
            end_time REAL,
            duration REAL DEFAULT 0.0,
            mob_count INTEGER DEFAULT 0,
            enemy_forces_start REAL DEFAULT 0.0,
            enemy_forces_end REAL DEFAULT 0.0,
            enemy_forces_gained REAL DEFAULT 0.0
        )
    """
    )

    # Combat periods (active combat vs downtime tracking)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS combat_periods (
            period_id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER NOT NULL REFERENCES encounters(encounter_id),
            period_index INTEGER NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            duration REAL NOT NULL,
            event_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    logger.info("Creating database indices for fast queries...")

    # Guild indices for multi-tenancy
    db.execute("CREATE INDEX IF NOT EXISTS idx_guild_lookup ON guilds(guild_name, server, region)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_guild_active ON guilds(is_active, created_at)")

    # Log files indices (multi-tenant aware)
    db.execute("CREATE INDEX IF NOT EXISTS idx_log_hash ON log_files(file_hash)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_log_processed ON log_files(processed_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_log_guild ON log_files(guild_id, processed_at DESC)")

    # Encounters indices (multi-tenant aware - guild_id first for row-level security)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_time ON encounters(guild_id, start_time DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_boss ON encounters(guild_id, boss_name, difficulty, start_time DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_type ON encounters(guild_id, encounter_type, success, start_time DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_instance ON encounters(guild_id, instance_name, difficulty)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_guild_progression ON encounters(guild_id, difficulty, success, start_time DESC)"
    )

    # Legacy single-tenant indexes (for backward compatibility during migration)
    db.execute("CREATE INDEX IF NOT EXISTS idx_encounter_time ON encounters(start_time, end_time)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_encounter_boss ON encounters(boss_name, difficulty)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_type ON encounters(encounter_type, success)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_encounter_instance ON encounters(instance_id)")

    # Characters indices (multi-tenant aware)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_guild_name ON characters(guild_id, character_name, server)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_guild_class ON characters(guild_id, class_name, spec_name)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_guild_active ON characters(guild_id, last_seen DESC)"
    )

    # Legacy character indices (for backward compatibility)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_name ON characters(character_name, server, region)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_character_guid ON characters(character_guid)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_class ON characters(class_name, spec_name)"
    )

    # Event blocks indices (critical for performance)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_block_lookup ON event_blocks(encounter_id, character_id, block_index)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_block_time ON event_blocks(start_time, end_time)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_block_character ON event_blocks(character_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_block_encounter ON event_blocks(encounter_id)")

    # Metrics indices (multi-tenant aware - critical for leaderboards and rankings)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_performance ON character_metrics(guild_id, dps DESC) WHERE dps > 0"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_healing ON character_metrics(guild_id, hps DESC) WHERE hps > 0"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_combat_dps ON character_metrics(guild_id, combat_dps DESC) WHERE combat_dps > 0"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_combat_hps ON character_metrics(guild_id, combat_hps DESC) WHERE combat_hps > 0"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_character ON character_metrics(guild_id, character_id, created_at DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_guild_encounter ON character_metrics(guild_id, encounter_id)"
    )

    # Legacy metrics indices (for backward compatibility)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_performance ON character_metrics(dps DESC, hps DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_combat_performance ON character_metrics(combat_dps DESC, combat_hps DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_encounter ON character_metrics(encounter_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_character ON character_metrics(character_id)"
    )

    # Spell summary indices
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_spell_usage ON spell_summary(character_id, spell_id)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_spell_encounter ON spell_summary(encounter_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_spell_damage ON spell_summary(total_damage DESC)")

    # M+ indices
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_mplus_level ON mythic_plus_runs(keystone_level, completed)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_mplus_dungeon ON mythic_plus_runs(dungeon_id)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_segment_run ON combat_segments(run_id, segment_index)"
    )

    # Combat periods indices
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_combat_periods_encounter ON combat_periods(encounter_id, period_index)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_combat_periods_time ON combat_periods(start_time, end_time)"
    )

    # Set schema version (v2 adds multi-tenant guild support)
    db.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (2)")

    db.commit()
    logger.info("Database schema created successfully")


def get_database_stats(db: DatabaseManager) -> Dict[str, Any]:
    """
    Get database statistics and performance metrics.

    Args:
        db: Database manager instance

    Returns:
        Dictionary with database statistics
    """
    stats = {}

    # Table row counts
    tables = [
        "encounters",
        "characters",
        "event_blocks",
        "character_metrics",
        "spell_summary",
    ]
    for table in tables:
        cursor = db.execute(f"SELECT COUNT(*) FROM {table}")
        stats[f"{table}_count"] = cursor.fetchone()[0]

    # Storage statistics
    cursor = db.execute(
        """
        SELECT
            SUM(compressed_size) as total_compressed,
            SUM(uncompressed_size) as total_uncompressed,
            AVG(compression_ratio) as avg_compression_ratio,
            COUNT(*) as block_count
        FROM event_blocks
    """
    )
    row = cursor.fetchone()
    if row and row[0]:
        stats.update(
            {
                "total_compressed_bytes": row[0],
                "total_uncompressed_bytes": row[1],
                "average_compression_ratio": round(row[2], 3),
                "total_blocks": row[3],
            }
        )

    # Recent activity
    cursor = db.execute(
        """
        SELECT COUNT(*)
        FROM encounters
        WHERE created_at > datetime('now', '-7 days')
    """
    )
    stats["encounters_last_7_days"] = cursor.fetchone()[0]

    # Database file size
    cursor = db.execute("PRAGMA page_count")
    page_count = cursor.fetchone()[0]
    cursor = db.execute("PRAGMA page_size")
    page_size = cursor.fetchone()[0]
    stats["database_size_bytes"] = page_count * page_size

    return stats


def optimize_database(db: DatabaseManager) -> None:
    """
    Run database optimization and maintenance.

    Args:
        db: Database manager instance
    """
    logger.info("Running database optimization...")

    start_time = time.time()

    # Analyze tables for query optimizer
    db.execute("ANALYZE")

    # Vacuum to reclaim space (may take time on large databases)
    db.execute("VACUUM")

    # Update statistics
    db.execute("PRAGMA optimize")

    elapsed = time.time() - start_time
    logger.info(f"Database optimization completed in {elapsed:.2f} seconds")
