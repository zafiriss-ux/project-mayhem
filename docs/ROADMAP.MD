# TITAN OS — Development Roadmap

## Philosophy
Stability first. Architecture before features. No uncontrolled iteration.

---

## Phase History (Phases 0–8, 11–20 CLOSED; Phases 9, 10, 21 OPEN — see below)

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
| Phase 8 | Multi-Athlete Coach Platform | 2026-04-04 | 8A/8B/8C all CLOSED; athlete isolation (ADR-0033 L3), coaching_pipeline extracted |
| Phase 9 | Autonomous Coaching Intelligence | OPEN 2026-04-20 | ThresholdAdapter (ADR-0052), cold-start protocol, athlete isolation L3 |
| Phase 10 | LLM Coach Query Layer | OPEN (deferred) | Pending Phase 9 corpus gate (≥3 athlete profiles × ≥90 decisions) |
| Phase 11 | Security Hardening Sprint | 2026-04-27 | Auth hardening, Telegram daemon fix (T5-98), Garmin env fix (T5-99) |
| Phase 12 | Testing Infrastructure | 2026-04-27 | mutmut (T5-84), metamorphic tests (T5-87), schemathesis 4.x (T5-94) |
| Phase 13 | Security & Data Integrity | CLOSED 2026-05-08 | FMEA items T5-101–T5-118; Telegram trust fix, ML kill-switch whitelist; 7 P1 items resolved (T5-110, T5-114–T5-119) |
| Phase 14 | Production Hardening | CLOSED 2026-05-09 | C-W12 CI restoration, T5-101 token encryption, T5-100 Garmin fallback, T5-111 audit log, T5-112 CSRF, T5-113 pip-audit pin |
| Phase 15 | Multi-Device & Scale | CLOSED 2026-05-15 | Opus audit (11 findings), JWT startup validation, datetime.now(UTC) migration, auth rate-limit, process supervisor; P15-D22 deferred |
| Phase 16 | Operational Hardening | CLOSED 2026-05-15 | TD-09/13/17/19 (XS) resolved, TD-10 partial, CodeQL #1/#2 resolved; TD-04/06/08/11/12 deferred |
| Phase 17 | Infrastructure & Scale | CLOSED 2026-05-22 | TD-06 Dockerfile, TD-12 runbooks; TD-CTL-01 and TD-NUTRITION-01 registered; TD-04/08/11 carry to Phase 18 |
| Phase 18 | Observability & Debt Clearance | CLOSED 2026-05-23 | TD-CTL-01 ✅, TD-11 ✅, TD-NUTRITION-01 ✅; TD-04/TD-08 deferred Phase 19 |
| Phase 19 | Structured Debt & Scale | CLOSED 2026-05-24 | TD-NEW-15 ✅ load tests, TD-04 ✅ ADR-0058 Phase A; TD-08/TD-NEW-18 DEFERRED Phase 20 |
| Phase 20 | Schema & EffectBus | CLOSED 2026-05-24 | FMEA G12 SATISFIED; hygiene & backup hardening; TD-08/TD-NEW-18/TD-04B deferred Phase 21 |
| Phase 21 | Governance Consolidation | OPEN 2026-05-24 | TD-08 schema extract (XL), TD-04 Phase B EffectBus, TD-NEW-18 alembic CI, pydantic-settings, pytest markers |

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

## Phase 8 — Multi-Athlete Coach Platform (CLOSED, 2026-04-04)

**Opened:** 2026-03-08 — ADR-0022 entry gate G1–G11 all cleared.
**Closed:** 2026-04-04 — Phase 8C (final sub-phase) CLOSED.

**Product direction:** Coach-managed, multi-athlete deployment (Phase 8 product direction).
**Prerequisite:** ADR-0022 entry gate G1–G11 ALL PASS (binary gate check required). ✅ CLEARED

All three sub-phases CLOSED as of 2026-04-04.

### Phase 8A — Infrastructure (PostgreSQL migration + athlete isolation) ✅ CLOSED 2026-04-04

**Gate document:** ADR-0044. No Phase 8B work without 8A binary complete.

- PostgreSQL migration via `PersistenceAdapter` (SQLAlchemy Core) + Alembic
- `athlete_id` foreign key on every table; Row-Level Security policies
- `TITAN_DB_BACKEND=sqlite|postgres` feature flag for dev continuity
- GDPR consent log table
- ADR-0018 Phase B: Effect Runner extracted as stateless function

### Phase 8B — Coach Dashboard ✅ CLOSED 2026-04-04

- Readiness grid, risk alerts, session explorer for coach view (10–50 athletes)
- `get_athlete_context(athlete_id, days) → dict` — Phase 8B Seam 2
- `DecisionRationale` persisted to DB as JSON column (Phase 8B Seam 1)
- React + FastAPI backend (ADR-0013); auth layer required first (T5-11 / ADR-0046)

### Phase 8C — Multi-Device Adapters ✅ CLOSED 2026-04-04

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

## Phase 10 — LLM Coach Query Layer (OPEN, deferred)

**Status:** Deferred — pending Phase 9 multi-athlete corpus gate.
Implement only after Phase 9 closes with sufficient data (corpus ≥ 3 athlete profiles × 90 decisions each).
Kill-switch pattern identical to ML safety (ADR-0014). See `FUTURE_UPGRADES.md` for full scope.

---

## Phase 11 — Security Hardening Sprint (CLOSED, 2026-04-27)

Auth store lockout hardening, Telegram `_poll_thread` daemon fix (T5-98), Garmin env-var
pollution fix (T5-99). FMEA: no unmitigated HIGH/CRITICAL items at close.

---

## Phase 12 — Testing Infrastructure (CLOSED, 2026-04-27)

mutmut 3.5.0 mutation testing targeted at H1–H5 governance gates (T5-84), metamorphic
testing for physiological models (T5-87), schemathesis 4.x API contract tests (T5-94).
FMEA: no unmitigated HIGH items at close.

---

## Phase 13 — Security & Data Integrity (CLOSED, 2026-05-08)

Closed 2026-05-08. `phase_close_audit.sh 13` exit 0; 2699 tests passing, 6 skipped;
SCRATCHPAD STATUS: IDLE. Resolved (7 P1 items): T5-110 (Coach-Athlete RBAC scoping,
ADR-0054), T5-114 (data-void governance rule, all stages), T5-115 (`data_source` column
+ SCHEMA_VERSION 15 + UPSERT guard), T5-116 (`/manual_entry` Telegram command), T5-117
(athlete profile unification, `UniversalAthleteProfile.from_env()`), T5-118 (Garmin
weight sync dual-format fix), T5-119 (in-menu profile editor). Deferred to Phase 14:
T5-101 (.garth_token Fernet encryption, P1 security), T5-100 (Garmin fallback adapters,
blocking gate for second athlete onboarding), T5-111 (audit log persistence, P2),
T5-112 (CSRF protection, P2), C-W12 (CI restoration, highest priority).

---

## Phase 14 — Production Hardening (CLOSED, 2026-05-09)

Closed 2026-05-09. All items resolved: C-W12 (CI restoration), T5-101 (.garth_token
Fernet encryption), T5-100 (Garmin fallback adapters — BiometricRouter + ManualEntryAdapter,
ADR-0055), T5-111 (audit log persistence), T5-112 (CSRF protection), T5-113 (pip-audit
pinned to ==2.10.0), T5-81/T5-82 (test-requirements sync), D2/D5/D10/D17/D18-20/M4
(audit close items). Deferred to Phase 15: Polar/Whoop/COROS adapters, D6
containerization, D13 process decoupling. phase_close_audit.sh 14 exit 0; 2724 tests
green. See `TECHNICAL_DEBT.md` for register.

---

## Phase 15 — Multi-Device & Scale (CLOSED, 2026-05-15)

Entry gate: Phase 14 close audit PASS (2026-05-09); Opus governance audit Phase 14
PASS (2026-05-09, 11 findings). Scope: Opus governance audit (mandatory), Polar/Whoop/COROS
adapters (BiometricSourceAdapter protocol — ADR-0055 ready), D6 Dockerfile + systemd unit,
D13 pipeline decoupling (long-term), real Garmin contract tests (vcrpy cassettes).
FMEA: F15-01 Polar/Whoop API auth change (MED → ADR-0055 protocol), F15-02 Docker
volume mount loss on deploy (LOW → rehearsed restore), F15-03 stale vcrpy cassettes
(MED → monthly refresh gate).
**CLOSED 2026-05-15**: phase_close_audit.sh 15 exit 0; 2764 tests passing, 6 skipped;
P1 items resolved: P15-C2 ✅ P15-C3 ✅ P15-D19 ✅ P15-D20 ✅ P15-D21 ✅ P15-M5 ✅
P15-SEC8 ✅ P15-H3 ✅ P15-OPS1 ✅; P15-D22 deferred to Phase 16.
See `TECHNICAL_DEBT.md` for register.

---

## Phase 16 — Operational Hardening (CLOSED, 2026-05-15)

Entry gate: Phase 15 close audit PASS (2026-05-15). Scope (priority order):
TD-09 coach_audit_log wiring (XS), TD-13 threshold mirrors (XS), TD-17 Telegram
replay protection (S), TD-19 gitleaks allowlist tighten (XS), TD-10 print() migration
(M, partial), TD-06 Dockerfile (M) — deferred.
FMEA: F16-01 coach audit silent (MED → TD-09), F16-02 Telegram replay attack
(HIGH → TD-17), F16-03 print() in prod logs (MED → TD-10).

**CLOSED 2026-05-15**: phase_close_audit.sh 16 exit 0; 2774 tests passing, 6 skipped;
TD-09 ✅ TD-13 ✅ TD-17 ✅ TD-19 ✅ TD-10 ✅ (partial); CodeQL #1/#2 ✅;
TD-04/TD-06/TD-08/TD-11/TD-12/P15-ARCH5 deferred to Phase 17.
See `TECHNICAL_DEBT.md` for register.

---

## Phase 17 — Infrastructure & Scale (CLOSED, 2026-05-22)

Entry gate: Phase 16 close audit PASS (2026-05-15). Scope (priority order):
1. ✅ TD-06: Dockerfile + docker-compose — RESOLVED 2026-05-15
2. ✅ TD-12: Author 3 missing runbooks — RESOLVED 2026-05-15
3. TD-11: OpenTelemetry metrics export — deferred to Phase 18
4. TD-04: DailyCoach split (ADR required) — deferred to Phase 18
5. TD-08: Schema single source of truth — deferred to Phase 18

New debt registered: TD-CTL-01 (TSBEngine root cause unknown), TD-NUTRITION-01 (carb display with low_carb active).

**Closed:** 2026-05-22 — phase close audit PASS.
See `TECHNICAL_DEBT.md` for full register.

---

## Phase 18 — Observability & Debt Clearance (CLOSED, 2026-05-23)

Entry gate: Phase 17 close audit PASS (2026-05-22).
Close gate: phase_close_audit.sh 18 exit 0 (2026-05-23); 2924 tests passing.

Outcomes:
1. TD-CTL-01: ✅ RESOLVED — per-day aggregation fix (PR #719).
2. TD-04: DailyCoach god-orchestrator — DEFERRED Phase 19 (ADR-0058 required).
3. TD-08: Schema single source of truth — DEFERRED Phase 19 (500+ lines scope).
4. TD-11: ✅ RESOLVED — MetricsCollector stdlib JSON sink; 3 instrumentation sites.
5. TD-NUTRITION-01: ✅ RESOLVED — carbs_range ±15% adjusted target (PR #720).

FMEA: F18-01 ✅, F18-02 deferred, F18-03 ✅, F18-04 ✅.
See `TECHNICAL_DEBT.md` for register.

---

## Phase 19 — Structured Debt & Scale (CLOSED, 2026-05-24)

**CLOSED 2026-05-24**: phase_close_audit.sh 19 exit 0; 2942 tests passing, 6 skipped;
TD-NEW-15 RESOLVED (load tests); TD-04/TD-NEW-10 RESOLVED (ADR-0058 Phase A);
TD-08 DEFERRED Phase 20; TD-NEW-18 DEFERRED Phase 20.

Entry gate: Phase 18 close audit PASS (2026-05-23). Scope delivered:
1. TD-04: DailyCoach god-orchestrator split — ADR-0058 Phase A EngineRegistry ✅ RESOLVED.
2. TD-NEW-15: Load/performance tests — scripts/load_test.py, tests/test_td_new_15_load.py ✅ RESOLVED.
3. TD-08 / TD-NEW-13: Schema single source of truth — DEFERRED Phase 20 (XL scope).
4. TD-NEW-18: Alembic CI path — DEFERRED Phase 20 (ADR-0044 resolution track).

FMEA: F19-01 MITIGATED, F19-02 DEFERRED, F19-03 DEFERRED, F19-04 ACCEPTABLE.
See `TECHNICAL_DEBT.md` for full register.

---

## Phase 20 — Schema & EffectBus (CLOSED, 2026-05-24)

Entry gate: Phase 19 close audit PASS (2026-05-24).
**CLOSED 2026-05-24**: phase_close_audit.sh 20 exit 0; 2955 tests passing; FMEA G12 SATISFIED.
Scope items deferred to Phase 21: TD-08, TD-04 Phase B, TD-NEW-18, P15-ARCH5, T5-15.
Hygiene & backup hardening delivered (F20-01–F20-04 all mitigated).

---

## Phase 21 — Governance Consolidation (OPEN, 2026-05-24)

Entry gate: Phase 20 close audit PASS (2026-05-24). Scope (priority order):
1. TD-08: Schema single source of truth — extract CREATE TABLE into titan/core/schema.py (XL).
2. TD-04 Phase B: EffectBus extraction (ADR-0058 Phase B).
3. TD-NEW-18: Alembic CI path — PostgreSQL migration CI gate (ADR-0044 resolution track).
4. P15-ARCH5: pydantic-settings migration.
5. T5-15: Pytest marker taxonomy (unit/integration/governance).

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
Last updated: 2026-05-24 (Phase 20 CLOSED 2026-05-24; Phase 21 OPEN 2026-05-24; Phase 19 CLOSED 2026-05-24; Phase 18 CLOSED 2026-05-23; Phase 17 CLOSED 2026-05-22; Phase 16 CLOSED 2026-05-15; Phase 15 CLOSED 2026-05-15; Phase 8 CLOSED 2026-04-04 — 8A/8B/8C all complete; Phase 9 OPEN 2026-04-20; Phase 11 CLOSED 2026-04-27; Phase 12 CLOSED 2026-04-27; Phase 13 CLOSED 2026-05-08; Phase 14 CLOSED 2026-05-09; Phase 10 deferred pending corpus gate)
