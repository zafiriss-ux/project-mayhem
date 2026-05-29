# TITAN OS — Development Roadmap

## Philosophy
Stability first. Architecture before features. No uncontrolled iteration.

---

## Phase History (Phases 0–8, 11–23 CLOSED; Phases 9, 10, 24 OPEN — see below)

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
| Phase 21 | Governance Consolidation | CLOSED 2026-05-24 | TECHNICAL_DEBT.md archived <1500 LOC; SCRATCHPAD.md archived; TD-08/TD-NEW-18/TD-04B/T5-15 DEFERRED Phase 22 |
| Phase 22 | Schema Extract & Observability | CLOSED 2026-05-25 | FMEA G12 SATISFIED; TD-NEW-18 ✅; TD-BACKUP-VERIFY ✅; TD-08/TD-04B/T5-15B/P15-ARCH5 DEFERRED Phase 23 |
| Phase 23 | Schema & EffectBus Phase B | CLOSED 2026-05-29 | ADR-0058 construction-site violation caught and fixed; TD-08/TD-04B/T5-15B/P15-ARCH5/TD-CI-SELFHOSTED DEFERRED Phase 24 |
| Phase 24 | Schema & EffectBus Phase C | OPEN 2026-05-29 | TD-08 schema extract, TD-04B EffectBus, T5-15B markers, P15-ARCH5 pydantic-settings, TD-CI-SELFHOSTED runner topology |

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

## Phase 21 — Governance Consolidation (CLOSED, 2026-05-24)

Entry gate: Phase 20 close audit PASS (2026-05-24). Scope: documentation archival and governance consolidation.

**CLOSED 2026-05-24**: phase_close_audit.sh 21 exit 0; 2959 tests passing; governance consolidation complete.
TECHNICAL_DEBT.md archived to <1500 LOC; SCRATCHPAD.md archived to 916 LOC.
Scope items deferred to Phase 22: TD-08, TD-04 Phase B, TD-NEW-18, P15-ARCH5, T5-15.

---

## Phase 22 — Schema Extract & Observability (CLOSED, 2026-05-25)

Entry gate: Phase 21 close audit PASS (2026-05-24). Scope (priority order):
1. TD-08: Schema single source of truth — DEFERRED Phase 23.
2. TD-04 Phase B: EffectBus extraction (ADR-0058 Phase B) — DEFERRED Phase 23.
3. TD-NEW-18: Alembic CI path — ✅ RESOLVED 2026-05-24 (chain integrity CI-gated).
4. P15-ARCH5: pydantic-settings migration — DEFERRED Phase 23.
5. T5-15: Pytest marker taxonomy — Phase A ✅; Phase B DEFERRED Phase 23.
6. TD-OBS: Metrics time-series sink — Prometheus endpoint ✅; OTel exporter DEFERRED Phase 23.
7. TD-BACKUP-VERIFY: Backup integrity verification — ✅ RESOLVED 2026-05-25.
8. TD-PYPROJECT-DEPS / TD-UV-LOCK-UNUSED — ✅ RESOLVED 2026-05-25.

**Closed:** 2026-05-25 — phase_close_audit.sh 22 exit 0; 2975 tests passing; FMEA G12 SATISFIED.

---

## Phase 23 — Schema & EffectBus Phase B (CLOSED, 2026-05-29)

Entry gate: Phase 22 close audit PASS (2026-05-25). Scope (priority order):
1. TD-08: Schema single source of truth — extract CREATE TABLE into titan/core/schema.py (XL); requires Opus pre-audit of migration path. DEFERRED Phase 24.
2. TD-04B: EffectBus extraction (ADR-0058 Phase B) — 27-file blast radius, needs ADR amendment. DEFERRED Phase 24.
3. T5-15 Phase B: Retroactive pytest markers (100+ remaining files, mechanical). DEFERRED Phase 24.
4. P15-ARCH5: pydantic-settings migration. DEFERRED Phase 24.
5. TD-CI-SELFHOSTED: Alembic runner topology — pending runner inventory docs. DEFERRED Phase 24.

**CLOSED 2026-05-29**: phase_close_audit.sh 23 exit 0; 2981 tests collected, 2974 passed, 7 skipped; ADR-0058 construction-site violation caught and fixed (worker engine construction routed through EngineRegistry); all governance invariants satisfied.

---

## Phase 24 — Schema & EffectBus Phase C (OPEN, 2026-05-29)

Entry gate: Phase 23 close audit PASS (2026-05-29).

**Architecture north star (Phase 24 → Phase 28):** cohort-level coaching generation
over per-athlete governance calibration, with H1–H5 hard stops as the
technology-invariant constraint surface and TD-04B EffectBus as the real-time
event foundation for any inference regime.

### Phase 24 Blocker-Clear Sequence (prerequisite for XL work)

| ID | Severity | Size | Status | Description |
|----|----------|------|--------|-------------|
| B1 | CRITICAL | M | ✅ DONE | Schema fitness function — `tests/test_schema_equivalence.py`; all 19 tables covered; TD-08 regression net established |
| B2a | HIGH | S | ✅ DONE | `EngineRegistry.from_db` param hygiene — `db`/`athlete_id` TODO-Phase9 markers; misleading docstring corrected |
| B2b | HIGH | S | ✅ DONE | ADR-0058 fitness test — exemptions pinned to exact paths; over-broad `"main"` substring match removed |
| B3 | HIGH | S | ✅ DONE | `_decrypt_token` hardened — structured `TOKEN_DECRYPT_FAIL` event + `ValueError` on decrypt failure; plaintext fallthrough eliminated (T5-101 / ADR-0050) |
| B2c | HIGH | M | IN PROGRESS | DailyCoach engine migration — 7 direct constructions moved to `EngineRegistry.from_db`; DailyCoach becomes pure consumer |

### Phase 24 Primary Scope (post-blocker-clear, priority order)

1. **TD-08** (XL): Schema single source of truth — SQLAlchemy Core declarative descriptor in `titan/core/schema.py`; `create_database()` renders from descriptor; `alembic/env.py` `target_metadata` wired (S1 strategy). Fitness net: `tests/test_schema_equivalence.py` validates every intermediate commit. Requires Opus post-implementation spot-check before Phase 25 entry.
2. **TD-04B** (XL): EffectBus extraction (ADR-0058 Phase B) — 27-file blast radius; requires ADR-0058 amendment; depends on B2c completion. EffectBus is the real-time event bus the Phase 28 inference layer requires for hard-stop enforcement.
3. **S3** (S): Auth observability bounded unit — structured auth-failure events (F5.1), lockout-restart survival test (F5.2), TTL boundary invariant (F5.3), audit-token-decode event (F1.2). Fold into debt-clear window between B2c and TD-08.
4. **S4** (XS): Move `alembic-integrity` CI gate from `runs-on: self-hosted` to `runs-on: ubuntu-latest`. One-line YAML change; fold into any in-flight PR.
5. **T5-15 Phase B** (M): Retroactive pytest markers across 100+ remaining files.
6. **P15-ARCH5** (M): pydantic-settings migration.
7. **TD-CI-SELFHOSTED** (S): Alembic runner topology documentation or runner confirmed.

---

## Phase 25 — Schema Descriptor & EffectBus Implementation (PLANNED)

**Entry gate:** Phase 24 close audit PASS; B2c RESOLVED; TD-08 and TD-04B scoped and
Opus-reviewed.

**Goal:** Execute the two XL items deferred since Phase 18. TD-08 produces the single
schema authority that eliminates the five-authority divergence (F3.1–F3.5). TD-04B
produces the EffectBus event backbone. Both close in the same phase — they are
structurally coupled: EffectBus emits schema-typed events; schema changes must
propagate through the bus.

**Key deliverables:**
1. `titan/core/schema.py` — SQLAlchemy Core declarative descriptor for all 19 tables.
2. `create_database()` renders from descriptor; ladder stays forward-only.
3. `alembic/env.py` `target_metadata` wired — autogenerate drift detection enabled (closes F3.5).
4. `consent_log` reconciled to SQLite ladder (closes F3.4).
5. EffectBus extracted from `DailyCoach`; all side effects dispatched as typed events.
6. CI convergence fitness: fresh render == ladder replay == descriptor projection.

**Constraint:** `tests/test_schema_equivalence.py` (B1) must pass at every
intermediate commit throughout the XL refactor.

---

## Phase 26 — CoachingScheduler Activation & Per-Athlete Isolation (PLANNED)

**Entry gate:** Phase 25 close audit PASS; `EngineRegistry.from_db` wired with real
DB hydration (TODO-Phase9 markers resolved); Phase 9 corpus gate met (≥ 3 athlete
profiles × ≥ 90 paired decisions).

**Goal:** Wire the fully-implemented, fully-tested `CoachingScheduler` (F4.1 —
functional but unwired since Phase 19) as the production multi-athlete runtime,
replacing the single-athlete `run_forever` worker loop. Complete Phase 9 per-athlete
engine isolation by wiring `db` and `athlete_id` into `EngineRegistry.from_db`.

**Key deliverables:**
1. ADR governing CoachingScheduler activation (closes F4.1 governance gap).
2. `EngineRegistry.from_db(db, athlete_id)` performs real DB hydration: TSB load
   history, HRV baseline, CS performances, APL threshold offsets.
3. `CoachingScheduler` registered as primary runtime; `run_forever` retained as
   single-athlete fallback behind a feature flag.
4. Per-athlete engine isolation: each pipeline call receives a freshly hydrated,
   athlete-scoped `EngineRegistry`.
5. Phase 9 auto-threshold calibration: MODERATE → STRONG without manual intervention
   when confidence bounds are met; every change recorded in `threshold_changelog`.

---

## Phase 27 — Cohort Analytics & Population Intelligence (PLANNED)

**Entry gate:** Phase 26 close audit PASS; ≥ 3 athlete profiles active with
per-athlete-isolated `EngineRegistry`; ADR-0052 offset calibration producing
per-athlete threshold deltas in production.

**Goal:** Aggregate per-athlete calibration signal into cohort-level patterns.
The system identifies which threshold adjustments generalise across profiles and
which are individual-specific. This is the foundation for population-level coaching
intelligence without requiring externally labelled training data.

**Key deliverables:**
1. Cohort calibration analytics: cross-athlete threshold delta distributions;
   population heuristics vs. individual outliers classified.
2. `CohortProfile` — aggregated signal surface for evidence promotion:
   HEURISTIC → MODERATE when ≥ 3 athletes independently confirm the same delta.
3. Proactive load modulation: predictive volume reduction before metrics breach
   safety bands; advisory mode first (≥ 3 correct predictions required before
   auto-apply). ADR-0014 promotion controls apply.
4. Multi-modal biometric ingestion: lab VO₂max, lactate curve, HRV4Training exports;
   weighted by provenance (lab > wearable > self-reported).
5. Rollback gate: revert calibrated threshold if `completion_rate` degrades or
   injury events increase within a 30-day observation window.

**Hard constraint:** H1–H5 write guard (ADR-0052) is enforced at the DB layer.
Cohort-level signal cannot loosen hard stops regardless of population consensus.

---

## Phase 28 — Inference Layer & H1–H5 Constraint Enforcement (PLANNED)

**Entry gate:** Phase 27 close audit PASS; `CohortProfile` producing stable population
priors; EffectBus (TD-04B) operational; Phase 10 corpus gate confirmed (≥ 3 profiles
× ≥ 90 paired decisions).

**Goal:** Introduce the LLM Coach Query Layer (Phase 10 scope) and any generation-model
coaching components, with H1–H5 as the hard constraint surface over all inference
outputs. No inference output can override a hard stop; the governance engine is the
final arbiter at every decision point regardless of inference confidence.

**Architecture principle:** static inference saturates at cohort scale; the pivot is
cohort-level generation with per-athlete governance calibration (ADR-0052 offsets)
tuning the constraint surface without loosening it. The EffectBus is the real-time
enforcement channel — every inference-generated effect is validated against the
current governance state before dispatch.

**Strategic option compatibility:**
- S1 (SQLAlchemy descriptor): inference models query typed schema objects; descriptor
  survives model architecture changes. ✅
- S2 (CoachingScheduler): multi-athlete runtime is inference-model-agnostic; scheduler
  dispatches to governance regardless of coaching source. ✅
- S3 (auth telemetry): LLM query endpoints share the same auth surface and telemetry
  pipeline. ✅
- S4 (CI gate): infrastructure change; no inference coupling. ✅

**Key deliverables:**
1. LLM Coach Query Layer with kill-switch identical to ML safety (ADR-0014 pattern).
2. Governance engine as hard constraint over all inference outputs — H1–H5 cannot
   be overridden by any model, prompt, or external signal.
3. Inference audit trail: every LLM-generated recommendation logged with governance
   outcome (followed / overridden / blocked by hard stop).
4. `CohortProfile` deltas surfaced as context to the inference layer; per-athlete
   offsets applied post-generation.
5. Technology-shift gate: Phase 28 entry requires Phase 9 corpus confirmed in
   production and EffectBus operational.

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
Last updated: 2026-05-29 (Phase 24 OPEN 2026-05-29; Phase 23 CLOSED 2026-05-29; Phase 22 CLOSED 2026-05-25; Phase 21 CLOSED 2026-05-24; Phase 20 CLOSED 2026-05-24; Phase 19 CLOSED 2026-05-24; Phase 18 CLOSED 2026-05-23; Phase 17 CLOSED 2026-05-22; Phase 16 CLOSED 2026-05-15; Phase 15 CLOSED 2026-05-15; Phase 8 CLOSED 2026-04-04 — 8A/8B/8C all complete; Phase 9 OPEN 2026-04-20; Phase 11 CLOSED 2026-04-27; Phase 12 CLOSED 2026-04-27; Phase 13 CLOSED 2026-05-08; Phase 14 CLOSED 2026-05-09; Phase 10 deferred pending corpus gate)
