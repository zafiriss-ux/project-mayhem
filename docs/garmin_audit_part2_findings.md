# Garmin Data-to-Action Pipeline Audit — Part 2 Findings

**Auditor:** Opus (Category-A deterministic audit)
**Date:** 2026-03-23
**Scope:** Infrastructure, science engines, and feature modules consuming Garmin data

---

## Batch 1: Advanced Metrics Engines

### Files Audited
- `titan/science/acwr_engine.py`
- `titan/science/glycogen_model.py`
- `titan/science/fatigue_engine.py`
- `titan/science/readiness_engine.py`

### Finding B1-F01: ACWREngine — Silent Division-by-Zero Masking via Falsy Check
**Severity:** MEDIUM
**Location:** `acwr_engine.py:20`
**Issue:** `if not chronic_28d_avg:` uses truthiness, which means `chronic_28d_avg = 0.0` (valid value meaning zero training) and `chronic_28d_avg = None` (missing data) are treated identically. Both return `(None, "INSUFFICIENT DATA", ...)`. While division by zero must be prevented, a zero chronic load with nonzero acute load is a real and dangerous scenario (infinite ACWR spike) that should produce a distinct HIGH RISK signal, not an "insufficient data" dismissal.
**Impact:** An athlete returning from complete rest (chronic=0) with a sudden acute load spike gets "INSUFFICIENT DATA" instead of an injury risk warning. The governance pipeline silently passes this through.
**Recommendation:** Explicitly check `if chronic_28d_avg is None:` for missing data, and `if chronic_28d_avg == 0.0:` for zero chronic load (return HIGH RISK or cap ACWR at a maximum value like 3.0).

### Finding B1-F02: ACWREngine — `injury_risk_score` Uses Hardcoded 1.15 Threshold
**Severity:** LOW
**Location:** `acwr_engine.py:48`
**Issue:** The `injury_risk_score` method uses a hardcoded `1.15` threshold for the Low-Moderate boundary, while all other boundaries use centralized `thresholds.py` constants. This is a Category-A migration miss from T5-17.
**Impact:** Threshold drift risk; inconsistency with centralized governance constants.
**Recommendation:** Extract `1.15` to `thresholds.py` as `ACWR_LOW_MODERATE_MAX`.

### Finding B1-F03: ReadinessEngine — No Null Guard on Garmin HRV/RHR Inputs
**Severity:** MEDIUM
**Location:** `readiness_engine.py:35-36`
**Issue:** `analyze_readiness` performs arithmetic directly on `today_hrv`, `baseline_hrv`, `today_rhr`, `baseline_rhr` with no null/None check. If any of these Garmin-sourced values are None (stale sync, sensor failure, bounds validation nulling), the engine raises `TypeError` at `hrv_diff = today_hrv - baseline_hrv`.
**Caller mitigation:** DailyCoach line 661 applies `today_rhr or 50` as a default, but no equivalent guard exists for `today_hrv`, `baseline_hrv`, or `baseline_rhr`. The `physiological_bounds.py` layer can null these values, which then propagate unguarded to ReadinessEngine.
**Impact:** Unhandled TypeError crashes the decision pipeline at Step 7.
**Recommendation:** Add explicit None checks with conservative defaults (e.g., assume baseline values when today's value is missing, producing a neutral readiness contribution).

### Finding B1-F04: DailyCoach — ACWR Default of 1.0 Masks Missing Garmin Data
**Severity:** HIGH
**Location:** `daily_coach.py:713`, `daily_coach.py:727`
**Issue:** `garmin_data.get('acwr', 1.0)` defaults to ACWR=1.0 (SWEET SPOT) when the ACWR field is absent from Garmin sync results. This means: if Garmin sync fails, times out, or returns incomplete data, the IntensityGovernor and VolumeLoadGauge see a perfectly healthy ACWR=1.0 and impose no load restrictions.
**Impact:** When Garmin data is stale or missing, the safety system sees a false "all clear" for ACWR. This is a zero-bypass violation — missing data should trigger conservative behavior, not optimistic defaults.
**Recommendation:** Default to `None` and let the governance gates treat None as "insufficient data → restrict intensity."

### Finding B1-F05: DailyCoach — drift_pct Default of 0.0 Masks Missing Drift Data
**Severity:** MEDIUM
**Location:** `daily_coach.py:708`
**Issue:** `garmin_data.get('drift_pct', 0.0)` defaults to zero drift when drift data is missing. Zero drift means "perfect cardiac efficiency," which bypasses the IntensityGovernor's drift-based YELLOW/RED gates entirely.
**Impact:** Missing drift data is treated as optimal performance rather than unknown status. IntensityGovernor drift gates (YELLOW at 3.5%, RED at 5.0%) never fire for athletes with missing drift data.
**Recommendation:** Default to `None` or a conservative sentinel value that triggers at least the YELLOW gate.

### Finding B1-F06: FatigueEngine — No Garmin Data Staleness Awareness
**Severity:** LOW
**Location:** `fatigue_engine.py:9-11`
**Issue:** `classify_fatigue` accepts boolean flags (`hr_suppression`, `rpe_mismatch`, `pace_hr_divergence`) without any freshness context. If Garmin data is 48h stale, these booleans derived from old data still drive fatigue classification as if current.
**Impact:** Stale fatigue signals could lead to overtraining or under-recovery recommendations.
**Note:** The DailyCoach does check `garmin_data_stale` at a higher level, but this flag doesn't influence the fatigue classification inputs themselves.

### Finding B1-F07: GlycogenDebtAccumulator — Stateful Object Not Protected Against Concurrent Access
**Severity:** LOW
**Location:** `glycogen_model.py:124-127`
**Issue:** `GlycogenDebtAccumulator` maintains mutable state (`daily_debt`, `debt_history`) with no threading protection. If the background Garmin sync thread triggers a debt update while the morning routine is reading `self.glycogen.daily_debt`, a race condition is possible.
**Mitigation:** DailyCoach creates its own accumulator instance (`self.glycogen = glycogen_accum or GlycogenDebtAccumulator()`), so the risk depends on whether multiple threads share the same DailyCoach instance.
**Impact:** Low probability, but data corruption path exists under concurrent access.

---

## Batch 2: Autonomic & Critical Speed Engines

### Files Audited
- `titan/science/autonomic_engine.py`
- `titan/science/critical_speed.py`
- `titan/science/rcp_engine.py`
- `titan/science/adaptive_memory.py`

### Finding B2-F01: CS_CONFIDENCE_LOCK — Default 1.0 Bypasses Lock When Tracker Is Missing
**Severity:** HIGH
**Location:** `governance_engine.py:149`
**Issue:** `confidence = getattr(cs_tracker, "confidence", 1.0)` defaults to confidence=1.0 (100%) when the cs_tracker object is None, has no confidence attribute, or was never calibrated. This means the CS_CONFIDENCE_LOCK gate (threshold 70%) is silently bypassed when no CS data exists.
**Impact:** An athlete with zero calibration data (no time-trials, intermittent Garmin sync) gets full confidence, enabling RACE_SIMULATION and TTE_PREDICTION features that depend on an uncalibrated CS model. Predictions will be meaningless or dangerous.
**Recommendation:** Default to `0.0` (no confidence) when cs_tracker is missing or has no confidence attribute. Missing data should lock, not unlock.

### Finding B2-F02: CriticalSpeedTracker — Thermal Degradation Ignores Dew Point
**Severity:** MEDIUM
**Location:** `critical_speed.py:218-234`
**Issue:** `apply_thermal` only considers dry-bulb temperature (`temp_c`). It does not account for dew point or humidity, which significantly affect heat stress and running performance. The Jones & Doust (1997) model is cited, but that study used controlled lab conditions. Real-world thermal stress is a function of both temperature and humidity (as acknowledged by the ESI model in `thresholds.py`).
**Impact:** On a 22°C day with 95% humidity (dew point 21°C), the degradation factor is the same as a 22°C day with 30% humidity (dew point 4°C). The CS estimate may be 5-8% too optimistic in humid conditions.
**Recommendation:** Integrate dew-point-based ESI into the thermal degradation model, or at minimum apply an additive humidity correction factor.

### Finding B2-F03: AutonomicFusionEngine — HRR z-score Returns 0.0 for Sparse Data
**Severity:** MEDIUM
**Location:** `autonomic_engine.py:76-77`
**Issue:** `_hrr_zscore` returns `0.0` (neutral) when fewer than 3 HRR records exist. Combined with the AFI weight of 0.35 for HRR, this means the AFI calculation silently drops 35% of its signal weight when Garmin HRR data is sparse or intermittent (common during the first weeks of use or after device changes).
**Impact:** AFI is inflated toward "healthy" because 35% of the composite signal contributes zero (neutral) rather than being flagged as low-confidence. The parasympathetic guard also cannot fire because `hrr_impaired` requires `len(self.hrr_log) >= 3`.
**Recommendation:** When HRR data is insufficient, either (a) redistribute the HRR weight to other signals proportionally, or (b) apply a confidence penalty to the AFI output that downstream consumers (readiness clamp) can act on.

### Finding B2-F04: AutonomicFusionEngine — Unbounded _afi_history Growth
**Severity:** LOW
**Location:** `autonomic_engine.py:145`
**Issue:** `self._afi_history.append(afi_today)` grows unboundedly. Only the last 2 entries are ever used (for the 48h buffer), but the list is never trimmed.
**Impact:** Memory leak over long-running sessions. Minimal practical impact given daily granularity, but violates clean resource management.
**Recommendation:** Trim to last 2 entries after each append.

### Finding B2-F05: RCPEngine — No Garmin Data Freshness or Quality Checks
**Severity:** LOW
**Location:** `rcp_engine.py:42-74`
**Issue:** `estimate_rcp_from_progressive_test` accepts raw pace/HR/RPE segments with no validation that the data came from a recent or properly-structured field test. Stale Garmin segments from weeks-old activities could be passed in.
**Impact:** RCP estimates could be based on outdated physiological state, leading to incorrect zone prescriptions.
**Note:** This is a data-provenance concern rather than a mathematical bug.

### Finding B2-F06: CriticalSpeedTracker — Confidence Recency Uses `datetime.now()` Without Timezone
**Severity:** LOW
**Location:** `critical_speed.py:211`
**Issue:** `days_since = (datetime.now() - latest).days` uses naive `datetime.now()` while comparing against ISO-format dates that may or may not include timezone info. If `datetime.fromisoformat(d)` returns a timezone-aware datetime and `datetime.now()` returns naive, this raises a `TypeError`.
**Impact:** Confidence calculation crash if timezone-aware dates are ever passed in.
**Recommendation:** Use `datetime.now(tz=datetime.timezone.utc)` consistently, or strip timezone from stored dates.

### Finding B2-F07: AdaptiveMemory — Stateful Session History Not Persisted
**Severity:** LOW
**Location:** `adaptive_memory.py:34-42`
**Issue:** `AdaptiveMemory` stores all state in-memory (`session_history`, `last_quality_sessions`, `last_3d_soreness`). If the DailyCoach process restarts, all adaptive memory is lost. The `session_density_index` and `mechanical_load_risk` methods produce incorrect results until enough sessions are re-logged.
**Impact:** After any restart, SDI returns "Not enough data" and monotony checks are ineffective. This is partially mitigated by DailyCoach hydrating from DB on startup, but the adaptive memory reconstruction path is not audited as complete.

---

## Batch 3: Planning & Optimization Modules

### Files Audited
- `titan/features/weekly_planner.py`
- `titan/features/optimal_time_calculator.py`
- `titan/features/nutrition_optimizer.py`

### Finding B3-F01: WeeklyPlanGenerator — Static Plans Ignore Garmin's 6h Sync Interval
**Severity:** MEDIUM
**Location:** `weekly_planner.py:237-362`
**Issue:** The `_generate_*_week` methods produce completely static, hardcoded plans (fixed distances, fixed session types per day). The plan structure is not adjusted based on the athlete's current ACWR, CTL/ATL, recent training load, or Garmin sync data. The only dynamic adjustments are post-hoc HRV downgrades (`_apply_hrv_adjustments`) and weather window hints (`_apply_weather_adjustments`).
**Impact:** The 7-day plan is generated once (Sunday 20:00 cron) and cached in `self.last_plan`. If Garmin syncs significant new data (e.g., a hard race) between plan generation and mid-week execution, the plan is not re-evaluated. The `get_today_session` method always returns from the stale plan.
**Recommendation:** At minimum, add a mid-week plan re-evaluation trigger when Garmin sync delivers significant deviations (e.g., ACWR spike, TSB drop > 10 points).

### Finding B3-F02: WeeklyPlanGenerator — HRV Adjustment Uses Raw Values Without Bounds Check
**Severity:** LOW
**Location:** `weekly_planner.py:366-378`
**Issue:** `_apply_hrv_adjustments` compares `latest < baseline - 10` using raw HRV values from `hrv_engine.get_hrv_summary()`. There is no null check — if `baseline` or `latest_hrv` is `None` (engine not hydrated, Garmin data missing), the comparison raises `TypeError`.
**Impact:** Weekly plan generation crashes if HRV data is unavailable.
**Recommendation:** Add None guards: `if baseline is not None and latest is not None and latest < baseline - 10:`.

### Finding B3-F03: OptimalTimeCalculator — TSB Adjustment Uses Truthiness (`if tsb_value`)
**Severity:** LOW
**Location:** `optimal_time_calculator.py:90`
**Issue:** `if tsb_value:` skips TSB adjustments when `tsb_value = 0.0` (perfectly balanced TSB). While TSB=0 doesn't need special handling, this is a truthiness anti-pattern that could mask issues if TSB calculation returns `0` when data is incomplete.
**Impact:** Minor — TSB=0 is a neutral state, but the pattern is inconsistent with explicit `None` checking used elsewhere.

### Finding B3-F04: NutritionOptimizer — Dew Point Default of 15°C Masks Missing Weather Data
**Severity:** MEDIUM
**Location:** `nutrition_optimizer.py:188`
**Issue:** `today_session.get("dew_point", 15)` defaults to 15°C (sticky threshold) when dew point is missing from the session dict. This produces hydration recommendations for "sticky" conditions (650 ml/h) even when no weather data exists.
**Impact:** In hot, humid environments where weather API fails, athletes receive underestimated hydration recommendations. In cool environments, they receive overestimated ones. The default should reflect "unknown" conditions, not a specific weather state.
**Recommendation:** When dew point is missing, return hydration with a "weather data unavailable — using conservative estimate" flag and default to the higher hydration band (800 ml/h) as the safe choice.

### Finding B3-F05: NutritionOptimizer — `analyze_weight_trend` Called Twice Per Plan
**Severity:** LOW (performance)
**Location:** `nutrition_optimizer.py:202`, `nutrition_optimizer.py:316`
**Issue:** `calculate_daily_nutrition` calls `self.analyze_weight_trend()` at line 202 (for the plan payload) and `_get_special_notes` calls it again at line 316. Both are full scans of `self.weight_history`. No caching.
**Impact:** Minor performance waste. No correctness impact.

### Finding B3-F06: WeeklyPlanGenerator — Plan Uses `datetime.now()` for Day Lookup
**Severity:** LOW
**Location:** `weekly_planner.py:69`
**Issue:** `today_name = datetime.now().strftime("%A")` uses local system time without timezone awareness. If the system clock is in UTC but the athlete is in UTC+3 (Athens), the plan could return tomorrow's session instead of today's near midnight.
**Impact:** Athlete could receive wrong day's session in edge cases around midnight.

---

## Batch 4: Interface & Core Modules

### Files Audited
- `titan/integrations/telegram_bot.py`
- `titan/core/athlete.py`
- `titan/core/equipment.py`
- `titan/utils/math_core.py`
- `titan/core/database.py` (read-path lock audit)

### Finding B4-F01: TelegramBot — Command Callbacks Execute Without Thread Safety
**Severity:** MEDIUM
**Location:** `telegram_bot.py:152-231`
**Issue:** Telegram command handlers (e.g., `/today`, `/sync`, `/stats`) invoke `self.cmd_callbacks["today"]()` directly from the polling thread. These callbacks typically call into DailyCoach methods which read from `self.glycogen.daily_debt`, HRV engine state, and other mutable objects. If the background Garmin sync thread is updating the same DailyCoach state concurrently, the callback reads stale or partially-updated data.
**Impact:** Telegram users may receive inconsistent or partially-computed results when commands coincide with background sync operations.
**Recommendation:** Ensure command callbacks either acquire a shared lock or operate on snapshot copies of engine state.

### Finding B4-F02: TelegramBot — /sync Command Blocks Polling Thread
**Severity:** MEDIUM
**Location:** `telegram_bot.py:192-199`
**Issue:** The `/sync` command handler calls `self.cmd_callbacks["sync"]()` synchronously in the polling thread. Garmin sync is a network operation that can take 10-60 seconds. During this time, the polling thread is blocked and no other Telegram commands are processed.
**Impact:** All Telegram commands are unresponsive during a manual sync operation.
**Recommendation:** Execute sync callback in a separate thread or use `threading.Thread(target=...)`.

### Finding B4-F03: MathCore — `weight_function_Wf` Uses Hardcoded Weight Thresholds
**Severity:** LOW
**Location:** `math_core.py:40-50`
**Issue:** `weight_function_Wf` uses hardcoded weight thresholds (74.5 kg panic, 75.0 kg floor, 75.5 kg safe zone) that are specific to one athlete. While `weight_function_from_profile` exists as a profile-aware alternative, the original `weight_function_Wf` is still present and may be called by legacy paths.
**Note:** This is a known legacy pattern. The profile-aware version at line 168 is the correct implementation.

### Finding B4-F04: MathCore — `system_status_SSV` Uses Hardcoded Weight 75.0 kg
**Severity:** LOW
**Location:** `math_core.py:97`
**Issue:** `weight < 75.0` is hardcoded in the system status validator. This should use the athlete's target weight from their profile. No profile-aware variant of `system_status_SSV` exists.
**Impact:** Multi-athlete support (Phase 9) will require refactoring this method.

### Finding B4-F05: UniversalAthleteProfile — BMR/TDEE Return Hardcoded Values
**Severity:** LOW
**Location:** `athlete.py:189`, `athlete.py:216`
**Issue:** `calculate_bmr()` returns `2020` and `calculate_tdee()` returns `2800` unconditionally, ignoring the athlete's actual demographics. The Mifflin-St Jeor formulas are commented out. Meanwhile, `NutritionOptimizer.calculate_daily_nutrition` independently calculates BMR using the same formula (line 142), creating a divergence where Telegram-reported BMR/TDEE differs from nutrition plan calculations.
**Impact:** If any consumer calls `athlete.calculate_bmr()` expecting a dynamic value, they get a hardcoded number. The nutrition optimizer bypasses this entirely.

### Finding B4-F06: DatabaseManager — Read Paths Properly Locked (T1-06 CLEAR)
**Severity:** N/A (Positive finding)
**Location:** `database.py` (all `get_*` methods)
**Issue:** All read paths in DatabaseManager consistently use `with self._lock:` before database access. The lock is an `RLock()` (reentrant), supporting nested transaction paths. `check_same_thread=False` is set on the SQLite connection, and the lock serializes access. The T1-06 race condition concern for DatabaseManager read paths is adequately mitigated at the database layer.
**Note:** However, the race condition exposure shifts to engine-level state (see B4-F01) — the DB reads are safe, but the in-memory engine state derived from those reads is not protected.

### Finding B4-F07: EquipmentManager — In-Memory State Not Synchronized with Garmin
**Severity:** LOW
**Location:** `equipment.py:27-53`
**Issue:** `EquipmentManager` maintains a hardcoded demo shoe database. `update_mileage()` only updates in-memory state. If Garmin Connect syncs activity data with shoe associations, there is no integration path to update the EquipmentManager's mileage counters.
**Impact:** Shoe mileage tracking drifts from reality unless manually updated.

---
