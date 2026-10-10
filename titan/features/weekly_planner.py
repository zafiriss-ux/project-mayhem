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

import logging
from datetime import UTC, date, datetime, timedelta

from titan.config.thresholds import (
    PLANNER_DEFAULT_WEEKLY_KM,
    PLANNER_VOLUME_WINDOW_DAYS,
    PLANNER_WEEKLY_KM_GROWTH_MAX,
)
from titan.core.structured_events import make_event_emitter
from titan.science.acwr_engine import ACWREngine
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.tsb_engine import TSBEngine

_log = logging.getLogger(__name__)
_planner_event = make_event_emitter("weekly_planner", _log)


class WeeklyPlanGenerator:
    """
    Intelligent weekly training plan generation.

    Analyzes past week performance and generates next week's plan
    considering lactate threshold, drift, HRV, and recovery status.
    """

    def __init__(
        self,
        hrv_engine: HRVGuidedEngine,
        tsb_engine: TSBEngine,
        acwr_engine: ACWREngine,
        db=None,  # noqa: ANN001
        athlete_id: str = "owner",
    ):
        """
        Initialize weekly planner.

        Args:
            hrv_engine: HRV analysis engine
            tsb_engine: TSB calculation engine
            acwr_engine: ACWR monitoring engine
            db: DatabaseManager whose training_log sets the weekly volume (SV-14 / D-062).
                Without one the phase templates keep their fixed kilometres.
            athlete_id: Whose training_log to read (ADR-0033).
        """
        self.hrv_engine = hrv_engine
        self.tsb_engine = tsb_engine
        self.acwr_engine = acwr_engine
        self.db = db
        self.athlete_id = athlete_id
        self.last_plan = None

    def get_today_session(
        self,
        *,
        esi_level: str | None = None,
        esi_pace_adjustment_sec_per_km: int = 0,
    ) -> dict:
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
                "esi_level": str(esi_level or "LOW").upper(),
                "esi_pace_adjustment_sec_per_km": int(esi_pace_adjustment_sec_per_km),
            }

        today_name = datetime.now(UTC).strftime("%A")
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
                result["esi_level"] = str(esi_level or "LOW").upper()
                result["esi_pace_adjustment_sec_per_km"] = int(esi_pace_adjustment_sec_per_km)
                return result

        # Today not found in plan (shouldn't happen for a 7-day plan)
        return {
            "session_type": "REST",
            "duration_min": 0,
            "distance_km": 0.0,
            "details": "Rest day (not scheduled in current plan)",
            "target_hr_zone": "N/A",
            "esi_level": str(esi_level or "LOW").upper(),
            "esi_pace_adjustment_sec_per_km": int(esi_pace_adjustment_sec_per_km),
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

        structure = self._scale_to_recent_volume(structure)

        # Apply HRV adjustments
        structure = self._apply_hrv_adjustments(structure, hrv_summary)

        # Apply weather adjustments if available
        if weather_forecast:
            structure = self._apply_weather_adjustments(structure, weather_forecast)

        # Package the plan
        plan = {
            "week_start": (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d"),
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
                "details": "Complete rest",
            },
            # SV-13 / D-061: no race date is known, so the week ends with an easy run, not a marathon.
            {"day": days[6], "session_type": "EASY", "distance_km": 8, "details": "Easy aerobic run"},
        ]

    def recent_weekly_km(self) -> float | None:
        """Average km per week over the last PLANNER_VOLUME_WINDOW_DAYS; None without a database.

        The window is the days before today (the plan is built in the morning, before the
        day's run). An athlete whose first run is more recent than the window is averaged over
        the days since that run (at least one week), so a short history is not divided by four.
        """
        if self.db is None:
            return None
        today = datetime.now(UTC).date()
        activities = self.db.get_recent_activities(limit=500, athlete_id=self.athlete_id)
        dated = [(str(a.get("date", ""))[:10], float(a.get("distance_km") or 0.0)) for a in activities]
        dated = [(d, km) for d, km in dated if d and d < today.isoformat()]
        if not dated:
            return 0.0
        span_days = (today - date.fromisoformat(min(d for d, _ in dated))).days
        span_days = max(7, min(PLANNER_VOLUME_WINDOW_DAYS, span_days))
        since = (today - timedelta(days=span_days)).isoformat()
        total = sum(km for d, km in dated if d >= since)
        return total / (span_days / 7)

    def _scale_to_recent_volume(self, structure: list[dict]) -> list[dict]:
        """SV-14 / D-062: scale the week so BUILD is the recent average + at most 10%.

        With no runs in the window the BUILD week is PLANNER_DEFAULT_WEEKLY_KM. Every phase
        keeps its shape relative to BUILD, so no phase goes above the 10% growth.
        """
        try:
            recent_km = self.recent_weekly_km()
        except Exception as exc:
            _log.warning("weekly_planner_recent_km_failed", extra={"error": str(exc)})
            recent_km = 0.0
        if recent_km is None:
            return structure
        if recent_km > 0:
            target_km = recent_km * (1 + PLANNER_WEEKLY_KM_GROWTH_MAX)
        else:
            target_km = PLANNER_DEFAULT_WEEKLY_KM
        build_km = sum(d["distance_km"] for d in self._generate_build_week({}, 0.0))
        factor = target_km / build_km
        for day in structure:
            day["distance_km"] = round(day["distance_km"] * factor, 1)
        _planner_event(
            "plan_volume_scaled", recent_weekly_km=round(recent_km, 1),
            target_build_km=round(target_km, 1), factor=round(factor, 3),
        )
        return structure

    def _apply_hrv_adjustments(self, structure: list[dict], hrv_summary: dict) -> list[dict]:
        """Adjust plan based on HRV status."""
        baseline = hrv_summary.get("baseline")
        latest = hrv_summary.get("latest_hrv")

        if baseline is not None and latest is not None and latest < baseline - 10:
            # Reduce intensity across the week
            for day in structure:
                if day["session_type"] in ["INTERVALS", "HAMMER"]:
                    day["session_type"] = "TEMPO"
                    day["details"] = "Steady tempo run @ LT (downgraded from intervals due to HRV)"
                elif day["session_type"] == "TEMPO":
                    day["session_type"] = "EASY"
                    day["details"] = "Easy aerobic run (downgraded due to HRV)"

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

    def should_replan(self, garmin_data: dict) -> bool:
        """
        Return True if a mid-week plan re-evaluation is warranted.

        Triggers (OR semantics — any one is sufficient):
        1. HRV drop > 10 ms below engine baseline
        2. HARD_STOP_SAFETY_GATES governance event within the last 24 h
        3. Illness flag set in garmin_data

        Args:
            garmin_data: Dict from a mid-week Garmin sync.  Expected keys
                (all optional — missing keys are treated as "not triggered"):
                - hrv_latest_ms (float): most recent HRV reading in ms
                - governance_events (list[dict]): each entry has ``type`` (str)
                  and ``hours_ago`` (float)
                - illness_flag (bool)

        Returns:
            True when the plan should be regenerated; False otherwise.
        """
        # ── Condition 1: HRV drop > 10 ms below baseline ─────────────────────
        hrv_latest = garmin_data.get("hrv_latest_ms")
        hrv_summary = self.hrv_engine.get_hrv_summary()
        baseline = hrv_summary.get("baseline")
        if hrv_latest is not None and baseline is not None and (baseline - hrv_latest) > 10.0:
            _planner_event("replan_triggered", reason="hrv_drop", hrv_latest_ms=hrv_latest, baseline_ms=baseline)
            return True

        # ── Condition 2: HARD_STOP governance event in last 24 h ─────────────
        for event in garmin_data.get("governance_events", []):
            if event.get("type") == "HARD_STOP_SAFETY_GATES" and event.get("hours_ago", 25) <= 24:
                _planner_event("replan_triggered", reason="hard_stop_governance", hours_ago=event.get("hours_ago"))
                return True

        # ── Condition 3: Illness flag ─────────────────────────────────────────
        if garmin_data.get("illness_flag", False):
            _planner_event("replan_triggered", reason="illness_flag")
            return True

        return False

    def _get_motivational_message(self, phase: str, tsb: float) -> str:
        """Get phase-appropriate motivational message."""
        messages = {
            "BASE": "Building the foundation - consistency is key! 💪",
            "BUILD": "Quality work pays off - stay sharp! 🎯",
            "PEAK": "Race-specific training - this is where champions are made! 🏆",
            "TAPER": "Trust the taper - your body is getting ready! 🚀",
        }
        return messages.get(phase, "Train smart, recover hard! 💪")
