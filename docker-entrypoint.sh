#!/bin/bash
set -e

# Docker entrypoint script for WoW Combat Log Parser
# Handles database initialization and unified server startup

# Ensure Python can find our modules
export PYTHONPATH=/app

echo "Starting WoW Combat Log Parser (Unified Server: Streaming + REST API v1)..."

# Detect database backend
if [ -n "$DB_HOST" ] && [ -n "$DB_NAME" ]; then
    echo "PostgreSQL backend detected:"
    echo "  Host: ${DB_HOST}:${DB_PORT:-5432}"
    echo "  Database: $DB_NAME"
    echo "  User: $DB_USER"
    DATABASE_TYPE="postgresql"
else
    echo "SQLite backend detected:"
    echo "  Database: ${DB_PATH:-combat_logs.db}"
    DATABASE_TYPE="sqlite"
fi

# Detect Redis configuration
if [ -n "$REDIS_HOST" ]; then
    echo "Redis caching enabled:"
    echo "  Host: ${REDIS_HOST}:${REDIS_PORT:-6379}"
    echo "  Database: ${REDIS_DB:-0}"
    REDIS_ENABLED="true"
else
    echo "Redis caching disabled (using memory cache)"
    REDIS_ENABLED="false"
fi

# Ensure the script runs as root initially for permission setup
if [ "$(id -u)" -eq 0 ]; then
    # Create data directory and set permissions
    mkdir -p /app/parser/data /app/parser/logs /app/parser/uploads

    # Only set ownership if appuser exists
    if id appuser >/dev/null 2>&1; then
        chown -R appuser:appuser /app/parser/data /app/parser/logs /app/parser/uploads
        chmod 755 /app/parser/data /app/parser/logs /app/parser/uploads
        # Re-exec this script as appuser for the rest of the process
        exec gosu appuser "$0" "$@"
    fi
fi

# Initialize SQLite database if using SQLite backend and database doesn't exist
if [ "$DATABASE_TYPE" = "sqlite" ]; then
    DB_PATH=${DB_PATH:-combat_logs.db}
    if [ ! -f "$DB_PATH" ]; then
        echo "SQLite database will be initialized by application at $DB_PATH..."
        # Create database directory if it doesn't exist
        mkdir -p "$(dirname "$DB_PATH")"
    else
        echo "SQLite database already exists at $DB_PATH"
    fi
fi

# Validate environment variables
if [ -z "$API_KEY" ]; then
    echo "Warning: API_KEY not set, using default key for development"
    export API_KEY="default-development-key"
fi

# Set log level
case "${LOG_LEVEL,,}" in
    debug|info|warning|error)
        echo "Log level set to: $LOG_LEVEL"
        ;;
    *)
        echo "Invalid LOG_LEVEL '$LOG_LEVEL', defaulting to 'info'"
        export LOG_LEVEL="info"
        ;;
esac

# Validate port
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "Invalid PORT '$PORT', defaulting to 8000"
    export PORT=8000
fi

echo "Configuration:"
if [ "$DATABASE_TYPE" = "postgresql" ]; then
    echo "  Database: PostgreSQL (${DB_HOST}:${DB_PORT:-5432}/${DB_NAME})"
else
    echo "  Database: SQLite (${DB_PATH:-combat_logs.db})"
fi
echo "  Cache: $REDIS_ENABLED"
echo "  Host: ${PARSER_HOST:-0.0.0.0}"
echo "  Port: ${PARSER_PORT:-8000}"
echo "  Log Level: ${LOG_LEVEL:-info}"
echo "  Workers: ${WORKER_COUNT:-1}"
echo ""
echo "Available Endpoints:"
echo "  WebSocket Streaming: ws://${PARSER_HOST:-0.0.0.0}:${PARSER_PORT:-8000}/stream"
echo "  REST API v1: http://${PARSER_HOST:-0.0.0.0}:${PARSER_PORT:-8000}/api/v1/*"
echo "  Health Check: http://${PARSER_HOST:-0.0.0.0}:${PARSER_PORT:-8000}/health"
echo "  API Documentation: http://${PARSER_HOST:-0.0.0.0}:${PARSER_PORT:-8000}/docs"
echo "  Metrics: http://${PARSER_HOST:-0.0.0.0}:${PARSER_PORT:-8000}/metrics"

# Wait for any dependent services (if needed)
# This could be extended to wait for external databases, etc.

echo "Starting application..."
echo "Command: $@"

# Execute the main command
exec "$@"