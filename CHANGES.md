# TITAN v51 — CHANGELOG

---

## v5.7.0 / v51.4 — Governance hardening, contract guard, CI baseline (2026-03-01)

### Safety & Governance

- **`GovernanceEngine` rewrite** (`titan/science/governance_engine.py`)
  Complete rewrite of `_check_vo2_eligibility` which had accumulated ~300 lines of
  duplicate/broken code from bad merges. Key fixes:
  - V4 gate was appending V1/V2/V3 codes instead of V4
  - V5 gate used `days_val = 999` anti-pattern making the gate unreachable
  - ACWR ceiling was hardcoded `1.5` instead of `VO2_ACWR_MAX = 1.30` from thresholds
  - Rewrote all V1–V5 gates to use canonical constants from `titan/config/thresholds.py`
  - V5 now correctly fails closed on `None` / non-integer inputs

- **`GovernanceContracts`** (`titan/science/governance_contracts.py`) — NEW MODULE
  Output shape guard for `vo2_eligibility` dicts at the governance → orchestration boundary.
  - `ContractViolation(ValueError)` — raised on shape/invariant violations
  - `assert_vo2_eligibility_contract(result)` — strict assertion (raises)
  - `validate_vo2_eligibility(result)` — non-raising variant (returns error string or None)
  - Validates: required keys, type safety, structural invariants, failure code set {V1–V5},
    order-consistency between `failed_conditions` and `detailed_failed_conditions`
  - Wired into `GovernanceEngine.apply_constraints()` — violations logged as structured JSON

- **Structured gate logging** — every governance gate event emits a JSON log line via
  `_gate_event(gate, action, **fields)`, enabling observability without code coupling.
  Lock codes now form a canonical set: `HARD_STOP_SAFETY_GATES`, `VO2_ELIGIBILITY_GATE`,
  `FUELING_GATE_LOCK`, `FUELING_GATE_FLAG`, `READINESS_2OF4_DOWNGRADE`,
  `INTENSITY_GATE_RED/YELLOW`, `PARASYMPATHETIC_GUARD`, `OVERRIDE_LOCKDOWN`,
  `CS_CONFIDENCE_LOCK`.

### Security

- **`launcher/main.py`** — argument redaction before logging.
  `sys.argv` was logged verbatim at startup. Added `_redact_argv(argv)` which replaces
  `--flag=value` and `--flag value` forms with `<redacted>`, preventing credential leakage
  into log files when flags like `--password` or `--token` are passed.

### Tests

- **`tests/test_governance_integration.py`** — NEW (27 tests across 3 classes)
  - `TestVo2EligibilityContract` — contract guard: valid pass/fail, missing key,
    invariant violations, unknown codes, `validate_*` None-input handling
  - `TestGovernanceOutputContract` — every V1–V5 gate path + all-fail + invalid-numeric
    produces contract-valid output from the live `GovernanceEngine`
  - `TestOrchestrationBoundaryBackwardCompat` — `governance_locks_applied` always list,
    `governance_clean` always bool, `vo2_eligibility` 6-field shape stable across paths,
    lock codes from canonical set only

- **`tests/test_p0_safety_gates.py`** — NEW (14 tests, P0 criticality)
  Extracted from stale branch, fixed import alias (`SUBJECTIVE_FATIGUE_EXTREME`)
  and lock-code assertions (`HARD_STOP_SAFETY_GATES` + `hard_stop_reasons[].gate`).

- **`test_core_modules.py`** — corruption recovery
  Removed 10 duplicate empty test definitions left by bad merges. Restored correct
  assertions for `test_vo2_gate_invalid_numeric_inputs_fail_closed`,
  `test_vo2_gate_acwr_above_conservative_ceiling_downgrades`, and
  `test_vo2_gate_failed_conditions_are_deterministically_ordered`.

### CI / Build

- **`.github/workflows/ci.yml`** — NEW — 3-job CI pipeline:
  - `test` — matrix Python 3.11 / 3.12; full pytest + `--cov-fail-under=80` for
    `governance_engine` and `governance_contracts`
  - `determinism` — 3 consecutive identical runs of governance tests must produce
    identical exit codes
  - `env-policy` — Python 3.11+ enforcement, pip dry-run, `.env` file guard,
    `system_check.py` module health

### Documentation

- Cherry-picked from stale branches into main:
  - `docs/specs/adaptive_priority_lock.md` — APL architecture spec (Status: Proposed)
  - `docs/specs/volume_load_gauge.md` — VLG aggregation spec (Status: Implemented)
  - `docs/adr/0008-adaptive-priority-lock-and-vlg-specs.md` — ADR for both specs
- **`ARCHITECTURE.md`** — complete rewrite reflecting v5.7.0:
  - Governance layer added to architecture diagram
  - Directory tree updated: `titan/config/`, `tests/`, `docs/specs/`, `docs/training/`,
    `.github/workflows/`, all 21 science modules
  - Module responsibilities tables for all governance/autonomic modules
  - 12-step DailyCoach morning routine documented
  - Governance safety model section (gate hierarchy, output contracts)
  - ADR table updated through ADR-0008

---

## v51.1 — Bug fixes, accuracy & documentation (2026-02-18)

### 🐛 Bug fixes

- **`WeatherAPI.calculate_dew_point`** — Magnus-Tetens formula was using a
  linear `+ humidity/100.0` term instead of the required logarithm.
  Fixed: `gamma = (a·T)/(b+T) + math.log(RH/100)`.
  Known-value check: T=20°C / RH=50% now returns Td≈9.3°C (was ~28°C).
  Added RH clamp `[1, 100]` to prevent `log(0)` domain error.

- **`WeatherAPI.find_optimal_training_windows`** — `duration_hours` boundary
  check and array slice used inconsistent float/int logic causing off-by-one
  for all durations. Fixed with `required_slots = max(1, math.ceil(duration_hours))`.
  Added early return `[]` for `duration_hours <= 0`.

### 🔌 API consistency

- **`DatabaseManager.save_session`** — parameter renamed from `temperature`
  to `temperature_c` (matches the SQLite column name).
  Backward-compatible: `temperature=` still works but emits `DeprecationWarning`.

### 📝 Documentation

- **`README.md`** — removed phantom module `integrations/wearables.py`;
  wearable data flows through `garmin_sync.py`.

- **`ARCHITECTURE.md`** — complete rewrite:
  - Diagram corrected (removed non-existent module boxes)
  - Directory tree reflects only on-disk files
  - Module Responsibilities: verbose docstrings → concise tables
  - Threading: 5 speculative threads → 3 real daemon threads
  - Config: removed non-existent `config.yaml` reference
  - DB Schema: actual tables listed; planned tables clearly marked
  - Footer updated: `✅ v51 deployed — 31 modules, 99 tests`

- **`docs/adr/`** — four Architecture Decision Records added (status: Implemented):
  - `0001` — optimal_time.py module name typo
  - `0002` — weather window fractional duration bug
  - `0003` — documentation / module layout alignment
  - `0004` — weather window edge-case test strategy

- **`CHANGES.md`** (this file) — corrected stale "All tests passing" claim
  from v51.0 release (the original `test_core_modules.py` failed under pytest).

### ✅ Tests

- **`test_core_modules.py`** — rewritten as proper pytest suite (8 classes):
  - `TestAthleteProfile`, `TestPeriodization`, `TestEquipment`, `TestDatabase`,
    `TestAthleteDatabase`, `TestMathCore`, `TestConstants`, `TestWeatherDewPoint`,
    `TestWeatherWindows`, `TestWeatherTrainingWindows`
  - Fixtures: `athlete`, `db(tmp_path)`, `populated_db`, `athlete_db(tmp_path)`, `api`
  - `@pytest.mark.parametrize` for phases, weight function, system status, dew point
  - `warnings.catch_warnings` assertion for `DeprecationWarning` on deprecated alias
  - 13 edge-case tests for `find_optimal_training_windows` (monkeypatched + live sim)
  - `pytest test_core_modules.py test_titan_logic.py -q` → **67 passed, 0 warnings**

---

## v51.0 — Major Restructure: v50 → v51

### **Release Date**: 2026-02-16

---

## 🆕 New Features

### 1. **Garmin Live Sync** (`integrations/garmin_sync.py`)
- ✅ Real-time activity sync
- ✅ Weight tracking from Garmin scale
- ✅ Sleep data import
- ✅ HRV data from Garmin devices
- ✅ Background sync every 6 hours
- ✅ Manual sync command

### 2. **Weekly Training Plan Generator** (`features/weekly_planner.py`)
- ✅ Analyzes lactate threshold from recent sessions
- ✅ Considers drift patterns
- ✅ HRV-guided adjustments
- ✅ TSB-aware planning
- ✅ Weather-adjusted sessions
- ✅ Phase-specific plans (BASE/BUILD/PEAK/TAPER)

### 3. **Optimal Running Time Calculator** (`features/optimal_time_calculator.py`)
- ✅ Hourly dew point analysis
- ✅ Temperature pattern optimization
- ✅ Session-type specific timing (INTERVALS vs LONG_RUN)
- ✅ TSB-aware recommendations
- ✅ Circadian rhythm consideration

### 4. **Nutrition Optimizer** (`features/nutrition_optimizer.py`)
- ✅ Weight trend analysis (7/14/30 day)
- ✅ Training load-based carb calculations
- ✅ RED-S detection and warnings
- ✅ Session-specific meal timing
- ✅ Hydration calculations with heat adjustment

### 5. **Telegram Bot Integration** (`integrations/telegram_bot.py`)
- ✅ Daily morning coaching (07:00)
- ✅ Weekly plan delivery (Sunday 20:00)
- ✅ Post-run analysis
- ✅ Recovery alerts
- ✅ Interactive commands (/today, /week, /stats)

### 6. **Weather API Integration** (`integrations/weather_api.py`)
- ✅ Hourly 48-hour forecast
- ✅ Dew point calculation
- ✅ Heat stress classification
- ✅ Training window optimization
- ✅ Background updates every hour

### 7. **Daily Coach Orchestrator** (`orchestration/daily_coach.py`)
- ✅ Morning routine automation
- ✅ Data sync coordination
- ✅ Recovery status analysis
- ✅ Optimal time calculation
- ✅ Nutrition plan generation
- ✅ Telegram notification delivery

---

## 🔧 Architecture Changes

### Modular Structure
**Before (v50)**: Single 5,974-line monolithic file
**After (v51)**: 35+ focused modules in 7 directories

### Directory Organization
```
titan/
├── core/          # 7 modules  - Foundation
├── science/       # 15 modules - Scientific engines
├── features/      # 8 modules  - Feature implementations
├── integrations/  # 4 modules  - External APIs
├── orchestration/ # 3 modules  - High-level coordination
├── ui/            # 2 modules  - User interfaces
└── utils/         # 5 modules  - Utilities
```

### Threading Implementation
**New**: 5 background threads for:
- Garmin sync (6h interval)
- Weather updates (1h interval)
- Telegram bot listener
- Daily coach (07:00)
- Weekly planner (Sunday 20:00)

---

## ✅ Preserved Functionality

### All 54 Original Classes Migrated
- ✅ UniversalAthleteProfile
- ✅ DatabaseManager + AthleteDatabase
- ✅ HRVGuidedEngine
- ✅ TSBEngine
- ✅ ACWREngine
- ✅ LactateLogic
- ✅ DriftEngine
- ✅ EfficiencyEngine
- ✅ DurabilityEngine
- ✅ TRIMPEngine
- ✅ GlycogenModel
- ✅ FatigueEngine
- ✅ ReadinessEngine
- ✅ ... and 41 more

### Database Schema
- ✅ All original tables preserved
- ⏳ Planned: weight_log, hrv_log, weather_cache, notification_log, weekly_plans
  (not yet created; see FUTURE_UPGRADES.md for schema design)
- ✅ Backward compatible

### Menu System
- ✅ All 46 original menu functions available
- ✅ Migrated to `ui/menu_system.py`

---

## 📊 Improvements

### Code Quality
- ✅ Full type hints throughout
- ✅ Comprehensive docstrings
- ✅ Scientific references in comments
- ✅ PEP 8 compliant

### Testing
- ✅ Test suite for core modules (`test_core_modules.py`)
- ✅ Test suite for science modules (`test_titan_logic.py`)
- ⚠️  Original `test_core_modules.py` used `print`/`return` style — not
  compatible with pytest (missing fixtures, `PytestReturnNotNoneWarning`);
  rewritten in v51.1 (see below)

### Documentation
- ✅ README.md with full usage guide
- ✅ ARCHITECTURE.md with design decisions
- ✅ MIGRATION_CORE_MODULES.md for developers
- ✅ QUICK_REFERENCE.md for quick lookups

---

## 🔮 Future Roadmap

### Phase 5: ML Enhancement (Q2 2026)
- LSTM for training load prediction
- Injury risk ML model
- Performance prediction with confidence intervals

### Phase 6: Web UI (Q3 2026)
- Streamlit dashboard
- Interactive charts
- Training calendar

### Phase 7: Mobile App (Q4 2026)
- React Native app
- Push notifications
- GPS tracking

---

## 🐛 Bug Fixes

- Fixed: Threading safety issues (none in v50, prevented in v51)
- Fixed: Memory leaks from infinite logs (added rotation)
- Improved: Error handling on all API calls
- Improved: Retry logic with exponential backoff

---

## 🙏 Acknowledgments

Built with:
- **Scientific Research**: 15+ peer-reviewed studies cited
- **Community Feedback**: Based on athlete needs
- **AI Assistance**: Claude Code for architecture design

---

**TITAN v51.0** - Από monolith σε production-ready AI system 🚀
