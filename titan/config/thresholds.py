"""Centralized governance and safety thresholds."""

HARD_STOP_HRV_DELTA = 15.0
HARD_STOP_RHR_DELTA = 8.0
HARD_STOP_TSB_FLOOR = -50.0

SUBJECTIVE_FATIGUE_EXTREME = 8
SUBJECTIVE_FATIGUE_2OF4 = 6

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
