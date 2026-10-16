"""F9 (D-076), AGENTS §13.4 Stage 3: shoes and personal bests are read per athlete.

Stage 1 is the existing athlete_id columns (DEFAULT 'owner'); Stage 2 (#1017) writes
the athlete. Here the reads and the mileage updates only see the given athlete's rows.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from titan.core.database import DatabaseManager
from titan.core.persistence import PostgreSQLAdapter


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


def _km(db, shoe_id):
    return db.conn.execute("SELECT total_km FROM gear_usage WHERE id = ?", (shoe_id,)).fetchone()[0]


@pytest.mark.unit
def test_get_active_shoes_returns_only_the_athletes_shoes(db) -> None:
    db.add_shoe("Pegasus")
    db.add_shoe("Vaporfly", athlete_id="athlete-b")
    assert [row[1] for row in db.get_active_shoes()] == ["Pegasus"]
    assert [row[1] for row in db.get_active_shoes(athlete_id="athlete-b")] == ["Vaporfly"]


@pytest.mark.unit
def test_another_athletes_shoe_is_not_found(db) -> None:
    other = db.add_shoe("Vaporfly", athlete_id="athlete-b")
    assert db.check_shoe_availability(other) == (False, "Shoe not found")
    assert db.check_shoe_availability(other, athlete_id="athlete-b") == (True, "Available")


@pytest.mark.unit
def test_update_shoe_mileage_skips_another_athletes_shoe(db) -> None:
    other = db.add_shoe("Vaporfly", athlete_id="athlete-b")
    db.update_shoe_mileage(other, 10.0, "2026-03-01")
    assert _km(db, other) == 0
    db.update_shoe_mileage(other, 10.0, "2026-03-01", athlete_id="athlete-b")
    assert _km(db, other) == 10.0


@pytest.mark.unit
def test_a_session_only_adds_mileage_to_its_athletes_shoe(db) -> None:
    other = db.add_shoe("Vaporfly", athlete_id="athlete-b")
    db.save_session("2026-03-01", "EASY", 8.0, 2400, shoe_id=other)
    assert _km(db, other) == 0
    db.save_session("2026-03-02", "EASY", 8.0, 2400, shoe_id=other, athlete_id="athlete-b")
    assert _km(db, other) == 8.0


@pytest.mark.unit
def test_get_pr_returns_the_athletes_own_record(db) -> None:
    db.save_personal_best(5.0, 1200, "2026-03-01")
    db.save_personal_best(5.0, 1100, "2026-03-02", athlete_id="athlete-b")
    assert db.get_pr(5.0)[0] == 1200
    assert db.get_pr(5.0, athlete_id="athlete-b")[0] == 1100
    assert db.get_pr(5.0, athlete_id="athlete-c") is None


def _pg_adapter():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE gear_usage (id INTEGER PRIMARY KEY, athlete_id TEXT, shoe_name TEXT, "
            "total_km REAL DEFAULT 0, last_used TEXT, compression_recovery_hours INTEGER, "
            "status TEXT DEFAULT 'ACTIVE', shoe_type TEXT, max_km_limit REAL DEFAULT 800)"
        ))
        conn.execute(text(
            "CREATE TABLE personal_bests (id INTEGER PRIMARY KEY, athlete_id TEXT, "
            "distance_km REAL, time_sec INTEGER, pace_sec_per_km REAL, date TEXT, race_name TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO gear_usage (id, athlete_id, shoe_name) VALUES "
            "(1, 'owner', 'Pegasus'), (2, 'athlete-b', 'Vaporfly')"
        ))
        conn.execute(text(
            "INSERT INTO personal_bests (athlete_id, distance_km, time_sec, date) VALUES "
            "('owner', 5.0, 1200, '2026-03-01'), ('athlete-b', 5.0, 1100, '2026-03-02')"
        ))
    return engine, PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)


@pytest.mark.integration
def test_postgres_adapter_reads_per_athlete() -> None:
    engine, adapter = _pg_adapter()
    try:
        assert [row[1] for row in adapter.get_active_shoes()] == ["Pegasus"]
        assert adapter.check_shoe_availability(2) == (False, "shoe_not_found")
        assert adapter.check_shoe_availability(2, athlete_id="athlete-b") == (True, "available")
        assert adapter.get_pr(5.0)[0] == 1200
        assert adapter.get_pr(5.0, athlete_id="athlete-b")[0] == 1100
        adapter.update_shoe_mileage(2, 5.0, "2026-03-03")
        adapter.update_shoe_mileage(2, 7.0, "2026-03-03", athlete_id="athlete-b")
        with engine.connect() as conn:
            km = conn.execute(text("SELECT total_km FROM gear_usage WHERE id = 2")).scalar_one()
        assert km == 7.0
    finally:
        adapter.close()
