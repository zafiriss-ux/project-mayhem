---
title: "[P1] Threshold alignment: sleep 50→60, HRV −10→−8, RHR +5→+6, 2-of-4 downgrade"
labels: ["P1", "thresholds", "governance", "readiness"]
---

## Problem Statement

Several numeric thresholds in `readiness_engine.py` do not match the values agreed in the governance architecture specification. Additionally, the "2-of-4 downgrade" rule described in the specification (downgrade session when at least 2 of 4 indicators are triggered) has no implementation anywhere in the codebase.

### Current vs Required Thresholds

| Signal | Current value | Required value | File | Line context |
|---|---|---|---|---|
| Sleep score "poor" boundary | `< 50` | `< 60` | `readiness_engine.py` | `if sleep_score < 50` |
| HRV delta penalty trigger | `< -10 pts` | `< -8 pts` | `readiness_engine.py` | `if hrv_delta < -10` |
| RHR delta penalty trigger | `> +5 bpm` | `> +6 bpm` | `readiness_engine.py` | `if rhr_delta > 5` |

The 2-of-4 downgrade rule evaluates four binary indicators at each morning routine execution:
1. HRV below threshold (soft — below −1SD, not the −2SD hard stop)
2. Sleep score in "poor" or "fair" band
3. Readiness score below 50
4. Subjective fatigue ≥ 6

When **2 or more** of these are true, the planned quality session is downgraded one intensity level before the hard gates run.

## Scope

1. Update the three numeric threshold values in `readiness_engine.py`.
2. Implement the 2-of-4 indicator evaluation and downgrade step in `governance_engine.py` (or a dedicated pre-gate step in `daily_coach.py`).
3. The downgrade must be documented in the governance audit trail returned to the Telegram message builder.

## Files Touched

| File | Change |
|---|---|
| `titan/science/readiness_engine.py` | Update three threshold constants |
| `titan/science/governance_engine.py` | Add `_evaluate_2of4_indicators(context)` returning `(count, indicators_list)`; apply downgrade if count >= 2 |
| `titan/orchestration/daily_coach.py` | Ensure all four indicator values are present in the context dict passed to governance |

## Threshold Change Details

### `readiness_engine.py` — Sleep score boundary

```python
# Current
if sleep_score < 50:
    score -= 15  # poor sleep

# Required
if sleep_score < 60:
    score -= 15  # poor sleep
```

The "fair" band upper boundary (`50–69`) must also shift to `60–69` so the bands remain contiguous and non-overlapping:
```
< 60:   poor  (was: < 50)
60-69:  fair  (was: 50-69, lower bound shifts up)
70-84:  neutral (no change)
≥ 85:  excellent (no change)
```

### `readiness_engine.py` — HRV delta penalty

```python
# Current
if hrv_delta < -10:
    score -= 20
elif hrv_delta < -5:
    score -= 10

# Required
if hrv_delta < -8:
    score -= 20
elif hrv_delta < -5:
    score -= 10
```

### `readiness_engine.py` — RHR delta penalty

```python
# Current
if rhr_delta > 5:
    score -= 15
elif rhr_delta > 3:
    score -= 8

# Required
if rhr_delta > 6:
    score -= 15
elif rhr_delta > 3:
    score -= 8
```

## 2-of-4 Downgrade Logic

### Indicator definitions

```
I1 (HRV soft): today_hrv < baseline_hrv - 1SD
I2 (Sleep):    sleep_score < 60  (using new threshold)
I3 (Readiness): readiness_score < 50
I4 (Subjective): subjective_fatigue_score >= 6
```

### Downgrade map

```
count = sum([I1, I2, I3, I4])

if count >= 2:
    INTERVALS   → TEMPO
    TEMPO       → EASY
    HAMMER      → EASY
    RACE        → TEMPO
    PROGRESSIVE → EASY
    EASY        → EASY  (no further downgrade)
    REST        → REST  (no change)
```

### Audit trail entry
When a downgrade fires, the governance output must include:
```python
{
  'downgrade_2of4': True,
  'indicators_triggered': ['I1_hrv_soft', 'I3_readiness'],  # example
  'original_session': 'INTERVALS',
  'downgraded_to': 'TEMPO'
}
```

## Acceptance Tests

### Scenario AT-T1: Sleep threshold shift
```
Given: sleep_score = 55
When: readiness_engine.analyze_readiness() is called
Then:
  - sleep_score 55 is classified as "poor" (< 60)
  - score penalty of -15 is applied
```

### Scenario AT-T1b: Sleep score exactly at new boundary
```
Given: sleep_score = 60
When: analyze_readiness() is called
Then:
  - sleep_score 60 is NOT classified as "poor"
  - falls into "fair" band (60-69)
  - penalty is -8 (fair), not -15 (poor)
```

### Scenario AT-T2: HRV delta at old threshold (now should NOT trigger)
```
Given: hrv_delta = -9  (i.e., today_hrv = baseline - 9)
When: analyze_readiness() is called
Then:
  - The -20 penalty does NOT apply (old threshold was -10, new is -8)
  - The -9 delta DOES trigger the -20 penalty under new threshold (< -8 → true)
```
Note: `-9 < -8` is true, so -9 triggers the new threshold. The test that changes is the borderline:

```
Given: hrv_delta = -9
Old behavior: -20 penalty (< -10? No. < -5? Yes → -10)   → penalty was -10
New behavior: -20 penalty (< -8? Yes → -20)               → penalty is -20
```
Verify new behavior applies -20, not -10.

### Scenario AT-T3: RHR delta at old threshold (now should NOT trigger high penalty)
```
Given: rhr_delta = +5  (was previously > 5 == false, so no high penalty)
Old rule: rhr_delta > 5 → false for delta=5 (strict >)
New rule: rhr_delta > 6 → false for delta=5

Given: rhr_delta = +6
Old rule: rhr_delta > 5 → true → -15 penalty
New rule: rhr_delta > 6 → false for delta=6 (strict >) → falls to elif > 3 → -8 penalty
```
Verify rhr_delta = +6 now receives -8 penalty, not -15.

### Scenario AT-2of4-A: Exactly 2 indicators — downgrade fires
```
Given:
  today_hrv = baseline_hrv - 1.5 × SD  (I1 = True)
  sleep_score = 58                       (I2 = True, < 60)
  readiness_score = 62                   (I3 = False)
  subjective_fatigue = 5                 (I4 = False)
  count = 2
  planned session = INTERVALS
When: governance pre-processing runs
Then:
  - session_type downgraded to TEMPO
  - audit entry 'downgrade_2of4' = True
  - indicators_triggered = ['I1_hrv_soft', 'I2_sleep']
```

### Scenario AT-2of4-B: Only 1 indicator — downgrade does NOT fire
```
Given:
  today_hrv = baseline_hrv - 1.5 × SD  (I1 = True)
  sleep_score = 72                       (I2 = False)
  readiness_score = 68                   (I3 = False)
  subjective_fatigue = 4                 (I4 = False)
  count = 1
  planned session = INTERVALS
When: governance pre-processing runs
Then:
  - session_type remains INTERVALS
  - 'downgrade_2of4' is absent from audit entry
```

### Scenario AT-2of4-C: All 4 indicators — downgrade fires, result is EASY
```
Given: all four indicators = True, planned session = HAMMER
When: governance pre-processing runs
Then:
  - session_type == EASY
  - count = 4 (still uses same downgrade map — one step down from HAMMER = EASY)
```

### Scenario AT-2of4-D: Already EASY session — no further downgrade
```
Given: count = 3, planned session = EASY
When: governance pre-processing runs
Then:
  - session_type remains EASY
  - 'downgrade_2of4' = True (still recorded)
  - 'downgraded_to' = 'EASY' (same as original, but flag is set)
```

### Scenario AT-2of4-E: Downgrade runs before hard gates
```
Given: count = 2, planned session = INTERVALS, TSB = -45 (above floor of -50)
When: full governance pipeline runs
Then:
  - 2-of-4 fires first, downgrades INTERVALS → TEMPO
  - H2 gate does not fire (TSB = -45 > -50)
  - Final session = TEMPO
```

## Explicit Non-Goals

- **No changes to the -2SD hard stop logic** in `hrv_engine.py` (that is Gate H1 in issue #001).
- **No changes to the −1SD soft downgrade in `hrv_engine.get_training_recommendation()`** — that logic remains as-is; I1 in the 2-of-4 check is an independent re-evaluation.
- **No new scoring components** added to `readiness_engine.py` beyond the threshold adjustments listed.
- **No changes to TSB thresholds** — those remain at their current values.
- **No changes to the sleep *excellent* band boundary** (≥85 stays unchanged).
- **No Telegram message template changes** — the audit dict is passed to the existing message builder unchanged.
- **No persistence or history** of 2-of-4 events beyond the single-session audit dict.
