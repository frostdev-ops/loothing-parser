#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '/app')

try:
    from src.database.schema import DatabaseManager, create_tables

    # Create database
    db = DatabaseManager("/tmp/test.db")
    create_tables(db)

    # Check if combat_dps column exists
    cursor = db.execute("PRAGMA table_info(character_metrics)")
    columns = [row[1] for row in cursor.fetchall()]

    print(f"character_metrics columns: {columns}")

    if "combat_dps" in columns:
        print("✓ combat_dps column exists")
    else:
        print("✗ combat_dps column missing")

    if "combat_hps" in columns:
        print("✓ combat_hps column exists")
    else:
        print("✗ combat_hps column missing")

    # Try creating the problematic index
    db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_combat_performance ON character_metrics(combat_dps DESC, combat_hps DESC)")
    print("✓ Index creation successful")

    db.close()
    print("✓ Schema test completed successfully")

except Exception as e:
    print(f"✗ Schema test failed: {e}")
    import traceback
    traceback.print_exc()