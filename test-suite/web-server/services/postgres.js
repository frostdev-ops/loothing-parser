const { Pool } = require("pg");
const logger = require("./logger");

let pool = null;

/**
 * Initialize PostgreSQL connection pool
 */
async function connectPostgres() {
  try {
    // Configuration from environment variables
    const config = {
      host: process.env.POSTGRES_HOST || "localhost",
      port: parseInt(process.env.POSTGRES_PORT) || 5432,
      database: process.env.POSTGRES_DB || "combat_logs_test",
      user: process.env.POSTGRES_USER || "postgres",
      password: process.env.POSTGRES_PASSWORD || "testpassword123",
      max: 20, // Maximum number of connections
      idleTimeoutMillis: 30000, // How long a connection can be idle
      connectionTimeoutMillis: 5000, // How long to wait for a connection
      ssl:
        process.env.POSTGRES_SSL === "true"
          ? { rejectUnauthorized: false }
          : false,
    };

    pool = new Pool(config);

    // Test the connection
    const client = await pool.connect();
    await client.query("SELECT NOW()");
    client.release();

    logger.info(
      `PostgreSQL connected to ${config.host}:${config.port}/${config.database}`,
    );

    // Setup connection event handlers
    pool.on("error", (err) => {
      logger.error("Unexpected error on idle PostgreSQL client", err);
    });

    pool.on("connect", () => {
      logger.debug("New PostgreSQL client connected");
    });

    pool.on("remove", () => {
      logger.debug("PostgreSQL client removed from pool");
    });

    return pool;
  } catch (error) {
    logger.error("Failed to connect to PostgreSQL:", error);
    throw error;
  }
}

/**
 * Execute a query with timing and error handling
 */
async function query(text, params = []) {
  const start = Date.now();
  let client;

  try {
    client = await pool.connect();
    const result = await client.query(text, params);
    const duration = Date.now() - start;

    logger.logDbOperation("SELECT", "query", duration, true);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("SELECT", "query", duration, false);
    logger.error("PostgreSQL query error:", {
      query: text,
      params,
      error: error.message,
    });
    throw error;
  } finally {
    if (client) {
      client.release();
    }
  }
}

/**
 * Get guild information by ID
 */
async function getGuild(guildId) {
  const text = "SELECT * FROM guilds WHERE id = $1";
  const result = await query(text, [guildId]);
  return result.rows[0];
}

/**
 * Get all guilds
 */
async function getAllGuilds() {
  const text = "SELECT * FROM guilds ORDER BY name, realm";
  const result = await query(text);
  return result.rows;
}

/**
 * Get encounters for a guild
 */
async function getEncounters(guildId, limit = 50, offset = 0) {
  const text = `
    SELECT
      e.*,
      g.name as guild_name,
      g.realm as guild_realm
    FROM encounters e
    JOIN guilds g ON e.guild_id = g.id
    WHERE e.guild_id = $1
    ORDER BY e.start_time DESC
    LIMIT $2 OFFSET $3
  `;
  const result = await query(text, [guildId, limit, offset]);
  return result.rows;
}

/**
 * Get encounter by ID
 */
async function getEncounter(encounterId) {
  const text = `
    SELECT
      e.*,
      g.name as guild_name,
      g.realm as guild_realm
    FROM encounters e
    JOIN guilds g ON e.guild_id = g.id
    WHERE e.id = $1
  `;
  const result = await query(text, [encounterId]);
  return result.rows[0];
}

/**
 * Get characters for a guild
 */
async function getCharacters(guildId, limit = 100, offset = 0) {
  const text = `
    SELECT * FROM characters
    WHERE guild_id = $1
    ORDER BY name
    LIMIT $2 OFFSET $3
  `;
  const result = await query(text, [guildId, limit, offset]);
  return result.rows;
}

/**
 * Get character by GUID
 */
async function getCharacter(guid) {
  const text = "SELECT * FROM characters WHERE guid = $1";
  const result = await query(text, [guid]);
  return result.rows[0];
}

/**
 * Get recent log files for a guild
 */
async function getLogFiles(guildId, limit = 20) {
  const text = `
    SELECT
      lf.*,
      g.name as guild_name
    FROM log_files lf
    JOIN guilds g ON lf.guild_id = g.id
    WHERE lf.guild_id = $1
    ORDER BY lf.processed_at DESC
    LIMIT $2
  `;
  const result = await query(text, [guildId, limit]);
  return result.rows;
}

/**
 * Get database statistics
 */
async function getStats() {
  const queries = [
    { name: "guilds", query: "SELECT COUNT(*) FROM guilds" },
    { name: "encounters", query: "SELECT COUNT(*) FROM encounters" },
    { name: "characters", query: "SELECT COUNT(*) FROM characters" },
    { name: "log_files", query: "SELECT COUNT(*) FROM log_files" },
  ];

  const stats = {};

  for (const { name, query: queryText } of queries) {
    try {
      const result = await query(queryText);
      stats[name] = parseInt(result.rows[0].count);
    } catch (error) {
      logger.error(`Failed to get stats for ${name}:`, error);
      stats[name] = 0;
    }
  }

  return stats;
}

/**
 * Get encounter summary with character counts
 */
async function getEncounterSummary(encounterId) {
  const text = `
    SELECT
      e.*,
      g.name as guild_name,
      g.realm as guild_realm,
      COUNT(c.id) as character_count
    FROM encounters e
    JOIN guilds g ON e.guild_id = g.id
    LEFT JOIN characters c ON c.guild_id = e.guild_id
    WHERE e.id = $1
    GROUP BY e.id, g.name, g.realm
  `;
  const result = await query(text, [encounterId]);
  return result.rows[0];
}

/**
 * Search encounters by name
 */
async function searchEncounters(guildId, searchTerm, limit = 20) {
  const text = `
    SELECT
      e.*,
      g.name as guild_name
    FROM encounters e
    JOIN guilds g ON e.guild_id = g.id
    WHERE e.guild_id = $1
      AND (
        e.encounter_name ILIKE $2
        OR e.zone_name ILIKE $2
      )
    ORDER BY e.start_time DESC
    LIMIT $3
  `;
  const result = await query(text, [guildId, `%${searchTerm}%`, limit]);
  return result.rows;
}

/**
 * Close the connection pool
 */
async function closePool() {
  if (pool) {
    await pool.end();
    pool = null;
    logger.info("PostgreSQL connection pool closed");
  }
}

/**
 * Get pool status
 */
function getPoolStatus() {
  if (!pool) {
    return { connected: false };
  }

  return {
    connected: true,
    totalCount: pool.totalCount,
    idleCount: pool.idleCount,
    waitingCount: pool.waitingCount,
  };
}

module.exports = {
  connectPostgres,
  query,
  getGuild,
  getAllGuilds,
  getEncounters,
  getEncounter,
  getCharacters,
  getCharacter,
  getLogFiles,
  getStats,
  getEncounterSummary,
  searchEncounters,
  closePool,
  getPoolStatus,
};
