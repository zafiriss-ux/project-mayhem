# TITAN OS — Operational Model (Endurance Generic)

**Version:** 1.0
**Scope:** Generic endurance training framework, parameterized per goal profile
**First instantiation:** 5K (see `profiles/5K.md`)

---

## 1. Purpose

This document defines the operational model governing all endurance training decisions within TITAN OS. It is intentionally profile-agnostic: concrete HR ceilings, drift limits, and weekly structures live in profile documents. This file defines the universal machinery.

**Design rule:** Longevity bias. When safety and performance conflict, safety wins. Always.

---

## 2. Input Variables

All decision-making draws from the following input set. Inputs are evaluated fresh each session before any recommendation is produced.

### 2.1 Autonomic / Recovery Inputs

| Variable | Source | Unit | Notes |
|---|---|---|---|
| `hrv` | Morning measurement (device) | ms (rMSSD or equivalent) | Compared to rolling 7-day baseline |
| `rhr` | Morning measurement | bpm | Compared to rolling 7-day baseline |
| `sleep_score` | Device or subjective | 0–100 or hours | Quantity + quality composite if available |
| `subjective_fatigue` | Athlete self-report | 1–10 | 1 = fully rested, 10 = exhausted |

### 2.2 Load Inputs

| Variable | Description | Unit |
|---|---|---|
| `acute_load` | Last 7-day training stress (ATL) | AU (arbitrary units) |
| `chronic_load` | Last 28-day training stress (CTL) | AU |
| `tsb` | Training Stress Balance = CTL − ATL | AU (positive = fresh, negative = fatigued) |
| `session_history` | Last N sessions: type, duration, HR data | Structured log |

### 2.3 In-Session Inputs

| Variable | Description | Unit |
|---|---|---|
| `hr_drift` | Cardiac drift during steady-state effort | % (HR at end vs. HR at start for same pace) |
| `rpe` | Perceived exertion at key session checkpoints | Borg 6–20 or RPE 1–10 |
| `session_hr_avg` | Mean HR for session or segment | bpm |
| `session_hr_ceiling` | Profile-defined intensity cap | bpm (from profile) |

---

## 3. Gate System

Gates are evaluated in strict order before any intensity or volume prescription is issued. A gate cannot be bypassed by an optimizer. An override requires explicit athlete action and is logged permanently.

### 3.1 Gate Colors

| Color | Meaning | System Action |
|---|---|---|
| **GREEN** | All signals nominal | Full prescribed session |
| **YELLOW** | 1–2 negative signals | Downgrade intensity or volume |
| **RED** | ≥3 negative signals, or any hard stop | Replace with recovery / rest |

### 3.2 Downgrade Rule

> **"2 of 4 negatives → downgrade"**
> If 2 or more of the 4 primary indicators (HRV, RHR, sleep, subjective fatigue) are negative, the session is downgraded from its planned intensity tier regardless of load metrics.

Negative thresholds are profile-defined. The rule structure is universal.

### 3.3 Hard Stops (immediate RED regardless of count)

The following conditions trigger RED unconditionally:

- HRV collapse: HRV < (baseline − profile-defined floor delta)
- RHR spike: RHR > (baseline + profile-defined ceiling delta)
- Active injury flag in session history
- Composite load = Critical (TSB below profile-defined critical threshold)
- In-session HR drift ≥ profile-defined drift hard limit during an intensity block

### 3.4 Gate Evaluation Sequence

1. **Injury / medical flag** (instant RED if present)
2. **HRV + RHR composite** (autonomic gate)
3. **Sleep score + subjective fatigue** (recovery gate)
4. **Acute load / TSB** (load gate)
5. **Aggregate color assignment** → apply downgrade rule if needed
6. **In-session drift monitor** (live gate during execution)

---

## 4. Intensity Governor

Governs all sub-maximal steady-state and threshold work.

### 4.1 Ceiling Rule

- **HR ceiling:** Profile-defined threshold ceiling (e.g., 153 bpm for 5K profile)
- **Drift limit:** HR drift during a steady-state block must remain < profile-defined limit
- **RPE check:** If RPE at target pace exceeds profile's RPE band ceiling, reduce pace immediately

### 4.2 Drift Monitoring

Cardiac drift is measured as:

```
drift_% = ((HR_last_5min - HR_first_5min) / HR_first_5min) × 100
```

- Below drift limit → continue
- At or above drift limit → reduce pace to restore control; do not increase intensity
- If drift cannot be controlled after pace reduction → terminate intensity block, convert remainder to easy

### 4.3 Ceiling Hierarchy

> HR ceiling → drift limit → RPE
> All three must be satisfied. The most restrictive signal governs.

---

## 5. VO2 Governor

Governs all maximal or near-maximal efforts (VO2max intervals, race-pace work).

### 5.1 "1 Rep in Reserve" Rule

Every VO2 interval set must end with at least 1 repetition in reserve. The athlete should be able to complete one more rep at the same quality if forced to. If that capacity is absent:

- Stop the set immediately
- Log as a "capacity flag"
- Do not continue VO2 work that session

### 5.2 Collapse Prevention

No-collapse conditions (all must be met to initiate VO2 work):

- Gate color = GREEN
- TSB ≥ profile-defined VO2 TSB floor
- No HRV collapse (autonomic gate = pass)
- Previous session: not VO2 or race-pace (minimum rest days = profile-defined)

If any condition fails → VO2 block is removed and replaced with Z2 or rest.

### 5.3 Form Degradation Stop

During a VO2 interval: if running form visibly collapses or target pace cannot be held within tolerance on the current rep, the set ends. Grinding through with degraded form is not counted as a successful rep and is logged as a warning.

---

## 6. Fueling Switch

Fueling strategy is binary at the session level based on training intent.

### 6.1 Quality Day (Intensity / VO2 sessions)

- Adequate carbohydrate availability required before the session
- No fasted or low-carb state for sessions with HR target above Zone 2 ceiling
- Post-session: protein + carbohydrate within recovery window (profile-defined)
- Rationale: intensity without fuel substrate = forced catabolism + elevated injury risk

### 6.2 Easy Day (Z1/Z2 and recovery sessions)

- Fueling is flexible; fat-adaptation stimulus is acceptable
- Low-carb or fasted state is permissible for pure Z2 aerobic work only
- Low-carb is never permissible in the intensity phase of a training block

### 6.3 Phase Lock Rule

> **No low-carb protocols during an active intensity phase.**
> An intensity phase is defined as any training week containing ≥1 threshold, tempo, or VO2 session.

---

## 7. Weekly Structure Template

Generic periodized week. Specific session counts and types are defined per profile.

| Day slot | Allowed session types | Gate requirement |
|---|---|---|
| Intensity day | Threshold, Tempo, VO2 | GREEN required |
| Long run day | Aerobic long (Z2) | GREEN or YELLOW (reduce if YELLOW) |
| Easy day | Z1/Z2 recovery | GREEN, YELLOW, or RED (convert to rest if RED) |
| Rest day | Complete rest or mobility | Any gate color |

**Constraint:** Intensity days may not be scheduled on consecutive days. If gate forces a rest on scheduled intensity day, the intensity day is lost — not shifted forward onto the next day.

---

## 8. Longevity Bias

This is the system's fundamental rule and takes precedence over all optimization objectives.

> **When any safety signal conflicts with any performance objective, safety wins.**

Operationally:
- A hard stop overrides a PR attempt
- A YELLOW gate overrides a coach's prescribed intensity session
- A RED gate overrides race preparation
- Accumulated overrides are never normalized; they are logged and factored into sustainability scoring

The system will never reward overreaching as discipline. Consistency over months outweighs heroic individual sessions.

---

## 9. Success Criteria (Generic)

A training block is considered successful when:

1. Gate compliance ≥ 90% of sessions (sessions executed at correct gate-assigned intensity)
2. No forced RED sessions in the final 2 weeks before a target event
3. Drift control maintained (< profile limit) in ≥ 85% of steady-state sessions
4. No injury flags in final 4 weeks
5. TSB within positive range (fresh) at event taper

---

## 10. Failure Patterns (Canonical)

The following patterns indicate model misuse or athlete non-compliance:

| Pattern | Signal | Consequence |
|---|---|---|
| Override normalization | ≥3 overrides in 7 days | Sustainability score penalty; block review triggered |
| Intensity on RED | Gate = RED, intensity executed | Hard audit; next 48h forced recovery |
| Drift ignored | Drift > limit, session continued | Session invalidated; VO2 work blocked next session |
| Low-carb + intensity | Fasted VO2 or threshold | Fuel availability warning; session flagged |
| Consecutive intensity | Two intensity days back-to-back | Structural violation; recovery day inserted |

---

## 11. Profile Extension Points

Each profile document (`profiles/<NAME>.md`) must define the following parameters to instantiate this framework:

- HR ceiling for threshold/tempo work (bpm)
- HR ceiling for Z2 work (bpm)
- Drift hard limit (%)
- Drift soft limit (%)
- HRV negative threshold (delta from baseline, ms)
- RHR negative threshold (delta from baseline, bpm)
- Sleep score negative threshold
- Subjective fatigue negative threshold (1–10)
- TSB critical floor (AU)
- TSB VO2 floor (AU)
- VO2 minimum rest days between sessions
- Weekly structure (session count per type)
- Recovery window post-intensity (hours)
- RPE band per zone

---

*This document is a spec, not implementation. All parameter values are in profile files. Zero code changes are implied.*
