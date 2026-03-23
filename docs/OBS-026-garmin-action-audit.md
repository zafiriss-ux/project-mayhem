# OBS-026: Garmin Data-to-Action Pipeline Audit (Part 2)

**Date:** 2026-03-23
**Auditor:** Opus (Category-A deterministic audit)
**Scope:** Infrastructure, science engines, and feature modules consuming Garmin data
**Status:** REVIEW_REQUESTED
**Priority:** BLOCKING

---

## 1. Executive Summary

This audit covers the full Garmin data-to-action pipeline beyond the initial sync layer (OBS-025). It traces how Garmin-sourced metrics flow through 16 modules across 4 architectural layers (science engines, governance, features, interface) and identifies **27 findings** across 4 batches.

**Critical pattern:** The system's dominant failure mode is **optimistic defaulting** — when Garmin data is missing, stale, or null, the pipeline substitutes values that indicate "healthy" or "optimal" states. This systematically bypasses safety gates that were designed to be conservative.

**Severity distribution:**
- HIGH: 2 (B1-F04 ACWR default, B2-F01 CS confidence default)
- MEDIUM: 8
- LOW: 16
- POSITIVE: 1 (B4-F06 DB lock audit clear)

---

## 2. HIGH Severity Findings — Zero-Bypass Violations

### H-1: ACWR Default of 1.0 Masks Missing Garmin Data (B1-F04)
**Location:** `daily_coach.py:713, 727`
`garmin_data.get('acwr', 1.0)` defaults to ACWR=1.0 (SWEET SPOT) when Garmin sync fails or returns incomplete data. IntensityGovernor and VolumeLoadGauge see "all clear" when they should see "unknown."

**Fix:** Default to `None`. Update IntensityGovernor and VLG to treat `None` ACWR as YELLOW gate trigger (conservative restriction).

### H-2: CS_CONFIDENCE_LOCK Bypassed When Tracker Is Missing (B2-F01)
**Location:** `governance_engine.py:149`
`getattr(cs_tracker, "confidence", 1.0)` defaults to 100% confidence when cs_tracker is None or uncalibrated. CS_CONFIDENCE_LOCK (70% threshold) never fires.

**Fix:** Default to `0.0`. Missing calibration data must lock race simulation and TTE prediction.

---

## 3. Optimistic Default Pattern — Systemic Analysis

| Location | Field | Default | Meaning | Should Be |
|----------|-------|---------|---------|-----------|
| `daily_coach.py:713` | `acwr` | `1.0` | Sweet spot | `None` → restrict |
| `daily_coach.py:708` | `drift_pct` | `0.0` | Perfect efficiency | `None` → YELLOW |
| `daily_coach.py:661` | `today_rhr` | `50` via `or` | Normal RHR | Explicit None guard |
| `governance_engine.py:149` | `confidence` | `1.0` | Full confidence | `0.0` → lock |
| `autonomic_engine.py:120` | `hrr_norm` | `0.0` | Neutral | Confidence penalty |
| `nutrition_optimizer.py:188` | `dew_point` | `15` | Sticky weather | Conservative band |

**Root cause:** No project-wide convention for "missing Garmin data" semantics. Each module independently chooses a default, and all choose optimistic ones.

**Recommendation:** Establish a canonical `MISSING_DATA_POLICY` constant or enum in `thresholds.py` that encodes the rule: "Missing data → conservative assumption, never optimistic."

---

## 4. Null Propagation Crash Paths

### Path 1: ReadinessEngine TypeError (B1-F03)
`physiological_bounds.validate_and_clamp()` can null `hrv_ms` → DailyCoach passes null `latest_hrv` to `ReadinessEngine.analyze_readiness()` → `hrv_diff = today_hrv - baseline_hrv` raises `TypeError`.

### Path 2: WeeklyPlanner HRV TypeError (B3-F02)
`hrv_engine.get_hrv_summary()` returns `None` for `baseline` or `latest_hrv` → `_apply_hrv_adjustments` compares `latest < baseline - 10` → `TypeError`.

**Both paths are unguarded and will crash the decision pipeline.**

---

## 5. Garmin 6h Sync Interval Impact on Features

| Module | Impact | Severity |
|--------|--------|----------|
| `WeeklyPlanGenerator` | Plan generated Sunday 20:00 is static all week. Mid-week Garmin data (race, illness) doesn't trigger re-evaluation. | MEDIUM |
| `OptimalTimeCalculator` | Uses live weather data (1h cache), but TSB/readiness inputs are from last Garmin sync (up to 6h stale). | LOW |
| `NutritionOptimizer` | Weight trend analysis depends on `add_weight_entry()` calls. If weight isn't synced from Garmin, trend data is empty → "INSUFFICIENT_DATA" for days. | LOW |
| `FatigueEngine` | Boolean flags derived from Garmin data have no freshness metadata. 48h stale flags drive fatigue classification as if current. | LOW |

---

## 6. Thread Safety Assessment

| Component | Lock Status | Risk |
|-----------|-------------|------|
| `DatabaseManager` (all read/write paths) | `RLock()` — consistent | **CLEAR** |
| `GlycogenDebtAccumulator` | No lock — mutable `daily_debt` | LOW (isolated instances) |
| `AutonomicFusionEngine` | No lock — mutable `_afi_history`, `hrr_log` | LOW (single-thread access pattern) |
| `AdaptiveMemory` | No lock — mutable session lists | LOW (not shared across threads) |
| `TelegramBot` command callbacks | Execute in poll thread — read engine state | **MEDIUM** (reads during sync) |
| `TelegramBot` /sync handler | Blocks poll thread synchronously | **MEDIUM** (all commands blocked) |

**T1-06 assessment:** DatabaseManager read paths are properly serialized via `RLock()`. The race condition risk has shifted from the DB layer to the engine-state layer, where Telegram callbacks read in-memory engine state while background sync may be updating it.

---

## 7. CS_CONFIDENCE_LOCK Verification (Intermittent Garmin Data)

**Scenario:** Athlete has sparse Garmin data — only 2 time-trial performances, last one 45 days ago.

**Expected behavior:** CS confidence should be low (~30%), triggering CS_CONFIDENCE_LOCK.

**Actual behavior:**
1. `CriticalSpeedTracker._update_confidence()` correctly computes: `n_score = min(2/5, 1.0) * 0.5 = 0.20`, `recency_score = max(0, 1 - 45/42) * 0.5 = 0.0` → `confidence = 0.20` (20%)
2. BUT: If `cs_tracker` is never instantiated or passed as `None`, `getattr(cs_tracker, "confidence", 1.0)` returns `1.0` → lock bypassed entirely.

**Verdict:** The tracker math is correct. The governance integration is broken for the "no tracker" case.

---

## 8. V1–V5 VO2 Eligibility Gate Verification

**Thresholds from `thresholds.py`:**
- V1: `VO2_ACWR_MIN = 0.80` ≤ ACWR ≤ `VO2_ACWR_MAX = 1.30`
- V2: Readiness ≥ `VO2_READINESS_MIN = 65.0`
- V3: Glycogen debt ≤ `VO2_GLYCOGEN_DEBT_MAX = 7.0`
- V4: Days since last VO2 ≥ `VO2_MIN_DAYS_SINCE_LAST = 2`
- V5: No active hard stops

**Interaction with B1-F04 (ACWR default):** When ACWR defaults to 1.0 due to missing Garmin data, V1 gate passes (1.0 is within [0.80, 1.30]). Combined with optimistic readiness defaults, the VO2 eligibility gate can pass when it should fail due to insufficient data.

**Recommendation:** V1 gate should explicitly reject `None` ACWR as ineligible.

---

## 9. Thermal Degradation Math Audit

### CriticalSpeedTracker.apply_thermal() (critical_speed.py:218-234)
- Formula: `factor = max(0.85, 1.0 - 0.025 * (temp_c - 20) / 5)`
- At 30°C: factor = 1.0 - 0.025 * 2 = 0.95 (5% degradation) ✓
- At 40°C: factor = 1.0 - 0.025 * 4 = 0.90 (10% degradation) ✓
- At 50°C: factor = max(0.85, 1.0 - 0.025 * 6) = 0.85 (floor) ✓
- **Math is correct for dry-bulb temperature.**

### Missing: Humidity/dew-point correction (B2-F02)
- The ESI model exists in `thresholds.py` (`ESI = temp_c + 0.5 * dew_point_c`) and is used in DailyCoach for pace adjustments.
- But `apply_thermal` doesn't use ESI — it only uses dry-bulb temperature.
- **Gap:** A 25°C day with 90% humidity (dew point 23°C) has ESI = 36.5 (extreme), but thermal degradation is only 2.5% (moderate).

### GlycogenDebtAccumulator.electrolyte_guard() (glycogen_model.py:255-289)
- Trigger: dew_point > 18°C AND duration > 60min AND quality session
- Sweat rate: `800 + (dew_point - 18) * 40` ml/hr
- At dew_point 24°C: 800 + 240 = 1040 ml/hr ✓
- Sodium: `total_sweat * 0.75` mg ✓ (within Cheuvront range)
- **Math is correct.**

---

## 10. Recommended Actions (Priority Order)

| # | Finding | Action | Tier |
|---|---------|--------|------|
| 1 | H-1 (B1-F04) | Change ACWR default from 1.0 to None; update IG/VLG for None handling | T1 |
| 2 | H-2 (B2-F01) | Change CS confidence default from 1.0 to 0.0 | T1 |
| 3 | B1-F03 | Add None guards in ReadinessEngine.analyze_readiness | T1 |
| 4 | B1-F05 | Change drift_pct default from 0.0 to None; update IG for None | T2 |
| 5 | B2-F03 | Add AFI confidence degradation for sparse HRR data | T2 |
| 6 | B3-F04 | Change dew_point default in NutritionOptimizer; add "unknown" flag | T2 |
| 7 | B2-F02 | Integrate ESI into CriticalSpeedTracker.apply_thermal | T2 |
| 8 | B3-F01 | Add mid-week plan re-evaluation trigger on significant Garmin data | T3 |
| 9 | B4-F01 | Add lock/snapshot for Telegram command callbacks | T3 |
| 10 | B4-F02 | Execute /sync in background thread | T3 |
| 11 | Systemic | Establish MISSING_DATA_POLICY convention in thresholds.py | T2 |
| 12 | B1-F02 | Extract hardcoded 1.15 to thresholds.py | T4 |
| 13 | B3-F02 | Add None guards in _apply_hrv_adjustments | T2 |

---

*Full per-batch findings: [docs/garmin_audit_part2_findings.md](garmin_audit_part2_findings.md)*
