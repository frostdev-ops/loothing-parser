"""
Database adapter to map parser expectations to existing lootbong database schema.

This adapter translates between:
- Parser schema: encounters, characters, guilds, character_metrics
- Existing schema: combat_encounters, combat_performances, guilds, characters

Key mappings:
- encounters → combat_encounters
- character_metrics → combat_performances
- characters → characters + derived data from combat_performances
- guilds → guilds (with column mapping)
"""

import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ExistingSchemaAdapter:
    """Adapter to work with existing lootbong database schema."""

    def __init__(self, db_connection):
        """
        Initialize adapter with database connection.

        Args:
            db_connection: Database connection/manager instance
        """
        self.db = db_connection
        self.backend_type = getattr(db_connection, 'backend_type', 'unknown')
        logger.info(f"Initialized ExistingSchemaAdapter with backend: {self.backend_type}")

    def _convert_uuid_to_string(self, value: Any) -> str:
        """Convert UUID to string for parser compatibility."""
        if isinstance(value, uuid.UUID):
            return str(value)
        elif isinstance(value, str):
            return value
        else:
            return str(value) if value is not None else None

    def _convert_string_to_uuid(self, value: Any) -> Optional[str]:
        """Convert string to UUID string for database queries."""
        if value is None:
            return None
        try:
            # Validate it's a proper UUID format
            uuid.UUID(str(value))
            return str(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid UUID format: {value}")
            return None

    def _execute_query(self, query: str, params: Tuple = (), fetch_results: bool = True) -> Optional[List[Dict[str, Any]]]:
        """Execute query with proper parameter substitution for backend."""
        try:
            if self.backend_type == "postgresql":
                # PostgreSQL uses %s placeholders
                if params:
                    query = query.replace('?', '%s')

            return self.db.execute(query, params, fetch_results)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise

    # Guild operations - map to existing guilds table
    def get_guild(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get guild information by ID."""
        try:
            query = """
                SELECT id, name, icon, owner_id, member_count, created_at, updated_at
                FROM guilds
                WHERE id = ?
            """
            result = self._execute_query(query, (guild_id,))

            if result and len(result) > 0:
                row = result[0]
                return {
                    'guild_id': row['id'],  # Map to parser expected field
                    'guild_name': row['name'],
                    'server': 'Unknown',  # Not in existing schema
                    'region': 'US',  # Default
                    'faction': None,  # Not in existing schema
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'is_active': True,  # Default
                    'member_count': row.get('member_count', 0),
                    'icon': row.get('icon'),
                    'owner_id': row.get('owner_id')
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get guild {guild_id}: {e}")
            return None

    def get_guilds(self, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get list of guilds."""
        try:
            query = """
                SELECT id, name, icon, owner_id, member_count, created_at, updated_at
                FROM guilds
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            result = self._execute_query(query, (limit, offset))

            guilds = []
            if result:
                for row in result:
                    guilds.append({
                        'guild_id': row['id'],
                        'guild_name': row['name'],
                        'server': 'Unknown',
                        'region': 'US',
                        'faction': None,
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at'],
                        'is_active': True,
                        'member_count': row.get('member_count', 0),
                        'icon': row.get('icon'),
                        'owner_id': row.get('owner_id')
                    })
            return guilds
        except Exception as e:
            logger.error(f"Failed to get guilds: {e}")
            return []

    # Encounter operations - map to combat_encounters table
    def get_encounters(self, guild_id: Optional[int] = None, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get encounters from combat_encounters table."""
        try:
            query = """
                SELECT id, guild_id, encounter_type, encounter_name as boss_name,
                       instance_name, difficulty, start_time, end_time, duration_ms,
                       combat_duration_ms, success, player_count, total_damage,
                       total_healing, total_deaths, keystone_level, created_at
                FROM combat_encounters
            """
            params = []

            if guild_id is not None:
                query += " WHERE guild_id = ?"
                params.append(guild_id)

            query += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            result = self._execute_query(query, tuple(params))

            encounters = []
            if result:
                for row in result:
                    # Convert duration from milliseconds to seconds for parser compatibility
                    duration_seconds = (row['duration_ms'] / 1000.0) if row['duration_ms'] else 0.0
                    combat_duration_seconds = (row['combat_duration_ms'] / 1000.0) if row['combat_duration_ms'] else 0.0

                    encounters.append({
                        'encounter_id': self._convert_uuid_to_string(row['id']),  # Convert UUID to string
                        'guild_id': row['guild_id'],
                        'encounter_type': row['encounter_type'] or 'raid',
                        'boss_name': row['boss_name'],
                        'difficulty': row['difficulty'],
                        'instance_id': None,  # Not in existing schema
                        'instance_name': row['instance_name'],
                        'pull_number': 1,  # Default
                        'start_time': row['start_time'].timestamp() if row['start_time'] else None,
                        'end_time': row['end_time'].timestamp() if row['end_time'] else None,
                        'success': row['success'],
                        'combat_length': duration_seconds,  # Parser expects this field
                        'raid_size': row['player_count'],
                        'wipe_percentage': None,  # Not directly available
                        'bloodlust_used': False,  # Default
                        'bloodlust_time': None,
                        'battle_resurrections': 0,  # Default
                        'created_at': row['created_at'],
                        # Additional fields from existing schema
                        'total_damage': row['total_damage'],
                        'total_healing': row['total_healing'],
                        'total_deaths': row['total_deaths'],
                        'keystone_level': row['keystone_level']
                    })
            return encounters
        except Exception as e:
            logger.error(f"Failed to get encounters: {e}")
            return []

    def get_encounter(self, encounter_id: str, guild_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get specific encounter by ID."""
        try:
            encounter_uuid = self._convert_string_to_uuid(encounter_id)
            if not encounter_uuid:
                return None

            query = """
                SELECT id, guild_id, encounter_type, encounter_name as boss_name,
                       instance_name, difficulty, start_time, end_time, duration_ms,
                       combat_duration_ms, success, player_count, total_damage,
                       total_healing, total_deaths, keystone_level, created_at
                FROM combat_encounters
                WHERE id = ?
            """
            params = [encounter_uuid]

            if guild_id is not None:
                query += " AND guild_id = ?"
                params.append(guild_id)

            result = self._execute_query(query, tuple(params))

            if result and len(result) > 0:
                row = result[0]
                duration_seconds = (row['duration_ms'] / 1000.0) if row['duration_ms'] else 0.0
                combat_duration_seconds = (row['combat_duration_ms'] / 1000.0) if row['combat_duration_ms'] else 0.0

                return {
                    'encounter_id': self._convert_uuid_to_string(row['id']),
                    'guild_id': row['guild_id'],
                    'encounter_type': row['encounter_type'] or 'raid',
                    'boss_name': row['boss_name'],
                    'difficulty': row['difficulty'],
                    'instance_id': None,
                    'instance_name': row['instance_name'],
                    'pull_number': 1,
                    'start_time': row['start_time'].timestamp() if row['start_time'] else None,
                    'end_time': row['end_time'].timestamp() if row['end_time'] else None,
                    'success': row['success'],
                    'combat_length': duration_seconds,
                    'raid_size': row['player_count'],
                    'wipe_percentage': None,
                    'bloodlust_used': False,
                    'bloodlust_time': None,
                    'battle_resurrections': 0,
                    'created_at': row['created_at'],
                    'total_damage': row['total_damage'],
                    'total_healing': row['total_healing'],
                    'total_deaths': row['total_deaths'],
                    'keystone_level': row['keystone_level']
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get encounter {encounter_id}: {e}")
            return None

    # Character operations - map to characters table + derive from combat_performances
    def get_characters(self, guild_id: Optional[int] = None, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get characters, combining data from characters and combat_performances."""
        try:
            # Get characters with last activity from combat_performances
            query = """
                SELECT DISTINCT
                    c.id, c.guild_id, c.character_name, c.server, c.class, c.spec, c.role,
                    c.created_at, c.updated_at,
                    MAX(cp.created_at) as last_seen,
                    COUNT(cp.id) as encounter_count
                FROM characters c
                LEFT JOIN combat_performances cp ON c.id = cp.character_id
            """
            params = []

            if guild_id is not None:
                query += " WHERE c.guild_id = ?"
                params.append(guild_id)

            query += """
                GROUP BY c.id, c.guild_id, c.character_name, c.server, c.class, c.spec, c.role,
                         c.created_at, c.updated_at
                ORDER BY last_seen DESC NULLS LAST
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            result = self._execute_query(query, tuple(params))

            characters = []
            if result:
                for row in result:
                    # Generate a character GUID if not available (parser expects this)
                    character_guid = f"{row['character_name']}-{row['server'] or 'Unknown'}"

                    characters.append({
                        'character_id': self._convert_uuid_to_string(row['id']),
                        'guild_id': row['guild_id'],
                        'character_guid': character_guid,
                        'character_name': row['character_name'],
                        'server': row['server'] or 'Unknown',
                        'region': 'US',  # Default
                        'class_name': row['class'],
                        'spec_name': row['spec'],
                        'role': row['role'],
                        'first_seen': row['created_at'],
                        'last_seen': row['last_seen'] or row['created_at'],
                        'encounter_count': row['encounter_count'] or 0
                    })
            return characters
        except Exception as e:
            logger.error(f"Failed to get characters: {e}")
            return []

    def get_character_by_name(self, character_name: str, guild_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get specific character by name."""
        try:
            query = """
                SELECT DISTINCT
                    c.id, c.guild_id, c.character_name, c.server, c.class, c.spec, c.role,
                    c.created_at, c.updated_at,
                    MAX(cp.created_at) as last_seen,
                    COUNT(cp.id) as encounter_count
                FROM characters c
                LEFT JOIN combat_performances cp ON c.id = cp.character_id
                WHERE c.character_name ILIKE ?
            """
            params = [f"%{character_name}%"]

            if guild_id is not None:
                query += " AND c.guild_id = ?"
                params.append(guild_id)

            query += """
                GROUP BY c.id, c.guild_id, c.character_name, c.server, c.class, c.spec, c.role,
                         c.created_at, c.updated_at
                LIMIT 1
            """

            result = self._execute_query(query, tuple(params))

            if result and len(result) > 0:
                row = result[0]
                character_guid = f"{row['character_name']}-{row['server'] or 'Unknown'}"

                return {
                    'character_id': self._convert_uuid_to_string(row['id']),
                    'guild_id': row['guild_id'],
                    'character_guid': character_guid,
                    'character_name': row['character_name'],
                    'server': row['server'] or 'Unknown',
                    'region': 'US',
                    'class_name': row['class'],
                    'spec_name': row['spec'],
                    'role': row['role'],
                    'first_seen': row['created_at'],
                    'last_seen': row['last_seen'] or row['created_at'],
                    'encounter_count': row['encounter_count'] or 0
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get character {character_name}: {e}")
            return None

    # Character metrics operations - map to combat_performances table
    def get_character_metrics(self, encounter_id: str, guild_id: Optional[int] = None, character_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get character metrics from combat_performances table."""
        try:
            encounter_uuid = self._convert_string_to_uuid(encounter_id)
            if not encounter_uuid:
                return []

            query = """
                SELECT
                    cp.id, cp.guild_id, cp.encounter_id, cp.character_id, cp.character_name,
                    cp.class, cp.spec, cp.role, cp.item_level, cp.damage_done, cp.healing_done,
                    cp.damage_taken, cp.overhealing, cp.absorb_healing, cp.deaths, cp.interrupts,
                    cp.dispels, cp.active_time_ms, cp.dps, cp.hps, cp.dtps, cp.activity_percentage,
                    cp.talent_build, cp.equipment, cp.metadata, cp.created_at,
                    c.server, c.id as char_uuid
                FROM combat_performances cp
                LEFT JOIN characters c ON cp.character_id = c.id
                WHERE cp.encounter_id = ?
            """
            params = [encounter_uuid]

            if guild_id is not None:
                query += " AND cp.guild_id = ?"
                params.append(guild_id)

            if character_name:
                query += " AND cp.character_name ILIKE ?"
                params.append(f"%{character_name}%")

            query += " ORDER BY cp.dps DESC"

            result = self._execute_query(query, tuple(params))

            metrics = []
            if result:
                for row in result:
                    # Generate character GUID
                    character_guid = f"{row['character_name']}-{row['server'] or 'Unknown'}"

                    # Convert active time from ms to seconds
                    active_time_seconds = (row['active_time_ms'] / 1000.0) if row['active_time_ms'] else 0.0

                    # Calculate additional metrics expected by parser
                    combat_time = active_time_seconds  # Use active time as combat time
                    combat_dps = row['dps'] or 0.0  # Use same as regular DPS
                    combat_hps = row['hps'] or 0.0  # Use same as regular HPS
                    combat_dtps = row['dtps'] or 0.0

                    metrics.append({
                        # Core identification
                        'metric_id': self._convert_uuid_to_string(row['id']),
                        'guild_id': row['guild_id'],
                        'encounter_id': encounter_uuid,
                        'character_id': self._convert_uuid_to_string(row['character_id']) if row['character_id'] else None,
                        'character_name': row['character_name'],
                        'character_guid': character_guid,
                        'class_name': row['class'],
                        'spec_name': row['spec'],
                        'role': row['role'],

                        # Combat metrics - map from existing schema
                        'damage_done': row['damage_done'] or 0,
                        'healing_done': row['healing_done'] or 0,
                        'damage_taken': row['damage_taken'] or 0,
                        'healing_received': 0,  # Not available in existing schema
                        'overhealing': row['overhealing'] or 0,
                        'death_count': row['deaths'] or 0,
                        'activity_percentage': row['activity_percentage'] or 0.0,
                        'time_alive': active_time_seconds,
                        'dps': row['dps'] or 0.0,
                        'hps': row['hps'] or 0.0,
                        'dtps': row['dtps'] or 0.0,

                        # Combat-aware metrics
                        'combat_time': combat_time,
                        'combat_dps': combat_dps,
                        'combat_hps': combat_hps,
                        'combat_dtps': combat_dtps,
                        'combat_activity_percentage': row['activity_percentage'] or 0.0,

                        # Absorption and shields
                        'damage_absorbed_by_shields': 0,  # Would need calculation
                        'damage_absorbed_for_me': row['absorb_healing'] or 0,

                        # Events and actions
                        'total_events': 0,  # Not directly available
                        'cast_count': 0,  # Not directly available
                        'interrupts': row['interrupts'] or 0,
                        'dispels': row['dispels'] or 0,

                        # Additional data
                        'item_level': row['item_level'],
                        'talent_build': row['talent_build'] or {},
                        'equipment': row['equipment'] or {},
                        'metadata': row['metadata'] or {},
                        'created_at': row['created_at']
                    })
            return metrics
        except Exception as e:
            logger.error(f"Failed to get character metrics for encounter {encounter_id}: {e}")
            return []

    def get_top_performers(self, metric: str = 'dps', guild_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performers by metric from combat_performances."""
        try:
            # Map metric names
            metric_column_map = {
                'dps': 'dps',
                'hps': 'hps',
                'healing': 'healing_done',
                'damage': 'damage_done'
            }

            column = metric_column_map.get(metric, 'dps')

            query = f"""
                SELECT
                    cp.character_name, cp.class, cp.spec, cp.role,
                    AVG(cp.{column}) as avg_metric,
                    MAX(cp.{column}) as max_metric,
                    COUNT(cp.id) as encounter_count,
                    c.server
                FROM combat_performances cp
                LEFT JOIN characters c ON cp.character_id = c.id
            """
            params = []

            if guild_id is not None:
                query += " WHERE cp.guild_id = ?"
                params.append(guild_id)

            query += f"""
                GROUP BY cp.character_name, cp.class, cp.spec, cp.role, c.server
                HAVING COUNT(cp.id) > 0 AND AVG(cp.{column}) > 0
                ORDER BY avg_metric DESC
                LIMIT ?
            """
            params.append(limit)

            result = self._execute_query(query, tuple(params))

            performers = []
            if result:
                for idx, row in enumerate(result):
                    character_guid = f"{row['character_name']}-{row['server'] or 'Unknown'}"

                    performers.append({
                        'rank': idx + 1,
                        'character_name': row['character_name'],
                        'character_guid': character_guid,
                        'class_name': row['class'],
                        'spec_name': row['spec'],
                        'role': row['role'],
                        'server': row['server'] or 'Unknown',
                        'avg_value': float(row['avg_metric'] or 0),
                        'max_value': float(row['max_metric'] or 0),
                        'encounter_count': row['encounter_count'],
                        'metric': metric
                    })
            return performers
        except Exception as e:
            logger.error(f"Failed to get top performers: {e}")
            return []

    # Database statistics and health checks
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics mapped to parser expectations."""
        try:
            stats = {}

            # Count records in each table
            tables = [
                ('encounters', 'combat_encounters'),
                ('characters', 'characters'),
                ('character_metrics', 'combat_performances'),
                ('guilds', 'guilds')
            ]

            for parser_table, db_table in tables:
                try:
                    result = self._execute_query(f"SELECT COUNT(*) as count FROM {db_table}")
                    count = result[0]['count'] if result and len(result) > 0 else 0
                    stats[f"{parser_table}_count"] = count
                except Exception as e:
                    logger.warning(f"Failed to count {db_table}: {e}")
                    stats[f"{parser_table}_count"] = 0

            # Additional stats
            try:
                # Recent activity
                result = self._execute_query("""
                    SELECT COUNT(*) as count FROM combat_encounters
                    WHERE created_at > NOW() - INTERVAL '7 days'
                """)
                stats["encounters_last_7_days"] = result[0]['count'] if result and len(result) > 0 else 0
            except:
                stats["encounters_last_7_days"] = 0

            return stats
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}

    def health_check(self) -> bool:
        """Check database connection health."""
        try:
            result = self._execute_query("SELECT 1 as test")
            return result is not None and len(result) > 0
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    # Utility methods for data conversion and validation
    def validate_encounter_id(self, encounter_id: str) -> bool:
        """Validate that encounter ID is a valid UUID."""
        try:
            uuid.UUID(encounter_id)
            return True
        except (ValueError, TypeError):
            return False

    def validate_guild_id(self, guild_id: int) -> bool:
        """Validate that guild ID exists."""
        try:
            result = self._execute_query("SELECT 1 FROM guilds WHERE id = ?", (guild_id,))
            return result is not None and len(result) > 0
        except Exception:
            return False

    # Transaction support
    def commit(self):
        """Commit current transaction."""
        if hasattr(self.db, 'commit'):
            self.db.commit()

    def rollback(self):
        """Rollback current transaction."""
        if hasattr(self.db, 'rollback'):
            self.db.rollback()

    def close(self):
        """Close database connection."""
        if hasattr(self.db, 'close'):
            self.db.close()