"""
Guild-related Pydantic models for API v1.

These models define the structure for guild data including roster management,
attendance tracking, performance analysis, and raid composition.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .common import TimeRange, ServerInfo, WoWClass, PerformanceMetric


class GuildMember(BaseModel):
    """Individual guild member information."""

    character_name: str = Field(..., description="Character name")
    class_info: WoWClass = Field(..., description="Character class information")
    current_spec: Optional[str] = Field(None, description="Current specialization")
    rank: str = Field(..., description="Guild rank/role")
    join_date: Optional[datetime] = Field(None, description="When they joined the guild")
    last_seen: datetime = Field(..., description="Last activity timestamp")

    # Performance summary
    average_dps: float = Field(0.0, description="Average DPS", ge=0)
    average_hps: float = Field(0.0, description="Average HPS", ge=0)
    attendance_rate: float = Field(0.0, description="Attendance percentage", ge=0, le=100)
    total_encounters: int = Field(0, description="Total encounters participated", ge=0)

    # Status
    active_status: str = Field(..., description="Activity status (active/inactive/trial/etc.)")
    notes: Optional[str] = Field(None, description="Additional notes about the member")

    class Config:
        schema_extra = {
            "example": {
                "character_name": "Playername",
                "class_info": {
                    "id": 8,
                    "name": "Mage",
                    "color": "#69CCF0"
                },
                "current_spec": "Fire",
                "rank": "Raider",
                "join_date": "2023-08-15T00:00:00Z",
                "last_seen": "2023-10-15T20:30:00Z",
                "average_dps": 125000.5,
                "average_hps": 2500.0,
                "attendance_rate": 85.5,
                "total_encounters": 150,
                "active_status": "active"
            }
        }


class GuildRoster(BaseModel):
    """Complete guild roster information."""

    guild_name: str = Field(..., description="Guild name")
    server: ServerInfo = Field(..., description="Guild server information")
    total_members: int = Field(..., description="Total number of members", ge=0)
    active_members: int = Field(..., description="Number of active members", ge=0)
    members: List[GuildMember] = Field(..., description="Guild member list")

    # Composition analysis
    class_distribution: Dict[str, int] = Field(..., description="Members by class")
    spec_distribution: Dict[str, int] = Field(..., description="Members by specialization")
    rank_distribution: Dict[str, int] = Field(..., description="Members by rank")

    # Activity metrics
    average_attendance: float = Field(0.0, description="Guild average attendance", ge=0, le=100)
    recruitment_needs: List[str] = Field(default_factory=list, description="Classes/specs needed")

    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last roster update")

    class Config:
        schema_extra = {
            "example": {
                "guild_name": "Example Guild",
                "server": {
                    "name": "Stormrage",
                    "region": "US"
                },
                "total_members": 50,
                "active_members": 35,
                "members": [],
                "class_distribution": {
                    "Mage": 3,
                    "Warrior": 4,
                    "Priest": 3
                },
                "spec_distribution": {
                    "Fire": 2,
                    "Frost": 1,
                    "Protection": 2
                },
                "average_attendance": 82.5,
                "recruitment_needs": ["Holy Priest", "Restoration Shaman"]
            }
        }


class AttendanceRecord(BaseModel):
    """Individual attendance record for an event."""

    character_name: str = Field(..., description="Character name")
    event_date: datetime = Field(..., description="Event date")
    event_type: str = Field(..., description="Type of event (raid/mythic+/etc.)")
    event_name: str = Field(..., description="Specific event name")
    attended: bool = Field(..., description="Whether they attended")
    late_arrival: bool = Field(False, description="Whether they arrived late")
    early_departure: bool = Field(False, description="Whether they left early")
    absence_reason: Optional[str] = Field(None, description="Reason for absence if applicable")

    class Config:
        schema_extra = {
            "example": {
                "character_name": "Playername",
                "event_date": "2023-10-15T20:00:00Z",
                "event_type": "raid",
                "event_name": "Vault of the Incarnates - Heroic",
                "attended": True,
                "late_arrival": False,
                "early_departure": False
            }
        }


class AttendanceTracking(BaseModel):
    """Guild attendance tracking and analysis."""

    guild_name: str = Field(..., description="Guild name")
    time_range: TimeRange = Field(..., description="Time range for attendance analysis")
    total_events: int = Field(..., description="Total number of events", ge=0)
    attendance_records: List[AttendanceRecord] = Field(..., description="Individual attendance records")

    # Summary statistics
    overall_attendance_rate: float = Field(..., description="Overall attendance rate", ge=0, le=100)
    member_attendance_summary: Dict[str, Dict[str, Any]] = Field(..., description="Per-member attendance summary")
    event_attendance_summary: Dict[str, Dict[str, Any]] = Field(..., description="Per-event attendance summary")

    # Trends and analysis
    attendance_trends: List[Dict[str, Any]] = Field(default_factory=list, description="Attendance trends over time")
    consistent_attendees: List[str] = Field(default_factory=list, description="Members with high consistent attendance")
    attendance_concerns: List[str] = Field(default_factory=list, description="Members with attendance issues")

    class Config:
        schema_extra = {
            "example": {
                "guild_name": "Example Guild",
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "total_events": 12,
                "attendance_records": [],
                "overall_attendance_rate": 85.5,
                "member_attendance_summary": {
                    "Playername": {
                        "attended": 10,
                        "total": 12,
                        "rate": 83.3
                    }
                },
                "consistent_attendees": ["Playername", "AnotherPlayer"],
                "attendance_concerns": ["InconsistentPlayer"]
            }
        }


class GuildPerformanceMetrics(BaseModel):
    """Guild-wide performance metrics."""

    time_range: TimeRange = Field(..., description="Time range for metrics")
    encounter_type: Optional[str] = Field(None, description="Type of encounters analyzed")
    difficulty: Optional[str] = Field(None, description="Difficulty level analyzed")

    # Aggregate metrics
    total_encounters: int = Field(..., description="Total encounters analyzed", ge=0)
    success_rate: float = Field(..., description="Overall success rate", ge=0, le=100)
    average_raid_dps: float = Field(..., description="Average raid DPS", ge=0)
    average_raid_hps: float = Field(..., description="Average raid HPS", ge=0)
    average_encounter_duration: float = Field(..., description="Average encounter duration", ge=0)

    # Performance trends
    performance_trends: Dict[str, List[Dict[str, Any]]] = Field(..., description="Performance trends over time")
    top_performers: Dict[str, List[Dict[str, Any]]] = Field(..., description="Top performers by metric")
    improvement_areas: List[str] = Field(default_factory=list, description="Areas needing improvement")

    class Config:
        schema_extra = {
            "example": {
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "encounter_type": "raid",
                "difficulty": "HEROIC",
                "total_encounters": 150,
                "success_rate": 75.5,
                "average_raid_dps": 2500000.0,
                "average_raid_hps": 800000.0,
                "average_encounter_duration": 245.7,
                "top_performers": {
                    "dps": [
                        {"character": "Playername", "value": 125000.5}
                    ]
                },
                "improvement_areas": ["Survivability", "Cooldown coordination"]
            }
        }


class GuildPerformance(BaseModel):
    """Comprehensive guild performance analysis."""

    guild_name: str = Field(..., description="Guild name")
    analysis_period: TimeRange = Field(..., description="Analysis time period")

    # Performance by content type
    raid_performance: Optional[GuildPerformanceMetrics] = Field(None, description="Raid performance metrics")
    mythic_plus_performance: Optional[GuildPerformanceMetrics] = Field(None, description="Mythic+ performance metrics")

    # Progression tracking
    progression_status: Dict[str, Any] = Field(..., description="Current progression status")
    recent_achievements: List[Dict[str, Any]] = Field(default_factory=list, description="Recent achievements")
    progression_goals: List[str] = Field(default_factory=list, description="Progression goals")

    # Overall assessment
    performance_score: float = Field(..., description="Overall performance score (0-100)", ge=0, le=100)
    strengths: List[str] = Field(default_factory=list, description="Guild strengths")
    weaknesses: List[str] = Field(default_factory=list, description="Areas for improvement")
    recommendations: List[str] = Field(default_factory=list, description="Improvement recommendations")

    class Config:
        schema_extra = {
            "example": {
                "guild_name": "Example Guild",
                "analysis_period": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "progression_status": {
                    "current_tier": "Vault of the Incarnates",
                    "heroic_progress": "8/8",
                    "mythic_progress": "3/8"
                },
                "performance_score": 85.5,
                "strengths": ["High DPS output", "Good attendance"],
                "weaknesses": ["Survivability issues", "Cooldown coordination"],
                "recommendations": ["Focus on defensive cooldown usage", "Improve positioning"]
            }
        }


class RaidCompositionSlot(BaseModel):
    """Single slot in raid composition."""

    role: str = Field(..., description="Role (tank/healer/dps)")
    class_name: str = Field(..., description="Class name")
    spec_name: str = Field(..., description="Specialization name")
    character_name: Optional[str] = Field(None, description="Assigned character name")
    priority: int = Field(..., description="Priority level (1=highest)", ge=1)
    notes: Optional[str] = Field(None, description="Notes about this slot")

    class Config:
        schema_extra = {
            "example": {
                "role": "tank",
                "class_name": "Warrior",
                "spec_name": "Protection",
                "character_name": "Tankname",
                "priority": 1,
                "notes": "Main tank for all encounters"
            }
        }


class RaidComposition(BaseModel):
    """Raid composition planning and analysis."""

    composition_name: str = Field(..., description="Name of this composition")
    encounter_type: str = Field(..., description="Type of encounter this is for")
    encounter_name: Optional[str] = Field(None, description="Specific encounter name")
    raid_size: int = Field(..., description="Target raid size", ge=1, le=30)

    # Composition slots
    tanks: List[RaidCompositionSlot] = Field(..., description="Tank assignments")
    healers: List[RaidCompositionSlot] = Field(..., description="Healer assignments")
    dps: List[RaidCompositionSlot] = Field(..., description="DPS assignments")

    # Analysis
    composition_score: float = Field(..., description="Composition effectiveness score (0-100)", ge=0, le=100)
    synergies: List[str] = Field(default_factory=list, description="Class/spec synergies")
    potential_issues: List[str] = Field(default_factory=list, description="Potential composition issues")
    alternative_options: List[str] = Field(default_factory=list, description="Alternative composition options")

    created_date: datetime = Field(default_factory=datetime.utcnow, description="When composition was created")
    last_used: Optional[datetime] = Field(None, description="When composition was last used")

    class Config:
        schema_extra = {
            "example": {
                "composition_name": "Heroic Raszageth Comp",
                "encounter_type": "raid",
                "encounter_name": "Raszageth the Storm-Eater",
                "raid_size": 20,
                "tanks": [
                    {
                        "role": "tank",
                        "class_name": "Warrior",
                        "spec_name": "Protection",
                        "character_name": "Tankname",
                        "priority": 1
                    }
                ],
                "healers": [],
                "dps": [],
                "composition_score": 92.5,
                "synergies": ["Warrior + Death Knight tank synergy", "Mage + Priest DPS buffs"],
                "potential_issues": ["Limited ranged DPS for air phase"]
            }
        }