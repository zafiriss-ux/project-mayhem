# TITAN Core Modules - Quick Reference Card

## Installation
```bash
# No external dependencies needed for core modules!
# Just ensure you're in the project directory
cd /home/user/project-mayhem
```

## Basic Imports
```python
# Core functionality
from titan.core import (
    UniversalAthleteProfile,
    DatabaseManager,
    AthleteDatabase,
    EquipmentManager,
    PeriodizationManager
)

# Utilities
from titan.utils import MathCore, SESSION_TYPES, DEFAULT_CONFIG
from titan.utils.constants import ACWR_SAFE_MIN, ACWR_SAFE_MAX
```

## Quick Recipes

### Create and Configure Athlete
```python
# Create profile
athlete = UniversalAthleteProfile(name="Jane Runner")
athlete.set_demographics("F", 28, 165, 58.0)
athlete.set_hr_data(42, 185)

# Auto-calculated values
print(athlete.threshold_hr)  # 88% of max HR
print(athlete.calculate_bmr())  # Mifflin-St Jeor formula
```

### Set Race Goal
```python
pm = PeriodizationManager(athlete)
goal = pm.add_goal(
    distance_km=21.1,
    target_time_str="1:30:00",
    race_date_str="2026-04-26"
)

# Check current phase
phase = pm.calculate_phase(athlete.race_day)
# Returns: "BASE", "BUILD", "PEAK", "TAPER", or "POST_RACE"
```

### Log Training Session
```python
db = DatabaseManager()
db.save_session(
    date="2026-02-13",
    session_type="TEMPO",
    distance_km=10.0,
    duration_sec=2400,  # 40 minutes
    avg_hr=165,
    rpe=7,
    shoe_id=1,
    surface="ROAD"
)
```

### Log Morning Metrics
```python
db.save_daily_metric(
    date="2026-02-13",
    weight=75.2,
    hrv=65,
    rhr=45,
    sleep_hours=7.5,
    sleep_quality=80,
    soreness=1,
    fatigue=2,
    mood=4
)
```

### Check Training Stress Balance
```python
ctl, atl, tsb = db.get_ctl_atl_tsb()
print(f"Fitness (CTL): {ctl}")
print(f"Fatigue (ATL): {atl}")
print(f"Form (TSB): {tsb}")

# Interpretation:
# TSB -10 to +5 = Race ready
# TSB < -30 = Overtraining risk
```

### Validate Equipment Choice
```python
eq = EquipmentManager()
ok, msg = eq.check_gear(
    session_type="INTERVALS",
    shoe_id="1",
    surface="TRACK"
)

if not ok:
    print(f"BLOCKED: {msg}")
else:
    print(f"OK: {msg}")
```

### Check Readiness Status
```python
weight_status = MathCore.weight_function_Wf(
    weight=75.2,
    night_drop=0.8,
    epoc=280
)
# Returns: "STABLE", "SAFE_DROP_RULE", "EMERGENCY_MODE", etc.

system_status = MathCore.system_status_SSV(
    hrv_status="NORMAL",
    sleep_score=75,
    pain=1,
    weight=75.2,
    epoc=280,
    night_drop=0.8
)
# Returns: "STABLE", "UNSTABLE", or "CRITICAL"
```

### Manage Multiple Athletes
```python
adb = AthleteDatabase()

# Create athletes
athlete1 = adb.create_athlete("Runner One", "M", 30, 180, 75)
athlete2 = adb.create_athlete("Runner Two", "F", 28, 165, 58)

# Switch between them
adb.switch_athlete(athlete1.athlete_id)
current = adb.get_current()

# List all
for a in adb.list_all():
    print(f"{a['name']}: {a['goal']}")
```

## Constants Reference

### Session Types
```python
SESSION_TYPES = [
    "EASY",         # Low intensity, aerobic base
    "LONG_RUN",     # Extended duration, fatigue resistance
    "TEMPO",        # Threshold pace, lactate clearance
    "INTERVALS",    # High intensity, VO2max work
    "VO2_MAX",      # Maximum aerobic power
    "HAMMER",       # Race-specific intensity
    "RECOVERY",     # Active recovery, very easy
    "PROGRESSIVE",  # Progressive buildup
    "RACE"          # Race day
]
```

### Training Load Zones
```python
EASY_SESSIONS = ["EASY", "RECOVERY"]
MODERATE_SESSIONS = ["TEMPO", "LONG_RUN", "PROGRESSIVE"]
HARD_SESSIONS = ["INTERVALS", "VO2_MAX", "HAMMER"]
```

### ACWR Thresholds
```python
ACWR_SAFE_MIN = 0.8   # Below = detraining risk
ACWR_SAFE_MAX = 1.3   # Above = injury risk
ACWR_INJURY_RISK = 1.5  # >1.5 = 2-4x injury risk
```

### TSB Ranges
```python
TSB_RACE_READY_MIN = -10  # Fresh enough
TSB_RACE_READY_MAX = 5    # Not detrained
TSB_OVERTRAINED = -30     # Danger zone
```

### HR Drift Thresholds
```python
HR_DRIFT_EXCELLENT = 5.0   # <5% = excellent aerobic base
HR_DRIFT_WARNING = 10.0    # >10% = decoupling issue
```

## Database Schema

### daily_metrics
```sql
date TEXT           -- ISO format: "2026-02-13"
weight_kg REAL      -- Weight in kilograms
hrv_rmssd REAL      -- HRV in milliseconds
resting_hr INTEGER  -- Resting heart rate (bpm)
sleep_hours REAL    -- Sleep duration
sleep_quality INT   -- 0-100 score
soreness INT        -- 0-5 scale
fatigue_level INT   -- 0-5 scale
mood INT            -- 0-5 scale
notes TEXT          -- Optional notes
```

### training_log
```sql
date TEXT           -- Session date
session_type TEXT   -- "EASY", "TEMPO", etc.
distance_km REAL    -- Distance in kilometers
duration_sec INT    -- Duration in seconds
avg_hr INT          -- Average heart rate
max_hr INT          -- Maximum heart rate
rpe INT             -- Rate of Perceived Exertion (1-10)
training_load INT   -- Calculated: RPE × minutes
shoe_id INT         -- Foreign key to gear_usage
surface TEXT        -- "TRACK", "ROAD", "TRAIL", etc.
temperature_c REAL  -- Temperature in Celsius
notes TEXT          -- Optional notes
```

### gear_usage
```sql
shoe_name TEXT              -- "Nike Pegasus 40"
total_km REAL              -- Total kilometers
last_used TEXT             -- Last use date (ISO)
compression_recovery_hours  -- Hours needed (default 24)
status TEXT                -- "ACTIVE", "RETIRED"
shoe_type TEXT             -- "DAILY", "RACE", "RECOVERY"
max_km_limit REAL          -- Retirement threshold
```

## Common Patterns

### Check Before Hard Session
```python
# Morning check
status = MathCore.system_status_SSV(hrv, sleep, pain, weight, epoc, drop)
if status == "CRITICAL":
    print("ABORT: System critical. Take rest day.")
elif status == "UNSTABLE":
    print("DOWNGRADE: Convert to easy session.")
else:
    print("GO: Cleared for hard session.")
```

### Shoe Rotation Check
```python
# Before run
available, msg = db.check_shoe_availability(shoe_id)
if not available:
    print(f"Choose different shoe: {msg}")

# After run
db.update_shoe_mileage(shoe_id, distance_km, date)
```

### Phase-Based Training
```python
phase = pm.calculate_phase(athlete.race_day)

if phase == "BASE":
    print("Focus: Volume, easy pace, aerobic base")
elif phase == "BUILD":
    print("Focus: Progressive overload, threshold work")
elif phase == "PEAK":
    print("Focus: Race-specific intensity, sharpening")
elif phase == "TAPER":
    print("Focus: Volume down 40-60%, maintain intensity")
elif phase == "POST_RACE":
    print("Focus: Recovery, easy miles only")
```

## Performance Formulas

### Max HR (Tanaka Formula)
```python
max_hr = 208 - (0.7 × age)
# More accurate than 220-age for trained athletes
```

### Threshold HR
```python
threshold_hr = max_hr × 0.88
# Lactate threshold typically at 88% max HR
```

### Training Load (sRPE)
```python
training_load = rpe × duration_minutes
# Foster et al. (2001): r=0.85 with TRIMP
```

### CTL/ATL/TSB
```python
# CTL: 42-day exponential moving average (fitness)
# ATL: 7-day exponential moving average (fatigue)
# TSB: CTL - ATL (form/freshness)

ctl_decay = 2 / (42 + 1)
atl_decay = 2 / (7 + 1)
```

## Testing

### Run All Tests
```bash
python3 test_core_modules.py
```

### Test Individual Module
```python
# Test athlete profile
athlete = UniversalAthleteProfile(name="Test")
assert athlete.max_hr == 208 - (0.7 * athlete.age)

# Test serialization
data = athlete.to_dict()
athlete2 = UniversalAthleteProfile.from_dict(data)
assert athlete2.name == athlete.name
```

## Debugging

### Enable Verbose Mode
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Database Contents
```python
db = DatabaseManager()
cursor = db.conn.cursor()

# Recent sessions
cursor.execute("SELECT * FROM training_log ORDER BY date DESC LIMIT 10")
for row in cursor.fetchall():
    print(row)
```

## Common Pitfalls

### ❌ Don't
```python
# Don't use relative dates
athlete.race_day = "2026-04-26"  # WRONG: string

# Don't forget to close database
db = DatabaseManager()
# ... use db ...
# (no close) - LEAKS CONNECTION
```

### ✅ Do
```python
# Use datetime objects
from datetime import datetime
athlete.race_day = datetime(2026, 4, 26)  # CORRECT

# Always close database
db = DatabaseManager()
try:
    # ... use db ...
finally:
    db.close()  # CORRECT
```

## File Locations

```
/home/user/project-mayhem/
├── titan/
│   ├── core/
│   │   ├── athlete.py          # Athlete profiles
│   │   ├── database.py         # Data persistence
│   │   ├── equipment.py        # Gear tracking
│   │   └── periodization.py    # Training phases
│   └── utils/
│       ├── constants.py        # System constants
│       └── math_core.py        # Math utilities
├── test_core_modules.py        # Test suite
└── archive/CORE_MIGRATION_SUMMARY.md   # Full documentation (archived)
```

## Support

For detailed documentation, see:
- `archive/CORE_MIGRATION_SUMMARY.md` - Complete migration guide (archived)
- `titan/MIGRATION_CORE_MODULES.md` - Technical details
- `test_core_modules.py` - Working examples

---

**Version**: 1.0
**Last Updated**: 2026-02-13
**Status**: Production Ready ✅
