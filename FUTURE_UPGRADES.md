# TITAN OS — Upcoming Upgrades

## Priority Order (as of 2026-03-02)

> Based on current repo state: mature core + 1014 tests + full governance layer.
> APL, VLG, OutcomeTracker (DB-persisted), EvidenceRegistry, and E2E suite are now implemented.
> Updated priorities reflect what remains before science-tuning is legitimate.

---


## Phase 4 — Observability & E2E (CLOSED)

### Completed

| # | Item | Status | Where |
|---|------|--------|-------|
| SEC-1 | Safe env var conversion: `_env_int`/`_env_float` helpers | DONE | `titan/main.py:315–325` |
| SEC-2 | Email format check + Chat ID loop + token format + API key length | DONE | `titan/ui/setup_wizard.py` |
| SEC-3 | `os.system("clear")` → ANSI escape; remove `import os` | DONE | `titan/ui/menu_system.py:16–17` |
| SEC-4 | Pin scikit-learn==1.4.2, pytest==8.3.3, hypothesis==6.112.1 | DONE | `requirements.txt` |
| SEC-5 | `_Secret(str)` wrapper: redacts credentials in repr/tracebacks | DONE | `titan/utils/constants.py` + `garmin_sync.py` + `telegram_bot.py` |
| SEC-6 | `verify=True` + cache geocoding coordinates | DONE | `titan/integrations/weather_api.py` |
| SEC-7 | `_validate_athlete_dict()`: schema guard before `from_dict()` | DONE | `titan/core/database.py:18–30` |
| SEC-8 | Exception Garmin → `_log.debug(exc_info=True)`, stdout clean | DONE | `titan/integrations/garmin_sync.py:45–59` |
| SEC-9 | Windows `.env` permission warning in `_save_env()` | DONE | `titan/ui/setup_wizard.py:108–111` |
| — | `database.py` bare `except: pass` → `_log.warning()` | DONE | `titan/core/database.py` |
| — | Weather fallback: `is_fallback: True` + warning stdout | DONE | `titan/integrations/weather_api.py` |
| — | Adaptive Priority Lock (APL) | DONE | `titan/science/adaptive_priority_lock.py` |
| — | VolumeLoadGauge (VLG) | DONE | `titan/science/volume_load_gauge.py` |
| — | Outcome Tracker (in-memory) | DONE | `titan/science/outcome_tracker.py` |
| — | Outcome Tracker — DB persistence | DONE | `governance_outcomes` table in `titan/core/database.py` |
| — | Evidence Registry | DONE | `titan/config/evidence_registry.py` |
| — | Structured observability (governance gates) | DONE | `_gate_event()` + `cause` tagging |
| — | VO2 gate failure details (structured) | DONE | `titan/science/governance_engine.py` |
| — | Governance audit summary | DONE | `titan/orchestration/daily_coach.py` |
| — | APL context injection in GovernanceEngine | DONE | `lock_thresholds` + `priority_vector` in context |
| — | GovernanceContracts (vo2_eligibility shape guard) | DONE | `governance_contracts.py` |
| — | CI pipeline (3-job: test + determinism + env-policy) | DONE | `.github/workflows/ci.yml` |
| — | P0 safety gate tests | DONE | `tests/test_p0_safety_gates.py` (20 tests) |
| — | Governance integration tests | DONE | `tests/test_governance_integration.py` (27 tests) |
| — | APL integration tests | DONE | `tests/test_apl_integration.py` (64 tests) |
| — | Phase 3 hygiene sweep | DONE | `tests/test_phase3_hygiene.py` (27 tests, 99% Phase 3 coverage) |
| — | E2E gold-path regression suite (onboarding, planning, recovery adaptation) | DONE | `tests/test_e2e_regression_suite.py` |
| — | Snapshot stability coverage | DONE | additional coverage in `test_e2e_regression_suite.py` |
| — | OutcomeTracker persistence integration tests | DONE | `tests/test_outcome_tracker_persistence.py` |
| — | `/calibration` Telegram command with 30-outcome gate + phase lock breakdown | DONE | `titan/main.py` + `titan/integrations/telegram_bot.py` |

| — | Structured flow logs for planner + readiness + nutrition | DONE | `titan/features/weekly_planner.py` + `titan/science/readiness_engine.py` + `titan/features/nutrition_optimizer.py` |
| — | SLO alerts for Telegram delivery, Garmin sync latency, nutrition plan missing | DONE | `titan/integrations/telegram_bot.py` + `titan/integrations/garmin_sync.py` + `titan/orchestration/daily_coach.py` |



---

## Phase 5 — Science Calibration (CLOSED)

All five deliverables completed (lock/outcome correlation analytics, HEURISTIC→MODERATE
promotion surfacing, MODERATE→STRONG cross-profile replication gate, `/calibration`
Telegram output, `EvidenceRegistry` promotion metadata schema enforcement).

### Calibration priorities (from EvidenceRegistry — for Phase 9 tuning):

| Parameter | Current Level | Why Calibrate First |
|-----------|--------------|---------------------|
| `VO2_READINESS_MIN` | HEURISTIC | Internal composite, highest-value calibration candidate |
| `HARD_STOP_TSB_FLOOR` | HEURISTIC | Coaching convention, no injury event correlation yet |
| `SUBJECTIVE_FATIGUE_2OF4` | HEURISTIC | 2-of-4 composite threshold not externally validated |
| `VO2_GLYCOGEN_DEBT_MAX` | MODERATE | Internal model units not externally validated |
| `HARD_STOP_HRV_DELTA` | MODERATE | 15% value is a policy choice within a validated range |

### Evidence promotion path:
1. HEURISTIC → MODERATE: correlate gate triggers with session outcomes (RPE, completion)
2. MODERATE → STRONG: replicated across multiple athlete profiles and phases

---

## Phase 6 — Web UI / Operator Console (Q2–Q3 2026)

**Why before ML**: Visibility and operational control deliver immediate value
earlier than heavy ML investment.

**Scope**:
- Dashboard: readiness score, TSB/CTL/ATL timeline, HRV trend, VLG color
- Session explorer: log review, manual annotation, governance decision trail
- Calibration review: lock rates by phase, threshold calibration candidates
- Manual override workflow with audit trail (currently in DB, not surfaced)
- Technology: Streamlit (rapid) → React + FastAPI (production)

---

## Phase 7 — ML Features (Q3–Q4 2026)

**Why after Web UI**: ML must land on a stable foundation of observability,
contracts, calibrated thresholds, and safety gates.

### 1. LSTM Load Prediction
- Time-series training load forecasting
- Shadow mode pilot first — no auto-application
- Model drift monitoring + calibration alerts
- Kill-switch mandatory before any athlete-facing deployment

### 2. Injury Risk Scoring
- Ensemble model (Random Forest + Gradient Boosting)
- Input features: ACWR, HRV deviation, sleep trend, soreness, weekly volume change
- Binary: high_risk vs safe; threshold tunable per athlete profile
- Recall target > 80%; validated against OutcomeTracker injury events

### 3. Automated Periodization
- AI-driven macrocycle / mesocycle planning
- Genetic algorithm optimization over periodization principles (Lydiard, Daniels, Seiler)
- Staged rollout: suggest-only → athlete-confirm → auto-apply
- Each AI recommendation must carry an evidence label (STRONG/MODERATE/HEURISTIC)

---

## Phase 8 — Multi-Platform & Social (2027)

### Additional Device Sync
- Strava, Polar, Whoop, COROS integrations
- Unified adapter interface in `integrations/`
- All new sources must provide HRV, RHR, sleep — otherwise read-only

### Multi-Athlete Team Dashboard
- Coach view: 10–50 athletes
- Comparative load/readiness grid
- High-risk alert system (VLG RED for any athlete triggers notification)

### Mobile App
- React Native (iOS + Android)
- Native notifications replacing Telegram for mobile users
- Offline mode with SQLite sync

---

## Phase 9 — Autonomous Coaching Intelligence (2028)

**Why after multi-athlete data**: Self-calibration requires a corpus of
outcomes across athlete profiles and phases. Autonomous intelligence without
sufficient evidence base is undefined behaviour.

**Goal**: Close the adaptive loop — the system self-improves from accumulated
evidence without requiring manual threshold edits.

### 1. Auto-Threshold Calibration
- MODERATE → STRONG promotion without manual intervention when confidence
  bounds are met across ≥3 athlete profiles
- Every autonomous threshold change recorded in a DB-backed ADR entry
  (`threshold_changelog` table: old_value, new_value, evidence_count, date)
- Rollback gate: revert if calibrated threshold degrades completion_rate
  or increases injury events within 30-day window

### 2. Athlete DNA Profile
- Replace population-level heuristics with athlete-specific learned thresholds
- Personal HRV baseline, TSB tolerance band, glycogen recovery rate estimated
  from longitudinal OutcomeTracker history (minimum 90 paired decisions)
- DNA profile versioned in DB; previous versions retained for rollback

### 3. Proactive Load Modulation
- Predictive volume reduction before risk metrics breach safety bands
  (ACWR trending toward 1.30, TSB trending toward -50)
- Signal: 7-day slope of CTL/ATL divergence fed into governance pre-check
- Must surface as "advisory" first (3+ correct predictions) before auto-applying

### 4. Multi-Modal Biometric Ingestion
- Lab VO2max test imports (CSV upload via Web UI)
- Lactate curve data to refine `LactateThresholdEngine` model
- HRV4Training export as an alternative HRV source
- All sources weighted by provenance: lab > wearable > self-reported

---

## Technology Stack (Current)

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Database | SQLite (via DatabaseManager) |
| Garmin | garth / garminconnect |
| Weather | OpenWeatherMap API |
| Bot | python-telegram-bot |
| Testing | pytest, hypothesis |
| CI | GitHub Actions (3-job pipeline) |
| ML (planned) | TensorFlow / scikit-learn |
| Web UI (planned) | Streamlit → React + FastAPI |
| Mobile (planned) | React Native |

---

## Governance Maturity Ladder

```
Level 0  Gates exist but not wired                    [PAST]
Level 1  Gates wired, contracts on key boundary       [v5.7.0 ✓]
Level 2  APL: phase-aware gate ordering               [v5.7.1 ✓]
Level 3  Outcome tracking + cause classification      [v5.7.1 ✓]
Level 4  Parameter provenance for all thresholds      [v5.7.1 ✓]
Level 5  DB-persisted outcomes + lock rates           [v5.7.1 ✓]
Level 6  /calibration command + structured flow logs  [Phase 4 ✓]
Level 7  Science calibration (≥30 outcomes)           [Phase 5 ✓]
Level 8  ML layer on calibrated foundation            [Phase 7]
Level 9  Autonomous self-calibration from evidence    [Phase 9]
```

---

## Success Metrics

**Phase 4 Close (Observability)**
- No unstructured log lines in any governance, orchestration, planner, or nutrition path
- `/calibration` Telegram command live and returning lock rate data
- SLO alerts firing on: no Telegram delivery, Garmin sync timeout, nutrition plan missing

**Phase 5 (Science Calibration)**
- ≥30 paired decisions in `governance_outcomes` before any threshold proposal
- At least one HEURISTIC parameter promoted to MODERATE with documented evidence
- Calibration report surfaced via `/calibration` command

**Phase 6 (Web UI)**
- Dashboard load time < 2s
- Manual override workflow usable without CLI
- Governance decision trail queryable via session explorer

**Phase 7 (ML)**
- LSTM accuracy > 85% on holdout set
- Injury recall > 80%
- All ML paths have kill-switch and shadow mode entry

**Phase 9 (Autonomous Intelligence)**
- Auto-calibration only activates after ≥3 corroborating athlete profiles
- Zero undocumented autonomous threshold changes (audit trail 100% coverage)
- Rollback triggered and verified at least once in staging before production

---

**TITAN OS** — Longevity-first, safety-first, transparency-first.
