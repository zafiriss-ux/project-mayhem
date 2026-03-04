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

## TIER 4 — Maintainability (Sprint 4+)

### T4-01 · Ruff debt burn-down (lint hygiene) 🟢

Ruff lint debt burn-down remains open until `ruff check . --statistics` reaches zero findings.
Keep this item open while any findings remain; close only when the burn-down is complete.

---

### T4-02 · Remove confirmed unused imports 🟡

5 confirmed unused imports in production code (not `__init__.py` re-exports):

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

### T4-04 · `titan_ctx` dict → typed context object in `titan/main.py` 🟡

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

*This document is the single source of truth for technical debt. Update it when items are
resolved, not in commit messages alone.*
