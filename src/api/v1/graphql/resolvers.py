"""
GraphQL resolvers for combat log data.

Implements the business logic for GraphQL queries with efficient
data loading and proper error handling.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from .types import (
    Character,
    Encounter,
    CharacterPerformance,
    EncounterSummary,
    Analytics,
    Guild,
    SpellUsage,
    PlayerRanking,
    TimeSeriesData,
    PerformanceTrend,
)
from ...database.schema import DatabaseManager
from ...database.query import QueryAPI

logger = logging.getLogger(__name__)


class BaseResolver:
    """Base resolver with common functionality."""

    def __init__(self, db: DatabaseManager):
        """Initialize resolver with database manager."""
        self.db = db
        self.query_api = QueryAPI(db)

    def _handle_error(self, error: Exception, operation: str) -> None:
        """Log error and re-raise with context."""
        logger.error(f"Error in {operation}: {str(error)}")
        raise error


class CharacterResolver(BaseResolver):
    """Resolver for character-related queries."""

    async def get_character(self, name: str, server: Optional[str] = None) -> Optional[Character]:
        """Get a specific character by name and server."""
        try:
            # Query character data from database
            character_data = await self.query_api.get_character_profile(
                character_name=name, server=server
            )

            if not character_data:
                return None

            return Character(
                id=character_data.get("id"),
                name=character_data.get("name"),
                server=character_data.get("server"),
                class_name=character_data.get("class_name"),
                spec_name=character_data.get("spec_name"),
                level=character_data.get("level"),
                guild_name=character_data.get("guild_name"),
                faction=character_data.get("faction"),
                race=character_data.get("race"),
                gender=character_data.get("gender"),
                first_seen=character_data.get("first_seen"),
                last_seen=character_data.get("last_seen"),
                total_encounters=character_data.get("total_encounters", 0),
                avg_item_level=character_data.get("avg_item_level"),
                is_active=character_data.get("is_active", False),
            )

        except Exception as e:
            self._handle_error(e, "get_character")

    async def list_characters(
        self,
        limit: int = 50,
        offset: int = 0,
        server: Optional[str] = None,
        class_name: Optional[str] = None,
        guild: Optional[str] = None,
        active_since: Optional[datetime] = None,
    ) -> List[Character]:
        """List characters with filtering options."""
        try:
            # Build filter criteria
            filters = {}
            if server:
                filters["server"] = server
            if class_name:
                filters["class_name"] = class_name
            if guild:
                filters["guild"] = guild
            if active_since:
                filters["active_since"] = active_since

            # Query characters
            characters_data = await self.query_api.list_characters(
                limit=limit, offset=offset, filters=filters
            )

            return [
                Character(
                    id=char.get("id"),
                    name=char.get("name"),
                    server=char.get("server"),
                    class_name=char.get("class_name"),
                    spec_name=char.get("spec_name"),
                    level=char.get("level"),
                    guild_name=char.get("guild_name"),
                    faction=char.get("faction"),
                    race=char.get("race"),
                    gender=char.get("gender"),
                    first_seen=char.get("first_seen"),
                    last_seen=char.get("last_seen"),
                    total_encounters=char.get("total_encounters", 0),
                    avg_item_level=char.get("avg_item_level"),
                    is_active=char.get("is_active", False),
                )
                for char in characters_data
            ]

        except Exception as e:
            self._handle_error(e, "list_characters")

    async def get_character_performance(
        self,
        character_name: str,
        server: Optional[str] = None,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        days: int = 30,
    ) -> List[CharacterPerformance]:
        """Get character performance across encounters."""
        try:
            # Build performance query filters
            filters = {
                "character_name": character_name,
                "days": days,
            }
            if server:
                filters["server"] = server
            if encounter_type:
                filters["encounter_type"] = encounter_type
            if difficulty:
                filters["difficulty"] = difficulty

            # Query performance data
            performance_data = await self.query_api.get_character_performance(**filters)

            return [
                CharacterPerformance(
                    character_name=perf.get("character_name"),
                    encounter_id=perf.get("encounter_id"),
                    encounter_name=perf.get("encounter_name"),
                    difficulty=perf.get("difficulty"),
                    date=perf.get("date"),
                    duration=perf.get("duration", 0.0),
                    dps=perf.get("dps", 0.0),
                    hps=perf.get("hps", 0.0),
                    dtps=perf.get("dtps", 0.0),
                    damage_done=perf.get("damage_done", 0),
                    healing_done=perf.get("healing_done", 0),
                    damage_taken=perf.get("damage_taken", 0),
                    deaths=perf.get("deaths", 0),
                    interrupts=perf.get("interrupts", 0),
                    dispels=perf.get("dispels", 0),
                    activity_percentage=perf.get("activity_percentage", 0.0),
                    parse_percentile=perf.get("parse_percentile"),
                    item_level=perf.get("item_level"),
                )
                for perf in performance_data
            ]

        except Exception as e:
            self._handle_error(e, "get_character_performance")


class EncounterResolver(BaseResolver):
    """Resolver for encounter-related queries."""

    async def get_encounter(self, encounter_id: int) -> Optional[Encounter]:
        """Get a specific encounter by ID."""
        try:
            encounter_data = await self.query_api.get_encounter_details(encounter_id)

            if not encounter_data:
                return None

            # Get participants for this encounter
            participants_data = await self.query_api.get_encounter_participants(encounter_id)
            participants = [
                Character(
                    id=p.get("id"),
                    name=p.get("name"),
                    server=p.get("server"),
                    class_name=p.get("class_name"),
                    spec_name=p.get("spec_name"),
                    level=p.get("level"),
                    guild_name=p.get("guild_name"),
                    faction=p.get("faction"),
                    race=p.get("race"),
                    gender=p.get("gender"),
                    first_seen=p.get("first_seen"),
                    last_seen=p.get("last_seen"),
                    total_encounters=p.get("total_encounters", 0),
                    avg_item_level=p.get("avg_item_level"),
                    is_active=p.get("is_active", False),
                )
                for p in participants_data
            ]

            return Encounter(
                id=encounter_data.get("id"),
                boss_name=encounter_data.get("boss_name"),
                encounter_type=encounter_data.get("encounter_type"),
                difficulty=encounter_data.get("difficulty"),
                start_time=encounter_data.get("start_time"),
                end_time=encounter_data.get("end_time"),
                duration=encounter_data.get("duration"),
                success=encounter_data.get("success", False),
                wipe_percentage=encounter_data.get("wipe_percentage"),
                raid_size=encounter_data.get("raid_size", 0),
                guild_name=encounter_data.get("guild_name"),
                zone_name=encounter_data.get("zone_name"),
                keystone_level=encounter_data.get("keystone_level"),
                affixes=encounter_data.get("affixes", []),
                total_damage=encounter_data.get("total_damage", 0),
                total_healing=encounter_data.get("total_healing", 0),
                participants=participants,
            )

        except Exception as e:
            self._handle_error(e, "get_encounter")

    async def list_encounters(
        self,
        limit: int = 50,
        offset: int = 0,
        boss_name: Optional[str] = None,
        difficulty: Optional[str] = None,
        success_only: Optional[bool] = None,
        guild: Optional[str] = None,
        min_duration: Optional[int] = None,
        max_duration: Optional[int] = None,
        days: int = 30,
    ) -> List[Encounter]:
        """List encounters with filtering."""
        try:
            # Build filter criteria
            filters = {"days": days}
            if boss_name:
                filters["boss_name"] = boss_name
            if difficulty:
                filters["difficulty"] = difficulty
            if success_only is not None:
                filters["success_only"] = success_only
            if guild:
                filters["guild"] = guild
            if min_duration:
                filters["min_duration"] = min_duration
            if max_duration:
                filters["max_duration"] = max_duration

            # Query encounters
            encounters_data = await self.query_api.list_encounters(
                limit=limit, offset=offset, filters=filters
            )

            encounters = []
            for enc_data in encounters_data:
                # For list view, don't load full participant data for performance
                encounter = Encounter(
                    id=enc_data.get("id"),
                    boss_name=enc_data.get("boss_name"),
                    encounter_type=enc_data.get("encounter_type"),
                    difficulty=enc_data.get("difficulty"),
                    start_time=enc_data.get("start_time"),
                    end_time=enc_data.get("end_time"),
                    duration=enc_data.get("duration"),
                    success=enc_data.get("success", False),
                    wipe_percentage=enc_data.get("wipe_percentage"),
                    raid_size=enc_data.get("raid_size", 0),
                    guild_name=enc_data.get("guild_name"),
                    zone_name=enc_data.get("zone_name"),
                    keystone_level=enc_data.get("keystone_level"),
                    affixes=enc_data.get("affixes", []),
                    total_damage=enc_data.get("total_damage", 0),
                    total_healing=enc_data.get("total_healing", 0),
                    participants=[],  # Load on demand via separate query
                )
                encounters.append(encounter)

            return encounters

        except Exception as e:
            self._handle_error(e, "list_encounters")

    async def get_encounter_summary(
        self,
        boss_name: Optional[str] = None,
        difficulty: Optional[str] = None,
        days: int = 30,
    ) -> List[EncounterSummary]:
        """Get encounter summary statistics."""
        try:
            filters = {"days": days}
            if boss_name:
                filters["boss_name"] = boss_name
            if difficulty:
                filters["difficulty"] = difficulty

            summary_data = await self.query_api.get_encounter_summary(**filters)

            return [
                EncounterSummary(
                    boss_name=summary.get("boss_name"),
                    difficulty=summary.get("difficulty"),
                    total_attempts=summary.get("total_attempts", 0),
                    successful_kills=summary.get("successful_kills", 0),
                    success_rate=summary.get("success_rate", 0.0),
                    average_duration=summary.get("average_duration", 0.0),
                    best_duration=summary.get("best_duration", 0.0),
                    worst_duration=summary.get("worst_duration", 0.0),
                    average_raid_size=summary.get("average_raid_size", 0.0),
                    last_attempt=summary.get("last_attempt"),
                    first_attempt=summary.get("first_attempt"),
                )
                for summary in summary_data
            ]

        except Exception as e:
            self._handle_error(e, "get_encounter_summary")


class AnalyticsResolver(BaseResolver):
    """Resolver for analytics and performance trend queries."""

    async def get_performance_trends(
        self,
        metric: str,
        character_name: Optional[str] = None,
        class_name: Optional[str] = None,
        encounter_type: Optional[str] = None,
        days: int = 30,
        granularity: str = "daily",
    ) -> List[PerformanceTrend]:
        """Get performance trends over time."""
        try:
            filters = {
                "metric": metric,
                "days": days,
                "granularity": granularity,
            }
            if character_name:
                filters["character_name"] = character_name
            if class_name:
                filters["class_name"] = class_name
            if encounter_type:
                filters["encounter_type"] = encounter_type

            trends_data = await self.query_api.get_performance_trends(**filters)

            return [
                PerformanceTrend(
                    metric=trend.get("metric"),
                    character_name=trend.get("character_name"),
                    class_name=trend.get("class_name"),
                    data_points=[
                        TimeSeriesData(
                            timestamp=point.get("timestamp"),
                            value=point.get("value"),
                            additional_data=point.get("additional_data"),
                        )
                        for point in trend.get("data_points", [])
                    ],
                    trend_direction=trend.get("trend_direction", "stable"),
                    trend_strength=trend.get("trend_strength", 0.0),
                    average_value=trend.get("average_value", 0.0),
                    min_value=trend.get("min_value", 0.0),
                    max_value=trend.get("max_value", 0.0),
                    std_deviation=trend.get("std_deviation", 0.0),
                )
                for trend in trends_data
            ]

        except Exception as e:
            self._handle_error(e, "get_performance_trends")

    async def get_top_performers(
        self,
        metric: str,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        class_name: Optional[str] = None,
        days: int = 30,
        limit: int = 10,
    ) -> List[PlayerRanking]:
        """Get top performing players by metric."""
        try:
            filters = {
                "metric": metric,
                "days": days,
                "limit": limit,
            }
            if encounter_type:
                filters["encounter_type"] = encounter_type
            if difficulty:
                filters["difficulty"] = difficulty
            if class_name:
                filters["class_name"] = class_name

            rankings_data = await self.query_api.get_top_performers(**filters)

            return [
                PlayerRanking(
                    character_name=ranking.get("character_name"),
                    server=ranking.get("server"),
                    class_name=ranking.get("class_name"),
                    guild_name=ranking.get("guild_name"),
                    metric_value=ranking.get("metric_value", 0.0),
                    rank=ranking.get("rank", 0),
                    percentile=ranking.get("percentile", 0.0),
                    sample_size=ranking.get("sample_size", 0),
                    best_performance=ranking.get("best_performance", 0.0),
                    average_performance=ranking.get("average_performance", 0.0),
                    consistency_score=ranking.get("consistency_score", 0.0),
                )
                for ranking in rankings_data
            ]

        except Exception as e:
            self._handle_error(e, "get_top_performers")

    async def get_spell_usage(
        self,
        character_name: Optional[str] = None,
        class_name: Optional[str] = None,
        encounter_type: Optional[str] = None,
        days: int = 30,
        limit: int = 20,
    ) -> List[SpellUsage]:
        """Get spell usage statistics."""
        try:
            filters = {"days": days, "limit": limit}
            if character_name:
                filters["character_name"] = character_name
            if class_name:
                filters["class_name"] = class_name
            if encounter_type:
                filters["encounter_type"] = encounter_type

            spell_data = await self.query_api.get_spell_usage(**filters)

            return [
                SpellUsage(
                    spell_id=spell.get("spell_id"),
                    spell_name=spell.get("spell_name"),
                    character_name=spell.get("character_name"),
                    class_name=spell.get("class_name"),
                    cast_count=spell.get("cast_count", 0),
                    hit_count=spell.get("hit_count", 0),
                    crit_count=spell.get("crit_count", 0),
                    miss_count=spell.get("miss_count", 0),
                    total_damage=spell.get("total_damage", 0),
                    total_healing=spell.get("total_healing", 0),
                    max_damage=spell.get("max_damage", 0),
                    max_healing=spell.get("max_healing", 0),
                    avg_damage=spell.get("avg_damage", 0.0),
                    avg_healing=spell.get("avg_healing", 0.0),
                    crit_percentage=spell.get("crit_percentage", 0.0),
                    hit_percentage=spell.get("hit_percentage", 0.0),
                    casts_per_minute=spell.get("casts_per_minute", 0.0),
                )
                for spell in spell_data
            ]

        except Exception as e:
            self._handle_error(e, "get_spell_usage")

    async def get_class_balance(
        self,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        metric: str = "dps",
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get class balance analysis."""
        try:
            filters = {
                "metric": metric,
                "days": days,
            }
            if encounter_type:
                filters["encounter_type"] = encounter_type
            if difficulty:
                filters["difficulty"] = difficulty

            # Get class balance data from database
            from datetime import datetime, timedelta
            import statistics

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Choose metric column
            metric_column = "damage_done" if metric == "dps" else "healing_done"

            # Build query with filters
            query = """
                SELECT
                    c.class_name,
                    c.spec,
                    COUNT(DISTINCT cm.encounter_id) as encounter_count,
                    AVG(CAST(json_extract(cm.metrics_data, '$.' || ?) AS FLOAT)) as avg_value,
                    COUNT(DISTINCT c.id) as sample_size
                FROM characters c
                JOIN character_metrics cm ON c.id = cm.character_id
                JOIN encounters e ON cm.encounter_id = e.id
                WHERE e.start_time BETWEEN ? AND ?
                {}
                {}
                GROUP BY c.class_name, c.spec
                ORDER BY avg_value DESC
            """.format(
                f"AND e.difficulty = ?" if difficulty else "",
                f"AND e.type = ?" if encounter_type else "",
            )

            params = [metric_column, start_date.isoformat(), end_date.isoformat()]
            if difficulty:
                params.append(difficulty)
            if encounter_type:
                params.append(encounter_type)

            cursor = self.db.execute(query, tuple(params))
            results = cursor.fetchall()

            class_data = []
            all_values = []

            for row in results:
                if row["avg_value"]:
                    all_values.append(row["avg_value"])

                class_data.append(
                    {
                        "class_name": row["class_name"],
                        "spec": row["spec"],
                        "average_performance": row["avg_value"] or 0,
                        "sample_size": row["sample_size"],
                        "encounter_count": row["encounter_count"],
                    }
                )

            # Add relative performance
            avg_overall = statistics.mean(all_values) if all_values else 0
            for entry in class_data:
                if avg_overall > 0:
                    entry["relative_performance"] = entry["average_performance"] / avg_overall
                else:
                    entry["relative_performance"] = 1.0

            return class_data

        except Exception as e:
            self._handle_error(e, "get_class_balance")

    async def get_progression_tracking(
        self,
        guild_name: Optional[str] = None,
        server: Optional[str] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get raid progression tracking data."""
        try:
            filters = {"days": days}
            if guild_name:
                filters["guild_name"] = guild_name
            if server:
                filters["server"] = server

            # Get progression tracking from database
            from datetime import datetime, timedelta

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Get encounter progression data
            query = """
                SELECT
                    e.id,
                    e.name as boss_name,
                    e.difficulty,
                    e.start_time,
                    e.kill as is_kill,
                    e.duration,
                    e.elapsed_time,
                    COUNT(DISTINCT cm.character_id) as player_count
                FROM encounters e
                LEFT JOIN character_metrics cm ON e.id = cm.encounter_id
                WHERE e.start_time BETWEEN ? AND ?
                {}
                GROUP BY e.id
                ORDER BY e.start_time DESC
                LIMIT 200
            """.format(
                "AND e.guild_name = ?" if guild_name else ""
            )

            params = [start_date.isoformat(), end_date.isoformat()]
            if guild_name:
                params.append(guild_name)

            cursor = self.db.execute(query, tuple(params))
            results = cursor.fetchall()

            progression_data = []
            for row in results:
                encounter = {
                    "encounter_id": row["id"],
                    "boss_name": row["boss_name"],
                    "difficulty": row["difficulty"],
                    "kill_time": row["start_time"] if row["is_kill"] else None,
                    "is_kill": bool(row["is_kill"]),
                    "duration_seconds": row["duration"],
                    "player_count": row["player_count"],
                }
                progression_data.append(encounter)

            return progression_data

        except Exception as e:
            self._handle_error(e, "get_progression_tracking")


class GuildResolver(BaseResolver):
    """Resolver for guild-related queries."""

    async def get_guild(self, name: str, server: Optional[str] = None) -> Optional[Guild]:
        """Get guild information and roster."""
        try:
            guild_data = await self.query_api.get_guild_info(name, server)

            if not guild_data:
                return None

            # Get guild members
            members_data = await self.query_api.get_guild_members(name, server)
            members = [
                Character(
                    id=member.get("id"),
                    name=member.get("name"),
                    server=member.get("server"),
                    class_name=member.get("class_name"),
                    spec_name=member.get("spec_name"),
                    level=member.get("level"),
                    guild_name=member.get("guild_name"),
                    faction=member.get("faction"),
                    race=member.get("race"),
                    gender=member.get("gender"),
                    first_seen=member.get("first_seen"),
                    last_seen=member.get("last_seen"),
                    total_encounters=member.get("total_encounters", 0),
                    avg_item_level=member.get("avg_item_level"),
                    is_active=member.get("is_active", False),
                )
                for member in members_data
            ]

            return Guild(
                id=guild_data.get("id"),
                name=guild_data.get("name"),
                server=guild_data.get("server"),
                faction=guild_data.get("faction"),
                region=guild_data.get("region"),
                member_count=guild_data.get("member_count", 0),
                active_member_count=guild_data.get("active_member_count", 0),
                raid_team_count=guild_data.get("raid_team_count", 0),
                first_seen=guild_data.get("first_seen"),
                last_activity=guild_data.get("last_activity"),
                progression_score=guild_data.get("progression_score"),
                members=members,
            )

        except Exception as e:
            self._handle_error(e, "get_guild")

    async def list_guilds(
        self,
        limit: int = 50,
        offset: int = 0,
        server: Optional[str] = None,
        min_members: Optional[int] = None,
        active_since: Optional[datetime] = None,
    ) -> List[Guild]:
        """List guilds with filtering."""
        try:
            filters = {}
            if server:
                filters["server"] = server
            if min_members:
                filters["min_members"] = min_members
            if active_since:
                filters["active_since"] = active_since

            guilds_data = await self.query_api.list_guilds(
                limit=limit, offset=offset, filters=filters
            )

            return [
                Guild(
                    id=guild.get("id"),
                    name=guild.get("name"),
                    server=guild.get("server"),
                    faction=guild.get("faction"),
                    region=guild.get("region"),
                    member_count=guild.get("member_count", 0),
                    active_member_count=guild.get("active_member_count", 0),
                    raid_team_count=guild.get("raid_team_count", 0),
                    first_seen=guild.get("first_seen"),
                    last_activity=guild.get("last_activity"),
                    progression_score=guild.get("progression_score"),
                    members=[],  # Load on demand for performance
                )
                for guild in guilds_data
            ]

        except Exception as e:
            self._handle_error(e, "list_guilds")
