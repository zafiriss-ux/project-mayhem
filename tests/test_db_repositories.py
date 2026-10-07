"""Plan #18: DatabaseManager is a facade over per-domain repositories; its public API is unchanged."""

from __future__ import annotations

import inspect

import pytest

from titan.core.database import DatabaseManager
from titan.core.repositories.training import TrainingRepository

_TRAINING_METHODS = (
    "update_shoe_mileage", "add_shoe", "get_active_shoes", "check_shoe_availability",
    "save_personal_best", "get_pr", "log_cs_performance", "get_cs_performances",
    "save_session", "get_recent_activities", "get_training_load_history", "get_ctl_atl_tsb",
    "replay_tsb",
)


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
@pytest.mark.parametrize("name", _TRAINING_METHODS)
def test_training_facade_keeps_the_repository_signature(name: str) -> None:
    facade = inspect.signature(getattr(DatabaseManager, name), eval_str=True)
    repo = inspect.signature(getattr(TrainingRepository, name), eval_str=True)
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
def test_ctl_atl_tsb_reads_history_through_the_facade(db, monkeypatch) -> None:
    calls: list[tuple] = []

    def fake_history(days=None, athlete_id="owner"):
        calls.append((days, athlete_id))
        return []

    monkeypatch.setattr(db, "get_training_load_history", fake_history)
    assert db.get_ctl_atl_tsb(athlete_id="owner") == (0.0, 0.0, 0.0)
    assert calls and calls[0][1] == "owner"
