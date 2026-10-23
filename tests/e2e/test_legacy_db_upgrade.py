"""T-PRA-30 (D-4, C-2), plan task #19: the migration ladder on realistic data.

tests/fixtures/legacy_titan_v0.sql is eight weeks of training written by the
last release before schema versioning (user_version 0, commit 0358e23), with
that release's own code (tests/fixtures/legacy_db_generate.py). Opening it with
the current DatabaseManager must run v1..SCHEMA_VERSION without losing or
mis-scoping a row, and leave the same schema a fresh install gets.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "legacy_titan_v0.sql"
_LEGACY_TABLES = (
    "training_log", "daily_metrics", "gear_usage", "personal_bests",
    "governance_outcomes", "override_log", "cs_performances",
)
# Known ladder-vs-fresh differences, kept visible so a new one fails this test.
# Both are harmless today; reconciling them needs a schema migration (T-PRA-30 note).
_KNOWN_DRIFT = {
    # Fresh DDL (schema.py) says Integer; v3 added TEXT. Writers store "degraded".
    ("training_log", "quality_flag"),
}


def _legacy_counts() -> dict[str, int]:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_FIXTURE.read_text(encoding="utf-8"))
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _LEGACY_TABLES}
    conn.close()
    return counts


def _open_upgraded(tmp_path: Path) -> DatabaseManager:
    raw = sqlite3.connect(tmp_path / "titan_core.db")
    raw.executescript(_FIXTURE.read_text(encoding="utf-8"))
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    raw.close()
    return DatabaseManager(db_dir=tmp_path)


def _affinity(declared: str) -> str:
    """SQLite column affinity (https://sqlite.org/datatype3.html section 3.1)."""
    t = declared.upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if not t or "BLOB" in t:
        return "BLOB"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _columns(db: DatabaseManager) -> dict[tuple[str, str], tuple]:
    out = {}
    tables = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (table,) in tables:
        for _cid, name, decl, notnull, default, pk in db.conn.execute(f"PRAGMA table_info({table})"):
            norm_default = None if default is None else str(default).strip("'")
            out[(table, name)] = (_affinity(decl), bool(notnull) and not pk, norm_default, pk)
    return out


@pytest.fixture
def upgraded(tmp_path):
    db = _open_upgraded(tmp_path)
    yield db
    db.close()


@pytest.mark.integration
def test_v0_database_upgrades_with_every_row_kept_and_owned(upgraded) -> None:
    db = upgraded
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert db.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []

    for table, count in _legacy_counts().items():
        assert db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count, table
        cols = {r[1] for r in db.conn.execute(f"PRAGMA table_info({table})")}
        if "athlete_id" in cols:
            stray = db.conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE athlete_id IS NOT 'owner'"
            ).fetchone()[0]
            assert stray == 0, f"{table}: {stray} legacy rows not scoped to the owner"


@pytest.mark.integration
def test_upgraded_history_reads_back_through_the_public_api(upgraded) -> None:
    db = upgraded
    assert len(db.get_training_load_history(days=10_000)) == 48
    assert len(db.get_hrv_history(days=10_000)) == 56
    assert db.get_pr(5.0) == (1140, "2026-01-24", "Parkrun")
    shoes = {name: round(km, 1) for _id, name, km, *_rest in db.get_active_shoes()}
    assert shoes == {"Pegasus 40": 506.2, "Vaporfly 3": 52.8}
    manual = db.conn.execute(
        "SELECT COUNT(*) FROM training_log WHERE garmin_activity_id IS NULL"
    ).fetchone()[0]
    assert manual == 4  # manually logged runs survive the v8 NOT NULL migration


@pytest.mark.integration
def test_upgraded_database_accepts_new_writes_and_reopens(tmp_path) -> None:
    db = _open_upgraded(tmp_path)
    db.save_session(
        date="2026-03-02", session_type="EASY", distance_km=8.0, duration_sec=2640,
        avg_hr=138, rpe=3, training_load=40, garmin_activity_id="g-new",
    )
    db.close()

    again = DatabaseManager(db_dir=tmp_path)
    try:
        assert again.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert len(again.get_training_load_history(days=10_000)) == 49
    finally:
        again.close()


@pytest.mark.integration
def test_upgraded_schema_matches_a_fresh_install(upgraded, tmp_path) -> None:
    fresh = DatabaseManager(db_dir=tmp_path / "fresh")
    try:
        want, got = _columns(fresh), _columns(upgraded)
    finally:
        fresh.close()

    assert set(got) == set(want), {"only_fresh": set(want) - set(got), "only_upgraded": set(got) - set(want)}
    drift = {key for key in want if want[key] != got[key]}
    assert drift == _KNOWN_DRIFT, {key: (want[key], got[key]) for key in drift ^ _KNOWN_DRIFT}
