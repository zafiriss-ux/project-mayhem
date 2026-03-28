# ADR-0051 — Missing Data Policy: Conservative-Fail Principle for Safety-Critical Inputs

**Date:** 2026-03-28
**Status:** Accepted
**Type:** Governance Policy
**Scope:** All safety-critical input fields in GovernanceEngine, DailyCoach, and downstream
  engines that gate session recommendations, hard-stop decisions, or autonomic assessments
**Related:** ADR-0009 (safety gate hardening), ADR-0023 (physiological input validation),
  ADR-0030 (external data source resilience), T5-63, T5-64, OBS-028, OBS-029, OBS-030,
  OBS-033

---

## Context

TITAN OS uses a governance pipeline that reads biometric inputs from a `context` dict assembled
from the Garmin sync layer. When Garmin data is unavailable (network error, API degradation,
no recent sync), some fields in `context` may be `None` or absent.

Prior to T5-63 and T5-64 (2026-03-28), several governance methods applied an **optimistic
defaulting** pattern: they used `context.get("field", safe_value)` to substitute a value that
would pass the gate. This pattern made the system indistinguishable between two states:

- **State A:** Athlete data is available and within the safe range.
- **State B:** No Garmin data is available at all.

In State B, optimistic defaults caused the system to produce the same session recommendation
as in State A, bypassing the safety intent of the gate. Specific examples discovered:

1. **OBS-028 (T5-63):** `_check_vo2_eligibility_gate` — `acwr=None` → 1.0 (sweet spot);
   `readiness_score=None` → 100 (high readiness). Both gates passed on missing data.

2. **OBS-029 (T5-64):** `daily_coach.py` APL call — `cs_tracker.confidence` absent → 1.0
   (high confidence). APL tightening path (`confidence < 0.50` → `cs_min_confidence = 0.85`)
   was unreachable for new athletes with no time trial history.

3. **OBS-030 (T5-65, pending):** `_classify_hrv_drop` — `acwr=None` → `float(None)` raises
   `TypeError` → catches to `acwr = 1.0`. HRV drop may be classified as `TRAINING_EXPLAINED`
   when ACWR is unavailable.

These three findings represent a systemic policy gap, not isolated implementation errors.
The per-module fix approach (T5-44–T5-62) addressed individual constants but provided no
canonical reference for how None/absent inputs should be handled at governance boundaries.

---

## Decision

### Policy: Conservative-Fail for Safety-Critical Inputs

**A safety-critical input field that is `None` or absent from the governance context MUST
produce a conservative outcome — the same outcome as if the field had a value that would
fail the gate or tighten the constraint.**

This principle has the following concrete implications:

1. **Gate eligibility / pass/fail:**
   If a field is used in a gate condition (`field >= threshold`, `field ≤ threshold`, or
   a range check), a `None`/absent value MUST fail the gate. The gate must not substitute
   a value that would pass.

   *Correct:* `if acwr_raw is None: acwr_invalid = True` → V1 gate fails.
   *Incorrect:* `acwr = float(1.0 if acwr_raw is None else acwr_raw)` → V1 gate passes.

2. **Confidence / lock thresholds:**
   If a field drives a lock or tightening condition (`confidence < threshold`), a `None`/absent
   value MUST be treated as the minimum safe value (0.0 for confidence scores), not the
   maximum (1.0). Lower confidence → tighter constraint.

   *Correct:* `getattr(cs_tracker, 'confidence', 0.0)` → APL tightening fires.
   *Incorrect:* `getattr(cs_tracker, 'confidence', 1.0)` → APL tightening bypassed.

3. **Classification / narrative labels:**
   If a field drives a classification label (e.g., HRV drop cause), a `None`/absent value
   MUST produce an unknown/indeterminate label, not a specific classification that implies
   a known data state.

   *Correct:* `if acwr is None: return HrvDropClassification.UNKNOWN_ACWR`
   *Incorrect:* `acwr = 1.0` (fallback to sweet spot) → returns `TRAINING_EXPLAINED`.

4. **Default constant naming:**
   When a safe conservative fallback constant is needed, it MUST be named explicitly
   (e.g., `ESI_DEW_POINT_FALLBACK_C`) and registered in `evidence_registry.py` with
   provenance (STRONG / MODERATE / HEURISTIC). Magic number literals are not permitted.

### Scope

This policy applies to all fields that gate:
- Hard-stop decisions (H1–H5 gates)
- VO2 eligibility checks
- CS confidence locks
- APL tightening thresholds
- 2-of-4 soft downgrade gate
- HRV drop classification (narrative output)
- ESI / thermal stress computation

Non-safety fields (e.g., display labels, optional enrichment fields) may use optimistic
defaults where the consequence of missing data is cosmetic only.

### Implementation Pattern

The canonical implementation for a safety-critical field read is:

```python
# Read from context — do not supply a default that would pass the gate
field_raw = context.get("field_name")      # returns None if absent

if field_raw is None:
    field = None
    field_invalid = True                   # conservative: treat as gate failure
else:
    try:
        field = float(field_raw)
    except (TypeError, ValueError):
        field = None
        field_invalid = True
```

Not:

```python
# ANTI-PATTERN: optimistic default
field_raw = context.get("field_name", safe_value)  # absent → safe_value (passes gate)
field = float(safe_value if field_raw is None else field_raw)  # None → safe_value
```

---

## Consequences

### Positive

- Garmin API failures and data-absent states are distinguishable from healthy-data states.
- Safety gates cannot be bypassed by data absence.
- The governance pipeline is consistent with ADR-0030 (external data source resilience) and
  ADR-0023 (physiological input validation).
- Future module authors have a canonical reference rather than making ad hoc defaulting choices.

### Negative

- Sessions may be downgraded or blocked when data is absent, even if the athlete is healthy.
  This is the intended behavior: safety must err conservative.
- Existing modules not yet updated to this policy (e.g., `_classify_hrv_drop`, T5-65) will
  behave inconsistently until fixed. The fix backlog is tracked in TECHNICAL_DEBT.md.

### Neutral

- Fields already using conservative defaults (sleep_score/readiness_score in 2-of-4 gate,
  fixed by T5-49) are consistent with this policy. No change required for those.
- The governance engine's internal `getattr(cs_tracker, 'confidence', 0.0)` (fixed by T5-52)
  is consistent with this policy.

---

## Compliance Inventory

| Module / Method | Field | Status | Task |
|---|---|---|---|
| `governance_engine._check_vo2_eligibility_gate` | `acwr` | ✅ COMPLIANT (T5-63) | — |
| `governance_engine._check_vo2_eligibility_gate` | `readiness_score` | ✅ COMPLIANT (T5-63) | — |
| `daily_coach` APL call | `cs_tracker.confidence` | ✅ COMPLIANT (T5-64) | — |
| `governance_engine._check_2of4_gate` | `sleep_score` | ✅ COMPLIANT (T5-49) | — |
| `governance_engine._check_2of4_gate` | `readiness_score` | ✅ COMPLIANT (T5-49) | — |
| `governance_engine._classify_hrv_drop` | `acwr` | ❌ NON-COMPLIANT | T5-65 |
| `daily_coach` ESI path | `dew_point` | ❌ NON-COMPLIANT (12.0 literal) | T5-68 |

---

## Implementation Notes

**T5-63 (2026-03-28):** Fixed `_check_vo2_eligibility_gate` — `acwr` and `readiness_score`
None/absent now produce conservative gate-fail outcomes. PR #556 merged.

**T5-64 (2026-03-28):** Fixed `daily_coach` APL `cs_confidence` feed — absent `cs_tracker`
confidence now defaults to 0.0, enabling APL tightening for uncalibrated trackers. PR #557
merged.
