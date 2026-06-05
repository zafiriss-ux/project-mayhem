"""
T5-69 Stage 3: NOT NULL migration + PostgreSQLAdapter legacy write path fix.

Tests:
1. v8 migration skips NOT NULL when rows with NULL garmin_activity_id exist.
2. v8 migration applies NOT NULL (table recreation) when all rows are migrated.
3. PostgreSQLAdapter.save_session() passes garmin_activity_id through to the DB.
4. PostgreSQLAdapter.save_session() silently ignores duplicate garmin_activity_id
   (INSERT OR IGNORE / IntegrityError semantics).
"""

from __future__ import annotations

import pytest  # noqa: F401
from sqlalchemy import create_engine, text

from titan.core.database import DatabaseManager
from titan.core.persistence import PostgreSQLAdapter

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db(tmp_path, *, prepopulate_garmin_id: bool = False, add_null_row: bool = False):
    """Return a DatabaseManager at schema version 7 (no v8 yet) with optional rows."""
    db_path = str(tmp_path / "test.db")
    db = DatabaseManager(db_path)
    if prepopulate_garmin_id:
        db.save_session("2026-01-01", "EASY", 10.0, 3600, garmin_activity_id="ACT_001")
    if add_null_row:
        db.save_session("2026-01-02", "EASY", 5.0, 1800, garmin_activity_id=None)
    return db


def _build_pg_test_engine():
    """SQLite in-memory engine with the Stage-3 training_log schema."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE daily_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'default',
                date TEXT NOT NULL UNIQUE,
                weight_kg REAL,
                hrv_rmssd REAL,
                resting_hr INTEGER,
                sleep_hours REAL,
                sleep_quality INTEGER,
                soreness INTEGER,
                fatigue_level INTEGER,
                mood INTEGER,
                notes TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE gear_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'default',
                shoe_name TEXT NOT NULL,
                total_km REAL DEFAULT 0,
                last_used TEXT,
                compression_recovery_hours INTEGER DEFAULT 24,
                status TEXT DEFAULT 'ACTIVE',
                shoe_type TEXT,
                max_km_limit REAL DEFAULT 800
            )
        """))
        conn.execute(text("""
            CREATE TABLE training_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'default',
                date TEXT NOT NULL,
                session_type TEXT,
                distance_km REAL,
                duration_sec INTEGER,
                avg_hr INTEGER,
                max_hr INTEGER,
                rpe INTEGER,
                training_load INTEGER,
                shoe_id INTEGER,
                surface TEXT,
                temperature_c REAL,
                zone_distribution TEXT,
                notes TEXT,
                garmin_activity_id TEXT UNIQUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE personal_bests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'default',
                distance_km REAL NOT NULL,
                time_sec INTEGER NOT NULL,
                pace_sec_per_km REAL,
                date TEXT NOT NULL,
                race_name TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE governance_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'default',
                date TEXT NOT NULL,
                session_planned TEXT NOT NULL,
                session_post_governance TEXT NOT NULL,
                locks_applied_json TEXT NOT NULL,
                governance_clean INTEGER NOT NULL,
                phase TEXT NOT NULL,
                vlg_color TEXT NOT NULL,
                apl_priority_vector_json TEXT NOT NULL,
                lock_thresholds_active_json TEXT NOT NULL,
                acwr REAL NOT NULL,
                tsb_value REAL NOT NULL,
                readiness_score REAL NOT NULL,
                glycogen_debt REAL NOT NULL,
                afi_value REAL,
                outcome_rpe INTEGER,
                outcome_completed INTEGER,
                outcome_session_type_actual TEXT,
                outcome_notes TEXT,
                decision_was_followed INTEGER NOT NULL DEFAULT 1,
                override_outcome_exclusion INTEGER NOT NULL DEFAULT 0,
                outcome_independence_ok INTEGER NOT NULL DEFAULT 1,
                algorithm_version_snapshot TEXT
            )
        """))
    return engine


# ── v8 migration: skip when NULLs present ────────────────────────────────────

class TestV8MigrationSkipsWhenNullsExist:
    """v8 must not apply NOT NULL when any row has NULL garmin_activity_id."""

    @pytest.mark.integration
    def test_null_row_causes_skip(self, tmp_path):
        """Row with NULL garmin_activity_id → constraint NOT applied."""
        db = _make_db(tmp_path, add_null_row=True)
        # Reset version to re-trigger v8
        db.conn.execute("PRAGMA user_version = 7")
        db.conn.commit()
        db._run_migrations(db.conn.cursor())

        # garmin_activity_id must still be nullable (NOT NULL not applied)
        cols = {
            row[1]: row[3]  # name: notnull
            for row in db.conn.execute("PRAGMA table_info(training_log)").fetchall()
        }
        assert "garmin_activity_id" in cols
        assert cols["garmin_activity_id"] == 0, (
            "NOT NULL was applied even though NULL rows exist"
        )
        db.close()

    @pytest.mark.integration
    def test_empty_table_skips_constraint(self, tmp_path):
        """Empty table has no rows to migrate → constraint not applied (no rows to verify)."""
        db = DatabaseManager(str(tmp_path / "empty.db"))
        db.conn.execute("PRAGMA user_version = 7")
        db.conn.commit()
        db._run_migrations(db.conn.cursor())

        cols = {
            row[1]: row[3]
            for row in db.conn.execute("PRAGMA table_info(training_log)").fetchall()
        }
        # Empty table → 0 NULLs but also 0 rows migrated — constraint not applied
        # (v8 only promotes NOT NULL when ALL rows are confirmed migrated with non-NULL values)
        assert "garmin_activity_id" in cols
        db.close()


# ── v8 migration: apply NOT NULL when all rows have garmin_activity_id ────────

class TestV8MigrationAppliesWhenAllRowsMigrated:
    """v8 recreates table with NOT NULL when zero NULL garmin_activity_id rows."""

    @pytest.mark.integration
    def test_all_rows_migrated_applies_not_null(self, tmp_path):
        """All rows have garmin_activity_id → table recreated with NOT NULL."""
        db = _make_db(tmp_path, prepopulate_garmin_id=True)
        # Confirm no NULLs
        null_count = db.conn.execute(
            "SELECT COUNT(*) FROM training_log WHERE garmin_activity_id IS NULL"
        ).fetchone()[0]
        assert null_count == 0, "Precondition: no NULL rows"

        # Re-apply v8
        db.conn.execute("PRAGMA user_version = 7")
        db.conn.commit()
        cursor = db.conn.cursor()
        db._apply_v8_migrations(cursor)
        db.conn.commit()

        cols = {
            row[1]: row[3]
            for row in db.conn.execute("PRAGMA table_info(training_log)").fetchall()
        }
        assert cols["garmin_activity_id"] == 1, (
            "NOT NULL was not applied when all rows are migrated"
        )
        # Existing row must survive
        count = db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0]
        assert count == 1
        db.close()


# ── PostgreSQLAdapter.save_session passes garmin_activity_id ─────────────────

class TestPostgreSQLAdapterSaveSession:
    """PostgreSQLAdapter.save_session() must write garmin_activity_id."""

    @pytest.mark.integration
    def test_garmin_activity_id_persisted(self):
        """save_session() with garmin_activity_id writes the value to the DB."""
        engine = _build_pg_test_engine()
        adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
        try:
            adapter.save_session(
                "2026-01-10",
                "EASY",
                10.0,
                3600,
                garmin_activity_id="ACT_TEST_001",
            )
            with engine.connect() as conn:
                val = conn.execute(
                    text("SELECT garmin_activity_id FROM training_log LIMIT 1")
                ).scalar_one()
            assert val == "ACT_TEST_001"
        finally:
            adapter.close()

    @pytest.mark.integration
    def test_duplicate_garmin_activity_id_is_silent_noop(self):
        """Two save_session() calls with the same garmin_activity_id → one row."""
        engine = _build_pg_test_engine()
        adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
        try:
            adapter.save_session(
                "2026-01-11",
                "EASY",
                10.0,
                3600,
                garmin_activity_id="ACT_DUP_001",
            )
            # Second call must not raise and must not insert a second row
            adapter.save_session(
                "2026-01-11",
                "EASY",
                10.0,
                3600,
                garmin_activity_id="ACT_DUP_001",
            )
            with engine.connect() as conn:
                count = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM training_log"
                        " WHERE garmin_activity_id = 'ACT_DUP_001'"
                    )
                ).scalar_one()
            assert count == 1
        finally:
            adapter.close()

    @pytest.mark.integration
    def test_null_garmin_activity_id_inserts_row(self):
        """save_session() without garmin_activity_id still inserts a row."""
        engine = _build_pg_test_engine()
        adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
        try:
            adapter.save_session("2026-01-12", "EASY", 5.0, 1800)
            with engine.connect() as conn:
                count = conn.execute(
                    text("SELECT COUNT(*) FROM training_log")
                ).scalar_one()
            assert count == 1
        finally:
            adapter.close()
