# Existing Schema Integration Guide

This guide explains how to use the `ExistingSchemaAdapter` to integrate the combat log parser with the existing lootbong database schema.

## Overview

The parser was originally designed to create its own database tables:
- `encounters`
- `characters`
- `guilds`
- `character_metrics`
- `spell_summary`

The existing lootbong database has a more comprehensive schema with:
- `combat_encounters`
- `combat_performances`
- `characters`
- `guilds`
- Many additional tables

The `ExistingSchemaAdapter` bridges this gap by mapping parser expectations to the existing schema.

## Key Mappings

| Parser Table | Database Table | Notes |
|--------------|----------------|--------|
| `encounters` | `combat_encounters` | UUID → string conversion |
| `character_metrics` | `combat_performances` | Direct mapping with field name changes |
| `characters` | `characters` + `combat_performances` | Combined data sources |
| `guilds` | `guilds` | Column name mapping |
| `spell_summary` | N/A | Not implemented (optional) |

## Usage

### 1. Initialize the Adapter

```python
from database.existing_schema_adapter import ExistingSchemaAdapter

# Use with existing database connection
adapter = ExistingSchemaAdapter(db_connection)
```

### 2. Replace Direct Database Calls

**Before (Direct Schema):**
```python
encounters = db.execute("SELECT * FROM encounters WHERE guild_id = ?", (guild_id,))
```

**After (With Adapter):**
```python
encounters = adapter.get_encounters(guild_id=guild_id, limit=50)
```

### 3. Integration with Query API

Replace the database manager in your query classes:

```python
class QueryAPI:
    def __init__(self, db_connection):
        # Use adapter instead of direct database access
        self.adapter = ExistingSchemaAdapter(db_connection)

    def get_recent_encounters(self, limit=10):
        return self.adapter.get_encounters(limit=limit)

    def get_character_metrics(self, encounter_id, character_name=None, guild_id=None):
        return self.adapter.get_character_metrics(encounter_id, guild_id, character_name)
```

## Data Type Conversions

### UUID Handling
- **Database**: Uses UUID type for primary keys
- **Parser**: Expects string IDs
- **Adapter**: Automatically converts UUIDs ↔ strings

```python
# Database: id = UUID('550e8400-e29b-41d4-a716-446655440000')
# Parser gets: encounter_id = '550e8400-e29b-41d4-a716-446655440000'
```

### Timestamp Handling
- **Database**: PostgreSQL TIMESTAMP
- **Parser**: Unix timestamps (float)
- **Adapter**: Converts using `.timestamp()` method

```python
# Database: start_time = datetime(2024, 1, 1, 20, 0, 0)
# Parser gets: start_time = 1704135600.0
```

### Duration Conversion
- **Database**: Stores durations in milliseconds
- **Parser**: Expects durations in seconds
- **Adapter**: Automatically converts ms → seconds

```python
# Database: duration_ms = 300000
# Parser gets: combat_length = 300.0
```

## Field Mappings

### Encounters
| Parser Field | Database Field | Conversion |
|--------------|----------------|------------|
| `encounter_id` | `id` | UUID → string |
| `boss_name` | `encounter_name` | Direct |
| `combat_length` | `duration_ms` | ms → seconds |
| `raid_size` | `player_count` | Direct |

### Character Metrics
| Parser Field | Database Field | Conversion |
|--------------|----------------|------------|
| `character_guid` | Generated | `name-server` format |
| `class_name` | `class` | Direct |
| `spec_name` | `spec` | Direct |
| `time_alive` | `active_time_ms` | ms → seconds |
| `combat_time` | `active_time_ms` | ms → seconds |

### Characters
| Parser Field | Database Field | Source |
|--------------|----------------|---------|
| `character_id` | `id` | `characters` table |
| `character_guid` | Generated | `name-server` format |
| `encounter_count` | Calculated | `combat_performances` count |
| `last_seen` | Calculated | Max `combat_performances.created_at` |

## Error Handling

The adapter includes comprehensive error handling:

```python
try:
    encounters = adapter.get_encounters(guild_id=invalid_guild)
except Exception as e:
    logger.error(f"Failed to get encounters: {e}")
    encounters = []  # Graceful fallback
```

## Performance Considerations

1. **Caching**: Consider implementing query caching for frequently accessed data
2. **Indexes**: Ensure proper indexes exist on `guild_id`, `encounter_id`, `character_id`
3. **Batch Queries**: Use limits and offsets for large datasets
4. **Connection Pooling**: Reuse database connections

## Testing

Run the test script to verify functionality:

```bash
cd parser/examples
python test_existing_schema_adapter.py
```

This will test all adapter methods with mock data.

## Migration Strategy

1. **Phase 1**: Deploy adapter alongside existing parser
2. **Phase 2**: Update parser imports to use adapter
3. **Phase 3**: Remove old schema creation code
4. **Phase 4**: Add monitoring and optimization

## Limitations

1. **Spell Summary**: Not implemented (parser table `spell_summary` has no equivalent)
2. **Event Blocks**: Not implemented (compressed event storage not needed)
3. **Read-Only**: Adapter is primarily for reading existing data
4. **Guild Schema**: Some fields default to placeholder values

## Troubleshooting

### Common Issues

**UUID Conversion Errors:**
```python
# Check if string is valid UUID
if not adapter.validate_encounter_id(encounter_id):
    logger.error(f"Invalid encounter ID: {encounter_id}")
```

**Missing Guild:**
```python
# Verify guild exists before querying
if not adapter.validate_guild_id(guild_id):
    logger.error(f"Guild {guild_id} not found")
```

**Empty Results:**
```python
# Always check for empty results
encounters = adapter.get_encounters(guild_id=guild_id)
if not encounters:
    logger.warning("No encounters found")
```

### Debugging

Enable detailed logging:

```python
import logging
logging.getLogger('database.existing_schema_adapter').setLevel(logging.DEBUG)
```

This will show all SQL queries and parameter values.

## Future Enhancements

1. **Write Operations**: Add methods to insert/update data
2. **Advanced Filtering**: Add more sophisticated query filters
3. **Aggregation**: Add summary and statistics methods
4. **Caching Layer**: Implement intelligent query caching
5. **Event Streaming**: Add real-time event streaming support