"""
GraphQL schema definition using Strawberry.

Provides type-safe GraphQL interface with efficient data loading
and comprehensive query capabilities.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

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
from .resolvers import (
    CharacterResolver,
    EncounterResolver,
    AnalyticsResolver,
    GuildResolver,
)
from ..dependencies import DatabaseDependency
from ...database.schema import DatabaseManager


@strawberry.type
class Query:
    """GraphQL Query type providing all read operations."""

    # Character Queries
    @strawberry.field
    async def character(
        self,
        info: Info,
        name: str,
        server: Optional[str] = None,
    ) -> Optional[Character]:
        """Get a specific character by name and optional server."""
        db: DatabaseManager = info.context["db"]
        resolver = CharacterResolver(db)
        return await resolver.get_character(name, server)

    @strawberry.field
    async def characters(
        self,
        info: Info,
        limit: int = 50,
        offset: int = 0,
        server: Optional[str] = None,
        class_name: Optional[str] = None,
        guild: Optional[str] = None,
        active_since: Optional[datetime] = None,
    ) -> List[Character]:
        """Search characters with flexible filtering."""
        db: DatabaseManager = info.context["db"]
        resolver = CharacterResolver(db)
        return await resolver.list_characters(
            limit=limit,
            offset=offset,
            server=server,
            class_name=class_name,
            guild=guild,
            active_since=active_since,
        )

    @strawberry.field
    async def character_performance(
        self,
        info: Info,
        character_name: str,
        server: Optional[str] = None,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        days: int = 30,
    ) -> List[CharacterPerformance]:
        """Get character performance data across encounters."""
        db: DatabaseManager = info.context["db"]
        resolver = CharacterResolver(db)
        return await resolver.get_character_performance(
            character_name=character_name,
            server=server,
            encounter_type=encounter_type,
            difficulty=difficulty,
            days=days,
        )

    # Encounter Queries
    @strawberry.field
    async def encounter(
        self,
        info: Info,
        encounter_id: int,
    ) -> Optional[Encounter]:
        """Get a specific encounter by ID."""
        db: DatabaseManager = info.context["db"]
        resolver = EncounterResolver(db)
        return await resolver.get_encounter(encounter_id)

    @strawberry.field
    async def encounters(
        self,
        info: Info,
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
        """Search encounters with comprehensive filtering."""
        db: DatabaseManager = info.context["db"]
        resolver = EncounterResolver(db)
        return await resolver.list_encounters(
            limit=limit,
            offset=offset,
            boss_name=boss_name,
            difficulty=difficulty,
            success_only=success_only,
            guild=guild,
            min_duration=min_duration,
            max_duration=max_duration,
            days=days,
        )

    @strawberry.field
    async def encounter_summary(
        self,
        info: Info,
        boss_name: Optional[str] = None,
        difficulty: Optional[str] = None,
        days: int = 30,
    ) -> List[EncounterSummary]:
        """Get encounter summary statistics."""
        db: DatabaseManager = info.context["db"]
        resolver = EncounterResolver(db)
        return await resolver.get_encounter_summary(
            boss_name=boss_name,
            difficulty=difficulty,
            days=days,
        )

    # Analytics Queries
    @strawberry.field
    async def performance_trends(
        self,
        info: Info,
        metric: str,
        character_name: Optional[str] = None,
        class_name: Optional[str] = None,
        encounter_type: Optional[str] = None,
        days: int = 30,
        granularity: str = "daily",
    ) -> List[PerformanceTrend]:
        """Get performance trends over time."""
        db: DatabaseManager = info.context["db"]
        resolver = AnalyticsResolver(db)
        return await resolver.get_performance_trends(
            metric=metric,
            character_name=character_name,
            class_name=class_name,
            encounter_type=encounter_type,
            days=days,
            granularity=granularity,
        )

    @strawberry.field
    async def top_performers(
        self,
        info: Info,
        metric: str,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        class_name: Optional[str] = None,
        days: int = 30,
        limit: int = 10,
    ) -> List[PlayerRanking]:
        """Get top performing players by metric."""
        db: DatabaseManager = info.context["db"]
        resolver = AnalyticsResolver(db)
        return await resolver.get_top_performers(
            metric=metric,
            encounter_type=encounter_type,
            difficulty=difficulty,
            class_name=class_name,
            days=days,
            limit=limit,
        )

    @strawberry.field
    async def spell_usage(
        self,
        info: Info,
        character_name: Optional[str] = None,
        class_name: Optional[str] = None,
        encounter_type: Optional[str] = None,
        days: int = 30,
        limit: int = 20,
    ) -> List[SpellUsage]:
        """Get spell usage statistics."""
        db: DatabaseManager = info.context["db"]
        resolver = AnalyticsResolver(db)
        return await resolver.get_spell_usage(
            character_name=character_name,
            class_name=class_name,
            encounter_type=encounter_type,
            days=days,
            limit=limit,
        )

    # Guild Queries
    @strawberry.field
    async def guild(
        self,
        info: Info,
        name: str,
        server: Optional[str] = None,
    ) -> Optional[Guild]:
        """Get guild information and roster."""
        db: DatabaseManager = info.context["db"]
        resolver = GuildResolver(db)
        return await resolver.get_guild(name, server)

    @strawberry.field
    async def guilds(
        self,
        info: Info,
        limit: int = 50,
        offset: int = 0,
        server: Optional[str] = None,
        min_members: Optional[int] = None,
        active_since: Optional[datetime] = None,
    ) -> List[Guild]:
        """Search guilds with filtering."""
        db: DatabaseManager = info.context["db"]
        resolver = GuildResolver(db)
        return await resolver.list_guilds(
            limit=limit,
            offset=offset,
            server=server,
            min_members=min_members,
            active_since=active_since,
        )

    # Complex Aggregation Queries
    @strawberry.field
    async def class_balance(
        self,
        info: Info,
        encounter_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        metric: str = "dps",
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get class balance analysis."""
        db: DatabaseManager = info.context["db"]
        resolver = AnalyticsResolver(db)
        return await resolver.get_class_balance(
            encounter_type=encounter_type,
            difficulty=difficulty,
            metric=metric,
            days=days,
        )

    @strawberry.field
    async def progression_tracking(
        self,
        info: Info,
        guild_name: Optional[str] = None,
        server: Optional[str] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get raid progression tracking data."""
        db: DatabaseManager = info.context["db"]
        resolver = AnalyticsResolver(db)
        return await resolver.get_progression_tracking(
            guild_name=guild_name,
            server=server,
            days=days,
        )


@strawberry.type
class Mutation:
    """GraphQL Mutation type for write operations."""

    @strawberry.field
    async def upload_log(
        self,
        info: Info,
        log_data: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Upload and process a combat log."""
        # Implementation would connect to log processing system
        return "Log upload feature not yet implemented"

    @strawberry.field
    async def update_character_metadata(
        self,
        info: Info,
        character_name: str,
        server: Optional[str] = None,
        metadata: Dict[str, Any] = strawberry.UNSET,
    ) -> bool:
        """Update character metadata."""
        # Implementation would update character information
        return False


@strawberry.type
class Subscription:
    """GraphQL Subscription type for real-time updates."""

    @strawberry.subscription
    async def live_encounter_updates(
        self,
        info: Info,
        encounter_id: Optional[int] = None,
    ) -> Union[Encounter, str]:
        """Subscribe to live encounter updates."""
        # Implementation would connect to streaming system
        yield "Real-time subscriptions not yet implemented"

    @strawberry.subscription
    async def performance_alerts(
        self,
        info: Info,
        character_name: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> Union[CharacterPerformance, str]:
        """Subscribe to performance alerts."""
        yield "Performance alerts not yet implemented"


# Create the schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
)

# Create GraphQL router
app = GraphQLRouter(
    schema,
    graphiql=True,
    path="/api/v1/graphql",
    context_getter=lambda: {"db": None},  # Will be provided by middleware
)
