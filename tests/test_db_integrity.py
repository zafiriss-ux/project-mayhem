import sqlite3

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager


@pytest.mark.unit
def test_foreign_keys_enabled_on_fresh_db(tmp_path):
    db = DatabaseManager(db_name="fk_enabled.db", db_dir=tmp_path)
    try:
        cursor = db.conn.cursor()
        assert cursor.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.unit
def test_foreign_key_enforcement_is_live(tmp_path):
    """A shoe_id with no matching gear_usage row must be rejected, proving the
    FK constraint is enforced rather than merely declared."""
    db = DatabaseManager(db_name="fk_live.db", db_dir=tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO training_log (athlete_id, date, shoe_id) "
                "VALUES ('owner', '2026-06-21', 999999)"
            )
    finally:
        db.close()


@pytest.mark.unit
def test_fk_fail_closed_on_preexisting_violations(tmp_path):
    """If a DB already has orphaned FK rows, opening it must refuse rather
    than silently start enforcing FKs (which would surface as write errors
    elsewhere instead of a clear startup failure)."""
    db_path = tmp_path / "fk_violating.db"

    raw = sqlite3.connect(str(db_path))
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(
        "CREATE TABLE gear_usage (id INTEGER PRIMARY KEY, shoe_name TEXT NOT NULL)"
    )
    raw.execute(
        "CREATE TABLE training_log (id INTEGER PRIMARY KEY, athlete_id TEXT, "
        "date TEXT, shoe_id INTEGER REFERENCES gear_usage(id))"
    )
    raw.execute(
        "INSERT INTO training_log (athlete_id, date, shoe_id) "
        "VALUES ('owner', '2026-06-21', 999999)"
    )
    raw.commit()
    raw.close()

    with pytest.raises(RuntimeError, match="[Ii]ntegrity violations"):
        DatabaseManager(db_name="fk_violating.db", db_dir=tmp_path)


@pytest.mark.unit
def test_schema_forward_guard_refuses_newer_db(tmp_path):
    db_path = tmp_path / "forward_guard.db"

    db = DatabaseManager(db_name="forward_guard.db", db_dir=tmp_path)
    db.close()

    raw = sqlite3.connect(str(db_path))
    raw.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    raw.commit()
    raw.close()

    with pytest.raises(RuntimeError, match="user_version"):
        DatabaseManager(db_name="forward_guard.db", db_dir=tmp_path)


@pytest.mark.unit
def test_schema_version_equal_opens_clean(tmp_path):
    db_path = tmp_path / "equal_version.db"

    db = DatabaseManager(db_name="equal_version.db", db_dir=tmp_path)
    db.close()

    raw = sqlite3.connect(str(db_path))
    assert raw.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    raw.close()

    db2 = DatabaseManager(db_name="equal_version.db", db_dir=tmp_path)
    db2.close()


@pytest.mark.unit
def test_older_schema_version_still_migrates(tmp_path):
    db_path = tmp_path / "older_version.db"

    db = DatabaseManager(db_name="older_version.db", db_dir=tmp_path)
    db.close()

    raw = sqlite3.connect(str(db_path))
    raw.execute(f"PRAGMA user_version={SCHEMA_VERSION - 1}")
    raw.commit()
    raw.close()

    db2 = DatabaseManager(db_name="older_version.db", db_dir=tmp_path)
    try:
        cursor = db2.conn.cursor()
        assert cursor.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        db2.close()
