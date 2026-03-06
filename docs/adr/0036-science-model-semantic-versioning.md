# ADR-0036 — Science Model Semantic Versioning Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V8 — Risk: Semantic Versioning of Science Models (algorithm changes without breaking-change tracking)
**Phase:** 7.9 Hardening
**Supplements:** ADR-0021 (governance evolvability — mutation tests), ADR-0024 (documentation drift prevention), ADR-0028 (complexity budget)

---

## Context

TITAN OS has 26 science modules in `titan/science/`. Many of these modules contain
algorithms that have been revised across the v5.x development cycle. These revisions
are tracked in `CHANGES.md` as system version increments (v5.7.0, v5.7.1, etc.) but
the science modules themselves carry no independent versioning.

### The Problem

A science module version is distinct from the system version. Two types of changes
require different handling:

| Change type | Example | Current tracking | Risk |
|---|---|---|---|
| **Patch** — bug fix, no algorithm change | Fix off-by-one in rolling window | `CHANGES.md` entry | Low |
| **Minor** — new input accepted, backward-compatible | Add dew point input to `OptimalTimeCalculator` | `CHANGES.md` entry | Low |
| **Major (breaking)** — algorithm produces different output for same inputs | Change HRV delta calculation from absolute to percentage | `CHANGES.md` entry — **no distinction** | **HIGH** |

When a breaking algorithm change is introduced:

1. The `OutcomeTracker` calibration dataset contains historical decision→outcome pairs
   that were produced by the old algorithm.
2. The new algorithm may produce different governance decisions for the same inputs.
3. The calibration dataset is now heterogeneous — pairs from the old algorithm and pairs
   from the new algorithm are mixed without a discriminator field.
4. Phase 9 calibration trained on this mixed dataset will produce unreliable threshold
   estimates.

Additionally, the `model_calibration_metadata` introduced in ADR-0033 uses a
`schema_version` field. Without science model versioning, this field cannot distinguish
between "schema was migrated" and "algorithm was changed."

### The Boundary Condition Accumulation Risk

Over multiple iterations, governance modules accumulate special-case branches:
"if season is winter AND hrv_delta > X AND previous_session was VO₂ AND..." These
accumulate without being tracked as complexity increases. Without versioning, there is
no way to audit whether a boundary condition was introduced as a deliberate decision
or as an ad-hoc fix that was never reviewed.

---

## Decision

**Assign semantic version numbers to science modules and governance contracts.
Breaking algorithm changes must increment the MAJOR version and be recorded in
both the module file and the ADR register.**

### Module Version Tracking

Each science module gains a module-level constant:

```python
# titan/science/hrv_engine.py
MODULE_VERSION = "1.0.0"   # MAJOR.MINOR.PATCH
```

**Version increment rules:**

| Change | Increment | ADR required? |
|---|---|---|
| Bug fix, no output change | PATCH | No |
| New optional parameter, backward-compatible | MINOR | No (CHANGES.md entry sufficient) |
| Algorithm change that produces different output for same inputs | MAJOR | **YES** |
| Threshold constant change | MINOR if parameter, MAJOR if affects gate semantics | Depends |

A "breaking" algorithm change is defined as: **any change where the same inputs to a
public method produce a different output value**.

### Breaking Change ADR Requirement

Any MAJOR version increment in a science module must:

1. Create a new ADR documenting:
   - What changed and why
   - The exact function(s) affected
   - Whether existing `OutcomeTracker` data is still valid for Phase 9 calibration
   - If not valid: a data migration or reset plan
2. Update `model_calibration_metadata.schema_version` for the affected model.
3. Emit a `science_model_breaking_change` structured event at the next DailyCoach
   startup after the change is deployed.

### OutcomeTracker Algorithm Version Tagging

Every row in `governance_outcomes` must record the algorithm versions active at
decision time:

```sql
ALTER TABLE governance_outcomes ADD COLUMN algorithm_version_snapshot TEXT;
-- JSON: {"hrv_engine": "1.0.0", "governance_engine": "2.1.0", ...}
```

This allows Phase 9 calibration to filter outcome pairs by algorithm version and
avoid mixing heterogeneous algorithm generations.

### CI Enforcement (T4-30)

A CI check in `tests/test_science_model_versions.py` must:

1. Import all science modules and assert `MODULE_VERSION` exists and is a valid
   semver string.
2. Assert no MAJOR version change is committed without a corresponding ADR file
   (by checking `CHANGES.md` for the ADR reference — same pattern as T4-21/ADR-0024).

### Governance Module Special Case

The governance engine and governance contracts have particularly high breaking-change
risk. For these modules, MAJOR version increments require:

- A mutation test update (ADR-0021, T4-18) covering the changed gate.
- Evidence registry update (if the change affects a threshold with evidence labels).

---

## Debt Items Created

- **T4-30** — Science modules carry no independent version numbers — algorithm
  breaking changes are not distinguished from patch fixes in `CHANGES.md`; calibration
  data heterogeneity risk is undetected (Tier 4, independent)

---

## Alternatives Considered

**Alternative A — Use git blame / commit history as version tracking**
Rejected. Git history is not queryable at runtime. The `governance_outcomes` table
needs a version discriminator field that is populated without git access.

**Alternative B — Version the entire system rather than individual modules**
Rejected. The system version already exists (`v5.8.0`). The problem is that system
version does not distinguish which *specific algorithm* changed. Two different system
versions may have the same HRV algorithm while having different governance algorithm.

**Alternative C — Require ADR for all algorithm changes (not just MAJOR)**
Rejected. MINOR and PATCH changes are too frequent to warrant an ADR. The ADR overhead
is appropriate only for breaking changes. See ADR-0028 (complexity budget) and
ADR-0021 (governance evolvability) for the governance-specific case.

---

## Consequences

- Positive: Breaking algorithm changes are explicitly documented and traceable.
  Phase 9 calibration can filter `governance_outcomes` by algorithm version to
  avoid mixing heterogeneous data.
- Positive: `model_calibration_metadata.schema_version` (ADR-0033) gains a
  meaningful semantic anchor.
- Positive: CI enforces the MODULE_VERSION contract — no science module can be
  committed without a version number.
- Negative (acceptable): Retroactively adding `MODULE_VERSION` to 26 science modules
  requires a one-time pass (all start at "1.0.0"). Effort: ~30 minutes.
  This is T4-30 work.
- Negative (acceptable): The `algorithm_version_snapshot` column added to
  `governance_outcomes` requires a schema migration. Low complexity.
- Constraint: T4-30 (MODULE_VERSION constants) must be implemented before the
  `algorithm_version_snapshot` column in `governance_outcomes` can be populated
  meaningfully.
