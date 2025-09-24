# Existing Schema Database Adapter

This document describes the **ExistingSchemaAdapter** - a compatibility layer that allows the combat log parser to work with the existing lootbong database schema instead of creating its own tables.

## 🎯 Problem Solved

**Before**: Parser expected its own schema with tables like `encounters`, `characters`, `character_metrics`
**After**: Parser works seamlessly with existing `combat_encounters`, `combat_performances`, `characters`, `guilds` tables

## 📁 Files Created

### Core Adapter
- **`src/database/existing_schema_adapter.py`** - Main adapter class with all mapping logic
- **`src/config/existing_schema_config.py`** - Configuration management for adapter settings

### Documentation & Examples
- **`docs/existing_schema_integration.md`** - Comprehensive integration guide
- **`examples/test_existing_schema_adapter.py`** - Test script with mock data
- **`scripts/integrate_existing_schema.py`** - Integration helper script

## 🗺️ Schema Mapping

| Parser Expectation | Database Reality | Adapter Handling |
|-------------------|------------------|------------------|
| `encounters` table | `combat_encounters` table | ✅ Direct mapping with field conversion |
| `character_metrics` table | `combat_performances` table | ✅ Direct mapping with field conversion |
| `characters` table | `characters` + `combat_performances` | ✅ Combined data from both tables |
| `guilds` table | `guilds` table | ✅ Column name mapping |
| `spell_summary` table | No equivalent | ⚠️ Not implemented (optional) |

## 🔄 Key Conversions

### Data Type Conversions
- **UUIDs** → **Strings**: Database UUIDs converted to string format for parser
- **Timestamps** → **Unix Time**: PostgreSQL timestamps to Unix float timestamps
- **Milliseconds** → **Seconds**: Duration fields converted from ms to seconds
- **JSONB** → **Dict**: JSON fields properly deserialized

### Field Mappings
- `encounter_name` → `boss_name`
- `duration_ms` → `combat_length` (converted to seconds)
- `player_count` → `raid_size`
- `active_time_ms` → `time_alive` (converted to seconds)

## 🚀 Quick Start

### 1. Basic Usage

```python
from database.existing_schema_adapter import ExistingSchemaAdapter

# Initialize with your existing database connection
adapter = ExistingSchemaAdapter(db_connection)

# Use exactly like the parser expected
encounters = adapter.get_encounters(guild_id=1, limit=10)
characters = adapter.get_characters(guild_id=1)
metrics = adapter.get_character_metrics(encounter_id, guild_id=1)
```

### 2. Integration with Existing Parser

```python
# Replace direct database calls
# OLD: db.execute("SELECT * FROM encounters...")
# NEW: adapter.get_encounters(...)

class CombatLogParser:
    def __init__(self, db_connection):
        self.adapter = ExistingSchemaAdapter(db_connection)

    def get_recent_encounters(self, guild_id):
        return self.adapter.get_encounters(guild_id=guild_id, limit=50)
```

### 3. Configuration

```python
from config.existing_schema_config import create_adapter_from_config

# Create adapter with configuration
adapter = create_adapter_from_config(db_connection)
```

## 🧪 Testing

```bash
# Test the adapter with mock data
cd parser/examples
python test_existing_schema_adapter.py

# Validate environment and create integration examples
cd parser/scripts
python integrate_existing_schema.py --validate --create-example
```

## ⚙️ Environment Variables

Set these environment variables to configure the adapter:

```bash
# Core database settings (required)
DB_HOST=your-database-host
DB_NAME=loottracker
DB_USER=lootuser
DB_PASSWORD=your-password

# Adapter settings (optional)
PARSER_USE_EXISTING_SCHEMA=true
PARSER_SKIP_TABLE_CREATION=true
PARSER_DEFAULT_QUERY_LIMIT=50
PARSER_ENABLE_QUERY_CACHING=true
```

## 🎭 Adapter Methods

### Guild Operations
```python
guild = adapter.get_guild(guild_id)
guilds = adapter.get_guilds(limit=10, offset=0)
```

### Encounter Operations
```python
encounters = adapter.get_encounters(guild_id=1, limit=10)
encounter = adapter.get_encounter(encounter_id, guild_id=1)
```

### Character Operations
```python
characters = adapter.get_characters(guild_id=1, limit=10)
character = adapter.get_character_by_name("PlayerName", guild_id=1)
```

### Performance Metrics
```python
metrics = adapter.get_character_metrics(encounter_id, guild_id=1)
top_dps = adapter.get_top_performers('dps', guild_id=1, limit=10)
```

### Database Management
```python
stats = adapter.get_database_stats()
health = adapter.health_check()
```

## 🔍 Error Handling

The adapter includes comprehensive error handling:

- **Graceful Degradation**: Returns empty arrays/None on failures
- **Detailed Logging**: SQL queries and errors logged for debugging
- **Validation**: UUID and data validation before queries
- **Fallback Values**: Default values for missing fields

## 📊 Performance Features

- **Query Limits**: Prevents accidentally large queries
- **Field Mapping**: Efficient column name translation
- **Type Conversion**: Optimized UUID and timestamp handling
- **Connection Reuse**: Works with existing connection pools

## 🎯 Benefits

1. **No Schema Changes**: Works with existing database as-is
2. **Zero Migration**: No data migration required
3. **Backward Compatible**: Existing system unaffected
4. **Parser Compatible**: Parser works without modifications
5. **Comprehensive**: Handles all major parser use cases

## ⚠️ Limitations

1. **Read-Only**: Primarily designed for reading existing data
2. **Spell Summary**: Not implemented (parser feature not essential)
3. **Event Blocks**: Compressed event storage not supported
4. **Some Fields**: Default values for fields not in existing schema

## 🛠️ Integration Steps

1. **Install**: Copy adapter files to parser directory
2. **Configure**: Set environment variables
3. **Initialize**: Replace database manager with adapter
4. **Test**: Run provided test scripts
5. **Deploy**: Use in production with existing database

## 📚 Next Steps

1. Review the [Integration Guide](docs/existing_schema_integration.md)
2. Run the test script to verify functionality
3. Use the integration script to help with setup
4. Update your parser initialization code
5. Deploy and monitor

The adapter provides a seamless bridge between the parser's expectations and the existing sophisticated database schema, enabling combat log parsing without any database changes.

## 🤝 Support

- Check logs for SQL query debugging
- Use health check method to verify connectivity
- Validate environment with provided scripts
- Test with mock data before production use