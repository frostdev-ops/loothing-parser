const express = require("express");
const multer = require("multer");
const path = require("path");
const fs = require("fs").promises;
const axios = require("axios");
const FormData = require("form-data");
const { v4: uuidv4 } = require("uuid");
const logger = require("../services/logger");

const router = express.Router();

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: async (req, file, cb) => {
    const uploadDir = path.join(__dirname, "../uploads");
    try {
      await fs.mkdir(uploadDir, { recursive: true });
      cb(null, uploadDir);
    } catch (error) {
      logger.error("Failed to create upload directory:", error);
      cb(error);
    }
  },
  filename: (req, file, cb) => {
    // Generate unique filename with timestamp
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const uniqueSuffix = uuidv4().substring(0, 8);
    const extension = path.extname(file.originalname);
    const basename = path.basename(file.originalname, extension);

    const filename = `${basename}_${timestamp}_${uniqueSuffix}${extension}`;
    cb(null, filename);
  },
});

// File filter for combat log files
const fileFilter = (req, file, cb) => {
  const allowedMimes = ["text/plain", "text/log", "application/octet-stream"];

  const allowedExts = [".txt", ".log"];
  const fileExt = path.extname(file.originalname).toLowerCase();

  // Check file extension
  if (!allowedExts.includes(fileExt)) {
    return cb(new Error("Only .txt and .log files are allowed"), false);
  }

  // Check MIME type (more flexible for different systems)
  if (!allowedMimes.includes(file.mimetype)) {
    logger.warn(`Unusual MIME type for combat log: ${file.mimetype}`);
    // Allow anyway, as combat logs might have different MIME types
  }

  cb(null, true);
};

// Configure multer
const upload = multer({
  storage,
  fileFilter,
  limits: {
    fileSize: 500 * 1024 * 1024, // 500MB max file size
    files: 1, // Only one file at a time
  },
});

/**
 * Upload combat log file
 */
router.post("/", upload.single("combatLog"), async (req, res) => {
  const startTime = Date.now();
  const uploadId = uuidv4();

  try {
    if (!req.file) {
      return res.status(400).json({
        error: "No file uploaded",
        details: "Please select a combat log file to upload",
      });
    }

    const { file } = req;
    const { guildId = 1, guildName, description } = req.body;

    logger.info(
      `Upload started: ${file.originalname} (${(file.size / 1024 / 1024).toFixed(2)}MB)`,
    );

    // Store upload metadata in Redis
    if (req.db.redis) {
      await req.db.redis.cache(
        `upload:${uploadId}`,
        {
          id: uploadId,
          originalName: file.originalname,
          filename: file.filename,
          size: file.size,
          guildId: parseInt(guildId),
          guildName,
          description,
          status: "uploaded",
          uploadTime: new Date().toISOString(),
          clientId: req.sessionID || "unknown",
        },
        3600,
      ); // 1 hour TTL
    }

    // Emit upload start event via WebSocket
    if (req.io) {
      req.io.emit("upload:started", {
        uploadId,
        filename: file.originalname,
        size: file.size,
        guildId: parseInt(guildId),
      });
    }

    // Send file to Python API for processing
    const parsingResult = await sendToParser(file.path, {
      guildId: parseInt(guildId),
      guildName,
      description,
      uploadId,
    });

    // Update upload status
    if (req.db.redis) {
      await req.db.redis.cache(
        `upload:${uploadId}`,
        {
          id: uploadId,
          originalName: file.originalname,
          filename: file.filename,
          size: file.size,
          guildId: parseInt(guildId),
          guildName,
          description,
          status: "processed",
          uploadTime: new Date().toISOString(),
          processingTime: Date.now() - startTime,
          result: parsingResult,
          clientId: req.sessionID || "unknown",
        },
        3600,
      );
    }

    // Clean up uploaded file
    try {
      await fs.unlink(file.path);
      logger.debug(`Cleaned up uploaded file: ${file.filename}`);
    } catch (cleanupError) {
      logger.warn(`Failed to cleanup uploaded file: ${cleanupError.message}`);
    }

    const duration = Date.now() - startTime;
    logger.logUpload(file.originalname, file.size, duration, true);

    // Emit completion event
    if (req.io) {
      req.io.emit("upload:completed", {
        uploadId,
        filename: file.originalname,
        duration,
        result: parsingResult,
      });
    }

    res.json({
      success: true,
      uploadId,
      filename: file.originalname,
      size: file.size,
      processingTime: duration,
      result: parsingResult,
    });
  } catch (error) {
    logger.error("Upload processing error:", error);

    // Update upload status with error
    if (req.db.redis) {
      try {
        await req.db.redis.cache(
          `upload:${uploadId}`,
          {
            id: uploadId,
            originalName: req.file?.originalname || "unknown",
            status: "failed",
            error: error.message,
            uploadTime: new Date().toISOString(),
            processingTime: Date.now() - startTime,
            clientId: req.sessionID || "unknown",
          },
          3600,
        );
      } catch (redisError) {
        logger.error("Failed to update upload status in Redis:", redisError);
      }
    }

    // Emit error event
    if (req.io) {
      req.io.emit("upload:error", {
        uploadId,
        filename: req.file?.originalname || "unknown",
        error: error.message,
      });
    }

    // Clean up file if it exists
    if (req.file?.path) {
      try {
        await fs.unlink(req.file.path);
      } catch (cleanupError) {
        logger.warn(
          `Failed to cleanup failed upload file: ${cleanupError.message}`,
        );
      }
    }

    const duration = Date.now() - startTime;
    logger.logUpload(
      req.file?.originalname || "unknown",
      req.file?.size || 0,
      duration,
      false,
    );

    res.status(500).json({
      error: "Upload processing failed",
      details: error.message,
      uploadId,
    });
  }
});

/**
 * Get upload status
 */
router.get("/status/:uploadId", async (req, res) => {
  try {
    const { uploadId } = req.params;

    if (!req.db.redis) {
      return res.status(503).json({
        error: "Upload tracking not available",
        details: "Redis connection not available",
      });
    }

    const uploadStatus = await req.db.redis.get(`upload:${uploadId}`);

    if (!uploadStatus) {
      return res.status(404).json({
        error: "Upload not found",
        details: `No upload found with ID: ${uploadId}`,
      });
    }

    res.json(uploadStatus);
  } catch (error) {
    logger.error("Get upload status error:", error);
    res.status(500).json({
      error: "Failed to get upload status",
      details: error.message,
    });
  }
});

/**
 * Get recent uploads
 */
router.get("/recent", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    const guildId = req.query.guildId ? parseInt(req.query.guildId) : null;

    if (req.db.redis) {
      // Try to get from Redis cache first
      const cacheKey = `recent_uploads:${guildId || "all"}:${limit}`;
      const cached = await req.db.redis.get(cacheKey);
      if (cached) {
        return res.json(cached);
      }
    }

    // Get from PostgreSQL
    const recentUploads = guildId
      ? await req.db.postgres.getLogFiles(guildId, limit)
      : await req.db.postgres
          .query(
            "SELECT * FROM log_files ORDER BY processed_at DESC LIMIT $1",
            [limit],
          )
          .then((result) => result.rows);

    const response = {
      uploads: recentUploads,
      total: recentUploads.length,
      guildId,
      limit,
    };

    // Cache for 5 minutes
    if (req.db.redis) {
      const cacheKey = `recent_uploads:${guildId || "all"}:${limit}`;
      await req.db.redis.cache(cacheKey, response, 300);
    }

    res.json(response);
  } catch (error) {
    logger.error("Get recent uploads error:", error);
    res.status(500).json({
      error: "Failed to get recent uploads",
      details: error.message,
    });
  }
});

/**
 * Delete upload record
 */
router.delete("/:uploadId", async (req, res) => {
  try {
    const { uploadId } = req.params;

    if (!req.db.redis) {
      return res.status(503).json({
        error: "Upload management not available",
      });
    }

    const deleted = await req.db.redis.del(`upload:${uploadId}`);

    if (deleted === 0) {
      return res.status(404).json({
        error: "Upload not found",
      });
    }

    res.json({
      success: true,
      message: "Upload record deleted",
    });
  } catch (error) {
    logger.error("Delete upload error:", error);
    res.status(500).json({
      error: "Failed to delete upload",
      details: error.message,
    });
  }
});

/**
 * Send file to Python parser API
 */
async function sendToParser(filePath, metadata) {
  try {
    const parserUrl = process.env.PARSER_API_URL || "http://localhost:8000";
    const apiKey = process.env.API_KEY || "test-api-key-123";

    // Create form data
    const formData = new FormData();
    const fileStream = await fs.readFile(filePath);
    formData.append("file", fileStream, {
      filename: path.basename(filePath),
      contentType: "text/plain",
    });

    // Add metadata
    if (metadata.guildId) {
      formData.append("guild_id", metadata.guildId.toString());
    }
    if (metadata.guildName) {
      formData.append("guild_name", metadata.guildName);
    }
    if (metadata.description) {
      formData.append("description", metadata.description);
    }

    // Send to parser
    const response = await axios.post(
      `${parserUrl}/api/v1/parse/upload`,
      formData,
      {
        headers: {
          "X-API-Key": apiKey,
          ...formData.getHeaders(),
        },
        timeout: 300000, // 5 minutes timeout
        maxContentLength: 500 * 1024 * 1024, // 500MB
        maxBodyLength: 500 * 1024 * 1024,
      },
    );

    logger.info(
      `Parser response: ${response.status} - ${JSON.stringify(response.data)}`,
    );
    return response.data;
  } catch (error) {
    logger.error("Parser API error:", error.response?.data || error.message);

    if (error.response) {
      throw new Error(
        `Parser API error (${error.response.status}): ${error.response.data?.error || error.message}`,
      );
    } else if (error.code === "ECONNREFUSED") {
      throw new Error("Parser API is not available");
    } else {
      throw new Error(`Parser communication error: ${error.message}`);
    }
  }
}

/**
 * Handle multer errors
 */
router.use((error, req, res, next) => {
  if (error instanceof multer.MulterError) {
    logger.warn("Multer error:", error);

    switch (error.code) {
      case "LIMIT_FILE_SIZE":
        return res.status(400).json({
          error: "File too large",
          details: "Maximum file size is 500MB",
        });
      case "LIMIT_FILE_COUNT":
        return res.status(400).json({
          error: "Too many files",
          details: "Only one file can be uploaded at a time",
        });
      case "LIMIT_UNEXPECTED_FILE":
        return res.status(400).json({
          error: "Unexpected file field",
          details: 'Use field name "combatLog" for file uploads',
        });
      default:
        return res.status(400).json({
          error: "Upload error",
          details: error.message,
        });
    }
  }

  // Handle custom file filter errors
  if (error.message.includes("Only .txt and .log files are allowed")) {
    return res.status(400).json({
      error: "Invalid file type",
      details: "Only .txt and .log files are allowed for combat logs",
    });
  }

  next(error);
});

module.exports = router;
