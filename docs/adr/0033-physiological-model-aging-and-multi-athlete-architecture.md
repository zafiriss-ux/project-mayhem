# ADR-0033 — Physiological Model Aging & Multi-Athlete Architecture Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V8 — Risks: Calibration Bias, Model Aging, Athlete Adaptation Lag, Single-Athlete Overfitting
**Phase:** 7.9 Hardening (gate for Phase 9 multi-athlete)
**Supplements:** ADR-0014 (ML scaffold), ADR-0023 (physiological bounds), ADR-0032 (explainability), T5-05 (recalibration — extended by this ADR)

---

## Context

TITAN OS was designed, trained, and calibrated against a single athlete. Every constant,
heuristic threshold, and algorithmic weight in the system carries an implicit assumption:
that the athlete whose data shaped it is the athlete the system will always serve.

This creates four compounding risks:

### Risk 1 — Calibration Bias

The physiological models (HRV engine, lactate threshold, critical speed, TRIMP weighting)
have been tuned to one athlete's response curves. A different athlete — with a different
VO₂max trajectory, different HRV range, different stress-recovery pattern — will receive
recommendations derived from a foreign physiology.

**Current state:** No mechanism exists to detect when the active athlete's physiological
profile diverges from the profile the models were tuned against. The models run
unconditionally.

### Risk 2 — Model Aging

Even for the same athlete, physiological models age. An athlete who improves VO₂max by
5 ml/kg/min over 18 months of training operates at different metabolic thresholds than
when the model's baselines were established. The system's critical speed estimate,
glycogen depletion curve, and lactate threshold will lag behind the athlete's true
physiology — sometimes by months.

**Current state:** T5-05 documents this risk and defers recalibration to Phase 9. However
no trigger mechanism or detection heuristic is specified. There is no way for the system
to know that it is operating on a stale model.

### Risk 3 — Athlete Adaptation Outpacing the Model

Rapid physiological improvement (common in the first 6–12 months of structured training)
can make governance thresholds systematically conservative. If the athlete's HRV baseline
rises 10ms above the model's reference, the `HARD_STOP_HRV_DELTA` gate will fire on days
that are physiologically normal for the current athlete but anomalous relative to the
old baseline.

**Current state:** HRV baselines are computed from rolling windows. However the rolling
window anchor (initial calibration period) is never updated or flagged as potentially
stale relative to the athlete's evolved fitness.

### Risk 4 — Single-Athlete Overfitting (Architectural)

Implicit per-athlete assumptions baked into the codebase as defaults:

| Location | Assumption | Risk |
|---|---|---|
| `_create_synthetic_fallback()` | Athens, GR climate (T1-09 partially addressed) | Wrong environmental inputs for other athletes |
| `thresholds.py` constants | Tuned for one athlete's HRV range (~45–65ms baseline) | Wrong gate sensitivity for different physiology |
| `OutcomeTracker` calibration | Single athlete's decisions populate the calibration dataset | Calibration for athlete A corrupts governance for athlete B |
| `evidence_registry.py` | Evidence quality labels reflect single-athlete validation | Misleadingly high evidence quality for untested athlete profiles |

---

## Decision

**Establish a three-layer protocol for model aging detection, recalibration triggering,
and multi-athlete isolation — to be implemented in Phase 9, with Phase 8 prerequisite
guard rails installed in Phase 7.9.**

### Layer 1 — Model Age Tracking (Phase 7.9 prerequisite)

Add a `model_calibration_metadata` table to SQLite:

```sql
CREATE TABLE model_calibration_metadata (
    model_name      TEXT PRIMARY KEY,
    calibrated_at   TEXT NOT NULL,   -- ISO-8601 timestamp
    calibrated_for  TEXT NOT NULL,   -- athlete_id (future) or 'default'
    baseline_hrv_ms REAL,            -- HRV baseline at calibration time
    baseline_vo2    REAL,            -- VO₂max estimate at calibration time
    schema_version  INTEGER NOT NULL
);
```

At DailyCoach startup, check model age:

```python
MODEL_CALIBRATION_MAX_AGE_DAYS = 180   # 6 months — stored in thresholds.py
```

If any model's `calibrated_at` is older than `MODEL_CALIBRATION_MAX_AGE_DAYS`,
emit a structured event `model_calibration_stale` (WARNING severity, per ADR-0031)
and include a coaching-context flag `models_may_be_stale = True`. Do NOT block the
morning routine — this is a WARNING, not a HARD_STOP.

### Layer 2 — Adaptation Drift Detection (Phase 7.9 prerequisite)

At weekly plan generation time (`WeeklyPlanGenerator`), compare:

```
current_30d_hrv_mean  vs  calibrated_baseline_hrv_ms
```

If `|current_30d_hrv_mean - calibrated_baseline_hrv_ms| > HRV_DRIFT_THRESHOLD_MS`:
- Emit `hrv_baseline_drift_detected` structured event.
- Include drift magnitude and direction in the weekly plan coaching context.
- Flag in the Operator Console readiness dashboard.

```python
HRV_DRIFT_THRESHOLD_MS = 8.0   # stored in thresholds.py; matches HARD_STOP_HRV_DELTA scale
```

**Rationale:** If the athlete's 30-day HRV mean has shifted more than one HARD_STOP
delta from the calibration baseline, the model's reference frame is materially stale.

### Layer 3 — Multi-Athlete Isolation Architecture (Phase 9)

When Phase 9 introduces support for more than one athlete profile:

1. **Athlete ID as a first-class key** — every governance decision, every DB row,
   every model calibration record must carry an `athlete_id` foreign key.
2. **Per-athlete threshold overrides** — `thresholds.py` constants become defaults;
   per-athlete overrides stored in a `athlete_thresholds` table.
3. **Calibration isolation** — `OutcomeTracker` decision→outcome pairs are keyed by
   `athlete_id`. Calibration for athlete A cannot affect governance for athlete B.
4. **Cold-start protocol for new athletes** — new athletes get a 30-day supervised
   onboarding period with conservative defaults (all thresholds shifted 20% toward
   the safe direction) until sufficient outcome data exists for calibration.

### What This Does NOT Change

- Current single-athlete operation is unaffected.
- Phase 8 multi-sport scope (ADR-0016) proceeds without multi-athlete support — sport
  type and athlete identity are orthogonal axes. Phase 8 remains single-athlete,
  multi-sport.
- T5-05 (recalibration mechanism) is not superseded — this ADR adds trigger detection;
  T5-05 specifies the recalibration algorithm itself. Both remain open for Phase 9.

---

## Debt Items Created

- **T5-07** — No model age tracking or adaptation drift detection — physiological model
  staleness is invisible at runtime (Tier 5; Phase 7.9 guard rails as Phase 8 prerequisite;
  full Layer 3 deferred Phase 9)

---

## Alternatives Considered

**Alternative A — Continuous recalibration via OutcomeTracker feedback**
Rejected for Phase 7.9. Continuous recalibration creates the exact feedback loop risk
described in ADR-0035. Recalibration must be a deliberate, gated event — not automatic.

**Alternative B — Treat model aging as a monitoring concern only**
Rejected. A governance system that evaluates HRV gates against a baseline that is 18
months stale will produce systematically wrong hard-stop decisions. This is a data
integrity issue in the governance pipeline, not merely a monitoring gap.

**Alternative C — Replace all heuristic constants with athlete-adaptive running
averages**
Rejected for current phase. Fully adaptive constants eliminate the safety margin that
fixed thresholds provide. A miscalibrated rolling window could cause the system to
"adapt" to an overtraining pattern and fail to fire safety gates. Fixed thresholds with
drift detection is the safer architecture.

---

## Consequences

- Positive: Model staleness becomes visible at runtime through structured events and
  Operator Console flags. Athletes and operators are informed when recalibration is due.
- Positive: Phase 9 multi-athlete isolation has a clear architectural contract to
  implement against.
- Positive: HRV baseline drift is detected weekly — early warning before governance
  gates become systematically miscalibrated.
- Negative (acceptable): Requires a new `model_calibration_metadata` table (schema
  migration). Lightweight — single row per model, no high-frequency writes.
- Constraint: T5-07 Layer 1 and 2 (Phase 7.9 guard rails) are Phase 8 prerequisites
  per ADR-0022 spirit (no Phase 8 work without active model staleness monitoring).

---

## Review Trigger

This ADR should be reviewed when:
- Layer 3 (multi-athlete isolation) is scheduled for implementation in Phase 9.
- The HRV baseline drift detector fires more than twice in a 30-day window, suggesting the recalibration cadence needs adjustment.
- A new physiological model is introduced that has a staleness profile different from the models described here (e.g., a model that requires daily recalibration rather than weekly).
- The `model_calibration_metadata` schema requires a breaking change.

---

## Amendment — Layer 3: Multi-Athlete Calibration Isolation

**Amendment date:** 2026-04-12
**Status:** Accepted
**Author:** Architect (Claude)
**Supplements:** ADR-0046 (multi-athlete execution model), ADR-0052 (ThresholdAdapter)
**Closes:** T5-07 Layer 3 (deferred Phase 9 since 2026-03-13)
**Activates:** INV-04 (reserved slot assigned — see AGENTS.md §8.3)

---

### Amendment Context

Layer 3 was deferred at the original ADR-0033 authoring date (2026-03-06) with four
intent statements but no implementation contracts. Two subsequent architectural decisions
have since been accepted that constrain Layer 3's design space:

- **ADR-0046** (2026-03-08) — established the stateless `coaching_pipeline(ctx)` execution
  model, `AthleteCoachingContext`, and `CoachingScheduler`. Multi-athlete execution is now
  architecturally sequenced through `CoachingScheduler → coaching_pipeline()` per athlete.
  Layer 3 must build isolation within that execution contract, not around it.

- **ADR-0052** (2026-04-04) — accepted `ThresholdAdapter` as the canonical mechanism for
  per-athlete threshold variation, with `athlete_threshold_offsets` as the DB table name.
  The original Layer 3 sketch used the name `athlete_thresholds`; this amendment supersedes
  that name. Additive offset (δT) replaces full per-athlete threshold storage.

Additionally, three Phase 9 structural prerequisites are now confirmed RESOLVED:
T5-75 (AST structural invariant), T5-76 (concurrent pipeline isolation), T5-77
(SIGTERM mid-pipeline integrity). These satisfied the ADR-0046 entry gate.

INV-04 was reserved in AGENTS.md §8.3 pending this Layer 3 specification. It is
assigned below and in AGENTS.md.

---

### Layer 3 Decision

**Establish the implementation contract for multi-athlete calibration isolation across
four sub-domains: database key enforcement, OutcomeTracker scoping, cold-start
protocol, and adapter contract resolution.**

---

#### Sub-decision L3-A — Athlete ID as First-Class Database Key

Every table that stores governance-relevant state must carry `athlete_id` as a non-null
foreign key referencing an `athletes` canonical table. This closes the ADR-0040
single-athlete shortcut at the persistence layer.

**`athletes` canonical table (new — SCHEMA_VERSION bump required at implementation time):**

```sql
CREATE TABLE athletes (
    athlete_id                TEXT PRIMARY KEY,
    display_name              TEXT NOT NULL,
    created_at                TEXT NOT NULL,   -- ISO-8601 UTC
    is_cold_start             INTEGER NOT NULL DEFAULT 1,  -- 1 = active cold-start
    cold_start_ends_at        TEXT,            -- ISO-8601 UTC; NULL until exit conditions met
    cold_start_sessions_count INTEGER NOT NULL DEFAULT 0
);
```

**Tables requiring `athlete_id` column addition:**

| Table | Migration action | Notes |
|---|---|---|
| `governance_outcomes` | ALTER TABLE ADD COLUMN `athlete_id` NOT NULL | Backfill existing rows with the owner athlete_id constant defined at migration time |
| `model_calibration_metadata` | RENAME COLUMN `calibrated_for` TO `athlete_id` | Semantic clarification only; existing data valid after rename |
| `athlete_threshold_offsets` | No change required | athlete_id is already part of the PK per ADR-0052 |

**Enforcement rule (extends AGENTS.md §16.10):**

Any function that reads or writes governance state must accept `athlete_id: str` as an
explicit parameter. No implicit routing via session state, module-level globals, or
default constructor values is permitted. Violation is subject to G-CI-07 (athlete
isolation invariant) rejection.

The ADR-0040 `ADR-0040-SINGLE-ATHLETE-SHORTCUT` annotation exemption register is
retired for all modules modified in Phase 9. New and modified code is subject to the
full athlete isolation contract above. Existing annotated methods in
`titan/core/persistence.py` retain their exemption annotation until updated in T5-07-L3-D.

---

#### Sub-decision L3-B — OutcomeTracker Calibration Isolation

All `OutcomeTracker` reads (the feedback loop calibration path, T1-22) must be scoped
to a single `athlete_id` at every query boundary.

**Binding constraints:**

1. **No cross-athlete reads.** Any `SELECT` on `governance_outcomes` without a
   `WHERE athlete_id = ?` predicate is a prohibited pattern, treated as equivalent to an
   `INSERT OR REPLACE` violation under INV-09. This is enforced by a G-CI-07 extension.

2. **Per-athlete independence window.** The independence window from T1-22 (minimum gap
   between a coaching decision and its paired outcome record) operates per-athlete.
   Outcome records from athlete B must not influence the independence window clock
   for athlete A.

3. **Calibration diversity gate (per-athlete extension of AGENTS.md §16.7).** Before any
   Phase 9 calibration run, the dataset for that specific athlete must satisfy:
   - ≥ 30 paired `decision → outcome` records for that athlete_id
   - ≥ 3 distinct decision types represented
   - No single decision type comprising > 60% of the dataset

   Cross-athlete pooling to satisfy this gate is explicitly forbidden.

4. **CI gate extension.** G-CI-07 must be extended to include an AST check confirming
   that all `OutcomeTracker` query methods pass an `athlete_id` argument. Methods that
   omit `athlete_id` fail the gate.

---

#### Sub-decision L3-C — Cold-Start Protocol

New athletes enter a supervised cold-start period before ThresholdAdapter offsets
are permitted to adapt. This protects against premature calibration on thin data.

**Cold-start definition:**

- Duration: 30 **training days** — calendar days with at least one recorded coaching
  session. Tracked via `athletes.cold_start_sessions_count`. Not raw calendar days.
- Exit condition (both must be satisfied simultaneously):
  1. `cold_start_sessions_count ≥ 30`
  2. `OutcomeTracker` contains ≥ 30 paired `decision → outcome` records for this athlete_id

**Cold-start threshold behaviour:**

During cold-start, `ThresholdAdapter` is initialised with conservative static offsets
rather than learned δT values. The following constants must be added to `thresholds.py`
at implementation time:

```python
# ADR-0033 Layer 3 — cold-start conservative bias
COLD_START_SOFT_GATE_CONSERVATIVE_FACTOR = 0.80   # 20% shift toward conservative end
COLD_START_HARD_STOP_FACTOR = 1.00                # Hard-stop gates (H1–H5) unchanged
```

The circuit breaker defined in ADR-0052 (`FALSE_NEG > 20%` over 30 days → adaptation
pause) is **disabled** during cold-start. δT must not adapt — it stays at the
conservative initial value until cold-start exit.

**Cold-start exit protocol:**

1. `coaching_pipeline()` checks `athletes.is_cold_start` at entry (per-athlete, per-run).
2. When both exit conditions are satisfied: write `cold_start_ends_at = utcnow()`,
   set `is_cold_start = 0` within the same DB transaction.
3. ThresholdAdapter transitions from static conservative offsets to learned δT on the
   next coaching run after exit.
4. Emit structured event `athlete_cold_start_completed` (INFO severity, ADR-0031
   contract).
5. Flag in Operator Console readiness dashboard.

**Default athlete (system owner, `athlete_id = 'owner'`):**

The original system owner bypasses cold-start. At the Phase 9 migration:
- `is_cold_start = 0`
- `cold_start_sessions_count = 30`
- `cold_start_ends_at` = migration timestamp

Rationale: the owner's calibration dataset predates Phase 9 and has been validated
through Layers 1 and 2. Cold-start is designed for genuinely new athletes only.

---

#### Sub-decision L3-D — Adapter Contract Resolution

DEC-021 (OBS-021, 2026-03-17) deferred adapter read method isolation to Phase 9
under the ADR-0040 exemption. This sub-decision closes that deferral.

The `coach: Any` field in `AthleteCoachingContext` (identified in T5-16-B task
learning note) must be replaced by an explicit Protocol or TypedDict callable contract
before any multi-athlete coaching endpoint is built. This is a Phase 9 blocking gate.
Coaching pipeline callers must receive only the typed interface, never the full
`DailyCoach` instance.

For adapter read methods carrying the `ADR-0040-SINGLE-ATHLETE-SHORTCUT` annotation in
`titan/core/persistence.py`: each method must be updated to accept `athlete_id: str`
as a required parameter in Phase 9. The exemption annotation is retired for that method
upon update. Methods without `athlete_id` become non-compliant under AGENTS.md §16.10.

---

### INV-04 Assignment

> **INV-04** — Per-athlete calibration isolation: all `OutcomeTracker` reads are scoped
> to a single `athlete_id`; no cross-athlete query reaches the calibration path.
>
> **Test reference:** `tests/test_athlete_calibration_isolation.py` (to be created as
> part of T5-07-L3-B). Until that file exists, INV-04 enforcement state is DEFERRED —
> the invariant is defined but has no automated gate.

---

### What This Amendment Does NOT Change

- ADR-0052 (`ThresholdAdapter`) is not modified. L3-C references ADR-0052's circuit
  breaker; it does not alter its definition.
- ADR-0046 execution model (`coaching_pipeline`, `CoachingScheduler`) is unchanged.
- Hard-stop gates H1–H5 remain excluded from per-athlete adaptation per ADR-0052.
- Single-athlete runtime operation is unaffected until the Phase 9 migration runs.
- T5-07 Layers 1–2 (model_calibration_metadata schema; HrvCalibrationDriftState /
  describe_calibration_drift()) are not modified by this amendment.

---

### Debt Items Created by This Amendment

See TECHNICAL_DEBT.md T5-07-L3-A through T5-07-L3-D.

---

## Addendum (2026-10-23, ADR-0070): what the code does

- `coaching_pipeline` puts `cold_start_conservative_factor` (0.80 during cold start) in the context,
  but no gate reads it. The soft gates are not shifted during cold start (P4-11).
- Outside cold start, the `ThresholdAdapter` is loaded and handed to a `GovernanceEngine` that is
  then discarded (`titan/orchestration/coaching_pipeline.py`, "Stage 4 will wire this engine").
  The learned offsets reach no decision yet (T-PRA-18).
- The owner has no `athletes` cold-start row, so for the owner the cold-start state is unknown.
- Hard-stop gates H1–H5 stay excluded from adaptation, as this ADR says. They are also guarded in
  the database since schema v34 (ADR-0069 §4).
