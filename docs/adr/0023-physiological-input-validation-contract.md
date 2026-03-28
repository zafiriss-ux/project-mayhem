# ADR-0023 — Physiological Input Validation Contract

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Master Risk Matrix — Risk #9 (Physiological Edge-Case Fragility)
**Phase:** 7.8 Hardening

---

## Context

Risk #9 is classified as **Low probability, Critical severity** because physiological
edge-cases rarely occur in normal operation but are precisely the conditions under
which an athlete is most vulnerable. A governance system that silently produces
incorrect output when inputs are pathological is more dangerous than one that fails
loudly.

### Current State

Science engines receive numerical inputs sourced from Garmin sync → SQLite → engine
hydration. No systematic validation exists at the pipeline boundary. Specific known
failure modes:

1. **HRV = 0 or near-zero** — can result from sensor error or missing nights. Passing
   `hrv_ms = 0` to `HRVEngine` produces a delta relative to baseline that will trivially
   exceed `HARD_STOP_HRV_DELTA` (15ms), triggering a hard stop. This is correct behaviour
   — but if `baseline_hrv = 0` (also missing), the delta is 0, silently *disabling* the
   gate. Current code has no guard.

2. **RHR spike to physiologically impossible values** — Garmin occasionally records
   resting HR of 200+ bpm due to optical sensor artefact. Passing this to `TSBEngine`
   or `ReadinessEngine` without clamping can produce catastrophically wrong readiness
   scores.

3. **ACWR = 0 or negative** — if CTL = 0 (athlete is new or data gap), dividing ATL/CTL
   produces infinity or NaN, which flows into `VolumeLoadGauge` silently.

4. **Glycogen debt = negative** — logically impossible; occurs from mismatched calorie
   accounting. A negative glycogen debt passed to the VO2 eligibility gate (gate G5)
   disables the fueling lock incorrectly.

5. **Temperature > 60°C or < -30°C** — weather API edge cases in extreme locations.
   Passed to `OptimalTimeCalculator` without bounds → may corrupt dew-point calculation.

### Evidence

`test_property_based.py` exists but covers high-level happy-path invariants, not
physiology-specific boundary values. No test currently passes `hrv_ms = 0` or
`rhr_bpm = 200` to the engine layer to verify graceful handling.

---

## Decision

**Introduce a `PhysiologicalBounds` validation layer at the database→science pipeline
boundary. Engines must reject or clamp impossible inputs rather than propagating them.**

### 1. Validation Layer Location

The validation boundary is the **database read path**, not the engine internals. Engines
should not need to validate their own inputs — that is an infrastructure concern.
Specifically:

- `DatabaseManager.get_daily_metrics()` must validate all physiological fields before
  returning them to callers.
- `DatabaseManager.get_training_load_history()` must validate CTL/ATL values before
  returning them.
- The validation logic lives in a new module: `titan/science/physiological_bounds.py`.

### 2. `PhysiologicalBounds` Module Contract

```python
# titan/science/physiological_bounds.py

BOUNDS = {
    "hrv_ms":           (0.1, 300.0),   # never zero; max physiologically recorded ~250ms
    "rhr_bpm":          (25, 120),       # extreme athlete low; artefact ceiling
    "ctl":              (0.0, 300.0),    # TSS/day; >200 = elite peak
    "atl":              (0.0, 500.0),    # acute load; higher ceiling for sprint athletes
    "acwr":             (0.0, 3.0),      # 0 if no chronic load; cap runaway values
    "glycogen_debt":    (0.0, 20.0),     # negative = impossible; >7 = lock threshold
    "temperature_c":    (-40.0, 55.0),   # operational climate range
    "dew_point_c":      (-40.0, 40.0),
}

@dataclass
class BoundsViolation:
    field: str
    value: float
    lo: float
    hi: float
    action: str   # "clamped" | "nulled" | "hard_reject"

def validate_and_clamp(
    data: dict[str, float | None],
    context: str,   # e.g. "daily_metrics", "training_load"
) -> tuple[dict[str, float | None], list[BoundsViolation]]:
    ...
```

### 3. Violation Policy

| Condition | Action | Rationale |
|---|---|---|
| Value outside bounds but within 2× the bound | Clamp to bound; emit `bounds_violation` structured log event | Sensor artefact — recoverable |
| Value outside bounds by more than 2× | Set field to `None`; emit `bounds_violation` + `data_quality_warning` | Likely corrupt reading — treat as missing |
| `hrv_ms` = 0 exactly | Set to `None` unconditionally | Zero HRV is sensor failure, not physiology |
| `ctl` = 0 or `atl` = 0 and ACWR requested | Return `acwr = None`; do not divide | Division-by-zero safety |

**"Hard reject" is not used in the clamp path.** The engine layer must always receive
a value it can operate on (even if `None` = missing data). Governance gates already
handle missing data via the `data_confidence_low` advisory (ADR-0019, T2-10).

### 4. Engine Null Handling Contract

Engines that receive `None` for a required input must:
1. Return a result with `confidence = "low"` and `advisory_only = True`.
2. Not raise `TypeError` or `AttributeError` from a null dereference.

This is an existing expectation (T2-10, data confidence gate). ADR-0023 adds the
upstream validation that ensures engines receive `None` rather than `0` or `NaN`.

### 5. Engineering Execution Item

**T1-18** (new Tier 1 item — added to `TECHNICAL_DEBT.md`):

> Create `titan/science/physiological_bounds.py`, integrate into
> `DatabaseManager.get_daily_metrics()` and `get_training_load_history()`,
> add `tests/test_physiological_bounds.py` (happy-path + boundary + each violation
> policy case).

---

## Options Considered

### Option A — Validate inside each engine
Each engine validates its own inputs at the top of its `calculate()` method.

**Rejected.** 26 modules × repeated validation logic = maintenance nightmare and
inconsistent bounds across engines. Centralised validation at the pipeline boundary
is architecturally cleaner.

### Option B — Validate in Garmin sync before DB write
Clamp/reject bad values before they enter the database.

**Partially accepted.** This is the *ideal* long-term approach (defence in depth).
However, it requires changes to `garmin_sync.py` (Tier 1–3 scope) and does not protect
against historical data already in the database. The DB read path is the
**minimum required** boundary. Garmin sync validation can be added in Phase 8 as a
second layer (defence in depth), but is not a substitute.

### Option C — Read-path validation only (SELECTED)
Single validation layer at `DatabaseManager` read methods. Centralised, testable,
retroactively protects historical data. Chosen for Phase 7.8.

---

## Consequences

**Positive:**
- Governance gates cannot be silently disabled by sensor artefacts.
- `NaN`/`Inf` values eliminated from the decision pipeline.
- Violations are logged with structured events → visible in operator console.

**Neutral:**
- A small number of legitimate edge-case sessions (e.g., first athlete day with
  CTL = 0) will produce `confidence = "low"` results. This is correct behaviour.

**Negative:**
- Bound constants in `physiological_bounds.py` are heuristic (MODERATE evidence).
  They must be added to `evidence_registry.py` with appropriate labels.
- New failure mode: a clamped value that is physiologically valid but outside our
  bounds triggers a spurious `data_quality_warning`. Bounds must be conservative.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0009 | Safety gate hardening — validation layer prevents gates from being silently disabled by bad inputs. Complementary. |
| ADR-0019 | `data_confidence_low` advisory (T2-10) — validation layer is the upstream producer of `confidence = "low"` signals. |
| ADR-0021 | Governance mutation tests — should include at least one test per gate where the relevant input is `None` (validation-caused). |

---

## Status

Accepted. Engineering execution: **T1-18** (Tier 1 — data integrity; execute before
any Tier 2 items in Phase 7.9+).

---

## Implementation Notes

**T5-63 (2026-03-28):** Extended the validation contract to `_check_vo2_eligibility_gate`
in `GovernanceEngine`. Prior to this fix, `acwr=None` and `readiness_score=None` both
defaulted to safe-range values (1.0 and 100 respectively), causing VO2 eligibility gates
V1 and V2 to pass silently on missing Garmin data. The fix applies the conservative-fail
principle (ADR-0051): absent/None inputs produce gate-failure outcomes. PR #556 merged
2026-03-28.

**OBS-030 / T5-65 (pending):** `_classify_hrv_drop` carries the same pattern — `acwr=None`
falls through `float(None)` TypeError to `acwr = 1.0`. This is a remaining non-compliant
call site. Fix registered as T5-65; implement after ADR-0051 acceptance.
