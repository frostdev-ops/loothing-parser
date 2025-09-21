"""
Analytics-related API endpoints for v1.

Provides advanced analytics including performance trends, class balance,
spell usage statistics, and damage breakdown analysis.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Depends
import statistics
import json

from ..models.analytics import (
    PerformanceTrend,
    ProgressionTracking,
    ClassBalance,
    ClassBalanceEntry,
    SpellUsageStats,
    SpellUsageEntry,
    DamageBreakdown,
    DamageSource,
)
from ..models.common import TimeRange, PerformanceMetric
from src.database.schema import DatabaseManager

router = APIRouter()


@router.get("/analytics/trends/{metric}", response_model=PerformanceTrend)
async def get_performance_trends(
    metric: str, days: int = Query(30, ge=7, le=365), db: DatabaseManager = Depends()
):
    """Get performance trends for a specific metric over time."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Map metric names to database columns
        metric_mapping = {
            "average_dps": "damage_done",
            "average_hps": "healing_done",
            "deaths": "deaths",
            "casts": "total_casts",
        }

        if metric not in metric_mapping:
            raise HTTPException(status_code=400, detail=f"Invalid metric: {metric}")

        db_column = metric_mapping[metric]

        # Query daily averages for the metric
        query = """
            SELECT
                DATE(cm.timestamp) as date,
                AVG(CAST(json_extract(cm.metrics_data, '$.' || ?) AS FLOAT)) as value,
                COUNT(DISTINCT cm.character_id) as sample_size
            FROM character_metrics cm
            JOIN encounters e ON cm.encounter_id = e.id
            WHERE DATE(cm.timestamp) BETWEEN ? AND ?
            GROUP BY DATE(cm.timestamp)
            ORDER BY date ASC
        """

        cursor = db.execute(query, (db_column, start_date.date().isoformat(), end_date.date().isoformat()))
        results = cursor.fetchall()

        data_points = []
        values = []

        for row in results:
            data_point = {
                "date": row["date"],
                "value": row["value"] if row["value"] else 0,
                "sample_size": row["sample_size"]
            }
            data_points.append(data_point)
            if row["value"]:
                values.append(row["value"])

        # Calculate trend
        trend_direction = "stable"
        trend_strength = 0.0

        if len(values) >= 2:
            # Simple linear trend calculation
            first_half = values[:len(values)//2]
            second_half = values[len(values)//2:]

            first_avg = statistics.mean(first_half) if first_half else 0
            second_avg = statistics.mean(second_half) if second_half else 0

            if second_avg > first_avg * 1.05:
                trend_direction = "up"
                trend_strength = min((second_avg - first_avg) / first_avg, 1.0) if first_avg > 0 else 0.5
            elif second_avg < first_avg * 0.95:
                trend_direction = "down"
                trend_strength = min((first_avg - second_avg) / first_avg, 1.0) if first_avg > 0 else 0.5
            else:
                trend_direction = "stable"
                trend_strength = 0.1

        return PerformanceTrend(
            metric_name=metric,
            time_range=TimeRange(start=start_date.isoformat() + "Z", end=end_date.isoformat() + "Z"),
            data_points=data_points,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            statistical_significance=0.8 if len(values) >= 10 else 0.3
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating trends: {str(e)}")


@router.get("/analytics/progression", response_model=ProgressionTracking)
async def get_progression_tracking(
    guild_name: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: DatabaseManager = Depends(),
):
    """Get raid progression tracking data."""
    raise HTTPException(status_code=501, detail="Analytics endpoints not yet implemented")


@router.get("/analytics/class-balance", response_model=ClassBalance)
async def get_class_balance(
    encounter_type: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: DatabaseManager = Depends(),
):
    """Get class balance analysis."""
    raise HTTPException(status_code=501, detail="Analytics endpoints not yet implemented")


@router.get("/analytics/spells", response_model=SpellUsageStats)
async def get_spell_usage_stats(
    class_name: Optional[str] = Query(None),
    character_name: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: DatabaseManager = Depends(),
):
    """Get spell usage statistics."""
    raise HTTPException(status_code=501, detail="Analytics endpoints not yet implemented")


@router.get("/analytics/damage-breakdown", response_model=DamageBreakdown)
async def get_damage_breakdown(
    encounter_id: Optional[int] = Query(None),
    character_name: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: DatabaseManager = Depends(),
):
    """Get damage breakdown analysis."""
    raise HTTPException(status_code=501, detail="Analytics endpoints not yet implemented")
