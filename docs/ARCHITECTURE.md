# TITAN OS — Architecture Reference

## System Overview

TITAN OS is a personal endurance coaching platform that combines physiological science engines,
real-world data ingestion (Garmin, weather), and an LLM-assisted daily coaching pipeline to
deliver governance-first, context-aware training recommendations. Its core design principles are:
safety of data integrity above all else; every coaching decision must pass explicit governance
gates before reaching the athlete; and all components are built for longevity — meaning the
system anticipates multi-year athlete timelines and multi-sport corpus growth.

---

## Entry Point Flow

```
launcher/main.py
  → validate_environment()          # checks .env, Python version, data dir
  → ensure_config()                 # runs setup wizard if first run
  → run_titan_kernel()
      → titan.__main__.main()
          → titan/main.py: run()
              → DatabaseManager(db_dir=TITAN_DATA_DIR)
              → UniversalAthleteProfile.from_env()
              → instantiate all science engines (TSBEngine, HRVGuidedEngine, …)
              → DailyCoach(db=db, tsb_engine=tsb_engine, …)
              → hydrate tsb_engine.daily_loads from DB
              → TitanContextContract(…) → ctx dict
              → main_menu(ctx)        # enters interactive menu loop
```

---

## Layer Map

### Layer 1 — Entry & Config

| Module | Role |
|---|---|
| `launcher/main.py` | Process entry point; environment validation; kernel bootstrap |
| `launcher/validator.py` | Data-dir resolution, `.env` validation |
| `launcher/paths.py` | Canonical path constants |
| `launcher/wizard.py` | CLI setup wizard (first-run credential collection) |
| `launcher/gui_wizard.py` | GUI variant of setup wizard |
| `launcher/errors.py` | `TitanError` hierarchy; kernel error translation |
| `launcher/logger.py` | Launcher-level logging init |
| `titan/config/thresholds.py` | Single source of truth for all safety threshold constants |
| `titan/config/evidence_registry.py` | Evidence citations for governance decisions |
| `titan/config/settings.py` | Centralised env-var config via pydantic-settings (P15-ARCH5) |
| `titan/utils/constants.py` | Shared numeric constants |
| `titan/utils/math_core.py` | Low-level math helpers |
| `titan/utils/secrets.py` | Credential loading / encryption helpers |

### Layer 2 — Data & Persistence

| Module | Role |
|---|---|
| `titan/core/database.py` | `DatabaseManager` — SQLite backend, all migrations, SCHEMA_VERSION |
| `titan/core/repositories/training.py` | `TrainingRepository` — training-domain SQL (training log and CTL/ATL/TSB load history, shoes, personal bests, CS performances) behind the `DatabaseManager` facade (plan #18, one domain per PR) |
| `titan/core/repositories/physiology.py` | `PhysiologyRepository` — physiology-domain SQL (daily metrics, HRV, resting HR, HRR, glycogen debt, weight history) behind the `DatabaseManager` facade (plan #18) |
| `titan/core/athlete.py` | `UniversalAthleteProfile` — athlete profile loading and validation |
| `titan/core/persistence.py` | `PersistenceAdapter` ABC and SQLite implementation |
| `titan/core/periodization.py` | Periodization phase state |
| `titan/core/equipment.py` | Equipment inventory model |
| `titan/core/structured_events.py` | Structured event logging helpers |
| `titan/core/schema.py` | SQLAlchemy Core MetaData descriptor — single authoritative source for all 19 table definitions (TD-08) |

### Layer 3 — Science Engines

| Module | Role |
|---|---|
| `titan/science/tsb_engine.py` | CTL/ATL/TSB calculation from `daily_loads` |
| `titan/science/hrv_engine.py` | HRV guided readiness (HRVGuidedEngine) |
| `titan/science/trimp_engine.py` | TRIMP (training impulse) calculation |
| `titan/science/acwr_engine.py` | Acute:Chronic Workload Ratio |
| `titan/science/governance_engine.py` | Hard governance gates (lock codes) |
| `titan/science/governance_contracts.py` | Typed contracts for governance decisions |
| `titan/science/physiological_bounds.py` | Physiological input validation |
| `titan/science/adaptive_priority_lock.py` | Adaptive Priority Lock (APL) + VLG |
| `titan/science/intensity_governor.py` | YELLOW/RED intensity gate |
| `titan/science/readiness_engine.py` | Composite readiness score |
| `titan/science/glycogen_model.py` | Glycogen debt estimation |
| `titan/science/fatigue_engine.py` | Fatigue classification |
| `titan/science/autonomic_engine.py` | Autonomic Fusion Index (AFI) |
| `titan/science/drift_engine.py` | Cardiac drift detection |
| `titan/science/durability_engine.py` | Durability analysis |
| `titan/science/efficiency_engine.py` | Running economy / efficiency |
| `titan/science/biomechanics.py` | Biomechanics analysis |
| `titan/science/critical_speed.py` | Critical speed tracker |
| `titan/science/lactate_logic.py` | Lactate threshold logic |
| `titan/science/rcp_engine.py` | Respiratory compensation point |
| `titan/science/adaptive_memory.py` | Athlete-specific memory/adaptation |
| `titan/science/ml_safety.py` | ML prediction safety gates (shadow mode) |
| `titan/science/load_prediction_shadow.py` | Shadow ML load prediction |
| `titan/science/data_trust.py` | Data quality trust scoring |
| `titan/science/data_sanity.py` | Input data sanity layer (ADR-0026) |
| `titan/science/rollback_gate.py` | Completion-rate calibration rollback gate (P27-04) |
| `titan/science/threshold_adapter.py` | Population-specific threshold adaptation |
| `titan/science/outcome_tracker.py` | Governance outcome recording |
| `titan/science/override_signal.py` | Human override signal handling |
| `titan/science/injury_risk_model.py` | Injury risk assessment |
| `titan/science/volume_load_gauge.py` | Volume load gauge |
| `titan/science/automated_periodization.py` | Automated periodization engine |

### Layer 4 — Orchestration

| Module | Role |
|---|---|
| `titan/orchestration/daily_coach.py` | `DailyCoach` v5.8 — 12-step morning pipeline |
| `titan/orchestration/coaching_pipeline.py` | Coaching pipeline helpers |
| `titan/orchestration/coaching_scheduler.py` | Scheduling for daily coaching routine |
| `titan/orchestration/contracts.py` | Typed contracts: `TitanContext`, `TitanContextContract`, `DecisionResult`, `PlannedEffect` |
| `titan/orchestration/engine_registry.py` | `EngineRegistry` — single construction site for all per-athlete science engines (ADR-0058) |
| `titan/orchestration/effect_bus.py` | `TitanEffectBus` — registry-based PlannedEffect dispatcher; no if/elif branches (ADR-0058 Phase B) |

### Layer 5 — Integrations, UI & API

| Module | Role |
|---|---|
| `titan/integrations/garmin_sync.py` | Garmin Connect API sync |
| `titan/integrations/biometric_router.py` | Routes biometric data to correct engine |
| `titan/integrations/biometric_source.py` | Biometric source abstraction |
| `titan/integrations/telegram_bot.py` | Telegram bot — coaching delivery + override UI |
| `titan/integrations/weather_api.py` | Weather API client |
| `titan/integrations/notification_gateway.py` | Notification abstraction |
| `titan/ui/menu_system.py` | Interactive CLI menu (main loop) |
| `titan/ui/operator_console.py` | Operator readiness / session explorer console |
| `titan/ui/setup_wizard.py` | In-UI credential setup |
| `titan/api/main.py` | FastAPI application |
| `titan/api/auth.py` | JWT authentication |
| `titan/api/dependencies.py` | FastAPI dependency injection |
| `titan/api/models.py` | Pydantic API models |
| `titan/features/nutrition_optimizer.py` | Nutrition plan generation |
| `titan/features/weekly_planner.py` | Weekly training plan generation |
| `titan/features/optimal_time_calculator.py` | Optimal training time calculation |
| `scripts/import_garmin_csv.py` | Offline Garmin CSV import |
| `scripts/import_activity_laps.py` | Activity lap data import |

---

## Critical Data Flows

### Training Load → CTL/ATL/TSB

```
training_log table (SQLite, training_load column)
  → DatabaseManager.get_training_load_history(days=400)   # CTL_DECAY_DAYS default
  → titan/main.py: tsb_engine.add_daily_load(date, load)  # hydration loop after DailyCoach init
  → TSBEngine.daily_loads: list[tuple[str, float]]
  → TSBEngine.calculate_ctl() / calculate_atl() / calculate_tsb()
  → ctx["tsb_engine"] / ctx["daily_coach"].tsb
  → DailyCoach Step 5: tsb_value, tsb_status = self.tsb.calculate_tsb()
  → menu_system: ctx["tsb_engine"] read in browser / display flows
```

> **⚠️ KNOWN ISSUE (TD-CTL-01):** `TSBEngine.daily_loads` is empty at UI render time despite
> successful DB hydration (15 rows confirmed in DB). All pipeline components verified
> individually. Root cause is an unknown state mutation between hydration and UI render.
> Registered 2026-05-20. See `TECHNICAL_DEBT.md` TD-CTL-01.

### Garmin Sync Flow

```
GarminSync.sync_all(days_back=14)
  → Garmin Connect API (garth library)
  → DatabaseManager: saves to training_log, sleep_log (daily_metrics), hrv_log (daily_metrics),
    weight_log (daily_metrics)
  → DailyCoach Step 1: garmin_data returned as GarminSyncResult
  → DailyCoach Step 2: _persist_garmin_data() writes to DB
  → DailyCoach Step 9: _feed_load_engines() reloads TSBEngine
```

### Daily Coaching Pipeline (DailyCoach.run_morning_routine)

```
Step  1 — sync_garmin:         GarminSync.sync_all()
Step  2 — persist_garmin:      _persist_garmin_data() → DB writes
Step  3 — feed_hrv_hrr:        HRVGuidedEngine.feed_hrv() + HRR data
Step  4 — compute_afi:         AutonomicEngine → Autonomic Fusion Index
Step  5 — calculate_tsb:       TSBEngine.calculate_tsb()
Step  6 — update_glycogen:     GlycogenModel.daily_debt → DB
Step  7 — analyze_readiness:   ReadinessEngine composite score
         (7.5) intensity_governor YELLOW/RED gate
Step  8 — load_today_session:  WeeklyPlanGenerator → today's session
Step  9 — apply_governance:    VLG + APL priority resolution → GovernanceEngine hard gates
Step 10 — calculate_optimal_time: weather + HRV → optimal training window
Step 11 — calculate_nutrition: NutritionOptimizer → fueling plan
Step 12 — send_telegram:       DecisionResult → PlannedEffect → TelegramBot delivery
```

### Athlete Profile Flow

```
.env file (TITAN_DATA_DIR)
  → UniversalAthleteProfile.from_env()
  → titan/main.py: passed to DailyCoach, GovernanceEngine, and all engines at init
  → ctx["athlete_profile"] (AthleteProfile TypedDict)
```

---

## Shared State — ctx dict

`TitanContext` is a `TypedDict` populated by `TitanContextContract.to_payload()` in
`titan/main.py`. All values are **references**, not copies — every engine and UI component
that reads from `ctx` shares the same live objects.

| Key | Type | Contents |
|---|---|---|
| `garmin` | `GarminSync` | Garmin sync client |
| `weather` | weather client | Weather API client |
| `telegram` | `TitanTelegramBot` | Telegram bot instance |
| `hrv_engine` | `HRVGuidedEngine` | HRV analysis engine |
| `tsb_engine` | `TSBEngine` | CTL/ATL/TSB engine (holds `daily_loads`) |
| `acwr_engine` | `ACWREngine` | ACWR calculation engine |
| `readiness_engine` | `ReadinessEngine` | Composite readiness scorer |
| `glycogen_model` | `GlycogenModel` | Glycogen debt model |
| `drift_engine` | `DriftEngine` | Cardiac drift engine |
| `lactate_logic` | `LactateLogic` | Lactate threshold engine |
| `trimp_engine` | `TRIMPEngine` | TRIMP engine |
| `fatigue_engine` | `FatigueEngine` | Fatigue classifier |
| `adaptive_memory` | `AdaptiveMemory` | Athlete adaptation memory |
| `biomechanics` | `BiomechanicsEngineProtocol` | Biomechanics engine |
| `efficiency_engine` | `EfficiencyEngine` | Running economy engine |
| `durability_engine` | `DurabilityEngine` | Durability engine |
| `critical_speed` | `CriticalSpeedEngine` | Critical speed tracker |
| `rcp_engine` | `RCPEngine` | Respiratory compensation point engine |
| `weekly_planner` | `WeeklyPlanGenerator` | Weekly plan generator |
| `optimal_time_calc` | `OptimalTimeCalculator` | Optimal training time calculator |
| `nutrition_optimizer` | `NutritionOptimizer` | Nutrition plan optimizer |
| `daily_coach` | `DailyCoach` | Main 12-step orchestrator |
| `db` | `DatabaseManager` | SQLite database manager |
| `athlete_profile` | `AthleteProfile` | Athlete profile dict |
| `last_garmin_data` | `Mapping[str, object]` | Last Garmin sync result |
| `last_weekly_plan` | `Mapping[str, object] \| None` | Last generated weekly plan |
| `today_session_type` | `str` | Today's session type string |

---

## Database Schema Summary

- **Backend:** SQLite at `~/Documents/TITAN/titan.db`
- **SCHEMA_VERSION:** 18 (tracked via `PRAGMA user_version`)
- **Connection class:** `titan/core/database.py:DatabaseManager`

> **⚠️ Always pass `db_dir` explicitly** when constructing `DatabaseManager`.
> The no-arg default resolves to `~/Documents/TITAN/` which may not be the
> production data directory in all environments.

Key tables:

| Table | Purpose |
|---|---|
| `training_log` | Training sessions — `training_load`, HR, RPE, duration, `athlete_id` |
| `daily_metrics` | Sleep, HRV, RHR, weight — one row per athlete per date |
| `governance_outcomes` | Governance decisions with lock codes and rationale |
| `athlete_threshold_offsets` | Per-athlete threshold overrides |
| `athletes` | Athlete registry (single-athlete: `athlete_id = 'owner'`) |
| `override_log` | Human override audit trail |
| `override_signals` | Active override signals |
| `gear_usage` | Equipment usage tracking |
| `personal_bests` | PR history |
| `cs_performances` | Critical speed performance samples |
| `coach_athlete_assignments` | Coach–athlete RBAC assignments |
| `coach_audit_log` | Coach access audit log |
| `activity_laps` | Lap-level activity breakdown |

---

## Known Architectural Gaps

| ID | Description | Priority |
|---|---|---|
| TD-CTL-01 | TSBEngine `daily_loads` empty at UI render despite 15 rows in DB. All pipeline components verified individually (hydration code correct, no exceptions). Root cause: unknown state mutation between hydration and UI render. | HIGH |
| TD-04 | DailyCoach god-orchestrator (~1747 LOC); violates single-responsibility; targeted by ADR-0018 kernel boundary split | HIGH |
| TD-08 | Schema defined in two places (database.py + Alembic migration path) | MED |
| TD-11 | No OTel / Prometheus metrics export; observability gap for production | HIGH |

See `TECHNICAL_DEBT.md` for the full register and phase execution sequences.

---

## ADR Index

Architecture Decision Records live in `docs/adr/`. Key decisions affecting the overall
architecture:

| ADR | Decision |
|---|---|
| 0006 | Cold start and engine sync hardening |
| 0017 | Composition root fan-in and DailyCoach god-orchestrator audit |
| 0018 | Kernel Boundary: Decision Pipeline / Effect Runner split |
| 0020 | Persistence Failure Behavioral Policy |
| 0022 | Phase 8 Entry Gate Review |
| 0023 | Physiological Input Validation Contract |
| 0027 | Hidden Inter-Module Coupling Prevention |
| 0033 | Physiological Model Aging and Multi-Athlete Architecture Protocol |
| 0040 | Athlete Identity Isolation |
| 0042 | Human Override as First-Class Invariant |
| 0044 | PostgreSQL migration as Phase 8A entry gate |
| 0046 | DailyCoach multi-athlete execution model |
| 0047 | Architecture Fitness Functions |
| 0051 | Missing Data Policy (Conservative-Fail) |
| 0054 | Coach-Athlete RBAC Scoping |
