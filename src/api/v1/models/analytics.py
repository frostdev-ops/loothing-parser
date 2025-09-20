"""
Analytics-related Pydantic models for API v1.

These models define the structure for analytics data including performance
trends, progression tracking, class balance, and spell usage statistics.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .common import TimeRange, PerformanceMetric


class PerformanceTrend(BaseModel):
    """Performance trend analysis over time."""

    metric_name: str = Field(..., description="Name of the metric being tracked")
    time_range: TimeRange = Field(..., description="Time range for the trend")
    data_points: List[Dict[str, Any]] = Field(..., description="Trend data points")
    trend_direction: str = Field(..., description="Overall trend direction (up/down/stable)")
    trend_strength: float = Field(..., description="Strength of the trend (0-1)", ge=0, le=1)
    statistical_significance: float = Field(..., description="Statistical significance (0-1)", ge=0, le=1)

    class Config:
        schema_extra = {
            "example": {
                "metric_name": "average_dps",
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "data_points": [
                    {"date": "2023-10-01", "value": 120000, "sample_size": 25},
                    {"date": "2023-10-02", "value": 122000, "sample_size": 28}
                ],
                "trend_direction": "up",
                "trend_strength": 0.85,
                "statistical_significance": 0.95
            }
        }


class ProgressionTracking(BaseModel):
    """Raid progression tracking."""

    guild_name: Optional[str] = Field(None, description="Guild name")
    time_range: TimeRange = Field(..., description="Time range for progression")
    encounters: List[Dict[str, Any]] = Field(..., description="Encounter progression data")
    milestones: List[Dict[str, Any]] = Field(..., description="Important progression milestones")
    current_progress: Dict[str, Any] = Field(..., description="Current progression status")
    progression_rate: float = Field(..., description="Rate of progression", ge=0)

    class Config:
        schema_extra = {
            "example": {
                "guild_name": "Example Guild",
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "encounters": [
                    {
                        "boss_name": "Raszageth",
                        "difficulty": "HEROIC",
                        "first_kill": "2023-10-15T20:30:00Z",
                        "attempts": 25
                    }
                ],
                "current_progress": {
                    "current_tier": "Vault of the Incarnates",
                    "heroic_bosses_killed": 8,
                    "mythic_bosses_killed": 3
                },
                "progression_rate": 0.75
            }
        }


class ClassBalanceEntry(BaseModel):
    """Single entry in class balance analysis."""

    class_name: str = Field(..., description="Class name")
    spec_name: Optional[str] = Field(None, description="Specialization name")
    metric_values: Dict[str, PerformanceMetric] = Field(..., description="Performance metrics")
    relative_performance: float = Field(..., description="Performance relative to average", ge=0)
    sample_size: int = Field(..., description="Number of data points", ge=1)
    confidence_interval: Optional[Dict[str, float]] = Field(None, description="95% confidence interval")

    class Config:
        schema_extra = {
            "example": {
                "class_name": "Mage",
                "spec_name": "Fire",
                "metric_values": {
                    "dps": {
                        "value": 125000.5,
                        "percentile": 85.0,
                        "rank": 3
                    }
                },
                "relative_performance": 1.15,
                "sample_size": 150,
                "confidence_interval": {"lower": 120000, "upper": 130000}
            }
        }


class ClassBalance(BaseModel):
    """Class balance analysis."""

    analysis_type: str = Field(..., description="Type of balance analysis")
    time_range: TimeRange = Field(..., description="Time range for analysis")
    encounter_filters: Optional[Dict[str, Any]] = Field(None, description="Encounter filters applied")
    class_data: List[ClassBalanceEntry] = Field(..., description="Class performance data")
    balance_score: float = Field(..., description="Overall balance score (0-1)", ge=0, le=1)
    outliers: List[str] = Field(default_factory=list, description="Classes/specs that are outliers")

    class Config:
        schema_extra = {
            "example": {
                "analysis_type": "dps_balance",
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "encounter_filters": {"difficulty": "HEROIC"},
                "class_data": [],
                "balance_score": 0.82,
                "outliers": ["Fire Mage", "Beast Mastery Hunter"]
            }
        }


class SpellUsageEntry(BaseModel):
    """Single spell usage entry."""

    spell_id: int = Field(..., description="Spell ID")
    spell_name: str = Field(..., description="Spell name")
    cast_count: int = Field(..., description="Number of casts", ge=0)
    total_damage: int = Field(0, description="Total damage done", ge=0)
    total_healing: int = Field(0, description="Total healing done", ge=0)
    crit_rate: float = Field(0.0, description="Critical strike rate", ge=0, le=100)
    usage_frequency: float = Field(..., description="How often this spell is used", ge=0, le=100)

    class Config:
        schema_extra = {
            "example": {
                "spell_id": 133,
                "spell_name": "Fireball",
                "cast_count": 150,
                "total_damage": 15000000,
                "total_healing": 0,
                "crit_rate": 35.2,
                "usage_frequency": 85.7
            }
        }


class SpellUsageStats(BaseModel):
    """Spell usage statistics analysis."""

    character_name: Optional[str] = Field(None, description="Character name (if for specific character)")
    class_name: Optional[str] = Field(None, description="Class name (if for specific class)")
    time_range: TimeRange = Field(..., description="Time range for analysis")
    spell_entries: List[SpellUsageEntry] = Field(..., description="Spell usage data")
    most_used_spells: List[str] = Field(..., description="Most frequently used spells")
    highest_damage_spells: List[str] = Field(..., description="Highest damage spells")
    spell_diversity_score: float = Field(..., description="Spell diversity score (0-1)", ge=0, le=1)

    class Config:
        schema_extra = {
            "example": {
                "class_name": "Mage",
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "spell_entries": [],
                "most_used_spells": ["Fireball", "Fire Blast", "Pyroblast"],
                "highest_damage_spells": ["Pyroblast", "Combustion", "Fireball"],
                "spell_diversity_score": 0.75
            }
        }


class DamageSource(BaseModel):
    """Single damage source entry."""

    source_type: str = Field(..., description="Type of damage source (spell/ability/environmental)")
    source_name: str = Field(..., description="Name of the damage source")
    total_damage: int = Field(..., description="Total damage from this source", ge=0)
    percentage_of_total: float = Field(..., description="Percentage of total damage", ge=0, le=100)
    hit_count: int = Field(..., description="Number of hits", ge=0)
    average_hit: float = Field(..., description="Average damage per hit", ge=0)
    crit_rate: float = Field(0.0, description="Critical strike rate", ge=0, le=100)

    class Config:
        schema_extra = {
            "example": {
                "source_type": "spell",
                "source_name": "Fireball",
                "total_damage": 15000000,
                "percentage_of_total": 25.5,
                "hit_count": 150,
                "average_hit": 100000,
                "crit_rate": 35.2
            }
        }


class DamageBreakdown(BaseModel):
    """Damage breakdown analysis."""

    encounter_id: Optional[int] = Field(None, description="Specific encounter ID")
    character_name: Optional[str] = Field(None, description="Character name")
    time_range: Optional[TimeRange] = Field(None, description="Time range for analysis")
    damage_sources: List[DamageSource] = Field(..., description="Damage source breakdown")
    total_damage: int = Field(..., description="Total damage analyzed", ge=0)
    top_damage_percentage: float = Field(..., description="Percentage from top 3 sources", ge=0, le=100)
    damage_distribution: Dict[str, float] = Field(..., description="Damage distribution by category")

    class Config:
        schema_extra = {
            "example": {
                "encounter_id": 12345,
                "character_name": "Playername",
                "damage_sources": [],
                "total_damage": 50000000,
                "top_damage_percentage": 75.2,
                "damage_distribution": {
                    "direct_damage": 60.5,
                    "periodic_damage": 25.3,
                    "pet_damage": 14.2
                }
            }
        }