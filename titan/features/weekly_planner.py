"""
Weekly Training Plan Generator

Generates intelligent weekly plans based on:
- Recent lactate threshold
- Training drift patterns
- HRV trends
- TSB status
- Weather forecast
- Periodization phase
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from titan.science.acwr_engine import ACWREngine
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.tsb_engine import TSBEngine

_log = logging.getLogger(__name__)


def _planner_event(action: str, **fields) -> None:
    """Emit a structured weekly planner event as a single JSON log line."""
    _log.info(json.dumps({"flow": "weekly_planner", "action": action, **fields}, default=str))


class WeeklyPlanGenerator:
    """
    Intelligent weekly training plan generation.

    Analyzes past week performance and generates next week's plan
    considering lactate threshold, drift, HRV, and recovery status.
    """

    def __init__(self, hrv_engine: HRVGuidedEngine, tsb_engine: TSBEngine, acwr_engine: ACWREngine):
        """
        Initialize weekly planner.

        Args:
            hrv_engine: HRV analysis engine
            tsb_engine: TSB calculation engine
            acwr_engine: ACWR monitoring engine
        """
        self.hrv_engine = hrv_engine
        self.tsb_engine = tsb_engine
        self.acwr_engine = acwr_engine
        self.last_plan = None

    def get_today_session(self) -> dict:
        """
        Return the planned session for today from the last generated plan.

        Looks up today's day name (Monday, Tuesday…) in last_plan['daily_sessions'].
        Falls back to EASY if no plan has been generated yet.
        """
        if not self.last_plan:
            return {
                "session_type": "EASY",
                "duration_min": 45,
                "distance_km": 8.0,
                "details": "Easy Run (generate a weekly plan first)",
                "target_hr_zone": "Z2",
            }

        today_name = datetime.now().strftime("%A")  # 'Monday', 'Tuesday', …
        for session in self.last_plan.get("daily_sessions", []):
            if session.get("day") == today_name:
                result = dict(session)
                # Inject duration_min if missing (estimate from session type)
                if "duration_min" not in result:
                    pace_map = {
                        "INTERVALS": 5.5,  # avg including recovery
                        "TEMPO": 4.5,
                        "HAMMER": 5.0,
                        "EASY": 6.0,
                        "LONG_RUN": 6.0,
                        "RECOVERY": 6.5,
                        "RACE": 4.0,
                        "REST": 0.0,
                    }
                    pace = pace_map.get(result.get("session_type", "EASY"), 6.0)
                    dist = float(result.get("distance_km", 0))
                    result["duration_min"] = max(0, int(dist * pace))
                return result

        # Today not found in plan (shouldn't happen for a 7-day plan)
        return {
            "session_type": "REST",
            "duration_min": 0,
            "distance_km": 0.0,
            "details": "Rest day (not scheduled in current plan)",
            "target_hr_zone": "N/A",
        }

    def analyze_past_week(self, sessions: list[dict]) -> dict:
        """
        Analyze past week's training.

        Args:
            sessions: List of session dictionaries from past week

        Returns:
            Analysis summary
        """
        if not sessions:
            _planner_event("past_week_analyzed", sessions=0, readiness="UNKNOWN")
            return {
                "total_km": 0,
                "quality_sessions": 0,
                "avg_drift": 0,
                "lactate_status": "UNKNOWN",
                "readiness": "UNKNOWN",
            }

        total_km = sum(s.get("distance_km", 0) for s in sessions)
        quality_sessions = sum(
            1 for s in sessions if s.get("session_type") in ["INTERVALS", "TEMPO", "HAMMER"]
        )

        # Calculate average drift
        drifts = [s.get("drift_pct", 0) for s in sessions if "drift_pct" in s]
        avg_drift = sum(drifts) / len(drifts) if drifts else 0

        # Analyze lactate threshold approximation
        lt_sessions = [s for s in sessions if s.get("session_type") == "TEMPO"]
        lactate_status = "IMPROVING" if lt_sessions and avg_drift < 3.5 else "STABLE"

        # HRV trend
        hrv_trend = self.hrv_engine.get_trend_analysis()

        # TSB status
        tsb_value, tsb_status = self.tsb_engine.calculate_tsb()

        analysis = {
            "total_km": total_km,
            "quality_sessions": quality_sessions,
            "avg_drift": round(avg_drift, 1),
            "lactate_status": lactate_status,
            "hrv_trend": hrv_trend,
            "tsb": tsb_value,
            "tsb_status": tsb_status,
            "readiness": "GOOD"
            if avg_drift < 4 and tsb_value is not None and tsb_value > -20
            else "COMPROMISED",
        }
        _planner_event(
            "past_week_analyzed",
            sessions=len(sessions),
            total_km=analysis["total_km"],
            quality_sessions=analysis["quality_sessions"],
            readiness=analysis["readiness"],
        )
        return analysis

    def generate_weekly_plan(
        self, athlete_profile: dict, weather_forecast: list[dict] = None, phase: str = "BUILD"
    ) -> dict:
        """
        Generate next week's training plan.

        Args:
            athlete_profile: Athlete profile dictionary
            weather_forecast: 7-day weather forecast
            phase: Current training phase (BASE/BUILD/PEAK/TAPER)

        Returns:
            Weekly plan dictionary
        """
        # Get current status
        hrv_summary = self.hrv_engine.get_hrv_summary()
        tsb_value, tsb_status = self.tsb_engine.calculate_tsb()

        _planner_event(
            "plan_generation_started",
            phase=phase,
            tsb_value=tsb_value,
            tsb_status=tsb_status,
            weather_days=len(weather_forecast or []),
        )

        # Determine weekly structure based on phase
        if phase == "BASE":
            structure = self._generate_base_week(athlete_profile, tsb_value)
        elif phase == "BUILD":
            structure = self._generate_build_week(athlete_profile, tsb_value)
        elif phase == "PEAK":
            structure = self._generate_peak_week(athlete_profile, tsb_value)
        elif phase == "TAPER":
            structure = self._generate_taper_week(athlete_profile, tsb_value)
        else:
            structure = self._generate_build_week(athlete_profile, tsb_value)

        # Apply HRV adjustments
        structure = self._apply_hrv_adjustments(structure, hrv_summary)

        # Apply weather adjustments if available
        if weather_forecast:
            structure = self._apply_weather_adjustments(structure, weather_forecast)

        # Package the plan
        plan = {
            "week_start": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "phase": phase,
            "total_km": sum(d["distance_km"] for d in structure),
            "quality_count": sum(
                1 for d in structure if d["session_type"] in ["INTERVALS", "TEMPO", "HAMMER"]
            ),
            "easy_count": sum(1 for d in structure if d["session_type"] == "EASY"),
            "rest_count": sum(1 for d in structure if d["session_type"] == "REST"),
            "lactate_threshold": athlete_profile.get("threshold_hr", "N/A"),
            "avg_drift": "See past week analysis",
            "hrv_baseline": hrv_summary.get("baseline", "N/A"),
            "tsb_status": tsb_status,
            "daily_sessions": structure,
            "motivation": self._get_motivational_message(phase, tsb_value),
        }

        self.last_plan = plan
        _planner_event(
            "plan_generated",
            phase=phase,
            sessions=len(structure),
            weekly_km=plan["total_km"],
            quality_sessions=plan["quality_count"],
            recovery_days=plan["rest_count"],
        )
        return plan

    def _generate_base_week(self, profile: dict, tsb: float) -> list[dict]:
        """Generate BASE phase week (volume focus)."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return [
            {
                "day": days[0],
                "session_type": "EASY",
                "distance_km": 10,
                "details": "Easy aerobic, Z1-Z2",
            },
            {
                "day": days[1],
                "session_type": "EASY",
                "distance_km": 12,
                "details": "Easy aerobic with strides",
            },
            {
                "day": days[2],
                "session_type": "TEMPO",
                "distance_km": 14,
                "details": "8km steady + 3x2km @ LT1",
            },
            {"day": days[3], "session_type": "EASY", "distance_km": 8, "details": "Recovery run"},
            {"day": days[4], "session_type": "EASY", "distance_km": 10, "details": "Easy aerobic"},
            {
                "day": days[5],
                "session_type": "LONG_RUN",
                "distance_km": 20,
                "details": "Long aerobic run",
            },
            {
                "day": days[6],
                "session_type": "REST",
                "distance_km": 0,
                "details": "Complete rest or cross-training",
            },
        ]

    def _generate_build_week(self, profile: dict, tsb: float) -> list[dict]:
        """Generate BUILD phase week (intensity + volume)."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return [
            {
                "day": days[0],
                "session_type": "EASY",
                "distance_km": 10,
                "details": "Recovery from weekend",
            },
            {
                "day": days[1],
                "session_type": "INTERVALS",
                "distance_km": 12,
                "details": "3km WU + 6x1km @ VO2max + 2km CD",
            },
            {"day": days[2], "session_type": "EASY", "distance_km": 10, "details": "Easy aerobic"},
            {
                "day": days[3],
                "session_type": "TEMPO",
                "distance_km": 15,
                "details": "3km WU + 8km @ LT + 2km CD",
            },
            {"day": days[4], "session_type": "EASY", "distance_km": 8, "details": "Recovery run"},
            {
                "day": days[5],
                "session_type": "LONG_RUN",
                "distance_km": 22,
                "details": "Long run with progression",
            },
            {"day": days[6], "session_type": "REST", "distance_km": 0, "details": "Complete rest"},
        ]

    def _generate_peak_week(self, profile: dict, tsb: float) -> list[dict]:
        """Generate PEAK phase week (race-specific)."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return [
            {"day": days[0], "session_type": "EASY", "distance_km": 8, "details": "Easy recovery"},
            {
                "day": days[1],
                "session_type": "INTERVALS",
                "distance_km": 10,
                "details": "5x1km @ race pace - 90s rec",
            },
            {"day": days[2], "session_type": "EASY", "distance_km": 8, "details": "Easy aerobic"},
            {
                "day": days[3],
                "session_type": "TEMPO",
                "distance_km": 12,
                "details": "5km @ race pace",
            },
            {"day": days[4], "session_type": "EASY", "distance_km": 6, "details": "Shake-out"},
            {
                "day": days[5],
                "session_type": "LONG_RUN",
                "distance_km": 18,
                "details": "Moderate long run",
            },
            {"day": days[6], "session_type": "REST", "distance_km": 0, "details": "Rest"},
        ]

    def _generate_taper_week(self, profile: dict, tsb: float) -> list[dict]:
        """Generate TAPER week (pre-race)."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return [
            {"day": days[0], "session_type": "EASY", "distance_km": 6, "details": "Very easy"},
            {
                "day": days[1],
                "session_type": "EASY",
                "distance_km": 6,
                "details": "Easy with 4x100m strides",
            },
            {"day": days[2], "session_type": "EASY", "distance_km": 5, "details": "Shake-out"},
            {"day": days[3], "session_type": "REST", "distance_km": 0, "details": "Complete rest"},
            {
                "day": days[4],
                "session_type": "EASY",
                "distance_km": 4,
                "details": "Light jog + strides",
            },
            {
                "day": days[5],
                "session_type": "REST",
                "distance_km": 0,
                "details": "Rest before race",
            },
            {"day": days[6], "session_type": "RACE", "distance_km": 42.195, "details": "RACE DAY!"},
        ]

    def _apply_hrv_adjustments(self, structure: list[dict], hrv_summary: dict) -> list[dict]:
        """Adjust plan based on HRV status."""
        baseline = hrv_summary.get("baseline")
        latest = hrv_summary.get("latest_hrv")

        if baseline and latest:
            if latest < baseline - 10:  # HRV significantly suppressed
                # Reduce intensity across the week
                for day in structure:
                    if day["session_type"] in ["INTERVALS", "HAMMER"]:
                        day["session_type"] = "TEMPO"
                        day["details"] += " (downgraded from intervals due to HRV)"
                    elif day["session_type"] == "TEMPO":
                        day["session_type"] = "EASY"
                        day["details"] += " (downgraded due to HRV)"

        return structure

    def _apply_weather_adjustments(self, structure: list[dict], forecast: list[dict]) -> list[dict]:
        """Adjust plan based on weather forecast."""
        # Add optimal time suggestions based on dew point
        for i, day in enumerate(structure):
            if i < len(forecast):
                day_forecast = forecast[i]
                # Find best time window
                if day_forecast.get("min_dew_hour"):
                    day["optimal_time"] = f"{day_forecast['min_dew_hour']}:00 (best conditions)"

        return structure

    def _get_motivational_message(self, phase: str, tsb: float) -> str:
        """Get phase-appropriate motivational message."""
        messages = {
            "BASE": "Building the foundation - consistency is key! 💪",
            "BUILD": "Quality work pays off - stay sharp! 🎯",
            "PEAK": "Race-specific training - this is where champions are made! 🏆",
            "TAPER": "Trust the taper - your body is getting ready! 🚀",
        }
        return messages.get(phase, "Train smart, recover hard! 💪")
