"""
Query Federation Layer for Hybrid Database Architecture
Unified interface for PostgreSQL and InfluxDB with automatic tier selection
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple
from enum import Enum

import structlog
import pandas as pd
from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from .config import QueryFederationConfig
from .postgres_queries import PostgreSQLQueries
from .influx_queries import InfluxDBQueries
from .cache_manager import QueryCacheManager
from .query_optimizer import QueryOptimizer


logger = structlog.get_logger(__name__)


class DataTier(Enum):
    """Data storage tiers with different characteristics."""
    HOT = "hot"           # < 7 days, full resolution, InfluxDB
    WARM = "warm"         # 7-30 days, 5-min aggregates, InfluxDB
    COLD = "cold"         # > 30 days, 1-hour aggregates, S3/InfluxDB
    RELATIONAL = "pg"     # Relational data, PostgreSQL


class QueryType(Enum):
    """Types of queries supported by the federation layer."""
    COMBAT_EVENTS = "combat_events"
    PLAYER_METRICS = "player_metrics"
    ENCOUNTER_SUMMARY = "encounter_summary"
    CROSS_NODE_METRICS = "cross_node_metrics"
    GUILD_DATA = "guild_data"
    CHARACTER_DATA = "character_data"
    LOOT_DATA = "loot_data"


class QueryFederation:
    """
    Unified query interface across PostgreSQL and InfluxDB.

    Features:
    - Automatic tier selection based on time range
    - Query optimization and caching
    - Cross-database joins
    - Performance monitoring
    """

    def __init__(self, config: QueryFederationConfig):
        self.config = config

        # Database connections
        self.pg_engine = None
        self.pg_session_factory = None
        self.influx_client = None

        # Components
        self.pg_queries = PostgreSQLQueries(config)
        self.influx_queries = InfluxDBQueries(config)
        self.cache_manager = QueryCacheManager(config)
        self.optimizer = QueryOptimizer(config)

        # Statistics
        self.query_stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "tier_distribution": {tier.value: 0 for tier in DataTier},
            "average_response_time": 0.0,
            "last_reset": time.time()
        }

    async def start(self):
        """Initialize database connections and components."""
        logger.info("Starting Query Federation")

        try:
            # Initialize PostgreSQL connection
            self.pg_engine = create_async_engine(
                self.config.postgres_url,
                pool_size=self.config.pg_pool_size,
                max_overflow=self.config.pg_max_overflow,
                pool_pre_ping=True,
                echo=self.config.debug
            )

            self.pg_session_factory = sessionmaker(
                self.pg_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Initialize InfluxDB connection
            self.influx_client = InfluxDBClient(
                url=self.config.influx_url,
                token=self.config.influx_token,
                org=self.config.influx_org,
                timeout=self.config.influx_timeout * 1000
            )

            # Test connections
            await self._test_connections()

            # Start components
            await self.cache_manager.start()

            logger.info("Query Federation started successfully")

        except Exception as e:
            logger.error("Failed to start Query Federation", error=str(e))
            raise

    async def stop(self):
        """Close database connections and stop components."""
        logger.info("Stopping Query Federation")

        try:
            await self.cache_manager.stop()

            if self.influx_client:
                self.influx_client.close()

            if self.pg_engine:
                await self.pg_engine.dispose()

            logger.info("Query Federation stopped")

        except Exception as e:
            logger.error("Error stopping Query Federation", error=str(e))

    async def query(
        self,
        query_type: QueryType,
        filters: Dict[str, Any],
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: Optional[int] = None,
        cache_ttl: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a federated query across databases.

        Args:
            query_type: Type of query to execute
            filters: Query filters (guild_id, player_name, etc.)
            time_range: Optional time range tuple (start, end)
            limit: Optional result limit
            cache_ttl: Optional cache TTL in seconds

        Returns:
            Query results with metadata
        """
        start_time = time.time()
        query_key = self._generate_query_key(query_type, filters, time_range, limit)

        try:
            # Check cache first
            cached_result = await self.cache_manager.get(query_key)
            if cached_result:
                self.query_stats["cache_hits"] += 1
                logger.debug("Cache hit for query", query_type=query_type.value)
                return cached_result

            # Determine optimal data tiers and databases
            query_plan = await self._create_query_plan(query_type, filters, time_range)

            # Execute query plan
            result = await self._execute_query_plan(query_plan)

            # Cache result
            cache_ttl = cache_ttl or self._get_default_cache_ttl(query_type, time_range)
            await self.cache_manager.set(query_key, result, cache_ttl)

            # Update statistics
            self._update_query_stats(query_plan, time.time() - start_time)

            return result

        except Exception as e:
            logger.error("Query execution failed", query_type=query_type.value, error=str(e))
            raise

    async def _create_query_plan(
        self,
        query_type: QueryType,
        filters: Dict[str, Any],
        time_range: Optional[Tuple[datetime, datetime]]
    ) -> Dict[str, Any]:
        """Create an optimized query execution plan."""
        plan = {
            "query_type": query_type,
            "filters": filters,
            "time_range": time_range,
            "data_sources": [],
            "optimization_hints": {}
        }

        # Determine required data sources based on query type
        if query_type in [QueryType.GUILD_DATA, QueryType.CHARACTER_DATA, QueryType.LOOT_DATA]:
            # Relational data from PostgreSQL
            plan["data_sources"].append({
                "database": "postgresql",
                "tier": DataTier.RELATIONAL,
                "tables": self._get_pg_tables_for_query(query_type),
                "priority": 1
            })

        elif query_type in [QueryType.COMBAT_EVENTS, QueryType.PLAYER_METRICS]:
            # Time-series data from InfluxDB
            if time_range:
                tiers = self._determine_influx_tiers(time_range)
                for i, tier in enumerate(tiers):
                    plan["data_sources"].append({
                        "database": "influxdb",
                        "tier": tier,
                        "bucket": self._get_bucket_for_tier(tier),
                        "priority": i + 1
                    })
            else:
                # Default to hot tier for recent data
                plan["data_sources"].append({
                    "database": "influxdb",
                    "tier": DataTier.HOT,
                    "bucket": self.config.influx_bucket_raw,
                    "priority": 1
                })

        elif query_type == QueryType.ENCOUNTER_SUMMARY:
            # Hybrid query: PostgreSQL for encounter metadata + InfluxDB for metrics
            plan["data_sources"].extend([
                {
                    "database": "postgresql",
                    "tier": DataTier.RELATIONAL,
                    "tables": ["combat_encounters", "characters"],
                    "priority": 1
                },
                {
                    "database": "influxdb",
                    "tier": self._determine_influx_tier_for_time_range(time_range),
                    "bucket": self._get_bucket_for_time_range(time_range),
                    "priority": 2
                }
            ])

        # Add optimization hints
        plan["optimization_hints"] = await self.optimizer.analyze_query(plan)

        return plan

    def _determine_influx_tiers(self, time_range: Tuple[datetime, datetime]) -> List[DataTier]:
        """Determine which InfluxDB tiers to query based on time range."""
        start_time, end_time = time_range
        now = datetime.now(timezone.utc)

        tiers = []

        # Hot tier: last 7 days
        hot_threshold = now - timedelta(days=7)
        if end_time > hot_threshold:
            tiers.append(DataTier.HOT)

        # Warm tier: 7-30 days
        warm_threshold = now - timedelta(days=30)
        if start_time < hot_threshold and end_time > warm_threshold:
            tiers.append(DataTier.WARM)

        # Cold tier: > 30 days
        if start_time < warm_threshold:
            tiers.append(DataTier.COLD)

        return tiers or [DataTier.HOT]  # Default to hot tier

    def _determine_influx_tier_for_time_range(
        self,
        time_range: Optional[Tuple[datetime, datetime]]
    ) -> DataTier:
        """Determine the primary InfluxDB tier for a time range."""
        if not time_range:
            return DataTier.HOT

        tiers = self._determine_influx_tiers(time_range)
        return tiers[0] if tiers else DataTier.HOT

    def _get_bucket_for_tier(self, tier: DataTier) -> str:
        """Get InfluxDB bucket name for a data tier."""
        tier_buckets = {
            DataTier.HOT: self.config.influx_bucket_raw,
            DataTier.WARM: self.config.influx_bucket_aggregated,
            DataTier.COLD: self.config.influx_bucket_archive
        }
        return tier_buckets.get(tier, self.config.influx_bucket_raw)

    def _get_bucket_for_time_range(
        self,
        time_range: Optional[Tuple[datetime, datetime]]
    ) -> str:
        """Get InfluxDB bucket for a time range."""
        tier = self._determine_influx_tier_for_time_range(time_range)
        return self._get_bucket_for_tier(tier)

    def _get_pg_tables_for_query(self, query_type: QueryType) -> List[str]:
        """Get PostgreSQL tables needed for a query type."""
        table_mapping = {
            QueryType.GUILD_DATA: ["guilds", "characters", "guild_roles"],
            QueryType.CHARACTER_DATA: ["characters", "armory_snapshots", "character_activity"],
            QueryType.LOOT_DATA: ["loot_entries", "characters", "Instance"],
            QueryType.ENCOUNTER_SUMMARY: ["combat_encounters", "characters"]
        }
        return table_mapping.get(query_type, [])

    async def _execute_query_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a query plan across multiple data sources."""
        query_type = plan["query_type"]
        results = {}

        # Execute queries for each data source
        for source in plan["data_sources"]:
            if source["database"] == "postgresql":
                pg_result = await self._execute_postgresql_query(query_type, plan, source)
                results["postgresql"] = pg_result

            elif source["database"] == "influxdb":
                influx_result = await self._execute_influxdb_query(query_type, plan, source)
                results[f"influxdb_{source['tier'].value}"] = influx_result

        # Merge and post-process results
        final_result = await self._merge_query_results(query_type, results, plan)

        return {
            "data": final_result,
            "metadata": {
                "query_type": query_type.value,
                "data_sources": [s["database"] for s in plan["data_sources"]],
                "tiers_used": [s.get("tier", {}).get("value", s.get("tier")) for s in plan["data_sources"]],
                "execution_time_ms": 0,  # Will be set by caller
                "cache_status": "miss"
            }
        }

    async def _execute_postgresql_query(
        self,
        query_type: QueryType,
        plan: Dict[str, Any],
        source: Dict[str, Any]
    ) -> Any:
        """Execute a PostgreSQL query."""
        try:
            async with self.pg_session_factory() as session:
                if query_type == QueryType.GUILD_DATA:
                    return await self.pg_queries.get_guild_data(
                        session, plan["filters"]
                    )
                elif query_type == QueryType.CHARACTER_DATA:
                    return await self.pg_queries.get_character_data(
                        session, plan["filters"]
                    )
                elif query_type == QueryType.LOOT_DATA:
                    return await self.pg_queries.get_loot_data(
                        session, plan["filters"]
                    )
                elif query_type == QueryType.ENCOUNTER_SUMMARY:
                    return await self.pg_queries.get_encounter_metadata(
                        session, plan["filters"], plan["time_range"]
                    )
                else:
                    logger.warning("Unsupported PostgreSQL query type", query_type=query_type.value)
                    return None

        except Exception as e:
            logger.error("PostgreSQL query failed", query_type=query_type.value, error=str(e))
            raise

    async def _execute_influxdb_query(
        self,
        query_type: QueryType,
        plan: Dict[str, Any],
        source: Dict[str, Any]
    ) -> Any:
        """Execute an InfluxDB query."""
        try:
            bucket = source["bucket"]
            tier = source["tier"]

            if query_type == QueryType.COMBAT_EVENTS:
                return await self.influx_queries.get_combat_events(
                    bucket, plan["filters"], plan["time_range"]
                )
            elif query_type == QueryType.PLAYER_METRICS:
                return await self.influx_queries.get_player_metrics(
                    bucket, plan["filters"], plan["time_range"]
                )
            elif query_type == QueryType.CROSS_NODE_METRICS:
                return await self.influx_queries.get_cross_node_metrics(
                    bucket, plan["filters"], plan["time_range"]
                )
            elif query_type == QueryType.ENCOUNTER_SUMMARY:
                return await self.influx_queries.get_encounter_metrics(
                    bucket, plan["filters"], plan["time_range"]
                )
            else:
                logger.warning("Unsupported InfluxDB query type", query_type=query_type.value)
                return None

        except Exception as e:
            logger.error("InfluxDB query failed", query_type=query_type.value, error=str(e))
            raise

    async def _merge_query_results(
        self,
        query_type: QueryType,
        results: Dict[str, Any],
        plan: Dict[str, Any]
    ) -> Any:
        """Merge results from multiple data sources."""
        if query_type == QueryType.ENCOUNTER_SUMMARY:
            # Merge PostgreSQL encounter metadata with InfluxDB metrics
            pg_data = results.get("postgresql", {})
            influx_data = results.get("influxdb_hot") or results.get("influxdb_warm") or results.get("influxdb_cold")

            if pg_data and influx_data:
                return await self._join_encounter_data(pg_data, influx_data)
            else:
                return pg_data or influx_data

        elif len(results) == 1:
            # Single data source
            return list(results.values())[0]

        else:
            # Multiple time-series sources - concatenate and sort
            combined_data = []
            for source_data in results.values():
                if isinstance(source_data, list):
                    combined_data.extend(source_data)
                elif isinstance(source_data, dict) and "data" in source_data:
                    combined_data.extend(source_data["data"])

            # Sort by timestamp if available
            if combined_data and isinstance(combined_data[0], dict) and "timestamp" in combined_data[0]:
                combined_data.sort(key=lambda x: x["timestamp"])

            return combined_data

    async def _join_encounter_data(self, pg_data: Dict, influx_data: Any) -> Dict:
        """Join PostgreSQL encounter metadata with InfluxDB metrics."""
        try:
            # This is a simplified join - in practice you'd implement more sophisticated joining
            encounter_data = dict(pg_data)

            if isinstance(influx_data, list) and influx_data:
                # Add aggregated metrics from InfluxDB
                total_damage = sum(event.get("damage", 0) for event in influx_data)
                total_healing = sum(event.get("healing", 0) for event in influx_data)

                encounter_data.update({
                    "total_damage": total_damage,
                    "total_healing": total_healing,
                    "event_count": len(influx_data)
                })

            return encounter_data

        except Exception as e:
            logger.error("Failed to join encounter data", error=str(e))
            return pg_data

    def _generate_query_key(
        self,
        query_type: QueryType,
        filters: Dict[str, Any],
        time_range: Optional[Tuple[datetime, datetime]],
        limit: Optional[int]
    ) -> str:
        """Generate a cache key for the query."""
        import hashlib
        import json

        key_data = {
            "type": query_type.value,
            "filters": filters,
            "time_range": [t.isoformat() for t in time_range] if time_range else None,
            "limit": limit
        }

        key_string = json.dumps(key_data, sort_keys=True, default=str)
        return f"query:{hashlib.md5(key_string.encode()).hexdigest()}"

    def _get_default_cache_ttl(
        self,
        query_type: QueryType,
        time_range: Optional[Tuple[datetime, datetime]]
    ) -> int:
        """Get default cache TTL based on query characteristics."""
        if not time_range:
            return 300  # 5 minutes for recent data

        end_time = time_range[1]
        now = datetime.now(timezone.utc)
        age = now - end_time

        if age < timedelta(hours=1):
            return 60   # 1 minute for very recent data
        elif age < timedelta(days=1):
            return 300  # 5 minutes for recent data
        elif age < timedelta(days=7):
            return 1800  # 30 minutes for week-old data
        else:
            return 3600  # 1 hour for older data

    async def _test_connections(self):
        """Test database connections."""
        try:
            # Test PostgreSQL
            async with self.pg_engine.begin() as conn:
                result = await conn.execute("SELECT 1")
                await result.fetchone()

            # Test InfluxDB
            health = self.influx_client.health()
            if health.status != "pass":
                raise InfluxDBError(f"InfluxDB health check failed: {health.message}")

            logger.info("Database connections tested successfully")

        except Exception as e:
            logger.error("Database connection test failed", error=str(e))
            raise

    def _update_query_stats(self, plan: Dict[str, Any], execution_time: float):
        """Update query statistics."""
        self.query_stats["total_queries"] += 1

        # Update tier distribution
        for source in plan["data_sources"]:
            tier = source.get("tier")
            if tier and isinstance(tier, DataTier):
                self.query_stats["tier_distribution"][tier.value] += 1

        # Update average response time
        total_time = (self.query_stats["average_response_time"] *
                     (self.query_stats["total_queries"] - 1) + execution_time)
        self.query_stats["average_response_time"] = total_time / self.query_stats["total_queries"]

    def get_query_stats(self) -> Dict[str, Any]:
        """Get query federation statistics."""
        stats = dict(self.query_stats)
        stats["cache_hit_rate"] = (
            self.query_stats["cache_hits"] / max(self.query_stats["total_queries"], 1)
        )
        stats["uptime_seconds"] = time.time() - self.query_stats["last_reset"]
        return stats

    async def health_check(self) -> Dict[str, bool]:
        """Perform health check on all components."""
        health_status = {}

        try:
            # Check PostgreSQL
            await self._test_connections()
            health_status["postgresql"] = True
        except Exception:
            health_status["postgresql"] = False

        try:
            # Check InfluxDB
            health = self.influx_client.health()
            health_status["influxdb"] = health.status == "pass"
        except Exception:
            health_status["influxdb"] = False

        # Check cache
        health_status["cache"] = await self.cache_manager.health_check()

        # Overall health
        health_status["overall"] = all(health_status.values())

        return health_status