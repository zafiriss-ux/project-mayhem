"""The upgrade to v30/v31 survives an interruption (DB-01, D-104).

A process killed in the middle of the upgrade (``docker stop`` past its grace time, an
OOM kill, a power cut) gets no commit and no cleanup. The next start must open the
database, finish the upgrade and keep every row. Each crash case runs a child process
that ends with ``os._exit(137)`` right before one chosen SQL statement.

The field-damage cases build by hand the half states the code before D-104 could leave:
an empty ``<table>_v30_new`` beside the old table, or the rows only in
``<table>_v30_new``.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager

_REPO = Path(__file__).resolve().parents[1]

# The v29 shapes of the three tables v30 rebuilds (same as test_schema_v30_multi_athlete).
_V29_DDL = (
    """CREATE TABLE sync_metadata (
        source TEXT PRIMARY KEY,
        last_attempt_ts TEXT,
        last_success_ts TEXT,
        last_sync_ok INTEGER NOT NULL DEFAULT 0,
        last_error_class TEXT
    )""",
    """CREATE TABLE override_log (
        id INTEGER NOT NULL,
        date VARCHAR NOT NULL,
        prescribed_type VARCHAR,
        actual_type VARCHAR,
        reason VARCHAR,
        CONSTRAINT pk_override_log PRIMARY KEY (id)
    )""",
    """CREATE TABLE consent_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        athlete_id   TEXT NOT NULL DEFAULT 'default',
        consent_type TEXT NOT NULL,
        granted_at   TEXT NOT NULL,
        revoked_at   TEXT
    )""",
)
_V30_TABLES = ("sync_metadata", "override_log", "consent_log", "athlete_profiles", "athlete_accounts")
_REBUILT = ("sync_metadata", "override_log", "consent_log")
_TODAY = "2026-10-17"

_SYNC_ROW = ("owner", "garmin", "2026-10-15T07:00:00+00:00", "2026-10-15T07:00:00+00:00", 1, None)
_OVERRIDE_ROW = (7, "owner", "2026-10-14", "TEMPO", "EASY", "legs heavy")
_CONSENT_ROW = (1, "default", "health_data", "unversioned", "2026-06-02", None, "legacy")

_V30_SYNC_DDL = """CREATE TABLE sync_metadata_v30_new (
    athlete_id TEXT NOT NULL, source TEXT NOT NULL, last_attempt_ts TEXT,
    last_success_ts TEXT, last_sync_ok INTEGER NOT NULL DEFAULT 0, last_error_class TEXT,
    PRIMARY KEY (athlete_id, source))"""
_V30_OVERRIDE_DDL = """CREATE TABLE override_log_v30_new (
    id INTEGER NOT NULL, athlete_id VARCHAR NOT NULL, date VARCHAR NOT NULL,
    prescribed_type VARCHAR, actual_type VARCHAR, reason VARCHAR,
    CONSTRAINT pk_override_log PRIMARY KEY (id))"""


def _make_v29_database(path: Path) -> None:
    DatabaseManager(db_dir=path).close()
    raw = sqlite3.connect(path / "titan_core.db")
    for table in _V30_TABLES:
        raw.execute(f"DROP TABLE {table}")
    for ddl in _V29_DDL:
        raw.execute(ddl)
    raw.execute(
        "INSERT INTO sync_metadata VALUES ('garmin', '2026-10-15T07:00:00+00:00', "
        "'2026-10-15T07:00:00+00:00', 1, NULL)"
    )
    raw.execute(
        "INSERT INTO override_log (id, date, prescribed_type, actual_type, reason) "
        "VALUES (7, '2026-10-14', 'TEMPO', 'EASY', 'legs heavy')"
    )
    raw.execute(
        "INSERT INTO consent_log (consent_type, granted_at) VALUES ('health_data', '2026-06-02')"
    )
    raw.execute("PRAGMA user_version = 29")
    raw.commit()
    raw.close()


def _make_v30_database(path: Path) -> None:
    """A current database turned back into v30: worker_routine_executions in its v26 shape."""
    DatabaseManager(db_dir=path).close()
    raw = sqlite3.connect(path / "titan_core.db")
    raw.execute("DROP TABLE worker_routine_executions")
    raw.execute(
        "CREATE TABLE worker_routine_executions (athlete_id TEXT NOT NULL, "
        "execution_date TEXT NOT NULL, routine_type TEXT NOT NULL, started_at TEXT NOT NULL, "
        "completed_at TEXT, PRIMARY KEY (athlete_id, execution_date, routine_type))"
    )
    raw.execute(
        "INSERT INTO worker_routine_executions VALUES "
        f"('owner', '{_TODAY}', 'morning', '{_TODAY}T07:00:00+00:00', '{_TODAY}T07:02:00+00:00')"
    )
    raw.execute("PRAGMA user_version = 30")
    raw.commit()
    raw.close()


_CHILD = textwrap.dedent("""
    import os
    import sqlite3
    import sys
    from pathlib import Path

    target = " ".join(sys.argv[2].split())
    real_connect = sqlite3.connect


    class CrashCursor(sqlite3.Cursor):
        def execute(self, sql, *args):
            if " ".join(str(sql).split()) == target:
                sys.stdout.write("KILLED\\n")
                sys.stdout.flush()
                os._exit(137)  # a kill: no commit, no rollback, no cleanup
            return super().execute(sql, *args)


    class CrashConnection(sqlite3.Connection):
        def cursor(self, factory=CrashCursor):
            return super().cursor(factory)

        def execute(self, sql, *args):
            return self.cursor().execute(sql, *args)


    def connect(*a, **k):
        k.setdefault("factory", CrashConnection)
        return real_connect(*a, **k)


    sqlite3.connect = connect
    from titan.core.database import DatabaseManager

    DatabaseManager(db_dir=Path(sys.argv[1])).close()
    sys.stdout.write("NOT KILLED\\n")
""")


def _open_and_kill_before(tmp_path: Path, statement: str) -> None:
    script = tmp_path / "crash_child.py"
    script.write_text(_CHILD, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(_REPO), TITAN_DATA_DIR=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, str(script), str(tmp_path), statement],
        cwd=_REPO, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 137 and proc.stdout.strip() == "KILLED", (
        f"the child was not killed before {statement!r}: rc={proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr[-2000:]}"
    )


def _tables(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _assert_upgraded_with_rows(path: Path) -> None:
    db = DatabaseManager(db_dir=path)  # the next start
    try:
        conn = db.conn
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert not {t for t in _tables(conn) if t.endswith("_v30_new")}
        assert conn.execute(
            "SELECT athlete_id, source, last_attempt_ts, last_success_ts, last_sync_ok, "
            "last_error_class FROM sync_metadata"
        ).fetchall() == [_SYNC_ROW]
        assert conn.execute(
            "SELECT id, athlete_id, date, prescribed_type, actual_type, reason FROM override_log"
        ).fetchall() == [_OVERRIDE_ROW]
        assert conn.execute(
            "SELECT id, athlete_id, consent_type, text_version, granted_at, revoked_at, channel "
            "FROM consent_log"
        ).fetchall() == [_CONSENT_ROW]
    finally:
        db.close()


# Every statement of the v30 step that writes, and the closing user_version write.
_V30_KILL_POINTS = [
    pytest.param(
        "INSERT INTO sync_metadata_v30_new SELECT 'owner', source, last_attempt_ts, "
        "last_success_ts, last_sync_ok, last_error_class FROM sync_metadata",
        id="sync_metadata-after-create",
    ),
    pytest.param("DROP TABLE sync_metadata", id="sync_metadata-before-drop"),
    pytest.param(
        "ALTER TABLE sync_metadata_v30_new RENAME TO sync_metadata", id="sync_metadata-before-rename"
    ),
    pytest.param("DROP TABLE override_log", id="override_log-before-drop"),
    pytest.param(
        "ALTER TABLE override_log_v30_new RENAME TO override_log", id="override_log-before-rename"
    ),
    pytest.param("DROP TABLE consent_log", id="consent_log-before-drop"),
    pytest.param(
        "ALTER TABLE consent_log_v30_new RENAME TO consent_log", id="consent_log-before-rename"
    ),
    pytest.param(f"PRAGMA user_version = {SCHEMA_VERSION}", id="before-user-version"),
]


@pytest.mark.parametrize("statement", _V30_KILL_POINTS)
def test_v30_upgrade_killed_midway_finishes_on_next_start(tmp_path, statement):
    _make_v29_database(tmp_path)
    _open_and_kill_before(tmp_path, statement)
    _assert_upgraded_with_rows(tmp_path)


def test_v31_upgrade_killed_before_attempts_backfill_keeps_old_rows_at_one(tmp_path):
    """A v30 row was one run that is over: it must end with attempts = 1, never 0."""
    _make_v30_database(tmp_path)
    _open_and_kill_before(tmp_path, "UPDATE worker_routine_executions SET attempts = 1")
    db = DatabaseManager(db_dir=tmp_path)
    try:
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.conn.execute(
            "SELECT athlete_id, completed_at, delivered_at, attempts FROM worker_routine_executions"
        ).fetchall() == [("owner", f"{_TODAY}T07:02:00+00:00", None, 1)]
    finally:
        db.close()


# ── databases damaged in the field by the code before D-104 ─────────────────────────


def _damage(path: Path, *statements: str) -> None:
    raw = sqlite3.connect(path / "titan_core.db")
    for sql in statements:
        raw.execute(sql)
    raw.commit()
    raw.close()


def test_stale_empty_v30_new_beside_old_table_is_dropped_and_rebuilt(tmp_path):
    """The restart loop: an empty sync_metadata_v30_new committed, old rows intact, v29."""
    _make_v29_database(tmp_path)
    _damage(tmp_path, _V30_SYNC_DDL)
    _assert_upgraded_with_rows(tmp_path)


def test_rows_only_in_v30_new_are_renamed_back(tmp_path):
    """Old sync_metadata dropped, its rows only in sync_metadata_v30_new: no empty table."""
    _make_v29_database(tmp_path)
    _damage(
        tmp_path,
        _V30_SYNC_DDL,
        "INSERT INTO sync_metadata_v30_new SELECT 'owner', * FROM sync_metadata",
        "DROP TABLE sync_metadata",
    )
    _assert_upgraded_with_rows(tmp_path)


def test_base_table_rows_only_in_v30_new_are_renamed_back(tmp_path):
    """override_log is a base table: the start must not create it empty over the rows."""
    _make_v29_database(tmp_path)
    _damage(
        tmp_path,
        _V30_OVERRIDE_DDL,
        "INSERT INTO override_log_v30_new SELECT id, 'owner', date, prescribed_type, "
        "actual_type, reason FROM override_log",
        "DROP TABLE override_log",
    )
    _assert_upgraded_with_rows(tmp_path)


def test_rows_orphaned_in_v30_new_after_upgrade_are_moved_back(tmp_path):
    """The silent loss already happened: user_version 31, an empty sync_metadata in the
    new shape, the rows only in sync_metadata_v30_new. The next start moves them back."""
    DatabaseManager(db_dir=tmp_path).close()
    _damage(
        tmp_path,
        _V30_SYNC_DDL,
        "INSERT INTO sync_metadata_v30_new VALUES ('owner', 'garmin', "
        "'2026-10-15T07:00:00+00:00', '2026-10-15T07:00:00+00:00', 1, NULL)",
    )
    db = DatabaseManager(db_dir=tmp_path)
    try:
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert "sync_metadata_v30_new" not in _tables(db.conn)
        assert db.conn.execute(
            "SELECT athlete_id, source, last_attempt_ts, last_success_ts, last_sync_ok, "
            "last_error_class FROM sync_metadata"
        ).fetchall() == [_SYNC_ROW]
    finally:
        db.close()


def test_new_table_with_rows_and_v30_new_with_rows_are_both_kept(tmp_path):
    """Two copies with rows: nothing is dropped, the open still succeeds."""
    DatabaseManager(db_dir=tmp_path).close()
    _damage(
        tmp_path,
        "INSERT INTO sync_metadata VALUES ('owner', 'garmin', NULL, NULL, 1, NULL)",
        _V30_SYNC_DDL,
        "INSERT INTO sync_metadata_v30_new VALUES ('owner', 'hrv_rewrite', NULL, NULL, 1, NULL)",
    )
    db = DatabaseManager(db_dir=tmp_path)
    try:
        assert db.conn.execute("SELECT COUNT(*) FROM sync_metadata").fetchone()[0] == 1
        assert db.conn.execute("SELECT COUNT(*) FROM sync_metadata_v30_new").fetchone()[0] == 1
    finally:
        db.close()
