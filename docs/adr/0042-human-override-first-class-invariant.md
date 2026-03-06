# ADR-0042 — Human Override as First-Class Architectural Invariant

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Architect Directive V8 — Decision 3: No ML/AI layer without human override capability on every decision
**Phase:** IMMEDIATE — effective from this commit forward, all phases
**Supplements:** ADR-0012 (Manual Override Workflow mechanics), ADR-0032 (ML explainability),
ADR-0035 (Feedback Loop Integrity — override signal as calibration data), ADR-0038
(Governance Decision Rationale)

---

## Context

ADR-0012 implemented a Manual Override Workflow for the Operator Console. This gave
operators a mechanical path to override governance decisions. It was a necessary step.

However, ADR-0012 describes *a feature* — not an *invariant*. A feature can be
incomplete, partially implemented, or applied selectively. An invariant cannot.

The question this ADR answers is different from ADR-0012:

> **Not**: "How does the operator override a specific decision in the Operator Console?"
> **But**: "Is it architecturally guaranteed that *every* TITAN OS recommendation —
> governance or ML — can be overridden by the athlete or coach, and that every override
> is treated as a first-class signal rather than an exception?"

These are different questions. The first is UX. The second is architecture.

### Why This Matters Now

Phase 7 introduced ML advisory models (`InjuryRiskEnsembleModel`,
`AutomatedPeriodizationEngine`, `LoadPredictionShadowModel`). Phase 8 will promote
them from shadow to advisory. Phase 9 will promote them to calibration-influencing.

At each promotion step, the consequence of a recommendation the athlete cannot override
grows. An ML model recommending a training plan modification that the athlete cannot
reject — or can reject but the rejection is not captured — is a system that trains
itself in the absence of human judgement. This is the exact failure mode ADR-0035
addresses from a data integrity perspective. This ADR addresses it from an
architectural invariant perspective.

### The Three Current Gaps

**Gap 1 — Not every decision type has a registered override handler.**
ADR-0012 covers the Operator Console workflow. The Telegram bot (primary athlete
interaction channel) has no override path — a hard-stop received via Telegram cannot
be overridden without going to the Operator Console (which is not yet deployed,
ADR-0013). In practice, the athlete ignores the Telegram message. This is an
*unrecorded* override — the worst kind.

**Gap 2 — Override recording is incomplete.**
ADR-0035 adds `decision_was_followed` to `governance_outcomes`. This is correct but
not yet implemented (T1-22 OPEN). More fundamentally: overrides from the Telegram
path (where no formal override button exists) are **never recorded at all** —
they are simply absences in the outcome data.

**Gap 3 — Override signals are not treated as learning.**
An override is currently a deviation — something the system tolerates but does not
value. The correct architecture treats an override as **valuable signal**: the athlete
or coach has domain knowledge that the model lacks. This signal must be captured,
analysed for patterns, and eventually used to calibrate the models (Phase 9). Ignoring
overrides means discarding the most valuable feedback the system will ever receive.

---

## Decision

**Declare human override capability a non-negotiable architectural invariant.
Every recommendation produced by TITAN OS — governance or ML — must be overridable.
Every override must be recorded as a structured signal. The system must treat override
patterns as first-class calibration data.**

### Invariant Statement

> No TITAN OS decision pipeline may produce a recommendation that the athlete or
> coach cannot override through at least one interaction path (Telegram or Operator
> Console). Every override must produce a structured `OverrideSignal` record in the
> `governance_outcomes` table. No recommendation type may be added to the system
> without a registered override handler.

### The OverrideSignal Contract

```python
# titan/science/override_signal.py  (new module — extends ADR-0012)
from dataclasses import dataclass

@dataclass
class OverrideSignal:
    decision_id: str         # References governance_outcomes row
    athlete_id: str          # ADR-0040 isolation
    override_source: str     # "telegram_bot" | "operator_console" | "api" | "manual_db"
    override_timestamp: str  # ISO-8601
    original_decision: str   # Decision type overridden (e.g., "HARD_STOP", "DOWNGRADE")
    override_reason: str     # Free text from operator (required — may not be empty)
    outcome_expectation: str # What the athlete expects: "I feel fine", "Will monitor", etc.
    # Populated at outcome recording time (ADR-0035 window):
    post_override_hrv: float | None = None
    post_override_rhr: float | None = None
    post_override_fatigue: int | None = None
    adverse_event: bool = False  # Did an injury or illness follow within 7 days?
```

**The `override_reason` field is NOT optional.** An override without a reason is not
recorded — the system prompts again. This is a deliberate friction mechanism: not
to discourage overrides, but to ensure they carry semantic content. "I feel fine"
is a valid reason. Empty is not.

### Override Paths (Telegram + Operator Console)

**Telegram path (primary — must be implemented in T4-32):**

When the morning briefing contains a hard-stop or downgrade, the Telegram message
must include an inline button:

```
🛑 Hard stop today. [Details above]

Do you want to override?
[✅ Accept governance] [⚠️ Override (requires reason)]
```

If the athlete taps "Override":
1. Bot prompts: "Brief reason? (e.g., 'I feel fine', 'Important race', 'Stress from work')"
2. Athlete replies.
3. Bot records `OverrideSignal` with `override_source = "telegram_bot"`.
4. Bot replies: "Override recorded. Your training plan proceeds as you decided.
   I'll check in after your session."
5. The governance engine emits `decision_overridden` structured event (WARNING severity).

If the athlete does NOT tap either button (ignores the message):
- After 4 hours: bot sends a follow-up: "Did you train today? [Yes, I overrode] [No, I rested]"
- This captures the *absence* of a response as a weak override signal.
- Record as `OverrideSignal` with `override_reason = "no_response_assumed_override"`.

**Operator Console path (existing — ADR-0012):**
No change. Already documented. The `OverrideSignal` record must be added alongside
the existing override workflow records.

### ML Decision Override Contract

Every ML advisory recommendation (ADR-0032 `ExplainableOutput`) must:

1. Be presented alongside an explicit "Accept / Override" prompt.
2. Accept the same `OverrideSignal` contract.
3. NOT influence calibration if overridden (ADR-0035 `decision_was_followed = 0`).

No ML model promoted from shadow to advisory may be merged without demonstrating
that its recommendations are overridable through at least one interaction path.
This is added to the Phase 8 entry gate criteria (ADR-0022).

### Override Pattern Analysis (Phase 8+)

`OperatorConsoleService` must provide an **Override Pattern Report**:

```python
override_analysis: {
    "total_overrides_90d": int,
    "by_decision_type": {"HARD_STOP": int, "DOWNGRADE": int, ...},
    "adverse_events_after_override_pct": float,  # % where adverse_event = True
    "override_reason_categories": dict,           # clustered by keyword
    "trust_signal": str                           # from ADR-0038
}
```

`adverse_events_after_override_pct` is the most important metric. If it exceeds 15%:
emit `override_adverse_correlation_alert` (CRITICAL severity). This means athletes
are overriding governance and getting hurt. The governance thresholds may be correct
and the override pattern is dangerous — or the thresholds may be too conservative
and athletes are right to override. Either way, immediate architect review is required.

If `adverse_events_after_override_pct` is below 3%: this is evidence the governance
is being overridden safely — threshold calibration review is warranted (T5-05).

### What This Does NOT Mean

- Overrides are not errors. They are expected and valuable.
- The system does not increase restrictions on athletes who override frequently.
  Override rate is monitored (ADR-0038) but not penalised.
- An athlete who overrides a governance hard-stop and trains safely is providing
  the most valuable calibration signal the system can receive.
- The system must never block an override. It records, warns, and monitors — but
  ultimately the athlete and coach decide.

### Rules for New Recommendations (HARD — no exceptions)

**Rule A42-1 — Every new decision type must have an override handler.**
Any new governance lock code or ML recommendation type must be registered in the
override handler registry before it can be merged. The CI check (T4-32) validates
this.

**Rule A42-2 — Override silence is recorded.**
Any recommendation the athlete does not respond to is treated as a probable override
(see Telegram path above). Silence cannot be treated as acceptance.

**Rule A42-3 — Override reason is mandatory.**
No override may be recorded with an empty reason. The UX must enforce this.

**Rule A42-4 — Override signals flow to calibration.**
Every `OverrideSignal` with a post-session outcome must flow to the `governance_outcomes`
table via ADR-0035 guardrails. No override signal may be discarded.

---

## Debt Items Created

- **T4-32** — No override handler registry — new governance decision types and ML
  recommendations can be added without a corresponding override path; no CI check
  enforces the invariant (Tier 4, independent; CI check + Telegram override button)

---

## Alternatives Considered

**Alternative A — Require explicit approval rather than an override**
Rejected. Requiring the athlete to explicitly approve every recommendation shifts the
interaction model from coaching to bureaucracy. The default must be that the system's
recommendation is followed unless the athlete actively overrides. This matches how
a real coaching relationship works.

**Alternative B — Allow some decisions to be non-overridable (absolute hard-stops)**
Rejected. There is no governance decision in TITAN OS that should be absolutely
non-overridable. Even a hard-stop for HRV crash or illness pattern (ADR-0037) can
be overridden by an athlete who knows the system is measuring an artefact or a
non-physiological stressor. The system's job is to inform and recommend — not to
lock the athlete out of their own training.

**Alternative C — Defer override contract to Phase 8 (when ML is promoted)**
Rejected. The Telegram path gap (Gap 1) exists today. Athletes are currently making
unrecorded overrides every time they ignore a hard-stop message. This unrecorded
override data is lost permanently — it cannot be retroactively captured. Every day
without the contract is permanently lost calibration data.

---

## Consequences

- Positive: The system learns from every human decision — not just the decisions
  that align with its recommendations. Override signals are the highest-value
  calibration data the system will ever have.
- Positive: Athletes and coaches can use governance as a tool rather than fighting
  against it. When the system is wrong, the athlete overrides and the system learns.
  When the system is right and the athlete overrides anyway, the adverse event
  correlation tracker catches it.
- Positive: `adverse_events_after_override_pct` provides an objective, data-driven
  answer to the question "is the governance too conservative?" — without requiring
  architectural intuition.
- Negative (acceptable): Implementing the Telegram override button requires
  `TitanTelegramBot` to handle inline keyboard callbacks and multi-step conversations.
  This is non-trivial but well within the existing pyTelegramBotAPI capabilities.
- Negative (acceptable): Mandatory override reasons add friction to the override
  path. This is intentional. The friction is calibrated to be low enough that
  legitimate overrides occur easily, but high enough that casual dismissal of a
  governance recommendation does not go unrecorded.
- Constraint: T4-32 (override handler registry CI check) is IMMEDIATE. The Telegram
  override button implementation is a dependency for T1-22 completing the full
  override capture pipeline.
