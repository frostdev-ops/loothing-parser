"""
Hybrid Database Manager for Combat Log Storage

Routes data to appropriate database:
- InfluxDB: Time-series combat event data
- PostgreSQL: Relational metadata characters encounters etc.
"""

import os
import logging
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import hashlib
import json

from .postgres_adapter import PostgreSQLManager
from .influx_manager import InfluxDBManager

logger = logging.getLogger(__name__)


class HybridDatabaseManager:
    """
    Manages both PostgreSQL and InfluxDB for optimal data storage.

    - Combat events go to InfluxDB for time-series optimization
    - Metadata summaries and relational data go to PostgreSQL
    """

    def __init__(self):
        """Initialize both database connections."""
        logger.info("Initializing hybrid database manager...")

        # Initialize PostgreSQL for relational data
        self.postgres = PostgreSQLManager()

        # Initialize InfluxDB for time-series data
        self.influx = InfluxDBManager()

        # Run PostgreSQL migrations if needed
        self._ensure_schema()

        logger.info("Hybrid database manager initialized successfully")

    def _ensure_schema(self):
        """Ensure PostgreSQL schema is up to date."""
        try:
            # Check if schema version table exists
            result = self.postgres.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'schema_version'
                )
                """
            )

            if not result or not result[0][0]:
                logger.info("Schema not found applying initial migration...")
                self._apply_initial_migration()
            else:
                # Check current version
                result = self.postgres.execute(
                    "SELECT MAX(version) FROM schema_version"
                )
                current_version = result[0][0] if result else 0
                logger.info(f"Current schema version: {current_version}")

        except Exception as e:
            logger.error(f"Failed to ensure schema: {e}")
            # Try to apply initial migration anyway
            self._apply_initial_migration()

    def _apply_initial_migration(self):
        """Apply the initial schema migration."""
        try:
            migration_file = os.path.join(
                os.path.dirname(__file__),
                "migrations",
                "001_initial_schema.sql",
            )

            if os.path.exists(migration_file):
                with open(migration_file, 'r') as f:
                    migration_sql = f.read()

                # Split by semicolons and execute each statement
                statements = [s.strip() for s in migration_sql.split(';') if s.strip()]
                for statement in statements:
                    if statement:
                        self.postgres.execute(statement, fetch_results=False)

                logger.info("Initial migration applied successfully")
            else:
                logger.warning(f"Migration file not found: {migration_file}")

        except Exception as e:
            logger.error(f"Failed to apply initial migration: {e}")

    def execute(self, query: str, params=None, fetch_results=True):
        """
        Execute SQL query through PostgreSQL connection.

        This method provides backward compatibility for code expecting
        a unified database interface with an execute() method.

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_results: Whether to return results

        Returns:
            Query results if fetch_results=True, otherwise None
        """
        return self.postgres.execute(query, params, fetch_results)

    def commit(self):
        """
        Commit transaction through PostgreSQL connection.

        This method provides backward compatibility for code expecting
        a unified database interface with a commit() method.
        """
        if hasattr(self.postgres, 'commit'):
            return self.postgres.commit()
        else:
            # PostgreSQL connections usually auto-commit unless in transaction
            logger.debug("PostgreSQL connection does not require explicit commit")

    def save_encounter(
        self,
        encounter_data: Dict[str, Any],
        guild_id: int = 1
    ) -> str:
        """
        Save encounter metadata to PostgreSQL.

        Args:
            encounter_data: Encounter information
            guild_id: Guild identifier

        Returns:
            Encounter ID (UUID)
        """
        try:
            import uuid

            # Generate UUID for encounter
            encounter_id = encounter_data.get('id')
            if not encounter_id:
                encounter_id = str(uuid.uuid4())

            # Calculate duration in milliseconds
            duration_ms = None
            if encounter_data.get('start_time') and encounter_data.get('end_time'):
                start = encounter_data['start_time']
                end = encounter_data['end_time']
                if isinstance(start, str):
                    from datetime import datetime
                    start = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    end = datetime.fromisoformat(end.replace('Z', '+00:00'))
                duration_ms = int((end - start).total_seconds() * 1000)

            # Save to PostgreSQL using existing combat_encounters table
            self.postgres.execute(
                """
                INSERT INTO combat_encounters (
                    id, guild_id, encounter_name, instance_name, difficulty,
                    start_time, end_time, duration_ms, combat_duration_ms,
                    success, player_count, total_damage, total_healing,
                    total_deaths, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    duration_ms = EXCLUDED.duration_ms,
                    combat_duration_ms = EXCLUDED.combat_duration_ms,
                    success = EXCLUDED.success,
                    total_damage = EXCLUDED.total_damage,
                    total_healing = EXCLUDED.total_healing,
                    updated_at = CURRENT_TIMESTAMP
                """, 
                (
                    encounter_id,
                    guild_id,
                    encounter_data.get('name'),
                    encounter_data.get('zone_name'),
                    encounter_data.get('difficulty'),
                    encounter_data.get('start_time'),
                    encounter_data.get('end_time'),
                    duration_ms,
                    duration_ms,  # Use same value for combat_duration_ms
                    encounter_data.get('success', False),
                    encounter_data.get('player_count', 0),
                    encounter_data.get('total_damage', 0),
                    encounter_data.get('total_healing', 0),
                    encounter_data.get('total_deaths', 0),
                    json.dumps(encounter_data.get('metadata', {}))
                ),
                fetch_results=False
            )

            logger.debug(f"Saved encounter metadata: {encounter_id}")
            return encounter_id

        except Exception as e:
            logger.error(f"Failed to save encounter: {e}")
            raise

    def save_combat_event(
        self,
        encounter_id: str,
        event: Dict[str, Any],
        guild_id: int = None
    ) -> bool:
        """
        Save a single combat event to InfluxDB.

        Args:
            encounter_id: Encounter identifier
            event: Combat event data
            guild_id: Guild identifier for multi-tenant isolation

        Returns:
            Success status
        """
        try:
            # Extract event data
            timestamp = event.get('timestamp')
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

            # Add guild_id to tags for multi-tenant isolation
            tags = event.get('tags', {}) or {}
            if guild_id:
                tags['guild_id'] = str(guild_id)

            return self.influx.write_combat_event(
                encounter_id=encounter_id,
                timestamp=timestamp,
                event_type=event.get('event_type'),
                source_guid=event.get('source_guid'),
                source_name=event.get('source_name'),
                target_guid=event.get('target_guid'),
                target_name=event.get('target_name'),
                spell_id=event.get('spell_id'),
                spell_name=event.get('spell_name'),
                amount=event.get('amount'),
                overkill=event.get('overkill'),
                school=event.get('school'),
                critical=event.get('critical', False),
                absorbed=event.get('absorbed'),
                blocked=event.get('blocked'),
                resisted=event.get('resisted'),
                guild_id=guild_id,
                tags=tags,
                fields=event.get('fields')
            )

        except Exception as e:
            logger.error(f"Failed to save combat event: {e}")
            return False

    def save_combat_events_batch(
        self,
        encounter_id: str,
        events: List[Dict[str, Any]],
        guild_id: int = None
    ) -> bool:
        """
        Save multiple combat events in batch to InfluxDB.

        Args:
            encounter_id: Encounter identifier
            events: List of combat events
            guild_id: Guild identifier for multi-tenant isolation

        Returns:
            Success status
        """
        try:
            # Prepare events for batch write
            influx_events = []
            for event in events:
                # Ensure timestamp is datetime
                timestamp = event.get('timestamp')
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

                # Add guild_id to tags for multi-tenant isolation
                tags = event.get('tags', {}) or {}
                if guild_id:
                    tags['guild_id'] = str(guild_id)

                influx_event = {
                    'encounter_id': encounter_id,
                    'timestamp': timestamp,
                    'event_type': event.get('event_type'),
                    'source_guid': event.get('source_guid'),
                    'source_name': event.get('source_name'),
                    'target_guid': event.get('target_guid'),
                    'target_name': event.get('target_name'),
                    'spell_id': event.get('spell_id'),
                    'spell_name': event.get('spell_name'),
                    'amount': event.get('amount'),
                    'overkill': event.get('overkill'),
                    'school': event.get('school'),
                    'critical': event.get('critical', False),
                    'absorbed': event.get('absorbed'),
                    'blocked': event.get('blocked'),
                    'resisted': event.get('resisted'),
                    'tags': tags,
                    'fields': event.get('fields', {})
                }
                influx_events.append(influx_event)

            return self.influx.write_combat_events_batch(influx_events, guild_id=guild_id)

        except Exception as e:
            logger.error(f"Failed to save combat events batch: {e}")
            return False

    def save_character(
        self,
        character_data: Dict[str, Any],
        guild_id: int = 1
    ) -> int:
        """
        Save or update character to PostgreSQL.

        Args:
            character_data: Character information
            guild_id: Guild identifier

        Returns:
            Character ID
        """
        try:
            # Map to existing database schema
            # The existing database uses different column names
            character_name = character_data.get('name')
            server = character_data.get('realm')

            # Check if character exists
            result = self.postgres.execute(
                "SELECT id FROM characters WHERE character_name = %s AND server = %s",
                (character_name, server)
            )

            if result:
                character_id = result[0]['id']
                self.postgres.execute(
                    """
                    UPDATE characters SET
                        class = %s, spec = %s, role = %s,
                        level = %s, item_level_equipped = %s, item_level_overall = %s,
                        race = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        character_data.get('class'),
                        character_data.get('spec'),
                        character_data.get('role'),
                        character_data.get('level'),
                        character_data.get('item_level'),
                        character_data.get('item_level'),
                        character_data.get('race'),
                        character_id
                    ),
                    fetch_results=False
                )
            else:
                # Insert new character using existing schema
                # Note: id is UUID in existing schema
                import uuid
                new_id = str(uuid.uuid4())

                result = self.postgres.execute(
                    """
                    INSERT INTO characters (
                        id, guild_id, character_name, server, region,
                        class, spec, role, level,
                        item_level_equipped, item_level_overall, race
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        new_id,
                        guild_id,
                        character_name,
                        server,
                        character_data.get('region', 'US'),
                        character_data.get('class'),
                        character_data.get('spec'),
                        character_data.get('role'),
                        character_data.get('level'),
                        character_data.get('item_level'),
                        character_data.get('item_level'),
                        character_data.get('race')
                    )
                )
                character_id = result[0]['id']

            logger.debug(f"Saved character: {character_id} - {character_data.get('name')}")
            return character_id

        except Exception as e:
            logger.error(f"Failed to save character: {e}")
            raise

    def save_character_metrics(
        self,
        encounter_id: str,
        metrics: List[Dict[str, Any]]
    ) -> bool:
        """
        Save character performance metrics to PostgreSQL.

        Args:
            encounter_id: Encounter identifier (UUID)
            metrics: List of character metrics

        Returns:
            Success status
        """
        try:
            import uuid

            for metric in metrics:
                # Get character ID if we have the name
                character_id = None
                character_name = metric.get('character_name')
                if character_name:
                    result = self.postgres.execute(
                        "SELECT id FROM characters WHERE character_name = %s",
                        (character_name,)
                    )
                    if result:
                        character_id = result[0]['id']

                # Generate UUID for performance record
                perf_id = str(uuid.uuid4())

                self.postgres.execute(
                    """
                    INSERT INTO combat_performances (
                        id, guild_id, encounter_id, character_id, character_name,
                        class, spec, role, item_level,
                        damage_done, healing_done, damage_taken, overhealing,
                        absorb_healing, deaths, interrupts, dispels,
                        active_time_ms, dps, hps, dtps, activity_percentage,
                        metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        perf_id,
                        metric.get('guild_id', 1),
                        encounter_id,
                        character_id,
                        character_name,
                        metric.get('class'),
                        metric.get('spec'),
                        metric.get('role', 'DPS'),  # Default to DPS if not specified
                        metric.get('item_level'),
                        metric.get('damage_done', 0),
                        metric.get('healing_done', 0),
                        metric.get('damage_taken', 0),
                        metric.get('overhealing', 0),
                        metric.get('absorb_healing', 0),
                        metric.get('deaths', 0),
                        metric.get('interrupts', 0),
                        metric.get('dispels', 0),
                        int(metric.get('active_time', 0) * 1000),  # Convert to milliseconds
                        metric.get('dps', 0.0),
                        metric.get('hps', 0.0),
                        metric.get('dtps', 0.0),
                        metric.get('activity_percent', 0.0),
                        json.dumps(metric.get('metadata', {}))
                    ),
                    fetch_results=False
                )

            logger.debug(f"Saved {len(metrics)} character performances for encounter {encounter_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save character performances: {e}")
            return False

    def query_encounter_events(
        self,
        encounter_id: str,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Query combat events from InfluxDB.

        Args:
            encounter_id: Encounter identifier
            **filters: Additional filters

        Returns:
            List of events
        """
        return self.influx.query_encounter_events(encounter_id, **filters)

    def query_player_statistics(
        self,
        encounter_id: str,
        player_name: str = None,
        metric_type: str = "damage"
    ) -> List[Dict[str, Any]]:
        """
        Query player statistics from InfluxDB.

        Args:
            encounter_id: Encounter identifier
            player_name: Optional player filter
            metric_type: Type of metric

        Returns:
            List of statistics
        """
        return self.influx.query_player_statistics(encounter_id, player_name, metric_type)

    def get_encounter_metadata(
        self,
        encounter_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get encounter metadata from PostgreSQL.

        Args:
            encounter_id: Encounter identifier

        Returns:
            Encounter metadata or None
        """
        try:
            result = self.postgres.execute(
                "SELECT * FROM combat_encounters WHERE id = %s",
                (encounter_id,)
            )
            return result[0] if result else None

        except Exception as e:
            logger.error(f"Failed to get encounter metadata: {e}")
            return None

    def health_check(self) -> Dict[str, bool]:
        """
        Check health of both database connections.

        Returns:
            Health status for each database
        """
        return {
            "postgresql": self.postgres.health_check(),
            "influxdb": self.influx.health_check()
        }

    def rollback(self):
        """Rollback PostgreSQL transaction."""
        if hasattr(self.postgres, 'rollback'):
            return self.postgres.rollback()
        else:
            logger.warning("PostgreSQL manager does not support rollback")

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in PostgreSQL."""
        try:
            result = self.postgres.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = %s
                )
                """,
                (table_name,)
            )
            return result[0][0] if result else False
        except Exception as e:
            logger.error(f"Failed to check table existence: {e}")
            return False

    def close(self):
        """Close all database connections."""
        if hasattr(self, 'postgres'):
            self.postgres.close()
        if hasattr(self, 'influx'):
            self.influx.close()
        logger.info("Hybrid database manager closed")

    def __del__(self):
        """Cleanup on destruction."""
        try:
            self.close()
        except Exception:
            pass  # Ignore errors during cleanup