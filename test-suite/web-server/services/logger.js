const winston = require("winston");
const path = require("path");

// Custom log format
const logFormat = winston.format.combine(
  winston.format.timestamp({
    format: "YYYY-MM-DD HH:mm:ss",
  }),
  winston.format.errors({ stack: true }),
  winston.format.printf(({ level, message, timestamp, stack }) => {
    if (stack) {
      return `${timestamp} [${level.toUpperCase()}]: ${message}\n${stack}`;
    }
    return `${timestamp} [${level.toUpperCase()}]: ${message}`;
  }),
);

// Create logger instance
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || "info",
  format: logFormat,
  defaultMeta: { service: "wow-web-server" },
  transports: [
    // Console output
    new winston.transports.Console({
      format: winston.format.combine(winston.format.colorize(), logFormat),
    }),

    // Error log file
    new winston.transports.File({
      filename: path.join(__dirname, "../logs/error.log"),
      level: "error",
      maxsize: 10 * 1024 * 1024, // 10MB
      maxFiles: 5,
      tailable: true,
    }),

    // Combined log file
    new winston.transports.File({
      filename: path.join(__dirname, "../logs/combined.log"),
      maxsize: 10 * 1024 * 1024, // 10MB
      maxFiles: 5,
      tailable: true,
    }),
  ],
});

// Create logs directory if it doesn't exist
const fs = require("fs");
const logsDir = path.join(__dirname, "../logs");
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}

// Add request logging helper
logger.logRequest = (req, res, responseTime) => {
  const logData = {
    method: req.method,
    url: req.originalUrl,
    status: res.statusCode,
    responseTime: `${responseTime}ms`,
    userAgent: req.get("User-Agent"),
    ip: req.ip || req.connection.remoteAddress,
  };

  const level = res.statusCode >= 400 ? "warn" : "info";
  logger.log(
    level,
    `${req.method} ${req.originalUrl} - ${res.statusCode} - ${responseTime}ms`,
    logData,
  );
};

// Add database operation logging helper
logger.logDbOperation = (operation, table, duration, success = true) => {
  const level = success ? "debug" : "error";
  const message = `DB ${operation} on ${table} - ${duration}ms - ${success ? "SUCCESS" : "FAILED"}`;
  logger.log(level, message);
};

// Add upload logging helper
logger.logUpload = (filename, size, duration, success = true) => {
  const level = success ? "info" : "error";
  const sizeInMB = (size / (1024 * 1024)).toFixed(2);
  const message = `Upload ${filename} (${sizeInMB}MB) - ${duration}ms - ${success ? "SUCCESS" : "FAILED"}`;
  logger.log(level, message);
};

// Add WebSocket logging helper
logger.logSocket = (event, clientId, data = {}) => {
  logger.debug(`WebSocket ${event} from client ${clientId}`, data);
};

module.exports = logger;
