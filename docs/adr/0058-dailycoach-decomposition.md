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

### Phase B — Effect Isolation (future, Phase 20)

Split `_effect_runner()` into a separate `TitanEffectBus` class that receives
a `DailyCoachingPayload` and dispatches to registered handlers (Telegram,
persistence, metrics). Handlers are registered at startup, not hardcoded.

Not implemented in this ADR. Stub only.

### Phase C — Daemon Extraction (future, Phase 20+)

Move the background thread lifecycle (`_start_daemon`, `_stop_daemon`, morning
routine scheduling) into `CoachingScheduler` (already stubbed in T5-16-B).
`DailyCoach` becomes a pure synchronous coaching object.

Not implemented in this ADR. Stub only.

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
