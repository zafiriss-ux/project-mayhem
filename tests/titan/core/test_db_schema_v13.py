"""SCHEMA_VERSION 13 contract tests — T5-07-L3-A + T5-74.

Verifies the six acceptance criteria for the v13 schema migration:
  1. athletes table exists + owner row seeded correctly.
  2. governance_outcomes.athlete_id column present.
  3. save_governance_decision() persists athlete_id explicitly (not via DEFAULT).
  4. model_calibration_metadata.calibrated_for absent; athlete_id present.
  5. PRAGMA user_version == 13.
  6. Migration idempotency: create_tables() is safe to call on an existing DB.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    instance = DatabaseManager(db_name="v13_contract.db", db_dir=tmp_path)
    yield instance
    instance.close()


# ── Test 1 ────────────────────────────────────────────────────────────────────


def test_athletes_table_seeded_with_owner(db: DatabaseManager) -> None:
    """After create_tables(), athletes must contain exactly one owner row
    with is_cold_start=0 and cold_start_sessions_count=30 (ADR-0033 L3-C)."""
    cursor = db.conn.cursor()
    row = cursor.execute(
        "SELECT athlete_id, display_name, is_cold_start, cold_start_sessions_count "
        "FROM athletes WHERE athlete_id = 'owner'"
    ).fetchone()
    assert row is not None, "owner row must be seeded in athletes table"
    athlete_id, display_name, is_cold_start, cold_start_sessions_count = row
    assert athlete_id == "owner"
    assert display_name == "Owner"
    assert is_cold_start == 0, "owner bypasses cold-start (ADR-0033 L3-C)"
    assert cold_start_sessions_count == 30


# ── Test 2 ────────────────────────────────────────────────────────────────────


def test_governance_outcomes_has_athlete_id_column(db: DatabaseManager) -> None:
    """governance_outcomes must contain athlete_id column (T5-74)."""
    cols = {
        row[1]
        for row in db.conn.execute(
            "PRAGMA table_info(governance_outcomes)"
        ).fetchall()
    }
    assert "athlete_id" in cols, "governance_outcomes must have athlete_id column"


# ── Test 3 ────────────────────────────────────────────────────────────────────


def test_save_governance_decision_persists_athlete_id(
    db: DatabaseManager,
) -> None:
    """save_governance_decision() must write athlete_profile_id explicitly to
    athlete_id column — value must be 'owner', NOT the schema DEFAULT."""
    db.save_governance_decision({
        "date": "2026-04-14",
        "session_planned": "EASY",
        "session_post_governance": "EASY",
        "athlete_profile_id": "owner",
    })
    row = db.conn.execute(
        "SELECT athlete_id FROM governance_outcomes WHERE date = ?",
        ("2026-04-14",),
    ).fetchone()
    assert row is not None, "governance decision must be persisted"
    assert row[0] == "owner", (
        f"athlete_id must be 'owner' (explicit insert), got {row[0]!r}"
    )


def test_save_governance_decision_defaults_to_owner_when_key_absent(
    db: DatabaseManager,
) -> None:
    """save_governance_decision() must default athlete_id to 'owner' when
    athlete_profile_id key is absent from the decision dict."""
    db.save_governance_decision({
        "date": "2026-04-14",
        "session_planned": "REST",
        "session_post_governance": "REST",
    })
    row = db.conn.execute(
        "SELECT athlete_id FROM governance_outcomes WHERE date = ?",
        ("2026-04-14",),
    ).fetchone()
    assert row is not None
    assert row[0] == "owner", (
        f"Default fallback must be 'owner', got {row[0]!r}"
    )


# ── Test 4 ────────────────────────────────────────────────────────────────────


def test_model_calibration_metadata_calibrated_for_absent(
    db: DatabaseManager,
) -> None:
    """model_calibration_metadata must NOT contain calibrated_for after v13
    and MUST contain athlete_id (renamed column — T5-07-L3-A)."""
    cols = {
        row[1]
        for row in db.conn.execute(
            "PRAGMA table_info(model_calibration_metadata)"
        ).fetchall()
    }
    assert "athlete_id" in cols, (
        "athlete_id must be present in model_calibration_metadata"
    )
    assert "calibrated_for" not in cols, (
        "calibrated_for must be absent from model_calibration_metadata after v13"
    )


# ── Test 5 ────────────────────────────────────────────────────────────────────


def test_schema_version_is_thirteen(db: DatabaseManager) -> None:
    """PRAGMA user_version must equal 20 (SCHEMA_VERSION) after create_tables()."""
    assert SCHEMA_VERSION == 20, (
        f"SCHEMA_VERSION constant must be 20, got {SCHEMA_VERSION}"
    )
    version = db.conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 20, (
        f"PRAGMA user_version must be 20 after create_tables(), got {version}"
    )


# ── Test 6 ────────────────────────────────────────────────────────────────────


def test_v13_migration_idempotent_on_existing_db(tmp_path: Path) -> None:
    """create_tables() is idempotent: calling it twice on the same DB must not
    raise and must preserve the athletes owner row (CREATE ... IF NOT EXISTS +
    INSERT OR IGNORE guard)."""
    db_path = tmp_path / "idempotent.db"
    db1 = DatabaseManager(db_name=db_path.name, db_dir=tmp_path)
    db1.close()

    # Second open triggers create_tables() + _run_migrations() again.
    db2 = DatabaseManager(db_name=db_path.name, db_dir=tmp_path)
    try:
        rows = db2.conn.execute(
            "SELECT COUNT(*) FROM athletes WHERE athlete_id = 'owner'"
        ).fetchone()
        assert rows[0] == 1, "owner row must exist exactly once after idempotent open"
        version = db2.conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 20
    finally:
        db2.close()


def test_v13_migration_upgrades_pre_v13_database(tmp_path: Path) -> None:
    """Opening a DB with user_version=12 must trigger the v13 migration and
    result in the athletes table + backfill of governance_outcomes.athlete_id."""
    db_path = tmp_path / "pre_v13.db"

    # Simulate a v12 database: governance_outcomes present with athlete_id='default'.
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE governance_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'default',
                date TEXT NOT NULL,
                session_planned TEXT NOT NULL,
                session_post_governance TEXT NOT NULL,
                locks_applied_json TEXT NOT NULL DEFAULT '[]',
                governance_clean INTEGER NOT NULL DEFAULT 0,
                phase TEXT NOT NULL DEFAULT '',
                vlg_color TEXT NOT NULL DEFAULT '',
                apl_priority_vector_json TEXT NOT NULL DEFAULT '{}',
                lock_thresholds_active_json TEXT NOT NULL DEFAULT '{}',
                acwr REAL NOT NULL DEFAULT 0.0,
                tsb_value REAL NOT NULL DEFAULT 0.0,
                readiness_score REAL NOT NULL DEFAULT 0.0,
                glycogen_debt REAL NOT NULL DEFAULT 0.0,
                afi_value REAL,
                decision_was_followed INTEGER NOT NULL DEFAULT 1,
                override_outcome_exclusion INTEGER NOT NULL DEFAULT 0,
                outcome_independence_ok INTEGER NOT NULL DEFAULT 1,
                algorithm_version_snapshot TEXT
            )
        """)
        conn.execute("""
            INSERT INTO governance_outcomes
                (date, session_planned, session_post_governance, athlete_id)
            VALUES ('2026-01-01', 'EASY', 'EASY', 'default')
        """)
        conn.execute("PRAGMA user_version = 12")

    # Opening via DatabaseManager must run v13 migration.
    db = DatabaseManager(db_name=db_path.name, db_dir=tmp_path)
    try:
        # athletes table created + owner seeded
        owner = db.conn.execute(
            "SELECT athlete_id FROM athletes WHERE athlete_id = 'owner'"
        ).fetchone()
        assert owner is not None, "v13 migration must create athletes table with owner"

        # governance_outcomes backfill: 'default' → 'owner'
        row = db.conn.execute(
            "SELECT athlete_id FROM governance_outcomes WHERE date = '2026-01-01'"
        ).fetchone()
        assert row is not None
        assert row[0] == "owner", (
            f"v13 migration must backfill 'default' → 'owner', got {row[0]!r}"
        )

        version = db.conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 20
    finally:
        db.close()
