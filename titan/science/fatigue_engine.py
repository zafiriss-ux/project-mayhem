"""Fatigue Classification Engine"""

from titan.config.thresholds import FATIGUE_SORENESS_PERIPHERAL_MIN

MODULE_VERSION = "1.0.0"

class FatigueEngine:
    @staticmethod
    def classify_fatigue(
        hr_suppression: bool, rpe_mismatch: bool, pace_hr_divergence: bool, soreness: int
    ) -> tuple[str, list[str]]:
        """Classify fatigue type and severity"""
        types = []
        if hr_suppression:
            types.append("CENTRAL")
        if rpe_mismatch:
            types.append("CENTRAL")
        if pace_hr_divergence:
            types.append("METABOLIC")
        if soreness >= FATIGUE_SORENESS_PERIPHERAL_MIN:
            types.append("PERIPHERAL")

        if not types:
            return "LOW", ["NONE"]
        if "CENTRAL" in types and "METABOLIC" in types:
            return "HIGH", list(set(types))
        if "PERIPHERAL" in types and ("CENTRAL" in types or "METABOLIC" in types):
            return "MEDIUM", list(set(types))
        return "MEDIUM", list(set(types))
