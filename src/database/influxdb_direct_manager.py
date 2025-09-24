"""
InfluxDB Direct Manager - Time-Series Native Combat Log Storage

This manager implements the pure time-series architecture where:
- ALL combat events stream directly to InfluxDB
- Encounters are defined as time windows not entities
- PostgreSQL only stores metadata (guilds characters summaries)
- Real-time aggregation using InfluxDB continuous queries
"""

import os
import logging
from typing import List, Dict, Any, Optional, Generator
from datetime import datetime, timedelta
import json
import uuid
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS
from influxdb_client.client.query_api import QueryApi
from influxdb_client.client.exceptions import InfluxDBError

from .postgres_adapter import PostgreSQLManager
from .influx_manager import InfluxDBManager

logger = logging.getLogger(__name__)


class InfluxDBDirectManager:
    """
    Pure time-series manager for combat event data.

    This replaces HybridDatabaseManager with a true time-series approach:
    - Events stream directly to InfluxDB without SQL storage
    - Encounters are time windows defined by ENCOUNTER_START/END events
    - Real-time aggregation and analytics via Flux queries
    """

    def __init__(
        self,
        influx_url: str = None,
        influx_token: str = None,
        influx_org: str = None,
        influx_bucket: str = None,
        postgres_enabled: bool = True
    ):
        """
        Initialize the time-series native manager.

        Args:
            influx_url: InfluxDB URL
            influx_token: InfluxDB authentication token
            influx_org: InfluxDB organization
            influx_bucket: InfluxDB bucket for combat events
            postgres_enabled: Whether to maintain PostgreSQL for metadata
        """
        logger.info("Initializing InfluxDB Direct Manager (Time-Series Native)")

        # Initialize InfluxDB for all combat event data
        self.influx = InfluxDBManager(
            url=influx_url,
            token=influx_token,
            org=influx_org,
            bucket=influx_bucket
        )

        # Initialize PostgreSQL only for metadata (optional)
        self.postgres = None
        if postgres_enabled:
            try:
                self.postgres = PostgreSQLManager()
                logger.info("PostgreSQL enabled for metadata storage")
            except Exception as e:
                logger.warning(f"PostgreSQL unavailable running InfluxDB-only: {e}")

        # Event streaming statistics
        self.stats = {
            "events_streamed": 0,
            "encounters_processed": 0,
            "streaming_errors": 0,
            "last_stream_time": None
        }

        logger.info("InfluxDB Direct Manager initialized successfully")

    def _validate_guild_id(self, guild_id: int = None) -> int:
        """
        Validate guild_id with fallback handling.

        Args:
            guild_id: Guild identifier to validate

        Returns:
            Valid guild_id (defaults to 1 if invalid/missing)
        """
        if guild_id is None or guild_id <= 0:
            logger.warning(f"Invalid or missing guild_id: {guild_id}, using fallback guild_id=1")
            return 1

        return guild_id

    def _generate_time_window_encounter_id(
        self,
        encounter_start: datetime,
        guild_id: int,
        boss_encounter_id: str = None,
        boss_name: str = None
    ) -> str:
        """
        Generate a time-window based encounter ID for proper time-series organization.

        The ID format includes:
        - Guild ID for multi-tenancy
        - Timestamp for time-series ordering
        - Boss encounter ID or name hash for encounter identification
        - Short UUID suffix for uniqueness

        Args:
            encounter_start: Start timestamp of the encounter
            guild_id: Guild identifier
            boss_encounter_id: Game's encounter ID (e.g., 2902 for Ulgrax)
            boss_name: Boss name as fallback identifier

        Returns:
            Time-window based encounter ID: "guild{guild_id}_t{timestamp}_enc{boss_id}_{uuid_suffix}"
        """
        try:
            # Convert timestamp to milliseconds for precision
            timestamp_ms = int(encounter_start.timestamp() * 1000)

            # Use boss encounter ID if available, otherwise hash boss name
            if boss_encounter_id:
                boss_identifier = str(boss_encounter_id)
            elif boss_name:
                import hashlib
                boss_hash = hashlib.sha256(boss_name.encode()).hexdigest()[:8]
                boss_identifier = f"hash{boss_hash}"
            else:
                boss_identifier = "unknown"

            # Generate short UUID suffix for uniqueness
            import uuid
            uuid_suffix = str(uuid.uuid4())[:8]

            # Create time-window based encounter ID
            encounter_id = f"guild{guild_id}_t{timestamp_ms}_enc{boss_identifier}_{uuid_suffix}"

            logger.debug(f"Generated time-window encounter ID: {encounter_id}")
            return encounter_id

        except Exception as e:
            logger.error(f"Failed to generate time-window encounter ID: {e}")
            # Fallback to UUID
            return str(uuid.uuid4())

    def process_encounter_event(self, event: Dict[str, Any], guild_id: int = None) -> bool:
        """
        Process ENCOUNTER_START or ENCOUNTER_END events for boundary detection.

        Args:
            event: Encounter event data
            guild_id: Guild identifier for multi-tenancy

        Returns:
            Success status
        """
        try:
            event_type = event.get('event_type')
            timestamp = event.get('timestamp')

            if not event_type or not timestamp:
                logger.warning(f"Invalid encounter event: missing type or timestamp")
                return False

            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

            validated_guild_id = self._validate_guild_id(guild_id)

            if event_type == "ENCOUNTER_START":
                # Store encounter start info for later pairing with END event
                encounter_key = f"{event.get('encounter_id', 'unknown')}_{validated_guild_id}"
                self._active_encounters = getattr(self, '_active_encounters', {})
                self._active_encounters[encounter_key] = {
                    'start_time': timestamp,
                    'boss_name': event.get('encounter_name', 'Unknown Boss'),
                    'difficulty': event.get('difficulty', 0),
                    'guild_id': validated_guild_id,
                    'encounter_id': event.get('encounter_id')
                }
                logger.info(f"Started encounter tracking: {encounter_key}")

            elif event_type == "ENCOUNTER_END":
                # Match with stored START event and create window
                encounter_key = f"{event.get('encounter_id', 'unknown')}_{validated_guild_id}"
                active_encounters = getattr(self, '_active_encounters', {})

                if encounter_key in active_encounters:
                    start_info = active_encounters[encounter_key]
                    encounter_metadata = {
                        'boss_name': start_info['boss_name'],
                        'difficulty': start_info['difficulty'],
                        'guild_id': validated_guild_id,
                        'encounter_id': start_info['encounter_id'],
                        'success': event.get('success', False)
                    }

                    # Create encounter window
                    window_id = self.define_encounter_window(
                        encounter_start=start_info['start_time'],
                        encounter_end=timestamp,
                        encounter_metadata=encounter_metadata
                    )

                    # Clean up active encounter
                    del active_encounters[encounter_key]
                    logger.info(f"Completed encounter: {encounter_key} -> {window_id}")
                else:
                    logger.warning(f"ENCOUNTER_END without matching START: {encounter_key}")

            return True

        except Exception as e:
            logger.error(f"Failed to process encounter event: {e}")
            return False

    def stream_combat_events(
        self,
        events: List[Dict[str, Any]],
        encounter_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Stream combat events directly to InfluxDB.

        This is the core method that replaces SQL storage with direct streaming.

        Args:
            events: List of combat events to stream
            encounter_context: Optional encounter metadata for tagging

        Returns:
            Success status
        """
        try:
            if not events:
                return True

            # Prepare events for InfluxDB with time-series optimizations
            influx_points = []
            encounter_id = encounter_context.get('encounter_id') if encounter_context else None

            for event in events:
                # Create InfluxDB point for each event
                point = Point("combat_events")

                # Set timestamp with high precision
                timestamp = event.get('timestamp')
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                point.time(timestamp, WritePrecision.MS)

                # Core tags for efficient querying (indexed)
                if encounter_id:
                    point.tag("encounter_id", encounter_id)
                point.tag("event_type", event.get('event_type', 'UNKNOWN'))

                if event.get('source_guid'):
                    point.tag("source_guid", event['source_guid'])
                if event.get('source_name'):
                    point.tag("source_name", event['source_name'])
                if event.get('target_guid'):
                    point.tag("target_guid", event['target_guid'])
                if event.get('target_name'):
                    point.tag("target_name", event['target_name'])

                # Spell/ability information
                if event.get('spell_id'):
                    point.tag("spell_id", str(event['spell_id']))
                if event.get('spell_name'):
                    point.tag("spell_name", event['spell_name'])
                if event.get('school'):
                    point.tag("school", event['school'])

                # Encounter context tags
                if encounter_context:
                    if encounter_context.get('boss_name'):
                        point.tag("boss_name", encounter_context['boss_name'])
                    if encounter_context.get('difficulty'):
                        point.tag("difficulty", encounter_context['difficulty'])
                    # Add guild_id with validation and fallback
                    guild_id_from_context = encounter_context.get('guild_id')
                    validated_guild_id = self._validate_guild_id(guild_id_from_context)
                    point.tag("guild_id", str(validated_guild_id))

                # Numeric fields (not indexed for aggregation)
                if event.get('amount') is not None:
                    point.field("amount", float(event['amount']))
                if event.get('overkill') is not None:
                    point.field("overkill", float(event['overkill']))
                if event.get('absorbed') is not None:
                    point.field("absorbed", float(event['absorbed']))
                if event.get('blocked') is not None:
                    point.field("blocked", float(event['blocked']))
                if event.get('resisted') is not None:
                    point.field("resisted", float(event['resisted']))

                # Boolean flags
                point.field("critical", event.get('critical', False))

                # Additional metadata as fields
                if event.get('raw_event'):
                    point.field("raw_event", str(event['raw_event']))

                influx_points.append(point)

            # Stream to InfluxDB in batch
            success = self.influx.write_api.write(
                bucket=self.influx.bucket,
                org=self.influx.org,
                record=influx_points
            )

            # Update statistics
            self.stats["events_streamed"] += len(events)
            self.stats["last_stream_time"] = datetime.now()

            logger.debug(f"Streamed {len(events)} events to InfluxDB")
            return True

        except Exception as e:
            self.stats["streaming_errors"] += 1
            logger.error(f"Failed to stream combat events: {e}")
            return False

    def define_encounter_window(
        self,
        encounter_start: datetime,
        encounter_end: datetime,
        encounter_metadata: Dict[str, Any]
    ) -> str:
        """
        Define an encounter as a time window in InfluxDB.

        This method creates encounter boundaries using time ranges rather
        than separate entity tables.

        Args:
            encounter_start: Start timestamp of encounter
            encounter_end: End timestamp of encounter
            encounter_metadata: Boss name difficulty success etc.

        Returns:
            Encounter window ID (UUID)
        """
        try:
            # Generate time-window based encounter ID
            encounter_id = self._generate_time_window_encounter_id(
                encounter_start=encounter_start,
                guild_id=encounter_metadata.get('guild_id', 1),
                boss_encounter_id=encounter_metadata.get('encounter_id'),
                boss_name=encounter_metadata.get('boss_name')
            )

            # Create encounter boundary markers in InfluxDB
            start_point = Point("encounter_boundary") \
                .tag("encounter_id", encounter_id) \
                .tag("boundary_type", "start") \
                .tag("boss_name", encounter_metadata.get('boss_name', '')) \
                .tag("difficulty", encounter_metadata.get('difficulty', '')) \
                .tag("guild_id", str(encounter_metadata.get('guild_id', 1))) \
                .field("success", False) \
                .time(encounter_start, WritePrecision.MS)

            end_point = Point("encounter_boundary") \
                .tag("encounter_id", encounter_id) \
                .tag("boundary_type", "end") \
                .tag("boss_name", encounter_metadata.get('boss_name', '')) \
                .tag("difficulty", encounter_metadata.get('difficulty', '')) \
                .tag("guild_id", str(encounter_metadata.get('guild_id', 1))) \
                .field("success", encounter_metadata.get('success', False)) \
                .field("duration_ms", int((encounter_end - encounter_start).total_seconds() * 1000)) \
                .time(encounter_end, WritePrecision.MS)

            # Write boundary markers
            self.influx.write_api.write(
                bucket=self.influx.bucket,
                org=self.influx.org,
                record=[start_point, end_point]
            )

            # Optionally store encounter summary in PostgreSQL
            if self.postgres:
                self._store_encounter_summary(encounter_id, encounter_start, encounter_end, encounter_metadata)

            self.stats["encounters_processed"] += 1
            logger.info(f"Defined encounter window: {encounter_id} ({encounter_metadata.get('boss_name')})")
            return encounter_id

        except Exception as e:
            logger.error(f"Failed to define encounter window: {e}")
            raise

    def query_encounter_events(
        self,
        encounter_id: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        event_types: List[str] = None,
        player_name: str = None,
        boss_name: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Query combat events using time windows.

        This demonstrates encounter-as-time-window queries instead of JOIN operations.

        Args:
            encounter_id: Specific encounter UUID
            start_time: Time window start (if not using encounter_id)
            end_time: Time window end (if not using encounter_id)
            event_types: Filter by event types
            player_name: Filter by player
            boss_name: Filter by boss encounter
            limit: Result limit

        Returns:
            List of combat events
        """
        try:
            # If encounter_id provided get time window from boundaries
            if encounter_id and not (start_time and end_time):
                boundary_query = f'''
                    from(bucket: "{self.influx.bucket}")
                    |> range(start: -30d)
                    |> filter(fn: (r) => r._measurement == "encounter_boundary")
                    |> filter(fn: (r) => r.encounter_id == "{encounter_id}")
                    |> pivot(rowKey:["_time"] columnKey: ["boundary_type"] valueColumn: "_time")
                '''

                boundary_result = self.influx.query_api.query(
                    org=self.influx.org,
                    query=boundary_query
                )

                # Extract time window from boundaries
                if boundary_result and boundary_result[0].records:
                    record = boundary_result[0].records[0]
                    start_time = record.values.get("start")
                    end_time = record.values.get("end")

                if not (start_time and end_time):
                    logger.warning(f"Could not find time window for encounter {encounter_id}")
                    return []

            # Build time-based event query
            if not (start_time and end_time):
                start_time = datetime.now() - timedelta(hours=1)
                end_time = datetime.now()

            query_parts = [
                f'from(bucket: "{self.influx.bucket}")',
                f'|> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)',
                '|> filter(fn: (r) => r._measurement == "combat_events")'
            ]

            # Add filters
            if encounter_id:
                query_parts.append(f'|> filter(fn: (r) => r.encounter_id == "{encounter_id}")')

            if event_types:
                event_filter = " or ".join([f'r.event_type == "{et}"' for et in event_types])
                query_parts.append(f'|> filter(fn: (r) => {event_filter})')

            if player_name:
                query_parts.append(f'|> filter(fn: (r) => r.source_name == "{player_name}" or r.target_name == "{player_name}")')

            if boss_name:
                query_parts.append(f'|> filter(fn: (r) => r.boss_name == "{boss_name}")')

            if limit:
                query_parts.append(f'|> limit(n: {limit})')

            query_parts.append('|> sort(columns: ["_time"])')

            # Execute time-series query
            flux_query = "\n".join(query_parts)
            result = self.influx.query_api.query(org=self.influx.org, query=flux_query)

            # Parse results into events
            events = []
            for table in result:
                for record in table.records:
                    event = {
                        "timestamp": record.get_time(),
                        "encounter_id": record.values.get("encounter_id"),
                        "event_type": record.values.get("event_type"),
                        "source_guid": record.values.get("source_guid"),
                        "source_name": record.values.get("source_name"),
                        "target_guid": record.values.get("target_guid"),
                        "target_name": record.values.get("target_name"),
                        "spell_id": record.values.get("spell_id"),
                        "spell_name": record.values.get("spell_name"),
                        "amount": record.get_value() if record.get_field() == "amount" else None,
                        "critical": record.values.get("critical"),
                        "school": record.values.get("school")
                    }
                    events.append(event)

            logger.debug(f"Queried {len(events)} events for time window")
            return events

        except Exception as e:
            logger.error(f"Failed to query encounter events: {e}")
            return []

    def aggregate_encounter_metrics(
        self,
        encounter_id: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        group_by: List[str] = None
    ) -> Dict[str, Any]:
        """
        Real-time aggregation of encounter metrics using Flux queries.

        This replaces complex SQL JOINs with time-series aggregations.

        Args:
            encounter_id: Specific encounter
            start_time: Time window start
            end_time: Time window end
            group_by: Grouping fields (source_name spell_name etc.)

        Returns:
            Aggregated metrics dictionary
        """
        try:
            if not group_by:
                group_by = ["source_name"]

            # Get time window if encounter_id provided
            if encounter_id and not (start_time and end_time):
                # Query encounter boundaries (implementation similar to above)
                pass

            # Build aggregation query
            group_by_str = '" "'.join(group_by)

            damage_query = f'''
                from(bucket: "{self.influx.bucket}")
                |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "combat_events")
                |> filter(fn: (r) => r.event_type =~ /.*DAMAGE.*/)
                |> filter(fn: (r) => r._field == "amount")
                |> group(columns: ["{group_by_str}"])
                |> sum()
                |> yield(name: "total_damage")
            '''

            healing_query = f'''
                from(bucket: "{self.influx.bucket}")
                |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "combat_events")
                |> filter(fn: (r) => r.event_type =~ /.*HEAL.*/)
                |> filter(fn: (r) => r._field == "amount")
                |> group(columns: ["{group_by_str}"])
                |> sum()
                |> yield(name: "total_healing")
            '''

            # Execute parallel aggregations
            damage_result = self.influx.query_api.query(org=self.influx.org, query=damage_query)
            healing_result = self.influx.query_api.query(org=self.influx.org, query=healing_query)

            # Combine results
            metrics = {
                "damage": {},
                "healing": {},
                "summary": {
                    "total_damage": 0,
                    "total_healing": 0,
                    "unique_players": 0
                }
            }

            # Process damage results
            for table in damage_result:
                for record in table.records:
                    key = record.values.get("source_name", "Unknown")
                    value = record.get_value() or 0
                    metrics["damage"][key] = value
                    metrics["summary"]["total_damage"] += value

            # Process healing results
            for table in healing_result:
                for record in table.records:
                    key = record.values.get("source_name", "Unknown")
                    value = record.get_value() or 0
                    metrics["healing"][key] = value
                    metrics["summary"]["total_healing"] += value

            # Calculate summary stats
            all_players = set(metrics["damage"].keys()) | set(metrics["healing"].keys())
            metrics["summary"]["unique_players"] = len(all_players)

            logger.debug(f"Aggregated metrics for {len(all_players)} players")
            return metrics

        except Exception as e:
            logger.error(f"Failed to aggregate encounter metrics: {e}")
            return {}

    def _store_encounter_summary(
        self,
        encounter_id: str,
        start_time: datetime,
        end_time: datetime,
        metadata: Dict[str, Any]
    ):
        """Store encounter summary in PostgreSQL for metadata queries."""
        if not self.postgres:
            return

        try:
            self.postgres.execute(
                """
                INSERT INTO combat_encounters (
                    id, guild_id, encounter_name, instance_name, difficulty,
                    start_time, end_time, duration_ms, success, player_count,
                    metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    duration_ms = EXCLUDED.duration_ms,
                    success = EXCLUDED.success,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    encounter_id,
                    metadata.get('guild_id', 1),
                    metadata.get('boss_name'),
                    metadata.get('instance_name'),
                    metadata.get('difficulty'),
                    start_time,
                    end_time,
                    int((end_time - start_time).total_seconds() * 1000),
                    metadata.get('success', False),
                    metadata.get('player_count', 0),
                    json.dumps(metadata)
                ),
                fetch_results=False
            )

        except Exception as e:
            logger.warning(f"Failed to store encounter summary in PostgreSQL: {e}")

    def health_check(self) -> Dict[str, bool]:
        """Check health of time-series storage."""
        health = {
            "influxdb": self.influx.health_check(),
            "postgres": self.postgres.health_check() if self.postgres else True
        }
        return health

    def get_stats(self) -> Dict[str Any]:
        """Get streaming statistics."""
        return {
            **self.stats,
            "influxdb_health": self.influx.health_check()
        }

    def close(self):
        """Close all connections."""
        if self.influx:
            self.influx.close()
        if self.postgres:
            self.postgres.close()
        logger.info("InfluxDB Direct Manager closed")

    # Backward compatibility methods for existing code
    def execute(self, query: str, params=None, fetch_results=True):
        """Backward compatibility - delegate to PostgreSQL for metadata queries."""
        if self.postgres:
            return self.postgres.execute(query, params, fetch_results)
        else:
            logger.warning("PostgreSQL not available for metadata queries")
            return [] if fetch_results else None

    def commit(self):
        """Backward compatibility - commit PostgreSQL transactions."""
        if self.postgres and hasattr(self.postgres, 'commit'):
            return self.postgres.commit()