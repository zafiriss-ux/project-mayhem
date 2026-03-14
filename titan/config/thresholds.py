"""Centralized governance and safety thresholds."""

HARD_STOP_HRV_DELTA = 15.0
HARD_STOP_RHR_DELTA = 8.0
HARD_STOP_TSB_FLOOR = -50.0
ILLNESS_PATTERN_HRV_DELTA = 20.0
ILLNESS_PATTERN_RHR_DELTA = 10.0

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

# AdaptiveMemory thresholds — T5-18 (Category A only).
ADAPTIVE_MEMORY_EASY_PACE_DROP_MULTIPLIER = 1.08
ADAPTIVE_MEMORY_HOURS_24 = 24
ADAPTIVE_MEMORY_HOURS_36 = 36
ADAPTIVE_MEMORY_HOURS_48 = 48
ADAPTIVE_MEMORY_HOURS_72 = 72

# Data freshness thresholds — ADR-0026 / T1-19.
# Hours since last Garmin sync before the system emits warnings or degrades confidence.
STALE_DATA_WARN_HOURS = 24        # Emit data_freshness_warn structured log event
STALE_DATA_HARD_CEILING_HOURS = 72  # Emit data_confidence_low advisory (T2-10 mechanism)

# Garmin source freshness gate — T1-20 / ADR-0030.
GARMIN_DATA_MAX_AGE_HOURS = 26

# OutcomeTracker feedback-loop guardrails — ADR-0035 / T1-22.
OUTCOME_INDEPENDENCE_WINDOW_DAYS = 2
CALIBRATION_MAX_THRESHOLD_DELTA_PCT = 0.10
CALIBRATION_MIN_OUTCOME_COUNT = 10

# Unified data trust thresholds — ADR-0041 / T1-23.
GARMIN_DATA_SUSPECT_AGE_HOURS = 12
WEATHER_DATA_SUSPECT_AGE_HOURS = 2

# Operator trust-drift monitor — ADR-0038 / T2-16.
OPERATOR_TRUST_DRIFT_WARNING_RATE_30D = 0.25

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
    }
)
