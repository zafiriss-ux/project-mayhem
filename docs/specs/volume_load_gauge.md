# Volume Load Gauge (VLG) — Specification

| Field | Value |
|-------|-------|
| **Status** | Proposed — documentation only |
| **Layer** | `titan/science/` |
| **Proposed module** | `titan/science/volume_load_gauge.py` |
| **Related ADR** | [0007-adaptive-priority-lock-placement.md](../adr/0007-adaptive-priority-lock-placement.md) |
| **Related spec** | [adaptive_priority_lock.md](./adaptive_priority_lock.md) |

---

## 1. Purpose

The Volume Load Gauge (VLG) is a proposed aggregation engine that unifies three
existing but independently invoked load-state signals into a single typed output:

| Source engine | Signal produced | Current call site |
|---|---|---|
| `titan/science/tsb_engine.py` | CTL, ATL, TSB, TSB status | `DailyCoach.run_morning_routine()` Step 5 |
| `titan/science/acwr_engine.py` | Acute:Chronic ratio, risk band | `WeeklyPlanGenerator.analyze_past_week()` |
| `titan/science/glycogen_model.py` | daily_debt (g), status string | `DailyCoach.run_morning_routine()` Step 6 |

These three engines are each mathematically complete, well-tested, and stable.
The VLG does **not** modify them. It reads their outputs and composes a unified
`VLGState` object that downstream consumers (primarily the Adaptive Priority
Lock) can interrogate without importing each engine individually.

---

## 2. Why a Unified Abstraction Is Needed

The Adaptive Priority Lock (APL) requires knowledge of the athlete's current
load state to determine which governance gates should rank higher in a given
context. Without VLG, the APL would need to accept three separate engine
references and manually interpret their outputs. This creates coupling that
scales poorly as additional load signals are added (e.g., D-prime depletion,
osmotic stress index).

VLG provides:

- **Single responsibility boundary**: one place where raw load metrics are
  translated into a human-readable, machine-actionable load band.
- **Composability**: APL, governance engine, and future ML modules all consume
  the same `VLGState` object.
- **No new computation**: VLG is a pure aggregator; it runs no EMA, no
  curve fitting, no statistical inference. All computation remains in the
  source engines.

---

## 3. VLGState — Proposed Data Contract

```python
@dataclass
class VLGState:
    # ── Raw signal pass-through ───────────────────────────────────────────
    tsb: float              # Training Stress Balance (CTL - ATL)
    tsb_status: str         # e.g. "PRODUCTIVE OVERLOAD", "FRESH"
    ctl: float              # Chronic Training Load (42d EMA)
    atl: float              # Acute Training Load (7d EMA)

    acwr: float             # Acute:Chronic Workload Ratio
    acwr_risk: str          # "UNDERTRAINING" / "SWEET SPOT" / "DANGER ZONE"

    glycogen_debt: float    # Current glycogen deficit (grams)
    glycogen_status: str    # e.g. "LOW", "MODERATE", "CRITICAL"

    # ── Derived composite ─────────────────────────────────────────────────
    composite_load: float   # Normalised load index, range 0.0 (no load) → 1.0 (max)
    load_band: str          # "UNDERLOAD" / "OPTIMAL" / "OVERLOAD" / "CRITICAL"
```

### composite_load derivation (proposed formula)

```
composite_load =
    0.50 × normalize(ATL,  min=0, max=150)   # acute fatigue dominates
  + 0.30 × normalize(ACWR, min=0, max=1.5)   # injury risk contribution
  + 0.20 × normalize(glycogen_debt, min=0, max=500g)

load_band thresholds:
    composite_load < 0.25  → UNDERLOAD
    0.25 ≤ load < 0.55     → OPTIMAL
    0.55 ≤ load < 0.80     → OVERLOAD
    load ≥ 0.80            → CRITICAL
```

---

## 4. Proposed Class Signature

```python
class VolumeLoadGauge:
    """
    Unified load-state aggregator.

    Reads outputs from TSBEngine, ACWREngine, and GlycogenDebtAccumulator.
    Produces a VLGState dataclass consumed by AdaptivePriorityLock and
    downstream reporting modules.

    No computation is performed here — all metrics are calculated by their
    respective source engines before being passed in.
    """

    def compute(
        self,
        tsb_engine: TSBEngine,
        acwr_engine: ACWREngine,
        glycogen_accum: GlycogenDebtAccumulator,
    ) -> VLGState:
        """
        Aggregate current load state into a VLGState.

        Args:
            tsb_engine:     Fully hydrated TSBEngine (daily_loads populated).
            acwr_engine:    Fully hydrated ACWREngine (current ACWR computed).
            glycogen_accum: Updated GlycogenDebtAccumulator (post overnight resynthesis).

        Returns:
            VLGState with all fields populated and load_band assigned.
        """
        ...
```

---

## 5. Integration Point in DailyCoach

VLG is invoked after Step 6 (glycogen update) and before Step 9b (governance),
using data already computed in earlier steps:

```
Step 5  → tsb_value, tsb_status already available
Step 6  → glycogen_accum updated
           ↓
Step 6b → vlg_state = VolumeLoadGauge.compute(tsb_engine, acwr_engine, glycogen_accum)
           ↓
Step 7  → ReadinessEngine (unchanged)
Step 8  → WeeklyPlanner (unchanged)
           ↓
Step 9a → priority_vector = AdaptivePriorityLock.resolve(vlg_state, afi_constraints, ...)
           ↓
Step 9b → GovernanceEngine.apply_constraints(..., context={'priority_vector': priority_vector})
```

The `DailyCoach` constructor receives `volume_load_gauge` as an optional
parameter, auto-instantiated if `None`, consistent with the existing pattern
used for `autonomic_engine`, `cs_tracker`, `glycogen_accum`, and `governance`.

---

## 6. Constraints

- **No Python file is modified by this document.** VLG does not exist yet as
  runtime code. This spec is design-only groundwork.
- The VLG must be **stateless** between calls. It does not hold a reference
  to any engine between invocations.
- VLG must not access the database directly. All DB-backed values arrive
  pre-computed via the source engines.
- VLG must not trigger any side effects (no Telegram, no DB writes, no logging
  beyond debug level).

---

## 7. Files Affected (future implementation)

| Path | Action | Notes |
|------|--------|-------|
| `titan/science/volume_load_gauge.py` | **CREATE** | New module; no existing file touched |
| `titan/science/__init__.py` | Add export | `VolumeLoadGauge`, `VLGState` added to `__all__` |
| `titan/orchestration/daily_coach.py` | Inject | Optional constructor param + call in Step 6b |

No other files require modification.
