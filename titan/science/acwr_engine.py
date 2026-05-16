"""ACWR Engine - Injury Prevention via Workload Monitoring"""

from titan.config.thresholds import (
    ACWR_DETRAINING_RISK_MAX,
    ACWR_HIGH_RISK_MAX,
    ACWR_MAINTENANCE_MAX,
    ACWR_MODERATE_RISK_MAX,
    ACWR_SEVERE_DETRAINING_MAX,
    ACWR_SWEET_SPOT_MAX,
)

MODULE_VERSION = "1.0.0"

class ACWREngine:
    """Acute:Chronic Workload Ratio (Gabbett 2016)"""

    @staticmethod
    def calculate_acwr(acute_7d: float, chronic_28d_avg: float) -> tuple[float | None, str, str]:
        """Calculate ACWR = Acute / (Chronic * 7)"""
        if not chronic_28d_avg:
            return None, "INSUFFICIENT DATA", "Need 28 days"
        acwr = acute_7d / (chronic_28d_avg * 7)

        if acwr < ACWR_SEVERE_DETRAINING_MAX:
            return round(acwr, 2), "🛑 SEVERE DETRAINING", "Increase gradually"
        if acwr < ACWR_DETRAINING_RISK_MAX:
            return round(acwr, 2), "⚠️ DETRAINING RISK", "Consider volume increase"
        if acwr <= ACWR_MAINTENANCE_MAX:
            return round(acwr, 2), "➡️ MAINTENANCE", "Good for recovery weeks"
        if acwr <= ACWR_SWEET_SPOT_MAX:
            return round(acwr, 2), "✅ SWEET SPOT", "Optimal adaptation"
        if acwr <= ACWR_MODERATE_RISK_MAX:
            return round(acwr, 2), "⚠️ MODERATE RISK", "Monitor fatigue"
        return round(acwr, 2), "🛑 HIGH INJURY RISK", "REDUCE LOAD (2-4x risk)"

    @staticmethod
    def weekly_load_recommendation(chronic_avg: float, target: float = 1.2) -> float:
        return round(chronic_avg * 7 * target, 1)

    @staticmethod
    def injury_risk_score(acwr: float) -> tuple[int, str]:
        if acwr < ACWR_DETRAINING_RISK_MAX:
            return 1, "Very Low"
        if acwr <= ACWR_MAINTENANCE_MAX:
            return 2, "Low"
        if acwr <= 1.15:
            return 3, "Low-Moderate"
        if acwr <= ACWR_SWEET_SPOT_MAX:
            return 4, "Moderate"
        if acwr <= ACWR_MODERATE_RISK_MAX:
            return 6, "Moderate-High"
        if acwr <= ACWR_HIGH_RISK_MAX:
            return 8, "High (2-3x risk)"
        return 10, "Extreme (4x+ risk)"
