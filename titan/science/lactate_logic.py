"""Lactate Threshold Logic - LT1/LT2 Estimation without Lactate Meter"""

from titan.config.thresholds import (
    LACTATE_LT1_MAX_DRIFT_PCT,
    LACTATE_LT1_MAX_HR_PCT,
    LACTATE_LT2_MAX_RPE,
    LACTATE_LT2_MIN_RPE,
)

MODULE_VERSION = "1.0.0"

class LactateLogic:
    @staticmethod
    def estimate_lt1(hr_percent_max: float, drift_percent: float) -> dict:
        """
        LT1 ≈ drift < 3% + HR < 75-78% HRmax.

        Returns a dict so callers can branch on the boolean without
        fragile string parsing.
        """
        is_lt1 = (
            drift_percent < LACTATE_LT1_MAX_DRIFT_PCT
            and hr_percent_max <= LACTATE_LT1_MAX_HR_PCT
        )
        return {
            "is_lt1": is_lt1,
            "status_text": "LT1_ZONE: TRUE (Pure aerobic)" if is_lt1 else "LT1_ZONE: FALSE",
            "hr_pct_max": round(hr_percent_max, 1),
            "drift_pct": round(drift_percent, 1),
        }

    @staticmethod
    def estimate_lt2(hr_stable: bool, rpe: float) -> dict:
        """
        LT2 ≈ tempo → HR stable & RPE 6-7.

        Returns a dict for programmatic use.
        """
        is_lt2 = hr_stable and LACTATE_LT2_MIN_RPE <= rpe <= LACTATE_LT2_MAX_RPE
        return {
            "is_lt2": is_lt2,
            "status_text": "LT2_APPROX: TRUE (Threshold hit)" if is_lt2 else "LT2_APPROX: FALSE",
            "hr_stable": hr_stable,
            "rpe": rpe,
        }

    @staticmethod
    def tempo_volume_decision(is_lt2_true: bool) -> dict:
        """Decide if full tempo volume is safe."""
        ok = bool(is_lt2_true)
        return {
            "ok": ok,
            "text": "TEMPO VOLUME: OK (Full planned volume)"
            if ok
            else "TEMPO VOLUME: DOWNGRADE (Cut reps or distance)",
        }
