# ADR 0017 — Composition Root Fan-In and DailyCoach God-Orchestrator: Architecture Audit

**Date:** 2026-03-04
**Branch:** `claude/fix-db-concurrency-race-rKCdE`
**Type:** Architectural Assessment (read-only, no code changes)
**Scope:** Structural coupling audit of `titan/main.py` and `titan/orchestration/daily_coach.py`

---

## Context

The engineering audit of 2026-03-04 identified two structural observations about the
system's composition topology:

1. **High fan-in composition root** — `titan/main.py` imports and wires a large number
   of modules directly at startup.
2. **DailyCoach as god-orchestrator** — `DailyCoach` owns hydration, sync, persistence,
   governance flow, and delivery preparation across its constructor and 12-step morning
   routine.

A third observation — broad `Any` fields in typed payload contracts — is tracked as an
engineering debt item (T4-10 in `TECHNICAL_DEBT.md`) because it has a concrete fix path
that does not require architectural decision.

This ADR records the assessment of observations 1 and 2: what the patterns are, what
their trade-offs are, and what (if anything) should be done.

---

## Findings

### Finding 1 — High Fan-In Composition Root (`titan/main.py`)

#### Pattern description

`titan/main.py` is the system's single composition root. It imports and instantiates:
- All six background workers (`GarminSync`, `WeatherAPI`, `TitanTelegramBot`, scheduler)
- All science engines passed into `DailyCoach`
- The database manager
- The UI layer (`MenuSystem`, `OperatorConsoleService`)

All wiring happens in one place, producing a high-fan-in import graph at the startup
boundary.

#### Trade-offs

| | Detail |
|---|---|
| **Upside** | Single place to see all dependencies; easy to audit what the system uses |
| **Upside** | No hidden singletons or ambient globals; all objects are explicitly constructed |
| **Upside** | Straightforward to mock the entire system in tests by patching at construction |
| **Downside** | High blast radius for startup changes — modifying any imported module can break startup |
| **Downside** | Subsystem ownership is unclear; `titan/main.py` has no bounded identity |
| **Downside** | Import-time side effects (if any module has them) all fire together |

#### Assessment

For a single-athlete, single-process system of the current scale, a monolithic
composition root is a reasonable and common pattern. The risk is not correctness — it is
**change surface concentration**. Any refactor of the startup sequence must touch
`titan/main.py`, and all subsystems are coupled to each other through it.

The pattern becomes a problem when:
- New subsystems are added without a clear ownership boundary
- Startup failures in one subsystem prevent the others from starting (already partially
  mitigated by the T2-07 startup observability fix)
- Testing requires constructing the entire system to test one subsystem

**No immediate code change is recommended.** The pattern is acceptable at current scale.

#### Future direction (not a commitment)

If the system grows to 3+ distinct user-facing subsystems (e.g., CLI + Operator Console
API server + Telegram bot as independent processes), the composition root should be split
into per-subsystem entrypoints with a shared dependency kernel. This is a Phase 9+
concern.

---

### Finding 2 — DailyCoach as God-Orchestrator

#### Pattern description

`DailyCoach.__init__()` accepts 10+ engine/integration dependencies and owns:
- Cold-start hydration (CTL/ATL rebuild, baseline fetch)
- Garmin sync coordination
- Governance gate evaluation
- Persistence of results to DB
- Telegram delivery preparation

The 12-step `run_morning_routine()` is the single method that sequences all of this.

#### Trade-offs

| | Detail |
|---|---|
| **Upside** | All morning routine logic is in one file; easy to read end-to-end |
| **Upside** | Execution order is explicit and auditable (numbered steps) |
| **Upside** | No hidden sequencing; step failures are visible in one place |
| **Downside** | High complexity concentration — constructor dependency surface is very large |
| **Downside** | High change-risk concentration — any morning routine concern requires touching `daily_coach.py` |
| **Downside** | Difficult to unit-test individual steps without constructing the full `DailyCoach` |
| **Downside** | The daemon overlap bug (T1-07) is a direct consequence of `DailyCoach` owning its own thread management without a lifecycle supervisor |

#### Assessment

`DailyCoach` is a classic **orchestrator god object**. At the current system scale and
team size, the centralisation provides more benefit (clarity, auditability) than harm.
The 12-step structure makes the routine readable in a single pass.

The pattern becomes a problem when:
- Individual steps need independent scheduling or retry semantics
- Steps need to be reordered or composed differently for different athlete profiles
- The 12-step routine grows beyond ~15 steps (cognitive load threshold)

**No immediate restructuring is recommended.** The most impactful near-term improvement
is not decomposing `DailyCoach` but rather adding the lifecycle supervision guard
(T1-07 in `TECHNICAL_DEBT.md`) that prevents daemon overlap — the most acute operational
risk from the current design.

#### Future direction (not a commitment)

If routine step count grows past ~15, or if per-step retry/scheduling requirements
diverge, the appropriate decomposition is:

1. **Lifecycle supervisor** — a single `WorkerSupervisor` class that owns start/health/
   stop/drain for all background threads (Garmin, Weather, Telegram, DailyCoach scheduler).
   This removes thread management responsibility from `DailyCoach` and addresses T1-07,
   T3-06, and T3-07 in a single architectural move.

2. **Step extraction** — each of the 12 steps becomes an independently callable function
   (or `Step` object) that `DailyCoach` sequences. Steps can be tested independently
   without constructing the full orchestrator.

Neither decomposition should be attempted until the current open debt items (T1-06
through T1-09) are resolved — structural refactors on top of race conditions add risk
without benefit.

---

## Decision

**Status: Accepted — fan-in paths documented (Phase B assessment complete)**

Both patterns — monolithic composition root and god-orchestrator DailyCoach — are
**accepted as-is** at the current system scale. No code changes are mandated by this ADR.

The following engineering debt items have been registered in `TECHNICAL_DEBT.md` as the
concrete, incremental improvement path:

| Item | Concern addressed |
|---|---|
| T1-06 | DB concurrency race (root cause: shared-connection model in composition root) |
| T1-07 | DailyCoach daemon overlap (root cause: no lifecycle supervisor) |
| T3-06 | Worker shutdown escalation (root cause: no supervisor for join outcome) |
| T3-07 | `scheduled_tasks` unsynchronised (root cause: DailyCoach owns scheduling) |
| T4-10 | `Any`-typed payload contracts (root cause: typed contracts introduced incrementally) |

The lifecycle supervisor pattern (described in Finding 2 → Future direction) is the
recommended Phase 9 architectural move if and when debt items T1-06, T1-07, T3-06, and
T3-07 do not collectively resolve the operational risks from the current design.

---

## What This ADR Does Not Change

- `titan/main.py` is not modified.
- `titan/orchestration/daily_coach.py` is not modified.
- No new modules are introduced by this ADR.
- Engineering debt items registered here must go through their own implementation PRs.

---

*Assessment only. No `.py` files modified.*
