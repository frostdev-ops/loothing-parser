# Hierarchical M+ Encounter Structure

## Overview

The parser now properly handles hierarchical structure for Mythic+ dungeons, ensuring that dungeon bosses and trash segments are correctly nested within their parent M+ encounter instead of being displayed as separate encounters.

## Structure

```
Mythic+ Run (Parent Encounter)
├── Metadata
│   ├── Keystone Level
│   ├── Affixes
│   ├── Instance Name
│   └── Success/Timer Status
├── Fights (Child Segments)
│   ├── Trash Segment (Entrance)
│   ├── Boss Fight 1
│   ├── Trash Segment 2
│   ├── Boss Fight 2
│   ├── Trash Segment 3
│   └── ...
└── Characters & Metrics
    ├── Player Performance
    ├── Ability Breakdowns
    └── Death Analysis
```

## Implementation Details

### Event Processing Logic

1. **CHALLENGE_MODE_START**: Creates a new M+ parent encounter
   - Initializes with keystone level and affixes
   - Automatically starts an initial trash segment

2. **ENCOUNTER_START within M+**: Creates a boss fight within the M+ run
   - Ends the current trash segment
   - Starts a new boss fight marked with `is_boss = True`
   - Does NOT create a separate encounter

3. **ENCOUNTER_END within M+**: Ends the boss fight
   - Marks boss success/failure
   - Starts a new trash segment for the next area

4. **CHALLENGE_MODE_END**: Finalizes the M+ run
   - Sets overall success and timer status
   - Ends any open fight segments

### Key Changes

1. **Modified `UnifiedSegmenter.process_event()`**:
   - Checks if we're in a M+ run before processing ENCOUNTER_START/END
   - Routes dungeon bosses to M+-specific handlers

2. **Added Boss/Trash Handlers**:
   - `_start_dungeon_boss()`: Creates boss fight within M+
   - `_end_dungeon_boss()`: Ends boss and starts next trash segment

3. **Enhanced Fight Model**:
   - Added `is_boss` and `is_trash` flags
   - Fight type included in serialization

## Usage

### Accessing M+ Structure

```python
# Get all encounters
encounters = segmenter.get_encounters()

# Filter for M+ runs
mplus_runs = [e for e in encounters if e.encounter_type == EncounterType.MYTHIC_PLUS]

# Access fights within M+ run
for mplus in mplus_runs:
    print(f"M+ Run: {mplus.encounter_name} +{mplus.keystone_level}")

    for fight in mplus.fights:
        if fight.is_boss:
            print(f"  Boss: {fight.fight_name}")
        elif fight.is_trash:
            print(f"  Trash: {fight.fight_name}")
```

### JSON Output Structure

```json
{
  "encounter_type": "mythic_plus",
  "encounter_name": "The Dawnbreaker",
  "keystone_level": 10,
  "fights": [
    {
      "fight_id": 1,
      "fight_name": "The Dawnbreaker - Trash (Entrance)",
      "fight_type": "trash",
      "duration": 120.5
    },
    {
      "fight_id": 2,
      "fight_name": "Boss: Speaker Shadowcrown",
      "fight_type": "boss",
      "duration": 85.3,
      "success": true
    },
    {
      "fight_id": 3,
      "fight_name": "The Dawnbreaker - Trash (2)",
      "fight_type": "trash",
      "duration": 90.2
    }
  ]
}
```

## Benefits

1. **Proper Hierarchy**: Dungeon content is correctly grouped under M+ runs
2. **Clear Fight Types**: Easy to distinguish bosses from trash
3. **Accurate Metrics**: Character performance tracked per-fight within the run
4. **Better Analysis**: Can analyze boss vs trash performance separately

## Testing

Use `test_mplus_simple.py` to verify the hierarchical structure:

```bash
python test_mplus_simple.py
```

This will process a combat log and display the M+ hierarchy, confirming that:
- M+ runs are parent encounters
- Dungeon bosses are child fights within the M+ run
- Trash segments are properly tracked between bosses
- No orphaned dungeon encounters exist