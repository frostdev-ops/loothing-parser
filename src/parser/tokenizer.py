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
    LINE_PATTERN = re.compile(
        r"^(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\.\d{3}[-+]\d+)\s\s(.+)$"
    )

    # Standard base parameter count (after event type)
    BASE_PARAM_COUNT = 8  # sourceGUID through destRaidFlags

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
            timestamp_clean = timestamp_str.rsplit("-", 1)[0].rsplit("+", 1)[0]
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
        if event_type in [
            "COMBAT_LOG_VERSION",
            "ZONE_CHANGE",
            "MAP_CHANGE",
            "ENCOUNTER_START",
            "ENCOUNTER_END",
            "CHALLENGE_MODE_START",
            "CHALLENGE_MODE_END",
            "COMBATANT_INFO",
        ]:
            # These events have their own specific formats
            base_params = []
            prefix_params = []
            suffix_params = remaining_params
        else:
            # Standard combat events have base parameters
            if len(remaining_params) >= self.BASE_PARAM_COUNT:
                base_params = remaining_params[: self.BASE_PARAM_COUNT]
                remaining_params = remaining_params[self.BASE_PARAM_COUNT :]
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
            raw_line=line,
        )

    def _split_params(self, params_str: str) -> List[str]:
        """
        Split parameter string by commas, handling quoted strings and nested structures.

        Args:
            params_str: Comma-separated parameter string

        Returns:
            List of parameter values
        """
        params = []
        current = []
        in_quotes = False
        bracket_depth = 0
        paren_depth = 0

        for char in params_str:
            if char == '"' and (not current or current[-1] != "\\"):
                in_quotes = not in_quotes
                current.append(char)
            elif not in_quotes:
                if char == "[":
                    bracket_depth += 1
                    current.append(char)
                elif char == "]":
                    bracket_depth -= 1
                    current.append(char)
                elif char == "(":
                    paren_depth += 1
                    current.append(char)
                elif char == ")":
                    paren_depth -= 1
                    current.append(char)
                elif char == "," and bracket_depth == 0 and paren_depth == 0:
                    # Only split on commas at top level
                    params.append("".join(current).strip())
                    current = []
                else:
                    current.append(char)
            else:
                current.append(char)

        # Don't forget the last parameter
        if current:
            params.append("".join(current).strip())

        # Clean up parameters (remove quotes, convert types, parse nested structures)
        cleaned = []
        for param in params:
            if param.startswith('"') and param.endswith('"'):
                cleaned.append(param[1:-1])
            elif param == "nil":
                cleaned.append(None)
            elif param.startswith("[") and param.endswith("]"):
                # Parse array
                cleaned.append(self._parse_array(param))
            elif param.startswith("(") and param.endswith(")"):
                # Parse tuple
                cleaned.append(self._parse_tuple(param))
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
        if param in ["true", "false"]:
            return param == "true"

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
        if param.startswith("0x"):
            try:
                return int(param, 16)
            except ValueError:
                pass

        return param

    def _parse_array(self, array_str: str) -> List[Any]:
        """
        Parse array string into Python list.

        Args:
            array_str: String representation of array like "[1,2,3]" or "[(1,2),(3,4)]"

        Returns:
            Parsed list
        """
        # Remove outer brackets
        content = array_str[1:-1].strip()

        if not content:
            return []

        # Split by commas at top level only
        elements = []
        current = []
        paren_depth = 0
        bracket_depth = 0
        in_quotes = False

        for char in content:
            if char == '"' and (not current or current[-1] != "\\"):
                in_quotes = not in_quotes
                current.append(char)
            elif not in_quotes:
                if char == "(":
                    paren_depth += 1
                    current.append(char)
                elif char == ")":
                    paren_depth -= 1
                    current.append(char)
                elif char == "[":
                    bracket_depth += 1
                    current.append(char)
                elif char == "]":
                    bracket_depth -= 1
                    current.append(char)
                elif char == "," and paren_depth == 0 and bracket_depth == 0:
                    elements.append("".join(current).strip())
                    current = []
                else:
                    current.append(char)
            else:
                current.append(char)

        # Add last element
        if current:
            elements.append("".join(current).strip())

        # Parse each element
        parsed_elements = []
        for element in elements:
            if element.startswith("(") and element.endswith(")"):
                parsed_elements.append(self._parse_tuple(element))
            elif element.startswith("[") and element.endswith("]"):
                parsed_elements.append(self._parse_array(element))
            else:
                parsed_elements.append(self._convert_param(element))

        return parsed_elements

    def _parse_tuple(self, tuple_str: str) -> tuple:
        """
        Parse tuple string into Python tuple.

        Args:
            tuple_str: String representation of tuple like "(1,2,3)"

        Returns:
            Parsed tuple
        """
        # Remove outer parentheses
        content = tuple_str[1:-1].strip()

        if not content:
            return ()

        # Split by commas at top level only
        elements = []
        current = []
        paren_depth = 0
        bracket_depth = 0
        in_quotes = False

        for char in content:
            if char == '"' and (not current or current[-1] != "\\"):
                in_quotes = not in_quotes
                current.append(char)
            elif not in_quotes:
                if char == "(":
                    paren_depth += 1
                    current.append(char)
                elif char == ")":
                    paren_depth -= 1
                    current.append(char)
                elif char == "[":
                    bracket_depth += 1
                    current.append(char)
                elif char == "]":
                    bracket_depth -= 1
                    current.append(char)
                elif char == "," and paren_depth == 0 and bracket_depth == 0:
                    elements.append("".join(current).strip())
                    current = []
                else:
                    current.append(char)
            else:
                current.append(char)

        # Add last element
        if current:
            elements.append("".join(current).strip())

        # Parse each element
        parsed_elements = []
        for element in elements:
            if element.startswith("(") and element.endswith(")"):
                parsed_elements.append(self._parse_tuple(element))
            elif element.startswith("[") and element.endswith("]"):
                parsed_elements.append(self._parse_array(element))
            else:
                parsed_elements.append(self._convert_param(element))

        return tuple(parsed_elements)

    def _parse_event_params(
        self, event_type: str, params: List[Any]
    ) -> Tuple[List[Any], List[Any]]:
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
        if event_type.startswith("SWING_"):
            prefix = "SWING"
        elif event_type.startswith("SPELL_"):
            prefix = "SPELL"
        elif event_type.startswith("RANGE_"):
            prefix = "RANGE"
        elif event_type.startswith("ENVIRONMENTAL_"):
            prefix = "ENVIRONMENTAL"

        # Extract prefix-specific parameters
        prefix_params = []
        if prefix == "SPELL" and len(params) >= 3:
            # SPELL events have spellId, spellName, spellSchool
            prefix_params = params[:3]
            params = params[3:]
        elif prefix == "ENVIRONMENTAL" and len(params) >= 1:
            # ENVIRONMENTAL events have environmentalType
            prefix_params = params[:1]
            params = params[1:]
        # SWING and RANGE have no prefix-specific parameters

        # Handle Advanced Combat Logging (ACL) parameters
        suffix_params = self._handle_acl_params(event_type, params)

        return prefix_params, suffix_params

    def _handle_acl_params(self, event_type: str, params: List[Any]) -> List[Any]:
        """
        Handle Advanced Combat Logging (ACL) parameters.

        ACL inserts 18 additional parameters before damage/heal amounts:
        unitGUID, ownerGUID, currentHP, maxHP, attackPower, spellPower, armor,
        absorb, powerType1-7 (7 params), x, y, map, facing, ilvl

        Args:
            event_type: The event type
            params: Parameters after prefix params

        Returns:
            Actual suffix parameters with ACL params skipped
        """
        # Events that have damage/heal amounts that could be affected by ACL
        acl_affected_events = [
            "DAMAGE", "HEAL", "ABSORBED", "MISSED", "HEALED",
            "ENERGIZE", "DRAIN", "LEECH"
        ]

        # Check if this event type could have ACL parameters
        has_acl_suffix = any(suffix in event_type for suffix in acl_affected_events)

        if not has_acl_suffix:
            # Non-ACL affected events, return params as-is
            return params

        # Detect ACL presence by parameter count
        # For SPELL_DAMAGE with ACL: we expect at least 18 ACL + 6+ damage params = 24+ total
        # For SWING_DAMAGE with ACL: we expect at least 18 ACL + 6+ damage params = 24+ total
        # For SPELL_HEAL with ACL: we expect at least 18 ACL + 4+ heal params = 22+ total

        expected_min_acl_params = 22  # Conservative threshold

        if len(params) >= expected_min_acl_params:
            # Likely has ACL parameters - skip first 18 params
            return params[18:]
        else:
            # No ACL or insufficient params, return as-is
            return params

    def get_stats(self) -> Dict[str, int]:
        """
        Get parsing statistics.

        Returns:
            Dictionary with line_count and error_count
        """
        return {
            "lines_processed": self.line_count,
            "errors": self.error_count,
            "success_rate": (self.line_count - self.error_count) / max(self.line_count, 1),
        }
