# TITAN Core Modules Migration Report

## Overview
Successfully extracted and migrated 6 core modules from `TITAN_v50_FULL_KERNEL_FINAL.py` to the new modular structure.

## Migration Summary

### ✅ Completed Modules

#### 1. `titan/utils/constants.py`
**Purpose**: System-wide constants, session types, and configuration defaults

**Content**:
- `DEFAULT_CONFIG`: HR zones, ACWR limits, database version
- `SESSION_TYPES`: List of all session types (EASY, TEMPO, INTERVALS, etc.)
- `EASY_SESSIONS`, `MODERATE_SESSIONS`, `HARD_SESSIONS`: Training intensity categories
- `HR_ZONE_RANGES`: Heart rate zone definitions
- Weight management constants (WEIGHT_FLOOR_DEFAULT, WEIGHT_PANIC_THRESHOLD, etc.)
- Training load constants (ACWR thresholds, TSB ranges, CTL/ATL days)
- Equipment constants (shoe mileage, compression recovery)
- Glycogen depletion estimates
- Training phase durations

**Dependencies**: None (pure constants)

---

#### 2. `titan/utils/math_core.py`
**Purpose**: Mathematical utility functions for weight management and system status

**Extracted From**: Lines 752-790 of original file

**Classes**:
- `MathCore`: Static methods for weight and status calculations

**Methods**:
- `weight_function_Wf(weight, night_drop, epoc)`: Weight management state evaluation
- `system_status_SSV(hrv_status, sleep_score, pain, weight, epoc, night_drop)`: Overall readiness assessment

**Dependencies**:
- Standard library: `typing`

**Scientific Basis**:
- Weight management thresholds based on athlete-specific parameters
- HRV-guided training principles (Kiviniemi, 2007)

---

#### 3. `titan/core/athlete.py`
**Purpose**: Complete athlete profile management with demographics and physiology

**Extracted From**: Lines 116-270 of original file

**Classes**:
- `UniversalAthleteProfile`: Comprehensive athlete data model

**Key Attributes**:
- Demographics: age, gender, height, weight
- Physiological: resting_hr, max_hr, threshold_hr, vo2_max
- Training: race_day, current_goal, paces, personal_bests
- Critical Speed Model: critical_speed_m_per_s, d_prime_m
- Weight management: weight_floor, weight_ceiling, weight_panic

**Methods**:
- `set_demographics()`: Update athlete demographics with auto-calculated weight thresholds
- `set_hr_data()`: Update HR data with Tanaka formula for max HR estimation
- `calculate_bmr()`: Basal Metabolic Rate (Mifflin-St Jeor equation)
- `calculate_tdee()`: Total Daily Energy Expenditure
- `str_to_sec()`, `sec_to_str()`: Time conversion utilities
- `to_dict()`, `from_dict()`: JSON serialization

**Dependencies**:
- Standard library: `datetime`, `typing`

**Backward Compatibility**:
- Properties `resting_hr_baseline` and `vo2_max_baseline` for legacy code

---

#### 4. `titan/core/periodization.py`
**Purpose**: Race goal and training phase management

**Extracted From**: Lines 271-339 of original file

**Classes**:
- `PeriodizationManager`: Training phase calculator and goal tracker

**Methods**:
- `add_goal(distance_km, target_time_str, race_date_str)`: Create new race goal
- `calculate_phase(race_date)`: Determine training phase based on race proximity
- `complete_goal(goal_id, actual_time_str)`: Mark goal complete with suggestions

**Training Phases**:
- **BASE** (>70 days): High volume, aerobic foundation
- **BUILD** (35-70 days): Progressive overload, threshold work
- **PEAK** (10-35 days): Race-specific intensity
- **TAPER** (1-10 days): Volume reduction, maintain intensity
- **POST_RACE** (after race): Recovery and adaptation

**Dependencies**:
- Standard library: `datetime`, `typing`

**Scientific Basis**:
- Classical periodization (Bompa & Haff, 2009)
- Taper duration: 10-14 days optimal (Bosquet et al., 2007)

---

#### 5. `titan/core/equipment.py`
**Purpose**: Shoe tracking, surface analysis, and training intent validation

**Extracted From**: Lines 2473-2516 of original file

**Classes**:
- `EquipmentManager`: Shoe lifecycle and usage validation

**Methods**:
- `check_gear(session_type, shoe_id, surface)`: Validate equipment for session
- `add_shoe()`: Add new shoe to tracking
- `update_mileage()`: Update shoe kilometers
- `get_shoe_status()`: Get shoe health status
- `list_all_shoes()`: List all shoes with status

**Validation Logic**:
1. **Mileage Check**: Flag expired shoes (>max_km)
2. **Type Mismatch**: Block fast work in recovery shoes
3. **Surface Risk**: Warn about high-impact sessions on concrete

**Dependencies**:
- Standard library: `typing`

**Scientific Basis**:
- Shoe lifespan: 500-800km (Tenforde et al., 2020)
- Shoe rotation reduces injury risk by 39% (Malisoux et al., 2013)
- Surface hardness impacts loading rates (Dixon et al., 2000)

---

#### 6. `titan/core/database.py`
**Purpose**: Persistent storage for training data and athlete profiles

**Extracted From**: Lines 5304-5588 (DatabaseManager) and 619-694 (AthleteDatabase)

**Classes**:
- `DatabaseManager`: SQLite database for training data
- `AthleteDatabase`: Multi-athlete JSON storage

**DatabaseManager Tables**:
1. **daily_metrics**: Morning check-in data (weight, HRV, sleep, soreness)
2. **training_log**: Complete session history with HR, RPE, load
3. **gear_usage**: Shoe mileage and compression recovery tracking
4. **personal_bests**: PR history by distance

**Key Methods (DatabaseManager)**:
- `save_daily_metric()`: Store morning wellness data
- `save_session()`: Store training session with automatic load calculation
- `get_ctl_atl_tsb()`: Calculate Training Stress Balance (Banister model)
- `get_training_load_history()`: Retrieve historical training loads
- `add_shoe()`, `update_shoe_mileage()`: Gear management
- `check_shoe_availability()`: Validate shoe readiness (mileage + compression recovery)
- `save_personal_best()`, `get_pr()`: PR tracking

**Key Methods (AthleteDatabase)**:
- `create_athlete()`: Create new athlete profile
- `switch_athlete()`: Switch between athletes
- `get_current()`: Get active athlete
- `list_all()`: List all athletes
- `save_athlete()`, `load_all()`: Persistent storage

**Dependencies**:
- Standard library: `sqlite3`, `json`, `datetime`, `pathlib`, `typing`
- Internal: `titan.core.athlete.UniversalAthleteProfile`

**Scientific Basis**:
- CTL/ATL/TSB calculation (Banister et al., 1975; Coggan, 2003)
- sRPE training load (Foster et al., 2001)
- Foam compression recovery (Malisoux et al., 2013)

---

## Module Structure

```
titan/
├── core/
│   ├── __init__.py          ✅ Updated with exports
│   ├── athlete.py           ✅ UniversalAthleteProfile
│   ├── database.py          ✅ DatabaseManager, AthleteDatabase
│   ├── equipment.py         ✅ EquipmentManager
│   └── periodization.py     ✅ PeriodizationManager
└── utils/
    ├── __init__.py          ✅ Updated with exports
    ├── constants.py         ✅ All system constants
    └── math_core.py         ✅ MathCore utilities
```

---

## Import Examples

### Core Modules
```python
from titan.core import (
    UniversalAthleteProfile,
    DatabaseManager,
    AthleteDatabase,
    EquipmentManager,
    PeriodizationManager
)

# Create athlete
athlete = UniversalAthleteProfile(name="John Doe")
athlete.set_demographics("M", 30, 180, 75)
athlete.set_hr_data(45, 190)

# Database
db = DatabaseManager()
db.save_session(
    date="2026-02-13",
    session_type="TEMPO",
    distance_km=10.0,
    duration_sec=2400,
    rpe=7
)

# Equipment
eq = EquipmentManager()
ok, msg = eq.check_gear("INTERVALS", "1", "TRACK")

# Periodization
pm = PeriodizationManager(athlete)
pm.add_goal(21.1, "1:30:00", "2026-04-26")
phase = pm.calculate_phase(athlete.race_day)
```

### Utils
```python
from titan.utils import (
    MathCore,
    SESSION_TYPES,
    ACWR_SAFE_MIN,
    ACWR_SAFE_MAX,
    DEFAULT_CONFIG
)

# Weight check
status = MathCore.weight_function_Wf(74.8, 1.0, 300)

# System status
readiness = MathCore.system_status_SSV(
    hrv_status="NORMAL",
    sleep_score=75,
    pain=1,
    weight=75.2,
    epoc=280,
    night_drop=0.8
)

# Session types
for session in SESSION_TYPES:
    print(session)  # EASY, TEMPO, INTERVALS, ...
```

---

## Syntax Validation

All modules passed Python syntax validation:
- ✅ `titan/utils/constants.py`
- ✅ `titan/utils/math_core.py`
- ✅ `titan/core/athlete.py`
- ✅ `titan/core/periodization.py`
- ✅ `titan/core/equipment.py`
- ✅ `titan/core/database.py`

---

## Dependencies Summary

### External Dependencies (required in environment)
- `sqlite3` (standard library)
- `json` (standard library)
- `datetime` (standard library)
- `pathlib` (standard library)
- `typing` (standard library)

**No external pip packages required for core modules!**

### Internal Dependencies
- `titan.core.database` imports `titan.core.athlete.UniversalAthleteProfile`

---

## Code Quality Improvements

### ✅ Added Features
1. **Comprehensive docstrings**: Every class and method documented
2. **Type hints**: Full typing support for better IDE integration
3. **Scientific references**: Citations for key algorithms and thresholds
4. **Error handling**: Graceful handling of missing data
5. **Backward compatibility**: Legacy property aliases maintained

### ✅ Best Practices
- PEP 8 compliant formatting
- Clear separation of concerns
- Immutable constants where appropriate
- Descriptive variable names
- Comprehensive inline comments

---

## Testing Recommendations

### Unit Tests Needed
1. **athlete.py**
   - Profile creation and serialization
   - Time conversion utilities
   - HR calculations (Tanaka formula)

2. **database.py**
   - CTL/ATL/TSB calculations
   - Session save/retrieve
   - Shoe compression recovery logic

3. **equipment.py**
   - Gear validation rules
   - Mileage tracking
   - Surface risk assessment

4. **periodization.py**
   - Phase calculation boundaries
   - Goal completion logic

5. **math_core.py**
   - Weight function edge cases
   - System status combinations

---

## Next Steps

### Immediate Tasks
1. ✅ Core modules extracted and validated
2. ⏳ Extract science modules (see next migration phase)
3. ⏳ Extract features modules
4. ⏳ Extract UI/orchestration modules
5. ⏳ Create integration tests
6. ⏳ Update main application to use new modules

### Future Enhancements
1. Add unit tests for all modules
2. Add integration tests for database operations
3. Create migration scripts for legacy data
4. Add logging throughout
5. Create configuration file loader
6. Add data validation schemas

---

## Notes

### Critical Speed Model
The athlete profile includes Critical Speed (CS) and D' (D-prime):
- **CS**: Sustainable speed indefinitely (Monod & Scherrer, 1965)
- **D'**: Finite anaerobic work capacity above CS (measured in meters)
- Used for interval planning and fatigue prediction

### Weight Management
Three-tier weight threshold system:
- **Floor** (75.0 kg): Safe minimum weight
- **Panic** (74.5 kg): Critical intervention needed
- **Ceiling** (76.2 kg): Upper healthy range

### Training Load (sRPE)
Session RPE method (Foster et al., 2001):
- Training Load = RPE (1-10) × Duration (minutes)
- Correlation r=0.85 with HR-based TRIMP
- Simple, validated, no equipment needed

---

## File Locations

All files created in:
- `/home/user/project-mayhem/titan/core/`
- `/home/user/project-mayhem/titan/utils/`

Original source file:
- `/home/user/project-mayhem/TITAN_v50_FULL_KERNEL_FINAL.py`

---

**Migration Status**: ✅ COMPLETE for Phase 1 (Core Modules)
**Date**: 2026-02-13
**Lines Migrated**: ~1,500 lines from monolithic file
**New Modules**: 6 files + 2 __init__.py updates
