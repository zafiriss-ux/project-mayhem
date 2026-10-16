"""D-080: a Garmin activity edited after the first sync updates its stored row.

Before, INSERT OR IGNORE kept the first version and every later edit was dropped.
"""

from __future__ import annotations

import pytest

from titan.core.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


def _rows(db):
    return db.conn.execute(
        "SELECT athlete_id, date, distance_km, duration_sec, avg_hr, training_load, notes, shoe_id "
        "FROM training_log ORDER BY athlete_id"
    ).fetchall()


@pytest.mark.unit
def test_a_resynced_edit_replaces_the_stored_activity(db) -> None:
    db.save_session("2026-10-10", "EASY", 8.0, 2400, avg_hr=140, training_load=60,
                    notes="Morning Run", garmin_activity_id="g-1")
    db.save_session("2026-10-10", "TEMPO", 10.0, 3000, avg_hr=150, training_load=90,
                    notes="Tempo (edited)", garmin_activity_id="g-1")
    assert _rows(db) == [("owner", "2026-10-10", 10.0, 3000, 150, 90, "Tempo (edited)", None)]


@pytest.mark.unit
def test_the_edited_load_reaches_the_load_history(db) -> None:
    today = db.conn.execute("SELECT date('now')").fetchone()[0]
    db.save_session(today, "EASY", 8.0, 2400, training_load=60, garmin_activity_id="g-1")
    db.save_session(today, "EASY", 8.0, 2400, training_load=95, garmin_activity_id="g-1")
    assert db.get_training_load_history(days=7) == [(today, 95.0)]


@pytest.mark.unit
def test_the_shoe_is_kept_and_its_km_follow_the_edit(db) -> None:
    shoe = db.add_shoe("Pegasus")
    db.save_session("2026-10-10", "EASY", 8.0, 2400, shoe_id=shoe, garmin_activity_id="g-1")
    db.save_session("2026-10-10", "EASY", 10.0, 3000, garmin_activity_id="g-1")  # no shoe from Garmin
    assert _rows(db)[0][-1] == shoe
    km = db.conn.execute("SELECT total_km FROM gear_usage WHERE id = ?", (shoe,)).fetchone()[0]
    assert km == 10.0


@pytest.mark.unit
def test_a_new_shoe_takes_the_km_from_the_old_one(db) -> None:
    old, new = db.add_shoe("Pegasus"), db.add_shoe("Vaporfly")
    db.save_session("2026-10-10", "EASY", 8.0, 2400, shoe_id=old, garmin_activity_id="g-1")
    db.save_session("2026-10-10", "EASY", 8.0, 2400, shoe_id=new, garmin_activity_id="g-1")
    km = dict(db.conn.execute("SELECT id, total_km FROM gear_usage").fetchall())
    assert km == {old: 0.0, new: 8.0}


@pytest.mark.unit
def test_another_athletes_activity_with_the_same_id_is_left_alone(db) -> None:
    db.save_session("2026-10-10", "EASY", 8.0, 2400, training_load=60, garmin_activity_id="g-1")
    db.save_session("2026-10-10", "EASY", 20.0, 6000, training_load=200, garmin_activity_id="g-1",
                    athlete_id="athlete-b")
    assert _rows(db) == [("owner", "2026-10-10", 8.0, 2400, None, 60, None, None)]
