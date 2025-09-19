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
        self.connection = sqlite3.connect(
            self.db_path, timeout=30.0, check_same_thread=False
        )

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

    # Log files tracking (prevent duplicate processing)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS log_files (
            file_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            file_size INTEGER NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_count INTEGER DEFAULT 0,
            encounter_count INTEGER DEFAULT 0,
            INDEX idx_log_hash(file_hash),
            INDEX idx_log_processed(processed_at)
        )
    """
    )

    # Encounter metadata (denormalized for speed)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS encounters (
            encounter_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            character_guid TEXT UNIQUE NOT NULL,
            character_name TEXT NOT NULL,
            realm TEXT,
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

    logger.info("Creating database indices for fast queries...")

    # Encounters indices
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_time ON encounters(start_time, end_time)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_boss ON encounters(boss_name, difficulty)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_type ON encounters(encounter_type, success)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_instance ON encounters(instance_id)"
    )

    # Characters indices
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_name ON characters(character_name, realm)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_guid ON characters(character_guid)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_class ON characters(class_name, spec_name)"
    )

    # Event blocks indices (critical for performance)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_block_lookup ON event_blocks(encounter_id, character_id, block_index)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_block_time ON event_blocks(start_time, end_time)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_block_character ON event_blocks(character_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_block_encounter ON event_blocks(encounter_id)"
    )

    # Metrics indices
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_performance ON character_metrics(dps DESC, hps DESC)"
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
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_spell_encounter ON spell_summary(encounter_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_spell_damage ON spell_summary(total_damage DESC)"
    )

    # M+ indices
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_mplus_level ON mythic_plus_runs(keystone_level, completed)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_mplus_dungeon ON mythic_plus_runs(dungeon_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_segment_run ON combat_segments(run_id, segment_index)"
    )

    # Set schema version
    db.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (1)")

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
        "items",
        "loot_drops",
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
