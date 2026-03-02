# ADR 0009 — Safety Gate Hardening: C1 & C2 Resolution from ADR-0007

| Field | Value |
|-------|-------|
| **Date** | 2026-03-02 |
| **Branch** | `claude/phase-5-maintenance-oUitY` |
| **Type** | Implementation — safety-critical fix |
| **Scope** | `titan/science/governance_engine.py` · `tests/test_p0_safety_gates.py` |

---

## Context

ADR-0007 (Intensity Governance Architecture Audit, 2026-02-25) identified five
safety-critical conflicts (C1–C5) between `docs/training/DECISION_MODEL.md` and
the then-current `governance_engine.py`. Since that audit:

- **C3** (TSB critical floor gate) — resolved: implemented as hard stop H2.
- **C4** (injury flag gate — absent) — resolved: implemented as hard stop H3.
- **C5** (subjective fatigue hardcoded) — resolved: implemented as hard stop H4.

`tests/test_p0_safety_gates.py` was written after those fixes to document and
test the implemented behavior. **However, two conflicts remain:**

---

### C1 — HRV Collapse: AND Logic Violates OR Semantics

**Spec** (`DECISION_MODEL.md` Gate 2):

```
hrv_collapse = (hrv < hrv_baseline_7d − profile.hrv_collapse_delta_ms)
rhr_collapse = (rhr > rhr_baseline_7d + profile.rhr_collapse_delta_bpm)

IF hrv_collapse OR rhr_collapse → autonomic_gate = RED (HARD STOP)
```

`GOVERNANCE_PHILOSOPHY §5`: *"Never ignore HRV collapse."*

**Actual** (`governance_engine.py` `_check_hard_stops()`, gate H1 at time of
audit / after prior fixes):

```python
h1_trigger = (
    today_hrv < baseline_hrv - HARD_STOP_HRV_DELTA
    and today_rhr > baseline_rhr + HARD_STOP_RHR_DELTA   # ← AND, not OR
)
```

**Impact:** An athlete with HRV collapsed 20 ms below baseline but normal RHR
passes all hard stops and can receive an intensity prescription. This directly
violates the safety-first governance contract.

**Status: VIOLATED**

---

### C2 — RHR Spike: AND Logic Violates OR Semantics

Same root cause. RHR spike above `HARD_STOP_RHR_DELTA` alone does not trigger
a hard stop — it only fires in conjunction with HRV collapse.

**Impact:** An athlete with elevated RHR (acute autonomic stress, illness onset,
dehydration) and normal HRV variability passes all hard stops.

**Status: VIOLATED**

---

### Additional: Gate Evaluation Order Mismatch

**Spec** (DECISION_MODEL §4, canonical evaluation sequence):

| Step | Gate |
|------|------|
| **1** | Injury / Medical Flag — **first, non-bypassable** |
| 2 | Autonomic Gate (HRV + RHR) |
| 3 | Recovery Gate |
| 4 | Load Gate (TSB) |

**Actual** (prior implementation order in `_check_hard_stops()`):

1. H1 — HRV/RHR (AND)
2. H2 — TSB floor
3. H3 — Injury flag ← should be Gate 1
4. H4 — Extreme fatigue

**Impact:** Minor in practice (all gates are evaluated non-exclusively; final
session_type always reflects worst outcome). However, the injury gate mutating
session_plan after HRV/RHR mutation creates a less predictable audit trail and
violates the documented evaluation hierarchy.

---

## Decision

### 1. Split H1 into independent OR gates (H2 + H3)

`HRV collapse` and `RHR spike` become **independent hard-stop conditions**.
Either alone is sufficient to trigger REST. This directly implements DECISION_MODEL Gate 2.

### 2. Reorder gates to match DECISION_MODEL §4

New evaluation order in `_check_hard_stops()`:

| Label | Condition | Outcome | DECISION_MODEL Gate |
|-------|-----------|---------|---------------------|
| **H1** | `injury_flag == True` | REST, max_zone=1 | Gate 1 |
| **H2** | `hrv < baseline − HARD_STOP_HRV_DELTA` | REST, max_zone=1 | Gate 2a |
| **H3** | `rhr > baseline + HARD_STOP_RHR_DELTA` | REST, max_zone=1 | Gate 2b |
| **H4** | `tsb ≤ HARD_STOP_TSB_FLOOR` | EASY, max_zone=2 | Gate 4 |
| **H5** | `subjective_fatigue ≥ SUBJECTIVE_FATIGUE_EXTREME` | EASY, max_zone=2 | Gate 3/aggregate |

### 3. Update `test_p0_safety_gates.py`

- **Remove** `test_H1_only_hrv_drops_does_not_fire` — was documenting wrong
  AND behavior; contradicts DECISION_MODEL and GOVERNANCE_PHILOSOPHY.
- **Remove** `test_H1_only_rhr_spikes_does_not_fire` — same reason.
- **Add** `test_H2_hrv_collapse_alone_forces_rest` — verifies OR semantics.
- **Add** `test_H3_rhr_spike_alone_forces_rest` — verifies OR semantics.
- **Update** all gate-label assertions: H1→H2 (HRV), H2→H4 (TSB), H3→H1
  (injury), H4→H5 (fatigue).

---

## Consequences

### Positive

- HRV collapse alone now correctly prescribes REST — closes C1.
- RHR spike alone now correctly prescribes REST — closes C2.
- Injury flag is evaluated first, matching DECISION_MODEL §4 canonical order.
- Audit trail gate labels now align with DECISION_MODEL gate numbers.
- All five ADR-0007 critical conflicts (C1–C5) are resolved.

### Negative / Trade-offs

- Tests that explicitly verified AND behavior are removed. This is correct:
  those tests documented a safety defect, not a valid design choice.
- Gate labels shift (H1–H4 → H1–H5). Any external tooling parsing raw log
  `governance_gate` fields for `H1`–`H4` will need to be updated. No such
  tooling exists in this codebase beyond the test suite.

### Not changed

- Threshold constants (`HARD_STOP_HRV_DELTA`, `HARD_STOP_RHR_DELTA`,
  `HARD_STOP_TSB_FLOOR`, `SUBJECTIVE_FATIGUE_EXTREME`) — unchanged.
- VO2 eligibility gate, fueling gate, 2-of-4 rule, APL gates — unchanged.
- `GovernanceContracts`, `IntensityGovernor`, `VolumeLoadGauge`,
  `AdaptivePriorityLock`, `OutcomeTracker` — unchanged.
- CI pipeline — unchanged; existing coverage thresholds hold.

---

## ADR-0007 Resolution Status After This ADR

| Conflict | Finding | Resolution |
|----------|---------|------------|
| C1 — HRV collapse hard stop | AND logic, collapse alone not caught | **CLOSED** — H2 fires independently |
| C2 — RHR spike hard stop | AND logic, spike alone not caught | **CLOSED** — H3 fires independently |
| C3 — TSB critical floor gate | Absent | Closed prior (now relabeled H4) |
| C4 — Injury flag gate | Absent (highest-priority gate missing) | Closed prior (now relabeled H1, correct priority) |
| C5 — Subjective fatigue hardcoded | 2-of-4 incomplete | Closed prior (now relabeled H5) |

All five critical conflicts from ADR-0007 are resolved.

---

## References

- `docs/training/DECISION_MODEL.md` §2 (Gate 2), §4 (canonical evaluation order)
- `docs/architecture/GOVERNANCE_PHILOSOPHY.md` §5 (never ignore HRV collapse)
- `docs/adr/0007-intensity-governance-architecture-audit.md` — original audit
- `titan/science/governance_engine.py` — implementation target
- `tests/test_p0_safety_gates.py` — test suite target
- `titan/config/thresholds.py` — threshold constants (unchanged)
