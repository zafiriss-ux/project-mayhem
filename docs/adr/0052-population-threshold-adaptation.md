# ADR-0052 — Population-Specific Threshold Adaptation via OutcomeTracker

**Date:** 2026-04-04
**Status:** Accepted
**Deferral note (2026-06-12):** Calibration wiring deferred 2026-06-12 per formal deferral
decision. Re-entry: B-3 closed AND owner corpus gate met. Ref: TECHNICAL_DEBT.md T-PRA-18-CAL.
**Deciders:** Architect (Claude) + Owner (Zaf)
**Source:** HD-09 / TITAN_HARDENING_FRAMEWORK_v1.md §1.1
**Related:** ADR-0033 (model aging + multi-athlete), ADR-0035 (OutcomeTracker integrity),
  ADR-0008 (APL spec), ADR-0009 (safety gate hardening)

---

## Context

TITAN OS applies identical governance thresholds (HRV delta, RHR delta, ACWR safe band,
readiness floors) regardless of athlete age, fitness tier, or accumulated training history.
This creates systematic governance error:

- **Masters athletes (>45)** have lower HRV baselines and slower recovery — static thresholds
  produce false positives (unnecessary REST decisions).
- **Beginners** have higher HRV variability — static thresholds produce false negatives
  (missed overreaching signals).
- **Elite athletes** adapt faster — the 10–16 week threshold half-life implied by static
  constants is too long.

The `OutcomeTracker` already collects `decision→outcome` pairs per athlete (ADR-0033,
`AGENTS.md §16`). The `AdaptivePriorityLock` already adjusts the `priority_vector` per
cycle. The missing piece is feeding `OutcomeTracker` divergence signals back into per-athlete
threshold offsets, closing the calibration loop.

---

## Decision

**Per-athlete threshold adaptation via OutcomeTracker feedback loop.**

### Model: Additive offset per athlete, per threshold constant

Each governed threshold `T` (from `titan/config/thresholds.py`) has a per-athlete offset
`δT`, initialized to `0.0`. The effective threshold used at runtime is:

```
effective_T = T_canonical + δT_athlete
```

### Adaptation mechanism

`OutcomeTracker.run_calibration_cycle(athlete_id)` computes:

- `FALSE_POS rate`: governance fired a hard/soft gate but the athlete performed well
  post-session (governance too conservative).
- `FALSE_NEG rate`: governance passed the athlete but post-session outcome was negative
  (governance too permissive).

Adjustment rules (per threshold, per cycle):

| Condition | Action |
|---|---|
| `FALSE_POS > 30%` | Relax threshold: δT adjusted toward permissive direction |
| `FALSE_NEG > 15%` | Tighten threshold: δT adjusted toward conservative direction |
| Either direction | Maximum ±5% of `T_canonical` per cycle (damping ceiling) |
| Any adjustment | Requires `evidence_count ≥ CALIBRATION_MIN_OUTCOME_COUNT` (10) |

### Non-negotiable constraints

1. **Hard-stop constants are never adapted.** `δT = 0.0` always for H1–H5 gates
   (`HARD_STOP_HRV_DELTA`, `HARD_STOP_RHR_DELTA`, `HARD_STOP_TSB_FLOOR`,
   `SUBJECTIVE_FATIGUE_EXTREME`, `HARD_STOP_ILLNESS_FLAG`). These constants are
   safety invariants; adaptation is architecturally forbidden.
2. **Offset bounded:** `|δT| ≤ 20%` of `T_canonical` at all times (hard ceiling; enforced
   at write time by `ThresholdAdapter`).
3. **Damping:** Maximum `±5%` change per calibration cycle per threshold (per T5-05
   constraint pattern).
4. **Per-athlete isolation:** Adaptation is per-athlete only. Cross-athlete learning is
   forbidden (ADR-0040 athlete isolation invariant).
5. **Persistence:** All `δT` values are persisted to the `athlete_threshold_offsets` SQLite
   table (see Stage 1 below). In-memory-only adaptation is not permitted.
6. **Observability:** Every calibration cycle MUST emit a structured event:
   `threshold_calibrated` (level INFO) containing `threshold_name`, `athlete_id`,
   `old_offset`, `new_offset`, `evidence_count`.
7. **Architect review flag:** Cumulative `|δT|` drift > 10% of `T_canonical` MUST set a
   `calibration_review_required` flag in the `athlete_threshold_offsets` row.

### Circuit breaker (AGENTS.md §16.7)

- `FALSE_NEG rate > 20%` over any rolling 30-day window → circuit breaker fires.
- Outcome: automatic freeze of all `δT` updates for the affected athlete; event emitted
  (`calibration_circuit_breaker_open`); manual recalibration required before adaptation
  resumes.

---

## Implementation (Phase 9)

Implementation is deferred to Phase 9. The ADR is accepted now to unblock architectural
planning and to record the HD-09 decision. No production code changes in this commit.

### Stage 1 — Schema (additive, no existing table changes)

New table `athlete_threshold_offsets`:

```sql
CREATE TABLE IF NOT EXISTS athlete_threshold_offsets (
    athlete_id              TEXT    NOT NULL DEFAULT 'default',
    threshold_name          TEXT    NOT NULL,
    offset_value            REAL    NOT NULL DEFAULT 0.0,
    last_calibrated         TEXT    NOT NULL,
    evidence_count          INTEGER NOT NULL DEFAULT 0,
    calibration_review_required INTEGER NOT NULL DEFAULT 0,
    circuit_breaker_open    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (athlete_id, threshold_name)
);
```

### Stage 2 — ThresholdAdapter module

New module: `titan/science/threshold_adapter.py`

- `get_effective_threshold(athlete_id: str, threshold_name: str) -> float`
  Reads canonical constant from `thresholds.py`, applies `δT` from DB.
  Returns `T_canonical` when no row exists (zero-offset default).
- `update_offset(athlete_id: str, threshold_name: str, outcome_data: dict) -> None`
  Applies adaptation logic, enforces all constraints, persists result, emits event.
- Hard-stop guard: if `threshold_name in HARD_STOP_THRESHOLD_NAMES`, raises
  `AdaptationForbiddenError` (never silently returns).

### Stage 3 — GovernanceEngine integration

`GovernanceEngine` accepts an optional `ThresholdAdapter` (constructor injection).

- When present: uses `adapter.get_effective_threshold()` instead of direct constant
  references for non-hard-stop thresholds.
- When absent (default `None`): behavior is unchanged — all canonical constants used
  directly. Full backward compatibility preserved.

### Stage 4 — OutcomeTracker wiring

`OutcomeTracker.run_calibration_cycle(athlete_id)` calls
`ThresholdAdapter.update_offset()` for each threshold with sufficient evidence.
Calibration cycle is triggered by the weekly governance review process.

---

## Consequences

### Positive

- Masters athletes governed correctly without manual threshold adjustment.
- Governance accuracy improves automatically over 30–90 days per athlete.
- Consistent with existing `OutcomeTracker` infrastructure — no new architectural
  concepts introduced.
- Backward compatible: `GovernanceEngine` default behavior is unchanged until an
  adapter is explicitly wired.

### Negative / Risks

- New DB table required (Stage 1 — additive migration, safe).
- `GovernanceEngine` gains an optional dependency (injected; no circular coupling).
- Adaptation can diverge if outcome labeling is biased (mitigated by circuit breaker
  and architect review flag).
- Minimum 10-outcome evidence window means masters adaptation begins ~3–4 weeks into
  tracking, not immediately.

### Not in scope (Phase 9)

- **Population priors** (age-based starting offsets, e.g., `δHRV_DELTA_masters = +2.0`)
  — deferred to Phase 10; requires cross-athlete evidence base.
- **Cross-athlete learning** — architecturally forbidden (ADR-0040).
- **Continuous adaptation** (real-time offset updates) — batch cycle only (weekly).

---

## Compliance

| ADR / Policy | Verdict |
|---|---|
| ADR-0033 (model calibration) | Consistent — extends Layer 3 calibration loop |
| ADR-0040 (athlete isolation) | Compliant — per-athlete offsets, no cross-athlete sharing |
| ADR-0009 (safety gate hardening) | Compliant — hard-stop gates explicitly excluded |
| T5-05 circuit-breaker pattern | Enforced — circuit breaker + damping + domain baseline |
| AGENTS.md §16.7 calibration circuit breaker | Enforced explicitly in Stage 2 |
