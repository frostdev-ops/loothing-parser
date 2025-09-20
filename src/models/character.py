"""
Character data models for proper name parsing and storage.
"""

from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class Character:
    """
    Represents a parsed character with separate name, server, and region components.

    Handles parsing of WoW character names in format:
    - "Name" (same server)
    - "Name-Server" (cross-realm, same region)
    - "Name-Server-Region" (cross-realm, cross-region)
    """

    name: str
    server: Optional[str] = None
    region: Optional[str] = None
    full_name: str = ""  # Original combined name for backward compatibility

    def __post_init__(self):
        """Set full_name if not provided."""
        if not self.full_name:
            self.full_name = self.construct_full_name()

    def construct_full_name(self) -> str:
        """Construct the full name from components."""
        parts = [self.name]
        if self.server:
            parts.append(self.server)
        if self.region:
            parts.append(self.region)
        return "-".join(parts)

    @classmethod
    def from_full_name(cls, full_name: str) -> "Character":
        """
        Parse a character name from the combat log format.

        Args:
            full_name: Character name in format "Name", "Name-Server", or "Name-Server-Region"

        Returns:
            Character object with parsed components
        """
        return cls(**parse_character_name(full_name))


def parse_character_name(full_name: str) -> dict:
    """
    Parse character name into components.

    Args:
        full_name: Character name from combat log

    Returns:
        Dictionary with name, server, region, and full_name keys

    Examples:
        >>> parse_character_name("Felica")
        {'name': 'Felica', 'server': None, 'region': None, 'full_name': 'Felica'}

        >>> parse_character_name("Felica-Duskwood")
        {'name': 'Felica', 'server': 'Duskwood', 'region': None, 'full_name': 'Felica-Duskwood'}

        >>> parse_character_name("Felica-Duskwood-US")
        {'name': 'Felica', 'server': 'Duskwood', 'region': 'US', 'full_name': 'Felica-Duskwood-US'}
    """
    if not full_name:
        return {'name': '', 'server': None, 'region': None, 'full_name': full_name}

    # Clean the name (remove quotes if present)
    clean_name = full_name.strip('"')

    # Split by hyphens
    parts = clean_name.split('-')

    # Handle different cases
    if len(parts) == 1:
        # Just a name (same server)
        return {
            'name': parts[0],
            'server': None,
            'region': None,
            'full_name': clean_name
        }
    elif len(parts) == 2:
        # Name-Server (cross-realm, same region)
        return {
            'name': parts[0],
            'server': parts[1],
            'region': None,
            'full_name': clean_name
        }
    elif len(parts) >= 3:
        # Name-Server-Region (cross-realm, cross-region)
        # Handle names with multiple hyphens by treating last part as region
        # and second-to-last as server
        return {
            'name': '-'.join(parts[:-2]) if len(parts) > 3 else parts[0],
            'server': parts[-2],
            'region': parts[-1],
            'full_name': clean_name
        }

    # Fallback (shouldn't happen)
    return {
        'name': clean_name,
        'server': None,
        'region': None,
        'full_name': clean_name
    }


def is_valid_region(region: str) -> bool:
    """
    Check if a region code is valid.

    Args:
        region: Region code to validate

    Returns:
        True if valid region code
    """
    valid_regions = {'US', 'EU', 'KR', 'CN', 'TW'}
    return region.upper() in valid_regions


def normalize_server_name(server: str) -> str:
    """
    Normalize server name for consistent storage.

    Args:
        server: Server name to normalize

    Returns:
        Normalized server name
    """
    if not server:
        return server

    # Remove common prefixes/suffixes and normalize case
    normalized = server.strip()

    # Convert to title case for consistency
    return normalized.title()


def normalize_region_code(region: str) -> str:
    """
    Normalize region code for consistent storage.

    Args:
        region: Region code to normalize

    Returns:
        Normalized region code (uppercase)
    """
    if not region:
        return region

    return region.upper()