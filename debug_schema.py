#!/usr/bin/env python3
"""
Debug script to test schema creation.
"""
import traceback
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

try:
    from src.database.schema import DatabaseManager, create_tables

    db_path = '/app/data/combat_logs.db'
    logger.info(f"Creating database at {db_path}")

    db_manager = DatabaseManager(db_path)
    logger.info("DatabaseManager created successfully")

    logger.info("Starting table creation...")
    create_tables(db_manager)
    logger.info("Tables created successfully")

    # Test if tables exist
    cursor = db_manager.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    logger.info(f"Tables found: {[table[0] for table in tables]}")

    # Check character_metrics table specifically
    try:
        cursor = db_manager.execute("PRAGMA table_info(character_metrics);")
        columns = cursor.fetchall()
        logger.info(f"character_metrics columns: {columns}")

        # Check if combat_dps column exists
        combat_dps_exists = any(col[1] == 'combat_dps' for col in columns)
        logger.info(f"combat_dps column exists: {combat_dps_exists}")

    except Exception as e:
        logger.error(f"Error checking character_metrics table: {e}")

    db_manager.close()
    logger.info("Database closed successfully")

except Exception as e:
    logger.error(f"Error occurred: {e}")
    traceback.print_exc()