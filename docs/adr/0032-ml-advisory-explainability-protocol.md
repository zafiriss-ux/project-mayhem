# ADR-0032 — ML Advisory Explainability Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V7 — Risk: ML Physiological Safety & Ethical Opacity
**Phase:** 7.9 Hardening (gate for Phase 8 ML promotion)
**Supplements:** ADR-0014 (Phase 7 ML scaffold — shadow/advisory mode + kill-switch), ADR-0021 (Governance Evolvability Protocol), T5-05 (athlete model recalibration — Phase 9)

---

## Context

ADR-0014 established a rigorous ML safety architecture for Phase 7:
- All ML models operate in **shadow mode** by default (output computed but not used in
  decisions).
- A `TITAN_ML_KILL_SWITCH` environment variable disables all ML inference instantly.
- Evidence labels (STRONG / MODERATE / HEURISTIC) tag each model's output.
- Promotion from shadow to advisory requires an explicit architectural decision.

The three Phase 7 ML components are:

| Module | Type | Current mode |
|---|---|---|
| `LoadPredictionShadowModel` | LSTM next-session load predictor | Shadow only |
| `InjuryRiskEnsembleModel` | Ensemble injury probability scorer | Advisory (label: recall > 80% target) |
| `AutomatedPeriodizationEngine` | Genetic-algorithm periodization suggester | Suggest-only |

### The Explainability Gap

ADR-0014 correctly prevents ML models from taking autonomous action. However, it does
not specify what information must accompany an ML recommendation when it operates in
advisory or suggest-only mode.

**Current state for `InjuryRiskEnsembleModel` (advisory):**
The model returns a probability score (0.0–1.0). No feature attribution is returned.
The governing engine receives: `{"injury_risk_score": 0.73}`. It does not know whether
the score is driven by:
- Recent ACWR spike (recoverable; rest one day)
- Chronic TSB depression (systemic; reduce load for a week)
- Biomechanics anomaly (structural; physio referral)
- Historical injury proximity (temporal; monitor)

These four scenarios warrant completely different coaching responses. A governance system
that receives only `0.73` and applies a single response policy is operating on an
opaque input.

**The physiological safety risk:**
When a model recommends a high training load (LSTM predicts: "athlete can handle 95km
this week"), the coach may follow the recommendation if it is presented as confident —
even if the model's confidence derives from a data period when the athlete was at peak
fitness, not from the current physiological context. Without an explanation, the human
in the loop (the athlete + architect) cannot evaluate whether the confidence is
warranted.

**ADR-0021 addresses the governance engine's lock mechanism** (machine-verifiable
mutation tests). It does not address the *content* of ML recommendations.

**T5-05 addresses model recalibration** (when the athlete's physiology drifts from
the model's training distribution). It does not address what must be communicated
*before* recalibration is needed.

### Why This Is Phase 7.9 (Not Deferred to Phase 9)

`InjuryRiskEnsembleModel` is currently operating in advisory mode. It is actively
influencing coaching context today (its output is not blocked by the kill-switch in
normal operation). The explainability gap is therefore active, not hypothetical.

The LSTM and genetic algorithm are shadow-mode only — their explainability requirement
is a *gate* for future promotion. Defining the gate now prevents the promotion from
happening without the required infrastructure.

---

## Decision

**No ML model may operate in advisory mode, and no ML model may be promoted from shadow
to advisory mode, without satisfying the Explainability Contract defined below.**

### The Explainability Contract

Every ML model operating in advisory or suggest-only mode must return an
`ExplainableOutput` object alongside its primary output:

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class FeatureContribution:
    feature_name: str       # e.g., "acwr_7d", "hrv_delta_ms", "days_since_last_vo2"
    contribution: float     # Signed contribution to output (+ increases risk/load, - decreases)
    current_value: Any      # Actual value used in this inference

@dataclass
class ExplainableOutput:
    model_name: str
    primary_output: Any                             # The actual prediction/score
    confidence_low: float                           # 5th percentile estimate
    confidence_high: float                          # 95th percentile estimate
    top_features: list[FeatureContribution]         # Top 3 contributing features, ranked
    plain_text_reason: str                          # Human-readable summary (≤ 2 sentences)
    evidence_label: str                             # STRONG / MODERATE / HEURISTIC (ADR-0014)
    data_freshness_ok: bool                         # True iff input data passes ADR-0030 staleness check
```

**`plain_text_reason` generation:**
Each model provides a template-based reason generator. Template-based (not LLM-based)
to ensure determinism and testability:

```python
# InjuryRiskEnsembleModel example
def _generate_reason(self, top_features, score) -> str:
    primary = top_features[0]
    if score >= 0.70:
        severity = "elevated"
    elif score >= 0.45:
        severity = "moderate"
    else:
        severity = "low"
    return (
        f"Injury risk is {severity} ({score:.0%}). "
        f"Primary driver: {primary.feature_name} = {primary.current_value} "
        f"(contribution: {primary.contribution:+.2f})."
    )
```

**Example output:**
```
Injury risk is elevated (73%). Primary driver: acwr_7d = 1.42 (contribution: +0.31).
```

### Governance Engine Integration

When the governance engine receives an `ExplainableOutput` from an advisory ML model:

1. If `data_freshness_ok = False`: discard the advisory output, emit
   `ml_advisory_discarded_stale_data` event, fall back to non-ML governance path.
2. Log `plain_text_reason` to the structured event payload for the coaching report.
3. Include top feature contributions in the Operator Console session explorer payload
   (ADR-0011).
4. Do NOT allow an opaque (non-`ExplainableOutput`) advisory recommendation to
   influence any governance gate.

### Promotion Gate for Shadow Models

Before any shadow model may be promoted to advisory:

**Binary gate (all items required):**

| # | Criterion | Verification |
|---|---|---|
| P1 | Model returns `ExplainableOutput` with all required fields | Unit test: `test_explainable_output_contract.py` |
| P2 | `plain_text_reason` non-empty for 100% of test cases | `pytest tests/test_ml_explainability.py` → green |
| P3 | `top_features` length ≥ 1 for all non-trivial inputs | Assertion in `ExplainableOutput.__post_init__` |
| P4 | `data_freshness_ok` correctly set using ADR-0030 staleness check | Integration test with stale mock data |
| P5 | `confidence_low` < `primary_output` < `confidence_high` (for probability models) | Property-based test (T4-23) |
| P6 | A new ADR documents the promotion decision and references this ADR | Architect review |

### `InjuryRiskEnsembleModel` Immediate Work (T5-06-A)

Since `InjuryRiskEnsembleModel` is currently advisory, it must be retroactively brought
into compliance with this contract. The minimum change:

1. Add feature contribution tracking to the ensemble aggregation step.
2. Return `ExplainableOutput` from `assess_injury_risk()`.
3. Update governance engine to log `plain_text_reason`.
4. Add `tests/test_ml_explainability.py` (minimum: happy path + stale data path).

This is classified as **T5-06-A** (sub-item of T5-06) and elevated to **Phase 8
prerequisite** — it must be resolved before Phase 8 work begins, per ADR-0022 G1
(all Tier 1–4 OPEN items closed). However, since the model is currently advisory-mode
and the risk is active, the architect may choose to accelerate T5-06-A to Phase 7.9.

**Architecture note:** The `InjuryRiskEnsembleModel` in Phase 7 is a scaffold —
actual ML training is not implemented; the model returns computed heuristic scores.
Feature contribution tracking is therefore straightforward (no SHAP/LIME required);
it requires only exposing which input features drove the heuristic aggregation.

---

## Debt Items Created

- **T5-06** — ML advisory models lack explainability contract; no feature attribution
  returned; plain-text reason absent (Tier 5, deferred Phase 8/9 for LSTM and
  genetic algorithm; T5-06-A for `InjuryRiskEnsembleModel` — **Phase 8 prerequisite**)

---

## Alternatives Considered

**Alternative A — Use SHAP / LIME for post-hoc explainability**
Rejected for current phase. SHAP requires the model to be a true ML model with
feature matrices. TITAN Phase 7 models are heuristic scaffolds. SHAP is the correct
tool for Phase 9 when real training pipelines are in place. The template-based
approach is appropriate for scaffold stage.

**Alternative B — Defer all explainability to Phase 9**
Rejected. `InjuryRiskEnsembleModel` is already advisory. Deferring means the
active advisory model operates without the contract today. The risk is active,
not hypothetical.

**Alternative C — Display raw feature weights to athlete**
Rejected. Raw feature weights (e.g., `acwr_7d` weight = 0.31) are meaningless to
a non-technical athlete. The `plain_text_reason` template converts this into
actionable language ("Primary driver: training load spike in the last 7 days").

---

## Consequences

- Positive: Every ML advisory recommendation is accompanied by a human-readable
  reason and top feature contributions. Athletes and operators can evaluate whether
  the recommendation is appropriate for their current context.
- Positive: Stale data is explicitly detected and the advisory output is discarded
  rather than silently wrong.
- Positive: Promotion of shadow models is gated — no model can become advisory
  without the explainability contract being satisfied.
- Negative (acceptable): Retroactively adding `ExplainableOutput` to
  `InjuryRiskEnsembleModel` requires touching the ensemble aggregation logic and
  the governance engine integration. Estimated effort: ~4h. No architecture change.
- Constraint: T5-06-A is a Phase 8 prerequisite (ADR-0022 G1). If it is not resolved
  before Phase 8 begins, it becomes a blocker.
