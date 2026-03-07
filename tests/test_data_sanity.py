"""
Tests for the data sanity layer — ADR-0026 / T1-19.

Covers:
- DataSanityChecker.check_activity(): cross-field rules (max_hr/avg_hr, distance/duration,
  future timestamp, unparseable timestamp)
- DataSanityChecker.check_daily_metrics(): date null/empty rule
- DataSanityChecker.check_hrv(): hrv_ms == 0 reject rule
- has_rejects() / has_warns() helpers
- Clean records produce no violations
- DatabaseManager.get_last_garmin_sync_timestamp(): returns correct datetime
- Schema migration v3: quality_flag column added to training_log and daily_metrics
- save_session() and save_daily_metric() accept quality_flag
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from titan.science.data_sanity import (
    DataSanityChecker,
    SanityViolation,
    has_rejects,
    has_warns,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _future_date_str(hours: int = 2) -> str:
    """Return an ISO date string that is `hours` hours in the future."""
    return (datetime.now(tz=UTC) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")


def _past_date_str(days: int = 1) -> str:
    return (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")


# ─── check_activity: happy path ──────────────────────────────────────────────


def test_clean_activity_no_violations():
    checker = DataSanityChecker()
    row = {
        "date": _past_date_str(),
        "distance_km": 10.0,
        "duration_sec": 3600,
        "avg_hr": 140,
        "max_hr": 165,
    }
    violations = checker.check_activity(row)
    assert violations == []


def test_activity_missing_hr_fields_no_violation():
    """Partial activity records (no HR data) should not trigger violations."""
    checker = DataSanityChecker()
    row = {"date": _past_date_str(), "distance_km": 5.0, "duration_sec": 1800}
    violations = checker.check_activity(row)
    assert violations == []


def test_activity_zero_distance_zero_duration_no_violation():
    """Both zero is not a cross-field inconsistency — it's just an empty record."""
    checker = DataSanityChecker()
    row = {"date": _past_date_str(), "distance_km": 0.0, "duration_sec": 0}
    violations = checker.check_activity(row)
    assert violations == []


# ─── check_activity: max_hr < avg_hr ─────────────────────────────────────────


def test_max_hr_less_than_avg_hr_rejected():
    checker = DataSanityChecker()
    row = {
        "date": _past_date_str(),
        "distance_km": 10.0,
        "duration_sec": 3600,
        "avg_hr": 155,
        "max_hr": 130,  # impossible
    }
    violations = checker.check_activity(row)
    assert len(violations) == 1
    assert violations[0].rule == "max_hr_lt_avg_hr"
    assert violations[0].severity == "reject"
    assert violations[0].field == "max_hr"


def test_max_hr_equal_to_avg_hr_is_valid():
    checker = DataSanityChecker()
    row = {"date": _past_date_str(), "avg_hr": 155, "max_hr": 155}
    violations = checker.check_activity(row)
    assert violations == []


def test_max_hr_zero_avg_hr_zero_not_rejected():
    """Zero HR fields are treated as missing — no cross-field rule fires."""
    checker = DataSanityChecker()
    row = {"date": _past_date_str(), "avg_hr": 0, "max_hr": 0}
    violations = checker.check_activity(row)
    assert violations == []


# ─── check_activity: nonzero distance + zero duration ────────────────────────


def test_nonzero_distance_zero_duration_rejected():
    checker = DataSanityChecker()
    row = {"date": _past_date_str(), "distance_km": 10.0, "duration_sec": 0}
    violations = checker.check_activity(row)
    assert any(v.rule == "nonzero_distance_zero_duration" for v in violations)
    assert all(v.severity == "reject" for v in violations if v.rule == "nonzero_distance_zero_duration")


def test_zero_distance_nonzero_duration_valid():
    """Indoor sessions (e.g. treadmill) may have 0 distance — that's fine."""
    checker = DataSanityChecker()
    row = {"date": _past_date_str(), "distance_km": 0.0, "duration_sec": 3600}
    violations = checker.check_activity(row)
    assert violations == []


# ─── check_activity: future timestamp ────────────────────────────────────────


def test_activity_future_timestamp_rejected():
    checker = DataSanityChecker()
    row = {"date": _future_date_str(hours=2), "distance_km": 5.0, "duration_sec": 1800}
    violations = checker.check_activity(row)
    future_violations = [v for v in violations if v.rule == "timestamp_in_future"]
    assert len(future_violations) == 1
    assert future_violations[0].severity == "reject"


def test_activity_within_drift_margin_not_rejected():
    """Timestamps within 1 hour of now are within the clock-drift margin."""
    checker = DataSanityChecker()
    # 30 minutes in the future — within the 1-hour drift margin
    marginal = (datetime.now(tz=UTC) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
    row = {"date": marginal, "distance_km": 5.0, "duration_sec": 1800}
    violations = checker.check_activity(row)
    future_violations = [v for v in violations if v.rule == "timestamp_in_future"]
    assert future_violations == []


def test_activity_past_timestamp_not_rejected():
    checker = DataSanityChecker()
    row = {"date": "2026-01-01", "distance_km": 5.0, "duration_sec": 1800}
    violations = checker.check_activity(row)
    assert violations == []


def test_activity_unparseable_timestamp_warns():
    checker = DataSanityChecker()
    row = {"date": "not-a-date", "distance_km": 5.0, "duration_sec": 1800}
    violations = checker.check_activity(row)
    warn_violations = [v for v in violations if v.rule == "timestamp_unparseable"]
    assert len(warn_violations) == 1
    assert warn_violations[0].severity == "warn"


# ─── check_daily_metrics ─────────────────────────────────────────────────────


def test_duplicate_activity_id_in_payload_rejected():
    checker = DataSanityChecker()
    seen_ids: set[str] = set()

    first = checker.check_activity(
        {"activity_id": "a1", "date": _past_date_str(), "distance_km": 5.0, "duration_sec": 1200},
        seen_activity_ids=seen_ids,
    )
    duplicate = checker.check_activity(
        {"activity_id": "a1", "date": _past_date_str(), "distance_km": 6.0, "duration_sec": 1400},
        seen_activity_ids=seen_ids,
    )

    assert first == []
    assert len(duplicate) == 1
    assert duplicate[0].rule == "duplicate_activity_id_in_payload"
    assert duplicate[0].severity == "reject"


def test_hrv_future_timestamp_rejected():
    checker = DataSanityChecker()
    future = (datetime.now(tz=UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    violations = checker.check_hrv({"rmssd": 42.0, "date": future})

    assert len(violations) == 1
    assert violations[0].rule == "timestamp_in_future"
    assert violations[0].severity == "reject"


def test_hrv_unparseable_timestamp_warns():
    checker = DataSanityChecker()
    violations = checker.check_hrv({"rmssd": 42.0, "date": "bad-timestamp"})

    assert len(violations) == 1
    assert violations[0].rule == "timestamp_unparseable"
    assert violations[0].severity == "warn"


def test_daily_metrics_null_date_rejected():
    checker = DataSanityChecker()
    violations = checker.check_daily_metrics({"date": None, "hrv_rmssd": 55.0})
    assert len(violations) == 1
    assert violations[0].rule == "date_null_or_empty"
    assert violations[0].severity == "reject"


def test_daily_metrics_empty_string_date_rejected():
    checker = DataSanityChecker()
    violations = checker.check_daily_metrics({"date": "", "hrv_rmssd": 55.0})
    assert len(violations) == 1
    assert violations[0].rule == "date_null_or_empty"


def test_daily_metrics_valid_date_no_violations():
    checker = DataSanityChecker()
    violations = checker.check_daily_metrics({"date": "2026-01-15"})
    assert violations == []


# ─── check_hrv ───────────────────────────────────────────────────────────────


def test_hrv_zero_rejected():
    checker = DataSanityChecker()
    violations = checker.check_hrv({"rmssd": 0.0})
    assert len(violations) == 1
    assert violations[0].rule == "hrv_zero_sensor_failure"
    assert violations[0].severity == "reject"


def test_hrv_zero_via_hrv_ms_key():
    checker = DataSanityChecker()
    violations = checker.check_hrv({"hrv_ms": 0.0})
    assert len(violations) == 1
    assert violations[0].severity == "reject"


def test_hrv_valid_value_no_violation():
    checker = DataSanityChecker()
    assert checker.check_hrv({"rmssd": 55.0}) == []


def test_hrv_none_value_no_violation():
    checker = DataSanityChecker()
    assert checker.check_hrv({"rmssd": None}) == []


def test_hrv_missing_field_no_violation():
    checker = DataSanityChecker()
    assert checker.check_hrv({}) == []


# ─── SanityViolation dataclass ───────────────────────────────────────────────


def test_sanity_violation_fields():
    v = SanityViolation(
        record_type="activity",
        field="max_hr",
        rule="max_hr_lt_avg_hr",
        value="max_hr=130 < avg_hr=155",
        severity="reject",
    )
    assert v.record_type == "activity"
    assert v.field == "max_hr"
    assert v.rule == "max_hr_lt_avg_hr"
    assert v.severity == "reject"


# ─── has_rejects / has_warns helpers ─────────────────────────────────────────


def test_has_rejects_true():
    v = SanityViolation("activity", "max_hr", "r", "v", "reject")
    assert has_rejects([v]) is True


def test_has_rejects_false_when_only_warns():
    v = SanityViolation("activity", "date", "r", "v", "warn")
    assert has_rejects([v]) is False


def test_has_warns_true():
    v = SanityViolation("activity", "date", "r", "v", "warn")
    assert has_warns([v]) is True


def test_has_warns_false_when_only_rejects():
    v = SanityViolation("activity", "max_hr", "r", "v", "reject")
    assert has_warns([v]) is False


def test_has_rejects_empty_list():
    assert has_rejects([]) is False


def test_has_warns_empty_list():
    assert has_warns([]) is False


# ─── Multiple rules can fire on same record ───────────────────────────────────


def test_multiple_violations_on_one_record():
    checker = DataSanityChecker()
    row = {
        "date": _past_date_str(),
        "distance_km": 10.0,
        "duration_sec": 0,     # nonzero_distance_zero_duration
        "avg_hr": 155,
        "max_hr": 130,          # max_hr_lt_avg_hr
    }
    violations = checker.check_activity(row)
    rules = {v.rule for v in violations}
    assert "max_hr_lt_avg_hr" in rules
    assert "nonzero_distance_zero_duration" in rules
    assert len(violations) == 2


# ─── Database integration: get_last_garmin_sync_timestamp ────────────────────


def test_get_last_garmin_sync_timestamp_no_data(tmp_path):
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_sync_ts_empty.db", db_dir=tmp_path)
    result = db.get_last_garmin_sync_timestamp()
    assert result is None
    db.close()


def test_get_last_garmin_sync_timestamp_returns_latest(tmp_path):
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_sync_ts.db", db_dir=tmp_path)
    db.save_daily_metric(date="2026-01-10", hrv=55.0)
    db.save_daily_metric(date="2026-01-12", hrv=60.0)
    db.save_daily_metric(date="2026-01-11", hrv=58.0)

    result = db.get_last_garmin_sync_timestamp()
    assert result is not None
    assert result.year == 2026
    assert result.month == 1
    assert result.day == 12
    db.close()


def test_get_last_garmin_sync_timestamp_uses_training_log(tmp_path):
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_sync_ts_tl.db", db_dir=tmp_path)
    db.save_session(date="2026-02-20", session_type="EASY", distance_km=10.0, duration_sec=3600)

    result = db.get_last_garmin_sync_timestamp()
    assert result is not None
    assert result.day == 20
    db.close()


def test_get_last_garmin_sync_timestamp_picks_later_of_two_tables(tmp_path):
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_sync_ts_max.db", db_dir=tmp_path)
    db.save_daily_metric(date="2026-01-10", hrv=55.0)
    db.save_session(date="2026-01-15", session_type="EASY", distance_km=10.0, duration_sec=3600)

    result = db.get_last_garmin_sync_timestamp()
    assert result is not None
    assert result.day == 15  # training_log has later date
    db.close()


# ─── Schema migration v3: quality_flag column ────────────────────────────────


def test_quality_flag_column_exists_after_migration(tmp_path):
    """After creating a new DB, quality_flag column should be present."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_qflag_schema.db", db_dir=tmp_path)
    cursor = db.conn.cursor()

    # Check training_log
    cursor.execute("PRAGMA table_info(training_log)")
    tl_columns = [row[1] for row in cursor.fetchall()]
    assert "quality_flag" in tl_columns

    # Check daily_metrics
    cursor.execute("PRAGMA table_info(daily_metrics)")
    dm_columns = [row[1] for row in cursor.fetchall()]
    assert "quality_flag" in dm_columns

    db.close()


def test_save_session_with_quality_flag(tmp_path):
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_qflag_session.db", db_dir=tmp_path)
    db.save_session(
        date="2026-01-01",
        session_type="EASY",
        distance_km=10.0,
        duration_sec=3600,
        quality_flag="degraded",
    )
    cursor = db.conn.cursor()
    cursor.execute("SELECT quality_flag FROM training_log WHERE date = '2026-01-01'")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "degraded"
    db.close()


def test_save_session_quality_flag_none_by_default(tmp_path):
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_qflag_none.db", db_dir=tmp_path)
    db.save_session(
        date="2026-01-02",
        session_type="EASY",
        distance_km=5.0,
        duration_sec=1800,
    )
    cursor = db.conn.cursor()
    cursor.execute("SELECT quality_flag FROM training_log WHERE date = '2026-01-02'")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] is None
    db.close()


def test_save_daily_metric_with_quality_flag(tmp_path):
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_qflag_dm.db", db_dir=tmp_path)
    db.save_daily_metric(date="2026-01-03", hrv=55.0, quality_flag="degraded")
    cursor = db.conn.cursor()
    cursor.execute("SELECT quality_flag FROM daily_metrics WHERE date = '2026-01-03'")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "degraded"
    db.close()
