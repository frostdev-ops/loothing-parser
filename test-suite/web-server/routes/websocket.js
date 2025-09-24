const logger = require("../services/logger");

/**
 * WebSocket event handlers
 */
function setupWebSocket(io, dbConnections) {
  io.on("connection", (socket) => {
    const clientId = socket.id;
    logger.logSocket("connection", clientId, { ip: socket.handshake.address });

    // Join client to a room based on guild
    socket.on("join-guild", (guildId) => {
      const room = `guild-${guildId}`;
      socket.join(room);
      socket.guildId = guildId;
      logger.logSocket("join-guild", clientId, { guildId, room });

      socket.emit("joined-guild", { guildId, room });
    });

    // Leave guild room
    socket.on("leave-guild", (guildId) => {
      const room = `guild-${guildId}`;
      socket.leave(room);
      logger.logSocket("leave-guild", clientId, { guildId, room });

      socket.emit("left-guild", { guildId, room });
    });

    // Subscribe to encounter updates
    socket.on("subscribe-encounter", (encounterId) => {
      const room = `encounter-${encounterId}`;
      socket.join(room);
      logger.logSocket("subscribe-encounter", clientId, { encounterId, room });

      socket.emit("subscribed-encounter", { encounterId, room });
    });

    // Unsubscribe from encounter updates
    socket.on("unsubscribe-encounter", (encounterId) => {
      const room = `encounter-${encounterId}`;
      socket.leave(room);
      logger.logSocket("unsubscribe-encounter", clientId, {
        encounterId,
        room,
      });

      socket.emit("unsubscribed-encounter", { encounterId, room });
    });

    // Request live metrics for an encounter
    socket.on("request-live-metrics", async (data) => {
      try {
        const { encounterId, metric = "damage" } = data;
        logger.logSocket("request-live-metrics", clientId, {
          encounterId,
          metric,
        });

        if (!dbConnections.influxdb) {
          socket.emit("metrics-error", {
            error: "InfluxDB not available",
            encounterId,
            metric,
          });
          return;
        }

        // Get live metrics from InfluxDB
        let metricsData;
        switch (metric) {
          case "damage":
            metricsData =
              await dbConnections.influxdb.getDamageMetrics(encounterId);
            break;
          case "healing":
            metricsData =
              await dbConnections.influxdb.getHealingMetrics(encounterId);
            break;
          case "timeseries":
            metricsData = await dbConnections.influxdb.getTimeSeriesData(
              encounterId,
              data.type || "damage",
            );
            break;
          default:
            metricsData = [];
        }

        socket.emit("live-metrics", {
          encounterId,
          metric,
          data: metricsData,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        logger.error("Live metrics request error:", error);
        socket.emit("metrics-error", {
          error: error.message,
          encounterId: data.encounterId,
          metric: data.metric,
        });
      }
    });

    // Ping/pong for connection health
    socket.on("ping", () => {
      socket.emit("pong");
    });

    // Handle client status updates
    socket.on("status-update", (status) => {
      logger.logSocket("status-update", clientId, status);

      // Store client status in Redis for monitoring
      if (dbConnections.redis) {
        dbConnections.redis.cache(
          `client:${clientId}`,
          {
            ...status,
            lastSeen: new Date().toISOString(),
            guildId: socket.guildId,
          },
          300,
        ); // 5 minute TTL
      }
    });

    // Handle disconnect
    socket.on("disconnect", (reason) => {
      logger.logSocket("disconnect", clientId, { reason });

      // Clean up client data
      if (dbConnections.redis) {
        dbConnections.redis.del(`client:${clientId}`);
      }
    });

    // Send initial connection info
    socket.emit("connected", {
      clientId,
      timestamp: new Date().toISOString(),
      server: "wow-combat-parser-test",
    });
  });

  // Broadcast system events
  const broadcastSystemEvent = (event, data) => {
    io.emit("system-event", {
      event,
      data,
      timestamp: new Date().toISOString(),
    });
  };

  // Broadcast to guild room
  const broadcastToGuild = (guildId, event, data) => {
    const room = `guild-${guildId}`;
    io.to(room).emit(event, {
      ...data,
      guildId,
      timestamp: new Date().toISOString(),
    });
  };

  // Broadcast to encounter room
  const broadcastToEncounter = (encounterId, event, data) => {
    const room = `encounter-${encounterId}`;
    io.to(room).emit(event, {
      ...data,
      encounterId,
      timestamp: new Date().toISOString(),
    });
  };

  // Periodic system status broadcast
  const broadcastSystemStatus = async () => {
    try {
      const status = {
        connections: io.engine.clientsCount,
        databases: {
          postgres: dbConnections.postgres ? "connected" : "disconnected",
          influxdb: dbConnections.influxdb ? "connected" : "disconnected",
          redis: dbConnections.redis ? "connected" : "disconnected",
        },
        timestamp: new Date().toISOString(),
      };

      // Get active rooms
      const rooms = Array.from(io.sockets.adapter.rooms.keys()).filter(
        (room) => room.startsWith("guild-") || room.startsWith("encounter-"),
      );

      status.activeRooms = rooms.length;
      status.rooms = rooms;

      broadcastSystemEvent("status-update", status);
    } catch (error) {
      logger.error("Failed to broadcast system status:", error);
    }
  };

  // Start periodic status broadcast (every 30 seconds)
  const statusInterval = setInterval(broadcastSystemStatus, 30000);

  // Cleanup interval on shutdown
  process.on("SIGTERM", () => {
    clearInterval(statusInterval);
  });

  process.on("SIGINT", () => {
    clearInterval(statusInterval);
  });

  // Export broadcast functions for use by other routes
  return {
    broadcastSystemEvent,
    broadcastToGuild,
    broadcastToEncounter,
    getConnectionCount: () => io.engine.clientsCount,
    getRooms: () => Array.from(io.sockets.adapter.rooms.keys()),
  };
}

module.exports = setupWebSocket;
