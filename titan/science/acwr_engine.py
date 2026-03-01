"""ACWR Engine - Injury Prevention via Workload Monitoring"""
from typing import Tuple, Optional

class ACWREngine:
    """Acute:Chronic Workload Ratio (Gabbett 2016)"""

    @staticmethod
    def calculate_acwr(acute_7d: float, chronic_28d_avg: float) -> Tuple[Optional[float], str, str]:
        """Calculate ACWR = Acute / (Chronic * 7)"""
        if not chronic_28d_avg:
            return None, "INSUFFICIENT DATA", "Need 28 days"
        acwr = acute_7d / (chronic_28d_avg * 7)

        if acwr < 0.5:
            return round(acwr, 2), "🛑 SEVERE DETRAINING", "Increase gradually"
        elif acwr < 0.8:
            return round(acwr, 2), "⚠️ DETRAINING RISK", "Consider volume increase"
        elif acwr <= 1.0:
            return round(acwr, 2), "➡️ MAINTENANCE", "Good for recovery weeks"
        elif acwr <= 1.3:
            return round(acwr, 2), "✅ SWEET SPOT", "Optimal adaptation"
        elif acwr <= 1.5:
            return round(acwr, 2), "⚠️ MODERATE RISK", "Monitor fatigue"
        else:
            return round(acwr, 2), "🛑 HIGH INJURY RISK", "REDUCE LOAD (2-4x risk)"

    @staticmethod
    def weekly_load_recommendation(chronic_avg: float, target: float = 1.2) -> float:
        return round(chronic_avg * 7 * target, 1)

    @staticmethod
    def injury_risk_score(acwr: float) -> Tuple[int, str]:
        if acwr < 0.8:
            return 1, "Very Low"
        elif acwr <= 1.0:
            return 2, "Low"
        elif acwr <= 1.15:
            return 3, "Low-Moderate"
        elif acwr <= 1.3:
            return 4, "Moderate"
        elif acwr <= 1.5:
            return 6, "Moderate-High"
        elif acwr <= 1.7:
            return 8, "High (2-3x risk)"
        else:
            return 10, "Extreme (4x+ risk)"
