"""
Character-related Pydantic models for API v1.

These models define the structure for character data including profiles,
performance metrics, history, rankings, gear analysis, and talents.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .common import ServerInfo, WoWClass, ItemInfo, SpellInfo, PerformanceMetric, TimeRange


class CharacterProfile(BaseModel):
    """Complete character profile information."""

    character_id: int = Field(..., description="Internal character ID")
    character_guid: str = Field(..., description="WoW character GUID")
    name: str = Field(..., description="Character name")
    server: ServerInfo = Field(..., description="Character's server information")
    class_info: WoWClass = Field(..., description="Character class information")
    current_spec: Optional[str] = Field(None, description="Current specialization")
    level: Optional[int] = Field(None, description="Character level", ge=1, le=80)
    item_level: Optional[int] = Field(None, description="Average item level", ge=1)

    # Activity statistics
    first_seen: datetime = Field(..., description="First appearance in logs")
    last_seen: datetime = Field(..., description="Most recent appearance in logs")
    total_encounters: int = Field(0, description="Total encounters participated in", ge=0)
    total_combat_time: float = Field(0.0, description="Total time in combat (seconds)", ge=0)

    # Overall performance summary
    lifetime_damage: int = Field(0, description="Total damage dealt", ge=0)
    lifetime_healing: int = Field(0, description="Total healing done", ge=0)
    lifetime_deaths: int = Field(0, description="Total number of deaths", ge=0)
    average_dps: float = Field(0.0, description="Average DPS across all encounters", ge=0)
    average_hps: float = Field(0.0, description="Average HPS across all encounters", ge=0)

    # Recent activity
    recent_encounters: List[int] = Field(default_factory=list, description="Recent encounter IDs")
    activity_streak: int = Field(0, description="Consecutive days with activity", ge=0)

    class Config:
        schema_extra = {
            "example": {
                "character_id": 12345,
                "character_guid": "Player-1234-56789ABC",
                "name": "Playername",
                "server": {"name": "Stormrage", "region": "US", "locale": "enUS"},
                "class_info": {
                    "id": 8,
                    "name": "Mage",
                    "color": "#69CCF0",
                    "specs": [
                        {"id": 62, "name": "Arcane", "role": "DPS"},
                        {"id": 63, "name": "Fire", "role": "DPS"},
                        {"id": 64, "name": "Frost", "role": "DPS"},
                    ],
                },
                "current_spec": "Fire",
                "level": 70,
                "item_level": 415,
                "first_seen": "2023-09-01T14:30:00Z",
                "last_seen": "2023-10-15T20:45:00Z",
                "total_encounters": 150,
                "total_combat_time": 18000.0,
                "lifetime_damage": 500000000,
                "lifetime_healing": 2500000,
                "lifetime_deaths": 8,
                "average_dps": 125000.5,
                "average_hps": 500.2,
                "recent_encounters": [12345, 12346, 12347],
                "activity_streak": 15,
            }
        }


class CharacterPerformance(BaseModel):
    """Character performance metrics for a specific encounter or time period."""

    character_name: str = Field(..., description="Character name")
    encounter_id: Optional[int] = Field(None, description="Specific encounter ID")
    time_range: Optional[TimeRange] = Field(None, description="Time range for metrics")

    # Damage metrics
    damage_done: PerformanceMetric = Field(..., description="Total damage dealt")
    dps: PerformanceMetric = Field(..., description="Damage per second")
    damage_taken: PerformanceMetric = Field(..., description="Damage taken")

    # Healing metrics
    healing_done: PerformanceMetric = Field(..., description="Total healing done")
    hps: PerformanceMetric = Field(..., description="Healing per second")
    overhealing: int = Field(0, description="Amount of overhealing", ge=0)

    # Survival metrics
    deaths: int = Field(0, description="Number of deaths", ge=0)
    time_alive_percent: float = Field(100.0, description="Percentage of time alive", ge=0, le=100)
    damage_avoided: int = Field(0, description="Damage avoided through mechanics", ge=0)

    # Activity metrics
    activity_percentage: float = Field(0.0, description="Activity percentage", ge=0, le=100)
    cast_efficiency: float = Field(0.0, description="Cast time efficiency", ge=0, le=100)
    uptime_percentage: float = Field(0.0, description="Combat uptime percentage", ge=0, le=100)

    # Advanced metrics
    damage_absorbed: int = Field(0, description="Damage absorbed by shields", ge=0)
    interrupts: int = Field(0, description="Number of interrupts performed", ge=0)
    dispels: int = Field(0, description="Number of dispels performed", ge=0)

    class Config:
        schema_extra = {
            "example": {
                "character_name": "Playername",
                "encounter_id": 12345,
                "damage_done": {
                    "value": 5000000.0,
                    "percentile": 95.3,
                    "rank": 2,
                    "total_participants": 20,
                },
                "dps": {"value": 125000.5, "percentile": 95.3, "rank": 2, "total_participants": 20},
                "healing_done": {
                    "value": 500000.0,
                    "percentile": 75.0,
                    "rank": 5,
                    "total_participants": 20,
                },
                "deaths": 0,
                "time_alive_percent": 100.0,
                "activity_percentage": 98.5,
                "cast_efficiency": 92.3,
                "interrupts": 3,
                "dispels": 1,
            }
        }


class CharacterHistoryEntry(BaseModel):
    """Single entry in character history."""

    date: datetime = Field(..., description="Date of the entry")
    encounter_id: int = Field(..., description="Encounter ID")
    boss_name: str = Field(..., description="Boss name")
    difficulty: str = Field(..., description="Encounter difficulty")
    success: bool = Field(..., description="Whether encounter was successful")
    dps: float = Field(0.0, description="DPS for this encounter", ge=0)
    hps: float = Field(0.0, description="HPS for this encounter", ge=0)
    deaths: int = Field(0, description="Deaths in this encounter", ge=0)
    duration: float = Field(0.0, description="Encounter duration in seconds", ge=0)

    class Config:
        schema_extra = {
            "example": {
                "date": "2023-10-15T20:30:00Z",
                "encounter_id": 12345,
                "boss_name": "Raszageth",
                "difficulty": "HEROIC",
                "success": True,
                "dps": 125000.5,
                "hps": 2500.0,
                "deaths": 0,
                "duration": 245.7,
            }
        }


class CharacterHistory(BaseModel):
    """Character performance history over time."""

    character_name: str = Field(..., description="Character name")
    time_range: TimeRange = Field(..., description="Time range for history")
    entries: List[CharacterHistoryEntry] = Field(..., description="History entries")
    total_encounters: int = Field(..., description="Total encounters in period")

    # Summary statistics
    average_dps: float = Field(0.0, description="Average DPS over period", ge=0)
    best_dps: float = Field(0.0, description="Best DPS performance", ge=0)
    average_hps: float = Field(0.0, description="Average HPS over period", ge=0)
    best_hps: float = Field(0.0, description="Best HPS performance", ge=0)
    success_rate: float = Field(0.0, description="Encounter success rate", ge=0, le=100)
    total_deaths: int = Field(0, description="Total deaths in period", ge=0)

    class Config:
        schema_extra = {
            "example": {
                "character_name": "Playername",
                "time_range": {"start": "2023-10-01T00:00:00Z", "end": "2023-10-31T23:59:59Z"},
                "entries": [
                    {
                        "date": "2023-10-15T20:30:00Z",
                        "encounter_id": 12345,
                        "boss_name": "Raszageth",
                        "difficulty": "HEROIC",
                        "success": True,
                        "dps": 125000.5,
                        "hps": 2500.0,
                        "deaths": 0,
                        "duration": 245.7,
                    }
                ],
                "total_encounters": 25,
                "average_dps": 120000.0,
                "best_dps": 135000.0,
                "average_hps": 2200.0,
                "best_hps": 3500.0,
                "success_rate": 85.5,
                "total_deaths": 3,
            }
        }


class CharacterRanking(BaseModel):
    """Character ranking information."""

    character_name: str = Field(..., description="Character name")
    metric: str = Field(..., description="Ranking metric")
    global_rank: Optional[int] = Field(None, description="Global rank", ge=1)
    server_rank: Optional[int] = Field(None, description="Server rank", ge=1)
    class_rank: Optional[int] = Field(None, description="Class rank", ge=1)
    spec_rank: Optional[int] = Field(None, description="Specialization rank", ge=1)
    percentile: float = Field(..., description="Percentile ranking", ge=0, le=100)
    value: float = Field(..., description="Metric value")
    total_parses: int = Field(..., description="Total number of parses", ge=1)

    class Config:
        schema_extra = {
            "example": {
                "character_name": "Playername",
                "metric": "dps",
                "global_rank": 150,
                "server_rank": 5,
                "class_rank": 25,
                "spec_rank": 8,
                "percentile": 95.3,
                "value": 125000.5,
                "total_parses": 5000,
            }
        }


class CharacterGearItem(BaseModel):
    """Single gear item for character."""

    slot: str = Field(..., description="Equipment slot")
    item: ItemInfo = Field(..., description="Item information")
    enchant_id: Optional[int] = Field(None, description="Enchant ID")
    gem_ids: List[int] = Field(default_factory=list, description="Gem IDs")
    upgrade_level: int = Field(0, description="Item upgrade level", ge=0)

    class Config:
        schema_extra = {
            "example": {
                "slot": "Head",
                "item": {
                    "id": 195480,
                    "name": "Primal Berserk Faceguard",
                    "quality": "Epic",
                    "item_level": 415,
                    "slot": "Head",
                },
                "enchant_id": 6643,
                "gem_ids": [192985, 192985],
                "upgrade_level": 5,
            }
        }


class CharacterGear(BaseModel):
    """Character gear analysis."""

    character_name: str = Field(..., description="Character name")
    snapshot_time: datetime = Field(..., description="When gear was recorded")
    average_item_level: float = Field(..., description="Average item level")
    items: List[CharacterGearItem] = Field(..., description="Equipped items")
    set_bonuses: List[Dict[str, Any]] = Field(
        default_factory=list, description="Active set bonuses"
    )
    optimization_score: Optional[float] = Field(
        None, description="Gear optimization score", ge=0, le=100
    )

    class Config:
        schema_extra = {
            "example": {
                "character_name": "Playername",
                "snapshot_time": "2023-10-15T20:30:00Z",
                "average_item_level": 415.5,
                "items": [
                    {
                        "slot": "Head",
                        "item": {
                            "id": 195480,
                            "name": "Primal Berserk Faceguard",
                            "quality": "Epic",
                            "item_level": 415,
                        },
                        "enchant_id": 6643,
                        "gem_ids": [192985],
                    }
                ],
                "set_bonuses": [
                    {
                        "set_name": "Primal Berserk",
                        "pieces_equipped": 2,
                        "bonus_description": "2-piece: Increases critical strike by 5%",
                    }
                ],
                "optimization_score": 92.5,
            }
        }


class CharacterTalentRow(BaseModel):
    """Single talent row."""

    row: int = Field(..., description="Talent row number", ge=1)
    selected_talent: SpellInfo = Field(..., description="Selected talent")
    alternative_talents: List[SpellInfo] = Field(
        default_factory=list, description="Other talents in row"
    )

    class Config:
        schema_extra = {
            "example": {
                "row": 1,
                "selected_talent": {
                    "id": 190411,
                    "name": "Incarnation: Chosen of Elune",
                    "school": "Nature",
                    "icon": "spell_druid_incarnation",
                },
                "alternative_talents": [
                    {
                        "id": 102560,
                        "name": "Force of Nature",
                        "school": "Nature",
                        "icon": "ability_druid_forceofnature",
                    }
                ],
            }
        }


class CharacterTalents(BaseModel):
    """Character talent and specialization analysis."""

    character_name: str = Field(..., description="Character name")
    specialization: str = Field(..., description="Current specialization")
    talent_loadout: str = Field(..., description="Talent loadout string")
    snapshot_time: datetime = Field(..., description="When talents were recorded")
    talent_rows: List[CharacterTalentRow] = Field(..., description="Talent selections by row")
    optimization_notes: List[str] = Field(
        default_factory=list, description="Talent optimization suggestions"
    )

    class Config:
        schema_extra = {
            "example": {
                "character_name": "Playername",
                "specialization": "Fire",
                "talent_loadout": "B4PAAAAAAAAAAAAAAAAAAAAAAAAASkISSSSSLJRSSSKSSSBAAAAAA",
                "snapshot_time": "2023-10-15T20:30:00Z",
                "talent_rows": [
                    {
                        "row": 1,
                        "selected_talent": {
                            "id": 190411,
                            "name": "Combustion",
                            "icon": "spell_fire_sealoffire",
                        },
                    }
                ],
                "optimization_notes": [
                    "Consider taking Phoenix Flames for better mobility",
                    "Flamestrike might be better for AoE encounters",
                ],
            }
        }
