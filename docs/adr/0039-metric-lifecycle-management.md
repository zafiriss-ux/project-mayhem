# ADR-0039 — Metric Lifecycle Management Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V8 — Risk: Metric Proliferation Debt (obsolete metrics with disproportionate weight due to inertia)
**Phase:** 7.9 Hardening
**Supplements:** ADR-0024 (documentation drift prevention), ADR-0028 (complexity budget), ADR-0031 (structured log sustainability)

---

## Context

TITAN OS computes and tracks numerous physiological metrics: HRV delta, CTL, ATL, TSB,
ACWR, TRIMP, glycogen debt, readiness score, AFI (Autonomic Fusion Index), Critical Speed,
drift index, efficiency index, durability score, and more.

Each metric was introduced with a specific purpose. Over time:

1. **Metrics accumulate without retirement gates** — once added, a metric persists
   indefinitely, even if its predictive value for governance decisions has not been
   validated.

2. **Metrics carry weight through inertia** — the first metrics added to the system
   (HRV, ACWR) have been integrated into governance gates, weekly planning, and Telegram
   briefings. Later metrics (AFI, Critical Speed confidence, biomechanics score) were
   added without revising the relative weighting of earlier metrics. Early metrics
   have disproportionate governance influence not because they are more predictive —
   but because they were first.

3. **Orphaned metrics** — some computed values are logged but not consumed by any
   governance gate or coaching decision. They consume CPU, DB write bandwidth, and
   developer attention in test fixtures without contributing to outcomes.

### Concrete Examples

| Metric | Current usage | Potential concern |
|---|---|---|
| `TRIMP` | Computed daily; used in weekly plan | Not in any governance gate; predictive overlap with CTL/ATL |
| `drift_index` | Computed in session analysis | Not surfaced in Telegram briefing; gate involvement unclear |
| `efficiency_index` | Computed per-session | Appears in Operator Console payload; not in governance gates |
| `biomechanics_score` | Computed by `BiomechanicsEngine` | Evidence label not confirmed in evidence registry |
| `durability_score` | Computed by `DurabilityEngine` | Usage path to governance unclear |

This is not a claim that these metrics are wrong — it is a recognition that their
governance role is undocumented and their continued computation has never been reviewed
relative to their contribution.

### The Proliferation Risk

Phase 8 (multi-sport) and Phase 9 (multi-athlete, ML calibration) will each introduce
new metrics. Without a lifecycle protocol:

- The total metric count will continue growing.
- Each new metric is added as a "new thing on top" without asking "does this replace
  or supersede something existing?"
- Governance complexity increases as more metrics potentially feed into more gate
  conditions.
- Test fixtures must maintain realistic values for all metrics, increasing fixture
  maintenance burden (T4-24 addresses fixture factory, but not metric proliferation).

---

## Decision

**Establish a metric lifecycle protocol with three states: Active, Under Review, and
Deprecated. Conduct an initial classification audit in Phase 7.9. Require lifecycle
state review at each phase boundary.**

### Metric Lifecycle States

| State | Meaning | Action |
|---|---|---|
| **Active** | Metric is consumed by at least one governance gate, coaching output, or Operator Console payload | Continue computing; maintain in evidence registry |
| **Under Review** | Metric is computed but its governance role is unclear or its predictive value is unvalidated | Flag in Telegram engineering report; architect review within one phase |
| **Deprecated** | Metric has been reviewed and found redundant, superseded, or without validated governance role | Remove from computation path; archive historical values; update evidence registry |

### Initial Classification Audit (T2-17)

The T2-17 implementation must:

1. Enumerate all metrics computed by science engines.
2. For each metric, determine:
   - Is it consumed by a governance gate (H1–H7, soft locks)?
   - Is it surfaced in the Telegram briefing?
   - Is it in the Operator Console payload?
   - Does it have an entry in `evidence_registry.py`?
3. Mark each metric as Active, Under Review, or Deprecated.
4. Output a `metrics_lifecycle_report` structured event at each DailyCoach startup
   listing any metrics in "Under Review" state.

### Phase Boundary Review Gate

At each phase boundary (Phase 7→8, Phase 8→9), the architect must:

1. Review all "Under Review" metrics — classify each as Active or Deprecated.
2. Propose at least one Deprecation per phase if the metric count exceeds 20.
3. Document the classification decision in a new ADR or phase boundary summary.

### Deprecation Protocol

A metric may only be deprecated if:

1. It has been in "Under Review" state for at least one full phase.
2. An architect review confirms no governance gate, coaching output, or Phase N+1
   plan depends on it.
3. Historical values in the database are preserved (no deletion) — only computation
   is removed.
4. The deprecation is documented in `CHANGES.md` and the evidence registry.

### Evidence Registry Requirement

No metric may remain in "Active" state without an entry in `evidence_registry.py`
specifying:
- Evidence quality (STRONG / MODERATE / HEURISTIC)
- Literature reference or rationale
- Governance role (which gates consume it)

This extends the existing evidence registry requirement to cover all computed metrics,
not just governance threshold constants.

### New Metric Gate

No new metric may be added to the computation path without:

1. An evidence registry entry at the time of introduction.
2. An explicit governance role: which gate, coaching output, or Operator Console
   payload will consume it?
3. A test asserting the metric is consumed (not just computed).

---

## Debt Items Created

- **T2-17** — Metric lifecycle states not tracked — obsolete metrics accumulate without
  retirement; orphaned metrics consume resources without governance contribution;
  new metrics lack mandatory evidence registry entries (Tier 2, observability,
  independent)

---

## Alternatives Considered

**Alternative A — Remove all metrics not in a governance gate immediately**
Rejected. Some metrics (TRIMP, drift index) may have value in Phase 8/9 contexts even
if they are not in current governance gates. Premature removal forfeits historical
data. The "Under Review" state provides a structured path to removal without data loss.

**Alternative B — Add all metrics to governance gates to justify their existence**
Rejected. Adding metrics to governance gates to avoid deprecation is scope creep that
increases governance complexity. The correct test is "does this metric provide
information not already provided by another metric in the same gate?" — not "can we
find some gate to put it in?"

**Alternative C — Defer to Phase 9 (after ML calibration reveals which metrics
are predictive)**
Partially accepted. The ML calibration in Phase 9 will provide empirical evidence of
metric predictive value. However, the lifecycle protocol must be in place *before*
Phase 9 so that the calibration can operate on a clean, well-documented metric set.
Starting the protocol in Phase 7.9 gives one full phase (Phase 8) for Under Review
metrics to be classified before Phase 9 calibration begins.

---

## Consequences

- Positive: The metric set becomes explicitly governed. Each metric has a documented
  role, evidence quality, and lifecycle state.
- Positive: Phase 8 and Phase 9 metric additions are gated — no metric can enter the
  computation path without a governance role and evidence entry.
- Positive: Orphaned metrics are identified and removed, reducing computation overhead
  and test fixture complexity.
- Negative (acceptable): The initial classification audit (T2-17) requires reading
  all science engine output paths — estimated effort 3–4 hours.
- Constraint: T2-17 is Tier 2. Per Rule E1, it may only begin after all Tier 1 items
  are resolved.
