"""
Talent parsing module for extracting talent data from COMBATANT_INFO events.

Parses talent information from WoW combat logs and stores it in the database
for character talent tracking and optimization analysis.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TalentSelection:
    """Represents a single talent selection."""
    talent_slot: int
    talent_spell_id: int
    talent_tier: int = 0
    talent_column: int = 0
    is_selected: bool = True

@dataclass
class TalentSnapshot:
    """Represents a complete talent set for a character at a specific time."""
    character_id: int
    encounter_id: Optional[int]
    snapshot_time: float
    source: str
    specialization: str
    talent_loadout: str
    talents: List[TalentSelection]
    total_talents: int = 0

    def __post_init__(self):
        self.total_talents = len(self.talents)


class TalentParser:
    """Parser for extracting talent data from COMBATANT_INFO events."""

    def __init__(self):
        # Regex patterns for talent data extraction
        self.talent_pattern = re.compile(r'\((\d+),(\d+)(?:,([^)]*))?\)')

    def parse_combatant_info_talents(self, combatant_info_data: str, character_id: int,
                                   encounter_id: Optional[int], timestamp: float) -> Optional[TalentSnapshot]:
        """
        Parse talent data from COMBATANT_INFO event.

        Args:
            combatant_info_data: Raw COMBATANT_INFO data string
            character_id: Database character ID
            encounter_id: Database encounter ID (optional)
            timestamp: Event timestamp

        Returns:
            TalentSnapshot object or None if parsing fails
        """
        try:
            # Split COMBATANT_INFO data by commas
            parts = combatant_info_data.split(',')

            # COMBATANT_INFO format (simplified):
            # GUID,faction,strength,agility,stamina,intellect,spirit,mastery,haste,crit,multistrike,leech,
            # versatility,avoidance,speed,lifesteal,indestructible,gear_avg_ilvl,gear_equipped_ilvl,
            # artifact_traits,equipment_data,talents_data,auras_data,additional_data

            # Find talent data section - typically comes after equipment data
            # Look for talent data patterns after the equipment section
            talent_section = None
            in_equipment = False
            bracket_depth = 0

            for i, part in enumerate(parts):
                # Track bracket depth to know when we're out of equipment section
                bracket_depth += part.count('[') - part.count(']')

                if '[' in part and not in_equipment:
                    in_equipment = True
                elif bracket_depth == 0 and in_equipment and '(' in part:
                    # We're out of equipment section and found talent data
                    talent_section = ','.join(parts[i:])
                    break

            if not talent_section:
                logger.debug("No talent section found in COMBATANT_INFO")
                return None

            # Extract talent data - typically in format [(spellId,rank,...),...] after gear
            # Look for the second bracket section (first is gear, second is talents)
            sections = re.findall(r'\[([^\]]+)\]', talent_section)

            if len(sections) < 2:
                logger.debug("Not enough data sections found for talents")
                return None

            # Second section typically contains talent data
            talent_data = sections[1] if len(sections) > 1 else sections[0]

            # Parse individual talent selections
            talents = []
            talent_matches = self.talent_pattern.findall(talent_data)

            for slot_index, match in enumerate(talent_matches):
                spell_id_str, rank_str, extra_data = match
                spell_id = int(spell_id_str)
                rank = int(rank_str) if rank_str else 0

                # Skip empty/invalid talents
                if spell_id == 0:
                    continue

                # Calculate tier and column from slot (approximate)
                # Modern WoW has different talent systems, this is a simplified approach
                tier = (slot_index // 3) + 1  # Rough tier calculation
                column = (slot_index % 3) + 1  # Rough column calculation

                talent = TalentSelection(
                    talent_slot=slot_index + 1,
                    talent_spell_id=spell_id,
                    talent_tier=tier,
                    talent_column=column,
                    is_selected=True
                )

                talents.append(talent)

            if not talents:
                logger.debug("No valid talents found in COMBATANT_INFO")
                return None

            # Try to determine specialization from the talent choices
            # This is a simplified approach - could be enhanced with spec detection logic
            specialization = "Unknown"

            # Generate a basic talent loadout string (simplified)
            # In a real implementation, this would follow WoW's loadout format
            talent_loadout = ','.join([str(t.talent_spell_id) for t in talents])

            # Create talent snapshot
            snapshot = TalentSnapshot(
                character_id=character_id,
                encounter_id=encounter_id,
                snapshot_time=timestamp,
                source='combatant_info',
                specialization=specialization,
                talent_loadout=talent_loadout,
                talents=talents
            )

            logger.debug(f"Parsed talents for character {character_id}: {snapshot.total_talents} talents, "
                        f"spec {specialization}")

            return snapshot

        except Exception as e:
            logger.error(f"Error parsing COMBATANT_INFO talent data: {e}")
            return None

    def store_talent_snapshot(self, db, snapshot: TalentSnapshot, guild_id: int) -> Optional[int]:
        """
        Store talent snapshot in the database.

        Args:
            db: Database manager instance
            snapshot: TalentSnapshot to store
            guild_id: Guild ID for multi-tenancy

        Returns:
            Snapshot ID if successful, None otherwise
        """
        try:
            # Insert talent snapshot
            cursor = db.execute(
                """
                INSERT OR REPLACE INTO character_talent_snapshots
                (guild_id, encounter_id, character_id, snapshot_time, source,
                 specialization, talent_loadout, total_talents)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, snapshot.encounter_id, snapshot.character_id, snapshot.snapshot_time,
                 snapshot.source, snapshot.specialization, snapshot.talent_loadout,
                 snapshot.total_talents)
            )

            # Get the snapshot ID
            snapshot_id = cursor.lastrowid
            if not snapshot_id:
                # If using REPLACE, get the existing ID
                cursor = db.execute(
                    "SELECT snapshot_id FROM character_talent_snapshots WHERE character_id = %s AND encounter_id = %s",
                    (snapshot.character_id, snapshot.encounter_id)
                )
                row = cursor.fetchone()
                snapshot_id = row[0] if row else None

            if not snapshot_id:
                logger.error("Failed to get snapshot ID after insert")
                return None

            # Clear existing talent selections for this snapshot
            db.execute("DELETE FROM character_talent_selections WHERE snapshot_id = %s", (snapshot_id,))

            # Insert talent selections
            for talent in snapshot.talents:
                db.execute(
                    """
                    INSERT INTO character_talent_selections
                    (snapshot_id, talent_slot, talent_spell_id, talent_tier,
                     talent_column, is_selected)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, talent.talent_slot, talent.talent_spell_id,
                     talent.talent_tier, talent.talent_column, talent.is_selected)
                )

            db.commit()
            logger.debug(f"Stored talent snapshot {snapshot_id} with {len(snapshot.talents)} talents")
            return snapshot_id

        except Exception as e:
            logger.error(f"Error storing talent snapshot: {e}")
            db.rollback()
            return None

    def get_character_talents_by_encounter(self, db, character_id: int, encounter_id: int) -> Optional[TalentSnapshot]:
        """
        Retrieve talent snapshot for a character in a specific encounter.

        Args:
            db: Database manager instance
            character_id: Character ID
            encounter_id: Encounter ID

        Returns:
            TalentSnapshot or None if not found
        """
        try:
            # Get snapshot metadata
            cursor = db.execute(
                """
                SELECT snapshot_id, guild_id, snapshot_time, source,
                       specialization, talent_loadout, total_talents
                FROM character_talent_snapshots
                WHERE character_id = %s AND encounter_id = %s
                """,
                (character_id, encounter_id)
            )

            snapshot_row = cursor.fetchone()
            if not snapshot_row:
                return None

            (snapshot_id, guild_id, snapshot_time, source, specialization,
             talent_loadout, total_talents) = snapshot_row

            # Get talent selections
            cursor = db.execute(
                """
                SELECT talent_slot, talent_spell_id, talent_tier,
                       talent_column, is_selected
                FROM character_talent_selections
                WHERE snapshot_id = %s
                ORDER BY talent_slot
                """,
                (snapshot_id,)
            )

            talents = []
            for row in cursor.fetchall():
                (talent_slot, talent_spell_id, talent_tier,
                 talent_column, is_selected) = row

                talent = TalentSelection(
                    talent_slot=talent_slot,
                    talent_spell_id=talent_spell_id,
                    talent_tier=talent_tier,
                    talent_column=talent_column,
                    is_selected=bool(is_selected)
                )
                talents.append(talent)

            snapshot = TalentSnapshot(
                character_id=character_id,
                encounter_id=encounter_id,
                snapshot_time=snapshot_time,
                source=source,
                specialization=specialization,
                talent_loadout=talent_loadout,
                talents=talents,
                total_talents=total_talents
            )

            return snapshot

        except Exception as e:
            logger.error(f"Error retrieving talent snapshot: {e}")
            return None

    def generate_talent_recommendations(self, snapshot: TalentSnapshot, encounter_type: str = None) -> List[Dict[str, Any]]:
        """
        Generate basic talent recommendations based on the current build.

        Args:
            snapshot: TalentSnapshot to analyze
            encounter_type: Type of encounter ('raid', 'mythic_plus', etc.)

        Returns:
            List of recommendation dictionaries
        """
        recommendations = []

        try:
            # This is a simplified recommendation system
            # In a real implementation, this would use encounter-specific data
            # and class/spec expertise

            if snapshot.total_talents < 10:
                recommendations.append({
                    "type": "missing_talents",
                    "priority": "high",
                    "message": f"Only {snapshot.total_talents} talents selected. Consider filling all talent slots."
                })

            # Check for common talent synergies (simplified example)
            spell_ids = [t.talent_spell_id for t in snapshot.talents]

            # Example: Check for missing defensive talents for raid content
            if encounter_type == "raid":
                # This would be class/spec specific in a real implementation
                defensive_talents = [spell_id for spell_id in spell_ids if spell_id in [1000, 2000, 3000]]  # Example IDs
                if not defensive_talents:
                    recommendations.append({
                        "type": "defensive_talents",
                        "priority": "medium",
                        "message": "Consider taking defensive talents for raid encounters"
                    })

            # Example: Check for AoE talents for M+ content
            if encounter_type == "mythic_plus":
                aoe_talents = [spell_id for spell_id in spell_ids if spell_id in [4000, 5000, 6000]]  # Example IDs
                if not aoe_talents:
                    recommendations.append({
                        "type": "aoe_talents",
                        "priority": "medium",
                        "message": "Consider AoE talents for Mythic+ dungeons"
                    })

        except Exception as e:
            logger.warning(f"Error generating talent recommendations: {e}")

        return recommendations