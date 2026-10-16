"""Centralized governance and safety thresholds."""

HARD_STOP_HRV_DELTA = 15.0
# H2 also fires on a drop of this fraction of the baseline, whichever comes first (ADR-0064).
# 30% equals 15 ms at a 50 ms baseline, so it only tightens H2 below that baseline.
HARD_STOP_HRV_DROP_PCT = 0.30
HARD_STOP_RHR_DELTA = 8.0
HARD_STOP_TSB_FLOOR = -50.0
ILLNESS_PATTERN_HRV_DELTA = 20.0
ILLNESS_PATTERN_RHR_DELTA = 10.0

# HRV rolling-baseline drift detector (HD-01 / INV-06 / T5-07).
# Fires when the mean of the most-recent window diverges from the prior anchor
# by more than this amount. Catches gradual multi-day deterioration that the
# per-cycle HARD_STOP_HRV_DELTA check would miss.
HRV_DRIFT_THRESHOLD_MS = 8.0

SUBJECTIVE_FATIGUE_EXTREME = 8
SUBJECTIVE_FATIGUE_2OF4 = 6

# Banister CTL/ATL EMA windows.
CTL_DECAY_DAYS = 42
ATL_DECAY_DAYS = 7

# VO2 gate thresholds.
# Notes:
# - ACWR upper bound is kept conservative at 1.30 for quality/high-intensity work,
#   aligned with contemporary load-management practice favoring tighter control of
#   acute spikes vs the older 1.50 ceiling.
# - Readiness floor is set at 65 to avoid prescribing VO2 intensity on borderline
#   recovery days.
VO2_ACWR_MIN = 0.80
VO2_ACWR_MAX = 1.30
VO2_READINESS_MIN = 65.0
VO2_GLYCOGEN_DEBT_MAX = 7.0
VO2_MIN_DAYS_SINCE_LAST = 2

# Environmental Stress Index (ESI) thresholds — T5-14.
# Composite score model: score = temperature_c + 0.5 * dew_point_c
ESI_MODERATE_MIN = 16.0
ESI_HIGH_MIN = 22.0
ESI_EXTREME_MIN = 28.0

# ESI missing-data fallback for dew_point — T5-68 / ADR-0034 / ADR-0051.
# When dew_point is absent from weather data, assume 18.0°C (lower boundary of
# "uncomfortable" band per WEATHER_DEW_POINT_UNCOMFORTABLE_MIN_C).  Using 12.0°C
# (comfortable) would underestimate thermal stress; the conservative-fail
# principle (ADR-0051) requires we err toward higher perceived heat load.
ESI_DEW_POINT_FALLBACK_C = 18.0

ESI_PACE_ADJUSTMENT_MODERATE_SEC_PER_KM = 8
ESI_PACE_ADJUSTMENT_HIGH_SEC_PER_KM = 15
ESI_PACE_ADJUSTMENT_EXTREME_SEC_PER_KM = 25

# ACWR engine thresholds — T5-17 (Category A only).
ACWR_SEVERE_DETRAINING_MAX = 0.5
ACWR_DETRAINING_RISK_MAX = 0.8
ACWR_MAINTENANCE_MAX = 1.0
ACWR_SWEET_SPOT_MAX = 1.3
ACWR_MODERATE_RISK_MAX = 1.5
ACWR_HIGH_RISK_MAX = 1.7

# AdaptiveMemory thresholds — T5-18 (Category A only).
ADAPTIVE_MEMORY_EASY_PACE_DROP_MULTIPLIER = 1.08
ADAPTIVE_MEMORY_HOURS_24 = 24
ADAPTIVE_MEMORY_HOURS_36 = 36
ADAPTIVE_MEMORY_HOURS_48 = 48
ADAPTIVE_MEMORY_HOURS_72 = 72

# DurabilityEngine thresholds — T5-27 (Category A only).
DURABILITY_PACE_DECAY_EXCELLENT_MAX = 2
DURABILITY_PACE_DECAY_GOOD_MAX = 5
DURABILITY_PACE_DECAY_MODERATE_MAX = 8
DURABILITY_INDEX_DEVELOPING_MIN = 85
DURABILITY_INDEX_COMPETITIVE_MIN = 90
DURABILITY_INDEX_ELITE_MIN = 95
DURABILITY_INDEX_WORLD_CLASS_MIN = 98
DURABILITY_PROTOCOL_BASE_BUILD_MAX = 88
DURABILITY_PROTOCOL_MAINTENANCE_MAX = 93
DURABILITY_PROTOCOL_STRONG_MAX = 96

# FatigueEngine thresholds — T5-28 (Category A only).
FATIGUE_SORENESS_PERIPHERAL_MIN = 5

# LactateLogic thresholds — T5-32 (Category A only).
LACTATE_LT1_MAX_DRIFT_PCT = 3.0
LACTATE_LT1_MAX_HR_PCT = 78.0
LACTATE_LT2_MIN_RPE = 6.0
LACTATE_LT2_MAX_RPE = 7.0

# IntensityGovernor thresholds — T5-31 (Category A only).
INTENSITY_GOVERNOR_DRIFT_YELLOW = 3.5
INTENSITY_GOVERNOR_DRIFT_RED = 5.0
INTENSITY_GOVERNOR_GLYCOGEN_YELLOW = 4.0
INTENSITY_GOVERNOR_GLYCOGEN_RED = 6.0
INTENSITY_GOVERNOR_ACWR_YELLOW = 1.3
INTENSITY_GOVERNOR_ACWR_RED = 1.5
INTENSITY_GOVERNOR_READINESS_YELLOW = 55.0
INTENSITY_GOVERNOR_READINESS_RED = 40.0

# Conservative volume modifier when intensity gate fires but modifier is absent — ADR-0051.
INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE = 0.7  # Conservative volume reduction when modifier absent (ADR-0051)
# A session downgraded by a gate without its own modifier (2of4, hard stops, VO2, fueling)
# keeps INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE of its volume and at most this long (ADR-0065).
GOVERNANCE_DOWNGRADE_MAX_DURATION_MIN = 60
# SLEEP_DEBT_NIGHTS nights in a row with a sleep score under SLEEP_DEBT_SCORE_MAX make the day EASY
# with INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE of its volume (SV-16 / ADR-0066). The score limit
# is the one of the 2-of-4 sleep indicator (I2) in governance_engine.
SLEEP_DEBT_NIGHTS = 3
SLEEP_DEBT_SCORE_MAX = 60

# WeeklyPlanGenerator volume (SV-14 / D-062): the week follows the athlete's average km per week
# over the last PLANNER_VOLUME_WINDOW_DAYS, plus at most PLANNER_WEEKLY_KM_GROWTH_MAX; with no runs
# in that window the BUILD week is PLANNER_DEFAULT_WEEKLY_KM.
PLANNER_VOLUME_WINDOW_DAYS = 28
PLANNER_WEEKLY_KM_GROWTH_MAX = 0.10
PLANNER_DEFAULT_WEEKLY_KM = 30.0

# VolumeLoadGauge thresholds — T5-35 (Category A only).
VLG_TSB_YELLOW_MIN = -30.0
VLG_ACWR_RED_MIN = 0.7
VLG_ACWR_YELLOW_MIN = 0.8
VLG_ACWR_YELLOW_MAX = 1.3
VLG_ACWR_RED_MAX = 1.5
VLG_GLYCOGEN_YELLOW_MIN = 4.0
VLG_GLYCOGEN_RED_MIN = 7.0

# GovernanceEngine thresholds — T5-30 (Category A only).
GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD = 0.80
GOVERNANCE_CS_CONFIDENCE_THRESHOLD = 0.70
# Cold-start: no outcome history → default-deny override lockdown (TD-03).
OVERRIDE_LOCKDOWN_COLD_START_DEFAULT = True

# WeatherAPI dew-point decision bands — T5-41 (Category A only).
WEATHER_DEW_POINT_EXTREME_MIN_C = 24.0
WEATHER_DEW_POINT_OPPRESSIVE_MIN_C = 21.0
WEATHER_DEW_POINT_UNCOMFORTABLE_MIN_C = 18.0
WEATHER_DEW_POINT_STICKY_MIN_C = 15.0
WEATHER_DEW_POINT_COMFORTABLE_MIN_C = 12.0
WEATHER_DEW_POINT_PLEASANT_MIN_C = 8.0

# Data freshness thresholds — ADR-0026 / T1-19.
# Hours since last Garmin sync before the system emits warnings or degrades confidence.
STALE_DATA_WARN_HOURS = 24        # Emit data_freshness_warn structured log event
STALE_DATA_HARD_CEILING_HOURS = 72  # Emit data_confidence_low advisory (T2-10 mechanism)

# Garmin source freshness gate — T1-20 / ADR-0030.
GARMIN_DATA_MAX_AGE_HOURS = 26

# Garmin API degradation threshold — ADR-0050 / T5-12 Pass 2.
# Consecutive sync failures before the system treats degradation as non-transient.
GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT = 3

# OutcomeTracker feedback-loop guardrails — ADR-0035 / T1-22.
OUTCOME_INDEPENDENCE_WINDOW_DAYS = 2
CALIBRATION_MAX_THRESHOLD_DELTA_PCT = 0.10
CALIBRATION_MIN_OUTCOME_COUNT = 10

# Unified data trust thresholds — ADR-0041 / T1-23.
GARMIN_DATA_SUSPECT_AGE_HOURS = 12
WEATHER_DATA_SUSPECT_AGE_HOURS = 2

# Operator trust-drift monitor — ADR-0038 / T2-16.
OPERATOR_TRUST_DRIFT_WARNING_RATE_30D = 0.25

# API rate-limiter key ceiling — HD-05 / OBS-038.
# Upper bound on the number of (user_id, role, endpoint) tuples retained in the
# in-process rate-limiter. Prevents unbounded memory growth when many unique
# authenticated identities hit distinct endpoints (or when tokens rotate).
# Eviction policy: LRU (least-recently-used key is dropped first).
RATE_LIMITER_MAX_KEYS = 10_000

# Hard-stop gate exclusion set — ADR-0052 Stage 1.
# Threshold keys corresponding to H2–H5 safety gates that are permanently
# excluded from per-athlete adaptation via ThresholdAdapter (Stage 2+).
# Key names match the canonical constant names used in governance_engine.py:
#   HARD_STOP_HRV_DELTA        → H2 HRV collapse gate
#   HARD_STOP_RHR_DELTA        → H3 RHR spike gate
#   HARD_STOP_TSB_FLOOR        → H4 TSB critical-floor gate
#   SUBJECTIVE_FATIGUE_EXTREME → H5 extreme subjective fatigue gate
#
# H1 (injury_flag) is a boolean context input — not a numeric threshold.
# It cannot appear in athlete_threshold_offsets (which stores REAL delta_value)
# and is therefore excluded by type, not by this guard.
HARD_STOP_THRESHOLD_KEYS: frozenset[str] = frozenset({
    "HARD_STOP_HRV_DELTA",
    "HARD_STOP_HRV_DROP_PCT",
    "HARD_STOP_RHR_DELTA",
    "HARD_STOP_TSB_FLOOR",
    "SUBJECTIVE_FATIGUE_EXTREME",
})

# ── ADR-0052 — ThresholdAdapter (Phase 9) ────────────────────────────────────
THRESHOLD_ADAPTER_DAMPING_PCT: float = 0.05        # ±5% δT change per adaptation cycle
THRESHOLD_ADAPTER_MAX_DELTA_PCT: float = 0.20      # |δT| ceiling: ±20% of base value
THRESHOLD_ADAPTER_FALSE_NEG_WINDOW_DAYS: int = 30  # circuit breaker look-back window
THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT: float = 0.20  # 20% false-neg rate → breaker active

# ── P27-04 — Calibration rollback gate ───────────────────────────────────────
# Minimum completion-rate drop (in percentage points) over the 30-day pre/post
# calibration window that triggers a rollback recommendation.
# Aligned with THRESHOLD_ADAPTER_DAMPING_PCT (5%) × 2 cycles of evidence-registry
# promotion magnitude — 10pp is the smallest observable regression that a single
# adaptation cycle could not explain by noise alone.
ROLLBACK_DEGRADATION_THRESHOLD_PP: float = 10.0

# ── ADR-0033 Layer 3 L3-C — Cold-start conservative bias ─────────────────────
COLD_START_SOFT_GATE_CONSERVATIVE_FACTOR: float = 0.80  # 20% shift toward conservative
COLD_START_HARD_STOP_FACTOR: float = 1.00               # Hard-stop gates (H1–H5) unchanged

# ── ADR-0053 — Data-void governance gate (H6) ────────────────────────────────
DATA_VOID_THRESHOLD_HOURS: float = 48.0  # Hours since last Garmin sync before H6 fires
DATA_VOID_ZONE_CAP: int = 2              # Max training zone permitted when H6 is active

# Governance lock codes (ADR-0024 / T4-21): machine-readable canonical set.
CANONICAL_LOCK_CODES: frozenset[str] = frozenset(
    {
        "HARD_STOP_SAFETY_GATES",
        "VO2_ELIGIBILITY_GATE",
        "FUELING_GATE_LOCK",
        "FUELING_GATE_FLAG",
        "READINESS_2OF4_DOWNGRADE",
        "INTENSITY_GATE_RED",
        "INTENSITY_GATE_YELLOW",
        "PARASYMPATHETIC_GUARD",
        "OVERRIDE_LOCKDOWN",
        "CS_CONFIDENCE_LOCK",
        "PERSISTENCE_DEGRADED_CEILING",
        "STARTUP_DATA_CONFIDENCE_CEILING",
        "FAIL_SAFE_LOCK",
        "DATA_MISSING_CONSERVATIVE_H2",
        "DATA_MISSING_CONSERVATIVE_H3",
        "DATA_MISSING_CONSERVATIVE_H4",
        "DATA_MISSING_CONSERVATIVE_H5",
        "DATA_VOID_CONSERVATIVE",
    }
)

# ── Hydration constants — daily baseline (Burke et al. 2011; Sawka et al. 2007) ──
HYDRATION_BASE_ML_PER_KG: float = 35.0   # ml/kg body weight/day baseline
HYDRATION_EASY_ML: int = 300             # additional ml for easy session
HYDRATION_TEMPO_ML: int = 500            # additional ml for tempo session
HYDRATION_INTERVALS_ML: int = 600        # additional ml for interval/high-intensity session
HYDRATION_LONG_RUN_ML: int = 800         # additional ml for long run session

# ── Nutrition constants — fat macronutrient floor ────────────────────────────
MIN_FAT_G: int = 40          # minimum daily fat intake in grams (dietary guideline floor)
FAT_KCAL_PER_GRAM: int = 9   # caloric density of fat (Atwater factor)

# ── CI tooling constants (importable by tests + CI scripts) ──────────────────
MODULE_COUNT_CEILING: int = 90  # T4-27-C: 73→79 (2026-06-09); 79→80 (Architect confirmed 2026-10-07);
# 80→87 (Architect confirmed 2026-10-07, plan #18 repositories package + 6 modules);
# 87→90 (D-029, DailyCoach split, plan tasks 6 and 9). Matches
# the canonical assertion in tests/test_documentation_consistency.py
# (AGENTS §16.11; +1 P27-04 rollback_gate.py). pkgutil.walk_packages
# counts packages (dirs with init.py) in addition to source modules;
# the find-based local test counts fewer .py files (both ≤ ceiling).
