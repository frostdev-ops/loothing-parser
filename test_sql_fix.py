#!/usr/bin/env python3
"""
Test script to verify SQL parameter type error fixes.
"""
import logging
import tempfile
from pathlib import Path

from src.processing.unified_parallel_processor import UnifiedParallelProcessor
from src.database.schema import DatabaseManager, create_tables
from src.database.storage import EventStorage

# Set up logging to see debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_sql_fix():
    """Test the SQL parameter type error fixes."""
    logger.info("Starting SQL fix test...")

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        db_path = tmp_db.name

    try:
        # Initialize database
        db = DatabaseManager(db_path)
        create_tables(db)
        storage = EventStorage(db)

        # Process an example file with Tazavesh M+ content
        example_file = Path("examples/WoWCombatLog-091525_213021.txt")
        if not example_file.exists():
            logger.error(f"Example file not found: {example_file}")
            return False

        logger.info(f"Processing file: {example_file}")

        # Process with UnifiedParallelProcessor
        processor = UnifiedParallelProcessor()
        encounters = processor.process_file(example_file)

        logger.info(f"Found {len(encounters)} encounters")

        if not encounters:
            logger.warning("No encounters found in the file")
            return False

        # Store encounters in database - this is where the error occurred before
        result = storage.store_unified_encounters(
            encounters=encounters,
            log_file_path=str(example_file),
        )

        logger.info(f"Storage result: {result}")
        logger.info("SQL fix test completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up
        try:
            db.close()
            Path(db_path).unlink(missing_ok=True)
        except:
            pass

if __name__ == "__main__":
    success = test_sql_fix()
    exit(0 if success else 1)