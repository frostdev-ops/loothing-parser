"""
Encounter-related API endpoints for v1.

Provides comprehensive encounter analysis including detailed metrics,
replay functionality, timeline visualization, and comparison tools.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, Path, HTTPException, Depends

from ..models.encounters import (
    EncounterDetail,
    EncounterReplay,
    EncounterTimeline,
    EncounterComparison,
    DeathAnalysis,
    ResourceUsage,
)
from ..models.responses import PaginatedResponse, ComparisonResponse
from ..models.common import TimeRange, SortOrder
from src.database.schema import DatabaseManager
from src.database.query import QueryAPI

router = APIRouter()


@router.get("/encounters", response_model=PaginatedResponse[EncounterDetail])
async def list_encounters(
    limit: int = Query(20, ge=1, le=100, description="Number of encounters per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    encounter_type: Optional[str] = Query(
        None, description="Filter by encounter type (raid/mythic_plus)"
    ),
    boss_name: Optional[str] = Query(None, description="Filter by boss name"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    sort_by: str = Query("start_time", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    db: DatabaseManager = Depends(),
):
    """
    List encounters with comprehensive filtering and pagination.

    Returns a paginated list of encounter details including timing,
    participants, outcomes, and performance summaries.
    """
    try:
        query_api = QueryAPI(db)

        # Build filters
        filters = {}
        if encounter_type:
            filters["encounter_type"] = encounter_type
        if boss_name:
            filters["boss_name"] = boss_name
        if difficulty:
            filters["difficulty"] = difficulty
        if success is not None:
            filters["success"] = success
        if start_date:
            filters["start_date"] = start_date.timestamp()
        if end_date:
            filters["end_date"] = end_date.timestamp()

        # Get encounters with pagination
        encounters = query_api.get_encounters(
            limit=limit,
            offset=offset,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order.value,
        )

        # Get total count for pagination
        total_count = query_api.get_encounters_count(filters=filters)

        # Convert EncounterSummary to EncounterDetail
        encounter_details = []
        for enc in encounters:
            # Get character metrics for participants
            metrics = query_api.get_character_metrics(enc.encounter_id)
            participant_names = [m.character_name for m in metrics]

            # Calculate totals
            total_damage = sum(m.damage_done for m in metrics)
            total_healing = sum(m.healing_done for m in metrics)
            total_deaths = sum(m.death_count for m in metrics)

            detail = EncounterDetail(
                encounter_id=enc.encounter_id,
                encounter_type=enc.encounter_type,
                boss_name=enc.boss_name,
                difficulty=enc.difficulty or "",
                zone_name=enc.boss_name,  # Use boss_name as zone for now
                start_time=enc.start_time,
                end_time=enc.end_time,
                duration=enc.combat_length,
                combat_duration=enc.combat_length,
                success=enc.success,
                wipe_percentage=None,
                participants=participant_names,
                raid_size=enc.raid_size,
                total_damage=total_damage,
                total_healing=total_healing,
                total_deaths=total_deaths,
            )
            encounter_details.append(detail)

        # Calculate pagination metadata
        has_next = offset + limit < total_count
        has_previous = offset > 0
        page = (offset // limit) + 1
        total_pages = (total_count + limit - 1) // limit

        return PaginatedResponse(
            items=encounter_details,
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
        raise HTTPException(status_code=500, detail=f"Failed to retrieve encounters: {str(e)}")


@router.get("/encounters/{encounter_id}", response_model=EncounterDetail)
async def get_encounter_detail(
    encounter_id: int = Path(..., description="Encounter ID"), db: DatabaseManager = Depends()
):
    """
    Get detailed encounter information.

    Returns comprehensive encounter data including timing, participants,
    performance metrics, and outcome details.
    """
    try:
        query_api = QueryAPI(db)

        encounter = query_api.get_encounter_detail(encounter_id)

        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        return encounter

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve encounter: {str(e)}")


@router.get("/encounters/{encounter_id}/replay", response_model=EncounterReplay)
async def get_encounter_replay(
    encounter_id: int = Path(..., description="Encounter ID"), db: DatabaseManager = Depends()
):
    """
    Get encounter replay data for event-by-event analysis.

    Returns chronological event data that can be used to replay
    the encounter with detailed timeline markers.
    """
    try:
        query_api = QueryAPI(db)

        replay = query_api.get_encounter_replay(encounter_id)

        if not replay:
            raise HTTPException(
                status_code=404, detail=f"No replay data found for encounter {encounter_id}"
            )

        return replay

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve encounter replay: {str(e)}"
        )


@router.get("/encounters/{encounter_id}/timeline", response_model=EncounterTimeline)
async def get_encounter_timeline(
    encounter_id: int = Path(..., description="Encounter ID"), db: DatabaseManager = Depends()
):
    """
    Get encounter timeline visualization data.

    Returns structured timeline data including phases, damage/healing
    over time, resource usage, and key events for visualization.
    """
    try:
        query_api = QueryAPI(db)

        timeline = query_api.get_encounter_timeline(encounter_id)

        if not timeline:
            raise HTTPException(
                status_code=404, detail=f"No timeline data found for encounter {encounter_id}"
            )

        return timeline

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve encounter timeline: {str(e)}"
        )


@router.get("/encounters/{encounter_id}/deaths", response_model=DeathAnalysis)
async def get_encounter_deaths(
    encounter_id: int = Path(..., description="Encounter ID"), db: DatabaseManager = Depends()
):
    """
    Get detailed death analysis for an encounter.

    Returns comprehensive death data including causes, timing,
    avoidability analysis, and patterns.
    """
    try:
        query_api = QueryAPI(db)

        deaths = query_api.get_encounter_deaths(encounter_id)

        if not deaths:
            raise HTTPException(
                status_code=404, detail=f"No death data found for encounter {encounter_id}"
            )

        return deaths

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve encounter deaths: {str(e)}"
        )


@router.get("/encounters/{encounter_id}/resources", response_model=ResourceUsage)
async def get_encounter_resources(
    encounter_id: int = Path(..., description="Encounter ID"), db: DatabaseManager = Depends()
):
    """
    Get resource usage analysis for an encounter.

    Returns detailed analysis of mana, energy, cooldowns, and
    consumable usage throughout the encounter.
    """
    try:
        query_api = QueryAPI(db)

        resources = query_api.get_encounter_resources(encounter_id)

        if not resources:
            raise HTTPException(
                status_code=404, detail=f"No resource data found for encounter {encounter_id}"
            )

        return resources

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve encounter resources: {str(e)}"
        )


@router.post("/encounters/compare", response_model=EncounterComparison)
async def compare_encounters(
    encounter_ids: List[int] = Query(..., description="Encounter IDs to compare"),
    db: DatabaseManager = Depends(),
):
    """
    Compare multiple encounters for analysis.

    Returns detailed comparison showing performance differences,
    improvements, and trends across the specified encounters.
    """
    try:
        query_api = QueryAPI(db)

        if len(encounter_ids) < 2:
            raise HTTPException(
                status_code=400, detail="At least 2 encounters required for comparison"
            )

        comparison = query_api.compare_encounters(encounter_ids)

        if not comparison:
            raise HTTPException(
                status_code=404, detail="Unable to generate comparison for the specified encounters"
            )

        return comparison

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare encounters: {str(e)}")


@router.get("/encounters/{encounter_id}/participants")
async def get_encounter_participants(
    encounter_id: int = Path(..., description="Encounter ID"), db: DatabaseManager = Depends()
):
    """
    Get list of participants for an encounter.

    Returns detailed participant information including roles,
    performance metrics, and participation status.
    """
    try:
        query_api = QueryAPI(db)

        participants = query_api.get_encounter_participants(encounter_id)

        if not participants:
            raise HTTPException(
                status_code=404, detail=f"No participants found for encounter {encounter_id}"
            )

        return {"encounter_id": encounter_id, "participants": participants}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve encounter participants: {str(e)}"
        )


@router.get("/encounters/{encounter_id}/summary")
async def get_encounter_summary(
    encounter_id: int = Path(..., description="Encounter ID"), db: DatabaseManager = Depends()
):
    """
    Get encounter performance summary.

    Returns high-level performance metrics and key statistics
    for quick encounter assessment.
    """
    try:
        query_api = QueryAPI(db)

        summary = query_api.get_encounter_summary(encounter_id)

        if not summary:
            raise HTTPException(
                status_code=404, detail=f"No summary data found for encounter {encounter_id}"
            )

        return summary

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve encounter summary: {str(e)}"
        )
