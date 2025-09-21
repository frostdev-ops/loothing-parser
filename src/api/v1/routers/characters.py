"""
Character-related API endpoints for v1.

Provides comprehensive character analysis including profiles, performance metrics,
history tracking, rankings, gear analysis, and talent optimization.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, Path, HTTPException, Depends
from fastapi.responses import JSONResponse

from ..models.characters import (
    CharacterProfile,
    CharacterPerformance,
    CharacterHistory,
    CharacterRanking,
    CharacterGear,
    CharacterTalents,
)
from ..models.responses import PaginatedResponse, TimeSeriesResponse, RankingResponse
from ..models.common import TimeRange, SortOrder
from src.database.schema import DatabaseManager
from src.database.query import QueryAPI

router = APIRouter()


@router.get("/characters", response_model=PaginatedResponse[CharacterProfile])
async def list_characters(
    limit: int = Query(20, ge=1, le=100, description="Number of characters per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    server: Optional[str] = Query(None, description="Filter by server name"),
    region: Optional[str] = Query(None, description="Filter by region"),
    class_name: Optional[str] = Query(None, description="Filter by class name"),
    min_encounters: Optional[int] = Query(None, ge=0, description="Minimum encounter count"),
    active_since: Optional[datetime] = Query(None, description="Active since date"),
    sort_by: str = Query(
        "last_seen", description="Sort field (last_seen, total_encounters, average_dps)"
    ),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    db: DatabaseManager = Depends(),
):
    """
    List all characters with optional filtering and pagination.

    Returns a paginated list of character profiles with summary information.
    Supports filtering by server, region, class, activity level, and more.
    """
    try:
        query_api = QueryAPI(db)

        # Build filters
        filters = {}
        if server:
            filters["server"] = server
        if region:
            filters["region"] = region
        if class_name:
            filters["class_name"] = class_name
        if min_encounters:
            filters["min_encounters"] = min_encounters
        if active_since:
            filters["active_since"] = active_since.timestamp()

        # Get characters with pagination
        characters = query_api.get_characters(
            limit=limit,
            offset=offset,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order.value,
        )

        # Get total count for pagination
        total_count = query_api.get_characters_count(filters=filters)

        # Calculate pagination metadata
        has_next = offset + limit < total_count
        has_previous = offset > 0
        page = (offset // limit) + 1
        total_pages = (total_count + limit - 1) // limit

        return PaginatedResponse(
            items=characters,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_next": has_next,
                "has_previous": has_previous,
                "page": page,
                "total_pages": total_pages,
            },
            filters=filters,
            sort={sort_by: sort_order.value},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve characters: {str(e)}")


@router.get("/characters/{character_name}", response_model=CharacterProfile)
async def get_character_profile(
    character_name: str = Path(..., description="Character name"),
    server: Optional[str] = Query(None, description="Server name for disambiguation"),
    db: DatabaseManager = Depends(),
):
    """
    Get detailed character profile information.

    Returns comprehensive character data including class, server, activity statistics,
    lifetime performance metrics, and recent activity summary.
    """
    try:
        query_api = QueryAPI(db)

        character = query_api.get_character_profile(character_name=character_name, server=server)

        if not character:
            raise HTTPException(status_code=404, detail=f"Character '{character_name}' not found")

        return character

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve character profile: {str(e)}"
        )


@router.get("/characters/{character_name}/performance", response_model=CharacterPerformance)
async def get_character_performance(
    character_name: str = Path(..., description="Character name"),
    encounter_id: Optional[int] = Query(None, description="Specific encounter ID"),
    start_date: Optional[datetime] = Query(None, description="Start date for time range"),
    end_date: Optional[datetime] = Query(None, description="End date for time range"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    encounter_type: Optional[str] = Query(None, description="Filter by encounter type"),
    db: DatabaseManager = Depends(),
):
    """
    Get character performance metrics for specific encounter or time period.

    Returns detailed performance analysis including DPS/HPS metrics, survival stats,
    activity percentages, and percentile rankings compared to other players.
    """
    try:
        query_api = QueryAPI(db)

        # Build time range if dates provided
        time_range = None
        if start_date and end_date:
            time_range = TimeRange(start=start_date, end=end_date)
        elif not encounter_id:
            # Default to last 30 days if no specific criteria
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)
            time_range = TimeRange(start=start_date, end=end_date)

        performance = query_api.get_character_performance(
            character_name=character_name,
            encounter_id=encounter_id,
            time_range=time_range,
            difficulty=difficulty,
            encounter_type=encounter_type,
        )

        if not performance:
            raise HTTPException(
                status_code=404,
                detail=f"No performance data found for character '{character_name}'",
            )

        return performance

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve character performance: {str(e)}"
        )


@router.get("/characters/{character_name}/history", response_model=CharacterHistory)
async def get_character_history(
    character_name: str = Path(..., description="Character name"),
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    encounter_type: Optional[str] = Query(None, description="Filter by encounter type"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of history entries"),
    db: DatabaseManager = Depends(),
):
    """
    Get character performance history over time.

    Returns chronological performance data showing progression, improvements,
    and consistency over the specified time period.
    """
    try:
        query_api = QueryAPI(db)

        # Calculate time range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        time_range = TimeRange(start=start_date, end=end_date)

        history = query_api.get_character_history(
            character_name=character_name,
            time_range=time_range,
            encounter_type=encounter_type,
            difficulty=difficulty,
            limit=limit,
        )

        if not history:
            raise HTTPException(
                status_code=404, detail=f"No history data found for character '{character_name}'"
            )

        return history

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve character history: {str(e)}"
        )


@router.get("/characters/{character_name}/rankings", response_model=List[CharacterRanking])
async def get_character_rankings(
    character_name: str = Path(..., description="Character name"),
    metrics: List[str] = Query(
        ["dps", "hps"], description="Metrics to rank (dps, hps, damage_done, etc.)"
    ),
    encounter_type: Optional[str] = Query(None, description="Filter by encounter type"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    days: int = Query(30, ge=1, le=365, description="Number of days to consider"),
    db: DatabaseManager = Depends(),
):
    """
    Get character rankings across different metrics.

    Returns percentile rankings and absolute positions for the character
    compared to all other players in the specified time period and filters.
    """
    try:
        query_api = QueryAPI(db)

        # Calculate time range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        time_range = TimeRange(start=start_date, end=end_date)

        rankings = []
        for metric in metrics:
            ranking = query_api.get_character_ranking(
                character_name=character_name,
                metric=metric,
                time_range=time_range,
                encounter_type=encounter_type,
                difficulty=difficulty,
            )
            if ranking:
                rankings.append(ranking)

        return rankings

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve character rankings: {str(e)}"
        )


@router.get("/characters/{character_name}/gear", response_model=CharacterGear)
async def get_character_gear(
    character_name: str = Path(..., description="Character name"),
    encounter_id: Optional[int] = Query(
        None, description="Specific encounter ID for gear snapshot"
    ),
    db: DatabaseManager = Depends(),
):
    """
    Get character gear analysis and optimization suggestions.

    Returns equipped items, enchants, gems, set bonuses, and optimization
    recommendations based on current and optimal gear configurations.
    """
    try:
        query_api = QueryAPI(db)

        gear = query_api.get_character_gear(
            character_name=character_name, encounter_id=encounter_id
        )

        if not gear:
            raise HTTPException(
                status_code=404, detail=f"No gear data found for character '{character_name}'"
            )

        return gear

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve character gear: {str(e)}")


@router.get("/characters/{character_name}/talents", response_model=CharacterTalents)
async def get_character_talents(
    character_name: str = Path(..., description="Character name"),
    encounter_id: Optional[int] = Query(
        None, description="Specific encounter ID for talent snapshot"
    ),
    db: DatabaseManager = Depends(),
):
    """
    Get character talent analysis and optimization suggestions.

    Returns current talent selections, alternative options, and recommendations
    for optimization based on encounter type and performance data.
    """
    try:
        query_api = QueryAPI(db)

        talents = query_api.get_character_talents(
            character_name=character_name, encounter_id=encounter_id
        )

        if not talents:
            raise HTTPException(
                status_code=404, detail=f"No talent data found for character '{character_name}'"
            )

        return talents

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve character talents: {str(e)}"
        )


@router.get("/characters/{character_name}/trends", response_model=TimeSeriesResponse)
async def get_character_trends(
    character_name: str = Path(..., description="Character name"),
    metric: str = Query("dps", description="Metric to trend (dps, hps, survival_rate, etc.)"),
    days: int = Query(30, ge=7, le=365, description="Number of days to analyze"),
    interval: str = Query("1d", description="Data point interval (1h, 1d, 1w)"),
    encounter_type: Optional[str] = Query(None, description="Filter by encounter type"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    db: DatabaseManager = Depends(),
):
    """
    Get character performance trends over time.

    Returns time series data showing how the character's performance in the
    specified metric has changed over the given time period.
    """
    try:
        query_api = QueryAPI(db)

        # Calculate time range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        time_range = TimeRange(start=start_date, end=end_date)

        trends = query_api.get_character_trends(
            character_name=character_name,
            metric=metric,
            time_range=time_range,
            interval=interval,
            encounter_type=encounter_type,
            difficulty=difficulty,
        )

        if not trends:
            raise HTTPException(
                status_code=404, detail=f"No trend data found for character '{character_name}'"
            )

        return trends

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve character trends: {str(e)}"
        )


@router.post("/characters/{character_name}/compare")
async def compare_characters(
    character_name: str = Path(..., description="Base character name"),
    compare_with: List[str] = Query(..., description="Character names to compare with"),
    metric: str = Query("dps", description="Primary metric for comparison"),
    encounter_id: Optional[int] = Query(None, description="Specific encounter for comparison"),
    days: int = Query(30, ge=1, le=365, description="Time period for comparison"),
    db: DatabaseManager = Depends(),
):
    """
    Compare character performance with other characters.

    Returns detailed comparison showing relative performance, strengths,
    weaknesses, and statistical analysis across multiple characters.
    """
    try:
        query_api = QueryAPI(db)

        # Calculate time range if no specific encounter
        time_range = None
        if not encounter_id:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            time_range = TimeRange(start=start_date, end=end_date)

        comparison = query_api.compare_characters(
            base_character=character_name,
            compare_characters=compare_with,
            metric=metric,
            encounter_id=encounter_id,
            time_range=time_range,
        )

        return comparison

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare characters: {str(e)}")
