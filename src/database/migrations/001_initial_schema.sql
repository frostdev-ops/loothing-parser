-- PostgreSQL Migration: Initial Schema
-- Migrated from SQLite to PostgreSQL with proper types and constraints

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Guilds table
CREATE TABLE IF NOT EXISTS guilds (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    realm VARCHAR(100),
    region VARCHAR(10),
    faction VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, realm, region)
);

-- Log files tracking
CREATE TABLE IF NOT EXISTS log_files (
    id SERIAL PRIMARY KEY,
    guild_id INTEGER REFERENCES guilds(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64),
    file_size BIGINT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_events BIGINT DEFAULT 0,
    UNIQUE(file_hash)
);

-- Encounters table (metadata only, events go to InfluxDB)
CREATE TABLE IF NOT EXISTS encounters (
    id VARCHAR(50) PRIMARY KEY,  -- UUID or hash-based ID
    guild_id INTEGER REFERENCES guilds(id) ON DELETE CASCADE,
    log_file_id INTEGER REFERENCES log_files(id) ON DELETE CASCADE,
    encounter_name VARCHAR(255),
    encounter_id INTEGER,  -- WoW encounter ID
    difficulty VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration REAL,
    success BOOLEAN DEFAULT FALSE,
    phase_count INTEGER DEFAULT 1,
    pull_number INTEGER DEFAULT 1,
    zone_name VARCHAR(255),
    zone_id INTEGER,
    player_count INTEGER DEFAULT 0,
    item_level_avg REAL,
    composition_hash VARCHAR(64),
    wipe_percentage REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Characters table
CREATE TABLE IF NOT EXISTS characters (
    id SERIAL PRIMARY KEY,
    guild_id INTEGER REFERENCES guilds(id) ON DELETE CASCADE,
    guid VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    realm VARCHAR(100),
    class VARCHAR(50),
    spec VARCHAR(50),
    role VARCHAR(20),
    race VARCHAR(50),
    gender VARCHAR(20),
    faction VARCHAR(20),
    level INTEGER,
    item_level INTEGER,
    talents TEXT,  -- JSON string
    covenant VARCHAR(50),
    soulbind VARCHAR(100),
    conduits TEXT,  -- JSON string
    legendaries TEXT,  -- JSON string
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guid)
);

-- Create indexes for characters
CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(character_name);
CREATE INDEX IF NOT EXISTS idx_characters_guild_id ON characters(guild_id);
CREATE INDEX IF NOT EXISTS idx_characters_class_spec ON characters(class, spec);

-- Event blocks for compressed storage (only metadata, actual events in InfluxDB)
CREATE TABLE IF NOT EXISTS event_blocks (
    id SERIAL PRIMARY KEY,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    block_index INTEGER NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    event_count INTEGER DEFAULT 0,
    compressed_data BYTEA,  -- Compressed binary data
    compressed_size INTEGER,
    uncompressed_size INTEGER,
    compression_ratio REAL,
    compression_algorithm VARCHAR(20) DEFAULT 'zstd',
    checksum VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(encounter_id, block_index)
);

-- Character metrics per encounter
CREATE TABLE IF NOT EXISTS character_metrics (
    id SERIAL PRIMARY KEY,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    character_guid VARCHAR(50),
    character_name VARCHAR(100),
    damage_done BIGINT DEFAULT 0,
    healing_done BIGINT DEFAULT 0,
    damage_taken BIGINT DEFAULT 0,
    healing_taken BIGINT DEFAULT 0,
    deaths INTEGER DEFAULT 0,
    interrupts INTEGER DEFAULT 0,
    dispels INTEGER DEFAULT 0,
    crowd_control INTEGER DEFAULT 0,
    defensive_casts INTEGER DEFAULT 0,
    offensive_casts INTEGER DEFAULT 0,
    resources_gained BIGINT DEFAULT 0,
    resources_wasted BIGINT DEFAULT 0,
    active_time REAL DEFAULT 0.0,
    dps REAL,
    hps REAL,
    dtps REAL,
    activity_percent REAL,
    death_time REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(encounter_id, character_guid)
);

-- Create indexes for metrics
CREATE INDEX IF NOT EXISTS idx_character_metrics_encounter ON character_metrics(encounter_id);
CREATE INDEX IF NOT EXISTS idx_character_metrics_character ON character_metrics(character_id);
CREATE INDEX IF NOT EXISTS idx_character_metrics_dps ON character_metrics(dps DESC);
CREATE INDEX IF NOT EXISTS idx_character_metrics_hps ON character_metrics(hps DESC);

-- Spell summary statistics
CREATE TABLE IF NOT EXISTS spell_summary (
    id SERIAL PRIMARY KEY,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    character_guid VARCHAR(50),
    spell_id INTEGER,
    spell_name VARCHAR(255),
    spell_school VARCHAR(50),
    total_damage BIGINT DEFAULT 0,
    total_healing BIGINT DEFAULT 0,
    cast_count INTEGER DEFAULT 0,
    hit_count INTEGER DEFAULT 0,
    crit_count INTEGER DEFAULT 0,
    miss_count INTEGER DEFAULT 0,
    avg_damage REAL,
    avg_healing REAL,
    min_hit BIGINT,
    max_hit BIGINT,
    crit_percent REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(encounter_id, character_guid, spell_id)
);

-- Create indexes for spell summary
CREATE INDEX IF NOT EXISTS idx_spell_summary_encounter ON spell_summary(encounter_id);
CREATE INDEX IF NOT EXISTS idx_spell_summary_character ON spell_summary(character_guid);
CREATE INDEX IF NOT EXISTS idx_spell_summary_spell ON spell_summary(spell_id);

-- Mythic Plus run tracking
CREATE TABLE IF NOT EXISTS mythic_plus_runs (
    id SERIAL PRIMARY KEY,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    dungeon_id INTEGER,
    dungeon_name VARCHAR(255),
    keystone_level INTEGER,
    keystone_affixes TEXT,  -- JSON array
    time_limit INTEGER,
    completion_time INTEGER,
    deaths INTEGER DEFAULT 0,
    percent_completed REAL,
    num_chests INTEGER,
    score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Combat segments (for boss phases, trash pulls, etc)
CREATE TABLE IF NOT EXISTS combat_segments (
    id SERIAL PRIMARY KEY,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    segment_type VARCHAR(50),  -- 'phase', 'trash', 'intermission'
    segment_index INTEGER,
    segment_name VARCHAR(255),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(encounter_id, segment_type, segment_index)
);

-- Combat periods (active combat windows)
CREATE TABLE IF NOT EXISTS combat_periods (
    id SERIAL PRIMARY KEY,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    period_index INTEGER,
    start_offset REAL,  -- Seconds from encounter start
    end_offset REAL,
    duration REAL,
    is_active_combat BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Character gear snapshots
CREATE TABLE IF NOT EXISTS character_gear_snapshots (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    snapshot_time TIMESTAMP,
    average_item_level REAL,
    equipped_item_level REAL,
    armor INTEGER,
    stamina INTEGER,
    strength INTEGER,
    agility INTEGER,
    intellect INTEGER,
    critical_strike INTEGER,
    haste INTEGER,
    mastery INTEGER,
    versatility INTEGER,
    leech INTEGER,
    speed INTEGER,
    avoidance INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Character gear items
CREATE TABLE IF NOT EXISTS character_gear_items (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER REFERENCES character_gear_snapshots(id) ON DELETE CASCADE,
    slot VARCHAR(50),
    item_id INTEGER,
    item_name VARCHAR(255),
    item_level INTEGER,
    item_quality VARCHAR(20),
    enchant_id INTEGER,
    enchant_name VARCHAR(255),
    gem_ids TEXT,  -- JSON array
    bonus_ids TEXT,  -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Character talent snapshots
CREATE TABLE IF NOT EXISTS character_talent_snapshots (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    encounter_id VARCHAR(50) REFERENCES encounters(id) ON DELETE CASCADE,
    snapshot_time TIMESTAMP,
    class_talents TEXT,  -- JSON structure
    spec_talents TEXT,  -- JSON structure
    pvp_talents TEXT,  -- JSON structure
    talent_loadout_code VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Character talent selections
CREATE TABLE IF NOT EXISTS character_talent_selections (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER REFERENCES character_talent_snapshots(id) ON DELETE CASCADE,
    talent_tree VARCHAR(20),  -- 'class' or 'spec'
    talent_id INTEGER,
    talent_name VARCHAR(255),
    talent_rank INTEGER,
    row_index INTEGER,
    column_index INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_encounters_guild ON encounters(guild_id);
CREATE INDEX IF NOT EXISTS idx_encounters_start_time ON encounters(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_encounters_difficulty ON encounters(difficulty);
CREATE INDEX IF NOT EXISTS idx_encounters_success ON encounters(success);
CREATE INDEX IF NOT EXISTS idx_encounters_zone ON encounters(zone_name, encounter_name);

CREATE INDEX IF NOT EXISTS idx_log_files_guild ON log_files(guild_id);
CREATE INDEX IF NOT EXISTS idx_log_files_hash ON log_files(file_hash);

CREATE INDEX IF NOT EXISTS idx_event_blocks_encounter ON event_blocks(encounter_id);
CREATE INDEX IF NOT EXISTS idx_event_blocks_time ON event_blocks(start_time, end_time);

-- Insert initial schema version
INSERT INTO schema_version (version, description)
VALUES (1, 'Initial PostgreSQL schema with InfluxDB integration')
ON CONFLICT (version) DO NOTHING;

-- Create update trigger function for updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply update triggers to tables with updated_at
CREATE TRIGGER update_guilds_updated_at BEFORE UPDATE ON guilds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_encounters_updated_at BEFORE UPDATE ON encounters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_characters_updated_at BEFORE UPDATE ON characters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_character_metrics_updated_at BEFORE UPDATE ON character_metrics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();