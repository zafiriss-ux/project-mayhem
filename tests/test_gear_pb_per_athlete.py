"""F9 (D-076), AGENTS §13.4 Stage 2: shoes and personal bests are written with their athlete.

The athlete_id columns already exist (DEFAULT 'owner'); reads are unchanged until Stage 3.
"""

from __future__ import annotations

import pytest

from titan.core.database import DatabaseManager
from titan.core.persistence import SQLiteAdapter


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
def test_add_shoe_writes_the_athlete(db) -> None:
    owner_shoe = db.add_shoe("Pegasus")
    other_shoe = db.add_shoe("Vaporfly", shoe_type="RACE", athlete_id="athlete-b")
    rows = dict(db.conn.execute("SELECT id, athlete_id FROM gear_usage").fetchall())
    assert rows == {owner_shoe: "owner", other_shoe: "athlete-b"}


@pytest.mark.unit
def test_save_personal_best_writes_the_athlete(db) -> None:
    db.save_personal_best(5.0, 1200, "2026-03-01")
    db.save_personal_best(5.0, 1100, "2026-03-02", athlete_id="athlete-b")
    rows = db.conn.execute(
        "SELECT time_sec, athlete_id FROM personal_bests ORDER BY time_sec"
    ).fetchall()
    assert rows == [(1100, "athlete-b"), (1200, "owner")]


@pytest.mark.unit
def test_the_sqlite_adapter_passes_the_athlete_through(tmp_path) -> None:
    adapter = SQLiteAdapter(db_name="adapter.db", db_dir=tmp_path)
    try:
        adapter.add_shoe("Trail", athlete_id="athlete-b")
        adapter.save_personal_best(10.0, 2400, "2026-03-03", athlete_id="athlete-b")
        conn = adapter._manager.conn
        assert conn.execute("SELECT athlete_id FROM gear_usage").fetchall() == [("athlete-b",)]
        assert conn.execute("SELECT athlete_id FROM personal_bests").fetchall() == [("athlete-b",)]
    finally:
        adapter.close()
