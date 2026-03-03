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

### T1-01 · Wrong Telegram library in `requirements.txt` 🔴

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

### T1-02 · HRV silent data loss in `garmin_sync.py` 🔴

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

### T1-03 · Migration observability gap in `database.py` 🔴

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

### T1-04 · Hardcoded safety thresholds bypassing `thresholds.py` 🟠

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

**Effort:** ~30 minutes. Zero behaviour change — values are currently identical.

---

### T1-05 · Dead duplicate ACWR constants in `constants.py` 🟠

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

### T2-01 · Error taxonomy: `garmin_sync.py` 🟠

**Current state:** Most failures result in `print()` + broad `except Exception`.
Cannot distinguish `auth_failed` / `rate_limited` / `payload_malformed` / `timeout` /
`api_unavailable` from log output alone.

**Fix direction:**
- Define failure classes as constants: `GARMIN_AUTH_FAIL`, `GARMIN_RATE_LIMIT`,
  `GARMIN_PAYLOAD_MALFORMED`, `GARMIN_TIMEOUT`, `GARMIN_API_UNAVAILABLE`
- Route every `except` to the appropriate class + emit `_garmin_event(failure_class, ...)`
- User-facing messages can remain friendly; structured log line must be machine-readable

**Subsystem coverage:** `sync_activities`, `sync_weight`, `sync_sleep`, `sync_hrv`

---

### T2-02 · Error taxonomy: `daily_coach.py` 🟠

**Current state:** `DailyCoach._run_morning_routine()` has multiple broad catch + print
patterns across the 12 steps. Step-level failures are not distinguishable in logs.

**Fix direction:**
- Step-level structured events: `(step_number, step_name, outcome, failure_class)`
- Failure classes: `DATA_MISSING`, `ENGINE_ERROR`, `PERSIST_ERROR`, `DELIVERY_ERROR`
- Persist path should emit `ACTIVITY_PERSISTED` / `ACTIVITY_SKIPPED` per activity

---

### T2-03 · Error taxonomy: `telegram_bot.py` 🟠

**Current state:** Init/send/poll/scheduler paths have print-only handling in several
failure branches. Structured `_telegram_event()` exists for critical failures but is
not consistently used.

**Fix direction:**
- Apply `_telegram_event()` to all failure paths (not just SLO-critical ones)
- Failure classes: `SEND_FAIL`, `POLL_FAIL`, `SCHEDULER_DRIFT`, `CALLBACK_ERROR`

---

### T2-04 · Error taxonomy: `governance_engine.py` 🟠

**Current state:** `check_override_lockdown()` has a bare `except Exception` that hides
DB failure classes.

**Fix direction:**
- Distinguish `DB_READ_ERROR` from `COMPUTATION_ERROR` from `SCHEMA_MISMATCH`
- Override lockdown failures should be conservative: fail safe (treat as lockdown active)
  and emit a structured alert

---

### T2-05 · JSON guard for DB governance rows in `database.py` 🟠

**Location:** `titan/core/database.py` — `get_governance_decisions()`

`json.loads()` is called directly on `locks_applied_json` and similar columns without a
fallback. A single malformed row (manual DB edit, schema migration edge case, legacy data)
will raise and abort the entire read, losing all governance history access.

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

### T2-06 · Athlete load error detail in `database.py` 🟠

**Location:** `titan/core/database.py` or `AthleteDatabase.load_all()`

Broad `except` on file load silently skips corrupted athlete files with a warning.
Field-level reason is not captured, making forensic diagnosis of partial corruption
impossible.

**Fix direction:** Log `(filename, error_class, error_message, field_hint)` per skip.

---

### T2-07 · Launcher and startup error path observability 🟠

**Location:** `main.py`, `titan/main.py`, integration init paths (`titan/integrations/garmin_sync.py` `connect()`, `titan/integrations/telegram_bot.py` `__init__()`)

**Current state:** Launch-time errors in the startup guard and integration init paths emit `print()` rather than structured log events. Startup failures are indistinguishable from runtime failures in aggregated log output, degrading incident RCA accuracy.

**Fix direction:**
- Replace `print(f"Error: ...")` in startup/init paths with `log.error("startup_failure", component=..., error_class=..., detail=...)`
- Applies to: `main.py` startup guard, `GarminSync.connect()` auth failure path, `TitanTelegramBot.__init__()` token validation failure
- User-facing friendly messages may remain; each must be paired with a machine-readable structured event

**Effort:** ~2h. Surgical; no architecture change.

---

### T2-08 · Residual broad catches in DB best-effort branches 🟠

**Location:** `titan/core/database.py` — init and non-migration best-effort paths

**Current state:** Beyond T2-05 (JSON guard on governance rows) and T2-06 (athlete file load detail), additional broad `except Exception` clauses exist in DB init and best-effort load paths. These silently absorb failure classes beyond their intended idempotency guard, hiding error categories from operators.

**Fix direction:**
- Audit all `except Exception` / bare `except` clauses in `database.py` outside of `_run_migrations()` (already scoped in T1-03)
- Narrow each to the minimal expected exception type
- Emit a structured log event for any catch that survives narrowing
- Conservative default: when uncertain, emit a warning and re-raise

**Works best after:** T1-03 and T2-05 complete (they establish the narrowing pattern for this file).

**Effort:** ~2h.

---

## TIER 3 — Dependency Hygiene (Sprint 3)

Independent of Tier 2. Can be done in parallel once Tier 1 is complete.

### T3-02 · Add `ruff` and `mypy` to dev requirements 🟡

**Current problem:** `pyproject.toml` has full `[tool.ruff]` and `[tool.mypy]`
configurations but neither appears in `requirements.txt`. They must be installed
separately, which breaks reproducible dev environments.

**Fix:** Add to `requirements-dev.txt` (after T3-01) or to current `requirements.txt`
dev section:
```
ruff>=0.3.0
mypy>=1.9.0
```

---

### T3-03 · Secrets handling simplification in `garmin_sync.py` + `telegram_bot.py` 🟡

**Current problem:** Both files maintain credentials in multiple representations
simultaneously (`self.email` plain string, `_Secret` wrapper, `SecretStr` wrapper).
This creates:
- Maintenance confusion about which representation is "live"
- Risk of accidentally logging the wrong one
- Unnecessary memory duplication of sensitive values

**Fix direction:** One canonical `_Secret` container per credential. Remove redundant
aliases.

---

### T3-04 · Threading lifecycle: use `threading.Event` for clean stop 🟡

**Affected:** `garmin_sync.py` background worker, `telegram_bot.py` scheduler

**Current problem:** Background workers sleep in second-by-second loops checking a
boolean flag. Stop latency equals sleep granularity (1s). In long-interval scenarios,
this is fine, but it cannot guarantee deterministic shutdown order for clean teardown.

**Fix direction:**
```python
self._stop_event = threading.Event()
# Instead of: time.sleep(1); if self._stop_flag: break
# Use:        self._stop_event.wait(timeout=1.0); if self._stop_event.is_set(): break
```

Optionally add `thread.join(timeout=5)` in the shutdown path.

---

### T3-05 · Threading lifecycle: weather updater `Event.wait()` pattern 🟡

**Affected:** `titan/integrations/weather_api.py` background update loop

**Current state:** T3-04 applied `threading.Event` to the Garmin sync and Telegram scheduler workers. The weather background update loop was not included and continues to use a boolean flag + `time.sleep(1)` second-by-second polling pattern, making its shutdown less deterministic than the other two workers.

**Fix direction:** Apply the identical pattern from T3-04:
- Replace the boolean stop flag with `self._stop_event = threading.Event()`
- Replace the inner `time.sleep(interval)` with `self._stop_event.wait(timeout=interval_seconds)`
- In `stop()`: call `self._stop_event.set()` before joining the thread

**Independent:** Can proceed immediately; no dependency on T3-01 through T3-04.

**Effort:** ~30 minutes. Mirrors T3-04 exactly.

---

## TIER 4 — Maintainability (Sprint 4+)

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

### T4-03 · Typed payload contracts at critical boundaries 🟡

**Current state:** The orchestration pipeline relies on loose `dict` contracts between
subsystems (`garmin_data`, `today_session`, `titan_ctx`). This works at current scale
but creates key-mismatch / implicit-contract risk as the system grows.

**Fix direction:**
- Define lightweight `@dataclass` or `TypedDict` schemas for the 3–4 most critical
  inter-layer payloads
- Start with `GarminSyncResult` (already partially structured) and `DailyCoachContext`
- Do NOT attempt a full typed migration in one pass

---

### T4-04 · `titan_ctx` dict → typed context object in `titan/main.py` 🟡

The large `titan_ctx` dict in the entrypoint accumulates keys across subsystems with no
type contract. Future key additions are invisible to static analysis.

Depends on T4-03 (start smaller, work up to main context object).

---

### T4-05 · Architecture change lock for `governance_engine.py` 🟡

**Current gap:** There is no process-level protection preventing changes to
`governance_engine.py` without architectural review. This module is the sole
non-bypassable safety gate; a well-intentioned "quick fix" here can silently degrade
system safety.

**Fix direction:**
- Add a CODEOWNERS entry for `titan/science/governance_engine.py` requiring explicit
  review sign-off
- Add a comment header to the file: `# ARCHITECTURE LOCK — see ADR-0009 before modifying`
- Consider a CI lint check that fails if `governance_engine.py` is modified without
  a corresponding ADR reference in the commit message

---

### T4-06 · Doc freshness maintenance process 🟡

**Risk (28%):** Historical metric snapshots embedded in closed debt entries (error counts, test counts, date-bound measurements) drift out of sync with the actual codebase state over time. Without explicit date-annotation, future contributors may treat recorded closure measurements as current readings, leading to incorrect triage decisions.

**Fix direction:**
- **Annotation policy:** Any closed item containing a numeric baseline or measurement must carry an explicit date annotation and a note that the value is a historical closure snapshot, not a live reading. Use "as of [date] at closure" — never "currently X".
- **Review checkpoint:** At the close of each phase sprint, scan `TECHNICAL_DEBT.md` for stale present-tense measurements and annotate or remove them.
- **Forbidden language in closed items:** Avoid present-tense claims ("currently X errors", "currently are"). Use past-tense or explicitly dated language.

**Immediate action applied (2026-03-03):** T4-01 historical error-category list re-annotated as a pre-closure snapshot (see T4-01 above).

**Effort:** ~1h for initial policy pass; ~15 min per sprint close for ongoing maintenance.

---

## TIER 5 — Future Optionality

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
- **All tests passing** (1122 green, 100% coverage on governance + Phase 7 modules) ✅

---

## Tracking

When an item is completed, mark it here with date and PR reference:

| Item | Completed | PR |
|---|---|---|
| T3-01 | 2026-03-03 | [#172](https://github.com/zafiriss-ux/project-mayhem/pull/172) |
| T4-01 | 2026-03-03 | [#167](https://github.com/zafiriss-ux/project-mayhem/pull/167) |
| T5-01 | 2026-03-03 | [#173](https://github.com/zafiriss-ux/project-mayhem/pull/173), [#174](https://github.com/zafiriss-ux/project-mayhem/pull/174), [#175](https://github.com/zafiriss-ux/project-mayhem/pull/175) |
| T5-02 | 2026-03-03 | [#169](https://github.com/zafiriss-ux/project-mayhem/pull/169) |
| T5-03 | 2026-03-03 | [#170](https://github.com/zafiriss-ux/project-mayhem/pull/170) |
| T5-04 | 2026-03-03 | [#171](https://github.com/zafiriss-ux/project-mayhem/pull/171) |

*This document is the single source of truth for technical debt. Update it when items are
resolved, not in commit messages alone.*
