# ADR-0038 — Governance Decision Rationale Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V8 — Risks: Explainability Gap (non-ML governance), Operator Trust Drift
**Phase:** 7.9 Hardening
**Supplements:** ADR-0011 (Session Explorer payload), ADR-0012 (Manual Override Workflow), ADR-0031 (structured log sustainability), ADR-0032 (ML explainability — ML-specific counterpart)

---

## Context

ADR-0032 established an explainability contract for ML advisory models. However, the
primary decision engine in TITAN OS is not ML — it is the deterministic
`GovernanceEngine` with its 7-gate pipeline. This engine also lacks an explicit
rationale output.

### The Explainability Gap (Non-ML)

When the governance engine produces a decision, the athlete and operator currently
receive one of:

- A session recommendation ("Easy run, 45 min, Zone 2")
- A hard stop ("Rest day required")
- A downgrade ("Moderate session only")

What they do NOT receive:

- Which specific gates fired and why
- What the input values were that triggered each gate
- Whether the decision was close to a boundary (barely fired vs. comfortably fired)
- What the athlete could do differently to change the outcome tomorrow

**Current state:**

The `GovernanceEngine` emits structured log events (T2-04, T2-10) but these events
are in the observability layer — they are not surfaced in the coaching message or
the Telegram briefing as human-readable rationale.

ADR-0011 (Session Explorer) includes governance gate results in the Operator Console
payload. However this is a back-office tool (web UI, not yet implemented beyond the
service layer). The athlete interacts via Telegram — and the Telegram message provides
no rationale.

### The Operator Trust Drift Risk

When operators (athletes acting as their own coaches) consistently receive governance
decisions without rationale:

1. Initially: they trust the system ("it knows best").
2. Over time: decisions that conflict with their felt sense of readiness ("I feel
   fine but it says rest") accumulate without explanation.
3. Result: they override governance without critical analysis, or they disable it
   entirely — not because the decisions are wrong but because they are opaque.

This pattern is well-documented in human-AI interaction research: **transparency
increases appropriate reliance**. Without rationale, operators cannot distinguish
"the system is correctly identifying a risk I cannot perceive" from "the system is
being overly conservative based on a metric I know is unreliable today."

**Override rate as a trust signal:**

The `governance_outcomes` table (ADR-0035) records override events. A rising override
rate without a corresponding rise in observed adverse outcomes is a signal that
governance is losing operator trust — not that the athlete is being reckless. The
system must monitor this and respond with increased transparency, not increased
restriction.

---

## Decision

**Every governance decision must include a human-readable `DecisionRationale` object.
This rationale must be surfaced in the Telegram coaching message, the Session Explorer
payload, and any structured log event associated with the decision.**

### The DecisionRationale Contract

```python
from dataclasses import dataclass, field

@dataclass
class GateFinding:
    gate_id: str          # e.g., "H2_HRV_DELTA", "VO2_ELIGIBILITY_GATE"
    fired: bool
    input_value: float    # The actual measured value
    threshold: float      # The threshold that was compared
    margin: float         # (threshold - input_value): negative means gate fired
    severity: str         # "HARD_STOP" | "SOFT_DOWNGRADE" | "INFO"

@dataclass
class DecisionRationale:
    decision_type: str                 # "HARD_STOP" | "DOWNGRADE" | "APPROVED" | "DEGRADED_MODE"
    primary_reason: str                # Human-readable 1-sentence summary
    gate_findings: list[GateFinding]   # All evaluated gates, fired or not
    actionable_guidance: str           # What the athlete can do to change tomorrow's outcome
    confidence: str                    # "HIGH" | "MODERATE" | "LOW" (data freshness quality)
    data_freshness_ok: bool            # Per ADR-0030
```

**Example output (Telegram message fragment):**

```
🛑 Hard stop today.

Why: Your HRV dropped 18ms below your 7-day baseline (threshold: 15ms). Your
resting heart rate also rose 9bpm above baseline (threshold: 8bpm). This pattern
suggests significant physiological stress.

Both signals exceeded threshold simultaneously (illness pattern — see ADR-0037).
Full rest is recommended.

Tomorrow: If HRV recovers to within 10ms of baseline, easy training may resume.
```

**Example output (APPROVED with context):**

```
✅ Easy run approved: 45 min, Zone 2.

Why: All 7 governance gates passed. HRV is 3ms below baseline (within threshold).
ACWR is 1.05 (safe zone: 0.80–1.30). TSB is –12 (floor: –50).

Note: Dew point is 22°C today — pace targets have been adjusted +15 sec/km (ESI HIGH).
```

### Template-Based Generation

Rationale generation must be **template-based** (deterministic), not LLM-generated,
for the same reasons as ADR-0032: testability, determinism, and no external dependency.

Each gate has a registered template in `governance_engine.py`:

```python
GATE_RATIONALE_TEMPLATES = {
    "H2_HRV_DELTA": (
        "HRV dropped {input_value:.0f}ms below baseline "
        "(threshold: {threshold:.0f}ms; margin: {margin:+.0f}ms)."
    ),
    "VO2_ELIGIBILITY_GATE": (
        "VO₂max session {'approved' if not fired else 'blocked'}: "
        "ACWR={input_value:.2f} (safe range: 0.80–1.30)."
    ),
    # ... one template per gate
}
```

### Override Frequency Monitoring

`OperatorConsoleService.get_readiness_dashboard()` must include:

```python
override_metrics: {
    "overrides_last_30d": int,
    "override_rate_pct": float,      # % of governance decisions overridden
    "override_rate_trend": str,      # "RISING" | "STABLE" | "FALLING"
    "trust_signal": str              # "HIGH_TRUST" | "MODERATE_TRUST" | "LOW_TRUST"
}
```

If `override_rate_pct > 25%` over any 30-day window, emit `operator_trust_drift_warning`
structured event (WARNING severity, per ADR-0031) and increase rationale verbosity
(include margin values for all gates, not just fired gates).

### Session Explorer Integration

The `DecisionRationale` object must be serialised into the Session Explorer payload
(ADR-0011) in full — all gate findings, margins, and actionable guidance.

### What This Does NOT Change

- `GovernanceEngine` gate logic is unchanged — this ADR adds a rationale output
  layer, not a new evaluation layer.
- Governance lock codes are unchanged.
- ADR-0032 ML explainability contract is unchanged (ML rationale and governance
  rationale are parallel but separate concerns).

---

## Debt Items Created

- **T2-16** — Governance decisions lack human-readable rationale — gate findings,
  input values, and actionable guidance are absent from Telegram coaching messages
  and Session Explorer; override rate monitoring absent (Tier 2, observability;
  after all Tier 1 items)

---

## Alternatives Considered

**Alternative A — Surface rationale only in the Operator Console (not Telegram)**
Rejected. The primary interaction channel for the athlete is Telegram. Rationale
confined to a web UI that does not yet exist (ADR-0013 technology path deferred)
provides no immediate value. The Telegram message is the canonical coaching output.

**Alternative B — Log all gate values to structured events only**
Rejected. Structured events are in the observability layer — they require log access
to read. The athlete has Telegram access. The rationale must flow through the primary
channel, not only the back-office channel.

**Alternative C — Generate rationale using an LLM**
Rejected. An LLM in the critical coaching path introduces non-determinism, latency,
cost, and a new external dependency. Template-based generation is deterministic,
testable, and has no external dependencies. This is consistent with ADR-0032's
decision for ML rationale.

---

## Consequences

- Positive: Athletes receive transparent, actionable governance decisions. The
  difference between "your HRV barely fired the gate" and "your HRV is 20ms over
  the threshold" is communicated — allowing informed override decisions.
- Positive: Override rate monitoring provides an early signal of governance trust
  erosion, allowing the architect to investigate whether governance calibration needs
  adjustment.
- Positive: Operators who understand why a decision was made are more likely to
  follow appropriate governance and override inappropriate governance — increasing
  both safety and operator agency.
- Negative (acceptable): Template-based rationale requires one template per gate
  (currently 7 gates + 3 soft locks = ~10 templates). Maintenance overhead is low
  since templates change only when gate semantics change (already gated by ADR-0021).
- Constraint: T2-16 is Tier 2. Per Rule E1, it may only begin after all Tier 1 items
  (T1-18, T1-19, T1-20, T1-21, T1-22) are resolved.
