# Adaptive Priority Lock (APL) — Architecture Specification

| Field | Value |
|-------|-------|

| **Status** | **Implemented** — `titan/science/adaptive_priority_lock.py` |
| **Layer** | `titan/science/` |
| **Module** | `titan/science/adaptive_priority_lock.py` |
| **Tests** | `tests/test_apl_integration.py` — 64 tests |
| **Related ADR** | [0007-intensity-governance-architecture-audit.md](../adr/0007-intensity-governance-architecture-audit.md) · [0008-adaptive-priority-lock-and-vlg-specs.md](../adr/0008-adaptive-priority-lock-and-vlg-specs.md) |

| **Status** | Proposed — documentation only |
| **Layer** | `titan/science/` |
| **Proposed module** | `titan/science/adaptive_priority_lock.py` |
| **Related ADR** | [0007-adaptive-priority-lock-placement.md](../adr/0007-adaptive-priority-lock-placement.md) |

| **Related spec** | [volume_load_gauge.md](./volume_load_gauge.md) |

---

## 1. Purpose

The Adaptive Priority Lock (APL) is a proposed science-layer engine that acts
as a **pre-governance priority resolver**. It answers a single question before
the `GovernanceEngine` runs:

> *Given the current training phase, volume load, and autonomic state, in what
> order should the three governance gates be evaluated, and what adaptive
> thresholds should apply to each?*

The existing `GovernanceEngine` evaluates three hard binary gates
(`PARASYMPATHETIC_GUARD`, `OVERRIDE_LOCKDOWN`, `CS_CONFIDENCE_LOCK`) in a
fixed sequence with fixed thresholds. This is correct and must remain unchanged.
APL adds phase-aware, load-aware **ordering** and **threshold scaling** — it
does not modify any gate logic.

---

## 2. Design Principles

1. **GovernanceEngine gates are not touched.** APL produces a `priority_vector`
   injected into the `context` dict. `GovernanceEngine.apply_constraints()`
   reads `context.get('priority_vector', {})` and adjusts its evaluation order
   accordingly. No gate condition is altered.

2. **APL is a pure resolver — stateless per call.** It holds no rolling history,
   writes no database entries, and triggers no side effects.

3. **DailyCoach remains an orchestrator only.** APL is invoked via a single
   method call between Steps 9a and 9b of `run_morning_routine()`. The coach
   passes pre-computed inputs; APL returns a dict.

4. **PARASYMPATHETIC_GUARD always ranks #1.** It is a safety gate. No phase or
   load context can demote it below priority rank 1.

5. **Layer purity.** APL lives in `titan/science/` (not `orchestration/`,
   not `features/`, not `utils/`) because it performs physiological reasoning,
   not sequencing, planning, or utility math.

---

## 3. Inputs

| Input | Source | Type |
|-------|--------|------|
| `vlg_state` | `VolumeLoadGauge.compute()` | `VLGState` |
| `afi_constraints` | `AutonomicFusionEngine.get_readiness_constraints()` | `dict` |
| `phase` | `PeriodizationManager.calculate_phase()` | `str` |
| `cs_confidence` | `CriticalSpeedTracker.confidence` | `float` (0.0–1.0) |

---

## 4. Outputs

```python
{
    "priority_vector": {
        "PARASYMPATHETIC_GUARD": 1,   # always rank 1
        "CS_CONFIDENCE_LOCK":   2,    # example — phase-dependent
        "OVERRIDE_LOCKDOWN":    3,    # example — phase-dependent
    },
    "lock_thresholds": {
        "acwr_ceiling":     float,    # phase-scaled ACWR upper bound
        "tsb_floor":        float,    # context-aware TSB minimum for quality sessions
        "cs_min_confidence": float,   # adaptive CS confidence minimum
    },
    "apl_rationale": {
        "PARASYMPATHETIC_GUARD": str,  # human-readable justification per gate
        "CS_CONFIDENCE_LOCK":   str,
        "OVERRIDE_LOCKDOWN":    str,
    },
}
```

---

## 5. Priority Resolution Rules

### 5.1 PARASYMPATHETIC_GUARD (always rank 1)

No rule may promote any other gate above this. When `afi_constraints
['parasympathetic_guard']['triggered']` is `True`, the guard has already
clamped readiness to ≤25 and disabled Z4/Z5. APL confirms it remains rank 1
regardless of phase.

A lock never raises intensity (ADR-0068): the guard gives `min(current, EASY)`
and `min(current zone, 2)`, so a `REST` from a hard stop stays `REST`. The
`OVERRIDE_LOCKDOWN` reads the athlete's own 14-day override ratio
(`athlete_id` in the governance context); without an `athlete_id` it fails
closed (locked, zone 2) and never reads the owner's ratio.

### 5.2 Phase × Load matrix

| Phase | VLG load_band | Gate rank 2 | Gate rank 3 | Rationale |
|-------|--------------|-------------|-------------|-----------|
| `PEAK` | any | `CS_CONFIDENCE_LOCK` | `OVERRIDE_LOCKDOWN` | Race-quality sessions require verified CS model; load risk secondary |
| `BUILD` | `OVERLOAD` or `CRITICAL` | `OVERRIDE_LOCKDOWN` | `CS_CONFIDENCE_LOCK` | Protect adaptation; block excess volume before CS refinement |
| `BUILD` | `OPTIMAL` or `UNDERLOAD` | `CS_CONFIDENCE_LOCK` | `OVERRIDE_LOCKDOWN` | CS model accuracy needed for quality session prescription |
| `BASE` | any | `OVERRIDE_LOCKDOWN` | `CS_CONFIDENCE_LOCK` | Volume integrity critical; CS model still accumulating data |
| `TAPER` | any | `CS_CONFIDENCE_LOCK` | `OVERRIDE_LOCKDOWN` | CS model locks in race-pace accuracy; volume naturally drops |
| `POST_RACE` | any | `OVERRIDE_LOCKDOWN` | `CS_CONFIDENCE_LOCK` | Load must stay well below threshold during recovery |

### 5.3 Adaptive threshold scaling

| Threshold | Default | PEAK adjustment | BUILD (OVERLOAD) | TAPER |
|-----------|---------|----------------|-----------------|-------|
| `acwr_ceiling` | 1.30 | 1.10 (tighter) | 1.15 | 1.25 |
| `tsb_floor` | −50 | −20 (fresher required) | −40 | −15 |
| `cs_min_confidence` | 0.70 | 0.85 (higher bar) | 0.60 | 0.80 |

These override the static defaults inside `GovernanceEngine` only when APL is
present. If APL is not injected, governance falls back to its existing static
thresholds unchanged.

---

## 6. Data Flow

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                     TITAN KERNEL — APL DATA FLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 [GARMIN SYNC]──activities, HRV, HRR, sleep, weight──────────────────┐
                                                                      │
                                                                      ▼
 [HRV ENGINE] ──ln_rmssd_deviation──→ [AUTONOMIC ENGINE]             │
 [GARMIN HRR] ──hrr_60──────────────→     · AFI (-1..+1)             │
                                           · 48h CNS buffer           │
                                           · para_guard {triggered,   │
                                             clamp, disabled_zones}   │
                                                      │               │
                                               afi_constraints        │
                                                      │               │
                                                      ▼               ▼
 [TSB ENGINE] ──CTL/ATL/TSB──┐                                        │
 [ACWR ENGINE] ──acwr────────┤──→ [VOLUME LOAD GAUGE]                 │
 [GLYCOGEN] ──daily_debt─────┘         · composite_load (0..1)        │
                                        · load_band                   │
                                        · tsb, acwr, glycogen_debt    │
                                                      │               │
                                                vlg_state             │
                                                      │               │
 [PERIODIZATION] ──phase ────────────────────────────┤               │
 [CS TRACKER] ──confidence ──────────────────────────┤               │
                                                      │               │
                                                      ▼               │
                                   ┌──────────────────────────────┐   │
                                   │  ADAPTIVE PRIORITY LOCK      │   │
                                   │                              │   │
                                   │  Inputs:                     │   │
                                   │    vlg_state                 │   │
                                   │    afi_constraints           │   │
                                   │    phase                     │   │
                                   │    cs_confidence             │   │
                                   │                              │   │
                                   │  Phase-aware rules:          │   │
                                   │  PEAK  → CS_LOCK priority ↑  │   │
                                   │  BUILD → OVERRIDE_LOCK ↑     │   │
                                   │  TAPER → all thresholds ↓    │   │
                                   │  VLG CRITICAL → PARA first   │   │
                                   │                              │   │
                                   │  Output: priority_vector     │   │
                                   │    {PARASYMPATHETIC_GUARD: 1 │   │
                                   │     CS_CONFIDENCE_LOCK: 2    │   │
                                   │     OVERRIDE_LOCKDOWN: 3}    │   │
                                   │  + lock_thresholds (adaptive)│   │
                                   └──────────────────────────────┘   │
                                                      │               │
                                           priority_vector            │
                                        + lock_thresholds             │
                                                      │               │
                                                      ▼               │
 [WEEKLY PLANNER] ──today_session──→ [GOVERNANCE ENGINE] ←───────────┘
                                        · Gate 1: PARASYMPATHETIC_GUARD
                                        · Gate 2: (phase-resolved)
                                        · Gate 3: (phase-resolved)
                                        (order from priority_vector)
                                        (thresholds from lock_thresholds)
                                                      │
                                              session_plan (post-governance)
                                                      │
                                                      ▼
                                         [DAILY COACH → TELEGRAM BOT]
                                           (LLM receives result only;
                                            never computes priority)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  KEY:  [existing engine]   [EXISTING — consumes APL output]   [NEW]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 7. Proposed Class Signature

```python
class AdaptivePriorityLock:
    """
    Pre-governance priority resolver.

    Reads VLGState, AFI constraints, training phase, and CS confidence.
    Produces a priority_vector and adaptive lock_thresholds that are
    injected into GovernanceEngine.apply_constraints() via the context dict.

    Stateless: no instance state is mutated between calls.
    No DB access. No side effects.
    """

    # Priority rank 1 is always PARASYMPATHETIC_GUARD — non-negotiable
    _SAFETY_GATE = "PARASYMPATHETIC_GUARD"

    def resolve(
        self,
        vlg_state: VLGState,
        afi_constraints: dict,
        phase: str,
        cs_confidence: float,
    ) -> dict:
        """
        Resolve gate priority and adaptive thresholds for the current context.

        Args:
            vlg_state:       Aggregated load state from VolumeLoadGauge.compute().
            afi_constraints: Output of AutonomicFusionEngine.get_readiness_constraints().
            phase:           Current periodization phase string
                             (BASE / BUILD / PEAK / TAPER / POST_RACE).
            cs_confidence:   CriticalSpeedTracker.confidence, float 0.0–1.0.

        Returns:
            dict with keys:
              priority_vector   — {gate_name: int rank, ...}
              lock_thresholds   — {threshold_name: float, ...}
              apl_rationale     — {gate_name: str explanation, ...}
        """
        ...
```

---

## 8. Integration Points

| # | Location | Nature of change |
|---|----------|-----------------|
| **IP-1** | `titan/science/__init__.py` | Add `AdaptivePriorityLock` to exports and `__all__` |
| **IP-2** | `titan/orchestration/daily_coach.py` `__init__()` | Optional `adaptive_priority_lock` param (auto-instantiated if `None`) |
| **IP-3** | `DailyCoach.run_morning_routine()` Step 9a | `priority_vector = self.apl.resolve(vlg_state, afi_constraints, phase, cs_confidence)` |
| **IP-4** | `DailyCoach.run_morning_routine()` Step 9b | `context['priority_vector'] = priority_vector` passed into `governance.apply_constraints()` |
| **IP-5** | `GovernanceEngine.apply_constraints()` | Read `context.get('priority_vector', {})` to reorder gate blocks; static fallback if absent |

---

## 9. Files Affected (future implementation)

| Path | Action | Notes |
|------|--------|-------|
| `titan/science/adaptive_priority_lock.py` | **CREATE** | New module; no existing file touched |
| `titan/science/volume_load_gauge.py` | **CREATE** | Dependency; see [volume_load_gauge.md](./volume_load_gauge.md) |
| `titan/science/__init__.py` | Add export | `AdaptivePriorityLock` added to `__all__` |
| `titan/orchestration/daily_coach.py` | Inject | Optional constructor param + resolve call in Step 9a |
| `titan/science/governance_engine.py` | Read-only context key | `context.get('priority_vector', {})` — no gate logic changed |

---

## 10. What APL Does Not Do

- Does **not** modify any gate condition inside `GovernanceEngine`.
- Does **not** bypass any hard gate.
- Does **not** hold athlete history or accumulate state.
- Does **not** access the database.
- Does **not** produce a Telegram message or any user-facing output.
- Does **not** replace the `AutonomicFusionEngine` or any other engine.
- Is **not** the LLM reasoning layer. The LLM (Telegram narrative) receives
  only the post-governance session plan, not the priority vector.
