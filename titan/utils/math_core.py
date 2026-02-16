"""
TITAN Math Core Utilities
Weight management and system status functions
"""

from typing import Literal


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
