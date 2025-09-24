#!/usr/bin/env python3
"""
Integration script to switch parser to use existing database schema.

This script helps integrate the ExistingSchemaAdapter into the parser system,
allowing it to work with the existing lootbong database schema instead of
creating its own tables.

Usage:
    python scripts/integrate_existing_schema.py [--dry-run] [--validate]
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add parser source to path
parser_root = Path(__file__).parent.parent
sys.path.insert(0, str(parser_root / "src"))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def validate_environment():
    """Validate that environment is ready for existing schema integration."""
    logger.info("Validating environment for existing schema integration...")

    checks = {
        "database_config": False,
        "required_tables": False,
        "dependencies": False
    }

    # Check database environment variables
    required_env_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these variables in your .env file or environment")
    else:
        logger.info("✅ Database configuration environment variables found")
        checks["database_config"] = True

    # Check if adapter files exist
    adapter_path = parser_root / "src" / "database" / "existing_schema_adapter.py"
    config_path = parser_root / "src" / "config" / "existing_schema_config.py"

    if not adapter_path.exists():
        logger.error(f"❌ ExistingSchemaAdapter not found at {adapter_path}")
    elif not config_path.exists():
        logger.error(f"❌ Configuration module not found at {config_path}")
    else:
        logger.info("✅ Adapter and configuration files found")
        checks["dependencies"] = True

    # Check database connection (if possible)
    try:
        from config.existing_schema_config import get_database_config, validate_existing_schema_environment

        db_config = get_database_config()
        logger.info(f"✅ Database config loaded: {db_config['host']}:{db_config['port']}/{db_config['database']}")

        env_checks = validate_existing_schema_environment()
        logger.info("Environment validation results:")
        for check, result in env_checks.items():
            if result is True:
                logger.info(f"  ✅ {check}")
            elif result is False:
                logger.warning(f"  ❌ {check}")
            else:
                logger.info(f"  ⚠️  {check} (needs database connection to verify)")

    except Exception as e:
        logger.error(f"❌ Failed to validate configuration: {e}")
        return False

    success = all(checks.values())
    if success:
        logger.info("✅ Environment validation passed!")
    else:
        logger.error("❌ Environment validation failed!")

    return success


def create_integration_example():
    """Create an example of how to integrate the adapter."""
    logger.info("Creating integration example...")

    example_path = parser_root / "examples" / "integrated_parser_example.py"
    example_path.parent.mkdir(exist_ok=True)

    example_code = '''#!/usr/bin/env python3
"""
Example of integrated parser using ExistingSchemaAdapter.

This example shows how to use the parser with the existing database schema
instead of creating new tables.
"""

import os
import sys
from pathlib import Path

# Add parser source to path
parser_root = Path(__file__).parent.parent
sys.path.insert(0, str(parser_root / "src"))

from database.existing_schema_adapter import ExistingSchemaAdapter
from config.existing_schema_config import create_adapter_from_config, get_database_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IntegratedCombatParser:
    """Combat parser that works with existing database schema."""

    def __init__(self):
        """Initialize parser with existing schema adapter."""
        self.db_config = get_database_config()
        self.db_connection = self._create_db_connection()
        self.adapter = create_adapter_from_config(self.db_connection)

        logger.info("Combat parser initialized with existing schema adapter")

    def _create_db_connection(self):
        """Create database connection based on configuration."""
        # This would use your actual database connection class
        # For example, if using the existing DatabaseManager:

        try:
            from database.schema import DatabaseManager
            return DatabaseManager()
        except ImportError:
            # Fallback for testing
            logger.warning("Using mock database connection for testing")
            return MockDatabaseConnection()

    def get_recent_encounters(self, guild_id, limit=10):
        """Get recent encounters for a guild."""
        return self.adapter.get_encounters(guild_id=guild_id, limit=limit)

    def get_player_performance(self, encounter_id, character_name=None, guild_id=None):
        """Get player performance metrics for an encounter."""
        return self.adapter.get_character_metrics(encounter_id, guild_id, character_name)

    def get_guild_top_performers(self, guild_id, metric='dps', limit=10):
        """Get top performers for a guild."""
        return self.adapter.get_top_performers(metric, guild_id, limit)

    def get_database_statistics(self):
        """Get database statistics."""
        return self.adapter.get_database_stats()


class MockDatabaseConnection:
    """Mock database connection for testing without actual database."""

    def __init__(self):
        self.backend_type = "postgresql"

    def execute(self, query, params=(), fetch_results=True):
        logger.info(f"Mock query executed: {query[:50]}...")
        return []


def main():
    """Example usage of integrated parser."""
    try:
        # Initialize integrated parser
        parser = IntegratedCombatParser()

        # Example: Get recent encounters for guild ID 1
        encounters = parser.get_recent_encounters(guild_id=1, limit=5)
        logger.info(f"Found {len(encounters)} recent encounters")

        # Example: Get top DPS performers
        top_dps = parser.get_guild_top_performers(guild_id=1, metric='dps', limit=5)
        logger.info(f"Found {len(top_dps)} top DPS performers")

        # Example: Get database stats
        stats = parser.get_database_statistics()
        logger.info(f"Database statistics: {stats}")

        logger.info("Integration example completed successfully!")

    except Exception as e:
        logger.error(f"Integration example failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

    with open(example_path, 'w') as f:
        f.write(example_code)

    os.chmod(example_path, 0o755)
    logger.info(f"✅ Integration example created at {example_path}")


def update_database_manager():
    """Suggest updates to database manager to use adapter."""
    logger.info("Checking database manager for integration opportunities...")

    schema_path = parser_root / "src" / "database" / "schema.py"
    if not schema_path.exists():
        logger.warning(f"Database schema file not found at {schema_path}")
        return

    logger.info("Found database schema file")
    logger.info("Suggested integration steps:")
    logger.info("1. Modify DatabaseManager.__init__ to detect existing schema")
    logger.info("2. Add adapter initialization when existing schema is detected")
    logger.info("3. Update create_tables() to skip table creation when using existing schema")
    logger.info("4. Update query methods to use adapter when available")

    suggested_code = """
# Add to DatabaseManager.__init__:
def __init__(self, db_path="combat_logs.db", use_existing_schema=None):
    # ... existing init code ...

    # Check if we should use existing schema
    if use_existing_schema is None:
        use_existing_schema = os.getenv('PARSER_USE_EXISTING_SCHEMA', 'false').lower() == 'true'

    self.use_existing_schema = use_existing_schema
    self.adapter = None

    if self.use_existing_schema:
        from .existing_schema_adapter import ExistingSchemaAdapter
        from ..config.existing_schema_config import create_adapter_from_config
        self.adapter = create_adapter_from_config(self)
        logger.info("Using existing schema adapter")

# Modify create_tables():
def create_tables(self):
    if self.use_existing_schema:
        logger.info("Skipping table creation - using existing schema")
        return

    # ... existing create_tables code ...
"""

    logger.info("Example integration code:")
    print(suggested_code)


def main():
    """Main integration script."""
    parser = argparse.ArgumentParser(description="Integrate existing schema adapter")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--validate", action="store_true", help="Only validate environment")
    parser.add_argument("--create-example", action="store_true", help="Create integration example")

    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")

    # Always validate environment first
    if not validate_environment():
        logger.error("Environment validation failed. Please fix issues before continuing.")
        return 1

    if args.validate:
        logger.info("Validation complete - environment is ready for existing schema integration")
        return 0

    # Create integration example
    if args.create_example or not args.validate:
        if not args.dry_run:
            create_integration_example()

    # Show database manager integration suggestions
    update_database_manager()

    logger.info("Integration preparation complete!")
    logger.info("Next steps:")
    logger.info("1. Review the integration example")
    logger.info("2. Update your parser initialization code to use the adapter")
    logger.info("3. Set PARSER_USE_EXISTING_SCHEMA=true in your environment")
    logger.info("4. Test with your existing database")

    return 0


if __name__ == "__main__":
    sys.exit(main())