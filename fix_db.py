#!/usr/bin/env python3
"""
Script to drop the combat_events table from PostgreSQL.
"""

import psycopg2
import psycopg2.extras
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_database():
    """Drop the combat_events table that was causing foreign key issues."""
    try:
        # Connection parameters
        conn_params = {
            "host": "192.168.10.137",
            "port": 5432,
            "database": "lootdata",
            "user": "lootbong",
            "password": "n8Gu%^4S7N%$!zIs"
        }

        logger.info("Connecting to PostgreSQL...")
        conn = psycopg2.connect(**conn_params)

        with conn.cursor() as cursor:
            # Drop the combat_events table if it exists
            logger.info("Dropping combat_events table...")
            cursor.execute("DROP TABLE IF EXISTS combat_events CASCADE")

            # Check what tables exist
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)

            tables = cursor.fetchall()
            logger.info(f"Existing tables: {[t[0] for t in tables]}")

            # Check columns in characters table
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'characters'
                AND table_schema = 'public'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            logger.info(f"Characters table columns: {columns}")

            # Check if character_metrics table exists and its columns
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'character_metrics'
                AND table_schema = 'public'
                ORDER BY ordinal_position
            """)
            metrics_columns = cursor.fetchall()
            if metrics_columns:
                logger.info(f"Character_metrics table columns: {metrics_columns}")
            else:
                logger.info("Character_metrics table does not exist")

        conn.commit()
        logger.info("Successfully cleaned up database!")
        conn.close()

    except Exception as e:
        logger.error(f"Failed to fix database: {e}")
        raise

if __name__ == "__main__":
    fix_database()