const express = require("express");
const logger = require("../services/logger");

const router = express.Router();

/**
 * Get damage metrics for an encounter
 */
router.get("/damage/:encounterId", async (req, res) => {
  try {
    const { encounterId } = req.params;
    const groupBy = req.query.groupBy?.split(",") || ["source_name"];

    if (!req.db.influxdb) {
      return res.status(503).json({
        error: "Metrics not available",
        details: "InfluxDB connection not available",
      });
    }

    const cacheKey = `damage_metrics:${encounterId}:${groupBy.join(",")}`;
    let metrics;

    if (req.db.redis) {
      metrics = await req.db.redis.get(cacheKey);
      if (metrics) {
        return res.json(metrics);
      }
    }

    const damageData = await req.db.influxdb.getDamageMetrics(
      encounterId,
      groupBy,
    );

    const response = {
      encounterId,
      metric: "damage",
      data: damageData,
      groupBy,
      total: damageData.length,
    };

    if (req.db.redis) {
      await req.db.redis.cache(cacheKey, response, 300);
    }

    res.json(response);
  } catch (error) {
    logger.error("Get damage metrics error:", error);
    res.status(500).json({
      error: "Failed to get damage metrics",
      details: error.message,
    });
  }
});

/**
 * Get healing metrics for an encounter
 */
router.get("/healing/:encounterId", async (req, res) => {
  try {
    const { encounterId } = req.params;
    const groupBy = req.query.groupBy?.split(",") || ["source_name"];

    if (!req.db.influxdb) {
      return res.status(503).json({
        error: "Metrics not available",
        details: "InfluxDB connection not available",
      });
    }

    const cacheKey = `healing_metrics:${encounterId}:${groupBy.join(",")}`;
    let metrics;

    if (req.db.redis) {
      metrics = await req.db.redis.get(cacheKey);
      if (metrics) {
        return res.json(metrics);
      }
    }

    const healingData = await req.db.influxdb.getHealingMetrics(
      encounterId,
      groupBy,
    );

    const response = {
      encounterId,
      metric: "healing",
      data: healingData,
      groupBy,
      total: healingData.length,
    };

    if (req.db.redis) {
      await req.db.redis.cache(cacheKey, response, 300);
    }

    res.json(response);
  } catch (error) {
    logger.error("Get healing metrics error:", error);
    res.status(500).json({
      error: "Failed to get healing metrics",
      details: error.message,
    });
  }
});

/**
 * Get time-series data for charts
 */
router.get("/timeseries/:encounterId", async (req, res) => {
  try {
    const { encounterId } = req.params;
    const metric = req.query.metric || "damage";
    const windowSize = req.query.window || "30s";

    if (!req.db.influxdb) {
      return res.status(503).json({
        error: "Time-series data not available",
        details: "InfluxDB connection not available",
      });
    }

    const cacheKey = `timeseries:${encounterId}:${metric}:${windowSize}`;
    let timeSeriesData;

    if (req.db.redis) {
      timeSeriesData = await req.db.redis.get(cacheKey);
      if (timeSeriesData) {
        return res.json(timeSeriesData);
      }
    }

    const data = await req.db.influxdb.getTimeSeriesData(
      encounterId,
      metric,
      windowSize,
    );

    const response = {
      encounterId,
      metric,
      windowSize,
      data,
      total: data.length,
    };

    if (req.db.redis) {
      await req.db.redis.cache(cacheKey, response, 180);
    }

    res.json(response);
  } catch (error) {
    logger.error("Get time-series data error:", error);
    res.status(500).json({
      error: "Failed to get time-series data",
      details: error.message,
    });
  }
});

/**
 * Get player performance summary
 */
router.get("/player/:encounterId/:playerName", async (req, res) => {
  try {
    const { encounterId, playerName } = req.params;

    if (!req.db.influxdb) {
      return res.status(503).json({
        error: "Player metrics not available",
        details: "InfluxDB connection not available",
      });
    }

    const cacheKey = `player_metrics:${encounterId}:${playerName}`;
    let playerData;

    if (req.db.redis) {
      playerData = await req.db.redis.get(cacheKey);
      if (playerData) {
        return res.json(playerData);
      }
    }

    const summary = await req.db.influxdb.getPlayerSummary(
      encounterId,
      playerName,
    );

    if (req.db.redis) {
      await req.db.redis.cache(cacheKey, summary, 300);
    }

    res.json(summary);
  } catch (error) {
    logger.error("Get player metrics error:", error);
    res.status(500).json({
      error: "Failed to get player metrics",
      details: error.message,
    });
  }
});

/**
 * Get system statistics
 */
router.get("/stats", async (req, res) => {
  try {
    const stats = {};

    // Get PostgreSQL stats
    if (req.db.postgres) {
      try {
        stats.database = await req.db.postgres.getStats();
      } catch (error) {
        logger.warn("Failed to get PostgreSQL stats:", error.message);
        stats.database = {};
      }
    }

    // Get InfluxDB stats
    if (req.db.influxdb) {
      try {
        stats.influxdb = await req.db.influxdb.getBucketStats();
      } catch (error) {
        logger.warn("Failed to get InfluxDB stats:", error.message);
        stats.influxdb = {};
      }
    }

    // Get Redis stats
    if (req.db.redis) {
      try {
        stats.redis = await req.db.redis.getStats();
      } catch (error) {
        logger.warn("Failed to get Redis stats:", error.message);
        stats.redis = {};
      }
    }

    res.json(stats);
  } catch (error) {
    logger.error("Get system stats error:", error);
    res.status(500).json({
      error: "Failed to get system statistics",
      details: error.message,
    });
  }
});

module.exports = router;
