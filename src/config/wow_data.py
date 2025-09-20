"""
World of Warcraft data mappings and configurations.

This module contains configurable mappings for various WoW game data including
difficulty levels, specializations, affixes, and other game constants.
"""

from typing import Dict, Set
from enum import IntEnum


class DifficultyID(IntEnum):
    """WoW Difficulty IDs as used in combat logs."""

    # Dungeons
    DUNGEON_NORMAL = 1
    DUNGEON_HEROIC = 2
    DUNGEON_MYTHIC = 23
    DUNGEON_TIMEWALKING = 24
    DUNGEON_CHALLENGE = 8  # Challenge Mode (old M+)

    # Raids - Classic sizes
    RAID_10_NORMAL = 3
    RAID_25_NORMAL = 4
    RAID_10_HEROIC = 5
    RAID_25_HEROIC = 6

    # Raids - Flexible
    RAID_LFR = 17
    RAID_NORMAL = 14
    RAID_HEROIC = 15
    RAID_MYTHIC = 16

    # Special
    RAID_40 = 9
    RAID_TIMEWALKING = 33
    RAID_EVENT = 18

    # PvP
    PVP_BATTLEGROUND = 11
    PVP_ARENA = 12
    PVP_RATED_BATTLEGROUND = 13

    # Scenarios
    SCENARIO_NORMAL = 7
    SCENARIO_HEROIC = 19


# Configurable difficulty name mappings
DIFFICULTY_NAMES: Dict[int, str] = {
    # Dungeons
    1: "Normal",
    2: "Heroic",
    23: "Mythic",
    24: "Timewalking",
    8: "Challenge Mode",

    # Raids - Classic
    3: "10 Normal",
    4: "25 Normal",
    5: "10 Heroic",
    6: "25 Heroic",

    # Raids - Modern
    17: "LFR",
    14: "Normal",
    15: "Heroic",
    16: "Mythic",

    # Raids - Special
    9: "40 Player",
    33: "Timewalking",
    18: "Event",

    # PvP
    11: "Battleground",
    12: "Arena",
    13: "Rated Battleground",

    # Scenarios
    7: "Scenario",
    19: "Heroic Scenario",

    # Legacy
    20: "Mythic Keystone",  # Old M+ designation
    167: "Torghast",
    168: "Path of Ascension",

    # Add any unknown IDs you encounter here
}


# Raid difficulties (for encounter categorization)
RAID_DIFFICULTIES: Set[int] = {
    3, 4, 5, 6,  # Classic 10/25
    14, 15, 16, 17,  # Modern LFR/Normal/Heroic/Mythic
    9, 33, 18  # Special
}


# Dungeon difficulties
DUNGEON_DIFFICULTIES: Set[int] = {
    1, 2, 8, 23, 24
}


# Tank specializations
TANK_SPECS: Dict[int, str] = {
    # Death Knight
    250: "Blood",

    # Demon Hunter
    581: "Vengeance",

    # Druid
    104: "Guardian",

    # Monk
    268: "Brewmaster",

    # Paladin
    66: "Protection",

    # Warrior
    73: "Protection",
}


# Healer specializations
HEALER_SPECS: Dict[int, str] = {
    # Druid
    105: "Restoration",

    # Monk
    270: "Mistweaver",

    # Paladin
    65: "Holy",

    # Priest
    256: "Discipline",
    257: "Holy",

    # Shaman
    264: "Restoration",

    # Evoker
    1468: "Preservation",
    1473: "Augmentation",  # Can be support/healer hybrid
}


# All specializations (including DPS)
ALL_SPECS: Dict[int, str] = {
    # Death Knight
    250: "Blood",
    251: "Frost",
    252: "Unholy",

    # Demon Hunter
    577: "Havoc",
    581: "Vengeance",

    # Druid
    102: "Balance",
    103: "Feral",
    104: "Guardian",
    105: "Restoration",

    # Evoker
    1467: "Devastation",
    1468: "Preservation",
    1473: "Augmentation",

    # Hunter
    253: "Beast Mastery",
    254: "Marksmanship",
    255: "Survival",

    # Mage
    62: "Arcane",
    63: "Fire",
    64: "Frost",

    # Monk
    268: "Brewmaster",
    269: "Windwalker",
    270: "Mistweaver",

    # Paladin
    65: "Holy",
    66: "Protection",
    70: "Retribution",

    # Priest
    256: "Discipline",
    257: "Holy",
    258: "Shadow",

    # Rogue
    259: "Assassination",
    260: "Outlaw",
    261: "Subtlety",

    # Shaman
    262: "Elemental",
    263: "Enhancement",
    264: "Restoration",

    # Warlock
    265: "Affliction",
    266: "Demonology",
    267: "Destruction",

    # Warrior
    71: "Arms",
    72: "Fury",
    73: "Protection",
}


# Mythic+ Affixes (Season 1 - The War Within)
MYTHIC_PLUS_AFFIXES: Dict[int, str] = {
    # Level 2+ (rotating weekly)
    9: "Tyrannical",
    10: "Fortified",

    # Level 5+ (rotating weekly)
    3: "Volcanic",
    4: "Necrotic",
    6: "Raging",
    7: "Bolstering",
    8: "Sanguine",
    11: "Bursting",
    13: "Explosive",
    14: "Quaking",
    122: "Inspiring",
    123: "Spiteful",
    124: "Storming",
    134: "Entangling",
    135: "Afflicted",
    136: "Incorporeal",

    # Level 10+ (seasonal)
    148: "Xal'atath's Bargain: Ascendant",
    158: "Xal'atath's Bargain: Devour",
    159: "Xal'atath's Bargain: Voidbound",
    160: "Xal'atath's Bargain: Oblivion",

    # Legacy affixes (for old logs)
    2: "Skittish",
    5: "Teeming",
    12: "Grievous",
    16: "Infested",
    117: "Reaping",
    119: "Beguiling",
    120: "Awakened",
    121: "Prideful",
    128: "Tormented",
    129: "Encrypted",
    130: "Shrouded",
    131: "Thundering",
}


# Major cooldowns/buffs to track
MAJOR_COOLDOWNS: Dict[int, str] = {
    # Bloodlust effects
    2825: "Bloodlust",
    32182: "Heroism",
    80353: "Time Warp",
    264667: "Primal Rage",
    390386: "Fury of the Aspects",
    178207: "Drums of Fury",
    230935: "Drums of the Mountain",
    256740: "Drums of the Maelstrom",

    # Power Infusion
    10060: "Power Infusion",

    # Major defensive cooldowns
    31850: "Ardent Defender",
    86659: "Guardian of Ancient Kings",
    33206: "Pain Suppression",
    47788: "Guardian Spirit",
    6940: "Blessing of Sacrifice",
    102342: "Ironbark",

    # Battle resurrections
    20484: "Rebirth",
    61999: "Raise Ally",
    20707: "Soulstone",
    95750: "Intercession",
    361227: "Return",
}


# Common consumables
FLASK_IDS: Set[int] = {
    # The War Within flasks
    431972, 431973, 431974, 431975, 431976, 431977,

    # Dragonflight flasks (for older logs)
    370652, 370653, 370654, 370655, 371172, 371204, 371339, 371354, 371386,
}


FOOD_BUFF_IDS: Set[int] = {
    # The War Within food
    462854,  # Skyfury (Haste food)
    462855,  # Blessed Recovery (Versatility food)
    462856,  # Critical Strike food
    462857,  # Mastery food

    # Well Fed generic buffs
    104273,  # Well Fed (various foods give this)
}


# Augment runes
AUGMENT_RUNE_IDS: Set[int] = {
    # The War Within
    452925,  # Crystallized Augment Rune

    # Dragonflight (for older logs)
    393438,  # Draconic Augment Rune
}


def get_difficulty_name(difficulty_id: int) -> str:
    """
    Get the human-readable name for a difficulty ID.

    Args:
        difficulty_id: WoW difficulty ID from combat log

    Returns:
        Human-readable difficulty name
    """
    return DIFFICULTY_NAMES.get(difficulty_id, f"Unknown ({difficulty_id})")


def get_spec_name(spec_id: int) -> str:
    """
    Get the spec name from spec ID.

    Args:
        spec_id: WoW specialization ID

    Returns:
        Specialization name
    """
    return ALL_SPECS.get(spec_id, f"Unknown Spec ({spec_id})")


def is_tank_spec(spec_id: int) -> bool:
    """Check if a spec ID is a tank specialization."""
    return spec_id in TANK_SPECS


def is_healer_spec(spec_id: int) -> bool:
    """Check if a spec ID is a healer specialization."""
    return spec_id in HEALER_SPECS


def is_raid_difficulty(difficulty_id: int) -> bool:
    """Check if a difficulty ID represents a raid."""
    return difficulty_id in RAID_DIFFICULTIES


def is_dungeon_difficulty(difficulty_id: int) -> bool:
    """Check if a difficulty ID represents a dungeon."""
    return difficulty_id in DUNGEON_DIFFICULTIES


def get_affix_name(affix_id: int) -> str:
    """Get the name of a Mythic+ affix."""
    return MYTHIC_PLUS_AFFIXES.get(affix_id, f"Unknown Affix ({affix_id})")


def is_bloodlust_spell(spell_id: int) -> bool:
    """Check if a spell ID is a bloodlust effect."""
    bloodlust_spells = {2825, 32182, 80353, 264667, 390386, 178207, 230935, 256740}
    return spell_id in bloodlust_spells


def is_battle_res_spell(spell_id: int) -> bool:
    """Check if a spell ID is a battle resurrection."""
    battle_res_spells = {20484, 61999, 20707, 95750, 361227}
    return spell_id in battle_res_spells


def is_flask_buff(spell_id: int) -> bool:
    """Check if a spell ID is a flask buff."""
    return spell_id in FLASK_IDS


def is_food_buff(spell_id: int) -> bool:
    """Check if a spell ID is a food buff."""
    return spell_id in FOOD_BUFF_IDS


def is_augment_rune(spell_id: int) -> bool:
    """Check if a spell ID is an augment rune."""
    return spell_id in AUGMENT_RUNE_IDS