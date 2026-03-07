"""HR Drift Engine - Cardiac Decoupling Analysis"""


MODULE_VERSION = "1.0.0"

class DriftEngine:
    @staticmethod
    def compute_drift(hr_first_half: float, hr_second_half: float) -> float:
        """Compute HR drift percentage between halves"""
        if hr_first_half <= 0:
            return 0.0
        return ((hr_second_half - hr_first_half) / hr_first_half) * 100.0

    @staticmethod
    def drift_rule(drift_percent: float) -> str:
        """Interpret drift for training decisions"""
        if drift_percent > 5.0:
            return "🛑 DRIFT > 5%: Stop progression. No hammer today"
        if drift_percent < 3.0:
            return "✅ DRIFT < 3%: Hammer extension allowed"
        return "➡️ DRIFT 3-5%: Maintain, no extra load"

    @staticmethod
    def classify_drift(drift_percent: float) -> str:
        """Classify aerobic efficiency"""
        if drift_percent < 2.0:
            return "EXCELLENT"
        elif drift_percent < 3.5:
            return "GOOD"
        elif drift_percent < 5.0:
            return "ACCEPTABLE"
        else:
            return "POOR"
