"""
Base response models for API v1.

These models provide standardized response formats for different types
of API endpoints including pagination, time series, aggregations, etc.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Generic, TypeVar, Union
from pydantic import BaseModel, Field
from .common import PaginationMeta, TimeRange, SortOrder

T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """Base response model with metadata."""

    success: bool = Field(True, description="Whether the request was successful")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    data: T = Field(..., description="Response data")
    message: Optional[str] = Field(None, description="Optional message")

    class Config:
        arbitrary_types_allowed = True


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response with metadata."""

    items: List[T] = Field(..., description="List of items")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
    filters: Optional[Dict[str, Any]] = Field(None, description="Applied filters")
    sort: Optional[Dict[str, SortOrder]] = Field(None, description="Applied sorting")

    class Config:
        schema_extra = {
            "example": {
                "items": [],
                "pagination": {
                    "total": 250,
                    "limit": 20,
                    "offset": 40,
                    "has_next": True,
                    "has_previous": True,
                    "page": 3,
                    "total_pages": 13
                },
                "filters": {"difficulty": ["HEROIC", "MYTHIC"]},
                "sort": {"timestamp": "desc"}
            }
        }


class TimeSeriesPoint(BaseModel):
    """Single point in a time series."""

    timestamp: datetime = Field(..., description="Point timestamp")
    value: float = Field(..., description="Point value")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional point metadata")

    class Config:
        schema_extra = {
            "example": {
                "timestamp": "2023-10-15T14:30:00Z",
                "value": 125000.5,
                "metadata": {"encounter_id": 12345, "difficulty": "HEROIC"}
            }
        }


class TimeSeriesResponse(BaseModel):
    """Time series data response."""

    series_name: str = Field(..., description="Name of the time series")
    time_range: TimeRange = Field(..., description="Time range of the data")
    interval: str = Field(..., description="Data point interval (e.g., '1h', '1d')")
    data_points: List[TimeSeriesPoint] = Field(..., description="Time series data points")
    aggregation: Optional[str] = Field(None, description="Aggregation method used")
    total_points: int = Field(..., description="Total number of data points")

    class Config:
        schema_extra = {
            "example": {
                "series_name": "DPS Over Time",
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "interval": "1d",
                "data_points": [
                    {
                        "timestamp": "2023-10-15T14:30:00Z",
                        "value": 125000.5,
                        "metadata": {"encounter_id": 12345}
                    }
                ],
                "aggregation": "average",
                "total_points": 31
            }
        }


class AggregationResult(BaseModel):
    """Single aggregation result."""

    group_by: Dict[str, Any] = Field(..., description="Grouping criteria")
    metrics: Dict[str, float] = Field(..., description="Calculated metrics")
    count: int = Field(..., description="Number of items in this group")

    class Config:
        schema_extra = {
            "example": {
                "group_by": {"class_name": "Mage", "difficulty": "HEROIC"},
                "metrics": {
                    "avg_dps": 125000.5,
                    "max_dps": 150000.0,
                    "min_dps": 100000.0
                },
                "count": 25
            }
        }


class AggregationResponse(BaseModel):
    """Aggregated data response."""

    query: str = Field(..., description="Aggregation query description")
    group_by_fields: List[str] = Field(..., description="Fields used for grouping")
    metrics: List[str] = Field(..., description="Calculated metrics")
    time_range: Optional[TimeRange] = Field(None, description="Time range if applicable")
    results: List[AggregationResult] = Field(..., description="Aggregation results")
    total_groups: int = Field(..., description="Total number of groups")

    class Config:
        schema_extra = {
            "example": {
                "query": "Average DPS by class and difficulty",
                "group_by_fields": ["class_name", "difficulty"],
                "metrics": ["avg_dps", "max_dps", "min_dps"],
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "results": [
                    {
                        "group_by": {"class_name": "Mage", "difficulty": "HEROIC"},
                        "metrics": {"avg_dps": 125000.5, "max_dps": 150000.0, "min_dps": 100000.0},
                        "count": 25
                    }
                ],
                "total_groups": 10
            }
        }


class ComparisonItem(BaseModel):
    """Single item in a comparison."""

    identifier: str = Field(..., description="Unique identifier for this item")
    name: str = Field(..., description="Display name")
    metrics: Dict[str, float] = Field(..., description="Metrics for comparison")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        schema_extra = {
            "example": {
                "identifier": "encounter_12345",
                "name": "Heroic Raszageth - Pull #3",
                "metrics": {
                    "raid_dps": 2500000.0,
                    "combat_length": 245.7,
                    "deaths": 2
                },
                "metadata": {
                    "timestamp": "2023-10-15T20:30:00Z",
                    "success": False
                }
            }
        }


class ComparisonResponse(BaseModel):
    """Comparison data response."""

    comparison_type: str = Field(..., description="Type of comparison")
    baseline: ComparisonItem = Field(..., description="Baseline item for comparison")
    comparisons: List[ComparisonItem] = Field(..., description="Items being compared")
    metrics_analyzed: List[str] = Field(..., description="Metrics included in comparison")
    insights: Optional[List[str]] = Field(None, description="Automated insights from comparison")

    class Config:
        schema_extra = {
            "example": {
                "comparison_type": "encounter_attempts",
                "baseline": {
                    "identifier": "encounter_12345",
                    "name": "Heroic Raszageth - Best Pull",
                    "metrics": {"raid_dps": 2500000.0, "combat_length": 245.7, "deaths": 0}
                },
                "comparisons": [
                    {
                        "identifier": "encounter_12346",
                        "name": "Heroic Raszageth - Pull #2",
                        "metrics": {"raid_dps": 2300000.0, "combat_length": 180.5, "deaths": 3}
                    }
                ],
                "metrics_analyzed": ["raid_dps", "combat_length", "deaths"],
                "insights": ["DPS improved by 8.7% from previous attempt", "Survived 36% longer"]
            }
        }


class RankingEntry(BaseModel):
    """Single entry in a ranking list."""

    rank: int = Field(..., description="Rank position (1-based)", ge=1)
    identifier: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Display name")
    value: float = Field(..., description="Ranking metric value")
    percentile: Optional[float] = Field(None, description="Percentile ranking", ge=0, le=100)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional data")

    class Config:
        schema_extra = {
            "example": {
                "rank": 1,
                "identifier": "player_12345",
                "name": "Playername",
                "value": 125000.5,
                "percentile": 95.3,
                "metadata": {
                    "class_name": "Mage",
                    "spec_name": "Fire",
                    "item_level": 415
                }
            }
        }


class RankingResponse(BaseModel):
    """Ranking data response."""

    ranking_type: str = Field(..., description="Type of ranking")
    metric: str = Field(..., description="Metric being ranked")
    time_range: Optional[TimeRange] = Field(None, description="Time range for ranking")
    filters: Optional[Dict[str, Any]] = Field(None, description="Applied filters")
    entries: List[RankingEntry] = Field(..., description="Ranking entries")
    total_entries: int = Field(..., description="Total number of ranked entries")

    class Config:
        schema_extra = {
            "example": {
                "ranking_type": "character_dps",
                "metric": "average_dps",
                "time_range": {
                    "start": "2023-10-01T00:00:00Z",
                    "end": "2023-10-31T23:59:59Z"
                },
                "filters": {"difficulty": "HEROIC", "class_name": "Mage"},
                "entries": [
                    {
                        "rank": 1,
                        "identifier": "player_12345",
                        "name": "Playername",
                        "value": 125000.5,
                        "percentile": 95.3,
                        "metadata": {"spec_name": "Fire", "item_level": 415}
                    }
                ],
                "total_entries": 150
            }
        }


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    code: int = Field(..., description="HTTP status code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")

    class Config:
        schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid character name format",
                "code": 400,
                "details": {
                    "field": "character_name",
                    "provided": "invalid@name",
                    "expected": "Valid character name without special characters"
                },
                "timestamp": "2023-10-15T14:30:00Z",
                "request_id": "req_123456789"
            }
        }


class StatusResponse(BaseModel):
    """API status response."""

    status: str = Field(..., description="Overall status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Status timestamp")
    components: Dict[str, str] = Field(..., description="Component statuses")
    performance: Optional[Dict[str, float]] = Field(None, description="Performance metrics")

    class Config:
        schema_extra = {
            "example": {
                "status": "operational",
                "version": "1.0.0",
                "timestamp": "2023-10-15T14:30:00Z",
                "components": {
                    "database": "healthy",
                    "cache": "healthy",
                    "processing": "healthy"
                },
                "performance": {
                    "avg_response_time_ms": 45.3,
                    "requests_per_second": 125.7,
                    "error_rate_percent": 0.02
                }
            }
        }