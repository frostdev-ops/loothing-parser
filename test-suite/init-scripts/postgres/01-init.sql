-- PostgreSQL Initialization for Test Suite
-- This script sets up the database for testing with sample data

-- Create extensions needed for the application
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Set timezone to UTC for consistency
SET timezone = 'UTC';

-- Create additional test-specific configuration
ALTER DATABASE combat_logs_test SET timezone TO 'UTC';

-- Create test guild for multi-tenancy testing
DO $$
BEGIN
    -- Check if test guild exists, if not create it
    IF NOT EXISTS (SELECT 1 FROM guilds WHERE name = 'Test Guild' AND realm = 'Test-Realm') THEN
        INSERT INTO guilds (name, realm, region, faction, created_at, updated_at)
        VALUES ('Test Guild', 'Test-Realm', 'US', 'Alliance', NOW(), NOW());
    END IF;
END $$;

-- Create additional test guilds for multi-tenant testing
INSERT INTO guilds (name, realm, region, faction, created_at, updated_at)
VALUES
    ('Alpha Testing Guild', 'Stormrage', 'US', 'Alliance', NOW(), NOW()),
    ('Beta Raiders', 'Area-52', 'US', 'Horde', NOW(), NOW()),
    ('Gamma Squad', 'Tichondrius', 'US', 'Horde', NOW(), NOW())
ON CONFLICT (name, realm, region) DO NOTHING;

-- Create test users table for web interface authentication
CREATE TABLE IF NOT EXISTS test_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    guild_id INTEGER REFERENCES guilds(id),
    role VARCHAR(50) DEFAULT 'member',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Insert test users
INSERT INTO test_users (username, email, guild_id, role)
VALUES
    ('testadmin', 'admin@test.com', 1, 'admin'),
    ('testuser1', 'user1@test.com', 1, 'member'),
    ('testuser2', 'user2@test.com', 2, 'member')
ON CONFLICT (username) DO NOTHING;

-- Create sample encounter types for testing
INSERT INTO encounters (
    id, guild_id, encounter_name, encounter_id, difficulty,
    start_time, end_time, duration, success, zone_name, zone_id,
    player_count, created_at, updated_at
) VALUES
    (
        'test-encounter-1', 1, 'Test Boss', 2902, 'Heroic',
        NOW() - INTERVAL '1 hour', NOW() - INTERVAL '50 minutes', 600.0, true,
        'Test Raid', 1001, 20, NOW(), NOW()
    ),
    (
        'test-encounter-2', 1, 'Training Dummy', 0, 'Normal',
        NOW() - INTERVAL '30 minutes', NOW() - INTERVAL '25 minutes', 300.0, true,
        'Test Area', 1002, 1, NOW(), NOW()
    )
ON CONFLICT (id) DO NOTHING;

-- Create sample characters for testing
INSERT INTO characters (
    guild_id, guid, name, realm, class, spec, role, level, created_at, updated_at
) VALUES
    (1, 'Player-1234-56789ABC', 'Testpaladin', 'Test-Realm', 'Paladin', 'Protection', 'TANK', 80, NOW(), NOW()),
    (1, 'Player-1234-56789DEF', 'Testpriest', 'Test-Realm', 'Priest', 'Holy', 'HEALER', 80, NOW(), NOW()),
    (1, 'Player-1234-56789GHI', 'Testwarrior', 'Test-Realm', 'Warrior', 'Fury', 'DAMAGER', 80, NOW(), NOW()),
    (1, 'Player-1234-56789JKL', 'Testmage', 'Test-Realm', 'Mage', 'Fire', 'DAMAGER', 80, NOW(), NOW())
ON CONFLICT (guid) DO NOTHING;

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- Create indexes for performance testing
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_encounters_guild_time ON encounters(guild_id, start_time);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_characters_guild_class ON characters(guild_id, class, spec);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_log_files_guild_processed ON log_files(guild_id, processed_at);

-- Create a view for quick test data verification
CREATE OR REPLACE VIEW test_summary AS
SELECT
    'Guilds' as table_name, COUNT(*) as count FROM guilds
UNION ALL
SELECT
    'Characters', COUNT(*) FROM characters
UNION ALL
SELECT
    'Encounters', COUNT(*) FROM encounters
UNION ALL
SELECT
    'Log Files', COUNT(*) FROM log_files
UNION ALL
SELECT
    'Test Users', COUNT(*) FROM test_users;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Test database initialized successfully at %', NOW();
END $$;