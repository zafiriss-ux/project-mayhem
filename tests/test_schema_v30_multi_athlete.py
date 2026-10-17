"""Schema v30, Phase 4 step 2 (ADR-0067 D3, D4, D5; D-091).

- ``sync_metadata`` and ``override_log`` get ``athlete_id`` with no DEFAULT; the rows a
  v29 database already has become the owner's.
- ``consent_log`` gets ``text_version`` and ``channel`` and loses the ``'default'``
  athlete; an old row can never count as consent to a numbered text.
- ``athlete_profiles`` and ``athlete_accounts`` exist for athletes other than the owner.
"""

from __future__ import annotations

import sqlite3

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager

# The v29 shapes of the three rebuilt tables (main 39aee23).
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


def _make_v29_database(tmp_path) -> None:
    db = DatabaseManager(db_dir=tmp_path)
    db.close()
    raw = sqlite3.connect(tmp_path / "titan_core.db")
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


def _athlete_id_column(conn, table: str) -> tuple:
    return next(row for row in conn.execute(f"PRAGMA table_info({table})") if row[1] == "athlete_id")


@pytest.fixture
def upgraded(tmp_path):
    _make_v29_database(tmp_path)
    db = DatabaseManager(db_dir=tmp_path)
    yield db
    db.close()


@pytest.mark.unit
def test_v29_rows_become_the_owners(upgraded) -> None:
    conn = upgraded.conn
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 32
    assert conn.execute("SELECT athlete_id, source, last_sync_ok FROM sync_metadata").fetchall() == [
        ("owner", "garmin", 1)
    ]
    assert conn.execute("SELECT id, athlete_id, reason FROM override_log").fetchall() == [
        (7, "owner", "legs heavy")
    ]
    assert upgraded.get_last_sync_outcome("garmin")["last_sync_ok"] is True
    assert upgraded.get_override_log()[0]["reason"] == "legs heavy"


@pytest.mark.unit
def test_old_consent_rows_never_count_as_consent(upgraded) -> None:
    rows = upgraded.conn.execute(
        "SELECT athlete_id, consent_type, text_version, channel FROM consent_log"
    ).fetchall()
    assert rows == [("default", "health_data", "unversioned", "legacy")]


@pytest.mark.unit
@pytest.mark.parametrize("table", ["sync_metadata", "override_log", "consent_log"])
def test_new_athlete_id_columns_have_no_default(upgraded, table) -> None:
    _cid, _name, _type, notnull, default, _pk = _athlete_id_column(upgraded.conn, table)
    assert notnull == 1
    assert default is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "insert",
    [
        "INSERT INTO sync_metadata (source) VALUES ('weather')",
        "INSERT INTO override_log (date) VALUES ('2026-10-16')",
        "INSERT INTO consent_log (consent_type, text_version, granted_at, channel) "
        "VALUES ('health_data', 'v1', '2026-10-16', 'telegram')",
        "INSERT INTO athlete_profiles (birth_date, sex, weight_kg, height_cm, max_hr, threshold_hr, "
        "training_phase, training_goal, location_city, location_country, updated_at) "
        "VALUES ('1990-01-01', 'F', 60, 165, 190, 170, 'BUILD', '10K', 'Athens', 'GR', 'now')",
        "INSERT INTO athlete_accounts (garmin_token_state, updated_at) VALUES ('missing', 'now')",
    ],
)
def test_an_insert_without_athlete_id_fails(upgraded, insert) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        upgraded.conn.execute(insert)


@pytest.mark.unit
def test_sync_metadata_is_keyed_by_athlete_and_source(upgraded) -> None:
    conn = upgraded.conn
    conn.execute("INSERT INTO athletes (athlete_id, display_name, created_at) VALUES ('a-0000beef', 'A', 'now')")
    conn.execute("INSERT INTO sync_metadata (athlete_id, source) VALUES ('a-0000beef', 'garmin')")
    assert conn.execute("SELECT COUNT(*) FROM sync_metadata WHERE source = 'garmin'").fetchone()[0] == 2


@pytest.mark.unit
def test_a_garmin_account_and_a_chat_bind_to_one_athlete(upgraded) -> None:
    conn = upgraded.conn
    for athlete in ("a-00000001", "a-00000002"):
        conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')",
            (athlete, athlete),
        )
    conn.execute(
        "INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_token_state, "
        "telegram_chat_id, updated_at) VALUES ('a-00000001', 'g-1', 'ok', '111', 'now')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_token_state, "
            "updated_at) VALUES ('a-00000002', 'g-1', 'ok', 'now')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO athlete_accounts (athlete_id, garmin_token_state, telegram_chat_id, "
            "updated_at) VALUES ('a-00000002', 'ok', '111', 'now')"
        )


@pytest.mark.unit
def test_a_profile_rejects_an_unknown_sex(upgraded) -> None:
    conn = upgraded.conn
    conn.execute("INSERT INTO athletes (athlete_id, display_name, created_at) VALUES ('a-0000beef', 'A', 'now')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO athlete_profiles VALUES ('a-0000beef', '1990-01-01', 'X', 70, 175, 190, "
            "170, 'BUILD', '10K', 'Athens', 'GR', 'now')"
        )


@pytest.mark.unit
def test_reopening_a_v30_database_changes_nothing(tmp_path) -> None:
    _make_v29_database(tmp_path)
    DatabaseManager(db_dir=tmp_path).close()
    raw = sqlite3.connect(tmp_path / "titan_core.db")
    before = raw.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    raw.close()

    db = DatabaseManager(db_dir=tmp_path)
    try:
        after = db.conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
        assert after == before
        assert db.conn.execute("SELECT COUNT(*) FROM override_log").fetchone()[0] == 1
    finally:
        db.close()
