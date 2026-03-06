import logging
import sqlite3
from unittest.mock import patch

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager


class _ErrorCursor:
    """Cursor that raises a non-duplicate OperationalError on ALTER TABLE."""

    _pragma_result = type("Row", (), {"__getitem__": lambda self, i: 0})()

    def execute(self, sql):
        if sql.strip().upper().startswith("PRAGMA"):
            return self  # supports .fetchone()
        raise sqlite3.OperationalError("disk I/O error")

    def fetchone(self):
        return (0,)


class _DuplicateColumnCursor:
    """Cursor that raises duplicate-column error on ALTER TABLE."""

    def execute(self, sql):
        if sql.strip().upper().startswith("PRAGMA"):
            return self
        raise sqlite3.OperationalError("duplicate column name: hrr_60")

    def fetchone(self):
        return (0,)


def test_run_migrations_suppresses_only_duplicate_column_error(tmp_path):
    db = DatabaseManager(db_name="migration_test.db", db_dir=tmp_path)
    cursor = db.conn.cursor()

    # Columns already exist after init; running again should only encounter duplicate-column errors.
    db._run_migrations(cursor)

    db.close()


def test_apply_v1_migrations_reraises_non_duplicate_operational_error(tmp_path):
    """_apply_v1_migrations must re-raise non-duplicate-column OperationalErrors."""
    db = DatabaseManager(db_name="v1_error.db", db_dir=tmp_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
            db._apply_v1_migrations(_ErrorCursor())
    finally:
        db.close()


def test_apply_v1_migrations_suppresses_duplicate_column_operational_error(tmp_path):
    """_apply_v1_migrations must suppress duplicate-column OperationalErrors."""
    db = DatabaseManager(db_name="v1_dup.db", db_dir=tmp_path)
    try:
        db._apply_v1_migrations(_DuplicateColumnCursor())  # must not raise
    finally:
        db.close()


def test_run_migrations_emits_structured_log_on_column_add(tmp_path, caplog):
    """Structured migration log events must be emitted (JSON format) on first init."""
    import json as _json

    caplog.set_level(logging.INFO, logger="titan.core.database")

    db = DatabaseManager(db_name="migration_log.db", db_dir=tmp_path)

    migration_payloads = []
    for record in caplog.records:
        try:
            payload = _json.loads(record.message)
            if payload.get("action") == "db_schema_migration":
                migration_payloads.append(payload)
        except (ValueError, AttributeError):
            pass

    assert migration_payloads, "Expected db_schema_migration JSON log events on first init"
    assert all("version" in p for p in migration_payloads)

    db.close()


def test_database_manager_init_logs_structured_warning_when_best_effort_logging_fails(
    tmp_path,
    monkeypatch,
    caplog,
):
    logger = logging.getLogger("titan.database")

    def _raise_os_error(_message):
        raise OSError("log sink unavailable")

    monkeypatch.setattr(logger, "info", _raise_os_error)

    caplog.set_level(logging.WARNING, logger="titan.core.database")
    db = DatabaseManager(db_name="init_logging_warn.db", db_dir=tmp_path)

    payloads = [
        record.message
        for record in caplog.records
        if "db_init_logging_skipped" in record.message
    ]
    assert payloads, "Expected db_init_logging_skipped structured warning"
    db.close()


def test_database_manager_init_logs_data_dir_fallback_when_launcher_missing(
    tmp_path,
    caplog,
):
    real_import = __import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "launcher.validator":
            raise ModuleNotFoundError("No module named 'launcher'", name="launcher")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=_fake_import):
        caplog.set_level(logging.WARNING, logger="titan.core.database")
        db = DatabaseManager(db_name="fallback_dir.db", db_dir=None)

    payloads = [
        record.message
        for record in caplog.records
        if "db_init_data_directory_fallback" in record.message
    ]
    assert payloads, "Expected db_init_data_directory_fallback structured warning"
    db.close()


def test_database_manager_init_reraises_non_launcher_module_not_found(tmp_path):
    real_import = __import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "launcher.validator":
            raise ModuleNotFoundError("No module named 'sqlite3'", name="sqlite3")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=_fake_import), pytest.raises(
        ModuleNotFoundError,
        match="sqlite3",
    ):
        DatabaseManager(db_name="should_fail.db", db_dir=None)


# ── T1-16: PRAGMA user_version schema tracking ──────────────────────────────

def test_schema_migration_sets_user_version_to_schema_version_on_fresh_db(tmp_path):
    """A fresh DB must have user_version == SCHEMA_VERSION after init."""
    db = DatabaseManager(db_name="version_fresh.db", db_dir=tmp_path)
    try:
        with db._lock:
            version = db.conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        db.close()


def test_schema_migration_idempotent_on_second_call(tmp_path):
    """Calling _run_migrations() a second time must not raise and must leave
    user_version unchanged."""
    db = DatabaseManager(db_name="version_idempotent.db", db_dir=tmp_path)
    try:
        cursor = db.conn.cursor()
        db._run_migrations(cursor)
        with db._lock:
            version = db.conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        db.close()


# ── T1-17: Daily SQLite hot backup ──────────────────────────────────────────

def test_backup_creates_file_in_backup_dir(tmp_path):
    """backup_database() must create a dated backup file in the backup dir."""
    db = DatabaseManager(db_name="backup_create.db", db_dir=tmp_path)
    backup_dir = tmp_path / "backups"
    try:
        result = db.backup_database(backup_dir=backup_dir)
        assert result is not None
        assert result.exists()
        assert result.name.startswith("titan_")
        assert result.suffix == ".db"
    finally:
        db.close()


def test_backup_idempotent_same_day(tmp_path):
    """Calling backup_database() twice on the same day must create one file and
    return None on the second call (no-op)."""
    db = DatabaseManager(db_name="backup_idempotent.db", db_dir=tmp_path)
    backup_dir = tmp_path / "backups"
    try:
        first = db.backup_database(backup_dir=backup_dir)
        second = db.backup_database(backup_dir=backup_dir)
        assert first is not None
        assert second is None
        assert len(list(backup_dir.glob("titan_*.db"))) == 1
    finally:
        db.close()


def test_backup_prunes_old_files(tmp_path):
    """backup_database() with keep=3 must remove files beyond the 3 most recent."""
    from pathlib import Path

    db = DatabaseManager(db_name="backup_prune.db", db_dir=tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Pre-populate 5 old dated backup files
    for i in range(1, 6):
        (backup_dir / f"titan_2026-01-0{i}.db").write_bytes(b"")

    try:
        db.backup_database(backup_dir=backup_dir, keep=3)
        remaining = sorted(backup_dir.glob("titan_*.db"))
        assert len(remaining) == 3
    finally:
        db.close()
