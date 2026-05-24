"""TD-NEW-14: PersistenceAdapter ABC drift fitness tests."""
from __future__ import annotations

import inspect

import pytest

from titan.core.database import DatabaseManager
from titan.core.persistence import PersistenceAdapter, SQLiteAdapter


def test_persistence_adapter_signatures_match():
    """Fitness function — prevents future drift between ABC and DatabaseManager."""
    dm_methods = dict(inspect.getmembers(DatabaseManager, predicate=inspect.isfunction))
    mismatches: list[str] = []
    for name in sorted(PersistenceAdapter.__abstractmethods__):
        abc_method = getattr(PersistenceAdapter, name)
        if name not in dm_methods:
            mismatches.append(f"{name}: present in ABC but not in DatabaseManager")
            continue
        abc_params = list(inspect.signature(abc_method).parameters.keys())
        dm_params = list(inspect.signature(dm_methods[name]).parameters.keys())
        if abc_params != dm_params:
            mismatches.append(
                f"{name}:\n    ABC: {abc_params}\n    DM:  {dm_params}"
            )
    assert not mismatches, (
        f"ABC ↔ DatabaseManager signature drifts ({len(mismatches)}):\n" +
        "\n".join(mismatches)
    )


def test_sqlite_adapter_implements_all_methods(tmp_path):
    """SQLiteAdapter must have no unimplemented abstract methods."""
    adapter = SQLiteAdapter(db_name="drift_check.db", db_dir=tmp_path)
    try:
        unimplemented = [
            name
            for name in PersistenceAdapter.__abstractmethods__
            if not callable(getattr(type(adapter), name, None))
        ]
        assert not unimplemented, (
            f"SQLiteAdapter is missing implementations: {unimplemented}"
        )
    finally:
        adapter.close()
