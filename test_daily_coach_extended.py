#!/usr/bin/env python3
"""
Extended tests for DailyCoach orchestrator.

Previous coverage was limited to 4 helper method tests via TestDailyCoachHelpers.
This file adds:
  - _persist_garmin_data() — activity saving, sleep extraction, metrics row
  - _get_baseline_rhr() — rolling N-day average from DB
  - _get_recent_trimp() — TRIMP extraction with sRPE fallback
  - _feed_load_engines() — DB → TSBEngine reload (clear + re-add)
  - _hydrate_engines_from_db() — startup hydration with cold DB
  - run_morning_routine() — fully mocked happy-path smoke test

Run with:
    pytest test_daily_coach_extended.py -v
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("GARMIN_EMAIL",        "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD",     "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN",  "")
os.environ.setdefault("TELEGRAM_CHAT_ID",    "12345")
os.environ.setdefault("WEATHER_API_KEY",     "test")
os.environ.setdefault("WEATHER_LOCATION",    "Athens,GR")

sys.path.insert(0, str(Path(__file__).parent))


def _json_events(caplog):
    events = []
    for record in caplog.records:
        try:
            events.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            continue
    return events



# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _make_coach(tmp_path):
    """
    Build a DailyCoach with all external dependencies mocked.
    Returns (coach, mocks_dict).
    """
    from titan.core.database import DatabaseManager
    from titan.features.nutrition_optimizer import NutritionOptimizer
    from titan.features.weekly_planner import WeeklyPlanGenerator
    from titan.orchestration.daily_coach import DailyCoach
    from titan.science.acwr_engine import ACWREngine
    from titan.science.glycogen_model import GlycogenModel
    from titan.science.hrv_engine import HRVGuidedEngine
    from titan.science.readiness_engine import ReadinessEngine
    from titan.science.tsb_engine import TSBEngine

    db       = DatabaseManager(str(tmp_path / "coach_test.db"))
    hrv_eng  = HRVGuidedEngine()
    tsb_eng  = TSBEngine()
    readiness= ReadinessEngine()

    garmin_mock = MagicMock()
    garmin_mock.sync_all.return_value = {
        "activities": [], "sleep": [], "hrv": [], "hrr": [], "weight": [],
    }

    weather_mock  = MagicMock()
    telegram_mock = MagicMock()
    telegram_mock.send_daily_coaching.return_value = True

    opt_time_mock = MagicMock()
    opt_time_mock.calculate_optimal_time.return_value = {
        "recommended_time": "07:30",
        "dew_point": 12.0,
        "quality": "GOOD",
        "reasoning": [],
    }

    glycogen_model = GlycogenModel()
    nutrition      = NutritionOptimizer(glycogen_model)

    acwr_eng = ACWREngine()
    planner  = WeeklyPlanGenerator(hrv_eng, tsb_eng, acwr_eng)

    coach = DailyCoach(
        garmin_sync        = garmin_mock,
        weather_api        = weather_mock,
        telegram_bot       = telegram_mock,
        hrv_engine         = hrv_eng,
        tsb_engine         = tsb_eng,
        readiness_engine   = readiness,
        optimal_time_calc  = opt_time_mock,
        nutrition_optimizer= nutrition,
        weekly_planner     = planner,
        db                 = db,
    )

    return coach, {
        "db": db,
        "garmin": garmin_mock,
        "telegram": telegram_mock,
        "hrv": hrv_eng,
        "tsb": tsb_eng,
        "nutrition": nutrition,
        "planner": planner,
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. _persist_garmin_data
# ════════════════════════════════════════════════════════════════════════════

class TestPersistGarminData:
    """Tests for DailyCoach._persist_garmin_data()."""

    @pytest.fixture
    def coach(self, tmp_path):
        c, _ = _make_coach(tmp_path)
        return c

    def _call(self, coach, garmin_data):
        today = datetime.now().strftime("%Y-%m-%d")
        return coach._persist_garmin_data(garmin_data, today)

    def test_empty_data_returns_defaults(self, coach):
        rhr, sleep_score, sleep_hours = self._call(coach, {
            "activities": [], "sleep": [], "hrv": [], "weight": [],
        })
        assert rhr == 0
        assert sleep_score == 75   # conservative default
        assert sleep_hours == 7.5  # default

    def test_activity_saved_to_db(self, coach):
        today = datetime.now().strftime("%Y-%m-%d")
        garmin_data = {
            "activities": [{
                "date": today,
                "session_type": "EASY",
                "distance_km": 8.0,
                "duration_sec": 2400,
                "avg_hr": 140,
                "max_hr": 165,
                "rpe": 5,
                "name": "Morning run",
            }],
            "sleep": [], "hrv": [], "weight": [],
        }
        coach._persist_garmin_data(garmin_data, today)
        loads = coach.db.get_training_load_history(7)
        assert len(loads) >= 1

    def test_sleep_entry_extracts_rhr(self, coach):
        garmin_data = {
            "activities": [],
            "sleep": [{"restingHeartRate": 48, "sleepTimeSeconds": 27000}],
            "hrv": [], "weight": [],
        }
        rhr, _, _ = self._call(coach, garmin_data)
        assert rhr == 48

    def test_sleep_entry_extracts_hours(self, coach):
        garmin_data = {
            "activities": [],
            "sleep": [{"sleepTimeSeconds": 28800}],  # 8 hours
            "hrv": [], "weight": [],
        }
        _, _, hours = self._call(coach, garmin_data)
        assert abs(hours - 8.0) < 0.1

    def test_malformed_activity_does_not_raise(self, coach):
        """A missing/invalid activity field must be skipped, not crash."""
        garmin_data = {
            "activities": [{"date": None, "session_type": None}],
            "sleep": [], "hrv": [], "weight": [],
        }
        # Should not raise
        self._call(coach, garmin_data)

    def test_empty_sleep_entry_skipped(self, coach):
        """None / empty sleep entries must be skipped gracefully."""
        garmin_data = {
            "activities": [],
            "sleep": [None, {}],
            "hrv": [], "weight": [],
        }
        rhr, sleep_score, _ = self._call(coach, garmin_data)
        assert rhr == 0
        assert sleep_score == 75  # default unchanged


# ════════════════════════════════════════════════════════════════════════════
# 2. _get_baseline_rhr
# ════════════════════════════════════════════════════════════════════════════

class TestGetBaselineRhr:

    @pytest.fixture
    def coach(self, tmp_path):
        c, _ = _make_coach(tmp_path)
        return c

    def test_empty_db_returns_default(self, coach):
        assert coach._get_baseline_rhr(days=7) == 50.0

    def test_returns_average_of_stored_rhr(self, coach):
        base = datetime.now() - timedelta(days=3)
        for i in range(4):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            coach.db.save_daily_metric(date=d, rhr=45 + i)  # 45, 46, 47, 48
        result = coach._get_baseline_rhr(days=7)
        # Average of 45+46+47+48 = 46.5
        assert abs(result - 46.5) < 0.5

    def test_excludes_entries_outside_window(self, coach):
        old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        coach.db.save_daily_metric(date=old_date, rhr=60)
        # 60 bpm entry is 30d old → excluded from 7d window → falls back to 50
        result = coach._get_baseline_rhr(days=7)
        assert result == 50.0


# ════════════════════════════════════════════════════════════════════════════
# 3. _get_recent_trimp
# ════════════════════════════════════════════════════════════════════════════

class TestGetRecentTrimp:

    @pytest.fixture
    def coach(self, tmp_path):
        c, _ = _make_coach(tmp_path)
        return c

    def test_empty_activities_returns_zero(self, coach):
        assert coach._get_recent_trimp([]) == 0.0

    def test_uses_trimp_field_when_present(self, coach):
        activities = [{"trimp": 80.0}, {"trimp": 60.0}]
        result = coach._get_recent_trimp(activities)
        assert result == pytest.approx(140.0, abs=0.1)

    def test_falls_back_to_training_load(self, coach):
        """When trimp=0, falls back to training_load * 0.6."""
        activities = [{"trimp": 0, "training_load": 100}]
        result = coach._get_recent_trimp(activities)
        assert result == pytest.approx(60.0, abs=0.1)

    def test_mixed_trimp_and_load(self, coach):
        activities = [
            {"trimp": 80.0},
            {"trimp": 0, "training_load": 100},
        ]
        result = coach._get_recent_trimp(activities)
        # 80 + (100 * 0.6) = 140
        assert result == pytest.approx(140.0, abs=0.1)

    def test_missing_fields_treated_as_zero(self, coach):
        activities = [{}]
        assert coach._get_recent_trimp(activities) == 0.0


# ════════════════════════════════════════════════════════════════════════════
# 4. _feed_load_engines
# ════════════════════════════════════════════════════════════════════════════

class TestFeedLoadEngines:

    @pytest.fixture
    def coach(self, tmp_path):
        c, _ = _make_coach(tmp_path)
        return c

    def test_empty_db_leaves_tsb_no_loads(self, coach):
        coach._feed_load_engines([])
        assert len(coach.tsb.daily_loads) == 0

    def test_loads_from_db_populate_tsb(self, coach):
        base = datetime.now() - timedelta(days=5)
        for i in range(5):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            coach.db.save_session(
                date=d, session_type="EASY",
                distance_km=8.0, duration_sec=2400, rpe=5,
            )
        coach._feed_load_engines([])
        assert len(coach.tsb.daily_loads) == 5

    def test_reload_does_not_double_count(self, coach):
        base = datetime.now() - timedelta(days=3)
        for i in range(3):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            coach.db.save_session(
                date=d, session_type="EASY",
                distance_km=8.0, duration_sec=2400, rpe=5,
            )
        coach._feed_load_engines([])
        ctl_first = coach.tsb.calculate_ctl()

        coach._feed_load_engines([])  # second call — should produce same CTL
        ctl_second = coach.tsb.calculate_ctl()

        assert ctl_first == ctl_second, "Double-reload should not change CTL"


# ════════════════════════════════════════════════════════════════════════════
# 5. _hydrate_engines_from_db (startup hydration)
# ════════════════════════════════════════════════════════════════════════════

class TestHydrateEnginesFromDb:

    @pytest.fixture
    def coach(self, tmp_path):
        c, _ = _make_coach(tmp_path)
        return c

    def test_cold_db_hydration_does_not_raise(self, coach):
        """Hydrating from an empty DB (first-ever run) must not raise."""
        # Coach already ran _hydrate_engines_from_db in __init__.
        # Call it again explicitly to verify idempotence.
        coach._hydrate_engines_from_db()  # should not raise

    def test_hrv_data_loaded_after_hydration(self, coach):
        """After inserting HRV metrics and re-hydrating, engine has data."""
        base = datetime.now() - timedelta(days=5)
        for i in range(5):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            coach.db.save_daily_metric(date=d, hrv=60 + i)

        coach.hrv.hrv_log.clear()
        coach._hydrate_engines_from_db()
        assert len(coach.hrv.hrv_log) > 0

    def test_weight_history_loaded_after_hydration(self, coach):
        base = datetime.now() - timedelta(days=5)
        for i in range(5):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            coach.db.save_daily_metric(date=d, weight=75.0 - i * 0.1)

        coach.nutrition.weight_history.clear()
        coach._hydrate_engines_from_db()
        assert len(coach.nutrition.weight_history) > 0

    def test_tsb_loads_after_hydration(self, coach):
        base = datetime.now() - timedelta(days=5)
        for i in range(5):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            coach.db.save_session(
                date=d, session_type="EASY",
                distance_km=8.0, duration_sec=2400, rpe=5,
            )

        coach.tsb.daily_loads.clear()
        coach._hydrate_engines_from_db()
        assert len(coach.tsb.daily_loads) > 0

    def test_double_hydration_does_not_drift(self, coach):
        """Calling hydration twice must not double-count loads."""
        base = datetime.now() - timedelta(days=3)
        for i in range(3):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            coach.db.save_session(
                date=d, session_type="EASY",
                distance_km=8.0, duration_sec=2400, rpe=5,
            )

        coach._hydrate_engines_from_db()
        ctl_1 = coach.tsb.calculate_ctl()

        coach._hydrate_engines_from_db()
        ctl_2 = coach.tsb.calculate_ctl()

        assert ctl_1 == ctl_2, "CTL drifted after double hydration"


# ════════════════════════════════════════════════════════════════════════════
# 6. run_morning_routine — full smoke test with mocked integrations
# ════════════════════════════════════════════════════════════════════════════

class TestRunMorningRoutineSmoke:

    @pytest.fixture
    def coach_mocks(self, tmp_path):
        return _make_coach(tmp_path)

    def test_morning_routine_returns_bool(self, coach_mocks):
        coach, mocks = coach_mocks
        result = coach.run_morning_routine(soreness=3)
        assert isinstance(result, bool)

    def test_morning_routine_sends_telegram_message(self, coach_mocks):
        coach, mocks = coach_mocks
        coach.run_morning_routine(soreness=3)
        mocks["telegram"].send_daily_coaching.assert_called_once()

    def test_morning_routine_calls_garmin_sync(self, coach_mocks):
        coach, mocks = coach_mocks
        coach.run_morning_routine(soreness=3)
        mocks["garmin"].sync_all.assert_called_once()

    def test_morning_routine_with_activities_saves_to_db(self, coach_mocks, tmp_path):
        coach, mocks = coach_mocks
        today = datetime.now().strftime("%Y-%m-%d")
        mocks["garmin"].sync_all.return_value = {
            "activities": [{
                "date":         today,
                "session_type": "EASY",
                "distance_km":  10.0,
                "duration_sec": 3600,
                "avg_hr":       140,
                "max_hr":       165,
                "rpe":          5,
                "name":         "Test Run",
            }],
            "sleep": [], "hrv": [], "hrr": [], "weight": [],
        }
        coach.run_morning_routine(soreness=3)
        loads = coach.db.get_training_load_history(7)
        assert len(loads) >= 1


    def test_morning_routine_normalizes_vo2_contract(self, coach_mocks):
        coach, mocks = coach_mocks

        def fake_apply_constraints(session_plan, context):
            out = dict(session_plan)
            out['vo2_eligibility'] = {
                'eligible': False,
                'failed_conditions': 'V1',
                'detailed_failed_conditions': {'code': 'V1'},
            }
            return out

        coach.governance.apply_constraints = fake_apply_constraints
        coach.run_morning_routine(soreness=3)
        payload = mocks["telegram"].send_daily_coaching.call_args[0][0]
        vo2 = payload['vo2_eligibility']
        assert vo2['failed_conditions'] == ['V1']
        assert vo2['detailed_failed_conditions'] == []


class TestDailyCoachErrorTaxonomy:

    @pytest.fixture
    def coach_mocks(self, tmp_path):
        return _make_coach(tmp_path)

    def test_step_event_logs_failure_class_for_delivery(self, coach_mocks, caplog):
        coach, mocks = coach_mocks
        caplog.set_level(logging.INFO)

        mocks["telegram"].send_daily_coaching.side_effect = RuntimeError("telegram down")

        with pytest.raises(RuntimeError):
            coach.run_morning_routine(soreness=3)

        events = _json_events(caplog)
        step12 = [
            e for e in events
            if e.get("flow") == "daily_coach"
            and e.get("action") == "step_event"
            and e.get("step_number") == 12
        ]
        assert step12
        assert step12[-1]["outcome"] == "FAILED"
        assert step12[-1]["failure_class"] == "DELIVERY_ERROR"

    def test_activity_persist_emits_per_activity_outcomes(self, coach_mocks, caplog):
        coach, _ = coach_mocks
        caplog.set_level(logging.INFO)

        coach.db.save_session = MagicMock(side_effect=[None, RuntimeError("db busy")])
        today = datetime.now().strftime("%Y-%m-%d")
        coach._persist_garmin_data(
            {
                "activities": [
                    {"date": today, "session_type": "EASY"},
                    {"date": today, "session_type": "EASY"},
                ],
                "sleep": [],
                "hrv": [],
                "weight": [],
            },
            today,
        )

        events = _json_events(caplog)
        activity_events = [
            e for e in events
            if e.get("flow") == "daily_coach" and e.get("action") == "activity_persist"
        ]
        outcomes = [e.get("outcome") for e in activity_events]
        assert "ACTIVITY_PERSISTED" in outcomes
        assert "ACTIVITY_SKIPPED" in outcomes
