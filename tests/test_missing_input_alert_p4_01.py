"""P4-01 (ADR-0069 §5): a missing HRV, RHR or TSB opens a degraded-mode timer.

When H2, H3 or H4_MISSING applies, ``data_confidence_low`` is set and a timer opens for
that input. If the gap lasts 24 hours, one notification is sent; the next one only after the
input has come back and gone missing again. The decision does not change: the ADR-0051 EASY
ceiling is already there. Synthetic data only.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time

from tests.test_daily_coach_characterization import (  # noqa: F401  (world is a fixture)
    _run_scenario,
    normal_day,
    world,
)
from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DegradedModeTracker

T0 = "2026-03-02 07:30:00"


@pytest.fixture
def db(tmp_path: Path):
    d = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    yield d
    d.close()


def _states(db) -> dict[str, str]:
    return dict(db.get_all_degraded_mode_states(athlete_id="owner"))


@pytest.mark.unit
def test_one_alert_after_24_hours_then_none_while_still_missing(db):
    sent: list[str] = []
    with freeze_time(T0) as clock:
        tracker = DegradedModeTracker(db=db)
        tracker.update_missing_inputs({"hrv_missing": "HRV"}, sent.append)
        assert sent == []
        assert "hrv_missing" in _states(db)
        clock.tick(timedelta(hours=24))
        tracker.update_missing_inputs({"hrv_missing": "HRV"}, sent.append)
        assert len(sent) == 1
        assert "HRV" in sent[0] and "24h" in sent[0]
        clock.tick(timedelta(hours=24))
        tracker.update_missing_inputs({"hrv_missing": "HRV"}, sent.append)
        assert len(sent) == 1


@pytest.mark.unit
def test_the_timer_closes_when_the_input_returns(db):
    sent: list[str] = []
    with freeze_time(T0) as clock:
        tracker = DegradedModeTracker(db=db)
        tracker.update_missing_inputs({"rhr_missing": "RHR"}, sent.append)
        clock.tick(timedelta(hours=24))
        tracker.update_missing_inputs({"rhr_missing": "RHR"}, sent.append)
        tracker.update_missing_inputs({}, sent.append)
        assert not any(k.startswith("rhr_missing") for k in _states(db))
        tracker.update_missing_inputs({"rhr_missing": "RHR"}, sent.append)
        clock.tick(timedelta(hours=24))
        tracker.update_missing_inputs({"rhr_missing": "RHR"}, sent.append)
        assert len(sent) == 2


@pytest.mark.unit
def test_a_restarted_worker_does_not_alert_twice(db):
    sent: list[str] = []
    with freeze_time(T0) as clock:
        DegradedModeTracker(db=db).update_missing_inputs({"tsb_missing": "TSB"}, sent.append)
        clock.tick(timedelta(hours=24))
        DegradedModeTracker(db=db).update_missing_inputs({"tsb_missing": "TSB"}, sent.append)
        clock.tick(timedelta(hours=24))
        DegradedModeTracker(db=db).update_missing_inputs({"tsb_missing": "TSB"}, sent.append)
    assert len(sent) == 1


@pytest.mark.unit
def test_a_failed_alert_is_tried_again_next_time(db):
    sent: list[str] = []

    def _down(_msg):
        raise RuntimeError("telegram down (synthetic)")

    with freeze_time(T0) as clock:
        tracker = DegradedModeTracker(db=db)
        tracker.update_missing_inputs({"hrv_missing": "HRV"}, sent.append)
        clock.tick(timedelta(hours=24))
        tracker.update_missing_inputs({"hrv_missing": "HRV"}, _down)
        clock.tick(timedelta(hours=24))
        tracker.update_missing_inputs({"hrv_missing": "HRV"}, sent.append)
    assert len(sent) == 1


def test_the_morning_alerts_once_for_the_missing_hrv_baseline(world):
    """The first mornings have no 14-day HRV baseline: H2_MISSING applies (ADR-0051)."""
    days = _run_scenario(world, [normal_day(i) for i in range(4)], soreness=1)["days"]
    alerts = [[t for t in day["telegram"] if "HRV baseline missing for over" in t] for day in days]
    assert alerts[0] == []
    assert len(alerts[1]) == 1
    assert alerts[2] == [] and alerts[3] == []
    assert not any("data_confidence_low unresolved" in t for day in days for t in day["telegram"])


def test_the_trace_marks_low_confidence_when_an_input_is_missing(world, monkeypatch):
    from titan.orchestration.daily_coach import DailyCoach

    traces: list[dict] = []
    original = DailyCoach._effect_runner

    def spy(self, result):
        traces.append(dict(result.decision_trace))
        return original(self, result)

    monkeypatch.setattr(DailyCoach, "_effect_runner", spy)
    _run_scenario(world, [normal_day(0)], soreness=1)
    assert traces[-1]["data_confidence_low"] is True
    assert traces[-1]["missing_inputs"].get("hrv_missing") == "HRV baseline"
