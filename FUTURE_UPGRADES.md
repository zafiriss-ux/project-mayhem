# TITAN OS — Upcoming Upgrades

## Priority Order (as of 2026-03-01)

> Based on current repo state: mature core + 600+ tests + governance layer in place.
> Items 1–5 from the previous list are substantially completed. Updated priorities below.

---

## IMMEDIATE — Next Cycle

### 1) Adaptive Priority Lock (`adaptive_priority_lock.py`) — NEXT
**Why first**: The VLG is implemented and the spec is written. APL is the last missing piece
of the governance infrastructure before the layer is fully sealed.

**Scope**:
- Implement per `docs/specs/adaptive_priority_lock.md`
- Pure resolver: VLGState + GovernanceEngine output → final session intent
- No gate logic modification
- Unit tests + integration with GovernanceEngine
- ADR entry for any deviations from spec

### 2) E2E Regression Suite
**Why second**: Unit and integration tests are strong, but full user journey coverage is missing.

**Scope**:
- 3–5 gold-path scenarios: new athlete onboarding, weekly plan generation, recovery adaptation
- Snapshot tests for decision stability (same inputs → same output every time)
- Smoke checks after each release

### 3) Observability — Remaining Flows
**Why third**: Governance gates now emit structured JSON. The remaining flows (planner,
scoring, Telegram handlers) still use unstructured logging.

**Scope**:
- Structured logs for `WeeklyPlanGenerator`, `ReadinessEngine`, `NutritionOptimizer`
- SLO metrics: error rate, response latency, fallback frequency
- Alert rules for silent failures (no Telegram delivery, Garmin sync timeout)

---

## COMPLETED (previously listed as immediate)

These items from the previous priority list are now implemented:

| # | Item | Status | Where |
|---|------|--------|-------|
| 1 | Structured observability for governance | DONE | `_gate_event()` in `governance_engine.py` |
| 2 | Runtime / dependency hardening + CI | DONE | `.github/workflows/ci.yml` |
| 4 | Data contract & schema governance | DONE | `governance_contracts.py` + `validate_vo2_eligibility()` |
| 5 | Safety policy gates | DONE | `GovernanceEngine` 7-gate system + `IntensityGovernor` |

---

## Phase 5 — Web UI / Operator Console (Q2–Q3 2026)
**Why before ML**: Visibility and operational control deliver immediate value earlier than
heavy ML investment.

**Scope**:
- Dashboard: readiness score, TSB/CTL/ATL timeline, HRV trend
- Session explorer: log review, manual annotation
- Manual review/approve workflow for critical governance overrides
- Technology: Streamlit (rapid) → React (production)

---

## Phase 6 — ML Features (Q3–Q4 2026)
**Why after Web UI**: ML must land on a foundation of stable observability, contracts, and safety.

### 1. LSTM Load Prediction
- Time-series training load forecasting
- Shadow mode pilot first (no auto-application)
- Model drift monitoring + calibration alerts
- Kill-switch mandatory

### 2. Injury Risk Scoring
- Ensemble model (Random Forest + Gradient Boosting)
- 15+ features: ACWR, HRV deviation, sleep trend, soreness, weekly volume change
- Binary: high_risk vs safe; threshold tunable per athlete profile
- Recall target > 80%

### 3. Automated Periodization
- AI-driven macrocycle / mesocycle planning
- Genetic algorithm optimization over periodization principles
- Staged rollout with athlete confirmation gate

---

## Phase 7 — Multi-Platform & Social (2027)

### Additional Device Sync
- Strava, Polar, Whoop, COROS integrations
- Unified adapter interface in `integrations/`

### Multi-Athlete Team Dashboard
- Coach view: 10–50 athletes
- Comparative load/readiness grid
- High-risk alert system

### Mobile App
- React Native (iOS + Android)
- Native notifications replacing Telegram for mobile users
- Offline mode with SQLite sync

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
| CI | GitHub Actions |
| ML (planned) | TensorFlow / scikit-learn |
| Web UI (planned) | Streamlit → React + FastAPI |
| Mobile (planned) | React Native |

---

## Success Metrics

### Governance (current cycle)
- All V1–V5 gate paths contract-valid: ACHIEVED
- Governance coverage ≥ 80%: ENFORCED in CI
- P0 safety gate tests passing: ACHIEVED (14 tests)

### Next Cycle (APL + E2E)
- APL resolves session intent deterministically for all VLGState/GovernanceEngine combinations
- E2E gold paths pass on every PR merge
- No unstructured log lines in any governance or orchestration path

### Web UI
- Dashboard load time < 2s
- Manual override workflow usable without CLI

### ML
- LSTM accuracy > 85% on holdout set
- Injury recall > 80%
- All ML paths have kill-switch

---

**TITAN OS** — Longevity-first, safety-first, transparency-first.
