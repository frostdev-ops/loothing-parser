const redis = require("redis");
const logger = require("./logger");

let client = null;

/**
 * Initialize Redis connection
 */
async function connectRedis() {
  try {
    // Configuration from environment variables
    const config = {
      url: process.env.REDIS_URL || "redis://localhost:6379",
      socket: {
        reconnectStrategy: (retries) => Math.min(retries * 50, 500),
      },
      database: parseInt(process.env.REDIS_DB) || 0,
    };

    if (process.env.REDIS_PASSWORD) {
      config.password = process.env.REDIS_PASSWORD;
    }

    client = redis.createClient(config);

    // Error handling
    client.on("error", (err) => {
      logger.error("Redis error:", err);
    });

    client.on("connect", () => {
      logger.debug("Redis connecting...");
    });

    client.on("ready", () => {
      logger.info("Redis connection ready");
    });

    client.on("end", () => {
      logger.info("Redis connection ended");
    });

    client.on("reconnecting", () => {
      logger.warn("Redis reconnecting...");
    });

    // Connect
    await client.connect();

    // Test the connection
    await client.ping();

    logger.info(`Redis connected to ${config.url} (db: ${config.database})`);
    return client;
  } catch (error) {
    logger.error("Failed to connect to Redis:", error);
    throw error;
  }
}

/**
 * Cache data with TTL
 */
async function cache(key, data, ttl = 300) {
  try {
    const serialized = JSON.stringify(data);
    await client.setEx(key, ttl, serialized);
    logger.debug(`Cached data for key: ${key} (TTL: ${ttl}s)`);
  } catch (error) {
    logger.error("Redis cache error:", error);
    throw error;
  }
}

/**
 * Get cached data
 */
async function get(key) {
  try {
    const data = await client.get(key);
    if (data) {
      logger.debug(`Cache hit for key: ${key}`);
      return JSON.parse(data);
    }
    logger.debug(`Cache miss for key: ${key}`);
    return null;
  } catch (error) {
    logger.error("Redis get error:", error);
    return null; // Return null on error to allow fallback to database
  }
}

/**
 * Delete cached data
 */
async function del(key) {
  try {
    const result = await client.del(key);
    logger.debug(`Deleted cache key: ${key} (existed: ${result > 0})`);
    return result;
  } catch (error) {
    logger.error("Redis delete error:", error);
    throw error;
  }
}

/**
 * Delete multiple keys by pattern
 */
async function delPattern(pattern) {
  try {
    const keys = await client.keys(pattern);
    if (keys.length > 0) {
      const result = await client.del(keys);
      logger.debug(`Deleted ${result} keys matching pattern: ${pattern}`);
      return result;
    }
    return 0;
  } catch (error) {
    logger.error("Redis delete pattern error:", error);
    throw error;
  }
}

/**
 * Check if key exists
 */
async function exists(key) {
  try {
    return await client.exists(key);
  } catch (error) {
    logger.error("Redis exists error:", error);
    return false;
  }
}

/**
 * Set TTL for existing key
 */
async function expire(key, ttl) {
  try {
    return await client.expire(key, ttl);
  } catch (error) {
    logger.error("Redis expire error:", error);
    throw error;
  }
}

/**
 * Get TTL for key
 */
async function ttl(key) {
  try {
    return await client.ttl(key);
  } catch (error) {
    logger.error("Redis TTL error:", error);
    return -1;
  }
}

/**
 * Increment counter
 */
async function incr(key, amount = 1) {
  try {
    if (amount === 1) {
      return await client.incr(key);
    } else {
      return await client.incrBy(key, amount);
    }
  } catch (error) {
    logger.error("Redis incr error:", error);
    throw error;
  }
}

/**
 * Set with NX option (only if not exists)
 */
async function setNX(key, data, ttl = null) {
  try {
    const serialized = JSON.stringify(data);
    if (ttl) {
      return await client.set(key, serialized, "NX", "EX", ttl);
    } else {
      return await client.set(key, serialized, "NX");
    }
  } catch (error) {
    logger.error("Redis setNX error:", error);
    throw error;
  }
}

/**
 * Hash operations
 */
const hash = {
  async set(key, field, value) {
    try {
      const serialized =
        typeof value === "string" ? value : JSON.stringify(value);
      await client.hSet(key, field, serialized);
      logger.debug(`Set hash field ${key}:${field}`);
    } catch (error) {
      logger.error("Redis hash set error:", error);
      throw error;
    }
  },

  async get(key, field) {
    try {
      const data = await client.hGet(key, field);
      if (data) {
        try {
          return JSON.parse(data);
        } catch {
          return data; // Return as string if not JSON
        }
      }
      return null;
    } catch (error) {
      logger.error("Redis hash get error:", error);
      return null;
    }
  },

  async getAll(key) {
    try {
      const data = await client.hGetAll(key);
      const result = {};
      for (const [field, value] of Object.entries(data)) {
        try {
          result[field] = JSON.parse(value);
        } catch {
          result[field] = value;
        }
      }
      return result;
    } catch (error) {
      logger.error("Redis hash getAll error:", error);
      return {};
    }
  },

  async del(key, field) {
    try {
      return await client.hDel(key, field);
    } catch (error) {
      logger.error("Redis hash del error:", error);
      throw error;
    }
  },

  async exists(key, field) {
    try {
      return await client.hExists(key, field);
    } catch (error) {
      logger.error("Redis hash exists error:", error);
      return false;
    }
  },
};

/**
 * List operations
 */
const list = {
  async push(key, ...items) {
    try {
      const serialized = items.map((item) =>
        typeof item === "string" ? item : JSON.stringify(item),
      );
      return await client.lPush(key, serialized);
    } catch (error) {
      logger.error("Redis list push error:", error);
      throw error;
    }
  },

  async pop(key) {
    try {
      const data = await client.lPop(key);
      if (data) {
        try {
          return JSON.parse(data);
        } catch {
          return data;
        }
      }
      return null;
    } catch (error) {
      logger.error("Redis list pop error:", error);
      return null;
    }
  },

  async range(key, start = 0, stop = -1) {
    try {
      const data = await client.lRange(key, start, stop);
      return data.map((item) => {
        try {
          return JSON.parse(item);
        } catch {
          return item;
        }
      });
    } catch (error) {
      logger.error("Redis list range error:", error);
      return [];
    }
  },

  async length(key) {
    try {
      return await client.lLen(key);
    } catch (error) {
      logger.error("Redis list length error:", error);
      return 0;
    }
  },
};

/**
 * Session management
 */
const session = {
  async set(sessionId, data, ttl = 3600) {
    const key = `session:${sessionId}`;
    return await cache(key, data, ttl);
  },

  async get(sessionId) {
    const key = `session:${sessionId}`;
    return await get(key);
  },

  async del(sessionId) {
    const key = `session:${sessionId}`;
    return await del(key);
  },

  async extend(sessionId, ttl = 3600) {
    const key = `session:${sessionId}`;
    return await expire(key, ttl);
  },
};

/**
 * Get Redis statistics
 */
async function getStats() {
  try {
    const info = await client.info();
    const stats = {};

    // Parse the info string
    const lines = info.split("\r\n");
    for (const line of lines) {
      if (line.includes(":")) {
        const [key, value] = line.split(":");
        stats[key] = isNaN(value) ? value : parseFloat(value);
      }
    }

    return {
      connected_clients: stats.connected_clients || 0,
      used_memory: stats.used_memory || 0,
      used_memory_human: stats.used_memory_human || "0B",
      total_commands_processed: stats.total_commands_processed || 0,
      keyspace_hits: stats.keyspace_hits || 0,
      keyspace_misses: stats.keyspace_misses || 0,
      hit_rate:
        stats.keyspace_hits && stats.keyspace_misses
          ? (
              (stats.keyspace_hits /
                (stats.keyspace_hits + stats.keyspace_misses)) *
              100
            ).toFixed(2)
          : "0.00",
    };
  } catch (error) {
    logger.error("Redis stats error:", error);
    return {};
  }
}

/**
 * Flush all data (for testing)
 */
async function flushAll() {
  try {
    await client.flushAll();
    logger.warn("Redis: All data flushed");
  } catch (error) {
    logger.error("Redis flush error:", error);
    throw error;
  }
}

/**
 * Close Redis connection
 */
async function close() {
  try {
    if (client) {
      await client.quit();
      client = null;
      logger.info("Redis connection closed");
    }
  } catch (error) {
    logger.error("Redis close error:", error);
  }
}

/**
 * Get connection status
 */
function getConnectionStatus() {
  return {
    connected: client ? client.isReady : false,
    url: process.env.REDIS_URL || "redis://localhost:6379",
    database: parseInt(process.env.REDIS_DB) || 0,
  };
}

module.exports = {
  connectRedis,
  cache,
  get,
  del,
  delPattern,
  exists,
  expire,
  ttl,
  incr,
  setNX,
  hash,
  list,
  session,
  getStats,
  flushAll,
  close,
  getConnectionStatus,
};
