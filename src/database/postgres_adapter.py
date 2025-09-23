"""
PostgreSQL database adapter for WoW combat log storage.

Provides PostgreSQL connectivity for Docker Compose environments while
maintaining compatibility with the existing schema structure.
"""

import os
import logging
from typing import Optional, Dict, Any, List, Union
import time
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from urllib.parse import quote

logger = logging.getLogger(__name__)


class PostgreSQLManager:
    """
    Manages PostgreSQL database connections for Docker environments.

    Provides connection pooling, transaction management, and schema
    operations compatible with the existing SQLite schema.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        **kwargs
    ):
        """
        Initialize PostgreSQL database manager.

        Args:
            host: Database host (from env DB_HOST)
            port: Database port (from env DB_PORT)
            database: Database name (from env DB_NAME)
            user: Database user (from env DB_USER)
            password: Database password (from env DB_PASSWORD)
        """
        # Get configuration from environment or parameters
        self.host = host or os.getenv("DB_HOST", "localhost")
        self.port = port or int(os.getenv("DB_PORT", "5432"))
        self.database = database or os.getenv("DB_NAME", "lootdata")
        self.user = user or os.getenv("DB_USER", "lootbong")
        self.password = password or os.getenv("DB_PASSWORD", "")

        # Connection pool settings
        self.min_connections = int(os.getenv("DB_POOL_MIN", "2"))
        self.max_connections = int(os.getenv("DB_POOL_MAX", "20"))

        self.connection_pool: Optional[ThreadedConnectionPool] = None
        self._setup_database()

    def _setup_database(self):
        """Initialize database connection pool and ensure tables exist."""
        try:
            # Build connection string
            # Note: psycopg2 handles special characters in password correctly when passed as parameters
            conn_params = {
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "user": self.user,
                "password": self.password
            }

            # Create connection pool with parameters dict (handles special chars properly)
            self.connection_pool = ThreadedConnectionPool(
                minconn=self.min_connections,
                maxconn=self.max_connections,
                **conn_params
            )

            logger.info(f"PostgreSQL connection pool created: {self.host}:{self.port}/{self.database}")

            # Test connection and create schema if needed
            self._initialize_schema()

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection: {e}")
            raise RuntimeError(f"Database connection failed: {e}")

    def _initialize_schema(self):
        """Check that required tables exist in the database."""
        # The main application has already created all necessary tables
        # We just need to verify they exist
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check that essential tables exist
                    cursor.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name IN ('characters', 'combat_encounters', 'combat_performances', 'guilds')
                    """)

                    existing_tables = [row[0] for row in cursor.fetchall()]

                    required_tables = ['characters', 'combat_encounters', 'combat_performances']
                    missing_tables = [t for t in required_tables if t not in existing_tables]

                    if missing_tables:
                        logger.warning(f"Missing tables in database: {missing_tables}")
                        # Don't fail - the main app will create these
                    else:
                        logger.info(f"Verified required tables exist: {required_tables}")

            logger.info("PostgreSQL schema check completed")

    def get_connection(self):
        """Get a connection from the pool."""
        if not self.connection_pool:
            raise RuntimeError("Database connection pool not initialized")

        return self.connection_pool.getconn()

    def put_connection(self, conn):
        """Return a connection to the pool."""
        if self.connection_pool:
            self.connection_pool.putconn(conn)

    def execute(self, query: str, params: tuple = None, fetch_results: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a SQL query with optional parameters.

        Args:
            query: SQL query string
            params: Query parameters
            fetch_results: Whether to fetch and return results

        Returns:
            Query results as list of dictionaries, or None
        """
        conn = None
        try:
            conn = self.get_connection()

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, params)

                if fetch_results and cursor.description:
                    results = cursor.fetchall()
                    # Convert to list of dicts for compatibility
                    return [dict(row) for row in results]

            conn.commit()
            return None

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database query failed: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise
        finally:
            if conn:
                self.put_connection(conn)

    def execute_many(self, query: str, params_list: List[tuple]) -> None:
        """
        Execute a query multiple times with different parameters.

        Args:
            query: SQL query string
            params_list: List of parameter tuples
        """
        conn = None
        try:
            conn = self.get_connection()

            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)

            conn.commit()

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Batch database operation failed: {e}")
            raise
        finally:
            if conn:
                self.put_connection(conn)

    def begin_transaction(self):
        """Begin a new transaction and return connection."""
        conn = self.get_connection()
        conn.autocommit = False
        return conn

    def health_check(self) -> bool:
        """
        Check database health.

        Returns:
            True if database is healthy, False otherwise
        """
        try:
            result = self.execute("SELECT 1", fetch_results=True)
            return len(result) == 1 and result[0]['?column?'] == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def close(self):
        """Close all connections in the pool."""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("PostgreSQL connection pool closed")

    def __del__(self):
        """Cleanup on object destruction."""
        self.close()


# Compatibility adapter to match SQLite interface
class DatabaseManager:
    """
    Database manager that automatically selects PostgreSQL or SQLite based on environment.
    Maintains compatibility with existing SQLite interface.
    """

    def __init__(self, db_path: str = "combat_logs.db"):
        """
        Initialize database manager with automatic backend selection.

        Args:
            db_path: SQLite database path (used only if PostgreSQL not available)
        """
        # Check if we're in a Docker environment with PostgreSQL
        if os.getenv("DB_HOST") and os.getenv("DB_NAME"):
            logger.info("Using PostgreSQL database backend")
            self.backend = PostgreSQLManager()
            self.db_type = "postgresql"
        else:
            # Fall back to SQLite for standalone operation
            logger.info(f"Using SQLite database backend: {db_path}")
            from .schema import DatabaseManager as SQLiteManager
            self.backend = SQLiteManager(db_path)
            self.db_type = "sqlite"

    def execute(self, query: str, params: tuple = None, fetch_results: bool = True) -> Optional[List[Dict[str, Any]]]:
        """Execute query on the appropriate backend."""
        if self.db_type == "postgresql":
            return self.backend.execute(query, params, fetch_results)
        else:
            # SQLite backend compatibility
            if fetch_results:
                return self.backend.execute(query, params)
            else:
                self.backend.execute(query, params)
                return None

    def execute_many(self, query: str, params_list: List[tuple]) -> None:
        """Execute many queries on the appropriate backend."""
        return self.backend.execute_many(query, params_list)

    def health_check(self) -> bool:
        """Check database health."""
        if hasattr(self.backend, 'health_check'):
            return self.backend.health_check()
        else:
            # Basic health check for SQLite
            try:
                self.execute("SELECT 1")
                return True
            except:
                return False

    def close(self):
        """Close database connections."""
        if hasattr(self.backend, 'close'):
            self.backend.close()

    def __del__(self):
        """Cleanup on destruction."""
        self.close()