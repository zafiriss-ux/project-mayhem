# TITAN v51 — CHANGELOG

---

## v5.7.3 / v51.7 — Phase 5 closure: maintenance & documentation sync (2026-03-02)

### Phase Status

- **Phase 5 — Science Calibration** — marked **CLOSED** in `docs/ROADMAP.MD`.
  All five deliverables completed in prior commits (lock/outcome correlation
  analytics, HEURISTIC→MODERATE promotion surfacing, MODERATE→STRONG cross-profile
  replication gate, `/calibration` Telegram output, `EvidenceRegistry` promotion
  metadata schema). No remaining items.

### Housekeeping

- **`CLAUDE.md`** — full accuracy pass to reflect v5.7.2 reality:
  - Version badge updated: v5.7.0 → v5.7.2.
  - Science module count corrected: 21 → 23 (includes `AdaptivePriorityLock`
    and `OutcomeTracker` introduced in v5.7.1).
  - `titan/config/` entry updated to list `evidence_registry.py` alongside
    `thresholds.py`.
  - Repository layout `tests/` section expanded from 2 files to the full
    13-file suite (added phase3/4 hygiene, E2E regression, observability,
    SLO, outcome tracker persistence, science engines, schema validation,
    Telegram calibration, and APL integration tests).
  - Governance infrastructure module count corrected: 4 → 6 (APL and
    OutcomeTracker now listed explicitly).
  - Database section updated: `governance_outcomes` table added (fifth table,
    created by `OutcomeTracker` in v5.7.1).
  - ADR-0008 note corrected: "(APL: proposed)" → "(APL: implemented)".
  - Key Files table updated: APL spec note corrected to "(implemented; v5.7.1)";
    `EvidenceRegistry` and `OutcomeTracker` added as first-class references;
    ROADMAP.MD phase range updated to "Phase 0–9".
  - Test count updated from 932 to 963 (Phase 4 hygiene sweep).
  - Running Tests section: added Phase 5 APL + phase hygiene commands.

---

## v5.7.2 / v51.6 — Phase 3 hygiene: branch coverage sweep (2026-03-02)

### Test Hygiene

- **`tests/test_phase3_hygiene.py`** — **NEW** (27 tests)
  Branch-coverage sweep closing all remaining uncovered defensive paths in
  the five Phase 3 science modules:
  - `governance_contracts.py` 78 % → **100 %**: all 11 `isinstance` guard
    violations and structural-invariant raise branches now documented as tests.
  - `governance_engine.py` 93 % → **99 %**: exception-handler fallbacks in
    `_evaluate_2of4_indicators` (HRV, sleep, subjective fatigue conversions),
    `_check_hard_stops` subjective-fatigue except path, `check_override_lockdown`
    DB-exception fallback, `_to_dict_maybe` dict-passthrough and arbitrary-object
    paths, fueling gate LOCK (TEMPO/INTERVALS ≥ 90 min) and FLAG
    (EASY/PROGRESSIVE 60–89 min) branches, intensity gate RED/YELLOW lock codes,
    and session_override passthrough.
  - `adaptive_priority_lock.py` 94 % → **100 %**: matrix-miss fallback (lines
    237–239) covered via monkeypatch; unknown-phase normalisation and
    cs_confidence < 0.50 tightening also explicitly tested.
  - `intensity_governor.py` 98 %, `volume_load_gauge.py` 100 % — unchanged.
  - Total Phase 3 module coverage: **99 %** (579 stmts, 3 missed).
  - One intentionally uncovered line remains: `governance_engine.py:475`
    (`_log.error` on self-produced contract violation — unreachable in
    production; defensive guard only).

---

## v5.7.1 / v51.5 — Platform maturity: APL, Outcome Tracker, Evidence Registry (2026-03-01)

### Governance Infrastructure

- **`AdaptivePriorityLock`** (`titan/science/adaptive_priority_lock.py`) — **NEW**
  Pre-governance priority resolver completing the governance infrastructure layer.
  - Phase × load_band matrix (5 phases × 4 bands) produces a `priority_vector`
    that reorders `{PARASYMPATHETIC_GUARD, CS_CONFIDENCE_LOCK, OVERRIDE_LOCKDOWN}` evaluation.
  - `PARASYMPATHETIC_GUARD` is rank 1 without exception — non-negotiable safety gate.
  - Adaptive threshold scaling per phase: PEAK tightens ACWR to 1.10 and cs_confidence
    to 0.85; TAPER sets ACWR to 1.25 and tsb_floor to -15.
  - `GovernanceEngine.apply_constraints()` reads `context.get('lock_thresholds', {})`
    and passes threshold overrides to `check_cs_confidence_lock()` and
    `check_override_lockdown()`. Static fallback when APL is absent — no behaviour change.
  - `DailyCoach.run_morning_routine()` now includes Step 9a (VLG + APL resolution)
    before Step 9b (governance). APL result injected into governance context.
  - Stateless, no DB access, no side effects.

- **`GovernanceEngine`** — threshold override support
  - `check_override_lockdown(db, threshold=None)` — accepts optional APL threshold override.
  - `check_cs_confidence_lock(cs_tracker, threshold=None)` — same pattern.
  - `apply_constraints()` extracts `lock_thresholds` and `priority_vector` from context;
    logs `apl_active=True/False` and `priority_vector` in the COMPLETE gate event.

### Observability — cause tagging

  Every governance gate event now includes a `cause` field:
  - `cause='TRAINING_LOGIC'` — gate fired on valid data exceeding a threshold
    (H1, H2, H3, H4, 2OF4, FUELING, OVERRIDE_LOCKDOWN).
  - `cause='DATA_PROBLEM'` — gate fired because input data was missing, invalid,
    or uncomputable (VO2 gate when `acwr_invalid/readiness_invalid` etc.; CS_CONFIDENCE_LOCK
    which is by definition a calibration data availability problem).
  This distinction is the key observability primitive: a DATA_PROBLEM in production
  means a pipeline or integration issue, not overtraining.

### Outcome Tracking

- **`OutcomeTracker`** (`titan/science/outcome_tracker.py`) — **NEW**
  Foundational decision→outcome connection. Without this, thresholds cannot be calibrated.
  - `record_decision()` — captures governance output + input signal snapshot + APL state.
  - `record_outcome()` — attaches post-session RPE, completion, actual session type.
  - `classify_lock_cause()` — classifies each decision as DATA_PROBLEM/TRAINING_LOGIC/CLEAN.
  - `get_calibration_summary()` — aggregate lock rates, completion rates, override rates.
  - `get_lock_rate_by_phase()` — reveals if specific phases systematically over-gate.
  - `DailyCoach` automatically records every governance decision (Step 9c).
  - Phase 2: persist to DB table `governance_outcomes`; compute threshold accuracy metrics.

### Parameter Provenance

- **`EvidenceRegistry`** (`titan/config/evidence_registry.py`) — **NEW**
  Source evidence for every constant in `titan/config/thresholds.py`.
  This is the mandatory prerequisite before any science-tuning of threshold values.
  - `ThresholdEvidence` dataclass: parameter, value, evidence_level, population, source,
    rationale, policy_note.
  - Evidence levels: STRONG / MODERATE / HEURISTIC — all 10 thresholds annotated.
  - `VO2_MIN_DAYS_SINCE_LAST` — STRONG (Billat 2001, Laursen 2002, Seiler 2009).
  - `VO2_READINESS_MIN` — HEURISTIC (internal composite, highest calibration priority).
  - `HARD_STOP_TSB_FLOOR` — HEURISTIC (coaching convention, not a measured injury threshold).
  - `get_policy_parameters()`, `get_calibration_candidates()`, `get_registry_summary()`.

### Documentation

- `docs/specs/adaptive_priority_lock.md` — status updated to **Implemented**.
- `docs/specs/volume_load_gauge.md` — extracted from stale branch, on-disk.
- `docs/adr/0008-adaptive-priority-lock-and-vlg-specs.md` — extracted from stale branch.

### Tests

- **`tests/test_apl_integration.py`** — **NEW** (64 tests, 6 test classes)
  - `TestAPLOutputContract` — all required keys present for all phases (parametrized)
  - `TestParasympatheticGuardInvariant` — rank 1 across all phases × loads × cs_confidence values
  - `TestPhaseLoadMatrix` — gate ordering verified for PEAK, TAPER, POST_RACE, BASE, BUILD
  - `TestAdaptiveThresholds` — PEAK/TAPER/BUILD overrides, default fallback, float types
  - `TestAPLStateless` — determinism, no state accumulation across calls
  - `TestAPLEdgeCases` — unknown phase, None/empty AFI, invalid cs_confidence
  - `TestOutcomeTracker` — record/retrieve, outcome miss, calibration summary, lock rates
  - `TestEvidenceRegistry` — all canonical parameters registered, values mirror thresholds.py,
    evidence levels valid, rationale non-empty

- All 91 tests pass (64 new + 27 existing governance integration tests).
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
