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

## TIER 3 — Dependency Hygiene (Sprint 3)

Independent of Tier 2. Can be done in parallel once Tier 1 is complete.

### T3-01 · Split `requirements.txt` into runtime vs build vs dev 🟡

**Current problem:**
- `scikit-learn==1.4.2` — not imported anywhere in `titan/`; legacy from archived monolith
- `pandas==2.2.1` — not imported anywhere in `titan/`; same reason
- `pyyaml==6.0.1` — not imported anywhere in `titan/`
- `pyinstaller==6.4.0` — build tool, not a runtime dep
- `pywin32==306` — Windows-only build dep, not a runtime dep

**Fix:**
```
requirements.txt          → runtime only (garminconnect, requests, pyTelegramBotAPI, numpy)
requirements-dev.txt      → pytest, pytest-cov, hypothesis, ruff, mypy
requirements-build.txt    → pyinstaller, pywin32 (Windows only)
```

**Effort:** ~1h. Reduces fresh-install footprint significantly.

---

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

## TIER 4 — Maintainability (Sprint 4+)

### T4-01 · Ruff debt burn-down (lint hygiene) 🟡

**Current state:** Significant Ruff findings across the codebase, primarily:
- Typing modernisations (`Optional[X]` → `X | None`, `Union[A, B]` → `A | B`)
- Import ordering
- Whitespace / line-length
- Unused imports (5 confirmed in production code — see T4-02)

**Operational closure status:** **OPEN**. Configuration exists in `pyproject.toml`, but
burn-down execution is still pending.

**Latest measured baseline (2026-03-03):** `ruff check . --statistics` reports
**~750 errors** (exact count may shift as files change).

Top categories currently are:
- `UP006` (non-PEP585 annotation)
- `W293` (blank-line-with-whitespace)
- `UP045` (non-PEP604 optional annotation)
- `I001` (unsorted imports)
- `UP035` (deprecated imports)

**Closure criterion:** T4-01 closes only after a substantive subsystem-by-subsystem
reduction of Ruff findings (not only policy/config presence).

**Strategy:** Burn down per subsystem, not all at once. Suggested order:
1. `titan/config/` (smallest, highest reference value)
2. `titan/science/governance_*.py` (policy-critical, high read frequency)
3. `titan/core/`
4. `titan/integrations/` (after Tier 2 error taxonomy work)
5. `titan/orchestration/` + `titan/features/`
6. `titan/ui/`

Add Ruff to CI as a non-blocking warning gate first, then promote to blocking after
each subsystem is clean.

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

## TIER 5 — Future Optionality (Plan now, implement when the time comes)

Do not implement these until Tiers 1–3 are complete. Document the decision now so it
is not made ad-hoc under pressure.

### T5-01 · SQLite retention / archival strategy 🟢

**Current state:** `governance_outcomes` and `training_log` grow indefinitely. No
retention policy exists.

**Decision needed:** Is TITAN OS intentionally single-athlete, single-lifetime?
- If yes: document this as an architectural constraint. SQLite will handle years of data
  for a single athlete without issue.
- If no (multi-athlete Phase 8): define a data lifecycle strategy before Phase 8 begins:
  - Rolling window (keep N months of raw data, archive older)
  - Per-athlete DB files vs single shared DB
  - Archival export format (CSV, JSON, SQLite copy)

This decision gates Phase 8 feasibility. It must be made in an ADR before Phase 8 work starts.

---

### T5-02 · UI evolution path 🟢

**Current state:** Terminal menu system (80s DOS aesthetic, functional, loved).

**Planned path (from ADR-0013):**
- Phase A (terminal facelift): retro-HUD dashboard snapshot on startup; action rail
  (primary / secondary actions); status cards with VLG colour + readiness score
- Phase B: Streamlit operator prototype (rapid; reuses `OperatorConsoleService` payloads directly)
- Phase C: React + FastAPI production (ADR-0013)

**Constraint:** Do not invest in Phase A terminal changes until Tier 1–2 hardening is
complete. The terminal UI is cosmetic; data integrity and observability are not.

---

### T5-03 · Multi-sport scope decision 🟢

**Current state:** `garmin_sync.get_activities_by_date(..., "running")` is hardcoded
to running only.

**Decision needed:** Is multi-sport in scope for Phase 8?
- If yes: design a unified adapter interface before implementing additional sports (Strava,
  Polar, Whoop, COROS already in Phase 8 roadmap)
- If no (longevity running focus): document explicitly to prevent scope creep

---

### T5-04 · ML promotion gates (Phase 7 → Stage 1+) 🟢

Before any Phase 7 engine is promoted from shadow/advisory to athlete-facing:
- `LoadPredictionShadowModel`: ≥30 predictions with RMSE < 10% of actual
- `InjuryRiskEnsembleModel`: recall ≥ 0.80 on holdout; false positive rate < 0.30
- `AutomatedPeriodizationEngine`: ≥10 confirmed suggestions with ≥80% adoption

Each promotion requires:
1. ADR update (evidence label upgrade: HEURISTIC → MODERATE)
2. Kill-switch env var explicitly set to disabled in deployment docs
3. Operator Console calibration review showing promotion readiness

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
| (open) | — | — |

*This document is the single source of truth for technical debt. Update it when items are
resolved, not in commit messages alone.*
