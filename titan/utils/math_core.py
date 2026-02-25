"""
TITAN Math Core Utilities
Weight management, unit conversion, and system status functions
"""

from typing import Literal, Optional


class MathCore:
    """
    Core mathematical and status evaluation functions for TITAN.
    Handles weight management alerts and system status assessment.
    """

    @staticmethod
    def weight_function_Wf(
        weight: float,
        night_drop: float,
        epoc: float
    ) -> str:
        """
        Weight management function - evaluates weight status and returns appropriate action.

        Args:
            weight: Current weight in kg
            night_drop: Weight drop overnight in kg
            epoc: Excess Post-exercise Oxygen Consumption in kcal

        Returns:
            Status string indicating weight management state

        Weight States:
            - AGGRESSIVE_CORRECTION: weight < 74.5 kg (panic threshold)
            - EMERGENCY_MODE: weight < 75.0 kg (floor threshold)
            - NIGHT_DROP_ALERT: overnight drop > 1.2 kg
            - EPOC_OVERRIDE: EPOC > 350 kcal (high metabolic stress)
            - SAFE_DROP_RULE: weight <= 75.5 kg (controlled drop zone)
            - STABLE: Normal weight range
        """
        if weight < 74.5:
            return "AGGRESSIVE_CORRECTION"
        if weight < 75.0:
            return "EMERGENCY_MODE"
        if night_drop > 1.2:
            return "NIGHT_DROP_ALERT"
        if epoc > 350:
            return "EPOC_OVERRIDE"
        if weight <= 75.5:
            return "SAFE_DROP_RULE"
        return "STABLE"

    @staticmethod
    def system_status_SSV(
        hrv_status: str,
        sleep_score: int,
        pain: int,
        weight: float,
        epoc: float,
        night_drop: float
    ) -> Literal["CRITICAL", "UNSTABLE", "STABLE"]:
        """
        System Status Validator - evaluates overall athlete readiness.

        Integrates multiple biomarkers to determine training readiness state.
        Based on Kiviniemi (2007) HRV-guided training principles.

        Args:
            hrv_status: Heart Rate Variability status ("LOW", "NORMAL", "HIGH")
            sleep_score: Sleep quality score (0-100)
            pain: Soreness/pain level (0-5 scale)
            weight: Current weight in kg
            epoc: Excess Post-exercise Oxygen Consumption in kcal
            night_drop: Weight drop overnight in kg

        Returns:
            System status: "CRITICAL", "UNSTABLE", or "STABLE"

        Decision Logic:
            CRITICAL: Any of:
                - Pain >= 3
                - HRV status = "LOW"
                - Sleep score < 60
                - Weight < 75.0 kg
                - EPOC > 350 kcal

            UNSTABLE: Any of:
                - Pain == 2
                - Sleep score 60-65
                - Night drop > 1.0 kg

            STABLE: None of the above conditions
        """
        critical_cond = (
            pain >= 3 or
            hrv_status == "LOW" or
            sleep_score < 60 or
            weight < 75.0 or
            epoc > 350
        )

        unstable_cond = (
            pain == 2 or
            60 <= sleep_score < 65 or
            night_drop > 1.0
        )

        if critical_cond:
            return "CRITICAL"
        if unstable_cond:
            return "UNSTABLE"
        return "STABLE"

    # ─────────────────────────────────────────────────────────────────────────
    # UNIT CONVERTERS  (used by CriticalSpeedEngine, DriftEngine, etc.)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def pace_to_ms(pace_sec_per_km: float) -> float:
        """
        Convert running pace (sec/km) to speed (m/s).

        Example: 4:00/km = 240 sec/km → 1000/240 = 4.167 m/s

        Args:
            pace_sec_per_km: Pace in seconds per kilometre

        Returns:
            Speed in metres per second (0.0 if pace is 0 or invalid)
        """
        if not pace_sec_per_km or pace_sec_per_km <= 0:
            return 0.0
        return round(1000.0 / pace_sec_per_km, 4)

    @staticmethod
    def ms_to_pace(speed_ms: float) -> float:
        """
        Convert speed (m/s) to running pace (sec/km).

        Example: 4.167 m/s → 1000/4.167 = 240 sec/km (4:00/km)

        Args:
            speed_ms: Speed in metres per second

        Returns:
            Pace in seconds per kilometre (0.0 if speed is 0 or invalid)
        """
        if not speed_ms or speed_ms <= 0:
            return 0.0
        return round(1000.0 / speed_ms, 2)

    @staticmethod
    def format_pace(pace_sec_per_km: float) -> str:
        """
        Format pace as MM:SS string.

        Example: 240 → "4:00"
        """
        if not pace_sec_per_km or pace_sec_per_km <= 0:
            return "N/A"
        mins = int(pace_sec_per_km) // 60
        secs = int(pace_sec_per_km) % 60
        return f"{mins}:{secs:02d}"

    # ─────────────────────────────────────────────────────────────────────────
    # PROFILE-AWARE WEIGHT FUNCTION
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def weight_function_from_profile(
        weight: float,
        night_drop: float,
        epoc: float,
        target_weight: Optional[float] = 75.0,
        critical_margin: float = 0.5,
        emergency_margin: float = 0.0,
    ) -> str:
        """
        Profile-aware weight function.

        Uses athlete-specific target weight instead of hardcoded 75 kg.

        Args:
            weight: Current weight in kg
            night_drop: Overnight weight drop in kg
            epoc: EPOC in kcal
            target_weight: Athlete's goal weight (from athlete_profile)
            critical_margin: kg below target → AGGRESSIVE_CORRECTION
            emergency_margin: kg below target → EMERGENCY_MODE

        Returns:
            Same status strings as weight_function_Wf
        """
        if target_weight is None:
            target_weight = 75.0
        if weight < (target_weight - critical_margin):
            return "AGGRESSIVE_CORRECTION"
        if weight < target_weight:
            return "EMERGENCY_MODE"
        if night_drop > 1.2:
            return "NIGHT_DROP_ALERT"
        if epoc > 350:
            return "EPOC_OVERRIDE"
        if weight <= (target_weight + 0.5):
            return "SAFE_DROP_RULE"
        return "STABLE"
