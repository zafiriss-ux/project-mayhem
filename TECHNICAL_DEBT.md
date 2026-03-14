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
  T4-18 (independent — governance mutation test suite; AGENTS.md §16.1)
  T4-19 (independent — architectural invariant test suite)
  T4-20 (independent — PR template + architecture checklist)
```
T1-16, T1-17, T3-09, T4-18, T4-19, T4-20 are marked `independent`.
T2-13 is independent of T2-12 but depends on T1-15.
Do not start Tier N+1 while any Tier N item is OPEN (Rule E1).

**Phase 7.9 execution sequence (per Risk Matrix Architecture Review 2026-03-06 + Risk Review V7 2026-03-06 + Risk Review V8 2026-03-06 + Architect Directive V8 2026-03-06):**
```
⚠️  ARCHITECT INVARIANTS — effective immediately, all phases (ADRs 0040–0042):
    AGENTS.md §16.10: Athlete identity isolation — new code must comply from this commit
    ADR-0041: DataTrustLevel contract — new data sources require trust emitter
    ADR-0042: Human override required — every recommendation type needs override handler

TIER 1 (data integrity — must complete before any Tier 2 items in Phase 7.9+):
  T1-18 (physiological input validation contract; ADR-0023)
  T1-19 (structural + temporal data sanity layer; ADR-0026; after T1-18)
  T1-20 (Garmin connectivity staleness gate; ADR-0030; independent)
  T1-21 (non-training stress safety partition — H2/H3 illness vs. life-stress; ADR-0037; independent)
  T1-22 (OutcomeTracker feedback-loop guardrails — schema + independence window; AGENTS.md §16.7; independent)
  T1-23 (unified DataTrustLevel contract + data_trust.py module; ADR-0041; independent)

TIER 2 (observability — after all Tier 1 pass):
  T2-14 (structured event severity + alert deduplication + runbook; AGENTS.md §16.6)
  T2-15 (weather synthetic fallback: location context + governance flag; ADR-0030; after T1-20)
  T2-16 (governance decision rationale + override-rate monitoring; ADR-0038; after all Tier 1)
  T2-17 (metric lifecycle audit + evidence registry coverage; AGENTS.md §16.9; independent)

TIER 4 (maintainability — independent; can run in parallel after Tier 1–3 close):
  T4-21 (documentation consistency CI checks; AGENTS.md §16.3)
  T4-22 (agent context continuity + CLAUDE.md integrity; AGENTS.md §16.4)
  T4-23 (property-based test expansion for science engine edge cases)
  T4-24 (test fixture factory — eliminate fixture drift)
  T4-25 (dependency drift: automated CI audit for unpinned/stale deps)
  T4-26 (module boundary TypedDict contracts + coupling invariant test; ADR-0027)
  T4-27 (complexity budget CI check: module count ceiling; AGENTS.md §16.11)
  T4-28 (context snapshot generator + multi-agent protocol; AGENTS.md §16.5)
  T4-30 (science module semantic versioning — MODULE_VERSION constants + CI; AGENTS.md §16.8; independent)
  T4-31 (athlete isolation invariant CI check — exemption register + comment annotations; AGENTS.md §16.10; IMMEDIATE)
  T4-32 (override handler registry + Telegram inline override button; ADR-0042; IMMEDIATE)

TIER 5 (future / Phase 8+):
  T5-06 (ML advisory explainability contract; ADR-0032; T5-06-A is Phase 8A early work — complete before Phase 8B begins)
  T5-07 (model calibration metadata table + adaptation drift detection; ADR-0033; ✅ Layers 1–2 RESOLVED 2026-03-13; Layer 3 deferred Phase 9)
  T5-14 (ESI environmental compensation overlay for training zones; ADR-0034; Phase 8 scheduled)
```
T1-20, T1-21, T1-22, T1-23 are marked `independent` (no ordering dependency between them).
T4-21 through T4-28 are marked `independent`. T4-30, T4-31, T4-32 are marked `independent`.
T4-31 and T4-32 are marked `IMMEDIATE` — they enforce AGENTS.md §16.10/0042 invariants that are effective
from this commit forward. They require no new Phase boundary to begin.
T1-23 is a Phase 8 entry gate criterion (AGENTS.md §16.2 updated retroactively).
T5-14 (formerly T4-29) is Phase 8 scheduled work (low-blast-radius ESI overlay; no schema changes required). Reclassified from Tier 4 to Tier 5 on 2026-03-07 to clear G1 of the Phase 8 entry gate — it is Phase 8 internal work, not a Phase 8 prerequisite.
T2-17 is marked `independent` (can run concurrently with other Tier 2 items after Tier 1 closes).
T5-06-A (`InjuryRiskEnsembleModel` explainability) is **Phase 8A early work** — must be RESOLVED
before Phase 8B coach-dashboard work begins. (Note: G1 of the Phase 8 entry gate covers only
Tier 1–4 items; T5-06-A is Tier 5 and did not block Phase 8 entry. Phase 8 is now OPEN.)
T5-07 Layer 1 & 2 (model age tracking + drift detection) ✅ RESOLVED 2026-03-13 (commit: b6bea2a). SQLite schema migration in place; Alembic migration remains tracked as T5-08-B D5.
Phase 8 OPEN — all G1–G11 cleared 2026-03-08. See AGENTS.md §16.2 and ADR-0022 for gate record.

---

## TIER 1 — Data Integrity (All Resolved ✅)

All 23 Tier 1 items (T1-01 through T1-23) are **RESOLVED**.
Full history: [`archive/technical_debt_t1_t3_resolved.md`](archive/technical_debt_t1_t3_resolved.md)

| # | Item | Resolved |
|---|------|----------|
| T1-01 | Wrong Telegram library in requirements.txt | 2026-03-02 |
| T1-02 | HRV silent data loss in garmin_sync.py | 2026-03-02 |
| T1-03 | Migration observability gap in database.py | 2026-03-02 |
| T1-04 | Hardcoded safety thresholds bypassing thresholds.py | 2026-03-02 |
| T1-05 | Dead duplicate ACWR constants in constants.py | 2026-03-02 |
| T1-06 | DB concurrency: read paths unguarded + close() race | 2026-03-04 |
| T1-07 | DailyCoach daemon overlap — run_morning_routine_async() unserialised | 2026-03-04 |
| T1-08 | Silent hardcoded fallback in _get_baseline_rhr() | 2026-03-04 |
| T1-09 | Synthetic weather fallback without degraded-mode gate | 2026-03-04 |
| T1-10 | DB write methods: cursor outside lock — race window | 2026-03-05 |
| T1-11 | main.py shutdown: routine thread not joined before db.close() | 2026-03-05 |
| T1-12 | _persist_garmin_data(): non-atomic persistence | 2026-03-05 |
| T1-13 | DB write methods: cursor race in governance/science paths | 2026-03-06 |
| T1-14 | Garmin activity duplicate persistence — no idempotency key | 2026-03-06 |
| T1-15 | _persist_garmin_data() fail-open: persistence failure not propagated | 2026-03-06 |
| T1-16 | Schema version tracking absent | 2026-03-06 |
| T1-17 | No backup/recovery policy | 2026-03-06 |
| T1-18 | No physiological bounds validation | 2026-03-07 |
| T1-19 | No structural/temporal data sanity validation | 2026-03-07 |
| T1-20 | Garmin connectivity failure has no staleness gate | 2026-03-07 |
| T1-21 | Governance gates H2/H3 fire without distinguishing training vs illness stress | 2026-03-07 |
| T1-22 | OutcomeTracker schema lacks feedback-loop guardrails | 2026-03-07 |
| T1-23 | No unified DataTrustLevel contract | 2026-03-07 |

---

## TIER 2 — Observability (All Resolved ✅)

All 17 Tier 2 items (T2-01 through T2-17) are **RESOLVED**.
Full history: [`archive/technical_debt_t1_t3_resolved.md`](archive/technical_debt_t1_t3_resolved.md)

| # | Item | Resolved |
|---|------|----------|
| T2-01 | Error taxonomy: garmin_sync.py | 2026-03-02 |
| T2-02 | Error taxonomy: daily_coach.py | 2026-03-02 |
| T2-03 | Error taxonomy: telegram_bot.py | 2026-03-02 |
| T2-04 | Error taxonomy: governance_engine.py | 2026-03-02 |
| T2-05 | JSON guard for DB governance rows | 2026-03-02 |
| T2-06 | Athlete load error detail in database.py | 2026-03-02 |
| T2-07 | Launcher and startup error path observability | 2026-03-02 |
| T2-08 | Residual broad catches in DB best-effort branches | 2026-03-02 |
| T2-09 | Residual print() operational/error paths across integration modules | 2026-03-06 |
| T2-10 | Startup engine hydration has no data-confidence gate | 2026-03-06 |
| T2-11 | Telegram fallback logs message content — privacy risk | 2026-03-06 |
| T2-12 | UI path silent except Exception: pass | 2026-03-06 |
| T2-13 | Degraded mode duration not tracked | 2026-03-06 |
| T2-14 | Structured events lack severity levels; deduplication absent | 2026-03-07 |
| T2-15 | Weather synthetic fallback uses hardcoded location defaults | 2026-03-07 |
| T2-16 | Governance decisions lack human-readable rationale | 2026-03-07 |
| T2-17 | Metric lifecycle states not tracked | 2026-03-07 |

---

## TIER 3 — Dependency Hygiene (All Resolved ✅)

All Tier 3 items (T3-02 through T3-09) are **RESOLVED**.
Full history: [`archive/technical_debt_t1_t3_resolved.md`](archive/technical_debt_t1_t3_resolved.md)

| # | Item | Resolved |
|---|------|----------|
| T3-02 | Add ruff and mypy to dev requirements | 2026-03-02 |
| T3-03 | Secrets handling simplification | 2026-03-02 |
| T3-04 | Threading lifecycle: use threading.Event for clean stop | 2026-03-02 |
| T3-05 | Threading lifecycle: weather updater Event.wait() pattern | 2026-03-02 |
| T3-06 | Background worker shutdown without escalation | 2026-03-04 |
| T3-07 | scheduled_tasks list mutable and unsynchronized | 2026-03-04 |
| T3-08 | Weather + Telegram worker shutdown: no post-join alive escalation | 2026-03-06 |
| T3-09 | Telegram is single point of failure — no notification fallback | 2026-03-06 |

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

**Original state (pre-fix):** When a Garmin sync operation exceeds its timeout budget, the system emits
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

**Original state (pre-fix):** `KeyboardInterrupt` is caught at the menu level and suppressed. The
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

**Original state (pre-fix):** T4-03 introduced typed payload contracts at critical boundaries, but many
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

**Original state (pre-fix):** `pyproject.toml` contains coverage configuration and `pytest` settings,
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

**Original state (pre-fix):** Existing test coverage for `setup_wizard.py` focuses on `_save_env`.
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

**Original state (pre-fix):** Existing concurrency tests are unit-level and test isolated components
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

**Original state (pre-fix):** The inter-sync sleep is implemented as a `for` loop with `interval_hours * 3600`
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

### T4-15 · Weather updater thread has no explicit name — diagnostics parity gap ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `4ddc184`.
**Source:** Engineering Audit V4 (2026-03-05) — hidden debt item.
**Priority:** P4. Cosmetic/diagnostic only. No correctness or safety impact.

**Location:** `titan/integrations/weather_api.py` — `start_background_updates()`.

**Original state (pre-fix):** The `threading.Thread` for the weather updater is created without a `name=`
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

**Resolution:**
- Added `name="WeatherUpdater"` to the background thread in
  `start_background_updates()`.
- Existing weather integration tests now assert the emitted shutdown-timeout event uses
  `worker_name="WeatherUpdater"`, preserving diagnostics correlation.

**Acceptance gate (binary):**
```bash
ruff check titan/integrations/weather_api.py   # zero findings
python -m pytest -q   # 100% green
```

**Effort:** 5 minutes. Single parameter addition.

---

### T4-16 · Setup wizard prints duplicate Windows permission warning ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `4ddc184`.
**Source:** Engineering Audit V4 (2026-03-05) — hidden debt item.
**Priority:** P4. UX/cosmetic. No correctness impact.

**Location:** `titan/ui/setup_wizard.py` — `_save_env()` function, lines ~195-205.

**Original state (pre-fix):** `_save_env()` contains two consecutive `if os.name == "nt":` blocks that each
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

**Resolution:**
- Consolidated Windows permission messaging into a single `if os.name == "nt":` block
  with one clear warning path.
- Removed duplicate chmod/warning flow so `_save_env()` now has one permission update
  and one Windows-specific warning branch.

**Acceptance gate (binary):**
```bash
ruff check titan/ui/setup_wizard.py   # zero findings
python -m pytest -q   # 100% green
# Manual: count `if os.name == "nt":` blocks in _save_env — must be exactly 1.
```

**Effort:** ~15 minutes. Merge two blocks, remove duplicate.

---

### T4-17 · Setup wizard modifies `.gitignore` at runtime — operational side effect ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `4ddc184`.
**Source:** Engineering Audit V4 (2026-03-05) — hidden debt item.
**Priority:** P3. Operational side effect with blast radius on repository state.

**Location:** `titan/ui/setup_wizard.py` — `_save_env()` function, lines ~207-216.

**Original state (pre-fix):** After saving `.env`, the wizard appends entries to `.gitignore` at the
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

**Resolution:**
- Removed runtime `.gitignore` mutation from setup wizard `_save_env()`.
- Added regression coverage in `tests/titan/ui/test_setup_wizard.py` asserting wizard
  execution does not create or modify `.gitignore`.

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
**Source:** Architecture Review 2026-03-06 — AGENTS.md §16.1 (Governance Evolvability Protocol).
**Priority:** P2 (maintainability — "lock paralysis" risk as codebase grows).

**Location:** `titan/science/governance_engine.py` + new `tests/test_governance_mutation.py`

**Original state (pre-fix):**

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

**Original state (pre-fix):**

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

**Original state (pre-fix):**

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

### T4-21 · Documentation consistency not automated — lock codes, evidence registry, ADR index can drift silently ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `07a9361`.
**Source:** Master Risk Matrix — Risk #13 (Governance Documentation Rot). Architecture Review 2026-03-06. AGENTS.md §16.3.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** New `tests/test_documentation_consistency.py` + `titan/config/thresholds.py` + `.github/workflows/ci.yml`.

**Original state (pre-fix):**

Four documentation drift failure modes with no automated detection:
1. Lock codes in `governance_engine.py` not verified against a canonical set (canonical
   set lives in CLAUDE.md prose — not machine-readable).
2. Thresholds in `thresholds.py` can be added without corresponding `evidence_registry.py`
   entries.
3. `docs/adr/README.md` index can fall behind actual ADR file count.
4. `TECHNICAL_DEBT.md` tracking table can diverge from prose RESOLVED/OPEN status.

**Fix direction (per AGENTS.md §16.3):**

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

### T4-22 · No machine-verifiable agent session start protocol — context drift undetectable ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `a2a9961`.
**Source:** Master Risk Matrix — Risk #1 (Agent Context Drift) + Risk #17 (Self-Referential Prompt Decay). Architecture Review 2026-03-06. AGENTS.md §16.4.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** New `tests/test_claude_md_integrity.py` + `AGENTS.md` + `.github/workflows/ci.yml`.

**Original state (pre-fix):**

AI agent sessions begin without a verified baseline. Known failure modes: stale module
counts in CLAUDE.md, non-canonical lock codes generated by agents, Tier ordering
violations (E1), re-proposing already-closed debt items. CLAUDE.md can decay when agents
edit it incorrectly in a session.

**Fix direction (per AGENTS.md §16.4):**

1. Create `tests/test_claude_md_integrity.py` with:
   - `test_adr_count_in_claude_md_matches_files()` — ADR file count vs CLAUDE.md mentions
   - `test_module_count_in_claude_md_matches_filesystem()` — module count vs actual
   - `test_open_tier_items_not_misrepresented()` — phase closed claims vs open items
2. Update `AGENTS.md` §SESSION_START with the 5-step S1–S5 protocol from AGENTS.md §16.4.
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

### T4-23 · Property-based tests cover only happy-path invariants — physiology edge cases absent ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: bd2da17.
**Source:** Master Risk Matrix — Risk #2 (Test Suite Illusion of Safety) + Risk #9 (Physiological Edge-Case Fragility). Architecture Review 2026-03-06.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `test_property_based.py` (extend) + `tests/test_science_edge_cases.py` (new).

**Original state (pre-fix):**

`test_property_based.py` used Hypothesis for high-level invariants but did not test
physiology-specific boundary values. No test verified that:
- `hrv_ms = 0` preserved governance gate H2 behavior.
- `rhr_bpm = 200` avoided "excellent" readiness classification.
- `acwr = None` (post-T1-18) avoided a `VolumeLoadGauge` crash.
- Healthy governance inputs stayed clean with no gate locks (non-regression).

**Resolution:**

1. Extended `test_property_based.py` with Hypothesis-driven out-of-range physiology
   inputs bounded by `physiological_bounds.BOUNDS`, including the `hrv_ms=0` nulling rule.
2. Added `tests/test_science_edge_cases.py` with parameterized edge-case coverage for
   H2/HRV behavior, extreme RHR readiness behavior, `acwr=None` VLG resilience, and
   healthy-profile governance clean-path invariants.
3. Hardened integration edge handling in `VolumeLoadGauge.resolve()` for `acwr=None` /
   non-numeric values and in `ReadinessEngine.analyze_readiness()` for out-of-bounds RHR
   inputs to prevent false "✅ EXCELLENT" classifications.
4. Closure test count: 1708 tests green.

**Acceptance gate (binary):**
```bash
ruff check test_property_based.py tests/test_science_edge_cases.py
python -m pytest test_property_based.py tests/test_science_edge_cases.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~3h. Completed.

---

### T4-24 · Test fixtures are hand-crafted per file — fixture drift accumulates silently ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `0590862`.
**Source:** Master Risk Matrix — Risk #15 (Test Fixture Drift). Architecture Review 2026-03-06.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `tests/conftest.py` (extend) + affected test files (audit required).

**Original state (pre-fix):**

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

### T4-25 · Dependency pinning not audited — transitive drift and stale packages undetected ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `9dd54af`.
**Source:** Master Risk Matrix — Risk #6 (Dependency Drift). Architecture Review 2026-03-06.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `requirements.txt` + `.github/workflows/ci.yml`.

**Original state (pre-fix):**

`requirements.txt` pins direct dependencies but does not pin transitive dependencies
via a lockfile or constraints file. Over time:
1. Transitive package updates could break the build silently (a new transitive dep version
   is incompatible with Python 3.11 or with another dep in the graph).
2. Known CVEs in direct or transitive dependencies were not surfaced in CI.
3. No periodic audit job checked whether pinned versions were current or stale.

**Resolution:**

Added a dedicated CI workflow job (`dependency-drift-audit`) in `.github/workflows/ci.yml`
that performs two checks: (1) fails when unpinned dependencies are present in
`requirements.txt`/`requirements-dev.txt`, and (2) fails when `pip list --outdated`
returns stale packages. Added tests in `tests/test_t4_25_dependency_drift_audit.py`
to lock the new CI contract. Closure test count at gate time: 1713.

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

### T4-26 · Module boundaries use raw dicts — implicit coupling undetectable by static analysis ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `e40181a`.
**Source:** Architect Observations V6 — Risk #2 (Hidden Inter-Module Dependencies). ADR-0027.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `titan/core/database.py` (return types) + `tests/test_architectural_invariants.py` (new coupling test).

**Original state (pre-fix):**

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

**Resolution:** Added `TypedDict` boundary contracts (`DailyMetricsRow`, `TrainingLoadRow`, `GearUsageRow`) in `titan/core/database.py`, updated boundary-return method annotations, and added the coupling invariant test `test_no_science_imports_from_orchestration()` in `tests/test_architectural_invariants.py`.

**Effort:** ~2h. TypedDict definitions + annotation updates + one new test.

---

### T4-27 · No module count ceiling — complexity accumulation untracked ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `33e8255`.
**Source:** Architect Observations V6 — Risk #4 (Complexity Accumulation). AGENTS.md §16.11.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** `tests/test_documentation_consistency.py` (extend; T4-21).

**Original state (pre-fix):**

Module count grows unchecked with each phase. At 46 modules (Phase 7 close), the system
is within cognitive range. Without a ceiling, Phase 8 + Phase 9 additions could reach
65+ modules — the point at which the module graph exceeds single-engineer working memory.

**Fix direction (per AGENTS.md §16.11):**

Add to `tests/test_documentation_consistency.py`:
```python
def test_module_count_within_budget():
    """Module count must not exceed 60 (Phase 8 ceiling per AGENTS.md §16.11)."""
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

**Resolution:** Added a dedicated `complexity-budget` CI job in `.github/workflows/ci.yml` that computes the live `titan/` module count via `pkgutil.walk_packages(...)` and fails if count exceeds the Phase 8 ceiling of 60 modules. Added `tests/test_t4_27_complexity_budget_ci.py` to assert job presence and enforce real module-count + fail-threshold behavior in workflow config.

**Effort:** ~30 minutes. One CI guard + one dedicated workflow contract test module.

---

### T4-28 · No multi-agent context handoff artifact — advisor recommendations operate without ADR context ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `92555d3`.
**Source:** Architect Observations V6 — Risk #5 (Multi-Agent Fragmentation). AGENTS.md §16.5.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** New `scripts/generate_context_snapshot.py` + `docs/context-snapshot.md` + `AGENTS.md`.

**Original state (pre-fix):**

Multiple AI tools (ChatGPT, Gemini, Claude Chat, Codex, Claude Code) operate on this
codebase. Each has a different and potentially contradictory mental model of the system's
current state. Advisor tools can recommend patterns that contradict existing ADRs because
they are not provided the ADR register. Implementer tools can implement contradictory
parallel changes because they are not aware of concurrent work.

**Fix direction (per AGENTS.md §16.5):**

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

**Resolution:**

Implemented documentation drift guardrails in `tests/test_claude_md_integrity.py` by adding
(1) a historical snapshot consistency check (`CLAUDE.md` declared test count vs pytest
collected count) and (2) a key-files existence check (`CLAUDE.md` key files table entries
must exist on disk). Updated `CLAUDE.md` historical snapshot to 1718 tests at T4-28 close.

---

### T4-30 · Science modules carry no independent version numbers — algorithm breaking changes indistinguishable from patches ✅ RESOLVED 2026-03-07 (independent)

**Status:** ✅ RESOLVED 2026-03-07. Commit: `4ddc184`.
**Source:** Risk Review V8 — Risk: Semantic Versioning of Science Models. AGENTS.md §16.8.
**Priority:** P3 (Tier 4 — maintainability). Independent.

**Location:** All 26 `titan/science/*.py` modules, `titan/core/database.py` (schema migration), `tests/test_science_model_versions.py` (new CI check).

**Original state (pre-fix):**

Science modules have no `MODULE_VERSION` constant. A breaking algorithm change
(different output for same inputs) is indistinguishable from a patch fix in `CHANGES.md`.
The `governance_outcomes` table does not record which algorithm versions were active
when a decision was made. Phase 9 calibration will train on a mixed-version dataset
producing unreliable threshold estimates.

**Resolution:**

1. Added `MODULE_VERSION = "1.0.0"` across all `titan/science/*.py` modules tracked by
   the version-invariant test.
2. Added `algorithm_version_snapshot` persistence support in
   `governance_outcomes` (schema + writes/reads/updates) through `DatabaseManager`.
3. Updated `OutcomeTracker` to capture and persist an algorithm-version snapshot with
   each decision.
4. Added `tests/test_science_model_versions.py` CI coverage to enforce
   `MODULE_VERSION` presence and semver validity for every science module.

**Acceptance gate (binary):**
```bash
ruff check titan/science/ tests/test_science_model_versions.py
python -m pytest tests/test_science_model_versions.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~3h. 26 version constants (30min) + schema migration + OutcomeTracker update + CI test.

---

### T4-31 · No athlete isolation invariant CI check — new code may silently introduce cross-athlete assumptions ✅ RESOLVED 2026-03-07 (IMMEDIATE)

**Status:** ✅ RESOLVED 2026-03-07. Commit: eb20bb2.
**Source:** Architect Directive V8 — Decision 1 (Athlete Profile as System Core). AGENTS.md §16.10.
**Priority:** P3 (Tier 4 — maintainability; IMMEDIATE because the invariant it enforces is
already active and new violations must be caught from this commit forward).

**Location:** New `tests/test_athlete_isolation_invariant.py`; all `titan/` module files
in exemption register (module-level comment annotations).

**Original state (pre-fix):**

AGENTS.md §16.10 is active from this commit. Without a CI check, new code can violate the
isolation invariant (implicit athlete queries, no `athlete_id` parameter, cross-athlete
assumptions) and the violation will not be detected until Phase 9 when the migration
becomes blocked.

**Resolution:**

1. Added `tests/test_athlete_isolation_invariant.py` as a deterministic CI invariant check with a
   maintained exemption register constant and explicit assertion messages.
2. Enforced that non-database `titan/` modules cannot introduce SQL-like literals that omit
   `athlete_id`; violations report exact `file:line` evidence.
3. Enforced that migration `CREATE TABLE` statements in `DatabaseManager` include `athlete_id`
   unless the table is explicitly global (`sync_metadata` allowlist).
4. Enforced that each exemption-register module still contains the required
   `ADR-0040-SINGLE-ATHLETE-SHORTCUT` annotation.
5. Final full-suite closure: 1721 tests passing.

**Fix direction (per AGENTS.md §16.10):**

1. Add module-level `# AGENTS.md §16.10-SINGLE-ATHLETE-SHORTCUT: ...` comment to all files
   in the AGENTS.md §16.10 exemption register (see AGENTS.md §16.10 §Exemption Register).
2. Create `tests/test_athlete_isolation_invariant.py`:
   - Parse all `titan/` Python files.
   - For files NOT in the exemption register: assert no SQL string contains
     `SELECT|UPDATE|DELETE` without `athlete_id` in the same string (heuristic).
   - For files in the exemption register: assert the `AGENTS.md §16.10-SINGLE-ATHLETE-SHORTCUT`
     comment exists.
   - Assert new table migration blocks include `athlete_id` column.
3. Register the exemption list as a Python constant in the test file for easy maintenance.

**Acceptance gate (binary):**
```bash
ruff check tests/test_athlete_isolation_invariant.py
python -m pytest tests/test_athlete_isolation_invariant.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~2h. Comment annotations (30min per exemption file) + CI test.

---

### T4-32 · No override handler registry — new decision types lack guaranteed override path; Telegram override button absent ✅ RESOLVED 2026-03-07 (IMMEDIATE)

**Status:** ✅ RESOLVED 2026-03-07. Commit: dfe8907. **IMMEDIATE** (effective from ADR-0042, which is active from this commit).
**Source:** Architect Directive V8 — Decision 3 (Human Override as Invariant). ADR-0042.
**Priority:** P2 (Tier 4 — but IMMEDIATE because every day without the Telegram override
button is permanently lost override signal data; ADR-0042 §Gap 2).

**Location:** `titan/integrations/telegram_bot.py` (inline override button + callback handler),
`titan/science/override_signal.py` (new module), `titan/core/database.py` (schema migration
or OutcomeTracker extension), new `tests/test_override_handler_registry.py`.

**Original state (pre-fix):**

ADR-0042 was active from this commit point, but two gaps remained unaddressed:

1. The Telegram bot had no override button — athletes could silently ignore hard-stop messages
   without their decision being recorded, permanently losing calibration data.
2. No CI check existed to verify that every governance lock code and ML recommendation
   type had a registered override handler.

**Resolution:**

- Added `titan/science/override_signal.py` with `OverrideSignal` + mandatory-reason recording path.
- Added override-signal persistence support in `titan/core/database.py` (schema v6 `override_signals` + writer).
- Added override handler registry in `titan/science/governance_engine.py` mapped from canonical lock codes.
- Added Telegram override affordance + callback/reason flow in `titan/integrations/telegram_bot.py`.
- Added CI guard `tests/test_override_handler_registry.py` and module-level tests for new behavior.
- Closure suite count: 1730 tests all green at task close.

**Acceptance gate (binary):**
```bash
ruff check titan/science/override_signal.py titan/integrations/telegram_bot.py \
            titan/science/governance_engine.py tests/test_override_handler_registry.py
python -m pytest tests/test_override_handler_registry.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~6h. New module + Telegram callback handler + registry + CI test.

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

**Original state (pre-fix):**

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

**Original state (pre-fix):**

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

**Phase 9 calibration design constraints (DEC-FR-01 / DEC-FR-02 — 2026-03-08):**

When the Phase 9 calibration mechanism is designed, the following must be included
as hard requirements — not optional:

1. **Damping constant:** a maximum per-cycle adjustment percentage (e.g. ±5% per run)
   to prevent runaway feedback divergence. This is a named constant in `thresholds.py`,
   not a hard-coded float. Evidence registry entry required.
2. **Minimum observation count before modification:** no parameter may be adjusted unless
   the relevant observation pool exceeds a defined minimum (separate from the 90-day gate
   above — this applies per-parameter, not globally).
3. **CI test:** a test verifying that the damping constant is respected — i.e., a
   calibration run with a large input divergence must not produce an adjustment exceeding
   the damping bound.
4. **Domain baseline snapshot:** before any calibration loop is wired, a test must pin the
   input→output semantic contracts for core metrics (readiness score range [0,100], ACWR
   safe band [0.80,1.30], injury risk range [0.0,1.0]) as invariants. This ensures
   calibration cannot shift the meaning of these concepts without a test failure.

5. **Proxy metric alignment guard (DEC-FR-03 — 2026-03-08):** The calibration loop
   must not be evaluated solely on surrogate signals (e.g., lower lock rate, higher
   readiness scores, tighter ACWR band). Optimizing a proxy without anchoring to the
   real coaching goal risks Goodhart's Law: the system achieves better metric scores
   while drifting away from actual athlete benefit. Required safeguard:
   - At least one acceptance criterion in the Phase 9 calibration ADR must be stated
     in terms of **domain outcomes** (e.g., RPE alignment, injury incidence rate,
     athlete-reported feel), not governance metric movements alone.
   - The divergence detector must be validated against a held-out outcome set that
     was not used to tune the detector itself.
   - Any new proxy metric added to the calibration signal must include a written
     justification of its correlation with domain outcomes, filed in
     `titan/config/evidence_registry.py` before the metric is wired.

These constraints are architectural requirements for Phase 9 entry, not implementation details.
An ADR will be required before implementing the calibration adjustment mechanism.

---

### T5-06 · ML advisory models lack explainability contract — feature attribution and plain-text reason absent 🟢

**Decision status:** OPEN — T5-06-A is **Phase 8A early work** (complete before Phase 8B); remainder deferred Phase 9.
**Workflow Path (T5-06-A): A** *(touches ≥ 3 production modules — PILOT-01 excluded)*
**Source:** Risk Review V7 — Risk: ML Physiological Safety & Ethical Opacity. Architecture Review 2026-03-06. ADR-0032.

**Original state (pre-fix):**

`InjuryRiskEnsembleModel` operates in advisory mode and returns a probability score
(0.0–1.0) with no feature attribution. The governance engine cannot determine whether
a score of 0.73 is driven by an ACWR spike (rest one day), chronic TSB depression
(reduce load a week), a biomechanics anomaly (physio referral), or historical injury
proximity (monitor). These four scenarios warrant entirely different coaching responses.
The two shadow-mode models (`LoadPredictionShadowModel`, `AutomatedPeriodizationEngine`)
will have the same gap when promoted to advisory.

**T5-06-A — `InjuryRiskEnsembleModel` explainability (Phase 8A early work):**

Since `InjuryRiskEnsembleModel` is currently advisory, it must be brought into compliance
with the `ExplainableOutput` contract (ADR-0032) early in Phase 8, before Phase 8B begins.

Fix direction:
1. Add `ExplainableOutput` dataclass to `titan/science/ml_safety.py` (or a new
   `titan/science/ml_explainability.py` module).
2. Extend `InjuryRiskEnsembleModel.assess_injury_risk()` to return `ExplainableOutput`
   alongside the primary score: top-3 feature contributions, confidence range,
   `plain_text_reason` (template-based, not LLM-based), `data_freshness_ok`
   (using ADR-0030 staleness flag).
3. Update governance engine integration to log `plain_text_reason` and include
   feature contributions in the Operator Console session explorer payload (ADR-0011).
4. Add `tests/test_ml_explainability.py`:
   - `test_injury_risk_returns_explainable_output` — happy path contract.
   - `test_injury_risk_stale_data_discarded` — stale data → `data_freshness_ok=False`
     → advisory output discarded by governance.
   - `test_plain_text_reason_nonempty` — reason string non-empty for all test cases.

**T5-06-B — Shadow model promotion gate (deferred Phase 9):**
`LoadPredictionShadowModel` and `AutomatedPeriodizationEngine` must satisfy the
ADR-0032 promotion gate (criteria P1–P6) before being promoted to advisory mode.
No implementation before Phase 8 closes.

**Acceptance gate for T5-06-A (binary):**
```bash
ruff check titan/science/injury_risk_model.py titan/science/ml_safety.py \
            tests/test_ml_explainability.py
python -m pytest tests/test_ml_explainability.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort (T5-06-A):** ~4h. `ExplainableOutput` dataclass + ensemble attribution
logic + governance integration update + tests.

**Phase 8A early work:** T5-06-A must be RESOLVED before Phase 8B begins. (Phase 8 is already OPEN — G1–G11 all cleared 2026-03-08. T5-06-A is Tier 5 and was not a G1 blocking criterion.)

---

### T5-07 · No model calibration age tracking or adaptation drift detection — physiological model staleness invisible at runtime ✅ RESOLVED (Layers 1–2) — Layer 3 deferred Phase 9

**Status:** ✅ RESOLVED (Layers 1–2) — 2026-03-13. Commit: b6bea2a. Foundation scaffold implemented: `model_calibration_metadata` schema migration (SQLite v7), `upsert_model_calibration_metadata()` + `get_recent_hrv_mean()` in `database.py` (Layer 1); `HrvCalibrationDriftState` dataclass + `describe_calibration_drift()` in `hrv_engine.py` (Layer 2). Layer 3 (multi-athlete isolation): deferred Phase 9 (see ADR-0033 §Layer 3). Alembic migration of this table remains tracked as T5-08-B D5.
**Workflow Path: A** *(schema migration — PILOT-01 excluded)*
**Source:** Risk Review V8 — Risks: Model Aging, Calibration Bias, Athlete Adaptation Lag, Single-Athlete Overfitting. ADR-0033.
**Priority:** P1 for Layers 1–2 (Phase 8A, high priority); P5 for Layer 3 (Phase 9).

**Location:** `titan/core/database.py` (new `model_calibration_metadata` table), `titan/orchestration/daily_coach.py` (startup check), `titan/config/thresholds.py` (new constants).

**Original state (pre-fix):**

Physiological models (HRV baselines, lactate threshold, critical speed) are calibrated
against historical data from a single athlete at a specific fitness level. As the athlete
improves (or as physiology changes seasonally), the model's reference frame becomes stale.
An athlete whose HRV baseline has risen 10ms over 6 months will trigger H2 gate on days
that are physiologically normal — because the gate compares against a stale baseline. No
mechanism exists to detect or flag this staleness. See ADR-0033 for full context.

**Fix direction (per ADR-0033) — Layer 1 (Phase 8A early work):**

1. Add to `thresholds.py`:
   ```python
   MODEL_CALIBRATION_MAX_AGE_DAYS = 180
   HRV_DRIFT_THRESHOLD_MS = 8.0
   ```
2. Schema migration: add `model_calibration_metadata` table:
   ```sql
   CREATE TABLE model_calibration_metadata (
       model_name TEXT PRIMARY KEY, calibrated_at TEXT NOT NULL,
       calibrated_for TEXT NOT NULL DEFAULT 'default',
       baseline_hrv_ms REAL, baseline_vo2 REAL, schema_version INTEGER NOT NULL
   );
   ```
3. Populate initial row for the HRV engine with current 30-day HRV mean and
   `calibrated_at = now`.
4. In `DailyCoach` startup, check model age. If > `MODEL_CALIBRATION_MAX_AGE_DAYS`:
   emit `model_calibration_stale` structured event (WARNING severity, per AGENTS.md §16.6).

**Fix direction (per ADR-0033) — Layer 2 (Phase 8A early work):**

5. In `WeeklyPlanGenerator`, compare current 30-day HRV mean vs stored baseline.
   If `|delta| > HRV_DRIFT_THRESHOLD_MS`: emit `hrv_baseline_drift_detected` structured
   event and flag in Operator Console readiness dashboard.

**Layer 3 (Phase 9 — multi-athlete isolation):** See ADR-0033 §Layer 3. Deferred.

**Acceptance gate for Layers 1–2 (binary):**
```bash
ruff check titan/core/database.py titan/orchestration/daily_coach.py \
            titan/features/weekly_plan.py titan/config/thresholds.py \
            tests/test_model_calibration_metadata.py
python -m pytest tests/test_model_calibration_metadata.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort (Layers 1–2):** ~4h. Schema + startup check + weekly drift check + tests.
**Phase 8A early work:** Layers 1–2 must be RESOLVED before Phase 8B begins. Schema migration aligns naturally with T5-08 (Phase 8A PostgreSQL migration). (Phase 8 is already OPEN — T5-07 is Tier 5 and did not block the G1–G11 entry gate.)

---

---

### T5-08 · PostgreSQL migration not yet implemented — multi-athlete persistence layer unbuilt ⚠️ PARTIAL 2026-03-08

**Status:** ⚠️ PARTIAL 2026-03-08. Commit: 54e95d9. QA verdict: FAIL — ADR-0044 deliverables D1–D9 not satisfied. See T5-08-B for remaining work.
**Workflow Path: A** *(PostgreSQL migration + architectural refactor — PILOT-01 excluded)*
**Source:** FUTURE_UPGRADES.md Phase 8/10 scope (product direction), ADR-0044 (storage topology decision). Fulfills ADR-0015 Phase 8 gate.
**Priority:** P1 for Phase 8 (Phase 8A prerequisite).

**Location:** `titan/core/database.py` (replace with `titan/core/persistence.py`), `requirements.txt` (add `sqlalchemy`, `alembic`, `psycopg2-binary`), new `alembic/` directory.

**Original state (pre-fix):**

TITAN OS targets a multi-athlete coach platform (FUTURE_UPGRADES.md Phase 8/10 scope). SQLite's single-writer
concurrency model cannot support 50 athletes × 3 daemon threads. Per-athlete SQLite
files solve concurrency but multiply migration, backup, and GDPR erasure complexity by N.
PostgreSQL is the correct topology. See ADR-0044 for full decision rationale.

**Fix direction (ADR-0044 Phase 8A deliverables D1–D9):**

1. Implement `titan/core/persistence.py` with `PersistenceAdapter` (SQLAlchemy Core).
2. Set up Alembic (`alembic init alembic/`); write migration for all 5 current tables.
3. Add `athlete_id TEXT NOT NULL DEFAULT 'default'` to all 5 tables.
4. Add `consent_log` table (athlete_id, consent_type, granted_at, revoked_at).
5. Add Row-Level Security policies; test with `tests/test_athlete_rls_isolation.py`.
6. Add `TITAN_DB_BACKEND=sqlite|postgres` feature flag.
7. Update `requirements.txt` with pinned versions.
8. Update hot backup (T1-17 pattern) for `pg_dump`.

**Partial implementation (commit 54e95d9 — scaffold only):**
- Added `PostgreSQLDatabaseManager` and `get_database_manager()` to `titan/core/database.py` while keeping SQLite `DatabaseManager` as default backend.
- Preserved table semantics for `training_log` and `governance_outcomes` in the PostgreSQL backend with matching CTL/ATL reconstruction and governance persistence behavior.
- Extended `tests/titan/core/test_database.py` with backend parity tests (SQLite vs PostgreSQL adapter path) for CTL/ATL reconstruction, governance persistence, and training load history queries.

**ADR-0044 deliverable coverage (scaffold only):**

| Deliverable | Status | Notes |
|---|---|---|
| D1 — `PersistenceAdapter` (SQLAlchemy Core) | ✗ NOT DONE | `PostgreSQLDatabaseManager` added to existing `database.py`; no `persistence.py`; no SQLAlchemy Core |
| D2 — Alembic migration (5 tables) | ✗ NOT DONE | No `alembic/` directory |
| D3 — `athlete_id` on all 5 tables | ✗ NOT DONE | Not added to any table |
| D4 — RLS policies + test | ✗ NOT DONE | No `tests/test_athlete_rls_isolation.py` |
| D5 — `model_calibration_metadata` table | ✗ NOT DONE | No migration |
| D6 — `TITAN_DB_BACKEND` feature flag | ✓ DONE | `get_database_manager()` switches on env var |
| D7 — `pg_dump` backup strategy | ✗ NOT DONE | T1-17 pattern not updated for PostgreSQL |
| D8 — `TECHNICAL_DEBT.md` marked RESOLVED | ✗ NOT DONE | Incorrectly marked; corrected by this edit |
| D9 — `consent_log` table | ✗ NOT DONE | Not included in migration |

**Acceptance gate (binary — remains open until T5-08-B RESOLVED):**
```bash
ruff check titan/core/persistence.py alembic/ tests/test_athlete_rls_isolation.py
python -m pytest tests/test_athlete_rls_isolation.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
TITAN_DB_BACKEND=sqlite python -m pytest -q
```

**Effort:** ~3–4 weeks. Full migration + Alembic + RLS + both backend test paths. See T5-08-B.

---

### T5-08-B · ADR-0044 full migration — PersistenceAdapter + Alembic + RLS + consent schema 🔴 OPEN

**Status:** OPEN — D1 interface contract DONE (2026-03-08, commit eaaa35e); D2a DONE (2026-03-13, commit df449e7); D2b DONE (2026-03-13, commit d7ad4b7); D2c DONE (2026-03-13, commit f6901b6); D3 DONE (2026-03-13, commit pending); D4 DONE (2026-03-13, commit pending); D5 DONE (2026-03-13, commit pending). **Complete D2 is now finished (D2a + D2b + D2c).** Remaining scope: D7, D9. **D4 closed; D7/D9 remain out of scope for this pass.** Phase 8A prerequisite — blocks Phase 8B; G10 gate in ADR-0022 not cleared until this resolves.
**Workflow Path: A** *(full ADR-0044 D2–D5, D7–D9 implementation; PILOT-01 excluded)*
**Source:** ADR-0044 (PostgreSQL migration decision); QA FAIL on T5-08 scaffold (2026-03-08); OBS-007 process finding.
**Priority:** P1 for Phase 8 (Phase 8B cannot begin until T5-08-B is RESOLVED).
**Predecessor:** T5-08 PARTIAL (scaffold: `PostgreSQLDatabaseManager` in `titan/core/database.py`, backend parity tests, `TITAN_DB_BACKEND` env var).

**ADR Deliverable Checklist (ADR-0044) — current state:**

| # | Deliverable | Status | Notes |
|---|---|---|---|
| D1 | `titan/core/persistence.py`: `PersistenceAdapter` ABC (30 abstract methods); `SQLiteAdapter` delegating to `DatabaseManager`; `PostgreSQLAdapter` delegation scaffold (explicit `NotImplementedError` for unimplemented PG methods) | ✓ DONE 2026-03-08 | Interface contract + SQLite parity complete. SQLAlchemy Core PG query implementation folded into D2 scope (queries must be written against the schema defined by D2 migration). Acceptance test met: 1841 tests green. |
| D2a | Alembic migration for all 5 current tables (`daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, `governance_outcomes`) | ✓ DONE 2026-03-13 | Completed in commit `df449e7`: Alembic scaffold wired, migration created, `alembic upgrade head` + `downgrade -1`/`upgrade head` round-trip validated, migration tests added. |
| D2b | SQLAlchemy Core query implementation for all 30 `PostgreSQLAdapter` methods (replacing `NotImplementedError` stubs) | ✓ DONE 2026-03-13 | Completed in commit `d7ad4b7`: SQLAlchemy Core-backed `PostgreSQLAdapter` query layer implemented against D2a schema; adapter persistence tests updated for happy-path/boundary behavior. |
| D2c | PostgreSQL concurrency stress tests equivalent to `test_database_manager_thread_safety.py` and `test_harden_db_concurrency.py` (OBS-005) | ✓ DONE 2026-03-13 | Completed in commit `f6901b6`: added PostgreSQLAdapter concurrency stress tests (mixed read/write multi-thread load + same-date concurrent upsert stability). This closes the deferred OBS-005 PostgreSQL concurrency validation criterion and completes D2. |
| D3 | `athlete_id TEXT NOT NULL DEFAULT 'default'` column on all 5 tables | ✓ DONE 2026-03-13 | Implemented via Alembic revision `20260313_02`; persistence adapter/schema tests updated for D3 column contract. |
| D4 | Row-Level Security policies active and tested | ✓ DONE 2026-03-13 | Implemented in Alembic revision `20260313_04` with PostgreSQL-only RLS enablement + athlete isolation policy for D4 tables; tests added in `tests/titan/core/test_athlete_rls_isolation.py`. |
| D5 | `model_calibration_metadata` table in Alembic migration (ADR-0033 T5-07 Layer 1) | ✓ DONE 2026-03-13 | Implemented in Alembic revision `20260313_03`; migration tests added for upgrade contract + downgrade removal. |
| D6 | `TITAN_DB_BACKEND=sqlite\|postgres` feature flag | ✓ DONE (T5-08) | `get_database_manager()` switches on env var |
| D7 | `pg_dump` hot backup replaces SQLite file copy (T1-17 re-implementation for PostgreSQL) | ✗ NOT DONE | |
| D8 | `TECHNICAL_DEBT.md` T5-08 marked RESOLVED | ✗ NOT DONE | Blocked — T5-08-B must be RESOLVED first |
| D9 | `consent_log` table in Alembic migration (athlete_id, consent_type, granted_at, revoked_at) | ✗ NOT DONE | |

**D2a closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: `df449e7`.
- **Resolution:** Added Alembic scaffold + D2a migration for exactly the 5 current tables; validated upgrade/downgrade round-trip; added tests for migration creation and round-trip behavior.
- **Task learning:** Keeping D2 split milestones explicit in this checklist prevents accidental scope bleed from D2a into D2b/D2c.

**D2b closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: `d7ad4b7`.
- **Resolution:** Replaced D2b `PostgreSQLAdapter` stub/delegation path with SQLAlchemy Core query implementations across the D2b contract and updated `tests/titan/core/test_persistence.py` to cover happy-path + boundary behavior for the changed adapter methods.
- **Task learning:** Date-windowed query tests must seed rows within the active lookback window to avoid false negatives unrelated to adapter logic.

**D2c closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: `f6901b6`.
- **Resolution:** Added `tests/titan/core/test_postgresql_adapter_concurrency.py` with PostgreSQLAdapter-path concurrency stress coverage equivalent in intent to existing SQLite concurrency checks: mixed read/write multi-thread load and same-date concurrent upsert stability.
- **Task learning:** Concurrency contract validation for PostgreSQLAdapter is best captured with deterministic multi-thread stress tests that assert both thread completion and stable final persisted state.
- **Complete D2 status:** ✅ D2 is now fully complete via D2a + D2b + D2c.

**D3 closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: pending.
- **Resolution:** Added Alembic D3 migration (`20260313_02`) to append `athlete_id TEXT NOT NULL DEFAULT 'default'` to `daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, and `governance_outcomes`; updated PostgreSQLAdapter table metadata and backend parity tests to validate the new default-backed column contract.
- **Task learning:** Introducing additive schema revisions requires migration tests that target fixed revisions (`20260313_01`) where historical expectations assume a single-head chain.

**D5 closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: pending.
- **Resolution:** Added Alembic D5 migration (`20260313_03`) creating `model_calibration_metadata` in the PostgreSQL/Alembic path with composite primary key (`model_name`, `athlete_id`) and default-backed `athlete_id`/`calibrated_for` columns; added migration tests for upgrade schema contract and downgrade removal behavior.
- **Task learning:** Isolating D5 as an additive revision after D3 preserves the existing migration chain while keeping SQLite schema behavior unchanged.

**D4 closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: pending.
- **Resolution:** Added Alembic D4 migration (`20260313_04`) that activates PostgreSQL Row-Level Security on `daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, `governance_outcomes`, and `model_calibration_metadata`, applying `titan_athlete_isolation` with `current_setting('app.current_athlete_id', true)` for both read and write enforcement; non-PostgreSQL dialects are explicit no-ops to preserve SQLite behavior.
- **Task learning:** Dialect-gated migration logic keeps the SQLite path stable while enabling enforceable PostgreSQL athlete isolation in a single revision.
- **Next deliverables:** D7 and D9 (both remain out of scope for this pass).

**Note — D6 already done (T5-08):** `TITAN_DB_BACKEND=sqlite|postgres` feature flag via `get_database_manager()` is active. SQLite path remains fully operational throughout this migration. No test refactoring required against SQLite until the fallback is formally retired (no earlier than Phase 8B close).

**Acceptance gate (binary):**
```bash
ruff check titan/core/persistence.py alembic/ tests/test_athlete_rls_isolation.py
python -m pytest tests/test_athlete_rls_isolation.py -v
alembic upgrade head
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
TITAN_DB_BACKEND=sqlite python -m pytest -q
```

**Effort:** ~3 weeks (D2a–D2c, D3–D5, D7, D9; D1 done, D6 done). Sequence: D2a → D2b → D2c → D3 → D4/D5 (parallel) → D7/D9 (parallel).

---

### T5-09 · No unified `get_athlete_context()` query interface — LLM Seam 2 unbuilt 🔴 OPEN

**Status:** OPEN (Phase 8B prerequisite; also required for Phase 10 LLM layer).
**Workflow Path: A** *(effort > 1 day — PILOT-01 excluded)*
**Source:** FUTURE_UPGRADES.md Phase 8/10 scope (LLM Seam 2).
**Priority:** P2 for Phase 8B; P5 for Phase 10.

**Location:** New `get_athlete_context()` in `titan/core/persistence.py` (or `titan/core/athlete_context.py`).

**Original state (pre-fix):**

The coach dashboard and Phase 10 LLM both need to assemble athlete context from multiple
data domains. No single function exists — each caller would assemble from raw queries,
creating duplicated logic and inconsistent output shapes.

**Fix direction:**

```python
def get_athlete_context(
    athlete_id: str,
    days: int = 7,
    include_governance: bool = True,
    include_training: bool = True,
    include_biometrics: bool = True,
) -> dict:
    """FUTURE_UPGRADES.md Phase 8/10 scope Seam 2. Returns JSON-serialisable dict (float → 2dp, no datetime objects)."""
```

**Acceptance gate (binary):**
```bash
ruff check titan/core/athlete_context.py tests/test_athlete_context.py
python -m pytest tests/test_athlete_context.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~1 week.

---

### T5-10 · Phase 10 LLM coach query layer not yet designed in detail 🟡 DEFERRED

**Status:** OPEN (deferred — Phase 10; implement only after Phase 9 closes with sufficient multi-athlete corpus).
**Source:** FUTURE_UPGRADES.md Phase 8/10 scope (Decision 3, Seam 3), ADR-0045 (LLM backend abstraction).
**Priority:** P5 (future optionality).

**Location:** `titan/integrations/llm_coach.py` (new module, Phase 10 only).

**Contract (do not deviate):**

```python
LLM_BACKEND = os.environ.get("TITAN_LLM_BACKEND", "none")  # none | claude | ollama

def coach_query(prompt: str, athlete_context: dict) -> str:
    if LLM_BACKEND == "none":
        return _deterministic_fallback_summary(athlete_context)
    # ADR-0045: route to Claude API or Ollama depending on LLM_BACKEND
```

**Hard invariants (CI must verify):**
- No governance module imports `llm_coach` (LLM never in safety path).
- `TITAN_LLM_BACKEND=none`: all paths return deterministic output.
- Every LLM recommendation passes through override handler registry (ADR-0042).

**Deferred until:** Phase 9 closes AND multi-athlete corpus ≥ 100 paired outcomes per athlete.

---

### T5-11 · No API authentication layer for Phase 8B web UI — health data accessible without auth 🔴 OPEN

**Status:** OPEN (Phase 8B entry gate — must be designed before any coach dashboard endpoints are built).
**Workflow Path: A** *(cross-subsystem auth layer; ADR required before implementation — PILOT-01 excluded)*
**Source:** Architecture review 2026-03-06. Not previously recorded.
**Priority:** P0 for Phase 8B (do NOT build any coach API endpoint without this resolved).

**Location:** New `titan/api/auth.py` (Phase 8B); FastAPI app (`titan/api/main.py`).

**Original state (pre-fix):**

ADR-0013 (technology path) specifies React + FastAPI for the coach dashboard. FUTURE_UPGRADES.md Phase 8/10 scope
confirms multi-athlete deployment. However, no auth layer has been designed. FastAPI
endpoints serving health data (HRV, RHR, governance decisions, training log) for 50
athletes with zero authentication is a GDPR violation and a serious security risk.

**Required before any Phase 8B endpoint is built:**

- Auth mechanism selected and locked in an ADR (options: JWT + refresh tokens, OAuth2 via
  Google/GitHub, or session-based). Recommendation: OAuth2 (eliminates credential management;
  Google Workspace is common in coaching contexts).
- Coach role vs athlete role permissions defined.
- All API endpoints behind auth middleware — no public endpoints except health check.
- Athlete data never returned to a request authenticated as a different athlete (RLS +
  application-level check).
- Token expiry and rotation policy defined.

**Debt item:** A dedicated ADR (0046 or next available) must be written and accepted before
Phase 8B begins. This item is not implementable without that ADR.

---

### T5-12 · Garmin unofficial API fragility — no fallback if Garmin changes auth mechanism 🟡 OPEN

**Status:** OPEN (risk monitoring — no immediate action; mitigation design deferred Phase 8C).
**Workflow Path: A** *(no implementation until Phase 8C; path applies when mitigation design begins)*
**Source:** Architecture review 2026-03-06. Not previously recorded.
**Priority:** P3 (medium — risk is real but not blocking current phases).

**Location:** `titan/integrations/garmin_sync.py`.

**Original state (pre-fix):**

`garminconnect` is an **unofficial, reverse-engineered** Python library. It scrapes
Garmin Connect's web authentication flow, not an official API. Garmin has changed its
authentication mechanism at least twice in the past three years, breaking the library on
each occasion.

**Risk scenario:** Garmin deploys a new login challenge (CAPTCHA, MFA enforcement, OAuth
mandate) → `garmin_sync.py` fails silently or with an exception → `DailyCoach` cold-starts
with zero biometric data → governance runs on stale data → wrong coaching decisions.

**Current mitigation (partial):** T1-09 introduced synthetic fallback for weather. No
equivalent synthetic fallback for Garmin data exists beyond what `DailyCoach` already
handles for missing today-data.

**Required mitigation design (Phase 8C):**

- Explicit "Garmin API degraded" structured event with severity CRITICAL.
- Coach dashboard indicator: "Garmin sync failed — last data: N hours ago."
- `garminconnect` library pinned to a tested version with a change-alert in CI
  (`pip-audit` or `pip-check` on the pinned version).
- Phase 8C multi-device adapter: if Garmin fails, HRV/RHR may be sourced from a
  secondary device (Polar, Whoop, COROS) via the unified adapter (ADR-0016/ADR-0041).

---

### T5-13 · No coach action audit trail — GDPR accountability gap for health data processors 🔴 OPEN

**Status:** OPEN (Phase 8B entry gate — must be implemented alongside first coach dashboard feature).
**Workflow Path: A** *(schema migration + cross-subsystem middleware — PILOT-01 excluded)*
**Source:** Architecture review 2026-03-06. Not previously recorded.
**Priority:** P1 for Phase 8B (GDPR Article 5(2) accountability requirement).

**Location:** New `coach_audit_log` table (Phase 8A Alembic migration), new `titan/api/audit.py` middleware.

**Original state (pre-fix):**

Phase 8B grants coaches the ability to view all athletes' health data and submit manual
overrides. Under GDPR, any entity that processes health data on behalf of another person
is a **data processor** and must maintain records of processing activities (Article 30)
and be able to demonstrate accountability (Article 5(2)).

Specifically: when a coach views Athlete A's HRV data and submits an override, that action
must be logged with: coach identity, athlete affected, action type, timestamp, and reason.
Without this log, a data subject access request or a supervisory authority audit cannot be
satisfied.

**Required:**

```sql
CREATE TABLE coach_audit_log (
    id              SERIAL PRIMARY KEY,
    coach_id        TEXT NOT NULL,
    athlete_id      TEXT NOT NULL,
    action_type     TEXT NOT NULL,   -- 'VIEW_DATA' | 'SUBMIT_OVERRIDE' | 'EXPORT_DATA' | 'DELETE_DATA'
    resource        TEXT NOT NULL,   -- e.g., 'governance_outcomes', 'training_log'
    action_detail   JSONB,           -- optional: override payload, query parameters
    performed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Every FastAPI endpoint that accesses athlete health data must write to this table via
a shared middleware (not per-endpoint — this must be non-bypassable).

---

### T5-14 · Training zone thresholds not adjusted for environmental stress — ESI framework absent 🔴 OPEN

**Status:** OPEN (Phase 8 scheduled — implement after Phase 8 entry gate passes per AGENTS.md §16.2).
**Workflow Path: A** *(touches 5 production modules — PILOT-01 excluded)*
**Reclassified:** 2026-03-07 from T4-29 (Tier 4) to T5-14 (Tier 5). Rationale: this is Phase 8 internal work, not a Phase 8 prerequisite; keeping it as an OPEN Tier 4 item blocked G1 of the Phase 8 entry gate despite the work being correctly deferred into Phase 8.
**Source:** Risk Review V8 — Risk: Static Thresholding. ADR-0034.
**Priority:** P3 (accuracy improvement; not safety-gate). Independent.

**Location:** `titan/config/thresholds.py` (ESI constants), `titan/orchestration/daily_coach.py` (ESI context field), `titan/features/optimal_time.py` (ESI pace adjustment), `titan/features/weekly_plan.py` (zone target adjustment), `titan/science/governance_engine.py` (VO₂ block under ESI EXTREME).

**Original state (pre-fix):**

Training zone targets are applied identically regardless of environmental conditions.
An athlete targeting Zone 2 at the same pace in 18°C and 32°C with 80% humidity
is not doing the same physiological work. Dew-point-optimised timing is already
implemented (`OptimalTimeCalculator`), but the training targets themselves are not
adjusted when the athlete trains outside the optimal window or when conditions are
unavoidably adverse.

**Fix direction (per ADR-0034):**

1. Add ESI constants to `thresholds.py` (dew point thresholds, temp thresholds, pace adjustment table).
2. Compute `esi_level` and `esi_pace_adjustment_sec_per_km` in `DailyCoach` from
   current weather data.
3. Pass ESI context to `WeeklyPlanGenerator` and `OptimalTimeCalculator`.
4. Block VO₂max workouts when ESI is EXTREME (via `VO2_ELIGIBILITY_GATE` modification).
5. Include ESI level and adjusted targets in Telegram briefing.
6. Add `tests/test_esi_compensation.py`.

**Acceptance gate (binary):**
```bash
ruff check titan/config/thresholds.py titan/orchestration/daily_coach.py \
            titan/features/optimal_time.py titan/features/weekly_plan.py \
            titan/science/governance_engine.py tests/test_esi_compensation.py
python -m pytest tests/test_esi_compensation.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~4h. ESI computation function + integration into 3 consumers + tests.

---

### T5-15 · Test suite has no pytest layer marker taxonomy — unit/integration/governance indistinguishable 🟡 DEFERRED

**Status:** DEFERRED (Phase 9 housekeeping).
**Recorded:** 2026-03-08 (DEC-001 / OBS-001 — future maintenance observation, architect review).
**Source:** Engineer observation post-Phase 7 CI safeguards review.
**Priority:** P4 (engineering quality-of-life; no functional or safety impact).

**Context:**
118 test files (~1780+ tests) have no pytest mark taxonomy beyond filename conventions.
`pyproject.toml` registers only `markers = ["timeout: ..."]`. No `unit`, `integration`,
or `governance` marks exist. Targeted subset runs rely on filename patterns
(`pytest tests/test_p0*.py`, `pytest tests/test_governance_integration.py`), which is
adequate at current scale but degrades as the suite grows toward ~3000 tests.

**Acceptance gate (binary):**
1. Register markers in `pyproject.toml`: `unit`, `integration`, `governance`, `invariant`.
2. Apply exactly one marker to every test function across all 118 test files.
3. `pytest -m governance -q` collects only governance tests (no `PytestUnknownMarkWarning`).
4. `pytest -m unit -q` completes in under 30 seconds on CI hardware.
5. All three mandatory gates pass: `ruff check .` → `pytest -q -W error::pytest.PytestWarning` → `pytest -q`.

**Scope note:** Mechanical refactor only — no test logic changes. Marker assignment follows
this taxonomy:
- `unit` — tests a single class/function in isolation (mocks all external deps)
- `integration` — tests interaction between 2+ modules or with SQLite
- `governance` — tests a governance gate contract or invariant (may overlap with integration)
- `invariant` — tests a doc/schema/CI invariant (e.g. `test_claude_md_integrity.py`)

**Effort:** ~2h mechanical pass. No architectural decision required.

**Phase 9 gate:** This item is a prerequisite for Phase 9 targeted-execution CI optimisation.
Do not implement during Phase 8 — it is a large-scope mechanical refactor with no Phase 8
safety or functional benefit.

---

### T5-16 · DailyCoach multi-athlete execution model undefined — Phase 8B orchestration semantics unresolved ✅ RESOLVED

**Status:** RESOLVED — ADR-0046 accepted 2026-03-08. Execution model decided: Model 2
(stateless coaching function). T5-16-A implementation entry created below.
**Resolved:** 2026-03-08 (ADR-0046 — `docs/adr/0046-dailycoach-multi-athlete-execution-model.md`)
**Workflow Path: A** *(architectural decision required — PILOT-01 excluded)*
**Source:** Architect review 2026-03-08 (risk package evaluation). Not previously recorded.

**Decision summary (full rationale in ADR-0046):**

- **Model chosen:** Model 2 — stateless `coaching_pipeline(athlete_context)` function,
  building on ADR-0018 kernel boundary.
- **Concurrency:** Engines, governance context, `OutcomeTracker`, Telegram target, and
  Garmin credentials are per-athlete. `WeatherAPI` cache (per-location) and PostgreSQL
  connection pool are safely shared.
- **Daemon thread:** Retained for single-athlete CLI mode unchanged. For multi-athlete
  mode: replaced by a `CoachingScheduler` (supervised `ThreadPoolExecutor`) that fires
  `coaching_pipeline()` per athlete at schedule time — O(1) thread count regardless of
  athlete count.
- **Engine hydration:** On-demand from DB per coaching pipeline call (not once at
  startup). Acceptable at Phase 8B scale (≤50 athletes × 1 call/day).
- **Single-athlete mode:** `DailyCoach.run_morning_routine()` retained as thin wrapper
  around `coaching_pipeline()` — no behaviour change.

---

### T5-16-A · Extract `coaching_pipeline()` stateless function + `CoachingScheduler` stub 🔴 OPEN

**Status:** OPEN (Phase 8B — required before any multi-athlete coaching execution endpoint
is built; NOT required for dashboard read paths via T5-09).
**Workflow Path: A** *(multi-module refactor — PILOT-01 excluded)*
**Source:** ADR-0046 (accepted 2026-03-08). Created by T5-16 resolution.
**Priority:** P0 for Phase 8B multi-athlete coaching execution (not for T5-09/T5-11 which
are unblocked independently by ADR-0046).

**Location:**
- New: `titan/orchestration/coaching_pipeline.py` — `coaching_pipeline()` function +
  `AthleteCoachingContext` dataclass
- New: `titan/orchestration/coaching_scheduler.py` — `CoachingScheduler` stub
- Modified: `titan/orchestration/daily_coach.py` — `run_morning_routine()` becomes
  a thin wrapper calling `coaching_pipeline()`

**Fix direction:**

1. Define `AthleteCoachingContext` dataclass in `titan/orchestration/coaching_pipeline.py`:
   - Fields: `athlete_id`, `athlete_profile`, `garmin_data`, `weather_snapshot`, engine
     instances (all per-athlete), `db`, governance context.
2. Extract the 12-step logic from `DailyCoach.run_morning_routine()` into
   `coaching_pipeline(ctx: AthleteCoachingContext, *, effect_runner) -> DailyCoachingPayload`.
   The function must be side-effect-free except through `effect_runner` callbacks
   (matching ADR-0018 Effect Runner contract).
3. Update `DailyCoach.run_morning_routine()` to construct `AthleteCoachingContext` from
   `self` and call `coaching_pipeline()`. All existing tests must continue to pass.
4. Add `CoachingScheduler` stub in `titan/orchestration/coaching_scheduler.py` with:
   - `register_athlete(athlete_id, schedule_config)` method
   - `start()` / `stop()` lifecycle
   - Internal `ThreadPoolExecutor` with configurable thread cap
   - Per-athlete overlap lock (same pattern as `DailyCoach._routine_lock`)
   - The scheduler fires `coaching_pipeline()` per athlete at scheduled time.
   - Stub-level implementation is sufficient for Phase 8B gate; full wiring is Phase 9.

**Acceptance criteria:**
- `coaching_pipeline()` and `AthleteCoachingContext` exist in
  `titan/orchestration/coaching_pipeline.py`.
- `DailyCoach.run_morning_routine()` delegates to `coaching_pipeline()` with no
  behaviour change observed by existing tests.
- `CoachingScheduler` stub exists in `titan/orchestration/coaching_scheduler.py` with
  the four methods above.
- All three mandatory gates pass (ruff + pytest -W error + pytest -q).
- New tests cover: `coaching_pipeline()` with a mock `effect_runner`; `CoachingScheduler`
  register/start/stop lifecycle; per-athlete overlap lock enforcement.
- **State isolation oracle (DEC-FR-07 — 2026-03-08):** A test verifies that calling
  `coaching_pipeline()` sequentially for two athletes with opposing readiness states (one
  nominal / governance-clean, one at hard-stop boundary) produces fully independent outputs
  with no state cross-contamination. This guards against temporal logic bugs where shared
  mutable state in engine instances bleeds between athlete contexts.

```bash
ruff check .
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort:** ~6h. Refactor extraction + dataclass + scheduler stub + tests.

**Phase 8B gate:** T5-16-A must be RESOLVED before any multi-athlete coaching execution
endpoint is built. T5-09, T5-11, T5-13 are independent — they are not blocked by T5-16-A.

---

### T5-17 · ACWR Engine — threshold literals not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: pending.
**Source:** Binder1 audit finding A5 / DEC-1 §3.2 (Architect DEC 2026-03-13). Category A policy thresholds confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR from test-gap fixes (T5-17 must not be bundled with S1–S3 execution items).
**Workflow Path:** A
**Cross-reference:** T1-05 (RESOLVED — dead ACWR duplicates in `constants.py`) is distinct. T1-05 removed dead code from `utils/constants.py`. T5-17 covers inline policy threshold literals remaining inside the science module itself.

**Original state (pre-fix):** The Category A ACWR literals `0.5`, `0.8`, `1.0`, `1.3`, `1.5`, and `1.7` were embedded directly in `titan/science/acwr_engine.py` and were not centralized under `titan/config/thresholds.py` with provenance records.

**Resolution:** Added six ACWR Category A constants to `titan/config/thresholds.py`, added matching provenance entries to `titan/config/evidence_registry.py`, and rewired `titan/science/acwr_engine.py` to reference only centralized thresholds for both `calculate_acwr()` and `injury_risk_score()`. Extended `tests/titan/science/test_acwr_engine_thresholds.py` with threshold-source boundary assertions and risk-score boundary coverage. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green at 1914 collected/passed tests.

**Task learning:** Boundary-oriented tests should consume threshold constants directly when extracting policy literals; this locks source-of-truth behavior and prevents silent reintroduction of inline policy values.

**Effort:** ~2h. Extraction + evidence registry + cross-reference tests.

---

### T5-18 · Adaptive Memory — Category A threshold literals not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: pending.
**Source:** Binder1 audit finding B4 / DEC-1 §4.2 (Architect DEC 2026-03-13). `1.08` and time windows confirmed Category A.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR required.
**Workflow Path:** A

**Original state (pre-fix):**
- `1.08` — pace threshold for mechanical load risk in `titan/science/adaptive_memory.py`: **Category A** (governance-facing risk output). Extract to `thresholds.py`.
- `24`, `36`, `48`, `72` — time window constants (hours) for SDI/supercompensation in `titan/science/adaptive_memory.py`: **Category A** (recalibration targets). Extract to `thresholds.py`.

**Scope explicitly excluded:** `2.5`, `2.0`, `1.5` multipliers — confirmed Category B (algorithm-local) by Architect Follow-up Pack 2026-03-14 (T5-19 NO_ACTION). These values remain inline. Do NOT extract.

**Resolution:** Added the five approved Category A constants (`1.08`, `24`, `36`, `48`, `72`) in `titan/config/thresholds.py` and added matching provenance entries in `titan/config/evidence_registry.py`. Updated `titan/science/adaptive_memory.py` to import and use only these centralized constants for supercompensation windows, session-density windows, and easy-pace-drop risk detection, while leaving `2.5/2.0/1.5` inline per T5-19 NO_ACTION. Extended `test_new_modules.py` AdaptiveMemory coverage to assert thresholds-source wiring and boundary behavior. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green at 1912 collected/passed tests.

**Task learning:** Category-A/Category-B partitioning must be encoded directly in tests during extraction work; this prevents accidental broadening where algorithm-local multipliers get centralized without architectural approval.

**Effort:** ~2h. Extraction + evidence registry entries.

---

### T5-19 · Adaptive Memory — multiplier constants classification required ✅ CLOSED (NO_ACTION) 2026-03-14

**Status:** ✅ CLOSED — NO_ACTION (Architect Follow-up Pack 2026-03-14)
**Source:** Binder1 audit finding B4 / DEC-1 §4.2.
**Type:** Open Question → RESOLVED
**Priority:** N/A — closed.
**Workflow Path:** A

**Architect Decision (2026-03-14):** The values `2.5`, `2.0`, `1.5` in `titan/science/adaptive_memory.py` are **Category B** (algorithm-local multipliers). They are internal scoring multipliers with no governance-facing output and no recalibration meaning. They remain inline. No extraction to `thresholds.py` required. T5-18 is unblocked. T5-18 scope does NOT expand to include these values.

---

### T5-20 · APL — DailyCoach → apl.resolve arg contract integration test missing ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: pending.
**Source:** Binder1 audit finding C2 / DEC-1 §5.2. Test gap confirmed.
**Type:** Test Gap
**Priority:** P3. Independent.
**Workflow Path:** A

**Original state (pre-fix):** DailyCoach had no integration-level assertion for the exact `apl.resolve()` call boundary, so phase normalization and `cs_tracker.confidence` argument propagation/type guarantees were not contract-protected.

**Resolution:** Added integration coverage in `tests/titan/orchestration/test_daily_coach.py` to assert exact kwargs passed from `DailyCoach.run_morning_routine()` into `apl.resolve()` including normalized phase (`BUILD`/default `BASE`) and confidence propagation. Applied a minimal call-site fix in `titan/orchestration/daily_coach.py` to pass `cs_confidence` through `_safe_float(..., 1.0)` so the integration contract is float-typed and stable. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green at 1909 collected/passed tests.

**Task learning:** Integration contracts at orchestrator→engine boundaries should assert argument names and normalized types, not only downstream payload shape, because silent type drift can bypass pure unit tests while still altering runtime policy behavior.

**Effort:** ~1h.

---

### T5-21 · Athlete Profile — athlete_id timestamp collision risk ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: b108421.
**Source:** Binder1 audit / DEC-2 §Athlete Profile finding. S2 hardening approved.
**Type:** Code Hardening
**Priority:** P2. Test-first required.
**Workflow Path:** A

**Original state (pre-fix):** `athlete_id` generation used timestamp with second-level precision, creating collision risk when two profiles were created in the same second and allowing silent overwrite.

**Resolution:** Added and expanded test-first collision coverage in `tests/titan/core/test_athlete.py` for same-second profile creation and exact timestamp+UUID seed collision paths. Hardened `UniversalAthleteProfile` ID generation in `titan/core/athlete.py` by appending a monotonic per-process sequence to the timestamp+UUID format so IDs remain unique even when both timestamp and UUID seed collide. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green at 1900 collected/passed tests.

**Task learning:** UUID entropy alone is not a proof of uniqueness under deterministic stubs; explicit collision-path tests enforce the contract and justify a deterministic tie-breaker in ID generation.

**Effort:** ~1h.

---

### T5-22 · Athlete Profile — to_dict/from_dict omits weight_ceiling and weight_panic fields ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: ed1e20a.
**Source:** Binder1 audit / DEC-2 §Athlete Profile finding. S2 hardening approved.
**Type:** Serialization Contract
**Priority:** P2. Test-first required.
**Workflow Path:** A

**Original state (pre-fix):** Serialization round-trips were incomplete: while `weight_ceiling` / `weight_panic` required explicit guardrail coverage, `critical_speed_m_per_s` and `d_prime_m` were not hydrated by `from_dict()`, so those fields reset to constructor defaults instead of preserving profile-specific values.

**Resolution:** Added/extended test-first coverage in `tests/titan/core/test_athlete.py` for guardrail round-trip preservation (`weight_ceiling`, `weight_panic`), exact round-trip completeness for `critical_speed_m_per_s` / `d_prime_m`, and missing-field default boundary behavior. Updated `UniversalAthleteProfile.from_dict()` in `titan/core/athlete.py` to hydrate `critical_speed_m_per_s` and `d_prime_m` with contract defaults when absent. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green at 1902 collected/passed tests.

**Task learning:** Serialization contracts can drift asymmetrically (`to_dict` updated while `from_dict` lags), so an exact round-trip test for every persisted field is the fastest way to detect silent default reintroduction before state flows into orchestration.

**Effort:** ~1h.

---

### T5-23 · Autonomic Fusion Engine — docstring claims ±20/+10 range, formula is ±15 ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: 0f5fede.
**Source:** Binder1 audit / DEC-2 §AFI finding. Architect decision: formula is authoritative; docstring is wrong.
**Type:** Documentation Correction
**Priority:** P4. Independent.
**Workflow Path:** A

**Original state (pre-fix):** `titan/science/autonomic_engine.py` documented `afi_modifier` as `-20..+10` in `get_readiness_constraints()`, while the authoritative formula `round(afi_final * 15)` already produced a symmetric `[-15, +15]` range.

**Resolution:** Added test-first AFI range coverage in `tests/test_science_engines.py` to assert the exact no-HRR formula boundaries (`-0.65` and `+0.65`) and to assert the documentation-facing range string for `calculate_afi()`. Updated the `calculate_afi()` docstring in `titan/science/autonomic_engine.py` so the documented range behavior matches the authoritative formula without changing the AFI formula itself. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green at 1904 collected/passed tests.

**Task learning:** Optional-signal formulas need explicit documentation of both "signal present" and "signal absent" ranges; otherwise, mathematically correct code can still expose contract ambiguity at integration boundaries.

**Effort:** ~30 minutes.

---

### T5-24 · Biomechanics Engine — orchestration contract typed as `object` ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: ed1e20a.
**Source:** Binder1 audit / DEC-2 §Biomechanics Engine Pattern P7 finding.
**Type:** Architecture Debt
**Priority:** P4. Independent. Not before its turn in execution order.
**Workflow Path:** A
**Cross-reference:** T4-26 (RESOLVED 2026-03-07) addressed the orchestration contract layer broadly. T5-24 captures the specific `biomechanics: object` annotation gap not covered by T4-26's resolution scope.

**Architect Brief (issued 2026-03-14):**
- **Typed artifact:** `BiomechanicsEngineProtocol` (a `Protocol` class, not `TypedDict`)
- **Location:** `titan/orchestration/contracts.py`
- **Method:** Perform call-site audit first — identify every method of `BiomechanicsEngine` that is actually consumed by the orchestration layer. Define the `Protocol` only for methods that are genuinely consumed. No speculative interface surface.
- **Constraint:** Do not add methods to the Protocol that are not already called at real call sites. Surface area must match actual consumption, not the full engine API.

**Scope (approved for execution):**
1. Read-only call-site audit: map every reference to `BiomechanicsEngine` in `titan/orchestration/` and any other layer that consumes it.
2. Define `BiomechanicsEngineProtocol` in `titan/orchestration/contracts.py` covering only the consumed methods.
3. Update the orchestration contract annotation from `object` to `BiomechanicsEngineProtocol`.
4. Add/update tests in `tests/titan/orchestration/test_contracts.py` to assert Protocol compliance.

**Acceptance gates (binary):**
- `BiomechanicsEngineProtocol` exists in `titan/orchestration/contracts.py`
- Protocol surface covers only methods verified as consumed at real call sites (no speculative methods)
- Orchestration layer annotation updated from `object`
- Test asserting Protocol compliance passes
- All three mandatory gates green

---

### T5-25 · Database Manager — SQLite/PostgreSQL interface parity matrix absent 🔴 OPEN

**Status:** OPEN (Phase 8 — Binder1 audit; DEC-2 approved 2026-03-13; **DEBT ONLY / NO IMPLEMENTATION — Architect Follow-up Pack 2026-03-14**)
**Source:** Binder1 audit / DEC-2 §Database Manager Pattern P7 variant finding.
**Type:** Architecture Debt — design artefact
**Priority:** P4. Related to T5-08-B but distinct scope.
**Workflow Path:** A
**Cross-reference:** T5-08-B (OPEN — full ADR-0044 PostgreSQL migration) addresses implementation. T5-25 addresses the **interface parity matrix** as a documented architectural contract (what methods/behaviours must be identical across both backends). These are related but distinct debt items.

**Architect Decision (2026-03-14):** This is a **design artefact / parity matrix document**, not a code task. No Codex implementation handoff is permitted for T5-25 at this stage.

**Sequencing constraint:** The parity matrix document must exist before T5-08-B D7 and D9 can be closed. It is a prerequisite for those deliverables. T5-25 is NOT blocked by T5-08-B — it may be authored independently — but it must be complete before T5-08-B D7/D9 are declared DONE.

**Scope:** Produce a documented parity matrix specifying which methods and behaviours must be identical across `SQLiteDatabaseManager` and `PostgreSQLDatabaseManager`, and what backend-specific divergence (if any) is explicitly permitted. Output is a document (architecture artefact), not code.

**Acceptance gate (binary):** Parity matrix document exists and is accepted by Architect; T5-08-B D7 and D9 may not close without it.

---

### T5-26 · Drift Engine — analyze_cardiac_drift wrapper missing from public API ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: d985d67.
**Source:** Binder1 audit / DEC-2 §Drift Engine finding. S1-CRITICAL. Approved fix: option (a) — add wrapper to `DriftEngine`.
**Type:** API Contract
**Priority:** P1. Test-first required. Highest priority within Binder1 batch.
**Workflow Path:** A

**Original state (pre-fix):** `main.py` `cb_drift` callback called `drift_eng.analyze_cardiac_drift(...)` but `DriftEngine` did not expose that method, producing an `AttributeError` risk at runtime.

**Resolution:** Added `analyze_cardiac_drift()` wrapper to `DriftEngine` with guard handling for insufficient input and a stable payload contract (`drift_percent`, `assessment`, `lt_zone`), plus a new mirrored test module `tests/titan/science/test_drift_engine.py` covering the real `cb_drift` path and drift engine public methods. Final full-suite gate at closure: 1852 passed.

**Task learning:** Telegram callback integrations can silently mask API contract drift by catching exceptions and returning user-facing error strings; a real-engine callback path test is necessary to keep orchestration wiring and engine public APIs aligned.

**Effort:** ~2h.

---

### T5-27 · Durability Engine — Category A threshold literals not centralized in thresholds.py 🔴 OPEN

**Status:** ✅ RESOLVED 2026-03-14. Commit: 3d6284e.
**Source:** Binder1 audit / DEC-2 §Durability Engine Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR after S1–S3 execution items.
**Workflow Path:** A

**Scope:** The following inline literals in `titan/science/durability_engine.py` are Category A policy thresholds: `2`, `5`, `8` (pace durability bands), `85`, `90`, `95`, `98` (durability index bands), `88`, `93`, `96` (training protocol bands). Extract to `thresholds.py`.

**Acceptance gate (binary):** Same pattern as T5-17. Zero inline literals remain for listed values; `thresholds.py` + `evidence_registry.py` updated; all gates green.

**Effort:** ~2h.

---

### T5-28 · Fatigue Engine — soreness threshold literal not centralized in thresholds.py 🔴 OPEN

**Status:** ✅ RESOLVED 2026-03-14. Commit: 3d6284e.
**Source:** Binder1 audit / DEC-2 §Fatigue Engine Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Scope:** Inline threshold `>= 5` (soreness score trigger in `titan/science/fatigue_engine.py`) is Category A — governance-facing policy threshold. Note: `SUBJECTIVE_FATIGUE_2OF4 = 6` is already in `thresholds.py`. The `>= 5` literal may represent a distinct policy threshold requiring its own named constant. Extract to `thresholds.py` with STRONG/HEURISTIC provenance.

**Acceptance gate (binary):** Same pattern as T5-17.

**Effort:** ~1h.

---

### T5-29 · Garmin Live Sync — sleep/HRV partial-failure policy inconsistency 🔴 OPEN

**Status:** ✅ RESOLVED 2026-03-14. Commit: 3d6284e.
**Source:** Binder1 audit / DEC-2 §Garmin Live Sync finding. Architect decision: align `sync_sleep()` to per-day best-effort model.
**Type:** Behavior Contract
**Priority:** P2. Intentional behavior change — test-first required.
**Workflow Path:** A

**Scope:** `sync_sleep()` aborts the entire date range on a single failure; `sync_hrv()` uses per-day best-effort (continues on individual day failures). Architect decision: align `sync_sleep()` to the per-day best-effort model for consistency.

**Fix (approved):** Test first: assert new per-day contract for `sync_sleep()` → apply minimal fix → test green.

**Acceptance gate (binary):** Failing test written first → fix applied → test green → all gates green.

**Effort:** ~2h.

---

### T5-30 · Governance Engine — class-local threshold literals not centralized in thresholds.py 🔴 OPEN

**Status:** ✅ RESOLVED 2026-03-14. Commit: 3d6284e.
**Source:** Binder1 audit / DEC-2 §Governance Engine Pattern P5 finding. Category A confirmed by architect in DEC-2.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A
**Cross-reference:** T1-04 (RESOLVED 2026-03-02 — "Hardcoded safety thresholds bypassing thresholds.py") did not cover these specific class-local values. T5-30 is a missed case from T1-04's resolution scope.

**Scope:** Class-local thresholds `0.80` and `0.70` in `titan/science/governance_engine.py` are Category A policy thresholds. Extract to `thresholds.py`.

**Acceptance gate (binary):** Same pattern as T5-17. `governance_engine.py` references constants from `thresholds.py`; no inline literals remain for these values; all gates green.

**Effort:** ~1h. Extraction only.

---

### T5-31 · Intensity Governor — threshold literals not centralized in thresholds.py 🔴 OPEN

**Status:** ✅ RESOLVED 2026-03-14. Commit: 3d6284e.
**Source:** Binder1 audit / DEC-2 §Intensity Governor Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Scope:** Inline threshold literals in `titan/science/intensity_governor.py`: `3.5`, `5.0`, `4.0`, `6.0`, `1.3`, `1.5`, `55`, `40` — all Category A policy thresholds. Extract to `thresholds.py`.

**Acceptance gate (binary):** Same pattern as T5-17.

**Effort:** ~2h.

---

### T5-32 · Lactate Logic — threshold literals not centralized in thresholds.py 🔴 OPEN

**Status:** ✅ RESOLVED 2026-03-14. Commit: 3d6284e.
**Source:** Binder1 audit / DEC-2 §Lactate Logic Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Scope:** Inline threshold literals in `titan/science/lactate_logic.py`: `3.0`, `78.0`, `6.0`, `7.0` — Category A policy thresholds (LT1/LT2 boundary zone). Extract to `thresholds.py`.

**Acceptance gate (binary):** Same pattern as T5-17.

**Effort:** ~1h.

---

### T5-33 · Periodization/Automated — implicit coupling contract absent 🔴 BLOCKED PENDING MORE INPUT

**Status:** BLOCKED PENDING MORE INPUT (Architect Follow-up Pack 2026-03-14 — read-only audit required before any brief can be written)
**Source:** Binder1 audit / DEC-2 §Periodization + Equipment Pattern P7 variant finding.
**Type:** Architecture Debt
**Priority:** P4. No implementation. Audit-only next step.
**Workflow Path:** A

**Scope:** `titan/core/periodization.py` and `titan/science/automated_periodization.py` have an implicit coupling contract with no formal boundary test or typed interface. Architectural coupling risk. No implementation before dedicated architect brief.

**Required Codex read-only audit (before brief can be written):**
The architect requires answers to the following three questions from a read-only audit of `titan/core/periodization.py` and `titan/science/automated_periodization.py`. No code changes. No implementation.

a) **Direction:** Who calls whom? Does `automated_periodization.py` call into `core/periodization.py`, or the reverse, or is there bidirectional coupling?
b) **Layer violation:** Is there a layer violation across the `core/` ↔ `science/` boundary? (i.e., does a science module import from core, or does core import from science — in either direction?)
c) **Shared mutable state:** Is there any shared mutable state between the two modules (e.g., shared object references, shared DB handles, shared in-memory structures)?

**Next step:** Codex performs read-only audit, answers (a)–(c). Architect then writes brief. No implementation until brief is accepted.

**Acceptance gate (binary):** Defined when brief is written (after audit answers are received).

---

### T5-34 · Setup Wizard — dual bootstrap contract divergence (titan vs launcher wizard) 🔴 BLOCKED PENDING MORE INPUT

**Status:** BLOCKED PENDING MORE INPUT (Architect Follow-up Pack 2026-03-14 — contract-first, read-only audit required before implementation)
**Source:** Binder1 audit / DEC-2 §Setup Wizard Pattern S4 finding.
**Type:** Architecture Debt
**Priority:** P4. No implementation yet. Contract-first.
**Workflow Path:** A
**Cross-reference:** T4-07 (RESOLVED — wizard credential duplicates), T4-12 (RESOLVED — wizard interactive flow tests) are distinct. T5-34 addresses the architectural divergence between the `titan/ui/setup_wizard.py` and `launcher/wizard.py` bootstrap contracts — a different concern not covered by T4-07/T4-12.

**Scope:** Two wizard implementations (`titan/ui/setup_wizard.py` and `launcher/wizard.py`) have diverging contracts (env persistence, validation logic, error handling). Architectural consistency risk for first-run setup flows.

**Required Codex read-only audit (before brief can be written):**
The architect requires a read-only audit mapping the divergence between the two wizard implementations. No code changes. No implementation. Contract-first.

Audit scope:
- **`titan/ui/setup_wizard.py`:** What does it write to env / config? What fields does it validate? What are the validation rules?
- **`launcher/wizard.py`:** What does it write to env / config? What fields does it validate? What are the validation rules?
- **Divergence map:** Where do the two implementations produce different outputs, apply different validation, or handle errors differently? Produce a side-by-side delta.

**Next step:** Codex performs read-only audit and produces divergence map. Architect then writes implementation brief. No implementation until brief is accepted.

**Acceptance gate (binary):** Defined when brief is written (after divergence map is received).

---

### T5-35 · Volume Load Gauge — threshold literals not centralized in thresholds.py 🔴 OPEN

**Status:** ✅ RESOLVED 2026-03-14. Commit: 3d6284e.
**Source:** Binder1 audit / DEC-2 §Volume Load Gauge Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Scope:** Inline threshold literals in `titan/science/volume_load_gauge.py`: `-30` (TSB floor band), `0.7`, `0.8`, `1.3`, `1.5` (ACWR bands), `4`, `7` (glycogen debt bands) — Category A policy thresholds. Extract to `thresholds.py`. Note: some of these (e.g. `0.8`, `1.3`, `1.5`) may overlap with T5-17 (ACWR engine constants) — when implementing, verify whether a shared constant or a per-module constant is architecturally correct.

**Acceptance gate (binary):** Same pattern as T5-17.

**Effort:** ~2h.

---

### T2-18 · CTL/ATL decay windows are inline default parameters — not centralized in thresholds.py ✅ RESOLVED 2026-03-08

**Status:** ✅ RESOLVED 2026-03-08. Commit: 54e95d9.
**Workflow Path: A** *(targeted constant promotion + CI guard)*
**Source:** DEC-FR-04 — Future Risk Analysis 2026-03-08. Verified: `tsb_engine.py:17,27`.

**Original state (pre-fix):**

`TSBEngine.calculate_ctl(decay: int = 42)` and `calculate_atl(decay: int = 7)` defined the
canonical CTL/ATL EMA windows as inline default parameters. These windows were architectural
constants (Banister model — exercise science consensus), not tuneable per-run options. No
entry existed in `thresholds.py` or `evidence_registry.py`.

**Resolution:**

- Added canonical constants `CTL_DECAY_DAYS` and `ATL_DECAY_DAYS` in
  `titan/config/thresholds.py` and added STRONG provenance entries in
  `titan/config/evidence_registry.py`.
- Updated CTL/ATL runtime calculations to consume the centralized constants in:
  `titan/science/tsb_engine.py`, `titan/core/database.py`,
  `titan/orchestration/daily_coach.py`, and legacy exports in
  `titan/utils/constants.py`.
- Updated tests to enforce canonical usage and boundary behavior when decay
  constants change: `tests/titan/science/test_tsb_engine.py`,
  `tests/test_physiological_bounds.py`, and `tests/test_constants_hygiene.py`.
- Mandatory gates passed at closure:

```bash
ruff check .
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Test count at closure:** 1820 passed.

---

### T2-19 · No nominal-state coherence oracle for quality sessions — silent over-conservative governance drift undetectable ✅ RESOLVED 2026-03-08 (future-risk-analysis)

**Status:** RESOLVED — implemented in `tests/test_science_edge_cases.py` as part of
Future Risk Analysis session 2026-03-08.

**Source:** DEC-FR-10 — Future Risk Analysis 2026-03-08.

**Gap addressed:**

`test_governance_remains_clean_for_healthy_input_profile()` verified governance-clean for
`session_type="EASY", max_zone=2` under nominal inputs. No test verified that a quality
session (`INTERVALS + max_zone=5`) — which routes through the VO2 eligibility gate —
also passes cleanly under fully nominal conditions. A regression in the VO2 gate logic
(wrong comparison, off-by-one, threshold inversion) would leave all easy-session tests
green while silently blocking all high-intensity sessions.

**Resolution:**

Added `test_governance_approves_quality_session_under_nominal_conditions()` to
`tests/test_science_edge_cases.py`. The oracle asserts: given `_quality_session()` (INTERVALS,
max_zone=5) and `_healthy_context()` (all metrics nominal), `governance_clean` is True
with no locks and no hard stops. Failure message includes the full lock and hard-stop lists
for immediate diagnostic value.

---

### PILOT-01 · Opus QA layer — automated test-quality review between Codex and mandatory gates 🟡 PILOT

**Status:** PILOT — not permanent. Activate on next Phase 8 sprint item; evaluate after one sprint.
**Recorded:** 2026-03-08 (E14 — idea captured before implementation).

**Applicability gate — classify the item before activating PILOT-01:**

PILOT-01 runs **by default** only when ALL of the following hold:
- Effort estimate ≤ 1 day (≤ ~6h).
- No schema changes (no `CREATE TABLE`, `ALTER TABLE`, column additions, or Alembic migration).
- No cross-subsystem dependency changes (does not alter import graph between packages).
- Scope limited to ≤ 2 modules (production code side).

PILOT-01 is **opt-in only** (requires explicit architect APPROVED note in this entry before
Codex activates it) when the item involves any of:
- Schema migration or database backend replacement (e.g. T5-07 Layer 1, T5-08 PostgreSQL).
- Architectural refactor — kernel boundary changes, subsystem extraction, god-object splits.
- Multi-tier change — touches governance infrastructure (Tier 1–4) across ≥ 2 tiers.
- Effort > 1 day or item is explicitly labelled P0.

**Fallback (non-negotiable):** If the applicability conditions are not met, PILOT-01 must not
run. Codex proceeds directly to the mandatory gates workflow. No QA step is inserted.

Rationale: the Opus QA reviewer operates on test quality within a bounded implementation
context. For migration and refactor items the reviewer lacks the schema diff, migration
sequence, and cross-module coupling context required to make a valid coverage judgement.
A REJECT in that context adds friction without diagnostic value and risks incorrect advice.

**Motivation:** Codex's test output passes gates mechanically (ruff + pytest) but may miss semantic
gaps: undertested edge cases, missing invariant coverage, acceptance criteria not fully exercised.
An automated QA pass before the gates can catch these earlier and reduce back-and-forth.

**Protocol design (pilot version):**

```
Codex implements item
  └─► Opus QA review (test quality only — see scope below)
        ├─ APPROVE  →  Codex runs mandatory gates → DONE
        └─ REJECT   →  Codex fixes, re-submits to Opus once
                          └─ Opus re-review (one re-review max)
                                └─ Codex runs mandatory gates → DONE
```

**Scope of Opus QA (bounded — do not expand without updating this entry):**
- Do the tests actually cover the acceptance criteria in the debt item?
- Are the critical edge cases exercised (boundary values, error paths, invariant violations)?
- Are regression tests present for any behaviour that was broken or changed?
- Are parametrize / property-based tests used where the input space warrants it?

**Out of scope for Opus QA (explicit exclusions):**
- Architectural decisions — those belong to Claude (architect role).
- Code style, naming, formatting — ruff handles this.
- Implementation correctness — mandatory gates (pytest) handle this.
- Overriding or substituting the mandatory gates — see invariant below.

**Mandatory gates invariant (non-negotiable):**
> Opus QA approval is an advisory signal only.
> The three mandatory gates (ruff, pytest strict, pytest full) are the **sole binding DONE criterion**.
> A PR is NOT done until all three gates are clean — regardless of Opus QA status.
> Opus QA approval does NOT mean gates have passed.

**Pilot success criteria (binary — evaluate after first Phase 8 sprint item):**
1. Opus QA identified at least one gap that would not have been caught by the gates alone.
2. The QA loop completed within one fix cycle (no more than one re-review required).
3. Total wall-clock overhead added to the sprint item ≤ 20% of implementation time.
4. No gate failures caused by Opus QA advice (i.e. Opus did not recommend changes that broke gates).

**If pilot passes all four criteria:** promote to permanent protocol in `AGENTS.md §17` +
update `CLAUDE.md` agent roster. Author ADR-0046 documenting the decision.

**If pilot fails:** close this entry as REJECTED, document root cause here, do not retry
without architectural discussion.

---

All Tier 5 decisions up to T5-16-A have been locked or deferred. T5-17 through T5-35 are new entries from the Binder1 audit triage (DEC-1 + DEC-2, 2026-03-13). T5-19, T5-24, T5-25, T5-33, T5-34 are blocked pending architect input or brief. See Tracking table for completion dates and PRs.
Relevant ADRs: 0013 (UI path), 0014 (ML scaffold), 0015 (SQLite/multi-athlete), 0016 (multi-sport), 0022 (Phase 8 gate), 0028 (complexity budget), 0032 (ML explainability), 0033 (model aging), 0035 (feedback loop), 0036 (semantic versioning), 0043 (product direction + LLM seams), 0044 (PostgreSQL migration), 0045 (local LLM backend abstraction).

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
| T2-02 | ✅ RESOLVED | PR: TBD |
| T2-03 | ✅ RESOLVED | PR: TBD |
| T2-04 | ✅ RESOLVED | PR: TBD |
| T2-05 | ✅ RESOLVED | PR: TBD |
| T2-06 | 2026-03-04 | PR: TBD |
| T2-07 | ✅ RESOLVED | PR: TBD |
| T2-08 | ✅ RESOLVED | PR: TBD |
| T3-01 | 2026-03-03 | [#172](https://github.com/zafiriss-ux/project-mayhem/pull/172) |
| T3-02 | 2026-03-04 | PR: TBD |
| T3-03 | 2026-03-04 | PR: TBD |
| T3-04 | 2026-03-04 | PR: TBD |
| T3-05 | 2026-03-04 | PR: TBD |
| T4-01 | 2026-03-03 | [#167](https://github.com/zafiriss-ux/project-mayhem/pull/167) |
| T4-02 | ✅ RESOLVED | PR: TBD |
| T4-03 | 2026-03-04 | PR: TBD |
| T4-04 | ✅ RESOLVED | PR: TBD |
| T4-05 | ✅ RESOLVED | PR: TBD |
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
| T4-15 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-16 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-17 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-18 | ✅ RESOLVED | 2026-03-06 |
| T4-19 | ✅ RESOLVED | 2026-03-06 |
| T4-20 | ✅ RESOLVED | 2026-03-06 |
| T1-18 | ✅ RESOLVED | 2026-03-07 |
| T1-19 | ✅ RESOLVED | 2026-03-07 |
| T1-20 | ✅ RESOLVED (independent) | 2026-03-07 |
| T2-14 | ✅ RESOLVED | 2026-03-07 |
| T2-15 | ✅ RESOLVED | 2026-03-07 |
| T4-21 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 07a9361) |
| T4-22 | ✅ RESOLVED (independent) | 2026-03-07 (commit: a2a9961) |
| T4-23 | ✅ RESOLVED | 2026-03-07 (commit: bd2da17) |
| T4-24 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 0590862) |
| T4-25 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 9dd54af) |
| T4-26 | ✅ RESOLVED (independent) | 2026-03-07 (commit: e40181a) |
| T4-27 | ✅ RESOLVED | 2026-03-07 (commit: 33e8255) |
| T4-28 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 92555d3) |
| T5-04 | OPEN (deferred — Phase 9+) | — |
| T5-05 | OPEN (deferred — Phase 9+) | — |
| T5-06 | OPEN (T5-06-A: Phase 8A early work, before Phase 8B; T5-06-B: deferred Phase 9) | — |
| T1-21 | ✅ RESOLVED | 2026-03-07 |
| T1-22 | ✅ RESOLVED | 2026-03-07 |
| T1-23 | ✅ RESOLVED (independent; Phase 8 entry gate) | 2026-03-07 |
| T2-16 | ✅ RESOLVED | 2026-03-07 |
| T2-17 | ✅ RESOLVED (independent) | 2026-03-07 |
| T5-14 | OPEN (Phase 8 scheduled — formerly T4-29; reclassified 2026-03-07) | — |
| T5-15 | DEFERRED (Phase 9 housekeeping — test marker taxonomy) | — |
| T4-30 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-31 | ✅ RESOLVED (IMMEDIATE — AGENTS.md §16.10 active) | 2026-03-07 (commit: eb20bb2) |
| T4-32 | ✅ RESOLVED | 2026-03-07 (commit: dfe8907) |
| T5-07 | ✅ RESOLVED (Layers 1–2) — 2026-03-13 (commit: b6bea2a); Layer 3: deferred Phase 9 | 2026-03-13 |
| T5-08 | ⚠️ PARTIAL (scaffold only; D6 done; D1–D5, D7–D9 open — see T5-08-B) | 2026-03-08 |
| T5-08-B | 🔴 OPEN — D1 DONE (2026-03-08); D2a DONE (2026-03-13, commit: df449e7); D2b DONE (2026-03-13, commit: d7ad4b7); D2c DONE (2026-03-13, commit: f6901b6); D3 DONE (2026-03-13, commit: pending); D4 DONE (2026-03-13, commit: pending); D5 DONE (2026-03-13, commit: pending); **complete D2 finished**; D7, D9 remaining | D1: 2026-03-08; D2a: 2026-03-13; D2b: 2026-03-13; D2c: 2026-03-13; D3: 2026-03-13; D4: 2026-03-13; D5: 2026-03-13 |
| T5-09 | OPEN (Phase 8B prerequisite) | — |
| T5-10 | OPEN (deferred — Phase 10) | — |
| T5-11 | OPEN (Phase 8B entry gate — auth ADR required first) | — |
| T5-12 | OPEN (risk monitoring; mitigation design Phase 8C) | — |
| T5-13 | OPEN (Phase 8B entry gate — GDPR) | — |
| T5-16 | ✅ RESOLVED — ADR-0046 accepted; T5-16-A implementation entry created | 2026-03-08 |
| T5-16-A | OPEN (Phase 8B — coaching_pipeline() extraction + CoachingScheduler stub) | — |
| T5-17 | ✅ RESOLVED (Phase 8 — ACWR threshold extraction to thresholds.py; separate PR) | 2026-03-14 |
| T5-18 | ✅ RESOLVED (Phase 8 — Adaptive Memory 1.08 + time windows extraction; scope respected: 1.08 + 24/36/48/72 only; Category B 2.5/2.0/1.5 left inline per T5-19) | 2026-03-14 |
| T5-19 | ✅ CLOSED — NO_ACTION (2026-03-14): 2.5/2.0/1.5 confirmed Category B; remain inline; T5-18 unblocked | 2026-03-14 |
| T5-20 | ✅ RESOLVED | 2026-03-14 |
| T5-21 | ✅ RESOLVED (Phase 8 — Athlete Profile athlete_id uniqueness hardening; test-first) | 2026-03-14 |
| T5-22 | ✅ RESOLVED (Phase 8 — Athlete Profile serialization completeness incl guardrails + CS/D'; test-first) | 2026-03-14 |
| T5-23 | ✅ RESOLVED (Phase 8 — AFI no-HRR range docstring correction; formula unchanged) | 2026-03-14 |
| T5-24 | ✅ RESOLVED (BiomechanicsEngineProtocol in contracts.py; call-site audit complete; brief issued 2026-03-14) | 2026-03-14 (commit: ed1e20a) |
| T5-25 | OPEN (Phase 8 — DB Manager SQLite/PostgreSQL parity matrix; **DEBT ONLY / NO IMPLEMENTATION**; design artefact; must exist before T5-08-B D7/D9 close) | — |
| T5-26 | ✅ RESOLVED | 2026-03-14 |
| T5-27 | OPEN (Phase 8 — Durability Engine threshold extraction; separate PR) | — |
| T5-28 | OPEN (Phase 8 — Fatigue Engine soreness threshold extraction; separate PR) | — |
| T5-29 | OPEN (Phase 8 — Garmin sync sleep/HRV partial-failure policy; test-first) | — |
| T5-30 | OPEN (Phase 8 — Governance Engine class-local threshold extraction; separate PR after S1-S3) | — |
| T5-31 | OPEN (Phase 8 — Intensity Governor threshold extraction; separate PR) | — |
| T5-32 | OPEN (Phase 8 — Lactate Logic threshold extraction; separate PR) | — |
| T5-33 | BLOCKED PENDING MORE INPUT (read-only audit required: call direction, layer violation, shared mutable state; no implementation) | — |
| T5-34 | BLOCKED PENDING MORE INPUT (read-only audit required: divergence map of titan/ui/setup_wizard.py vs launcher/wizard.py; contract-first; no implementation) | — |
| T5-35 | OPEN (Phase 8 — VLG threshold extraction; separate PR; cross-check overlap with T5-17) | — |
| ADR-0018 Phase B (G9) | ✅ IMPLEMENTED — G9 cleared | 2026-03-08 (commit: c51e217) |
| T2-18 | ✅ RESOLVED | 2026-03-08 |
| T2-19 | ✅ RESOLVED — nominal coherence oracle implemented | 2026-03-08 |

*This document is the single source of truth for technical debt. Update it when items are
resolved, not in commit messages alone.*

*Last updated: 2026-03-08 — Future Risk Analysis session. 11-category forward risk review
(DEC-FR-01 through DEC-FR-11). Actions: T2-18 (CTL/ATL constant centralization — RESOLVED);
T2-19 (nominal coherence oracle — RESOLVED, implemented in test_science_edge_cases.py);
T5-05 augmented with Phase 9 calibration design constraints (damping, domain baseline snapshot);
T5-16-A acceptance criteria augmented with state isolation oracle requirement.
CLAUDE.md snapshot updated 1791→1820 at T2-18 close.*

*Updated: 2026-03-08 — QA FAIL on T5-08 (PostgreSQL scaffold). T5-08 status corrected: RESOLVED → PARTIAL.
T5-08-B created (ADR-0044 D1–D5, D7–D9 — full PersistenceAdapter + Alembic + RLS + consent schema migration).
OBS-007 written + DEC-007 processed (SCRATCHPAD.md): ADR Deliverable Checklist added as mandatory process
rule at task closure for any task referencing an ADR with a numbered deliverable table.*

*Updated: 2026-03-08 — Architect review of T5-08-B D1 (QA PASS report from Codex/Opus). D1 accepted as
interface contract DONE (PersistenceAdapter ABC + SQLiteAdapter parity; 1841 tests green). SQLAlchemy Core
PostgreSQL query implementation (30 methods) folded into D2 scope — queries must be written against the
schema defined by D2 Alembic migration. T5-08-B deliverable table updated to ADR Deliverable Checklist
format with per-row status. AGENTS.md updated: (1) diagnostic runs clarification added to HARD GATE
forbidden shortcuts; (2) QA role boundary note added to §17.3 Path B. Next deliverable: D2.*

*Updated: 2026-03-13 — Architect verdict: T5-08-B D2 split into three strictly sequential child deliverables:
D2a (Alembic migration for 5 tables) → D2b (SQLAlchemy Core implementation for 30 PostgreSQLAdapter methods)
→ D2c (PostgreSQL concurrency stress tests, satisfying OBS-005 deferred criterion). Codex must not continue
with the old monolithic D2. D3 dependency is unchanged — D3 begins only after D2c is DONE. No new ADR
created; no implementation performed; no architectural decisions invented. Deliverable table and status line
updated accordingly. Next deliverable: D2a.*

*Updated: 2026-03-13 — Binder1 audit triage complete. DEC-1 (ACWR / Adaptive Memory / APL) and DEC-2 (remaining 29 modules) issued by Architect. T5-17 through T5-35 registered (19 new entries). T5-19 BLOCKED (architect clarification required on Adaptive Memory 2.5/2.0/1.5 multipliers). T5-24, T5-25, T5-33, T5-34 debt-only (require dedicated brief before implementation). Records steward pass — no implementation performed, no new architectural decisions. Codex MAY START execution only after deterministic baseline confirmed (≥1845 passed) and per DEC-2 §9 Execution Authorization conditions.*

*Updated: 2026-03-14 — Records Steward Follow-up Pass (Architect Follow-up Pack 2026-03-14). Six records updates applied:*
*(1) T5-19 CLOSED NO_ACTION: 2.5/2.0/1.5 multipliers confirmed Category B (algorithm-local); remain inline; no extraction required.*
*(2) T5-18 UNBLOCKED: scope confirmed as 1.08 + 24/36/48/72 only; 2.5/2.0/1.5 explicitly excluded from scope.*
*(3) T5-24 brief issued: BiomechanicsEngineProtocol in titan/orchestration/contracts.py; call-site audit first; Protocol covers only consumed methods; no speculative surface.*
*(4) T5-25 confirmed DEBT ONLY / NO IMPLEMENTATION: design artefact (parity matrix document); sequencing constraint: must exist before T5-08-B D7/D9 close.*
*(5) T5-33 re-classed BLOCKED PENDING MORE INPUT: read-only audit required (call direction, layer violation, shared mutable state) before brief can be written.*
*(6) T5-34 re-classed BLOCKED PENDING MORE INPUT: read-only audit required (divergence map: titan/ui/setup_wizard.py vs launcher/wizard.py) before brief can be written.*
*No implementation performed. No new architectural decisions. No renumbering.*

---

## Codex Handoff Blocks (Records Steward — 2026-03-14)

> These blocks are prepared by the records steward for the next Codex session. They are informational only.
> Codex must run all mandatory gates (ruff, pytest -W error, pytest) before beginning any implementation.

### Block A — Immediate Next Implementation Task

**Governance Contracts S1 Hardening**

This is the current execution lane, unchanged after T5-26 closure. Codex resumes Governance Contracts S1 hardening per the existing task queue. No new task branching. No blocked items from T5-24 / T5-25 / T5-33 / T5-34 are in this lane.

Execution order for S1 hardening is defined by the existing TECHNICAL_DEBT.md task sequence. T5-18 is now unblocked (T5-19 closed) and may be scheduled in its normal position in the T5-1x execution queue.

---

### Block B — Architect-Approved Future Implementation Item

**T5-24 · BiomechanicsEngineProtocol**

Status: Brief issued 2026-03-14. NOT yet in execution queue — not before its turn in execution order.

When T5-24 reaches its turn:
1. Perform call-site audit (read-only): map all references to `BiomechanicsEngine` in `titan/orchestration/` and consuming layers.
2. Define `BiomechanicsEngineProtocol` in `titan/orchestration/contracts.py` — consumed methods only, no speculative surface.
3. Update orchestration contract annotation from `object` to `BiomechanicsEngineProtocol`.
4. Add Protocol compliance test in `tests/titan/orchestration/test_contracts.py`.
5. All three mandatory gates green.

Do NOT begin T5-24 implementation until it is assigned in execution order.

---

### Block C — Audit-Only Handoff (T5-33)

**T5-33 · Periodization/Automated — read-only audit**

Task: Read `titan/core/periodization.py` and `titan/science/automated_periodization.py`. No code changes. Answer three questions:

a) Who calls whom? (direction of coupling)
b) Is there a layer violation across core/ ↔ science/?
c) Is there any shared mutable state between the two modules?

Return answers to Architect. No implementation. No brief writing. No TECHNICAL_DEBT.md changes.

---

### Block D — Audit-Only Handoff (T5-34)

**T5-34 · Setup Wizard — read-only audit**

Task: Read `titan/ui/setup_wizard.py` and `launcher/wizard.py`. No code changes. Produce a divergence map covering:

- What `titan/ui/setup_wizard.py` writes/validates (env fields, validation rules, error handling)
- What `launcher/wizard.py` writes/validates (env fields, validation rules, error handling)
- Where they diverge (side-by-side delta)

Return divergence map to Architect. No implementation. No brief writing. No TECHNICAL_DEBT.md changes.

> **T5-25 has no Codex implementation handoff.** It is a design artefact to be authored by the architect or under direct architect direction. Codex does not implement T5-25.

---
