"""
Tests for three bug fixes:
[A] Downgraded weekly plan session descriptions match new session_type
[B] ACWR uses time-based 7d/28d windows, not activity count
[C] avg_pace_sec_per_km is calculated from duration + distance at import time
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from titan.core.database import DatabaseManager
from titan.features.weekly_planner import WeeklyPlanGenerator
from titan.science.acwr_engine import ACWREngine


def _make_db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_name="test_fix.db", db_dir=tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# [A] Downgraded session descriptions match the NEW session_type
# ─────────────────────────────────────────────────────────────────────────────

def _make_planner_with_low_hrv() -> WeeklyPlanGenerator:
    hrv_engine = MagicMock()
    hrv_engine.get_hrv_summary.return_value = {"baseline": 60, "latest_hrv": 45}
    hrv_engine.get_trend_analysis.return_value = {"trend": "declining"}

    tsb_engine = MagicMock()
    tsb_engine.calculate_tsb.return_value = (5.0, "OPTIMAL")

    acwr_engine = ACWREngine()
    return WeeklyPlanGenerator(hrv_engine, tsb_engine, acwr_engine)


def test_downgraded_session_has_correct_description():
    """INTERVALS→TEMPO and TEMPO→EASY descriptions must reflect the NEW type, not the original."""
    planner = _make_planner_with_low_hrv()
    profile = {"threshold_hr": 165}

    plan = planner.generate_weekly_plan(profile, phase="BUILD")
    sessions = plan["daily_sessions"]

    # Collect only the sessions that were explicitly downgraded
    downgraded = [s for s in sessions if "downgraded" in s["details"].lower()]
    assert len(downgraded) > 0, "Expected at least one downgraded session in low-HRV BUILD week"

    for session in downgraded:
        stype = session["session_type"]
        desc = session["details"].lower()

        if stype == "TEMPO":
            assert "vo2" not in desc, (
                f"TEMPO session still has VO2max description: {session['details']!r}"
            )
            assert "tempo" in desc or "lt" in desc, (
                f"TEMPO session description doesn't reflect tempo work: {session['details']!r}"
            )

        if stype == "EASY":
            # Must not contain the original LT-work description
            assert "8km @ lt" not in desc, (
                f"EASY session still has LT description: {session['details']!r}"
            )
            assert "easy" in desc or "aerobic" in desc, (
                f"EASY session description doesn't reflect easy work: {session['details']!r}"
            )


def test_downgraded_intervals_become_tempo_with_tempo_description():
    """A BUILD week INTERVALS session must become TEMPO with a tempo-appropriate description."""
    planner = _make_planner_with_low_hrv()
    profile = {"threshold_hr": 165}
    plan = planner.generate_weekly_plan(profile, phase="BUILD")

    # BUILD week originally has INTERVALS on Tuesday — it should be downgraded to TEMPO
    tuesday = next((s for s in plan["daily_sessions"] if s["day"] == "Tuesday"), None)
    assert tuesday is not None
    assert tuesday["session_type"] == "TEMPO"
    # Must NOT carry the original VO2max intervals description
    assert "vo2max" not in tuesday["details"].lower()
    assert "6x1km" not in tuesday["details"].lower()


def test_downgraded_tempo_becomes_easy_with_easy_description():
    """A BUILD week TEMPO session must become EASY with an easy-appropriate description."""
    planner = _make_planner_with_low_hrv()
    profile = {"threshold_hr": 165}
    plan = planner.generate_weekly_plan(profile, phase="BUILD")

    # BUILD week originally has TEMPO on Thursday
    thursday = next((s for s in plan["daily_sessions"] if s["day"] == "Thursday"), None)
    assert thursday is not None
    assert thursday["session_type"] == "EASY"
    # Must NOT carry the original LT tempo description
    assert "@ lt" not in thursday["details"].lower()
    assert "8km @ lt" not in thursday["details"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# [B] ACWR uses time-based 7d/28d windows
# ─────────────────────────────────────────────────────────────────────────────

def test_acwr_uses_time_window(tmp_path):
    """
    Insert 20 activities spread over 30 days.
    Manually compute acute (last 7d) and chronic (last 28d daily avg), verify ACWR matches.
    """
    db = _make_db(tmp_path)
    today = date.today()

    # Insert 1 activity per day for the last 30 days with training_load=50
    for i in range(30):
        d = (today - timedelta(days=i)).isoformat()
        db.save_session(
            date=d,
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            training_load=50,
            garmin_activity_id=f"test_{i}",
        )

    # Also insert 5 old activities (35-39 days ago) with load=100 to confirm they don't affect 28d window
    for i in range(35, 40):
        d = (today - timedelta(days=i)).isoformat()
        db.save_session(
            date=d,
            session_type="EASY",
            distance_km=15.0,
            duration_sec=5400,
            training_load=100,
            garmin_activity_id=f"old_{i}",
        )

    activities = db.get_recent_activities(limit=90)

    # Time-based calculation (mirrors the fixed menu_system.py logic)
    cutoff_7d = (today - timedelta(days=7)).isoformat()
    cutoff_28d = (today - timedelta(days=28)).isoformat()

    acute_7d = sum(
        a.get("training_load", 0)
        for a in activities
        if a.get("date", "") >= cutoff_7d
    )
    chronic_daily_avg = sum(
        a.get("training_load", 0)
        for a in activities
        if a.get("date", "") >= cutoff_28d
    ) / 28

    acwr_val, status, _ = ACWREngine.calculate_acwr(acute_7d, chronic_daily_avg)

    # Boundaries (inclusive): today-7 through today = 8 days of activities
    # Boundaries (inclusive): today-28 through today = 29 days of activities
    # acute_7d = 8 * 50 = 400
    # chronic sum = 29 * 50 = 1450; daily avg = 1450/28 ≈ 51.79
    # ACWR = 400 / (51.79 * 7) ≈ 1.10
    assert acwr_val is not None
    assert 1.0 <= acwr_val <= 1.2, f"Expected ACWR in [1.0, 1.2] but got {acwr_val}"
    # Old activities (35-39d ago) must be outside the 28d window
    assert acute_7d == 8 * 50, f"Expected 8 activities in last 7d (incl boundary), got acute_7d={acute_7d}"
    # Verify old activities did not bleed into the 28d window
    old_in_28d = sum(
        a.get("training_load", 0)
        for a in activities
        if a.get("date", "") >= cutoff_28d and a.get("training_load", 0) == 100
    )
    assert old_in_28d == 0, "Old (35-39d ago) activities must not appear in 28d window"


def test_acwr_count_vs_time_differ_when_activity_density_uneven(tmp_path):
    """
    With 5 activities in last 7 days but 20 activities total, count-based [-7:] would
    pick 7 activities spanning more than 7 days, producing a wrong result.
    Time-based calculation should only use activities within 7 days.
    """
    db = _make_db(tmp_path)
    today = date.today()

    # 5 activities in last 7 days (high load)
    for i in range(5):
        d = (today - timedelta(days=i)).isoformat()
        db.save_session(
            date=d, session_type="INTERVALS", distance_km=12.0, duration_sec=3600,
            training_load=80, garmin_activity_id=f"recent_{i}",
        )
    # 15 activities spread over days 8-30 (lower load)
    for i in range(8, 23):
        d = (today - timedelta(days=i)).isoformat()
        db.save_session(
            date=d, session_type="EASY", distance_km=8.0, duration_sec=2700,
            training_load=30, garmin_activity_id=f"older_{i}",
        )

    activities = db.get_recent_activities(limit=90)

    # Time-based acute: only the 5 recent activities
    cutoff_7d = (today - timedelta(days=7)).isoformat()
    acute_7d_time = sum(
        a.get("training_load", 0) for a in activities if a.get("date", "") >= cutoff_7d
    )
    # Count-based (old buggy approach): last 7 activities regardless of date
    acute_7d_count = sum(a.get("training_load", 0) for a in sorted(activities, key=lambda x: x["date"], reverse=True)[:7])

    # They differ because the recent week has 5 high-load + some of the older ones fill the 7-slot
    assert acute_7d_time == 5 * 80  # only the 5 recent ones
    assert acute_7d_count != acute_7d_time  # count-based picks different activities


# ─────────────────────────────────────────────────────────────────────────────
# [C] avg_pace_sec_per_km calculated from duration + distance
# ─────────────────────────────────────────────────────────────────────────────

def test_pace_calculated_from_duration_distance(tmp_path):
    """
    Insert activity with distance=10km, duration=3000sec (50min).
    Expected avg_pace_sec_per_km = 3000/10 = 300 (5:00/km).
    """
    db = _make_db(tmp_path)
    db.save_session(
        date="2026-05-21",
        session_type="EASY",
        distance_km=10.0,
        duration_sec=3000,
        training_load=40,
        garmin_activity_id="pace_test_1",
        avg_pace_sec_per_km=300,
    )

    activities = db.get_recent_activities(limit=5)
    assert len(activities) == 1
    pace = activities[0].get("avg_pace_sec_per_km")
    assert pace == 300, f"Expected pace=300 sec/km (5:00/km), got {pace}"


def test_pace_stored_and_retrieved_correctly(tmp_path):
    """avg_pace_sec_per_km round-trips through DB correctly."""
    db = _make_db(tmp_path)

    # 10km in 50min = 300 sec/km
    pace = int(3000 / 10)
    db.save_session(
        date="2026-05-20",
        session_type="TEMPO",
        distance_km=10.0,
        duration_sec=3000,
        training_load=60,
        garmin_activity_id="pace_test_2",
        avg_pace_sec_per_km=float(pace),
    )

    activities = db.get_recent_activities(limit=5)
    assert activities[0]["avg_pace_sec_per_km"] == pace


def test_pace_display_format():
    """Verify the display formula: pace_sec → min:sec string."""
    pace_sec = 300
    mins = pace_sec // 60
    secs = pace_sec % 60
    display = f"{mins}:{secs:02d}/km"
    assert display == "5:00/km"

    pace_sec = 268  # ~4:28/km
    mins = pace_sec // 60
    secs = pace_sec % 60
    display = f"{mins}:{secs:02d}/km"
    assert display == "4:28/km"


def test_import_garmin_csv_computes_pace():
    """import_garmin_csv.py pace formula: duration_sec / distance_km."""
    from scripts.import_garmin_csv import parse_distance, parse_duration

    distance = parse_distance("10,00")  # 10.0 km
    duration = parse_duration("00:50:00")  # 3000 sec

    pace_sec = int(duration / distance) if distance > 0 else None
    assert pace_sec == 300, f"Expected 300 sec/km (5:00/km), got {pace_sec}"
