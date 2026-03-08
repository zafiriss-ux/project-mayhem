# ADR 0018 — Kernel Boundary: Decision Pipeline / Effect Runner Split

**Date:** 2026-03-05
**Branch:** `claude/kernel-boundary-pipeline-split-gH04T`
**Type:** Architectural Decision + Implementation Plan
**Status:** Accepted — Phase A implemented (v5.8.0); Phase B implemented (v5.8.0; commit c51e217) 2026-03-08
**Scope:** Phase A (Surgical — implemented) + Phase B (Structural — implemented 2026-03-08)
**Supersedes:** N/A
**Related:** ADR-0017 (Composition Root & DailyCoach Architecture Audit)

---

## Context

After the Phase 7.5 Hardening Sprint (closed 2026-03-04) the system is stable at the
concurrency and data integrity level. A post-close audit identified a deeper architectural
issue: TITAN OS has no clean runtime boundary between **pure decisions** and **side-effects**
(DB writes, Telegram delivery, sync). All confirmed issues share a single root cause.

### Diagnosed findings (from live code)

**`titan/core/database.py` — write method cursor race window**

All six write methods (`save_daily_metric`, `save_session`, `save_hrr`,
`update_shoe_mileage`, `add_shoe`, `save_personal_best`) create the cursor **before**
acquiring `self._lock`:

```python
# Current (wrong):
cursor = self.conn.cursor()   # ← outside lock, outside _closed check
with self._lock:
    cursor.execute(...)
```

`_ensure_open_locked()` exists and is called correctly by all **read** paths (`lock →
_ensure_open_locked → cursor`). The write paths have always skipped this guard, leaving a
race window between cursor creation and the `_closed` flag check.

**`titan/orchestration/daily_coach.py` — non-atomic persistence**

`_persist_garmin_data()` writes activities one-by-one (individual `commit()` calls per
activity, then a separate `commit()` for daily metrics). A crash or exception mid-loop
leaves a **partial day state** — some activities committed, daily metrics absent —
with no rollback mechanism.

**`titan/main.py` — shutdown race**

The shutdown sequence is:
```
garmin.stop → weather.stop → telegram.stop → db.close()
```
There is no explicit `join()` of the `DailyCoach._routine_thread` before `db.close()`.
If the routine is mid-execution at shutdown time, any subsequent DB operation hits a
closed connection → `sqlite3.ProgrammingError`.

### Common root cause

> **Side-effects without a central lifecycle / effect boundary.**

All three issues are independent manifestations of the same design gap: write-path
operations are scattered across threads and methods with no single serialisation point
and no lifecycle contract.

---

## Decision

TITAN OS introduces a **Kernel Boundary** separating two execution phases:

```
┌─────────────────────────────────────────────────────────┐
│  DECISION PIPELINE  (pure, deterministic)               │
│  Input:  snapshot of state (DB reads, Garmin data)      │
│  Output: DecisionResult (decisions + planned effects)   │
│  Invariant: NO side-effects here                        │
└─────────────────────────┬───────────────────────────────┘
                          │ DecisionResult
                          ▼
┌─────────────────────────────────────────────────────────┐
│  EFFECT RUNNER  (serialized, lifecycle-managed)         │
│  Input:  DecisionResult                                 │
│  Executes: DB writes → Telegram send → schedule         │
│  Invariant: one effect at a time, shutdown-safe         │
└─────────────────────────────────────────────────────────┘
```

The separation is implemented in two phases. Phase A is surgical (no structural
reorganisation). Phase B is structural (explicit pipeline split).

---

## Implementation Plan

### Phase A — Surgical Fixes ✅ Implemented (v5.8.0)

**Execution order is strict (CLAUDE.md Rule E1):**

```
A1 (database.py write methods)
    ↓
A2 (main.py shutdown join)      ← may execute in parallel with A1
    ↓
A3 (atomic persistence)         ← depends on A1
```

---

#### Task A1 — DB write methods: cursor inside lock

**File:** `titan/core/database.py`
**Methods:** `save_daily_metric`, `save_session`, `save_hrr`, `update_shoe_mileage`,
`add_shoe`, `save_personal_best`

Apply the same pattern already used by all read paths:

```python
# BEFORE (wrong):
cursor = self.conn.cursor()      # ← outside lock, outside _closed check
with self._lock:
    cursor.execute(...)
    self.conn.commit()

# AFTER (correct — same as read paths):
with self._lock:
    self._ensure_open_locked()   # ← guard before any use of self.conn
    cursor = self.conn.cursor()  # ← inside lock
    cursor.execute(...)
    self.conn.commit()
```

Note: `save_session` contains two `cursor.execute()` calls (training_log insert +
gear_usage update). Both must remain inside the same `with self._lock` block. The
`training_load` calculation (pure arithmetic) may remain outside the lock.

---

#### Task A2 — main.py shutdown: join routine thread before db.close()

**File:** `titan/main.py`
**Location:** `finally` block of `main()`

```python
# BEFORE:
garmin.stop_background_sync()
weather.stop_background_updates()
telegram.stop_bot()
db.close()

# AFTER:
garmin.stop_background_sync()
weather.stop_background_updates()
telegram.stop_bot()
# Explicit join before db.close() — prevents sqlite3.ProgrammingError at shutdown
routine_thread = getattr(daily_coach, '_routine_thread', None)
if routine_thread is not None and routine_thread.is_alive():
    routine_thread.join(timeout=30)
    if routine_thread.is_alive():
        log.error(
            "worker_shutdown_timeout",
            extra={
                "worker_name": "DailyCoachRoutine",
                "timeout_seconds": 30,
                "still_alive": True,
            },
        )
db.close()
```

The `worker_shutdown_timeout` event follows the T3-06 pattern already established for
the three background worker stop paths.

---

#### Task A3 — `_persist_garmin_data()`: atomic SQLite transaction

**File:** `titan/orchestration/daily_coach.py`
**Method:** `_persist_garmin_data()`

Wrap the activity loop and the daily metrics write in a single SQLite transaction via
`DatabaseManager`. All activity saves and the `save_daily_metric` call must either all
commit or all roll back together. No partial day state may be persisted.

Implementation approach (engineer discretion on exact API surface):

- Option 1: add a `begin_transaction()` / `commit_transaction()` / `rollback_transaction()`
  context manager to `DatabaseManager` that wraps raw `self.conn` transaction control
  under the existing `self._lock`.
- Option 2: collect all writes as a batch operation and execute them in a single
  `with self._lock` block within `DatabaseManager` (single cursor, single commit).

Whichever approach is chosen, the invariant is:

> After `_persist_garmin_data()` returns, the database contains either **all** of
> today's activities + daily metrics, or **none** of them. There is no intermediate state.

---

### Phase B — Decision/Effect Separation ✅ Implemented (commit c51e217, 2026-03-08)

**Status:** Accepted 2026-03-07. Scoped implementation plan below. No implementation in current sprint.

**Scope note — pipeline boundary correction (2026-03-07):**
The original design described a "steps 1–11 pure, step 12 effects" split. Pre-implementation
code review of `run_morning_routine()` revealed that steps 2, 3, 6, and 7 contain
**operational safety side-effects** that cannot be deferred:
- Step 2: `db.record_sync_outcome()`, `telegram.send_alert()` (persistence failure + staleness)
- Step 3: `db.save_hrr()` inside HRV/HRR feed
- Step 6: `db.update_glycogen_debt()`
- Step 7: `telegram.send_alert()` (degraded RHR baseline — fires even if governance hard-stops)

Deferring these to an effect runner would break the safety design: a persistence failure
alert must reach the athlete before the coaching recommendation, regardless of governance
outcome. These alerts are not coaching effects — they are operational signals.

**Corrected boundary:**
- **Data hydration phase (steps 1–6):** remains in `run_morning_routine()` unchanged.
  Sequential, side-effectful by necessity; A3 atomic-persistence invariant already covers this.
- **Decision pipeline (steps 7–11):** `_decision_pipeline()` — pure computation.
  Input: all signals produced by steps 1–6. Output: `DecisionResult`.
- **Effect runner (step 9c + step 12):** `_effect_runner()` — outcome recording + Telegram delivery.

B3 (deterministic replay) from the original design is not a separate implementation task —
it is an architectural consequence of `_decision_pipeline()` being pure.

---

#### Task B1 — `PlannedEffect` + `DecisionResult` in `contracts.py`

**File:** `titan/orchestration/contracts.py`

Add two new types. `PlannedEffect` must be defined before `DecisionResult`.

```python
@dataclass(frozen=True)
class PlannedEffect:
    """A single side-effect to be executed by the Effect Runner.

    effect_type discriminant values (exhaustive):
      'record_outcome'  — write governance decision to outcome_tracker (DB)
      'send_telegram'   — deliver coaching briefing via Telegram
    """
    effect_type: str                        # discriminant (see docstring)
    payload: Mapping[str, object]           # effect-specific data, frozen at decision time


@dataclass(frozen=True)
class DecisionResult:
    """Immutable output of the Decision Pipeline (steps 7–11).

    Invariant: constructed without executing any side-effects.
    The same DecisionResult can be replayed against any EffectRunner.
    """
    session_plan: TodaySessionPlan          # post-governance recommendation
    coaching_payload: DailyCoachingPayload  # Telegram delivery content
    planned_effects: tuple[PlannedEffect, ...]  # ordered effects (tuple — immutable)
    decision_trace: Mapping[str, object]    # forensic replay data (frozen dict)
    snapshot_at: str                        # ISO-8601 timestamp of state snapshot
```

Implementation notes:
- Use `tuple[PlannedEffect, ...]` not `list` — `DecisionResult` is `frozen=True`;
  mutable fields are prohibited.
- `decision_trace` captures the governance gate outputs and key input values at
  decision time. Minimum fields: `hrv`, `tsb`, `acwr`, `lock_codes_active`,
  `session_planned_pre_governance`, `locks_applied`, `governance_clean`, `phase`,
  `vlg_color`, `afi_value`, `readiness_score`, `glycogen_debt`.
  These fields are needed by `_effect_runner()` to call `outcome_tracker.record_decision()`
  without re-reading the database.
- `snapshot_at` is a plain ISO-8601 string (not `datetime`) — trivially JSON-serialisable.
- `PlannedEffect` has two `effect_type` values only: `'record_outcome'` and
  `'send_telegram'`. Data hydration effects (steps 1–6) are outside the pipeline boundary.

---

#### Task B2 — Refactor `run_morning_routine()` into `_decision_pipeline()` + `_effect_runner()`

**File:** `titan/orchestration/daily_coach.py`

```python
def run_morning_routine(self, soreness=None, subjective_fatigue_score=None):
    # ── Data hydration (steps 1–6) — unchanged ──────────────────────────
    # Side-effectful by design: DB writes, conditional safety alerts.
    # A3 atomic-persistence invariant applies to _persist_garmin_data().
    garmin_data   = step_1_sync_garmin()
    rhr, sleep_s, sleep_h = step_2_persist(garmin_data)
    step_3_feed_hrv_hrr(garmin_data)
    afi_final, afi_constraints = step_4_compute_afi(garmin_data, sleep_s)
    tsb_value, tsb_status, cs_thermal = step_5_kinetics(garmin_data)
    step_6_update_glycogen(garmin_data, sleep_h)

    # ── Decision Pipeline (steps 7–11) — pure ───────────────────────────
    result: DecisionResult = self._decision_pipeline(
        garmin_data=garmin_data,
        soreness=soreness,
        subjective_fatigue_score=subjective_fatigue_score,
        afi_final=afi_final,
        afi_constraints=afi_constraints,
        tsb_value=tsb_value,
        tsb_status=tsb_status,
        cs_thermal=cs_thermal,
        rhr=rhr,
        sleep_score=sleep_s,
        sleep_hours=sleep_h,
        persistence_degraded=persistence_degraded,
        garmin_data_stale=garmin_data_stale,
        data_trust=data_trust,
    )

    # ── Effect Runner (step 9c + step 12) ───────────────────────────────
    return self._effect_runner(result)
```

**`_decision_pipeline()` contract (strict):**
- Accepts all signals produced by steps 1–6 as keyword arguments (including baseline RHR,
  which is pre-computed in `run_morning_routine()` because its unavailability triggers a
  safety alert that must fire before the pipeline runs).
- Executes: step 7 (readiness + fatigue), step 7.5 (intensity governor), step 8 (today's
  session), step 9a (VLG + APL), step 9b (governance), step 10 (optimal time), step 11
  (nutrition), and coaching payload assembly.
- Populates `DecisionResult.decision_trace` with all fields needed for outcome recording.
- DB reads inside the pipeline (e.g. `weekly_planner.get_today_session()`,
  `governance.get_governance_report()`) are permitted — reads have no side effects.
- **Prohibited:** any `db.save_*`, any `telegram.*`, any `self.db.transaction()`.
- Violation of the no-write / no-send invariant is a **P0 defect — not a warning**.

**`_effect_runner()` contract (strict):**
- Accepts a `DecisionResult` and iterates `planned_effects` in order.
- Dispatches on `PlannedEffect.effect_type`:
  - `'record_outcome'` → calls `self.outcome_tracker.record_decision(...)` using
    fields from `result.decision_trace`
  - `'send_telegram'`  → calls `self.telegram.send_daily_coaching(result.coaching_payload)`
- Also calls `self._degraded_tracker.update(...)` with the alert lambda before dispatching
  effects (degraded-mode persistent alert must fire before coaching delivery).
- Returns `bool` (Telegram delivery success).

**Replay invariant (consequence of purity):**
A saved `DecisionResult` (JSON-serialisable by construction) can be re-fed to any
`_effect_runner()` instance to reproduce or audit past decisions. No additional code
is required for this capability — it is automatic when `_decision_pipeline()` is pure.

---

### Phase C — Effect Registry (Phase 6/7 concern, not current scope)

When TITAN OS grows to multiple concurrent athletes or a web UI, the `EffectRunner`
becomes an explicit service with an effect queue and audit trail. Phase C is a Phase 9
concern. No action required now.

---

## Consequences

### Positive

- **Deterministic replay**: same snapshot → same decision. Forensic debugging enabled.
- **Controlled shutdown**: effects are serialized → join is a single point, not scattered.
- **Concurrency safety by construction**: decision pipeline is pure → thread-safe without
  additional locks.
- **Better observability**: one event stream for all effects; incident diagnosis is easier.
- **Governance layer unchanged**: `GovernanceEngine` and all seven gates remain as-is.

### Trade-offs

- Phase B adds complexity to `DailyCoach` (two private methods instead of one monolith).
- `DecisionResult` is a new type that requires tests.
- Atomic persistence (A3) requires a DB transaction API extension.

### Neutral

- `titan/main.py` composition root is unchanged — ADR-0017 assessment stands.
- `DailyCoach` remains the central orchestrator — no microservice decomposition.
- The lifecycle supervisor pattern (ADR-0017 Finding 2) remains a Phase 9 concern.

---

## Acceptance Criteria — Phase B

| # | Criterion | Verification |
|---|-----------|-------------|
| B1.1 | `PlannedEffect` and `DecisionResult` present in `titan/orchestration/contracts.py` with exact field signatures | Code review |
| B1.2 | `DecisionResult.planned_effects` is `tuple[PlannedEffect, ...]` (immutable) | Code review; `frozen=True` dataclass |
| B1.3 | `PlannedEffect.effect_type` exhaustive values are `'record_outcome'` and `'send_telegram'` only | Code review + docstring |
| B1.4 | `ruff check .` zero findings after B1 | `ruff check .` |
| B1.5 | Full test suite green after B1 | `python -m pytest -q` |
| B2.1 | `run_morning_routine()` calls `_decision_pipeline()` then `_effect_runner()` after steps 1–6 | Code review |
| B2.2 | `_decision_pipeline()` contains zero calls to `db.save_*`, `telegram.*`, or `self.db.transaction()` | `grep -n "save_\|telegram\.\|\.transaction" titan/orchestration/daily_coach.py` → zero hits inside `_decision_pipeline` body |
| B2.3 | `_effect_runner()` dispatches `'record_outcome'` and `'send_telegram'` | Code review + unit test |
| B2.4 | `_persist_garmin_data()` remains inside `self.db.transaction()` (A3 invariant preserved) | Code review |
| B2.5 | `_decision_pipeline()` receives all step 1–6 computed signals as arguments; baseline RHR (DB read with side-effectful alert) is pre-computed in `run_morning_routine()` before the pipeline call | Code review |
| B2.6 | `decision_trace` contains minimum fields: `hrv`, `tsb`, `acwr`, `lock_codes_active`, `session_planned_pre_governance`, `locks_applied`, `governance_clean`, `phase`, `vlg_color`, `afi_value`, `readiness_score`, `glycogen_debt` | Code review + test |
| B2.7 | `ruff check .` zero findings after B2 | `ruff check .` |
| B2.8 | Full test suite green after B2 | `python -m pytest -q` |
| ALL | `python -m pytest -q -W error::pytest.PytestWarning` zero warnings | Gate 2 |
| ALL | Full suite green, count ≥ 1791 | Gate 3 |

---

## Test Matrix — Phase B

### B1 Tests — `tests/titan/orchestration/test_contracts.py`

Create this file if it does not exist.

| Test name | Scenario | Assert |
|-----------|----------|--------|
| `test_planned_effect_is_frozen` | Attempt to mutate a `PlannedEffect` field | `FrozenInstanceError` raised |
| `test_decision_result_is_frozen` | Attempt to mutate a `DecisionResult` field | `FrozenInstanceError` raised |
| `test_decision_result_planned_effects_is_tuple` | Construct `DecisionResult` with a tuple of effects | `isinstance(result.planned_effects, tuple)` |
| `test_planned_effect_discriminants` | Construct both valid `effect_type` values | `effect_type in {'record_outcome', 'send_telegram'}` |

### B2 Tests — `tests/titan/orchestration/test_daily_coach.py`

Add to the existing file.

| Test name | Scenario | Assert |
|-----------|----------|--------|
| `test_decision_pipeline_returns_decision_result` | Call `_decision_pipeline()` with pre-computed signal kwargs (all mocked) | Return type is `DecisionResult` |
| `test_decision_pipeline_no_db_writes` | Patch `db.save_daily_metric`, `db.save_hrr`, `db.update_glycogen_debt`, `outcome_tracker.record_decision`; call `_decision_pipeline()` | None of the mocks are called |
| `test_decision_pipeline_no_telegram_calls` | Patch `telegram.send_daily_coaching`, `telegram.send_alert`; call `_decision_pipeline()` | Neither mock is called |
| `test_decision_pipeline_decision_trace_has_required_fields` | Call `_decision_pipeline()` with mocked signals | `decision_trace` contains all 12 required keys |
| `test_effect_runner_dispatches_record_outcome` | Pass `DecisionResult` with `record_outcome` effect | `outcome_tracker.record_decision` called with trace fields |
| `test_effect_runner_dispatches_send_telegram` | Pass `DecisionResult` with `send_telegram` effect | `telegram.send_daily_coaching` called with `coaching_payload` |
| `test_effect_runner_effects_execute_in_order` | Pass `DecisionResult` with `[record_outcome, send_telegram]` effects | Calls recorded in that order |
| `test_run_morning_routine_delegates_pipeline_then_runner` | Patch `_decision_pipeline` and `_effect_runner`; call `run_morning_routine()` | Pipeline called after step 6; runner called with pipeline's return value |

**Implementation notes:**
- The no-DB-writes test and no-Telegram-calls test are the critical invariant tests.
  They must **fail** (not skip) if any save/send call is detected inside `_decision_pipeline()`.
- `test_decision_pipeline_returns_decision_result` should pass all step 1–6 signal args
  as minimal valid values (e.g. `afi_final=0.0`, `tsb_value=0.0`) with all engine methods
  mocked to return plausible outputs.
- Use `unittest.mock.patch.object` throughout.

---

## Files Affected by Phase B Implementation

| File | Task | Change |
|------|------|--------|
| `titan/orchestration/contracts.py` | B1 | Add `PlannedEffect` + `DecisionResult` dataclasses |
| `titan/orchestration/daily_coach.py` | B2 | Add `_decision_pipeline()` (steps 7–11, pure) + `_effect_runner()` (outcome record + Telegram); refactor `run_morning_routine()` to call them after steps 1–6 |
| `tests/titan/orchestration/test_contracts.py` | B1 | New file — 4 tests for type invariants |
| `tests/titan/orchestration/test_daily_coach.py` | B2 | 8 new tests (pipeline purity × 3 + decision_trace fields + runner dispatch × 2 + ordering + delegation) |

**Files NOT affected by Phase B (boundary is strict):**
- `titan/orchestration/daily_coach.py` steps 1–6 logic — unchanged
- All science engine modules — unchanged
- Governance layer — unchanged
- `titan/main.py` — unchanged

---

## Commit Convention — Phase B

One commit per task:

| Task | Commit message suffix |
|------|-----------------------|
| B1 | `ref ADR-0018-B1` |
| B2 | `ref ADR-0018-B2` |

Each commit must include both the production code change and its tests.

---

## Acceptance Criteria — Phase A

| # | Criterion | Verification |
|---|-----------|-------------|
| A1.1 | All six write methods follow: `lock → _ensure_open_locked → cursor → execute → commit` | Code review |
| A1.2 | `ruff check .` reports zero findings after A1 changes | `ruff check .` |
| A1.3 | Full test suite green after A1 changes | `python -m pytest -q` |
| A2.1 | `finally` block joins `_routine_thread` with `timeout=30` before `db.close()` | Code review |
| A2.2 | `worker_shutdown_timeout` event emitted if thread is still alive at timeout | Test: mock alive thread |
| A2.3 | Full test suite green after A2 changes | `python -m pytest -q` |
| A3.1 | Activity loop + `save_daily_metric` execute in a single SQLite transaction | Code review |
| A3.2 | Exception mid-loop rolls back all activity writes (no partial commit) | Test: crash simulation |
| A3.3 | Full test suite green after A3 changes | `python -m pytest -q` |
| ALL | 1417+ tests green, zero PytestWarning | `python -m pytest -q -W error::pytest.PytestWarning` |
| ALL | Coverage ≥ 91.96% | `pytest --cov=titan --cov-report=term-missing` |

---

## Test Matrix — Phase A (Test Creation Policy)

This section is the **authoritative test specification** for Phase A. The implementing
engineer must produce tests that satisfy every row below. Tests must be committed in the
same PR as the code change they cover (CLAUDE.md Test Creation/Update Rule).

### A1 Tests — `tests/titan/core/test_database.py`

The file exists. Add the following tests to the existing file.

| Test name | Scenario | Assert |
|-----------|----------|--------|
| `test_save_daily_metric_cursor_inside_lock` | Mock `self._lock`, inspect call order | `_ensure_open_locked` called before `cursor()` |
| `test_save_session_cursor_inside_lock` | Same for `save_session` | Same pattern |
| `test_save_hrr_cursor_inside_lock` | Same for `save_hrr` | Same pattern |
| `test_update_shoe_mileage_cursor_inside_lock` | Same for `update_shoe_mileage` | Same pattern |
| `test_add_shoe_cursor_inside_lock` | Same for `add_shoe` | Same pattern |
| `test_save_personal_best_cursor_inside_lock` | Same for `save_personal_best` | Same pattern |
| `test_write_after_close_raises` | Call `db.close()` then any write method | `DatabaseClosedError` or equivalent raised; no `sqlite3.ProgrammingError` leaks |
| `test_concurrent_writes_no_race` | Two threads call `save_daily_metric` simultaneously on same date | Both complete without exception; final state is one of the two valid outcomes |

**Implementation note:** Use `unittest.mock.patch.object` to intercept the lock and
verify that `_ensure_open_locked()` is called within the lock context (i.e., before
`self.conn.cursor()` is reached). For the closed-DB test, use a real `DatabaseManager`
with an in-memory SQLite database (`:memory:`), call `close()`, then assert the write
raises the expected guard error rather than propagating a raw `sqlite3.ProgrammingError`.

---

### A2 Tests — `tests/test_full_lifecycle_stress.py`

The file exists. Add the following tests.

| Test name | Scenario | Assert |
|-----------|----------|--------|
| `test_shutdown_joins_routine_thread_before_db_close` | Patch `daily_coach._routine_thread` with a mock thread that reports `is_alive() = False` | `join()` called before `db.close()` |
| `test_shutdown_timeout_emits_structured_event` | Patch `_routine_thread` with a thread that stays alive through the join | `worker_shutdown_timeout` event emitted at ERROR level with `worker_name`, `timeout_seconds`, `still_alive` fields |
| `test_shutdown_no_join_if_thread_none` | `daily_coach._routine_thread` is `None` | No join attempted; `db.close()` completes normally |
| `test_shutdown_no_join_if_thread_not_alive` | Thread exists but `is_alive()` returns `False` | No join attempted; `db.close()` completes normally |

**Implementation note:** Use `unittest.mock.MagicMock` for the thread object. Assert
the call order using `unittest.mock.call_args_list` or `side_effect` on the mock's
`is_alive()` and `join()` methods. The test must not actually sleep 30 seconds — use
`unittest.mock.patch("threading.Thread.join")` or pass a mock thread directly.

---

### A3 Tests — `tests/titan/orchestration/test_daily_coach.py`

The file exists. Add the following tests.

| Test name | Scenario | Assert |
|-----------|----------|--------|
| `test_persist_garmin_data_all_committed_on_success` | Provide 3 activities + valid daily metrics | DB contains all 3 activities + daily metrics row; no partial state |
| `test_persist_garmin_data_rollback_on_activity_failure` | Patch `db.save_session` to raise on 2nd call | DB contains zero committed activities and no daily metrics row (full rollback) |
| `test_persist_garmin_data_rollback_on_metrics_failure` | Patch `db.save_daily_metric` to raise | All activity writes rolled back; DB is empty |
| `test_persist_garmin_data_empty_activities` | `garmin_data['activities'] = []` | Only daily metrics row committed; no exception |
| `test_persist_garmin_data_idempotent_on_retry` | Call `_persist_garmin_data` twice with same data | Second call either replaces or raises duplicate cleanly; no partial state |

**Implementation note:** Use an in-memory SQLite `DatabaseManager` (`:memory:`) rather
than mocking DB calls, so the rollback assertion is real. The test must verify database
state directly (query the DB after the call) — not just assert that no exception was
raised. For rollback tests, use `unittest.mock.patch.object(db, 'save_session',
side_effect=[None, RuntimeError("simulated crash")])` and then query
`db.conn.execute("SELECT COUNT(*) FROM training_log")` to assert zero rows.

---

## Files Affected by Phase A Implementation

| File | Task | Change |
|------|------|--------|
| `titan/core/database.py` | A1 | Write methods: cursor inside lock + `_ensure_open_locked()` |
| `titan/main.py` | A2 | Shutdown: explicit join of `_routine_thread` before `db.close()` |
| `titan/orchestration/daily_coach.py` | A3 | `_persist_garmin_data()`: atomic transaction |
| `tests/titan/core/test_database.py` | A1 | 8 new tests (cursor-inside-lock + closed-DB + concurrent) |
| `tests/test_full_lifecycle_stress.py` | A2 | 4 new tests (join ordering + timeout event + guard paths) |
| `tests/titan/orchestration/test_daily_coach.py` | A3 | 5 new tests (atomic commit + rollback simulation) |

---

## Commit Convention

One commit per task:

| Task | Commit message suffix |
|------|-----------------------|
| A1 | `ref ADR-0018-A1` |
| A2 | `ref ADR-0018-A2` |
| A3 | `ref ADR-0018-A3` |

Each commit must include both the production code change **and** its corresponding tests.
A code commit without tests is not accepted (CLAUDE.md Test Creation/Update Rule).

---

## What This ADR Does Not Change

- Governance engine (`GovernanceEngine`, `GovernanceContracts`, `IntensityGovernor`) —
  untouched.
- Science engines (all 26 modules in `titan/science/`) — untouched.
- `titan/orchestration/contracts.py` — Phase B concern only.
- `titan/main.py` composition root pattern — ADR-0017 assessment unchanged.
- `DailyCoach` orchestrator pattern — ADR-0017 assessment unchanged.

---

*Phase A: surgical fixes (v5.8.0). Phase B: pipeline split implemented 2026-03-08 (commit c51e217). No `.py` files modified by this ADR document itself.*
