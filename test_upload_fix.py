#!/usr/bin/env python3
"""
Test script to simulate the upload service and verify SQL fixes.
"""
import logging
import tempfile
import asyncio
from pathlib import Path

# Set up logging to see debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_upload_simulation():
    """Simulate the upload service process that was failing."""
    logger.info("Starting upload simulation test...")

    try:
        # Import after setting up logging
        from src.database.schema import DatabaseManager, create_tables
        from src.database.storage import EventStorage
        from src.processing.unified_parallel_processor import UnifiedParallelProcessor

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name

        # Initialize database
        db = DatabaseManager(db_path)
        create_tables(db)
        storage = EventStorage(db)

        # Create a small test file with just the M+ start event
        test_content = '''9/15/2025 22:13:48.068-4  CHALLENGE_MODE_START,"Tazavesh, the Veiled Market",2441,392,13,[9,10,147]
9/15/2025 22:13:49.000-4  COMBATANT_INFO,Player-1168-0A9943A9,0,500,120,1000,550,0.0,0.0,0.0,5.0,5.0,5.0,100,0.0,10.0,0.0,0.0,1,[1,2,3]
9/15/2025 22:14:48.068-4  CHALLENGE_MODE_END,2441,1,13,60000,[392]
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_file:
            tmp_file.write(test_content)
            test_file_path = tmp_file.name

        logger.info(f"Created test file: {test_file_path}")

        # Process with UnifiedParallelProcessor (same as upload service)
        processor = UnifiedParallelProcessor()
        encounters = processor.process_file(test_file_path)

        logger.info(f"Found {len(encounters)} encounters")

        if encounters:
            logger.info(f"First encounter: {encounters[0].encounter_name}")
            logger.info(f"Instance ID: {encounters[0].instance_id} (type: {type(encounters[0].instance_id)})")

        # Store encounters in database - this is where the error occurred before
        result = storage.store_unified_encounters(
            encounters=encounters,
            log_file_path=test_file_path,
        )

        logger.info(f"Storage result: {result}")
        logger.info("Upload simulation test completed successfully!")

        # Clean up
        Path(test_file_path).unlink(missing_ok=True)
        db.close()
        Path(db_path).unlink(missing_ok=True)

        return True

    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_upload_simulation())
    exit(0 if success else 1)