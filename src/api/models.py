"""
Pydantic models for streaming API.
"""

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class StreamMessage(BaseModel):
    """Message sent from client to streaming endpoint."""

    type: Literal["log_line", "start_session", "end_session", "heartbeat", "checkpoint"]
    timestamp: float = Field(..., description="Unix timestamp with microseconds")
    line: Optional[str] = Field(None, description="Combat log line")
    sequence: Optional[int] = Field(None, description="Sequence number for ordering")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "log_line",
                "timestamp": 1698765432.123,
                "line": '9/15/2025 21:30:21.462-4  SPELL_DAMAGE,Player-1234,PlayerName,0x512,0x0,Target-5678,TargetName,0x10a28,0x0,1234,"Spell Name",0x40,5678,0,0,0,0,0,0,0',
                "sequence": 12345,
                "metadata": {},
            }
        }


class StreamResponse(BaseModel):
    """Response from server to streaming client."""

    type: Literal["ack", "error", "status", "metrics"]
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())
    message: Optional[str] = None
    sequence_ack: Optional[int] = Field(
        None, description="Last processed sequence number"
    )
    data: Optional[Dict[str, Any]] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "type": "ack",
                "timestamp": 1698765432.456,
                "sequence_ack": 12345,
                "data": {"events_processed": 1000, "lag_ms": 45},
            }
        }


class SessionStart(BaseModel):
    """Session start metadata."""

    client_id: str = Field(..., description="Unique client identifier")
    client_version: Optional[str] = Field(None, description="Client software version")
    character_name: Optional[str] = Field(None, description="Main character name")
    realm: Optional[str] = Field(None, description="WoW realm name")
    log_start_time: Optional[float] = Field(None, description="When logging started")

    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "desktop-client-123",
                "client_version": "1.0.0",
                "character_name": "Playername",
                "realm": "Stormrage",
                "log_start_time": 1698765400.0,
            }
        }


class AuthResponse(BaseModel):
    """Authentication response."""

    authenticated: bool
    client_id: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)
    rate_limit: Optional[Dict[str, int]] = None
    message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "authenticated": True,
                "client_id": "client-123",
                "permissions": ["stream", "query"],
                "rate_limit": {"events_per_minute": 10000, "connections": 5},
                "message": "Authentication successful",
            }
        }


class StreamStats(BaseModel):
    """Real-time streaming statistics."""

    total_events: int = 0
    events_per_second: float = 0.0
    buffer_size: int = 0
    lag_ms: float = 0.0
    encounters_active: int = 0
    characters_tracked: int = 0
    uptime_seconds: float = 0.0
    last_event_time: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "total_events": 150000,
                "events_per_second": 245.7,
                "buffer_size": 150,
                "lag_ms": 23.5,
                "encounters_active": 1,
                "characters_tracked": 20,
                "uptime_seconds": 3600.0,
                "last_event_time": 1698765432.789,
            }
        }


class EncounterUpdate(BaseModel):
    """Real-time encounter state update."""

    encounter_id: Optional[int] = None
    encounter_type: str  # "raid" or "mythic_plus"
    boss_name: str
    difficulty: Optional[str] = None
    status: Literal["started", "in_progress", "ended", "wiped"]
    start_time: float
    duration: float = 0.0
    participants: int = 0
    top_dps: Optional[Dict[str, float]] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": 12345,
                "encounter_type": "raid",
                "boss_name": "Raszageth",
                "difficulty": "HEROIC",
                "status": "in_progress",
                "start_time": 1698765432.0,
                "duration": 245.7,
                "participants": 20,
                "top_dps": {"PlayerName": 125000.5},
            }
        }


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str
    code: int
    details: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Authentication failed",
                "code": 401,
                "details": "Invalid API key provided",
                "timestamp": 1698765432.123,
            }
        }


class ItemInfo(BaseModel):
    """WoW item information."""

    item_id: int
    item_name: str
    quality: int  # 0=Poor, 1=Common, 2=Uncommon, 3=Rare, 4=Epic, 5=Legendary
    item_level: int
    item_type: Optional[str] = None
    subtype: Optional[str] = None
    slot: Optional[str] = None
    class_mask: int = 0
    races_mask: int = 0
    source_type: Optional[str] = None
    source_info: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "item_id": 212448,
                "item_name": "Void Reaper's Warp Blade",
                "quality": 4,
                "item_level": 639,
                "item_type": "Weapon",
                "subtype": "One-Handed Sword",
                "slot": "MainHand",
                "class_mask": 1024,
                "races_mask": 0,
                "source_type": "raid",
                "source_info": "Nerubar Palace"
            }
        }


class LootDrop(BaseModel):
    """Loot drop record."""

    drop_id: int
    encounter_id: int
    character_name: str
    character_guid: str
    item_id: int
    item_name: str
    item_level: int
    quality: int
    quantity: int = 1
    drop_timestamp: float
    source_name: Optional[str] = None
    loot_method: Optional[str] = None
    encounter_name: Optional[str] = None
    difficulty: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "drop_id": 1234,
                "encounter_id": 567,
                "character_name": "Playername",
                "character_guid": "Player-1234-567890AB",
                "item_id": 212448,
                "item_name": "Void Reaper's Warp Blade",
                "item_level": 639,
                "quality": 4,
                "quantity": 1,
                "drop_timestamp": 1698765432.789,
                "source_name": "Ulgrax the Devourer",
                "loot_method": "personal_loot",
                "encounter_name": "Ulgrax the Devourer",
                "difficulty": "HEROIC"
            }
        }


class PlayerStats(BaseModel):
    """Aggregated player statistics."""

    character_name: str
    character_guid: str
    realm: Optional[str] = None
    class_name: Optional[str] = None
    spec_name: Optional[str] = None
    total_encounters: int = 0
    total_loot_received: int = 0
    average_dps: float = 0.0
    average_hps: float = 0.0
    total_damage_done: int = 0
    total_healing_done: int = 0
    death_count: int = 0
    recent_items: List[ItemInfo] = Field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "character_name": "Playername",
                "character_guid": "Player-1234-567890AB",
                "realm": "Stormrage",
                "class_name": "Death Knight",
                "spec_name": "Unholy",
                "total_encounters": 45,
                "total_loot_received": 12,
                "average_dps": 125000.5,
                "average_hps": 0.0,
                "total_damage_done": 1250000000,
                "total_healing_done": 0,
                "death_count": 3,
                "recent_items": [],
                "first_seen": "2024-01-15T20:30:00",
                "last_seen": "2024-01-20T22:15:00"
            }
        }


class LootSummary(BaseModel):
    """Loot distribution summary."""

    total_items_distributed: int = 0
    total_encounters: int = 0
    distribution_by_difficulty: Dict[str, int] = Field(default_factory=dict)
    distribution_by_class: Dict[str, int] = Field(default_factory=dict)
    distribution_by_item_type: Dict[str, int] = Field(default_factory=dict)
    top_recipients: List[Dict[str, Any]] = Field(default_factory=list)
    recent_drops: List[LootDrop] = Field(default_factory=list)
    average_item_level: float = 0.0

    class Config:
        json_schema_extra = {
            "example": {
                "total_items_distributed": 450,
                "total_encounters": 120,
                "distribution_by_difficulty": {"HEROIC": 180, "MYTHIC": 120, "NORMAL": 150},
                "distribution_by_class": {"Death Knight": 45, "Paladin": 38, "Warrior": 42},
                "distribution_by_item_type": {"Weapon": 25, "Armor": 180, "Trinket": 35},
                "top_recipients": [{"character_name": "Playername", "item_count": 15}],
                "recent_drops": [],
                "average_item_level": 635.5
            }
        }
