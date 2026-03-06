# ADR-0043 — Post-Phase 9 Product Direction: Multi-Athlete Coach Platform and LLM Seams

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Strategic review session 2026-03-06 — post-Phase 9 direction alignment
**Phase:** Strategic — effective immediately across all future phases
**Supplements:** ADR-0015 (SQLite retention / Phase 8 gate), ADR-0022 (Phase 8 entry gate),
ADR-0033 (multi-athlete architecture), ADR-0038 (governance rationale protocol),
ADR-0040 (athlete identity invariant), ADR-0042 (human override invariant),
ADR-0044 (PostgreSQL migration — companion decision)

---

## Context

TITAN OS was designed, built, and calibrated as a single-athlete personal tool. As of
Phase 7 close (v5.8.0), the system has a mature governance layer, an evidence-backed
science stack, 1122+ tests, and a clear Phase 8–9 roadmap.

Before Phase 8 begins, two strategic questions must be answered explicitly:

**Q1 — Who is the user?**
A single athlete using it as a personal tool, or a coach managing 10–50 athletes?

**Q2 — What role does an LLM play?**
Real-time during-workout coaching, post-workout explanation assistant, or a coach-facing
query tool that operates asynchronously over aggregated athlete data?

Without explicit answers to both questions, Phase 8 design decisions (UI, DB topology,
notification model, interaction model) will be made with inconsistent assumptions —
exactly the failure mode that produced T4-01.

### Why these questions were deferred until now

These are product decisions, not engineering decisions. They require the architect to
have visibility into the full governance and science stack — which was not mature enough
to reason about until Phase 7 closed. The decision to defer them was correct.

### Input observations that informed this decision

**Observation 1 — Real-time push during training is hostile UX.**
Pushing phone notifications to an athlete mid-session (mid-run, mid-interval) is
disruptive and dangerous. The wrist (Garmin) is the right channel for during-workout
guidance. TITAN already syncs plans to Garmin Connect. No new architecture is required
for during-workout coaching — it is already provided by the device. A phone notification
that fires at kilometre 28 of a long run is not a coaching tool; it is an irritant.

**Observation 2 — LLM integration requires prompt-engineering skills that are not
assumed to be available in-house.**
LLM integration is not blocked by engineering capability — it can be implemented — but
it requires ongoing prompt maintenance, model version management, and latency budgeting.
These are new operational costs. The system must be designed so that LLM is an
**optional, additive layer** that can be introduced when resources allow, not a
structural dependency that blocks other work.

**Observation 3 — The most valuable LLM use case is coach-facing, not athlete-facing.**
An athlete asking "why was I stopped today?" is an edge case — the Telegram briefing
with governance rationale (ADR-0038, T2-16) answers this adequately without an LLM.
A coach managing 30 athletes asking "which athletes are at high risk this week?" is
a high-frequency, high-value use case that no deterministic query can answer as
fluently as a language model operating over structured context.

---

## Decision

### Decision 1 — The product target is a multi-athlete coach platform

TITAN OS is being built for a **coach-managed, multi-athlete deployment**, not a
single-athlete personal tool.

**What this means in practice:**

| Dimension | Implication |
|---|---|
| Primary user | Coach managing 10–50 athletes |
| Secondary user | Individual athlete (receives output, not configuration) |
| UI focus | Coach dashboard first; athlete-facing view is minimal |
| Data isolation | Each athlete is an isolated data domain (ADR-0040, ADR-0033 Layer 3) |
| DB topology | PostgreSQL, not SQLite (see ADR-0044) |
| Privacy model | GDPR/health data handling required from Phase 8A forward |
| Notification model | Athlete: Telegram morning briefing only; Watch: during-workout |

This decision does NOT retroactively change Phase 7 work. The single-athlete
architecture remains in production until Phase 8A migration.

### Decision 2 — The interaction model is asynchronous, not real-time

**The phone is for planning and post-workout analysis. The watch is for during workout.**

No architecture investment is made in real-time phone-based coaching interruptions.
ADR-0018 Phase B (Effect Runner extraction) is still required — but its primary
motivation is multi-athlete parallel execution, not real-time coaching.

### Decision 3 — LLM integration is Phase 10, optional, and coach-facing only

LLM is explicitly out of scope for Phases 8 and 9. It enters in **Phase 10**, after
Phase 9 closes with a sufficient multi-athlete outcome corpus.

**LLM role in Phase 10:**
- Coach query interface: "Which athletes are at risk this week?", "Why did Athlete A
  receive a hard stop three times in the last 14 days?"
- Input: structured JSON context from `get_athlete_context()` (Seam 2 below)
- Output: natural language summary and recommendations
- Boundary: LLM never participates in governance decisions. It queries results only.
- Kill-switch: same pattern as ML safety (ADR-0014, `ml_safety.py`)

**LLM does NOT:**
- Generate governance decisions
- Override threshold values
- Operate on raw physiological data
- Run during training sessions

### Decision 4 — Three LLM seams must be built during Phase 8, not Phase 10

These seams are cheap to build correctly now and prohibitively expensive to retrofit later.

**Seam 1 — Governance rationale as structured JSON (T2-16 / ADR-0038)**

Already specified by ADR-0038. Emphasized here as a Phase 10 enabler: the
`DecisionRationale` object (with `gate_findings`, `input_value`, `threshold`, `margin`,
`actionable_guidance`) must be persisted to the DB as a JSON column on the
`governance_outcomes` table — not only emitted as a structured log event.

When a Phase 10 LLM needs to explain "why was Athlete A stopped three times last week?",
it reads this column directly. Without DB persistence, the rationale is lost after the
log rotation window.

**Seam 2 — Unified `get_athlete_context()` query interface (T5-09)**

A single function that aggregates all context needed to produce a coaching summary:

```python
def get_athlete_context(
    athlete_id: str,
    days: int = 7,
    include_governance: bool = True,
    include_training: bool = True,
    include_biometrics: bool = True,
) -> dict:
    """
    Returns a structured dict suitable for rendering a coaching summary,
    populating a dashboard widget, or feeding to an LLM coach query.

    ADR-0043 Seam 2: This is the single read path for all athlete context.
    No caller should assemble athlete context from multiple raw DB queries.
    """
```

This function is Phase 8B work (coach dashboard needs it). The LLM uses it in Phase 10
by calling it and passing the result as context. The LLM integration is then a thin
wrapper — not a new data assembly layer.

**Seam 3 — LLM as an optional plug-in module, never a structural dependency**

The LLM integration module (Phase 10) must follow the same pattern as ML safety:

```python
# titan/integrations/llm_coach.py  (Phase 10)
LLM_COACH_ENABLED = os.environ.get("TITAN_LLM_COACH", "0") == "1"

def coach_query(prompt: str, athlete_context: dict) -> str:
    if not LLM_COACH_ENABLED:
        return _deterministic_fallback_summary(athlete_context)
    # Claude API call here
    ...
```

If `TITAN_LLM_COACH=0` (the default), all code paths fall back to deterministic
template-based summaries — identical in structure to ADR-0038 rationale templates.
The system is fully functional without the LLM.

---

## Phase Sequencing (updated)

The existing Phase 8 roadmap is resequenced into three sub-phases to reflect the
multi-athlete PostgreSQL prerequisite:

```
Phase 8A  (prerequisite)   PostgreSQL migration + athlete_id isolation (ADR-0044)
Phase 8B  (primary value)  Coach dashboard: readiness grid, risk alerts, session explorer
Phase 8C  (expansion)      Multi-device adapters: Strava, Polar, Whoop, COROS
Phase 9   (intelligence)   Autonomous calibration — now powered by multi-athlete corpus
Phase 10  (optional layer) LLM coach query interface (Claude API, env-gated)
```

Phase 9 becomes significantly more powerful when operating over multi-athlete outcome
data. The auto-calibration gate ("≥3 corroborating athlete profiles") is the minimum
threshold set in `FUTURE_UPGRADES.md` — with Phase 8 data, this becomes achievable
in the first months of Phase 9 rather than requiring years.

---

## ADR-0018 Phase B Consequence

ADR-0018 Phase B (Effect Runner extraction from DailyCoach) is now a **Phase 8A
prerequisite** alongside PostgreSQL migration. The reason:

For multi-athlete parallel execution, `DailyCoach` must become a stateless function
that accepts an athlete context and returns a decision — not a 12-step orchestrator
with global state. Without this extraction, running morning briefings for 50 athletes
concurrently requires 50 instantiations of a god-object, each holding conflicting
shared state.

**ADR-0022 Phase 8 entry gate is updated to include:**
- G9: ADR-0018 Phase B implemented (Effect Runner extracted as stateless decision function)
- G10: ADR-0044 Phase 8A storage topology ADR accepted and implementation plan documented

---

## What This Does NOT Change

- Phase 7 architecture is unchanged and remains in production.
- The Telegram bot remains the primary athlete notification channel through Phase 8.
- ADR-0022 entry gate (G1–G8) is unchanged; G9 and G10 are added.
- The ML kill-switch pattern (ADR-0014) applies to the LLM integration in Phase 10.
- ADR-0042 (human override invariant) applies to any LLM recommendation in Phase 10.
- ADR-0040 (athlete identity invariant) governs all new code from this commit forward.

---

## Debt Items Created

- **T5-08** — Storage topology decision for multi-athlete not yet locked — per-athlete
  SQLite files vs shared PostgreSQL undefined (Tier 5; decision made in ADR-0044;
  implementation is T5-08 execution item; Phase 8A)

- **T5-09** — No unified `get_athlete_context()` query interface — LLM Seam 2 not
  implemented; coach dashboard and Phase 10 LLM both depend on it (Tier 5; Phase 8B
  prerequisite; implement alongside coach dashboard)

- **T5-10** — Phase 10 LLM coach query layer not designed — Claude API integration,
  env-gated kill-switch, and deterministic fallback not yet specified in detail
  (Tier 5; deferred until Phase 9 closes with sufficient multi-athlete corpus;
  ADR-0043 Seam 3 provides the architectural contract)

---

## Alternatives Considered

**Alternative A — Real-time during-workout coaching via phone push notifications**
Rejected. Hostile to athlete experience mid-session. The Garmin watch already provides
this via plan sync. No additional architecture is needed or desirable.

**Alternative B — LLM as athlete-facing explanation assistant (Phase 8 or 9)**
Rejected. The primary athlete interaction channel (Telegram) already addresses the
"why was I stopped?" use case via ADR-0038 governance rationale. Adding an LLM to this
path introduces latency, cost, and non-determinism for a problem that template-based
rationale solves adequately. The LLM adds disproportionate value on the coach side where
natural language aggregation over many athletes is the dominant use case.

**Alternative C — Keep single-athlete scope and not invest in multi-athlete**
Rejected. The science stack — autonomous calibration in Phase 9, evidence promotion from
HEURISTIC to STRONG — requires a corpus of outcomes across multiple athlete profiles.
A single-athlete system plateaus at MODERATE evidence quality and can never reach STRONG.
The multi-athlete platform is the only path to a scientifically self-improving system.

**Alternative D — LLM in the governance critical path (replacing deterministic gates)**
Rejected categorically. Governance decisions must be deterministic, auditable, and
testable. LLM non-determinism in a safety-critical path is architecturally incompatible
with the governance invariants established in ADR-0009, ADR-0021, and ADR-0035.

---

## Consequences

- Positive: Every Phase 8 design decision now has an explicit target context (multi-athlete
  coach platform) rather than implicit single-athlete assumptions. ADR debates about "is
  this needed?" are resolved by checking against this target.
- Positive: The LLM door is kept open with minimal upfront investment (three seams).
  Phase 10 LLM integration is a thin wrapper over existing data structures, not a new
  subsystem.
- Positive: Phase 9 autonomous calibration becomes genuinely powerful when backed by a
  multi-athlete outcome corpus — not just an engineering exercise with 3 data points.
- Positive: The notification model is clarified permanently: phone = async planning and
  analysis; watch = during-workout. No future feature may violate this boundary without
  an explicit ADR override.
- Negative (acceptable): Phase 8A (PostgreSQL migration) adds ~4–6 weeks of work before
  the first user-visible feature (coach dashboard). This cost is paid once and permanently
  eliminates the SQLite concurrency ceiling.
- Constraint: ADR-0044 (PostgreSQL migration) must be accepted before any Phase 8 code
  is written. This ADR and ADR-0044 are co-dependent decisions.
