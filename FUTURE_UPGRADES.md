# TITAN OS — Upcoming Upgrades

## Priority Order (as of 2026-03-02)

> Based on current repo state: mature core + 650+ tests + full governance layer.
> APL, VLG, OutcomeTracker, and EvidenceRegistry are now implemented.
> Updated priorities reflect what remains before science-tuning is legitimate.

---

## IMMEDIATE — Next Cycle

### 0) Security Hardening

Security audit (2026-03-02) identified the following issues, in fix-priority order:

**[SEC-1] — CRITICAL: Unsafe env var type conversion** (`titan/main.py:317–321`)
Direct `int()`/`float()` conversion of env vars without try/except. An invalid
value (e.g. `ATHLETE_AGE=abc`) crashes the process at startup.
- Wrap conversions in try/except with descriptive error message and safe exit.

**[SEC-2] — CRITICAL: Weak input validation in setup wizard** (`titan/ui/setup_wizard.py:71–86`)
No format validation on Garmin email, API keys, or location string. Chat ID stored
as string but used as int (silent coercion).
- Validate email format (regex), enforce numeric Chat ID at collection time,
  add minimum-length checks for API keys.

**[SEC-3] — HIGH: `os.system()` for terminal clear** (`titan/ui/menu_system.py:18`)
Anti-pattern: spawns a shell subprocess. Safe to replace with `subprocess.run()`
or `os.system` avoided entirely via ANSI escape codes.
- Replace with `print("\033[2J\033[H", end="")` or `subprocess.run(["clear"])`.

**[SEC-4] — HIGH: Unpinned dependencies** (`requirements.txt:20,34,36`)
`scikit-learn>=1.4,<1.5`, `pytest>=8,<9`, `hypothesis>=6.100` use version ranges.
Different environments may resolve to incompatible minor versions.
- Pin to exact versions: `pytest==8.1.0`, `hypothesis==6.100.0`, `scikit-learn==1.4.2`.

**[SEC-5] — HIGH: Plaintext credential storage** (`garmin_sync.py:21–22`, `telegram_bot.py:31–32`)
Garmin and Telegram credentials held in plaintext object attributes.
Memory dump or exception trace could expose them.
- Move to `keyring` or `SecretStr` wrapper; never store raw credentials in instance vars.

**[SEC-6] — MEDIUM: No explicit SSL verify flag** (`integrations/weather_api.py:117–147`)
`requests.get()` calls rely on the default `verify=True`. Implicit reliance on
defaults is fragile across library versions.
- Add `verify=True` explicitly to all `requests` calls.

**[SEC-7] — MEDIUM: No JSON schema validation on profile load** (`core/database.py:855`)
`json.load()` + `from_dict()` with no schema guard. Malformed backup files cause
`KeyError`/`TypeError` at runtime.
- Add a lightweight schema check (field presence + type) before `from_dict()`.

**[SEC-8] — MEDIUM: Exception details leaked in Garmin error message** (`garmin_sync.py:44–54`)
`f"(Detail: {e})"` in user-facing print may expose OAuth token fragments or paths.
- Log detail at DEBUG level only; show a generic message to the user.

**[SEC-9] — LOW: `.env` file permissions not verified on Windows** (`setup_wizard.py:101`)
`Path.chmod(0o600)` is a no-op on Windows — the file stays world-readable.
- Document the limitation; add a platform check and warn the user on Windows.

---

### 1) E2E Regression Suite
**Why**: Unit and integration tests are strong (650+ tests), but full user
journey coverage is missing. Without gold-path E2E tests, each release carries
unknown risk that inter-module wiring regressed.

**Scope**:
- 3–5 gold-path scenarios: new athlete onboarding, weekly plan generation, recovery adaptation
- Snapshot tests for decision stability (same inputs → same output, every run)
- Smoke checks after each release (smoke = import + instantiate + run 1 step)

### 2) Observability — Remaining Flows
**Why**: Governance gates now emit structured JSON with `cause` tags.
The remaining high-value flows (planner, readiness, nutrition) still use
unstructured logging. Silent failures in these paths are invisible.

**Scope**:
- Structured decision events for `WeeklyPlanGenerator` (why was this session chosen?)
- Structured events for `ReadinessEngine` (which component drove the score?)
- Structured events for `NutritionOptimizer` (why RED-S warning? which metric?)
- SLO alerts: no Telegram delivery, Garmin sync timeout, nutrition plan missing

### 3) Outcome Tracker — DB persistence
**Why**: `OutcomeTracker` is implemented in-memory. Calibration analytics
require a DB-backed accumulation cycle across multiple restarts.

**Scope**:
- `governance_outcomes` table in SQLite (schema: GovernanceDecision fields)
- Restore tracker state on DailyCoach startup from DB
- `/calibration` Telegram command: show lock_rate_by_phase, completion_rate
- Minimum 30 paired decisions before calibration recommendations surface

---

## COMPLETED (this cycle)

| # | Item | Status | Where |
|---|------|--------|-------|
| — | Adaptive Priority Lock (APL) | DONE | `titan/science/adaptive_priority_lock.py` |
| — | VolumeLoadGauge (VLG) | DONE | `titan/science/volume_load_gauge.py` |
| — | Outcome Tracker | DONE | `titan/science/outcome_tracker.py` |
| — | Evidence Registry | DONE | `titan/config/evidence_registry.py` |
| — | Structured observability (governance gates) | DONE | `_gate_event()` + `cause` tagging |
| — | APL context injection in GovernanceEngine | DONE | `lock_thresholds` + `priority_vector` in context |
| — | GovernanceContracts (vo2_eligibility shape guard) | DONE | `governance_contracts.py` |
| — | CI pipeline (3-job: test + determinism + env-policy) | DONE | `.github/workflows/ci.yml` |
| — | P0 safety gate tests | DONE | `tests/test_p0_safety_gates.py` (14 tests) |
| — | Governance integration tests | DONE | `tests/test_governance_integration.py` (27 tests) |
| — | APL integration tests | DONE | `tests/test_apl_integration.py` (64 tests) |

---

## Phase 5 — Science Calibration (after ≥30 outcomes in OutcomeTracker)

**Why after outcome accumulation**: Thresholds are currently policy heuristics.
Science-tuning before correlated outcome data exists would be noise, not signal.

### Calibration priorities (from EvidenceRegistry):

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
Level 0  Gates exist but not wired              [PAST]
Level 1  Gates wired, contracts on key boundary  [v5.7.0 ✓]
Level 2  APL: phase-aware gate ordering          [v5.7.1 ✓ THIS CYCLE]
Level 3  Outcome tracking + cause classification [v5.7.1 ✓ THIS CYCLE]
Level 4  Parameter provenance for all thresholds [v5.7.1 ✓ THIS CYCLE]
Level 5  DB-persisted outcomes + lock rates      [NEXT]
Level 6  Science calibration (≥30 outcomes)      [Phase 5]
Level 7  ML layer on calibrated foundation       [Phase 7]
```

### Success Metrics

**Next Cycle (Security + E2E + Observability)**
- All SEC-1–SEC-5 fixes merged and CI-green
- E2E gold paths pass on every PR merge
- No unstructured log lines in any governance or orchestration path

**Web UI**
- Dashboard load time < 2s
- Manual override workflow usable without CLI

**ML**
- LSTM accuracy > 85% on holdout set
- Injury recall > 80%
- All ML paths have kill-switch

---

**TITAN OS** — Longevity-first, safety-first, transparency-first.
