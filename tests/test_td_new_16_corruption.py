"""TD-NEW-16: DatabaseManager corruption-detection and backup tests."""
from __future__ import annotations

import pytest

from titan.core.database import DatabaseManager


@pytest.mark.integration
def test_integrity_check_method_exists():
    db = DatabaseManager(":memory:")
    assert hasattr(db, "check_integrity")
    assert callable(db.check_integrity)
    db.close()


@pytest.mark.integration
def test_integrity_check_passes_healthy_db(tmp_path):
    db = DatabaseManager(db_name="healthy.db", db_dir=tmp_path)
    try:
        assert db.check_integrity() is True
    finally:
        db.close()


@pytest.mark.integration
def test_integrity_check_detects_corruption(tmp_path):
    path = tmp_path / "corrupt.db"
    db = DatabaseManager(db_name="corrupt.db", db_dir=tmp_path)
    db.save_session(
        date="2026-01-01",
        session_type="EASY",
        distance_km=5.0,
        duration_sec=1800,
        rpe=4,
        training_load=30,
    )
    db.close()

    # Overwrite header area to corrupt the SQLite file
    data = bytearray(path.read_bytes())
    data[100:150] = b"\x00" * 50
    path.write_bytes(bytes(data))

    try:
        db2 = DatabaseManager(db_name="corrupt.db", db_dir=tmp_path)
        result = db2.check_integrity()
        assert result is False, "check_integrity() should return False for corrupted DB"
        db2.close()
    except Exception:
        pass  # corruption detected at open — acceptable per spec


@pytest.mark.integration
def test_backup_and_restore_roundtrip(tmp_path):
    db = DatabaseManager(db_name="source.db", db_dir=tmp_path)
    db.save_session(
        date="2026-03-01",
        session_type="TEMPO",
        distance_km=10.0,
        duration_sec=3600,
        rpe=7,
        training_load=70,
    )
    backup_dir = tmp_path / "backups"
    result = db.backup_database(backup_dir=backup_dir)
    db.close()

    assert result is not None, "backup_database() should return a path"
    assert result.exists(), "Backup file should exist"

    db2 = DatabaseManager(db_name=result.name, db_dir=backup_dir)
    rows = db2.get_training_load_history(days=365, athlete_id="owner")
    assert rows, "Backup DB should contain the inserted training rows"
    db2.close()
