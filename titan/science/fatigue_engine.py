"""Fatigue Classification Engine"""



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
        if soreness >= 5:
            types.append("PERIPHERAL")

        if not types:
            return "LOW", ["NONE"]
        if "CENTRAL" in types and "METABOLIC" in types:
            return "HIGH", list(set(types))
        if "PERIPHERAL" in types and ("CENTRAL" in types or "METABOLIC" in types):
            return "MEDIUM", list(set(types))
        return "MEDIUM", list(set(types))
