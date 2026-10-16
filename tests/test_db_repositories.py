"""Plan #18: DatabaseManager is a facade over per-domain repositories; its public API is unchanged."""

from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager
from titan.core.repositories.access import AccessRepository
from titan.core.repositories.governance import GovernanceRepository
from titan.core.repositories.operations import OperationsRepository
from titan.core.repositories.physiology import PhysiologyRepository
from titan.core.repositories.training import TrainingRepository

_TRAINING_METHODS = (
    "update_shoe_mileage", "add_shoe", "get_active_shoes", "check_shoe_availability",
    "save_personal_best", "get_pr", "log_cs_performance", "get_cs_performances",
    "save_session", "get_recent_activities", "get_training_load_history", "get_ctl_atl_tsb",
    "replay_tsb",
)
_PHYSIOLOGY_METHODS = (
    "save_daily_metric", "save_daily_metric_if_missing", "save_hrr", "get_hrr_history",
    "update_glycogen_debt", "get_baseline_rhr", "get_hrv_history", "get_recent_hrv_mean",
    "get_weight_history", "get_daily_metric",
)
_GOVERNANCE_METHODS = (
    "log_override", "record_override_signal", "get_override_ratio", "get_override_log",
    "save_governance_decision", "update_governance_outcome", "get_governance_decisions",
    "annotate_governance_outcome", "save_threshold_offset", "get_athlete_threshold_offsets",
    "delete_threshold_offset", "get_completion_rate", "is_athlete_cold_start",
    "check_and_exit_cold_start", "increment_cold_start_sessions", "get_false_negative_rate",
    "get_model_calibration_metadata",
)
_OPERATIONS_METHODS = (
    "get_nutrition_preferences", "save_nutrition_preferences", "get_all_degraded_mode_states",
    "upsert_degraded_mode_state", "delete_degraded_mode_state", "record_sync_outcome",
    "get_last_sync_outcome", "get_last_garmin_sync_timestamp", "backup_database",
    "_record_backup_failure", "_prune_old_backups", "check_integrity", "get_table_names",
    "is_db_reachable",
)
_ACCESS_METHODS = (
    "record_failed_login", "is_login_locked_out", "clear_login_lockout", "upsert_auth_user",
    "get_auth_user_by_id", "get_auth_user_by_username", "insert_auth_token", "get_auth_token",
    "set_auth_token_revoked", "delete_expired_auth_tokens", "get_active_auth_tokens_for_user",
    "_get_all_athlete_ids", "get_assigned_athletes", "assign_athlete_to_coach", "log_coach_action",
    "get_coach_audit_log",
)
_ROOT = Path(__file__).resolve().parents[1]
_FACADES = (
    [(TrainingRepository, n) for n in _TRAINING_METHODS]
    + [(PhysiologyRepository, n) for n in _PHYSIOLOGY_METHODS]
    + [(GovernanceRepository, n) for n in _GOVERNANCE_METHODS]
    + [(OperationsRepository, n) for n in _OPERATIONS_METHODS]
    + [(AccessRepository, n) for n in _ACCESS_METHODS]
)


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
@pytest.mark.parametrize(("repository", "name"), _FACADES)
def test_facade_keeps_the_repository_signature(repository: type, name: str) -> None:
    facade = inspect.signature(getattr(DatabaseManager, name), eval_str=True)
    repo = inspect.signature(getattr(repository, name), eval_str=True)
    assert facade == repo


@pytest.mark.unit
def test_gear_repository_shares_the_managers_connection(db) -> None:
    shoe_id = db.add_shoe("Pegasus", max_km=500)
    db.update_shoe_mileage(shoe_id, 12.5, "2026-10-01T07:00:00+00:00")

    assert db._training is db._training
    assert db._training.get_active_shoes() == db.get_active_shoes()
    assert db.get_active_shoes()[0][:4] == (shoe_id, "Pegasus", 12.5, 500)


@pytest.mark.unit
def test_gear_calls_fail_on_a_closed_manager(db) -> None:
    db.close()
    with pytest.raises(RuntimeError, match="closed"):
        db.get_active_shoes()


@pytest.mark.unit
def test_personal_bests_and_cs_performances_round_trip(db) -> None:
    db.save_personal_best(5.0, 1180, "2026-01-10", "Parkrun")
    db.save_personal_best(5.0, 1140, "2026-02-14")
    db.log_cs_performance("2026-01-24", 5000, 1140.0)
    db.log_cs_performance("2026-02-21", 3000, 640.0, surface="TRACK", wind_adjusted=True)

    assert db.get_pr(5.0) == (1140, "2026-02-14", None)
    assert db.get_cs_performances(limit=1) == [("2026-02-21", 3000.0, 640.0)]
    assert db.conn.execute("SELECT wind_adjusted FROM cs_performances WHERE surface='TRACK'").fetchone() == (1,)


@pytest.mark.unit
def test_save_session_deprecation_warning_points_at_the_caller(db) -> None:
    with pytest.warns(DeprecationWarning, match="temperature_c") as record:
        db.save_session("2026-01-05", "EASY", 8.0, 2640, rpe=3, temperature=12.0)
    assert record[0].filename == __file__
    assert db.conn.execute("SELECT temperature_c FROM training_log").fetchone() == (12.0,)


@pytest.mark.unit
def test_recent_activities_keep_a_missing_avg_hr_as_none(db) -> None:
    """F7: a session saved without HR reads back avg_hr None, not 0 bpm."""
    db.save_session("2026-01-06", "EASY", 5.0, 1800)
    db.save_session("2026-01-07", "EASY", 6.0, 2100, avg_hr=142)
    by_date = {a["date"]: a["avg_hr"] for a in db.get_recent_activities()}
    assert by_date == {"2026-01-06": None, "2026-01-07": 142}


@pytest.mark.unit
def test_ctl_atl_tsb_reads_history_through_the_facade(db, monkeypatch) -> None:
    calls: list[tuple] = []

    def fake_history(days=None, athlete_id="owner"):
        calls.append((days, athlete_id))
        return []

    monkeypatch.setattr(db, "get_training_load_history", fake_history)
    assert db.get_ctl_atl_tsb(athlete_id="owner") == (0.0, 0.0, 0.0)
    assert calls and calls[0][1] == "owner"


@pytest.mark.unit
def test_daily_metrics_round_trip_per_athlete(db) -> None:
    db.save_daily_metric("2026-10-01", weight=70.2, hrv=62.0, rhr=48, soreness=2)
    db.save_daily_metric("2026-10-01", hrv=40.0, athlete_id="other")
    db.save_daily_metric("2026-10-01", hrv=64.0)  # Garmin re-sync keeps manual soreness
    db.save_daily_metric_if_missing("2026-10-01", hrv=99.0)
    db.save_hrr("2026-10-01", 32, 51)
    db.update_glycogen_debt("2026-10-01", 3.456)

    assert db.get_daily_metric("2026-10-01") == {
        "date": "2026-10-01", "hrv_rmssd": 64.0, "resting_hr": 48,
        "sleep_hours": None, "weight_kg": 70.2, "data_source": "garmin_api", "sleep_quality": None,
    }
    assert db.get_daily_metric("2026-10-01", athlete_id="other")["hrv_rmssd"] == 40.0
    assert db.conn.execute(
        "SELECT soreness, hrr_60, hrr_120, glycogen_debt FROM daily_metrics WHERE athlete_id='owner'"
    ).fetchone() == (2, 32, 51, 3.46)


@pytest.mark.unit
def test_missing_row_warnings_still_come_from_the_database_logger(db, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="titan.core.database"):
        db.save_hrr("2026-10-02", 30)
        db.update_glycogen_debt("2026-10-02", 1.0)
    messages = [r.getMessage() for r in caplog.records if r.name == "titan.core.database"]
    assert any("save_hrr_no_row_updated" in m for m in messages)
    assert any("update_glycogen_debt_no_row_updated" in m for m in messages)


@pytest.mark.unit
def test_recent_hrv_mean_reads_history_through_the_facade(db, monkeypatch) -> None:
    monkeypatch.setattr(db, "get_hrv_history", lambda days=14, athlete_id="owner": [
        ("2026-10-02", 60.0), ("2026-10-01", 50.0),
    ])
    assert db.get_recent_hrv_mean(days=2) == 55.0


@pytest.mark.unit
def test_governance_decision_and_outcome_round_trip_per_athlete(db) -> None:
    decision = {
        "date": "2026-10-03", "session_planned": "TEMPO", "session_post_governance": "EASY",
        "locks_applied": ["CS_CONFIDENCE_LOCK"], "governance_clean": False, "phase": "BASE",
    }
    db.save_governance_decision(decision)
    db.save_governance_decision({**decision, "athlete_profile_id": "other"})

    assert db.update_governance_outcome("2026-10-03", rpe=4, completed=True) is True
    assert db.annotate_governance_outcome("2026-10-03", "felt fine") is True

    [owner] = db.get_governance_decisions()
    assert owner["locks_applied"] == ["CS_CONFIDENCE_LOCK"]
    assert (owner["outcome_rpe"], owner["outcome_completed"]) == (4, True)
    [other] = db.get_governance_decisions(athlete_id="other")
    assert other["outcome_rpe"] is None


@pytest.mark.unit
def test_override_log_and_ratio(db) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    db.log_override(today, "TEMPO", "EASY", "legs heavy")

    assert db.get_override_log(limit=1)[0]["reason"] == "legs heavy"
    assert db.get_override_ratio(days=14) is None  # cold start: no governance history
    db.save_governance_decision(
        {"date": today, "session_planned": "TEMPO", "session_post_governance": "EASY"}
    )
    assert db.get_override_ratio(days=14) == round(1 / 14, 3)


@pytest.mark.unit
def test_threshold_offsets_per_athlete_and_hard_stops_refused(db) -> None:
    db.save_threshold_offset("a1", "ACWR_CEILING", 0.05, "calibration", 0.8, "2026-10-04")
    db.save_threshold_offset("a2", "ACWR_CEILING", -0.05, "manual", 1.0, "2026-10-04")

    assert [o["delta_value"] for o in db.get_athlete_threshold_offsets("a1")] == [0.05]
    assert db.delete_threshold_offset("a1", "ACWR_CEILING") == 1
    assert db.get_athlete_threshold_offsets("a1") == []
    assert len(db.get_athlete_threshold_offsets("a2")) == 1
    with pytest.raises(ValueError):
        db.save_threshold_offset("a1", "HARD_STOP_TSB_FLOOR", 1.0, "manual", 1.0, "2026-10-04")


@pytest.mark.unit
def test_unknown_athlete_is_treated_as_cold_start(db) -> None:
    assert db.is_athlete_cold_start("nobody") is True


@pytest.mark.unit
def test_sync_outcome_keeps_the_last_success_after_a_failure(db) -> None:
    ok = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
    failed = datetime(2026, 10, 6, 6, 0, tzinfo=UTC)
    db.record_sync_outcome(source="garmin", attempted_at=ok, success=True)
    db.record_sync_outcome(source="garmin", attempted_at=failed, success=False, error_class="Timeout")

    assert db.get_last_sync_outcome("garmin") == {
        "last_attempt_ts": failed, "last_success_ts": ok,
        "last_sync_ok": False, "last_error_class": "Timeout",
    }
    assert db.get_last_sync_outcome("strava") is None


@pytest.mark.unit
def test_garmin_freshness_is_the_newest_date_in_either_table(db) -> None:
    assert db.get_last_garmin_sync_timestamp() is None
    db.save_daily_metric("2026-10-03", hrv=60.0)
    db.save_session("2026-10-04", "EASY", 8.0, 2640, rpe=3)
    assert db.get_last_garmin_sync_timestamp() == datetime(2026, 10, 4, tzinfo=UTC)


@pytest.mark.unit
def test_degraded_mode_state_and_nutrition_preferences_round_trip(db) -> None:
    db.upsert_degraded_mode_state("GARMIN_API_UNAVAILABLE", "2026-10-05T06:00:00+00:00")
    db.upsert_degraded_mode_state("GARMIN_API_UNAVAILABLE", "2026-10-06T06:00:00+00:00")
    assert db.get_all_degraded_mode_states() == [
        ("GARMIN_API_UNAVAILABLE", "2026-10-06T06:00:00+00:00")
    ]
    db.delete_degraded_mode_state("GARMIN_API_UNAVAILABLE")
    assert db.get_all_degraded_mode_states() == []

    assert db.get_nutrition_preferences() is None
    db.save_nutrition_preferences(prefs={"dietary_style": "vegetarian"})
    prefs = db.get_nutrition_preferences()
    assert (prefs["dietary_style"], prefs["meal_frequency"]) == ("vegetarian", 3)


@pytest.mark.unit
def test_lockout_engages_at_max_attempts_and_clears(db) -> None:
    assert db.record_failed_login("zaf", 60.0, max_attempts=2) is False
    assert db.is_login_locked_out("zaf") is False
    assert db.record_failed_login("zaf", 60.0, max_attempts=2) is True
    assert db.is_login_locked_out("zaf") is True
    db.clear_login_lockout("zaf")
    assert db.is_login_locked_out("zaf") is False


@pytest.mark.unit
def test_auth_users_and_refresh_tokens_round_trip(db) -> None:
    db.upsert_auth_user("u1", "zaf", "hash", "coach", None)
    db.insert_auth_token("j1", "u1", "2026-10-07T00:00:00", "2026-10-08T00:00:00")
    db.insert_auth_token("j2", "u1", "2026-10-07T00:00:00", "2026-10-06T00:00:00")
    db.set_auth_token_revoked("j1")

    assert db.get_auth_user_by_username("zaf") == db.get_auth_user_by_id("u1")
    assert db.get_auth_user_by_id("u1")["is_active"] is True
    assert db.get_auth_token("j1")["revoked"] is True
    assert db.get_active_auth_tokens_for_user("u1", "2026-10-07T12:00:00") == []
    db.delete_expired_auth_tokens("2026-10-07T12:00:00")
    assert db.get_auth_token("j2") is None
    assert db.get_auth_user_by_id("missing") is None


@pytest.mark.unit
def test_coach_scope_is_only_the_assigned_athletes(db) -> None:
    assert db.get_assigned_athletes("coach-1") == []  # nothing assigned: no access
    db.assign_athlete_to_coach("coach-1", "a1")
    db.assign_athlete_to_coach("coach-1", "a1")  # idempotent
    assert db.get_assigned_athletes("coach-1") == ["a1"]
    assert db.get_assigned_athletes("system") == db._get_all_athlete_ids() == ["owner"]

    db.log_coach_action("coach-1", "VIEW", "a1", resource="plan")
    db.log_coach_action("coach-2", "VIEW", "owner")
    [entry] = db.get_coach_audit_log(coach_id="coach-1")
    assert (entry["athlete_id"], entry["resource"]) == ("a1", "plan")
    assert len(db.get_coach_audit_log()) == 2


@pytest.mark.unit
def test_model_calibration_metadata_round_trip_with_schema_version_default(db) -> None:
    assert db.get_model_calibration_metadata("hrv_model") is None
    db.upsert_model_calibration_metadata(
        model_name="hrv_model", calibrated_at="2026-10-01T06:00:00", baseline_hrv_ms=52.5
    )
    db.upsert_model_calibration_metadata(
        model_name="hrv_model", calibrated_at="2026-10-02T06:00:00", athlete_id="a1",
        baseline_vo2=55.0, schema_version=3,
    )
    assert db.get_model_calibration_metadata("hrv_model") == {
        "model_name": "hrv_model", "athlete_id": "owner", "calibrated_at": "2026-10-01T06:00:00",
        "baseline_hrv_ms": 52.5, "baseline_vo2": None, "schema_version": SCHEMA_VERSION,
    }
    assert db.get_model_calibration_metadata("hrv_model", athlete_id="a1")["schema_version"] == 3
    db.upsert_model_calibration_metadata(
        model_name="hrv_model", calibrated_at="2026-10-03T06:00:00", baseline_hrv_ms=50.0
    )
    row = db.get_model_calibration_metadata("hrv_model")
    assert (row["calibrated_at"], row["baseline_hrv_ms"]) == ("2026-10-03T06:00:00", 50.0)


@pytest.mark.unit
def test_calibration_upsert_inside_a_transaction_rolls_back_with_it(db) -> None:
    with pytest.raises(RuntimeError), db.transaction():
        db.upsert_model_calibration_metadata(model_name="m", calibrated_at="2026-10-01")
        raise RuntimeError("abort")
    assert db.get_model_calibration_metadata("m") is None


@pytest.mark.unit
def test_new_database_has_its_tables_and_owner_rows(db) -> None:
    assert db.is_db_reachable() is True
    tables = db.get_table_names()
    assert tables == sorted(tables)
    assert {"athletes", "coach_athlete_assignments", "model_calibration_metadata"} <= set(tables)
    assert db._get_all_athlete_ids() == ["owner"]
    assert db.get_assigned_athletes("system") == ["owner"]


@pytest.mark.unit
def test_reopening_a_database_does_not_duplicate_the_owner_rows(tmp_path) -> None:
    DatabaseManager(db_dir=tmp_path).close()
    again = DatabaseManager(db_dir=tmp_path)
    try:
        assert again._get_all_athlete_ids() == ["owner"]
        assert again.get_assigned_athletes("system") == ["owner"]
    finally:
        again.close()


@pytest.mark.unit
def test_introspection_fails_on_a_closed_manager(db) -> None:
    db.close()
    with pytest.raises(RuntimeError, match="closed"):
        db.get_table_names()
    with pytest.raises(RuntimeError, match="closed"):
        db.is_db_reachable()


@pytest.mark.unit
def test_database_scoped_gates_also_cover_the_repositories() -> None:
    """The SQL left database.py; the gates and owners scoped to that file must follow it."""
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    smoke = (_ROOT / ".github" / "workflows" / "docker-smoke.yml").read_text(encoding="utf-8")
    owners = (_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "titan/core/database.py\n            titan/core/repositories/*.py\n" in ci  # G-CI-02
    assert '"titan/core/repositories/**"' in smoke
    assert "/titan/core/repositories/ @zafiriss-ux" in owners
