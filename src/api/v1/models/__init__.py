"""
Enhanced Pydantic models for API v1 responses.

This module provides comprehensive data models for all API responses,
including paginated results, time series data, aggregations, and more.
"""

from .responses import *
from .characters import *
from .encounters import *
from .analytics import *
from .guilds import *
from .common import *

__all__ = [
    # Base response types
    "PaginatedResponse",
    "TimeSeriesResponse",
    "AggregationResponse",
    "ComparisonResponse",
    "RankingResponse",
    "ErrorResponse",
    "StatusResponse",
    # Character models
    "CharacterProfile",
    "CharacterPerformance",
    "CharacterHistory",
    "CharacterRanking",
    "CharacterGear",
    "CharacterTalents",
    # Encounter models
    "EncounterDetail",
    "EncounterReplay",
    "EncounterTimeline",
    "EncounterComparison",
    "DeathAnalysis",
    "ResourceUsage",
    # Analytics models
    "PerformanceTrend",
    "ProgressionTracking",
    "ClassBalance",
    "SpellUsageStats",
    "DamageBreakdown",
    # Guild models
    "GuildRoster",
    "AttendanceTracking",
    "GuildPerformance",
    "RaidComposition",
    # Common types
    "PaginationMeta",
    "SortOrder",
    "TimeRange",
    "FilterCriteria",
]
