# TITAN OS v5.8 — Modular Architecture

## Vision

TITAN OS is a closed-loop, longevity-first athletic operating system for runners. It integrates with Garmin Connect, applies science-based algorithms, generates training plans, and delivers coaching via Telegram — with a non-bypassable governance layer that enforces safety before every session recommendation.

- **Live Garmin Integration** — real-time sync of activities, weight, sleep, HRV
- **Science Engines** — 26 modules: HRV, TSB/CTL/ATL, ACWR, lactate, drift, AFI, VLG, governance, ML scaffold, and more
- **Governance Layer** — 10 modules (6 governance + 4 ML scaffold) enforcing safety gates, hard stops, output contracts, and kill-switch enforcement
- **Intelligent Weekly Planning** — lactate threshold + drift analysis + HRV-guided scheduling
- **Optimal Time Calculator** — dew point, temperature, circadian rhythm analysis
- **Smart Nutrition** — weight-velocity, periodization phase, and load-adjusted macros
- **Telegram Bot** — automated coaching notifications and on-demand commands
- **Multi-threading** — background sync, weather updates, daily coaching

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                   TELEGRAM BOT INTERFACE                     │
│            (daily coaching · weekly plans · alerts)          │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    ORCHESTRATION LAYER                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  DailyCoach v5.8  (12-step morning routine + scheduler) │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    GOVERNANCE LAYER          ← v5.7–v5.8      │
│  ┌──────────────────┐  ┌──────────────────────────────────┐  │
│  │ GovernanceEngine │  │     IntensityGovernor            │  │
│  │  (7 safety gates)│  │  (GREEN / YELLOW / RED)          │  │
│  └──────────────────┘  └──────────────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────────────────────┐  │
│  │ VolumeLoadGauge  │  │    GovernanceContracts           │  │
│  │ (TSB+ACWR+glycog)│  │  (output shape validation)       │  │
│  └──────────────────┘  └──────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                      FEATURE MODULES                          │
│  ┌──────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Weekly Planner  │  │  Nutrition   │  │ Optimal Time   │  │
│  │    Generator     │  │  Optimizer   │  │  Calculator    │  │
│  └──────────────────┘  └──────────────┘  └────────────────┘  │
└───────────────┬─────────────────────────────┬────────────────┘
                │                             │
┌───────────────▼─────────────────────────────▼────────────────┐
│                      SCIENCE ENGINES (26)                     │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │
│  │    HRV    │ │    TSB    │ │   ACWR    │ │   Lactate   │  │
│  │  Engine   │ │  Engine   │ │  Engine   │ │   Logic     │  │
│  └───────────┘ └───────────┘ └───────────┘ └─────────────┘  │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │
│  │   Drift   │ │Efficiency │ │Durability │ │    TRIMP    │  │
│  │  Engine   │ │  Engine   │ │  Engine   │ │   Engine    │  │
│  └───────────┘ └───────────┘ └───────────┘ └─────────────┘  │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │
│  │ Readiness │ │ Glycogen  │ │  Fatigue  │ │  Adaptive   │  │
│  │  Engine   │ │   Model   │ │  Engine   │ │   Memory    │  │
│  └───────────┘ └───────────┘ └───────────┘ └─────────────┘  │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │
│  │ Autonomic │ │ Critical  │ │    RCP    │ │Biomechanics │  │
│  │  Fusion   │ │   Speed   │ │  Engine   │ │   Engine    │  │
│  └───────────┘ └───────────┘ └───────────┘ └─────────────┘  │
└───────────────┬─────────────────────────────┬────────────────┘
                │                             │
┌───────────────▼─────────────────────────────▼────────────────┐
│                    INTEGRATION LAYER                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │    Garmin    │   │   Weather    │   │    Telegram      │  │
│  │  Live Sync   │   │   API Sync   │   │    Bot API       │  │
│  └──────────────┘   └──────────────┘   └──────────────────┘  │
└───────────────┬─────────────────────────────┬────────────────┘
                │                             │
┌───────────────▼─────────────────────────────▼────────────────┐
│                        CORE LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │   Athlete    │  │   Database   │  │  Periodization +   │  │
│  │   Profile    │  │   Manager    │  │    Equipment       │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                      CONFIG LAYER                             │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  titan/config/thresholds.py  (safety constants)       │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

Directory layout as of v5.7.0 — for current layout see `CLAUDE.md §Repository Layout`.
The science/ and tests/ sections below are partial; significant additions were made in v5.7.1–v5.8.0.

```
project-mayhem/
├── README.md                           # Main documentation
├── ARCHITECTURE.md                     # This file
├── CHANGES.md                          # Change log
├── DEPLOYMENT_GUIDE.md                 # Deployment guide
├── FUTURE_UPGRADES.md                  # Roadmap / upcoming features
├── CORE_MIGRATION_SUMMARY.md           # v50 → v51 migration notes
├── requirements.txt                    # Python dependencies (pinned)
├── pyproject.toml                      # pytest + coverage config
├── main.py                             # Root-level launcher (python main.py)
├── system_check.py                     # Module health check
├── test_core_modules.py                # pytest suite — core modules
├── test_titan_logic.py                 # pytest suite — science logic
├── test_new_modules.py                 # pytest suite — new modules
├── test_main_smoke.py                  # Smoke tests for main entry point
├── test_menu_system.py                 # Menu system tests
├── test_daily_coach_extended.py        # Extended daily coach tests
├── test_error_paths.py                 # Error handling tests
├── test_logic_pytest.py                # Logic tests (pytest style)
├── test_telegram_bot.py                # Telegram integration tests
├── test_property_based.py              # Property-based tests (hypothesis)
│
├── tests/                              # Additional integration tests
│   ├── test_governance_integration.py  # Governance output contract + orchestration boundary
│   └── test_p0_safety_gates.py         # P0 hard-stop safety gate tests
│
├── .github/workflows/
│   ├── ci.yml                          # Test matrix (Py3.11/3.12), coverage, determinism, env-policy
│   ├── codeql.yml                      # CodeQL security scanning
│   └── secret-scan.yml                 # Secret detection
│
├── docs/
│   ├── adr/                            # Architecture Decision Records
│   │   ├── 0001–0006 (previous fixes and hardening)
│   │   ├── 0007-intensity-governance-architecture-audit.md
│   │   └── 0008-adaptive-priority-lock-and-vlg-specs.md
│   └── specs/                          # Component specifications
│       ├── adaptive_priority_lock.md   # APL spec (Status: Implemented ← v5.7.1)
│       └── volume_load_gauge.md        # VLG spec (Status: Implemented)
│   ├── ROADMAP.MD                      # Development workflow roadmap (Phase 0–3)
│   ├── adr/                            # Architecture Decision Records (0001–0008)
│   │   ├── README.md
│   │   ├── 0001-fix-typo-optimal-time-module-reference.md
│   │   ├── 0002-fix-weather-window-duration-bug.md
│   │   ├── 0003-align-documentation-with-current-module-layout.md
│   │   ├── 0004-improve-tests-for-weather-window-edge-cases.md
│   │   ├── 0005-fix-runtime-startup-issues.md
│   │   ├── 0006-architectural-hardening-cold-start-and-engine-sync.md
│   │   ├── 0007-intensity-governance-architecture-audit.md
│   │   └── 0008-adaptive-priority-lock-and-vlg-specs.md
│   ├── architecture/
│   │   ├── EVALUATION_ORDER.md         # Gate evaluation sequence and tie-breaking rules
│   │   └── GOVERNANCE_PHILOSOPHY.md    # Safety-first design rationale
│   ├── specs/
│   │   ├── adaptive_priority_lock.md   # APL specification (Status: Proposed)
│   │   └── volume_load_gauge.md        # VLG specification (Status: Implemented)
│   └── training/
│       ├── DECISION_MODEL.md           # 7-gate deterministic decision pipeline
│       ├── OPERATIONAL_MODEL.md        # Generic endurance framework (profile-agnostic)
│       └── profiles/
│           └── 5K.md                   # 5K race profile (instantiation of OPERATIONAL_MODEL)
│
└── titan/                              # Main package (47 Python modules)
    ├── __init__.py
    ├── main.py                         # Entry point
    │
    ├── config/                         # 1 module
    │   └── thresholds.py               # Safety threshold constants (VO2, HRV, TSB, fatigue)
    │
    ├── core/                           # 4 modules
    │   ├── athlete.py                  # UniversalAthleteProfile + AthleteDatabase
    │   ├── database.py                 # DatabaseManager (SQLite, thread-safe)
    │   ├── periodization.py            # PeriodizationManager
    │   └── equipment.py                # EquipmentManager (shoes, gear)
    │
    ├── science/                        # 26 modules
    │   ├── hrv_engine.py               # HRV analysis + guided training
    │   ├── tsb_engine.py               # CTL/ATL/TSB calculations
    │   ├── acwr_engine.py              # Acute:Chronic workload ratio
    │   │   — Foundational engines —
    │   ├── hrv_engine.py               # HRV analysis + guided training (Kiviniemi 2007)
    │   ├── tsb_engine.py               # CTL/ATL/TSB (CTL α=2/43, ATL α=2/8)
    │   ├── acwr_engine.py              # Acute:Chronic workload ratio (safe 0.8–1.3)
    │   ├── lactate_logic.py            # LT1/LT2 estimation
    │   ├── drift_engine.py             # HR drift calculation
    │   ├── efficiency_engine.py        # Efficiency Factor
    │   ├── durability_engine.py        # Pace durability index
    │   ├── trimp_engine.py             # TRIMP calculations
    │   ├── glycogen_model.py           # Glycogen depletion/refueling + GlycogenDebtAccumulator
    │   ├── fatigue_engine.py           # Fatigue classification
    │   ├── readiness_engine.py         # Composite readiness scoring (HRV + sleep + TSB)
    │   │   — Autonomic & critical systems —
    │   ├── autonomic_engine.py         # Autonomic Fusion Index (HRV 0.40 + HRR 0.35 + sleep 0.15 + resp 0.10)
    │   ├── critical_speed.py           # CS & D' tracker with thermal degradation + calibration confidence
    │   ├── rcp_engine.py               # Respiratory Compensation Point
    │   ├── biomechanics.py             # Cadence, stride, form
    │   ├── adaptive_memory.py          # Session history + supercompensation
    │   ├── autonomic_engine.py         # AutonomicFusionEngine (AFI)
    │   ├── governance_engine.py        # GovernanceEngine (7 safety gates)
    │   ├── governance_contracts.py     # GovernanceContracts (output shape guard)
    │   ├── intensity_governor.py       # IntensityGovernor (GREEN/YELLOW/RED)
    │   ├── volume_load_gauge.py        # VolumeLoadGauge — TSB+ACWR+glycogen aggregator
    │   ├── adaptive_priority_lock.py   # AdaptivePriorityLock — pre-governance resolver ← v5.7.1
    │   └── outcome_tracker.py          # OutcomeTracker — decision→outcome foundation ← v5.7.1
    │   │   — Advanced —
    │   ├── biomechanics.py             # Cadence, stride, form analysis
    │   ├── adaptive_memory.py          # Session history + supercompensation
    │   │   — Governance infrastructure —
    │   ├── governance_engine.py        # 7-gate safety system (H1–H4 hard stops, V1–V5 VO2, fueling)
    │   ├── governance_contracts.py     # Output shape contracts + structural invariant validation
    │   ├── intensity_governor.py       # Graduated GREEN/YELLOW/RED intensity enforcement
    │   └── volume_load_gauge.py        # Unified load aggregation: TSB + ACWR + glycogen → VLGState
    │
    ├── features/                       # 3 modules
    │   ├── weekly_planner.py           # Weekly training plan generator
    │   ├── optimal_time_calculator.py  # Optimal running time calculator
    │   └── nutrition_optimizer.py      # Nutrition + weight tracking
    │
    ├── integrations/                   # 3 modules
    │   ├── garmin_sync.py              # Live Garmin API integration (6h background thread)
    │   ├── weather_api.py              # Weather API + dew point + caching
    │   └── telegram_bot.py             # Telegram bot + notifications
    │
    ├── orchestration/                  # 1 module
    │   └── daily_coach.py              # DailyCoach v5.8 — 12-step morning routine + scheduler
    │
    ├── ui/                             # 2 modules
    │   ├── menu_system.py              # Interactive menu
    │   └── setup_wizard.py             # First-run setup wizard
    │
    ├── config/                         # 2 files
    │   ├── thresholds.py               # Safety threshold constants (single source of truth)
    │   └── evidence_registry.py        # Parameter provenance: source, evidence level ← v5.7.1
    │
    └── utils/                          # 2 modules
        ├── math_core.py                # MathCore: pace conversion, weight function, system status
        └── constants.py                # SESSION_TYPES, ACWR bounds, HR zones
```

---

## Module Responsibilities

### Governance Layer (NEW — v5.7)

| Module | Class / API | Responsibilities |
|--------|-------------|-----------------|
| `science/governance_engine.py` | `GovernanceEngine` | 7-gate safety pipeline. Hard stops H1–H4 (HRV collapse, RHR spike, TSB floor, extreme subjective fatigue). Soft gates: V1–V5 VO2 eligibility, fueling gate, 2-of-4 readiness downgrade, CS confidence lock, override lockdown, parasympathetic guard. Emits structured JSON log per gate event. |
| `science/governance_contracts.py` | `assert_vo2_eligibility_contract()`, `validate_vo2_eligibility()`, `ContractViolation` | Enforces stable output shape on `vo2_eligibility` dicts at the governance→orchestration boundary. Checks: required keys, type safety, structural invariants (eligible ↔ failed_conditions ↔ downgraded_to), failure code validity (V1–V5). Non-raising `validate_*` variant for production paths. |
| `science/intensity_governor.py` | `IntensityGovernor`, `GateResult` | Translates gate signals into graduated enforcement: GREEN (proceed), YELLOW (downgrade intensity/volume), RED (replace with recovery). `GateResult` dataclass carries: color, max_zone, volume_modifier, session_override, triggered_signals, audit. |
| `science/volume_load_gauge.py` | `VolumeLoadGauge`, `VLGState` | Pure aggregation over TSB, ACWR, glycogen debt → unified `VLGState(color, score, components, rationale)`. No new computation — consumes outputs of TSBEngine, ACWREngine, GlycogenModel. |

### Science Engines — Foundational

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `science/hrv_engine.py` | `HRVGuidedEngine` | HRV-guided training (Kiviniemi 2007, Plews 2013). Baseline tracking, trend analysis, daily guidance (proceed / modify / rest) |
| `science/tsb_engine.py` | `TSBEngine` | Training Stress Balance: CTL (α=2/43), ATL (α=2/8), TSB=CTL−ATL. Rebuilt from DB on cold start via `get_training_load_history()` |
| `science/acwr_engine.py` | `ACWREngine` | Acute:Chronic Workload Ratio. Safe range 0.8–1.3 (from `thresholds.py`) |
| `science/lactate_logic.py` | `LactateLogic` | LT1/LT2 estimation from pace/HR data |
| `science/drift_engine.py` | `DriftEngine` | HR drift calculation (fatigue marker) |
| `science/efficiency_engine.py` | `EfficiencyEngine` | Efficiency Factor (pace-per-HR ratio) |
| `science/durability_engine.py` | `DurabilityEngine` | Pace durability index |
| `science/trimp_engine.py` | `TRIMPEngine` | Training Impulse calculations |
| `science/glycogen_model.py` | `GlycogenModel`, `GlycogenEngine`, `GlycogenDebtAccumulator` | Glycogen depletion/refueling, debt accumulation across days |
| `science/fatigue_engine.py` | `FatigueEngine` | Fatigue classification from subjective and objective inputs |
| `science/readiness_engine.py` | `ReadinessEngine` | Composite readiness score from HRV + sleep + TSB |

### Science Engines — Autonomic & Critical Systems

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `science/autonomic_engine.py` | `AutonomicFusionEngine` | Autonomic Fusion Index (AFI). Signal weights: HRV 0.40 + HRR 0.35 + sleep 0.15 + respiration 0.10. AFI range: −1.0 (severely impaired) → +1.0 (optimal) |
| `science/critical_speed.py` | `CriticalSpeedEngine`, `CriticalSpeedTracker` | CS & D' calculation with thermal degradation correction, GAP adjustment, and calibration confidence tracking. CS confidence gates governance (`CS_CONFIDENCE_LOCK` if < 70%) |
| `science/rcp_engine.py` | `RCPEngine` | Respiratory Compensation Point estimation |
| `science/biomechanics.py` | `BiomechanicsEngine` | Cadence, stride length, form efficiency |
| `science/adaptive_memory.py` | `AdaptiveMemory` | Session history, supercompensation window, adaptive load anchors |

### Features

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `features/weekly_planner.py` | `WeeklyPlanGenerator` | 7-day plan from lactate threshold, drift, HRV trends, TSB, periodization phase, weather forecast |
| `features/optimal_time_calculator.py` | `OptimalTimeCalculator` | Best training hour from dew point, temperature, session type, circadian preference, TSB |
| `features/nutrition_optimizer.py` | `NutritionOptimizer` | Macros from weight velocity, training load (TSB/ACWR), phase; granular hydration tiers |

### Integrations

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `integrations/garmin_sync.py` | `GarminSync` | Live sync: activities, weight, sleep, HRV, stress; 6-hour background thread; graceful token-expiry recovery |
| `integrations/weather_api.py` | `WeatherAPI` | 48-hour forecast; Magnus-Tetens dew point; heat stress classification; 1-hour cache; `find_optimal_training_windows(duration_hours)` |
| `integrations/telegram_bot.py` | `TitanTelegramBot` | Scheduled coaching messages; `/today`, `/week`, `/stats`, `/recovery`, `/nutrition` commands |

### Core

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `core/athlete.py` | `UniversalAthleteProfile`, `AthleteDatabase` | Demographics, HR zones, BMR/TDEE, serialization, multi-athlete CRUD |
| `core/database.py` | `DatabaseManager` | Thread-safe SQLite; sessions, daily metrics, gear, PRs; `temperature_c` canonical column; `get_training_load_history()` feeds CTL/ATL on startup |
| `core/periodization.py` | `PeriodizationManager` | Phase calculation (BASE/BUILD/PEAK/TAPER/POST_RACE) from days-to-race |
| `core/equipment.py` | `EquipmentManager` | Shoe-type × session-type × surface gear checks |

### Config

| Module | Exports | Responsibilities |
|--------|---------|-----------------|
| `config/thresholds.py` | `HARD_STOP_HRV_DELTA=15.0`, `HARD_STOP_RHR_DELTA=8.0`, `HARD_STOP_TSB_FLOOR=-50.0`, `SUBJECTIVE_FATIGUE_EXTREME=8`, `SUBJECTIVE_FATIGUE_2OF4=6`, `VO2_ACWR_MIN=0.80`, `VO2_ACWR_MAX=1.30`, `VO2_READINESS_MIN=65.0`, `VO2_GLYCOGEN_DEBT_MAX=7.0`, `VO2_MIN_DAYS_SINCE_LAST=2` | Single source of truth for all safety threshold constants. Imported by governance_engine, intensity_governor, and tests. |

### Utils

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `utils/math_core.py` | `MathCore` | `pace_to_ms`, `ms_to_pace`, `format_pace`; `weight_function_Wf`; `system_status_SSV` |
| `utils/constants.py` | — | `SESSION_TYPES` (9 types), `ACWR_SAFE_MIN/MAX`, `DEFAULT_CONFIG` (HR zones, training defaults) |

---

## Threading Architecture

Three background threads run continuously when the system is live:

```
Thread A — Garmin Sync Worker     (daemon, every 6 h)
  └─ pulls activities, weight, sleep, HRV → writes to database

Thread B — Weather Update Worker  (daemon, every 1 h)
  └─ fetches 48-hour forecast → updates in-memory cache
  └─ recalculates optimal time windows on significant changes

Thread C — Daily Coach / Scheduler (daemon, cron-style)
  └─ 07:00 → 12-step morning routine (Garmin pull → governance → Telegram)
  └─ 20:00 Sunday → weekly plan generation → Telegram
```

SQLite write paths use `threading.Lock` (`check_same_thread=False`). Read paths
(e.g., `get_training_load_history()`, `get_governance_decisions()`) are **not**
currently lock-guarded — this is a known gap tracked as **T1-06** in
`TECHNICAL_DEBT.md`. The fix (extend the write lock to cover reads + add a
`_closed` flag to `close()`) is scheduled for the Phase 8 hardening sprint.

Worker shutdown calls `thread.join(timeout=5)` on each daemon without escalating
non-termination — tracked as **T3-06**. `run_morning_routine_async()` does not
deduplicate concurrent triggers — tracked as **T1-07**.

---

## Data Flow

### Startup

```
main.py
  → DailyCoach.__init__()
  → _hydrate_engines_from_db()   restore HRV (14d), weight (30d), load (42d)
  → TSBEngine.add_daily_load()   rebuild CTL/ATL from DB history
  → main_menu()                  interactive loop
```

### Morning Routine (07:00) — DailyCoach v5.8 — 12 Steps

```
Step  1  GarminSync.sync()              pull overnight HRV, sleep, weight
Step  2  DatabaseManager.persist()      write fresh metrics to DB
Step  3  HRVEngine + HRR update         live autonomic signal refresh
Step  4  AutonomicFusionEngine.compute() AFI from HRV + HRR + sleep + respiration
Step  5  CriticalSpeedTracker.adjust()  thermal degradation + CS calibration
Step  6  GlycogenDebtAccumulator.update() rolling glycogen debt
Step  7  ReadinessEngine.score()        composite score (HRV + sleep + TSB)
Step  8  WeeklyPlanner.today_session()  prescribed session for today
Step  9  GovernanceEngine.apply_constraints()  ← NON-BYPASSABLE SAFETY GATE
           H1-H4 hard stops (abort if any fires)
           V1-V5 VO2 eligibility checks
           Fueling gate
           2-of-4 readiness downgrade
           CS confidence lock
           Override lockdown
           Parasympathetic guard
           GovernanceContracts validates output shape
Step 10  OptimalTimeCalculator          best training window (dew point + session type + TSB)
Step 11  NutritionOptimizer             macro targets + hydration
Step 12  TelegramBot.send()             single morning coaching message
```

### Post-Run Flow

```
GarminSync detects new activity
  → import HR, pace, cadence, power
  → DriftEngine, EfficiencyEngine, LactateLogic, TrimpEngine
  → TSBEngine, ACWREngine       update training load
  → AdaptiveMemory              log session + supercompensation estimate
  → WeeklyPlanner               adjust remaining sessions if needed
  → TelegramBot.send()          post-run analysis
```

### Sunday Evening (20:00)

```
WeeklyPlanner.generate_week()
  → LactateLogic, DriftEngine, HRVEngine, TSBEngine  past-week analysis
  → PeriodizationManager        current training phase
  → WeatherAPI.get_forecast()   7-day outlook
  → OptimalTimeCalculator       best hour for each session
  → TelegramBot.send()          full weekly plan + optimal times
```

---

## Governance Safety Model

### Gate Hierarchy

```
Hard Stops (H1–H4) — abort session entirely if any fires:
  H1  HRV drops > 15% below 7-day baseline (PARASYMPATHETIC_GUARD)
  H2  Resting HR rises > 8 bpm above 7-day baseline
  H3  TSB below −50 (HARD_STOP_TSB_FLOOR)
  H4  Subjective fatigue ≥ 8/10 (SUBJECTIVE_FATIGUE_EXTREME)

VO2 Eligibility Gates (V1–V5) — block VO2/HAMMER sessions:
  V1  ACWR outside [0.80, 1.30]
  V2  Readiness score < 65
  V3  Glycogen debt > 7.0
  V4  Fatigue level = HIGH
  V5  Days since last VO2 < 2

Soft Gates — downgrade intensity/volume:
  FUELING_GATE_LOCK      fueling not confirmed for high-intensity
  FUELING_GATE_FLAG      fueling not confirmed for moderate sessions
  READINESS_2OF4_DOWNGRADE  2 or more of {HRV, RHR, sleep, fatigue} signal weakness
  CS_CONFIDENCE_LOCK     CriticalSpeed calibration confidence < 70%
  OVERRIDE_LOCKDOWN      >80% of recent 14-day decisions were user overrides
```

### Output Contracts

Every `vo2_eligibility` dict produced by `GovernanceEngine` is validated by `governance_contracts.py` before it crosses into orchestration. The contract enforces:

- Required keys: `eligible`, `failed_conditions`, `original_session`, `downgraded_to`, `detailed_failed_conditions`, `reason`
- Structural invariants: `eligible=True` ↔ empty `failed_conditions` ↔ `downgraded_to=None`
- Failure codes restricted to canonical set `{V1, V2, V3, V4, V5}`
- `failed_conditions` and `detailed_failed_conditions` codes must match in order

Contract violations are logged as structured JSON errors; the session dict is still forwarded to orchestration (fail-safe, not fail-stop at the contract boundary).

---

## Environment Variables

Configuration is via `.env` file (`~/Documents/TITAN/.env`):

```bash
# Garmin Connect
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_secure_password

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id

# Weather (OpenWeatherMap)
WEATHER_API_KEY=your_api_key
WEATHER_LOCATION=Athens,GR

# Optional overrides (defaults shown)
DATABASE_PATH=titan.db
LOG_LEVEL=INFO
GARMIN_SYNC_INTERVAL_HOURS=6
WEATHER_CACHE_DURATION_HOURS=1
```

---

## Database Schema

Four tables, all created by `DatabaseManager.create_database()`.

```sql
CREATE TABLE IF NOT EXISTS daily_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL UNIQUE,
    weight_kg       REAL,
    hrv_rmssd       REAL,
    resting_hr      INTEGER,
    sleep_hours     REAL,
    sleep_quality   INTEGER,      -- 0-100
    soreness        INTEGER,      -- 0-5
    fatigue_level   INTEGER,      -- 0-5
    mood            INTEGER,      -- 0-5
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS training_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    session_type    TEXT,
    distance_km     REAL,
    duration_sec    INTEGER,
    avg_hr          INTEGER,
    max_hr          INTEGER,
    rpe             INTEGER,          -- 1-10
    training_load   INTEGER,          -- computed: rpe × (duration_sec / 60)
    shoe_id         INTEGER,          -- FK → gear_usage.id
    surface         TEXT,
    temperature_c   REAL,             -- canonical column name
    zone_distribution TEXT,           -- JSON HR zone breakdown
    notes           TEXT,
    FOREIGN KEY (shoe_id) REFERENCES gear_usage(id)
);

CREATE TABLE IF NOT EXISTS gear_usage (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    shoe_name                  TEXT NOT NULL,
    total_km                   REAL DEFAULT 0,
    last_used                  TEXT,
    compression_recovery_hours INTEGER DEFAULT 24,
    status                     TEXT DEFAULT 'ACTIVE',
    shoe_type                  TEXT,
    max_km_limit               REAL DEFAULT 800
);

CREATE TABLE IF NOT EXISTS personal_bests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    distance_km     REAL NOT NULL,
    time_sec        INTEGER NOT NULL,
    pace_sec_per_km REAL,
    date            TEXT NOT NULL,
    race_name       TEXT
);
```

---

## Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | Fix typo in optimal_time module reference | Implemented |
| 0002 | Fix weather window duration bug | Implemented |
| 0003 | Align docs with current module layout | Implemented |
| 0004 | Improve tests for weather window edge cases | Implemented |
| 0005 | Fix runtime startup issues | Implemented |
| 0006 | Architectural hardening: cold start and engine sync | Implemented |
| 0007 | Intensity governance architecture audit (read-only) | Implemented |
| 0008 | Adaptive Priority Lock and VLG specs | Proposed (VLG implemented; APL pending) |

Full records in `docs/adr/`.

---

## Roadmap

The development roadmap is tracked in `docs/ROADMAP.MD`. Current state:

- **Phase 0** (Stabilization) — CLOSED
- **Phase 1** (Product Definition) — CLOSED
- **Phase 2** (Architectural Rails) — CLOSED
- **Phase 3** (Engine Implementation) — IN PROGRESS
  - `volume_load_gauge.py` — IMPLEMENTED
  - `adaptive_priority_lock.py` — SPECIFIED (implementation next)
  - Governance integration — IMPLEMENTED (no gate logic modifications)
  - Unit + integration tests — IMPLEMENTED
  - CI validation — IMPLEMENTED

Next cycle priorities:
1. **APL implementation** — `adaptive_priority_lock.py` following the spec in `docs/specs/adaptive_priority_lock.md`
2. **E2E regression suite** — gold-path scenarios: new athlete, weekly plan, recovery adaptation
3. **Observability** — structured logs for remaining flows (planner, scoring, Telegram handlers)
4. **Web UI / Operator Console** — readiness dashboard, load timeline, manual review workflow

---

**Status**: v5.7.0 — 47 modules, 600+ tests passing across 12 test files
**Python**: 3.11+ (mandatory)
**Last updated**: 2026-03-01
