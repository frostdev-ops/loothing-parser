# 📈 Migration Guide: v1 to v2 (Multi-Tenant Guilds)

This guide provides step-by-step instructions for migrating from the single-tenant combat log parser (v1) to the multi-tenant guild-based system (v2).

## 📋 Table of Contents

- [Overview](#overview)
- [Pre-Migration Assessment](#pre-migration-assessment)
- [Backup Procedures](#backup-procedures)
- [Migration Process](#migration-process)
- [Post-Migration Verification](#post-migration-verification)
- [Rollback Procedures](#rollback-procedures)
- [Troubleshooting](#troubleshooting)
- [Performance Optimization](#performance-optimization)

## Overview

### What's Changing

The v2 migration introduces:

- **Guild System**: Multi-tenant architecture with complete data isolation
- **Database Schema**: New `guilds` table and `guild_id` foreign keys
- **API Changes**: Guild-scoped authentication and endpoints
- **Indexing**: Guild-first composite indexes for performance
- **CLI Updates**: Guild context parameters

### Migration Impact

| Component           | Changes                | Downtime Required   |
| ------------------- | ---------------------- | ------------------- |
| Database Schema     | ⚠️ Major               | Yes (15-30 minutes) |
| API Endpoints       | ⚠️ Breaking            | Yes                 |
| WebSocket Streaming | ⚠️ Breaking            | Yes                 |
| CLI Commands        | ⚠️ Optional Parameters | No                  |
| Data Storage        | ✅ Preserved           | No                  |

### Compatibility

- **Backward Compatible**: Existing data is preserved and assigned to Default Guild (ID: 1)
- **API Changes**: New endpoints require guild context, old endpoints deprecated
- **CLI Enhanced**: New guild parameters, existing commands still work with defaults

## Pre-Migration Assessment

### 1. System Requirements

#### Minimum Requirements

- **Database**: SQLite 3.24+ or PostgreSQL 12+ (future)
- **Python**: 3.9+
- **Memory**: 2GB RAM (for large databases)
- **Storage**: 20% additional space for migration process
- **Downtime Window**: 15-60 minutes depending on data size

#### Compatibility Check

```bash
# Check current schema version
python -c "
import sqlite3
conn = sqlite3.connect('./data/combat_logs.db')
version = conn.execute('SELECT value FROM metadata WHERE key = \"schema_version\"').fetchone()
print(f'Current schema version: {version[0] if version else \"1 (implied)\"}')
conn.close()
"

# Check database size
du -h ./data/combat_logs.db

# Count existing records
python -c "
import sqlite3
conn = sqlite3.connect('./data/combat_logs.db')
encounters = conn.execute('SELECT COUNT(*) FROM encounters').fetchone()[0]
characters = conn.execute('SELECT COUNT(*) FROM characters').fetchone()[0]
print(f'Encounters: {encounters:,}')
print(f'Characters: {characters:,}')
conn.close()
"
```

### 2. Data Inventory

#### Current Data Assessment

```sql
-- Data distribution analysis
SELECT
    COUNT(*) as total_encounters,
    MIN(start_time) as oldest_encounter,
    MAX(start_time) as newest_encounter,
    COUNT(DISTINCT boss_name) as unique_bosses,
    COUNT(DISTINCT instance_name) as unique_instances
FROM encounters;

-- Character distribution
SELECT
    COUNT(*) as total_characters,
    COUNT(DISTINCT name) as unique_names,
    COUNT(DISTINCT class) as unique_classes,
    COUNT(DISTINCT spec) as unique_specs
FROM characters;

-- Storage size estimate
SELECT
    'encounters' as table_name,
    COUNT(*) as row_count,
    AVG(LENGTH(COALESCE(boss_name, '') || COALESCE(instance_name, ''))) as avg_row_size
FROM encounters
UNION ALL
SELECT
    'characters' as table_name,
    COUNT(*) as row_count,
    AVG(LENGTH(COALESCE(name, '') || COALESCE(class, '') || COALESCE(spec, ''))) as avg_row_size
FROM characters;
```

### 3. Application Dependencies

#### Services Using the Parser

Document all services that depend on the combat log parser:

- **API Clients**: Web dashboards, mobile apps
- **Integrations**: Discord bots, guild websites
- **Automated Scripts**: Backup systems, analytics
- **Monitoring**: Performance tracking, alerting

#### Configuration Review

```bash
# Check current API keys
python -c "
from src.api.auth import auth_manager
stats = auth_manager.get_all_stats()
print(f'Current API keys: {stats[\"active_api_keys\"]}')
print(f'Active connections: {stats[\"total_active_connections\"]}')
"

# Review configuration files
cat .env 2>/dev/null || echo "No .env file found"
ls -la config/ 2>/dev/null || echo "No config directory found"
```

## Backup Procedures

### 1. Complete System Backup

#### Database Backup

```bash
#!/bin/bash
# backup_system.sh

BACKUP_DIR="./backups/migration_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "Creating system backup in $BACKUP_DIR..."

# Database backup
echo "Backing up database..."
sqlite3 ./data/combat_logs.db .backup "$BACKUP_DIR/combat_logs_pre_migration.db"

# Verify backup integrity
echo "Verifying backup integrity..."
sqlite3 "$BACKUP_DIR/combat_logs_pre_migration.db" "PRAGMA integrity_check;" > "$BACKUP_DIR/integrity_check.txt"

# Configuration backup
echo "Backing up configuration..."
cp -r .env* "$BACKUP_DIR/" 2>/dev/null || true
cp -r config/ "$BACKUP_DIR/" 2>/dev/null || true

# Log files backup
echo "Backing up logs..."
cp -r logs/ "$BACKUP_DIR/" 2>/dev/null || true

# Create backup manifest
cat > "$BACKUP_DIR/backup_manifest.txt" << EOF
Backup created: $(date)
Original database size: $(du -h ./data/combat_logs.db | cut -f1)
Backup database size: $(du -h "$BACKUP_DIR/combat_logs_pre_migration.db" | cut -f1)
Schema version: $(sqlite3 ./data/combat_logs.db "SELECT value FROM metadata WHERE key = 'schema_version'" 2>/dev/null || echo "1")
Encounter count: $(sqlite3 ./data/combat_logs.db "SELECT COUNT(*) FROM encounters")
Character count: $(sqlite3 ./data/combat_logs.db "SELECT COUNT(*) FROM characters")
EOF

echo "Backup completed: $BACKUP_DIR"
echo "Backup manifest:"
cat "$BACKUP_DIR/backup_manifest.txt"
```

#### Compressed Backup

```bash
# Create compressed backup for long-term storage
BACKUP_FILE="combat_logs_v1_backup_$(date +%Y%m%d).tar.gz"

tar -czf "$BACKUP_FILE" \
    ./data/combat_logs.db \
    .env* \
    config/ \
    logs/ \
    --exclude="*.pyc" \
    --exclude="__pycache__"

echo "Compressed backup created: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
```

### 2. Export Critical Data

#### Export Encounters

```bash
# Export encounters to CSV for external backup
sqlite3 -header -csv ./data/combat_logs.db \
    "SELECT * FROM encounters ORDER BY start_time" \
    > "encounters_export_$(date +%Y%m%d).csv"

# Export characters
sqlite3 -header -csv ./data/combat_logs.db \
    "SELECT * FROM characters" \
    > "characters_export_$(date +%Y%m%d).csv"
```

#### Export for Manual Recovery

```sql
-- Export as SQL statements
.output encounters_backup.sql
.mode insert encounters
SELECT * FROM encounters;

.output characters_backup.sql
.mode insert characters
SELECT * FROM characters;

.output character_metrics_backup.sql
.mode insert character_metrics
SELECT * FROM character_metrics;

.output
```

## Migration Process

### 1. Pre-Migration Shutdown

#### Stop All Services

```bash
#!/bin/bash
# shutdown_services.sh

echo "Stopping combat log parser services..."

# Stop API server
pkill -f "python -m src.api.app" || true

# Stop streaming server
pkill -f "streaming_server" || true

# Stop any background workers
pkill -f "parallel_processor" || true

# Verify all services stopped
sleep 5
if pgrep -f "python -m src.api"; then
    echo "WARNING: Some services still running"
    pgrep -f "python -m src.api"
else
    echo "All services stopped successfully"
fi
```

#### Final Backup Verification

```bash
# Create final pre-migration backup
sqlite3 ./data/combat_logs.db .backup "./migration_final_backup.db"

# Verify database is not corrupted
sqlite3 ./data/combat_logs.db "PRAGMA integrity_check;"
if [ $? -eq 0 ]; then
    echo "Database integrity verified"
else
    echo "ERROR: Database corruption detected. Aborting migration."
    exit 1
fi
```

### 2. Schema Migration

#### Execute Migration Script

```python
#!/usr/bin/env python3
# migrate_to_v2.py

import sqlite3
import sys
import time
from datetime import datetime

def migrate_database(db_path):
    """Migrate database from v1 to v2 schema."""

    print(f"Starting migration of {db_path}")
    print(f"Migration started at: {datetime.now()}")

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("BEGIN TRANSACTION")

        # 1. Check current schema version
        try:
            version = conn.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            current_version = version[0] if version else "1"
        except sqlite3.OperationalError:
            current_version = "1"

        print(f"Current schema version: {current_version}")

        if current_version == "2":
            print("Database already at v2, skipping migration")
            return True

        # 2. Create guilds table
        print("Creating guilds table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_name TEXT NOT NULL,
                server TEXT NOT NULL,
                region TEXT NOT NULL,
                faction TEXT CHECK(faction IN ('Alliance', 'Horde')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                settings_json TEXT DEFAULT '{}',
                contact_info TEXT,
                timezone TEXT DEFAULT 'UTC',
                UNIQUE(guild_name, server, region)
            )
        """)

        # 3. Create default guild
        print("Creating default guild...")
        conn.execute("""
            INSERT OR IGNORE INTO guilds
            (guild_id, guild_name, server, region, faction)
            VALUES (1, 'Default Guild', 'Unknown', 'US', 'Alliance')
        """)

        # 4. Add guild_id columns to existing tables
        print("Adding guild_id columns...")

        # Check if columns already exist
        encounters_cols = [col[1] for col in conn.execute("PRAGMA table_info(encounters)").fetchall()]
        if 'guild_id' not in encounters_cols:
            conn.execute("ALTER TABLE encounters ADD COLUMN guild_id INTEGER DEFAULT 1")
            print("  ✓ Added guild_id to encounters")

        characters_cols = [col[1] for col in conn.execute("PRAGMA table_info(characters)").fetchall()]
        if 'guild_id' not in characters_cols:
            conn.execute("ALTER TABLE characters ADD COLUMN guild_id INTEGER DEFAULT 1")
            print("  ✓ Added guild_id to characters")

        # Check if character_metrics table exists
        try:
            metrics_cols = [col[1] for col in conn.execute("PRAGMA table_info(character_metrics)").fetchall()]
            if 'guild_id' not in metrics_cols:
                conn.execute("ALTER TABLE character_metrics ADD COLUMN guild_id INTEGER DEFAULT 1")
                print("  ✓ Added guild_id to character_metrics")
        except sqlite3.OperationalError:
            print("  - character_metrics table not found, skipping")

        # Check if log_files table exists
        try:
            log_files_cols = [col[1] for col in conn.execute("PRAGMA table_info(log_files)").fetchall()]
            if 'guild_id' not in log_files_cols:
                conn.execute("ALTER TABLE log_files ADD COLUMN guild_id INTEGER DEFAULT 1")
                print("  ✓ Added guild_id to log_files")
        except sqlite3.OperationalError:
            print("  - log_files table not found, skipping")

        # 5. Create foreign key constraints (for new data)
        print("Setting up foreign key constraints...")
        conn.execute("PRAGMA foreign_keys = ON")

        # 6. Create guild-optimized indexes
        print("Creating guild-optimized indexes...")

        indexes = [
            ("idx_encounters_guild_start", "encounters", "guild_id, start_time DESC"),
            ("idx_encounters_guild_boss", "encounters", "guild_id, boss_name"),
            ("idx_encounters_guild_instance", "encounters", "guild_id, instance_name"),
            ("idx_encounters_guild_type_difficulty", "encounters", "guild_id, encounter_type, difficulty"),
            ("idx_characters_guild_name", "characters", "guild_id, name"),
            ("idx_characters_guild_class", "characters", "guild_id, class"),
            ("idx_characters_guild_class_spec", "characters", "guild_id, class, spec"),
        ]

        for idx_name, table, columns in indexes:
            try:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})")
                print(f"  ✓ Created {idx_name}")
            except sqlite3.OperationalError as e:
                print(f"  - Failed to create {idx_name}: {e}")

        # Try to create character_metrics indexes if table exists
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_guild_encounter ON character_metrics(guild_id, encounter_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_guild_character ON character_metrics(guild_id, character_id)")
            print("  ✓ Created character_metrics indexes")
        except sqlite3.OperationalError:
            print("  - character_metrics indexes skipped (table not found)")

        # 7. Update metadata table
        print("Updating schema version...")
        conn.execute("""
            INSERT OR REPLACE INTO metadata (key, value, updated_at)
            VALUES ('schema_version', '2', CURRENT_TIMESTAMP)
        """)

        # 8. Update statistics
        encounter_count = conn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
        character_count = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]

        print("Migration statistics:")
        print(f"  - Encounters migrated: {encounter_count:,}")
        print(f"  - Characters migrated: {character_count:,}")
        print(f"  - All data assigned to Default Guild (ID: 1)")

        # 9. Commit transaction
        conn.execute("COMMIT")
        print("Migration completed successfully!")

        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        try:
            conn.execute("ROLLBACK")
            print("Changes rolled back")
        except:
            pass
        return False

    finally:
        conn.close()

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "./data/combat_logs.db"

    print("=== Combat Log Parser v1 → v2 Migration ===")
    print(f"Target database: {db_path}")

    # Confirm migration
    confirm = input("Proceed with migration? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Migration cancelled")
        sys.exit(0)

    start_time = time.time()
    success = migrate_database(db_path)
    end_time = time.time()

    print(f"\nMigration completed in {end_time - start_time:.2f} seconds")

    if success:
        print("✅ Migration successful")
        sys.exit(0)
    else:
        print("❌ Migration failed")
        sys.exit(1)
```

#### Run Migration

```bash
# Make migration script executable
chmod +x migrate_to_v2.py

# Run migration
python migrate_to_v2.py ./data/combat_logs.db

# Alternative: Use the built-in migration
python -c "
from src.database.schema import DatabaseManager
db = DatabaseManager('./data/combat_logs.db')
db._migrate_to_v2_guilds()
print('Migration completed via DatabaseManager')
"
```

### 3. Update Configuration

#### Update Environment Variables

```bash
# Update .env file
cat >> .env << EOF

# Guild System Configuration (v2)
DEFAULT_GUILD_ID=1
DEFAULT_GUILD_NAME="Default Guild"
ENABLE_GUILD_ISOLATION=true
GUILD_CACHE_TTL=3600

# Migration Settings
SCHEMA_VERSION=2
MIGRATION_DATE=$(date +%Y-%m-%d)
EOF
```

#### Update API Keys

```python
# update_api_keys.py
from src.api.auth import auth_manager

# Update default development key with guild context
print("Updating API keys with guild context...")

# The default key should already be updated, but verify
stats = auth_manager.get_all_stats()
print(f"API keys configured: {stats['active_api_keys']}")
print(f"Guild-enabled keys: {len([k for k in auth_manager._api_keys.values() if k.guild_id])}")

# Generate additional guild-specific keys if needed
for guild_id, guild_name in [(1, "Default Guild")]:
    key_id, api_key = auth_manager.generate_api_key(
        client_id=f"guild_{guild_id}_main",
        description=f"Main API key for {guild_name}",
        guild_id=guild_id,
        guild_name=guild_name,
        permissions={"stream", "query", "upload"},
        events_per_minute=15000,
        max_connections=10
    )
    print(f"Generated key for {guild_name}: {api_key}")
```

## Post-Migration Verification

### 1. Database Integrity

#### Schema Verification

```sql
-- Verify schema version
SELECT key, value FROM metadata WHERE key = 'schema_version';

-- Check guilds table
SELECT COUNT(*) as guild_count FROM guilds;
SELECT * FROM guilds;

-- Verify foreign key columns exist
PRAGMA table_info(encounters);
PRAGMA table_info(characters);

-- Check data integrity
SELECT COUNT(*) as encounters_with_guild FROM encounters WHERE guild_id IS NOT NULL;
SELECT COUNT(*) as characters_with_guild FROM characters WHERE guild_id IS NOT NULL;

-- Verify foreign key relationships
SELECT COUNT(*) as orphaned_encounters FROM encounters e
LEFT JOIN guilds g ON e.guild_id = g.guild_id
WHERE g.guild_id IS NULL;
```

#### Index Verification

```sql
-- Check index creation
SELECT name, sql FROM sqlite_master
WHERE type = 'index'
AND name LIKE '%guild%'
ORDER BY name;

-- Test index usage
EXPLAIN QUERY PLAN
SELECT * FROM encounters
WHERE guild_id = 1
ORDER BY start_time DESC
LIMIT 10;
```

### 2. Data Validation

#### Record Counts

```bash
# Compare pre and post migration counts
python -c "
import sqlite3

# Connect to backup and current database
backup_conn = sqlite3.connect('./migration_final_backup.db')
current_conn = sqlite3.connect('./data/combat_logs.db')

# Compare counts
backup_encounters = backup_conn.execute('SELECT COUNT(*) FROM encounters').fetchone()[0]
current_encounters = current_conn.execute('SELECT COUNT(*) FROM encounters').fetchone()[0]

backup_characters = backup_conn.execute('SELECT COUNT(*) FROM characters').fetchone()[0]
current_characters = current_conn.execute('SELECT COUNT(*) FROM characters').fetchone()[0]

print('Migration Verification:')
print(f'Encounters - Before: {backup_encounters:,}, After: {current_encounters:,}')
print(f'Characters - Before: {backup_characters:,}, After: {current_characters:,}')

if backup_encounters == current_encounters and backup_characters == current_characters:
    print('✅ All records preserved')
else:
    print('❌ Record count mismatch detected')

backup_conn.close()
current_conn.close()
"
```

#### Data Sampling

```sql
-- Sample data verification
SELECT
    guild_id,
    COUNT(*) as encounter_count,
    MIN(start_time) as oldest,
    MAX(start_time) as newest
FROM encounters
GROUP BY guild_id;

-- Verify specific encounters
SELECT encounter_id, boss_name, instance_name, guild_id
FROM encounters
ORDER BY start_time DESC
LIMIT 10;
```

### 3. Functional Testing

#### API Testing

```bash
# Test API endpoints with guild context
export API_KEY="dev_key_12345"

# Test encounter retrieval
curl -H "Authorization: Bearer $API_KEY" \
     "http://localhost:8000/api/v1/encounters?limit=5"

# Test guild-specific queries
curl -H "Authorization: Bearer $API_KEY" \
     "http://localhost:8000/api/v1/encounters/stats"

# Test upload endpoint
curl -X POST \
     -H "Authorization: Bearer $API_KEY" \
     -F "file=@examples/WoWCombatLog-091925_190638.txt" \
     "http://localhost:8000/api/v1/logs/upload"
```

#### CLI Testing

```bash
# Test CLI with guild parameters
python -m src.cli parse examples/WoWCombatLog-091925_190638.txt --guild-id 1

# Test analysis
python -m src.cli analyze examples/WoWCombatLog-091925_190638.txt --guild-name "Default Guild"

# Test without guild parameters (should use defaults)
python -m src.cli parse examples/WoWCombatLog-091925_190638.txt
```

#### WebSocket Testing

```python
# test_websocket_migration.py
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws"
    headers = {"Authorization": "Bearer dev_key_12345"}

    try:
        async with websockets.connect(uri, extra_headers=headers) as websocket:
            # Should receive welcome message with guild info
            welcome = await websocket.recv()
            message = json.loads(welcome)

            print(f"Welcome message: {message}")
            print(f"Guild context: {message.get('guild_name', 'Not found')}")

            if message.get("guild_id") == 1:
                print("✅ WebSocket guild context working")
            else:
                print("❌ WebSocket guild context missing")

    except Exception as e:
        print(f"WebSocket test failed: {e}")

# Run test
asyncio.run(test_websocket())
```

### 4. Performance Verification

#### Query Performance

```python
# test_performance.py
import time
import sqlite3

def test_query_performance():
    conn = sqlite3.connect('./data/combat_logs.db')

    # Test guild-filtered queries
    start = time.time()
    encounters = conn.execute("""
        SELECT * FROM encounters
        WHERE guild_id = 1
        ORDER BY start_time DESC
        LIMIT 100
    """).fetchall()
    guild_query_time = time.time() - start

    # Test unfiltered query for comparison
    start = time.time()
    all_encounters = conn.execute("""
        SELECT * FROM encounters
        ORDER BY start_time DESC
        LIMIT 100
    """).fetchall()
    unfiltered_time = time.time() - start

    print(f"Guild-filtered query: {guild_query_time*1000:.2f}ms")
    print(f"Unfiltered query: {unfiltered_time*1000:.2f}ms")

    if guild_query_time < 0.1:  # Should be under 100ms
        print("✅ Query performance acceptable")
    else:
        print("⚠️ Query performance may need optimization")

    conn.close()

test_query_performance()
```

## Rollback Procedures

### 1. Emergency Rollback

#### Immediate Rollback

```bash
#!/bin/bash
# emergency_rollback.sh

echo "EMERGENCY ROLLBACK - Restoring v1 database"

# Stop current services
pkill -f "python -m src.api.app" || true

# Restore backup database
if [ -f "./migration_final_backup.db" ]; then
    cp "./migration_final_backup.db" "./data/combat_logs.db"
    echo "✅ Database restored from backup"
else
    echo "❌ Backup file not found: ./migration_final_backup.db"
    exit 1
fi

# Verify restoration
python -c "
import sqlite3
conn = sqlite3.connect('./data/combat_logs.db')
try:
    version = conn.execute('SELECT value FROM metadata WHERE key = \"schema_version\"').fetchone()
    print(f'Restored schema version: {version[0] if version else \"1\"}')
except:
    print('Schema version: 1 (pre-migration)')
conn.close()
"

echo "Rollback completed. Restart services manually."
```

### 2. Selective Rollback

#### Rollback Guild Schema Only

```sql
-- Remove guild-specific columns (careful!)
-- Note: SQLite doesn't support DROP COLUMN directly

-- Create backup of current data
CREATE TABLE encounters_backup AS SELECT * FROM encounters;
CREATE TABLE characters_backup AS SELECT * FROM characters;

-- Recreate tables without guild_id (if needed)
-- This is complex and should only be done in emergency
```

### 3. Validation After Rollback

```bash
# Verify rollback success
python -c "
import sqlite3
conn = sqlite3.connect('./data/combat_logs.db')

# Check if guild columns exist
try:
    conn.execute('SELECT guild_id FROM encounters LIMIT 1')
    print('Guild columns still present')
except:
    print('Guild columns removed - rollback successful')

# Verify data integrity
encounters = conn.execute('SELECT COUNT(*) FROM encounters').fetchone()[0]
characters = conn.execute('SELECT COUNT(*) FROM characters').fetchone()[0]
print(f'Data integrity - Encounters: {encounters:,}, Characters: {characters:,}')

conn.close()
"
```

## Troubleshooting

### 1. Common Migration Issues

#### Migration Fails with "Column Already Exists"

**Problem**: ALTER TABLE fails because guild_id column already exists

**Solution**:

```sql
-- Check if column exists before adding
SELECT name FROM pragma_table_info('encounters') WHERE name = 'guild_id';

-- If exists, skip ALTER TABLE or use IF NOT EXISTS
```

#### Foreign Key Constraint Failures

**Problem**: Cannot add foreign key constraints to existing data

**Solution**:

```sql
-- Disable foreign keys during migration
PRAGMA foreign_keys = OFF;

-- Perform migration
-- ...

-- Re-enable foreign keys
PRAGMA foreign_keys = ON;

-- Validate constraints
PRAGMA foreign_key_check;
```

#### Index Creation Failures

**Problem**: Index creation fails due to existing indexes

**Solution**:

```sql
-- Drop existing conflicting indexes
DROP INDEX IF EXISTS idx_encounters_start_time;

-- Create new guild-optimized indexes
CREATE INDEX idx_encounters_guild_start ON encounters(guild_id, start_time DESC);
```

### 2. Performance Issues

#### Slow Queries After Migration

**Problem**: Queries slower than expected after adding guild_id

**Diagnostic**:

```sql
-- Check query execution plan
EXPLAIN QUERY PLAN
SELECT * FROM encounters
WHERE guild_id = 1
ORDER BY start_time DESC;

-- Should show: USING INDEX idx_encounters_guild_start
```

**Solution**:

```sql
-- Rebuild indexes
REINDEX idx_encounters_guild_start;

-- Update table statistics
ANALYZE encounters;
ANALYZE characters;
```

#### High Memory Usage

**Problem**: Migration process uses excessive memory

**Solution**:

```python
# Process migration in batches
batch_size = 10000
offset = 0

while True:
    rows = conn.execute(f"""
        SELECT encounter_id FROM encounters
        ORDER BY encounter_id
        LIMIT {batch_size} OFFSET {offset}
    """).fetchall()

    if not rows:
        break

    # Process batch
    encounter_ids = [row[0] for row in rows]
    conn.execute(f"""
        UPDATE encounters
        SET guild_id = 1
        WHERE encounter_id IN ({','.join('?' * len(encounter_ids))})
    """, encounter_ids)

    offset += batch_size
    print(f"Processed {offset} encounters...")
```

### 3. API Issues

#### Authentication Failures

**Problem**: API keys don't work after migration

**Diagnostic**:

```python
from src.api.auth import auth_manager
stats = auth_manager.get_all_stats()
print(f"Active API keys: {stats['active_api_keys']}")

# Check specific key
auth_response = auth_manager.authenticate_api_key("dev_key_12345")
print(f"Auth result: {auth_response}")
```

**Solution**:

```python
# Regenerate API keys with guild context
key_id, new_key = auth_manager.generate_api_key(
    client_id="migrated_client",
    description="Post-migration API key",
    guild_id=1,
    guild_name="Default Guild"
)
```

#### Missing Guild Context

**Problem**: API responses missing guild information

**Solution**:

```python
# Verify authentication dependency
from src.api.v1.dependencies import get_authenticated_user

# Check if AuthResponse includes guild fields
# Should have: guild_id, guild_name
```

### 4. Data Validation Issues

#### Orphaned Records

**Problem**: Records exist without valid guild_id

**Diagnostic**:

```sql
-- Find orphaned encounters
SELECT COUNT(*) FROM encounters e
LEFT JOIN guilds g ON e.guild_id = g.guild_id
WHERE g.guild_id IS NULL;

-- Find encounters with NULL guild_id
SELECT COUNT(*) FROM encounters WHERE guild_id IS NULL;
```

**Solution**:

```sql
-- Assign orphaned records to default guild
UPDATE encounters SET guild_id = 1 WHERE guild_id IS NULL;
UPDATE characters SET guild_id = 1 WHERE guild_id IS NULL;

-- Remove truly orphaned records (last resort)
DELETE FROM encounters WHERE guild_id NOT IN (SELECT guild_id FROM guilds);
```

## Performance Optimization

### 1. Post-Migration Optimization

#### Rebuild Statistics

```sql
-- Update table statistics for query optimizer
ANALYZE encounters;
ANALYZE characters;
ANALYZE character_metrics;
ANALYZE guilds;

-- Vacuum database to optimize storage
VACUUM;
```

#### Index Optimization

```sql
-- Verify index usage
SELECT name, sql FROM sqlite_master
WHERE type = 'index'
AND tbl_name IN ('encounters', 'characters', 'character_metrics')
ORDER BY name;

-- Consider additional indexes based on usage patterns
CREATE INDEX IF NOT EXISTS idx_encounters_guild_difficulty_boss
ON encounters(guild_id, difficulty, boss_name);

CREATE INDEX IF NOT EXISTS idx_characters_guild_last_seen
ON characters(guild_id, last_seen DESC);
```

### 2. Cache Optimization

#### Guild-Aware Caching

```python
# Update cache keys to include guild context
def get_cache_key(base_key: str, guild_id: int) -> str:
    return f"{base_key}:guild:{guild_id}"

# Example usage
cache_key = get_cache_key("encounters:recent", guild_id=1)
```

### 3. Query Optimization

#### Guild-First Query Patterns

```sql
-- Always start WHERE clauses with guild_id
SELECT * FROM encounters
WHERE guild_id = ?
AND boss_name = ?
ORDER BY start_time DESC;

-- Use guild_id in JOINs
SELECT e.*, c.name, c.class
FROM encounters e
JOIN characters c ON e.guild_id = c.guild_id
WHERE e.guild_id = ?;
```

## Best Practices

### 1. Migration Planning

- **Test First**: Always test migration on a copy of production data
- **Monitor Resources**: Track CPU, memory, and disk usage during migration
- **Batch Processing**: For large datasets, process in batches to avoid timeouts
- **Communication**: Notify all stakeholders of downtime window

### 2. Post-Migration

- **Monitor Performance**: Track query response times for the first week
- **Update Documentation**: Ensure all API docs reflect guild requirements
- **Train Users**: Update any training materials for new guild parameters
- **Gradual Rollout**: Consider enabling guild features gradually

### 3. Ongoing Maintenance

- **Regular Backups**: Implement automated backups with guild context
- **Performance Monitoring**: Track per-guild performance metrics
- **Capacity Planning**: Monitor guild growth and resource usage
- **Version Control**: Document all future schema changes

---

## Support and Resources

- **Guild Management**: See [GUILD_MANAGEMENT.md](GUILD_MANAGEMENT.md)
- **Deployment Guide**: See [DEPLOYMENT.md](DEPLOYMENT.md)
- **API Reference**: See [API_REFERENCE.md](API_REFERENCE.md)
- **Performance Tuning**: See [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md)

For migration support, contact the development team with:

- Backup verification results
- Migration error logs
- Database size and record counts
- System specifications

**Important**: Keep all backup files until you've verified the migration success and system stability for at least one week.
