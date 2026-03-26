from titan.features.weekly_planner import WeeklyPlanGenerator


class _FakeHRVEngine:
    def __init__(self, baseline=60, latest_hrv=57):
        self.baseline = baseline
        self.latest_hrv = latest_hrv

    def get_hrv_summary(self):
        return {"baseline": self.baseline, "latest_hrv": self.latest_hrv}

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


def _planner(tsb_value=-5.0, tsb_status="BALANCED", baseline=60, latest_hrv=57):
    return WeeklyPlanGenerator(
        hrv_engine=_FakeHRVEngine(baseline=baseline, latest_hrv=latest_hrv),
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


def test_analyze_past_week_compromised_when_drift_and_tsb_are_bad():
    planner = _planner(tsb_value=-25)

    analysis = planner.analyze_past_week(
        [
            {"distance_km": 8, "session_type": "TEMPO", "drift_pct": 4.2},
            {"distance_km": 6, "session_type": "EASY", "drift_pct": 5.0},
        ]
    )

    assert analysis["avg_drift"] == 4.6
    assert analysis["lactate_status"] == "STABLE"
    assert analysis["readiness"] == "COMPROMISED"


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


def test_generate_weekly_plan_base_phase_with_weather_uses_base_structure():
    planner = _planner()

    plan = planner.generate_weekly_plan(
        athlete_profile={"threshold_hr": 168},
        weather_forecast=[{"min_dew_hour": 6}] * 7,
        phase="BASE",
    )

    assert plan["daily_sessions"][2]["session_type"] == "TEMPO"
    assert plan["daily_sessions"][5]["session_type"] == "LONG_RUN"
    assert plan["daily_sessions"][0]["optimal_time"] == "6:00 (best conditions)"


def test_generate_weekly_plan_peak_phase_uses_peak_defaults():
    planner = _planner()

    plan = planner.generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase="PEAK")

    assert plan["daily_sessions"][1]["session_type"] == "INTERVALS"
    assert plan["daily_sessions"][3]["distance_km"] == 12


def test_generate_weekly_plan_taper_phase_keeps_race_day_and_message():
    planner = _planner()

    plan = planner.generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase="TAPER")

    assert plan["daily_sessions"][6]["session_type"] == "RACE"
    assert plan["motivation"].startswith("Trust the taper")


def test_get_today_session_without_plan_returns_easy_default():
    planner = _planner()

    session = planner.get_today_session()

    assert session["session_type"] == "EASY"
    assert session["target_hr_zone"] == "Z2"


def test_get_today_session_when_today_missing_returns_rest_fallback():
    planner = _planner()
    planner.last_plan = {
        "daily_sessions": [
            {"day": "NotADay", "session_type": "TEMPO", "distance_km": 10, "details": "x"}
        ]
    }

    session = planner.get_today_session()

    assert session["session_type"] == "REST"
    assert session["duration_min"] == 0


def test_get_today_session_estimates_duration_for_missing_duration(monkeypatch):
    planner = _planner()

    class _FakeNow:
        def strftime(self, _format):
            return "Monday"

    class _FakeDateTime:
        @staticmethod
        def now():
            return _FakeNow()

    monkeypatch.setattr("titan.features.weekly_planner.datetime", _FakeDateTime)
    planner.last_plan = {
        "daily_sessions": [
            {"day": "Monday", "session_type": "TEMPO", "distance_km": 10.0, "details": "Tempo"}
        ]
    }

    session = planner.get_today_session()

    assert session["duration_min"] == 45
    assert session["session_type"] == "TEMPO"


# ── T5-58: null HRV guard in _apply_hrv_adjustments ──────────────────────────

def test_apply_hrv_adjustments_does_not_raise_when_baseline_is_none() -> None:
    """T5-58: TypeError guard — baseline=None must not raise."""
    planner = _planner()
    structure = [{"session_type": "INTERVALS", "details": "i"}]

    result = planner._apply_hrv_adjustments(structure, {"baseline": None, "latest_hrv": 50.0})

    assert result[0]["session_type"] == "INTERVALS"


def test_apply_hrv_adjustments_does_not_raise_when_latest_hrv_is_none() -> None:
    """T5-58: TypeError guard — latest_hrv=None must not raise."""
    planner = _planner()
    structure = [{"session_type": "INTERVALS", "details": "i"}]

    result = planner._apply_hrv_adjustments(structure, {"baseline": 70.0, "latest_hrv": None})

    assert result[0]["session_type"] == "INTERVALS"


def test_apply_hrv_adjustments_does_not_downgrade_when_both_hrv_are_none() -> None:
    """T5-58: when both HRV values are None, structure is unchanged."""
    planner = _planner()
    structure = [
        {"session_type": "INTERVALS", "details": "i"},
        {"session_type": "TEMPO", "details": "t"},
    ]

    result = planner._apply_hrv_adjustments(structure, {"baseline": None, "latest_hrv": None})

    assert result[0]["session_type"] == "INTERVALS"
    assert result[1]["session_type"] == "TEMPO"


# ── existing tests ────────────────────────────────────────────────────────────

def test_apply_hrv_adjustments_downgrades_intervals_and_tempo_when_suppressed():
    planner = _planner()
    structure = [
        {"session_type": "INTERVALS", "details": "i"},
        {"session_type": "TEMPO", "details": "t"},
        {"session_type": "EASY", "details": "e"},
    ]

    adjusted = planner._apply_hrv_adjustments(structure, {"baseline": 70, "latest_hrv": 50})

    assert adjusted[0]["session_type"] == "TEMPO"
    assert "downgraded from intervals" in adjusted[0]["details"]
    assert adjusted[1]["session_type"] == "EASY"


def test_apply_weather_adjustments_only_sets_optimal_time_when_hour_truthy():
    planner = _planner()
    structure = [{"day": "Monday"}, {"day": "Tuesday"}, {"day": "Wednesday"}]
    forecast = [{"min_dew_hour": 5}, {"min_dew_hour": 0}]

    adjusted = planner._apply_weather_adjustments(structure, forecast)

    assert adjusted[0]["optimal_time"] == "5:00 (best conditions)"
    assert "optimal_time" not in adjusted[1]
    assert "optimal_time" not in adjusted[2]


def test_get_motivational_message_unknown_phase_uses_default_message():
    planner = _planner()

    message = planner._get_motivational_message("OFFSEASON", tsb=0)

    assert message == "Train smart, recover hard! 💪"
