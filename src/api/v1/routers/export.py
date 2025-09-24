"""
Data export API endpoints for v1.

Provides endpoints for exporting data in various formats including
Warcraft Logs format, CSV, JSON, and integration with external services.
"""

import json
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from fastapi.responses import StreamingResponse, JSONResponse

from src.database.schema import DatabaseManager
from src.database.query import QueryAPI

router = APIRouter()


@router.get("/export/encounters/{encounter_id}")
async def export_encounter(
    encounter_id: int = Path(..., description="Encounter ID to export"),
    format: str = Query("json", regex="^(json|csv|wcl)$", description="Export format"),
    decompress_events: bool = Query(False, description="Include decompressed event data (JSON only)"),
    guild_id: Optional[int] = Query(None, description="Guild ID for multi-tenant filtering"),
    db: DatabaseManager = Depends(),
):
    """
    Export encounter data in specified format.

    Formats:
    - json: Full hierarchical JSON with encounter, metrics, and optionally events
    - csv: Flattened CSV format with character metrics
    - wcl: Basic Warcraft Logs compatible format
    """
    try:
        query_api = QueryAPI(db)

        # Get full encounter data
        encounter_data = query_api.export_encounter_data(
            encounter_id=encounter_id,
            guild_id=guild_id,
            decompress_events=(decompress_events and format == "json"),
        )

        if not encounter_data:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        if format == "json":
            # Return as JSON response
            return JSONResponse(
                content=encounter_data,
                headers={
                    "Content-Disposition": f"attachment; filename=encounter_{encounter_id}.json"
                }
            )

        elif format == "csv":
            # Convert to CSV format
            output = io.StringIO()

            # Create CSV with character metrics
            if encounter_data["character_metrics"]:
                fieldnames = list(encounter_data["character_metrics"][0].keys())
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(encounter_data["character_metrics"])

            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=encounter_{encounter_id}.csv"
                }
            )

        elif format == "wcl":
            # Basic Warcraft Logs format
            wcl_data = {
                "version": 1,
                "reportInfo": {
                    "gameVersion": "10.2.5",
                    "lang": "en",
                },
                "fights": [{
                    "id": encounter_data["encounter"]["encounter_id"],
                    "boss": encounter_data["encounter"]["boss_name"],
                    "difficulty": encounter_data["encounter"]["difficulty"] or "Normal",
                    "kill": encounter_data["encounter"]["success"],
                    "start_time": encounter_data["encounter"]["start_time"],
                    "end_time": encounter_data["encounter"]["end_time"],
                    "size": encounter_data["encounter"]["raid_size"],
                }],
                "friendlies": [
                    {
                        "name": m["character_name"],
                        "id": idx + 1,
                        "guid": m["character_guid"],
                        "type": m["class_name"] or "Unknown",
                        "fights": [{
                            "id": encounter_data["encounter"]["encounter_id"],
                            "damage": m["damage_done"],
                            "healing": m["healing_done"],
                            "damageTaken": m["damage_taken"],
                            "deathEvents": m["death_count"],
                        }],
                    }
                    for idx, m in enumerate(encounter_data["character_metrics"])
                ],
                "title": f"Combat Log - {encounter_data['encounter']['boss_name']}",
                "zone": encounter_data["encounter"]["boss_name"],
            }

            return JSONResponse(
                content=wcl_data,
                headers={
                    "Content-Disposition": f"attachment; filename=encounter_{encounter_id}_wcl.json"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export encounter: {str(e)}")


@router.get("/export/character/{character_name}")
async def export_character_data(
    character_name: str = Path(..., description="Character name to export"),
    format: str = Query("json", regex="^(json|csv|wcl)$", description="Export format"),
    days: int = Query(30, ge=1, le=365, description="Days of history to export"),
    guild_id: Optional[int] = Query(None, description="Guild ID for multi-tenant filtering"),
    db: DatabaseManager = Depends(),
):
    """
    Export character performance data.

    Returns historical performance metrics for the character
    over the specified time period in the requested format.
    """
    try:
        query_api = QueryAPI(db)

        # Calculate time range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Get character metrics across encounters
        query = """
            SELECT
                e.encounter_id,
                e.boss_name,
                e.difficulty,
                e.encounter_type,
                e.start_time,
                e.success,
                e.combat_length,
                cm.damage_done,
                cm.healing_done,
                cm.damage_taken,
                cm.death_count,
                cm.dps,
                cm.hps,
                cm.activity_percentage,
                cm.combat_dps,
                cm.combat_hps
            FROM character_metrics cm
            JOIN encounters e ON cm.encounter_id = e.encounter_id
            JOIN characters c ON cm.character_id = c.character_id
            WHERE c.character_name = ?
            AND e.start_time BETWEEN ? AND ?
        """
        params = [character_name, start_date.timestamp(), end_date.timestamp()]

        if guild_id is not None:
            query += " AND e.guild_id = ? AND c.guild_id = ?"
            params.extend([guild_id, guild_id])

        query += " ORDER BY e.start_time DESC"

        cursor = db.execute(query, params)

        performance_data = []
        for row in cursor:
            performance_data.append({
                "encounter_id": row[0],
                "boss_name": row[1],
                "difficulty": row[2],
                "encounter_type": row[3],
                "date": datetime.fromtimestamp(row[4]).isoformat() if row[4] else None,
                "success": bool(row[5]),
                "duration": row[6],
                "damage_done": row[7],
                "healing_done": row[8],
                "damage_taken": row[9],
                "deaths": row[10],
                "dps": row[11],
                "hps": row[12],
                "activity": row[13],
                "combat_dps": row[14],
                "combat_hps": row[15],
            })

        if not performance_data:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for character '{character_name}' in the last {days} days"
            )

        # Get character info
        cursor = db.execute(
            """
            SELECT character_name, server, region, class_name, spec_name
            FROM characters
            WHERE character_name = ?
            """,
            (character_name,)
        )
        char_info = cursor.fetchone()

        export_data = {
            "character": {
                "name": char_info[0] if char_info else character_name,
                "server": char_info[1] if char_info else "Unknown",
                "region": char_info[2] if char_info else "US",
                "class": char_info[3] if char_info else "Unknown",
                "spec": char_info[4] if char_info else "Unknown",
            },
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days,
            },
            "performance": performance_data,
            "statistics": {
                "total_encounters": len(performance_data),
                "success_rate": sum(1 for p in performance_data if p["success"]) / len(performance_data) * 100,
                "average_dps": sum(p["dps"] for p in performance_data) / len(performance_data),
                "average_hps": sum(p["hps"] for p in performance_data) / len(performance_data),
                "total_deaths": sum(p["deaths"] for p in performance_data),
            }
        }

        if format == "json":
            return JSONResponse(
                content=export_data,
                headers={
                    "Content-Disposition": f"attachment; filename={character_name}_performance.json"
                }
            )

        elif format == "csv":
            output = io.StringIO()

            if performance_data:
                fieldnames = list(performance_data[0].keys())
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(performance_data)

            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={character_name}_performance.csv"
                }
            )

        elif format == "wcl":
            # Basic WCL format for character
            wcl_data = {
                "character": export_data["character"],
                "rankings": [
                    {
                        "encounter": p["boss_name"],
                        "difficulty": p["difficulty"],
                        "spec": export_data["character"]["spec"],
                        "dps": p["dps"],
                        "percentile": 50,  # Would need actual percentile calculation
                        "kill": p["success"],
                        "date": p["date"],
                    }
                    for p in performance_data[:20]  # Limit to recent 20
                ],
            }

            return JSONResponse(
                content=wcl_data,
                headers={
                    "Content-Disposition": f"attachment; filename={character_name}_wcl.json"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export character data: {str(e)}")


@router.get("/export/wcl")
async def export_warcraft_logs_format(
    encounter_id: Optional[int] = Query(None, description="Specific encounter to export"),
    character_name: Optional[str] = Query(None, description="Specific character to export"),
    guild_id: Optional[int] = Query(None, description="Guild ID for filtering"),
    days: int = Query(7, ge=1, le=30, description="Days of data to export"),
    db: DatabaseManager = Depends(),
):
    """
    Export data in Warcraft Logs compatible format.

    This provides a basic WCL-compatible JSON structure that can be
    used for external analysis or import into WCL-compatible tools.
    """
    try:
        query_api = QueryAPI(db)

        if encounter_id:
            # Export specific encounter in WCL format
            return await export_encounter(
                encounter_id=encounter_id,
                format="wcl",
                decompress_events=False,
                guild_id=guild_id,
                db=db
            )

        elif character_name:
            # Export character data in WCL format
            return await export_character_data(
                character_name=character_name,
                format="wcl",
                days=days,
                guild_id=guild_id,
                db=db
            )

        else:
            # Export recent encounters in WCL format
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            query = """
                SELECT
                    e.encounter_id,
                    e.boss_name,
                    e.difficulty,
                    e.start_time,
                    e.end_time,
                    e.success,
                    e.raid_size,
                    COUNT(DISTINCT cm.character_id) as player_count
                FROM combat_encounters e
                LEFT JOIN character_metrics cm ON e.encounter_id = cm.encounter_id
                WHERE e.start_time BETWEEN ? AND ?
            """
            params = [start_date.timestamp(), end_date.timestamp()]

            if guild_id is not None:
                query += " AND e.guild_id = ?"
                params.append(guild_id)

            query += " GROUP BY e.encounter_id ORDER BY e.start_time DESC LIMIT 50"

            cursor = db.execute(query, params)

            fights = []
            for idx, row in enumerate(cursor):
                fights.append({
                    "id": idx + 1,
                    "encounter_id": row[0],
                    "boss": row[1],
                    "difficulty": row[2] or "Normal",
                    "start_time": row[3],
                    "end_time": row[4],
                    "kill": bool(row[5]),
                    "size": row[6],
                    "player_count": row[7],
                })

            wcl_export = {
                "version": 1,
                "reportInfo": {
                    "gameVersion": "10.2.5",
                    "exportDate": datetime.now().isoformat(),
                    "days": days,
                },
                "fights": fights,
                "title": f"Combat Logs Export - {days} days",
            }

            return JSONResponse(
                content=wcl_export,
                headers={
                    "Content-Disposition": f"attachment; filename=wcl_export_{days}d.json"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export WCL format: {str(e)}")


@router.get("/export/sheets")
async def export_google_sheets(
    encounter_id: Optional[int] = Query(None, description="Specific encounter to export"),
    guild_id: Optional[int] = Query(None, description="Guild ID for filtering"),
    db: DatabaseManager = Depends(),
):
    """
    Export data for Google Sheets integration.

    Returns a simplified JSON structure optimized for import
    into Google Sheets or similar spreadsheet applications.
    """
    try:
        query_api = QueryAPI(db)

        if encounter_id:
            # Get encounter data
            encounter_data = query_api.export_encounter_data(
                encounter_id=encounter_id,
                guild_id=guild_id,
                decompress_events=False,
            )

            if not encounter_data:
                raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

            # Format for sheets (array of arrays)
            headers = [
                "Character", "Class", "Spec", "DPS", "HPS",
                "Damage Done", "Healing Done", "Deaths", "Activity %"
            ]

            rows = []
            for m in encounter_data["character_metrics"]:
                rows.append([
                    m["character_name"],
                    m["class_name"] or "",
                    m["spec_name"] or "",
                    round(m["dps"], 1),
                    round(m["hps"], 1),
                    m["damage_done"],
                    m["healing_done"],
                    m["death_count"],
                    round(m["activity_percentage"], 1),
                ])

            sheets_data = {
                "encounter": {
                    "boss": encounter_data["encounter"]["boss_name"],
                    "difficulty": encounter_data["encounter"]["difficulty"],
                    "date": encounter_data["encounter"]["start_time"],
                    "success": encounter_data["encounter"]["success"],
                },
                "headers": headers,
                "data": rows,
            }

            return JSONResponse(
                content=sheets_data,
                headers={
                    "Content-Disposition": f"attachment; filename=encounter_{encounter_id}_sheets.json"
                }
            )

        else:
            # Export summary data for sheets
            query = """
                SELECT
                    c.character_name,
                    c.class_name,
                    c.spec_name,
                    COUNT(DISTINCT cm.encounter_id) as encounters,
                    AVG(cm.dps) as avg_dps,
                    AVG(cm.hps) as avg_hps,
                    SUM(cm.death_count) as total_deaths
                FROM characters c
                JOIN character_metrics cm ON c.character_id = cm.character_id
            """
            params = []

            if guild_id is not None:
                query += " WHERE c.guild_id = ?"
                params.append(guild_id)

            query += " GROUP BY c.character_id ORDER BY avg_dps DESC LIMIT 100"

            cursor = db.execute(query, params)

            headers = ["Character", "Class", "Spec", "Encounters", "Avg DPS", "Avg HPS", "Deaths"]
            rows = []

            for row in cursor:
                rows.append([
                    row[0],  # character_name
                    row[1] or "",  # class_name
                    row[2] or "",  # spec_name
                    row[3],  # encounters
                    round(row[4], 1) if row[4] else 0,  # avg_dps
                    round(row[5], 1) if row[5] else 0,  # avg_hps
                    row[6] or 0,  # total_deaths
                ])

            sheets_data = {
                "title": "Character Performance Summary",
                "headers": headers,
                "data": rows,
            }

            return JSONResponse(
                content=sheets_data,
                headers={
                    "Content-Disposition": "attachment; filename=performance_summary_sheets.json"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export for sheets: {str(e)}")