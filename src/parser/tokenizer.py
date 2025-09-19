"""
Line tokenizer for parsing WoW combat log lines.
"""

import re
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ParsedLine:
    """Represents a parsed combat log line."""
    timestamp: datetime
    event_type: str
    base_params: List[Any]
    prefix_params: List[Any]
    suffix_params: List[Any]
    advanced_params: Dict[str, Any]
    raw_line: str


class LineTokenizer:
    """
    Tokenizes individual lines from WoW combat logs.

    Handles the CSV-like format with special delimiter handling for timestamps.
    """

    # Regex pattern to split timestamp from rest of line
    # Format: "M/D/YYYY HH:MM:SS.mmm-Z  EVENT_TYPE,params..."
    LINE_PATTERN = re.compile(r'^(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\.\d{3}[-+]\d+)\s\s(.+)$')

    # Standard base parameter count (after event type)
    BASE_PARAM_COUNT = 10  # sourceGUID through destRaidFlags

    def __init__(self):
        self.line_count = 0
        self.error_count = 0

    def parse_line(self, line: str) -> Optional[ParsedLine]:
        """
        Parse a single combat log line into structured components.

        Args:
            line: Raw line from combat log file

        Returns:
            ParsedLine object or None if parsing fails
        """
        self.line_count += 1

        # Strip any trailing whitespace
        line = line.rstrip()

        # Skip empty lines
        if not line:
            return None

        # Match the timestamp and rest of line
        match = self.LINE_PATTERN.match(line)
        if not match:
            self.error_count += 1
            return None

        timestamp_str, rest = match.groups()

        # Parse timestamp
        try:
            # Convert timestamp format "9/18/2025 20:23:42.758-4" to datetime
            # Remove timezone for simplicity (can add pytz later if needed)
            timestamp_clean = timestamp_str.rsplit('-', 1)[0].rsplit('+', 1)[0]
            timestamp = datetime.strptime(timestamp_clean, "%m/%d/%Y %H:%M:%S.%f")
        except ValueError:
            self.error_count += 1
            return None

        # Split the rest by commas
        params = self._split_params(rest)
        if not params:
            self.error_count += 1
            return None

        event_type = params[0]

        # Extract base parameters (if they exist)
        base_params = []
        remaining_params = params[1:]

        # Special handling for non-combat events
        if event_type in ['COMBAT_LOG_VERSION', 'ZONE_CHANGE', 'MAP_CHANGE',
                          'ENCOUNTER_START', 'ENCOUNTER_END',
                          'CHALLENGE_MODE_START', 'CHALLENGE_MODE_END']:
            # These events have their own specific formats
            base_params = []
            prefix_params = []
            suffix_params = remaining_params
        else:
            # Standard combat events have base parameters
            if len(remaining_params) >= self.BASE_PARAM_COUNT:
                base_params = remaining_params[:self.BASE_PARAM_COUNT]
                remaining_params = remaining_params[self.BASE_PARAM_COUNT:]
            else:
                # Not enough parameters for a standard event
                base_params = remaining_params
                remaining_params = []

            # Parse prefix and suffix specific parameters
            prefix_params, suffix_params = self._parse_event_params(event_type, remaining_params)

        return ParsedLine(
            timestamp=timestamp,
            event_type=event_type,
            base_params=base_params,
            prefix_params=prefix_params,
            suffix_params=suffix_params,
            advanced_params={},  # Will be populated by event-specific parsers
            raw_line=line
        )

    def _split_params(self, params_str: str) -> List[str]:
        """
        Split parameter string by commas, handling quoted strings.

        Args:
            params_str: Comma-separated parameter string

        Returns:
            List of parameter values
        """
        params = []
        current = []
        in_quotes = False

        for char in params_str:
            if char == '"' and (not current or current[-1] != '\\'):
                in_quotes = not in_quotes
                current.append(char)
            elif char == ',' and not in_quotes:
                params.append(''.join(current).strip())
                current = []
            else:
                current.append(char)

        # Don't forget the last parameter
        if current:
            params.append(''.join(current).strip())

        # Clean up parameters (remove quotes, convert types)
        cleaned = []
        for param in params:
            if param.startswith('"') and param.endswith('"'):
                cleaned.append(param[1:-1])
            elif param == 'nil':
                cleaned.append(None)
            else:
                # Try to convert to appropriate type
                cleaned.append(self._convert_param(param))

        return cleaned

    def _convert_param(self, param: str) -> Any:
        """
        Convert parameter string to appropriate type.

        Args:
            param: Parameter value as string

        Returns:
            Converted value (int, float, bool, or str)
        """
        if param in ['true', 'false']:
            return param == 'true'

        # Try integer
        try:
            return int(param)
        except ValueError:
            pass

        # Try float
        try:
            return float(param)
        except ValueError:
            pass

        # Try hex number (for flags)
        if param.startswith('0x'):
            try:
                return int(param, 16)
            except ValueError:
                pass

        return param

    def _parse_event_params(self, event_type: str, params: List[Any]) -> Tuple[List[Any], List[Any]]:
        """
        Split remaining parameters into prefix-specific and suffix-specific.

        Args:
            event_type: The event type (e.g., SPELL_DAMAGE)
            params: Remaining parameters after base params

        Returns:
            Tuple of (prefix_params, suffix_params)
        """
        # Determine prefix
        prefix = None
        if event_type.startswith('SWING_'):
            prefix = 'SWING'
        elif event_type.startswith('SPELL_'):
            prefix = 'SPELL'
        elif event_type.startswith('RANGE_'):
            prefix = 'RANGE'
        elif event_type.startswith('ENVIRONMENTAL_'):
            prefix = 'ENVIRONMENTAL'

        # Extract prefix-specific parameters
        prefix_params = []
        if prefix == 'SPELL' and len(params) >= 3:
            # SPELL events have spellId, spellName, spellSchool
            prefix_params = params[:3]
            params = params[3:]
        elif prefix == 'ENVIRONMENTAL' and len(params) >= 1:
            # ENVIRONMENTAL events have environmentalType
            prefix_params = params[:1]
            params = params[1:]
        # SWING and RANGE have no prefix-specific parameters

        # Remaining parameters are suffix-specific
        suffix_params = params

        return prefix_params, suffix_params

    def get_stats(self) -> Dict[str, int]:
        """
        Get parsing statistics.

        Returns:
            Dictionary with line_count and error_count
        """
        return {
            'lines_processed': self.line_count,
            'errors': self.error_count,
            'success_rate': (self.line_count - self.error_count) / max(self.line_count, 1)
        }