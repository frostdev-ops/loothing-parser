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
                DATE(e.start_time) as date,
                AVG(cm.{}) as value,
                COUNT(DISTINCT cm.character_id) as sample_size
            FROM character_metrics cm
            JOIN encounters e ON cm.encounter_id = e.encounter_id
            WHERE DATE(e.start_time) BETWEEN ? AND ?
            GROUP BY DATE(e.start_time)
            ORDER BY date ASC
        """.format(
            db_column
        )

        cursor = db.execute(query, (start_date.date().isoformat(), end_date.date().isoformat()))
        results = cursor.fetchall()

        data_points = []
        values = []

        for row in results:
            data_point = {
                "date": row["date"],
                "value": row["value"] if row["value"] else 0,
                "sample_size": row["sample_size"],
            }
            data_points.append(data_point)
            if row["value"]:
                values.append(row["value"])

        # Calculate trend
        trend_direction = "stable"
        trend_strength = 0.0

        if len(values) >= 2:
            # Simple linear trend calculation
            first_half = values[: len(values) // 2]
            second_half = values[len(values) // 2 :]

            first_avg = statistics.mean(first_half) if first_half else 0
            second_avg = statistics.mean(second_half) if second_half else 0

            if second_avg > first_avg * 1.05:
                trend_direction = "up"
                trend_strength = (
                    min((second_avg - first_avg) / first_avg, 1.0) if first_avg > 0 else 0.5
                )
            elif second_avg < first_avg * 0.95:
                trend_direction = "down"
                trend_strength = (
                    min((first_avg - second_avg) / first_avg, 1.0) if first_avg > 0 else 0.5
                )
            else:
                trend_direction = "stable"
                trend_strength = 0.1

        return PerformanceTrend(
            metric_name=metric,
            time_range=TimeRange(
                start=start_date.isoformat() + "Z", end=end_date.isoformat() + "Z"
            ),
            data_points=data_points,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            statistical_significance=0.8 if len(values) >= 10 else 0.3,
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
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Get encounter progression data
        query = """
            SELECT
                e.id,
                e.name as boss_name,
                e.difficulty,
                e.start_time,
                e.kill as is_kill,
                e.duration,
                e.elapsed_time
            FROM encounters e
            WHERE e.start_time BETWEEN ? AND ?
            {}
            ORDER BY e.start_time DESC
        """.format(
            "AND e.guild_name = ?" if guild_name else ""
        )

        params = [start_date.isoformat(), end_date.isoformat()]
        if guild_name:
            params.append(guild_name)

        cursor = db.execute(query, tuple(params))
        results = cursor.fetchall()

        encounters_data = []
        first_kills = {}
        current_progress = {"heroic_bosses_killed": 0, "mythic_bosses_killed": 0}

        for row in results:
            boss_key = f"{row['boss_name']}_{row['difficulty']}"

            # Track first kills
            if row["is_kill"] and boss_key not in first_kills:
                first_kills[boss_key] = {
                    "boss_name": row["boss_name"],
                    "difficulty": row["difficulty"],
                    "first_kill": row["start_time"],
                    "attempts": 0,  # Will be calculated later
                }

                # Update current progress
                if row["difficulty"] == "HEROIC":
                    current_progress["heroic_bosses_killed"] += 1
                elif row["difficulty"] == "MYTHIC":
                    current_progress["mythic_bosses_killed"] += 1

        # Convert first kills to list
        encounters_list = list(first_kills.values())

        # Calculate progression rate (bosses killed per week)
        weeks = days / 7
        total_bosses_killed = len(first_kills)
        progression_rate = total_bosses_killed / weeks if weeks > 0 else 0

        return ProgressionTracking(
            guild_name=guild_name,
            time_range=TimeRange(
                start=start_date.isoformat() + "Z", end=end_date.isoformat() + "Z"
            ),
            encounters=encounters_list[:20],  # Limit to recent 20
            milestones=[],  # Could be populated with specific achievements
            current_progress=current_progress,
            progression_rate=progression_rate,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracking progression: {str(e)}")


@router.get("/analytics/class-balance", response_model=ClassBalance)
async def get_class_balance(
    encounter_type: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: DatabaseManager = Depends(),
):
    """Get class balance analysis."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Build query with filters
        query = """
            SELECT
                c.class_name,
                c.spec,
                COUNT(DISTINCT cm.encounter_id) as encounter_count,
                AVG(cm.damage_done) as avg_damage,
                AVG(cm.healing_done) as avg_healing,
                COUNT(DISTINCT c.character_id) as sample_size
            FROM characters c
            JOIN character_metrics cm ON c.character_id = cm.character_id
            JOIN encounters e ON cm.encounter_id = e.encounter_id
            WHERE e.start_time BETWEEN ? AND ?
            {}
            {}
            GROUP BY c.class_name, c.spec
            ORDER BY avg_damage DESC
        """.format(
            f"AND e.difficulty = ?" if difficulty else "",
            f"AND e.type = ?" if encounter_type else "",
        )

        params = [start_date.isoformat(), end_date.isoformat()]
        if difficulty:
            params.append(difficulty)
        if encounter_type:
            params.append(encounter_type)

        cursor = db.execute(query, tuple(params))
        results = cursor.fetchall()

        class_data = []
        all_damages = []

        for row in results:
            if row["avg_damage"]:
                all_damages.append(row["avg_damage"])

        overall_avg = statistics.mean(all_damages) if all_damages else 0

        for row in results:
            avg_damage = row["avg_damage"] if row["avg_damage"] else 0
            relative_perf = (avg_damage / overall_avg) if overall_avg > 0 else 1.0

            entry = ClassBalanceEntry(
                class_name=row["class_name"],
                spec_name=row["spec"],
                metric_values={
                    "dps": PerformanceMetric(
                        value=avg_damage,
                        percentile=0.0,  # Would need more complex calculation
                        rank=0,  # Would need ranking logic
                    )
                },
                relative_performance=relative_perf,
                sample_size=row["sample_size"],
            )
            class_data.append(entry)

        # Calculate balance score (lower standard deviation = better balance)
        if all_damages and len(all_damages) > 1:
            std_dev = statistics.stdev(all_damages)
            avg = statistics.mean(all_damages)
            cv = std_dev / avg if avg > 0 else 0  # Coefficient of variation
            balance_score = max(0, 1 - cv)  # Convert to 0-1 scale
        else:
            balance_score = 0.5

        # Find outliers (classes performing > 1.5 std dev from mean)
        outliers = []
        if all_damages and len(all_damages) > 2:
            std_dev = statistics.stdev(all_damages)
            mean_damage = statistics.mean(all_damages)

            for entry in class_data:
                if entry.metric_values["dps"].value > mean_damage + 1.5 * std_dev:
                    outliers.append(f"{entry.class_name} {entry.spec_name or ''}".strip())

        return ClassBalance(
            analysis_type="dps_balance",
            time_range=TimeRange(
                start=start_date.isoformat() + "Z", end=end_date.isoformat() + "Z"
            ),
            encounter_filters={"difficulty": difficulty, "type": encounter_type},
            class_data=class_data,
            balance_score=balance_score,
            outliers=outliers,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing class balance: {str(e)}")


@router.get("/analytics/spells", response_model=SpellUsageStats)
async def get_spell_usage_stats(
    class_name: Optional[str] = Query(None),
    character_name: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: DatabaseManager = Depends(),
):
    """Get spell usage statistics."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Query spell usage data
        query = """
            SELECT
                ss.spell_id,
                ss.spell_name,
                SUM(ss.cast_count) as total_casts,
                SUM(ss.total_damage) as total_damage,
                SUM(ss.total_healing) as total_healing,
                AVG(ss.crit_rate) as avg_crit_rate,
                COUNT(DISTINCT ss.encounter_id) as encounter_count
            FROM spell_summary ss
            JOIN characters c ON ss.character_id = c.id
            JOIN encounters e ON ss.encounter_id = e.id
            WHERE e.start_time BETWEEN ? AND ?
            {}
            {}
            GROUP BY ss.spell_id, ss.spell_name
            ORDER BY total_casts DESC
            LIMIT 50
        """.format(
            f"AND c.class_name = ?" if class_name else "",
            f"AND c.name = ?" if character_name else "",
        )

        params = [start_date.isoformat(), end_date.isoformat()]
        if class_name:
            params.append(class_name)
        if character_name:
            params.append(character_name)

        cursor = db.execute(query, tuple(params))
        results = cursor.fetchall()

        spell_entries = []
        most_used = []
        highest_damage = []
        total_casts = 0

        damage_spells = []

        for row in results:
            total_casts += row["total_casts"]

            entry = SpellUsageEntry(
                spell_id=row["spell_id"],
                spell_name=row["spell_name"],
                cast_count=row["total_casts"],
                total_damage=row["total_damage"] or 0,
                total_healing=row["total_healing"] or 0,
                crit_rate=row["avg_crit_rate"] or 0.0,
                usage_frequency=(row["total_casts"] / total_casts * 100) if total_casts > 0 else 0,
            )
            spell_entries.append(entry)

            if len(most_used) < 5:
                most_used.append(row["spell_name"])

            if row["total_damage"] and row["total_damage"] > 0:
                damage_spells.append((row["spell_name"], row["total_damage"]))

        # Sort damage spells and get top 5
        damage_spells.sort(key=lambda x: x[1], reverse=True)
        highest_damage = [spell[0] for spell in damage_spells[:5]]

        # Calculate diversity score (based on how evenly distributed spell usage is)
        if spell_entries:
            usage_counts = [e.cast_count for e in spell_entries]
            max_usage = max(usage_counts)
            min_usage = min(usage_counts)
            diversity_score = 1.0 - ((max_usage - min_usage) / max_usage) if max_usage > 0 else 0.5
        else:
            diversity_score = 0.5

        return SpellUsageStats(
            character_name=character_name,
            class_name=class_name,
            time_range=TimeRange(
                start=start_date.isoformat() + "Z", end=end_date.isoformat() + "Z"
            ),
            spell_entries=spell_entries,
            most_used_spells=most_used,
            highest_damage_spells=highest_damage,
            spell_diversity_score=diversity_score,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting spell usage stats: {str(e)}")


@router.get("/analytics/damage-breakdown", response_model=DamageBreakdown)
async def get_damage_breakdown(
    encounter_id: Optional[int] = Query(None),
    character_name: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: DatabaseManager = Depends(),
):
    """Get damage breakdown analysis."""
    try:
        # Build query based on filters
        if encounter_id:
            # Specific encounter breakdown
            query = """
                SELECT
                    ss.spell_name as source_name,
                    'spell' as source_type,
                    SUM(ss.total_damage) as total_damage,
                    SUM(ss.cast_count) as hit_count,
                    AVG(ss.crit_rate) as crit_rate
                FROM spell_summary ss
                JOIN characters c ON ss.character_id = c.id
                WHERE ss.encounter_id = ?
                {}
                GROUP BY ss.spell_name
                HAVING total_damage > 0
                ORDER BY total_damage DESC
            """.format(
                f"AND c.name = ?" if character_name else ""
            )

            params = [encounter_id]
            if character_name:
                params.append(character_name)
        else:
            # Time-range based breakdown
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            query = """
                SELECT
                    ss.spell_name as source_name,
                    'spell' as source_type,
                    SUM(ss.total_damage) as total_damage,
                    SUM(ss.cast_count) as hit_count,
                    AVG(ss.crit_rate) as crit_rate
                FROM spell_summary ss
                JOIN characters c ON ss.character_id = c.id
                JOIN encounters e ON ss.encounter_id = e.id
                WHERE e.start_time BETWEEN ? AND ?
                {}
                GROUP BY ss.spell_name
                HAVING total_damage > 0
                ORDER BY total_damage DESC
                LIMIT 30
            """.format(
                f"AND c.name = ?" if character_name else ""
            )

            params = [start_date.isoformat(), end_date.isoformat()]
            if character_name:
                params.append(character_name)

        cursor = db.execute(query, tuple(params))
        results = cursor.fetchall()

        damage_sources = []
        total_damage = 0
        top_3_damage = 0

        # Calculate total damage
        for row in results:
            if row["total_damage"]:
                total_damage += row["total_damage"]

        # Build damage sources
        for i, row in enumerate(results):
            damage = row["total_damage"] or 0
            hit_count = row["hit_count"] or 1

            source = DamageSource(
                source_type=row["source_type"],
                source_name=row["source_name"],
                total_damage=damage,
                percentage_of_total=(damage / total_damage * 100) if total_damage > 0 else 0,
                hit_count=hit_count,
                average_hit=damage / hit_count if hit_count > 0 else 0,
                crit_rate=row["crit_rate"] or 0.0,
            )
            damage_sources.append(source)

            if i < 3:
                top_3_damage += damage

        # Calculate damage distribution (simplified)
        damage_distribution = {
            "direct_damage": 70.0,  # Would need event parsing for accurate calculation
            "periodic_damage": 20.0,
            "pet_damage": 10.0,
        }

        time_range = None
        if not encounter_id:
            time_range = TimeRange(
                start=start_date.isoformat() + "Z", end=end_date.isoformat() + "Z"
            )

        return DamageBreakdown(
            encounter_id=encounter_id,
            character_name=character_name,
            time_range=time_range,
            damage_sources=damage_sources,
            total_damage=int(total_damage),
            top_damage_percentage=(top_3_damage / total_damage * 100) if total_damage > 0 else 0,
            damage_distribution=damage_distribution,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing damage breakdown: {str(e)}")
