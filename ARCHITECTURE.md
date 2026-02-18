# TITAN v51 - Modular Architecture Design

## 🎯 Vision
Transform TITAN from monolithic script to production-grade AI Training System with:
- **Live Garmin Integration**: Real-time data sync (activities, weight, sleep, HRV)
- **Intelligent Weekly Planning**: Lactate threshold + drift analysis + HRV-guided training
- **Optimal Time Calculator**: Dew point, temperature, circadian rhythm analysis
- **Smart Nutrition**: Weight-based, scientifically-backed diet adjustments
- **Telegram Bot**: Automated notifications and coaching
- **Multi-threading**: Background sync, weather updates, notifications
- **Extensible**: Ready for ML enhancements, web UI, team features

## 📊 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    TELEGRAM BOT INTERFACE                    │
│              (Daily notifications, weekly plans)             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   ORCHESTRATION LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Weekly Plan  │  │ Daily Coach  │  │ Notification │      │
│  │  Generator   │  │   Engine     │  │   Manager    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└───────────────┬──────────────────┬──────────────┬───────────┘
                │                  │              │
┌───────────────▼──────────────────▼──────────────▼───────────┐
│                     FEATURE MODULES                          │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Training Plan   │  │  Nutrition   │  │ Optimal Time   │ │
│  │   Generator     │  │  Optimizer   │  │   Calculator   │ │
│  └─────────────────┘  └──────────────┘  └────────────────┘ │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Injury Warning  │  │ Taper Engine │  │ Recovery Score │ │
│  └─────────────────┘  └──────────────┘  └────────────────┘ │
└───────────────┬──────────────────┬──────────────┬───────────┘
                │                  │              │
┌───────────────▼──────────────────▼──────────────▼───────────┐
│                     SCIENCE ENGINES                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ HRV Engine  │  │ TSB Engine  │  │ ACWR Engine │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Lactate     │  │ Drift       │  │ Efficiency  │         │
│  │ Logic       │  │ Engine      │  │ Engine      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Durability  │  │ Glycogen    │  │ TRIMP       │         │
│  │ Engine      │  │ Model       │  │ Engine      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└───────────────┬──────────────────┬──────────────┬───────────┘
                │                  │              │
┌───────────────▼──────────────────▼──────────────▼───────────┐
│                     INTEGRATION LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Garmin     │  │   Weather    │  │   Telegram   │      │
│  │ Live Sync    │  │   API Sync   │  │   Bot API    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└───────────────┬──────────────────┬──────────────┬───────────┘
                │                  │              │
┌───────────────▼──────────────────▼──────────────▼───────────┐
│                       CORE LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Athlete    │  │   Database   │  │    Config    │      │
│  │   Profile    │  │   Manager    │  │   Manager    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

## 📁 Directory Structure

> **Legend:** modules marked `[planned]` are on the roadmap but not yet present in
> the repository.  All other entries reflect files that exist on disk as of v51.

### Current Architecture

```
project-mayhem/
├── README.md                          # Main documentation
├── ARCHITECTURE.md                    # This file
├── CHANGES.md                         # Change log
├── DEPLOYMENT_GUIDE.md                # Deployment guide
├── FUTURE_UPGRADES.md                 # Roadmap / upcoming features
├── CORE_MIGRATION_SUMMARY.md          # v50 → v51 migration notes
├── requirements.txt                   # Python dependencies
├── system_check.py                    # Module health check script
├── test_core_modules.py               # pytest suite — core modules
├── test_titan_logic.py                # pytest suite — science logic
│
└── titan/                             # Main package
    ├── __init__.py
    ├── main.py                        # Entry point / REPL demo
    │
    ├── core/                          # Core foundation (4 modules)
    │   ├── __init__.py
    │   ├── athlete.py                 # UniversalAthleteProfile + AthleteDatabase
    │   ├── database.py                # DatabaseManager (SQLite, thread-safe)
    │   ├── periodization.py           # PeriodizationManager
    │   └── equipment.py               # EquipmentManager (shoes, gear)
    │
    ├── science/                       # Scientific engines (15 modules)
    │   ├── __init__.py
    │   ├── hrv_engine.py              # HRV analysis + guided training
    │   ├── tsb_engine.py              # CTL/ATL/TSB calculations
    │   ├── acwr_engine.py             # Acute:Chronic workload ratio
    │   ├── lactate_logic.py           # LT1/LT2 estimation
    │   ├── drift_engine.py            # HR drift calculation
    │   ├── efficiency_engine.py       # Efficiency Factor
    │   ├── durability_engine.py       # Pace durability
    │   ├── trimp_engine.py            # TRIMP calculations
    │   ├── glycogen_model.py          # Glycogen depletion/refueling
    │   ├── fatigue_engine.py          # Fatigue classification
    │   ├── readiness_engine.py        # Composite readiness scoring
    │   ├── critical_speed.py          # CS & D-prime
    │   ├── rcp_engine.py              # Respiratory Compensation Point
    │   ├── biomechanics.py            # Cadence, stride, form
    │   └── adaptive_memory.py         # Session history + supercompensation
    │
    ├── features/                      # Feature modules (3 modules)
    │   ├── __init__.py
    │   ├── weekly_planner.py          # 🆕 Weekly training plan generator
    │   ├── optimal_time_calculator.py # 🆕 Optimal running time calculator
    │   └── nutrition_optimizer.py     # 🆕 Enhanced nutrition + weight tracking
    │
    ├── integrations/                  # External integrations (3 modules)
    │   ├── __init__.py
    │   ├── garmin_sync.py             # 🆕 Live Garmin API integration
    │   ├── weather_api.py             # 🆕 Live weather API with caching
    │   └── telegram_bot.py            # 🆕 Telegram bot + notifications
    │                                  #   (wearable data flows through garmin_sync.py)
    │
    ├── orchestration/                 # 🆕 High-level orchestration (1 module)
    │   ├── __init__.py
    │   └── daily_coach.py             # Daily coaching + optimal time
    │
    ├── ui/                            # User interfaces (2 modules)
    │   ├── __init__.py
    │   ├── menu_system.py             # Menu system (migrated from v50)
    │   └── setup_wizard.py            # First-run setup wizard
    │
    └── utils/                         # Utilities (2 modules)
        ├── __init__.py
        ├── math_core.py               # MathCore: pace, weight, system-status
        └── constants.py               # SESSION_TYPES, ACWR bounds, HR zones
```

## 🔧 Module Responsibilities

### 🆕 New Core Features

#### 1. **Weekly Planner** (`features/weekly_planner.py`)
```python
class WeeklyPlanGenerator:
    """
    Generates next week's training plan based on:
    - Recent lactate threshold (from lactate_logic.py)
    - Training drift analysis (from drift_engine.py)
    - HRV trends (from hrv_engine.py)
    - TSB status (from tsb_engine.py)
    - Current periodization phase
    - Weather forecast
    - Recovery status

    Output: 7-day plan with:
    - Session type, duration, intensity
    - Specific workouts (warmup/main/cooldown)
    - Nutrition requirements
    - Equipment recommendations
    """
```

#### 2. **Optimal Time Calculator** (`features/optimal_time_calculator.py`)
```python
class OptimalTimeCalculator:
    """
    Calculates best running time for each day based on:
    - Dew point throughout the day (hourly forecast)
    - Temperature patterns
    - Wind conditions
    - Athlete's circadian rhythm preferences
    - Training stress balance (avoid running when fatigued)
    - Sunrise/sunset times
    - Session type requirements (long run = early morning, intervals = late morning)

    Output: Recommended time window with reasoning
    """
```

#### 3. **Nutrition Optimizer** (`features/nutrition_optimizer.py`)
```python
class NutritionOptimizer:
    """
    Enhanced nutrition module that:
    - Reads weight from Garmin API (daily weigh-ins)
    - Tracks weight trends (7/14/30 day averages)
    - Calculates optimal macros based on:
      * Current training load (from TSB/ACWR)
      * Weight change velocity
      * Periodization phase
      * Session type requirements
    - Provides daily nutrition plans
    - Alerts for energy availability issues
    - Session-specific fueling strategies

    Scientific backing: Burke et al., Jeukendrup protocols
    """
```

#### 4. **Garmin Live Sync** (`integrations/garmin_sync.py`)
```python
class GarminSync:
    """
    Live Garmin Connect API integration:

    Data pulled:
    - Activities (runs with full metrics: HR, pace, cadence, power)
    - Daily weight entries
    - Sleep data (hours, quality, deep/REM phases)
    - HRV data (rMSSD from Garmin devices)
    - Daily stress scores
    - Body Battery (Garmin metric)

    Features:
    - Automatic sync every 6 hours (threaded)
    - Manual sync command
    - Incremental sync (only new data)
    - Error handling with retry logic
    - Sync history tracking
    """
```

#### 5. **Telegram Bot** (`integrations/telegram_bot.py`)
```python
class TitanTelegramBot:
    """
    Telegram bot for notifications and coaching:

    Automated messages:
    - Weekly training plan (every Sunday 20:00)
    - Daily optimal running time (every day 07:00)
    - Post-run analysis (after Garmin sync detects new activity)
    - Nutrition adjustments (when weight changes detected)
    - Recovery alerts (HRV/sleep warnings)
    - Injury risk warnings

    Interactive commands:
    - /today - Today's workout
    - /week - This week's plan
    - /stats - Performance summary
    - /recovery - Recovery status
    - /nutrition - Today's nutrition plan

    Features:
    - Rich formatting (markdown)
    - Inline keyboards for quick responses
    - Chart generation (ASCII visualizations)
    """
```

#### 6. **Weather API** (`integrations/weather_api.py`)
```python
class WeatherAPI:
    """
    Live weather integration with intelligent caching:

    Features:
    - Hourly forecast (next 48 hours)
    - Dew point calculation
    - Heat stress index
    - Wind chill
    - Training condition recommendations
    - Optimal time suggestions

    Caching:
    - 1-hour cache for current conditions
    - 6-hour cache for forecasts
    - Automatic refresh in background thread
    """
```

### 🧵 Threading Architecture

```python
# Background Threads
Thread 1: Garmin Sync Worker
  - Runs every 6 hours
  - Pulls new activities, weight, sleep, HRV
  - Updates database
  - Triggers notifications if needed

Thread 2: Weather Update Worker
  - Runs every hour
  - Fetches weather forecast
  - Updates cache
  - Recalculates optimal times if significant changes

Thread 3: Telegram Bot Listener
  - Always running
  - Listens for user commands
  - Sends scheduled notifications

Thread 4: Weekly Plan Generator
  - Runs every Sunday at 19:00
  - Analyzes past week
  - Generates next week plan
  - Sends to Telegram

Thread 5: Daily Coach
  - Runs every day at 07:00
  - Calculates optimal running time
  - Sends daily coaching message
  - Checks recovery status
```

## 🔄 Data Flow

### Morning Routine (07:00)
```
1. Daily Coach Thread activates
2. Garmin Sync: Pull overnight data (sleep, HRV, weight)
3. Weather API: Get today's forecast
4. Calculate:
   - Recovery status (HRV + sleep + TSB)
   - Optimal running time (dew point + temp + recovery)
   - Today's session from weekly plan
   - Nutrition requirements
5. Telegram Bot: Send morning message with:
   - Recovery status
   - Today's workout
   - Optimal time window
   - Nutrition plan
```

### Post-Run Flow
```
1. Garmin Sync: Detect new activity
2. Import activity data
3. Analyze:
   - HR drift
   - Efficiency factor
   - Lactate estimation
   - Fatigue level
4. Update:
   - Training load (TSB, ACWR)
   - Performance trends
   - Next sessions in weekly plan (adjust if needed)
5. Telegram Bot: Send post-run analysis
6. Check:
   - Injury risk (alert if high)
   - Recovery needs (adjust next session if needed)
```

### Sunday Evening (20:00)
```
1. Weekly Plan Generator activates
2. Analyze past week:
   - Total training load
   - Lactate threshold changes
   - Drift patterns
   - Recovery trends
   - HRV baseline shifts
3. Generate next week plan:
   - Session types and sequencing
   - Volume and intensity distribution
   - Specific workouts
   - Nutrition requirements
4. Weather forecast: Get 7-day outlook
5. Optimal times: Calculate for each session
6. Telegram Bot: Send comprehensive weekly plan
```

## 🔐 Configuration & Security

### Environment Variables (.env)
```bash
# Garmin
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_secure_password

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id

# Weather API (OpenWeatherMap)
WEATHER_API_KEY=your_api_key
WEATHER_LOCATION=Athens,GR

# Database
DATABASE_PATH=data/database/titan.db

# Logging
LOG_LEVEL=INFO
LOG_DIR=data/logs
```

### Configuration (config.yaml)
```yaml
athlete:
  default_profile: "main"

garmin:
  sync_interval_hours: 6
  retry_attempts: 3
  timeout_seconds: 30

telegram:
  enabled: true
  morning_notification_time: "07:00"
  weekly_plan_time: "20:00"  # Sunday

weather:
  provider: "openweathermap"
  update_interval_hours: 1
  cache_duration_hours: 6

training:
  polarized_ratio: [80, 10, 10]  # Easy, Tempo, Hard
  deload_week_frequency: 4
  taper_weeks: 3

threading:
  enabled: true
  max_workers: 5
```

## 📊 Database Schema Updates

### New Tables

```sql
-- Weight tracking from Garmin
CREATE TABLE weight_log (
    date TEXT PRIMARY KEY,
    weight_kg REAL NOT NULL,
    source TEXT DEFAULT 'garmin',
    body_fat_pct REAL,
    muscle_mass_kg REAL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- HRV data from Garmin
CREATE TABLE hrv_log (
    date TEXT PRIMARY KEY,
    rmssd REAL NOT NULL,
    source TEXT DEFAULT 'garmin',
    hr_avg REAL,
    hr_min REAL,
    stress_score INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weather cache
CREATE TABLE weather_cache (
    location TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    hour_offset INT NOT NULL,
    temp_c REAL,
    humidity INT,
    dew_point REAL,
    wind_speed REAL,
    conditions TEXT,
    PRIMARY KEY (location, timestamp, hour_offset)
);

-- Notification history
CREATE TABLE notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notification_type TEXT NOT NULL,
    channel TEXT NOT NULL,  -- 'telegram', 'email', etc.
    status TEXT NOT NULL,    -- 'sent', 'failed', 'pending'
    content TEXT,
    error_message TEXT
);

-- Weekly plans
CREATE TABLE weekly_plans (
    week_start_date TEXT PRIMARY KEY,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    plan_json TEXT NOT NULL,  -- Full plan as JSON
    lactate_threshold_used REAL,
    avg_drift_used REAL,
    avg_hrv_used REAL,
    notes TEXT
);
```

## 🔮 Future Enhancements (Post-v51)

### Phase 5: ML Enhancement
- LSTM for training load prediction
- Injury risk ML model
- Performance prediction with confidence intervals
- Automated periodization adjustment

### Phase 6: Web UI
- Streamlit dashboard
- Interactive charts
- Training calendar
- Nutrition planner

### Phase 7: Advanced Features
- Multi-athlete coaching
- Team leaderboards
- Social features
- Integration with Strava, Polar, Whoop

### Phase 8: Mobile App
- React Native app
- Push notifications
- Offline mode
- GPS tracking integration

---

**Status**: 🚧 Architecture approved - Beginning implementation
**Target Completion**: 2026-02-15
**Version**: 51.0.0-alpha
