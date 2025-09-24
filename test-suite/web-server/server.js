const express = require("express");
const http = require("http");
const socketIo = require("socket.io");
const path = require("path");
const cors = require("cors");
const helmet = require("helmet");
const compression = require("compression");
const morgan = require("morgan");
const rateLimit = require("express-rate-limit");
require("dotenv").config();

// Import custom modules
const logger = require("./services/logger");
const { connectPostgres } = require("./services/postgres");
const { connectInfluxDB } = require("./services/influxdb");
const { connectRedis } = require("./services/redis");

// Import routes
const uploadRoutes = require("./routes/upload");
const encounterRoutes = require("./routes/encounters");
const metricsRoutes = require("./routes/metrics");
const websocketHandler = require("./routes/websocket");

// Initialize Express app
const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
  cors: {
    origin: process.env.CORS_ORIGIN || "*",
    methods: ["GET", "POST"],
  },
});

// Environment configuration
const PORT = process.env.PORT || 3000;
const NODE_ENV = process.env.NODE_ENV || "development";

// Security middleware
app.use(
  helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        styleSrc: ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        scriptSrc: [
          "'self'",
          "'unsafe-inline'",
          "https://cdn.jsdelivr.net",
          "https://cdnjs.cloudflare.com",
        ],
        imgSrc: ["'self'", "data:", "https:"],
        connectSrc: ["'self'", "ws:", "wss:"],
      },
    },
  }),
);

// CORS configuration
app.use(
  cors({
    origin: process.env.CORS_ORIGIN || true,
    credentials: true,
  }),
);

// Compression and parsing
app.use(compression());
app.use(express.json({ limit: "50mb" }));
app.use(express.urlencoded({ extended: true, limit: "50mb" }));

// Logging
app.use(
  morgan("combined", {
    stream: { write: (message) => logger.info(message.trim()) },
  }),
);

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // limit each IP to 100 requests per windowMs
  message: "Too many requests from this IP, please try again later.",
  standardHeaders: true,
  legacyHeaders: false,
});
app.use(limiter);

// Upload rate limiting (more restrictive)
const uploadLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, // 1 hour
  max: 10, // limit each IP to 10 uploads per hour
  message: "Upload limit exceeded, please try again later.",
  standardHeaders: true,
  legacyHeaders: false,
});

// Static files
app.use(
  express.static(path.join(__dirname, "public"), {
    maxAge: "1h",
    etag: true,
  }),
);

// Database connections
let dbConnections = {
  postgres: null,
  influxdb: null,
  redis: null,
};

// Connect to databases
async function initializeDatabases() {
  try {
    logger.info("Initializing database connections...");

    // Connect to PostgreSQL
    dbConnections.postgres = await connectPostgres();
    logger.info("PostgreSQL connection established");

    // Connect to InfluxDB
    dbConnections.influxdb = await connectInfluxDB();
    logger.info("InfluxDB connection established");

    // Connect to Redis
    dbConnections.redis = await connectRedis();
    logger.info("Redis connection established");

    logger.info("All database connections initialized successfully");
    return true;
  } catch (error) {
    logger.error("Failed to initialize databases:", error);
    return false;
  }
}

// Make database connections available to routes
app.use((req, res, next) => {
  req.db = dbConnections;
  req.io = io;
  next();
});

// Health check endpoint
app.get("/health", (req, res) => {
  const health = {
    status: "healthy",
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    databases: {
      postgres: dbConnections.postgres ? "connected" : "disconnected",
      influxdb: dbConnections.influxdb ? "connected" : "disconnected",
      redis: dbConnections.redis ? "connected" : "disconnected",
    },
  };

  res.json(health);
});

// API routes
app.use("/api/upload", uploadLimiter, uploadRoutes);
app.use("/api/encounters", encounterRoutes);
app.use("/api/metrics", metricsRoutes);

// Serve main dashboard
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

// Serve upload interface
app.get("/upload", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "upload.html"));
});

// 404 handler
app.use("*", (req, res) => {
  res.status(404).json({ error: "Route not found" });
});

// Global error handler
app.use((error, req, res, next) => {
  logger.error("Unhandled error:", error);
  res.status(500).json({
    error: "Internal server error",
    ...(NODE_ENV === "development" && {
      details: error.message,
      stack: error.stack,
    }),
  });
});

// WebSocket handling
websocketHandler(io, dbConnections);

// Graceful shutdown
process.on("SIGTERM", () => {
  logger.info("SIGTERM received, shutting down gracefully...");
  server.close(() => {
    logger.info("HTTP server closed");

    // Close database connections
    if (dbConnections.postgres) {
      dbConnections.postgres.end();
    }
    if (dbConnections.redis) {
      dbConnections.redis.quit();
    }

    process.exit(0);
  });
});

process.on("SIGINT", () => {
  logger.info("SIGINT received, shutting down gracefully...");
  server.close(() => {
    logger.info("HTTP server closed");

    // Close database connections
    if (dbConnections.postgres) {
      dbConnections.postgres.end();
    }
    if (dbConnections.redis) {
      dbConnections.redis.quit();
    }

    process.exit(0);
  });
});

// Start server
async function startServer() {
  try {
    // Initialize databases first
    const dbInitialized = await initializeDatabases();
    if (!dbInitialized) {
      logger.warn("Starting server without all database connections");
    }

    // Start HTTP server
    server.listen(PORT, "0.0.0.0", () => {
      logger.info(`Server running on port ${PORT} in ${NODE_ENV} mode`);
      logger.info(`Dashboard: http://localhost:${PORT}`);
      logger.info(`Upload interface: http://localhost:${PORT}/upload`);
      logger.info(`Health check: http://localhost:${PORT}/health`);
    });
  } catch (error) {
    logger.error("Failed to start server:", error);
    process.exit(1);
  }
}

// Handle unhandled promise rejections
process.on("unhandledRejection", (reason, promise) => {
  logger.error("Unhandled Rejection at:", promise, "reason:", reason);
});

// Handle uncaught exceptions
process.on("uncaughtException", (error) => {
  logger.error("Uncaught Exception:", error);
  process.exit(1);
});

// Start the application
startServer();
