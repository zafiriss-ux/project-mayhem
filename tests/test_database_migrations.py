import logging
import sqlite3
from unittest.mock import patch

import pytest

from titan.core.database import DatabaseManager


class _DummyConn:
    def commit(self):
        return None


class _ErrorCursor:
    def execute(self, _sql):
        raise sqlite3.OperationalError("disk I/O error")


class _DuplicateColumnCursor:
    def execute(self, _sql):
        raise sqlite3.OperationalError("duplicate column name: hrr_60")


def test_run_migrations_suppresses_only_duplicate_column_error(tmp_path):
    db = DatabaseManager(db_name="migration_test.db", db_dir=tmp_path)
    cursor = db.conn.cursor()

    # Columns already exist after init; running again should only encounter duplicate-column errors.
    db._run_migrations(cursor)

    db.close()


def test_run_migrations_reraises_non_duplicate_operational_error():
    dummy_db = type("DummyDB", (), {"conn": _DummyConn()})()

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        DatabaseManager._run_migrations(dummy_db, _ErrorCursor())


def test_run_migrations_suppresses_duplicate_column_operational_error():
    dummy_db = type("DummyDB", (), {"conn": _DummyConn()})()

    DatabaseManager._run_migrations(dummy_db, _DuplicateColumnCursor())


def test_run_migrations_emits_structured_log_on_column_add(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="titan.core.database")

    db = DatabaseManager(db_name="migration_log.db", db_dir=tmp_path)

    records = [
        record for record in caplog.records if record.message == "db_schema_migration"
    ]
    assert records, "Expected db_schema_migration log records when columns are added"

    for record in records:
        assert hasattr(record, "column_added")
        assert hasattr(record, "table")
        assert hasattr(record, "timestamp")

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
