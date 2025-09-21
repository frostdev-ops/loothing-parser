"""
GraphQL types using Strawberry.

Defines all GraphQL types for characters, encounters, analytics, and guilds
with proper field definitions and relationships.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import strawberry


@strawberry.type
class Character:
    """GraphQL type for character data."""

    id: int
    name: str
    server: Optional[str]
    class_name: Optional[str]
    spec_name: Optional[str]
    level: Optional[int]
    guild_name: Optional[str]
    faction: Optional[str]
    race: Optional[str]
    gender: Optional[str]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    total_encounters: int
    avg_item_level: Optional[float]
    is_active: bool


@strawberry.type
class CharacterPerformance:
    """GraphQL type for character performance metrics."""

    character_name: str
    encounter_id: int
    encounter_name: str
    difficulty: Optional[str]
    date: datetime
    duration: float
    dps: float
    hps: float
    dtps: float
    damage_done: int
    healing_done: int
    damage_taken: int
    deaths: int
    interrupts: int
    dispels: int
    activity_percentage: float
    parse_percentile: Optional[float]
    item_level: Optional[int]


@strawberry.type
class Encounter:
    """GraphQL type for encounter data."""

    id: int
    boss_name: str
    encounter_type: str
    difficulty: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    duration: Optional[float]
    success: bool
    wipe_percentage: Optional[float]
    raid_size: int
    guild_name: Optional[str]
    zone_name: Optional[str]
    keystone_level: Optional[int]
    affixes: Optional[List[str]]
    total_damage: int
    total_healing: int
    participants: List[Character]


@strawberry.type
class EncounterSummary:
    """GraphQL type for encounter summary statistics."""

    boss_name: str
    difficulty: Optional[str]
    total_attempts: int
    successful_kills: int
    success_rate: float
    average_duration: float
    best_duration: float
    worst_duration: float
    average_raid_size: float
    last_attempt: datetime
    first_attempt: datetime


@strawberry.type
class SpellUsage:
    """GraphQL type for spell usage statistics."""

    spell_id: int
    spell_name: str
    character_name: Optional[str]
    class_name: Optional[str]
    cast_count: int
    hit_count: int
    crit_count: int
    miss_count: int
    total_damage: int
    total_healing: int
    max_damage: int
    max_healing: int
    avg_damage: float
    avg_healing: float
    crit_percentage: float
    hit_percentage: float
    casts_per_minute: float


@strawberry.type
class PlayerRanking:
    """GraphQL type for player rankings."""

    character_name: str
    server: Optional[str]
    class_name: Optional[str]
    guild_name: Optional[str]
    metric_value: float
    rank: int
    percentile: float
    sample_size: int
    best_performance: float
    average_performance: float
    consistency_score: float


@strawberry.type
class TimeSeriesData:
    """GraphQL type for time series data points."""

    timestamp: datetime
    value: float
    additional_data: Optional[Dict[str, Any]]


@strawberry.type
class PerformanceTrend:
    """GraphQL type for performance trends over time."""

    metric: str
    character_name: Optional[str]
    class_name: Optional[str]
    data_points: List[TimeSeriesData]
    trend_direction: str  # "increasing", "decreasing", "stable"
    trend_strength: float  # 0.0 to 1.0
    average_value: float
    min_value: float
    max_value: float
    std_deviation: float


@strawberry.type
class Analytics:
    """GraphQL type for analytics data."""

    metric_name: str
    time_period: str
    data: Dict[str, Any]
    generated_at: datetime
    sample_size: int
    confidence_level: Optional[float]


@strawberry.type
class Guild:
    """GraphQL type for guild data."""

    id: int
    name: str
    server: Optional[str]
    faction: Optional[str]
    region: Optional[str]
    member_count: int
    active_member_count: int
    raid_team_count: int
    first_seen: Optional[datetime]
    last_activity: Optional[datetime]
    progression_score: Optional[float]
    members: List[Character]


@strawberry.type
class GuildRoster:
    """GraphQL type for guild roster information."""

    guild_name: str
    server: Optional[str]
    total_members: int
    active_members: int
    class_distribution: Dict[str, int]
    spec_distribution: Dict[str, int]
    average_item_level: float
    roster_stability: float  # Member retention rate
    last_updated: datetime


@strawberry.type
class CombatReplay:
    """GraphQL type for combat replay data."""

    encounter_id: int
    timeline: List[Dict[str, Any]]
    key_events: List[Dict[str, Any]]
    damage_timeline: List[TimeSeriesData]
    healing_timeline: List[TimeSeriesData]
    death_events: List[Dict[str, Any]]
    phase_transitions: List[Dict[str, Any]]


@strawberry.type
class ItemUsage:
    """GraphQL type for item/gear usage statistics."""

    item_id: int
    item_name: str
    item_level: int
    item_slot: str
    usage_count: int
    characters_using: int
    average_performance_boost: Optional[float]
    popularity_trend: str
    recommended_for_classes: List[str]


@strawberry.type
class ClassBalance:
    """GraphQL type for class balance analysis."""

    class_name: str
    spec_name: Optional[str]
    sample_size: int
    metric_name: str
    average_value: float
    median_value: float
    percentile_95: float
    percentile_75: float
    percentile_25: float
    percentile_5: float
    balance_score: float  # Relative to other classes
    trend_direction: str


@strawberry.type
class ProgressionData:
    """GraphQL type for raid progression tracking."""

    guild_name: str
    server: Optional[str]
    raid_tier: str
    difficulty: str
    bosses_defeated: int
    total_bosses: int
    progression_percentage: float
    first_kill_dates: Dict[str, datetime]
    fastest_clear_time: Optional[float]
    current_progress_boss: Optional[str]
    estimated_completion_date: Optional[datetime]


@strawberry.type
class DamageBreakdown:
    """GraphQL type for detailed damage breakdown."""

    character_name: str
    encounter_id: int
    total_damage: int
    damage_by_spell: List[SpellUsage]
    damage_by_target: Dict[str, int]
    damage_by_school: Dict[str, int]
    overkill_damage: int
    absorbed_damage: int
    blocked_damage: int
    effective_damage: int


@strawberry.type
class HealingBreakdown:
    """GraphQL type for detailed healing breakdown."""

    character_name: str
    encounter_id: int
    total_healing: int
    healing_by_spell: List[SpellUsage]
    healing_by_target: Dict[str, int]
    overhealing: int
    absorbed_healing: int
    effective_healing: int
    healing_per_second: float
    emergency_healing: int  # Healing when target below 50% HP
