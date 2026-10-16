"""D-078: the WAL file shrinks back to a size limit after a checkpoint.

Without ``journal_size_limit`` SQLite keeps the WAL at its largest size; the SQLite
assessment saw 861 MB beside a 107 MB database.
"""

from __future__ import annotations

import pytest

import titan.core.database as database
from titan.core.database import WAL_SIZE_LIMIT_BYTES, DatabaseManager


@pytest.mark.unit
def test_the_connection_sets_the_wal_size_limit(tmp_path) -> None:
    db = DatabaseManager(db_dir=tmp_path)
    try:
        limit = db.conn.execute("PRAGMA journal_size_limit").fetchone()[0]
        assert limit == WAL_SIZE_LIMIT_BYTES == 64 * 1024 * 1024
    finally:
        db.close()


@pytest.mark.unit
def test_the_wal_shrinks_to_the_limit_after_a_checkpoint(tmp_path, monkeypatch) -> None:
    small = 64 * 1024
    monkeypatch.setattr(database, "WAL_SIZE_LIMIT_BYTES", small)
    db = DatabaseManager(db_dir=tmp_path)
    wal = tmp_path / "titan_core.db-wal"
    try:
        db.conn.execute("PRAGMA wal_autocheckpoint=0")
        db.conn.execute("CREATE TABLE filler (blob TEXT)")
        db.conn.executemany("INSERT INTO filler VALUES (?)", [("x" * 4000,) for _ in range(500)])
        db.conn.commit()
        assert wal.stat().st_size > 10 * small

        db.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        db.conn.execute("INSERT INTO filler VALUES ('y')")  # the next write resets the WAL
        db.conn.commit()
        assert wal.stat().st_size <= small
    finally:
        db.close()
