# CLAUDE.md — TITAN OS

## Project Overview

**TITAN OS** (v51.3) is a closed-loop, longevity-first athletic operating system for runners. It integrates with Garmin Connect to sync training data and wearables, applies science-based algorithms (HRV, TSB/CTL/ATL, ACWR, lactate threshold, drift analysis), generates weekly training plans, calculates optimal workout timing based on weather/dew point, optimizes nutrition macros, and delivers coaching via a Telegram bot.

- **Language**: Python 3.11+ (mandatory — uses `tomllib`, UTF-8 mode PEP 686)
- **Database**: SQLite (thread-safe, via `DatabaseManager`)
- **External APIs**: Garmin Connect, OpenWeatherMap, Telegram Bot API

---

## Repository Layout

```
project-mayhem/
├── main.py                  # Root launcher (delegates to titan/main.py)
├── system_check.py          # Module health check (31 checks)
├── requirements.txt         # Production + dev dependencies
├── pyproject.toml           # pytest + coverage config
├── test_core_modules.py     # 69 core module tests
├── test_new_modules.py      # Additional module tests
├── test_titan_logic.py      # 8 science logic tests
├── tests/                   # Additional test suite directory
├── docs/adr/                # Architecture Decision Records (ADRs)
└── titan/                   # Main package
    ├── core/                # Athlete, Database, Periodization, Equipment
    ├── science/             # 15 science engines (HRV, TSB, ACWR, lactate, etc.)
    ├── features/            # Weekly planner, optimal time, nutrition optimizer
    ├── integrations/        # Garmin, Weather API, Telegram bot
    ├── orchestration/       # Daily coach (morning routine + DB hydration)
    ├── ui/                  # Menu system, setup wizard
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
WEATHER_API_KEY=your_openweathermap_key
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
# Run all tests
pytest

# Run with coverage
pytest --cov=titan --cov-report=term-missing

# Run specific test files
pytest test_core_modules.py
pytest test_titan_logic.py
pytest test_new_modules.py
```

Test configuration is in `pyproject.toml`. Tests discover all `test_*.py` files in the root directory.

---

## Architecture Notes

### Layered Architecture (bottom-up)

1. **Core** (`titan/core/`) — `UniversalAthleteProfile`, `DatabaseManager` (SQLite, thread-safe), `PeriodizationManager`, `EquipmentManager`
2. **Science** (`titan/science/`) — 15 independent engines: HRV, TSB/CTL/ATL, ACWR, lactate, drift, efficiency, durability, TRIMP, glycogen, fatigue, readiness, critical speed, RCP, biomechanics, adaptive memory
3. **Integrations** (`titan/integrations/`) — `GarminSync` (6h background thread), `WeatherAPI` (1h cache, 48h forecast), `TitanTelegramBot`
4. **Features** (`titan/features/`) — `WeeklyPlanGenerator`, `OptimalTimeCalculator`, `NutritionOptimizer`
5. **Orchestration** (`titan/orchestration/`) — `DailyCoach` ties everything together; hydrates engines from DB on startup

### Threading

Three daemon background threads run when the system is live:
- **Garmin Sync** — every 6 hours
- **Weather Update** — every 1 hour
- **Daily Coach / Scheduler** — cron-style (07:00 morning briefing, 20:00 Sunday weekly plan)

All SQLite writes use `threading.Lock` (`check_same_thread=False`).

### Database

Four SQLite tables: `daily_metrics`, `training_log`, `gear_usage`, `personal_bests`.
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
| `CORE_MIGRATION_SUMMARY.md` | v50 → v51 migration notes |
| `titan/utils/constants.py` | `SESSION_TYPES`, `ACWR_SAFE_MIN/MAX`, `DEFAULT_CONFIG` |
| `titan/utils/math_core.py` | `MathCore`: pace conversion, `weight_function_Wf`, `system_status_SSV` |
