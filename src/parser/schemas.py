"""
Event schemas for validation and parameter mapping.
"""

from typing import Dict, List, Tuple, Optional


class EventSchema:
    """
    Defines the expected parameter structure for different event types.
    """

    # Base parameter names (common to most combat events)
    BASE_PARAMS = [
        'hide_caster', 'source_guid', 'source_name', 'source_flags',
        'source_raid_flags', 'dest_guid', 'dest_name', 'dest_flags',
        'dest_raid_flags'
    ]

    # Prefix-specific parameter counts
    PREFIX_PARAMS = {
        'SPELL': ['spell_id', 'spell_name', 'spell_school'],
        'ENVIRONMENTAL': ['environmental_type'],
        'SWING': [],
        'RANGE': []
    }

    # Suffix-specific parameter schemas
    SUFFIX_PARAMS = {
        '_DAMAGE': [
            'amount', 'overkill', 'school', 'resisted', 'blocked',
            'absorbed', 'critical', 'glancing', 'crushing'
        ],
        '_MISSED': [
            'miss_type', 'is_offhand', 'amount_missed', 'critical'
        ],
        '_HEAL': [
            'amount', 'overhealing', 'absorbed', 'critical'
        ],
        '_ENERGIZE': [
            'amount', 'overenergize', 'power_type', 'max_power'
        ],
        '_AURA_APPLIED': ['aura_type'],
        '_AURA_REMOVED': ['aura_type'],
        '_AURA_APPLIED_DOSE': ['aura_type', 'stacks'],
        '_AURA_REMOVED_DOSE': ['aura_type', 'stacks'],
        '_AURA_REFRESH': ['aura_type'],
        '_CAST_START': [],
        '_CAST_SUCCESS': [],
        '_CAST_FAILED': ['failed_type'],
        '_INTERRUPT': ['interrupted_spell_id', 'interrupted_spell_name', 'interrupted_spell_school'],
        '_DISPEL': ['dispelled_spell_id', 'dispelled_spell_name', 'dispelled_spell_school', 'aura_type'],
        '_ABSORBED': [
            'absorb_source_guid', 'absorb_source_name', 'absorb_source_flags',
            'absorb_source_raid_flags', 'absorb_spell_id', 'absorb_spell_name',
            'absorb_spell_school', 'amount', 'critical'
        ]
    }

    # Advanced parameter schemas (after suffix params)
    ADVANCED_PARAMS = {
        # These appear in Advanced Combat Logging mode
        '_DAMAGE': [
            'source_current_hp', 'source_max_hp', 'source_attack_power',
            'source_spell_power', 'source_armor', 'source_absorb',
            'source_power_type', 'source_current_power', 'source_max_power',
            'source_power_cost', 'source_position_x', 'source_position_y',
            'source_ui_map_id', 'source_facing', 'dest_current_hp',
            'dest_max_hp', 'dest_attack_power', 'dest_spell_power',
            'dest_armor', 'dest_absorb', 'dest_power_type',
            'dest_current_power', 'dest_max_power', 'dest_power_cost',
            'dest_position_x', 'dest_position_y', 'dest_ui_map_id',
            'dest_facing'
        ],
        '_HEAL': [
            'source_current_hp', 'source_max_hp', 'source_attack_power',
            'source_spell_power', 'source_armor', 'source_absorb',
            'source_power_type', 'source_current_power', 'source_max_power',
            'source_power_cost', 'source_position_x', 'source_position_y',
            'source_ui_map_id', 'source_facing', 'dest_current_hp',
            'dest_max_hp', 'dest_attack_power', 'dest_spell_power',
            'dest_armor', 'dest_absorb', 'dest_power_type',
            'dest_current_power', 'dest_max_power', 'dest_power_cost',
            'dest_position_x', 'dest_position_y', 'dest_ui_map_id',
            'dest_facing'
        ]
    }

    # Special event schemas (non-combat events)
    SPECIAL_EVENTS = {
        'COMBAT_LOG_VERSION': [
            'version', 'advanced_log_enabled', 'build_version', 'project_id'
        ],
        'ZONE_CHANGE': [
            'zone_id', 'zone_name', 'instance_id'
        ],
        'MAP_CHANGE': [
            'ui_map_id', 'ui_map_name', 'x0', 'y0', 'x1', 'y1'
        ],
        'ENCOUNTER_START': [
            'encounter_id', 'encounter_name', 'difficulty_id', 'group_size', 'instance_id'
        ],
        'ENCOUNTER_END': [
            'encounter_id', 'encounter_name', 'difficulty_id', 'group_size',
            'success', 'duration_ms'
        ],
        'CHALLENGE_MODE_START': [
            'zone_name', 'instance_id', 'challenge_mode_id', 'keystone_level', 'affix_ids'
        ],
        'CHALLENGE_MODE_END': [
            'instance_id', 'success', 'keystone_level', 'duration_ms', 'par_value', 'final_rating'
        ],
        'PARTY_KILL': [],
        'EMOTE': ['emote_text']
    }

    @classmethod
    def get_event_schema(cls, event_type: str) -> Optional[List[str]]:
        """
        Get the expected parameter schema for an event type.

        Args:
            event_type: The event type string

        Returns:
            List of parameter names or None if unknown event
        """
        # Check if it's a special event
        if event_type in cls.SPECIAL_EVENTS:
            return cls.SPECIAL_EVENTS[event_type]

        # For combat events, build the schema from components
        schema = []

        # Add base parameters
        schema.extend(cls.BASE_PARAMS)

        # Determine prefix and add its parameters
        prefix = cls._get_event_prefix(event_type)
        if prefix in cls.PREFIX_PARAMS:
            schema.extend(cls.PREFIX_PARAMS[prefix])

        # Determine suffix and add its parameters
        suffix = cls._get_event_suffix(event_type)
        for suffix_key in cls.SUFFIX_PARAMS:
            if suffix_key in event_type:
                schema.extend(cls.SUFFIX_PARAMS[suffix_key])
                break

        return schema if schema else None

    @classmethod
    def _get_event_prefix(cls, event_type: str) -> str:
        """Extract the prefix from an event type."""
        for prefix in ['SWING', 'SPELL', 'RANGE', 'ENVIRONMENTAL']:
            if event_type.startswith(prefix + '_'):
                return prefix
        return ''

    @classmethod
    def _get_event_suffix(cls, event_type: str) -> str:
        """Extract the suffix from an event type."""
        # Find the last underscore and return everything after it
        parts = event_type.split('_')
        if len(parts) >= 2:
            # Handle multi-part suffixes like AURA_APPLIED
            if 'AURA' in event_type:
                aura_index = parts.index('AURA')
                return '_'.join(parts[aura_index:])
            # Single part suffix
            return '_' + parts[-1]
        return ''

    @classmethod
    def validate_event(cls, event_type: str, params: List) -> Tuple[bool, Optional[str]]:
        """
        Validate that an event has the expected parameters.

        Args:
            event_type: The event type string
            params: List of parameters

        Returns:
            Tuple of (is_valid, error_message)
        """
        schema = cls.get_event_schema(event_type)

        if schema is None:
            # Unknown event type - we'll allow it but log it
            return True, f"Unknown event type: {event_type}"

        # We don't require exact parameter count match
        # (logs can have extra parameters we don't know about)
        # Just check we have at least the minimum expected
        min_expected = len([p for p in schema if p not in ['critical', 'glancing', 'crushing']])

        if len(params) < min_expected:
            return False, f"Expected at least {min_expected} parameters, got {len(params)}"

        return True, None