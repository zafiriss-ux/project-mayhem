# TITAN OS — Technical Debt Archive: Tiers 1–3 (All Resolved)

**Archived:** 2026-03-07
**Source:** Extracted from `TECHNICAL_DEBT.md` — all items in Tiers 1, 2, 3 were RESOLVED.
**Purpose:** Historical record. Do not re-open items here — add new findings in `TECHNICAL_DEBT.md`.

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

**Original state (pre-fix):** `except Exception: pass` per HRV day swallows every failure silently.
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

**Original state (pre-fix):** `contextlib.suppress(Exception)` on `ALTER TABLE` statements is correct for
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

**Original state (pre-fix):** `DatabaseManager` uses a single shared SQLite connection with
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

**Original state (pre-fix):** `run_morning_routine_async()` spawns a new daemon thread on every call
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

**Original state (pre-fix):** `_get_baseline_rhr()` wraps all logic in a bare `except Exception: return 50.0`.
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

**Original state (pre-fix):** On weather API failure, the integration fabricates current and forecast
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

**Original state (pre-fix):** These 6 write methods were not in the original T1-10 scope but carry the
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

**Original state (pre-fix):** `training_log` has no stable external identity column for Garmin-sourced
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

**Original state (pre-fix):**

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

**Original state (pre-fix):**

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

**Original state (pre-fix):**

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

### T1-18 · No physiological bounds validation — impossible sensor values flow into governance gates ✅ RESOLVED 2026-03-07

**Status:** ✅ RESOLVED 2026-03-07. Commit: `393af84`.
**Source:** Master Risk Matrix — Risk #9 (Physiological Edge-Case Fragility). Architecture Review 2026-03-06. ADR-0023.
**Priority:** P1 (Tier 1 — safety critical). Data integrity.

**Location:** `titan/science/` (new module) + `titan/core/database.py` (`get_daily_metrics`, `get_training_load_history`).

**Original state (pre-fix):**

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

**Resolution update (2026-03-07):** Extended the physiological input contract to the
remaining consumed DB→engine fields (`weight_kg`, `training_load`, `sleep_hours`) and
validated same-day Garmin physiological payload values in `DailyCoach._persist_garmin_data()`
before readiness/governance/planning consumption; added focused regression coverage.

---

### T1-19 · No structural/temporal data sanity validation — cross-field anomalies enter DB silently ✅ RESOLVED 2026-03-07

**Status:** ✅ RESOLVED 2026-03-07. Commit: `23d0084`.
**Source:** Master Risk Matrix — Risk #10 (Input Data Sanity). Architecture Review 2026-03-06. ADR-0026.
**Priority:** P1 (Tier 1 — data integrity).

**Original state (pre-fix):** Structurally corrupt Garmin data (e.g., `max_hr < avg_hr`, future
timestamps, `distance_km > 0` with `duration_seconds = 0`) was written to the database without
validation. Stale data (last sync >72h) was used as current without a freshness flag.

**Resolution:**

Three layers implemented per ADR-0026:

1. **Layer 1** — `titan/science/data_sanity.py`: `DataSanityChecker` with `check_activity()`,
   `check_daily_metrics()`, `check_hrv()`. Integrated into `DailyCoach._persist_garmin_data()`.
   Reject-severity violations skip the record; warn-severity writes with `quality_flag="degraded"`.
2. **Layer 2** — Temporal freshness check in `DailyCoach._hydrate_engines_from_db()`.
   `STALE_DATA_WARN_HOURS=24h` → `data_freshness_warn`; `STALE_DATA_HARD_CEILING_HOURS=72h` →
   `data_confidence_low` advisory (`confidence["freshness"] = False`).
3. **Layer 3** — Schema v3 migration: `quality_flag TEXT` column added to `daily_metrics` and
   `training_log`. `get_last_garmin_sync_timestamp()` added to `DatabaseManager`.

36 new tests in `tests/test_data_sanity.py` (structural + DB integration), plus focused
orchestration/data-sanity coverage for duplicate activity IDs and HRV temporal sanity at
persist time. Test suite: 1626 passed, 1 skipped as of closure. ruff: 0 findings.

**Effort:** ~4h. New module + 3-point integration + migration + tests.

---

### T1-20 · Garmin connectivity failure has no staleness gate — DailyCoach silently operates on stale data ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: 92f7961 (merged via PR #302 in e79ecb7).
**Source:** Risk Review V7 — Risk: External Dependency Fragility (SPOF). Architecture Review 2026-03-06. ADR-0030.
**Priority:** P1 (Tier 1 — data integrity).

**Location:** `titan/orchestration/daily_coach.py` (Step 2 — data hydration), `titan/integrations/garmin_sync.py` (sync outcome recording), `titan/core/database.py` (sync metadata storage), `titan/config/thresholds.py` (new constants).

**Original state (pre-fix):**

If the Garmin Connect API becomes unavailable (auth failure, library breaking change,
network error), the Garmin sync daemon logs the error but does not set any
governance-visible flag. `DailyCoach` continues running morning routines using the
last-synced SQLite data. After 26+ hours without a successful sync, the governance
engine evaluates gates on data that may no longer reflect the athlete's current state.
The T2-10 data-confidence gate runs at startup only and does not produce a persistent
`garmin_data_stale` flag for continuous operation.

This is structurally identical to the weather degraded-mode gap resolved in T1-09,
but for the primary physiological data source.

**Fix direction (per ADR-0030):**

1. Add `GARMIN_DATA_MAX_AGE_HOURS = 26` to `titan/config/thresholds.py`.
2. Record each sync attempt outcome (`success` / `failure + error_class + timestamp`)
   to the database (new `sync_metadata` table or existing `daily_metrics` metadata
   column — simplest approach: add `last_garmin_sync_ts` and `last_garmin_sync_ok`
   columns via `_run_migrations()`).
3. In `DailyCoach` Step 2, compute Garmin data age. If age > `GARMIN_DATA_MAX_AGE_HOURS`:
   - Emit `garmin_data_stale` structured event (CRITICAL severity, per AGENTS.md §16.6).
   - Set `garmin_data_stale = True` on coaching context.
   - Engage ADR-0020 degraded conservative mode: cap recommendation at "easy
     maintenance only".
   - Send Telegram alert via T3-09 fallback-aware gateway.
4. Add `tests/test_garmin_staleness_gate.py` (mock stale sync timestamp → assert
   degraded mode engaged + correct governance output).

**Acceptance gate (binary):**
```bash
ruff check titan/orchestration/daily_coach.py titan/integrations/garmin_sync.py \
            titan/core/database.py titan/config/thresholds.py \
            tests/test_garmin_staleness_gate.py
python -m pytest tests/test_garmin_staleness_gate.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~3h. DB migration + DailyCoach integration + governance context update + tests.

---

### T1-21 · Governance gates H2/H3 fire without distinguishing training-stress from non-training-stress — illness pattern indistinguishable from life stress ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `72abbc8`.
**Source:** Risk Review V8 — Risk: Non-Training Stress Protocol. ADR-0037.
**Priority:** P0 (Tier 1 — safety-critical).

**Location:** `titan/science/governance_engine.py` (H2/H3 gate evaluation), `titan/config/thresholds.py` (new constants), `titan/orchestration/daily_coach.py` (coaching context).

**Original state (pre-fix):**

HRV and RHR respond to all stressors — training, illness, life stress, travel, and
more. When H2 (`HARD_STOP_HRV_DELTA`) or H3 (`HARD_STOP_RHR_DELTA`) fires, the
current governance engine applies a single response regardless of cause. An athlete
with a depressed HRV from a stressful workday receives the same "easy maintenance"
recommendation as an athlete in genuine overreaching. More critically, an athlete
showing an illness pattern (both HRV and RHR simultaneously outside threshold, without
ACWR elevation) receives "easy maintenance" when full rest is clinically appropriate.
This is a safety gap — not merely a communication gap.

**Fix direction (per ADR-0037):**

1. Add to `thresholds.py`:
   ```python
   ILLNESS_PATTERN_HRV_DELTA = 20.0   # ms — dual-signal illness threshold
   ILLNESS_PATTERN_RHR_DELTA = 10.0   # bpm — must exceed alongside HRV for ILLNESS_PATTERN
   ```
2. In `governance_engine.py` after H2/H3 fire, run `classify_hrv_stress_context()`:
   - Compare ACWR vs `VO2_ACWR_MAX` to determine if training explains the signal.
   - If both HRV and RHR exceed illness thresholds without ACWR elevation: classify
     as `ILLNESS_PATTERN` → recommend full rest.
   - If HRV exceeds threshold without ACWR elevation (but RHR is within illness
     threshold): classify as `UNEXPLAINED_MODERATE`.
   - If ACWR elevation explains the signal: `TRAINING_EXPLAINED` (no change to
     existing response).
3. Update coaching context with `hrv_stress_context` field.
4. Update Telegram briefing to include stress context in coaching message.
5. Add `tests/test_non_training_stress_partition.py` covering:
   - `ILLNESS_PATTERN`: both deltas high, ACWR normal → full rest recommended
   - `UNEXPLAINED_MODERATE`: HRV delta high only, ACWR normal → easy maintenance
   - `TRAINING_EXPLAINED`: ACWR elevated, HRV delta high → existing H2/H3 behaviour

**Acceptance gate (binary):**
```bash
ruff check titan/science/governance_engine.py titan/config/thresholds.py \
            tests/test_non_training_stress_partition.py
python -m pytest tests/test_non_training_stress_partition.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~3h. Governance post-gate classifier + context field + message template + tests.


**Resolution:**

Implemented ADR-0037 non-training stress protocol with explicit stress-context
classification and traceability. Added illness-pattern thresholds to
`titan/config/thresholds.py`, added `classify_hrv_stress_context()` and structured
classification events in `titan/science/governance_engine.py`, surfaced
`hrv_stress_context` through orchestration payload contracts and DailyCoach Telegram
payload, and displayed stress context in `titan/integrations/telegram_bot.py`. Added
new partition coverage in `tests/test_non_training_stress_partition.py`, plus orchestration
payload coverage in `tests/titan/orchestration/test_daily_coach.py` and updated
`test_core_modules.py` assertions to reflect the explicit illness-pattern override path.
Final gate snapshot at closure: 1652 tests passing.

---

### T1-22 · OutcomeTracker schema lacks feedback-loop guardrails — calibration data at risk of circular validation bias ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `d5b9f40`.
**Source:** Risk Review V8 — Risk: Feedback Loop Corruption. AGENTS.md §16.7.
**Priority:** P1 (Tier 1 — data integrity; must be resolved before T5-05 calibration logic is implemented).

**Location:** `titan/science/outcome_tracker.py`, `titan/core/database.py` (schema migration), `titan/config/thresholds.py` (new constants).

**Original state (pre-fix):**

`OutcomeTracker` stores governance decision→outcome pairs for future Phase 9 calibration.
However the current schema captures no information about:
1. Whether the athlete followed the governance recommendation or overrode it.
2. Whether the outcome was recorded within an independence window (ruling out
   confounding from the pre-session physiological state that also produced the decision).
3. What algorithm versions were active when the decision was made.

Without these guardrails, Phase 9 calibration will train on a dataset where:
- Override outcomes (survivorship-biased: successful overrides are over-represented)
  are mixed with followed-governance outcomes.
- The system may "learn" to validate its own conservative bias (see AGENTS.md §16.7).
- Algorithm version mixing will produce heterogeneous training data.

**Fix direction (per AGENTS.md §16.7):**

1. Schema migration: add columns to `governance_outcomes`:
   ```sql
   decision_was_followed     INTEGER NOT NULL DEFAULT 1
   override_outcome_exclusion INTEGER NOT NULL DEFAULT 0
   outcome_independence_ok   INTEGER NOT NULL DEFAULT 1
   algorithm_version_snapshot TEXT  -- JSON: {"governance_engine": "x.y.z", ...}
   ```
2. Add to `thresholds.py`:
   ```python
   OUTCOME_INDEPENDENCE_WINDOW_DAYS = 2
   CALIBRATION_MAX_THRESHOLD_DELTA_PCT = 0.10
   CALIBRATION_MIN_OUTCOME_COUNT = 10
   ```
3. Update `OutcomeTracker.record_outcome()` to:
   - Accept `decision_was_followed` flag (passed from override workflow, ADR-0012).
   - Validate independence window; reject and log if window not met.
   - Populate `algorithm_version_snapshot` from active MODULE_VERSIONs (T4-30 prerequisite
     for full population; stub acceptable until T4-30 closes).
4. Add `tests/test_outcome_tracker_guardrails.py`:
   - Override outcome correctly sets `decision_was_followed = 0` and
     `override_outcome_exclusion = 1`.
   - Outcome within independence window rejected with structured event.
   - Calibration diversity check gate (≥20% high-intensity, ≥10% HARD_STOP outcomes).

**Acceptance gate (binary):**
```bash
ruff check titan/science/outcome_tracker.py titan/core/database.py \
            titan/config/thresholds.py tests/test_outcome_tracker_guardrails.py
python -m pytest tests/test_outcome_tracker_guardrails.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~4h. Schema migration + OutcomeTracker update + calibration diversity gate + tests.

**Resolution:**

Implemented OutcomeTracker feedback-loop guardrails within existing module boundaries.
Added threshold constants, DB schema migration v5 for guardrail metadata, and
outcome recording flags (`decision_was_followed`, `override_outcome_exclusion`,
`outcome_independence_ok`, `algorithm_version_snapshot`). Calibration summary
and lock/outcome correlations now exclude non-independent and override-derived
outcomes from reuse while preserving existing valid-path behavior when no
independence timestamp is provided. Added guardrail-focused tests in
`tests/test_outcome_tracker_guardrails.py` and persistence coverage updates in
`tests/test_outcome_tracker_persistence.py`. Final gate snapshot at closure:
1655 tests passing.

---

### T1-23 · No unified DataTrustLevel contract — external data sources emit ad-hoc trust signals not visible to governance ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `97dc41f`.
**Source:** Architect Directive V8 — Decision 2 (Unified Data Health Check). ADR-0041.
**Priority:** P0 (Tier 1 — data integrity; IMMEDIATE; Phase 8 integration blocked without this).

**Location:** New `titan/science/data_trust.py`, `titan/orchestration/daily_coach.py`
(coaching context update), `titan/integrations/garmin_sync.py` (trust emitter),
`titan/integrations/weather.py` (trust emitter), `titan/config/thresholds.py`.

**Original state (pre-fix):**

Three ADRs (0023, 0026, 0030) address data validation at different boundaries but each
produces a different ad-hoc signal. There is no unified `DataTrustLevel` type that all
downstream consumers (governance engine, weekly planner, Telegram briefing) can check
in a single place. Adding a new data source in Phase 8 requires re-inventing the
validation pattern from scratch — the default answer is "add a log line and move on,"
which is how silent errors accumulate. See ADR-0041 for the full failure mode.

**Fix direction (per ADR-0041):**

1. Create `titan/science/data_trust.py`:
   ```python
   class DataTrustLevel(Enum):
       TRUSTED = "TRUSTED"
       SUSPECT = "SUSPECT"
       INVALID = "INVALID"

   @dataclass
   class DataTrustReport:
       source: str
       trust_level: DataTrustLevel
       reasons: list[str]
       checked_at: str
       data_age_hours: float
   ```
2. Add to `thresholds.py`:
   ```python
   GARMIN_DATA_SUSPECT_AGE_HOURS = 12   # gap between T1-20 thresholds
   WEATHER_DATA_SUSPECT_AGE_HOURS = 2
   ```
3. Update `garmin_sync.py` and `weather.py` to emit `DataTrustReport` alongside data.
4. Map existing validation signals to `DataTrustLevel` (per ADR-0041 mapping table).
5. Add `coaching_ctx["data_trust"]` with per-source reports and `overall` level.
6. Governance engine reads `overall == INVALID` → engage ADR-0020 degraded mode.
   `overall == SUSPECT` → add caveat to coaching message.
7. Add `tests/test_data_trust_contract.py`:
   - Garmin data fresh + valid → `TRUSTED`
   - Garmin data > 12h → `SUSPECT`
   - Garmin data > 26h → `INVALID`
   - Bounds violation (ADR-0023) → `INVALID`
   - Structural inconsistency (ADR-0026) → `INVALID`
   - Weather synthetic fallback → `SUSPECT`

**Acceptance gate (binary):**
```bash
ruff check titan/science/data_trust.py titan/integrations/garmin_sync.py \
            titan/integrations/weather.py titan/orchestration/daily_coach.py \
            titan/config/thresholds.py tests/test_data_trust_contract.py
python -m pytest tests/test_data_trust_contract.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~4h. New module (~30 lines) + 2 emitter updates + coaching context + tests.

**Resolution:**
- Added unified trust contract in `titan/science/data_trust.py` with `DataTrustLevel`, `DataTrustReport`, and narrow evaluators for Garmin and weather trust.
- Wired Garmin and weather emitters to include trust reports and propagated aggregate trust through DailyCoach context/payload without changing recommendation logic outside trust caveat exposure.
- Added/updated tests for contract, emitters, and orchestration propagation. Final gate snapshot at closure: 1671 tests passing.

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

**Original state (pre-fix):** Despite T2-01 through T2-08 fixing the most critical error taxonomy paths,
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

**Original state (pre-fix):** `_hydrate_engines_from_db()` runs synchronously at startup, loading HRV
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

**Original state (pre-fix):** When the Telegram bot is unavailable (missing token, library not installed,
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

**Original state (pre-fix):** Both are in `titan/ui/` — where `print()` is permitted per ADR-0019 Decision 3.
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

**Original state (pre-fix):**

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

### T2-14 · Structured events lack severity levels; Telegram alert deduplication absent; no operational runbook ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: TBD.
**Source:** Risk Review V7 — Risk: Observability Overload. Architecture Review 2026-03-06. AGENTS.md §16.6.
**Priority:** P2 (Tier 2 — observability sustainability).

**Location:** All modules using `_emit_structured_event()` (~12 modules), `titan/integrations/telegram_bot.py`, `titan/main.py` (log rotation), `docs/operations/RUNBOOK.md` (new file).

**Original state (pre-fix):**

Phases 3–4 added structured event emission throughout the codebase. Without a severity
classification, all events are treated identically — Telegram receives both routine
`activity_synced` telemetry and critical `HARD_STOP_HRV_DELTA` governance events. A
recurring governance condition (e.g., H2 firing every morning for a training block)
sends the same identical Telegram message daily, causing alert fatigue. There is no
log rotation policy and no operational runbook for responding to critical events.

**Resolution:**

Implemented shared structured-event severity payload support via `EventSeverity` and propagated severity-enabled structured event helpers across orchestration/integration/science/core modules that emit observability events. Added Telegram CRITICAL alert deduplication keyed by `(event_type, lock_code)` with a 20h suppression window and 72h persistence summary behaviour, then wired stale Garmin-data alerting through the deduplicated path. Added rotating log file handler configuration in `titan/main.py` (`LOG_MAX_BYTES=10MB`, `LOG_BACKUP_COUNT=5`). Added/updated tests for severity payload contract, dedup suppression, persistence summaries, and rotating logging configuration. Final closure suite count: 1678 tests green.

**Fix direction (three parts per AGENTS.md §16.6):**

1. **Severity classification:** Add `EventSeverity` enum to a shared module. Extend
   `_emit_structured_event()` signature with `severity` parameter (default: `INFO` for
   backward compatibility). Classify all existing event types (CRITICAL / WARNING /
   INFO / DEBUG — see AGENTS.md §16.6 table). Update ~12 call sites mechanically.
2. **Alert deduplication:** In the Telegram gateway, maintain a deduplication dict
   (in-memory, keyed by `(event_type, lock_code)`) with TTL = `ALERT_DEDUP_WINDOW_HOURS`
   (default: 20h). After `ALERT_PERSIST_SUMMARY_HOURS` (default: 72h) of the same
   condition, send a summary message instead of silence.
3. **Operational runbook:** Create `docs/operations/RUNBOOK.md` with one section per
   CRITICAL event type (all 7 governance gates + ADR-0030 staleness events).
4. **Log rotation:** Configure `RotatingFileHandler` in `titan/main.py`
   (`LOG_MAX_BYTES = 10MB`, `LOG_BACKUP_COUNT = 5`).

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/telegram_bot.py titan/main.py
# (all modified _emit_structured_event call sites)
python -m pytest tests/test_structured_log_sustainability.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Tests required (minimum):**
- `test_critical_event_forwarded_to_telegram` — CRITICAL event → Telegram call made.
- `test_info_event_not_forwarded_to_telegram` — INFO event → no Telegram call.
- `test_dedup_suppresses_repeated_alert` — same CRITICAL event within dedup window → second Telegram call suppressed.
- `test_dedup_sends_summary_after_persist_window` — condition persists >72h → summary message sent.

**Effort:** ~5h. Mechanical severity tagging + gateway dedup logic + runbook + rotation config + tests.

---

### T2-15 · Weather synthetic fallback uses hardcoded location defaults — staleness context absent from governance ✅ RESOLVED 2026-03-07

**Status:** ✅ RESOLVED 2026-03-07. Commit: TBD.
**Source:** Risk Review V7 — Risk: External Dependency Fragility. Architecture Review 2026-03-06. ADR-0030.
**Priority:** P2 (Tier 2 — observability gap; silent wrong input to OptimalTimeCalculator).
**Dependency:** T1-20 must close first (the `weather_data_stale` governance flag established there is consumed here).

**Location:** `titan/integrations/weather.py` (`_create_synthetic_fallback()`) + `titan/features/optimal_time.py`.

**Original state (pre-fix):**

When the Open-Meteo API is unavailable, `_create_synthetic_fallback()` produces a
synthetic weather forecast using hardcoded Athens, GR climatological defaults (T1-09
resolution). If the athlete's `WEATHER_LOCATION` is different (e.g., Helsinki, FI in
winter), the synthetic forecast produces incorrect dew-point and heat-stress inputs to
`OptimalTimeCalculator`. Additionally, the coaching context does not carry a
`weather_confidence = SYNTHETIC` flag, so downstream consumers cannot gate on it.

**Resolution:**

Implemented synthetic weather fallback profiling in `weather_api.py` by deriving baseline
temperature/humidity from configured `WEATHER_LOCATION` with hemisphere-aware season mapping,
then using `_create_synthetic_fallback()` for degraded current conditions and synthetic forecast.
Added `weather_confidence` payload metadata (`LIVE`/`SYNTHETIC`) for current and forecast responses,
plus `weather_synthetic_fallback_activated` warning events (with location context) on fallback activation.
Updated `OptimalTimeCalculator` to honor `weather_confidence`, returning a conservative 06:00–09:00
safe window when confidence is synthetic while preserving existing live-weather optimization flow.
Expanded tests in `tests/titan/integrations/test_weather_api.py` and
`tests/titan/features/test_optimal_time_calculator.py` to cover confidence propagation,
location-sensitive fallback generation, synthetic forecast confidence tagging, and safe-window fallback.
Final closure suite count: 1681 tests green.

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/weather.py titan/features/optimal_time.py \
            tests/test_weather_staleness.py
python -m pytest tests/test_weather_staleness.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~2h. Targeted changes in two modules + tests.

---

### T2-16 · Governance decisions lack human-readable rationale — athletes receive opaque hard-stops without "why"; override rate unmonitored ✅ RESOLVED 2026-03-07

**Status:** ✅ RESOLVED 2026-03-07. Commit: TBD.
**Source:** Risk Review V8 — Risks: Explainability Gap (non-ML), Operator Trust Drift. ADR-0038.
**Priority:** P2 (Tier 2 — observability).
**Dependency:** All Tier 1 items (T1-18 through T1-22) were closed before implementation.

**Location:** `titan/science/governance_engine.py`, `titan/orchestration/daily_coach.py` (Telegram message composition), `titan/ui/operator_console.py` (Session Explorer payload), `titan/config/thresholds.py`.

**Original state (pre-fix):**

When the governance engine fired a hard-stop or downgrade, the athlete received a
Telegram message stating the recommendation but not the cause. The gate that fired,
the input value, the threshold, and the margin from the boundary were absent from
the coaching output. Over time, opaque decisions eroded operator trust — athletes
overrode governance not because they disagreed with the specific decision, but because
they could not evaluate whether the decision was warranted. Override rate was not monitored;
the system could not detect trust erosion.

**Resolution:**

- Added `GateFinding` and `DecisionRationale` dataclasses with `GATE_RATIONALE_TEMPLATES`
  so every governance evaluation emits human-readable rationale and gate findings.
- Included `primary_reason` and `actionable_guidance` in DailyCoach payload and Telegram message output.
- Added Session Explorer `gate_findings` payload and `override_metrics` (30-day rate, trend,
  trust signal, and `operator_trust_drift_warning`).
- Added threshold constant `OPERATOR_TRUST_DRIFT_WARNING_RATE_30D` to centralized thresholds.
- Added/updated tests: `tests/test_governance_rationale.py`,
  `tests/test_operator_console_dashboard.py`,
  `tests/titan/orchestration/test_daily_coach.py`, and
  `tests/titan/integrations/test_telegram_bot_rationale.py`.
- Closure test count: 1687 passed (`python -m pytest -q`).

---

### T2-17 · Metric lifecycle states not tracked — orphaned metrics consume resources without governance contribution; new metrics lack mandatory evidence registry entries ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: 91e0466.
**Source:** Risk Review V8 — Risk: Metric Proliferation Debt. AGENTS.md §16.9.
**Priority:** P2 (Tier 2 — observability).

**Location:** All `titan/science/` engine modules, `titan/config/evidence_registry.py`, `titan/orchestration/daily_coach.py` (coaching context emission).

**Original state (pre-fix):**

TITAN OS computed ~15+ physiological metrics. Several (TRIMP, drift_index,
efficiency_index, biomechanics_score, durability_score) had unclear governance roles —
they were computed but their path to any governance gate, Telegram briefing, or Operator
Console payload was not documented. Without a lifecycle protocol, Phase 8/9 additions
would compound this proliferation. Metrics without evidence registry entries could not be
audited for evidence quality.

**Resolution:**
- Added `METRIC_LIFECYCLE` and `METRIC_LIFECYCLE_STATES` to `titan/config/evidence_registry.py`, including governance, Telegram, Operator Console, and evidence coverage metadata per audited metric.
- Added `get_metrics_under_review()` helper and wired DailyCoach startup to emit a `metrics_under_review` structured event when any audited metric remains `Under Review`.
- Added lifecycle guard tests in `tests/test_metric_lifecycle.py`, module-mirrored coverage in `tests/titan/config/test_evidence_registry.py`, and startup event coverage in `tests/titan/orchestration/test_daily_coach.py`.
- Closure test count: 1692 passed (`python -m pytest -q`).

**Acceptance gate (binary):**
```bash
ruff check titan/config/evidence_registry.py tests/test_metric_lifecycle.py
python -m pytest tests/test_metric_lifecycle.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~4h. Audit (2h) + registry addition + CI check + tests.

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

**Original state (pre-fix):** All three background workers call `thread.join(timeout=5)` and continue
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

**Original state (pre-fix):** The `scheduled_tasks` list is appended and read across execution contexts
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

**Original state (pre-fix):**
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

**Original state (pre-fix):**

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

