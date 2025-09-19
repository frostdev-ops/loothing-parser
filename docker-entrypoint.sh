#!/bin/bash
set -e

# Docker entrypoint script for WoW Combat Log Parser
# Handles database initialization and application startup

echo "Starting WoW Combat Log Parser..."

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
    echo "Initializing database at $DB_PATH..."

    # Create database directory if it doesn't exist
    mkdir -p "$(dirname "$DB_PATH")"


    # Run database migrations
    if [ -d "/app/migrations" ]; then
        echo "Running database migrations..."
        python -c "
from src.database.schema import DatabaseManager, create_tables
import os
db_path = os.environ.get('DB_PATH', '/app/data/combat_logs.db')
db_manager = DatabaseManager(db_path)
create_tables(db_manager.engine)
db_manager.close()
print('Database initialized successfully')
"
    else
        echo "No migrations directory found, creating basic database..."
        python -c "
from src.database.schema import DatabaseManager, create_tables
import os
db_path = os.environ.get('DB_PATH', '/app/data/combat_logs.db')
db_manager = DatabaseManager(db_path)
create_tables(db_manager.engine)
db_manager.close()
print('Basic database created')
"
    fi
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

# Wait for any dependent services (if needed)
# This could be extended to wait for external databases, etc.

echo "Starting application..."
echo "Command: $@"

# Execute the main command
exec "$@"