# ADR-0058: DailyCoach God-Orchestrator Decomposition

**Status:** ACCEPTED
**Date:** 2026-05-24
**Author:** Zaf (Owner) / Claude (Design Authority)
**Supersedes:** ADR-0018 Phase B (partial — extends, does not replace)
**Related:** ADR-0046, T5-16-B, TD-04, TD-NEW-10

---

## Context

`titan/orchestration/daily_coach.py` is 1700+ LOC and owns:

1. Engine hydration (TSBEngine, HRVEngine, ReadinessEngine, etc.)
2. Garmin sync orchestration
3. The 12-step `_decision_pipeline()` governance call chain
4. The `_effect_runner()` (Telegram, persistence, metrics)
5. Background daemon thread management
6. `DegradedModeTracker` state
7. Morning routine scheduling

ADR-0018 Phase B extracted `_decision_pipeline()` and `_effect_runner()` as
internal boundaries. T5-16-B extracted `coaching_pipeline()` and
`CoachingScheduler`. Despite this, `DailyCoach` remains a god-orchestrator:
it is the single object that knows about every subsystem. Adding a new
biometric source, a new governance gate, or a new effect (Slack, email)
requires touching `DailyCoach` directly.

The specific failure modes (TD-04 / TD-NEW-10):
- Regression risk: any change to DailyCoach touches all subsystems
  simultaneously
- Test surface: `DailyCoach` tests require mocking 8+ subsystems
- Multi-athlete path: `coaching_pipeline()` exists but `DailyCoach.__init__`
  still hydrates engines once at startup, shared across hypothetical athletes

---

## Decision

Decompose `DailyCoach` across **three bounded phases**, with each phase
independently deliverable and testable. No phase requires the next to be
complete.

### Phase A — Engine Registry (this ADR, immediate)

Extract engine instantiation into a named `EngineRegistry` dataclass.
`DailyCoach.__init__` builds an `EngineRegistry` and holds it as
`self.engines`. No other change.

```python
@dataclass
class EngineRegistry:
    tsb:          TSBEngine
    hrv:          HRVGuidedEngine
    readiness:    ReadinessEngine
    autonomic:    AutonomicFusionEngine
    biomechanics: BiomechanicsEngine
    durability:   DurabilityEngine
    fatigue:      FatigueEngine
    lactate:      LactateLogic
    cs_tracker:   CriticalSpeedTracker
    apl:          AdaptivePriorityLock
```

Benefits immediately:

* `coaching_pipeline()` receives `EngineRegistry` → no implicit state access
* Tests can construct minimal registries with only the engines they need
* Future: per-athlete registry instantiated per-call (Phase 9 multi-athlete)

### Phase B — Effect Isolation (Phase 24, this amendment)

Extract `_effect_runner()` from `DailyCoach` into a standalone
`TitanEffectBus` class in `titan/orchestration/effect_bus.py`.
The bus receives a `DecisionResult` and dispatches each `PlannedEffect`
to a registered handler. Handlers are registered at construction time,
not hardcoded in the dispatch loop.

#### Motivation

`_effect_runner()` currently:

1. Runs a degraded-mode lifecycle check unconditionally (not a PlannedEffect).
2. Iterates `result.planned_effects` and branches on `effect_type` strings.
3. Is coupled to `DailyCoach` instance state (`self.outcome_tracker`,
   `self.telegram`, `self.garmin`, `self._degraded_tracker`).

This coupling prevents independent testing of effect dispatch, makes adding
new effects (Slack, email, webhooks) require modifying DailyCoach, and
blocks the Phase 28 inference layer from injecting synthetic effects.

#### TitanEffectBus Interface

```python
# titan/orchestration/effect_bus.py
from __future__ import annotations
from typing import Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from titan.orchestration.contracts import DecisionResult, PlannedEffect

EffectHandler = Callable[["PlannedEffect", "DecisionResult"], None]

class TitanEffectBus:
    """Dispatches PlannedEffects to registered handlers (ADR-0058 Phase B).

    Handlers are registered at construction time by the composition root
    (titan/main.py or titan/worker/__init__.py). The bus is stateless with
    respect to the decision — it holds no coaching state itself.

    Lifecycle hook:
      before_dispatch(result) is called once before the effect loop.
      Used for degraded-mode tracker update (T2-13 / ADR-0050).
      Defaults to no-op; injected by composition root.
    """
    def __init__(
        self,
        handlers: dict[str, EffectHandler],
        before_dispatch: Callable[["DecisionResult"], None] | None = None,
    ) -> None: ...

    def dispatch(self, result: "DecisionResult") -> bool:
        """Execute all planned effects in order. Returns True if all succeed."""
        ...

    def register(self, effect_type: str, handler: EffectHandler) -> None:
        """Register or replace a handler for the given effect_type."""
        ...
```

#### Canonical effect_type Values

The following are the exhaustive discriminant values for `PlannedEffect.effect_type`.
They are defined as module-level string constants in `contracts.py`:

```python
EFFECT_RECORD_OUTCOME = "record_outcome"
EFFECT_SEND_TELEGRAM  = "send_telegram"
```

Any new effect type MUST be added here and to this ADR before use.

#### Degraded-Mode Lifecycle Hook

The degraded-mode tracker update currently runs unconditionally at the top of
`_effect_runner()` before the effect loop. In Phase B it becomes the
`before_dispatch` hook injected at construction:

```python
def _make_degraded_hook(tracker, garmin, telegram):
    def hook(result: DecisionResult) -> None:
        trace = result.decision_trace
        tracker.update(
            flags={
                "persistence_degraded": bool(trace.get("persistence_degraded")),
                "data_confidence_low": bool(trace.get("data_confidence_low")),
                "garmin_data_stale": bool(trace.get("garmin_data_stale")),
                "garmin_api_degraded": bool(getattr(garmin, "is_api_degraded", False)),
            },
            alert_fn=lambda msg: telegram.send_alert(msg),
        )
    return hook
```

#### DailyCoach._effect_runner After Phase B

`DailyCoach._effect_runner` becomes a one-line delegation shim:

```python
def _effect_runner(self, result: DecisionResult) -> bool:
    return self._effect_bus.dispatch(result)
```

`self._effect_bus: TitanEffectBus` is constructed in `DailyCoach.__init__`
and wired with the two canonical handlers and the degraded-mode hook.
The shim is retained for backward compatibility with the `CoachCallables`
protocol; it will be removed when Phase C extracts the protocol.

#### Implementation Scope (Phase B only — 6 files)

| File | Change |
|------|--------|
| `titan/orchestration/effect_bus.py` | NEW — TitanEffectBus class |
| `titan/orchestration/contracts.py` | Add EFFECT_RECORD_OUTCOME, EFFECT_SEND_TELEGRAM constants |
| `titan/orchestration/daily_coach.py` | Wire self._effect_bus; _effect_runner becomes delegation shim |
| `titan/orchestration/coaching_pipeline.py` | No change required (CoachCallables protocol unchanged) |
| `tests/test_adr0058_fitness.py` | Phase B fitness gate (see below) |
| `docs/adr/0058-dailycoach-decomposition.md` | This amendment |

Explicitly OUT OF SCOPE for Phase B:
- Daemon lifecycle extraction (Phase C)
- CoachingScheduler activation (Phase 26)
- Per-athlete EffectBus isolation (Phase 9)
- Handler persistence / replay (Phase 28)

#### Phase B Fitness Functions

```python
# tests/test_adr0058_fitness.py (additions)

def test_effect_bus_module_exists():
    """titan/orchestration/effect_bus.py must exist and be importable."""

def test_effect_runner_is_delegation_shim():
    """DailyCoach._effect_runner must delegate to self._effect_bus.dispatch()
    and contain no direct outcome_tracker or telegram calls."""

def test_effect_bus_handlers_are_registered_not_hardcoded():
    """TitanEffectBus.dispatch must not contain if/elif effect_type branches —
    all dispatch must go through the handler registry."""

def test_effect_type_constants_defined_in_contracts():
    """EFFECT_RECORD_OUTCOME and EFFECT_SEND_TELEGRAM must be importable
    from titan.orchestration.contracts."""
```

#### Consequences

**Positive:**
- New effects (Slack, webhook, metrics flush) require zero changes to DailyCoach.
- TitanEffectBus is independently testable with mock handlers.
- Phase 28 inference layer can inject synthetic effects without touching DailyCoach.
- `_effect_runner` shrinks to 1 line; DailyCoach LOC reduced ~65 lines.

**Negative:**
- One new module (effect_bus.py) — module budget: update MODULE_COUNT_CEILING.
- Construction root (worker/__init__.py, main.py) must wire the bus.

**Invariant preserved:**
- `CoachCallables` protocol (`_decision_pipeline`, `_effect_runner`) is
  unchanged — no blast radius to coaching_pipeline.py callers.

### Phase C — Daemon Extraction (future, Phase 20+)

Move the background thread lifecycle (`_start_daemon`, `_stop_daemon`, morning
routine scheduling) into `CoachingScheduler` (already stubbed in T5-16-B).
`DailyCoach` becomes a pure synchronous coaching object.

Not implemented in this ADR. Stub only.

**Implemented 2026-10-09 (plan task 9, PR #972, D-035):** the thread lifecycle
(`run_morning_routine_async`, `_routine_thread`, `_routine_started_monotonic`)
moved to `BackgroundRoutineRunner` in `titan/orchestration/routine_runner.py`.
`titan/main.py` builds the runner around `daily_coach.run_morning_routine` and
`daily_coach.routine_lock`, schedules `runner.start`, and joins `runner.thread`
at shutdown. `DailyCoach` keeps only the lock, which it also holds while it
hydrates engines. The runner was not merged into `CoachingScheduler`: that class
calls its callbacks in its own loop and is not used by the console (D-035).

---

## EngineRegistry Contract

```python
# titan/orchestration/engine_registry.py

@dataclass(frozen=True)
class EngineRegistry:
    """
    Named container for all per-athlete science engines.

    Frozen: engines are hydrated once per coaching pipeline call,
    not mutated between calls. Thread safety: each call to
    coaching_pipeline() should receive its own registry instance
    (or a shared one if engines are stateless).

    Phase 9 multi-athlete: instantiate one EngineRegistry per athlete
    per pipeline call. No shared mutable engine state.
    """
    tsb:          TSBEngine
    hrv:          HRVGuidedEngine
    readiness:    ReadinessEngine
    autonomic:    AutonomicFusionEngine
    biomechanics: BiomechanicsEngine
    durability:   DurabilityEngine
    fatigue:      FatigueEngine
    lactate:      LactateLogic
    cs_tracker:   CriticalSpeedTracker
    apl:          AdaptivePriorityLock

    @classmethod
    def from_db(
        cls,
        db: DatabaseManager,
        athlete_id: str = "owner",
    ) -> "EngineRegistry":
        """
        Factory: hydrate all engines from DB for a given athlete.
        Single entry point — no engine construction elsewhere.
        """
        ...
```

`DailyCoach.__init__` builds `EngineRegistry` from injected parameters and
stores the result as `self.engines`. All existing code that accessed
`self.tsb_engine`, `self.hrv_engine`, etc. is redirected to
`self.engines.tsb`, `self.engines.hrv`, etc. via backward-compat properties.
No logic change — pure structural reorganisation.

`coaching_pipeline()` receives `EngineRegistry` via
`AthleteCoachingContext.engines`.

---

## Fitness Functions (CI-blocking after this ADR)

```python
# tests/test_adr0058_fitness.py

def test_engine_registry_is_single_construction_site():
    """
    No engine class (TSBEngine, HRVGuidedEngine, etc.)
    may be instantiated outside EngineRegistry.from_db()
    and titan/main.py (composition root).
    Exceptions: test files.
    """

def test_daily_coach_has_engines_attribute():
    """
    DailyCoach must expose self.engines: EngineRegistry
    after Phase A.
    """
```

---

## Consequences

**Positive:**

* `DailyCoach` LOC reduced ~150 lines (engine init block)
* Tests can construct `EngineRegistry` with mocks for only needed engines
* `coaching_pipeline()` is now fully self-contained (receives all state)
* Phase 9 multi-athlete path is unblocked: `EngineRegistry.from_db(athlete_id)` per athlete

**Negative:**

* One new module (`engine_registry.py`) — module budget: 72→73, update ceiling
* All `self.tsb_engine` → `self.engines.tsb` renames touch DailyCoach broadly
  (risk: high line count, low logic complexity — mitigated by fitness functions)

**Residual (Phase B/C):**

* `_effect_runner()` remains in DailyCoach until Phase B
* Daemon lifecycle remains in DailyCoach until Phase C
* DailyCoach is still large, but now has a clear decomposition path

---

## Implementation Checklist

* [x] `titan/orchestration/engine_registry.py` — `EngineRegistry` dataclass + `from_db()` factory
* [x] `DailyCoach.__init__` — build `EngineRegistry`, store as `self.engines`
* [x] `DailyCoach` — backward-compat properties for all engine attribute names
* [x] `AthleteCoachingContext` — add `engines: EngineRegistry | None` field
* [x] `titan/main.py` — use `EngineRegistry.from_db(db)` as single construction site
* [x] `titan/science/biomechanics.py` — `BiomechanicsEngine` alias
* [x] `tests/test_adr0058_fitness.py` — fitness functions
* [x] `MODULE_COUNT_CEILING` bumped 72→73 (T4-27-C protocol)
* [x] CLAUDE.md updated (ceiling 73 confirmed)
* [x] TD-04 / TD-NEW-10 RESOLVED in TECHNICAL_DEBT.md

---

## References

* ADR-0018: decision pipeline / effect runner boundary
* ADR-0046: multi-athlete execution model (CoachingScheduler)
* T5-16-B: coaching_pipeline.py + CoachingScheduler stub
* TD-04: DailyCoach god-orchestrator (Phase 17+)
* TD-NEW-10: Opus audit finding (2026-05-22)
