"""
Guild management API endpoints for v1.

Provides endpoints for guild CRUD operations, encounter management,
attendance tracking, performance analysis, and raid composition planning.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body
from fastapi.responses import JSONResponse

from ..models.guilds import GuildRoster, AttendanceTracking, GuildPerformance, RaidComposition, GuildSettings, GuildSettingsResponse
from ..models.responses import PaginatedResponse
from src.database.schema import DatabaseManager
from src.database.query import QueryAPI

router = APIRouter()


@router.get("/guilds", response_model=PaginatedResponse[Dict[str, Any]])
async def list_guilds(
    limit: int = Query(20, ge=1, le=100, description="Number of guilds per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: DatabaseManager = Depends(),
):
    """
    List all guilds with pagination.

    Returns a paginated list of guilds with their basic information
    and encounter counts.
    """
    try:
        query_api = QueryAPI(db)

        # Get guilds
        guilds = query_api.get_guilds(
            limit=limit,
            offset=offset,
            is_active=is_active,
        )

        # Get total count for pagination
        if is_active is not None:
            cursor = db.execute(
                "SELECT COUNT(*) FROM guilds WHERE is_active = %s",
                (is_active,)
            )
        else:
            cursor = db.execute("SELECT COUNT(*) FROM guilds")
        total_count = cursor.fetchone()[0]

        # Calculate pagination metadata
        has_next = offset + limit < total_count
        has_previous = offset > 0
        page = (offset // limit) + 1
        total_pages = (total_count + limit - 1) // limit

        return PaginatedResponse(
            items=guilds,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_next": has_next,
                "has_previous": has_previous,
                "page": page,
                "total_pages": total_pages,
            },
            filters={"is_active": is_active} if is_active is not None else {},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guilds: {str(e)}")


@router.post("/guilds", response_model=Dict[str, Any])
async def create_guild(
    guild_name: str = Body(..., description="Name of the guild"),
    server: str = Body(..., description="Server name"),
    region: str = Body("US", description="Region (US, EU, etc.)"),
    faction: Optional[str] = Body(None, description="Faction (Alliance/Horde)"),
    db: DatabaseManager = Depends(),
):
    """
    Create a new guild.

    Returns the newly created guild with its assigned guild_id.
    """
    try:
        query_api = QueryAPI(db)

        # Check if guild already exists
        cursor = db.execute(
            """
            SELECT guild_id FROM guilds
            WHERE guild_name = %s AND server = %s AND region = %s
            """,
            (guild_name, server, region)
        )
        existing = cursor.fetchone()

        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Guild '{guild_name}' already exists on {server}-{region}"
            )

        # Create the guild
        guild_id = query_api.create_guild(
            guild_name=guild_name,
            server=server,
            region=region,
            faction=faction,
        )

        # Return the created guild
        guild = query_api.get_guild(guild_id)

        return guild

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create guild: {str(e)}")


@router.get("/guilds/{guild_id}", response_model=Dict[str, Any])
async def get_guild(
    guild_id: int = Path(..., description="Guild ID"),
    db: DatabaseManager = Depends(),
):
    """
    Get guild details by ID.

    Returns comprehensive guild information including encounter statistics.
    """
    try:
        query_api = QueryAPI(db)

        guild = query_api.get_guild(guild_id)

        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild with ID {guild_id} not found")

        # Add encounter statistics
        cursor = db.execute(
            """
            SELECT
                COUNT(*) as total_encounters,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_encounters,
                COUNT(DISTINCT boss_name) as unique_bosses,
                COUNT(DISTINCT DATE(start_time, 'unixepoch')) as raid_days
            FROM combat_encounters
            WHERE guild_id = %s
            """,
            (guild_id,)
        )
        stats = cursor.fetchone()

        guild["statistics"] = {
            "total_encounters": stats[0] or 0,
            "successful_encounters": stats[1] or 0,
            "unique_bosses": stats[2] or 0,
            "raid_days": stats[3] or 0,
            "success_rate": (stats[1] / stats[0] * 100) if stats[0] > 0 else 0,
        }

        return guild

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guild: {str(e)}")


@router.put("/guilds/{guild_id}", response_model=Dict[str, Any])
async def update_guild(
    guild_id: int = Path(..., description="Guild ID"),
    guild_name: Optional[str] = Body(None, description="New guild name"),
    server: Optional[str] = Body(None, description="New server"),
    region: Optional[str] = Body(None, description="New region"),
    faction: Optional[str] = Body(None, description="New faction"),
    is_active: Optional[bool] = Body(None, description="Active status"),
    db: DatabaseManager = Depends(),
):
    """
    Update guild information.

    Returns the updated guild information.
    """
    try:
        query_api = QueryAPI(db)

        # Check if guild exists
        guild = query_api.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild with ID {guild_id} not found")

        # Update the guild
        success = query_api.update_guild(
            guild_id=guild_id,
            guild_name=guild_name,
            server=server,
            region=region,
            faction=faction,
            is_active=is_active,
        )

        if not success:
            raise HTTPException(status_code=400, detail="No updates provided")

        # Return updated guild
        guild = query_api.get_guild(guild_id)

        return guild

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update guild: {str(e)}")


@router.delete("/guilds/{guild_id}")
async def delete_guild(
    guild_id: int = Path(..., description="Guild ID"),
    db: DatabaseManager = Depends(),
):
    """
    Soft delete a guild (marks as inactive).

    Returns success status. The guild and its data are not actually deleted,
    just marked as inactive.
    """
    try:
        query_api = QueryAPI(db)

        # Check if guild exists
        guild = query_api.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild with ID {guild_id} not found")

        # Soft delete the guild
        success = query_api.delete_guild(guild_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete guild")

        return JSONResponse(
            status_code=200,
            content={
                "message": f"Guild '{guild['guild_name']}' has been deactivated",
                "guild_id": guild_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete guild: {str(e)}")


@router.patch("/admin/guild/settings", response_model=Dict[str, Any])
async def update_guild_settings(
    guild_id: int = Query(..., description="Guild ID"),
    settings: GuildSettings = Body(..., description="Guild settings to update"),
    db: DatabaseManager = Depends(),
):
    """
    Update guild settings.

    Updates the guild settings including raid schedule, loot system, and log visibility.
    Settings are stored in the JSONB settings column and only provided fields are updated.
    """
    try:
        query_api = QueryAPI(db)

        # Check if guild exists
        guild = query_api.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild with ID {guild_id} not found")

        # Update guild settings
        success = query_api.update_guild_settings(
            guild_id=guild_id,
            raid_schedule=settings.raid_schedule,
            loot_system=settings.loot_system,
            public_logs=settings.public_logs,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update guild settings")

        # Return success response
        return JSONResponse(
            status_code=200,
            content={
                "message": "Guild settings updated successfully",
                "guild_id": guild_id,
                "updated_at": guild["updated_at"] if guild.get("updated_at") else None,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update guild settings: {str(e)}")


@router.get("/guilds/{guild_id}/encounters", response_model=List[Dict[str, Any]])
async def get_guild_encounters(
    guild_id: int = Path(..., description="Guild ID"),
    encounter_type: Optional[str] = Query(None, description="Filter by type (raid/mythic_plus)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum encounters to return"),
    db: DatabaseManager = Depends(),
):
    """
    Get all encounters for a specific guild.

    Returns a list of encounter summaries for the guild,
    optionally filtered by encounter type.
    """
    try:
        query_api = QueryAPI(db)

        # Check if guild exists
        guild = query_api.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild with ID {guild_id} not found")

        # Get encounters
        encounters = query_api.get_guild_encounters(
            guild_id=guild_id,
            encounter_type=encounter_type,
            limit=limit,
        )

        # Convert to dict format
        encounter_dicts = []
        for enc in encounters:
            encounter_dicts.append({
                "encounter_id": enc.encounter_id,
                "encounter_type": enc.encounter_type,
                "boss_name": enc.boss_name,
                "difficulty": enc.difficulty,
                "start_time": enc.start_time.isoformat() if enc.start_time else None,
                "end_time": enc.end_time.isoformat() if enc.end_time else None,
                "success": enc.success,
                "combat_length": enc.combat_length,
                "raid_size": enc.raid_size,
                "character_count": enc.character_count,
            })

        return encounter_dicts

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guild encounters: {str(e)}")


@router.get("/guilds/{guild_id}/encounters/raid", response_model=List[Dict[str, Any]])
async def get_guild_raid_encounters(
    guild_id: int = Path(..., description="Guild ID"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    success_only: bool = Query(False, description="Only show successful kills"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum encounters to return"),
    db: DatabaseManager = Depends(),
):
    """
    Get raid encounters for a specific guild.

    Returns a list of raid encounter summaries for the guild,
    with optional filtering by difficulty and success status.
    """
    try:
        query_api = QueryAPI(db)

        # Check if guild exists
        guild = query_api.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild with ID {guild_id} not found")

        # Build query with filters
        query = """
            SELECT
                encounter_id, boss_name, difficulty, instance_name,
                start_time, end_time, success, combat_length, raid_size,
                wipe_percentage, bloodlust_used, battle_resurrections
            FROM combat_encounters
            WHERE guild_id = %s AND encounter_type = 'raid'
        """
        params = [guild_id]

        if difficulty:
            query += " AND difficulty = %s"
            params.append(difficulty)

        if success_only:
            query += " AND success = 1"

        query += " ORDER BY start_time DESC LIMIT %s"
        params.append(limit)

        cursor = db.execute(query, params)

        encounters = []
        for row in cursor:
            encounters.append({
                "encounter_id": row[0],
                "boss_name": row[1],
                "difficulty": row[2],
                "instance_name": row[3],
                "start_time": row[4],
                "end_time": row[5],
                "success": bool(row[6]),
                "combat_length": row[7],
                "raid_size": row[8],
                "wipe_percentage": row[9],
                "bloodlust_used": bool(row[10]) if row[10] is not None else None,
                "battle_resurrections": row[11],
            })

        return encounters

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve raid encounters: {str(e)}")


@router.get("/guilds/{guild_id}/encounters/mythic_plus", response_model=List[Dict[str, Any]])
async def get_guild_mythic_plus_encounters(
    guild_id: int = Path(..., description="Guild ID"),
    min_level: Optional[int] = Query(None, ge=2, le=30, description="Minimum keystone level"),
    in_time_only: bool = Query(False, description="Only show runs completed in time"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum encounters to return"),
    db: DatabaseManager = Depends(),
):
    """
    Get Mythic+ encounters for a specific guild.

    Returns a list of Mythic+ run summaries for the guild,
    with optional filtering by keystone level and timing.
    """
    try:
        query_api = QueryAPI(db)

        # Check if guild exists
        guild = query_api.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild with ID {guild_id} not found")

        # Build query with M+ specific data
        query = """
            SELECT
                e.encounter_id, e.instance_name, e.start_time, e.end_time,
                e.success, e.combat_length, e.raid_size,
                m.keystone_level, m.in_time, m.time_remaining,
                m.num_deaths, m.enemy_forces_percent
            FROM combat_encounters e
            LEFT JOIN mythic_plus_runs m ON e.encounter_id = m.encounter_id
            WHERE e.guild_id = %s AND e.encounter_type = 'mythic_plus'
        """
        params = [guild_id]

        if min_level:
            query += " AND m.keystone_level >= %s"
            params.append(min_level)

        if in_time_only:
            query += " AND m.in_time = 1"

        query += " ORDER BY e.start_time DESC LIMIT %s"
        params.append(limit)

        cursor = db.execute(query, params)

        encounters = []
        for row in cursor:
            encounters.append({
                "encounter_id": row[0],
                "dungeon_name": row[1],
                "start_time": row[2],
                "end_time": row[3],
                "success": bool(row[4]),
                "duration": row[5],
                "party_size": row[6],
                "keystone_level": row[7],
                "in_time": bool(row[8]) if row[8] is not None else None,
                "time_remaining": row[9],
                "num_deaths": row[10],
                "enemy_forces_percent": row[11],
            })

        return encounters

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve M+ encounters: {str(e)}")


# Keep the original placeholder endpoints for future implementation
@router.get("/guilds/{guild_name}/roster", response_model=GuildRoster)
async def get_guild_roster(
    guild_name: str, server: Optional[str] = Query(None), db: DatabaseManager = Depends()
):
    """Get guild roster with member analysis."""
    try:
        query_api = QueryAPI(db)

        # Find guild by name and server
        cursor = db.execute(
            """
            SELECT guild_id FROM guilds
            WHERE guild_name = %s AND (server = %s OR %s IS NULL)
            """,
            (guild_name, server, server)
        )
        guild_row = cursor.fetchone()

        if not guild_row:
            raise HTTPException(
                status_code=404,
                detail=f"Guild '{guild_name}' not found" + (f" on server '{server}'" if server else "")
            )

        guild_id = guild_row[0]

        # Get characters for this guild
        cursor = db.execute(
            """
            SELECT character_name, class, level, spec, role, last_seen
            FROM characters
            WHERE guild_id = %s
            ORDER BY character_name
            """,
            (guild_id,)
        )

        members = []
        for row in cursor:
            members.append({
                "character_name": row[0],
                "class": row[1],
                "level": row[2] or 80,
                "spec": row[3] or "Unknown",
                "role": row[4] or "DPS",
                "last_seen": row[5],
                "status": "active" if row[5] else "inactive"
            })

        return {
            "guild_name": guild_name,
            "server": server,
            "member_count": len(members),
            "members": members,
            "class_distribution": {},  # Could be enhanced with actual counts
            "role_distribution": {},   # Could be enhanced with actual counts
            "last_updated": None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guild roster: {str(e)}")


@router.get("/guilds/{guild_name}/attendance", response_model=AttendanceTracking)
async def get_guild_attendance(
    guild_name: str, days: int = Query(30, ge=7, le=365), db: DatabaseManager = Depends()
):
    """Get guild attendance tracking data."""
    try:
        query_api = QueryAPI(db)

        # Find guild by name
        cursor = db.execute(
            "SELECT guild_id FROM guilds WHERE guild_name = %s",
            (guild_name,)
        )
        guild_row = cursor.fetchone()

        if not guild_row:
            raise HTTPException(status_code=404, detail=f"Guild '{guild_name}' not found")

        guild_id = guild_row[0]

        # Get encounter participation in the last N days
        cursor = db.execute(
            """
            SELECT
                c.character_name,
                COUNT(DISTINCT DATE(e.start_time, 'unixepoch')) as raid_days,
                COUNT(e.encounter_id) as total_encounters,
                SUM(CASE WHEN e.success = 1 THEN 1 ELSE 0 END) as successful_encounters
            FROM characters c
            LEFT JOIN encounter_participants ep ON c.character_id = ep.character_id
            LEFT JOIN encounters e ON ep.encounter_id = e.encounter_id
                AND e.start_time >= strftime('%s', 'now', '-{} days')
            WHERE c.guild_id = %s
            GROUP BY c.character_id, c.character_name
            ORDER BY raid_days DESC, c.character_name
            """.format(days),
            (guild_id,)
        )

        members = []
        total_raid_days = 0

        # Get total available raid days for attendance calculation
        cursor_total = db.execute(
            """
            SELECT COUNT(DISTINCT DATE(start_time, 'unixepoch')) as total_raid_days
            FROM combat_encounters
            WHERE guild_id = %s AND start_time >= strftime('%s', 'now', '-{} days')
            """.format(days),
            (guild_id,)
        )
        total_raid_days = cursor_total.fetchone()[0] or 1

        for row in cursor:
            character_name, raid_days, total_encounters, successful_encounters = row
            attendance_rate = (raid_days / total_raid_days * 100) if total_raid_days > 0 else 0

            members.append({
                "character_name": character_name,
                "raid_days": raid_days or 0,
                "total_encounters": total_encounters or 0,
                "successful_encounters": successful_encounters or 0,
                "attendance_rate": round(attendance_rate, 2)
            })

        return {
            "guild_name": guild_name,
            "period_days": days,
            "total_raid_days": total_raid_days,
            "members": members,
            "summary": {
                "average_attendance": sum(m["attendance_rate"] for m in members) / len(members) if members else 0,
                "total_members": len(members),
                "active_members": len([m for m in members if m["raid_days"] > 0])
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guild attendance: {str(e)}")


@router.get("/guilds/{guild_name}/performance", response_model=GuildPerformance)
async def get_guild_performance(
    guild_name: str, days: int = Query(30, ge=7, le=365), db: DatabaseManager = Depends()
):
    """Get comprehensive guild performance analysis."""
    try:
        query_api = QueryAPI(db)

        # Find guild by name
        cursor = db.execute(
            "SELECT guild_id FROM guilds WHERE guild_name = %s",
            (guild_name,)
        )
        guild_row = cursor.fetchone()

        if not guild_row:
            raise HTTPException(status_code=404, detail=f"Guild '{guild_name}' not found")

        guild_id = guild_row[0]

        # Get performance data from encounter participants
        cursor = db.execute(
            """
            SELECT
                c.character_name,
                c.class,
                c.spec,
                AVG(ep.damage_done) as avg_dps,
                AVG(ep.healing_done) as avg_hps,
                COUNT(e.encounter_id) as encounters,
                SUM(CASE WHEN e.success = 1 THEN 1 ELSE 0 END) as kills,
                MAX(ep.damage_done) as best_dps,
                MAX(ep.healing_done) as best_hps
            FROM characters c
            LEFT JOIN encounter_participants ep ON c.character_id = ep.character_id
            LEFT JOIN encounters e ON ep.encounter_id = e.encounter_id
                AND e.start_time >= strftime('%s', 'now', '-{} days')
            WHERE c.guild_id = %s
            GROUP BY c.character_id, c.character_name, c.class, c.spec
            HAVING encounters > 0
            ORDER BY avg_dps DESC
            """.format(days),
            (guild_id,)
        )

        players = []
        for row in cursor:
            character_name, char_class, spec, avg_dps, avg_hps, encounters, kills, best_dps, best_hps = row

            players.append({
                "character_name": character_name,
                "class": char_class,
                "spec": spec or "Unknown",
                "average_dps": round(avg_dps or 0, 2),
                "average_hps": round(avg_hps or 0, 2),
                "encounters": encounters or 0,
                "kills": kills or 0,
                "success_rate": round((kills / encounters * 100) if encounters > 0 else 0, 2),
                "best_dps": round(best_dps or 0, 2),
                "best_hps": round(best_hps or 0, 2)
            })

        # Calculate guild-wide statistics
        total_encounters = sum(p["encounters"] for p in players)
        total_kills = sum(p["kills"] for p in players)
        avg_guild_dps = sum(p["average_dps"] for p in players) / len(players) if players else 0
        avg_guild_hps = sum(p["average_hps"] for p in players) / len(players) if players else 0

        # Get top performers
        top_dps = sorted(players, key=lambda x: x["average_dps"], reverse=True)[:5]
        top_hps = sorted([p for p in players if p["average_hps"] > 0], key=lambda x: x["average_hps"], reverse=True)[:5]

        return {
            "guild_name": guild_name,
            "period_days": days,
            "players": players,
            "summary": {
                "total_players": len(players),
                "total_encounters": total_encounters,
                "total_kills": total_kills,
                "overall_success_rate": round((total_kills / total_encounters * 100) if total_encounters > 0 else 0, 2),
                "average_guild_dps": round(avg_guild_dps, 2),
                "average_guild_hps": round(avg_guild_hps, 2)
            },
            "top_performers": {
                "dps": top_dps,
                "healers": top_hps
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guild performance: {str(e)}")