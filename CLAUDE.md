# CLAUDE.md — TITAN OS

## Project Overview

**TITAN OS** (v5.8.0) is a closed-loop, longevity-first athletic operating system for runners. It integrates with Garmin Connect to sync training data and wearables, applies science-based algorithms (HRV, TSB/CTL/ATL, ACWR, lactate threshold, drift analysis, autonomic fusion), enforces safety-first governance gates, generates weekly training plans, calculates optimal workout timing based on weather/dew point, optimizes nutrition macros, and delivers coaching via a Telegram bot.

- **Language**: Python 3.11+ (mandatory — uses `tomllib`, UTF-8 mode PEP 686)
- **Database**: SQLite (thread-safe, via `DatabaseManager`)
- **External APIs**: Garmin Connect, Open-Meteo (weather), Telegram Bot API (via `pyTelegramBotAPI`)

---

## Repository Layout

```
project-mayhem/
├── main.py                  # Root launcher (delegates to titan/main.py)
├── system_check.py          # Module health check
├── requirements.txt         # Production + dev dependencies (pinned)
├── pyproject.toml           # pytest + coverage config
├── test_core_modules.py     # Core module tests
├── test_new_modules.py      # Additional module tests
├── test_titan_logic.py      # Science logic tests
├── test_main_smoke.py       # Entry point smoke tests
├── test_menu_system.py      # Menu system tests
├── test_daily_coach_extended.py  # Extended daily coach tests
├── test_error_paths.py      # Error path tests
├── test_logic_pytest.py     # Logic tests (pytest)
├── test_telegram_bot.py     # Telegram integration tests
├── test_property_based.py   # Property-based tests (hypothesis)
├── tests/                   # Integration + hygiene tests (21 files)
│   ├── test_governance_integration.py       # Contract + boundary tests (27 tests)
│   ├── test_p0_safety_gates.py              # P0 hard-stop gate tests (20 tests)
│   ├── test_apl_integration.py              # APL contract + invariant tests (64 tests)
│   ├── test_phase3_hygiene.py               # Phase 3 branch-coverage sweep (27 tests)
│   ├── test_phase4_hygiene.py               # Phase 4 observability sweep (24 tests)
│   ├── test_e2e_regression_suite.py         # Gold-path E2E regression scenarios
│   ├── test_outcome_tracker_persistence.py  # OutcomeTracker DB persistence
│   ├── test_science_engines.py              # Comprehensive science engine tests
│   ├── test_athlete_database_schema_validation.py  # Schema validation
│   ├── test_telegram_calibration_command.py # /calibration Telegram command
│   ├── test_phase4_observability_flows.py   # Structured flow log tests
│   ├── test_phase4_slo_alerts.py            # SLO alert firing tests
│   ├── test_todo_fix_recommendations.py    # P0/P1/P2 gate coverage (boundary tests)
│   ├── test_operator_console_dashboard.py  # Operator Console service payload tests (Phase 6)
│   ├── test_phase6_hygiene.py              # Phase 6 branch-coverage sweep (24 tests)
│   ├── test_automated_periodization.py     # AutomatedPeriodizationEngine contract tests (Phase 7)
│   ├── test_injury_risk_model.py           # InjuryRiskEnsembleModel contract tests (Phase 7)
│   ├── test_load_prediction_shadow.py      # LoadPredictionShadowModel contract tests (Phase 7)
│   ├── test_ml_kill_switch.py              # ML kill-switch env toggle tests (Phase 7)
│   ├── test_phase7_hardening.py            # Phase 7 version + DailyCoach hardening tests
│   └── test_phase7_hygiene.py             # Phase 7 branch-coverage sweep (31 tests)
├── .github/workflows/       # CI pipelines (ci.yml, codeql.yml, secret-scan.yml)
├── docs/
│   ├── adr/                 # Architecture Decision Records (0001–0014)
│   ├── architecture/        # GOVERNANCE_PHILOSOPHY.md, EVALUATION_ORDER.md
│   ├── specs/               # adaptive_priority_lock.md, volume_load_gauge.md,
│   │                        # operator_console_readiness_dashboard.md,
│   │                        # operator_console_session_explorer.md,
│   │                        # operator_console_manual_override_workflow.md,
│   │                        # operator_console_technology_path.md
│   └── training/            # OPERATIONAL_MODEL.md, DECISION_MODEL.md, profiles/
└── titan/                   # Main package (46 modules, excl. __init__/__main__)
    ├── config/              # thresholds.py (safety constants), evidence_registry.py
    ├── core/                # Athlete, Database, Periodization, Equipment
    ├── science/             # 26 modules (engines + governance + ML scaffold)
    ├── features/            # Weekly planner, optimal time, nutrition optimizer
    ├── integrations/        # Garmin, Weather API, Telegram bot
    ├── orchestration/       # DailyCoach v5.8 (12-step morning routine)
    ├── ui/                  # Menu system, setup wizard, OperatorConsole
    └── utils/               # MathCore, constants
```

---

## Development Setup

```bash
# Requires Python 3.11+
python --version

# Install dependencies
pip install -r requirements.txt

# Run the system check
python system_check.py

# Launch via root launcher
python main.py

# Or launch directly (skips launcher validation, requires .env to be configured)
python -m titan
```

### Environment Configuration

The system reads from `~/Documents/TITAN/.env`. Required variables:

```bash
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
WEATHER_API_KEY=unused           # kept for backwards-compat; Open-Meteo requires no key
WEATHER_LOCATION=Athens,GR

# Optional overrides
DATABASE_PATH=titan.db
LOG_LEVEL=INFO
GARMIN_SYNC_INTERVAL_HOURS=6
WEATHER_CACHE_DURATION_HOURS=1
```

---

## Running Tests

```bash
# Run all tests (1122 total, all green as of v5.8.0 Phase 7 close)
pytest

# Run with coverage
pytest --cov=titan --cov-report=term-missing

# Run governance integration tests specifically
pytest tests/test_governance_integration.py -v

# Run with governance coverage threshold (CI requirement)
pytest --cov=titan.science.governance_engine \
       --cov=titan.science.governance_contracts \
       --cov-fail-under=80 -q

# Run APL integration tests
pytest tests/test_apl_integration.py -v

# Run phase hygiene sweeps
pytest tests/test_phase3_hygiene.py tests/test_phase4_hygiene.py tests/test_phase6_hygiene.py tests/test_phase7_hygiene.py -v

# Run specific test files
pytest test_core_modules.py
pytest test_titan_logic.py
pytest tests/test_p0_safety_gates.py
pytest tests/test_science_engines.py
```

Test configuration is in `pyproject.toml`. Tests discover all `test_*.py` files in the root directory and `tests/`.

---

## Architecture Notes

### Layered Architecture (bottom-up)

1. **Config** (`titan/config/`) — `thresholds.py`: single source of truth for all safety threshold constants
2. **Core** (`titan/core/`) — `UniversalAthleteProfile`, `DatabaseManager` (SQLite, thread-safe), `PeriodizationManager`, `EquipmentManager`
3. **Science** (`titan/science/`) — 26 modules:
   - Foundational engines (11): HRV, TSB/CTL/ATL, ACWR, lactate, drift, efficiency, durability, TRIMP, glycogen, fatigue, readiness
   - Autonomic & critical (4): `AutonomicFusionEngine` (AFI), `CriticalSpeedEngine`, `RCPEngine`, `BiomechanicsEngine`
   - Advanced (1): `AdaptiveMemory`
   - Governance infrastructure (6): `GovernanceEngine`, `GovernanceContracts`, `IntensityGovernor`, `VolumeLoadGauge`, `AdaptivePriorityLock`, `OutcomeTracker`
   - ML scaffold — shadow/advisory mode (4): `LoadPredictionShadowModel`, `InjuryRiskEnsembleModel`, `AutomatedPeriodizationEngine`, `MLSafety` (kill-switch)
4. **Governance Layer** (within science/) — 7-gate safety system; must run before every session recommendation; non-bypassable
5. **Integrations** (`titan/integrations/`) — `GarminSync` (6h background thread), `WeatherAPI` (1h cache, 48h forecast), `TitanTelegramBot`
6. **Features** (`titan/features/`) — `WeeklyPlanGenerator`, `OptimalTimeCalculator`, `NutritionOptimizer`
7. **Orchestration** (`titan/orchestration/`) — `DailyCoach` v5.7: 12-step morning routine, hydrates engines from DB on startup

### Key Safety Constants (`titan/config/thresholds.py`)

```python
HARD_STOP_HRV_DELTA       = 15.0   # ms drop (>=) triggering H2 gate
HARD_STOP_RHR_DELTA       = 8.0    # bpm rise (>=) triggering H3 gate
HARD_STOP_TSB_FLOOR       = -50.0  # TSB floor (<=) triggering H4 gate
SUBJECTIVE_FATIGUE_EXTREME = 8     # RPE/10 score (>=) triggering H5 gate
SUBJECTIVE_FATIGUE_2OF4   = 6      # Score for 2-of-4 soft downgrade
VO2_ACWR_MIN              = 0.80
VO2_ACWR_MAX              = 1.30
VO2_READINESS_MIN         = 65.0
VO2_GLYCOGEN_DEBT_MAX     = 7.0
VO2_MIN_DAYS_SINCE_LAST   = 2
```

### Governance Lock Codes (canonical set)

`HARD_STOP_SAFETY_GATES`, `VO2_ELIGIBILITY_GATE`, `FUELING_GATE_LOCK`,
`FUELING_GATE_FLAG`, `READINESS_2OF4_DOWNGRADE`, `INTENSITY_GATE_RED`,
`INTENSITY_GATE_YELLOW`, `PARASYMPATHETIC_GUARD`, `OVERRIDE_LOCKDOWN`,
`CS_CONFIDENCE_LOCK`

### Threading

Three daemon background threads run when the system is live:
- **Garmin Sync** — every 6 hours
- **Weather Update** — every 1 hour
- **Daily Coach / Scheduler** — cron-style (07:00 morning briefing, 20:00 Sunday weekly plan)

All SQLite writes use `threading.Lock` (`check_same_thread=False`).

### Database

Five SQLite tables: `daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, `governance_outcomes`.
- `governance_outcomes` — created by `OutcomeTracker` (v5.7.1); stores paired governance decisions + post-session outcomes for threshold calibration.
Canonical column name for temperature: `temperature_c`.
`get_training_load_history()` is used to rebuild CTL/ATL on startup.

### Key Architectural Decisions

See `docs/adr/` for Architecture Decision Records:
- `0001` — Fix typo in optimal time module reference
- `0002` — Fix weather window duration bug
- `0003` — Align docs with current module layout
- `0004` — Improve tests for weather window edge cases
- `0005` — Fix runtime startup issues
- `0006` — Architectural hardening: cold start and engine sync
- `0007` — Intensity governance architecture audit (read-only assessment)
- `0008` — Adaptive Priority Lock and VLG specs (VLG: implemented; APL: implemented — v5.7.1)
- `0009` — Safety gate hardening: C1 & C2 resolution (OR semantics + gate reorder — v5.7.4)
- `0010` — Operator Console: Readiness Dashboard MVP payload (Implemented — v5.8.0)
- `0011` — Operator Console: Session Explorer payload + manual annotation (Implemented — v5.8.0)
- `0012` — Operator Console: Manual Override Workflow (Accepted — v5.8.0)
- `0013` — Operator Console: Technology path — Streamlit → React + FastAPI (Accepted — v5.8.0)
- `0014` — Phase 7 ML scaffold: shadow/advisory mode, kill-switch, evidence labels (Implemented — v5.8.0)

---

## Git Workflow

- **Never push directly to `main`**
- Work on feature branches (prefix: `claude/`)
- Use `git status`, `git log`, `git diff` for inspection
- Use `git push -u origin <branch-name>` for pushes

---

## Key Files for Reference

| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | Full architectural design with diagrams and data flows |
| `CHANGES.md` | Version history and changelog |
| `DEPLOYMENT_GUIDE.md` | Deployment instructions |
| `FUTURE_UPGRADES.md` | Roadmap (ML, Streamlit dashboard, mobile app) |
| `docs/ROADMAP.MD` | Development workflow roadmap (Phase 0–9); Phases 0–7 CLOSED |
| `docs/training/DECISION_MODEL.md` | Authoritative 7-gate decision pipeline |
| `docs/training/OPERATIONAL_MODEL.md` | Generic endurance framework (profile-agnostic) |
| `docs/specs/adaptive_priority_lock.md` | APL spec (implemented; v5.7.1) |
| `docs/specs/volume_load_gauge.md` | VLG spec (implemented) |
| `CORE_MIGRATION_SUMMARY.md` | v50 → v51 migration notes |
| `titan/config/thresholds.py` | Safety threshold constants (single source of truth) |
| `titan/config/evidence_registry.py` | Parameter provenance for all thresholds (STRONG/MODERATE/HEURISTIC) |
| `titan/science/adaptive_priority_lock.py` | APL: phase × load matrix → priority vector + lock thresholds |
| `titan/science/outcome_tracker.py` | Decision→outcome correlation; calibration analytics; `governance_outcomes` DB |
| `titan/ui/operator_console.py` | `OperatorConsoleService`: dashboard, session explorer, override workflow, calibration review (v5.8.0) |
| `titan/utils/constants.py` | `SESSION_TYPES`, `DEFAULT_CONFIG` (note: `ACWR_SAFE_MIN/MAX` are dead — use `thresholds.py`) |
| `titan/science/ml_safety.py` | ML kill-switch (`TITAN_ML_KILL_SWITCH` env); enforced by all Phase 7 engines |
| `titan/science/load_prediction_shadow.py` | LSTM shadow load predictor (shadow mode only; kill-switch enforced) |
| `titan/science/injury_risk_model.py` | Ensemble injury risk model (advisory; recall > 80% target; kill-switch enforced) |
| `titan/science/automated_periodization.py` | Genetic-algorithm periodization suggester (suggest-only; kill-switch enforced) |
| `TECHNICAL_DEBT.md` | Tiered technical debt register + upgrade roadmap (all findings, prioritized) |
| `titan/utils/math_core.py` | `MathCore`: pace conversion, `weight_function_Wf`, `system_status_SSV` |
