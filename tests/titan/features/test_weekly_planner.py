from titan.features.weekly_planner import WeeklyPlanGenerator


class _FakeHRVEngine:
    def get_hrv_summary(self):
        return {"baseline": 60, "latest_hrv": 57}

    def get_trend_analysis(self):
        return {"trend": "stable"}


class _FakeTSBEngine:
    def __init__(self, value=-5.0, status="BALANCED"):
        self.value = value
        self.status = status

    def calculate_tsb(self):
        return self.value, self.status


class _FakeACWR:
    pass


def _planner(tsb_value=-5.0, tsb_status="BALANCED"):
    return WeeklyPlanGenerator(
        hrv_engine=_FakeHRVEngine(),
        tsb_engine=_FakeTSBEngine(value=tsb_value, status=tsb_status),
        acwr_engine=_FakeACWR(),
    )


def test_analyze_past_week_happy_path_returns_good_readiness():
    planner = _planner(tsb_value=-4)

    analysis = planner.analyze_past_week(
        [
            {"distance_km": 12, "session_type": "TEMPO", "drift_pct": 2.0},
            {"distance_km": 10, "session_type": "EASY", "drift_pct": 3.0},
        ]
    )

    assert analysis["total_km"] == 22
    assert analysis["quality_sessions"] == 1
    assert analysis["lactate_status"] == "IMPROVING"
    assert analysis["readiness"] == "GOOD"


def test_analyze_past_week_empty_sessions_returns_unknown_readiness():
    planner = _planner()

    analysis = planner.analyze_past_week([])

    assert analysis["total_km"] == 0
    assert analysis["readiness"] == "UNKNOWN"


def test_generate_weekly_plan_unknown_phase_falls_back_to_build(monkeypatch):
    planner = _planner(tsb_value=-3, tsb_status="FRESH")
    monkeypatch.setattr(planner, "_apply_hrv_adjustments", lambda structure, summary: structure)
    monkeypatch.setattr(planner, "_apply_weather_adjustments", lambda structure, forecast: structure)

    plan = planner.generate_weekly_plan(
        athlete_profile={"threshold_hr": 170},
        weather_forecast=None,
        phase="UNSUPPORTED",
    )

    assert plan["phase"] == "UNSUPPORTED"
    assert len(plan["daily_sessions"]) == 7
    assert plan["quality_count"] == 2


def test_get_today_session_without_plan_returns_easy_default():
    planner = _planner()

    session = planner.get_today_session()

    assert session["session_type"] == "EASY"
    assert session["target_hr_zone"] == "Z2"
