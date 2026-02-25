---
title: "[P2] Governance gates: VO2max session eligibility (5 conditions) + Fueling gate (flag/lock per phase)"
labels: ["P2", "governance", "vo2max", "nutrition", "fueling"]
---

## Problem Statement

Two governance rules described in the architecture specification are not implemented:

### 1. VO2max Session Eligibility Gate

High-intensity VO2max sessions (INTERVALS at Zone 5, HAMMER) carry the highest injury and maladaptation risk when the athlete is not physiologically ready. Five independent eligibility conditions must all be satisfied before such a session is permitted. Currently, no such check exists — a VO2max-type session can be scheduled on any day regardless of current readiness, glycogen state, ACWR, or training history.

### 2. Fueling Gate

Some sessions require mandatory fueling (intra-session carbohydrates) to be physiologically valid. If the athlete has not confirmed fueling availability, the session should be:
- **Flagged** (warning issued) for borderline cases
- **Locked** (converted to a lower-intensity alternative) when fueling absence would make the session unsafe

Currently, `glycogen_model.py` computes an electrolyte guard that checks dew point and duration, but there is no structured gate that:
- Enforces pre-session carbohydrate confirmation for quality sessions above a duration threshold
- Distinguishes flag (advisory) from lock (enforcement) by session phase
- Feeds its decision into the governance output

## Scope

Add two new gate methods to `governance_engine.py`:
1. `_check_vo2_eligibility(context)` — five-condition check; blocks VO2-type sessions if any condition fails
2. `_check_fueling_gate(context)` — per-phase flag/lock logic for carbohydrate availability

Both gates run after the `IntensityGovernor` result (issue #003) and before the existing Gate 1 (parasympathetic saturation guard).

## Files Touched

| File | Change |
|---|---|
| `titan/science/governance_engine.py` | Add `_check_vo2_eligibility()` and `_check_fueling_gate()` methods; call both in `apply_constraints()` |
| `titan/orchestration/daily_coach.py` | Ensure fueling confirmation field is collected and present in context dict |
| `titan/science/glycogen_model.py` | Expose `get_electrolyte_guard_status()` as a named method if not already named; no logic changes |

## Gate Specifications

---

### Gate V — VO2max Eligibility (5 conditions)

**Applies to:** session types `INTERVALS` with zone == 5, `HAMMER`, `RACE`

All five conditions must be True for the session to proceed unchanged. If any condition is False, the session is downgraded to `TEMPO` (not REST — the athlete still trains, but at sub-VO2 intensity).

#### Condition definitions

| # | Condition | Pass criterion | Fail action |
|---|---|---|---|
| V1 | ACWR in safe window | `0.8 <= acwr <= 1.5` | Downgrade to TEMPO |
| V2 | Readiness score sufficient | `readiness_score >= 60` | Downgrade to TEMPO |
| V3 | Glycogen debt not critical | `glycogen_debt < 7` | Downgrade to TEMPO |
| V4 | No active fatigue HIGH | `fatigue_level != "HIGH"` | Downgrade to TEMPO |
| V5 | Minimum rest interval since last VO2 session | `days_since_last_vo2 >= 2` | Downgrade to TEMPO |

For V5, `days_since_last_vo2` must be tracked in the context (read from training log). If the value is unavailable (no prior data), treat as passing (conservative default: allow first VO2 session).

#### Governance output when any condition fails

```python
{
  'vo2_eligibility': {
    'eligible': False,
    'failed_conditions': ['V2', 'V4'],  # list of failed condition IDs
    'original_session': 'INTERVALS_Z5',
    'downgraded_to': 'TEMPO',
    'reason': "VO2max session requires: readiness >= 60 (actual: 48), fatigue != HIGH (actual: HIGH)"
  }
}
```

---

### Gate F — Fueling Gate

**Applies to:** sessions with `duration_min >= 60` in the phases `TEMPO`, `INTERVALS`, `LONG_RUN`, `HAMMER`, `RACE`

#### Phase definitions and thresholds

| Phase | Duration threshold | Fueling requirement | No-fueling action |
|---|---|---|---|
| Phase 1 (Sub-threshold) | 60-89 min + session in [EASY, PROGRESSIVE] | Recommended but optional | FLAG only (advisory) |
| Phase 2 (Threshold quality) | 60-89 min + session in [TEMPO, INTERVALS] | Required | FLAG |
| Phase 2 (Threshold quality) | >= 90 min + session in [TEMPO, INTERVALS] | Mandatory | LOCK → downgrade to EASY |
| Phase 3 (Supramaximal) | Any duration + session in [HAMMER, RACE] | Mandatory | LOCK → downgrade to TEMPO |
| Phase 4 (Long run) | >= 90 min + session = LONG_RUN | Required | LOCK → downgrade to PROGRESSIVE |

**FLAG**: Warning included in Telegram message; session proceeds unchanged.

**LOCK**: Session type is changed; reason included in governance output.

#### Fueling confirmation field

A boolean `fueling_confirmed` must be present in the context dict. It represents the athlete's confirmation that intra-session carbohydrates are available. If the field is absent, treat as `False` (conservative — assume no fueling).

```python
# Context field populated in daily_coach.py morning collection
context['fueling_confirmed'] = True  # or False, based on athlete input
context['planned_duration_min'] = today_plan.duration_min
```

#### Governance output for fueling gate

When FLAG fires:
```python
{
  'fueling_gate': {
    'action': 'FLAG',
    'phase': 2,
    'reason': "Quality session 75 min without confirmed fueling: performance risk",
    'session_unchanged': True
  }
}
```

When LOCK fires:
```python
{
  'fueling_gate': {
    'action': 'LOCK',
    'phase': 3,
    'reason': "HAMMER session without confirmed fueling: unsafe glycogen depletion risk",
    'original_session': 'HAMMER',
    'locked_to': 'TEMPO'
  }
}
```

## Acceptance Tests

### VO2 Eligibility Gate

#### Scenario AT-V1: All 5 conditions pass — session unchanged
```
Given:
  acwr = 1.1 (pass V1)
  readiness_score = 72 (pass V2)
  glycogen_debt = 3.0 (pass V3)
  fatigue_level = "LOW" (pass V4)
  days_since_last_vo2 = 3 (pass V5)
  planned_session = "INTERVALS" (Zone 5)
When: _check_vo2_eligibility() is called
Then:
  - session_type unchanged
  - vo2_eligibility.eligible == True
  - failed_conditions == []
```

#### Scenario AT-V2: V2 fails (low readiness) — downgrade to TEMPO
```
Given:
  readiness_score = 48  (fail V2: < 60)
  all other conditions pass
  planned_session = "HAMMER"
When: _check_vo2_eligibility() is called
Then:
  - session_type == "TEMPO"
  - vo2_eligibility.eligible == False
  - failed_conditions == ["V2"]
```

#### Scenario AT-V3: V3 and V4 both fail — downgrade to TEMPO, both listed
```
Given:
  glycogen_debt = 8.5  (fail V3: >= 7)
  fatigue_level = "HIGH"  (fail V4)
  all other conditions pass
  planned_session = "INTERVALS"
When: _check_vo2_eligibility() is called
Then:
  - session_type == "TEMPO"
  - failed_conditions contains "V3" and "V4"
```

#### Scenario AT-V4: V1 fails — ACWR too high
```
Given:
  acwr = 1.6  (fail V1: > 1.5)
  planned_session = "RACE"
When: _check_vo2_eligibility() is called
Then:
  - session_type == "TEMPO"
  - failed_conditions == ["V1"]
```

#### Scenario AT-V5: V1 fails — ACWR too low (detraining)
```
Given:
  acwr = 0.7  (fail V1: < 0.8)
  planned_session = "INTERVALS"
When: _check_vo2_eligibility() is called
Then:
  - session_type == "TEMPO"
  - failed_conditions == ["V1"]
```

#### Scenario AT-V6: Gate does NOT apply to TEMPO session
```
Given: planned_session = "TEMPO" (not a VO2-type session)
When: _check_vo2_eligibility() is called
Then:
  - Gate is skipped entirely (TEMPO is sub-VO2max)
  - session_type unchanged
  - vo2_eligibility key absent from governance output
```

#### Scenario AT-V7: V5 — days_since_last_vo2 is unavailable
```
Given: context does not contain 'days_since_last_vo2'
When: _check_vo2_eligibility() is called
Then:
  - V5 is treated as passing (no data = allow)
  - No error raised
```

#### Scenario AT-V8: V5 — insufficient rest (1 day since last VO2)
```
Given: days_since_last_vo2 = 1  (fail V5: < 2)
When: _check_vo2_eligibility() is called
Then:
  - session_type == "TEMPO"
  - failed_conditions == ["V5"]
```

---

### Fueling Gate

#### Scenario AT-F1: Phase 3 session, fueling not confirmed — LOCK
```
Given:
  planned_session = "HAMMER"
  fueling_confirmed = False
  planned_duration_min = 45
When: _check_fueling_gate() is called
Then:
  - session_type == "TEMPO"
  - fueling_gate.action == "LOCK"
  - fueling_gate.phase == 3
  - fueling_gate.locked_to == "TEMPO"
```

#### Scenario AT-F2: Phase 2 session, >= 90 min, fueling not confirmed — LOCK
```
Given:
  planned_session = "TEMPO"
  fueling_confirmed = False
  planned_duration_min = 95
When: _check_fueling_gate() is called
Then:
  - session_type == "EASY"
  - fueling_gate.action == "LOCK"
```

#### Scenario AT-F3: Phase 2 session, 60-89 min, fueling not confirmed — FLAG only
```
Given:
  planned_session = "INTERVALS"
  fueling_confirmed = False
  planned_duration_min = 70
When: _check_fueling_gate() is called
Then:
  - session_type UNCHANGED (still INTERVALS)
  - fueling_gate.action == "FLAG"
  - fueling_gate.session_unchanged == True
```

#### Scenario AT-F4: Any session, fueling confirmed — gate passes
```
Given:
  planned_session = "HAMMER"
  fueling_confirmed = True
When: _check_fueling_gate() is called
Then:
  - Gate does not fire
  - session_type unchanged
  - fueling_gate key absent from governance output
```

#### Scenario AT-F5: Short session (< 60 min) — gate does not apply
```
Given:
  planned_session = "TEMPO"
  fueling_confirmed = False
  planned_duration_min = 45
When: _check_fueling_gate() is called
Then:
  - Gate does not fire (duration below threshold for Phase 2)
  - session_type unchanged
```

Exception: Phase 3 sessions (HAMMER, RACE) apply regardless of duration — see AT-F1.

#### Scenario AT-F6: LONG_RUN >= 90 min, fueling not confirmed — LOCK to PROGRESSIVE
```
Given:
  planned_session = "LONG_RUN"
  fueling_confirmed = False
  planned_duration_min = 110
When: _check_fueling_gate() is called
Then:
  - session_type == "PROGRESSIVE"
  - fueling_gate.action == "LOCK"
  - fueling_gate.locked_to == "PROGRESSIVE"
```

#### Scenario AT-F7: fueling_confirmed absent from context — treated as False
```
Given: context dict has no 'fueling_confirmed' key
  planned_session = "HAMMER"
When: _check_fueling_gate() is called
Then:
  - context.get('fueling_confirmed', False) == False
  - Gate fires as if fueling_confirmed = False
  - No KeyError raised
```

#### Scenario AT-F8: Gate ordering — VO2 eligibility runs before fueling gate
```
Given:
  planned_session = "HAMMER"
  VO2 eligibility gate fails (downgrade to TEMPO)
  fueling_confirmed = False
  planned_duration_min = 45 (short, Phase 3 exception applies)
When: full governance pipeline runs
Then:
  - VO2 gate runs first → downgrades HAMMER to TEMPO
  - Fueling gate evaluates TEMPO (the downgraded session)
  - TEMPO is Phase 2, duration 45 min → below FLAG threshold
  - Final session = TEMPO, no fueling lock
```

## Explicit Non-Goals

- **No changes to `glycogen_model.py` logic** — the fueling gate reads glycogen debt as a number; it does not modify how debt is computed.
- **No integration with a nutrition database or external API** — `fueling_confirmed` is a single boolean supplied by the athlete at morning check-in.
- **No changes to the electrolyte guard in `glycogen_model.py`** — that remains as a separate advisory output; the fueling gate does not replace or duplicate it.
- **No changes to weekly session scheduling** — if the fueling gate locks a session, the weekly plan for future days is not modified.
- **No tracking of fueling history** — the gate evaluates the current day only; no multi-day fueling pattern analysis.
- **No changes to Zone 4/Zone 5 definitions** — zone numbers are used as references only; zone boundary values are not modified.
- **No implementation of the Norwegian Recovery Window Protocol** — that is triggered by `glycogen_model.py` independently of this gate.
- **No UI changes to the Telegram template** — FLAG and LOCK outputs are passed as structured context to the existing message builder.
