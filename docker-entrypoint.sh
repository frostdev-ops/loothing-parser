#!/bin/bash
set -e

# Docker entrypoint script for WoW Combat Log Parser
# Handles database initialization and unified server startup

# Ensure Python can find our modules
export PYTHONPATH=/app

echo "Starting WoW Combat Log Parser (Unified Server: Streaming + REST API v1)..."

# Ensure the script runs as root initially for permission setup
if [ "$(id -u)" -eq 0 ]; then
    # Create data directory and set permissions
    mkdir -p /app/data /app/logs
    chown -R appuser:appuser /app/data /app/logs
    chmod 755 /app/data /app/logs

    # Re-exec this script as appuser for the rest of the process
    exec gosu appuser "$0" "$@"
fi

# Initialize database if it doesn't exist
if [ ! -f "$DB_PATH" ]; then
    echo "Database will be initialized by application at $DB_PATH..."
    # Create database directory if it doesn't exist
    mkdir -p "$(dirname "$DB_PATH")"
else
    echo "Database already exists at $DB_PATH"
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
echo "  Database: $DB_PATH"
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Log Level: $LOG_LEVEL"
echo ""
echo "Available Endpoints:"
echo "  WebSocket Streaming: ws://$HOST:$PORT/stream"
echo "  REST API v1: http://$HOST:$PORT/api/v1/*"
echo "  Health Check: http://$HOST:$PORT/health"
echo "  API Documentation: http://$HOST:$PORT/docs"
echo "  Metrics: http://$HOST:$PORT/metrics"

# Wait for any dependent services (if needed)
# This could be extended to wait for external databases, etc.

echo "Starting application..."
echo "Command: $@"

# Execute the main command
exec "$@"