import logging
import sqlite3

import pytest

from titan.core.database import DatabaseManager


class _DummyConn:
    def commit(self):
        return None


class _ErrorCursor:
    def execute(self, _sql):
        raise sqlite3.OperationalError("disk I/O error")


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
