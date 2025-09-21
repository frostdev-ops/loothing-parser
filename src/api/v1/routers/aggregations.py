"""
Advanced aggregation endpoints for v1 API.

Provides complex query capabilities including custom metrics, percentiles,
cross-encounter comparisons, and composite performance indices.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field

from ..models.responses import PaginatedResponse, TimeSeriesResponse
from ..models.common import TimeRange, FilterCriteria
from src.database.schema import DatabaseManager
from src.database.query import QueryAPI
from ..dependencies import require_read_permission

router = APIRouter()


class AggregationRequest(BaseModel):
    """Request model for custom aggregations."""

    metrics: List[str] = Field(..., description="Metrics to aggregate")
    group_by: List[str] = Field(default=[], description="Fields to group by")
    filters: Dict[str, Any] = Field(default={}, description="Filter criteria")
    time_range: Optional[TimeRange] = Field(None, description="Time range filter")
    aggregation_functions: List[str] = Field(
        default=["avg", "min", "max", "count"],
        description="Aggregation functions to apply",
    )
    percentiles: List[float] = Field(
        default=[50, 75, 90, 95, 99], description="Percentiles to calculate"
    )
    include_samples: bool = Field(default=False, description="Include raw sample data")


class PercentileData(BaseModel):
    """Percentile calculation results."""

    metric: str
    percentiles: Dict[str, float]
    sample_size: int
    min_value: float
    max_value: float
    mean: float
    std_dev: float
    distribution: Optional[Dict[str, int]] = None


class CompositeMetric(BaseModel):
    """Composite performance metric calculation."""

    name: str
    value: float
    components: Dict[str, float]
    weight_distribution: Dict[str, float]
    confidence_score: float
    rank_percentile: Optional[float] = None


class ComparisonResult(BaseModel):
    """Cross-encounter comparison result."""

    encounter_type_a: str
    encounter_type_b: str
    metric: str
    difference_percentage: float
    statistical_significance: float
    sample_sizes: Dict[str, int]
    confidence_interval: List[float]


@router.post("/aggregations/custom", response_model=Dict[str, Any])
async def custom_aggregation(
    request: AggregationRequest,
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
):
    """
    Perform custom aggregation with flexible grouping and functions.

    Supports complex multi-dimensional aggregations with custom filters,
    grouping, and aggregation functions.
    """
    try:
        query_api = QueryAPI(db)

        # Validate metrics
        valid_metrics = [
            "dps",
            "hps",
            "dtps",
            "damage_done",
            "healing_done",
            "damage_taken",
            "deaths",
            "activity_percentage",
            "duration",
        ]
        invalid_metrics = [m for m in request.metrics if m not in valid_metrics]
        if invalid_metrics:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid metrics: {invalid_metrics}. Valid metrics: {valid_metrics}",
            )

        # Build aggregation query
        aggregation_result = await query_api.execute_custom_aggregation(
            metrics=request.metrics,
            group_by=request.group_by,
            filters=request.filters,
            time_range=request.time_range,
            aggregation_functions=request.aggregation_functions,
            percentiles=request.percentiles,
            include_samples=request.include_samples,
        )

        return {
            "data": aggregation_result,
            "metadata": {
                "total_rows": len(aggregation_result),
                "metrics": request.metrics,
                "group_by": request.group_by,
                "functions": request.aggregation_functions,
                "generated_at": datetime.utcnow(),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Aggregation failed: {str(e)}")


@router.get("/aggregations/percentiles/{metric}")
async def get_percentiles(
    metric: str,
    character_name: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    encounter_type: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    percentiles: str = Query("50,75,90,95,99", description="Comma-separated percentiles"),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> PercentileData:
    """
    Calculate percentiles for a specific metric with filtering.

    Provides detailed statistical analysis including distribution data
    and confidence intervals.
    """
    try:
        query_api = QueryAPI(db)

        # Parse percentiles
        percentile_list = [float(p.strip()) for p in percentiles.split(",")]
        if any(p < 0 or p > 100 for p in percentile_list):
            raise HTTPException(status_code=400, detail="Percentiles must be between 0 and 100")

        # Build filters
        filters = {"days": days}
        if character_name:
            filters["character_name"] = character_name
        if class_name:
            filters["class_name"] = class_name
        if encounter_type:
            filters["encounter_type"] = encounter_type
        if difficulty:
            filters["difficulty"] = difficulty

        # Calculate percentiles
        percentile_data = await query_api.calculate_percentiles(
            metric=metric, percentiles=percentile_list, filters=filters
        )

        return PercentileData(
            metric=metric,
            percentiles=percentile_data["percentiles"],
            sample_size=percentile_data["sample_size"],
            min_value=percentile_data["min_value"],
            max_value=percentile_data["max_value"],
            mean=percentile_data["mean"],
            std_dev=percentile_data["std_dev"],
            distribution=percentile_data.get("distribution"),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Percentile calculation failed: {str(e)}")


@router.get("/aggregations/moving-averages/{metric}")
async def get_moving_averages(
    metric: str,
    window_size: int = Query(7, ge=1, le=30, description="Window size in days"),
    character_name: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    encounter_type: Optional[str] = Query(None),
    days: int = Query(90, ge=7, le=365),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> TimeSeriesResponse:
    """
    Calculate moving averages for performance tracking.

    Provides smoothed trend analysis with configurable window sizes
    for performance monitoring and improvement tracking.
    """
    try:
        query_api = QueryAPI(db)

        # Build filters
        filters = {"days": days}
        if character_name:
            filters["character_name"] = character_name
        if class_name:
            filters["class_name"] = class_name
        if encounter_type:
            filters["encounter_type"] = encounter_type

        # Calculate moving averages
        moving_avg_data = await query_api.calculate_moving_averages(
            metric=metric, window_size=window_size, filters=filters
        )

        return TimeSeriesResponse(
            metric=metric,
            data_points=moving_avg_data["data_points"],
            summary={
                "window_size": window_size,
                "total_points": len(moving_avg_data["data_points"]),
                "trend_direction": moving_avg_data.get("trend_direction"),
                "volatility": moving_avg_data.get("volatility"),
            },
            generated_at=datetime.utcnow(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Moving average calculation failed: {str(e)}")


@router.post("/aggregations/composite-metrics")
async def calculate_composite_metrics(
    character_names: List[str] = Body(..., description="Characters to analyze"),
    weight_config: Dict[str, float] = Body(
        default={
            "dps": 0.4,
            "hps": 0.3,
            "survivability": 0.2,
            "activity": 0.1,
        },
        description="Metric weights for composite score",
    ),
    encounter_type: Optional[str] = Body(None),
    difficulty: Optional[str] = Body(None),
    days: int = Body(30, ge=1, le=365),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> List[CompositeMetric]:
    """
    Calculate composite performance metrics for characters.

    Combines multiple performance indicators into weighted composite scores
    for holistic performance evaluation and ranking.
    """
    try:
        query_api = QueryAPI(db)

        # Validate weight configuration
        if abs(sum(weight_config.values()) - 1.0) > 0.01:
            raise HTTPException(status_code=400, detail="Weights must sum to 1.0")

        # Build filters
        filters = {"days": days}
        if encounter_type:
            filters["encounter_type"] = encounter_type
        if difficulty:
            filters["difficulty"] = difficulty

        # Calculate composite metrics for each character
        composite_results = []
        for character_name in character_names:
            character_filters = {**filters, "character_name": character_name}

            composite_data = await query_api.calculate_composite_metric(
                weight_config=weight_config, filters=character_filters
            )

            if composite_data:
                composite_results.append(
                    CompositeMetric(
                        name=character_name,
                        value=composite_data["composite_score"],
                        components=composite_data["component_scores"],
                        weight_distribution=weight_config,
                        confidence_score=composite_data["confidence_score"],
                        rank_percentile=composite_data.get("rank_percentile"),
                    )
                )

        # Sort by composite score descending
        composite_results.sort(key=lambda x: x.value, reverse=True)

        return composite_results

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Composite metric calculation failed: {str(e)}"
        )


@router.get("/aggregations/cross-encounter-comparison")
async def cross_encounter_comparison(
    encounter_type_a: str = Query(..., description="First encounter type"),
    encounter_type_b: str = Query(..., description="Second encounter type"),
    metric: str = Query(..., description="Metric to compare"),
    character_name: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> ComparisonResult:
    """
    Compare performance metrics across different encounter types.

    Provides statistical comparison with significance testing to identify
    meaningful performance differences between encounters.
    """
    try:
        query_api = QueryAPI(db)

        # Build base filters
        base_filters = {"days": days}
        if character_name:
            base_filters["character_name"] = character_name
        if class_name:
            base_filters["class_name"] = class_name
        if difficulty:
            base_filters["difficulty"] = difficulty

        # Get data for both encounter types
        filters_a = {**base_filters, "encounter_type": encounter_type_a}
        filters_b = {**base_filters, "encounter_type": encounter_type_b}

        comparison_data = await query_api.compare_encounter_performance(
            metric=metric, filters_a=filters_a, filters_b=filters_b
        )

        return ComparisonResult(
            encounter_type_a=encounter_type_a,
            encounter_type_b=encounter_type_b,
            metric=metric,
            difference_percentage=comparison_data["difference_percentage"],
            statistical_significance=comparison_data["p_value"],
            sample_sizes={
                encounter_type_a: comparison_data["sample_size_a"],
                encounter_type_b: comparison_data["sample_size_b"],
            },
            confidence_interval=comparison_data["confidence_interval"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cross-encounter comparison failed: {str(e)}")


@router.get("/aggregations/bracket-analysis/{metric}")
async def bracket_analysis(
    metric: str,
    bracket_count: int = Query(10, ge=3, le=20, description="Number of brackets"),
    character_name: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    encounter_type: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> Dict[str, Any]:
    """
    Analyze performance distribution across performance brackets.

    Divides players into performance brackets and analyzes characteristics
    of each bracket for competitive insights.
    """
    try:
        query_api = QueryAPI(db)

        # Build filters
        filters = {"days": days}
        if character_name:
            filters["character_name"] = character_name
        if class_name:
            filters["class_name"] = class_name
        if encounter_type:
            filters["encounter_type"] = encounter_type
        if difficulty:
            filters["difficulty"] = difficulty

        # Perform bracket analysis
        bracket_data = await query_api.analyze_performance_brackets(
            metric=metric, bracket_count=bracket_count, filters=filters
        )

        return {
            "metric": metric,
            "bracket_count": bracket_count,
            "brackets": bracket_data["brackets"],
            "summary": {
                "total_players": bracket_data["total_players"],
                "range_min": bracket_data["range_min"],
                "range_max": bracket_data["range_max"],
                "bracket_size": bracket_data["bracket_size"],
            },
            "metadata": {
                "filters": filters,
                "generated_at": datetime.utcnow(),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bracket analysis failed: {str(e)}")


@router.get("/aggregations/correlation-analysis")
async def correlation_analysis(
    primary_metric: str = Query(..., description="Primary metric to analyze"),
    secondary_metrics: str = Query(..., description="Comma-separated list of metrics to correlate"),
    character_name: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    encounter_type: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> Dict[str, Any]:
    """
    Analyze correlations between different performance metrics.

    Identifies relationships between metrics to understand performance
    dependencies and optimization opportunities.
    """
    try:
        query_api = QueryAPI(db)

        # Parse secondary metrics
        secondary_metric_list = [m.strip() for m in secondary_metrics.split(",")]

        # Build filters
        filters = {"days": days}
        if character_name:
            filters["character_name"] = character_name
        if class_name:
            filters["class_name"] = class_name
        if encounter_type:
            filters["encounter_type"] = encounter_type

        # Calculate correlations
        correlation_data = await query_api.calculate_metric_correlations(
            primary_metric=primary_metric,
            secondary_metrics=secondary_metric_list,
            filters=filters,
        )

        return {
            "primary_metric": primary_metric,
            "correlations": correlation_data["correlations"],
            "sample_size": correlation_data["sample_size"],
            "significance_levels": correlation_data["significance_levels"],
            "metadata": {
                "filters": filters,
                "generated_at": datetime.utcnow(),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Correlation analysis failed: {str(e)}")
