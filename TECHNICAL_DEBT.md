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

## TIER 2 — Observability Infrastructure (Sprint 2)

Complete Tier 1 first. These items do not corrupt data but make production incidents
significantly harder to diagnose.

**Rule:** Work one subsystem at a time. Do not attempt to fix all broad `except` handlers
simultaneously — each subsystem needs its own error taxonomy review and test update.

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

### T2-09 · Residual `print()` operational/error paths across integration modules ✅ RESOLVED (weather_api.py)

**Status (2026-03-04):** Completed for `weather_api.py`. Added `_weather_event()` structured
event helper. Replaced all 4 `print()` calls (fallback current, fallback forecast, background
worker error, background updates started) with `_weather_event()` calls at appropriate log
levels (WARNING / ERROR / INFO). `test_weather_api_has_no_print_calls` asserts zero
`print()` in module. Tests: 4 green in `tests/test_harden_db_concurrency.py`. PR: TBD.

Note: `telegram_bot.py`, `garmin_sync.py`, `daily_coach.py` (UI-boundary prints) are
intentionally deferred — those require separate subsystem review per Rule E2.
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

**Status (2026-03-04):** COMPLETED. Escalation after `join(timeout=5)` is implemented and tested for `titan/integrations/garmin_sync.py`: if the worker is still alive, it emits a structured `worker_shutdown_timeout` event at ERROR level with `(worker_name, timeout_seconds, still_alive=true)`, with no forced termination.
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

### T4-10 · Typed payload contracts use broad `Any` — weakens static guarantees 🟡

**Status:** OPEN
**Source:** Engineering audit 2026-03-04 (Architecture observation #3)

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

### T4-13 · No full lifecycle stress test for all background workers together 🟡

**Status:** OPEN
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

All Tier 5 decisions have been locked. See Tracking table for completion dates and PRs.
Relevant ADRs: 0013 (UI path), 0014 (ML scaffold), 0015 (SQLite/multi-athlete), 0016 (multi-sport).

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
| T2-09 | 2026-03-04 (weather_api.py) | PR: TBD |
| T3-06 | 2026-03-04 | PR: TBD |
| T3-07 | OPEN | — |
| T4-07 | OPEN | — |
| T4-08 | OPEN | — |
| T4-09 | 2026-03-04 | PR: TBD |
| T4-10 | OPEN | — |
| T4-11 | 2026-03-04 | PR: TBD |
| T4-12 | OPEN | — |
| T4-13 | OPEN | — |

*This document is the single source of truth for technical debt. Update it when items are
resolved, not in commit messages alone.*
