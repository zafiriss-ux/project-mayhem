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
        if drift_percent < 3.5:
            return "GOOD"
        if drift_percent < 5.0:
            return "ACCEPTABLE"
        return "POOR"

    def analyze_cardiac_drift(self, hr_data: list[float], duration_min: int) -> dict[str, object]:
        """Public wrapper for drift analysis used by orchestration callbacks."""
        if len(hr_data) < 2 or duration_min <= 0:
            return {
                "drift_percent": 0.0,
                "assessment": "INSUFFICIENT_DATA",
                "lt_zone": "UNKNOWN",
            }

        split_index = len(hr_data) // 2
        first_half = hr_data[:split_index]
        second_half = hr_data[split_index:]
        if not first_half or not second_half:
            return {
                "drift_percent": 0.0,
                "assessment": "INSUFFICIENT_DATA",
                "lt_zone": "UNKNOWN",
            }

        first_half_avg = sum(first_half) / len(first_half)
        second_half_avg = sum(second_half) / len(second_half)
        drift_percent = round(self.compute_drift(first_half_avg, second_half_avg), 1)
        assessment = self.classify_drift(drift_percent)
        if drift_percent < 3.0:
            lt_zone = "BELOW_LT"
        elif drift_percent < 5.0:
            lt_zone = "AT_LT"
        else:
            lt_zone = "ABOVE_LT"

        return {
            "drift_percent": drift_percent,
            "assessment": assessment,
            "lt_zone": lt_zone,
        }
