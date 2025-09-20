#!/usr/bin/env python3
"""Quick test to understand combat gaps."""

from datetime import datetime

# Sample of timestamps from the log
timestamps = [
    "9/15/2025 21:30:33.582-4",
    "9/15/2025 21:30:35.931-4",
    "9/15/2025 21:30:39.606-4",
    "9/15/2025 21:30:41.610-4",
    "9/15/2025 21:30:44.878-4",
    "9/15/2025 21:30:46.872-4",
    "9/15/2025 21:30:48.871-4",
    # Big gap here
    "9/15/2025 21:31:07.514-4",
    "9/15/2025 21:31:07.997-4",
    "9/15/2025 21:31:09.511-4",
    "9/15/2025 21:31:14.803-4",
    "9/15/2025 21:31:16.801-4",
    "9/15/2025 21:31:20.524-4",
    "9/15/2025 21:31:22.819-4",
    "9/15/2025 21:31:24.622-4",
    "9/15/2025 21:31:26.937-4",
    "9/15/2025 21:31:28.943-4",
    # Another gap
    "9/15/2025 21:31:45.000-4",
    "9/15/2025 21:31:47.123-4",
]

# Parse timestamps
parsed = []
for ts in timestamps:
    # Remove timezone
    ts_clean = ts.rsplit("-", 1)[0]
    dt = datetime.strptime(ts_clean, "%m/%d/%Y %H:%M:%S.%f")
    parsed.append(dt)

# Analyze gaps
gaps = []
for i in range(1, len(parsed)):
    gap = (parsed[i] - parsed[i-1]).total_seconds()
    gaps.append(gap)
    if gap > 3.0:  # 3 second threshold
        print(f"Combat break detected: {gap:.1f}s gap at {parsed[i].strftime('%H:%M:%S')}")

print(f"\nGap statistics:")
print(f"  Total events: {len(parsed)}")
print(f"  Average gap: {sum(gaps)/len(gaps):.2f}s")
print(f"  Max gap: {max(gaps):.1f}s")
print(f"  Gaps > 3s: {sum(1 for g in gaps if g > 3.0)}")
print(f"  Gaps > 5s: {sum(1 for g in gaps if g > 5.0)}")

# Detect combat periods with 3s threshold
combat_periods = []
period_start = parsed[0]
last_time = parsed[0]

for i in range(1, len(parsed)):
    gap = (parsed[i] - last_time).total_seconds()

    if gap > 3.0:
        # End current period
        duration = (last_time - period_start).total_seconds()
        combat_periods.append((period_start, last_time, duration))
        # Start new period
        period_start = parsed[i]

    last_time = parsed[i]

# Add final period
duration = (last_time - period_start).total_seconds()
combat_periods.append((period_start, last_time, duration))

print(f"\nCombat periods detected (3s gap threshold):")
for i, (start, end, duration) in enumerate(combat_periods, 1):
    print(f"  Period {i}: {start.strftime('%H:%M:%S')} - {end.strftime('%H:%M:%S')} ({duration:.1f}s)")