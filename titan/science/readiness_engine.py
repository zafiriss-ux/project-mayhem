"""Readiness Score Engine - Composite Recovery Analysis"""
import json
import logging
from typing import Dict

_log = logging.getLogger(__name__)


def _readiness_event(action: str, **fields) -> None:
    """Emit structured readiness events as single-line JSON logs."""
    _log.info(json.dumps({'readiness_flow': action, **fields}, default=str))

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
        _readiness_event(
            'ANALYZE_START',
            today_hrv=today_hrv,
            baseline_hrv=baseline_hrv,
            today_rhr=today_rhr,
            baseline_rhr=baseline_rhr,
            sleep_score=sleep_score,
            soreness=soreness,
        )
        score = 100

        # HRV component
        hrv_diff = today_hrv - baseline_hrv
        if hrv_diff < -8:
            score -= 20
        elif hrv_diff < -5:
            score -= 10
        elif hrv_diff > 10:
            score += 10

        # RHR component
        rhr_diff = today_rhr - baseline_rhr
        if rhr_diff > 6:
            score -= 15
        elif rhr_diff > 3:
            score -= 8

        # Sleep component — Garmin scale 0-100
         # (<60 = poor, 60-69 = fair, 70-84 = good, >=85 = excellent)
        if sleep_score < 60:
            score -= 15
        elif sleep_score < 70:
            score -= 8
        elif sleep_score >= 85:
            score += 5

        # Soreness component — scale 0-10 (or 0-5 × 2 from morning check-in)
        # Normalise to 0-10 range internally
        if soreness > 7:
            score -= 15
        elif soreness > 5:
            score -= 10
        elif soreness > 3:
            score -= 5

        score = max(0, min(100, score))

        # Interpretation
        if score >= 85:
            status = "✅ EXCELLENT"
        elif score >= 70:
            status = "👍 GOOD"
        elif score >= 50:
            status = "⚠️ FAIR"
        else:
            status = "🛑 POOR"

        result = {
            "score": score,
            "status": status,
            "hrv_contribution": hrv_diff,
            "rhr_contribution": -rhr_diff,
            "sleep_contribution": sleep_score,
            "soreness_impact": -soreness,
            "hrv_delta_pts": hrv_diff,
            "rhr_delta_pts": rhr_diff,
        }

        _readiness_event(
            'ANALYZE_COMPLETE',
            score=result['score'],
            status=result['status'],
            hrv_delta_pts=result['hrv_delta_pts'],
            rhr_delta_pts=result['rhr_delta_pts'],
        )
        return result
