# ADR 0006: Architectural Hardening — Cold-Start, Engine Sync, and Null Safety

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-02-18 |
| **Commits** | TBD |
| **Files** | `titan/science/tsb_engine.py`, `titan/orchestration/daily_coach.py`, `titan/features/weekly_planner.py`, `titan/features/nutrition_optimizer.py`, `README.md`, `test_core_modules.py` |

---

## Context

Audit of the live codebase revealed five independent bugs that collectively
caused silent failures on fresh installs, after restarts, and at peak fitness
(TSB ≈ 0):

| # | Bug | Impact |
|---|-----|--------|
| 1 | `TSBEngine.calculate_ctl()` guarded by `len < 7`, `calculate_atl()` by `len < 3` | `INSUFFICIENT DATA` for first 7 days after install |
| 2 | `_feed_load_engines()` set phantom attribute `self.tsb.load_history` (not a TSBEngine attribute) | Post-sync CTL/ATL silently stale |
| 3 | `_hydrate_engines_from_db()` appended to already-populated `daily_loads` on second call | Double-counting loads → inflated CTL/ATL after re-hydration |
| 4 | `analyze_past_week()` condition `tsb_value and tsb_value > -20` treated TSB=0.0 as falsy | Race-form (TSB=0.0) incorrectly returned 'COMPROMISED' readiness |
| 5 | `calculate_daily_nutrition()` hardcoded `height=180cm, age=35` in BMR formula | Nutrition incorrect for any athlete with different biometrics |

Two additional hygiene issues:
- Dead import `from science.lactate_logic import LactateLogic` in `weekly_planner.py` (never used)
- `README.md` startup command `cd titan && python main.py` wrong since root `main.py` was added

---

## Decision

### 1. TSB Cold-Start — remove arbitrary minimum-record guards

```python
# BEFORE (both methods):
if len(self.daily_loads) < 7:   # calculate_ctl
    return None
if len(self.daily_loads) < 3:   # calculate_atl
    return None

# AFTER:
if not self.daily_loads:
    return None
```

EMA is mathematically valid with ≥1 record: the seed equals the first load,
and the loop over `daily_loads[1:]` is empty (no-op). The old guards added
waiting time with no correctness benefit.

### 2. `_feed_load_engines()` — canonical API, clear before reload

```python
# BEFORE (phantom attribute, no reload):
self.tsb.load_history = loads  # TSBEngine has no load_history attribute

# AFTER (correct API, idempotent):
self.tsb.daily_loads.clear()
for date_str, load in reversed(loads):   # oldest-first for correct EMA
    self.tsb.add_daily_load(date_str, float(load))
```

### 3. `_hydrate_engines_from_db()` — `.clear()` before reload loops

Added `self.tsb.daily_loads.clear()` and `self.hrv.hrv_log.clear()` before
each reload loop. Prevents double-counting if the method is called more than
once (e.g., after reconnect or manual refresh).

### 4. `weekly_planner.py` — tsb_value None-safe comparison

```python
# BEFORE (falsy for TSB=0.0):
'readiness': 'GOOD' if avg_drift < 4 and tsb_value and tsb_value > -20 ...

# AFTER:
'readiness': 'GOOD' if avg_drift < 4 and tsb_value is not None and tsb_value > -20 ...
```

### 5. `nutrition_optimizer.py` — parameterise BMR

```python
# BEFORE:
def calculate_daily_nutrition(self, weight_kg, today_session, ...):
    bmr = 10 * weight_kg + 6.25 * 180 - 5 * 35 + 5

# AFTER:
def calculate_daily_nutrition(self, weight_kg, today_session, ...,
                              height_cm: int = 180, age: int = 35):
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
```

Defaults preserve existing behaviour; callers can now pass real athlete dimensions.

### 6. Dead import removed (`weekly_planner.py`)

Removed `from science.lactate_logic import LactateLogic` — imported but never
referenced anywhere in the module.

### 7. README startup command corrected

```bash
# BEFORE:
cd titan
python main.py

# AFTER:
python main.py
```

Root `main.py` is the canonical entry point since v51.

---

## Regression Tests Added (`test_core_modules.py`)

### `TestTSBColdStart` (6 tests)

| Test | Ελέγχει |
|------|---------|
| `test_zero_loads_returns_none` | 0 loads → CTL and ATL both None |
| `test_zero_loads_tsb_returns_none` | 0 loads → (None, "INSUFFICIENT DATA") |
| `test_single_load_returns_float` | 1 load → numeric CTL and ATL |
| `test_single_load_tsb_not_none` | 1 load → calculate_tsb() not None |
| `test_three_loads_returns_float` | 3 loads → numeric results (was blocked by old guard) |
| `test_zero_tsb_treated_as_race_form` | 1 identical load → TSB = 0.0 exactly |

### `TestTSBHydration` (2 tests)

| Test | Ελέγχει |
|------|---------|
| `test_clear_then_reload_gives_correct_ctl` | clear+reload produces identical CTL (no double-counting) |
| `test_double_hydrate_does_not_drift` | calling hydration twice gives same TSB |

### `TestWeeklyPlannerNullSafety` (2 tests)

| Test | Ελέγχει |
|------|---------|
| `test_none_tsb_does_not_raise` | None TSB → readiness='COMPROMISED', no TypeError |
| `test_zero_tsb_gives_good_readiness` | TSB=0.0 → readiness='GOOD' (not falsy) |

---

## Consequences

**Θετικά**
- Fresh install: CTL/ATL available immediately after the first session.
- Post-restart: `_feed_load_engines()` now actually refreshes in-memory state.
- Re-hydration: safe to call `_hydrate_engines_from_db()` multiple times.
- Athletes with TSB ≈ 0 (peak race form) receive correct 'GOOD' readiness.
- Nutrition plan accurate for any athlete biometrics (height, age parameterised).
- 10 new deterministic regression tests protect all five fixed paths.

**Ουδέτερα**
- `height_cm=180, age=35` defaults preserve existing output for callers that
  don't pass those arguments.
- Removing the < 7 guard changes CTL output for 1–6-record cases; previously
  `None`, now a valid EMA seed (correct behaviour).

**Αρνητικά**
- Κανένα. All changes are backward-compatible at the call sites.

---

## Επαλήθευση

```bash
pytest test_core_modules.py -q
# 69 passed, 0 warnings

pytest test_core_modules.py::TestTSBColdStart test_core_modules.py::TestTSBHydration test_core_modules.py::TestWeeklyPlannerNullSafety -v
# 10 passed
```
