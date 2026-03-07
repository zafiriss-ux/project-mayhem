# TITAN OS — Roadmap Phase History Archive (Phases 0–7.8)

**Archived:** 2026-03-07 — extracted from ROADMAP.MD for size reduction.
**Purpose:** Historical record of closed phases. Not maintained.

---

# TITAN OS — Development Roadmap

## Philosophy
Stability first. Architecture before features. No uncontrolled iteration.

---

## Phase 0 — Stabilization (CLOSED)
- main branch cleaned and protected
- Docs-only APL/VLG specification created
- Issue tracking enabled

---

## Phase 1 — Product Definition (CLOSED)
Goal: Define TITAN OS official kernel baseline.

- Modular kernel branch promoted to main
- Clean runtime verified
- main branch protection rules locked
- Architecture frozen

---

## Phase 2 — Architectural Rails (CLOSED)
Goal: Prevent future architectural drift.

- ADR discipline enforced (ADRs 0001–0007)
- PR template with scope declaration
- docs-before-code rule established
- Issue templates (Feature / Engine / Refactor)

Deliverable: Controlled development pipeline

---

## Phase 3 — Engine Implementation (CLOSED)
Goal: Introduce governance infrastructure and safety rails safely.

### Completed

- `volume_load_gauge.py` — IMPLEMENTED (pure aggregation: TSB + ACWR + glycogen → VLGState)
- `governance_engine.py` — REWROTE (corrupted V1–V5 gates fixed; thresholds from `config/thresholds.py`)
- `governance_contracts.py` — IMPLEMENTED (output shape + structural invariant validation at governance→orchestration boundary)
- `intensity_governor.py` — IMPLEMENTED (GREEN/YELLOW/RED graduated enforcement + GateResult dataclass)
- Governance integration — IMPLEMENTED (non-bypassable Step 9 in DailyCoach 12-step routine)
- Unit + integration tests — IMPLEMENTED (27 governance integration tests, 14 P0 safety gate tests)
- CI validation — IMPLEMENTED (ci.yml: test matrix, determinism job, env-policy job)
- Security: argv redaction in launcher — IMPLEMENTED
- Specs cherry-picked to main: `docs/specs/adaptive_priority_lock.md`, `docs/specs/volume_load_gauge.md`
- ADR-0008: Adaptive Priority Lock and VLG specs
- Phase 3 hygiene sweep — DONE (2026-03-02): `tests/test_phase3_hygiene.py` (27 tests);
  all five Phase 3 modules at 99% aggregate coverage; `governance_contracts` and
  `adaptive_priority_lock` at 100%; total suite 932 tests, all green.

### Remaining

- None.

---

## Phase 4 — Observability & E2E (CLOSED)
Goal: Production-grade visibility and regression safety.

### Completed

- E2E gold-path scenarios — DONE (`tests/test_e2e_regression_suite.py`)
- Snapshot tests for decision stability — DONE (additional coverage in E2E suite)
- OutcomeTracker DB persistence — DONE (`governance_outcomes` table, `tests/test_outcome_tracker_persistence.py`)
- Structured observability for governance gates — DONE (`_gate_event()` + cause tagging + audit summary)
- Structured logs for remaining flows — DONE (`WeeklyPlanGenerator`, `ReadinessEngine`, `NutritionOptimizer`)
- `/calibration` Telegram command — DONE (lock_rate_by_phase, completion_rate from `governance_outcomes`)
- SLO alerts — DONE (no Telegram delivery, Garmin sync timeout, nutrition plan missing)
- Smoke checks post-release — DONE (import + instantiate + run 1 step, CI-gated via `test_main_smoke.py`)
- Phase 4 hygiene sweep — DONE (2026-03-02): `tests/test_phase4_hygiene.py` (24 tests);
  `outcome_tracker` and `governance_engine` at 100%, `intensity_governor` at 100%;
  total suite 963 tests, all green.

### Remaining

- None.

---

## Phase 5 — Science Calibration (CLOSED)
Goal: Evidence-based threshold tuning on a foundation of real outcome data.

**Prerequisite**: ≥30 paired governance decisions in `governance_outcomes` table.

1. Correlate gate triggers with session outcomes (RPE, completion rate) — DONE (lock/outcome correlation analytics in OutcomeTracker + `/calibration` output)
2. Promote HEURISTIC thresholds to MODERATE where correlation is confirmed — DONE (heuristic promotion candidates now surfaced from lock/outcome correlation analytics)
3. Promote MODERATE thresholds to STRONG where replication across profiles is confirmed — DONE (moderate-promotion candidates now require replicated lock/outcome signal across ≥2 athlete profiles and ≥2 phases)
4. Surface calibration candidates via `/calibration` Telegram command — DONE (Telegram output now includes both HEURISTIC→MODERATE and MODERATE→STRONG candidate sections with trigger lock and sample context)
5. Document every promoted threshold in `EvidenceRegistry` with evidence count and date — DONE (promotion metadata fields now enforced in registry schema and validation tests)

### Remaining

- None.

Priority calibration targets (from `EvidenceRegistry`):
- `VO2_READINESS_MIN` — HEURISTIC
- `HARD_STOP_TSB_FLOOR` — HEURISTIC
- `SUBJECTIVE_FATIGUE_2OF4` — HEURISTIC
- `VO2_GLYCOGEN_DEBT_MAX` — MODERATE
- `HARD_STOP_HRV_DELTA` — MODERATE

---

## Phase 6 — Web UI / Operator Console (CLOSED, 2026-03-02)
Goal: Operational visibility before advanced ML investment.

1. Readiness + load dashboard (TSB/CTL/ATL timeline, HRV trend, VLG color) — DONE (service payload in `titan/ui/operator_console.py`, tested in `tests/test_operator_console_dashboard.py`)
2. Session explorer: log review, manual annotation, governance decision trail — DONE (explorer payload + annotation write path in `titan/ui/operator_console.py`, tested in `tests/test_operator_console_dashboard.py`)
3. Calibration review: lock rates by phase, threshold calibration candidates — DONE (calibration review payload in `titan/ui/operator_console.py`, tested in `tests/test_operator_console_dashboard.py`)
4. Manual override workflow with audit trail — DONE (override workflow payload + write path in `titan/ui/operator_console.py`, tested in `tests/test_operator_console_dashboard.py`)
5. Technology path: Streamlit (rapid prototype) → React + FastAPI (production) — DONE (ADR-0013 + `docs/specs/operator_console_technology_path.md`)

---

## Phase 7 — ML Features (CLOSED, 2026-03-02)
Goal: Machine learning on a stable, calibrated, observable foundation.

1. LSTM load prediction — shadow mode first, then graduated rollout — DONE (2026-03-02: shadow predictor scaffold in `titan/science/load_prediction_shadow.py` with contract tests in `tests/test_load_prediction_shadow.py`)
2. Injury risk model — ensemble (Random Forest + Gradient Boosting), recall > 80% — DONE (2026-03-02: advisory scaffold in `titan/science/injury_risk_model.py` with contract tests in `tests/test_injury_risk_model.py`)
3. Automated periodization — genetic algorithm, suggest-only → athlete-confirm → auto-apply — DONE (2026-03-02: suggest-only scaffold in `titan/science/automated_periodization.py` with contract tests in `tests/test_automated_periodization.py`)
4. Kill-switch mandatory for all ML paths before any athlete-facing deployment — DONE (2026-03-02: shared ML kill-switch enforcement in `titan/science/ml_safety.py`; athlete-facing guards wired in `load_prediction_shadow.py`, `injury_risk_model.py`, and `automated_periodization.py` with coverage in `tests/test_ml_kill_switch.py`)
5. Each ML recommendation carries an evidence label (STRONG/MODERATE/HEURISTIC) — DONE (2026-03-02: `ShadowLoadPrediction` now includes `evidence_label` so all Phase 7 recommendation payloads expose evidence context)
6. Phase 7 hygiene sweep — DONE (2026-03-02): `tests/test_phase7_hygiene.py` (31 tests);
   all four Phase 7 modules at 100% coverage (`load_prediction_shadow`, `injury_risk_model`,
   `automated_periodization`, `ml_safety`); missing branches closed (invalid-alpha guard,
   FLAT trend path, MEDIUM risk band); public-API, evidence-label, mode-string, kill-switch,
   dict-contract, and immutability invariants validated; total suite 1122 tests, all green.

### Remaining

- None.

---

## Phase 7.5 — Hardening Sprint (CLOSED, 2026-03-04)

**Gate:** Must be complete before Phase 8 feature work begins.
All items map 1:1 to `TECHNICAL_DEBT.md` entries. Tier ordering is mandatory (CLAUDE.md Rule E1).

### Tier 1 — Data Integrity (block all else until resolved)

- **T1-06** — Extend `DatabaseManager` write lock to cover reads; add `_closed` flag to `close()` to eliminate `sqlite3.ProgrammingError` race at shutdown.
- **T1-07** — Guard `run_morning_routine_async()` with `is_alive()` check to prevent concurrent DailyCoach routine execution.
- **T1-08** — Replace bare `except Exception: return 50.0` in `_get_baseline_rhr()` with specific exception handling; surface data-integrity incidents as structured events + Telegram alert.
- **T1-09** — Add `degraded: bool` / `data_quality` field to weather payload; gate `OptimalTimeCalculator` and `DailyCoach` output on it; emit `weather_degraded_mode_active` event.

### Tier 2 — Observability

- **T2-09** — Replace residual operational/error `print()` calls in `telegram_bot.py`, `garmin_sync.py`, `weather_api.py`, `daily_coach.py` with structured events (one module at a time, E2 sequence).

### Tier 3 — Concurrency Hygiene

- **T3-06** — Add `is_alive()` check after `join(timeout=5)` in all three background worker stop paths; emit `worker_shutdown_timeout` structured event on non-termination.
- **T3-07** — Guard `scheduled_tasks` list with `threading.Lock` on all append/iterate paths.

### Tier 4 — Maintainability & Test Coverage

- **T4-07** — Eliminate duplicate prompts in `setup_wizard.py`; add input validation per field.
- **T4-08** — Wrap long Garmin sync calls with `ThreadPoolExecutor` + `future.result(timeout=N)` to enable actual cancellation.
- **T4-09** — Emit structured `shutdown_requested` event on `KeyboardInterrupt` in main loop.
- **T4-10** — Replace broad `Any` fields in `titan/orchestration/contracts.py` with concrete types, one contract at a time.
- **T4-11** — Add `--cov-fail-under` ratchet gate in `pyproject.toml` / CI; set threshold to measured baseline at Phase 7.5 close.
- **T4-12** — Add interactive flow tests for `setup_wizard.py` (validation branches, cancellation path, happy path). Depends on T4-07.
- **T4-13** — Create `tests/test_full_lifecycle_stress.py`: start → run → stop across all four workers; assert clean shutdown + no race errors. Depends on T1-06, T1-07.

### Deliverable

All deliverables met (closed 2026-03-04):
- 1417 tests green (0 failures, 0 PytestWarning). Coverage 91.96% (gate: 80%).
- `ruff check .` zero findings (T4-01 resolved).
- `mypy titan/orchestration/contracts.py` zero errors (T4-10 resolved).
- Coverage gate active in CI (T4-11 resolved).
- ADR-0017 observations confirmed resolved (T1-06, T1-07, T3-06, T3-07 all RESOLVED).

### Architecture context

ADR-0017 (`docs/adr/0017-composition-root-and-dailycoach-architecture-audit.md`) documents the
trade-offs of the current composition root and DailyCoach orchestrator patterns. Both patterns are
**accepted as-is** for this phase. The lifecycle supervisor refactor (if warranted) is a Phase 9
concern, contingent on whether T1-06, T1-07, T3-06, T3-07 in isolation are sufficient to eliminate
the operational risks identified in the audit.

---

## Phase 7.6 — ADR-0018 Phase A: Kernel Boundary Surgical Fixes (CLOSED, 2026-03-05)

**Source:** ADR-0018 post-Phase-7.5 audit. Items mapped 1:1 to `TECHNICAL_DEBT.md` T1-10, T1-11, T1-12.

### Tier 1 — Data Integrity

- **T1-10** (ADR-0018-A1) ✅ RESOLVED — The 6 originally scoped write methods of
  `DatabaseManager` (`save_daily_metric`, `save_session`, `save_hrr`, `update_shoe_mileage`,
  `add_shoe`, `save_personal_best`) now enforce lock → `_ensure_open_locked()` → cursor →
  execute → commit. Note: 6 additional governance/science write methods with the same pattern
  were outside the original T1-10 scope — tracked as T1-13 (Phase 7.7).
- **T1-11** (ADR-0018-A2) ✅ RESOLVED — `DailyCoach._routine_thread` is now explicitly
  joined (timeout=30s) in `main.py` `finally` block before `db.close()`, with structured
  `worker_shutdown_timeout` escalation on non-termination.
- **T1-12** (ADR-0018-A3) ✅ RESOLVED — `_persist_garmin_data()` wraps activity loop +
  daily metric write in a single `with self.db.transaction():` block. Atomicity invariant holds.

### Deliverable (closed 2026-03-05)

- T1-10/T1-11/T1-12 resolved as scoped. 1435 tests green (0 failures, 0 PytestWarning).
  Coverage ≥ 92.5%. `ruff check .` zero findings.
- Phase B design (DecisionResult / pipeline split) documented in ADR-0018 — implementation
  deferred.

### Architecture context

ADR-0018 (`docs/adr/0018-kernel-boundary-decision-pipeline-effect-runner-split.md`) documents
the Kernel Boundary pattern. Phase A is surgical only. ADR-0017 composition root and DailyCoach
orchestrator patterns remain unchanged.

---

## Phase 7.7 — Engineering Audit V3 Hardening Sprint (CLOSED, 2026-03-06)

**Gate:** All Tier 1 items (T1-13, T1-14) must be complete before Phase 8 feature work begins.
**Source:** Engineering Audit V3 (2026-03-05). ADR-0019 captures architectural decisions for
all items below.

### Tier 1 — Data Integrity (block all else until resolved)

- **T1-13** — Extend T1-10 cursor-race fix to the 6 governance/science write methods not
  in original T1-10 scope: `update_glycogen_debt`, `log_cs_performance`, `log_override`,
  `save_governance_decision`, `update_governance_outcome`, `annotate_governance_outcome`.
  Identical surgical fix: lock → `_ensure_open_locked()` → cursor.
- **T1-14** — Add Garmin activity idempotency: `garmin_activity_id TEXT` column on
  `training_log` with partial unique index (`WHERE garmin_activity_id IS NOT NULL`). Change
  `save_session()` to `INSERT OR IGNORE`. Update `_persist_garmin_data()` to pass the
  Garmin SDK activity ID. Eliminates duplicate-session data inflation in CTL/ATL/TSB.

### Tier 2 — Observability (may proceed once T1-13 is resolved)

- **T2-09 completion** — Replace remaining operational `print()` calls in `titan/main.py`,
  `titan/integrations/telegram_bot.py`, and `titan/orchestration/daily_coach.py` with
  structured event emitters. `print()` is permitted only in `titan/ui/` (interactive UI paths).
  Execute one module at a time. Add `test_<module>_has_no_print_calls` per module.
- **T2-10** — Add startup hydration confidence gate to `DailyCoach`. Track per-engine
  hydration success in `_startup_hydration_confidence: dict[str, bool]`. Emit
  `startup_hydration_report` event. Pass `data_confidence_low=True` to `GovernanceContext`
  if fewer than 3/5 engines hydrated; governance applies conservative intensity ceiling.
- **T2-11** — Remove coaching content from Telegram fallback log. Replace
  `print(f"📱 [Telegram] {text[:200]}")` with metadata-only `_telegram_event("fallback_send",
  message_length=len(text), bot_available=False)`. Zero content in structured event.

### Tier 3 — Concurrency Hygiene (may proceed once T1-13 is resolved)

- **T3-08** — Extend T3-06 post-join alive escalation to Weather and Telegram workers.
  After each `join(timeout=5)`, add `is_alive()` check + `worker_shutdown_timeout` structured
  event for `_update_thread` (weather) and `_sched_thread`/`_poll_thread` (telegram).

### Acceptance gate (Phase 7.7 close — binary)

```bash
# All must pass simultaneously:
python -m pytest -q -W error::pytest.PytestWarning   # ≥1435 tests, 100% green
ruff check .                                          # zero findings
python -m pytest --cov=titan --cov-fail-under=92     # coverage ≥ 92%

# Idempotency invariant (T1-14):
# Replay same Garmin activity set twice → training_log row count unchanged
# get_ctl_atl_tsb() output identical before and after replay

# Startup confidence (T2-10):
# Cold start (empty DB) → startup_low_confidence event emitted

# Privacy gate (T2-11):
# Telegram fallback path → zero content fields in emitted event
```

### Architecture context

ADR-0019 (`docs/adr/0019-audit-v3-architectural-decisions.md`) captures the architectural
decisions for all Phase 7.7 items, including the Garmin idempotency contract, the startup
confidence gate design, the observability policy boundary (`print()` permitted in `titan/ui/`
only), and the worker shutdown escalation contract extension.

---

## Phase 7.8 — Architecture Risk Review + ADR Backfill (CLOSED, 2026-03-06)

**Source:** Architecture reviews V6–V8 (Risk Matrix items #1–#21). ADRs 0020–0042.

All 25 risk items from the master risk matrix assessed and locked as ADRs.
Key outputs: ADR-0021 (governance evolvability), ADR-0022 (Phase 8 entry gate),
ADR-0023–0042 (physiological bounds, data sanity, staleness, illness partition,
OutcomeTracker guardrails, DataTrustLevel, human override invariant, athlete identity invariant,
model aging, structured log sustainability, ML explainability, feedback loop integrity,
semantic versioning, complexity budget, documentation drift prevention).

T1-18 through T5-07 registered. Independent items opened and tracked.

---

