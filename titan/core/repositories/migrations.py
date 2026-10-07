"""Schema migrations: additive steps v1–v25 guarded by ``PRAGMA user_version``.

``SCHEMA_VERSION`` stays in ``titan.core.database``; base tables come from
``titan.core.schema``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

# Same logger as titan.core.database: migration log records keep their source name.
_log = logging.getLogger("titan.core.database")


class SchemaMigrations:
    """Migration steps, run on the owning DatabaseManager's cursor."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def _run_migrations(self, cursor) -> None:
        """Apply additive schema migrations guarded by PRAGMA user_version.

        Each migration is keyed by the target version it introduces. Only
        migrations with version > current user_version are applied.
        After all pending migrations run, user_version is updated to
        SCHEMA_VERSION. This replaces the old OperationalError-suppression
        approach with a deterministic version gate (T1-16).
        """
        current_version: int = cursor.execute("PRAGMA user_version").fetchone()[0]

        # deferred: titan.core.database imports this module
        from titan.core.database import SCHEMA_VERSION

        # INV-25: an older binary must never silently open a newer DB.
        # If the DB was written by a newer SCHEMA_VERSION, refuse — forward
        # migrations are not guaranteed reversible.
        if current_version > SCHEMA_VERSION:
            logging.getLogger('titan.database').critical(json.dumps({
                "flow": "database", "action": "schema_version_forward_guard",
                "invariant": "INV-25",
                "db_user_version": current_version,
                "binary_schema_version": SCHEMA_VERSION,
                "outcome": "REFUSED_TO_OPEN",
            }, default=str))
            raise RuntimeError(
                f"Database user_version ({current_version}) is newer than this "
                f"binary's SCHEMA_VERSION ({SCHEMA_VERSION}). An older binary "
                f"cannot safely open a newer database. Upgrade the binary."
            )

        # Ordered dict: version → (table, column_label, sql).
        # To add a future migration: increment SCHEMA_VERSION and add an entry.
        _migrations: dict[int, tuple[str, str, str]] = {
            1: (
                "daily_metrics / training_log",
                "hrr_60, hrr_120, glycogen_debt, garmin_activity_id",
                None,  # batch — see _apply_v1_migrations() below
            ),
            2: (
                "training_log",
                "idx_training_log_garmin_id (unique index)",
                None,  # DDL — see _apply_v2_migrations() below
            ),
            3: (
                "daily_metrics / training_log",
                "quality_flag (data sanity layer — ADR-0026 / T1-19)",
                None,  # batch — see _apply_v3_migrations() below
            ),
            4: (
                "sync_metadata",
                "Garmin sync outcome ledger (T1-20)",
                None,  # DDL — see _apply_v4_migrations() below
            ),
            5: (
                "governance_outcomes",
                "feedback-loop guardrail metadata columns (T1-22)",
                None,  # batch — see _apply_v5_migrations() below
            ),
            7: (
                "model_calibration_metadata",
                "calibration metadata ledger for model age and drift checks (T5-07 layer 1)",
                None,  # DDL — see _apply_v7_migrations() below
            ),
            8: (
                "training_log",
                "conditional NOT NULL on garmin_activity_id (T5-69 Stage 3)",
                None,  # conditional DDL — see _apply_v8_migrations() below
            ),
            9: (
                "degraded_mode_state",
                "DegradedModeTracker persistence table (HD-06 / OBS-039)",
                None,  # DDL — see _apply_v9_migrations() below
            ),
            10: (
                "auth_users / auth_tokens",
                "AuthStore SQLite persistence tables (HD-04 / T5-70 / ADR-0048)",
                None,  # DDL — see _apply_v10_migrations() below
            ),
            11: (
                "governance_outcomes",
                "athlete_id column for multi-athlete support (T5-74 / ADR-0033)",
                None,  # DDL — see _apply_v11_migrations() below
            ),
            12: (
                "athlete_threshold_offsets",
                "per-athlete threshold offset table (HD-09 / ADR-0052 Stage 1)",
                None,  # DDL — see _apply_v12_migrations() below
            ),
            13: (
                "athletes / governance_outcomes / model_calibration_metadata",
                "athletes canonical table + owner seed + governance_outcomes owner backfill "
                "+ drop calibrated_for (T5-07-L3-A / T5-74 / ADR-0033)",
                None,  # DDL — see _apply_v13_migrations() below
            ),
            14: (
                "daily_metrics / training_log",
                "athlete_id column for read-path isolation (T5-07-L3-D / ADR-0033-L3-D-RESOLVED)",
                None,  # DDL — see _apply_v14_migrations() below
            ),
            15: (
                "daily_metrics",
                "data_source column for input provenance tagging (T5-115)",
                None,  # DDL — see _apply_v15_migrations() below
            ),
            16: (
                "coach_athlete_assignments",
                "coach-athlete RBAC scoping table + system→owner seed (ADR-0054 / T5-110)",
                None,  # DDL — see _apply_v16_migrations() below
            ),
            17: (
                "coach_audit_log",
                "persistent coach action audit log (T5-111)",
                None,  # DDL — see _apply_v17_migrations() below
            ),
            18: (
                "training_log",
                "backfill athlete_id='default'→'owner' (v8 migration DEFAULT mismatch fix)",
                None,  # DML — see _apply_v18_migrations() below
            ),
            19: (
                "training_log",
                "avg_pace_sec_per_km column for pace storage and display",
                None,  # DDL — see _apply_v19_migrations() below
            ),
            20: (
                "athletes",
                "biological_sex, menstrual_tracking columns for sex-aware energy calculations",
                None,  # DDL — see _apply_v20_migrations() below
            ),
            21: (
                "nutrition_preferences",
                "Nutrition personalization preferences per athlete (ADR-0056)",
                None,  # DDL — see _apply_v21_migrations() below
            ),
            22: (
                "login_lockout",
                "SQLite-backed auth lockout table (TD-SEC-02)",
                None,  # DDL — see _apply_v22_migrations() below
            ),
            23: (
                "consent_log",
                "GDPR consent audit table — SQLite reconciliation of Alembic d9 (TD-08 Step 5 / F3.4)",
                None,  # DDL — see _apply_v23_migrations() below
            ),
            24: (
                "daily_metrics / personal_bests / gear_usage",
                "multi-athlete schema isolation: daily_metrics unique(athlete_id,date) "
                "rebuild; personal_bests + gear_usage athlete_id columns (P27-B1 / ADR-0033)",
                None,  # DDL — see _apply_v24_migrations() below
            ),
            25: (
                "cohort_calibration_signals",
                "cohort calibration signal table for CohortProfile scaffolding (P27-01)",
                None,  # DDL — see _apply_v25_migrations() below
            ),
        }

        if current_version < 1:
            self._db._apply_v1_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 1,
                    "columns_added": "hrr_60, hrr_120, glycogen_debt, garmin_activity_id",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 2:
            self._db._apply_v2_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 2,
                    "index_created": "idx_training_log_garmin_id",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 3:
            self._db._apply_v3_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 3,
                    "columns_added": "quality_flag (daily_metrics, training_log)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 4:
            self._db._apply_v4_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 4,
                    "table_created": "sync_metadata",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 5:
            self._db._apply_v5_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 5,
                    "columns_added": (
                        "decision_was_followed, override_outcome_exclusion, "
                        "outcome_independence_ok, algorithm_version_snapshot"
                    ),
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        # ADR-0058-NOTE: v6 (override_signals) is intentionally invoked outside
        # _migrations dict because the dict skips key 6 (historical numbering gap).
        # Do NOT add key 6 to the dict without verifying idempotency.
        # See Opus audit 2026-05-25, finding #8.
        if current_version < 6:
            self._db._apply_v6_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 6,
                    "table_created": "override_signals",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 7:
            self._db._apply_v7_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 7,
                    "table_created": "model_calibration_metadata",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 8:
            self._db._apply_v8_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 8,
                    "note": "garmin_activity_id NOT NULL check (T5-69 Stage 3)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 9:
            self._db._apply_v9_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 9,
                    "table_created": "degraded_mode_state",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 10:
            self._db._apply_v10_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 10,
                    "tables_created": "auth_users, auth_tokens",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 11:
            self._db._apply_v11_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 11,
                    "columns_added": "governance_outcomes.athlete_id (T5-74)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 12:
            self._db._apply_v12_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 12,
                    "table_created": "athlete_threshold_offsets (HD-09 / ADR-0052 Stage 1)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 13:
            self._db._apply_v13_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 13,
                    "tables_created": "athletes (owner seed)",
                    "columns_backfilled": "governance_outcomes.athlete_id default→owner",
                    "columns_dropped": "model_calibration_metadata.calibrated_for (T5-07-L3-A)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
        if current_version < 14:
            self._db._apply_v14_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 14,
                    "columns_added": "daily_metrics.athlete_id, training_log.athlete_id "
                                     "(T5-07-L3-D / ADR-0033-L3-D-RESOLVED)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 15:
            self._db._apply_v15_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 15,
                    "columns_added": "daily_metrics.data_source (T5-115)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 16:
            self._db._apply_v16_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 16,
                    "table_created": "coach_athlete_assignments (ADR-0054 / T5-110)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 17:
            self._db._apply_v17_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 17,
                    "table_created": "coach_audit_log (T5-111)",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 18:
            self._db._apply_v18_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 18,
                    "rows_backfilled": "training_log athlete_id 'default'→'owner'",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 19:
            self._db._apply_v19_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 19,
                    "columns_added": "training_log.avg_pace_sec_per_km",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 20:
            self._db._apply_v20_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 20,
                    "columns_added": "athletes.biological_sex, athletes.menstrual_tracking",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 21:
            self._db._apply_v21_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 21,
                    "table_added": "nutrition_preferences",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 22:
            self._db._apply_v22_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 22,
                    "table_added": "login_lockout",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 23:
            self._db._apply_v23_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 23,
                    "table_added": "consent_log",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )

        if current_version < 24:
            self._db._apply_v24_migrations(cursor)
            _log.info(json.dumps({
                "flow": "database", "action": "db_schema_migration",
                "version": 24,
                "changes": "daily_metrics unique(athlete_id,date); personal_bests+gear_usage athlete_id",
                "timestamp": datetime.now(UTC).isoformat() + "Z",
            }))

        if current_version < 25:
            self._db._apply_v25_migrations(cursor)
            _log.info(json.dumps({
                "flow": "database", "action": "db_schema_migration",
                "version": 25,
                "table_created": "cohort_calibration_signals (P27-01)",
                "timestamp": datetime.now(UTC).isoformat() + "Z",
            }))

        self._db._apply_v19_pace_backfill(cursor)

        # Suppress unused-variable warning for _migrations (kept as documentation).
        _ = _migrations

        # PRAGMA does not support ? binding — version is a trusted internal constant
        cursor.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))
        self._db.conn.commit()

    def _apply_v1_migrations(self, cursor) -> None:
        """Version 1: additive column migrations for daily_metrics and training_log."""
        column_migrations = [
            ("daily_metrics", "hrr_60", "ALTER TABLE daily_metrics ADD COLUMN hrr_60 INTEGER"),
            ("daily_metrics", "hrr_120", "ALTER TABLE daily_metrics ADD COLUMN hrr_120 INTEGER"),
            ("daily_metrics", "glycogen_debt", "ALTER TABLE daily_metrics ADD COLUMN glycogen_debt REAL"),
            ("training_log", "garmin_activity_id", "ALTER TABLE training_log ADD COLUMN garmin_activity_id TEXT"),
        ]
        for table_name, column_name, sql in column_migrations:
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
                _log.info(
                    json.dumps({
                        "flow": "database",
                        "action": "db_migration_already_applied",
                        "table": table_name,
                        "column": column_name,
                    })
                )

    def _apply_v2_migrations(self, cursor) -> None:
        """Version 2: unique index on training_log.garmin_activity_id."""
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_training_log_garmin_id
                ON training_log(garmin_activity_id)
                WHERE garmin_activity_id IS NOT NULL
            """)
        except sqlite3.OperationalError as exc:
            if "already exists" not in str(exc).lower():
                raise

    def _apply_v3_migrations(self, cursor) -> None:
        """Version 3: quality_flag column on daily_metrics and training_log (ADR-0026)."""
        column_migrations = [
            ("daily_metrics", "quality_flag", "ALTER TABLE daily_metrics ADD COLUMN quality_flag TEXT"),
            ("training_log", "quality_flag", "ALTER TABLE training_log ADD COLUMN quality_flag TEXT"),
        ]
        for table_name, column_name, sql in column_migrations:
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
                _log.info(
                    json.dumps({
                        "flow": "database",
                        "action": "db_migration_already_applied",
                        "table": table_name,
                        "column": column_name,
                    })
                )

    def _apply_v4_migrations(self, cursor) -> None:
        """Version 4: Garmin sync outcome metadata table (T1-20)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_metadata (
                source TEXT PRIMARY KEY,
                last_attempt_ts TEXT,
                last_success_ts TEXT,
                last_sync_ok INTEGER NOT NULL DEFAULT 0,
                last_error_class TEXT
            )
        """)

    def _apply_v5_migrations(self, cursor) -> None:
        """Version 5: OutcomeTracker guardrail metadata columns (T1-22)."""
        column_migrations = [
            (
                "governance_outcomes",
                "decision_was_followed",
                "ALTER TABLE governance_outcomes ADD COLUMN decision_was_followed INTEGER NOT NULL DEFAULT 1",
            ),
            (
                "governance_outcomes",
                "override_outcome_exclusion",
                "ALTER TABLE governance_outcomes ADD COLUMN override_outcome_exclusion INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "governance_outcomes",
                "outcome_independence_ok",
                "ALTER TABLE governance_outcomes ADD COLUMN outcome_independence_ok INTEGER NOT NULL DEFAULT 1",
            ),
            (
                "governance_outcomes",
                "algorithm_version_snapshot",
                "ALTER TABLE governance_outcomes ADD COLUMN algorithm_version_snapshot TEXT",
            ),
        ]
        for table_name, column_name, sql in column_migrations:
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
                _log.info(
                    json.dumps({
                        "flow": "database",
                        "action": "db_migration_already_applied",
                        "table": table_name,
                        "column": column_name,
                    })
                )

    def _apply_v6_migrations(self, cursor) -> None:
        """Version 6: override_signals table for ADR-0042 override capture."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS override_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL,
                athlete_id TEXT NOT NULL,
                override_source TEXT NOT NULL,
                override_reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

    def _apply_v7_migrations(self, cursor) -> None:
        """Version 7: calibration metadata table (T5-07 Layer 1 scaffold)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_calibration_metadata (
                model_name TEXT NOT NULL,
                athlete_id TEXT NOT NULL DEFAULT 'default',
                calibrated_at TEXT NOT NULL,
                calibrated_for TEXT NOT NULL DEFAULT 'default',
                baseline_hrv_ms REAL,
                baseline_vo2 REAL,
                schema_version INTEGER NOT NULL,
                PRIMARY KEY (model_name, athlete_id)
            )
        """)

    def _apply_v8_migrations(self, cursor) -> None:
        """Version 8: conditional NOT NULL on training_log.garmin_activity_id (T5-69 Stage 3).

        Per §13.4 Stage 3: adds NOT NULL only when ALL existing rows are confirmed
        migrated (garmin_activity_id IS NOT NULL for every row) AND at least one row
        exists.  Manually-logged sessions are by design allowed to have NULL
        garmin_activity_id (they have no Garmin identity), so in practice this
        constraint is almost always skipped.
        """
        null_count = (
            cursor.execute(
                "SELECT COUNT(*) FROM training_log WHERE garmin_activity_id IS NULL"
            ).fetchone()[0]
        )
        total_count = (
            cursor.execute("SELECT COUNT(*) FROM training_log").fetchone()[0]
        )

        if null_count > 0 or total_count == 0:
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_migration_v8_not_null_skipped",
                    "reason": (
                        f"null_count={null_count}, total_count={total_count} — "
                        "NOT NULL constraint not applied "
                        "(manual sessions present, or no rows to confirm migration)"
                    ),
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                })
            )
            return

        # All rows have garmin_activity_id and at least one row exists.
        # Recreate table with NOT NULL + athlete_id column.
        # SQLite does not support ALTER COLUMN — use the standard rename approach.
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # FROZEN HISTORICAL SNAPSHOT — DO NOT MODIFY OR SYNC TO DESCRIPTOR
        # This column list is intentionally frozen at the v8-era schema state.
        # It must NOT include columns added in later migrations (e.g.
        # avg_pace_sec_per_km added in v19, quality_flag in v3).
        # Adding post-v8 columns here would insert NULL values for rows that
        # existed before those columns were added — silent data corruption.
        # Ref: TD-08-R3 (Opus pre-Phase-25 audit 2026-06-03), V7-03.
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        cursor.execute("""
            CREATE TABLE training_log_v8_new (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id         TEXT NOT NULL DEFAULT 'owner',
                date               TEXT NOT NULL,
                session_type       TEXT,
                distance_km        REAL,
                duration_sec       INTEGER,
                avg_hr             INTEGER,
                max_hr             INTEGER,
                rpe                INTEGER,
                training_load      INTEGER,
                shoe_id            INTEGER,
                surface            TEXT,
                temperature_c      REAL,
                zone_distribution  TEXT,
                notes              TEXT,
                garmin_activity_id TEXT NOT NULL,
                quality_flag       TEXT,
                FOREIGN KEY (shoe_id) REFERENCES gear_usage(id)
            )
        """)
        cursor.execute("""
            INSERT INTO training_log_v8_new
                (id, date, session_type, distance_km, duration_sec,
                 avg_hr, max_hr, rpe, training_load, shoe_id,
                 surface, temperature_c, zone_distribution, notes,
                 garmin_activity_id, quality_flag)
            SELECT id, date, session_type, distance_km, duration_sec,
                   avg_hr, max_hr, rpe, training_load, shoe_id,
                   surface, temperature_c, zone_distribution, notes,
                   garmin_activity_id, quality_flag
            FROM training_log
        """)
        cursor.execute("DROP TABLE training_log")
        cursor.execute("ALTER TABLE training_log_v8_new RENAME TO training_log")
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_training_log_garmin_id
                ON training_log(garmin_activity_id)
                WHERE garmin_activity_id IS NOT NULL
        """)
        _log.info(
            json.dumps({
                "flow": "database",
                "action": "db_migration_v8_not_null_applied",
                "detail": (
                    "training_log.garmin_activity_id promoted to NOT NULL; "
                    "athlete_id column added"
                ),
                "timestamp": datetime.now(UTC).isoformat() + "Z",
            })
        )

    def _apply_v9_migrations(self, cursor) -> None:
        """Version 9: degraded_mode_state table for DegradedModeTracker persistence (HD-06)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS degraded_mode_state (
                failure_type TEXT PRIMARY KEY,
                degraded_since TEXT NOT NULL,
                athlete_id TEXT NOT NULL DEFAULT 'default'
            )
        """)

    def _apply_v10_migrations(self, cursor) -> None:
        """Version 10: auth_users and auth_tokens tables (HD-04 / T5-70 / ADR-0048)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                athlete_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                athlete_id TEXT,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES auth_users(id)
            )
        """)

    def _apply_v11_migrations(self, cursor) -> None:
        """Version 11: athlete_id column on governance_outcomes (T5-74 / ADR-0033)."""
        try:
            cursor.execute(
                "ALTER TABLE governance_outcomes ADD COLUMN athlete_id TEXT NOT NULL DEFAULT 'default'"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_migration_already_applied",
                    "table": "governance_outcomes",
                    "column": "athlete_id",
                })
            )

    def _apply_v12_migrations(self, cursor) -> None:
        """Version 12: athlete_threshold_offsets table (HD-09 / ADR-0052 Stage 1)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS athlete_threshold_offsets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL,
                threshold_key TEXT NOT NULL,
                delta_value REAL NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL
                    CHECK (source IN ('manual', 'calibration')),
                confidence REAL NOT NULL
                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
                UNIQUE (athlete_id, threshold_key)
            )
        """)

    def _apply_v13_migrations(self, cursor) -> None:
        """Version 13: athletes canonical table + owner seed + governance backfill
        + drop calibrated_for (T5-07-L3-A / T5-74 / ADR-0033).

        Steps:
          1. CREATE TABLE IF NOT EXISTS athletes (owner seeded via INSERT OR IGNORE).
          2. Backfill governance_outcomes.athlete_id: rows with 'default' or
             'DEFAULT' become 'owner' (single-athlete installations).
          3. Drop the redundant calibrated_for column from model_calibration_metadata
             by recreating the table without it (SQLite RENAME COLUMN supported from
             3.25+, but DROP COLUMN requires 3.35+; table-recreation is safer).
        """
        # 1 ── athletes table (idempotent via IF NOT EXISTS + INSERT OR IGNORE)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS athletes (
                athlete_id                TEXT PRIMARY KEY,
                display_name              TEXT NOT NULL,
                created_at                TEXT NOT NULL,
                is_cold_start             INTEGER NOT NULL DEFAULT 1,
                cold_start_ends_at        TEXT,
                cold_start_sessions_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO athletes
                (athlete_id, display_name, created_at, is_cold_start,
                 cold_start_ends_at, cold_start_sessions_count)
            VALUES
                ('owner', 'Owner', datetime('now'), 0,
                 datetime('now'), 30)
        """)

        # 2 ── Backfill governance_outcomes.athlete_id 'default'/'DEFAULT' → 'owner'
        cursor.execute("""
            UPDATE governance_outcomes
               SET athlete_id = 'owner'
             WHERE athlete_id IN ('default', 'DEFAULT')
        """)

        # 3 ── Drop calibrated_for from model_calibration_metadata
        #      Only act if the table and the column both exist.
        mcm_tables = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='model_calibration_metadata'"
        ).fetchone()
        if mcm_tables is None:
            return  # table not yet created (fresh DB running all migrations)

        mcm_cols = [
            row[1]
            for row in cursor.execute(
                "PRAGMA table_info(model_calibration_metadata)"
            ).fetchall()
        ]
        if "calibrated_for" not in mcm_cols:
            return  # already dropped or never added

        # Recreate without calibrated_for (safe for all SQLite versions).
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # FROZEN HISTORICAL SNAPSHOT — DO NOT MODIFY OR SYNC TO DESCRIPTOR
        # This column list is intentionally frozen at the v13-era schema state.
        # It must NOT include columns added in later migrations.
        # Ref: TD-08-R3 (Opus pre-Phase-25 audit 2026-06-03), V7-03.
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        cursor.execute("""
            CREATE TABLE model_calibration_metadata_v13 (
                model_name      TEXT NOT NULL,
                athlete_id      TEXT NOT NULL DEFAULT 'owner',
                calibrated_at   TEXT NOT NULL,
                baseline_hrv_ms REAL,
                baseline_vo2    REAL,
                schema_version  INTEGER NOT NULL,
                PRIMARY KEY (model_name, athlete_id)
            )
        """)
        cursor.execute("""
            INSERT INTO model_calibration_metadata_v13
                (model_name, athlete_id, calibrated_at,
                 baseline_hrv_ms, baseline_vo2, schema_version)
            SELECT model_name, athlete_id, calibrated_at,
                   baseline_hrv_ms, baseline_vo2, schema_version
            FROM model_calibration_metadata
        """)
        cursor.execute("DROP TABLE model_calibration_metadata")
        cursor.execute(
            "ALTER TABLE model_calibration_metadata_v13 "
            "RENAME TO model_calibration_metadata"
        )

    def _apply_v14_migrations(self, cursor) -> None:
        """Version 14: athlete_id on daily_metrics and training_log (T5-07-L3-D / ADR-0033)."""
        for table in ("daily_metrics", "training_log"):
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN athlete_id TEXT NOT NULL DEFAULT 'owner'"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    def _apply_v15_migrations(self, cursor) -> None:
        """Version 15: data_source provenance column on daily_metrics (T5-115)."""
        try:
            cursor.execute(
                "ALTER TABLE daily_metrics ADD COLUMN "
                "data_source TEXT NOT NULL DEFAULT 'garmin_api'"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

    def _apply_v16_migrations(self, cursor) -> None:
        """Version 16: coach_athlete_assignments RBAC scoping table (ADR-0054 / T5-110)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coach_athlete_assignments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                coach_id    TEXT NOT NULL,
                athlete_id  TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                UNIQUE(coach_id, athlete_id)
            )
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO coach_athlete_assignments
                (coach_id, athlete_id, assigned_at)
            VALUES ('system', 'owner', datetime('now'))
        """)

    def _apply_v17_migrations(self, cursor) -> None:
        """Version 17: coach_audit_log persistent action history (T5-111)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coach_audit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                coach_id     TEXT NOT NULL,
                athlete_id   TEXT NOT NULL,
                action_type  TEXT NOT NULL,
                resource     TEXT NOT NULL DEFAULT '',
                action_detail TEXT,
                performed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    def _apply_v18_migrations(self, cursor) -> None:
        """Version 18: backfill training_log rows where athlete_id='default'→'owner'.

        The v8 migration erroneously created training_log_v8_new with
        DEFAULT 'default' instead of DEFAULT 'owner'. When v14 tried to add the
        athlete_id column it hit a duplicate-column error (silently swallowed),
        leaving the wrong default in place. All rows in affected databases have
        athlete_id='default', invisible to get_training_load_history() which
        queries athlete_id='owner'. This backfill corrects those rows.
        """
        cursor.execute(
            "UPDATE training_log SET athlete_id = 'owner' WHERE athlete_id = 'default'"
        )

    def _apply_v19_migrations(self, cursor) -> None:
        """Version 19: add avg_pace_sec_per_km to training_log."""
        try:
            cursor.execute(
                "ALTER TABLE training_log ADD COLUMN avg_pace_sec_per_km REAL"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

    def _apply_v19_pace_backfill(self, cursor) -> None:
        """Backfill avg_pace_sec_per_km for rows with valid distance/duration but NULL pace."""
        # Guard: skip the UPDATE entirely when nothing needs backfilling — makes
        # every subsequent startup essentially free after the initial migration.
        cursor.execute(
            "SELECT COUNT(*) FROM training_log "
            "WHERE avg_pace_sec_per_km IS NULL "
            "AND distance_km > 0 "
            "AND duration_sec > 0"
        )
        if cursor.fetchone()[0] == 0:
            return
        cursor.execute("""
            UPDATE training_log
            SET avg_pace_sec_per_km = ROUND(duration_sec / distance_km)
            WHERE avg_pace_sec_per_km IS NULL
              AND distance_km > 0.1
              AND duration_sec > 0
        """)

    def _apply_v20_migrations(self, cursor) -> None:
        """Version 20: add biological_sex and menstrual_tracking to athletes."""
        for sql in (
            "ALTER TABLE athletes ADD COLUMN biological_sex TEXT DEFAULT 'male'",
            "ALTER TABLE athletes ADD COLUMN menstrual_tracking TEXT DEFAULT 'no'",
        ):
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    def _apply_v21_migrations(self, cursor) -> None:
        """Version 21: nutrition_preferences table (ADR-0056)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nutrition_preferences (
                athlete_id          TEXT PRIMARY KEY,
                training_time       TEXT NOT NULL DEFAULT 'variable',
                fasted_training     TEXT NOT NULL DEFAULT 'easy_only',
                dietary_style       TEXT NOT NULL DEFAULT 'standard',
                meal_frequency      INTEGER NOT NULL DEFAULT 3,
                biological_sex      TEXT NOT NULL DEFAULT 'male',
                menstrual_tracking  TEXT NOT NULL DEFAULT 'no',
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    def _apply_v22_migrations(self, cursor) -> None:
        """Version 22: login_lockout table for SQLite-backed auth lockout (TD-SEC-02)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_lockout (
                username        TEXT PRIMARY KEY,
                failed_count    INTEGER NOT NULL DEFAULT 0,
                locked_until_ts REAL,
                last_attempt_ts REAL
            )
        """)

    def _apply_v23_migrations(self, cursor) -> None:
        """Version 23: consent_log table — SQLite reconciliation of Alembic d9 (TD-08 Step 5 / F3.4)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS consent_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id   TEXT NOT NULL DEFAULT 'default',
                consent_type TEXT NOT NULL,
                granted_at   TEXT NOT NULL,
                revoked_at   TEXT
            )
        """)

    def _apply_v24_migrations(self, cursor) -> None:
        """Version 24: multi-athlete schema isolation (P27-B1 / ADR-0033).

        Three changes:
        (a) daily_metrics: unique key (date) → (athlete_id, date)
            Requires table-rebuild (SQLite cannot ALTER CONSTRAINT).
            FROZEN HISTORICAL SNAPSHOT: the column list in the rebuild is
            intentionally frozen at v24-era state. DO NOT sync to descriptor.
            Ref: P27-B1, TD-08-R3 pattern, Opus pre-Phase-27 audit A3-02.
        (b) personal_bests: add athlete_id column (DEFAULT 'owner')
        (c) gear_usage: add athlete_id column (DEFAULT 'owner')
        """
        # (a) daily_metrics rebuild: drop (date) unique, add (athlete_id, date) unique
        #
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # FROZEN HISTORICAL SNAPSHOT — DO NOT MODIFY OR SYNC TO DESCRIPTOR
        # Column list frozen at v24 state. Adding post-v24 columns here
        # would corrupt migration replay. Ref: P27-B1, TD-08-R3 pattern.
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_metrics_v24_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id      TEXT NOT NULL DEFAULT 'owner',
                date            TEXT NOT NULL,
                weight_kg       REAL,
                hrv_rmssd       REAL,
                resting_hr      INTEGER,
                sleep_hours     REAL,
                sleep_quality   INTEGER,
                soreness        INTEGER,
                fatigue_level   INTEGER,
                mood            INTEGER,
                notes           TEXT,
                data_source     TEXT NOT NULL DEFAULT 'garmin_api',
                hrr_60          INTEGER,
                hrr_120         INTEGER,
                glycogen_debt   REAL,
                quality_flag    TEXT,
                UNIQUE (athlete_id, date)
            )
        """)
        cursor.execute("""
            INSERT INTO daily_metrics_v24_new
            SELECT id, athlete_id, date, weight_kg, hrv_rmssd, resting_hr,
                   sleep_hours, sleep_quality, soreness, fatigue_level, mood,
                   notes, data_source, hrr_60, hrr_120, glycogen_debt, quality_flag
            FROM daily_metrics
        """)
        cursor.execute("DROP TABLE daily_metrics")
        cursor.execute("ALTER TABLE daily_metrics_v24_new RENAME TO daily_metrics")

        # (b) personal_bests: add athlete_id
        try:
            cursor.execute(
                "ALTER TABLE personal_bests ADD COLUMN athlete_id TEXT NOT NULL DEFAULT 'owner'"
            )
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise

        # (c) gear_usage: add athlete_id
        try:
            cursor.execute(
                "ALTER TABLE gear_usage ADD COLUMN athlete_id TEXT NOT NULL DEFAULT 'owner'"
            )
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise

    def _apply_v25_migrations(self, cursor) -> None:
        """Version 25: cohort_calibration_signals table (P27-01 scaffolding)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cohort_calibration_signals (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                threshold_key        TEXT NOT NULL,
                athlete_id           TEXT NOT NULL,
                proposed_delta       REAL NOT NULL,
                sample_size          INTEGER NOT NULL,
                completion_delta_pp  REAL,
                computed_at          TEXT NOT NULL,
                UNIQUE (threshold_key, athlete_id)
            )
        """)
