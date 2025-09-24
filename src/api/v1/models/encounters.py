"""
Encounter-related Pydantic models for API v1.

These models define the structure for encounter data including detailed
encounter information, replays, timelines, comparisons, and analysis.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from .common import TimeRange, PerformanceMetric


class EncounterDetail(BaseModel):
    """Detailed encounter information."""

    encounter_id: int = Field(..., description="Unique encounter ID")
    encounter_type: str = Field(..., description="Type of encounter (raid/mythic_plus)")
    boss_name: str = Field(..., description="Boss or encounter name")
    difficulty: str = Field(..., description="Encounter difficulty")
    zone_name: str = Field(..., description="Zone/instance name")

    # Timing information
    start_time: datetime = Field(..., description="Encounter start time")
    end_time: Optional[datetime] = Field(None, description="Encounter end time")
    duration: float = Field(..., description="Total encounter duration (seconds)")
    combat_duration: Optional[float] = Field(None, description="Active combat duration (seconds)")

    # Outcome
    success: bool = Field(..., description="Whether encounter was successful")
    wipe_percentage: Optional[float] = Field(None, description="Boss health % at wipe")

    # Participants
    participants: List[str] = Field(..., description="Character names that participated")
    raid_size: int = Field(..., description="Number of participants")

    # Performance summary
    total_damage: int = Field(0, description="Total raid damage")
    total_healing: int = Field(0, description="Total raid healing")
    total_deaths: int = Field(0, description="Total number of deaths")

    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": 12345,
                "encounter_type": "raid",
                "boss_name": "Raszageth the Storm-Eater",
                "difficulty": "HEROIC",
                "zone_name": "Vault of the Incarnates",
                "start_time": "2023-10-15T20:30:00Z",
                "end_time": "2023-10-15T20:34:05Z",
                "duration": 245.7,
                "combat_duration": 220.3,
                "success": True,
                "participants": ["PlayerOne", "PlayerTwo", "PlayerThree"],
                "raid_size": 20,
                "total_damage": 50000000,
                "total_healing": 15000000,
                "total_deaths": 2,
            }
        }


class EncounterReplay(BaseModel):
    """Event-by-event encounter replay data."""

    encounter_id: int = Field(..., description="Encounter ID")
    events: List[Dict[str, Any]] = Field(..., description="Chronological event list")
    timeline_markers: List[Dict[str, Any]] = Field(
        default_factory=list, description="Important timeline markers"
    )
    playback_speed_options: List[float] = Field(
        default_factory=lambda: [0.25, 0.5, 1.0, 2.0, 4.0], description="Available playback speeds"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": 12345,
                "events": [
                    {
                        "timestamp": 0.0,
                        "type": "encounter_start",
                        "data": {"boss_name": "Raszageth"},
                    },
                    {
                        "timestamp": 5.2,
                        "type": "damage",
                        "source": "PlayerOne",
                        "target": "Raszageth",
                        "amount": 125000,
                    },
                ],
                "timeline_markers": [
                    {"time": 0.0, "label": "Pull Start", "type": "phase"},
                    {"time": 120.0, "label": "Phase 2", "type": "phase"},
                ],
            }
        }


class EncounterTimeline(BaseModel):
    """Visual timeline data for encounter."""

    encounter_id: int = Field(..., description="Encounter ID")
    phases: List[Dict[str, Any]] = Field(..., description="Encounter phases")
    damage_timeline: List[Dict[str, Any]] = Field(..., description="Damage over time data")
    healing_timeline: List[Dict[str, Any]] = Field(..., description="Healing over time data")
    resource_timeline: List[Dict[str, Any]] = Field(..., description="Resource usage over time")
    death_events: List[Dict[str, Any]] = Field(default_factory=list, description="Death events")

    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": 12345,
                "phases": [
                    {"start": 0.0, "end": 120.0, "name": "Phase 1", "description": "Ground phase"},
                    {"start": 120.0, "end": 245.7, "name": "Phase 2", "description": "Air phase"},
                ],
                "damage_timeline": [
                    {"time": 0.0, "raid_dps": 0},
                    {"time": 10.0, "raid_dps": 2500000},
                ],
            }
        }


class EncounterComparison(BaseModel):
    """Comparison between multiple encounter attempts."""

    encounters: List[EncounterDetail] = Field(..., description="Encounters being compared")
    metrics_comparison: Dict[str, List[float]] = Field(
        ..., description="Metric comparisons across attempts"
    )
    improvement_analysis: List[str] = Field(
        default_factory=list, description="Analysis of improvements"
    )
    regression_analysis: List[str] = Field(
        default_factory=list, description="Analysis of regressions"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "encounters": [],
                "metrics_comparison": {
                    "raid_dps": [2300000, 2450000, 2500000],
                    "deaths": [5, 3, 2],
                    "duration": [280.5, 265.2, 245.7],
                },
                "improvement_analysis": [
                    "DPS improved by 8.7% from attempt 1 to 3",
                    "Death count reduced by 60%",
                ],
            }
        }


class DeathAnalysis(BaseModel):
    """Death analysis for an encounter."""

    encounter_id: int = Field(..., description="Encounter ID")
    total_deaths: int = Field(..., description="Total number of deaths")
    death_events: List[Dict[str, Any]] = Field(..., description="Individual death events")
    death_timeline: List[Dict[str, Any]] = Field(..., description="Deaths over time")
    death_causes: Dict[str, int] = Field(..., description="Death causes breakdown")
    avoidable_deaths: int = Field(0, description="Number of avoidable deaths")

    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": 12345,
                "total_deaths": 3,
                "death_events": [
                    {
                        "character": "PlayerOne",
                        "time": 120.5,
                        "cause": "Storm Breath",
                        "avoidable": True,
                    }
                ],
                "death_causes": {"Storm Breath": 2, "Lightning Strike": 1},
                "avoidable_deaths": 2,
            }
        }


class ResourceUsage(BaseModel):
    """Resource usage analysis for encounter."""

    encounter_id: int = Field(..., description="Encounter ID")
    mana_usage: List[Dict[str, Any]] = Field(
        default_factory=list, description="Mana usage over time"
    )
    energy_usage: List[Dict[str, Any]] = Field(
        default_factory=list, description="Energy usage over time"
    )
    rage_usage: List[Dict[str, Any]] = Field(
        default_factory=list, description="Rage usage over time"
    )
    cooldown_usage: List[Dict[str, Any]] = Field(
        default_factory=list, description="Major cooldown usage"
    )
    potion_usage: List[Dict[str, Any]] = Field(
        default_factory=list, description="Potion and consumable usage"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": 12345,
                "cooldown_usage": [
                    {
                        "character": "PlayerOne",
                        "ability": "Combustion",
                        "uses": 2,
                        "timestamps": [45.2, 180.7],
                    }
                ],
            }
        }
