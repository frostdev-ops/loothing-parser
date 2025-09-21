# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a World of Warcraft combat log parser project designed solely to track combat data from WoWCombatLog.txt files, including player statistics and raid encounter data. Loot data, Discord bots, and other integrations are handled upstream.

## Architecture

### Core Components

The parser must implement these key architectural elements:

1. **Event Parser**: Parse individual combat log lines with dynamic schemas based on event type
   - Base parameters (11 universal fields including timestamp, event type, GUIDs)
   - Event-specific parameters based on prefix (SWING_, SPELL_, ENVIRONMENTAL_)
   - Suffix-specific parameters (_DAMAGE, _HEAL, _AURA_APPLIED, etc.)

2. **State Machine**: Build and maintain combat state from the stateless log stream
   - Combatant roster tracking via GUID dictionary
   - Aura state management (buffs/debuffs tracking)
   - Resource tracking (health, mana, etc.)

3. **Encounter Segmentation**: Split logs into analyzable units
   - Raid encounters via ENCOUNTER_START/ENCOUNTER_END
   - Mythic+ dungeons via CHALLENGE_MODE_START/CHALLENGE_MODE_END
   - Hierarchical segmentation for trash pulls between bosses

4. **Combat Data Tracking**: Focus on combat-related events
   - Track damage, healing, and other combat metrics
   - Map actions to players and encounters
   - Maintain combat statistics and metadata

## Key Data Structures

### Combat Log Format
- CSV-like format with comma separation
- Timestamp format: MM/DD/YYYY HH:MM:SS.mmm-Z
- Dynamic parameter count based on event type
- Advanced Combat Logging must be enabled for full data

### Critical Event Types for Combat Tracking
- DAMAGE and HEAL events for combat metrics
- ENCOUNTER_START/END for fight boundaries
- COMBATANT_INFO for player/pet metadata
- SPELL_SUMMON for pet ownership mapping

## Development Guidelines

### Parser Implementation Requirements
1. **Defensive Parsing**: Handle unknown parameters gracefully without crashing
2. **Stateful Processing**: Maintain state across entire log file
3. **Pet Attribution**: Map pet/guardian actions to owners via SPELL_SUMMON and COMBATANT_INFO
4. **Performance Metrics**: Calculate eDPS/eHPS using elapsed time, not active time

### Data Quality Considerations
- Logs may be incomplete (started mid-session)
- Advanced Combat Logging may not always be enabled
- Handle orphaned pets when SPELL_SUMMON events are missing
- Account for overhealing in healing calculations

## Testing with Example Data

The `examples/` directory contains 8 WoWCombatLog files for testing:
- Various raid encounters and content types
- Different file sizes and durations
- Real combat data with all event types

When developing, use these logs to:
- Test parser resilience with different formats
- Verify state machine accuracy
- Validate combat tracking across encounters
- Ensure performance with large files

## Integration Points

### Upstream Integration
The parser output should be structured for upstream systems:
- Combat data should be queryable by player, encounter, and metrics
- Player statistics should aggregate across multiple logs
- Upstream systems handle loot data, Discord bots, and other features

### Database Schema
Design output format compatible with:
- Player tracking (name, class, spec, realm)
- Encounter tracking (boss, difficulty, date)
- Combat records (damage, healing, actions)
- Metric aggregations (eDPS, eHPS, etc.)