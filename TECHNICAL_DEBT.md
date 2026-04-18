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
  T4-27-C (module ceiling update policy for feature additions — follow-up from T5-16-A closure 2026-03-15)
  T4-28 (context snapshot generator + multi-agent protocol; AGENTS.md §16.5)
  T4-30 (science module semantic versioning — MODULE_VERSION constants + CI; AGENTS.md §16.8; independent)
  T4-31 (athlete isolation invariant CI check — exemption register + comment annotations; AGENTS.md §16.10; IMMEDIATE)
  T4-32 (override handler registry + Telegram inline override button; ADR-0042; IMMEDIATE)

TIER 5 (future / Phase 8+):
  T5-06 (ML advisory explainability contract; ADR-0032; T5-06-A is Phase 8A early work — complete before Phase 8B begins)
  T5-07 (model calibration metadata table + adaptation drift detection; ADR-0033; ✅ Layers 1–2 RESOLVED 2026-03-13; Layer 3 ADR ACCEPTED 2026-04-12 — implementation tracked as T5-07-L3-A through L3-D)
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

**Phase 8C execution sequence (CLOSED — 2026-04-04):**
```
T5-12 Pass 1 — ✅ COMPLETE 2026-03-18 (design document created:
               docs/specs/garmin_api_fragility_mitigation.md; ADR-0050 accepted)
T5-12 Pass 2 — DEFERRED Phase 9. Rationale: ADR-0050 accepted; mitigation design
               complete (docs/specs/garmin_api_fragility_mitigation.md);
               implementation requires multi-device adapter (ADR-0016/ADR-0041)
               which is Phase 9 scope.
```
Phase 8C opened 2026-03-17 (DEC-016). Bounded audit batch T5-39–T5-42 fully closed.
No further open Phase 8C items beyond T5-12 at time of opening.
Phase 8C CLOSED 2026-04-04.

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

### T4-27-C · Define module ceiling update policy for feature additions ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. Commit: `e061042`.
**Source:** Architect Decision 2026-03-15 (T5-16-A records steward pass). T4-27 child item.
**Priority:** P3 (Tier 4 — maintainability). Independent.
**Workflow Path: A**

**Rationale:** Accepted features that add structural modules must update the ceiling explicitly
through a records/policy path, so future additions do not require ad hoc corrections.

**Original state (pre-fix):** T5-16-A closure was blocked because the complexity-budget guard ceiling (61) was
stale — it had not been updated when the CoachingScheduler stub was added as a legitimate
structural module. The ceiling update happened ad hoc as part of the closure records pass rather
than as part of the feature implementation workflow.

**Fix direction:**

Add a subsection to AGENTS.md §16.11 (or equivalent policy location) specifying:
1. When any task adds one or more new `titan/` modules as a deliberate structural choice
   (not a bug fix or rename), the implementing engineer must update the ceiling in
   `tests/test_documentation_consistency.py::test_module_count_within_budget` in the same
   commit, with a one-line comment attributing the ceiling increment to the task ID.
2. The architect must confirm the new ceiling value in the task acceptance criteria before
   implementation begins.
3. Ad hoc ceiling corrections after the fact are a process violation — same category as
   a failed mandatory gate.

**Acceptance criteria (binary):**
- AGENTS.md §16.11 (or designated policy section) contains the three-rule module ceiling
  update protocol described above.
- At least one sentence cross-references T4-27-C as the source of this rule.
- `python -m pytest -q` passes with no regressions.

**Resolution:** Updated `AGENTS.md` §16.11 to codify the three-rule T4-27-C protocol for module ceiling updates on accepted structural feature additions, including a direct cross-reference back to T4-27-C as the rule source.

**Status:** ✅ RESOLVED — 2026-04-13. `MODULE_COUNT_CEILING = 71` moved to
`thresholds.py` (importable); `tests/test_complexity_budget.py` replaces CI inline
literal; ceiling is now testable and self-documenting. `ci.yml` complexity-budget job
updated to import from `thresholds.py` instead of using a hardcoded literal.

**Task learning:** Policy-only safeguards still need explicit ownership timing (architect confirms before implementation; implementing engineer updates in-commit) to avoid post-hoc records fixes.

**Effort:** ~30 minutes. Policy text only — no implementation.

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

**Decision status:** ⚠️ PARTIALLY RESOLVED 2026-03-15 — T5-06-A complete (Phase 8A early work). T5-06-B remains deferred Phase 9.
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


**Status (T5-06-A):** ✅ RESOLVED 2026-03-15. Commit: 9fe7e96.

**Resolution (T5-06-A):** Added deterministic `ExplainableOutput` support to the injury risk advisory payload (top-3 contributions, confidence range, template `plain_text_reason`, and `data_freshness_ok`); extended `InjuryRiskEnsembleModel` with `assess_injury_risk()` + stale-data discard helper; surfaced explainability data through payload boundaries used by Operator Console session explorer when present; and added dedicated explainability tests (`tests/test_ml_explainability.py`) plus contract updates in existing injury-risk tests. Final full-suite count at closure: 1941 passing tests.
**Implementation path note (DEC-019):** `ExplainableOutput` was added to `titan/science/ml_safety.py` — the first option listed in the fix direction. No separate `titan/science/ml_explainability.py` module was created, and none is expected going forward; `ml_safety.py` is the canonical home for this dataclass.

**Task learning:** Existing advisory model contracts are consumed by multiple stability tests, so explainability extensions should be additive and backward-compatible (`assess_risk()` delegating to `assess_injury_risk()`) to avoid integration churn while still meeting ADR contract obligations.

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

**Status:** ✅ RESOLVED (Layers 1–2) — 2026-03-13. Commit: b6bea2a. Layer 3: ADR ACCEPTED 2026-04-12. L3-A ✅ L3-B ✅ L3-C ✅ L3-D ✅ RESOLVED 2026-04-17. All four sub-decisions complete.
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

**Layer 3 (Phase 9 — multi-athlete isolation):** ADR ACCEPTED 2026-04-12. See ADR-0033 Amendment §Layer 3. Implementation items below (T5-07-L3-A through L3-D).

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

### T5-07-L3-A · `athletes` canonical table + athlete_id FK enforcement ✅ RESOLVED

**Status:** ✅ RESOLVED — 2026-04-14. Commit: pending push.
`athletes` canonical table created in SQLite `create_tables()` + Alembic migration
(`20260414_01`). Owner athlete seeded (`is_cold_start=0`, `cold_start_sessions_count=30`).
`governance_outcomes.athlete_id` column confirmed present; existing rows backfilled
`'default'`→`'owner'` via v13 migration. `model_calibration_metadata.calibrated_for`
dropped (table recreation); `athlete_id` is the sole athlete FK. `save_governance_decision()`
now uses explicit `'owner'` fallback in both SQLite and PostgreSQL backends.
`record_decision()` in `outcome_tracker.py` normalises sentinel to `'owner'`.
SCHEMA_VERSION bumped 12→13. Schema contract tests updated + 8 new DB tests green.
Bundled with T5-74 (overlapping schema scope).

**Source:** ADR-0033 Layer 3, Sub-decision L3-A.

**Fix direction:**
1. Create `athletes` table in Alembic migration (schema per ADR-0033 Amendment L3-A).
2. ALTER `governance_outcomes` — add `athlete_id TEXT NOT NULL`; backfill existing rows with `'owner'`.
3. RENAME COLUMN `model_calibration_metadata.calibrated_for` → `athlete_id`.
4. Bump SCHEMA_VERSION.
5. Add migration upgrade + downgrade tests.

**Acceptance criteria:**
- `athletes` table exists in both SQLite and Alembic migration. ✅
- `governance_outcomes.athlete_id` exists and is non-null. ✅
- `model_calibration_metadata.athlete_id` exists (renamed from `calibrated_for`). ✅
- SCHEMA_VERSION incremented. ✅ (12→13)
- Migration upgrade + downgrade tests green. ✅

**Priority:** P1 — implement before any multi-athlete coaching endpoint is built.
**Phase:** 9 — data integrity gate.
**Blocking gate:** No multi-athlete coaching execution endpoint before T5-07-L3-A is RESOLVED.

---

### T5-74 · `governance_outcomes`: add `athlete_id` column to SQLite schema + explicit INSERT ✅ RESOLVED

**Status:** ✅ RESOLVED — 2026-04-14. Bundled with T5-07-L3-A (overlapping schema scope).
`governance_outcomes.athlete_id` confirmed present in SQLite `create_tables()` (CREATE TABLE
DEFAULT `'owner'`; v11 migration ALTER TABLE guard for existing DBs). Both SQLite and
PostgreSQL `save_governance_decision()` INSERTs now pass `athlete_profile_id` explicitly with
`'owner'` fallback. Existing rows backfilled `'default'`→`'owner'` via v13 migration.
OBS-045 closed. Schema contract tests updated; 2 focused INSERT tests green.

**Source:** DEC-042 / OBS-045 — governance_outcomes athlete_id absent from SQLite schema and
INSERT.

**Acceptance criteria:**
- `governance_outcomes.athlete_id` column in SQLite create_tables(). ✅
- Explicit `athlete_id` in both SQLite and PostgreSQL save_governance_decision() INSERTs. ✅
- Existing rows backfilled with `'owner'`. ✅
- Tests: schema contract + INSERT default verification green. ✅

**Priority:** P1 — Phase 9 (ADR-0033 Layer 3 prerequisite). ✅ RESOLVED.

---

### T5-07-L3-B · OutcomeTracker per-athlete query scoping + G-CI-07 extension ✅ RESOLVED

**Status:** ✅ RESOLVED — 2026-04-17.
All `OutcomeTracker` query methods (`record_outcome`, `get_decisions`, `get_lock_rate_by_phase`,
`get_lock_outcome_correlation`, `get_calibration_summary`, `check_calibration_diversity`,
`get_calibration_analytics`) accept `athlete_id: str = "owner"` and filter the in-memory
`_decisions` list by `athlete_profile_id`. Independence window check scoped per-athlete.
`check_calibration_diversity()` new method: ≥30 reusable records, ≥3 distinct session types,
no single type >60%; all filtering per-athlete, cross-athlete pooling forbidden.
G-CI-07 extended: `test_outcome_tracker_query_methods_accept_athlete_id()` added to
`tests/test_athlete_isolation_invariant.py` (AST gate — fails if any query method drops athlete_id).
INV-04 moved to ENFORCED: `tests/test_athlete_calibration_isolation.py` created (10 tests, all green).
Tests: +11 new tests all green (1 AST gate + 10 calibration isolation tests).

**Source:** ADR-0033 Layer 3, Sub-decision L3-B + INV-04 activation.

**Priority:** P1 — Phase 9, after T5-07-L3-A.

---

### T5-07-L3-C · Cold-start protocol implementation ✅ RESOLVED

**Status:** ✅ RESOLVED — 2026-04-17. After T5-07-L3-A; parallel with T5-07-L3-B.
is_athlete_cold_start() replaced with flag-based implementation reading athletes.is_cold_start
(fail-closed for unknown athletes, INV-05). check_and_exit_cold_start() and
increment_cold_start_sessions() added to DatabaseManager. coaching_pipeline() checks cold-start
at entry; applies COLD_START_SOFT_GATE_CONSERVATIVE_FACTOR=0.80 to context; exits atomically when
both conditions met (sessions>=30 + outcomes>=CALIBRATION_MIN_OUTCOME_COUNT); emits
athlete_cold_start_completed (INFO). Owner athlete bypasses cold-start (is_cold_start=0 seeded).
DailyCoach passes db=self.db to AthleteCoachingContext. setup_env.sh (root + scripts/): pyenv
3.11 auto-activation added. Tests: tests/titan/core/test_cold_start.py (+8 tests).

**Source:** ADR-0033 Layer 3, Sub-decision L3-C.

**Fix direction:**
1. Add `COLD_START_SOFT_GATE_CONSERVATIVE_FACTOR = 0.80` and `COLD_START_HARD_STOP_FACTOR = 1.00` to `titan/science/thresholds.py`.
2. In `coaching_pipeline()`: check `athletes.is_cold_start` at entry; apply conservative factor to soft gates if active.
3. Implement cold-start exit: when both exit conditions met, write `cold_start_ends_at`, set `is_cold_start = 0` in same DB transaction.
4. Emit `athlete_cold_start_completed` structured event (INFO severity).
5. Owner athlete migration backfill (`is_cold_start=0`, `cold_start_sessions_count=30`).

**Acceptance criteria:**
- `COLD_START_*` constants in `thresholds.py`.
- `coaching_pipeline()` applies conservative factor during cold-start; hard-stops unchanged.
- Cold-start exit is atomic (same DB transaction as session write).
- `athlete_cold_start_completed` event emitted on exit.
- Owner athlete correctly bypasses cold-start after migration.
- Tests cover: cold-start active path, exit condition trigger, owner bypass.

**Priority:** P1 — Phase 9, after T5-07-L3-A.

---

### T5-07-L3-D · Adapter read method isolation + coach:Any contract resolution ✅ RESOLVED

**Status:** ✅ RESOLVED — 2026-04-17.
coach: Any eliminated from AthleteCoachingContext (commit: 490a41c, 2026-04-15).
Adapter read method isolation complete: all six read methods in `PersistenceAdapter`,
`SQLiteAdapter`, and `PostgreSQLAdapter` now accept `athlete_id: str = "owner"`.
`DatabaseManager` read methods updated with `WHERE athlete_id = ?` filtering.
Schema v14 migration adds `athlete_id TEXT NOT NULL DEFAULT 'owner'` to `daily_metrics`
and `training_log`. ADR-0040-SINGLE-ATHLETE-SHORTCUT exemptions retired in persistence.py
(replaced with ADR-0033-L3-D-RESOLVED comment). Isolation tests added for all six
methods in `test_persistence.py`. SCHEMA_VERSION bumped 13→14.
ADR-0033 Layer 3 complete: L3-A ✅ L3-B ✅ L3-C ✅ L3-D ✅.
Original status: OPEN — Phase 9. ADR-0033 Amendment (2026-04-12). After T5-07-L3-A and T5-07-L3-B.

**Source:** ADR-0033 Layer 3, Sub-decision L3-D + DEC-021 closure + T5-16-B task learning note.

**Fix direction:**
1. Update all `ADR-0040-SINGLE-ATHLETE-SHORTCUT`-annotated methods in `titan/core/persistence.py` to accept `athlete_id: str` as required parameter. Retire the annotation on each updated method.
2. Replace `AthleteCoachingContext.coach: Any` with an explicit Protocol or TypedDict defining only the callable contracts consumed by `coaching_pipeline()`. No caller may pass a full `DailyCoach` instance after this change.

**Acceptance criteria:**
- All previously-annotated adapter methods in `persistence.py` accept `athlete_id: str`; no `ADR-0040-SINGLE-ATHLETE-SHORTCUT` annotations remain in updated methods.
- `AthleteCoachingContext.coach` is typed (Protocol or TypedDict); `Any` removed.
- All existing tests green after signature changes.
- G-CI-07 passes with updated method signatures.

**Priority:** P2 — Phase 9, after T5-07-L3-A and L3-B (depends on isolation contract being in place).
**Blocking gate:** No multi-athlete coaching execution endpoint before T5-07-L3-D is RESOLVED.

---

### T5-08 · PostgreSQL migration not yet implemented — multi-athlete persistence layer unbuilt ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15 (via T5-08-B). Commit: 54e95d9 (scaffold); ADR-0044 deliverables D1, D2a/b/c, D3, D4, D5, D7, D9 completed in T5-08-B (final: D7 2026-03-15, D9 2026-03-15). D6 was a T5-08 pre-existing deliverable, not a T5-08-B implementation deliverable (DEC-015 2026-03-16). See T5-08-B for full deliverable record. **Records drift correction (2026-03-15):** T5-08-B D8 deliverable ("mark T5-08 RESOLVED") executed as part of T5-08-B RESOLVED declaration.
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

### T5-08-B · ADR-0044 full migration — PersistenceAdapter + Alembic + RLS + consent schema ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. T5-08-B deliverables: D1 DONE (2026-03-08, commit eaaa35e); D2a DONE (2026-03-13, commit df449e7); D2b DONE (2026-03-13, commit d7ad4b7); D2c DONE (2026-03-13, commit f6901b6); D3 DONE (2026-03-13, commit 6f641eb); D4 DONE (2026-03-13, commit 4ccf36d); D5 DONE (2026-03-13, commit ca8db90); D7 DONE (2026-03-15); D9 DONE (2026-03-15). Phase 8A prerequisite CLEARED. **Note — D6:** D6 (`TITAN_DB_BACKEND` feature flag) was a T5-08 deliverable (commit 54e95d9, 2026-03-08), not a T5-08-B implementation deliverable; carried in T5-08-B tracking table as a pre-existing ✓ reference only. D6 status not explicitly confirmed in T5-08-B closure record. Functional verification (DEC-015, 2026-03-16): `get_database_manager()` in `titan/core/database.py:1975` and `titan/core/persistence.py:122` both implement `TITAN_DB_BACKEND` env-var switching — D6 is present and correct. **Records drift correction (2026-03-15):** heading and status were not updated when D9 was completed; tracking table correctly showed RESOLVED 2026-03-15 — section body now aligned. **Records correction (2026-03-16, DEC-015):** "D6 DONE (T5-08)" removed from T5-08-B deliverable list; D6 note added above.
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
| D7 | `pg_dump` hot backup replaces SQLite file copy (T1-17 re-implementation for PostgreSQL) | ✓ DONE 2026-03-15 | Implemented in `PostgreSQLAdapter.backup_database()` using `pg_dump`; tests added for PostgreSQL happy-path, failure-path, backend-specific backup behavior, and backend env selection. **Change Type:** implementation |
| D8 | `TECHNICAL_DEBT.md` T5-08 marked RESOLVED | ✓ DONE 2026-03-15 | T5-08-B now RESOLVED; T5-08 marked RESOLVED (records correction, 2026-03-15) |
| D9 | `consent_log` table in Alembic migration (athlete_id, consent_type, granted_at, revoked_at) | ✓ DONE 2026-03-15 | Implemented in Alembic revision `20260315_05`; upgrade/downgrade migration tests added. **Change Type:** implementation |

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
- **Status:** ✅ RESOLVED 2026-03-13. Commit: `6f641eb`.
- **Resolution:** Added Alembic D3 migration (`20260313_02`) to append `athlete_id TEXT NOT NULL DEFAULT 'default'` to `daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, and `governance_outcomes`; updated PostgreSQLAdapter table metadata and backend parity tests to validate the new default-backed column contract.
- **Task learning:** Introducing additive schema revisions requires migration tests that target fixed revisions (`20260313_01`) where historical expectations assume a single-head chain.

**D5 closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: `ca8db90`.
- **Resolution:** Added Alembic D5 migration (`20260313_03`) creating `model_calibration_metadata` in the PostgreSQL/Alembic path with composite primary key (`model_name`, `athlete_id`) and default-backed `athlete_id`/`calibrated_for` columns; added migration tests for upgrade schema contract and downgrade removal behavior.
- **Task learning:** Isolating D5 as an additive revision after D3 preserves the existing migration chain while keeping SQLite schema behavior unchanged.

**D4 closure update (records maintenance):**
- **Status:** ✅ RESOLVED 2026-03-13. Commit: `4ccf36d`.
- **Resolution:** Added Alembic D4 migration (`20260313_04`) that activates PostgreSQL Row-Level Security on `daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, `governance_outcomes`, and `model_calibration_metadata`, applying `titan_athlete_isolation` with `current_setting('app.current_athlete_id', true)` for both read and write enforcement; non-PostgreSQL dialects are explicit no-ops to preserve SQLite behavior.
- **Task learning:** Dialect-gated migration logic keeps the SQLite path stable while enabling enforceable PostgreSQL athlete isolation in a single revision.
- **Next deliverables:** D9 (D7 resolved in this pass).

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

### T5-09 · No unified `get_athlete_context()` query interface — LLM Seam 2 unbuilt ✅ RESOLVED 2026-03-16

**Status:** ✅ RESOLVED 2026-03-16. Commit: 7952636.
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
ruff check titan/core/persistence.py tests/titan/core/test_persistence.py
python -m pytest tests/titan/core/test_persistence.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Resolution:**

Implemented a new unified `get_athlete_context()` interface in `titan/core/persistence.py` to return a single JSON-serialisable payload with optional `biometrics`, `training`, and `governance` domains. The function normalises floats to two decimals and converts datetime values to ISO-8601 strings recursively to ensure no datetime objects leak into callers. Updated `tests/titan/core/test_persistence.py` with happy-path aggregation/normalisation and boundary validation (`days >= 1`) coverage for the new public function. Final closure test suite count: 1975 passing tests.

**Task learning:**

Seam-style query interfaces are safest when they reuse adapter contracts instead of calling storage internals directly, because it preserves backend portability while still allowing a stable payload contract for downstream LLM/UI consumers.

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

### T5-11 · No API authentication layer for Phase 8B web UI — health data accessible without auth ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. Implementation commit: 3bd7147 (T5-11: Implement Phase 8B API authentication layer). All acceptance gate criteria met. Opus QA verdict: QA PASS.
**Workflow Path: B (APPROVED)** *(cross-subsystem auth logic with security invariants — Opus QA required at closure)*
**Change Type:** implementation

**[Opus QA] Task: T5-11 — QA PASS** — test coverage adequate for all acceptance criteria; happy path, token expiry, role violation, and isolation violation exercised; boundary conditions met; no gaps that would allow regression to pass undetected.
**Source:** Architecture review 2026-03-06. Not previously recorded.
**Priority:** P0 for Phase 8B (do NOT build any coach API endpoint without this resolved).

**ADR:** ADR-0048 — API Authentication Layer (Accepted 2026-03-15). See `docs/adr/0048-api-authentication-layer.md`.

**Location:** New `titan/api/auth.py` (Phase 8B); FastAPI app (`titan/api/main.py`).

**Original state (pre-fix):**

ADR-0013 (technology path) specifies React + FastAPI for the coach dashboard. FUTURE_UPGRADES.md Phase 8/10 scope
confirms multi-athlete deployment. However, no auth layer has been designed. FastAPI
endpoints serving health data (HRV, RHR, governance decisions, training log) for 50
athletes with zero authentication is a GDPR violation and a serious security risk.

**Architect decision summary (ADR-0048 — 2026-03-15):**

- **Auth mechanism:** JWT (RS256) + refresh token rotation, HTTP-only Secure cookie transport. External OAuth2 provider (Google/GitHub) rejected: contradicts local-first architecture and adds internet dependency.
- **Roles (flat, Phase 8B):** `COACH` (all athletes) and `ATHLETE` (own data only, `athlete_id` bound from JWT claim).
- **Isolation invariant:** every athlete-data endpoint runs both RLS (PostgreSQL) and application-level check — defense in depth.
- **Token policy:** access token 15 min (RS256), refresh token 7 days (server-side in `auth_tokens`, supports revocation), rotation on every use, max 3 active per user.
- **Secrets:** `TITAN_JWT_PRIVATE_KEY` / `TITAN_JWT_PUBLIC_KEY` env vars (PEM). Not in code or config files.
- **Sole public endpoint:** `GET /health`. All others behind `Depends(get_current_user)`.
- **New tables:** `auth_users` (UUID PK, username, bcrypt hash, role, athlete_id, created_at, is_active), `auth_tokens` (UUID PK / jti claim, user_id FK, issued_at, expires_at, revoked).
- **Module structure:** `titan/api/auth.py`, `titan/api/dependencies.py`, `titan/api/models.py`, `titan/api/main.py`.

**Sequencing constraint:** T5-11 → T5-13. The `coach_audit_log` middleware (T5-13) requires `coach_id` from the JWT claim produced by T5-11. T5-13 must not begin until T5-11 is RESOLVED.

**Acceptance gate for T5-11 (binary):**

1. `auth_users` and `auth_tokens` tables exist in Alembic migration
2. `titan/api/auth.py` — JWT create/verify with RS256
3. `titan/api/dependencies.py` — `get_current_user()`, `require_coach()` FastAPI dependencies
4. Every existing or new endpoint is behind `Depends(get_current_user)` except `GET /health`
5. Application-level isolation check: `ATHLETE` role sees only their own data
6. `tests/titan/api/test_auth.py` — happy path + token expiry + role violation + isolation violation
7. All mandatory gates green: `ruff check .` → `pytest -q -W error::pytest.PytestWarning` → `pytest -q`

---

### T5-12 · Garmin unofficial API fragility — no fallback if Garmin changes auth mechanism 🟡 OPEN

**Status:** OPEN — Pass 1 COMPLETE 2026-03-18 (design document: `docs/specs/garmin_api_fragility_mitigation.md`; ADR-0050 accepted). Pass 2 BLOCKED pending architect ADR acceptance.
**Workflow Path: A** *(no implementation until Pass 2 ADR accepted)*
**Source:** Architecture review 2026-03-06. Not previously recorded.
**Priority:** P3 (medium — risk is real but not blocking current phases).

**Architect brief (2026-03-16):**
- **Execution unit (Phase 8C, Pass 1):** Mitigation design pass — produce a written mitigation
  design document (not code). Scope: structured Garmin-degraded event definition, coach dashboard
  indicator specification, `garminconnect` library pinning strategy, and multi-device fallback
  interface sketch referencing ADR-0016/ADR-0041.
- **Pass type:** audit / design (no code changes in Pass 1)
- **Closure rule:** T5-12 remains OPEN after Pass 1; closure-capable only after implementation
  pass (Pass 2) is complete and acceptance gate met.
- **Required canonical doc update:** Mitigation design document created; T5-12 status updated
  to reflect design-complete.

**ADR scope declaration (2026-03-16):**
- ADR required before implementation (Pass 2) begins: YES — the multi-device fallback
  interface (Polar/Whoop/COROS via unified adapter) must be scoped against ADR-0016
  (multi-sport scope) and ADR-0041 (unified external data trust contract). A new ADR or
  amendment to ADR-0016/ADR-0041 is required if the fallback introduces a new sensor-source
  category not covered by those ADRs.
- ADR required before design pass (Pass 1): NO — the design pass may proceed; ADR authorship
  follows after the design document exists.
- Implementation (Pass 2) is **blocked** until the design ADR is accepted by the architect.

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

### T5-13 · No coach action audit trail — GDPR accountability gap for health data processors ✅ RESOLVED 2026-03-16

**Status:** ✅ RESOLVED 2026-03-16. Commit: b9bddd6.
**Workflow Path: A** *(schema migration + cross-subsystem middleware — PILOT-01 excluded)*
**Source:** Architecture review 2026-03-06. Not previously recorded.
**Priority:** P1 for Phase 8B (GDPR Article 5(2) accountability requirement).

**Sequencing constraint:** T5-13 depends on T5-11. The `coach_audit_log` middleware writes `current_user.id` (coach identity) sourced from the `get_current_user()` FastAPI dependency established by T5-11. T5-13 must not begin until T5-11 is RESOLVED. See ADR-0048 §3.

**Location:** New `coach_audit_log` table (Phase 8A Alembic migration), FastAPI audit middleware path in `titan/api/main.py`.

**Original state (pre-fix):**

Phase 8B granted coaches the ability to view all athletes' health data and submit manual
overrides. Under GDPR, any entity that processed health data on behalf of another person
was a **data processor** and had to maintain records of processing activities (Article 30)
and be able to demonstrate accountability (Article 5(2)).

Specifically: when a coach viewed Athlete A's HRV data and submitted an override, that action
had to be logged with: coach identity, athlete affected, action type, timestamp, and reason.
Without this log, a data subject access request or a supervisory authority audit could not be
satisfied.

**Resolution:**

Added Alembic revision `20260316_02` that creates `coach_audit_log` with the required
contract (`id`, `coach_id`, `athlete_id`, `action_type`, `resource`, `action_detail`,
`performed_at`). Added central FastAPI middleware-based auditing in `titan/api/main.py`
that logs coach access for covered athlete health-data endpoints and records coach/athlete
identities from the T5-11 auth dependency state. Added migration and API tests covering
all required action types and non-bypassability. Final suite at closure: 1961 tests green.

**Task learning:** Middleware-only audit hooks still need a deterministic athlete-id extraction
contract across path and query inputs; encoding that contract in tests prevents silent
coverage gaps when new coach endpoints are added.

---

### T5-14 · Training zone thresholds not adjusted for environmental stress — ESI framework absent ✅ RESOLVED 2026-03-16

**Status:** ✅ RESOLVED 2026-03-16. Merge commit: 31f8ef4 (PR #468).
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

**Resolution:**

ESI framework implemented across 5 production modules per ADR-0034. ESI constants (`ESI_MODERATE_DEW_POINT_C`, `ESI_EXTREME_DEW_POINT_C`, `ESI_TEMP_THRESHOLD_C`, `ESI_PACE_ADJUSTMENT_TABLE`) added to `thresholds.py`. `esi_level` and `esi_pace_adjustment_sec_per_km` computed in `DailyCoach` from current weather data and propagated as ESI context to `WeeklyPlanGenerator` and `OptimalTimeCalculator`. VO₂max workouts blocked under `ESI_EXTREME` via `VO2_ELIGIBILITY_GATE` in `governance_engine.py`. ESI level and adjusted zone targets surfaced in Telegram briefing. `tests/test_esi_compensation.py` added with boundary mutation coverage for the VO₂ eligibility guard and pace adjustment logic.

**Task learning:**

ESI is safest implemented as a multiplicative overlay anchored entirely to `thresholds.py` constants rather than as inline magic numbers, which keeps the compensation logic unit-testable without live weather data. Routing the VO₂ block through the existing `VO2_ELIGIBILITY_GATE` rather than adding a parallel planner-level guard preserves the safety-partition invariant: the block fires regardless of which downstream consumer requests a session prescription.

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

### T5-16-A · Extract `coaching_pipeline()` stateless function + `CoachingScheduler` stub ⚠️ PARTIALLY RESOLVED 2026-03-15 — see T5-16-B

**Status:** ⚠️ PARTIALLY RESOLVED 2026-03-15. ADR-0018 Phase B kernel boundary refactor complete (`_decision_pipeline()` + `_effect_runner()` inside `DailyCoach`). Three T5-16-A structural deliverables absent: `titan/orchestration/coaching_pipeline.py` module, `AthleteCoachingContext` dataclass, `titan/orchestration/coaching_scheduler.py` stub. Tracked in T5-16-B.
**Partial closure note:** The ADR-0018 Phase B refactor (pure decision pipeline + effect runner) was delivered and is correct. The T5-16-A structural extraction — standalone `coaching_pipeline.py` module, `AthleteCoachingContext`, and `CoachingScheduler` stub — was not delivered. Ceiling calibration (61→62) and T4-27-C remain valid; the ceiling increment was premature (anticipated a module that does not yet exist) but the policy is correct and stands.
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

**Architect note (2026-03-15 — records pass):** The T5-16-A resolution and ceiling
calibration (61 → 62) were a preventive/historical record only. No new sequencing gate
is created by this note. Execution sequencing for subsequent Phase 8B deliverables
remains: T5-08-B D7 → T5-08-B D9 → T5-11. T5-16-A closure does not alter that order.

**Drift postmortem (§20):**
- Drift: T5-16-A declared RESOLVED while three structural deliverables (`coaching_pipeline.py`, `AthleteCoachingContext`, `CoachingScheduler`) were absent from the repository.
- Why it escaped: Closure was evaluated against the ceiling calibration blocker only; no file-existence verification was performed against the acceptance criteria checklist before Records Steward closure actions.
- Guard now in place: ADR Deliverable Checklist rule (DEC-007 / §12.1) applies to T5-16-B — file existence must be confirmed by `ls` or equivalent before closure is declared.

---

### T5-16-B · CoachingScheduler stub + coaching_pipeline module extraction ✅ RESOLVED 2026-03-17

**Status:** ✅ RESOLVED 2026-03-17. Commit: 4e79c4a.
**Resolution:** `titan/orchestration/coaching_pipeline.py` created with `AthleteCoachingContext` frozen dataclass and stateless `coaching_pipeline()` function. `titan/orchestration/coaching_scheduler.py` created with `register_athlete()`, `start()`, `stop()` lifecycle and per-athlete overlap lock. `DailyCoach.run_morning_routine()` delegates to `coaching_pipeline()` via context object. State isolation oracle implemented and passing. Module ceiling updated 67→69 for the two new structural modules. 2008 tests green.
**Task learning:** The `coach: Any` field in `AthleteCoachingContext` passes the full `DailyCoach` instance — acceptable for single-athlete Phase 8C scope where state isolation is proven by the oracle test. For Phase 9 multi-athlete promotion, `coach` must be replaced by explicit callable contracts (per ADR-0046) to eliminate implicit shared-state risk.
**Workflow Path: A** *(structural extraction — PILOT-01 excluded)*
**Change Type:** implementation
**Source:** Architect records correction 2026-03-17. T5-16-A partial closure finding.
**Priority:** P1 for multi-athlete execution (blocking gate — no multi-athlete endpoint before this resolves).
**Predecessor:** T5-16-A PARTIALLY RESOLVED (ADR-0018 Phase B kernel boundary complete).

**ADR Deliverable Checklist (T5-16-A remaining scope):**

| # | Deliverable | Status |
|---|---|---|
| D1 | `titan/orchestration/coaching_pipeline.py` — `coaching_pipeline(ctx)` stateless function + `AthleteCoachingContext` dataclass | ✗ NOT DONE |
| D2 | `DailyCoach.run_morning_routine()` delegates to `coaching_pipeline()` with no behaviour change observed by existing tests | ✗ NOT DONE |
| D3 | `titan/orchestration/coaching_scheduler.py` — `CoachingScheduler` stub with `register_athlete()`, `start()`, `stop()`, per-athlete overlap lock | ✗ NOT DONE |
| D4 | State isolation oracle test: sequential calls for two athletes with opposing readiness states produce independent outputs | ✗ NOT DONE |
| D5 | All three mandatory gates green: ruff + pytest -W error + pytest -q | ✗ NOT DONE |

**Acceptance criteria (binary):**
- `titan/orchestration/coaching_pipeline.py` exists and contains `AthleteCoachingContext` dataclass and `coaching_pipeline()` function
- `DailyCoach.run_morning_routine()` delegates to `coaching_pipeline()` — all existing tests remain green with no behaviour change
- `titan/orchestration/coaching_scheduler.py` exists with `register_athlete()`, `start()`, `stop()` lifecycle, and per-athlete overlap lock
- State isolation oracle: test verifies two sequential `coaching_pipeline()` calls for athletes with opposing readiness states produce independent outputs
- `ruff check .` zero findings
- `python -m pytest -q -W error::pytest.PytestWarning` 100% green
- `python -m pytest -q` 100% green, count same or higher
- File existence verified by `ls titan/orchestration/coaching_pipeline.py titan/orchestration/coaching_scheduler.py` before closure is declared

**Effort:** ~4h.

**Blocking gate:** No multi-athlete coaching execution endpoint may be built until T5-16-B is RESOLVED.

**Bottleneck:** None — ready for implementation.
**Owner:** Codex
**Unblock condition:** All five deliverables confirmed present and gates green.

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

### T5-25 · Database Manager — SQLite/PostgreSQL interface parity matrix absent ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. Canonical artifact: `docs/PARITY_MATRIX.md` (v1.0).
**Change Type:** architect-decision
**Source:** Binder1 audit / DEC-2 §Database Manager Pattern P7 variant finding.
**Type:** Architecture Debt — design artefact
**Priority:** P4. Related to T5-08-B but distinct scope.
**Workflow Path:** A (records pass — no Codex implementation handoff)
**Cross-reference:** T5-08-B (OPEN — full ADR-0044 PostgreSQL migration) addresses implementation. T5-25 addresses the **interface parity matrix** as a documented architectural contract (what methods/behaviours must be identical across both backends). These are related but distinct debt items.

**Architect Decision (2026-03-14):** This is a **design artefact / parity matrix document**, not a code task. No Codex implementation handoff is permitted for T5-25 at this stage.

**Sequencing constraint:** The parity matrix document must exist before T5-08-B D7 and D9 can be closed. It is a prerequisite for those deliverables. T5-25 is NOT blocked by T5-08-B — it may be authored independently — but it must be complete before T5-08-B D7/D9 are declared DONE.

**Scope:** Produce a documented parity matrix specifying which methods and behaviours must be identical across `SQLiteDatabaseManager` and `PostgreSQLDatabaseManager`, and what backend-specific divergence (if any) is explicitly permitted. Output is a document (architecture artefact), not code.

**Acceptance gate (binary):** Parity matrix document exists and is accepted by Architect; T5-08-B D7 and D9 may not close without it.

**Resolution:** `docs/PARITY_MATRIX.md` created (2026-03-15, v1.0). All 32 `PersistenceAdapter` abstract methods classified across 10 functional areas (MUST_MATCH / PERMITTED_DIVERGENCE). D7 and D9 closure gates defined in §4. Sequencing constraint is now satisfied — T5-08-B D7 and D9 may proceed when they reach their turn in the execution queue.

**Task learning:** Interface parity matrices for dual-backend systems are most useful when they classify every method individually (not just the ones with known divergence) — the MUST_MATCH entries are the safety net that prevents D7/D9 from accidentally regressing working backends. Creating the matrix before D7/D9 rather than after forces the classification decision while the implementation is still in progress, not retrospectively.

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

### T5-27 · Durability Engine — Category A threshold literals not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: pending.
**Source:** Binder1 audit / DEC-2 §Durability Engine Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR after S1–S3 execution items.
**Workflow Path:** A

**Original state (pre-fix):** The Category A durability thresholds `2`, `5`, `8` (pace durability bands), `85`, `90`, `95`, `98` (durability index bands), and `88`, `93`, `96` (training protocol routing bands) were embedded inline in `titan/science/durability_engine.py` and were not centralized in `titan/config/thresholds.py` with provenance entries.

**Resolution:** Added the approved Durability Category A constants to `titan/config/thresholds.py`, added matching provenance records in `titan/config/evidence_registry.py`, and rewired `titan/science/durability_engine.py` to consume only the centralized constants for pace durability bands, durability index tiering, and protocol routing. Extended `tests/titan/science/test_durability_engine_thresholds.py` with threshold-source boundary assertions covering happy-path and boundary/error-path behaviors. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green at 1918 collected/passed tests.

**Task learning:** For threshold extraction tasks, source-of-truth tests should assert exact boundary values as constants so that future numeric edits require intentional updates in one canonical place instead of silent inline drift.

**Acceptance gate (binary):** Same pattern as T5-17. Zero inline literals remain for listed values; `thresholds.py` + `evidence_registry.py` updated; all gates green.

**Effort:** ~2h.

---

### T5-28 · Fatigue Engine — soreness threshold literal not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: (recorded in git history for T5-28 close).
**Source:** Binder1 audit / DEC-2 §Fatigue Engine Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Original state (pre-fix):** The soreness trigger threshold `>= 5` in `titan/science/fatigue_engine.py` was embedded inline and not centralized in `titan/config/thresholds.py`, with no matching provenance record in `titan/config/evidence_registry.py`.

**Resolution:** Added `FATIGUE_SORENESS_PERIPHERAL_MIN` to `titan/config/thresholds.py`, added the corresponding `FATIGUE_SORENESS_PERIPHERAL_MIN` provenance entry to `titan/config/evidence_registry.py`, and rewired `titan/science/fatigue_engine.py` to consume the centralized constant. Added mirrored module tests in `tests/titan/science/test_fatigue_engine.py` to verify threshold-source-of-truth behavior (monkeypatched constant drives classification boundary ON/OFF). Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green.

**Task learning:** For tiny threshold-extraction tasks, monkeypatching the imported constant in tests is the lowest-friction way to prove the engine reads from the canonical source rather than a silent inline literal.

**Acceptance gate (binary):** Same pattern as T5-17. Zero inline literals remain for listed value; `thresholds.py` + `evidence_registry.py` updated; all gates green.

**Effort:** ~1h.

---

### T5-29 · Garmin Live Sync — sleep/HRV partial-failure policy inconsistency ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: 814f0b7.
**Source:** Binder1 audit / DEC-2 §Garmin Live Sync finding. Architect decision: align `sync_sleep()` to per-day best-effort model.
**Type:** Behavior Contract
**Priority:** P2. Intentional behavior change — test-first required.
**Workflow Path:** A

**Original state (pre-fix):** `sync_sleep()` aborted the entire date range on a single failure, while `sync_hrv()` already used per-day best-effort continuation on individual day failures.

**Resolution:** Added test-first coverage for the partial-failure contract in `tests/test_garmin_sync.py`, then aligned `sync_sleep()` in `titan/integrations/garmin_sync.py` to skip failed days, emit day-level structured failure events, and continue syncing remaining days (matching `sync_hrv()` handling). Added a sleep skip-summary event for visibility. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green (1921 tests).

**Task learning:** Aligning sister sync paths is safest when tests assert both output continuity and observability semantics (warning log + structured event payload), not just returned record count.

**Acceptance gate (binary):** Failing test written first → fix applied → test green → all gates green.

**Effort:** ~2h.

---

### T5-30 · Governance Engine — class-local threshold literals not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. commit not individually recorded (pre-hash-enforcement era).
**Source:** Binder1 audit / DEC-2 §Governance Engine Pattern P5 finding. Category A confirmed by architect in DEC-2.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A
**Cross-reference:** T1-04 (RESOLVED 2026-03-02 — "Hardcoded safety thresholds bypassing thresholds.py") did not cover these specific class-local values. T5-30 is a missed case from T1-04's resolution scope.

**Original state (pre-fix):** `GovernanceEngine` kept class-local Category A thresholds `0.80` and `0.70` instead of sourcing them from `titan/config/thresholds.py`.

**Resolution:** Added `GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD` and `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` to `thresholds.py`, wired `GovernanceEngine` class defaults to these constants, and added matching provenance entries in `evidence_registry.py`. Extended governance hygiene tests and evidence-registry consistency tests to assert threshold source-of-truth behavior and value mirroring. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green (1925 tests).

**Task learning:** Source-of-truth extraction is safest when tests assert both runtime boundary behavior and registry-value synchronization, because either side can drift independently without explicit assertions.

**Acceptance gate (binary):** Same pattern as T5-17. `governance_engine.py` references constants from `thresholds.py`; no inline literals remain for these values; all gates green.

**Effort:** ~1h. Extraction only.

---

### T5-31 · Intensity Governor — threshold literals not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: cfe263e.
**Source:** Binder1 audit / DEC-2 §Intensity Governor Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Original state (pre-fix):** `titan/science/intensity_governor.py` used inline Category A policy literals (`3.5`, `5.0`, `4.0`, `6.0`, `1.3`, `1.5`, `55`, `40`) for drift, glycogen, ACWR, and readiness color-gate boundaries.

**Resolution:** Added eight `INTENSITY_GOVERNOR_*` constants to `titan/config/thresholds.py`, wired `IntensityGovernor` to import and use those constants for both gate logic and audit payload threshold fields, and added matching evidence records in `titan/config/evidence_registry.py`. Added mirrored module tests in `tests/titan/science/test_intensity_governor_thresholds.py` and extended evidence-registry contract coverage in `tests/test_apl_integration.py` to assert canonical registration/value mirroring for all extracted constants. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q` all green (1927 tests).

**Task learning:** The audit payload threshold fields are part of the external governance contract, so extraction must update both decision boundaries and emitted metadata to keep policy observability consistent.

**Acceptance gate (binary):** Same pattern as T5-17. `intensity_governor.py` references constants from `thresholds.py`; no inline literals remain for these values; all gates green.

**Effort:** ~2h.

---

### T5-32 · Lactate Logic — threshold literals not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. commit not individually recorded (pre-hash-enforcement era).
**Source:** Binder1 audit / DEC-2 §Lactate Logic Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Original state (pre-fix):** Category A policy literals `3.0`, `78.0`, `6.0`, and `7.0` were embedded directly in `titan/science/lactate_logic.py` for LT1/LT2 boundary checks instead of being centralized in `titan/config/thresholds.py` with explicit provenance.

**Resolution:** Added LactateLogic Category A constants to `titan/config/thresholds.py`, added matching evidence records in `titan/config/evidence_registry.py`, and rewired `titan/science/lactate_logic.py` to read those constants for LT1/LT2 classification boundaries. Added mirrored module tests in `tests/titan/science/test_lactate_logic.py` to verify happy-path behavior and threshold-source-of-truth boundaries via constant patching. Final closure gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`, and `python -m pytest -q`.

**Task learning:** Source-of-truth tests are most robust when they assert behavioral changes after monkeypatching module-level threshold constants, because that validates configuration ownership without coupling tests to implementation internals.

---

### T5-33 · Periodization/Automated — implicit coupling contract absent ✅ CLOSED — NO_ACTION

**Status:** ✅ CLOSED — NO_ACTION | 2026-03-14
**Source:** Binder1 audit / DEC-2 §Periodization + Equipment Pattern P7 variant finding.
**Type:** Architecture Debt
**Priority:** P4.
**Workflow Path:** A

**Architect verdict (2026-03-14):** Read-only audit complete. No direct coupling found between `titan/core/periodization.py` and `titan/science/automated_periodization.py`. No layer violation across the `core/` ↔ `science/` boundary. No shared mutable state. The two modules exhibit decoupled coexistence. No brief required. Closing as NO_ACTION.

---

### T5-34 · Setup Wizard — dual bootstrap contract divergence (titan vs launcher wizard) ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. commit not individually recorded (pre-hash-enforcement era).
**Source:** Binder1 audit / DEC-2 §Setup Wizard Pattern S4 finding.
**Type:** Architecture Debt
**Priority:** P4.
**Workflow Path:** A
**Cross-reference:** T4-07 (RESOLVED — wizard credential duplicates), T4-12 (RESOLVED — wizard interactive flow tests) are distinct. T5-34 addresses the architectural divergence between the `titan/ui/setup_wizard.py` and `launcher/wizard.py` bootstrap contracts — a different concern not covered by T4-07/T4-12.

**Original state (pre-fix):** `launcher/wizard.py` treated any existing `.env` file as ready regardless of missing or empty credentials, diverged on Garmin key naming (`GARMIN_USERNAME` without alias-read for `GARMIN_EMAIL`), accepted Telegram token length only when strictly greater than 20, and lacked numeric validation for `TELEGRAM_CHAT_ID`.

**Resolution:** Added launcher tests first (`tests/launcher/test_wizard.py`) covering readiness rejection for empty/incomplete existing config, Garmin alias-read acceptance (`GARMIN_EMAIL`/`GARMIN_USERNAME`), Telegram token threshold `>=20`, and numeric chat-id validation. Implemented minimal launcher fixes by adding numeric `TELEGRAM_CHAT_ID` validation, aligning token threshold to `>=20`, and strengthening `ensure_config()` to validate loaded required credentials with Garmin alias-read support before returning ready.

**Task learning:** Launcher bootstrap safety depends on semantic readiness checks, not file-presence checks; mirrored tests across the launcher path catch contract drift quickly when wizard and runtime expectations diverge.

**Architect classification (2026-03-14):**

- **Class 1 — must fix:**
  - GARMIN key name alignment (`GARMIN_USERNAME` vs `GARMIN_EMAIL`)
  - Launcher readiness semantics fix (ensure_config() must verify required loaded credentials, not only file existence)

- **Class 2 — should align:**
  - Telegram token threshold alignment to `>= 20` characters
  - Numeric `TELEGRAM_CHAT_ID` validation in launcher

- **Class 3 — intentional divergence / out of scope:**
  - env file path difference (do not unify)
  - OpenAI key present in launcher (do not remove)
  - keyring support difference (do not port to launcher)
  - weather required/optional semantics (do not change)

---

#### T5-34-A · Implementation Brief

**Scope:**
- Align `GARMIN_USERNAME` → `GARMIN_EMAIL` in launcher (or add alias read so both keys are accepted)
- Strengthen launcher `ensure_config()` readiness check so it verifies that required credentials are actually loaded, not only that the env file exists
- Align Telegram token minimum-length threshold to `>= 20` characters in launcher
- Add numeric validation for `TELEGRAM_CHAT_ID` in launcher

**Workflow Path:** A

**Explicit exclusions:**
- Do not unify env file paths
- Do not remove OpenAI key from launcher
- Do not port keyring support to launcher
- Do not change weather required/optional semantics

**Acceptance gates (binary):**
```bash
ruff check titan/ui/setup_wizard.py launcher/wizard.py
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Tests required:**
- Launcher readiness rejects a config where the file exists but credentials are empty/missing
- GARMIN key cross-read smoke test (alias read accepts both `GARMIN_USERNAME` and `GARMIN_EMAIL`)

---

### T5-35 · Volume Load Gauge — threshold literals not centralized in thresholds.py ✅ RESOLVED 2026-03-14

**Status:** ✅ RESOLVED 2026-03-14. Commit: pending.
**Source:** Binder1 audit / DEC-2 §Volume Load Gauge Pattern P5 finding. Category A confirmed.
**Type:** Threshold Governance
**Priority:** P3. Independent. Separate PR.
**Workflow Path:** A

**Original state (pre-fix):** `titan/science/volume_load_gauge.py` embedded Category A policy thresholds inline: `-30` (TSB caution boundary), `0.7`/`0.8`/`1.3`/`1.5` (ACWR red/yellow bands), and `4`/`7` (glycogen caution/red bands). These lived outside `thresholds.py`, so source-of-truth discipline and evidence linkage were incomplete.

**Resolution:**

- Added VLG Category A constants to `titan/config/thresholds.py` (`VLG_TSB_YELLOW_MIN`, ACWR band boundaries, glycogen band boundaries).
- Replaced inline literals in `titan/science/volume_load_gauge.py` with imports from `thresholds.py` only (no behavior changes).
- Added required evidence entries in `titan/config/evidence_registry.py` for each extracted VLG threshold.
- Extended `tests/titan/science/test_volume_load_gauge.py` with threshold-boundary source-of-truth assertions and registry-entry presence checks.
- Mandatory gates passed at closure:

```bash
ruff check .
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Test count at closure:** 1933 passed.

**Task learning:** Threshold extraction work is lower-risk when tests assert both boundary behavior and evidence-registry presence, because threshold centralization can drift either in runtime logic or in provenance metadata.

**Effort:** ~2h.

---

### T5-36 · No API rate limiting — DoS risk on Phase 8B endpoints ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. Commit: <this-commit>.
**Workflow Path: A** *(FastAPI middleware addition; no ADR required)*
**Source:** ADR-0048 §5 (Architect Decision 2026-03-15). Records-safe correction: architect text referenced T5-26, which is already assigned (Drift Engine — RESOLVED 2026-03-14). Assigned next available ID: T5-36.
**Priority:** P2 Phase 8B.

**Location:** `titan/api/main.py`

**Original state (pre-fix):**

Phase 8B FastAPI endpoints had no per-user rate limiting. Any authenticated client (coach or athlete) could issue unlimited requests per minute, creating a DoS risk on local deployments.

**Resolution:**

Added authenticated request rate limiting in the FastAPI middleware path keyed by `(user_id, role, method:path)`, with fixed limits of 100 req/min for `COACH` and 30 req/min for `ATHLETE`. Exceeding the threshold returns HTTP 429. Coverage was extended in `tests/titan/api/test_auth.py` for coach limit, athlete limit, authenticated 429 behavior, identity-keyed enforcement, and `/health` public behavior. Final suite count at closure: 1965 tests.

**Task learning:** Keeping the limiter bound to authenticated identity in middleware avoids auth-contract changes while still enforcing per-role limits globally across protected endpoints.

**Acceptance gate (binary):** Rate-limiting middleware active on all authenticated endpoints; requests exceeding the per-user limit receive HTTP 429; tests confirm limit enforcement; all mandatory gates green.

---

### T5-37 · Opus QA — Category A (machine-checkable) findings not yet migrated to CI gates ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. Commit: cc5ce69. Architect ruling 2026-03-15: CLOSED WITH REQUIRED RECORDS CORRECTION — ADR-0049 §7 correctly and substantively applied; stale closure hash (251df1c) replaced with canonical current closure commit.
**Execution model:** Hybrid Sequential (per ADR-0049 §7) — Audit Pass → Sequential Migration Units → Single Final Closure.
**Audit Pass status:** DONE (2026-03-15)
**Migration units completed:** 4 / 4
**Workflow Path: A** *(no ADR required beyond ADR-0049; clean implementation item)*
**Change Type:** implementation
**Source:** ADR-0049 (Opus QA Scope Reduction — Deterministic-to-CI Migration Policy, Accepted 2026-03-15). Records-safe: next available ID T5-37.
**Priority:** P1 — reduces Opus QA overhead and makes deterministic checks durable in CI.

**Original state (pre-fix):**

Opus QA reviews included **Category A findings** (machine-checkable deterministic patterns) that should have been encoded as CI checks: threshold source assertions, test-file path contracts, evidence-registry completeness, and Category A literal regression presence checks.

**Required:**

For each identified Category A pattern currently checked by Opus QA:
1. Identify the pattern (documented in ADR-0049 §3).
2. Write a CI test that checks the pattern deterministically.
3. Validate the CI test (see T5-38).
4. Remove the pattern from Opus QA scope (update ADR-0049 §3 Category A list as each pattern migrates).

**Finalized binding pattern list (Audit Pass):**
- Pattern 1: Threshold Source-of-Truth Enforcement
- Pattern 2: Evidence Registry Coverage Parity
- Pattern 3: Mirrored Test-File Path Contract
- Pattern 4: Category A Literal Regression Presence Check

**MIGRATION UNIT 1 — CLOSED**
- Pattern: Pattern 1 — Threshold Source-of-Truth Enforcement
- CI gate: `test_ci_gate_threshold_source_of_truth_enforcement`
- Validating meta-test: `test_meta_threshold_source_of_truth_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 1 / 4
  - T5-38: 1 / 4
- Parent status invariant: T5-37 remained OPEN at this checkpoint.

**MIGRATION UNIT 2 — CLOSED**
- Pattern: Pattern 2 — EVIDENCE REGISTRY COVERAGE PARITY
- CI gate: `test_ci_gate_evidence_registry_coverage_parity`
- Validating meta-test: `test_meta_evidence_registry_coverage_parity_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 2 / 4
  - T5-38: 2 / 4
- Parent status invariant: T5-37 remained OPEN at this checkpoint.

**MIGRATION UNIT 3 — CLOSED**
- Pattern: Pattern 3 — MIRRORED TEST-FILE PATH CONTRACT
- CI gate: `test_ci_gate_mirrored_test_file_path_contract`
- Validating meta-test: `test_meta_mirrored_test_file_path_contract_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 3 / 4
  - T5-38: 3 / 4
- Parent status invariant: T5-37 remained OPEN at this checkpoint.

**MIGRATION UNIT 4 — CLOSED**
- Pattern: Pattern 4 — CATEGORY A LITERAL REGRESSION PRESENCE CHECK
- CI gate: `test_ci_gate_category_a_literal_regression_presence_check`
- Validating meta-test: `test_meta_category_a_literal_regression_presence_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 4 / 4
  - T5-38: 4 / 4

**Resolution:**

Implemented the Pattern 4 deterministic CI gate and paired validating meta-test in `tests/test_opus_category_a_literal_regression_presence_gate.py`. The gate performs module-scoped AST/source-token inspection to prevent reintroduction of previously extracted Category A literals; the meta-test injects known-bad input and proves the gate fails. With Unit 4 closed, all finalized binding patterns (1–4) are now migrated with paired validating tests, and mandatory gates are green on the full suite.

**Parent closure proof (all conditions satisfied):**
1. Audit Pass DONE and recorded.
2. Migration Unit 1 CLOSED.
3. Migration Unit 2 CLOSED.
4. Migration Unit 3 CLOSED.
5. MIGRATION UNIT 4 — CLOSED.
6. Every CI gate has paired validating meta-test.
7. All mandatory gates green (`ruff check .`, strict pytest, full pytest).
8. No remaining pattern outside finalized binding list (4-pattern list complete).

**Task learning:** The literal-regression gate must compare source-level numeric tokens (including unary negatives) instead of only numeric values, so exact regression literals are blocked while avoiding false positives from semantically different literals.

**Acceptance gate (binary):** All identified Category A patterns from the initial triage have corresponding CI tests; each CI test is verified by its T5-38 validating test; Opus QA scope section in AGENTS.md reflects migrated-pattern exclusion; all mandatory gates green.

---

### T5-38 · Opus QA — CI gates replacing Category A findings lack validating tests ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. Commit: cc5ce69. Architect ruling 2026-03-15: CLOSED WITH REQUIRED RECORDS CORRECTION — ADR-0049 §7 correctly and substantively applied; stale closure hash (251df1c) replaced with canonical current closure commit.
**Execution model:** Hybrid Sequential (per ADR-0049 §7, paired with T5-37 per-gate) — no independent closure before T5-37.
**Migration units completed:** 4 / 4 (bound to T5-37 Audit Pass finalized list)
**Workflow Path: A** *(meta-test work; no ADR required)*
**Change Type:** implementation
**Source:** ADR-0049 §4 (Architect Decision 2026-03-15): every CI gate that replaces an Opus Category A finding must itself have a validating test to confirm the gate fires correctly on known-bad input. Records-safe: next available ID T5-38.
**Priority:** P1 — a CI gate without a validating test is an unverified gate.

**Original state (pre-fix):**

When a deterministic Opus finding was migrated to a CI test (T5-37), that CI gate could still be incorrectly written (pass on bad input, miss the failure mode, or silently no-op). Without validating meta-tests, a broken CI gate could create false confidence.

**Acceptance gate (binary):** Every CI gate added by T5-37 has a paired meta-test confirming it fires on known-bad input; no CI gate added under T5-37 is left without a validating test; all mandatory gates green.

**MIGRATION UNIT 1 — CLOSED**
- Pattern: Pattern 1 — Threshold Source-of-Truth Enforcement
- CI gate: `test_ci_gate_threshold_source_of_truth_enforcement`
- Validating meta-test: `test_meta_threshold_source_of_truth_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 1 / 4
  - T5-38: 1 / 4
- Parent status invariant: T5-38 remained OPEN at this checkpoint.

**MIGRATION UNIT 2 — CLOSED**
- Pattern: Pattern 2 — EVIDENCE REGISTRY COVERAGE PARITY
- CI gate: `test_ci_gate_evidence_registry_coverage_parity`
- Validating meta-test: `test_meta_evidence_registry_coverage_parity_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 2 / 4
  - T5-38: 2 / 4
- Parent status invariant: T5-38 remained OPEN at this checkpoint.

**MIGRATION UNIT 3 — CLOSED**
- Pattern: Pattern 3 — MIRRORED TEST-FILE PATH CONTRACT
- CI gate: `test_ci_gate_mirrored_test_file_path_contract`
- Validating meta-test: `test_meta_mirrored_test_file_path_contract_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 3 / 4
  - T5-38: 3 / 4
- Parent status invariant: T5-38 remained OPEN at this checkpoint.

**MIGRATION UNIT 4 — CLOSED**
- Pattern: Pattern 4 — CATEGORY A LITERAL REGRESSION PRESENCE CHECK
- CI gate: `test_ci_gate_category_a_literal_regression_presence_check`
- Validating meta-test: `test_meta_category_a_literal_regression_presence_gate_rejects_known_bad_input`
- Migration progress update:
  - T5-37: 4 / 4
  - T5-38: 4 / 4

**Resolution:** Added the Pattern 4 validating meta-test in the same gate file as the new CI gate (`tests/test_opus_category_a_literal_regression_presence_gate.py`) and preserved one-to-one pairing discipline across all four migration units.

**Parent closure proof:** T5-38 closure is valid because T5-37 lane completion is now 4/4 with paired meta-tests per unit and all mandatory gates green in the same pass.

**Task learning:** Pairing each CI gate with an immediate known-bad meta-test in the same module keeps the migration lane deterministic and prevents unverified gate drift.

---

### T5-39 · `adaptive_priority_lock.py` — replace inline `cs_min_confidence = 0.70` with canonical threshold import ✅ RESOLVED 2026-03-17

**Status:** ✅ RESOLVED 2026-03-17. Commit: `2f46d59` (PR #489 merge commit).
**Workflow Path: A** *(narrow import replacement — no ADR required)*
**Source:** DEC-020 (Response to OBS-020, 2026-03-16). `titan/science/adaptive_priority_lock.py`:35, `titan/config/thresholds.py`:96.
**Type:** Threshold Governance — Category A extraction
**Priority:** P3. Independent.
**Effort:** ~30 min.

**Scope constraint (hard):** This item covers **only** the `cs_min_confidence = 0.70` default-dict duplicate at `adaptive_priority_lock.py`:35. Phase override values (`PEAK`, `BUILD_OVERLOAD`, `TAPER` per-phase `cs_min_confidence` literals at lines 40–42) are **Category B** per DEC-020 and must remain inline. Do NOT extract phase overrides as part of this task.

**Location:** `titan/science/adaptive_priority_lock.py`:35.

**Original state (pre-fix):**

`_DEFAULT_THRESHOLDS` in `adaptive_priority_lock.py` defines `"cs_min_confidence": 0.70` as an
inline literal, with a comment acknowledging the duplicate (`# GovernanceEngine.CS_CONFIDENCE_THRESHOLD`).
The canonical constant `GOVERNANCE_CS_CONFIDENCE_THRESHOLD = 0.70` already exists in
`titan/config/thresholds.py`:96. The inline value is a Category A threshold duplication that
creates drift risk: a future change to `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` would not
automatically propagate to `_DEFAULT_THRESHOLDS`.

**Required:**

1. Import `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` from `titan/config/thresholds.py` at the top
   of `adaptive_priority_lock.py` (alongside any existing threshold imports).
2. Replace the inline `0.70` at `_DEFAULT_THRESHOLDS["cs_min_confidence"]` with
   `GOVERNANCE_CS_CONFIDENCE_THRESHOLD`.
3. Remove the now-redundant inline comment (`# GovernanceEngine.CS_CONFIDENCE_THRESHOLD`).
4. Add or extend a test in `tests/titan/science/test_adaptive_priority_lock.py` asserting that
   `_DEFAULT_THRESHOLDS["cs_min_confidence"]` equals `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` (source
   binding assertion — not just value equality).
5. Mandatory gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`,
   `python -m pytest -q` — all green.

**Acceptance gate (binary):** `adaptive_priority_lock.py` imports and uses
`GOVERNANCE_CS_CONFIDENCE_THRESHOLD` for the default `cs_min_confidence` value; phase override
literals remain inline unchanged; a source-binding test asserts the import; all mandatory gates
green.

**Task learning:** Branch created under `codex/*` prefix instead of canonical `claude/*` — process blemish only, no functional impact. Category A constant extractions benefit from pairing the import replacement and source-binding assertion in the same commit to keep the acceptance gate verifiable atomically.

---

### T5-40 · `notification_gateway.py` — boolean-return handling + branch coverage test ✅ RESOLVED 2026-03-17

**Status:** ✅ RESOLVED 2026-03-17. Commit: `b058ed2` (PR #491 merge commit).
**Workflow Path: A** *(narrow call-site fix + targeted test — no ADR required)*
**Source:** DEC-022 (Response to OBS-022, 2026-03-16). `titan/integrations/notification_gateway.py`:75–95, `titan/integrations/telegram_bot.py`:444–467, `tests/titan/integrations/test_notification_gateway.py`.
**Type:** Silent-failure path — delivery boolean ignored
**Priority:** P3. Independent.
**Effort:** ~1–2h.

**Canonical issue:**

`TelegramChannel.send()` currently ignores the boolean return value from the underlying bot
delivery call. Any non-exception path is treated as success, meaning a `False` return (delivery
rejected without raising) is a silent failure: the caller receives no indication that the message
was not delivered.

**Required:**

1. Consume the boolean return value from the bot delivery call inside `TelegramChannel.send()`
   (`notification_gateway.py`:75–95) and propagate delivery failure correctly to the caller
   (e.g., return `False` or raise a typed delivery exception — consistent with the existing
   channel contract).
2. Audit `telegram_bot.py`:444–467 for the same pattern and apply the same fix if present.
3. Add a targeted test in `tests/titan/integrations/test_notification_gateway.py` covering the
   `False`-without-exception branch: mock the bot call to return `False` without raising and
   assert that the failure is surfaced to the caller (not silently swallowed).
4. Mandatory gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`,
   `python -m pytest -q` — all green.

**Acceptance gate (binary):** `TelegramChannel.send()` consumes and propagates the boolean
return; the `False`-without-exception branch has explicit test coverage; all mandatory gates green.

**Task learning:** Branch created under `codex/*` prefix instead of canonical `claude/*` — process blemish only, no functional impact. PR title remained generic (did not follow `T<tier>-<id>: <short title>` format) — process blemish only, no functional impact. Both deviations are non-functional and did not affect test gate outcomes.

---

### T5-41 · `weather_api.py` — dew-point decision bands extraction to `thresholds.py` ✅ RESOLVED 2026-03-17

**Status:** ✅ RESOLVED 2026-03-17. Commit: `2f46d59` (PR #489 merge commit).
**Workflow Path: A** *(Category A constant extraction — no ADR required)*
**Source:** DEC-022 (Response to OBS-022, 2026-03-16). `titan/integrations/weather_api.py`:158–170, 529–537.
**Type:** Threshold Governance — Category A extraction
**Priority:** P3. Independent.
**Effort:** ~1h.

**Canonical issue:**

Dew-point decision bands are represented by multiple independent literal clusters inside
`titan/integrations/weather_api.py` (lines 158–170 and 529–537). The same weather-decision
domain is duplicated in at least two locations without a shared named constant, creating drift
risk: a future calibration change must be applied consistently across all clusters or the
decision boundaries diverge silently.

**Required:**

1. Identify all dew-point band literals in `weather_api.py` (both clusters at lines 158–170
   and 529–537, plus any others found during audit).
2. Extract the dew-point decision bands to named constants in `titan/config/thresholds.py`
   (alongside existing weather/environmental constants; add `evidence_registry.py` provenance
   entries as HEURISTIC if not already present).
3. Replace all inline literals in `weather_api.py` with imports of the new named constants.
4. Confirm no other module duplicates these literals (Grep sweep); fix any found.
5. Mandatory gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`,
   `python -m pytest -q` — all green.

**Acceptance gate (binary):** All dew-point decision band literals in `weather_api.py` are
replaced by named constants imported from `thresholds.py`; `evidence_registry.py` has
provenance entries; no remaining inline duplicates found by Grep; all mandatory gates green.

**Task learning:** Branch created under `codex/*` prefix instead of canonical `claude/*` — process blemish only, no functional impact. Multi-cluster literal extraction (two separate line ranges in the same file) requires a Grep sweep before writing replacements to avoid missing a third cluster introduced by future edits.

---

### T5-42 · `NutritionOptimizer` — public API test coverage gap ✅ RESOLVED 2026-03-17

**Status:** ✅ RESOLVED 2026-03-17. Commit: `b058ed2` (PR #491 merge commit).
**Workflow Path: A** *(test-only; no production code changes)*
**Source:** DEC-023 (Response to OBS-023, 2026-03-16). `titan/features/nutrition_optimizer.py`.
**Type:** Test Coverage — public API contract
**Priority:** P3. Independent.
**Effort:** ~1–2h.

**Canonical issue:**

`NutritionOptimizer` exposes three public methods. Mirrored tests currently cover
`analyze_weight_trend()` only. `add_weight_entry()` and `calculate_daily_nutrition()`
are public recommendation/hydration contract outputs and have no explicit test coverage.

**Required:**

`tests/titan/features/test_nutrition_optimizer.py` — add tests for:

1. `add_weight_entry()`:
   - happy path
   - duplicate date boundary
   - empty input boundary

2. `calculate_daily_nutrition()`:
   - happy path output contract
   - zero weight boundary
   - extreme macro target boundary
   - hydration edge cases

3. Mandatory gates: `ruff check .`, `python -m pytest -q -W error::pytest.PytestWarning`,
   `python -m pytest -q` — all green.

**Acceptance gate (binary):** `add_weight_entry()` and `calculate_daily_nutrition()` each
have explicit tests covering happy path and the stated boundary cases; all mandatory gates green.

**Task learning:** Branch created under `codex/*` prefix instead of canonical `claude/*` — process blemish only, no functional impact. PR title remained generic (did not follow `T<tier>-<id>: <short title>` format) — process blemish only, no functional impact. Both deviations are non-functional and did not affect test gate outcomes.

---

### T5-43 · cryptography/cffi native extension broken in CI environment ✅ RESOLVED 2026-03-17

**Status:** ✅ RESOLVED 2026-03-17. Commit: 3a7a67b. **Resolution:** Pinned `withings-sync==4.1.0` in `constraints.txt`. Root cause was broken `.VERSION` file in withings-sync 4.2.6/4.2.7 build process, which prevented cryptography/cffi from installing correctly. All 10 previously-erroring test files now collect and pass. Gate 2/Gate 3 fully restored.
**Workflow Path: A**
**Change Type:** implementation
**Source:** Repository State Verification Report 2026-03-17.
**Priority:** P2 — blocks Gate 2/Gate 3 for all T5-11/T5-13/T5-08-B related work.

**Original state:** `_cffi_backend` native extension absent from environment.
Causes `ModuleNotFoundError` at collection time for 10 test files:
- `tests/titan/api/test_audit.py`
- `tests/titan/api/test_auth.py`
- `tests/titan/core/test_alembic_d2a_migration.py`
- `tests/titan/core/test_alembic_d3_migration.py`
- `tests/titan/core/test_alembic_d5_model_calibration_metadata_migration.py`
- `tests/titan/core/test_alembic_d9_consent_log_migration.py`
- `tests/titan/core/test_alembic_t5_11_auth_migration.py`
- `tests/titan/core/test_alembic_t5_13_coach_audit_log_migration.py`
- `tests/titan/core/test_persistence.py`
- `tests/titan/core/test_postgresql_adapter_concurrency.py`

**Acceptance criteria (binary):**
- `python -c "import _cffi_backend"` exits 0
- `python -m pytest -q --no-header 2>&1 | tail -3` shows 0 collection errors
- `python -m pytest -q` passes with count ≥ 1999
- `ruff check .` zero findings

**Bottleneck:** Environment repair only — no production code changes.
**Owner:** Codex
**Unblock condition:** All 10 previously-erroring test files collect and pass cleanly.

**Task learning:** Transitive dependency build failures can silently block unrelated test modules. constraints.txt is the correct intervention point — not requirements.txt — when the broken package is a transitive dependency pulled by a pinned direct dependency.

---

### T5-44 · TRIMP uses session maxHR instead of athlete HRmax ✅ RESOLVED 2026-03-28

**Status:** ✅ RESOLVED 2026-03-28. PR #547 (commits 68b3bf6 + af5d1fb).
**Source:** OBS-027 / OBS-025 F-13
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/science/trimp_engine.py:49`, `titan/integrations/garmin_sync.py:335-339`
**Description:** `sync_activities()` passes session peak HR (not athlete physiological HRmax) to `TRIMPEngine.calculate_edwards_trimp()`, systematically misclassifying training zones and skewing TSB/CTL/ATL downstream.

**Resolution:** `TRIMPEngine.calculate_edwards_trimp()` parameter renamed from `max_hr` to `athlete_max_hr`; zone boundaries now use athlete physiological HRmax from `AthleteProfile`, not session peak HR. `GarminSync.sync_activities()` accepts `athlete_max_hr` parameter; `DailyCoach` injects `athlete_profile.max_hr` at construction via `GarminSync.athlete_max_hr` attribute. Session peak HR retained in activity dict as `max_hr` for diagnostic value. `MODULE_VERSION` bumped to 1.0.1.
**Task learning:** Engine contract fixes that add a new required parameter need caller wiring in the same PR to avoid a production silent-failure window where the parameter defaults to a safe-but-wrong value.

---

### T5-45 · HRV baseline uses population SD instead of sample SD ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #537.
**Source:** OBS-027 / OBS-025 F-07
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/hrv_engine.py:66`
**Description:** HRV baseline divides by N instead of N-1 (Plews et al. require sample SD); for 7-day window this underestimates SD by ~8%, making suppression thresholds 8% tighter than intended.

**Resolution:** `HRVEngine.calculate_baseline` now divides by N-1 (sample SD) instead of N (population SD), eliminating the ~8% systematic underestimation of SD for 7-day windows.
**Task learning:** Statistical estimators for small clinical windows must use sample SD (N-1) to avoid systematically tightening suppression thresholds below the evidence-based intent.

---

### T5-46 · No HRV deduplication on overlapping Garmin syncs ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #538.
**Source:** OBS-027 / OBS-025 F-08
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/hrv_engine.py:55`
**Description:** Overlapping Garmin syncs inflate the HRV log with duplicate entries; duplicate measurements skew baseline and trend calculations.

**Resolution:** HRV log ingestion now deduplicates entries by timestamp before baseline and trend calculations, preventing overlapping Garmin syncs from inflating the HRV baseline.
**Task learning:** Time-series ingestion pipelines must deduplicate on the natural key (timestamp) at the storage boundary to prevent measurement inflation from repeated syncs.

---

### T5-47 · Unguarded ZeroDivisionError when Garmin activity pace is zero ✅ RESOLVED 2026-03-26

**Status:** ✅ RESOLVED 2026-03-26. Commit: 52537ed (PR #526).
**Source:** OBS-027 / OBS-025 F-17
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/efficiency_engine.py:56`
**Description:** `1000.0 / avg_pace_sec_per_km` raises unguarded `ZeroDivisionError` for stationary or zero-pace activities synced from Garmin.

**Resolution:** `EfficiencyEngine.calculate_efficiency_factor` now returns `None` when `avg_pace_sec_per_km` is zero or `None`, eliminating the unguarded `ZeroDivisionError` on stationary or zero-pace Garmin activities.
**Task learning:** Pace-based calculations must return `None` (not `0.0`) for absent or zero data so downstream callers can distinguish "no data" from "minimum efficiency."

---

### T5-48 · Garmin data age not propagated into governance context ✅ RESOLVED 2026-03-28

**Status:** ✅ RESOLVED 2026-03-28. PR #548.
**Source:** OBS-027 / OBS-025 F-20
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/governance_engine.py` (context dict construction)
**Description:** ADR-0041 `DataTrustLevel` is evaluated at sync boundary but governance cannot distinguish fresh from 24-hour-stale data; staleness is invisible to all safety gates.

**Resolution:** `data_age_hours` field added to `GarminSyncResult` TypedDict and `GarminSyncResultContract`. Garmin sync paths (success, empty, timeout) populate the field correctly — timeout path bug fixed (was hardcoded `0.0`, now uses `_compute_data_age_hours()`). `DailyCoach` propagates `garmin_data_age_hours` and `garmin_data_trust_level` into governance context dict. `GovernanceEngine` includes both fields in every `_gate_event()` call across all gates (H1–H5, `VO2_ELIGIBILITY`, `FUELING`, `PARASYMPATHETIC_GUARD`, `OVERRIDE_LOCKDOWN`, `CS_CONFIDENCE_LOCK`, `APPLY_CONSTRAINTS`). Defensive defaults: `None` / `"UNKNOWN"` when absent from context.
**Task learning:** Observability-only propagation tasks can still surface real bugs (hardcoded `0.0` in timeout path). Scope constraint "no gate logic changes" must be verified explicitly in the diff before merge.

---

### T5-49 · Governance defaults missing sleep/readiness to 100 (optimistic) ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #535.
**Source:** OBS-027 / OBS-025 F-21/F-22
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/governance_engine.py:198,205`
**Description:** When `sleep_score` or `readiness_score` are absent from context, governance defaults to 100; safety-first design requires conservative defaults (e.g. 40) so the 2-of-4 downgrade can fire.

**Resolution:** Governance engine now defaults missing `sleep_score` and `readiness_score` to 40 (conservative) instead of 100, ensuring the 2-of-4 downgrade gate fires correctly on absent data.
**Task learning:** Safety-critical missing-value defaults must be conservative (low values trigger gates) rather than optimistic (high values suppress gates).

---

### T5-50 · All Garmin activities persisted with session_type EASY ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #539.
**Source:** OBS-027 / OBS-025 F-31
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py:1256`
**Description:** `sync_activities()` never sets `session_type`; the hardcoded default `'EASY'` is written to the DB for every activity regardless of actual effort level.

**Resolution:** `sync_activities()` now maps Garmin activity type to `session_type` before DB persistence, replacing the hardcoded `'EASY'` default with the actual effort classification from the source record.
**Task learning:** Activity classification fields that drive downstream governance logic must be derived from the source record at ingestion; hardcoded defaults must not stand in for missing type mappings.

---

### T5-51 · ACWR defaults to 1.0 (sweet spot) when Garmin sync fails ✅ RESOLVED 2026-03-26

**Status:** ✅ RESOLVED 2026-03-26. Commit: 5f68fc5 (PR #530).
**Source:** OBS-027 / OBS-026 B1-F04
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py:713,727`
**Description:** `garmin_data.get('acwr', 1.0)` defaults to ACWR=1.0 (sweet spot) on sync failure; `IntensityGovernor` and `VolumeLoadGauge` see "all clear" instead of "unknown," allowing VO2 eligibility and intensity gates to pass on absent data.

**Resolution:** `garmin_data.get('acwr', 1.0)` replaced with `None` propagation; downstream null guards use `0.0` where a float is required, so missing ACWR is no longer treated as an "all-clear" sweet-spot by the governance pipeline.
**Task learning:** Optimistic defaults on safety-critical fields must be replaced with `None` propagation so governance gates correctly reflect data absence rather than optimal state.

---

### T5-52 · CS confidence defaults to 1.0 when cs_tracker is None, bypassing CS_CONFIDENCE_LOCK ✅ RESOLVED 2026-03-26

**Status:** ✅ RESOLVED 2026-03-26. Commit: 19f9a1d (PR #529).
**Source:** OBS-027 / OBS-026 B2-F01
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/science/governance_engine.py:149`
**Description:** `getattr(cs_tracker, "confidence", 1.0)` returns 100% confidence when `cs_tracker` is `None` or uncalibrated; `CS_CONFIDENCE_LOCK` (70% threshold) never fires for athletes with no calibration data.

**Resolution:** `getattr(cs_tracker, "confidence", 1.0)` default changed to `0.0`, ensuring `CS_CONFIDENCE_LOCK` fires for any uncalibrated tracker instead of being silently bypassed.
**Task learning:** Safety lock defaults must use the most conservative value (0.0) when the controlling attribute is absent, never the most permissive (1.0).

---

### T5-53 · ReadinessEngine TypeError on null HRV from physiological bounds clamping ✅ RESOLVED 2026-03-26

**Status:** ✅ RESOLVED 2026-03-26. Commit: 0d9f852 (PR #527).
**Source:** OBS-027 / OBS-026 B1-F03
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py` → `titan/science/readiness_engine.py`
**Description:** `physiological_bounds.validate_and_clamp()` can null `hrv_ms`; `DailyCoach` passes null `latest_hrv` to `ReadinessEngine.analyze_readiness()` which performs `hrv_diff = today_hrv - baseline_hrv` → unguarded `TypeError` crash.

**Resolution:** `ReadinessEngine.analyze_readiness` now null-guards the HRV diff calculation; when either `today_hrv` or `baseline_hrv` is `None`, the HRV component is skipped and the readiness score is computed from remaining components only.
**Task learning:** Science engines receiving values from the physiological bounds clamping layer must guard every arithmetic operation on those values against `None`.

---

### T5-54 · drift_pct defaults to 0.0 (perfect efficiency) when Garmin sync fails ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #541.
**Source:** OBS-027 / OBS-026 B1-F05
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py:708`
**Description:** `garmin_data.get('drift_pct', 0.0)` defaults to 0.0 (perfect cardiac efficiency) on sync failure; `IntensityGovernor` should treat `None` drift as a YELLOW trigger, not a pass.

**Resolution:** Default changed from `0.0` to `None`. `IntensityGovernor` now treats missing drift as unknown rather than perfect efficiency; `None` drift no longer silently suppresses a YELLOW trigger.

**Task Learning:** Optimistic defaults for physiological metrics are indistinguishable from real clean data at the governance layer. Absence of a signal must propagate as `None`, not as a neutral value — the governor must decide what to do with missing data, not the data-fetch layer.

---

### T5-55 · Thermal degradation ignores dew point — ESI model unused in apply_thermal ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #544.
**Source:** OBS-027 / OBS-026 B2-F02
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/critical_speed.py:218-234`
**Description:** `CriticalSpeedTracker.apply_thermal()` uses dry-bulb temperature only; the ESI model (`ESI = temp_c + 0.5 * dew_point_c`) exists in `thresholds.py` and is used for pace adjustments in `DailyCoach`, but is not applied to thermal degradation — a 25°C/90% humidity day (ESI 36.5) gets only 2.5% degradation instead of the physiologically appropriate penalty.

**Resolution:** `apply_thermal()` now uses the ESI formula (`temp_c + 0.5 * dew_point_c`) when `dew_point` is available; falls back to dry-bulb temperature when absent. Thermal degradation penalty is now consistent with the ESI-based pace adjustment already applied in `DailyCoach`.

**Task Learning:** When a physiological model (ESI) is already implemented and validated in one part of the system, every consumer of that input domain must use it. A partial adoption — where pace uses ESI but thermal degradation uses dry-bulb — creates silent inconsistency: two outputs from the same session use different humidity assumptions with no user-visible signal.

---

### T5-56 · AFI confidence not degraded for sparse HRR data ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #542.
**Source:** OBS-027 / OBS-026 B2-F03
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/autonomic_engine.py:120`
**Description:** `AutonomicFusionEngine` defaults `hrr_norm` to 0.0 (neutral) for sparse HRR data with no confidence penalty; AFI should apply a confidence degradation when HRR history is insufficient.

**Resolution:** AFI confidence penalised to 0.7 when HRR history contains fewer than 3 data points. Absent HRR (`None`) carries no penalty — absence is a known unknown; sparse history is an unreliable signal being treated as reliable.

**Task Learning:** Sparse data and absent data are distinct failure modes and must be handled separately. A `None` value says "we have no reading"; a short history says "we have a reading but it may not be representative." Only the latter warrants a confidence penalty because it produces a value the engine will use.

---

### T5-57 · Weekly plan never re-evaluated on mid-week Garmin data changes ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #545.
**Source:** OBS-027 / OBS-026 B3-F01
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/features/weekly_plan.py`
**Description:** `WeeklyPlanGenerator` runs once Sunday 20:00 and is static for the week; significant mid-week Garmin data (race performance, illness, unexpected HRV drop) never triggers plan re-evaluation.

**Resolution:** `should_replan()` predicate added to `WeeklyPlanGenerator`; mid-week re-evaluation triggers on HRV drop >10 ms since plan generation, a `HARD_STOP` governance event within the preceding 24 hours, or an illness flag. When any trigger fires, the planner regenerates the remainder of the week's plan from current data.

**Task Learning:** A plan is only as good as the assumptions it was built on. Static weekly plans assume the athlete's physiological state is stable for seven days — a reasonable default but a dangerous invariant. Safety-relevant events (HARD_STOP, illness, significant HRV deterioration) invalidate the plan's underlying assumptions and must have a defined re-evaluation path. Polling-only architectures (run once, never revisit) need an explicit predicate to answer "is this plan still valid?" before the question is forced by a bad outcome.

---

### T5-58 · WeeklyPlanner HRV TypeError on null values in _apply_hrv_adjustments ✅ RESOLVED 2026-03-26

**Status:** ✅ RESOLVED 2026-03-26. Commit: d0dbd67 (PR #528).
**Source:** OBS-027 / OBS-026 B3-F02
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/features/weekly_plan.py` (`_apply_hrv_adjustments`)
**Description:** `hrv_engine.get_hrv_summary()` can return `None` for `baseline` or `latest_hrv`; `_apply_hrv_adjustments` compares `latest < baseline - 10` without null guard → unguarded `TypeError` crash path.

**Resolution:** `_apply_hrv_adjustments` now uses explicit `is not None` guards on both `baseline` and `latest_hrv` before comparison, preventing `TypeError` when `get_hrv_summary()` returns null HRV values.
**Task learning:** Use `is not None` rather than truthy checks for numeric null guards to avoid silently skipping valid `0.0` values while correctly blocking `None`.

---

### T5-59 · NutritionOptimizer dew_point defaults to 15°C (optimistic) ✅ RESOLVED 2026-03-27

**Status:** ✅ RESOLVED 2026-03-27. PR #536.
**Source:** OBS-027 / OBS-026 B3-F04
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/features/nutrition_optimizer.py:188`
**Description:** `NutritionOptimizer` defaults `dew_point` to 15°C when weather data is unavailable; 15°C is a comfortable value that underestimates sweat/electrolyte needs — should default to a conservative value or flag as unknown.

**Resolution:** `NutritionOptimizer` now defaults `dew_point` to 25°C (conservative, high-humidity proxy) when weather data is unavailable, preventing underestimation of sweat and electrolyte needs.
**Task learning:** Environmental defaults affecting safety-adjacent outputs (hydration, electrolytes) must use conservative worst-case values, not comfortable midpoint values.

---

### T5-60 · sleep field mapping mismatch — _persist_garmin_data reads raw Garmin format instead of sync_sleep() output ✅ RESOLVED 2026-03-28

**Status:** ✅ RESOLVED 2026-03-28. PR #552.
**Source:** OBS-027 / OBS-025 F-29
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py` (`_persist_garmin_data` sleep extraction block)
**Description:** `sync_sleep()` returns flattened keys (`total_sleep_hours`, `sleep_score`). `_persist_garmin_data` was reading raw Garmin keys (`restingHeartRate`, `sleepScores.overall.value`, `sleepTimeSeconds`). None of these exist in the flattened output. Result: `today_sleep_score` defaulted to 75 (hardcoded optimistic value); sleep quality indicator could not fire correctly. (`today_rhr` is not provided by `sync_sleep()` — RHR comes from a separate Garmin endpoint; the 0-default is correct behaviour when no RHR sync runs.)

**Resolution:** `_persist_garmin_data()` updated to read the flattened keys returned by `sync_sleep()` instead of raw Garmin keys. Default `today_sleep_score` changed from 75 → 50 (conservative: `sleep_delta` is negative when data is missing). Explicit `is None` guards replace `or 0` truthiness checks. H3 gate and 2-of-4 sleep indicator can now fire correctly.
**Task learning:** Truthiness checks (`or 0`) on numeric fields collapse `None` to `0` and prevent correct fallback. Explicit `is None` checks are required when `0` and `None` have different semantics.

---

### T5-61 · multi-day HRV sync discards 6 of 7 days — only today persisted to DB ✅ RESOLVED 2026-03-28

**Status:** ✅ RESOLVED 2026-03-28. PR #553.
**Source:** OBS-027 / OBS-025 F-27/F-32
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py` (`_persist_garmin_data` HRV persistence block)
**Description:** `sync_hrv(days_back=7)` fetches 7 days of HRV. `_persist_garmin_data` was persisting only the entry matching `today_str`. The other 6 days populated the in-memory hrv_engine but never reached the DB. On restart, HRV baseline was computed from a single day — not the 7-day window required for meaningful baseline computation (Plews et al.).

**Resolution:** `_persist_garmin_data()` now loops over all HRV entries. Historical entries are persisted via new `save_daily_metric_if_missing()` method (INSERT OR IGNORE) to protect manually entered data. Today's entry continues to use `save_daily_metric()` (INSERT OR REPLACE).
**Task learning:** Backfill operations must use INSERT OR IGNORE for historical dates — the user may have manually entered data that must not be overwritten.

---

### T5-62 · zero-sync silent failure — stale token assumed valid on 429 + empty sync recorded as success ✅ RESOLVED 2026-03-28

**Status:** ✅ RESOLVED 2026-03-28. PR #551.
**Source:** OBS-027 / zero-sync investigation Z1+Z2
**Severity:** HIGH
**Workflow Path: A**
**Location:**
- `titan/integrations/garmin_sync.py` (connect(), token validation block)
- `titan/orchestration/daily_coach.py` (sync_ok determination)
**Description:** Two-bug chain producing silent 0/0/0/0 sync loop. Bug 1: When verification ping got 429, token was assumed valid even if expired. Subsequent API calls failed silently — each sync method catches exception and returns []. Bug 2: DailyCoach determined success by `sync_status != "timeout_cancelled"` only. A sync returning 0/0/0/0 with no timeout was recorded as success=True, resetting the staleness timer. No alert fired.

**Resolution:**
- Part A (`garmin_sync.py`): When verification ping → 429 and the secondary call also fails, `_invalidate_session()` + `return False` instead of fallthrough to re-login. Token file is deleted, forcing re-authentication.
- Part B (`daily_coach.py`): Empty sync (0/0/0/0) is recorded as failure and fires a `garmin_sync_empty` WARNING event.
**Task learning:** Rate-limited windows require conservative behavior — hammering with re-login during a 429 window worsens the problem. Empty results without a timeout must be treated as failure, not success.

---

### T5-65 · classify_hrv_stress_context None ACWR returns TRAINING_EXPLAINED — fix to UNKNOWN conservative label ✅ RESOLVED

**Status:** RESOLVED 2026-03-29
**Source:** DEC-028 / OBS-030
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/science/governance_engine.py:235–242` (`classify_hrv_stress_context`)
**Description:** `classify_hrv_stress_context()` (originally described as `_classify_hrv_drop`) converted None ACWR to `1.0` via `float(context.get("acwr", 1.0))` and returned `TRAINING_EXPLAINED` when ACWR was absent. ADR-0051 (conservative-fail policy) requires None ACWR to return `UNKNOWN_ACWR`, not an optimistic classification. The fix was registered after ADR-0051 was accepted.

**Resolution:** Fix applied as part of T5-65 wave 2026-03-29. Confirmed ADR-0051 compliant by architect 2026-03-29. `classify_hrv_stress_context()` returns `UNKNOWN_ACWR` for None/absent/unparseable ACWR. No further implementation required.

**Task learning:** Code compliance verification before implementation avoids unnecessary churn. When an ADR fix is applied before the debt entry is created, always confirm live code state before opening an implementation task.

---

### T5-66 · save_daily_metric INSERT OR REPLACE silently destroys subjective fields on re-sync ✅ RESOLVED

**Status:** RESOLVED 2026-03-29
**Source:** DEC-029 / OBS-031
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/core/database.py:758` (`save_daily_metric`)
**Description:** `save_daily_metric` used `INSERT OR REPLACE INTO daily_metrics`. SQLite `INSERT OR REPLACE` semantics delete the existing row before inserting the new one; any column not included in the new insert is lost. On a Garmin re-sync, the new row contains only biometric fields — manually entered subjective fatigue scores (`subjective_fatigue_score`) and other manual fields are silently destroyed. The downstream consequence: on re-sync days, the 2-of-4 downgrade gate cannot fire correctly because the subjective fatigue input was erased.

**Resolution:** Replaced `INSERT OR REPLACE` with per-column `INSERT ... ON CONFLICT DO UPDATE SET` UPSERT. Garmin-sourced columns (`weight_kg`, `hrv_rmssd`, `resting_hr`, `sleep_hours`, `sleep_quality`, `quality_flag`) are overwritten on re-sync only when the new value is NOT NULL. Manual subjective fields (`soreness`, `fatigue_level`, `mood`, `notes`) are never touched by the `DO UPDATE SET` clause and are therefore preserved when a Garmin re-sync does not include them. Test: `tests/test_t5_66_save_daily_metric_upsert.py` (5 tests — all green).

**Task learning:** `INSERT OR REPLACE` silently destroys rows on conflict — per-column UPSERT is always required when a table stores data from multiple sources (biometric + manual) that must be independently preserved.

---

### T5-67 · sync_sleep/sync_hrv/sync_activities/sync_weight emit success events unconditionally ✅ RESOLVED

**Status:** RESOLVED 2026-04-04
**Source:** DEC-030 / OBS-032
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/integrations/garmin_sync.py` (`sync_sleep`, `sync_hrv`, `sync_activities`, `sync_weight`)
**Description:** All four sync methods emit a `_garmin_event("synced", count=len(sessions), ...)` success event regardless of whether an exception was caught and suppressed earlier in the method. When an exception path fires, `sessions` is `[]` (empty list), and the success event fires with `count=0` — indistinguishable at the SLO alerting layer from a legitimate zero-record sync. Misleading success events undermine SLO alerting reliability and mask real Garmin API failures.

**Acceptance criteria (binary):** Each of the four sync methods gates the success event on explicit absence of exception (e.g. via a boolean flag set only in the non-exception path). An exception-suppressed sync must not emit a success event; it must emit a failure or warning event instead.

**Resolution:** Boolean flag `sync_succeeded = False` added to all four methods. Flag is set `True` only after all processing completes without raising. Success events (`activities_synced`, `weight_synced`, `sleep_synced`, `hrv_synced`) and `_log_sync()` moved outside the try/except block, guarded by `if sync_succeeded:`. Exception path emits only the `*_failed` event. Tests: `tests/test_t5_67_sync_success_event_gating.py` extended with 6 new tests for `sync_activities` and `sync_weight` (3 each: outer-exception suppresses success, success path emits event, failure event fires on exception) — all 12 T5-67 tests green.

**Task learning:** Placing success events inside a try block without a flag creates a race: if a later statement in the try raises (e.g. `_log_sync`), both success and failure events fire. Explicit boolean flag + post-block gating is the only pattern that guarantees mutual exclusion.

---

### T5-68 · ESI dew_point 12.0°C magic number in daily_coach.py — extract to ESI_DEW_POINT_FALLBACK_C ✅ RESOLVED

**Status:** RESOLVED 2026-03-29
**Source:** DEC-033 / OBS-035
**Severity:** LOW
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py:713`
**Description:** `dew_point_c=_safe_float(garmin_data.get("dew_point"), 12.0)` hardcoded `12.0°C` as the ESI dew-point fallback. `NutritionOptimizer` uses `25°C` as its dew-point conservative fallback (T5-59). Two different fallback values for the same physical quantity in the same thermal-stress pipeline produced internally inconsistent sweat/electrolyte assessments.

**Resolution:** `ESI_DEW_POINT_FALLBACK_C = 18.0` added to `titan/config/thresholds.py`; HEURISTIC provenance entry added to `titan/config/evidence_registry.py`; `daily_coach.py:714` replaced `12.0` literal with `ESI_DEW_POINT_FALLBACK_C` imported from `thresholds.py`; ADR-0034 annotated with T5-68 implementation note and constant name. Test: `tests/test_t5_68_esi_dew_point_fallback.py` (6 tests — all green).

**Task learning:** All numeric thresholds used as fallback/default values must be named constants in `thresholds.py` with provenance in `evidence_registry.py`. Magic number fallbacks in pipeline code are silent ADR violations.

---

### T5-69 · sync_activities lacks activityId extraction — training_log has no activity_id column, no deduplication ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-03-29
**Source:** DEC-034 / OBS-036
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/integrations/garmin_sync.py` (`sync_activities`), `titan/core/database.py` (`save_session`, `training_log` schema)
**Description:** `sync_activities()` does not extract `activityId` from the Garmin API response. The `training_log` schema has no `activity_id` column. `save_session()` has no activity-identity deduplication. On overlapping Garmin syncs, the same activity is inserted multiple times. Unlike HRV (where per-date deduplication is sufficient because there is at most one HRV measurement per day), activities can have multiple legitimate sessions on the same date (double-day training), so per-date deduplication would incorrectly drop valid sessions. Activity-ID deduplication is the correct approach. Impact: duplicate TRIMP loads silently inflate CTL/ATL/TSB, potentially falsely triggering or suppressing hard-stop gates. Fix pattern: follow T5-46 HRV deduplication pattern — extract ID, add column, `INSERT OR IGNORE` on `activity_id`.

**Acceptance criteria (binary):** `sync_activities()` extracts `activityId`; `training_log` schema has an `activity_id` column (via staged schema migration per §13.4); `save_session()` uses `INSERT OR IGNORE` on `activity_id`; duplicate syncs of the same activity produce exactly one `training_log` row.

**Resolution:** `sync_activities()` extracts `activityId` via `a.get("activityId")` and passes it as `activity_id` to `save_session()`; `training_log` schema gained `garmin_activity_id TEXT` column via staged migration (version 1: column, version 2: unique index `WHERE garmin_activity_id IS NOT NULL`); `save_session()` uses `INSERT OR IGNORE` on the unique `garmin_activity_id` index preventing duplicate rows on overlapping syncs. Resolution record lost in merge conflict 2026-03-29; restored from implementation evidence. Stage 3 merged PR #572 2026-03-29. NOT NULL constraint is conditional — skipped when NULL rows exist (manual sessions without garmin_activity_id by design). Test: `tests/test_t5_69_activity_deduplication.py`.

---

### T5-72 · H2/H3 gates fail-open on missing HRV/RHR data — EASY ceiling not applied ✅ RESOLVED

**Status:** ✅ RESOLVED — 2026-04-17. Commit: pending push.
H2 and H3 except blocks (TypeError/ValueError on missing HRV/RHR) now apply EASY ceiling
directly to session_plan and signal apply_constraints via context flags
`_h2_data_missing` / `_h3_data_missing`. Lock codes `DATA_MISSING_CONSERVATIVE_H2` and
`DATA_MISSING_CONSERVATIVE_H3` added to CANONICAL_LOCK_CODES in thresholds.py and
_CANONICAL_LOCK_CODES in test_architectural_invariants.py. 2 new tests in
test_governance_mutation.py verify None HRV → EASY ceiling (not fail-open) and
None RHR → EASY ceiling.

**Source:** OBS from governance_engine.py H2/H3 except blocks.
**Severity:** HIGH — ADR-0051: missing safety-critical data must default conservative.
**Location:** `titan/science/governance_engine.py` (H2/H3 except blocks, apply_constraints)
`titan/config/thresholds.py` (CANONICAL_LOCK_CODES)
`tests/test_architectural_invariants.py` (_CANONICAL_LOCK_CODES)

---

### T5-73 · PostgreSQL save_session lacks ON CONFLICT — duplicate garmin_activity_id raises IntegrityError ✅ RESOLVED

**Status:** ✅ RESOLVED — ON CONFLICT (garmin_activity_id) DO NOTHING confirmed present in
PostgreSQLDatabaseManager.save_session() INSERT statement (line 2656). Matches SQLite
INSERT OR IGNORE semantics. Source inspection test added to tests/titan/core/test_database.py
to assert clause presence in perpetuity.

**Source:** OBS from PostgreSQLDatabaseManager schema review.
**Severity:** HIGH — duplicate Garmin re-sync raises IntegrityError without this clause.
**Location:** `titan/core/database.py` (PostgreSQLDatabaseManager.save_session)

---

### T5-70 · AuthStore stores users and tokens in process-local dicts — not wired to SQLite auth tables ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** DEC-035 / OBS-037
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/api/auth.py` (`AuthStore`), `titan/core/database.py` (auth query helpers)
**Description:** `AuthStore.__init__` stores users (`self._users`) and refresh tokens (`self._tokens`) in plain Python dicts. All session state is process-local. On any process restart, all authenticated sessions are invalidated (HTTP 401 for all clients). The `auth_users` and `auth_tokens` SQLite tables exist (created by T5-11 migration `20260316_01`) but are never read or written by production code. ADR-0048 §2.1 mandates server-side storage in `auth_tokens`; the current implementation deviates from the ADR.

**Acceptance criteria (binary):** `AuthStore` CRUD methods read from and write to the `auth_users`/`auth_tokens` SQLite tables via `DatabaseManager`; bcrypt and JWT logic is unchanged; a test verifies that a session persists across `AuthStore` re-instantiation (the key failure mode of the in-memory design).

**Resolution:** AuthStore wired to SQLite via DatabaseManager; bcrypt/JWT logic unchanged; 19 tests green. 2026-04-04.

---

### HD-01 · HRVGuidedEngine lacks baseline drift detection — silent HRV baseline staleness ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md
**Severity:** HIGH
**Location:** `titan/science/hrv_engine.py` (`HRVGuidedEngine`)
**Resolution:** `check_baseline_drift()` added to `HRVGuidedEngine`; emits `hrv_baseline_drift_warning` event when baseline drift exceeds threshold; 8 tests green. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---

### HD-02 · database.py activity timestamp truncation — UTC handling incorrect ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md
**Severity:** HIGH
**Location:** `titan/core/database.py` (lines 1405, 1843)
**Resolution:** UTC fix applied at database.py:1405,1843; tz-aware timestamp handling corrected. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---

### HD-03 · H5/FUELING/INTENSITY gates missing NaN guards — silent governance bypass ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md / ADR-0009
**Severity:** HIGH
**Location:** `titan/science/governance_engine.py` (H5, FUELING, INTENSITY gates)
**Resolution:** NaN guards added to H5, FUELING_GATE, and INTENSITY_GATE_RED/YELLOW paths per ADR-0009; 3 new tests green. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---

### HD-05 · AuthenticatedRateLimiter._requests accumulates keys unboundedly — memory DoS vector ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** DEC-036 / OBS-038
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/api/main.py` (`AuthenticatedRateLimiter`), `titan/config/thresholds.py`
**Description:** `AuthenticatedRateLimiter._requests` is a `defaultdict(deque)` keyed by `(user_id, role, method:path)`. Expired timestamps are pruned within each deque on every request, but dict entries for empty deques are never evicted. An adversary issuing requests across many unique paths or rotating through user accounts inflates the dict without bound. At scale this is a memory DoS vector.

**Acceptance criteria (binary):** `RATE_LIMITER_MAX_KEYS = 10_000` constant added to `titan/config/thresholds.py`; `AuthenticatedRateLimiter` implements LRU eviction when `len(self._requests) >= RATE_LIMITER_MAX_KEYS` (oldest-by-last-request key evicted on new key insertion); tests verify the ceiling is enforced and legitimate state is preserved for active keys.

**Resolution:** `RATE_LIMITER_MAX_KEYS=10000` added to thresholds.py; LRU eviction implemented; `limiter_eviction` WARNING event emitted on eviction; 6 tests green. 2026-04-04.

---

### HD-06 · DegradedModeTracker state not persisted — degradation timers lost on process restart ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** DEC-037 / OBS-039
**Severity:** HIGH
**Location:** `titan/orchestration/daily_coach.py` (`DegradedModeTracker`)
**Resolution:** `DegradedModeTracker` persists to `degraded_mode_state` SQLite table via `_persist_state()`; hydrates timers from DB on startup via `_hydrate_from_db()`; degradation timers survive process restarts; 9 tests green. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---

### HD-08 · PersistenceFailure mixed state: silent no-ops, mixed-epoch H3, unobservable degraded coaching output ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** DEC-038 / OBS-041
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py` (steps 3, 6, payload assembly), `titan/science/governance_engine.py` (context passthrough only)
**Description:** Three bounded observability/coherence gaps under `PersistenceFailure`: (1) `save_hrr()` and `update_glycogen_debt()` silently affect 0 rows when `daily_metrics` has no row for `today_str` after a persistence rollback — no event is emitted; (2) H3 gate consumes mixed-epoch data (`today_rhr` is ephemeral, `baseline_rhr` is DB-derived) with no flag propagated to the governance context; (3) `coaching_data` payload has no `persistence_degraded` bool field, making it impossible for the Telegram message or Operator Console to distinguish a persistence-degraded decision from a normal one. Gate logic must NOT be changed — ADR-0020 intent is preserved.

**Acceptance criteria (binary):** `_daily_coach_event("hrr_persist_skipped")` and `("glycogen_persist_skipped")` are emitted when `persistence_degraded=True` and the respective UPDATE affects 0 rows; `persistence_degraded: bool` is added to the governance context dict and to `coaching_data` payload; the Telegram coaching message annotates the session type when `persistence_degraded=True`; no changes to any gate decision logic.

**Resolution:** `data_confidence_low=True` when `persistence_degraded=True`; silent no-op WARNING events emitted for hrr/glycogen persist skips; `persistence_degraded` field added to governance context and `coaching_data` payload; 8 tests green. 2026-04-04.

---

### HD-09 · No population-specific threshold adaptation — static thresholds regardless of age/fitness tier

**Status:** ✅ RESOLVED — 2026-04-12. ThresholdAdapter implemented in `titan/science/threshold_adapter.py` (MODULE_VERSION 1.0.0); `athlete_threshold_offsets` DB table (schema v12, Alembic migration 20260412_01); `GovernanceEngine.__init__` accepts optional `threshold_adapter` parameter; `GovernanceEngine._get_soft_threshold()` routes soft-gate lookups through adapter; ADR-0052 constants in `thresholds.py`; evidence_registry entries added. Tests: `tests/titan/science/test_threshold_adapter.py` (42 tests). All three gates passed: G1 ruff clean, G2 strict pytest 2482 passed, G3 full pytest 2482 passed.

**ADR-0052 Stage 3 (2026-04-17):** ThresholdAdapter wired into `coaching_pipeline()`. Instantiated per-athlete, per-run. `load()` called at pipeline entry. `GovernanceEngine` constructed with `threshold_adapter=` argument and injected into `DailyCoach._decision_pipeline()` via `governance_engine=` kwarg; `_decision_pipeline()` uses injected engine for step 9 (`apply_constraints`) and step 12 (`get_governance_report`), falling back to `self.governance` when `None`. Cold-start bypass enforced: adapter skipped entirely during cold-start per ADR-0033 L3-C. `propose_adaptation()` NOT called (Stage 4 scope). Tests: `tests/titan/orchestration/test_coaching_pipeline_adapter.py` (+5).
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md §1.1 / HD-09
**Severity:** MED
**Failure Class:** Safety Logic
**Location:** `titan/config/thresholds.py`, `titan/science/governance_engine.py`, `titan/science/outcome_tracker.py`
**Description:** TITAN OS applies identical governance thresholds (HRV delta, RHR delta, ACWR safe band, readiness floors) regardless of athlete age, fitness tier, or accumulated training history. Masters athletes (>45) produce systematic false positives; beginners produce systematic false negatives. Static threshold half-life (~10–16 weeks) is too long for elite athlete adaptation. The `OutcomeTracker` already collects `decision→outcome` pairs per athlete but the calibration loop back into threshold constants does not exist.
**Architecture decision:** ADR-0052 — per-athlete additive offset `δT` per threshold; `ThresholdAdapter` module; `GovernanceEngine` optional injection; `athlete_threshold_offsets` DB table; hard-stop gates (H1–H5) excluded from adaptation; circuit breaker at `FALSE_NEG > 20%` over 30 days; damping ±5% per cycle; |δT| ≤ 20% ceiling.

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

**Opus verdict logging rule (forward policy — applies from 2026-03-14 onward):**

Each Opus QA verdict must be logged next to the relevant task entry using this format:

```
[Opus QA] Task: <task-id> — QA PASS | QA FAIL — <one-line rationale>
```

This rule applies to all future verdicts. Historical tasks (T5-35 and earlier) are not retrofitted.

---

All Tier 5 decisions up to T5-16-A have been locked or deferred. T5-16-A resolved 2026-03-15 (stale ceiling 61→62 was the blocker, not functional regression; T4-27-C created). T5-17 through T5-35 are new entries from the Binder1 audit triage (DEC-1 + DEC-2, 2026-03-13). T5-19, T5-24, T5-25, T5-33, T5-34 are blocked pending architect input or brief. See Tracking table for completion dates and PRs.
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
| T4-27-C | ✅ RESOLVED | 2026-03-15 |
| T4-28 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 92555d3) |
| T5-04 | OPEN (deferred — Phase 9+) | — |
| T5-05 | OPEN (deferred — Phase 9+) | — |
| T5-06 | ⚠️ PARTIAL (T5-06-A ✅ RESOLVED 2026-03-15; T5-06-B deferred Phase 9) | 2026-03-15 |
| T1-21 | ✅ RESOLVED | 2026-03-07 |
| T1-22 | ✅ RESOLVED | 2026-03-07 |
| T1-23 | ✅ RESOLVED (independent; Phase 8 entry gate) | 2026-03-07 |
| T2-16 | ✅ RESOLVED | 2026-03-07 |
| T2-17 | ✅ RESOLVED (independent) | 2026-03-07 |
| T5-14 | ✅ RESOLVED 2026-03-16 — ESI framework: constants in `thresholds.py`, ESI context in `DailyCoach`, VO₂ block via `VO2_ELIGIBILITY_GATE`, Telegram surfacing, `test_esi_compensation.py`; merge commit 31f8ef4 (PR #468) | 2026-03-16 |
| T5-15 | DEFERRED (Phase 9 housekeeping — test marker taxonomy) | — |
| T4-30 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-31 | ✅ RESOLVED (IMMEDIATE — AGENTS.md §16.10 active) | 2026-03-07 (commit: eb20bb2) |
| T4-32 | ✅ RESOLVED | 2026-03-07 (commit: dfe8907) |
| T5-07 | ✅ RESOLVED (Layers 1–2) — 2026-03-13 (commit: b6bea2a); Layer 3: ADR ACCEPTED 2026-04-12; L3-A ✅ RESOLVED 2026-04-14; L3-B ✅ RESOLVED 2026-04-17; L3-C OPEN Phase 9; L3-D ⚠️ PARTIAL 2026-04-15 | 2026-03-13 |
| T5-07-L3-A | ✅ RESOLVED 2026-04-14 — athletes table + owner seed + governance_outcomes owner backfill + calibrated_for removal; SCHEMA_VERSION 12→13; 8 new DB tests green | 2026-04-14 |
| T5-07-L3-B | ✅ RESOLVED 2026-04-17 — OutcomeTracker per-athlete query scoping; check_calibration_diversity(); get_calibration_analytics(); G-CI-07 AST gate; INV-04 ENFORCED; 11 new tests green | 2026-04-17 |
| T5-07-L3-D | ⚠️ PARTIAL — coach:Any resolved; CoachCallables Protocol in coaching_pipeline.py; adapter isolation pending T5-07-L3-D re-evaluation post L3-B closure | 2026-04-15 |
| T5-74 | ✅ RESOLVED 2026-04-14 — governance_outcomes.athlete_id confirmed in SQLite schema; explicit 'owner' fallback in both backends; v13 backfill; OBS-045 closed; bundled with T5-07-L3-A | 2026-04-14 |
| T5-08 | ✅ RESOLVED 2026-03-15 (via T5-08-B — ADR-0044 deliverables D1, D2a/b/c, D3, D4, D5, D7, D9 RESOLVED 2026-03-15; D6 was T5-08 pre-existing deliverable, not a T5-08-B implementation deliverable — DEC-015 2026-03-16; T5-08-B D8 closure record) | 2026-03-15 |
| T5-08-B | ✅ RESOLVED 2026-03-15 — D1 DONE (2026-03-08); D2a DONE (2026-03-13, commit: df449e7); D2b DONE (2026-03-13, commit: d7ad4b7); D2c DONE (2026-03-13, commit: f6901b6); D3 DONE (2026-03-13, commit: 6f641eb); D4 DONE (2026-03-13, commit: 4ccf36d); D5 DONE (2026-03-13, commit: ca8db90); D7 DONE (2026-03-15); D9 DONE (2026-03-15); **complete D2 finished**. D6 was a T5-08 pre-existing deliverable — not a T5-08-B implementation deliverable; D6 status not explicitly confirmed in T5-08-B closure record (DEC-015 2026-03-16: D6 functionally verified present in `persistence.py:122` + `database.py:1975`). | D1: 2026-03-08; D2a: 2026-03-13; D2b: 2026-03-13; D2c: 2026-03-13; D3: 2026-03-13; D4: 2026-03-13; D5: 2026-03-13; D7: 2026-03-15; D9: 2026-03-15 |
| T5-09 | ✅ RESOLVED 2026-03-16 — unified `get_athlete_context()` seam with JSON-safe payload + tests | 2026-03-16 |
| T5-10 | OPEN (deferred — Phase 10) | — |
| T5-11 | ✅ RESOLVED 2026-03-15 — JWT (RS256) + HTTP-only cookie auth layer; `auth_users` + `auth_tokens` tables; `get_current_user()` + `require_coach()` dependencies; isolation invariant enforced; Opus QA PASS; commit 3bd7147 | 2026-03-15 |
| T5-12 | OPEN — Pass 1 COMPLETE 2026-03-18; Pass 2 BLOCKED pending ADR acceptance | — |
| T5-13 | ✅ RESOLVED 2026-03-16 — coach audit trail + migration + non-bypassable middleware path | 2026-03-16 |
| T5-16 | ✅ RESOLVED — ADR-0046 accepted; T5-16-A implementation entry created | 2026-03-08 |
| T5-16-A | ⚠️ PARTIALLY RESOLVED 2026-03-15 — ADR-0018 Phase B complete; `coaching_pipeline.py` + `AthleteCoachingContext` + `CoachingScheduler` absent; see T5-16-B | 2026-03-15 |
| T5-16-B | ✅ RESOLVED 2026-03-17 — coaching_pipeline.py + coaching_scheduler.py extracted; DailyCoach delegates; state isolation oracle green; 2008 tests | 2026-03-17 |
| T5-17 | ✅ RESOLVED (Phase 8 — ACWR threshold extraction to thresholds.py; separate PR) | 2026-03-14 |
| T5-18 | ✅ RESOLVED (Phase 8 — Adaptive Memory 1.08 + time windows extraction; scope respected: 1.08 + 24/36/48/72 only; Category B 2.5/2.0/1.5 left inline per T5-19) | 2026-03-14 |
| T5-19 | ✅ CLOSED — NO_ACTION (2026-03-14): 2.5/2.0/1.5 confirmed Category B; remain inline; T5-18 unblocked | 2026-03-14 |
| T5-20 | ✅ RESOLVED | 2026-03-14 |
| T5-21 | ✅ RESOLVED (Phase 8 — Athlete Profile athlete_id uniqueness hardening; test-first) | 2026-03-14 |
| T5-22 | ✅ RESOLVED (Phase 8 — Athlete Profile serialization completeness incl guardrails + CS/D'; test-first) | 2026-03-14 |
| T5-23 | ✅ RESOLVED (Phase 8 — AFI no-HRR range docstring correction; formula unchanged) | 2026-03-14 |
| T5-24 | ✅ RESOLVED (BiomechanicsEngineProtocol in contracts.py; call-site audit complete; brief issued 2026-03-14) | 2026-03-14 (commit: ed1e20a) |
| T5-25 | ✅ RESOLVED 2026-03-15 — `docs/PARITY_MATRIX.md` v1.0 created; 32 methods classified; D7/D9 closure gates defined | 2026-03-15 |
| T5-26 | ✅ RESOLVED | 2026-03-14 |
| T5-27 | ✅ RESOLVED (Phase 8 — Durability Engine Category A threshold extraction to thresholds.py; separate PR scope) | 2026-03-14 |
| T5-28 | ✅ RESOLVED (Phase 8 — Fatigue Engine soreness threshold extraction to thresholds.py; separate PR) | 2026-03-14 |
| T5-29 | ✅ RESOLVED (Phase 8 — Garmin sync sleep/HRV partial-failure policy aligned; test-first) | 2026-03-14 |
| T5-30 | ✅ RESOLVED (Phase 8 — Governance Engine Category A threshold extraction to thresholds.py; separate PR) | 2026-03-14 |
| T5-31 | ✅ RESOLVED | 2026-03-14 |
| T5-32 | ✅ RESOLVED (Phase 8 — Lactate Logic threshold extraction; separate PR) | 2026-03-14 |
| T5-33 | ✅ CLOSED — NO_ACTION | 2026-03-14 |
| T5-34 | ✅ RESOLVED | 2026-03-14 |
| T5-35 | ✅ RESOLVED | 2026-03-14 |
| T5-36 | ✅ RESOLVED (P2 Phase 8B — authenticated per-role/per-user rate limiting implemented) | 2026-03-15 |
| T5-37 | ✅ RESOLVED (P1 — Opus Category A findings → CI gates; ADR-0049 Hybrid Sequential lane completed; Migration UNIT 1/2/3/4 CLOSED; progress 4/4) | 2026-03-15 |
| T5-38 | ✅ RESOLVED (P1 — validating meta-tests for each T5-37 CI gate; paired lane complete; Migration UNIT 1/2/3/4 CLOSED; progress 4/4) | 2026-03-15 |
| T5-39 | ✅ RESOLVED (P3 — Category A: `cs_min_confidence = 0.70` in `adaptive_priority_lock.py` → import `GOVERNANCE_CS_CONFIDENCE_THRESHOLD`; phase overrides remain inline per DEC-020) | 2026-03-17 |
| T5-40 | ✅ RESOLVED (P3 — `TelegramChannel.send()` boolean return consumed and propagated; `False`-without-exception branch has explicit test coverage; all gates green) | 2026-03-17 |
| T5-41 | ✅ RESOLVED (P3 — Category A: dew-point decision band literals in `weather_api.py`:158–170, 529–537 → extract to `thresholds.py` named constants) | 2026-03-17 |
| T5-42 | ✅ RESOLVED (P3 — `NutritionOptimizer` public API test coverage gap: `add_weight_entry()` and `calculate_daily_nutrition()` now have explicit happy-path + boundary tests; all gates green) | 2026-03-17 |
| T5-43 | ✅ RESOLVED 2026-03-17 — withings-sync pinned to 4.1.0 in constraints.txt; all 10 test files collectable; 1999 tests green | 2026-03-17 |
| T5-44 | ✅ RESOLVED 2026-03-28 — TRIMP zone calculation uses athlete HRmax; DailyCoach wiring complete (PRs #547, #548) | 2026-03-28 |
| T5-45 | ✅ RESOLVED 2026-03-27 — `HRVEngine.calculate_baseline` uses sample SD (N-1); ~8% suppression-threshold underestimation eliminated (PR #537) | 2026-03-27 |
| T5-46 | ✅ RESOLVED 2026-03-27 — HRV log deduplicates by timestamp at ingestion; baseline inflation from overlapping syncs eliminated (PR #538) | 2026-03-27 |
| T5-47 | ✅ RESOLVED 2026-03-26 — `EfficiencyEngine` returns `None` for zero/null pace; crash path eliminated (PR #526, commit 52537ed) | 2026-03-26 |
| T5-48 | ✅ RESOLVED 2026-03-28 — Garmin data age propagated to governance context and all gate events; timeout path bug fixed (PR #548) | 2026-03-28 |
| T5-49 | ✅ RESOLVED 2026-03-27 — Governance defaults missing sleep/readiness to 40 (conservative); 2-of-4 gate fires correctly on absent data (PR #535) | 2026-03-27 |
| T5-50 | ✅ RESOLVED 2026-03-27 — `sync_activities()` maps Garmin activity type to `session_type`; hardcoded `'EASY'` default eliminated (PR #539) | 2026-03-27 |
| T5-51 | ✅ RESOLVED 2026-03-26 — ACWR propagates `None` on sync failure; governance pipeline no longer sees optimistic sweet-spot (PR #530, commit 5f68fc5) | 2026-03-26 |
| T5-52 | ✅ RESOLVED 2026-03-26 — CS confidence default changed to 0.0; `CS_CONFIDENCE_LOCK` now fires for uncalibrated trackers (PR #529, commit 19f9a1d) | 2026-03-26 |
| T5-53 | ✅ RESOLVED 2026-03-26 — `ReadinessEngine` null-guards HRV diff; skips HRV component gracefully when either value is `None` (PR #527, commit 0d9f852) | 2026-03-26 |
| T5-54 | ✅ RESOLVED 2026-03-27 — drift_pct default changed from 0.0 to None; IntensityGovernor now treats missing drift as unknown not perfect efficiency (PR #541) | 2026-03-27 |
| T5-55 | ✅ RESOLVED 2026-03-27 — `apply_thermal()` now uses ESI formula (temp + 0.5*dew_point) when dew_point available; falls back to dry-bulb when absent (PR #544) | 2026-03-27 |
| T5-56 | ✅ RESOLVED 2026-03-27 — AFI confidence penalised to 0.7 when HRR history has fewer than 3 data points; absent HRR (None) carries no penalty (PR #542) | 2026-03-27 |
| T5-57 | ✅ RESOLVED 2026-03-27 — `should_replan()` predicate added; mid-week re-evaluation triggers on HRV drop >10ms, HARD_STOP event ≤24h, or illness flag (PR #545) | 2026-03-27 |
| T5-58 | ✅ RESOLVED 2026-03-26 — `_apply_hrv_adjustments` uses explicit `is not None` guards; crash path on null HRV eliminated (PR #528, commit d0dbd67) | 2026-03-26 |
| T5-59 | ✅ RESOLVED 2026-03-27 — `NutritionOptimizer` defaults `dew_point` to 25°C (conservative); sweat/electrolyte underestimation eliminated (PR #536) | 2026-03-27 |
| T5-60 | ✅ RESOLVED 2026-03-28 — sleep field mapping fixed; H3 gate restored (PR #552) | 2026-03-28 |
| T5-61 | ✅ RESOLVED 2026-03-28 — multi-day HRV persisted; INSERT OR IGNORE for historical (PR #553) | 2026-03-28 |
| T5-62 | ✅ RESOLVED 2026-03-28 — zero-sync silent failure fixed; stale token + empty sync detection (PR #551) | 2026-03-28 |
| T5-65 | ✅ RESOLVED 2026-03-29 — classify_hrv_stress_context returns UNKNOWN_ACWR for None/absent/unparseable ACWR; confirmed ADR-0051 compliant by architect 2026-03-29 | 2026-03-29 |
| T5-66 | ✅ RESOLVED 2026-03-29 — per-column UPSERT preserves mood/soreness/fatigue/notes on Garmin re-sync; 5 tests green | 2026-03-29 |
| T5-67 | ✅ RESOLVED 2026-04-04 — boolean flag gates success events in all 4 sync methods; 12 tests green | 2026-04-04 |
| HD-07 | ✅ RESOLVED 2026-04-04 — _activity_utc_date() replaces [:10] truncation; fromisoformat()+UTC for tz-aware timestamps; 10 tests green | 2026-04-04 |
| HD-01 | ✅ RESOLVED 2026-04-04 — check_baseline_drift() in HRVGuidedEngine; emits hrv_baseline_drift_warning; 8 tests green | 2026-04-04 |
| HD-02 | ✅ RESOLVED 2026-04-04 — database.py:1405,1843 UTC fix; fromisoformat()+UTC for tz-aware timestamps | 2026-04-04 |
| HD-03 | ✅ RESOLVED 2026-04-04 — H5/FUELING/INTENSITY NaN guards; ADR-0009; 3 new tests green | 2026-04-04 |
| HD-06 | ✅ RESOLVED 2026-04-04 — DegradedModeTracker persists to degraded_mode_state table; hydrates on startup; 9 tests green | 2026-04-04 |
| T5-70 | ✅ RESOLVED 2026-04-04 — AuthStore wired to SQLite via DatabaseManager; bcrypt/JWT unchanged; 19 tests green | 2026-04-04 |
| HD-05 | ✅ RESOLVED 2026-04-04 — RATE_LIMITER_MAX_KEYS=10000; LRU eviction; limiter_eviction WARNING event; 6 tests green | 2026-04-04 |
| HD-08 | ✅ RESOLVED 2026-04-04 — data_confidence_low=True when persistence_degraded; silent no-op WARNING events; 8 tests green | 2026-04-04 |
| T5-68 | ✅ RESOLVED 2026-03-29 — ESI_DEW_POINT_FALLBACK_C=18.0 in thresholds.py+evidence_registry; daily_coach.py:714 uses constant; ADR-0034 annotated; 6 tests green | 2026-03-29 |
| T5-69 | ✅ RESOLVED 2026-03-29 — activityId extracted; garmin_activity_id column + unique index via staged migration; INSERT OR IGNORE deduplication; record restored after merge conflict; Stage 3 merged PR #572 2026-03-29; NOT NULL constraint conditional (NULL rows skipped — manual sessions by design) | 2026-03-29 |
| ADR-0018 Phase B (G9) | ✅ IMPLEMENTED — G9 cleared | 2026-03-08 (commit: c51e217) |
| T2-18 | ✅ RESOLVED | 2026-03-08 |
| T2-19 | ✅ RESOLVED — nominal coherence oracle implemented | 2026-03-08 |
| HD-09 | ✅ RESOLVED 2026-04-12 — ThresholdAdapter MODULE_VERSION 1.0.0; athlete_threshold_offsets schema v12; GovernanceEngine._get_soft_threshold() injection; ADR-0052 constants; 42 tests green | 2026-04-12 |
| T5-75 | ✅ RESOLVED 2026-04-12 — AST structural invariant: single _decision_pipeline call site + gate-method reachability; 2 tests green (commit: 29fcc49) | 2026-04-12 |
| T5-76 | ✅ RESOLVED 2026-04-12 — Concurrent coaching_pipeline() no cross-contamination test; ADR-0046 entry gate satisfied (commit: 29fcc49) | 2026-04-12 |
| T5-77 | ✅ RESOLVED 2026-04-12 — SIGTERM mid-pipeline: 3 tests confirm no orphaned governance trace (commit: 29fcc49) | 2026-04-12 |
| T5-78 | ✅ RESOLVED 2026-04-14 — garminconnect upgraded 0.2.13→0.3.2; withings-sync dep removed; garmin_sync.py loads/dumps call sites updated; 0 collection errors | 2026-04-14 |
| T5-72 | ✅ RESOLVED 2026-04-17 — H2/H3 except: EASY ceiling + DATA_MISSING_CONSERVATIVE_H2/H3 lock codes; 2 tests green | 2026-04-17 |
| T5-73 | ✅ RESOLVED 2026-04-17 — PostgreSQLDatabaseManager.save_session() ON CONFLICT (garmin_activity_id) DO NOTHING confirmed present; source inspection test added | 2026-04-17 |

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

*Updated: 2026-03-14 — Records Steward Update Pass (T5-33 & T5-34 Audit Results). Two records updates applied:*
*(1) T5-33 CLOSED NO_ACTION: audit confirms no direct coupling, no layer violation, no shared mutable state — decoupled coexistence, no brief required.*
*(2) T5-34 OPEN — T5-34-A brief issued: Class 1 (GARMIN key alignment, launcher readiness semantics); Class 2 (Telegram token threshold ≥20, numeric CHAT_ID validation); Class 3 intentional divergence (env paths, OpenAI key, keyring, weather semantics). Next Codex-executable item: T5-34-A.*
*No implementation performed. No new architectural decisions. No renumbering.*

*Updated: 2026-03-15 — Records-only sync pass. T5-34-A implementation RESOLVED 2026-03-14. Weekly Governance Log and Codex Handoff Block D updated to reflect closure of T5-33 (NO_ACTION) and T5-34 (RESOLVED). No task status changes. No implementation performed.*

*Updated: 2026-03-15 — T5-25 Records Pass. T5-25 RESOLVED: `docs/PARITY_MATRIX.md` v1.0 created; 32 PersistenceAdapter methods classified (MUST_MATCH / PERMITTED_DIVERGENCE) across 10 functional areas; D7/D9 closure gates defined in §4. T5-08-B D7 and D9 rows annotated with Change Type: implementation. AGENTS.md updated with §18 Canonical Source Map, §19 Mandatory Change-Type Field, §20 Mini Drift Postmortem Rule. No production code changes. No new architectural decisions. No renumbering.*

*Updated: 2026-03-15 — Records/Governance Update Pass. AGENTS.md updated: §20 Mini Drift Postmortem Rule refined (not required for every corrective pass; triggered by recurrence or canonical-document impact only); §21 Governance Friction Principle added; §22 Friday Governance Review Output Rule added. TECHNICAL_DEBT.md: T5-16-A architect note added (preventive/historical; no new gate; sequencing D7 → D9 → T5-11 unchanged). No task status changes. No production code changes. No new debt items.*

*Updated: 2026-03-15 — ADR-0047 Records Pass (T5-11 / API Authentication Layer). ADR-0048 created (`docs/adr/0048-api-authentication-layer.md`; records-safe correction: ADR-0047 was already assigned to Architecture Fitness Functions — next available number 0048 used). T5-11 status updated: Workflow Path A → Path B (APPROVED), ADR-0048 Accepted 2026-03-15, architect decision summary and acceptance gate added, Codex implementation pass authorized. T5-13 sequencing constraint added: T5-13 depends on T5-11 (coach_id from JWT claim). T5-36 registered: No API rate limiting — DoS risk on Phase 8B endpoints (records-safe correction: architect text referenced T5-26 which is already assigned; next available ID T5-36 used). CLAUDE.md ADR index updated: ADR-0048 entry added. Tracking table updated: T5-11 row and T5-36 new row. No production code changes. No implementation performed.*

*Updated: 2026-03-15 — T5-11 Path B Closure + Opus QA Scope Reduction Records Pass. PART A: T5-11 RESOLVED: implementation commit 3bd7147 merged; Opus QA verdict QA PASS logged in canonical format per PILOT-01 verdict logging rule; T5-11 tracking table row updated to RESOLVED. PART B: ADR-0049 created (`docs/adr/0049-opus-qa-scope-reduction-deterministic-to-ci-migration.md`); AGENTS.md Opus QA scope section updated with Category A / Category B taxonomy and deterministic-to-CI migration policy; T5-37 registered (Category A findings → CI gates; ADR-0049 Accepted 2026-03-15); T5-38 registered (validating meta-tests for T5-37 CI gates; paired execution discipline); CLAUDE.md ADR index updated: ADR-0049 entry added; docs/adr/README.md updated: ADR-0049 row added. No production code changes. No Opus observations from T5-11 verdict converted to new debt items (cookie flags / logout coverage / token-cap trimming observations are not new implementation scope in this pass). No historical renumbering.*

*Updated: 2026-03-16 — DEC-020 records pass (OBS-020 / T5-39 registration). T5-39 registered: `adaptive_priority_lock.py` — replace inline `cs_min_confidence = 0.70` with canonical `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` import (Category A; Workflow Path A; ~30 min; phase overrides remain inline per DEC-020). OBS-020 marked REVIEWED in SCRATCHPAD.md; DEC-020 written. No implementation performed. Architect decision recorded: DEC-020 (response to OBS-020). No renumbering.*

*Updated: 2026-03-16 — DEC-022 records pass (OBS-022 / T5-40 + T5-41 registration). T5-40 registered: `TelegramChannel.send()` boolean-return silent-failure path + branch coverage test (`notification_gateway.py`:75–95, `telegram_bot.py`:444–467; Workflow Path A; P3; ~1–2h). T5-41 registered: dew-point decision band literals in `weather_api.py`:158–170, 529–537 → extract to `thresholds.py` named constants (Category A; Workflow Path A; P3; ~1h). No implementation performed. No new ADR. No renumbering.*

*Updated: 2026-03-16 — DEC-023 records pass (T5-42 registration). T5-42 registered: `NutritionOptimizer` public API test coverage gap — `add_weight_entry()` and `calculate_daily_nutrition()` lack explicit tests in `tests/titan/features/test_nutrition_optimizer.py` (Workflow Path A; P3; ~1–2h; test-only; no production code changes). No implementation performed. No new ADR. No renumbering.*

*Updated: 2026-03-17 — T5-39 + T5-41 closure records pass. T5-39 RESOLVED: `adaptive_priority_lock.py` `cs_min_confidence = 0.70` replaced with canonical `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` import; source-binding test added. T5-41 RESOLVED: dew-point decision band literals in `weather_api.py`:158–170, 529–537 extracted to `thresholds.py` named constants; `evidence_registry.py` provenance entries added. Closure commit: `2f46d59` (PR #489 merge). CLAUDE.md test snapshot updated to 1991 (accepted as correct). Branch prefix anomaly: PR #489 used `codex/*` prefix instead of canonical `claude/*` — recorded as process blemish only, no functional impact. Tracking table rows updated: T5-39 → RESOLVED 2026-03-17; T5-41 → RESOLVED 2026-03-17. Task learning notes added to both entries. No new debt items. No AGENTS.md changes. No re-review of functional content.*

*Updated: 2026-03-17 — T5-40 + T5-42 closure records pass. T5-40 RESOLVED: `TelegramChannel.send()` boolean return consumed and propagated; `False`-without-exception branch has explicit test coverage; all gates green. T5-42 RESOLVED: `add_weight_entry()` and `calculate_daily_nutrition()` now have explicit happy-path + boundary tests; all gates green. Closure commit: `b058ed2` (PR #491 merge). CLAUDE.md test snapshot accepted as 1999 (correct per architect verdict). Process blemishes recorded: PR #491 used `codex/*` branch prefix instead of canonical `claude/*`; PR title was generic (not `T<tier>-<id>: <short title>` format) — both non-functional deviations only. Tracking table rows updated: T5-40 → RESOLVED 2026-03-17; T5-42 → RESOLVED 2026-03-17. Task learning notes added to both entries. No new debt items. No AGENTS.md changes. No implementation changes. Audit batch T5-39–T5-42 fully closed; Phase 8C sequencing may now open.*

*Updated: 2026-03-17 — DEC-016 records pass: Phase 8C opens. SCRATCHPAD.md queue fully cleared: OBS-015 through OBS-024 all REVIEWED; DEC-016 through DEC-024 (excl. DEC-020 already processed 2026-03-16) written in Architect Review Log; SCRATCHPAD STATUS → IDLE. Architect decisions summary: DEC-016 (OBS-016) — Phase 8B closure evidence complete; Phase 8C OPEN; T5-12 Pass 1 authorized as first execution unit; T5-12 Pass 2 blocked until design ADR accepted. DEC-017 (OBS-017) — evidence_registry contract statement records correction authorized (broader provenance scope: thresholds.py + physiological_bounds.py). DEC-018 (OBS-018) — governance test root-level placement is intentional; NO_ACTION. DEC-019 (OBS-019) — T5-06-A module-path records correction authorized (phantom ml_explainability.py → actual ml_safety.py + injury_risk_model.py). DEC-021 (OBS-021) — single-athlete adapter contract is correct for current scope; NO_ACTION; multi-athlete scoping is Phase 9 per ADR-0046. DEC-022 (OBS-022) — already processed 2026-03-16 (T5-40 + T5-41). DEC-023 (OBS-023) — already processed 2026-03-16 (T5-42). DEC-024 (OBS-024) — operator console test root-level placement is enforced by test_phase6_hygiene.py; NO_ACTION. Phase 8C execution sequence added to header sequencing block. No new debt items in this pass. No implementation changes. No AGENTS.md changes.*

---

## Weekly Governance Log

### Template

```
### Friday Review — YYYY-MM-DD
State: healthy | caution | blocked
Learnings: [1–5 bullet points]
Required updates: [specific docs/registries]
Next-week tactic: [1–3 sentences max]
```

### Friday Review — 2026-03-14
State: healthy
Learnings:
- T5-17 through T5-35 Binder1 audit complete; 18 of 19 items resolved/closed; T5-25 remains OPEN (debt-only design artefact — no Codex implementation); T5-33 CLOSED NO_ACTION; T5-34 RESOLVED 2026-03-14
- T5-19 NO_ACTION classification established the Category A / Category B threshold-extraction distinction; this lens is now reusable for future audit passes
- Opus QA Trigger Policy formalised as standalone section in AGENTS.md; forward verdict logging rule established
Required updates: AGENTS.md (Opus QA Trigger Policy added this session); TECHNICAL_DEBT.md (Weekly Governance Log template added)
Next-week tactic: T5-33 and T5-34 are both closed (NO_ACTION and RESOLVED respectively). Codex execution lane continues Governance Contracts S1 hardening; T5-18 is unblocked and may be scheduled in its normal T5-1x position.

### Friday Review — 2026-03-15
State: healthy
Learnings:
- T5-37 / T5-38 CLOSED WITH REQUIRED RECORDS CORRECTION: Architect confirmed ADR-0049 §7 correctly and substantively applied; stale closure hash (251df1c) replaced with canonical current closure commit (cc5ce69)
- Bounded Execution Unit Rule: each migration unit must constitute a self-contained, independently verifiable unit of work with its own CI gate and validating meta-test; no partial-unit closure permitted
- Environment First Rule: environment bootstrap and gate verification must precede any implementation step within a migration unit; gate state is not assumed from prior unit
- No Mixed-Pass Rule: a single pass must not mix migration unit implementation with records correction; records corrections are isolated passes with their own commit and verification trail
Required updates: TECHNICAL_DEBT.md (stale closure hash corrected in T5-37 and T5-38 status entries); ARCHITECTURE.md (ADR-0049 added to ADR table)
Next-week tactic: Records correction complete. Execution lane resumes from current open items in normal T5-sequence order.

### Friday Review — 2026-03-17
State: healthy
Learnings:
- Bounded repository audit program completed across 8 passes with 8 OBS findings (OBS-017 through OBS-024) and 8 corresponding architect decisions (DEC-017 through DEC-024).
- The audit produced 4 new debt items only: T5-39, T5-40, T5-41, T5-42.
- 4 findings closed without new implementation debt: OBS-018, OBS-019 (records only), OBS-021 (annotation check), OBS-024.
- 3 non-debt records corrections were identified during the audit: evidence_registry contract statement, T5-06-A module-path clarification, ADR-0040 annotation verification.
- False alarms: 0.
- Scope drift incidents: 0.
Required updates: Weekly Governance Log entry only for this pass. No new debt registration in this pass.
Next-week tactic: After this records pass, execute the post-audit sequencing already confirmed by architect: (1) threshold-extraction batch first: T5-39 + T5-41; (2) then implementation/test batch: T5-40 + T5-42.

### Friday Review — 2026-03-21
State: healthy
Learnings:
- F1 (:memory: DB bug), F3 (CTL/ATL training_load=0), F4 (Windows skip) fixed in PR #508 (commit 3d5352e)
- CI failures are billing/infrastructure — not code regressions
- Garmin sync returning 0/0/0/0 post-merge: API rate-limit suspected, not a code bug
- Edwards TRIMP now wired: future syncs with HR data will produce non-zero CTL/ATL
Required updates: CLAUDE.md snapshot already updated to 2013 in PR #508
Next-week tactic: Verify CTL/ATL populates after next successful Garmin sync. If still 0, investigate _persist_garmin_data() call path directly.

### Friday Review — 2026-04-17
State: healthy
Learnings:
- ADR-0033 Layer 3 fully complete (L3-A through L3-D, four commits)
- T5-72 / T5-73 resolved; governance FAIL-OPEN gap closed
- scripts/hard_audit.sh created — replaces 14+ manual audit patterns
- setup_env.sh now auto-activates pyenv 3.11
Required updates: TECHNICAL_DEBT.md (this entry)
Next-week tactic: Run hard_audit.sh at session start instead of
manual checks. ADR-0052 Stage 3 (ThresholdAdapter wiring) is next.
Opus governance audit warranted after ADR-0052 Stage 3 closes Phase 9.

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

### Block C — CLOSED (T5-33)

**T5-33 · Periodization/Automated — ✅ CLOSED NO_ACTION | 2026-03-14**

Audit complete. No direct coupling, no layer violation, no shared mutable state. Decoupled coexistence confirmed. No brief required.

---

### Block D — CLOSED (T5-34)

**T5-34 · Setup Wizard — ✅ RESOLVED | 2026-03-14**

T5-34-A implementation complete. Class 1 and Class 2 fixes applied; launcher tests added; mandatory gates passed at closure. No further Codex action required on T5-34.

> **T5-25 has no Codex implementation handoff.** It is a design artefact to be authored by the architect or under direct architect direction. Codex does not implement T5-25.

---

### T5-78 · garminconnect 0.2.13 transitive dep (withings-sync) uninstallable on setuptools≥67 ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-14.
**Source:** Environment bootstrap failure, session 2026-04-14.
**Description:** garminconnect==0.2.13 declared withings-sync>=4.1.0 as
install_requires. withings-sync has no binary wheel and its setup.py
references self.install_layout (removed in setuptools≥67). Uninstallable
on this platform (setuptools==68.1.2). pip aborted mid-install leaving
alembic, bcrypt, fastapi, cffi uninstalled — causing 11 collection errors.
**Resolution:** garminconnect upgraded to 0.3.2 (drops withings-sync dep).
Compatibility audit (Phase A) confirmed all 11 titan/ call sites present.
Breaking change found and fixed: client.garth.loads/dumps() →
client.client.loads/dumps() (garmin_sync.py lines 313, 417; test mocks
updated in tests/test_garmin_sync.py and tests/titan/integrations/test_garmin_sync.py).
Collection errors: 0. Full suite: 2500 tests collected, all green.
**Priority:** RESOLVED — no further action.
**Phase:** Maintenance.
