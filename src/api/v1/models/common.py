"""
Common Pydantic models used across all API responses.

These models provide shared types for pagination, sorting, filtering,
and other common API functionality.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Generic, TypeVar, Union
from enum import Enum
from pydantic import BaseModel, Field, validator

T = TypeVar('T')


class SortOrder(str, Enum):
    """Sort order enumeration."""
    ASC = "asc"
    DESC = "desc"


class TimeRange(BaseModel):
    """Time range specification for queries."""
    start: datetime = Field(..., description="Start time (inclusive)")
    end: datetime = Field(..., description="End time (inclusive)")

    @validator('end')
    def end_after_start(cls, v, values):
        if 'start' in values and v <= values['start']:
            raise ValueError('End time must be after start time')
        return v

    class Config:
        schema_extra = {
            "example": {
                "start": "2023-10-01T00:00:00Z",
                "end": "2023-10-31T23:59:59Z"
            }
        }


class PaginationMeta(BaseModel):
    """Pagination metadata for paginated responses."""

    total: int = Field(..., description="Total number of items", ge=0)
    limit: int = Field(..., description="Number of items per page", ge=1, le=1000)
    offset: int = Field(..., description="Offset from start", ge=0)
    has_next: bool = Field(..., description="Whether there are more items")
    has_previous: bool = Field(..., description="Whether there are previous items")
    page: int = Field(..., description="Current page number (1-based)", ge=1)
    total_pages: int = Field(..., description="Total number of pages", ge=1)

    @validator('page', pre=True)
    def calculate_page(cls, v, values):
        if 'offset' in values and 'limit' in values:
            return (values['offset'] // values['limit']) + 1
        return v

    @validator('total_pages', pre=True)
    def calculate_total_pages(cls, v, values):
        if 'total' in values and 'limit' in values:
            return max(1, (values['total'] + values['limit'] - 1) // values['limit'])
        return v

    @validator('has_next', pre=True)
    def calculate_has_next(cls, v, values):
        if 'offset' in values and 'limit' in values and 'total' in values:
            return values['offset'] + values['limit'] < values['total']
        return v

    @validator('has_previous', pre=True)
    def calculate_has_previous(cls, v, values):
        if 'offset' in values:
            return values['offset'] > 0
        return v

    class Config:
        schema_extra = {
            "example": {
                "total": 250,
                "limit": 20,
                "offset": 40,
                "has_next": True,
                "has_previous": True,
                "page": 3,
                "total_pages": 13
            }
        }


class FilterCriteria(BaseModel):
    """Generic filter criteria for API queries."""

    field: str = Field(..., description="Field name to filter on")
    operator: str = Field(..., description="Filter operator (eq, ne, gt, lt, ge, le, in, like)")
    value: Union[str, int, float, bool, List[Any]] = Field(..., description="Filter value")

    @validator('operator')
    def validate_operator(cls, v):
        allowed_operators = ['eq', 'ne', 'gt', 'lt', 'ge', 'le', 'in', 'like', 'not_in']
        if v not in allowed_operators:
            raise ValueError(f'Operator must be one of: {", ".join(allowed_operators)}')
        return v

    class Config:
        schema_extra = {
            "example": {
                "field": "difficulty",
                "operator": "in",
                "value": ["HEROIC", "MYTHIC"]
            }
        }


class ServerInfo(BaseModel):
    """WoW server information."""

    name: str = Field(..., description="Server name")
    region: str = Field(..., description="Server region (US, EU, etc.)")
    locale: Optional[str] = Field(None, description="Server locale")
    timezone: Optional[str] = Field(None, description="Server timezone")

    class Config:
        schema_extra = {
            "example": {
                "name": "Stormrage",
                "region": "US",
                "locale": "enUS",
                "timezone": "America/New_York"
            }
        }


class WoWClass(BaseModel):
    """WoW class information."""

    id: int = Field(..., description="Class ID")
    name: str = Field(..., description="Class name")
    color: str = Field(..., description="Class color hex code")
    specs: List[Dict[str, Any]] = Field(default_factory=list, description="Available specializations")

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "name": "Warrior",
                "color": "#C79C6E",
                "specs": [
                    {"id": 71, "name": "Arms", "role": "DPS"},
                    {"id": 72, "name": "Fury", "role": "DPS"},
                    {"id": 73, "name": "Protection", "role": "Tank"}
                ]
            }
        }


class ItemInfo(BaseModel):
    """WoW item information."""

    id: int = Field(..., description="Item ID")
    name: str = Field(..., description="Item name")
    quality: str = Field(..., description="Item quality (Poor, Common, Uncommon, Rare, Epic, Legendary)")
    item_level: int = Field(..., description="Item level", ge=1)
    slot: Optional[str] = Field(None, description="Equipment slot")
    icon: Optional[str] = Field(None, description="Item icon name")

    class Config:
        schema_extra = {
            "example": {
                "id": 195480,
                "name": "Primal Berserk Spaulders",
                "quality": "Epic",
                "item_level": 415,
                "slot": "Shoulder",
                "icon": "inv_shoulder_plate_raiddeathknight_s_01"
            }
        }


class SpellInfo(BaseModel):
    """WoW spell information."""

    id: int = Field(..., description="Spell ID")
    name: str = Field(..., description="Spell name")
    school: Optional[str] = Field(None, description="Spell school (Physical, Fire, Frost, etc.)")
    icon: Optional[str] = Field(None, description="Spell icon name")
    cooldown: Optional[int] = Field(None, description="Cooldown in milliseconds")
    cast_time: Optional[int] = Field(None, description="Cast time in milliseconds")

    class Config:
        schema_extra = {
            "example": {
                "id": 190411,
                "name": "Incarnation: Chosen of Elune",
                "school": "Nature",
                "icon": "spell_druid_incarnation",
                "cooldown": 180000,
                "cast_time": 0
            }
        }


class PerformanceMetric(BaseModel):
    """Performance metric with metadata."""

    value: float = Field(..., description="Metric value")
    percentile: Optional[float] = Field(None, description="Percentile ranking (0-100)", ge=0, le=100)
    rank: Optional[int] = Field(None, description="Absolute ranking", ge=1)
    total_participants: Optional[int] = Field(None, description="Total number of participants", ge=1)

    class Config:
        schema_extra = {
            "example": {
                "value": 125000.5,
                "percentile": 95.3,
                "rank": 2,
                "total_participants": 20
            }
        }