"""Plan #18: DatabaseManager is a facade over per-domain repositories; its public API is unchanged."""

from __future__ import annotations

import inspect

import pytest

from titan.core.database import DatabaseManager
from titan.core.repositories.training import TrainingRepository

_GEAR_METHODS = ("update_shoe_mileage", "add_shoe", "get_active_shoes", "check_shoe_availability")


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
@pytest.mark.parametrize("name", _GEAR_METHODS)
def test_gear_facade_keeps_the_repository_signature(name: str) -> None:
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
