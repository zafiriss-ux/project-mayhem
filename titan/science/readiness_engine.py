"""Readiness Score Engine - Composite Recovery Analysis"""
import json
import logging

from titan.core.structured_events import EventSeverity, structured_event_payload

_log = logging.getLogger(__name__)


def _readiness_event(
    action: str,
    *,
    severity: EventSeverity | str = EventSeverity.INFO,
    **fields,
) -> None:
    """Emit a structured readiness event as a single JSON log line."""
    _log.info(json.dumps(structured_event_payload("readiness", action, severity=severity, **fields), default=str))


class ReadinessEngine:
    @staticmethod
    def analyze_readiness(
        today_hrv: float,
        baseline_hrv: float,
        today_rhr: float,
        baseline_rhr: float,
        sleep_score: int,
        soreness: int,
    ) -> dict:
        """Calculate composite readiness score (0-100)"""
        score = 100
        deductions = {
            "hrv": 0,
            "rhr": 0,
            "sleep": 0,
            "soreness": 0,
            "hrv_bonus": 0,
            "sleep_bonus": 0,
        }

        # HRV component
        hrv_diff = today_hrv - baseline_hrv
        if hrv_diff < -8:
            score -= 20
            deductions["hrv"] = 20
        elif hrv_diff < -5:
            score -= 10
            deductions["hrv"] = 10
        elif hrv_diff > 10:
            score += 10
            deductions["hrv_bonus"] = 10

        # RHR component
        rhr_diff = today_rhr - baseline_rhr
        if rhr_diff > 6:
            score -= 15
            deductions["rhr"] = 15
        elif rhr_diff > 3:
            score -= 8
            deductions["rhr"] = 8

        # Sleep component — Garmin scale 0-100
        # (<60 = poor, 60-69 = fair, 70-84 = good, >=85 = excellent)
        if sleep_score < 60:
            score -= 15
            deductions["sleep"] = 15
        elif sleep_score < 70:
            score -= 8
            deductions["sleep"] = 8
        elif sleep_score >= 85:
            score += 5
            deductions["sleep_bonus"] = 5

        # Soreness component — scale 0-10 (or 0-5 × 2 from morning check-in)
        # Normalise to 0-10 range internally
        if soreness > 7:
            score -= 15
            deductions["soreness"] = 15
        elif soreness > 5:
            score -= 10
            deductions["soreness"] = 10
        elif soreness > 3:
            score -= 5
            deductions["soreness"] = 5

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

        _readiness_event(
            "computed",
            score=score,
            status=status,
            hrv_diff=hrv_diff,
            rhr_diff=rhr_diff,
            sleep_score=sleep_score,
            soreness=soreness,
            components=deductions,
        )

        return {
            "score": score,
            "status": status,
            "hrv_contribution": hrv_diff,
            "rhr_contribution": -rhr_diff,
            "sleep_contribution": sleep_score,
            "soreness_impact": -soreness,
            "hrv_delta_pts": hrv_diff,
            "rhr_delta_pts": rhr_diff,
        }
