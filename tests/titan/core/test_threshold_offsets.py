"""ADR-0052 Stage 1 tests — athlete_threshold_offsets schema and write guard.

Tests cover:
  1. Table created by create_tables()
  2. save_threshold_offset() roundtrip — all fields persisted correctly
  3. UPSERT semantics — second write with same key wins, only 1 row
  4. H1–H5 exclusion — hard-stop keys raise ValueError
  5. Invalid source → DB CHECK constraint raises
  6. Confidence out of range → DB CHECK constraint raises
  7. Alembic upgrade + downgrade
  8. SCHEMA_VERSION incremented to 12
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from titan.config.thresholds import HARD_STOP_THRESHOLD_KEYS
from titan.core.database import SCHEMA_VERSION, DatabaseManager

# ── helpers ──────────────────────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _all_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    cur = conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


# ── Test 1 ────────────────────────────────────────────────────────────────────

def test_athlete_threshold_offsets_table_created(tmp_path: Path) -> None:
    """create_tables() must create athlete_threshold_offsets in sqlite_master."""
    db = DatabaseManager(db_name="schema_test.db", db_dir=tmp_path)
    try:
        exists = _table_exists(db.conn, "athlete_threshold_offsets")
    finally:
        db.close()
    assert exists, "athlete_threshold_offsets table was not created by create_tables()"


# ── Test 2 ────────────────────────────────────────────────────────────────────

def test_save_threshold_offset_roundtrip(tmp_path: Path) -> None:
    """All fields are stored and can be retrieved exactly."""
    db = DatabaseManager(db_name="roundtrip.db", db_dir=tmp_path)
    try:
        db.save_threshold_offset(
            athlete_id="athlete_42",
            threshold_key="ACWR_SWEET_SPOT_MAX",
            delta_value=-0.05,
            source="manual",
            confidence=0.75,
            updated_at="2026-04-12T08:00:00Z",
        )
        rows = _all_rows(db.conn, "athlete_threshold_offsets")
    finally:
        db.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["athlete_id"] == "athlete_42"
    assert row["threshold_key"] == "ACWR_SWEET_SPOT_MAX"
    assert row["delta_value"] == pytest.approx(-0.05)
    assert row["source"] == "manual"
    assert row["confidence"] == pytest.approx(0.75)
    assert row["updated_at"] == "2026-04-12T08:00:00Z"


# ── Test 3 ────────────────────────────────────────────────────────────────────

def test_save_threshold_offset_upsert(tmp_path: Path) -> None:
    """Second write on same (athlete_id, threshold_key) replaces first — 1 row, new value."""
    db = DatabaseManager(db_name="upsert.db", db_dir=tmp_path)
    try:
        db.save_threshold_offset(
            athlete_id="athlete_1",
            threshold_key="VO2_READINESS_MIN",
            delta_value=2.0,
            source="calibration",
            confidence=0.60,
            updated_at="2026-04-12T06:00:00Z",
        )
        db.save_threshold_offset(
            athlete_id="athlete_1",
            threshold_key="VO2_READINESS_MIN",
            delta_value=-3.5,
            source="manual",
            confidence=0.85,
            updated_at="2026-04-12T10:00:00Z",
        )
        rows = _all_rows(db.conn, "athlete_threshold_offsets")
    finally:
        db.close()

    assert len(rows) == 1, "UPSERT must produce exactly 1 row, not 2"
    row = rows[0]
    assert row["delta_value"] == pytest.approx(-3.5), "Second write delta_value must win"
    assert row["source"] == "manual"
    assert row["confidence"] == pytest.approx(0.85)
    assert row["updated_at"] == "2026-04-12T10:00:00Z"


# ── Test 4 ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hard_stop_key", sorted(HARD_STOP_THRESHOLD_KEYS))
def test_save_threshold_offset_rejects_hard_stop_keys(tmp_path: Path, hard_stop_key: str) -> None:
    """Every key in HARD_STOP_THRESHOLD_KEYS must raise ValueError (ADR-0052)."""
    db = DatabaseManager(db_name=f"reject_{hard_stop_key[:20]}.db", db_dir=tmp_path)
    try:
        with pytest.raises(ValueError, match="hard-stop gate"):
            db.save_threshold_offset(
                athlete_id="athlete_x",
                threshold_key=hard_stop_key,
                delta_value=1.0,
                source="manual",
                confidence=0.5,
                updated_at="2026-04-12T00:00:00Z",
            )
    finally:
        db.close()


# ── Test 5 ────────────────────────────────────────────────────────────────────

def test_save_threshold_offset_rejects_invalid_source(tmp_path: Path) -> None:
    """source='invalid' must be rejected by the DB CHECK constraint."""
    db = DatabaseManager(db_name="bad_source.db", db_dir=tmp_path)
    try:
        with pytest.raises((sqlite3.IntegrityError, Exception)):
            db.save_threshold_offset(
                athlete_id="athlete_y",
                threshold_key="VO2_ACWR_MAX",
                delta_value=0.1,
                source="invalid",
                confidence=0.5,
                updated_at="2026-04-12T00:00:00Z",
            )
    finally:
        db.close()


# ── Test 6 ────────────────────────────────────────────────────────────────────

def test_save_threshold_offset_rejects_confidence_out_of_range(tmp_path: Path) -> None:
    """confidence=1.5 must be rejected by the DB CHECK constraint (> 1.0)."""
    db = DatabaseManager(db_name="bad_confidence.db", db_dir=tmp_path)
    try:
        with pytest.raises((sqlite3.IntegrityError, Exception)):
            db.save_threshold_offset(
                athlete_id="athlete_z",
                threshold_key="VO2_ACWR_MAX",
                delta_value=0.1,
                source="manual",
                confidence=1.5,
                updated_at="2026-04-12T00:00:00Z",
            )
    finally:
        db.close()


# ── Test 7 ────────────────────────────────────────────────────────────────────

def test_alembic_migration_upgrade_downgrade(tmp_path: Path) -> None:
    """Alembic upgrade to head creates athlete_threshold_offsets; downgrade one step removes it."""
    from alembic.config import Config

    from alembic import command

    db_path = tmp_path / "alembic_migration_test.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    # Upgrade to head — table must exist
    command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as conn:
        assert _table_exists(conn, "athlete_threshold_offsets"), (
            "athlete_threshold_offsets must exist after upgrade to head"
        )

    # Downgrade one step (back to 20260410_01) — table must be gone
    command.downgrade(cfg, "20260410_01")
    with sqlite3.connect(db_path) as conn:
        assert not _table_exists(conn, "athlete_threshold_offsets"), (
            "athlete_threshold_offsets must be absent after downgrade past 20260412_01"
        )


# ── Test 8 ────────────────────────────────────────────────────────────────────

def test_schema_version_incremented(tmp_path: Path) -> None:
    """Fresh DB must carry SCHEMA_VERSION == 12 in PRAGMA user_version."""
    assert SCHEMA_VERSION == 12, (
        f"Expected SCHEMA_VERSION=12 in database.py, got {SCHEMA_VERSION}"
    )
    db = DatabaseManager(db_name="version_check.db", db_dir=tmp_path)
    try:
        version = db.conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        db.close()
    assert version == 12, (
        f"PRAGMA user_version must be 12 after create_tables(), got {version}"
    )
