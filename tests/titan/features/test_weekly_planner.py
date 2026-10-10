import pytest

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


@pytest.mark.unit
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


@pytest.mark.unit
def test_analyze_past_week_empty_sessions_returns_unknown_readiness():
    planner = _planner()

    analysis = planner.analyze_past_week([])

    assert analysis["total_km"] == 0
    assert analysis["readiness"] == "UNKNOWN"


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
def test_generate_weekly_plan_peak_phase_uses_peak_defaults():
    planner = _planner()

    plan = planner.generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase="PEAK")

    assert plan["daily_sessions"][1]["session_type"] == "INTERVALS"
    assert plan["daily_sessions"][3]["distance_km"] == 12


@pytest.mark.unit
def test_generate_weekly_plan_taper_phase_ends_with_an_easy_run_and_keeps_message():
    """SV-13 / D-061: without a race date the taper Sunday is EASY 8 km, not a 42.195 km RACE."""
    planner = _planner()

    plan = planner.generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase="TAPER")

    sunday = plan["daily_sessions"][6]
    assert (sunday["session_type"], sunday["distance_km"]) == ("EASY", 8)
    assert all(d["session_type"] != "RACE" for d in plan["daily_sessions"])
    assert plan["motivation"].startswith("Trust the taper")


@pytest.mark.unit
def test_get_today_session_without_plan_returns_easy_default():
    planner = _planner()

    session = planner.get_today_session()

    assert session["session_type"] == "EASY"
    assert session["target_hr_zone"] == "Z2"


@pytest.mark.unit
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


@pytest.mark.unit
def test_get_today_session_estimates_duration_for_missing_duration(monkeypatch):
    planner = _planner()

    class _FakeNow:
        def strftime(self, _format):
            return "Monday"

    class _FakeDateTime:
        @staticmethod
        def now(tz=None):
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

@pytest.mark.unit
def test_apply_hrv_adjustments_does_not_raise_when_baseline_is_none() -> None:
    """T5-58: TypeError guard — baseline=None must not raise."""
    planner = _planner()
    structure = [{"session_type": "INTERVALS", "details": "i"}]

    result = planner._apply_hrv_adjustments(structure, {"baseline": None, "latest_hrv": 50.0})

    assert result[0]["session_type"] == "INTERVALS"


@pytest.mark.unit
def test_apply_hrv_adjustments_does_not_raise_when_latest_hrv_is_none() -> None:
    """T5-58: TypeError guard — latest_hrv=None must not raise."""
    planner = _planner()
    structure = [{"session_type": "INTERVALS", "details": "i"}]

    result = planner._apply_hrv_adjustments(structure, {"baseline": 70.0, "latest_hrv": None})

    assert result[0]["session_type"] == "INTERVALS"


@pytest.mark.unit
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

@pytest.mark.unit
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


@pytest.mark.unit
def test_apply_weather_adjustments_only_sets_optimal_time_when_hour_truthy():
    planner = _planner()
    structure = [{"day": "Monday"}, {"day": "Tuesday"}, {"day": "Wednesday"}]
    forecast = [{"min_dew_hour": 5}, {"min_dew_hour": 0}]

    adjusted = planner._apply_weather_adjustments(structure, forecast)

    assert adjusted[0]["optimal_time"] == "5:00 (best conditions)"
    assert "optimal_time" not in adjusted[1]
    assert "optimal_time" not in adjusted[2]


@pytest.mark.unit
def test_get_motivational_message_unknown_phase_uses_default_message():
    planner = _planner()

    message = planner._get_motivational_message("OFFSEASON", tsb=0)

    assert message == "Train smart, recover hard! 💪"


# ── T5-57: should_replan() mid-week trigger ───────────────────────────────────


@pytest.mark.unit
def test_should_replan_returns_false_when_all_conditions_nominal():
    """T5-57: no triggers → should_replan returns False."""
    planner = _planner(baseline=60, latest_hrv=58)

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 58.0,
            "governance_events": [],
            "illness_flag": False,
        }
    )

    assert result is False


@pytest.mark.unit
def test_should_replan_returns_true_when_hrv_drops_more_than_10ms_below_baseline():
    """T5-57: HRV drop > 10ms below engine baseline triggers replan."""
    planner = _planner(baseline=65, latest_hrv=65)

    # 65 - 54 = 11ms drop > 10ms threshold
    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 54.0,
            "governance_events": [],
            "illness_flag": False,
        }
    )

    assert result is True


@pytest.mark.unit
def test_should_replan_returns_false_when_hrv_drop_exactly_10ms_below_baseline():
    """T5-57: HRV drop == 10ms (not strictly greater) → no trigger."""
    planner = _planner(baseline=65, latest_hrv=65)

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 55.0,
            "governance_events": [],
            "illness_flag": False,
        }
    )

    assert result is False


@pytest.mark.unit
def test_should_replan_returns_true_when_hard_stop_governance_event_present():
    """T5-57: HARD_STOP_SAFETY_GATES governance event in last 24h triggers replan."""
    planner = _planner()

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 60.0,
            "governance_events": [{"type": "HARD_STOP_SAFETY_GATES", "hours_ago": 12}],
            "illness_flag": False,
        }
    )

    assert result is True


@pytest.mark.unit
def test_should_replan_ignores_hard_stop_event_older_than_24h():
    """T5-57: governance HARD_STOP older than 24h does not trigger replan."""
    planner = _planner()

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 60.0,
            "governance_events": [{"type": "HARD_STOP_SAFETY_GATES", "hours_ago": 25}],
            "illness_flag": False,
        }
    )

    assert result is False


@pytest.mark.unit
def test_should_replan_ignores_non_hard_stop_governance_events():
    """T5-57: governance events that are not HARD_STOP type do not trigger replan."""
    planner = _planner()

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 60.0,
            "governance_events": [{"type": "INTENSITY_GATE_YELLOW", "hours_ago": 6}],
            "illness_flag": False,
        }
    )

    assert result is False


@pytest.mark.unit
def test_should_replan_returns_true_when_illness_flag_set():
    """T5-57: illness_flag=True triggers replan."""
    planner = _planner()

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 60.0,
            "governance_events": [],
            "illness_flag": True,
        }
    )

    assert result is True


@pytest.mark.unit
def test_should_replan_returns_true_on_multiple_conditions():
    """T5-57: multiple triggers simultaneously → still True (OR semantics)."""
    planner = _planner(baseline=65, latest_hrv=65)

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 50.0,  # 15ms drop
            "governance_events": [{"type": "HARD_STOP_SAFETY_GATES", "hours_ago": 3}],
            "illness_flag": True,
        }
    )

    assert result is True


@pytest.mark.unit
def test_should_replan_tolerates_missing_hrv_latest_ms():
    """T5-57: garmin_data missing hrv_latest_ms → HRV condition not triggered."""
    planner = _planner(baseline=65, latest_hrv=65)

    result = planner.should_replan(
        garmin_data={
            "governance_events": [],
            "illness_flag": False,
        }
    )

    assert result is False


@pytest.mark.unit
def test_should_replan_tolerates_missing_governance_events():
    """T5-57: garmin_data missing governance_events key → no error, no trigger."""
    planner = _planner()

    result = planner.should_replan(
        garmin_data={
            "hrv_latest_ms": 60.0,
            "illness_flag": False,
        }
    )

    assert result is False


@pytest.mark.unit
def test_should_replan_triggers_generate_weekly_plan_and_updates_last_plan(monkeypatch):
    """T5-57: when should_replan() returns True, calling it with athlete data re-evaluates plan."""
    planner = _planner(baseline=65, latest_hrv=65)
    planner.last_plan = {"phase": "BUILD", "daily_sessions": [], "total_km": 50}

    garmin_data = {
        "hrv_latest_ms": 50.0,  # triggers replan
        "governance_events": [],
        "illness_flag": False,
        "athlete_profile": {"threshold_hr": 168},
        "phase": "BUILD",
    }

    triggered = planner.should_replan(garmin_data)
    assert triggered is True

    # Caller re-evaluates plan after should_replan returns True
    new_plan = planner.generate_weekly_plan(
        athlete_profile=garmin_data.get("athlete_profile", {}),
        weather_forecast=None,
        phase=garmin_data.get("phase", "BUILD"),
    )

    assert new_plan is not None
    assert planner.last_plan is new_plan


class _FakeDB:
    def __init__(self, activities):
        self.activities = activities

    def get_recent_activities(self, limit=90, athlete_id="owner"):
        return self.activities[:limit]


def _runs(km_per_week, today):
    from datetime import timedelta

    return [
        {"date": (today - timedelta(days=d)).isoformat(), "distance_km": km_per_week / 4}
        for w in range(4) for d in (7 * w + 1, 7 * w + 3, 7 * w + 5, 7 * w + 7)
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("km_per_week", "expected_build_km"),
    [
        pytest.param(20.0, 22.0, id="novice-20km-gets-22km"),
        pytest.param(100.0, 110.0, id="high-volume-100km-gets-110km"),
        pytest.param(0.0, 30.0, id="no-history-gets-30km"),
    ],
)
def test_build_week_follows_the_last_four_weeks_plus_at_most_10pct(km_per_week, expected_build_km):
    """SV-14 / D-062: the week is the 4-week average + 10%, or 30 km with no runs."""
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    activities = _runs(km_per_week, today) if km_per_week else []
    planner = WeeklyPlanGenerator(
        hrv_engine=_FakeHRVEngine(), tsb_engine=_FakeTSBEngine(), acwr_engine=_FakeACWR(),
        db=_FakeDB(activities),
    )

    plan = planner.generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase="BUILD")

    assert plan["total_km"] == pytest.approx(expected_build_km, abs=0.5)
    long_run = max(d["distance_km"] for d in plan["daily_sessions"])
    assert long_run == pytest.approx(22 * expected_build_km / 77, abs=0.1)


@pytest.mark.unit
@pytest.mark.parametrize("phase", ["BASE", "BUILD", "PEAK", "TAPER"])
def test_no_phase_goes_above_the_recent_average_plus_10pct(phase):
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    planner = WeeklyPlanGenerator(
        hrv_engine=_FakeHRVEngine(), tsb_engine=_FakeTSBEngine(), acwr_engine=_FakeACWR(),
        db=_FakeDB(_runs(40.0, today)),
    )

    plan = planner.generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase=phase)

    assert plan["total_km"] <= 44.0 + 0.5


@pytest.mark.unit
def test_runs_older_than_four_weeks_do_not_count():
    from datetime import UTC, datetime, timedelta

    today = datetime.now(UTC).date()
    old = [{"date": (today - timedelta(days=40)).isoformat(), "distance_km": 200.0}]
    planner = WeeklyPlanGenerator(
        hrv_engine=_FakeHRVEngine(), tsb_engine=_FakeTSBEngine(), acwr_engine=_FakeACWR(),
        db=_FakeDB(old),
    )

    plan = planner.generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase="BUILD")

    assert plan["total_km"] == pytest.approx(30.0, abs=0.5)


@pytest.mark.unit
def test_without_a_database_the_templates_keep_their_kilometres():
    plan = _planner().generate_weekly_plan(athlete_profile={}, weather_forecast=None, phase="BUILD")

    assert plan["total_km"] == 77


@pytest.mark.unit
def test_a_short_history_is_averaged_over_its_own_length():
    """One week of 40 km from a new athlete is 40 km a week, not 10 (40 / 4 weeks)."""
    from datetime import UTC, datetime, timedelta

    today = datetime.now(UTC).date()
    week = [{"date": (today - timedelta(days=d)).isoformat(), "distance_km": 10.0} for d in (1, 3, 5, 7)]
    planner = WeeklyPlanGenerator(
        hrv_engine=_FakeHRVEngine(), tsb_engine=_FakeTSBEngine(), acwr_engine=_FakeACWR(),
        db=_FakeDB(week),
    )

    assert planner.recent_weekly_km() == pytest.approx(40.0)
