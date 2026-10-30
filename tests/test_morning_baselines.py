"""SG-01 / SG-06 (D-105): the HRV and RHR baselines of the morning, through the real DailyCoach.

- With fewer than 7 earlier HRV nights the baseline cannot be computed. It is missing,
  never 0.0: a 0.0 baseline made H2 compare 0 − today against the threshold, so a new
  athlete's HRV collapse went through as TEMPO. Missing baseline → EASY ceiling
  (ADR-0051, lock DATA_MISSING_CONSERVATIVE_H2).
- The RHR baseline for H3 and the HRV baseline for H2 are the days before today:
  today's reading no longer dilutes its own baseline.

Only I/O collaborators are stubbed (Garmin, Telegram, planner, weather, nutrition);
engines, governance and the database are the real ones.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DailyCoach
from titan.orchestration.engine_registry import EngineRegistry
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.tsb_engine import LOAD_HISTORY_DAYS

pytestmark = pytest.mark.integration


class _Garmin:
    athlete_max_hr = 0

    def __init__(self, today: str, hrv: float, rhr: int, status: str | None = None) -> None:
        self.today, self.hrv, self.rhr, self.status = today, hrv, rhr, status

    def sync_all(self) -> dict:
        payload = {
            "activities": [],
            "sleep": [{"date": self.today, "resting_hr": self.rhr, "sleep_score": 82, "total_sleep_hours": 7.8}],
            "hrv": [{"date": self.today, "rmssd": self.hrv}],
            "hrr": [],
            "weight": [{"date": self.today, "weight_kg": 70.0}],
            "fueling_confirmed": True,
        }
        if self.status is not None:
            payload["status"] = self.status
        return payload


class _Telegram:
    def __init__(self) -> None:
        self.daily: list[dict] = []

    def send_daily_coaching(self, payload: dict) -> bool:
        self.daily.append(payload)
        return True

    def send_alert(self, **_k) -> bool:
        return True

    def send_structured_alert(self, **_k) -> bool:
        return True


class _Planner:
    last_plan = None

    def get_today_session(self, **_k) -> dict:
        return {"session_type": "TEMPO", "duration_min": 50, "distance_km": 10.0, "max_zone": 4, "volume_pct": 1.0}


class _OptimalTime:
    def calculate_optimal_time(self, **_k) -> dict:
        return {"recommended_time": "07:00", "weather_data_quality": "live"}


class _Nutrition:
    def analyze_weight_trend(self) -> dict:
        return {"current_weight": 70.0}

    def add_weight_entry(self, *_a, **_k) -> None:
        return None

    def calculate_daily_nutrition(self, **_k) -> dict:
        return {}


def _morning(tmp_path, monkeypatch, *, athlete_id: str, prior_nights: int, today_hrv: float,
             today_rhr: int = 50, prior_rhr: int = 50, rhr_nights: int | None = None,
             loads: dict[int, int] | None = None, fail_load_reload: bool = False,
             sync_status: str | None = None) -> tuple[dict, dict]:
    """Run one real morning; return (Telegram payload, stored governance decision)."""
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    try:
        now = datetime.now(UTC).date()
        today = now.isoformat()
        # A shared DB, as in the pilot: the owner has 14 days of decisions and no
        # overrides, so the override-lockdown ceiling does not hide the HRV/RHR gates.
        for i in range(1, 15):
            db.save_governance_decision({"athlete_profile_id": "owner", "date": (now - timedelta(days=i)).isoformat(),
                                         "session_planned": "EASY", "session_post_governance": "EASY"})
        for i in range(1, prior_nights + 1):
            # rhr_nights: only the N most recent earlier nights carry an RHR (SD-03).
            rhr = prior_rhr if rhr_nights is None or i <= rhr_nights else None
            db.save_daily_metric((now - timedelta(days=i)).isoformat(), hrv=75.0 + (i % 3), rhr=rhr,
                                 sleep_quality=80, weight=70.0, athlete_id=athlete_id)
        # loads: {days back: training load} stored before the morning (M0-22).
        for back, load in (loads or {}).items():
            db.save_session((now - timedelta(days=back)).isoformat(), "EASY", 10.0, 3000,
                            training_load=load, athlete_id=athlete_id)
        engines = EngineRegistry.from_db(db=db, athlete_id=athlete_id)
        telegram = _Telegram()
        coach = DailyCoach(
            garmin_sync=_Garmin(today, today_hrv, today_rhr, sync_status), weather_api=None, telegram_bot=telegram,
            hrv_engine=engines.hrv, tsb_engine=engines.tsb, readiness_engine=engines.readiness,
            optimal_time_calc=_OptimalTime(), nutrition_optimizer=_Nutrition(), weekly_planner=_Planner(),
            db=db, athlete_id=athlete_id, engines=engines,
        )
        if fail_load_reload:
            # Only the post-sync reload of the load history fails (M0-22); the coach was
            # built from the loads read before it.
            real = db.get_training_load_history

            def _locked(*a, **k):
                if k.get("days") == LOAD_HISTORY_DAYS:
                    raise sqlite3.OperationalError("synthetic: database is locked")
                return real(*a, **k)
            monkeypatch.setattr(db, "get_training_load_history", _locked)
        assert coach.run_morning_routine(soreness=2)
        assert telegram.daily, "no daily message was sent"
        return telegram.daily[-1], db.get_governance_decision_on(athlete_id, today) or {}
    finally:
        db.close()


_ABOVE_EASY = {"TEMPO", "INTERVALS", "PROGRESSIVE", "HAMMER", "LONG", "VO2"}


def test_new_athlete_hrv_collapse_without_baseline_is_capped_at_easy(tmp_path, monkeypatch):
    """SG-01: 3 earlier nights (~76 ms) and 35 ms today: no TEMPO, and the lock says why."""
    payload, decision = _morning(tmp_path, monkeypatch, athlete_id="ath_new", prior_nights=3, today_hrv=35.0)
    assert payload["session_type"] in {"EASY", "REST"}, payload["session_type"]
    assert payload["session_type"] not in _ABOVE_EASY
    assert "DATA_MISSING_CONSERVATIVE_H2" in payload["governance_locks"], payload["governance_locks"]
    assert payload["hrv_baseline"] is None
    assert decision.get("session_post_governance") in {"EASY", "REST"}


def test_hrv_collapse_with_ten_nights_is_still_rest(tmp_path, monkeypatch):
    """With a real baseline (10 earlier nights) the collapse is still an H2 hard stop."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=35.0)
    assert payload["session_type"] == "REST"
    assert "HARD_STOP_SAFETY_GATES" in payload["governance_locks"]
    assert "DATA_MISSING_CONSERVATIVE_H2" not in payload["governance_locks"]


def test_hrv_collapse_on_the_morning_with_six_earlier_nights_stays_rest(tmp_path, monkeypatch):
    """6 earlier nights + today = 7 readings: before D-105 that was a baseline and H2 fired.

    Leaving today out makes the baseline missing that morning; the fix must not turn
    that REST into an EASY, so the old baseline stays when only it fires H2.
    """
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=6, today_hrv=35.0)
    assert payload["session_type"] == "REST", payload["session_type"]
    assert "HARD_STOP_SAFETY_GATES" in payload["governance_locks"]


def test_six_earlier_nights_without_collapse_is_capped_at_easy(tmp_path, monkeypatch):
    """6 earlier nights and a normal HRV: the baseline before today is missing → EASY ceiling."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=6, today_hrv=76.0)
    assert payload["session_type"] in {"EASY", "REST"}, payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H2" in payload["governance_locks"]


def test_rhr_spike_is_not_diluted_by_todays_reading(tmp_path, monkeypatch):
    """SG-06: earlier RHR 50, today 58 (+8): H3 fires; today's 58 is not in its own baseline."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          today_rhr=58)
    assert payload["session_type"] == "REST", payload["session_type"]
    assert "HARD_STOP_SAFETY_GATES" in payload["governance_locks"]


def test_baseline_rhr_excludes_today(tmp_path):
    """The 7-day RHR baseline is the 7 days before today, today's row is not in it."""
    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    try:
        now = datetime.now(UTC).date()
        for i in range(0, 11):
            db.save_daily_metric((now - timedelta(days=i)).isoformat(), rhr=58 if i == 0 else 50,
                                 athlete_id="owner")
        assert db.get_baseline_rhr(days=7, athlete_id="owner") == 50.0
    finally:
        db.close()


def test_hrv_summary_with_too_few_readings_has_no_baseline():
    """Fewer than 7 readings: baseline and std_dev are None, never 0.0."""
    engine = HRVGuidedEngine()
    for i in range(1, 4):
        engine.add_hrv_measurement(f"2026-10-0{i}", 75.0)
    summary = engine.get_hrv_summary()
    assert summary["baseline"] is None
    assert summary["std_dev"] is None
    assert summary["latest_hrv"] == 75.0


def test_hrv_summary_baseline_before_date_leaves_out_that_day():
    """With before_date the baseline is the 7 readings before that day (today excluded)."""
    engine = HRVGuidedEngine()
    for i in range(1, 8):
        engine.add_hrv_measurement(f"2026-10-0{i}", 70.0)
    engine.add_hrv_measurement("2026-10-08", 35.0)
    summary = engine.get_hrv_summary(before_date="2026-10-08")
    assert summary["baseline"] == 70.0
    assert summary["latest_hrv"] == 35.0
    # Six earlier readings are not enough once today is left out.
    short = HRVGuidedEngine()
    for i in range(1, 7):
        short.add_hrv_measurement(f"2026-10-0{i}", 70.0)
    short.add_hrv_measurement("2026-10-07", 35.0)
    assert short.get_hrv_summary(before_date="2026-10-07")["baseline"] is None


def test_rhr_baseline_from_one_night_counts_as_missing(tmp_path, monkeypatch):
    """SD-03 (ADR-0073 point 4, D-164): one earlier night is not a baseline. Before, H3
    compared today against that one night and said CLEAR, so the day stayed TEMPO. Now a
    baseline needs at least 4 nights in the 7 days before today: EASY ceiling with
    DATA_MISSING_CONSERVATIVE_H3."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          today_rhr=52, rhr_nights=1)
    assert payload["session_type"] not in _ABOVE_EASY, payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H3" in payload["governance_locks"], payload["governance_locks"]


def test_rhr_below_the_floor_counts_as_missing_for_h3(tmp_path, monkeypatch):
    """SD-02 (ADR-0073 point 3, D-163): RHR 15 is a sensor error. It used to be clamped to 25
    and passed H3 as measured, so the day stayed TEMPO. Now it counts as missing: EASY ceiling
    with DATA_MISSING_CONSERVATIVE_H3."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          today_rhr=15)
    assert payload["session_type"] not in _ABOVE_EASY, payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H3" in payload["governance_locks"], payload["governance_locks"]


def test_rhr_baseline_with_four_nights_is_a_baseline(tmp_path, monkeypatch):
    """SD-03: 4 nights in the 7 days are enough; H3 compares as before (no missing-data lock)."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          today_rhr=52, rhr_nights=4)
    assert "DATA_MISSING_CONSERVATIVE_H3" not in payload["governance_locks"], payload["governance_locks"]


def test_rhr_spike_over_one_night_still_rests(tmp_path, monkeypatch):
    """SD-03 guard (only tightens): one night of 50 and today 60 (+10) fired H3 before.
    The thin baseline stays when only it fires H3, so the REST is not lost."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          today_rhr=60, rhr_nights=1)
    assert payload["session_type"] == "REST", payload["session_type"]
    assert "HARD_STOP_SAFETY_GATES" in payload["governance_locks"]


def test_rhr_above_the_ceiling_still_rests(tmp_path, monkeypatch):
    """SD-02 guard: RHR 200 is still clamped to 120 and H3 still gives REST (only tightens)."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          today_rhr=200)
    assert payload["session_type"] == "REST", payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H3" not in payload["governance_locks"]


def test_hrv_above_the_ceiling_counts_as_missing_for_h2(tmp_path, monkeypatch):
    """SD-01 (ADR-0073 point 2, D-165): HRV 400 ms is a sensor error. It reached H2 as a valid
    high reading, so H2 said CLEAR and the day stayed TEMPO. Now it counts as missing: EASY
    ceiling with DATA_MISSING_CONSERVATIVE_H2."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=400.0)
    assert payload["session_type"] not in _ABOVE_EASY, payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H2" in payload["governance_locks"], payload["governance_locks"]


def test_hrv_at_the_ceiling_is_still_a_reading(tmp_path, monkeypatch):
    """SD-01 boundary: 300 ms is inside the bounds and stays a reading (no missing-data lock)."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=300.0)
    assert "DATA_MISSING_CONSERVATIVE_H2" not in payload["governance_locks"], payload["governance_locks"]


def test_hrv_below_the_floor_still_rests(tmp_path, monkeypatch):
    """SD-01 guard (only tightens): a near-zero HRV is still a collapse and H2 gives REST."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=0.05)
    assert payload["session_type"] == "REST", payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H2" not in payload["governance_locks"]


def test_failed_load_reload_counts_as_missing_for_h4(tmp_path, monkeypatch):
    """M0-22 (ADR-0073 point 1, D-166): the reload of the loads after the sync failed. The TSB
    came from loads without the last sync and H4 said CLEAR. Now H4 treats it as missing:
    EASY ceiling with DATA_MISSING_CONSERVATIVE_H4."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          loads=dict.fromkeys(range(1, 120), 40), fail_load_reload=True)
    assert payload["session_type"] not in _ABOVE_EASY, payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H4" in payload["governance_locks"], payload["governance_locks"]


def test_loads_reloaded_keep_h4_measured(tmp_path, monkeypatch):
    """M0-22: with the same loads and a working reload, H4 is measured (no missing-data lock)."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          loads=dict.fromkeys(range(1, 120), 40))
    assert "DATA_MISSING_CONSERVATIVE_H4" not in payload["governance_locks"], payload["governance_locks"]


def test_failed_reload_keeps_an_old_tsb_that_fires_h4(tmp_path, monkeypatch):
    """M0-22 guard (only tightens): the old TSB is already at the floor, so H4 fires on it and
    the day keeps the H4 volume cap instead of the plain missing-data ceiling."""
    loads = dict.fromkeys(range(8, 120), 40)
    loads.update(dict.fromkeys(range(1, 8), 250))
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          loads=loads, fail_load_reload=True)
    assert "DATA_MISSING_CONSERVATIVE_H4" not in payload["governance_locks"], payload["governance_locks"]
    assert "HARD_STOP_SAFETY_GATES" in payload["governance_locks"], payload["governance_locks"]
    assert payload["session_type"] in {"EASY", "REST"}, payload["session_type"]


def test_partial_sync_counts_tsb_as_missing_for_h4(tmp_path, monkeypatch):
    """SD-04 (ADR-0073 point 5, D-167): the activity fetch failed, so the sync is "partial" and
    the TSB lacks yesterday's run. H4 used to say CLEAR on it; now it is missing (EASY ceiling)."""
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          loads=dict.fromkeys(range(1, 120), 40), sync_status="partial")
    assert payload["session_type"] not in _ABOVE_EASY, payload["session_type"]
    assert "DATA_MISSING_CONSERVATIVE_H4" in payload["governance_locks"], payload["governance_locks"]


def test_partial_sync_keeps_an_old_tsb_that_fires_h4(tmp_path, monkeypatch):
    """SD-04 guard (only tightens): the TSB is already at the floor without the missing runs,
    so H4 fires on it and keeps its volume cap."""
    loads = dict.fromkeys(range(8, 120), 40)
    loads.update(dict.fromkeys(range(1, 8), 250))
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          loads=loads, sync_status="partial")
    assert "DATA_MISSING_CONSERVATIVE_H4" not in payload["governance_locks"], payload["governance_locks"]
    assert "HARD_STOP_SAFETY_GATES" in payload["governance_locks"], payload["governance_locks"]


def _stale_alerts(monkeypatch) -> list[str]:
    """Record the event types of the operator alerts the morning sends."""
    import titan.orchestration.daily_coach as dc
    sent: list[str] = []
    monkeypatch.setattr(dc, "alert_operator", lambda *_a, **k: sent.append(k.get("event_type")))
    return sent


def test_never_synced_athlete_counts_as_stale(tmp_path, monkeypatch):
    """SD-09: no Garmin sync has ever succeeded and today's timed out. The data age defaults to
    27 h, but the stale flag was only set when a past success existed. Now it is stale too:
    the operator is told and the day is capped."""
    sent = _stale_alerts(monkeypatch)
    payload, _ = _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0,
                          sync_status="timeout_cancelled")
    assert "garmin_data_stale" in sent, sent
    assert payload["session_type"] in {"EASY", "REST"}, payload["session_type"]


def test_synced_athlete_is_not_stale(tmp_path, monkeypatch):
    """SD-09 guard: today's sync worked, so the athlete is not stale."""
    sent = _stale_alerts(monkeypatch)
    _morning(tmp_path, monkeypatch, athlete_id="owner", prior_nights=10, today_hrv=76.0)
    assert "garmin_data_stale" not in sent, sent
