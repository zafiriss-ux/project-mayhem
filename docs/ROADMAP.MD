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

## Phase 7 — ML Features (PLANNED, Q3–Q4 2026, after Phase 6)
Goal: Machine learning on a stable, calibrated, observable foundation.

1. LSTM load prediction — shadow mode first, then graduated rollout
2. Injury risk model — ensemble (Random Forest + Gradient Boosting), recall > 80%
3. Automated periodization — genetic algorithm, suggest-only → athlete-confirm → auto-apply
4. Kill-switch mandatory for all ML paths before any athlete-facing deployment
5. Each ML recommendation carries an evidence label (STRONG/MODERATE/HEURISTIC)

---

## Phase 8 — Multi-Platform & Social (PLANNED, 2027)
Goal: Expand reach beyond single-athlete CLI to team and mobile contexts.

1. Additional device sync: Strava, Polar, Whoop, COROS — unified adapter interface
2. All new sync sources must provide HRV, RHR, sleep — otherwise read-only
3. Multi-athlete team dashboard (10–50 athletes, coach view, comparative load grid)
4. High-risk alert system: VLG RED for any athlete triggers coach notification
5. Mobile app: React Native (iOS + Android), offline SQLite sync, native notifications

---

## Phase 9 — Autonomous Coaching Intelligence (PLANNED, 2028)
Goal: Close the adaptive loop — the system self-improves from accumulated evidence
across multiple athlete profiles without requiring manual threshold edits.

**Prerequisite**: Phases 5–8 complete; ≥3 athlete profiles with ≥90 paired decisions each.

1. Auto-threshold calibration: MODERATE → STRONG without manual intervention
   when confidence bounds are met; every change recorded in `threshold_changelog` table
2. Rollback gate: revert if calibrated threshold degrades completion_rate or
   increases injury events within a 30-day observation window
3. Athlete DNA profile: athlete-specific learned thresholds replacing population heuristics;
   versioned in DB; previous versions retained for rollback
4. Proactive load modulation: predictive volume reduction before metrics breach safety bands;
   advisory mode first (3+ correct predictions required before auto-apply)
5. Multi-modal biometric ingestion: lab VO2max, lactate curve, HRV4Training exports;
   weighted by provenance (lab > wearable > self-reported)

---

## Core Rule

No feature development without:
1. Written specification
2. ADR entry
3. Clear integration boundary

Detailed scope, calibration parameters, success metrics, and tech stack are in
`FUTURE_UPGRADES.md` at the repository root. The two documents are complementary:
this roadmap governs *process and phase gates*; `FUTURE_UPGRADES.md` governs
*scope and implementation detail*.

---

This roadmap governs TITAN OS evolution.
Last updated: 2026-03-02 (Phase 6 closed)
