# TITAN OS — Technical Debt Register & Upgrade Roadmap

**Created:** 2026-03-02
**Source:** Full codebase audit + module-by-module engineering review (v5.8.0)
**Governance:** This document is the authoritative register for known technical debt.
All new findings must be added here. Items must not be "fixed" without a corresponding
issue/PR that references the tier and item number below.

---

## Triage Philosophy

> The same priority framework that governs training governs code: **safety of data
> integrity first, then observability, then everything else.** A silent failure that
> corrupts coaching decisions is more dangerous than a missing feature.

Items are organised into 5 tiers. Work within a tier must be completed before starting
on the next, except where explicitly marked as independent.

**PARTIAL → child item policy (mandatory):** When an item is partially resolved, a child
item must be created immediately to track the remaining scope. The parent item is marked
`PARTIALLY RESOLVED` with explicit scope boundaries. The child item is numbered sequentially
(e.g., T3-06 partial → T3-08 child). This prevents "mostly done" ambiguity and keeps the
register binary per Rule E5. See T3-06/T3-08 and T2-09/T2-11 as canonical examples.

**Phase 7.7 execution sequence (per ADR-0019):** ✅ CLOSED 2026-03-05
```
T1-13 ✅ → T1-14 ✅ → T2-09 ✅, T2-10 ✅, T2-11 ✅, T3-08 ✅
```
All Phase 7.7 items resolved. Phase 7.8 hardening sprint begins.

**Phase 7.8 execution sequence (per ADR-0020 + Architecture Review 2026-03-06):**
```
TIER 1 (data integrity — all before Tier 2):
  T1-15 (first — persistence failure policy; ADR-0020)
  T1-16 (independent — schema version tracking via PRAGMA user_version)
  T1-17 (independent — daily SQLite hot backup)

TIER 2 (observability — after all Tier 1 pass):
  T2-12 (after T1-15 gate passes — UI silent exceptions)
  T2-13 (after T1-15 gate passes — degraded mode duration alerting; independent of T2-12)

TIER 3 (dependency hygiene — after all Tier 2 pass):
  T3-09 (NotificationGateway + file fallback; independent)

TIER 4 (maintainability — after all Tier 3 pass):
  T4-14 (after T2-12 — Garmin worker loop)
  T4-15, T4-16, T4-17 (independent — low blast radius)
  T4-18 (independent — governance mutation test suite; ADR-0021)
  T4-19 (independent — architectural invariant test suite)
  T4-20 (independent — PR template + architecture checklist)
```
T1-16, T1-17, T3-09, T4-18, T4-19, T4-20 are marked `independent`.
T2-13 is independent of T2-12 but depends on T1-15.
Do not start Tier N+1 while any Tier N item is OPEN (Rule E1).

**Phase 7.9 execution sequence (per Risk Matrix Architecture Review 2026-03-06):**
```
TIER 1 (data integrity — must complete before any Tier 2 items in Phase 7.9+):
  T1-18 (physiological input validation contract; ADR-0023)
  T1-19 (structural + temporal data sanity layer; ADR-0026; after T1-18)

TIER 4 (maintainability — independent; can run in parallel after Tier 1–3 close):
  T4-21 (documentation consistency CI checks; ADR-0024)
  T4-22 (agent context continuity + CLAUDE.md integrity; ADR-0025)
  T4-23 (property-based test expansion for science engine edge cases)
  T4-24 (test fixture factory — eliminate fixture drift)
  T4-25 (dependency drift: automated CI audit for unpinned/stale deps)
  T4-26 (module boundary TypedDict contracts + coupling invariant test; ADR-0027)
  T4-27 (complexity budget CI check: module count ceiling; ADR-0028)
  T4-28 (context snapshot generator + multi-agent protocol; ADR-0029)
```
T4-21 through T4-28 are marked `independent`.
Phase 8 is gated — see ADR-0022 (Phase 8 Entry Gate). ADR-0022 G9 requires the
Phase 8 Simplicity Review (ADR-0028) before entry.

---

## TIER 1 — Data Integrity (Non-negotiable; fix before any new feature)

These items directly affect the accuracy of coaching decisions. A silent failure here
means the governance engine operates on corrupt data without knowing it.

### T1-01 · Wrong Telegram library in `requirements.txt` ✅ RESOLVED

**Status (2026-03-04):** Completed. `requirements.txt` uses `pyTelegramBotAPI==4.21.0`
and dependency/import alignment tests are in place. PR: TBD.

**File:** `requirements.txt:16` + `titan/integrations/telegram_bot.py:31`

```
# requirements.txt declares:
python-telegram-bot==21.0.1   # ← python-telegram-bot (PTB)

# Code imports:
import telebot                # ← pyTelegramBotAPI — DIFFERENT package, different API
```

**Impact:** Fresh install produces an `ImportError` on Telegram bot startup. The entire
delivery/control channel fails silently in environments that install from requirements.txt.

**Fix:**
```diff
- python-telegram-bot==21.0.1
+ pyTelegramBotAPI==4.21.0
```

**Effort:** 5 minutes. No logic change.

---

### T1-02 · HRV silent data loss in `garmin_sync.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `sync_hrv()` logs skipped-day errors, increments
`skipped_days`, and emits `hrv_day_skipped` structured events. PR: TBD.

**Location:** `titan/integrations/garmin_sync.py` — `sync_hrv()` inner loop

**Problem:** `except Exception: pass` per HRV day swallows every failure silently.
HRV is the primary input signal for governance gates H2 (hard stop) and readiness scoring.
If days are silently skipped, the governance engine makes decisions on incomplete baselines
without any warning.

**Fix direction:**
- Log every skipped day: `(date, error_class, error_message)`
- Add `skipped_days` counter to the HRV sync result dict (mirrors `skipped_records`
  pattern already used in the activities path)
- Emit a structured `_garmin_event("hrv_day_skipped", ...)` for each failure

**Effort:** ~2h. No architecture change.

---

### T1-03 · Migration observability gap in `database.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `_run_migrations()` now catches only
`sqlite3.OperationalError`, re-raises non-duplicate-column failures, and emits structured
`db_schema_migration` events. PR: TBD.

**Location:** `titan/core/database.py` — `_run_migrations()`

**Problem:** `contextlib.suppress(Exception)` on `ALTER TABLE` statements is correct for
"column already exists" (SQLite raises `OperationalError` in that case), but it also
swallows any *other* failure silently — including schema corruption, disk errors, or
permission issues. You cannot distinguish "already migrated" from "migration silently
failed."

**Fix direction:**
- Catch only `sqlite3.OperationalError` (not bare `Exception`)
- Within that, check if the error message contains "duplicate column name" before
  suppressing; re-raise anything else
- Emit a structured log event on successful migration: `(column_added, table, timestamp)`

**Effort:** ~1h. Surgical change, high safety value.

---

### T1-04 · Hardcoded safety thresholds bypassing `thresholds.py` ✅ RESOLVED

**Status (2026-03-04):** Fixed. `titan/science/volume_load_gauge.py` and
`titan/science/adaptive_priority_lock.py` now import the canonical constants from
`titan/config/thresholds.py` (`HARD_STOP_TSB_FLOOR`, `VO2_ACWR_MAX`) instead of
duplicating literal values.

**Three locations where constants are duplicated instead of imported:**

| File | Line | Hardcoded | Should be |
|---|---|---|---|
| `titan/science/volume_load_gauge.py` | 22 | `<= -50` | `HARD_STOP_TSB_FLOOR` |
| `titan/science/adaptive_priority_lock.py` | 31 | `1.30` (with comment) | `VO2_ACWR_MAX` |
| `titan/science/adaptive_priority_lock.py` | 32 | `-50.0` (with comment) | `HARD_STOP_TSB_FLOOR` |

`adaptive_priority_lock.py` acknowledges the duplication in comments but doesn't import.
If thresholds are tuned (Phase 5 calibration promotion), these values diverge silently.

**Fix:**
```python
# volume_load_gauge.py
from titan.config.thresholds import HARD_STOP_TSB_FLOOR
if tsb_value <= HARD_STOP_TSB_FLOOR:

# adaptive_priority_lock.py
from titan.config.thresholds import HARD_STOP_TSB_FLOOR, VO2_ACWR_MAX
_DEFAULT_THRESHOLDS = {
    'acwr_ceiling': VO2_ACWR_MAX,
    'tsb_floor':    HARD_STOP_TSB_FLOOR,
    ...
}
```

**Effort:** ~30 minutes. Zero behaviour change — values were identical at time of fix.

---

### T1-05 · Dead duplicate ACWR constants in `constants.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `ACWR_SAFE_MIN` and `ACWR_SAFE_MAX` are absent from
`titan/utils/constants.py` and enforced by constants hygiene tests. PR: TBD.

**File:** `titan/utils/constants.py`

`ACWR_SAFE_MIN = 0.8` and `ACWR_SAFE_MAX = 1.3` are defined here and are exact duplicates
of `VO2_ACWR_MIN` / `VO2_ACWR_MAX` in `thresholds.py`. They are never imported anywhere
in production code. They are dead constants that will mislead future developers about
which value is canonical.

**Fix:** Remove `ACWR_SAFE_MIN` and `ACWR_SAFE_MAX` from `constants.py`. Update `CLAUDE.md`
Key Files table (already done in this audit pass).

**Effort:** 10 minutes.

---

### T1-06 · DB concurrency partially synchronized — read paths unguarded + close() race ✅ RESOLVED

**Status (2026-03-04):** Completed. Three lock-guarded `DatabaseManager` methods added:
`get_baseline_rhr(days)`, `get_hrv_history(days)`, `get_weight_history(days)`.
`DailyCoach._get_baseline_rhr()` and `_hydrate_engines_from_db()` now call these methods
instead of directly accessing `self.db.conn.cursor()`. All direct `self.db.conn` accesses
in `daily_coach.py` removed. Tests: 10 green in `tests/test_harden_db_concurrency.py`.
PR: TBD.
**Source:** Engineering audit 2026-03-04 (Critical issue #1)

**Location:** `titan/core/database.py` — `DatabaseManager`

**Problem:** `DatabaseManager` uses a single shared SQLite connection with
`check_same_thread=False` and a `threading.Lock` guarding writes only. Read paths
(e.g., `get_training_load_history()`, `get_governance_decisions()`) are not
lock-guarded. Additionally, `close()` closes the shared connection without
coordinating against in-flight worker threads. Under high activity or at shutdown,
this produces intermittent `sqlite3.ProgrammingError` / race conditions.

**Concrete failure mode:**
- Worker thread calls `get_training_load_history()` (no lock held)
- Shutdown calls `DatabaseManager.close()` (closes the connection)
- Worker thread's cursor operation raises `sqlite3.ProgrammingError: Cannot operate on a closed database`

**Fix direction (option A — minimal, preferred):**
- Extend the existing write lock to cover reads as well (acquire before `cursor.execute`
  on all read methods, release in `finally`)
- Add a `_closed` flag; read paths check flag before acquiring cursor
- `close()` sets `_closed = True` under the lock before calling `connection.close()`

**Fix direction (option B — architectural, see ADR-0017):**
- Move to a writer-thread + queue pattern, or per-thread SQLite connections with
  explicit transaction boundaries (breaks shared-connection model entirely)

**Effort:** Option A: ~3h. Option B: architectural — requires ADR acceptance.

**Note:** Option A is the acceptable short-term fix. Option B is tracked in ADR-0017
as a future architectural improvement. Do not conflate the two.

---

### T1-07 · DailyCoach daemon overlap — `run_morning_routine_async()` unserialised ✅ RESOLVED

**Status (2026-03-04):** Completed. `run_morning_routine_async()` checks
`self._routine_thread.is_alive()` before spawning; emits `routine_skipped_overlap`
structured event with `trigger_source`, `running_since`, `thread_name` when skipped.
`_routine_thread` and `_routine_started_monotonic` are tracked on the instance.
Tests: existing tests green in `tests/titan/orchestration/test_daily_coach.py`.
PR: TBD.
**Source:** Engineering audit 2026-03-04 (Critical issue #2)

**Location:** `titan/orchestration/daily_coach.py` — `run_morning_routine_async()`

**Problem:** `run_morning_routine_async()` spawns a new daemon thread on every call
with no deduplication, serialisation, or job-tracking. If the scheduler retries or a
manual trigger arrives while a routine is already running, two (or more) concurrent
executions of the 12-step morning routine proceed simultaneously. This causes:
- Double Garmin sync (duplicated DB writes)
- Double governance gate evaluation with stale intermediate state
- Double Telegram delivery (athlete receives two morning briefings)
- Inconsistent `DailyCoachContext` state across concurrent runs

**Fix direction:**
- Add a `threading.Event` or `threading.Lock` guard: if a routine is already running,
  log a `routine_already_running` structured event and return early (skip, not queue)
- Track the running thread in `self._routine_thread`; check `is_alive()` before
  spawning a new one
- Emit `routine_skipped_overlap` event with `(trigger_source, running_since)` for
  observability

**Effort:** ~2h. No architecture change; surgical addition of a guard.

---

### T1-08 · Silent hardcoded fallback in `_get_baseline_rhr()` masks data errors ✅ RESOLVED

**Status (2026-03-04):** Completed. `_get_baseline_rhr()` catches only specific exceptions
(`sqlite3.Error`, `TypeError`, `ValueError`, `KeyError`) and returns `None`.
Caller uses `today_rhr` as fallback baseline (delta = 0; conservative) and emits
`baseline_rhr_degraded_mode` structured event. Added Telegram `send_alert()` call in
degraded mode path; alert failure itself is caught and emits
`baseline_rhr_degraded_alert_failed` event. Tests: 2 green in
`tests/test_harden_db_concurrency.py`. PR: TBD.
**Source:** Engineering audit 2026-03-04 (Critical issue #3)

**Location:** `titan/orchestration/daily_coach.py` — `_get_baseline_rhr()`

**Problem:** `_get_baseline_rhr()` wraps all logic in a bare `except Exception: return 50.0`.
If the DB query fails, the schema is wrong, or data is corrupt, the system silently
proceeds with a synthetic RHR baseline of 50.0 bpm. This synthetic value flows into
H3 governance gate (RHR delta hard stop). A real RHR of 70 bpm against a synthetic
baseline of 50 bpm produces a +20 delta — which incorrectly fires the H3 hard stop.
Conversely, a real RHR of 58 bpm against a broken baseline that should have been 60
silently suppresses a legitimate warning.

**Fix direction:**
- Remove the bare `except Exception: return 50.0`
- Catch specific exceptions (`sqlite3.Error`, `TypeError`, `ValueError`, `KeyError`)
- On DB/query failure: emit a structured `baseline_rhr_unavailable` event with
  `(error_class, detail)` and return `None` (or raise)
- Caller must handle `None`: treat as degraded mode → use conservative governance
  outcome (e.g., skip H3 comparison rather than compare against synthetic value), and
  surface the data-integrity incident via Telegram alert

**Effort:** ~2h. Includes caller update and test coverage.

---

### T1-09 · Synthetic weather fallback flows into decision inputs without degraded-mode gate ✅ RESOLVED

**Status (2026-03-04):** COMPLETED. `WeatherAPI` sets `data_quality: "synthetic"` on all
fallback payloads. `OptimalTimeCalculator.calculate_optimal_time()` returns early with
`weather_window_omitted: True` and `weather_data_quality: "synthetic"` when data is
synthetic. `DailyCoach.run_morning_routine()` checks `weather_degraded_mode` flag and
suppresses optimal time / dew point from coaching output, replacing them with the
`⚠️ Weather data unavailable — optimal time window omitted` note. Structured
`weather_degraded_mode_active` event emitted on fallback activation. Tests: existing
tests green. PR: TBD.
**Source:** Engineering audit 2026-03-04 (Critical issue #4)

**Location:** `titan/integrations/weather_api.py` — API failure fallback path

**Problem:** On weather API failure, the integration fabricates current and forecast
data and caches the synthetic values. This fabricated data flows into
`OptimalTimeCalculator` recommendations (dew point, temperature windows). The
orchestration and UI delivery layers receive no signal that the underlying data is
synthetic. An athlete could receive a "run at 07:00, dew point 12°C" recommendation
built entirely on hardcoded fallback data.

**Fix direction:**
- Add a `data_quality: Literal["live", "cached", "synthetic"]` field to the weather
  payload (or a `degraded: bool` flag)
- Set `degraded=True` on synthetic fallback paths
- `OptimalTimeCalculator` must check the flag: if `degraded`, omit weather-window
  recommendation or annotate it explicitly as "weather data unavailable"
- `DailyCoach` must surface degraded weather in Telegram output:
  `⚠️ Weather data unavailable — optimal time window omitted`
- Emit `weather_degraded_mode_active` structured event on fallback activation

**Effort:** ~3h. Requires changes in `weather_api.py`, `optimal_time.py`,
`daily_coach.py`, and test updates.

---

### T1-10 · DB write methods: cursor created outside lock — race window ✅ RESOLVED (2026-03-05, ADR-0018-A1)

**Status (2026-03):** COMPLETED. The 6 write methods originally in scope
(`save_daily_metric`, `save_session`, `save_hrr`, `update_shoe_mileage`, `add_shoe`,
`save_personal_best`) now correctly place cursor creation inside `with self._lock:` with
`_ensure_open_locked()` as the first call. Enforced pattern: lock →
`_ensure_open_locked()` → cursor → execute → commit.
**Note:** 6 additional governance/science write methods carry the same pattern error but
were outside T1-10's original scope. Tracked as **T1-13**.

**Location:** `titan/core/database.py` — `save_daily_metric()`, `save_session()`,
`save_hrr()`, `update_shoe_mileage()`, `add_shoe()`, `save_personal_best()`

**Original problem:** All six write methods created `cursor = self.conn.cursor()` **before**
entering the `with self._lock:` block. This meant cursor creation happened outside the
`_closed` check: if `db.close()` was called by the main thread concurrently, a cursor
could be created against a closed connection. The existing `_ensure_open_locked()` guard
was correctly used by all **read** paths but had never been wired into the write paths.

**Fix direction:**
- Move `cursor = self.conn.cursor()` inside `with self._lock:` for all six write methods.
- Add `self._ensure_open_locked()` as the first call inside the lock block (same pattern
  as read paths: `lock → _ensure_open_locked → cursor → execute → commit`).
- The `training_load` arithmetic calculation in `save_session()` (pure math, no I/O) may
  remain outside the lock.

**Acceptance gate (binary):**
```bash
ruff check titan/core/database.py   # must be zero findings
python -m pytest -q -W error::pytest.PytestWarning   # must be 100% green
```

**Effort:** ~1h. Surgical; no architecture change.
**Tests:** 8 new tests in `tests/titan/core/test_database.py` (see ADR-0018 Test Matrix §A1).
**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/core/test_database.py::test_save_daily_metric_cursor_inside_lock`
- `tests/titan/core/test_database.py::test_save_session_cursor_inside_lock`
- `tests/titan/core/test_database.py::test_write_after_close_raises`
- Invariant: in-scope write methods acquire lock and open-check before cursor creation, and closed-DB writes fail fast with deterministic errors.

**Implementation reference:**
- Commit: `b12517e`
- Branch: `codex/fix-db-cursor-race-in-write-methods`
- PR: [#259](https://github.com/zafiriss-ux/project-mayhem/pull/259)

---

### T1-11 · main.py shutdown: routine thread not joined before db.close() ✅ RESOLVED (2026-03-05, ADR-0018-A2)

**Status (2026-03):** COMPLETED. `main.py` `finally` block now explicitly joins
`DailyCoach._routine_thread` (timeout=30s) before `db.close()`. If the thread is still
alive after join, a structured `worker_shutdown_timeout` event is emitted at ERROR level
with `(worker_name="DailyCoachRoutine", timeout_seconds=30, still_alive=True)`. Follows
the T3-06 escalation pattern.

**Location:** `titan/main.py` — `finally` block of `main()`

**Original problem:** The shutdown sequence was `garmin.stop → weather.stop → telegram.stop →
db.close()` with no explicit `join()` of `DailyCoach._routine_thread` before `db.close()`.
If the morning routine was mid-execution at shutdown time, it would attempt DB operations
against a closed connection, producing a `sqlite3.ProgrammingError`.

**Fix direction:**
- After `telegram.stop_bot()` and before `db.close()`, add:
  ```python
  routine_thread = getattr(daily_coach, '_routine_thread', None)
  if routine_thread is not None and routine_thread.is_alive():
      routine_thread.join(timeout=30)
      if routine_thread.is_alive():
          log.error("worker_shutdown_timeout", extra={
              "worker_name": "DailyCoachRoutine",
              "timeout_seconds": 30,
              "still_alive": True,
          })
  ```
- This follows the T3-06 `worker_shutdown_timeout` event pattern already in use.

**Acceptance gate (binary):**
```bash
ruff check titan/main.py   # must be zero findings
python -m pytest -q -W error::pytest.PytestWarning   # must be 100% green
```

**Effort:** ~1h. Surgical; no architecture change.
**Tests:** 4 new tests in `tests/test_full_lifecycle_stress.py` (see ADR-0018 Test Matrix §A2).
**Closure evidence (pytest nodeids + invariant):**
- `tests/test_full_lifecycle_stress.py::test_shutdown_join_timeout_emits_worker_shutdown_timeout`
- `tests/test_full_lifecycle_stress.py::test_shutdown_sequence_stops_integrations_before_db_close`
- Invariant: shutdown joins the routine worker before DB close and emits escalation when join timeout leaves the routine thread alive.

**Implementation reference:**
- Commit: `48ac724`
- Branch: `codex/update-shutdown-sequence-in-main.py`
- PR: [#260](https://github.com/zafiriss-ux/project-mayhem/pull/260)

---

### T1-12 · `_persist_garmin_data()`: non-atomic persistence — partial commit risk ✅ RESOLVED (2026-03-05, ADR-0018-A3)

**Status (2026-03):** COMPLETED. `_persist_garmin_data()` now wraps the full activity
loop and `save_daily_metric()` in a single `with self.db.transaction():` block. On any
failure the entire day's writes roll back atomically. The invariant holds: after the
method returns, the database contains either all of today's data or none of it.

**Location:** `titan/orchestration/daily_coach.py` — `_persist_garmin_data()`

**Original problem:** The method wrote activities to `training_log` one-by-one with
individual commits, then wrote daily metrics in a separate commit. A crash mid-loop left
the database in a partial day state, silently corrupting the CTL/ATL load baseline used
by the governance engine on startup.

**Fix direction:**
- Wrap the full activity loop + `save_daily_metric()` in a single SQLite transaction.
- If any step fails, roll back all writes for that day.
- Implementation: add a transaction context manager to `DatabaseManager` (e.g.,
  `begin()` / `commit()` / `rollback()` or a `transaction()` context manager), or
  batch all writes in a single `with self._lock:` block with a single `commit()` at
  the end.
- The invariant: after `_persist_garmin_data()` returns, the database contains either
  **all** of today's data or **none** of it. No intermediate state is valid.

**Acceptance gate (binary):**
```bash
ruff check titan/orchestration/daily_coach.py   # must be zero findings
python -m pytest -q -W error::pytest.PytestWarning   # must be 100% green
```

**Effort:** ~3h. Requires DB transaction API extension and orchestration change.
**Dependency:** T1-10 (A1) must be complete first — atomic persistence builds on the
corrected lock pattern in the write methods.
**Tests:** 5 new tests in `tests/titan/orchestration/test_daily_coach.py` (see ADR-0018 Test Matrix §A3).
**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/orchestration/test_daily_coach.py::test_persist_garmin_data_success_commits_activities_and_metrics_atomically`
- `tests/titan/orchestration/test_daily_coach.py::test_persist_garmin_data_failure_mid_loop_rolls_back_entire_day`
- `tests/titan/core/test_database.py::test_transaction_rollback_restores_state`
- Invariant: Garmin persistence is all-or-nothing; mid-transaction failures roll back both activity rows and daily metrics.

**Implementation reference:**
- Commit: `b3aff31`
- Branch: `codex/make-garmin-persistence-atomic`
- PR: [#261](https://github.com/zafiriss-ux/project-mayhem/pull/261)

---

### T1-13 · DB write methods: cursor race in governance/science paths — 6 methods unpatched ✅ RESOLVED

**Status (2026-03):** COMPLETED. All 6 in-scope governance/science write methods now follow
the lock-first write pattern (`with self._lock` → `_ensure_open_locked()` → cursor acquisition
inside lock), closing the close-race window identified in Engineering Audit V3.

**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/core/test_database.py::test_governance_and_science_write_methods_cursor_inside_lock[save_governance_decision-<lambda>]`
- `tests/titan/core/test_database.py::test_in_scope_write_methods_no_cursor_on_close_race[<lambda>3]`
- `tests/titan/core/test_database.py::test_in_scope_write_methods_fail_fast_after_close[<lambda>5]`
- Invariant: governance/science write paths do not create cursors on closed connections and fail
  fast with controlled `RuntimeError` instead of racing into undefined DB state.

**Implementation reference:**
- Commit: `d892ef7`
- Branch: `codex/fix-db-cursor-race-in-write-methods`
- PR: [#264](https://github.com/zafiriss-ux/project-mayhem/pull/264)

**Location:** `titan/core/database.py` — `update_glycogen_debt()`, `log_cs_performance()`,
`log_override()`, `save_governance_decision()`, `update_governance_outcome()`,
`annotate_governance_outcome()`

**Problem:** These 6 write methods were not in the original T1-10 scope but carry the
identical cursor race: `cursor = self.conn.cursor()` is called **before** `with self._lock:`.
If `db.close()` runs concurrently, a cursor is created on a closed connection. The 4
governance-path methods (`save_governance_decision`, `update_governance_outcome`,
`annotate_governance_outcome`, `log_override`) are particularly important because they
are called during governance decision commits — exactly the path that must be race-free.

**Fix direction:**
- Apply the identical pattern established in T1-10 to all 6 methods:
  `with self._lock: → self._ensure_open_locked() → cursor = self.conn.cursor() → execute → commit`
- No architecture change required. Surgical, one method at a time.

**Acceptance gate (binary):**
```bash
ruff check titan/core/database.py   # must be zero findings
python -m pytest -q -W error::pytest.PytestWarning   # must be 100% green
```

**Effort:** ~1h. Identical pattern to T1-10.
**Tests:** Extend `tests/titan/core/test_database.py` — add concurrent-close tests for each
of the 6 methods (mirror the T1-10 test matrix in ADR-0018 §A1).


---

### T1-14 · Garmin activity duplicate persistence — no idempotency key ✅ RESOLVED

**Status (2026-03):** COMPLETED. Garmin activity persistence now uses an idempotency key path
(`garmin_activity_id` + duplicate-safe insert flow), preventing replayed syncs from inflating
`training_log` and downstream CTL/ATL/TSB baselines.

**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/core/test_database.py::test_save_session_ignores_duplicate_garmin_activity_id`
- `tests/titan/core/test_database.py::test_save_session_allows_multiple_manual_rows_with_null_garmin_activity_id`
- `tests/titan/orchestration/test_daily_coach.py::test_persist_garmin_data_duplicate_sync_is_idempotent`
- Invariant: duplicate Garmin activity IDs are ignored while manual (null-ID) sessions remain insertable,
  and replaying the same Garmin payload does not increase persisted activity rows.

**Implementation reference:**
- Commit: `c1a11bb`
- Branch: `codex/add-garmin_activity_id-to-training_log`
- PR: [#266](https://github.com/zafiriss-ux/project-mayhem/pull/266)
**Source:** ADR-0019 (architectural decision for idempotency contract).
**Execution readiness:** READY TO EXECUTE. ADR-0019 is Accepted (2026-03-05) — the
idempotency contract is fully decided (INSERT OR IGNORE, partial unique index, nullable
`garmin_activity_id`). This item is NOT blocked. Prerequisite: T1-13 acceptance gate
must pass first.

**Location:** `titan/core/database.py` — `create_database()`, `save_session()`; and
`titan/orchestration/daily_coach.py` — `_persist_garmin_data()`

**Problem:** `training_log` has no stable external identity column for Garmin-sourced
activities. `save_session()` uses a plain `INSERT`, with no deduplication guard.
Trigger scenarios that produce duplicate rows:
1. Re-run sync over an overlapping date window (e.g., retry after timeout)
2. Manual sync + background sync overlap over the same activity set
3. Crash mid-`_persist_garmin_data()` followed by a full re-sync of that day

**Impact:** Each duplicate inflates `training_load` in `training_log`. Since `get_ctl_atl_tsb()`
and `get_training_load_history()` aggregate all rows for a date, duplicate rows produce
inflated CTL/ATL, deflated TSB (more fatigue counted), and incorrect ACWR. Downstream:
governance gates over-restrict because the system "thinks" the athlete is more loaded than
they are.

**Architect decision (ADR-0019):**
- **Identity key**: `garmin_activity_id TEXT` column on `training_log`. Nullable — manually
  entered sessions have no Garmin ID and must not be blocked.
- **Uniqueness**: `CREATE UNIQUE INDEX ... WHERE garmin_activity_id IS NOT NULL` (partial
  index — enforces uniqueness for Garmin rows only).
- **Upsert strategy**: `INSERT OR IGNORE` — if an activity with the same `garmin_activity_id`
  already exists, silently skip. Do **not** upsert/overwrite existing rows; historical records
  are immutable. A deliberate correction requires a manual operator override path.
- **Migration**: add column + index via `_run_migrations()` using the existing
  `ALTER TABLE IF NOT EXISTS` pattern.

**Fix direction:**
1. Add `_run_migrations()` step: `ALTER TABLE training_log ADD COLUMN garmin_activity_id TEXT`
2. Add partial unique index: `CREATE UNIQUE INDEX IF NOT EXISTS idx_training_log_garmin_id
   ON training_log(garmin_activity_id) WHERE garmin_activity_id IS NOT NULL`
3. Update `save_session()` signature: add optional `garmin_activity_id: str | None = None`
4. Change `INSERT INTO training_log` to `INSERT OR IGNORE INTO training_log` and include
   `garmin_activity_id` in the column list + values
5. Update `_persist_garmin_data()`: pass `garmin_activity_id=act.get('activity_id')` (or
   equivalent Garmin SDK field) to `save_session()`

**Acceptance gate (binary):**
```bash
ruff check titan/core/database.py titan/orchestration/daily_coach.py  # zero findings
python -m pytest -q -W error::pytest.PytestWarning  # 100% green

# Manual idempotency invariant (must be scripted as a test):
# Call _persist_garmin_data() twice with the same activity set.
# training_log row count must be identical after both calls.
# get_ctl_atl_tsb() output must be identical after both calls.
```

**Effort:** ~3h. Schema migration + save_session change + orchestration update + tests.
**Tests:** Add to `tests/titan/core/test_database.py` and `tests/titan/orchestration/`:
- Duplicate Garmin activity: second `save_session()` with same `garmin_activity_id` → row count unchanged
- Null `garmin_activity_id`: two manual sessions insert without conflict
- `get_ctl_atl_tsb()` stability under replay: same output before and after re-sync


---

### T1-15 · `_persist_garmin_data()` fail-open: persistence failure not propagated to governance ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Engineering Audit V4 (2026-03-05) — C2 finding + supplementary analyst review.
**Priority:** P1 (data integrity / traceability gap; safety impact on future baselines).

**Location:** `titan/orchestration/daily_coach.py` — `_persist_garmin_data()` and
`run_morning_routine()` step 2 + `GovernanceEngine` intensity path.

**Problem:**

When `_persist_garmin_data()` catches a transaction failure (DB write fails, transaction
rolls back correctly per T1-12), it:
1. Logs structured events (`ACTIVITY_SKIPPED`, `daily_metrics_persist_failed`) — ✅ good.
2. Returns normally with defaults `(today_rhr=0, today_sleep_score=75, today_sleep_hours=7.5)`.
3. Does NOT signal the failure to its caller.

Consequence: `_run_step(2, ...)` sees a normal return → emits `step_event step_2
outcome="SUCCESS"` — **factually incorrect**. The governance context has no
`persistence_degraded` field. No Telegram alert is sent. The routine runs as if persistence
succeeded, delivering a full prescription with no conservative cap.

**Secondary risk:** On next restart, startup hydration lacks today's activities and daily
metrics. CTL/ATL/TSB baselines undercount today's load — a systematic fatigue undercount.
For a longevity-first system, undercounting fatigue is the more dangerous direction.

**Architect decision (ADR-0020):** Adopt degraded conservative mode (Option B).
- `_persist_garmin_data()` must signal failure via sentinel exception `PersistenceFailure`
  (preferred) or a boolean `persist_ok` return field.
- `run_morning_routine()` catches the signal, sets `persistence_degraded=True` in the
  governance context, sends a Telegram alert, and continues (no abort).
- `GovernanceEngine` applies intensity ceiling (cap at EASY, same as `data_confidence_low`)
  when `persistence_degraded=True`. This is an advisory constraint, not a lock code.
- `DailyCoachContextContract` gains `persistence_degraded: bool` field.
- Step 2 `step_event` must correctly emit `outcome="FAILED"` on persistence failure.

**Fix direction:**
1. Add sentinel `class PersistenceFailure(Exception): ...` in `daily_coach.py`.
2. In `_persist_garmin_data()`: outer except now catches, logs, then re-raises
   `PersistenceFailure(today_rhr, today_sleep_score, today_sleep_hours)` — structured
   data is preserved for the caller even in the failure path.
3. In `run_morning_routine()`: catch `PersistenceFailure` from step 2 call, extract
   the values, set `persistence_degraded = True`, send Telegram alert.
4. Add `persistence_degraded` to `GovernanceContext` construction (alongside
   `data_confidence_low`).
5. In `GovernanceEngine`: add `persistence_degraded` check in intensity ceiling path.

**Acceptance gate (binary):**
```bash
ruff check titan/orchestration/daily_coach.py titan/science/governance_engine.py
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
python -m pytest -q                                    # 100% green, count ≥ previous
```

**Tests required (4 minimum):**
- `test_persist_garmin_data_rollback_raises_persistence_failure_with_defaults` — mock
  transaction to raise; assert `PersistenceFailure` raised with correct default values;
  assert `PERSIST_ERROR` step event emitted (not SUCCESS).
- `test_run_morning_routine_persistence_failure_sets_degraded_flag` — mock step 2 to
  fail; assert `persistence_degraded=True` in governance context.
- `test_governance_engine_persistence_degraded_caps_intensity_at_easy` — assert EASY
  ceiling when `persistence_degraded=True`.
- `test_run_morning_routine_persistence_failure_sends_telegram_alert` — assert alert.

**Effort:** ~4h. Moderate complexity — touches DailyCoach orchestration, GovernanceEngine,
and contract type.

---

### T1-16 · Schema version tracking absent — `_run_migrations()` uses ad-hoc suppression ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Architecture Review 2026-03-06.
**Priority:** P1 (data integrity — any schema change without versioning silently breaks existing DBs).

**Location:** `titan/core/database.py` — `_run_migrations()`

**Problem:**

`_run_migrations()` uses `sqlite3.OperationalError` suppression to detect "column already
exists" (T1-03 fixed the bare `except Exception` form). However, there is no schema version
tracking — the system cannot distinguish between "DB is current", "DB is from an older
schema", or "DB schema is corrupted". Any future `ALTER TABLE` or new table addition runs
blindly against an unknown baseline. SQLite's `PRAGMA user_version` is the native,
zero-dependency solution.

**Fix direction:**

1. Define `SCHEMA_VERSION: int` constant at module level in `database.py`. Increment for
   every future migration.
2. In `_run_migrations()`:
   - Read `PRAGMA user_version` on startup.
   - Run only migrations with version > `user_version`.
   - After all migrations apply, write `PRAGMA user_version = SCHEMA_VERSION`.
3. Migrations become an ordered dict: `{version: sql_statement}`.
4. Replace ad-hoc `OperationalError` suppression with version-gated execution — "already
   applied" is determined by version number, not error swallowing.

**Acceptance gate (binary):**
```bash
ruff check titan/core/database.py
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
python -m pytest -q                                    # 100% green, count ≥ previous
```

**Tests required (2 minimum):**
- `test_schema_migration_applies_once_on_fresh_db` — new DB: assert `user_version` equals
  `SCHEMA_VERSION` after init.
- `test_schema_migration_idempotent` — run `_run_migrations()` twice; assert no error and
  `user_version` unchanged on second run.

**Effort:** ~2h. Surgical — confined to `database.py::_run_migrations()`.

---

### T1-17 · No backup/recovery policy — single SQLite file = complete data loss on disk failure ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Architecture Review 2026-03-06.
**Priority:** P1 (data integrity — single-athlete training history has no recovery path).

**Location:** `titan/core/database.py` — `DatabaseManager`

**Problem:**

`titan.db` is a single SQLite file with no backup strategy. A disk event, accidental
deletion, or filesystem corruption means complete loss of the athlete's training history —
including CTL/ATL baselines, HRV trends, governance outcomes, and personal bests. There is
no recovery path.

**Fix direction:**

1. Add `_backup_database()` method to `DatabaseManager` using `sqlite3.Connection.backup()`.
   This API is a hot backup — safe while the DB is open, no lock required.
2. Backup destination: `~/Documents/TITAN/backups/titan_YYYY-MM-DD.db` (one file per day).
3. Trigger: call `_backup_database()` once per morning routine, after successful persistence.
   Skip if today's backup already exists.
4. Retention: keep last 30 daily backups; prune older files in the same call.
5. Weekly JSON export: after daily backup, export `daily_metrics` + `training_log` rows
   as `~/Documents/TITAN/backups/titan_export_YYYY-MM-DD.json`. Human-readable; schema-
   independent; recoverable even if schema version changes.
6. Document backup policy in `DEPLOYMENT_GUIDE.md`: "Last 30 daily backups + weekly JSON
   export. SLA: recovery to yesterday's state on disk failure."

**Acceptance gate (binary):**
```bash
ruff check titan/core/database.py
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
python -m pytest -q                                    # 100% green, count ≥ previous
```

**Tests required (3 minimum):**
- `test_backup_creates_file_in_backup_dir` — mock filesystem; assert backup file created.
- `test_backup_idempotent_same_day` — call twice same day; assert one file, no error.
- `test_backup_prunes_old_files` — pre-populate 35 dated files; assert only 30 remain after
  backup call.

**Effort:** ~3h. Confined to `DatabaseManager` + one call site in `daily_coach.py`.

---

## TIER 2 — Observability Infrastructure (Sprint 2)

Complete Tier 1 first. These items do not corrupt data but make production incidents
significantly harder to diagnose.

**Rule:** Work one subsystem at a time. Do not attempt to fix all broad `except` handlers
simultaneously — each subsystem needs its own error taxonomy review and test update.

### T1-18 · No physiological bounds validation — impossible sensor values flow into governance gates 🔴 OPEN

**Status:** OPEN (Phase 7.9).
**Source:** Master Risk Matrix — Risk #9 (Physiological Edge-Case Fragility). Architecture Review 2026-03-06. ADR-0023.
**Priority:** P1 (Tier 1 — safety critical). Data integrity.

**Location:** `titan/science/` (new module) + `titan/core/database.py` (`get_daily_metrics`, `get_training_load_history`).

**Problem:**

Science engines receive values sourced from Garmin sync → SQLite → engine hydration with
no systematic bounds check. Three known failure modes:

1. `hrv_ms = 0` (sensor failure) → `baseline_hrv = 0` → HRV delta = 0 → H2 gate
   silently disabled.
2. `rhr_bpm = 200+` (optical sensor artefact) → corrupts readiness score.
3. `ctl = 0` (new athlete) → `acwr = atl / 0` → NaN/Inf flows into `VolumeLoadGauge`.

**Fix direction:**

Create `titan/science/physiological_bounds.py` with `BOUNDS` dict and
`validate_and_clamp(data, context)` function per ADR-0023.
Integrate into `DatabaseManager.get_daily_metrics()` and
`get_training_load_history()` at the return point.
Add `tests/test_physiological_bounds.py`.

**Acceptance gate (binary):**
```bash
ruff check titan/science/physiological_bounds.py titan/core/database.py \
            tests/test_physiological_bounds.py
python -m pytest tests/test_physiological_bounds.py -v   # all green
python -m pytest -q -W error::pytest.PytestWarning        # 100% green
python -m pytest -q                                        # count ≥ previous
```

**Effort:** ~3h. New module + DB integration + tests.

---

### T1-19 · No structural/temporal data sanity validation — cross-field anomalies enter DB silently 🔴 OPEN

**Status:** OPEN (Phase 7.9 — after T1-18).
**Source:** Master Risk Matrix — Risk #10 (Input Data Sanity). Architecture Review 2026-03-06. ADR-0026.
**Priority:** P1 (Tier 1 — data integrity).

**Location:** `titan/science/` (new module) + `titan/integrations/garmin_sync.py` + `titan/orchestration/daily_coach.py` + `titan/core/database.py` (migrations).

**Problem:**

Structurally corrupt Garmin data (e.g., `max_hr < avg_hr`, future timestamps, activities
with `distance_km = 0` and `duration_seconds = 3600`) is written to the database without
validation. Stale data (last sync >72h ago) is used as current without a freshness flag.
SQLite columns `date`, `garmin_id`, `timestamp` are nullable — NULL values cause silent
failures downstream.

**Fix direction (three layers per ADR-0026):**

1. Create `titan/science/data_sanity.py` (`DataSanityChecker` class with
   `check_activity`, `check_daily_metrics`, `check_hrv`).
2. Integrate into `garmin_sync.py` before each DB write call.
3. Add temporal freshness check to `DailyCoach` Step 1 (emit `data_confidence_low`
   when last sync > `STALE_DATA_HARD_CEILING_HOURS`).
4. Add NOT NULL migration for mandatory columns via `_run_migrations()`.
5. Add `tests/test_data_sanity.py`.

**Acceptance gate (binary):**
```bash
ruff check titan/science/data_sanity.py titan/integrations/garmin_sync.py \
            titan/orchestration/daily_coach.py titan/core/database.py \
            tests/test_data_sanity.py
python -m pytest tests/test_data_sanity.py -v   # all green
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~4h. New module + 3-point integration + migration + tests.

---

### T2-01 · Error taxonomy: `garmin_sync.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `sync_activities`, `sync_weight`, `sync_sleep`, and
`sync_hrv` route failures to Garmin failure-class constants and emit machine-readable
`_garmin_event(<failure_class>, ...)` structured events. PR: TBD.

**Original state (pre-fix):** Most failures resulted in `print()` + broad `except Exception`.
Could not distinguish `auth_failed` / `rate_limited` / `payload_malformed` / `timeout` /
`api_unavailable` from log output alone.

**Fix direction:**
- Define failure classes as constants: `GARMIN_AUTH_FAIL`, `GARMIN_RATE_LIMIT`,
  `GARMIN_PAYLOAD_MALFORMED`, `GARMIN_TIMEOUT`, `GARMIN_API_UNAVAILABLE`
- Route every `except` to the appropriate class + emit `_garmin_event(failure_class, ...)`
- User-facing messages can remain friendly; structured log line must be machine-readable

**Subsystem coverage:** `sync_activities`, `sync_weight`, `sync_sleep`, `sync_hrv`

---

### T2-02 · Error taxonomy: `daily_coach.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `DailyCoach.run_morning_routine()` now emits
step-level structured `step_event` logs with `(step_number, step_name, outcome,
failure_class)` and routes failures to `DATA_MISSING` / `ENGINE_ERROR` /
`PERSIST_ERROR` / `DELIVERY_ERROR`. Persist path emits per-activity
`ACTIVITY_PERSISTED` / `ACTIVITY_SKIPPED` plus daily metrics persist outcomes.
Completed: 2026-03-04
PR: TBD

**Original state (pre-fix):** `DailyCoach._run_morning_routine()` had multiple broad catch + print
patterns across the 12 steps. Step-level failures were not distinguishable in logs.

**Fix direction:**
- Step-level structured events: `(step_number, step_name, outcome, failure_class)`
- Failure classes: `DATA_MISSING`, `ENGINE_ERROR`, `PERSIST_ERROR`, `DELIVERY_ERROR`
- Persist path should emit `ACTIVITY_PERSISTED` / `ACTIVITY_SKIPPED` per activity

---

### T2-03 · Error taxonomy: `telegram_bot.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. Init/send/poll/scheduler failure paths now emit
machine-readable `_telegram_event("failure", ...)` events with standardized failure
classes (`SEND_FAIL`, `POLL_FAIL`, `SCHEDULER_DRIFT`, `CALLBACK_ERROR`) in all failure
branches, including console fallback and poller-unavailable startup paths.
Completed: 2026-03-04
PR: TBD

---

### T2-04 · Error taxonomy: `governance_engine.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `check_override_lockdown()` now classifies
failure paths as `DB_READ_ERROR` / `COMPUTATION_ERROR` / `SCHEMA_MISMATCH`, fails
safe with lockdown active, and emits structured failure fields for observability.
Completed: 2026-03-04
PR: TBD

---

### T2-05 · JSON guard for DB governance rows in `database.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `get_governance_decisions()` now routes
governance JSON decode through `_safe_json()` with fallback semantics, and malformed
payloads emit structured `governance_row_json_malformed` warning events that include
the source column and a capped raw preview. Tests cover valid parsing and malformed
fallback behavior. Completed: 2026-03-04
PR: TBD

**Location:** `titan/core/database.py` — `get_governance_decisions()`

`json.loads()` was called directly on `locks_applied_json` and similar columns without a
fallback. A single malformed row (manual DB edit, schema migration edge case, legacy data)
would raise and abort the entire read, losing all governance history access.

**Fix direction:**
```python
def _safe_json(raw: str, fallback=None):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log.warning("governance_row_json_malformed", raw=raw[:120])
        return fallback
```

---

### T2-06 · Athlete load error detail in `database.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `AthleteDatabase.load_all()` now emits
structured `athlete_file_skipped` warning events that include `filename`,
`error_class`, `error_message`, and best-effort `field_hint` for each skipped
corrupted athlete file while preserving best-effort load semantics.
Completed: 2026-03-04
PR: TBD

**Location:** `titan/core/database.py` or `AthleteDatabase.load_all()`

Broad `except` on file load silently skipped corrupted athlete files with a warning.
Field-level reason was not captured, making forensic diagnosis of partial corruption
impossible.

**Fix direction:** Log `(filename, error_class, error_message, field_hint)` per skip.

---

### T2-07 · Launcher and startup error path observability ✅ RESOLVED

**Status (2026-03-04):** Completed. Startup/init failure paths now emit structured `startup_failure` events with stable `component`, `error_class`, and `detail` fields while preserving friendly console messages where applicable.
Completed: 2026-03-04
PR: TBD

**Location:** `main.py`, `titan/main.py`, integration init paths (`titan/integrations/garmin_sync.py` `connect()`, `titan/integrations/telegram_bot.py` `__init__()`)

**Original state (pre-fix):** Launch-time errors in the startup guard and integration init paths emitted `print()` rather than structured log events. Startup failures were indistinguishable from runtime failures in aggregated log output, degrading incident RCA accuracy.

**Fix direction:**
- Replace `print(f"Error: ...")` in startup/init paths with `log.error("startup_failure", component=..., error_class=..., detail=...)`
- Applies to: `main.py` startup guard, `GarminSync.connect()` auth failure path, `TitanTelegramBot.__init__()` token validation failure
- User-facing friendly messages may remain; each must be paired with a machine-readable structured event

**Effort:** ~2h. Surgical; no architecture change.

---

### T2-08 · Residual broad catches in DB best-effort branches ✅ RESOLVED

**Status (2026-03-04):** Completed. All `except Exception` and bare `except` clauses
in `database.py` outside `_run_migrations()` have been narrowed to minimal specific
types and each surviving catch emits a structured `_database_event` warning. Audit
results:

- `_safe_json()` → `except (json.JSONDecodeError, TypeError)` — emits `governance_row_json_malformed`
- `DatabaseManager.__init__()` launcher import → `except ModuleNotFoundError` (further guarded by `error.name`) — emits `db_init_data_directory_fallback`
- `DatabaseManager.__init__()` logging PRAGMAs → `except (OSError, ValueError)` — emits `db_init_logging_skipped`
- `AthleteDatabase.__init__()` path resolution → `except TypeError` — emits `athlete_db_base_directory_fallback`
- `AthleteDatabase.load_all()` → `except (OSError, TypeError, ValueError, json.JSONDecodeError)` — emits `athlete_file_skipped`

At closure (2026-03-04): no broad catches remained; 1206 tests green (historical snapshot — not a live reading).
Completed: 2026-03-04
PR: TBD

**Location:** `titan/core/database.py` — init and non-migration best-effort paths

**Original state:** Additional broad `except Exception` clauses existed in DB init
and best-effort load paths, silently absorbing failure classes beyond their intended
idempotency guard.

**Fix direction:**
- Audit all `except Exception` / bare `except` clauses in `database.py` outside of `_run_migrations()` (already scoped in T1-03)
- Narrow each to the minimal expected exception type
- Emit a structured log event for any catch that survives narrowing
- Conservative default: when uncertain, emit a warning and re-raise

---

### T2-09 · Residual `print()` operational/error paths across integration modules ✅ RESOLVED

**Status (2026-03):** COMPLETED. Operational print paths in `daily_coach.py`,
`telegram_bot.py`, and `main.py` were replaced by structured event/log calls; remaining
`print()` usage is limited to UI/CLI boundary output and documentation examples.

**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/orchestration/test_daily_coach.py::test_run_morning_routine_happy_path_emits_step_success`
- `tests/titan/integrations/test_telegram_bot_observability.py::test_telegram_bot_has_no_print_calls`
- `tests/test_main_smoke.py::test_main_emits_shutdown_logs_on_keyboard_interrupt`
- Invariant: integration/orchestration operational paths now emit structured events instead of
  unstructured `print()` side channels.

**Implementation reference:**
- Commits: `56b6d60`, `e44a7bc`, `9a7f7dc`
- Branches: `codex/remove-operational-print-calls-from-telegram_bot.py`, `codex/remove-operational-print-calls-from-daily_coach.py`, `codex/replace-operational-print-statements-in-main.py`
- PRs: [#267](https://github.com/zafiriss-ux/project-mayhem/pull/267), [#268](https://github.com/zafiriss-ux/project-mayhem/pull/268), [#269](https://github.com/zafiriss-ux/project-mayhem/pull/269)

**Fix direction:** Replace each remaining operational `print()` with the module's structured
event emitter (`_telegram_event`, `_coach_event`, or `log.*`). Execute one module at a time
per Rule E2. Add `test_<module>_has_no_print_calls` assertion for each completed module.

**Acceptance gate per module (binary):**
```bash
ruff check <module_path>   # zero findings
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
# rg -n "print\(" titan/<path>/<module>.py   # zero matches
```

**Effort:** ~2h per module; 3 remaining modules = ~6h total.
**Source:** Engineering audit 2026-03-04 (Medium risk #1)

**Location:** `titan/integrations/telegram_bot.py`, `titan/integrations/garmin_sync.py`,
`titan/integrations/weather_api.py`, `titan/orchestration/daily_coach.py`

**Problem:** Despite T2-01 through T2-08 fixing the most critical error taxonomy paths,
the audit confirms that operational status and error messages are still emitted via
`print()` in several paths across the above modules. In service environments, `print()`
output is not machine-parsable, is not captured by structured log aggregators, and does
not contribute to alertability. This weakens incident RCA consistency relative to the
modules already migrated to structured events.

**Scope:** Operational/error `print()` calls only. User-facing console prints at UI
boundaries are intentional and must be preserved.

**Fix direction:**
- Audit each module for `print(` calls in non-UI paths
- Replace each with the module's existing structured event emitter
  (`_garmin_event`, `_telegram_event`, `_weather_event`, `_coach_event`)
- User-facing messages (menu text, Telegram output) remain as-is
- Run `python -m pytest -q` after each module to confirm 100% green

**Effort:** ~2h per module; 4 modules = ~8h total. Execute one module at a time
following Rule E2 subsystem sequence.

---

### T2-10 · Startup engine hydration has no data-confidence gate ✅ RESOLVED

**Status (2026-03):** COMPLETED. Startup hydration now tracks per-engine confidence and
propagates low-confidence state into the first governance context after startup.

**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/orchestration/test_daily_coach.py::test_hydrate_engines_from_db_cold_start_emits_low_confidence_warning`
- `tests/titan/orchestration/test_daily_coach.py::test_hydrate_engines_from_db_full_hydration_no_low_confidence_warning`
- `tests/titan/orchestration/test_daily_coach.py::test_run_morning_routine_passes_data_confidence_low_only_on_first_routine`
- Invariant: low-hydration startup state is surfaced explicitly and only the first post-startup
  routine carries `data_confidence_low` into governance for conservative capping.

**Implementation reference:**
- Commit: `c632844`
- Branch: `codex/implement-startup-hydration-confidence-gate`
- PR: [#271](https://github.com/zafiriss-ux/project-mayhem/pull/271)
**Priority:** P1. This is a semantic safety gap — governance makes decisions after restart
without knowing whether its input engines have valid baselines.
**Architect decision:** MADE. ADR-0019 Decision 5 is the authoritative contract for this
item. The conservative-mode intensity ceiling (cap at EASY when `data_confidence_low=True`)
is explicitly classified as an advisory downgrade — not a hard stop, not a lock code. The
3/5 threshold, `GovernanceContext.data_confidence_low` field, and single-routine scope are
all decided. No new ADR is required. This is an engineering execution task.

**Location:** `titan/orchestration/daily_coach.py` — `_hydrate_engines_from_db()` and
`run_morning_routine()` (governance context construction)

**Problem:** `_hydrate_engines_from_db()` runs synchronously at startup, loading HRV
history, weight history, training load, HRR, and CS performance data from the DB into
in-memory engine state. Each hydration call is wrapped in `except Exception: print(...)`,
which means failures are swallowed silently. Critically, **there is no flag passed
downstream** to indicate whether hydration succeeded.

Consequence: after a cold start (empty DB), crash, or schema migration, the governance
engine begins operating on zero-history baselines. It does not know this. The first N
governance decisions are made with the same confidence as normal operation, but with
empty or partial input data. For a safety-first longevity system, this is a semantic
correctness gap — the system should know it is operating on thin ice.

**Architect decision (ADR-0019):**
- Add `_startup_hydration_confidence: dict[str, bool]` to `DailyCoach.__init__()`.
  Keys: one per engine hydration attempt (`"hrv"`, `"weight"`, `"load"`, `"hrr"`, `"cs"`).
  Values: `True` if hydration loaded ≥1 data point; `False` if empty or exception.
- Emit a structured `startup_hydration_report` event listing which engines hydrated
  successfully.
- If fewer than 3 of 5 engines hydrated: emit `startup_low_confidence` event at WARNING
  level. This is the **conservative-mode trigger**.
- Pass `data_confidence_low: bool` into `GovernanceContext` for the first morning routine
  after startup. The governance engine, if it receives `data_confidence_low=True`, applies
  a conservative-mode ceiling: cap intensity recommendation at EASY (do not prescribe
  VO2max or tempo without a data baseline). This is **not** a hard stop — it is a
  precautionary downgrade consistent with the system's longevity-first philosophy.

**Fix direction:**
1. In `_hydrate_engines_from_db()`, return a `dict[str, bool]` confidence report instead
   of `None`. Track success/failure per engine with explicit boolean.
2. Store as `self._startup_hydration_confidence`.
3. Emit `startup_hydration_report` structured event with confidence dict.
4. In `run_morning_routine()`, pass `data_confidence_low` to the governance context if
   `_startup_hydration_confidence` indicates fewer than 3/5 engines hydrated.
5. In `GovernanceEngine`, handle `data_confidence_low=True` in the intensity ceiling
   (advisory, not hard-stop).

**Acceptance gate (binary):**
```bash
ruff check titan/orchestration/daily_coach.py titan/science/governance_engine.py  # zero findings
python -m pytest -q -W error::pytest.PytestWarning  # 100% green
# Test: cold start (empty DB) → startup_low_confidence event emitted
# Test: partial hydration (3/5 engines loaded) → data_confidence_low=True in context
# Test: full hydration (5/5) → data_confidence_low=False, no conservative mode
```

**Effort:** ~4h. Moderate complexity — touches DailyCoach init, governance context, and
GovernanceEngine.
**Tests:** Add to `tests/titan/orchestration/test_daily_coach.py` and
`tests/test_governance_integration.py`:
- cold start → confidence report shows all False → low-confidence event
- full hydration → confidence all True → no conservative mode
- governance conservative-mode: intensity ceiling applied under low confidence


---

### T2-11 · Telegram fallback logs message content — privacy/confidentiality risk ✅ RESOLVED

**Status (2026-03):** COMPLETED. Telegram fallback delivery logs are metadata-only and no
longer include message content previews.

**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/integrations/test_telegram_bot_observability.py::test_send_message_fallback_logs_metadata_without_message_content`
- `tests/titan/integrations/test_telegram_bot_observability.py::test_send_message_without_bot_emits_send_fail_event`
- Invariant: fallback delivery emits observability metadata (length/mode/reason) without
  leaking coaching payload text or previews.

**Implementation reference:**
- Commit: `96084d6`
- Branch: `codex/fix-telegram-fallback-log-leak`
- PR: [#270](https://github.com/zafiriss-ux/project-mayhem/pull/270)
**Priority:** P1. Coaching and health data (HRV, TSB, session recommendations) must not
appear in console/stdout logs in shared or containerised environments.

**Location:** `titan/integrations/telegram_bot.py` — `send_message()` fallback path

**Problem:** When the Telegram bot is unavailable (missing token, library not installed,
or temporary connectivity failure), the fallback currently prints:
```python
print(f"📱 [Telegram] {text[:200]}")
```
This truncates but still exposes up to 200 characters of coaching message content —
which may include HRV values, fatigue scores, session prescriptions, or other personal
health data — to stdout. In shared or containerised log environments, this constitutes a
confidentiality/privacy violation.

**Architect decision (ADR-0019):**
- Replace the content-preview fallback with a metadata-only structured event.
- Emit: `_telegram_event("fallback_send", subsystem="send_message",
  message_length=len(text), bot_available=False)` — no content, no preview.
- The event must carry zero coaching or health content.

**Fix direction:**
- Locate the `print(f"📱 [Telegram] {text[:200]}")` fallback in `send_message()`.
- Replace with `_telegram_event("fallback_send", level="warning",
  subsystem="send_message", message_length=len(text), bot_available=False)`.
- Remove the `text[:200]` slice entirely.
- Add test: `test_send_message_fallback_emits_no_content` — mock bot unavailable,
  call `send_message("sensitive data")`, assert no content in emitted event payload.

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/telegram_bot.py  # zero findings
python -m pytest -q -W error::pytest.PytestWarning  # 100% green
# Test: fallback path → zero content in structured event payload
```

**Effort:** ~1h. Surgical change; single location.
**Tests:** Add to `tests/test_telegram_bot.py`:
- fallback_send event payload contains `message_length` key but no `text`, `content`,
  `preview`, or message body


---

### T2-12 · UI path silent `except Exception: pass` — zero observability on shoe display and time parse ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Engineering Audit V4 (2026-03-05) — M2 finding.
**Priority:** P2. No safety impact (UI display only), but silent failures prevent diagnosis
of corrupted equipment data or malformed optimal-time responses.

**Location:** `titan/ui/menu_system.py` — two locations:
1. Line ~213: `except Exception:` with silent default fallback when parsing optimal time
   string (`opt_time_str.split(":")`). Swallows any `ValueError`/`AttributeError` and
   defaults to `(run_h=7, run_m=0)`.
2. Line ~473: `except Exception: pass` — silently swallows all errors when iterating
   and displaying shoe/equipment data. If `EquipmentManager` throws or shoe data is
   malformed, the UI renders nothing with zero indication.

**Problem:** Both are in `titan/ui/` — where `print()` is permitted per ADR-0019 Decision 3.
But silent absorption (`pass` or implicit fallback) without any log or display hint violates
the system's observability contract. The user sees missing shoe data with no explanation.
In a bug scenario, these silent catches make RCA impossible.

**Fix direction:**
- Location 1 (time parse): narrow to `except (ValueError, AttributeError):`, emit a
  `log.warning("optimal_time_parse_fallback", raw=opt_time_str)` and print a UI hint:
  `print("  (time format unavailable — defaulting to 07:00)")`.
- Location 2 (shoe display): narrow to `except (TypeError, KeyError, AttributeError):`,
  print `"  (equipment data unavailable)"` to the UI and emit a structured
  `log.warning("shoe_display_error", ...)`. Do NOT use bare `pass`.

**Acceptance gate (binary):**
```bash
ruff check titan/ui/menu_system.py   # zero findings
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
# rg -n "except Exception:\s*$\|except Exception: pass" titan/ui/menu_system.py → zero matches
```

**Tests required:**
- `test_menu_system_shoe_display_handles_malformed_data_gracefully` — inject malformed
  shoe data; assert UI output does not raise and shows fallback message (not silent).
- `test_menu_system_optimal_time_parse_fallback_emits_warning` — inject malformed time
  string; assert warning logged and default time used.

**Effort:** ~2h. Surgical; two locations in one file.

---

### T2-13 · Degraded mode duration not tracked — no alerting for prolonged degraded state ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Architecture Review 2026-03-06.
**Priority:** P2 (observability gap — system can run degraded for days without active alert).

**Location:** `titan/orchestration/daily_coach.py` + `titan/ui/operator_console.py`

**Problem:**

When the system enters degraded mode (Garmin fail, persistence fail, weather fail, low
startup confidence), it logs a structured event and may send a Telegram alert at the moment
of failure. However, it does not track *how long* it has been degraded. If the failure
persists across multiple morning routines (e.g., Garmin credentials expired, connectivity
outage), subsequent routines run silently in degraded mode — no repeated alert, no duration
signal, no SLO violation fired.

The athlete may go days without knowing their coaching prescriptions are in conservative
mode due to stale data.

**Fix direction:**

1. Add `_DegradedModeTracker` to `titan/orchestration/daily_coach.py` (internal dataclass
   or simple dict keyed by failure type with `degraded_since: datetime | None`).
2. On each morning routine: for each degraded flag (`persistence_degraded`,
   `data_confidence_low`, `weather_degraded`), set `degraded_since` if not already set.
   Clear `degraded_since` when the condition resolves.
3. SLO threshold: if any `degraded_since` is older than 24 hours, send a Telegram critical
   alert: `"⚠️ TITAN degraded for >{N}h — [failure_type] unresolved. Check credentials/connectivity."`
4. `OperatorConsoleService` dashboard payload gains `degraded_since: dict[str, str | None]`
   field — ISO 8601 timestamps per failure type, `null` when healthy.

**Acceptance gate (binary):**
```bash
ruff check titan/orchestration/daily_coach.py titan/ui/operator_console.py
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
python -m pytest -q                                    # 100% green, count ≥ previous
```

**Tests required (3 minimum):**
- `test_degraded_tracker_sets_timestamp_on_first_failure` — assert `degraded_since` set.
- `test_degraded_tracker_clears_on_recovery` — assert `degraded_since` cleared when flag
  resolves.
- `test_degraded_tracker_fires_alert_after_24h` — mock `degraded_since` to >24h ago;
  assert Telegram alert emitted.

**Effort:** ~3h. Touches orchestration + operator console payload.

---

## TIER 3 — Dependency Hygiene (Sprint 3)

Independent of Tier 2. Can be done in parallel once Tier 1 is complete.

### T3-02 · Add `ruff` and `mypy` to dev requirements ✅ RESOLVED

**Status (2026-03-04):** Completed. `requirements-dev.txt` contains `ruff>=0.3.0`
and `mypy>=1.9.0`, matching the `[tool.ruff]` and `[tool.mypy]` configs in
`pyproject.toml`. Reproducible dev environments are now fully supported.

---

### T3-03 · Secrets handling simplification in `garmin_sync.py` + `telegram_bot.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. Both files use a single `_CredentialSecret`
wrapper (backed by `_Secret`) as the one canonical representation per credential.
No plain-string aliases or duplicate wrappers remain. Logging of sensitive values
through the wrong representation is no longer possible.

---

### T3-04 · Threading lifecycle: use `threading.Event` for clean stop ✅ RESOLVED

**Status (2026-03-04):** Completed. Both `garmin_sync.py` and `telegram_bot.py`
background workers use `threading.Event` exclusively (`_stop_event.wait()` /
`_stop_event.is_set()`). The redundant boolean stop flags (`_stop_sync`, `_stop`)
have been removed. `stop_background_sync()` and `stop_bot()` call
`self._stop_event.set()` and join the thread with `timeout=5`. Tests updated.

---

### T3-05 · Threading lifecycle: weather updater `Event.wait()` pattern ✅ RESOLVED

**Status (2026-03-04):** Completed. `weather_api.py` `_background_update_worker`
uses `self._stop_event.wait(timeout=interval_seconds)` and checks
`self._stop_event.is_set()`. The redundant `_stop_update` boolean flag has been
removed from `__init__`, `start_background_updates`, and `stop_background_updates`.
Test fixtures updated. Shutdown behaviour is now consistent across all three
background workers.

---

### T3-06 · Background worker shutdown uses fixed `join(timeout=5)` without escalation ✅ RESOLVED

**Status (2026-03-04):** RESOLVED for `titan/integrations/garmin_sync.py`. Escalation
after `join(timeout=5)` is implemented and tested: if the worker is still alive, it emits a
structured `worker_shutdown_timeout` event at ERROR level with `(worker_name,
timeout_seconds, still_alive=true)`, with no forced termination.

**Status (2026-03):** Child item T3-08 has been completed; Weather and Telegram stop paths now include the same post-join alive escalation pattern, so this parent item is fully closed.
**Source:** Engineering audit 2026-03-04 (Medium risk #2)

**Location:** `titan/integrations/garmin_sync.py`, `titan/integrations/telegram_bot.py`,
`titan/integrations/weather_api.py` — stop/join paths

**Problem:** All three background workers call `thread.join(timeout=5)` and continue
execution regardless of whether the thread actually stopped. Non-terminated threads are
not escalated, flagged, or reported as a shutdown failure. A hung thread (e.g., blocked
on a network call or a lock) silently survives the shutdown sequence. This hides
hung-thread incidents and can leave the process zombie-running with active DB cursors.

**Fix direction:**
- After `join(timeout=5)`, check `thread.is_alive()`
- If still alive: emit a `worker_shutdown_timeout` structured event with
  `(worker_name, timeout_seconds, still_alive=True)`
- Escalation path: log at ERROR level; in future, integrate with lifecycle supervisor
  (see ADR-0017 for supervisor architecture)
- Do not forcibly kill threads (Python has no safe mechanism); document the
  escalation-only approach

**Effort:** ~1h per worker; 3 workers = ~3h total.

---

### T3-07 · `scheduled_tasks` list mutable and unsynchronized across execution contexts ✅ RESOLVED

**Status (2026-03-04):** Completed. `TelegramBot` now protects scheduler task mutation and iteration with `self._tasks_lock`, and emits `scheduler_task_added` structured events on append.
**Source:** Engineering audit 2026-03-04 (Medium risk #3)

**Location:** `titan/orchestration/daily_coach.py` or scheduler module —
`scheduled_tasks` list

**Problem:** The `scheduled_tasks` list is appended and read across execution contexts
(scheduler thread + potential manual trigger paths) without lock discipline. Current
usage is likely benign at today's trigger volume, but if runtime task mutation grows
(dynamic reschedule, manual override injection), list mutation during iteration produces
`RuntimeError: list changed size during iteration` or silent task loss.

**Fix direction:**
- Replace bare `list` with a `threading.Lock`-guarded accessor, or
- Use `collections.deque` (thread-safe for `append`/`popleft` but not iteration)
- Preferred: add a `_tasks_lock = threading.Lock()` and wrap all `append` / iteration
  under `with self._tasks_lock:`
- Emit `scheduler_task_added` structured event on each append for observability

**Effort:** ~1h. Surgical; no architecture change.

---

### T3-08 · Weather + Telegram worker shutdown: no post-join alive escalation ✅ RESOLVED

**Status (2026-03):** COMPLETED. Weather and Telegram worker stop paths now perform post-join
`is_alive()` checks and emit structured `worker_shutdown_timeout` escalation events.

**Closure evidence (pytest nodeids + invariant):**
- `tests/titan/integrations/test_weather_api.py::test_stop_background_updates_emits_shutdown_timeout_when_thread_stays_alive`
- `tests/titan/integrations/test_telegram_bot_observability.py::test_stop_bot_emits_shutdown_timeout_for_scheduler_thread`
- `tests/titan/integrations/test_telegram_bot_observability.py::test_stop_bot_emits_shutdown_timeout_for_poll_thread`
- Invariant: worker threads that survive `join(timeout=5)` now trigger explicit shutdown-timeout
  escalation events instead of silent continuation.

**Implementation reference:**
- Commit: `7164524`
- Branch: `codex/add-post-join-alive-escalation-for-workers`
- PR: [#272](https://github.com/zafiriss-ux/project-mayhem/pull/272)
**Priority:** P1. Must be resolved before Phase 8. Extends T3-06 to the two remaining workers.

**Location:** `titan/integrations/weather_api.py` — `stop_background_updates()`; and
`titan/integrations/telegram_bot.py` — `stop_bot()` (for `_sched_thread` and `_poll_thread`)

**Problem:**
- `weather_api.stop_background_updates()` calls `self._update_thread.join(timeout=5)` with
  no `is_alive()` check after join and no structured escalation event on non-termination.
- `telegram_bot.stop_bot()` checks `is_alive()` **before** each join (correct) but not
  **after** — if a thread survives the timeout, shutdown proceeds silently. No
  `worker_shutdown_timeout` event is emitted for weather or telegram workers.

The `DailyCoach._routine_thread` (T1-11) now has full escalation. The Garmin worker
(T3-06) has full escalation. Weather and Telegram are the remaining gaps. If either worker
hangs on a network call past the 5s timeout, `main.py` proceeds to `db.close()` with a
live thread that may still hold a cursor reference.

**Fix direction:**
- `weather_api.stop_background_updates()`: after `join(timeout=5)`, add:
  ```python
  if self._update_thread and self._update_thread.is_alive():
      _weather_event("worker_shutdown_timeout", level="error",
                     worker_name="WeatherUpdater", timeout_seconds=5, still_alive=True)
  ```
- `telegram_bot.stop_bot()`: after each `join(timeout=5)`, add identical alive-check +
  `_telegram_event("worker_shutdown_timeout", ...)` for `_sched_thread` and `_poll_thread`.
- Do not forcibly kill threads. Escalation-only approach (same as T3-06 / T1-11).

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/weather_api.py titan/integrations/telegram_bot.py  # zero findings
python -m pytest -q -W error::pytest.PytestWarning  # 100% green
# Tests must assert: simulated hung thread → worker_shutdown_timeout event emitted
```

**Effort:** ~2h total (1h per file). Surgical; no architecture change.
**Tests:** Add to existing integration test files — simulate hang via `thread.join` mock,
assert `worker_shutdown_timeout` event is emitted for both workers.

---

### T3-09 · Telegram is single point of failure — no notification fallback path ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Architecture Review 2026-03-06.
**Priority:** P2 (reliability — Telegram token expiry or API outage silences all coaching delivery).

**Location:** `titan/integrations/telegram_bot.py` + new `titan/integrations/notification_gateway.py`

**Problem:**

All outbound notifications (daily briefing, SLO alerts, Telegram fallback events) route
exclusively through `TitanTelegramBot`. If the bot token expires, the Telegram API applies
rate limits, or network connectivity is lost, the athlete receives no coaching output and
no alert about the silence. The failure is operationally invisible.

**Fix direction:**

1. Create `titan/integrations/notification_gateway.py` — `NotificationGateway` class with
   an ordered list of `NotificationChannel` implementations.
2. `NotificationGateway.send(message, level)` iterates channels in priority order; stops
   on first success; logs delivery chain result.
3. **Primary channel:** `TelegramChannel` — wraps existing `TitanTelegramBot.send_message()`.
4. **Secondary channel:** `FileChannel` — writes daily briefing to
   `~/Documents/TITAN/daily_briefing_YYYY-MM-DD.txt`. Always succeeds unless disk is
   full. No new dependencies.
5. `TitanTelegramBot` becomes a `TelegramChannel(NotificationChannel)` — backwards
   compatible; external call sites unchanged.
6. All `daily_coach.py` Telegram calls route through `NotificationGateway`.

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/notification_gateway.py titan/integrations/telegram_bot.py
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
python -m pytest -q                                    # 100% green, count ≥ previous
```

**Tests required (3 minimum):**
- `test_gateway_uses_primary_channel_on_success` — assert Telegram called; file not written.
- `test_gateway_falls_back_to_file_on_telegram_failure` — mock Telegram to raise; assert
  file written with briefing content.
- `test_gateway_logs_delivery_chain_result` — assert structured log event with channel name
  and outcome regardless of which channel succeeded.

**Effort:** ~4h. New module + integration wiring. Backwards compatible.

---

## TIER 4 — Maintainability (Sprint 4+)

### T4-01 · Ruff debt burn-down (lint hygiene) ✅ RESOLVED

**Status (2026-03-04):** Completed. `ruff check . --statistics` returns zero findings; burn-down closure criterion satisfied.

---

### T4-02 · Remove confirmed unused imports ✅ RESOLVED

**Status (2026-03-04):** Completed. The listed production imports are no longer reported as unused (`F401`) and the cleanup objective is satisfied.

Original audit snapshot (pre-fix):

| File | Line | Import | Fix |
|---|---|---|---|
| `titan/integrations/telegram_bot.py` | 32 | `from telebot import types` | Remove |
| `titan/config/evidence_registry.py` | ~1 | `from __future__ import annotations` | Remove |
| `titan/ui/operator_console.py` | ~3 | `from __future__ import annotations` | Remove |
| `titan/science/outcome_tracker.py` | ~25 | `from dataclasses import field` | Remove |
| `titan/science/adaptive_priority_lock.py` | ~20 | `from typing import Optional` | Remove |

---

### T4-03 · Typed payload contracts at critical boundaries ✅ RESOLVED

**Status (2026-03-04):** Completed. `titan/orchestration/contracts.py` defines
`TypedDict` schemas and frozen `@dataclass` contracts for the four most critical
inter-layer payloads: `HRVSyncMetrics` / `HRVSyncMetricsContract`,
`GarminSyncResult` / `GarminSyncResultContract`, `TodaySessionPlan`,
`DailyCoachContext` / `DailyCoachContextContract`, and `DailyCoachingPayload`.
Both `titan/integrations/garmin_sync.py` and `titan/orchestration/daily_coach.py`
import and use these contracts at their boundaries. Tests: 8 green in
`tests/test_t4_03_typed_payload_contracts.py` and
`tests/titan/orchestration/test_contracts.py`. PR: TBD.

**Original state:** The orchestration pipeline relied on loose `dict` contracts between
subsystems (`garmin_data`, `today_session`, `titan_ctx`). This worked at current scale
but created key-mismatch / implicit-contract risk as the system grew.

**Fix applied:**
- Defined lightweight `@dataclass` + `TypedDict` schemas for the 3–4 most critical
  inter-layer payloads
- Started with `GarminSyncResult` (already partially structured) and `DailyCoachContext`
- Did NOT attempt a full typed migration in one pass

---

### T4-04 · `titan_ctx` dict → typed context object in `titan/main.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. `titan/main.py` constructs `titan_ctx` using the typed `TitanContext` / `TitanContextContract` boundary instead of an untyped accumulator dict.

Original audit snapshot (pre-fix):
The large `titan_ctx` dict in the entrypoint accumulates keys across subsystems with no
type contract. Future key additions are invisible to static analysis.

Depends on T4-03 (start smaller, work up to main context object).

---

### T4-05 · Architecture change lock for `governance_engine.py` ✅ RESOLVED

**Status (2026-03-04):** Completed. All three process-level protections are in place:

1. **CODEOWNERS** — `.github/CODEOWNERS` assigns `@titan-architecture` as required
   reviewer for any PR touching `titan/science/governance_engine.py`.
2. **File header** — `governance_engine.py` carries `# ARCHITECTURE LOCK — see ADR-0009
   before modifying` as its first line (line 1), visible to any engineer opening the file.
3. **CI enforcement** — `env-policy` job in `.github/workflows/ci.yml` detects any commit
   that modifies `governance_engine.py` and fails the pipeline unless the commit message
   contains an `ADR-0009` reference.

Completed: 2026-03-04
PR: TBD

---

### T4-06 · Doc freshness maintenance process ✅ RESOLVED

**Status (2026-03-04):** Completed. Policy applied across all closed items:
- All "Current state:" labels in resolved items renamed to "Original state (pre-fix):" with verbs converted to past tense.
- All numeric measurements in closed items (test counts, error counts) annotated with "as of [date] at closure — historical snapshot, not a live reading."
- Forbidden "currently X" language removed from all closed items.
- Appendix B test-count annotated as a Phase 7 close snapshot.
- Ongoing policy: at the close of each phase sprint, scan `TECHNICAL_DEBT.md` for stale present-tense measurements and annotate or remove them.

**Risk (28%):** Historical metric snapshots embedded in closed debt entries (error counts, test counts, date-bound measurements) drift out of sync with the actual codebase state over time. Without explicit date-annotation, future contributors may treat recorded closure measurements as current readings, leading to incorrect triage decisions.

**Fix direction:**
- **Annotation policy:** Any closed item containing a numeric baseline or measurement must carry an explicit date annotation and a note that the value is a historical closure snapshot, not a live reading. Use "as of [date] at closure" — never "currently X".
- **Review checkpoint:** At the close of each phase sprint, scan `TECHNICAL_DEBT.md` for stale present-tense measurements and annotate or remove them.
- **Forbidden language in closed items:** Avoid present-tense claims ("currently X errors", "currently are"). Use past-tense or explicitly dated language.

**Immediate action applied (2026-03-03):** T4-01 historical error-category list re-annotated as a pre-closure snapshot (see T4-01 above).

**Effort:** ~1h for initial policy pass; ~15 min per sprint close for ongoing maintenance.

---

### T4-07 · Credential setup wizard quality debt — duplicate prompts + plaintext `.env` ✅ RESOLVED

**Status (2026-03-04):** Completed. `setup_wizard.py` no longer duplicates credential prompts, validates interactive inputs, and supports opt-in keyring-backed storage via `TITAN_USE_KEYRING=1` while preserving `.env` as the local default.
**Source:** Engineering audit 2026-03-04 (Medium risk #4 + Low-priority #3)

**Location:** `titan/ui/setup_wizard.py`

**Problem (two sub-issues):**
1. The setup wizard requests some credential fields twice within the same interactive flow.
   Duplicate prompts confuse first-time users and undermine trust in the tool.
2. Credentials are stored in plaintext in `~/Documents/TITAN/.env`. Best-effort file
   permissions are applied, but this is weak for any non-local deployment. No secret
   backend or keyring integration exists.

**Test gap (see also T4-12):** Interactive flow logic (duplicate prompts, validation
branches, cancellation behavior) is under-covered in `test_new_modules.py` — only
`_save_env` is meaningfully tested.

**Fix direction:**
- Audit `setup_wizard.py` for duplicate prompt calls; eliminate duplicates
- Add validation for each field before accepting (non-empty, format checks where
  applicable)
- Add support for `keyring` as an opt-in alternative to plaintext `.env` (guarded
  behind a feature flag or env var `TITAN_USE_KEYRING=1`). Do not remove `.env`
  support — it remains the default for local use
- **Independent:** Fix duplicate prompts first (no architecture change); keyring is
  a separate, optional hardening step

**Effort:** Duplicate prompt fix: ~1h. Keyring integration: ~4h.

---

### T4-08 · Garmin sync timeout is advisory-only — no cancel/short-circuit ✅ RESOLVED

**Status (2026-03-04):** Completed. `GarminSync.sync_all()` now enforces timeout cancellation with `ThreadPoolExecutor`, emits `garmin_sync_cancelled`, and returns `status="timeout_cancelled"` on timeout.
**Source:** Engineering audit 2026-03-04 (Low-priority #1)

**Location:** `titan/integrations/garmin_sync.py` — sync timeout + SLO alert path

**Problem:** When a Garmin sync operation exceeds its timeout budget, the system emits
an SLO alert (Telegram delivery). However, the slow operation itself is not
cancelled or short-circuited. The thread continues running until the underlying network
call completes or errors. This is observability-only control — the SLO alert fires but
the slow sync continues to hold resources.

**Fix direction:**
- Wrap long-running Garmin API calls with `concurrent.futures.ThreadPoolExecutor`
  and `future.result(timeout=N)` to enable actual cancellation
- On `TimeoutError`: cancel the future, emit `garmin_sync_cancelled` event, and
  return a partial result with `status="timeout_cancelled"`
- Note: Python thread cancellation is not clean for all call sites; assess per-method
  before applying

**Effort:** ~3h. Medium complexity due to Python thread cancellation semantics.

---

### T4-09 · Main loop suppresses `KeyboardInterrupt` without structured shutdown logging ✅ RESOLVED

**Status (2026-03-04):** COMPLETED. `titan/main.py` now catches `KeyboardInterrupt` explicitly in the top-level menu loop, emits structured `shutdown_requested` with `reason="keyboard_interrupt"` and `timestamp`, and then runs the clean shutdown sequence (`stop_background_sync`, `stop_background_updates`, `stop_bot`, `db.close`). PR: TBD.
**Source:** Engineering audit 2026-03-04 (Low-priority #2)

**Location:** `titan/main.py` or `main.py` — main menu loop

**Problem:** `KeyboardInterrupt` is caught at the menu level and suppressed. The
shutdown path does not log a structured `shutdown_requested` event with
`(reason="keyboard_interrupt", timestamp)`. In production, this makes it impossible
to distinguish intentional Ctrl+C shutdowns from unexpected process termination in
aggregated log output.

**Fix direction:**
- Catch `KeyboardInterrupt` explicitly in the top-level loop
- Emit `log.info("shutdown_requested", reason="keyboard_interrupt")` before exiting
- Call the existing clean shutdown sequence (stop background threads, close DB)
- This does not require signal handler changes — catching at the loop level is
  sufficient for this tool's deployment model

**Effort:** ~1h.

---

### T4-10 · Typed payload contracts use broad `Any` — weakens static guarantees ✅ RESOLVED

**Status (2026-03-04):** COMPLETED.
**Source:** Engineering audit 2026-03-04 (Architecture observation #3)

**Completion update (2026-03-04):**
- contracts updated: `DailyCoachContext`, `GarminSyncResult`, `TodaySessionPlan`, `DailyCoachingPayload`, `TitanContext`
- remaining contracts: none
- date: 2026-03-04
- PR: TBD

**Location:** `titan/orchestration/contracts.py` + typed boundaries in
`titan/integrations/garmin_sync.py`, `titan/orchestration/daily_coach.py`

**Problem:** T4-03 introduced typed payload contracts at critical boundaries, but many
fields in the resulting `TypedDict` and `@dataclass` schemas are typed as `Any`. `Any`
fields defeat the purpose of typed contracts — mypy cannot verify shape correctness at
boundaries, and key-mismatch bugs remain invisible to static analysis.

**Fix direction:**
- Audit all `Any` fields in `titan/orchestration/contracts.py`
- Replace with concrete types where the shape is known and stable:
  - `dict[str, Any]` → `TypedDict` with concrete fields
  - `list[Any]` → `list[ConcreteType]`
  - Scalar `Any` → `str | int | float | None` union as appropriate
- Do not attempt a full migration in one pass. Work one contract at a time.
- Run `mypy titan/orchestration/contracts.py` after each change; zero errors required.
- Depends on T4-03 (already closed) as the foundation.

**Effort:** ~4h per contract; estimate 4 contracts = ~16h total across multiple passes.

---

### T4-11 · No mandatory coverage gate in CI ✅ RESOLVED

**Status (2026-03-04):** Completed. `pyproject.toml` `[tool.pytest.ini_options]` now includes
`addopts = "--cov=titan --cov-fail-under=80 --cov-report=term-missing"`. Baseline measured at
86.42% (as of closure 2026-03-04 — historical snapshot, not a live reading). Gate fires at
<80%. Ratchet: do not lower the threshold below 80%; raise it as coverage improves.
PR: TBD.
**Source:** Engineering audit 2026-03-04 (Test coverage gap #1)

**Location:** `pyproject.toml` + `.github/workflows/ci.yml`

**Problem:** `pyproject.toml` contains coverage configuration and `pytest` settings,
but no `--cov-fail-under` threshold is enforced in the default test workflow. Coverage
can silently erode over time as new modules are added without corresponding tests. There
is no ratchet mechanism to prevent regression.

**Fix direction:**
- Add `--cov-fail-under=80` (or the current measured baseline, whichever is higher)
  to the `[tool.pytest.ini_options]` `addopts` in `pyproject.toml`, or as a CI step
  in `.github/workflows/ci.yml`
- Preferred strategy: **ratchet** — measure current coverage at closure of this item,
  set the threshold to that value, and only ever increase it
- Modules with existing ≥95% coverage (governance, Phase 7 ML) should be protected
  by per-module thresholds in addition to the global gate

**Effort:** ~1h to configure; ~2h to measure baseline and set threshold.

---

### T4-12 · Setup wizard interactive flow under-covered by tests ✅ RESOLVED

**Status (2026-03-04):** Completed. `tests/titan/ui/test_setup_wizard.py` covers one-prompt-per-field behavior, invalid-input re-prompt paths, and keyring/env credential persistence flows.
**Source:** Engineering audit 2026-03-04 (Test coverage gap #2)

**Location:** `test_new_modules.py` — setup wizard coverage

**Problem:** Existing test coverage for `setup_wizard.py` focuses on `_save_env`.
The interactive flow logic — duplicate prompt behaviour, per-field validation branches,
cancellation paths, and wizard completion state — is not covered. Given the wizard is
the first user-facing flow for new deployments, untested validation branches are a
high-value regression surface.

**Fix direction:**
- Create or extend tests in `tests/titan/ui/test_setup_wizard.py` (or nearest
  equivalent following project test layout)
- Cover: duplicate prompt elimination (once T4-07 is fixed), all validation branches
  (empty input, invalid format), cancellation path, full happy-path wizard completion
- Use `unittest.mock.patch("builtins.input", side_effect=[...])` for interactive
  prompt simulation
- Minimum: one test per distinct validation branch + one cancellation test

**Effort:** ~3h.

**Dependency:** T4-07 (fix wizard first, then add tests for the fixed behaviour).

---

### T4-13 · No full lifecycle stress test for all background workers together ✅ RESOLVED

**Status (2026-03-04):** Completed. Full lifecycle stress test implemented covering concurrent startup and shutdown of all background workers.
**Source:** Engineering audit 2026-03-04 (Test coverage gap #3)

**Location:** `tests/` — concurrency / integration test coverage

**Problem:** Existing concurrency tests are unit-level and test isolated components
(individual thread lifecycle, individual stop event). There is no integration test
that exercises a full start → run → stop sequence across all four workers together:
Garmin sync + Weather updater + Telegram bot + DailyCoach scheduler. Without such a
test, hung-thread shutdown bugs (T3-06) and daemon overlap bugs (T1-07) can only be
detected in production.

**Fix direction:**
- Create `tests/test_full_lifecycle_stress.py`
- Test scenario: instantiate all four workers with mocked external APIs, start all,
  let them run for 2–3 scheduler ticks (use mocked `time.sleep`/`Event.wait`), then
  call the full stop sequence and assert all threads are not alive within 10s
- Assert: no `sqlite3.ProgrammingError` raised during concurrent DB access
- Assert: no duplicate routine execution (T1-07 guard fires correctly)
- Use `pytest-timeout` to bound the test to ≤30s wall time

**Effort:** ~6h. Non-trivial mocking surface; do after T1-06 and T1-07 are fixed.

**Dependency:** T1-06, T1-07 (fix races first, then stress-test the fixes).

---

### T4-14 · Garmin background worker uses per-second loop instead of single `Event.wait()` ✅ RESOLVED

**Status (2026-03-06):** ✅ RESOLVED. `_bg_worker()` now uses a single `Event.wait(timeout=float(interval_hours * 3600))` wait cycle while preserving immediate stop-event exit semantics. PR: TBD.
**Source:** Engineering Audit V4 (2026-03-05) — M1 finding.
**Priority:** P3. No correctness impact. Wasted CPU/wake cycles; diagnostic noise in profiler.

**Location:** `titan/integrations/garmin_sync.py` — `_bg_worker()` lines ~452-455.

**Problem:** The inter-sync sleep is implemented as a `for` loop with `interval_hours * 3600`
iterations (21,600 for a 6h cycle), each calling `self._stop_event.wait(timeout=1.0)`:

```python
for _ in range(interval_hours * 3600):
    if self._stop_event.wait(timeout=1.0):
        return
```

This wakes the thread once per second regardless of whether the stop event is set. The
correct pattern (used by `weather_api.py` since T3-05) is a single `Event.wait()` with
the full interval as the timeout:

```python
if self._stop_event.wait(timeout=interval_hours * 3600):
    return
```

`threading.Event.wait()` returns immediately when the event is set — so the stop latency
is identical (sub-millisecond) and the CPU overhead of 21,600 loop iterations is eliminated.

**Fix direction:**
```python
# Replace:
for _ in range(interval_hours * 3600):
    if self._stop_event.wait(timeout=1.0):
        return

# With:
if self._stop_event.wait(timeout=float(interval_hours * 3600)):
    return
```

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/garmin_sync.py   # zero findings
python -m pytest -q -W error::pytest.PytestWarning   # 100% green
```

**Tests required:** Existing `_bg_worker` stop tests must remain green. Verify stop latency
test (set stop event; assert thread exits without waiting a full tick).

**Effort:** ~30 minutes. One-line change + test verification.

---

### T4-15 · Weather updater thread has no explicit name — diagnostics parity gap 🔴 OPEN (independent)

**Status (2026-03-06):** ✅ RESOLVED. `_bg_worker()` now uses a single `Event.wait(timeout=float(interval_hours * 3600))` wait cycle while preserving immediate stop-event exit semantics. PR: TBD. `independent` — can be done in parallel with T1-15.
**Source:** Engineering Audit V4 (2026-03-05) — hidden debt item.
**Priority:** P4. Cosmetic/diagnostic only. No correctness or safety impact.

**Location:** `titan/integrations/weather_api.py` — `start_background_updates()`.

**Problem:** The `threading.Thread` for the weather updater is created without a `name=`
parameter:
```python
self._update_thread = threading.Thread(
    target=self._background_update_worker, args=(interval_hours,), daemon=True
)
```
In `threading` diagnostics (e.g., `threading.enumerate()`, crash dumps, profiler output),
this thread appears as `Thread-N` (auto-incremented integer). The Garmin (`"GarminSync"`)
and DailyCoach (`"DailyCoachRoutine"`) threads are already named. Weather and Telegram
threads are the remaining gap.

**Fix direction:**
```python
self._update_thread = threading.Thread(
    target=self._background_update_worker,
    args=(interval_hours,),
    daemon=True,
    name="WeatherUpdater",   # add this
)
```
The canonical name `"WeatherUpdater"` is already used in T3-08 `worker_shutdown_timeout`
events — this aligns the thread name with the event name for correlation.

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/weather_api.py   # zero findings
python -m pytest -q   # 100% green
```

**Effort:** 5 minutes. Single parameter addition.

---

### T4-16 · Setup wizard prints duplicate Windows permission warning 🔴 OPEN (independent)

**Status (2026-03-06):** ✅ RESOLVED. `_bg_worker()` now uses a single `Event.wait(timeout=float(interval_hours * 3600))` wait cycle while preserving immediate stop-event exit semantics. PR: TBD. `independent` — can be done in parallel with T1-15.
**Source:** Engineering Audit V4 (2026-03-05) — hidden debt item.
**Priority:** P4. UX/cosmetic. No correctness impact.

**Location:** `titan/ui/setup_wizard.py` — `_save_env()` function, lines ~195-205.

**Problem:** `_save_env()` contains two consecutive `if os.name == "nt":` blocks that each
print a different Windows-specific permission warning. The first block prints a Greek-language
warning; the second prints an English warning for the same issue. A Windows user sees two
warnings about the same problem, one in each language:

```python
if os.name == "nt":
    print("  ⚠️  Windows: τα permissions ...")  # Greek
if os.name == "nt":
    print("  ⚠️  Windows limitation: .env file ...")  # English
```

Note also: `ENV_PATH.chmod(...)` is called twice — once before the first block and once
inside the else of the second block. The first call is on all platforms; the second is
duplicated on non-Windows.

**Fix direction:**
- Merge the two `if os.name == "nt":` blocks into a single block.
- Decide on one language for the warning (recommend English for consistency with the
  rest of the wizard's fallback messages, or Greek if the wizard is fully localised).
- Ensure `ENV_PATH.chmod()` is called exactly once on non-Windows, once total.

**Acceptance gate (binary):**
```bash
ruff check titan/ui/setup_wizard.py   # zero findings
python -m pytest -q   # 100% green
# Manual: count `if os.name == "nt":` blocks in _save_env — must be exactly 1.
```

**Effort:** ~15 minutes. Merge two blocks, remove duplicate.

---

### T4-17 · Setup wizard modifies `.gitignore` at runtime — operational side effect 🔴 OPEN (independent)

**Status (2026-03-06):** ✅ RESOLVED. `_bg_worker()` now uses a single `Event.wait(timeout=float(interval_hours * 3600))` wait cycle while preserving immediate stop-event exit semantics. PR: TBD. `independent` — can be done in parallel with T1-15.
**Source:** Engineering Audit V4 (2026-03-05) — hidden debt item.
**Priority:** P3. Operational side effect with blast radius on repository state.

**Location:** `titan/ui/setup_wizard.py` — `_save_env()` function, lines ~207-216.

**Problem:** After saving `.env`, the wizard appends entries to `.gitignore` at the
repository root if they are not already present:

```python
gitignore = Path(__file__).parent.parent.parent / ".gitignore"
existing = gitignore.read_text() if gitignore.exists() else ""
additions = []
for entry in [".env", "config_secrets.py", "data/database/", "data/logs/"]:
    if entry not in existing:
        additions.append(entry)
if additions:
    with gitignore.open("a") as f:
        f.write("\n# TITAN secrets\n" + "\n".join(additions) + "\n")
```

**Three issues with this pattern:**
1. **Silent runtime mutation of VCS state**: `.gitignore` is a version-controlled file.
   A tool running at runtime silently modifying it surprises contributors and CI pipelines.
   The change appears as unstaged in `git status` after wizard execution.
2. **Path fragility**: `Path(__file__).parent.parent.parent` assumes a fixed directory
   depth. If the package is installed or the file is moved, this silently fails or targets
   the wrong file.
3. **Idempotency**: The string check `if entry not in existing` is a substring match and
   may produce false negatives if the entry appears as part of a longer path.

**Fix direction (preferred — remove runtime mutation):**
- Remove the `.gitignore` write from `_save_env()` entirely.
- These entries should be committed into `.gitignore` in the repository once (they
  already should be, given T1-01 and the project's deployment model).
- If wizard-time `.gitignore` management is genuinely needed, document it as an
  explicit user-facing step ("Added `.env` to `.gitignore` — please commit this change")
  rather than a silent file mutation.

**Alternative (if runtime write must remain):**
- Use `git rev-parse --show-toplevel` to find the actual repo root (not file-depth
  heuristic).
- Use line-by-line exact matching, not `in existing` substring.
- Emit a `log.info("gitignore_updated", entries_added=additions)` instead of silent write.
- Print an explicit note to the user: `"✅ Updated .gitignore — remember to commit it."`

**Acceptance gate (binary):**
```bash
ruff check titan/ui/setup_wizard.py   # zero findings
python -m pytest -q   # 100% green
# Verify: running the wizard does not modify .gitignore during test (mock filesystem).
```

**Effort:** ~1h (remove approach) or ~2h (fix approach). Recommend remove.

---

### T4-18 · Governance lock relies on comment, not machine-verifiable contract ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Architecture Review 2026-03-06 — ADR-0021 (Governance Evolvability Protocol).
**Priority:** P2 (maintainability — "lock paralysis" risk as codebase grows).

**Location:** `titan/science/governance_engine.py` + new `tests/test_governance_mutation.py`

**Problem:**

`governance_engine.py` carries `# ARCHITECTURE LOCK — see ADR-0009 before modifying` as
its primary protection mechanism. This is a psychological deterrent — it is not enforced
by any automated check. As the codebase grows and AI agents assist with implementation,
there is no machine-readable signal that governance gate logic has been inadvertently
altered. A syntactically correct but scientifically wrong change passes all current tests.

**Fix direction:**

1. Create `tests/test_governance_mutation.py` — governance mutation test suite.
2. For each of the 7 gates (H2, H3, H4, H5, 2-of-4, VO2 eligibility, override lockdown):
   - Define a boundary input that is exactly on the threshold (must fire).
   - Define a boundary input that is one unit below the threshold (must not fire).
   - Assert the correct lock code is returned in both cases.
3. For each threshold constant in `thresholds.py` used by governance:
   - Assert the gate fires when the threshold value is met (not hardcoded — uses imported
     constant, so changing the constant changes the test automatically).
4. Replace the comment on `governance_engine.py:1` with:
   ```python
   # Gate parameters: see thresholds.py + evidence_registry.py.
   # Changes require: (1) ADR entry, (2) evidence_registry.py update, (3) mutation test update.
   ```

**Acceptance gate (binary):**
```bash
ruff check titan/science/governance_engine.py tests/test_governance_mutation.py
python -m pytest tests/test_governance_mutation.py -v   # all new tests green
python -m pytest -q -W error::pytest.PytestWarning      # 100% green (full suite)
python -m pytest -q                                      # 100% green, count ≥ previous
```

**Effort:** ~3h. New test file only; no production code change except the comment on line 1.

---

### T4-19 · Architectural invariant tests absent — AI agent semantic drift undetectable ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Architecture Review 2026-03-06.
**Priority:** P3 (process — AI-assisted development introduces semantic drift risk not caught by functional tests).

**Location:** new `tests/test_architectural_invariants.py`

**Problem:**

As the codebase grows with AI agent assistance, a class of bugs emerges that is
syntactically valid and passes all functional tests but violates architectural contracts:
hardcoded threshold values in governance code, silent exception swallowing, direct DB
access outside the lock, bypass of governance context fields. No automated check currently
catches these patterns.

**Fix direction:**

Create `tests/test_architectural_invariants.py` with the following invariants:

1. `test_no_silent_exception_swallow_in_production_code` — `rg "except Exception:\s*pass"`
   across `titan/` (excluding `ui/` where silent UI fallback is permitted per ADR-0019
   Decision 3). Assert zero matches.
2. `test_governance_engine_imports_no_numeric_literals_for_thresholds` — parse
   `governance_engine.py` AST; assert no float/int literals appear in gate function bodies
   (all thresholds must come from imports).
3. `test_all_governance_lock_codes_are_canonical` — assert that every string used as a
   lock code in `governance_engine.py` appears in the canonical set defined in `CLAUDE.md`
   / a constants module.
4. `test_database_manager_no_direct_conn_access_outside_lock` — parse `database.py` AST;
   assert `self.conn` is never accessed outside `with self._lock:` context.

**Acceptance gate (binary):**
```bash
ruff check tests/test_architectural_invariants.py
python -m pytest tests/test_architectural_invariants.py -v   # all new tests green
python -m pytest -q -W error::pytest.PytestWarning           # 100% green (full suite)
python -m pytest -q                                           # 100% green, count ≥ previous
```

**Effort:** ~2h. New test file only; no production code change.

---

### T4-20 · No PR template — architecture checklist absent from review process ✅ RESOLVED

**Status:** RESOLVED 2026-03-06.
**Source:** Architecture Review 2026-03-06.
**Priority:** P3 (process — without a checklist, ADR compliance depends on reviewer memory).

**Location:** new `.github/pull_request_template.md`

**Problem:**

Pull requests have no structured template. Reviewers must recall from memory whether a
given change requires an ADR update, an `evidence_registry.py` update, a `SCHEMA_VERSION`
bump, or a mutation test update. This is the primary vector for AI agent semantic drift
to survive code review — the agent produces a correct-looking diff; the reviewer approves
without checking architectural compliance.

**Fix direction:**

Create `.github/pull_request_template.md` with:
1. **Summary** — one-line description of the change.
2. **Architecture checklist (mandatory for every PR):**
   - [ ] Which ADRs are affected by this change? (list them, or write "none")
   - [ ] If a threshold constant was changed: `evidence_registry.py` updated?
   - [ ] If schema was changed: `SCHEMA_VERSION` bumped and migration added?
   - [ ] If governance gate logic was changed: mutation test updated?
   - [ ] `TECHNICAL_DEBT.md` updated (item closed, new items added)?
3. **Test plan** — what was tested and how.
4. **Gates** — checkbox: `ruff check .` ✅ / `pytest -q -W error` ✅ / `pytest -q` ✅

**Acceptance gate (binary):**
```bash
# File exists and is non-empty:
test -f .github/pull_request_template.md && wc -l .github/pull_request_template.md
# No code changes → no pytest gate required for this item.
```

**Effort:** ~30 minutes. Documentation-only change.

---

### T4-21 · Documentation consistency not automated — lock codes, evidence registry, ADR index can drift silently 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent).
**Source:** Master Risk Matrix — Risk #13 (Governance Documentation Rot). Architecture Review 2026-03-06. ADR-0024.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** New `tests/test_documentation_consistency.py` + `titan/config/thresholds.py` + `.github/workflows/ci.yml`.

**Problem:**

Four documentation drift failure modes with no automated detection:
1. Lock codes in `governance_engine.py` not verified against a canonical set (canonical
   set lives in CLAUDE.md prose — not machine-readable).
2. Thresholds in `thresholds.py` can be added without corresponding `evidence_registry.py`
   entries.
3. `docs/adr/README.md` index can fall behind actual ADR file count.
4. `TECHNICAL_DEBT.md` tracking table can diverge from prose RESOLVED/OPEN status.

**Fix direction (per ADR-0024):**

1. Add `CANONICAL_LOCK_CODES: frozenset[str]` to `titan/config/thresholds.py`.
2. Create `tests/test_documentation_consistency.py` with 4 checks:
   - Lock code completeness (AST parse `governance_engine.py` vs `CANONICAL_LOCK_CODES`)
   - Evidence registry completeness (all constants in `thresholds.py` → entries in `evidence_registry.py`)
   - ADR index currency (file count vs README.md table rows)
   - TECHNICAL_DEBT tracking consistency (prose RESOLVED vs tracking table rows)
3. Add `docs-consistency` job to `.github/workflows/ci.yml`.

**Acceptance gate (binary):**
```bash
ruff check titan/config/thresholds.py tests/test_documentation_consistency.py
python -m pytest tests/test_documentation_consistency.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~3h. New test file + one constant + CI job.

---

### T4-22 · No machine-verifiable agent session start protocol — context drift undetectable 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent).
**Source:** Master Risk Matrix — Risk #1 (Agent Context Drift) + Risk #17 (Self-Referential Prompt Decay). Architecture Review 2026-03-06. ADR-0025.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** New `tests/test_claude_md_integrity.py` + `AGENTS.md` + `.github/workflows/ci.yml`.

**Problem:**

AI agent sessions begin without a verified baseline. Known failure modes: stale module
counts in CLAUDE.md, non-canonical lock codes generated by agents, Tier ordering
violations (E1), re-proposing already-closed debt items. CLAUDE.md can decay when agents
edit it incorrectly in a session.

**Fix direction (per ADR-0025):**

1. Create `tests/test_claude_md_integrity.py` with:
   - `test_adr_count_in_claude_md_matches_files()` — ADR file count vs CLAUDE.md mentions
   - `test_module_count_in_claude_md_matches_filesystem()` — module count vs actual
   - `test_open_tier_items_not_misrepresented()` — phase closed claims vs open items
2. Update `AGENTS.md` §SESSION_START with the 5-step S1–S5 protocol from ADR-0025.
3. Add CI job `claude-md-integrity`.

**Acceptance gate (binary):**
```bash
ruff check tests/test_claude_md_integrity.py
python -m pytest tests/test_claude_md_integrity.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~2h. New test file + AGENTS.md update + CI job.

---

### T4-23 · Property-based tests cover only happy-path invariants — physiology edge cases absent 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent; coordinate with T1-18 implementation).
**Source:** Master Risk Matrix — Risk #2 (Test Suite Illusion of Safety) + Risk #9 (Physiological Edge-Case Fragility). Architecture Review 2026-03-06.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `test_property_based.py` (extend) + `tests/test_science_edge_cases.py` (new).

**Problem:**

`test_property_based.py` uses Hypothesis for high-level invariants but does not test
physiology-specific boundary values. No test currently verifies that:
- `hrv_ms = 0` does not disable governance gate H2.
- `rhr_bpm = 200` does not produce a valid readiness score.
- `acwr = None` (post-T1-18) does not cause a `VolumeLoadGauge` crash.
- All 7 governance gates return `locked=False` when inputs are healthy (non-regression).

**Fix direction:**

1. Extend `test_property_based.py` with Hypothesis strategies for out-of-range
   physiological values (bounded by `physiological_bounds.BOUNDS`).
2. Create `tests/test_science_edge_cases.py` with parametrised table tests for
   each known edge-case input pattern.

**Dependency:** Best done after T1-18 (`PhysiologicalBounds` module exists — import its
`BOUNDS` to generate test ranges).

**Acceptance gate (binary):**
```bash
ruff check test_property_based.py tests/test_science_edge_cases.py
python -m pytest test_property_based.py tests/test_science_edge_cases.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~3h. Test-only changes.

---

### T4-24 · Test fixtures are hand-crafted per file — fixture drift accumulates silently 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent).
**Source:** Master Risk Matrix — Risk #15 (Test Fixture Drift). Architecture Review 2026-03-06.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `tests/conftest.py` (extend) + affected test files (audit required).

**Problem:**

Multiple test files independently construct `UniversalAthleteProfile`, `DatabaseManager`,
and governance engine instances with hand-crafted values. When the schema of these
objects changes (e.g., a new required field), each test file must be updated separately.
The failure mode is silent: tests pass because the object is created without the new field
(default is used), but the test is no longer testing the intended scenario.

**Fix direction:**

1. Audit `tests/` for hand-crafted fixture patterns: `grep -rn "UniversalAthleteProfile("
   tests/` → list all construction sites.
2. Create shared factory fixtures in `tests/conftest.py`:
   - `athlete_profile_factory(overrides: dict) -> UniversalAthleteProfile`
   - `db_manager_factory(tmp_path) -> DatabaseManager`
   - `governance_engine_factory(athlete, db) -> GovernanceEngine`
3. Migrate the 5 most-duplicated construction sites to use the factory.
4. Document the factory pattern in `tests/conftest.py` header comment.

**Acceptance gate (binary):**
```bash
ruff check tests/conftest.py
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q   # count ≥ previous (no tests removed)
```

**Effort:** ~2h. Test-only refactor; no production code change.

---

### T4-25 · Dependency pinning not audited — transitive drift and stale packages undetected 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent).
**Source:** Master Risk Matrix — Risk #6 (Dependency Drift). Architecture Review 2026-03-06.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `requirements.txt` + `.github/workflows/ci.yml`.

**Problem:**

`requirements.txt` pins direct dependencies but does not pin transitive dependencies
via a lockfile or constraints file. Over time:
1. Transitive package updates can break the build silently (a new transitive dep version
   is incompatible with Python 3.11 or with another dep in the graph).
2. Known CVEs in direct or transitive dependencies are not surfaced in CI.
3. No periodic audit job checks whether pinned versions are current or have known
   security advisories.

**Fix direction:**

1. Add `pip-audit` to dev dependencies in `requirements.txt`.
2. Add a `dependency-audit` CI job:
   ```yaml
   - run: pip-audit --requirement requirements.txt --fix-version
   ```
   Job runs weekly (cron) and on PRs that modify `requirements.txt`.
3. Add `constraints.txt` (generated via `pip freeze > constraints.txt` in CI) to lock
   transitive dependencies for reproducible builds.

**Note:** This item does not replace the existing `requirements.txt` pin discipline —
it adds a CVE/drift detection layer on top.

**Acceptance gate (binary):**
```bash
pip-audit --requirement requirements.txt   # zero HIGH/CRITICAL CVEs
pip install -r requirements.txt -c constraints.txt  # resolves without conflict
python -m pytest -q   # count ≥ previous
```

**Effort:** ~1.5h. CI job + dev dependency + constraints file generation.

---

### T4-26 · Module boundaries use raw dicts — implicit coupling undetectable by static analysis 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent).
**Source:** Architect Observations V6 — Risk #2 (Hidden Inter-Module Dependencies). ADR-0027.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `titan/core/database.py` (return types) + `tests/test_architectural_invariants.py` (new coupling test).

**Problem:**

`DatabaseManager` return methods (`get_daily_metrics`, `get_training_load_history`)
return raw `dict` objects. Science engines access fields by string key. If a field is
renamed or removed, the failure is a silent `None` — not a `KeyError`, not a type error.
Example: rename `hrv_ms` → `hrv_rmssd_ms` in the schema and every engine silently
receives `None` for HRV without a test failure at the boundary.

**Fix direction (per ADR-0027):**

1. Define `TypedDict` classes in `titan/core/database.py`:
   `DailyMetricsRow`, `TrainingLoadRow`, `GearUsageRow`.
2. Update `get_daily_metrics()`, `get_training_load_history()`, `get_gear_usage()`
   return type annotations.
3. Add coupling invariant test to `tests/test_architectural_invariants.py`:
   `test_no_science_imports_from_orchestration()` — assert no circular layer imports.

**Acceptance gate (binary):**
```bash
ruff check titan/core/database.py tests/test_architectural_invariants.py
python -m pytest tests/test_architectural_invariants.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~2h. TypedDict definitions + annotation updates + one new test.

---

### T4-27 · No module count ceiling — complexity accumulation untracked 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent).
**Source:** Architect Observations V6 — Risk #4 (Complexity Accumulation). ADR-0028.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `tests/test_documentation_consistency.py` (extend; T4-21).

**Problem:**

Module count grows unchecked with each phase. At 46 modules (Phase 7 close), the system
is within cognitive range. Without a ceiling, Phase 8 + Phase 9 additions could reach
65+ modules — the point at which the module graph exceeds single-engineer working memory.

**Fix direction (per ADR-0028):**

Add to `tests/test_documentation_consistency.py`:
```python
def test_module_count_within_budget():
    """Module count must not exceed 60 (Phase 8 ceiling per ADR-0028)."""
    import pkgutil, titan
    mods = [m for m in pkgutil.walk_packages(titan.__path__, 'titan.')
            if '__' not in m.name]
    assert len(mods) <= 60, f"Complexity budget exceeded: {len(mods)} modules"
```

**Dependency:** T4-21 must exist first (the test is added to that file).

**Acceptance gate (binary):**
```bash
ruff check tests/test_documentation_consistency.py
python -m pytest tests/test_documentation_consistency.py::test_module_count_within_budget -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~30 minutes. One new test added to existing file.

---

### T4-28 · No multi-agent context handoff artifact — advisor recommendations operate without ADR context 🔴 OPEN (independent)

**Status:** OPEN (Phase 7.9 — independent).
**Source:** Architect Observations V6 — Risk #5 (Multi-Agent Fragmentation). ADR-0029.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** New `scripts/generate_context_snapshot.py` + `docs/context-snapshot.md` + `AGENTS.md`.

**Problem:**

Multiple AI tools (ChatGPT, Gemini, Claude Chat, Codex, Claude Code) operate on this
codebase. Each has a different and potentially contradictory mental model of the system's
current state. Advisor tools can recommend patterns that contradict existing ADRs because
they are not provided the ADR register. Implementer tools can implement contradictory
parallel changes because they are not aware of concurrent work.

**Fix direction (per ADR-0029):**

1. Create `scripts/generate_context_snapshot.py`:
   - Reads open items from `TECHNICAL_DEBT.md`
   - Reads latest 5 ADRs from `docs/adr/README.md`
   - Reads `CANONICAL_LOCK_CODES` from `titan/config/thresholds.py`
   - Outputs `docs/context-snapshot.md` with timestamped system state
2. Create initial `docs/context-snapshot.md` (first snapshot).
3. Update `AGENTS.md` §SESSION_START with M1–M4 multi-agent protocol rules
   (Rule M2 adds S0 to the existing S1–S5 checklist).

**Acceptance gate (binary):**
```bash
python scripts/generate_context_snapshot.py   # exits 0, creates docs/context-snapshot.md
ruff check scripts/generate_context_snapshot.py
python -m pytest -q -W error::pytest.PytestWarning   # no regressions
python -m pytest -q
```

**Effort:** ~2h. New script + docs file + AGENTS.md update.

---

## TIER 5 — Future Optionality

### T5-01 · SQLite retention / archival strategy 🟢

**Decision status:** CLOSED.
**Wording status:** LOCKED/CLOSED.
Decision locked (ADR-0015).
No further decision is open in T5-01.
Scope remains single-athlete, single-lifetime.
Phase 8 gate (mandatory): no implementation before ADR acceptance.

---

### T5-03 · Multi-sport scope decision 🟢

Decision status: CLOSED. Decision locked (ADR-0016).

---

### T5-04 · No science evidence review ritual — governance thresholds may become stale relative to new literature 🟢

**Decision status:** OPEN (deferred — Phase 9+).
**Source:** Master Risk Matrix — Risk #12 (Model Stagnation vs New Science). Architecture Review 2026-03-06.

**Problem:**

All thresholds in `thresholds.py` carry an evidence label (STRONG / MODERATE / HEURISTIC)
in `evidence_registry.py`. However, there is no scheduled review of whether the evidence
has been superseded by newer research (e.g., updated ACWR safe zone boundaries, revised
HRV interpretation protocols, new lactate threshold testing methods).

**Decision:**

Deferred to Phase 9. Gate criterion: `evidence_registry.py` must include a
`_LAST_REVIEWED` date for each entry. A scheduled CI job (quarterly) flags entries
whose `_LAST_REVIEWED` is older than 365 days. The flag is a warning, not a gate failure
— the architect decides whether to update the threshold or extend the review date.

**Phase 9 gate:** This item is a prerequisite for Phase 9 (lifecycle supervisor). No
implementation before Phase 8 closes.

---

### T5-05 · No athlete model recalibration mechanism — physiological models drift as athlete evolves 🟢

**Decision status:** OPEN (deferred — Phase 9+).
**Source:** Architect Observations V6 — Risk #3 (Model Aging). Architecture Review 2026-03-06.

**Problem:**

Physiological models (HRV baseline, CTL/ATL EMA constants, lactate thresholds,
critical speed) are calibrated on historical data and held constant once computed.
An athlete's body changes: fitness improves, injury changes biomechanics, age alters
recovery kinetics. The models remain accurate at first; over 6–12 months they may
produce coaching decisions that are correct by the model but wrong for the current
athlete.

The `OutcomeTracker` already collects decision→outcome pairs for this purpose
(ADR-0014, T2-10). The missing piece is a **recalibration trigger**: a mechanism
that detects systematic divergence between predicted and observed outcomes and
proposes model parameter updates.

**Observable early signal:** If the governance engine's VO2 eligibility gate (G6)
consistently predicts readiness but post-session RPE is ≥8 for 3+ consecutive sessions,
the readiness model is over-predicting. `OutcomeTracker` has the data; there is no
consumer that acts on it.

**Decision:**

Deferred to Phase 9. The `AutomatedPeriodizationEngine` (Phase 7 ML scaffold,
ADR-0014) is the intended consumer of `OutcomeTracker` calibration data. Phase 9
will implement the feedback loop: `OutcomeTracker` → divergence detector →
`AutomatedPeriodizationEngine` → parameter update proposal → architect review →
model update.

The feedback loop is advisory-only (not automatic) to preserve human oversight of
physiological model parameters. Consistent with ML scaffold philosophy (ADR-0014).

**Phase 9 gate:** Requires `OutcomeTracker` to have ≥90 days of decision→outcome
pairs before the divergence detector can produce statistically meaningful signals.
No implementation before Phase 8 closes and data accumulation criterion is met.

---

All Tier 5 decisions have been locked or deferred. See Tracking table for completion dates and PRs.
Relevant ADRs: 0013 (UI path), 0014 (ML scaffold), 0015 (SQLite/multi-athlete), 0016 (multi-sport), 0022 (Phase 8 gate), 0028 (complexity budget).

---

## Appendix A — Documentation Fixes (Already Applied in This Audit)

The following doc inconsistencies were corrected directly in this commit:

| What was wrong | What was fixed |
|---|---|
| CLAUDE.md: "49 modules" | Fixed to "46 modules (excl. __init__/__main__)" |
| CLAUDE.md: "23 science modules" | Fixed to "26 modules"; Phase 7 ML scaffold added |
| CLAUDE.md: tests/ "14 files" | Fixed to "21 files"; 6 Phase 7 test files added |
| CLAUDE.md: ADRs "0001-0013" | Fixed to "0001-0014" (ADR-0014 created) |
| CLAUDE.md: docs/specs/ incomplete | Added 4 operator console spec files |
| CLAUDE.md: "Phases 0-6 CLOSED" | Fixed to "Phases 0-7 CLOSED" |
| CLAUDE.md: OpenWeatherMap API | Fixed to Open-Meteo (actual provider in code) |
| CLAUDE.md: `WEATHER_API_KEY` | Annotated as unused (Open-Meteo requires no key) |
| CLAUDE.md: DailyCoach v5.7 | Fixed to v5.8 |
| CLAUDE.md: `ACWR_SAFE_MIN/MAX` reference | Annotated as dead/duplicate |
| TECHNICAL_DEBT.md: T4-01 "Top categories currently are" list | Re-annotated as pre-closure historical snapshot; present-tense wording removed (T4-06 policy applied) |

---

## Appendix B — What Is Already Good (Do Not Break)

These patterns are correct and must be preserved in all future work:

- **Governance gate ordering**: non-bypassable, runs before every session output ✅
- **CTL/ATL chronological calculation**: oldest-first EMA rebuild on startup ✅
- **SQLite WAL + busy_timeout + write lock**: correct thread-safety approach ✅
- **Idempotent additive migrations**: safe to run on every startup ✅
- **Structured gate events** (`_gate_event()`): excellent observability foundation ✅
- **SLO alerts** (Telegram delivery, Garmin sync timeout, nutrition missing): production-grade ✅
- **Kill-switch default-ON**: correct failure mode for ML scaffold ✅
- **Evidence labels on all ML payloads**: provenance discipline from day one ✅
- **`governance_contracts.py`**: output shape validation at governance→orchestration boundary ✅
- **All tests passing** (1122 green as of Phase 7 close, 2026-03-04 — historical snapshot, not a live reading; 100% coverage on governance + Phase 7 modules at that date) ✅

---

## Tracking

When an item is completed, mark it here with date and PR reference:

| Item | Completed | PR |
|---|---|---|
| T1-01 | 2026-03-04 | PR: TBD |
| T1-02 | 2026-03-04 | PR: TBD |
| T1-03 | 2026-03-04 | PR: TBD |
| T1-04 | 2026-03-04 | PR: TBD |
| T1-05 | 2026-03-04 | PR: TBD |
| T2-01 | 2026-03-04 | PR: TBD |
| T2-06 | 2026-03-04 | PR: TBD |
| T3-01 | 2026-03-03 | [#172](https://github.com/zafiriss-ux/project-mayhem/pull/172) |
| T3-02 | 2026-03-04 | PR: TBD |
| T3-03 | 2026-03-04 | PR: TBD |
| T3-04 | 2026-03-04 | PR: TBD |
| T3-05 | 2026-03-04 | PR: TBD |
| T4-01 | 2026-03-03 | [#167](https://github.com/zafiriss-ux/project-mayhem/pull/167) |
| T4-03 | 2026-03-04 | PR: TBD |
| T4-06 | 2026-03-04 | PR: TBD |
| T5-01 | 2026-03-03 | [#173](https://github.com/zafiriss-ux/project-mayhem/pull/173), [#174](https://github.com/zafiriss-ux/project-mayhem/pull/174), [#175](https://github.com/zafiriss-ux/project-mayhem/pull/175) |
| T5-02 | 2026-03-03 | [#169](https://github.com/zafiriss-ux/project-mayhem/pull/169) |
| T5-03 | 2026-03-03 | [#170](https://github.com/zafiriss-ux/project-mayhem/pull/170) |
| T5-04 | 2026-03-03 | [#171](https://github.com/zafiriss-ux/project-mayhem/pull/171) |
| T1-06 | 2026-03-04 | PR: TBD |
| T1-07 | 2026-03-04 | PR: TBD |
| T1-08 | 2026-03-04 | PR: TBD |
| T1-09 | 2026-03-04 | PR: TBD |
| T3-06 | 2026-03 | Garmin path + [#272](https://github.com/zafiriss-ux/project-mayhem/pull/272) (child T3-08 closure) |
| T3-07 | 2026-03-04 | PR: TBD |
| T4-07 | 2026-03-04 | PR: TBD |
| T4-08 | 2026-03-04 | PR: TBD |
| T4-09 | 2026-03-04 | PR: TBD |
| T4-10 | 2026-03-04 | PR: TBD |
| T4-11 | 2026-03-04 | PR: TBD |
| T4-12 | 2026-03-04 | PR: TBD |
| T4-13 | 2026-03-04 | PR: TBD |
| T1-10 | 2026-03 | [#259](https://github.com/zafiriss-ux/project-mayhem/pull/259) |
| T1-11 | 2026-03 | [#260](https://github.com/zafiriss-ux/project-mayhem/pull/260) |
| T1-12 | 2026-03 | [#261](https://github.com/zafiriss-ux/project-mayhem/pull/261) |
| T1-13 | 2026-03 | [#264](https://github.com/zafiriss-ux/project-mayhem/pull/264) |
| T1-14 | 2026-03 | [#266](https://github.com/zafiriss-ux/project-mayhem/pull/266) |
| T2-09 | 2026-03 (fully resolved) | [#267](https://github.com/zafiriss-ux/project-mayhem/pull/267), [#268](https://github.com/zafiriss-ux/project-mayhem/pull/268), [#269](https://github.com/zafiriss-ux/project-mayhem/pull/269) |
| T2-10 | 2026-03 | [#271](https://github.com/zafiriss-ux/project-mayhem/pull/271) |
| T2-11 | 2026-03 | [#270](https://github.com/zafiriss-ux/project-mayhem/pull/270) |

| T3-08 | 2026-03 | [#272](https://github.com/zafiriss-ux/project-mayhem/pull/272) |
| T1-15 | ✅ RESOLVED | 2026-03-06 |
| T1-16 | ✅ RESOLVED | 2026-03-06 |
| T1-17 | ✅ RESOLVED | 2026-03-06 |
| T2-12 | ✅ RESOLVED | 2026-03-06 |
| T2-13 | ✅ RESOLVED | 2026-03-06 |
| T3-09 | ✅ RESOLVED | 2026-03-06 |
| T4-14 | ✅ RESOLVED | 2026-03-06 (PR: TBD) |
| T4-15 | OPEN (independent) | — |
| T4-16 | OPEN (independent) | — |
| T4-17 | OPEN (independent) | — |
| T4-18 | ✅ RESOLVED | 2026-03-06 |
| T4-19 | ✅ RESOLVED | 2026-03-06 |
| T4-20 | ✅ RESOLVED | 2026-03-06 |
| T1-18 | OPEN | — |
| T1-19 | OPEN (after T1-18) | — |
| T4-21 | OPEN (independent) | — |
| T4-22 | OPEN (independent) | — |
| T4-23 | OPEN (independent) | — |
| T4-24 | OPEN (independent) | — |
| T4-25 | OPEN (independent) | — |
| T4-26 | OPEN (independent) | — |
| T4-27 | OPEN (independent) | — |
| T4-28 | OPEN (independent) | — |
| T5-04 | OPEN (deferred — Phase 9+) | — |
| T5-05 | OPEN (deferred — Phase 9+) | — |

*This document is the single source of truth for technical debt. Update it when items are
resolved, not in commit messages alone.*

*Last updated: 2026-03-06 — Risk Matrix Architecture Review V6 processed. 11 new items
registered (T1-18, T1-19, T4-21–T4-27, T5-04, T5-05). ADRs 0022–0029 created. Phase
7.9 execution sequence defined. Phase 8 entry gate formalised (ADR-0022).*
