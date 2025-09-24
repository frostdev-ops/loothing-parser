const { InfluxDB } = require("@influxdata/influxdb-client");
const logger = require("./logger");

let influxDB = null;
let queryApi = null;
let writeApi = null;

/**
 * Initialize InfluxDB connection
 */
async function connectInfluxDB() {
  try {
    // Configuration from environment variables
    const config = {
      url: process.env.INFLUX_URL || "http://localhost:8086",
      token:
        process.env.INFLUX_TOKEN ||
        "test-token-12345678901234567890123456789012345678901234567890",
      org: process.env.INFLUX_ORG || "wow-guild",
      bucket: process.env.INFLUX_BUCKET || "combat-events",
    };

    influxDB = new InfluxDB({
      url: config.url,
      token: config.token,
    });

    // Create query and write APIs
    queryApi = influxDB.getQueryApi(config.org);
    writeApi = influxDB.getWriteApi(config.org, config.bucket);

    // Test the connection
    await testConnection(config.org);

    logger.info(
      `InfluxDB connected to ${config.url} (org: ${config.org}, bucket: ${config.bucket})`,
    );

    return {
      influxDB,
      queryApi,
      writeApi,
      config,
    };
  } catch (error) {
    logger.error("Failed to connect to InfluxDB:", error);
    throw error;
  }
}

/**
 * Test InfluxDB connection
 */
async function testConnection(org) {
  try {
    const query = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -1m)
      |> limit(n: 1)
    `;

    // This will throw an error if connection fails
    const result = await queryApi.collectRows(query);
    logger.debug("InfluxDB connection test passed");
    return true;
  } catch (error) {
    // Connection might still work even if query fails (empty bucket, etc.)
    logger.warn("InfluxDB connection test warning:", error.message);
    return true;
  }
}

/**
 * Query combat events for an encounter
 */
async function getCombatEvents(encounterId, eventTypes = null, limit = 1000) {
  const start = Date.now();

  try {
    let query = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> filter(fn: (r) => r.encounter_id == "${encounterId}")
    `;

    if (eventTypes && eventTypes.length > 0) {
      const typeFilters = eventTypes
        .map((type) => `r.event_type == "${type}"`)
        .join(" or ");
      query += `|> filter(fn: (r) => ${typeFilters})`;
    }

    query += `|> sort(columns: ["_time"])
      |> limit(n: ${limit})`;

    const result = await queryApi.collectRows(query);
    const duration = Date.now() - start;

    logger.logDbOperation("SELECT", "combat_events", duration, true);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("SELECT", "combat_events", duration, false);
    logger.error("InfluxDB query error:", error);
    throw error;
  }
}

/**
 * Get damage aggregation for an encounter
 */
async function getDamageMetrics(encounterId, groupBy = ["source_name"]) {
  const start = Date.now();

  try {
    const groupColumns = groupBy.map((col) => `"${col}"`).join(", ");

    const query = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> filter(fn: (r) => r.encounter_id == "${encounterId}")
      |> filter(fn: (r) => r.event_type =~ /.*DAMAGE.*/)
      |> filter(fn: (r) => r._field == "amount")
      |> group(columns: [${groupColumns}])
      |> sum()
      |> yield(name: "total_damage")
    `;

    const result = await queryApi.collectRows(query);
    const duration = Date.now() - start;

    logger.logDbOperation("AGGREGATE", "damage_metrics", duration, true);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("AGGREGATE", "damage_metrics", duration, false);
    logger.error("InfluxDB damage metrics error:", error);
    throw error;
  }
}

/**
 * Get healing aggregation for an encounter
 */
async function getHealingMetrics(encounterId, groupBy = ["source_name"]) {
  const start = Date.now();

  try {
    const groupColumns = groupBy.map((col) => `"${col}"`).join(", ");

    const query = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> filter(fn: (r) => r.encounter_id == "${encounterId}")
      |> filter(fn: (r) => r.event_type =~ /.*HEAL.*/)
      |> filter(fn: (r) => r._field == "amount")
      |> group(columns: [${groupColumns}])
      |> sum()
      |> yield(name: "total_healing")
    `;

    const result = await queryApi.collectRows(query);
    const duration = Date.now() - start;

    logger.logDbOperation("AGGREGATE", "healing_metrics", duration, true);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("AGGREGATE", "healing_metrics", duration, false);
    logger.error("InfluxDB healing metrics error:", error);
    throw error;
  }
}

/**
 * Get time-series data for charts
 */
async function getTimeSeriesData(
  encounterId,
  metric = "damage",
  windowSize = "30s",
) {
  const start = Date.now();

  try {
    let eventFilter = "";
    let fieldName = "amount";

    switch (metric) {
      case "damage":
        eventFilter = "|> filter(fn: (r) => r.event_type =~ /.*DAMAGE.*/)";
        break;
      case "healing":
        eventFilter = "|> filter(fn: (r) => r.event_type =~ /.*HEAL.*/)";
        break;
      case "deaths":
        eventFilter = '|> filter(fn: (r) => r.event_type == "UNIT_DIED")';
        fieldName = "_value"; // Deaths don't have amount
        break;
      default:
        eventFilter = "";
    }

    const query = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> filter(fn: (r) => r.encounter_id == "${encounterId}")
      ${eventFilter}
      |> filter(fn: (r) => r._field == "${fieldName}")
      |> aggregateWindow(every: ${windowSize}, fn: sum, createEmpty: false)
      |> group(columns: ["source_name"])
      |> yield(name: "time_series_${metric}")
    `;

    const result = await queryApi.collectRows(query);
    const duration = Date.now() - start;

    logger.logDbOperation("TIME_SERIES", `${metric}_data`, duration, true);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("TIME_SERIES", `${metric}_data`, duration, false);
    logger.error(`InfluxDB time series ${metric} error:`, error);
    throw error;
  }
}

/**
 * Get player performance summary
 */
async function getPlayerSummary(encounterId, playerName) {
  const start = Date.now();

  try {
    const damageQuery = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> filter(fn: (r) => r.encounter_id == "${encounterId}")
      |> filter(fn: (r) => r.source_name == "${playerName}")
      |> filter(fn: (r) => r.event_type =~ /.*DAMAGE.*/)
      |> filter(fn: (r) => r._field == "amount")
      |> sum()
      |> yield(name: "total_damage")
    `;

    const healingQuery = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> filter(fn: (r) => r.encounter_id == "${encounterId}")
      |> filter(fn: (r) => r.source_name == "${playerName}")
      |> filter(fn: (r) => r.event_type =~ /.*HEAL.*/)
      |> filter(fn: (r) => r._field == "amount")
      |> sum()
      |> yield(name: "total_healing")
    `;

    const [damage, healing] = await Promise.all([
      queryApi.collectRows(damageQuery),
      queryApi.collectRows(healingQuery),
    ]);

    const duration = Date.now() - start;
    logger.logDbOperation("SUMMARY", "player_metrics", duration, true);

    return {
      player: playerName,
      encounter: encounterId,
      damage: damage[0]?._value || 0,
      healing: healing[0]?._value || 0,
    };
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("SUMMARY", "player_metrics", duration, false);
    logger.error("InfluxDB player summary error:", error);
    throw error;
  }
}

/**
 * Get recent encounters with basic metrics
 */
async function getRecentEncounters(limit = 10) {
  const start = Date.now();

  try {
    const query = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -7d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> group(columns: ["encounter_id"])
      |> first()
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: ${limit})
      |> yield(name: "recent_encounters")
    `;

    const result = await queryApi.collectRows(query);
    const duration = Date.now() - start;

    logger.logDbOperation("SELECT", "recent_encounters", duration, true);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("SELECT", "recent_encounters", duration, false);
    logger.error("InfluxDB recent encounters error:", error);
    throw error;
  }
}

/**
 * Get bucket statistics
 */
async function getBucketStats() {
  const start = Date.now();

  try {
    const query = `
      from(bucket: "${process.env.INFLUX_BUCKET || "combat-events"}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "combat_events")
      |> group()
      |> count()
      |> yield(name: "total_events")
    `;

    const result = await queryApi.collectRows(query);
    const duration = Date.now() - start;

    logger.logDbOperation("STATS", "bucket_info", duration, true);

    return {
      totalEvents: result[0]?._value || 0,
      bucket: process.env.INFLUX_BUCKET || "combat-events",
      org: process.env.INFLUX_ORG || "wow-guild",
    };
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("STATS", "bucket_info", duration, false);
    logger.error("InfluxDB bucket stats error:", error);
    return {
      totalEvents: 0,
      bucket: process.env.INFLUX_BUCKET || "combat-events",
      org: process.env.INFLUX_ORG || "wow-guild",
    };
  }
}

/**
 * Execute a custom Flux query
 */
async function customQuery(fluxQuery) {
  const start = Date.now();

  try {
    const result = await queryApi.collectRows(fluxQuery);
    const duration = Date.now() - start;

    logger.logDbOperation("CUSTOM", "flux_query", duration, true);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    logger.logDbOperation("CUSTOM", "flux_query", duration, false);
    logger.error("InfluxDB custom query error:", error);
    throw error;
  }
}

/**
 * Get connection status
 */
function getConnectionStatus() {
  return {
    connected: influxDB !== null,
    url: process.env.INFLUX_URL || "http://localhost:8086",
    org: process.env.INFLUX_ORG || "wow-guild",
    bucket: process.env.INFLUX_BUCKET || "combat-events",
  };
}

module.exports = {
  connectInfluxDB,
  getCombatEvents,
  getDamageMetrics,
  getHealingMetrics,
  getTimeSeriesData,
  getPlayerSummary,
  getRecentEncounters,
  getBucketStats,
  customQuery,
  getConnectionStatus,
};
