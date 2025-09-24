"""
InfluxDB Manager for Combat Event Time-Series Data

This module handles all InfluxDB interactions for storing and querying
combat log event data in a time-series optimized format.
"""

import os
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timedelta
import json
from influxdb_client import InfluxDBClient, Point, WritePrecision, Dialect
from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS
from influxdb_client.client.query_api import QueryApi
from influxdb_client.client.flux_table import FluxRecord
from influxdb_client.client.exceptions import InfluxDBError

logger = logging.getLogger(__name__)


class InfluxDBManager:
    """
    Manager for InfluxDB time-series data storage of combat events.

    Stores combat log events with high-performance writes and efficient
    time-based queries for analysis.
    """

    def __init__(
        self,
        url: str = None,
        token: str = None,
        org: str = None,
        bucket: str = None,
        timeout: int = 30000,
        verify_ssl: bool = True
    ):
        """
        Initialize InfluxDB connection manager.

        Args:
            url: InfluxDB URL (defaults to env INFLUX_URL)
            token: Authentication token (defaults to env INFLUX_TOKEN)
            org: Organization (defaults to env INFLUX_ORG)
            bucket: Bucket name (defaults to env INFLUX_BUCKET)
            timeout: Connection timeout in ms
            verify_ssl: Whether to verify SSL certificates
        """
        # Get configuration from environment or parameters
        self.url = url or os.getenv("INFLUX_URL", "http://influxdb:8086")
        self.token = token or os.getenv("INFLUX_TOKEN", "lootbong-influx-token")
        self.org = org or os.getenv("INFLUX_ORG", "lootbong")
        self.bucket = bucket or os.getenv("INFLUX_BUCKET", "combat_events")

        # Initialize client
        self.client = InfluxDBClient(
            url=self.url,
            token=self.token,
            org=self.org,
            timeout=timeout,
            verify_ssl=verify_ssl
        )

        # Initialize APIs
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.write_api_async = self.client.write_api(write_options=ASYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.bucket_api = self.client.buckets_api()

        # Ensure bucket exists
        self._ensure_bucket_exists()

        logger.info(f"InfluxDB manager initialized: {self.url}/{self.bucket}")

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            buckets = self.bucket_api.find_buckets()
            bucket_names = [b.name for b in buckets.buckets]

            if self.bucket not in bucket_names:
                # Create bucket with 30 day retention by default
                retention_rules = [{
                    "everySeconds": 2592000,  # 30 days
                    "shardGroupDurationSeconds": 604800,  # 7 days
                    "type": "expire"
                }]

                self.bucket_api.create_bucket(
                    bucket_name=self.bucket,
                    retention_rules=retention_rules,
                    org=self.org
                )
                logger.info(f"Created InfluxDB bucket: {self.bucket}")
            else:
                logger.info(f"Using existing InfluxDB bucket: {self.bucket}")

        except Exception as e:
            logger.error(f"Failed to ensure bucket exists: {e}")
            # Continue anyway - bucket might exist but we can't list it

    def write_combat_event(
        self,
        encounter_id: str,
        timestamp: datetime,
        event_type: str,
        source_guid: str = None,
        source_name: str = None,
        target_guid: str = None,
        target_name: str = None,
        spell_id: int = None,
        spell_name: str = None,
        amount: float = None,
        overkill: float = None,
        school: str = None,
        critical: bool = False,
        absorbed: float = None,
        blocked: float = None,
        resisted: float = None,
        tags: Dict[str, str] = None,
        fields: Dict[str, Any] = None
    ) -> bool:
        """
        Write a single combat event to InfluxDB.

        Args:
            encounter_id: Unique encounter identifier
            timestamp: Event timestamp
            event_type: Type of combat event (DAMAGE, HEAL, BUFF, etc)
            source_guid: Source entity GUID
            source_name: Source entity name
            target_guid: Target entity GUID
            target_name: Target entity name
            spell_id: Spell/ability ID
            spell_name: Spell/ability name
            amount: Damage/healing amount
            overkill: Overkill amount
            school: Damage school
            critical: Whether this was a critical hit
            absorbed: Amount absorbed
            blocked: Amount blocked
            resisted: Amount resisted
            tags: Additional tags for filtering
            fields: Additional field values

        Returns:
            Success status
        """
        try:
            # Create point with measurement name
            point = Point("combat_event")

            # Add timestamp
            point.time(timestamp, WritePrecision.MS)

            # Add tags (indexed fields for filtering)
            point.tag("encounter_id", encounter_id)
            point.tag("event_type", event_type)

            if source_guid:
                point.tag("source_guid", source_guid)
            if source_name:
                point.tag("source_name", source_name)
            if target_guid:
                point.tag("target_guid", target_guid)
            if target_name:
                point.tag("target_name", target_name)
            if spell_id:
                point.tag("spell_id", str(spell_id))
            if spell_name:
                point.tag("spell_name", spell_name)
            if school:
                point.tag("school", school)

            # Add custom tags
            if tags:
                for key, value in tags.items():
                    point.tag(key, value)

            # Add fields (non-indexed values)
            if amount is not None:
                point.field("amount", float(amount))
            if overkill is not None:
                point.field("overkill", float(overkill))
            if absorbed is not None:
                point.field("absorbed", float(absorbed))
            if blocked is not None:
                point.field("blocked", float(blocked))
            if resisted is not None:
                point.field("resisted", float(resisted))

            point.field("critical", critical)

            # Add custom fields
            if fields:
                for key, value in fields.items():
                    point.field(key, value)

            # Write to InfluxDB
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            return True

        except Exception as e:
            logger.error(f"Failed to write combat event: {e}")
            return False

    def write_combat_events_batch(self, events: List[Dict[str, Any]]) -> bool:
        """
        Write multiple combat events in a batch for better performance.

        Args:
            events: List of event dictionaries with same structure as write_combat_event

        Returns:
            Success status
        """
        try:
            points = []

            for event in events:
                point = Point("combat_event")

                # Required fields
                point.time(event['timestamp'], WritePrecision.MS)
                point.tag("encounter_id", event['encounter_id'])
                point.tag("event_type", event['event_type'])

                # Optional tags
                for tag_field in ['source_guid', 'source_name', 'target_guid',
                                 'target_name', 'spell_name', 'school']:
                    if tag_field in event and event[tag_field]:
                        point.tag(tag_field, event[tag_field])

                if 'spell_id' in event and event['spell_id']:
                    point.tag("spell_id", str(event['spell_id']))

                # Custom tags
                if 'tags' in event and event['tags']:
                    for key, value in event['tags'].items():
                        point.tag(key, value)

                # Numeric fields
                for num_field in ['amount', 'overkill', 'absorbed', 'blocked', 'resisted']:
                    if num_field in event and event[num_field] is not None:
                        point.field(num_field, float(event[num_field]))

                # Boolean fields
                if 'critical' in event:
                    point.field("critical", event['critical'])

                # Custom fields
                if 'fields' in event and event['fields']:
                    for key, value in event['fields'].items():
                        point.field(key, value)

                points.append(point)

            # Write batch
            self.write_api.write(bucket=self.bucket, org=self.org, record=points)
            logger.debug(f"Wrote batch of {len(events)} combat events")
            return True

        except Exception as e:
            logger.error(f"Failed to write combat events batch: {e}")
            return False

    def query_encounter_events(
        self,
        encounter_id: str,
        start_time: datetime = None,
        end_time: datetime = None,
        event_types: List[str] = None,
        source_name: str = None,
        target_name: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Query combat events for a specific encounter.

        Args:
            encounter_id: Encounter identifier
            start_time: Start of time range
            end_time: End of time range
            event_types: Filter by event types
            source_name: Filter by source name
            target_name: Filter by target name
            limit: Maximum number of results

        Returns:
            List of event records
        """
        try:
            # Build Flux query
            query_parts = [
                f'from(bucket: "{self.bucket}")',
                f'|> range(start: {self._format_time(start_time)}, stop: {self._format_time(end_time)})'
                if start_time and end_time else
                '|> range(start: -30d)',  # Default to last 30 days
                '|> filter(fn: (r) => r._measurement == "combat_event")',
                f'|> filter(fn: (r) => r.encounter_id == "{encounter_id}")'
            ]

            # Add filters
            if event_types:
                types_str = ' or '.join([f'r.event_type == "{et}"' for et in event_types])
                query_parts.append(f'|> filter(fn: (r) => {types_str})')

            if source_name:
                query_parts.append(f'|> filter(fn: (r) => r.source_name == "{source_name}")')

            if target_name:
                query_parts.append(f'|> filter(fn: (r) => r.target_name == "{target_name}")')

            # Add limit if specified
            if limit:
                query_parts.append(f'|> limit(n: {limit})')

            # Sort by time
            query_parts.append('|> sort(columns: ["_time"])')

            # Build final query
            query = '\n'.join(query_parts)

            # Execute query
            result = self.query_api.query(org=self.org, query=query)

            # Parse results
            events = []
            for table in result:
                for record in table.records:
                    event = self._record_to_dict(record)
                    events.append(event)

            return events

        except Exception as e:
            logger.error(f"Failed to query encounter events: {e}")
            return []

    def query_player_statistics(
        self,
        encounter_id: str,
        player_name: str = None,
        metric_type: str = "damage"  # damage, healing, deaths
    ) -> List[Dict[str, Any]]:
        """
        Query aggregated statistics for players in an encounter.

        Args:
            encounter_id: Encounter identifier
            player_name: Optional specific player filter
            metric_type: Type of metric to aggregate

        Returns:
            List of aggregated statistics
        """
        try:
            # Build aggregation query based on metric type
            if metric_type == "damage":
                query = f"""
                from(bucket: "{self.bucket}")
                |> range(start: -30d)
                |> filter(fn: (r) => r._measurement == "combat_event")
                |> filter(fn: (r) => r.encounter_id == "{encounter_id}")
                |> filter(fn: (r) => r.event_type =~ /DAMAGE/)
                |> filter(fn: (r) => r._field == "amount")
                """
                if player_name:
                    query += f'|> filter(fn: (r) => r.source_name == "{player_name}")'
                query += """
                |> group(columns: ["source_name"])
                |> sum()
                |> yield(name: "total_damage")
                """

            elif metric_type == "healing":
                query = f"""
                from(bucket: "{self.bucket}")
                |> range(start: -30d)
                |> filter(fn: (r) => r._measurement == "combat_event")
                |> filter(fn: (r) => r.encounter_id == "{encounter_id}")
                |> filter(fn: (r) => r.event_type =~ /HEAL/)
                |> filter(fn: (r) => r._field == "amount")
                """
                if player_name:
                    query += f'|> filter(fn: (r) => r.source_name == "{player_name}")'
                query += """
                |> group(columns: ["source_name"])
                |> sum()
                |> yield(name: "total_healing")
                """

            else:  # deaths
                query = f"""
                from(bucket: "{self.bucket}")
                |> range(start: -30d)
                |> filter(fn: (r) => r._measurement == "combat_event")
                |> filter(fn: (r) => r.encounter_id == "{encounter_id}")
                |> filter(fn: (r) => r.event_type == "UNIT_DIED")
                """
                if player_name:
                    query += f'|> filter(fn: (r) => r.target_name == "{player_name}")'
                query += """
                |> group(columns: ["target_name"])
                |> count()
                |> yield(name: "death_count")
                """

            # Execute query
            result = self.query_api.query(org=self.org, query=query)

            # Parse results
            stats = []
            for table in result:
                for record in table.records:
                    stats.append({
                        "player": record.values.get("source_name") or record.values.get("target_name"),
                        "value": record.get_value(),
                        "metric": metric_type
                    })

            return sorted(stats, key=lambda x: x['value'], reverse=True)

        except Exception as e:
            logger.error(f"Failed to query player statistics: {e}")
            return []

    def delete_encounter_events(self, encounter_id: str) -> bool:
        """
        Delete all events for a specific encounter.

        Args:
            encounter_id: Encounter identifier

        Returns:
            Success status
        """
        try:
            delete_api = self.client.delete_api()

            # Delete data for the encounter
            delete_api.delete(
                start=datetime.utcnow() - timedelta(days=365),  # Look back 1 year
                stop=datetime.utcnow() + timedelta(days=1),  # Include today
                predicate=f'encounter_id="{encounter_id}"',
                bucket=self.bucket,
                org=self.org
            )

            logger.info(f"Deleted events for encounter: {encounter_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete encounter events: {e}")
            return False

    def health_check(self) -> bool:
        """
        Check if InfluxDB connection is healthy.

        Returns:
            Health status
        """
        try:
            # Try to query the bucket
            query = f'from(bucket: "{self.bucket}") |> range(start: -1m) |> limit(n: 1)'
            self.query_api.query(org=self.org, query=query)
            return True
        except Exception as e:
            logger.error(f"InfluxDB health check failed: {e}")
            return False

    def _format_time(self, dt: datetime) -> str:
        """Format datetime for Flux query."""
        if dt:
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return "-30d"  # Default to 30 days ago

    def _record_to_dict(self, record: FluxRecord) -> Dict[str, Any]:
        """Convert Flux record to dictionary."""
        return {
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
            "school": record.values.get("school"),
            "absorbed": record.values.get("absorbed"),
            "blocked": record.values.get("blocked"),
            "resisted": record.values.get("resisted"),
            "overkill": record.values.get("overkill")
        }

    def close(self):
        """Close InfluxDB connection."""
        try:
            self.client.close()
            logger.info("InfluxDB connection closed")
        except Exception as e:
            logger.error(f"Error closing InfluxDB connection: {e}")

    def __del__(self):
        """Cleanup on destruction."""
        self.close()