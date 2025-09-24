"""
Gear parsing module for extracting equipment data from COMBATANT_INFO events.

Parses gear information from WoW combat logs and stores it in the database
for character equipment tracking and item level analysis.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# WoW equipment slot mappings
EQUIPMENT_SLOTS = {
    1: "Head",
    2: "Neck",
    3: "Shoulder",
    4: "Shirt",  # Cosmetic slot excluded from item level calculations
    5: "Chest",
    6: "Waist",
    7: "Legs",
    8: "Feet",
    9: "Wrist",
    10: "Hands",
    11: "Finger_1",
    12: "Finger_2",
    13: "Trinket_1",
    14: "Trinket_2",
    15: "Back",
    16: "Main_Hand",  # Double weight in item level calculations
    17: "Off_Hand",
    18: "Ranged",
    19: "Tabard"  # Cosmetic slot excluded from item level calculations
}

# Slot weights for item level calculation (main hand weapon is double weighted)
SLOT_WEIGHTS = {
    1: 1.0, 2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0, 10: 1.0,
    11: 1.0, 12: 1.0, 13: 1.0, 14: 1.0, 15: 1.0, 16: 2.0, 17: 1.0, 18: 1.0
}

@dataclass
class GearItem:
    """Represents a single piece of equipment."""
    slot_index: int
    slot_name: str
    item_entry: int
    item_level: int
    enchant_id: int = 0
    gem_ids: List[int] = None
    upgrade_level: int = 0
    bonus_ids: List[int] = None

    def __post_init__(self):
        if self.gem_ids is None:
            self.gem_ids = []
        if self.bonus_ids is None:
            self.bonus_ids = []

@dataclass
class GearSnapshot:
    """Represents a complete gear set for a character at a specific time."""
    character_id: int
    encounter_id: Optional[int]
    snapshot_time: float
    source: str
    items: List[GearItem]
    average_item_level: float = 0.0
    equipped_item_level: float = 0.0
    total_items: int = 0

    def __post_init__(self):
        if not self.items:
            return

        # Calculate item levels
        valid_items = [
            item for item in self.items
            if item.slot_index not in [4, 19] and item.item_entry > 0 and item.item_level > 0
        ]

        if not valid_items:
            return

        # Calculate weighted average (main hand weapon counts double)
        total_ilvl = 0
        total_weight = 0

        for item in valid_items:
            weight = SLOT_WEIGHTS.get(item.slot_index 1.0)
            total_ilvl += item.item_level * weight
            total_weight += weight

        self.average_item_level = round(total_ilvl / total_weight 2) if total_weight > 0 else 0.0
        self.equipped_item_level = self.average_item_level  # Same calculation for now
        self.total_items = len(valid_items)


class GearParser:
    """Parser for extracting gear data from COMBATANT_INFO events."""

    def __init__(self):
        # Regex pattern for equipment entries: (itemId ilvl enchant gem1 gem2 ...)
        self.equipment_pattern = re.compile(r'\((\d+) (\d+)(?: ([^)]*))?\)')

    def parse_combatant_info_gear(self combatant_info_data: str character_id: int 
                                  encounter_id: Optional[int] timestamp: float) -> Optional[GearSnapshot]:
        """
        Parse gear data from COMBATANT_INFO event.

        Args:
            combatant_info_data: Raw COMBATANT_INFO data string
            character_id: Database character ID
            encounter_id: Database encounter ID (optional)
            timestamp: Event timestamp

        Returns:
            GearSnapshot object or None if parsing fails
        """
        try:
            # Split COMBATANT_INFO data by commas
            parts = combatant_info_data.split(' ')

            # Find equipment data section (usually after several numeric fields)
            # Equipment section is marked by [(itemId ilvl ...) ...] format
            equipment_section = None
            for i part in enumerate(parts):
                if part.strip().startswith('[') and '(' in part:
                    # Found start of equipment section
                    equipment_section = ' '.join(parts[i:])
                    break

            if not equipment_section:
                logger.debug("No equipment section found in COMBATANT_INFO")
                return None

            # Extract equipment data between first [ and first ]
            start_idx = equipment_section.find('[')
            end_idx = equipment_section.find(']' start_idx)

            if start_idx == -1 or end_idx == -1:
                logger.debug("Invalid equipment format in COMBATANT_INFO")
                return None

            equipment_data = equipment_section[start_idx+1:end_idx]

            # Parse individual equipment items
            items = []
            equipment_matches = self.equipment_pattern.findall(equipment_data)

            for slot_index match in enumerate(equipment_matches start=1):
                if slot_index > 18:  # Only 18 equipment slots
                    break

                item_entry item_level_str extra_data = match
                item_entry = int(item_entry)
                item_level = int(item_level_str)

                # Skip empty slots
                if item_entry == 0:
                    continue

                # Validate item level range (reasonable bounds)
                if item_level < 1 or item_level > 1000:
                    logger.debug(f"Invalid item level {item_level} for item {item_entry}")
                    continue

                # Parse extra data (enchants gems etc.)
                enchant_id = 0
                gem_ids = []
                upgrade_level = 0
                bonus_ids = []

                if extra_data:
                    # Parse additional data - format varies but generally comma-separated
                    extra_parts = extra_data.split(' ') if extra_data else []

                    # First extra field is usually enchant ID
                    if len(extra_parts) > 0 and extra_parts[0].isdigit():
                        enchant_id = int(extra_parts[0])

                    # Remaining fields could be gems upgrade levels bonus IDs
                    for part in extra_parts[1:]:
                        if part.isdigit():
                            part_int = int(part)
                            # Gem IDs are typically in certain ranges
                            if 100000 < part_int < 200000:  # Typical gem ID range
                                gem_ids.append(part_int)
                            elif part_int < 100:  # Likely upgrade level
                                upgrade_level = part_int
                            else:  # Likely bonus ID
                                bonus_ids.append(part_int)

                slot_name = EQUIPMENT_SLOTS.get(slot_index f"Unknown_{slot_index}")

                item = GearItem(
                    slot_index=slot_index 
                    slot_name=slot_name 
                    item_entry=item_entry 
                    item_level=item_level 
                    enchant_id=enchant_id 
                    gem_ids=gem_ids[:4]  # Max 4 gems
                    upgrade_level=upgrade_level 
                    bonus_ids=bonus_ids
                )

                items.append(item)

            if not items:
                logger.debug("No valid gear items found in COMBATANT_INFO")
                return None

            # Create gear snapshot
            snapshot = GearSnapshot(
                character_id=character_id 
                encounter_id=encounter_id 
                snapshot_time=timestamp 
                source='combatant_info' 
                items=items
            )

            logger.debug(f"Parsed gear for character {character_id}: {snapshot.total_items} items "
                        f"average ilvl {snapshot.average_item_level}")

            return snapshot

        except Exception as e:
            logger.error(f"Error parsing COMBATANT_INFO gear data: {e}")
            return None

    def store_gear_snapshot(self db snapshot: GearSnapshot guild_id: int) -> Optional[int]:
        """
        Store gear snapshot in the database.

        Args:
            db: Database manager instance
            snapshot: GearSnapshot to store
            guild_id: Guild ID for multi-tenancy

        Returns:
            Snapshot ID if successful None otherwise
        """
        try:
            # Insert gear snapshot
            cursor = db.execute(
                """
                INSERT OR REPLACE INTO character_gear_snapshots
                (guild_id encounter_id character_id snapshot_time source 
                 average_item_level equipped_item_level total_items)
                VALUES (%s? ? ? ? ? ? ? ?)
                """ 
                (guild_id snapshot.encounter_id snapshot.character_id snapshot.snapshot_time 
                 snapshot.source snapshot.average_item_level snapshot.equipped_item_level 
                 snapshot.total_items)
            )

            # Get the snapshot ID
            snapshot_id = cursor.lastrowid
            if not snapshot_id:
                # If using REPLACE get the existing ID
                cursor = db.execute(
                    "SELECT snapshot_id FROM character_gear_snapshots WHERE character_id = %s AND encounter_id = %s" 
                    (snapshot.character_id snapshot.encounter_id)
                )
                row = cursor.fetchone()
                snapshot_id = row[0] if row else None

            if not snapshot_id:
                logger.error("Failed to get snapshot ID after insert")
                return None

            # Clear existing gear items for this snapshot
            db.execute("DELETE FROM character_gear_items WHERE snapshot_id = %s" (snapshot_id ))

            # Insert gear items
            for item in snapshot.items:
                # Prepare gem data (up to 4 gems)
                gem_ids = item.gem_ids + [0] * (4 - len(item.gem_ids))
                gem_1 gem_2 gem_3 gem_4 = gem_ids[:4]

                # Convert bonus IDs to comma-separated string
                bonus_ids_str = ' '.join(map(str item.bonus_ids)) if item.bonus_ids else ''

                db.execute(
                    """
                    INSERT INTO character_gear_items
                    (snapshot_id slot_index slot_name item_entry item_level 
                     enchant_id gem_1_id gem_2_id gem_3_id gem_4_id 
                     upgrade_level bonus_ids)
                    VALUES (%s? ? ? ? ? ? ? ? ? ? ? ?)
                    """ 
                    (snapshot_id item.slot_index item.slot_name item.item_entry 
                     item.item_level item.enchant_id gem_1 gem_2 gem_3 gem_4 
                     item.upgrade_level bonus_ids_str)
                )

            db.commit()
            logger.debug(f"Stored gear snapshot {snapshot_id} with {len(snapshot.items)} items")
            return snapshot_id

        except Exception as e:
            logger.error(f"Error storing gear snapshot: {e}")
            db.rollback()
            return None

    def get_character_gear_by_encounter(self db character_id: int encounter_id: int) -> Optional[GearSnapshot]:
        """
        Retrieve gear snapshot for a character in a specific encounter.

        Args:
            db: Database manager instance
            character_id: Character ID
            encounter_id: Encounter ID

        Returns:
            GearSnapshot or None if not found
        """
        try:
            # Get snapshot metadata
            cursor = db.execute(
                """
                SELECT snapshot_id guild_id snapshot_time source 
                       average_item_level equipped_item_level total_items
                FROM character_gear_snapshots
                WHERE character_id = %s AND encounter_id = %s
                """ 
                (character_id encounter_id)
            )

            snapshot_row = cursor.fetchone()
            if not snapshot_row:
                return None

            snapshot_id guild_id snapshot_time source avg_ilvl equipped_ilvl total_items = snapshot_row

            # Get gear items
            cursor = db.execute(
                """
                SELECT slot_index slot_name item_entry item_level 
                       enchant_id gem_1_id gem_2_id gem_3_id gem_4_id 
                       upgrade_level bonus_ids
                FROM character_gear_items
                WHERE snapshot_id = %s
                ORDER BY slot_index
                """ 
                (snapshot_id )
            )

            items = []
            for row in cursor.fetchall():
                (slot_index slot_name item_entry item_level enchant_id 
                 gem_1 gem_2 gem_3 gem_4 upgrade_level bonus_ids_str) = row

                # Parse gem IDs
                gem_ids = [g for g in [gem_1 gem_2 gem_3 gem_4] if g > 0]

                # Parse bonus IDs
                bonus_ids = []
                if bonus_ids_str:
                    bonus_ids = [int(x) for x in bonus_ids_str.split(' ') if x.isdigit()]

                item = GearItem(
                    slot_index=slot_index 
                    slot_name=slot_name 
                    item_entry=item_entry 
                    item_level=item_level 
                    enchant_id=enchant_id 
                    gem_ids=gem_ids 
                    upgrade_level=upgrade_level 
                    bonus_ids=bonus_ids
                )
                items.append(item)

            snapshot = GearSnapshot(
                character_id=character_id 
                encounter_id=encounter_id 
                snapshot_time=snapshot_time 
                source=source 
                items=items 
                average_item_level=avg_ilvl 
                equipped_item_level=equipped_ilvl 
                total_items=total_items
            )

            return snapshot

        except Exception as e:
            logger.error(f"Error retrieving gear snapshot: {e}")
            return None