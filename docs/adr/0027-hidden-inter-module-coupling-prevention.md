# ADR-0027 — Hidden Inter-Module Coupling Prevention

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Architect Observations V6 — Risk #2 (Hidden Inter-Module Dependencies)
**Phase:** 7.8 Hardening

---

## Context

The TITAN OS pipeline has a logical data flow:

```
Garmin Sync → DatabaseManager → Science Engines → GovernanceEngine
                                                         ↓
                                               DailyCoach (Orchestration)
                                                         ↓
                                               WeeklyPlanner / NutritionOptimizer
```

Each layer appears independent, but coupling accumulates through **shared assumptions**
rather than shared imports. These assumptions are invisible to static analysis and do
not cause test failures — they cause silent behaviour changes when one module evolves
and another does not.

### Observed and Projected Coupling Patterns

**Type A — Schema assumption coupling:**
`DailyCoach` hydrates engines by calling `db.get_daily_metrics(today)` and passing the
result directly to `ReadinessEngine`. If the shape of `get_daily_metrics()` changes (e.g.,
a field is renamed from `hrv_ms` to `hrv_rmssd_ms`), `ReadinessEngine` silently receives
`None` for the renamed field. No `ImportError`, no `TypeError` — just a wrong readiness
score.

**Type B — Ordering assumption coupling:**
`GovernanceEngine` assumes that by the time it is called, `CTL/ATL` have been correctly
computed by `TSBEngine`. If `DailyCoach` step ordering changes (steps 3 and 4 swapped),
`GovernanceEngine` evaluates on stale TSB values. ADR-0018 Phase A introduced the
`DecisionPipeline` to formalise this, but Phase B (full effect-runner split) is deferred.

**Type C — Configuration constant coupling:**
`VolumeLoadGauge` and `IntensityGovernor` both use thresholds from `thresholds.py` but
independently interpret what "readiness" means for gate decisions. If a threshold is
changed for one context, the other is silently affected.

**Type D — Test assumption coupling:**
Test fixtures construct objects with specific field values that are valid today but may
not reflect future object schema. The test passes because the object was created, not
because the scenario was correct. (This is also addressed by T4-24 / fixture factory.)

### Why This Is Dangerous at Scale

At 46 modules, each with 2–3 callers, the total implicit coupling surface is ~100+
assumption pairs. No individual pair is catastrophic; the accumulation is. When the
system crosses the Phase 8 boundary (multi-sport adapter), these assumptions will
produce a class of bugs that is extremely difficult to diagnose because each individual
module looks correct in isolation.

---

## Decision

**Introduce explicit boundary contracts at the three highest-risk coupling points,
and add a coupling audit to the Phase 8 Entry Gate (ADR-0022, Gate G4).**

### Boundary Contract 1 — DatabaseManager → Science Engine (schema coupling)

`DatabaseManager` return types must be typed `TypedDict` or `dataclass` instances,
not raw `dict`. This converts a runtime assumption failure into a static type error
caught by tools.

```python
# titan/core/database.py
from typing import TypedDict

class DailyMetricsRow(TypedDict):
    date: str
    hrv_ms: float | None
    rhr_bpm: float | None
    subjective_fatigue: int | None
    # ... complete field list
```

Science engines that receive `DailyMetricsRow` get IDE/type-checker warnings if they
access a field that does not exist in the schema. A schema rename triggers a type error
at every callsite — the failure is loud and immediate.

**Engineering execution:** T4-26 (Tier 4 — below).

### Boundary Contract 2 — GovernanceEngine → DailyCoach (ordering coupling)

`GovernanceEngine.evaluate()` must assert that its required inputs are populated before
evaluating:

```python
def evaluate(self, inputs: GovernanceInputs) -> GovernanceResult:
    assert inputs.ctl is not None, "TSBEngine must run before GovernanceEngine"
    assert inputs.atl is not None, "TSBEngine must run before GovernanceEngine"
    ...
```

These are `AssertionError` guards — they fire in tests immediately if step ordering
changes. In production (`python -O`), assertions are stripped, so the failure is a
test-only gate, not a runtime dependency. **Do not use `assert` for safety-critical
paths** — use explicit `if / raise` there (ADR-0009). This is about ordering contracts.

**This is a test-only mechanism.** Production code should fail gracefully (ADR-0020).
The assertion is documentation that executes.

### Boundary Contract 3 — Coupling Audit Gate (ADR-0022 supplement)

Add to the **Phase 8 Entry Gate** (ADR-0022, Gate G4 update):

> **G4b — Coupling audit:** Run `python -m pytest tests/test_architectural_invariants.py
> -k coupling -v` → zero violations.

`tests/test_architectural_invariants.py` (T4-19, already exists) gains a new test:

```python
def test_no_cross_layer_direct_import():
    """
    Science modules must not import from orchestration/.
    Orchestration modules must not import from ui/.
    UI modules must not import from science/ directly (only via orchestration/).
    """
```

This catches new Type B couplings before they reach production.

---

## Options Considered

### Option A — Runtime duck typing (current state)
Modules pass `dict` objects with no schema contract. Changes are caught by tests if
the affected test exercises the changed field.

**Rejected for Phase 8+.** The failure surface grows quadratically with module count.
By Phase 8, this is unmanageable.

### Option B — Full Protocol/ABC interface layer for every module boundary
Define `Protocol` classes for all engine inputs and outputs.

**Deferred to Phase 9.** High blast radius. ADR-0018 Phase B covers this at the kernel
boundary. Phase 9 extends it to all science engine boundaries. Not appropriate for
Phase 7.8 scope.

### Option C — TypedDict at DB boundary + ordering assertions + coupling test (SELECTED)
Targeted at the three highest-risk coupling points. Low blast radius. Testable.
Compatible with existing code without a full refactor.

---

## Consequences

**Positive:**
- Schema renames at the DB layer become statically detectable.
- Engine ordering violations become test failures rather than silent behaviour changes.
- The coupling audit test makes Type D coupling visible before Phase 8.

**Neutral:**
- `TypedDict` requires Python 3.8+ (already required; no new constraint).
- Existing `dict`-based callers must be migrated. Migration is mechanical and can be
  done incrementally (one `TypedDict` per `DatabaseManager` return method).

**Negative:**
- `assert` for ordering contracts is stripped with `python -O`. This is intentional
  (production should not crash on ordering; tests should). But it means production
  ordering bugs are still silent until tests catch them.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0018 | Kernel Boundary (Phase A: `DecisionPipeline`). This ADR targets the DB→Engine and Engine→Orchestration boundaries; ADR-0018 Phase B targets the full Decision/Effect split. Complementary; not duplicated. |
| ADR-0022 | Phase 8 Entry Gate. G4b (coupling audit) is added as a gate criterion. |
| ADR-0019 | T4-19 architectural invariant tests. New coupling test is added to that suite. |

---

## Status

Accepted. Engineering execution: **T4-26** (Tier 4 — maintainability; independent).
