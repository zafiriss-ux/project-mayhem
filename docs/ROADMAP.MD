# TITAN OS — Development Roadmap

## Philosophy
Stability first. Architecture before features. No uncontrolled iteration.

---

## Phase History (Phases 0–7.8 — All CLOSED)

| Phase | Goal | Closed | Key output |
|-------|------|--------|------------|
| Phase 0 | Stabilization | 2026-02 | main protected, APL/VLG specs |
| Phase 1 | Product Definition | 2026-02 | Modular kernel baseline, architecture frozen |
| Phase 2 | Architectural Rails | 2026-02 | ADR discipline, PR template, docs-before-code |
| Phase 3 | Engine Implementation | 2026-03-02 | GovernanceEngine, VLG, APL, 932 tests |
| Phase 4 | Observability & E2E | 2026-03-02 | OutcomeTracker, /calibration, SLO alerts, 963 tests |
| Phase 5 | Science Calibration | 2026-03-02 | HEURISTIC→MODERATE promotion path, EvidenceRegistry |
| Phase 6 | Operator Console | 2026-03-02 | Dashboard, Session Explorer, Override Workflow, ADR-0013 |
| Phase 7 | ML Features | 2026-03-02 | LSTM shadow, InjuryRisk, AutoPeriodization, kill-switch; 1122 tests |
| Phase 7.5 | Hardening Sprint | 2026-03-04 | T1-06→T4-13; 1417 tests; ruff zero; coverage gate active |
| Phase 7.6 | ADR-0018 Phase A | 2026-03-05 | T1-10/T1-11/T1-12; cursor race + atomicity; 1435 tests |
| Phase 7.7 | Engineering Audit V3 | 2026-03-06 | T1-13/T1-14, T2-09–T2-11, T3-08; 1535 tests |
| Phase 7.8 | Architecture Risk Review | 2026-03-06 | ADR-0020–0042; 25 risk items locked; T1-18→T5-07 registered |
| Phase 7.9 | Tier 1 Safety Hardening | 2026-03-08 | T1-18→T1-23 all RESOLVED; ADR-0022 G1–G11 all cleared; Phase 8 OPEN |

Full detail for Phases 7.5–7.8: see `archive/roadmap_phases_0_7_8.md`.

---

## Phase 7.9 — Tier 1 Safety Hardening (CLOSED, 2026-03-08)

**Gate:** All T1-18 through T1-23 must be RESOLVED before Phase 8 entry gate check.
**Source:** ADR-0022 G1 criterion; TECHNICAL_DEBT.md Tier 1 register.

| Item | Description | Status |
|---|---|---|
| T1-18 | Physiological bounds validation (ADR-0023) | ✅ RESOLVED 2026-03-06 |
| T1-19 | Input data sanity layer — Garmin cross-field validation (ADR-0026) | ✅ RESOLVED 2026-03-07 |
| T1-20 | Garmin staleness gate — silent stale data in DailyCoach (ADR-0030) | ✅ RESOLVED 2026-03-07 |
| T1-21 | H2/H3 illness vs life-stress partition (ADR-0037) | ✅ RESOLVED 2026-03-07 |
| T1-22 | OutcomeTracker feedback-loop guardrails (ADR-0035) | ✅ RESOLVED 2026-03-07 |
| T1-23 | DataTrustLevel unified contract (ADR-0041) | ✅ RESOLVED 2026-03-07 |

**Closed:** 2026-03-08 — all items RESOLVED; ADR-0022 G1–G11 gate cleared; Phase 8 OPEN.

---

## Phase 8 — Multi-Athlete Coach Platform (OPEN, 2026-03-08)

**Opened:** 2026-03-08 — ADR-0022 entry gate G1–G11 all cleared. See TECHNICAL_DEBT.md
line "Phase 8 OPEN — all G1–G11 cleared 2026-03-08" and ADR-0022 for the gate record.

**Product direction:** Coach-managed, multi-athlete deployment (Phase 8 product direction).
**Prerequisite:** ADR-0022 entry gate G1–G11 ALL PASS (binary gate check required). ✅ CLEARED

Phase 8 is sequenced into three sub-phases. No Phase 8B or 8C code may begin
before Phase 8A deliverables pass the ADR-0044 binary gate.

### Phase 8A — Infrastructure (PostgreSQL migration + athlete isolation)

**Gate document:** ADR-0044. No Phase 8B work without 8A binary complete.

- PostgreSQL migration via `PersistenceAdapter` (SQLAlchemy Core) + Alembic
- `athlete_id` foreign key on every table; Row-Level Security policies
- `TITAN_DB_BACKEND=sqlite|postgres` feature flag for dev continuity
- GDPR consent log table
- ADR-0018 Phase B: Effect Runner extracted as stateless function

### Phase 8B — Coach Dashboard

- Readiness grid, risk alerts, session explorer for coach view (10–50 athletes)
- `get_athlete_context(athlete_id, days) → dict` — Phase 8B Seam 2
- `DecisionRationale` persisted to DB as JSON column (Phase 8B Seam 1)
- React + FastAPI backend (ADR-0013); auth layer required first (T5-11 / ADR-0046)

### Phase 8C — Multi-Device Adapters

- Strava, Polar, Whoop, COROS integrations
- DataTrustLevel contract per ADR-0041 (all adapters must comply)
- All new sources must provide HRV, RHR, sleep — otherwise read-only

---

## Phase 9 — Autonomous Coaching Intelligence (OPEN, 2026-04-20)
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

## Tier 5 — Future Optionality (Plan now, implement later)

### T5-01 · SQLite retention / archival strategy (DECIDED)

- **Decision locked in ADR-0015**: TITAN OS is intentionally treated as
  **single-athlete, single-lifetime** until Phase 8 implementation begins.
- **Current policy**: `governance_outcomes` and `training_log` remain append-only;
  no retention pruning is introduced in the current scope.
- **Phase 8 gate**: multi-athlete work cannot begin before a dedicated ADR defines
  data lifecycle policy (rolling retention window, per-athlete vs shared DB
  topology, and archival/export format + restore procedure).


### T5-02 · UI evolution path (PLANNED)

- **Evolution path (ADR-0013)**:
  - Phase A: terminal facelift (retro-HUD startup snapshot, action rail,
    status cards with VLG colour + readiness score)
  - Phase B: Streamlit operator prototype (direct `OperatorConsoleService`
    payload reuse)
  - Phase C: React + FastAPI production implementation
- **Hard constraint**: do not invest in Phase A terminal cosmetics until Tier
  1–2 hardening is complete. UI cosmetics are lower priority than data
  integrity and observability.

### T5-03 · Multi-sport scope decision (DECIDED)

- **Decision locked in ADR-0016**: multi-sport is in scope for Phase 8.
- **Current scope remains running-only**: Garmin ingestion keeps the explicit
  `get_activities_by_date(..., "running")` filter until Phase 8 begins.
- **Phase 8 gate**: before adding non-running ingestion for Garmin / Strava /
  Polar / Whoop / COROS, a unified adapter interface must be documented and
  accepted.

### T5-04 · ML promotion gates (DECIDED)

- **Decision locked in ADR-0014 update**: no Phase 7 ML engine is promoted to
  athlete-facing Stage 1+ without passing explicit gate metrics:
  - `LoadPredictionShadowModel`: ≥30 predictions with RMSE <10% of actual
  - `InjuryRiskEnsembleModel`: recall ≥0.80 and false positive rate <0.30 on holdout
  - `AutomatedPeriodizationEngine`: ≥10 confirmed suggestions with ≥80% adoption
- **Promotion controls are mandatory** for each engine promotion:
  1. ADR evidence update (`HEURISTIC -> MODERATE`)
  2. Deployment docs explicitly set `TITAN_ML_KILL_SWITCH=0`
  3. Operator Console calibration review shows promotion readiness checklist

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
Last updated: 2026-03-08 (Phase 7.9 CLOSED: T1-18–T1-23 all RESOLVED; ADR-0022 G1–G11 all cleared; Phase 8 OPEN 2026-03-08; T5-16 RESOLVED — ADR-0046 accepted, T5-16-A implementation entry created)
