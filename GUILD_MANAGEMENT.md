# 🏰 Guild Management Guide

This guide covers the complete guild management system for the multi-tenant combat log parser. Each guild operates in complete isolation with dedicated data storage, API keys, and access controls.

## 📋 Table of Contents

- [Overview](#overview)
- [Guild Creation and Setup](#guild-creation-and-setup)
- [API Key Management](#api-key-management)
- [Data Isolation](#data-isolation)
- [Administration](#administration)
- [Migration and Maintenance](#migration-and-maintenance)
- [Troubleshooting](#troubleshooting)

## Overview

### Multi-Tenant Architecture

The parser implements a guild-first multi-tenant system where:

- **Complete Isolation**: Each guild's data is fully separated
- **Dedicated Storage**: Guild-specific encounters, characters, and metrics
- **Scoped Authentication**: API keys are tied to specific guilds
- **Performance Optimized**: Guild-first indexing for sub-100ms queries
- **Scalable Design**: Supports 100+ concurrent guilds efficiently

### Guild Hierarchy

```
Combat Log Parser
├── Guild 1 (ID: 1) - "Default Guild"
│   ├── Encounters
│   ├── Characters
│   ├── Metrics
│   └── API Keys
├── Guild 2 (ID: 2) - "Loothing"
│   ├── Encounters
│   ├── Characters
│   ├── Metrics
│   └── API Keys
└── Guild N...
```

## Guild Creation and Setup

### 1. Database Guild Registration

Guilds are stored in the `guilds` table with the following schema:

```sql
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
);
```

### 2. Creating a New Guild

#### Via Direct Database Insert

```sql
INSERT INTO guilds (guild_name, server, region, faction)
VALUES ('Your Guild Name', 'Stormrage', 'US', 'Alliance');
```

#### Via CLI (Future Enhancement)

```bash
python -m src.cli guild create \
    --name "Your Guild Name" \
    --server "Stormrage" \
    --region "US" \
    --faction "Alliance"
```

### 3. Guild Configuration

#### Required Information

- **Guild Name**: Must be unique per server/region combination
- **Server**: WoW realm name (e.g., "Stormrage", "Area-52")
- **Region**: Game region ("US", "EU", "KR", "TW", "CN")
- **Faction**: "Alliance" or "Horde"

#### Optional Metadata

- **Description**: Guild description or notes
- **Contact Info**: Guild leader contact information
- **Timezone**: Primary raid timezone
- **Raid Schedule**: When the guild typically raids

### 4. Default Guild

The system maintains a default guild (ID: 1) for:

- **Legacy Data**: Existing encounters from pre-guild system
- **Development**: Testing and development purposes
- **Fallback**: When guild_id is not specified in CLI operations

## API Key Management

### 1. Guild-Scoped API Keys

Each API key is associated with a specific guild and provides:

- **Guild-Only Access**: Cannot access other guild's data
- **Rate Limiting**: Per-guild rate limits (configurable)
- **Permission Scoping**: Granular permissions within guild context
- **Usage Tracking**: Guild-specific usage analytics

### 2. Creating Guild API Keys

#### Via Authentication Manager

```python
from src.api.auth import auth_manager

# Generate API key for guild
key_id, api_key = auth_manager.generate_api_key(
    client_id="your_guild_client",
    description="Main guild API key",
    guild_id=2,
    guild_name="Loothing",
    permissions={"stream", "query", "upload"},
    events_per_minute=15000,
    max_connections=10
)

print(f"API Key: {api_key}")
print(f"Key ID: {key_id}")
```

#### Default Development Key

For development and testing, a default key is available:

```
API Key: dev_key_12345
Guild: Default Guild (ID: 1)
Rate Limits: 20,000 events/minute, 10 connections
```

### 3. API Key Configuration

#### Permission Types

- **`stream`**: Access to WebSocket streaming endpoints
- **`query`**: Read access to encounters and statistics
- **`upload`**: Upload combat log files
- **`admin`**: Guild administration (manage API keys, settings)

#### Rate Limits

Configure per-guild rate limits based on usage patterns:

```python
# High-volume guild
events_per_minute=20000
max_connections=15

# Casual guild
events_per_minute=5000
max_connections=5
```

### 4. API Key Security

#### Best Practices

- **Secure Storage**: Store API keys securely, never in version control
- **Key Rotation**: Regularly rotate API keys (recommended: monthly)
- **Minimal Permissions**: Grant only necessary permissions
- **Monitor Usage**: Track API key usage for anomalies

#### Revoking Keys

```python
# Revoke an API key
auth_manager.revoke_api_key("key_id_here")
```

## Data Isolation

### 1. Guild-Level Isolation

All data tables include `guild_id` foreign keys:

```sql
-- Encounters table
ALTER TABLE encounters ADD COLUMN guild_id INTEGER REFERENCES guilds(guild_id);

-- Characters table
ALTER TABLE characters ADD COLUMN guild_id INTEGER REFERENCES guilds(guild_id);

-- Character metrics table
ALTER TABLE character_metrics ADD COLUMN guild_id INTEGER REFERENCES guilds(guild_id);

-- Log files table
ALTER TABLE log_files ADD COLUMN guild_id INTEGER REFERENCES guilds(guild_id);
```

### 2. Query Isolation

All queries automatically filter by guild_id:

```python
# Example: Get encounters for specific guild
def get_encounters(self, guild_id: int, limit: int = 50):
    return self.db.execute("""
        SELECT * FROM encounters
        WHERE guild_id = ?
        ORDER BY start_time DESC
        LIMIT ?
    """, (guild_id, limit)).fetchall()
```

### 3. Index Strategy

Guild-first composite indexes ensure optimal performance:

```sql
-- Primary guild indexes
CREATE INDEX idx_encounters_guild_start ON encounters(guild_id, start_time DESC);
CREATE INDEX idx_characters_guild_name ON characters(guild_id, name);
CREATE INDEX idx_metrics_guild_encounter ON character_metrics(guild_id, encounter_id);

-- Performance indexes
CREATE INDEX idx_encounters_guild_type_difficulty ON encounters(guild_id, encounter_type, difficulty);
CREATE INDEX idx_characters_guild_class_spec ON characters(guild_id, class, spec);
```

### 4. Cross-Guild Access Prevention

The system prevents cross-guild data access through:

- **API Authentication**: Guild-scoped API keys
- **Query Filtering**: Automatic guild_id filtering in all queries
- **WebSocket Isolation**: Guild-validated streaming sessions
- **Cache Separation**: Guild-aware cache keys

## Administration

### 1. Guild Statistics

#### Database Queries

```sql
-- Guild overview
SELECT
    g.guild_id,
    g.guild_name,
    g.server,
    g.region,
    COUNT(DISTINCT e.encounter_id) as total_encounters,
    COUNT(DISTINCT c.character_id) as total_characters,
    MAX(e.start_time) as last_activity
FROM guilds g
LEFT JOIN encounters e ON g.guild_id = e.guild_id
LEFT JOIN characters c ON g.guild_id = c.guild_id
GROUP BY g.guild_id;

-- Storage usage per guild
SELECT
    guild_id,
    COUNT(*) as encounter_count,
    SUM(duration_ms) as total_combat_time,
    AVG(duration_ms) as avg_encounter_duration
FROM encounters
GROUP BY guild_id;
```

#### API Endpoints (Future)

```bash
# Get guild statistics
GET /api/v1/admin/guilds/{guild_id}/stats

# List all guilds
GET /api/v1/admin/guilds

# Guild activity report
GET /api/v1/admin/guilds/{guild_id}/activity?days=30
```

### 2. Guild Maintenance

#### Data Cleanup

```sql
-- Remove old encounters (older than 1 year)
DELETE FROM encounters
WHERE guild_id = ?
AND start_time < datetime('now', '-1 year');

-- Archive inactive characters
UPDATE characters
SET is_active = FALSE
WHERE guild_id = ?
AND last_seen < datetime('now', '-90 days');
```

#### Storage Optimization

```sql
-- Rebuild indexes for guild
REINDEX idx_encounters_guild_start;
REINDEX idx_characters_guild_name;

-- Analyze tables for query optimization
ANALYZE encounters;
ANALYZE characters;
ANALYZE character_metrics;
```

### 3. Guild Migration

#### Moving Encounters Between Guilds

```sql
-- Transfer encounters (use with caution)
UPDATE encounters
SET guild_id = ?
WHERE encounter_id IN (SELECT encounter_id FROM log_transfers WHERE transfer_id = ?);

-- Update related character data
UPDATE characters
SET guild_id = ?
WHERE character_id IN (
    SELECT DISTINCT character_id
    FROM character_metrics cm
    JOIN encounters e ON cm.encounter_id = e.encounter_id
    WHERE e.guild_id = ?
);
```

### 4. Cross-Guild Operations

Only administrators should perform cross-guild operations:

#### Global Statistics

```python
def get_global_stats():
    """Get statistics across all guilds (admin only)."""
    return db.execute("""
        SELECT
            COUNT(DISTINCT guild_id) as total_guilds,
            COUNT(DISTINCT encounter_id) as total_encounters,
            COUNT(DISTINCT character_id) as total_characters,
            SUM(CASE WHEN start_time > datetime('now', '-7 days') THEN 1 ELSE 0 END) as recent_encounters
        FROM encounters
    """).fetchone()
```

#### Guild Comparison

```python
def compare_guilds(guild_ids: List[int]):
    """Compare performance metrics between guilds (admin only)."""
    return db.execute("""
        SELECT
            guild_id,
            COUNT(*) as encounter_count,
            AVG(duration_ms) as avg_duration,
            COUNT(DISTINCT boss_name) as unique_bosses
        FROM encounters
        WHERE guild_id IN ({})
        GROUP BY guild_id
    """.format(','.join('?' * len(guild_ids))), guild_ids).fetchall()
```

## Migration and Maintenance

### 1. Schema Migration (v1 → v2)

The migration from single-tenant to multi-tenant involves:

#### Pre-Migration Checklist

1. **Backup Database**: Create full backup before migration
2. **Stop Services**: Halt all API and streaming services
3. **Verify Data Integrity**: Run consistency checks
4. **Plan Downtime**: Estimate migration time based on data size

#### Migration Steps

```python
def migrate_to_guilds():
    """Migrate from v1 (single-tenant) to v2 (multi-tenant)."""

    # 1. Create guilds table
    db.execute("""CREATE TABLE IF NOT EXISTS guilds ...""")

    # 2. Create default guild
    db.execute("""
        INSERT OR IGNORE INTO guilds (guild_id, guild_name, server, region, faction)
        VALUES (1, 'Default Guild', 'Unknown', 'US', 'Alliance')
    """)

    # 3. Add guild_id columns
    db.execute("ALTER TABLE encounters ADD COLUMN guild_id INTEGER DEFAULT 1")
    db.execute("ALTER TABLE characters ADD COLUMN guild_id INTEGER DEFAULT 1")
    db.execute("ALTER TABLE character_metrics ADD COLUMN guild_id INTEGER DEFAULT 1")
    db.execute("ALTER TABLE log_files ADD COLUMN guild_id INTEGER DEFAULT 1")

    # 4. Create indexes
    db.execute("CREATE INDEX idx_encounters_guild_start ON encounters(guild_id, start_time DESC)")
    # ... additional indexes

    # 5. Update schema version
    db.execute("UPDATE metadata SET value = '2' WHERE key = 'schema_version'")
```

#### Post-Migration Verification

```sql
-- Verify all encounters have guild_id
SELECT COUNT(*) FROM encounters WHERE guild_id IS NULL;

-- Check foreign key integrity
SELECT COUNT(*) FROM encounters e
LEFT JOIN guilds g ON e.guild_id = g.guild_id
WHERE g.guild_id IS NULL;

-- Verify index creation
SELECT name FROM sqlite_master
WHERE type = 'index'
AND name LIKE 'idx_%guild%';
```

### 2. Data Backup Strategies

#### Guild-Specific Backups

```bash
# Backup specific guild data
sqlite3 combat_logs.db "
SELECT * FROM encounters WHERE guild_id = 2;
SELECT * FROM characters WHERE guild_id = 2;
SELECT * FROM character_metrics cm
JOIN encounters e ON cm.encounter_id = e.encounter_id
WHERE e.guild_id = 2;
" > guild_2_backup.sql
```

#### Full System Backup

```bash
# Complete database backup
sqlite3 combat_logs.db .backup backup_$(date +%Y%m%d_%H%M%S).db

# Compressed backup
sqlite3 combat_logs.db .backup /dev/stdout | gzip > backup_$(date +%Y%m%d).db.gz
```

### 3. Performance Monitoring

#### Guild-Specific Metrics

```python
def monitor_guild_performance(guild_id: int):
    """Monitor query performance for specific guild."""

    # Query execution time
    start_time = time.time()
    encounters = get_recent_encounters(guild_id, limit=100)
    query_time = time.time() - start_time

    # Cache hit rate
    cache_stats = get_cache_stats(f"guild:{guild_id}")

    return {
        "guild_id": guild_id,
        "query_time_ms": query_time * 1000,
        "cache_hit_rate": cache_stats["hit_rate"],
        "active_encounters": len(encounters)
    }
```

#### Index Effectiveness

```sql
-- Check index usage
EXPLAIN QUERY PLAN
SELECT * FROM encounters
WHERE guild_id = 1
ORDER BY start_time DESC
LIMIT 50;

-- Should show: USING INDEX idx_encounters_guild_start
```

## Troubleshooting

### 1. Common Issues

#### Guild Not Found

**Problem**: API key authentication fails with "Guild not found"

**Solution**:
```sql
-- Check if guild exists
SELECT * FROM guilds WHERE guild_id = ?;

-- Check API key guild association
SELECT ak.*, g.guild_name
FROM api_keys ak
LEFT JOIN guilds g ON ak.guild_id = g.guild_id
WHERE ak.key_id = ?;
```

#### Cross-Guild Data Access

**Problem**: User sees data from other guilds

**Solution**:
- Verify API key guild_id assignment
- Check query filtering logic
- Review cache key generation

#### Performance Degradation

**Problem**: Queries become slow after adding guild_id

**Solution**:
```sql
-- Rebuild indexes
REINDEX idx_encounters_guild_start;
REINDEX idx_characters_guild_name;

-- Update table statistics
ANALYZE encounters;
ANALYZE characters;

-- Check query plans
EXPLAIN QUERY PLAN SELECT ...
```

### 2. Debugging Commands

#### Guild Data Verification

```bash
# Check guild data integrity
python -m src.cli debug guild-integrity --guild-id 2

# Verify guild isolation
python -m src.cli debug cross-guild-check --guild-id 2

# Performance analysis
python -m src.cli debug guild-performance --guild-id 2 --duration 24h
```

#### Database Queries

```sql
-- Find orphaned encounters
SELECT encounter_id FROM encounters e
LEFT JOIN guilds g ON e.guild_id = g.guild_id
WHERE g.guild_id IS NULL;

-- Check data distribution
SELECT guild_id, COUNT(*) as encounter_count
FROM encounters
GROUP BY guild_id
ORDER BY encounter_count DESC;

-- Verify foreign keys
PRAGMA foreign_key_check;
```

### 3. Recovery Procedures

#### Restore Guild Data

```sql
-- Restore from backup
.restore guild_backup.db

-- Verify restoration
SELECT COUNT(*) FROM encounters WHERE guild_id = ?;
SELECT COUNT(*) FROM characters WHERE guild_id = ?;
```

#### Fix Guild Assignment

```sql
-- Reassign encounters to correct guild
UPDATE encounters
SET guild_id = ?
WHERE encounter_id IN (
    SELECT encounter_id FROM manual_guild_assignments
    WHERE target_guild_id = ?
);
```

## Best Practices

### 1. Guild Setup

- **Unique Naming**: Ensure guild names are unique within server/region
- **Consistent API Keys**: Use descriptive names for API key identification
- **Rate Limit Planning**: Set appropriate limits based on guild activity
- **Regular Backups**: Implement automated guild-specific backup schedules

### 2. Performance Optimization

- **Index Maintenance**: Regularly rebuild indexes for active guilds
- **Cache Strategy**: Implement guild-aware caching with appropriate TTL
- **Query Optimization**: Always include guild_id in WHERE clauses
- **Monitoring**: Track per-guild performance metrics

### 3. Security

- **Access Control**: Strictly enforce guild-based access controls
- **API Key Management**: Regular rotation and monitoring
- **Data Validation**: Validate guild_id in all operations
- **Audit Logging**: Track cross-guild operations and admin actions

### 4. Maintenance

- **Regular Cleanup**: Remove old encounter data based on guild policies
- **Storage Monitoring**: Track per-guild storage usage
- **Performance Reviews**: Monthly analysis of guild query performance
- **Capacity Planning**: Monitor guild growth and resource requirements

---

## Support

For guild management issues:

1. Check the [Migration Guide](MIGRATION_GUIDE.md) for upgrade procedures
2. Review [API Documentation](API_REFERENCE.md) for endpoint details
3. See [Performance Report](PERFORMANCE_REPORT.md) for optimization guides
4. Contact system administrators for cross-guild operations

**Next**: See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for detailed upgrade procedures.