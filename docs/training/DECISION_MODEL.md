# TITAN OS — Decision Model

**Version:** 1.0
**Scope:** Inputs → Gates → Outputs evaluation pipeline for endurance training recommendations

---

## 1. Overview

The decision model is a deterministic pipeline. Given a fixed set of inputs, it always produces the same output. There is no randomness in gate evaluation. Optimization logic operates only after all gates have been evaluated and passed.

```
INPUTS
  │
  ▼
[Gate 1: Injury / Medical]
  │ HARD STOP if flagged
  ▼
[Gate 2: Autonomic Gate (HRV + RHR)]
  │
  ▼
[Gate 3: Recovery Gate (Sleep + Subjective Fatigue)]
  │
  ▼
[Gate 4: Load Gate (Acute Load / TSB)]
  │
  ▼
[Aggregate Color Assignment + Downgrade Rule]
  │
  ▼
[Intensity Governor Check]
  │
  ▼
[VO2 Eligibility Check]
  │
  ▼
[Fueling State Check]
  │
  ▼
OUTPUTS (session prescription + audit record)
  │
  ▼
[In-Session: Live Drift Monitor]
  │
  ▼
[Post-Session: Log + Update Load Metrics]
```

---

## 2. Inputs

### 2.1 Pre-Session Inputs (required before any recommendation)

| Input | Type | Source | Required |
|---|---|---|---|
| `hrv` | float (ms) | Morning measurement | Yes |
| `hrv_baseline_7d` | float (ms) | Mean of the 7 readings before today; missing with fewer (EASY ceiling, D-105) | Yes |
| `rhr` | int (bpm) | Morning measurement | Yes |
| `rhr_baseline_7d` | float (bpm) | Mean of the 7 days before today, today excluded (D-105) | Yes |
| `sleep_score` | float (0–100) or hours | Device / self-report | Yes |
| `subjective_fatigue` | int (1–10) | Athlete self-report | Yes |
| `acute_load_atl` | float (AU) | Computed from session history | Yes |
| `chronic_load_ctl` | float (AU) | Computed from session history | Yes |
| `tsb` | float (AU) | CTL − ATL | Derived |
| `injury_flag` | bool | Athlete report / system flag | Yes |
| `session_history` | list | Previous N sessions log | Yes |
| `active_profile` | string | Profile ID (e.g., "5K") | Yes |
| `planned_session_type` | enum | Z1/Z2/Z3/Z4/VO2/Rest | Yes |

### 2.2 In-Session Inputs (live monitoring)

| Input | Type | Source |
|---|---|---|
| `current_hr` | int (bpm) | Live HR feed |
| `hr_first_5min_avg` | float (bpm) | Computed at 5-min mark |
| `hr_last_5min_avg` | float (bpm) | Computed at current position |
| `current_rpe` | int (1–10) | Athlete checkpoint input |
| `elapsed_time_min` | float | Session timer |
| `current_pace` | float (sec/km) | GPS or treadmill |

### 2.3 Profile Parameters (loaded from active profile)

All threshold values are read from the active profile file at evaluation time. The decision model does not hardcode values. See `profiles/<PROFILE_ID>.md` for concrete values.

---

## 3. Gates

Gates are evaluated in strict sequence. A gate failure stops evaluation at that point and assigns the corresponding color. Later gates are not evaluated when a hard stop fires.

### Gate 1 — Injury / Medical Flag

```
IF injury_flag == TRUE
  → color = RED (HARD STOP)
  → reason = "active_injury_flag"
  → skip all remaining gates
  → output = rest or medical review
```

This gate cannot be overridden by the optimizer. An athlete override is possible but is logged as a "RED override" and triggers heightened monitoring for the following 72 hours.

---

### Gate 2 — Autonomic Gate

Evaluates HRV and RHR relative to personal baseline.

```
hrv_negative  = (hrv < hrv_baseline_7d - profile.hrv_negative_delta_ms)
hrv_collapse  = (hrv < hrv_baseline_7d - profile.hrv_collapse_delta_ms)

rhr_negative  = (rhr > rhr_baseline_7d + profile.rhr_negative_delta_bpm)
rhr_collapse  = (rhr > rhr_baseline_7d + profile.rhr_collapse_delta_bpm)

IF hrv_collapse OR rhr_collapse
  → autonomic_gate = RED (HARD STOP)
ELSE IF hrv_negative OR rhr_negative
  → autonomic_gate = YELLOW
ELSE
  → autonomic_gate = GREEN
```

**Output:** `autonomic_gate` ∈ {GREEN, YELLOW, RED}

---

### Gate 3 — Recovery Gate

Evaluates sleep quality and subjective fatigue.

```
sleep_negative      = (sleep_score < profile.sleep_negative_threshold)
fatigue_negative    = (subjective_fatigue >= profile.subjective_fatigue_negative_threshold)

IF sleep_negative AND fatigue_negative
  → recovery_gate = YELLOW  (both signals negative, but neither alone is a hard stop)
ELSE IF sleep_negative OR fatigue_negative
  → recovery_gate = YELLOW
ELSE
  → recovery_gate = GREEN
```

Note: Recovery gate alone does not produce RED. It contributes to the aggregate color via the downgrade rule.

**Output:** `recovery_gate` ∈ {GREEN, YELLOW}

---

### Gate 4 — Load Gate

Evaluates acute load and TSB.

```
load_critical = (tsb < profile.tsb_critical_floor_au)
load_negative = (acute_load_atl > profile.atl_high_threshold)  # profile-defined

IF load_critical
  → load_gate = RED (HARD STOP)
ELSE IF load_negative
  → load_gate = YELLOW
ELSE
  → load_gate = GREEN
```

**Output:** `load_gate` ∈ {GREEN, YELLOW, RED}

---

### Aggregate Color Assignment

After Gates 2–4 are evaluated, the downgrade rule is applied.

```
# Count negative (YELLOW or RED) signals from primary indicators
negatives = 0

IF hrv_negative:        negatives += 1
IF rhr_negative:        negatives += 1
IF sleep_negative:      negatives += 1
IF fatigue_negative:    negatives += 1

# Apply downgrade rule
IF any gate == RED:
  → final_color = RED

ELSE IF negatives >= 2:
  → final_color = YELLOW  (downgrade rule triggered)

ELSE IF any gate == YELLOW:
  → final_color = YELLOW

ELSE:
  → final_color = GREEN
```

**The downgrade rule:** 2 of 4 primary indicators (HRV, RHR, sleep, subjective fatigue) negative → YELLOW, regardless of whether any single gate reached YELLOW.

---

### Gate 5 — Intensity Governor (applies if session type = Z3 or higher)

```
IF final_color == RED:
  → skip; output = rest/Z1

IF final_color == YELLOW AND planned_session_type IN [Z3, Z4, VO2]:
  → downgrade: Z4/VO2 → Z3, Z3 → Z2
  → apply profile.downgrade_volume_factor (e.g., reduce by 20%)

IF final_color == GREEN AND planned_session_type IN [Z3, Z4]:
  → verify: session_hr_ceiling = profile.threshold_hr_ceiling_bpm
  → verify: rpe_band = profile RPE range for session type
  → authorize session
```

---

### Gate 6 — VO2 Eligibility (applies only if session type = VO2)

```
vo2_eligible = (
  final_color == GREEN
  AND tsb >= profile.tsb_vo2_floor_au
  AND hrv >= hrv_baseline_7d  # no suppression
  AND days_since_last_vo2 >= profile.vo2_min_rest_days
  AND fueling_state == "carb_available"
)

IF NOT vo2_eligible:
  → replace VO2 session with Z2
  → log reason for each failed condition
```

---

### Gate 7 — Fueling State Check

```
IF planned_session_type IN [Z3, Z4, VO2]:
  IF fueling_state IN ["fasted", "low_carb"]:
    → fueling_gate = FAIL
    → flag: "intensity_without_fuel"
    → recommend: postpone session OR eat first
    → do not block session if athlete overrides, but log

IF active_training_phase == "intensity_phase":
  IF fueling_protocol == "low_carb":
    → flag: "phase_lock_violation"
    → log warning; do not silently allow
```

---

## 4. Evaluation Order (Canonical)

The following is the hard-coded evaluation sequence. No module may reorder these steps.

| Step | Gate / Module | Can Produce RED | Stops Pipeline |
|---|---|---|---|
| 1 | Injury / Medical Flag | Yes | Yes |
| 2 | Autonomic Gate (HRV + RHR) | Yes (collapse) | Yes (collapse only) |
| 3 | Recovery Gate (Sleep + Fatigue) | No | No |
| 4 | Load Gate (TSB / ATL) | Yes (critical) | Yes (critical only) |
| 5 | Aggregate Color + Downgrade Rule | Yes (aggregate RED) | Yes (if RED) |
| 6 | Intensity Governor | No (adjusts only) | No |
| 7 | VO2 Eligibility | No (removes VO2 only) | No |
| 8 | Fueling State | No (flags only) | No |
| 9 | **OUTPUT GENERATION** | — | — |
| 10 | In-Session Drift Monitor (live) | Yes (terminates block) | Partial (terminates intensity block) |
| 11 | Post-Session Logging | — | — |

---

## 5. Outputs

The decision model produces three outputs per evaluation cycle.

### 5.1 Session Prescription

```json
{
  "date": "YYYY-MM-DD",
  "profile": "5K",
  "original_plan": "Z4_intervals",
  "final_prescription": "Z2_easy_30min",
  "gate_color": "YELLOW",
  "downgrade_applied": true,
  "downgrade_reason": "2_of_4_negatives",
  "negative_signals": ["hrv_suppressed", "sleep_below_threshold"],
  "hr_ceiling": 145,
  "drift_limit_pct": 6,
  "rpe_band": [3, 4],
  "fueling_note": "fasted_ok_for_z2",
  "vo2_authorized": false
}
```

### 5.2 Audit Record

Every evaluation cycle produces an audit record regardless of outcome.

```json
{
  "timestamp": "ISO8601",
  "inputs_snapshot": { ... },
  "gate_results": {
    "injury_gate": "GREEN",
    "autonomic_gate": "YELLOW",
    "recovery_gate": "YELLOW",
    "load_gate": "GREEN",
    "aggregate": "YELLOW",
    "negatives_count": 2
  },
  "output": { ... },
  "override": false,
  "override_log": null
}
```

### 5.3 In-Session Drift Alert

Produced by live monitor when drift threshold is crossed.

```json
{
  "timestamp": "ISO8601",
  "event": "drift_limit_exceeded",
  "drift_pct": 6.2,
  "hr_start": 148,
  "hr_current": 157,
  "action": "terminate_intensity_block",
  "recommendation": "reduce_to_z2_and_cool_down"
}
```

---

## 6. Override Policy

An athlete may override any non-medical gate recommendation. Overrides are:

1. **Logged** — stored permanently in audit trail
2. **Counted** — override counter incremented
3. **Penalized** — sustainability score adjusted
4. **Never normalized** — 3+ overrides in 7 days triggers a block review

Override does not suppress warnings. The system continues to display the gate rationale alongside the overridden output.

```
override_record = {
  "gate_overridden": "autonomic_gate",
  "original_color": "RED",
  "athlete_action": "proceeded_with_intensity",
  "session_executed": "Z3_20min",
  "override_count_7d": 1,
  "sustainability_penalty": 0.05
}
```

---

## 7. Longevity Bias (Conflict Resolution)

When any signal is ambiguous, the system resolves toward safety.

| Conflict | Resolution |
|---|---|
| Gate YELLOW + athlete wants Z4 | Downgrade to Z3 at most; Z4 blocked |
| Gate RED + race day | Rest prescribed; race decision left to athlete with full audit |
| TSB borderline for VO2 | VO2 blocked; Z2 prescribed |
| Drift at soft limit | Warn, reduce pace; do not continue at same pace |
| Drift at hard limit | Terminate intensity block immediately |
| Fueling suboptimal + intensity scheduled | Flag + recommend delay; do not silently execute |

**Resolution rule:** In any ambiguous case, select the option with lower physiological cost.

---

## 8. Integration with Architecture

This decision model is a spec of the evaluation pipeline. It aligns with:

- `docs/architecture/EVALUATION_ORDER.md` — hard hierarchy (injury → load → intensity → performance)
- `docs/architecture/GOVERNANCE_PHILOSOPHY.md` — protective bias, hard gate principle
- `docs/foundation/PRODUCT_FOUNDATION.md` — longevity bias, optimization objective

The pipeline defined here is the concrete instantiation of those principles.

---

*This document is a spec, not implementation. No `.py` files are implied or modified.*
