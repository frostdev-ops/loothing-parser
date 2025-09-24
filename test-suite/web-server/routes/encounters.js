const express = require("express");
const logger = require("../services/logger");

const router = express.Router();

/**
 * Get encounters for a guild
 */
router.get("/", async (req, res) => {
  try {
    const guildId = parseInt(req.query.guildId) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 20, 100);
    const offset = parseInt(req.query.offset) || 0;
    const search = req.query.search?.trim();

    // Check cache first
    const cacheKey = `encounters:${guildId}:${limit}:${offset}:${search || "all"}`;
    let encounters;

    if (req.db.redis) {
      encounters = await req.db.redis.get(cacheKey);
      if (encounters) {
        return res.json(encounters);
      }
    }

    // Get from database
    if (search) {
      encounters = await req.db.postgres.searchEncounters(
        guildId,
        search,
        limit,
      );
    } else {
      encounters = await req.db.postgres.getEncounters(guildId, limit, offset);
    }

    const response = {
      encounters,
      guildId,
      total: encounters.length,
      limit,
      offset,
      search: search || null,
    };

    // Cache for 2 minutes
    if (req.db.redis) {
      await req.db.redis.cache(cacheKey, response, 120);
    }

    res.json(response);
  } catch (error) {
    logger.error("Get encounters error:", error);
    res.status(500).json({
      error: "Failed to get encounters",
      details: error.message,
    });
  }
});

/**
 * Get specific encounter details
 */
router.get("/:encounterId", async (req, res) => {
  try {
    const { encounterId } = req.params;

    // Check cache first
    const cacheKey = `encounter:${encounterId}`;
    let encounter;

    if (req.db.redis) {
      encounter = await req.db.redis.get(cacheKey);
      if (encounter) {
        return res.json(encounter);
      }
    }

    // Get encounter details from PostgreSQL
    encounter = await req.db.postgres.getEncounterSummary(encounterId);

    if (!encounter) {
      return res.status(404).json({
        error: "Encounter not found",
        details: `No encounter found with ID: ${encounterId}`,
      });
    }

    // Get recent events from InfluxDB (sample for preview)
    let recentEvents = [];
    if (req.db.influxdb) {
      try {
        recentEvents = await req.db.influxdb.getCombatEvents(
          encounterId,
          null,
          50,
        );
      } catch (influxError) {
        logger.warn(
          "Failed to get recent events from InfluxDB:",
          influxError.message,
        );
      }
    }

    const response = {
      encounter,
      recentEvents,
      eventCount: recentEvents.length,
    };

    // Cache for 5 minutes
    if (req.db.redis) {
      await req.db.redis.cache(cacheKey, response, 300);
    }

    res.json(response);
  } catch (error) {
    logger.error("Get encounter details error:", error);
    res.status(500).json({
      error: "Failed to get encounter details",
      details: error.message,
    });
  }
});

/**
 * Get encounter events (paginated)
 */
router.get("/:encounterId/events", async (req, res) => {
  try {
    const { encounterId } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const eventTypes = req.query.eventTypes?.split(",").filter(Boolean);

    if (!req.db.influxdb) {
      return res.status(503).json({
        error: "Event data not available",
        details: "InfluxDB connection not available",
      });
    }

    // Check cache
    const cacheKey = `encounter_events:${encounterId}:${limit}:${eventTypes?.join(",") || "all"}`;
    let events;

    if (req.db.redis) {
      events = await req.db.redis.get(cacheKey);
      if (events) {
        return res.json(events);
      }
    }

    // Get events from InfluxDB
    events = await req.db.influxdb.getCombatEvents(
      encounterId,
      eventTypes,
      limit,
    );

    const response = {
      encounterId,
      events,
      total: events.length,
      limit,
      eventTypes: eventTypes || null,
    };

    // Cache for 1 minute (events are volatile)
    if (req.db.redis) {
      await req.db.redis.cache(cacheKey, response, 60);
    }

    res.json(response);
  } catch (error) {
    logger.error("Get encounter events error:", error);
    res.status(500).json({
      error: "Failed to get encounter events",
      details: error.message,
    });
  }
});

module.exports = router;
