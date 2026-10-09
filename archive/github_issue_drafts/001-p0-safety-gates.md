---
title: "[P0] Hard-stop Safety Gates: HRV/RHR collapse, TSB floor, injury flag, subjective fatigue input"
labels: ["P0", "safety", "governance", "blocker"]
---

## Problem Statement

The current governance pipeline (`governance_engine.py`) enforces three gates (parasympathetic saturation, override lockdown, CS confidence lock), but it is missing a lower-level hard-stop layer that fires before any session type is even considered. Specifically:

1. **HRV/RHR collapse is not a hard stop.** `readiness_engine.py` scores HRV and RHR deviations and returns a numeric readiness score, but nothing prevents a HAMMER or INTERVALS session when both HRV and RHR are simultaneously in extreme deviation territory. The parasympathetic guard only fires on the `HRV↑ + HRR↓` *pattern*; it does not fire on the `HRV↓↓ + RHR↑↑` collapse pattern.

2. **TSB floor is advisory, not enforced.** `tsb_engine.py` labels TSB ≤ −50 as "OVERTRAINED", but `daily_coach.py` uses this label only for display. No gate blocks quality sessions when TSB < −50.

3. **Injury flags have no downstream gate.** There is no `injury_flag` field in the session context that `governance_engine.apply_constraints()` reads. If an athlete self-reports an injury, the system has no structured path to block training.

4. **Subjective fatigue is collected with a hardcoded RPE stub.** `fatigue_engine.py` receives `rpe_mismatch` as a boolean computed upstream, but the actual subjective input (daily wellness score, leg heaviness, mood) is not collected from the athlete at runtime — it is defaulted or mocked in `daily_coach.py`. This makes `classify_fatigue()` unreliable for gate decisions.

## Scope

Add a **pre-gate hard-stop layer** that evaluates four independent signals before the existing governance gates in `governance_engine.apply_constraints()`. This layer must:

- Block all sessions rated above EASY when conditions are met
- Return a structured reason for each block (for Telegram message construction)
- Be entirely specification-driven (thresholds passed as config, not hardcoded in logic)
- Add a subjective fatigue collection step in the morning routine that feeds real values into `fatigue_engine`

## Files Touched

| File | Change |
|---|---|
| `titan/science/governance_engine.py` | Add `_check_hard_stops(context)` method; call before existing gates |
| `titan/science/readiness_engine.py` | Expose `hrv_delta_pts` and `rhr_delta_pts` as named fields in output dict |
| `titan/science/tsb_engine.py` | Expose `tsb_value` as a named field (currently returned in tuple, position 0) |
| `titan/orchestration/daily_coach.py` | Add subjective fatigue collection step; pass real values to `fatigue_engine.classify_fatigue()` |
| `titan/config/thresholds.py` (new or existing) | Define `HARD_STOP_HRV_DELTA`, `HARD_STOP_RHR_DELTA`, `HARD_STOP_TSB_FLOOR` as config constants |

## Hard-Stop Definitions (Specification)

### Gate H1 — HRV/RHR Simultaneous Collapse
```
Trigger:
  today_hrv < baseline_hrv - HARD_STOP_HRV_DELTA   (suggested default: 15 pts absolute)
  AND today_rhr > baseline_rhr + HARD_STOP_RHR_DELTA (suggested default: 8 bpm)

Action:
  Force session_type = REST
  Set reason = "HRV/RHR dual collapse: autonomous nervous system under acute stress"
  Set max_zone = 1
  Block: INTERVALS, TEMPO, HAMMER, RACE, PROGRESSIVE, LONG_RUN
```

### Gate H2 — TSB Floor
```
Trigger:
  tsb_value <= HARD_STOP_TSB_FLOOR (suggested default: -50)

Action:
  Force session_type = EASY or REST (athlete choice preserved between these two)
  Set reason = "TSB at overtraining threshold: mandatory load reduction"
  Block: INTERVALS, TEMPO, HAMMER, RACE
```

### Gate H3 — Injury Flag
```
Trigger:
  context.get('injury_flag') is True

Action:
  Force session_type = REST
  Set reason = "Active injury flag: no training permitted until cleared"
  Block: ALL session types except REST and MOBILITY
```

### Gate H4 — Extreme Subjective Fatigue
```
Trigger:
  subjective_fatigue_score >= 8  (on athlete-reported 0-10 scale, collected at runtime)

Action:
  Force session_type = EASY
  Set reason = "Athlete-reported extreme fatigue: session downgraded"
  Block: INTERVALS, TEMPO, HAMMER, RACE
```

## Acceptance Tests

### Scenario AT-H1: HRV + RHR dual collapse
```
Given: today_hrv = 28, baseline_hrv = 55, today_rhr = 72, baseline_rhr = 52
(delta_hrv = -27, delta_rhr = +20 — both exceed thresholds)
When: governance_engine.apply_constraints() is called with planned session = INTERVALS
Then:
  - session_type == REST
  - governance_override contains reason string matching "HRV/RHR dual collapse"
  - max_zone == 1
```

### Scenario AT-H1b: Only HRV drops (not both)
```
Given: today_hrv = 28, baseline_hrv = 55, today_rhr = 54, baseline_rhr = 52
(only HRV drops; RHR delta = +2, below threshold)
When: apply_constraints() is called with planned session = INTERVALS
Then:
  - Gate H1 does NOT fire
  - Normal governance flow continues (H2/H3/H4 evaluated next)
```

### Scenario AT-H2: TSB floor
```
Given: tsb_value = -52
When: apply_constraints() is called with planned session = HAMMER
Then:
  - session_type in [EASY, REST]
  - reason contains "TSB at overtraining threshold"
  - HAMMER is blocked
```

### Scenario AT-H2b: TSB exactly at threshold (boundary)
```
Given: tsb_value = -50
When: apply_constraints() is called
Then:
  - Gate H2 fires (threshold is inclusive: <= -50)
```

### Scenario AT-H3: Injury flag present
```
Given: context = {'injury_flag': True, 'planned_session': 'TEMPO'}
When: apply_constraints() is called
Then:
  - session_type == REST
  - reason contains "Active injury flag"
  - TEMPO is blocked
```

### Scenario AT-H3b: No injury flag key in context
```
Given: context dict does not contain 'injury_flag' key
When: apply_constraints() is called
Then:
  - Gate H3 does NOT fire
  - context.get('injury_flag') safely returns None/False
```

### Scenario AT-H4: Extreme subjective fatigue
```
Given: athlete reports subjective_fatigue_score = 9 at morning check-in
When: apply_constraints() is called with planned session = INTERVALS
Then:
  - session_type == EASY
  - INTERVALS is blocked
  - reason contains "extreme fatigue"
```

### Scenario AT-H4b: Subjective fatigue below threshold
```
Given: subjective_fatigue_score = 7
When: apply_constraints() is called
Then:
  - Gate H4 does NOT fire (threshold is >= 8)
```

### Scenario AT-SUBJ: Subjective fatigue collection in morning routine
```
Given: daily_coach.run_morning_routine() is called
When: morning routine executes
Then:
  - A subjective fatigue value (integer 0-10) is collected from the athlete
  - This value is passed to fatigue_engine.classify_fatigue() as a real input
  - The value is NOT hardcoded or defaulted to a fixed number
```

### Scenario AT-CONFIG: Thresholds are config-driven
```
Given: HARD_STOP_HRV_DELTA = 20 (overriding default 15)
When: today_hrv = 40, baseline_hrv = 58 (delta = 18, below new threshold)
Then:
  - Gate H1 does NOT fire for HRV alone
  - New threshold value is respected without code change
```

## Explicit Non-Goals

- **No changes to HRV/RHR threshold values used in `readiness_engine.py` scoring** — that is a P1 issue.
- **No changes to the parasympathetic saturation guard** — that gate remains unchanged.
- **No UI/Telegram message redesign** — the reason string is passed to the existing message builder.
- **No new database tables or persistence** for the injury flag — it is passed in the daily context dict.
- **No refactoring of `fatigue_engine.classify_fatigue()` internals** — only the caller (`daily_coach.py`) is changed to supply real values.
- **No removal of existing Gate 1, 2, 3** in `governance_engine.py` — the H-gates run before them, not replacing them.
- **No machine-learning or prediction** for injury likelihood — this gate reads a binary flag only.
