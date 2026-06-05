"""TD-NEW-12: SQLite read-lock hardening tests."""
from __future__ import annotations

import ast
import pathlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pytest

from titan.core.database import DatabaseManager


def _seed_rows(db: DatabaseManager, n: int) -> None:
    for i in range(n):
        db.save_session(
            date=f"2026-0{(i % 9) + 1}-{(i % 28) + 1:02d}",
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            rpe=5,
            training_load=50,
        )


@pytest.mark.integration
@pytest.mark.governance
def test_concurrent_read_write_no_corruption(tmp_path):
    db = DatabaseManager(db_name="td12_rw.db", db_dir=tmp_path)
    errors: list[Exception] = []

    def _write():
        try:
            for i in range(100):
                db.save_session(
                    date=f"2026-01-{(i % 28) + 1:02d}",
                    session_type="EASY",
                    distance_km=5.0,
                    duration_sec=1800,
                    rpe=4,
                    training_load=30,
                )
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            errors.append(e)

    def _read():
        try:
            for _ in range(100):
                db.get_training_load_history(days=90, athlete_id="owner")
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_write), pool.submit(_read),
                   pool.submit(_read), pool.submit(_write)]
        for f in as_completed(futures):
            f.result()

    assert not errors, f"Concurrent read/write errors: {errors}"
    db.close()


@pytest.mark.integration
@pytest.mark.governance
def test_all_read_methods_use_lock():
    """Fitness function — CI-blocking: every get_/fetch_/load_ must hold the lock."""
    src = pathlib.Path("titan/core/database.py").read_text()
    tree = ast.parse(src)
    dm_class = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "DatabaseManager"
    )
    lines = src.splitlines()
    violations: list[str] = []
    for method in ast.walk(dm_class):
        if not isinstance(method, ast.FunctionDef):
            continue
        name = method.name
        if not (name.startswith("get_") or name.startswith("fetch_") or name.startswith("load_")):
            continue
        if name.startswith("_"):
            continue
        method_src = "\n".join(lines[method.lineno - 1 : method.end_lineno])
        if "self._lock" not in method_src:
            violations.append(f"L{method.lineno}: {name}")
    assert not violations, (
        f"Read methods missing self._lock ({len(violations)}):\n  " + "\n  ".join(violations)
    )
