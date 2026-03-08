# ADR-0046 — DailyCoach Multi-Athlete Execution Model

**Date:** 2026-03-08
**Status:** Accepted
**Deciders:** Architect
**Source:** T5-16 — Phase 8B entry gate (architect review 2026-03-08)
**Phase:** Phase 8B entry gate — effective before any multi-athlete coaching execution path is built
**Related:** ADR-0017 (god-orchestrator audit), ADR-0018 (kernel boundary), ADR-0013 (FastAPI tech path), ADR-0033 (multi-athlete isolation protocol)

---

## Context

`DailyCoach` was designed as a single-athlete, daemon-thread orchestrator. Its constructor
accepts 10+ engine/integration dependencies; its 12-step `run_morning_routine()` sequences
Garmin sync, engine hydration, governance evaluation, DB persistence, and Telegram delivery
for one athlete.

ADR-0018 introduced a kernel boundary (Decision Pipeline → Effect Runner split). The Decision
Pipeline is now conceptually pure: it reads a state snapshot and produces a `DecisionResult`.
The Effect Runner serialises DB writes and Telegram delivery. ADR-0017 accepted the
god-orchestrator pattern as-is for single-athlete operation.

Phase 8B introduces a coach dashboard (ADR-0013 — React + FastAPI) through which a coach
manages N athletes. T5-11 (auth) and T5-13 (audit trail) gate individual API endpoints.
T5-08 (PostgreSQL migration) is a Phase 8A prerequisite before Phase 8B begins.

**The problem:** No decision exists for how `DailyCoach` orchestrates ≥2 athletes
simultaneously. Three candidate models are available:

1. **Separate instances** — one `DailyCoach` instance per athlete; simplest; memory and
   daemon-thread count scale O(N); engine lifecycle unchanged.
2. **Stateless coaching function** — `DailyCoach.run_morning_routine()` is replaced by a
   stateless `coaching_pipeline(athlete_context)` function; daemon thread retired for
   multi-athlete mode; per-athlete execution scheduled by a central job runner.
3. **FastAPI lifecycle-scoped** — `DailyCoach` instantiated per-request by FastAPI
   dependency injection; no persistent daemon thread in multi-athlete mode.

Without an explicit decision, T5-09 (`get_athlete_context()`), T5-11 (auth layer), and
the coach dashboard API will be built on undefined execution semantics, creating implicit
coupling that requires re-architecture when the model is finally chosen.

---

## Concurrency Analysis

### State that MUST be per-athlete (cannot be shared)

| Component | Reason |
|---|---|
| Engine instances (`AutonomicFusionEngine`, `FatigueEngine`, `CriticalSpeedTracker`, etc.) | Each engine holds athlete-specific baselines (CTL/ATL, HRV rolling window, critical speed estimate). Sharing between athletes produces governance decisions against the wrong physiology. |
| `GovernanceEngine` + `IntensityGovernor` context | Gate evaluation uses athlete-specific thresholds (per ADR-0033 Layer 3 — athlete-level threshold overrides are Phase 9, but even with global thresholds the *inputs* differ per athlete). |
| `AdaptivePriorityLock` state | Priority locks are keyed to one athlete's phase × load position. |
| `OutcomeTracker` | Decision→outcome pairs are per-athlete (ADR-0033 §Calibration isolation). Cross-athlete contamination corrupts calibration. |
| Telegram delivery target (`chat_id`) | Each athlete has their own Telegram channel. |
| Garmin credentials | Each athlete authenticates independently. |
| `DegradedModeTracker` | Tracks degradation history per athlete coaching session. |

### State that MAY be shared across athletes

| Component | Condition for sharing |
|---|---|
| `WeatherAPI` cache | Shared when ≥2 athletes share the same `WEATHER_LOCATION`. Different locations require independent cache entries. The cache is already keyed by location — no change needed. |
| PostgreSQL connection pool (T5-08) | Connection pooling (e.g., `asyncpg` pool) is inherently shared and handles concurrent athlete queries safely. |
| `MLSafety` kill-switch state | The `TITAN_ML_KILL_SWITCH` environment variable is process-global; all athletes share the same ML enable/disable state. |

### Daemon thread lifecycle in multi-athlete mode

The existing daemon thread (`DailyCoach._routine_thread`) implements a single-athlete
`cron`-style scheduler (07:00 briefing, 20:00 Sunday plan). In multi-athlete mode:

- **N daemon threads** (one per athlete) is untenable at scale: 50 athletes = 50 threads
  doing nothing but sleeping, with no supervision, overlap protection, or failure isolation.
- **A shared scheduled-task runner** (e.g., `APScheduler` or a simple `ThreadPoolExecutor`-
  backed job queue) is the correct replacement. The runner fires `coaching_pipeline(ctx)`
  for each athlete at their configured schedule time.

---

## Decision

**Chosen model: Model 2 — Stateless coaching function.**

### Rationale

1. **Consistency with ADR-0018.** The kernel boundary already separates pure decision
   computation from side-effects. Model 2 extends this boundary to the full coaching
   pipeline: `coaching_pipeline(athlete_context)` is a pure-ish function that reads DB
   state, runs all 12 pipeline steps, and returns a `DailyCoachingPayload`. Effects
   (DB writes, Telegram delivery) are passed as callable dependencies, matching the
   ADR-0018 Effect Runner contract.

2. **Testability.** Stateless functions accept dependency-injected callables; tests can
   provide mocks without constructing the full `DailyCoach` object graph.

3. **Daemon thread retirement path.** Model 1 (separate instances) multiplies daemon
   threads with athletes. Model 2 eliminates per-athlete daemon threads in favour of a
   single supervised scheduler, reducing thread count from O(N) to O(1).

4. **FastAPI alignment.** Model 3 (per-request FastAPI DI) would fire coaching execution
   on every HTTP request, conflating the *query* path (read dashboard data) with the
   *execution* path (run morning routine). These are distinct operations with different
   triggers. Model 2 keeps them separate: the scheduler triggers coaching execution;
   FastAPI serves only reads (via T5-09 `get_athlete_context()`).

5. **Migration path.** The current single-athlete CLI mode retains the daemon thread
   unchanged (backward-compatible). Model 2 is introduced as an additional execution
   path, not a replacement — the existing `DailyCoach.run_morning_routine()` continues
   to function until the multi-athlete scheduler replaces it in Phase 9.

### What changes (Phase 8B)

1. **New `coaching_pipeline(athlete_context, *, db, effect_runner)` function** — extracts
   the core 12-step logic from `DailyCoach.run_morning_routine()` into a top-level
   function in `titan/orchestration/coaching_pipeline.py`. Accepts a fully-hydrated
   `AthleteCoachingContext` dataclass and a set of injectable effect callbacks. Returns
   `DailyCoachingPayload`.

2. **`AthleteCoachingContext` dataclass** — carries the per-athlete snapshot required
   to run the pipeline without shared mutable state:
   - `athlete_id: str`
   - `athlete_profile: UniversalAthleteProfile`
   - `garmin_data: GarminSyncResult`
   - `weather_snapshot: WeatherSnapshot`
   - Per-athlete engine instances (hydrated from DB at call time — see engine hydration below)
   - `db: DatabaseManager` (or `AsyncConnection` post T5-08)
   - Governance context (thresholds, APL phase)

3. **Engine hydration per call** — In single-athlete mode, engines are hydrated once at
   `DailyCoach.__init__()`. In multi-athlete mode, each call to `coaching_pipeline()`
   hydrates engines from DB for the target athlete. This is O(1) per athlete per call;
   DB read amplification is bounded by athlete count × morning-routine frequency (once
   daily). For Phase 8B scale (≤50 athletes), this is acceptable. Phase 9 may introduce
   a hydration cache with per-athlete TTL if profiling shows it is needed.

4. **Single supervised scheduler** — A `CoachingScheduler` (new module
   `titan/orchestration/coaching_scheduler.py`) replaces per-athlete daemon threads.
   It holds an athlete registry (list of `athlete_id`, schedule config) and fires
   `coaching_pipeline()` for each athlete at their configured time using a
   `ThreadPoolExecutor` with a fixed thread cap. Overlap protection per athlete is
   enforced via per-athlete locks (same pattern as the existing
   `DailyCoach._routine_lock`).

5. **Single-athlete CLI mode unchanged** — `DailyCoach.run_morning_routine()` is retained
   as a thin wrapper that constructs the `AthleteCoachingContext` and delegates to
   `coaching_pipeline()`. The existing daemon thread and scheduler cron logic remain
   intact. No behaviour change for single-athlete operation.

### What this ADR does NOT change

- `DailyCoach` is not deleted — it is kept as the single-athlete entrypoint.
- No code changes are mandated by this ADR itself. Changes are in T5-16-A.
- ADR-0033 Layer 3 (per-athlete threshold overrides, calibration isolation) remains Phase 9.
- T5-09, T5-11, T5-13 are not unblocked by this ADR alone — they have their own gate
  criteria. This ADR unblocks T5-09's `get_athlete_context()` design and any multi-athlete
  coaching execution work.

---

## Implementation Entry Created

**T5-16-A** — Extract `coaching_pipeline()` stateless function + `AthleteCoachingContext`
dataclass + `CoachingScheduler` stub; retain `DailyCoach.run_morning_routine()` as wrapper.
(Phase 8B; Workflow Path A; created by this ADR on acceptance.)

---

## Alternatives Considered

### Model 1 — Separate instances (rejected)

Each athlete gets a full `DailyCoach` object with its own daemon thread. Simplest to
implement but unsustainable at scale: 50 athletes = 50 daemon threads sleeping 23+ hours
per day, with no central supervision, no overlap protection across athletes, and no way
to restart a crashed athlete's thread without restarting the process.

The `DailyCoach.__init__()` already requires 10+ dependencies; constructing 50 copies
at startup bloats the composition root further, compounding the finding from ADR-0017.

**Rejected:** Linear thread growth with no lifecycle supervision.

### Model 3 — FastAPI lifecycle-scoped (rejected)

`DailyCoach` is instantiated as a FastAPI dependency per HTTP request. This conflates
two distinct operations:

- **Coaching execution** — compute today's readiness, governance gates, and plan.
  Triggered by schedule (07:00 daily). Has real side-effects (DB writes, Telegram).
- **Data query** — read athlete context for dashboard display. Triggered by HTTP request.
  Should be side-effect-free.

Executing a full morning routine on every dashboard page load is incorrect behaviour.
The per-request instantiation model also re-hydrates engines on every request, which
is unnecessary for read-only operations (T5-09 `get_athlete_context()` reads DB directly).

**Rejected:** Conflates read path with execution path; inappropriate for scheduled side-effecting work.

---

## Consequences

- **Positive:** Coaching pipeline becomes independently testable without full `DailyCoach`
  construction. Unit tests for individual pipeline steps are unblocked.
- **Positive:** Thread count is O(1) regardless of athlete count (controlled by scheduler
  pool size, not per-athlete daemon threads).
- **Positive:** Multi-athlete execution path is explicit and isolated; bugs in one athlete's
  pipeline cannot affect another's (stateless isolation + per-athlete lock).
- **Positive:** Backward-compatible — single-athlete CLI mode is unchanged until
  `DailyCoach.run_morning_routine()` is explicitly migrated in Phase 9.
- **Negative (acceptable):** Engine hydration cost shifts from once-at-startup to
  once-per-athlete-per-morning-routine-call. At Phase 8B scale (≤50 athletes, 1 call/day
  each) this is negligible.
- **Constraint:** T5-16-A (implementation) must be complete before any multi-athlete
  coaching endpoint (not dashboard *reads*) is built. Dashboard reads (T5-09) are
  unblocked by this ADR and do not require T5-16-A to be resolved first.

---

## Phase 8B Gate Status After This ADR

| Gate | Status |
|---|---|
| T5-16 ADR accepted | ✅ This document |
| Concurrency analysis complete | ✅ See §Concurrency Analysis |
| Daemon thread lifecycle decided | ✅ Retired for multi-athlete; retained for single-athlete CLI |
| Stateless contract defined | ✅ `coaching_pipeline()` + `AthleteCoachingContext` |
| Engine hydration per-athlete specified | ✅ On-demand from DB per call |
| T5-16-A implementation entry created | ✅ See §Implementation Entry |

*T5-09, T5-11, T5-13 remain independent gates for their respective Phase 8B work streams.*
