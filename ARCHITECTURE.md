# TITAN v51 — Modular Architecture

## 🎯 Vision

Transform TITAN from a monolithic script to a production-grade AI Training System:

- **Live Garmin Integration** — real-time sync of activities, weight, sleep, HRV
- **Intelligent Weekly Planning** — lactate threshold + drift analysis + HRV-guided scheduling
- **Optimal Time Calculator** — dew point, temperature, circadian rhythm analysis
- **Smart Nutrition** — weight-velocity, periodization phase, and load-adjusted macros
- **Telegram Bot** — automated coaching notifications and on-demand commands
- **Multi-threading** — background sync, weather updates, daily coaching
- **Extensible** — designed for ML enhancements, web UI, and team features

---

## 📊 Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                   TELEGRAM BOT INTERFACE                     │
│            (daily coaching · weekly plans · alerts)          │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    ORCHESTRATION LAYER                        │
│  ┌─────────────────────┐        ┌─────────────────────────┐  │
│  │   Weekly Planner    │        │     Daily Coach         │  │
│  │  (plan generation)  │        │  (morning routine +     │  │
│  └─────────────────────┘        │   optimal time)         │  │
│                                 └─────────────────────────┘  │
└───────────────┬─────────────────────────────┬────────────────┘
                │                             │
┌───────────────▼─────────────────────────────▼────────────────┐
│                      FEATURE MODULES                          │
│  ┌──────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Weekly Planner  │  │  Nutrition   │  │ Optimal Time   │  │
│  │    Generator     │  │  Optimizer   │  │  Calculator    │  │
│  └──────────────────┘  └──────────────┘  └────────────────┘  │
└───────────────┬─────────────────────────────┬────────────────┘
                │                             │
┌───────────────▼─────────────────────────────▼────────────────┐
│                      SCIENCE ENGINES                          │
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
│  │   Profile    │  │   Manager   │  │    Equipment       │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 📁 Directory Structure

All entries below exist on disk as of v51.2.

```
project-mayhem/
├── README.md                           # Main documentation
├── ARCHITECTURE.md                     # This file
├── CHANGES.md                          # Change log
├── DEPLOYMENT_GUIDE.md                 # Deployment guide
├── FUTURE_UPGRADES.md                  # Roadmap / upcoming features
├── CORE_MIGRATION_SUMMARY.md           # v50 → v51 migration notes
├── requirements.txt                    # Python dependencies
├── main.py                             # Root-level launcher (python main.py)
├── system_check.py                     # Module health check (31 checks)
├── test_core_modules.py                # pytest suite — core modules (69 tests)
├── test_titan_logic.py                 # pytest suite — science logic (8 tests)
├── docs/
│   └── adr/                            # Architecture Decision Records
│       ├── 0001-fix-typo-optimal-time-module-reference.md
│       ├── 0002-fix-weather-window-duration-bug.md
│       ├── 0003-align-documentation-with-current-module-layout.md
│       ├── 0004-improve-tests-for-weather-window-edge-cases.md
│       ├── 0005-fix-runtime-startup-issues.md
│       └── 0006-architectural-hardening-cold-start-and-engine-sync.md
│
└── titan/
    ├── __init__.py
    ├── main.py                         # Entry point (also callable via root main.py)
    │
    ├── core/                           # 4 modules
    │   ├── athlete.py                  # UniversalAthleteProfile + AthleteDatabase
    │   ├── database.py                 # DatabaseManager (SQLite, thread-safe)
    │   ├── periodization.py            # PeriodizationManager
    │   └── equipment.py                # EquipmentManager (shoes, gear)
    │
    ├── science/                        # 15 modules
    │   ├── hrv_engine.py               # HRV analysis + guided training
    │   ├── tsb_engine.py               # CTL/ATL/TSB calculations
    │   ├── acwr_engine.py              # Acute:Chronic workload ratio
    │   ├── lactate_logic.py            # LT1/LT2 estimation
    │   ├── drift_engine.py             # HR drift calculation
    │   ├── efficiency_engine.py        # Efficiency Factor
    │   ├── durability_engine.py        # Pace durability
    │   ├── trimp_engine.py             # TRIMP calculations
    │   ├── glycogen_model.py           # Glycogen depletion/refueling
    │   ├── fatigue_engine.py           # Fatigue classification
    │   ├── readiness_engine.py         # Composite readiness scoring
    │   ├── critical_speed.py           # CS & D-prime
    │   ├── rcp_engine.py               # Respiratory Compensation Point
    │   ├── biomechanics.py             # Cadence, stride, form
    │   └── adaptive_memory.py          # Session history + supercompensation
    │
    ├── features/                       # 3 modules
    │   ├── weekly_planner.py           # Weekly training plan generator
    │   ├── optimal_time_calculator.py  # Optimal running time calculator
    │   └── nutrition_optimizer.py      # Nutrition + weight tracking
    │
    ├── integrations/                   # 3 modules
    │   ├── garmin_sync.py              # Live Garmin API integration
    │   ├── weather_api.py              # Weather API + dew point + caching
    │   └── telegram_bot.py             # Telegram bot + notifications
    │                                   # (wearable data flows through garmin_sync.py)
    │
    ├── orchestration/                  # 1 module
    │   └── daily_coach.py              # Morning routine + DB hydration on startup
    │
    ├── ui/                             # 2 modules
    │   ├── menu_system.py              # Interactive menu (migrated from v50)
    │   └── setup_wizard.py             # First-run setup wizard
    │
    └── utils/                          # 2 modules
        ├── math_core.py                # MathCore: pace, weight function, system status
        └── constants.py                # SESSION_TYPES, ACWR bounds, HR zones
```

---

## 🔧 Module Responsibilities

### Features

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `features/weekly_planner.py` | `WeeklyPlanGenerator` | 7-day plan from lactate threshold, drift, HRV trends, TSB, periodization phase, weather forecast |
| `features/optimal_time_calculator.py` | `OptimalTimeCalculator` | Best training hour from dew point, temperature, session type, circadian preference, TSB |
| `features/nutrition_optimizer.py` | `NutritionOptimizer` | Macros from weight velocity, training load (TSB/ACWR), phase; granular hydration tiers |

### Integrations

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `integrations/garmin_sync.py` | `GarminSync` | Live sync: activities, weight, sleep, HRV, stress; 6-hour background thread; graceful token-expiry recovery (`rm -rf ~/.garth`) |
| `integrations/weather_api.py` | `WeatherAPI` | 48-hour forecast; Magnus-Tetens dew point; heat stress classification; 1-hour cache; `find_optimal_training_windows(duration_hours)` with `ceil`-based slot logic |
| `integrations/telegram_bot.py` | `TitanTelegramBot` | Scheduled coaching messages; `/today`, `/week`, `/stats`, `/recovery`, `/nutrition` commands |

### Core

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `core/athlete.py` | `UniversalAthleteProfile`, `AthleteDatabase` | Demographics, HR zones, BMR/TDEE, serialization, multi-athlete CRUD |
| `core/database.py` | `DatabaseManager` | Thread-safe SQLite; sessions, daily metrics, gear, PRs; `temperature_c` canonical param; `get_training_load_history()` feeds CTL/ATL on startup |
| `core/periodization.py` | `PeriodizationManager` | Phase calculation (BASE/BUILD/PEAK/TAPER/POST_RACE) from days-to-race |
| `core/equipment.py` | `EquipmentManager` | Shoe-type × session-type × surface gear checks |

### Utils

| Module | Class | Responsibilities |
|--------|-------|-----------------|
| `utils/math_core.py` | `MathCore` | `pace_to_ms`, `ms_to_pace`, `format_pace`; `weight_function_Wf`; `system_status_SSV` |
| `utils/constants.py` | — | `SESSION_TYPES`, `ACWR_SAFE_MIN/MAX`, `DEFAULT_CONFIG` (HR zones, training defaults) |

---

## 🧵 Threading Architecture

Three background threads run continuously when the system is live:

```
Thread A — Garmin Sync Worker     (daemon, every 6 h)
  └─ pulls activities, weight, sleep, HRV → writes to database

Thread B — Weather Update Worker  (daemon, every 1 h)
  └─ fetches 48-hour forecast → updates in-memory cache
  └─ recalculates optimal time windows on significant changes

Thread C — Daily Coach / Scheduler (daemon, cron-style)
  └─ 07:00 → morning routine (Garmin pull → readiness → optimal time → Telegram)
  └─ 20:00 Sunday → weekly plan generation → Telegram
```

All integrations use `threading.Lock` for SQLite writes (`check_same_thread=False`).

---

## 🔄 Data Flow

### Startup

```
main.py
  → DailyCoach.__init__()
  → _hydrate_engines_from_db()   restore HRV (14d), weight (30d), load (42d)
  → TSBEngine.add_daily_load()   rebuild CTL/ATL from DB history
  → main_menu()                  interactive loop
```

### Morning Routine (07:00)

```
Daily Coach activates
  → GarminSync.sync()          pull overnight HRV, sleep, weight
  → WeatherAPI.get_forecast()  today's 48-hour hourly data
  → ReadinessEngine.score()    HRV + sleep + TSB composite
  → OptimalTimeCalculator      best training window (dew point + session type + TSB)
  → WeeklyPlanner              today's prescribed session
  → NutritionOptimizer         macro targets + hydration
  → TelegramBot.send()         single morning coaching message
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

## 🔐 Environment Variables

Configuration is via `.env` file (no `config.yaml` required):

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

## 💾 Database Schema

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

## 🗺️ Roadmap

Next priorities, in order:

1. **ML load prediction** — LSTM on `training_log` for injury risk scoring and CTL forecasting
2. **Streamlit dashboard** — visual CTL/ATL/TSB timeline, HRV trend, weekly calendar
3. **Additional device sync** — Strava, Polar, Whoop (new `integrations/` modules)
4. **Multi-athlete support** — team coaching via `AthleteDatabase` CRUD already in place

---

**Status**: ✅ v51.3 deployed — 31 modules, 77 tests passing (69 core + 8 science)
**Version**: 51.3.0
