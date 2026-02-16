"""Readiness Score Engine - Composite Recovery Analysis"""
from typing import Dict

class ReadinessEngine:
    @staticmethod
    def analyze_readiness(
        today_hrv: float,
        baseline_hrv: float,
        today_rhr: float,
        baseline_rhr: float,
        sleep_score: int,
        soreness: int
    ) -> Dict:
        """Calculate composite readiness score (0-100)"""
        score = 100
        
        # HRV component
        hrv_diff = today_hrv - baseline_hrv
        if hrv_diff < -10: score -= 20
        elif hrv_diff < -5: score -= 10
        elif hrv_diff > 10: score += 10
        
        # RHR component
        rhr_diff = today_rhr - baseline_rhr
        if rhr_diff > 5: score -= 15
        elif rhr_diff > 3: score -= 8
        
        # Sleep component
        if sleep_score < 5: score -= 15
        elif sleep_score < 7: score -= 8
        elif sleep_score >= 9: score += 5
        
        # Soreness component
        if soreness > 7: score -= 15
        elif soreness > 5: score -= 10
        
        score = max(0, min(100, score))
        
        # Interpretation
        if score >= 85: status = "✅ EXCELLENT"
        elif score >= 70: status = "👍 GOOD"
        elif score >= 50: status = "⚠️ FAIR"
        else: status = "🛑 POOR"
        
        return {
            "score": score,
            "status": status,
            "hrv_contribution": hrv_diff,
            "rhr_contribution": -rhr_diff,
            "sleep_contribution": sleep_score,
            "soreness_impact": -soreness
        }
