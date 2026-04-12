"""
TITAN Database Management
Persistent storage for training data, athlete profiles, and performance metrics
"""
import json
import logging
import os
import re
import sqlite3
import threading
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS

try:
    import psycopg2
except ModuleNotFoundError:  # pragma: no cover - optional backend dependency
    psycopg2 = None
from titan.core.athlete import UniversalAthleteProfile
from titan.core.structured_events import EventSeverity, structured_event_payload

_log = logging.getLogger(__name__)

# Ελάχιστα πεδία που πρέπει να υπάρχουν σε κάθε αρχείο JSON αθλητή
_REQUIRED_ATHLETE_KEYS: frozenset = frozenset({"athlete_id"})


def _database_event(action: str, level: int = logging.INFO, **fields: Any) -> None:
    """Emit a structured database event as a single JSON log line."""
    severity = EventSeverity.INFO
    if level >= logging.ERROR:
        severity = EventSeverity.CRITICAL
    elif level >= logging.WARNING:
        severity = EventSeverity.WARNING
    payload = structured_event_payload("database", action, severity=severity, **fields)
    _log.log(level, json.dumps(payload, default=str))


def _safe_json(raw: Any, fallback: Any = None, column: str = "") -> Any:
    """Safely decode JSON payloads from governance rows with warning fallback."""
    if raw is None or raw == "":
        return fallback

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        _database_event(
            "governance_row_json_malformed",
            level=logging.WARNING,
            column=column,
            raw_preview=str(raw)[:120],
        )
        return fallback


def _validate_athlete_dict(data: object) -> None:
    """Ελαφρύς έλεγχος σχήματος πριν το from_dict().

    Raises:
        TypeError: αν το data δεν είναι dict
        ValueError: αν λείπουν υποχρεωτικά πεδία
    """
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict, got {type(data).__name__}")
    missing = _REQUIRED_ATHLETE_KEYS - data.keys()
    if missing:
        raise ValueError(f"Missing required athlete fields: {missing}")


def _derive_field_hint(error: Exception) -> str:
    """Infer likely problematic field from exception text when loading athlete JSON."""
    error_msg = str(error)

    match = re.search(r"field: ([a-zA-Z0-9_]+)", error_msg)
    if match:
        return match.group(1)

    match = re.search(r"Missing required athlete fields: \{([^}]+)\}", error_msg)
    if match:
        first_missing = match.group(1).replace("'", "").split(",")[0].strip()
        if first_missing:
            return first_missing

    if isinstance(error, json.JSONDecodeError):
        return f"json_pos_{error.lineno}:{error.colno}"

    return "unknown"


# Current schema version. Increment by 1 for every new migration added to
# _run_migrations(). The value is stored in PRAGMA user_version so the DB
# self-reports its schema state on every startup.
SCHEMA_VERSION = 12


class DatabaseManager:
    """
    Permanent memory system for TITAN.

    Manages SQLite database for storing:
    - Daily metrics (morning check-in data)
    - Training log (complete session history)
    - Gear usage (shoe tracking with compression recovery)
    - Personal bests (PR tracking)

    Database Tables:
    1. daily_metrics: Weight, HRV, sleep, soreness, mood
    2. training_log: Complete training history with HR, RPE, load
    3. gear_usage: Shoe mileage and lifecycle management
    4. personal_bests: PR tracking by distance

    Scientific Integration:
    - CTL/ATL/TSB calculation (Banister model)
    - ACWR tracking (Gabbett, 2016)
    - Compression recovery tracking (24h foam set)
    """

    def __init__(self, db_name: str = "titan_core.db", db_dir: Path | None = None):
        """
        Initialize database connection.

        Args:
            db_name: Name of the SQLite database file
            db_dir: Directory to store database (default: ~/Documents/TITAN/)

        Note:
            - Production: Database stored in ~/Documents/TITAN/ (persistent across updates)
            - Development: Can override db_dir for testing
        """
        if db_dir is None:
            # Use launcher's get_data_directory for frozen-safe path resolution
            try:
                from launcher.validator import get_data_directory
                base_dir = get_data_directory()
            except ModuleNotFoundError as error:
                if error.name not in {"launcher", "launcher.validator"}:
                    raise

                _database_event(
                    "db_init_data_directory_fallback",
                    level=logging.WARNING,
                    error_class=type(error).__name__,
                    error_message=str(error),
                )

                # Fallback for standalone titan module usage (development)
                import os
                import platform
                if platform.system() == 'Windows':
                    base = Path(os.environ.get('USERPROFILE', Path.home()))
                else:
                    base = Path.home()
                base_dir = base / 'Documents' / 'TITAN'
        else:
            base_dir = db_dir

        if db_name == ":memory:":
            self.db_path = Path(":memory:")
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            # Ensure directory exists
            base_dir.mkdir(parents=True, exist_ok=True)

            self.db_path = base_dir / db_name

            # Thread-safe connection: allow access from multiple threads
            # (Garmin sync, Telegram callback, and main thread all share one DB)
            self.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
        self._lock = threading.RLock()  # Serialise all writes (supports nested transaction paths)
        self._closed = False
        self._transaction_depth = 0

        # Enable WAL mode for concurrent read/write access
        # WAL = Write-Ahead Logging (better concurrency than default rollback journal)
        # Critical for frozen builds where multiple threads access DB simultaneously
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        journal_row = cursor.fetchone()
        journal_mode = journal_row[0] if journal_row else "WAL"

        # Setter PRAGMA may not return a row; read it explicitly afterwards.
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA synchronous")
        synchronous_row = cursor.fetchone()
        synchronous = synchronous_row[0] if synchronous_row else "NORMAL"

        # Busy timeout: wait up to 5 seconds if DB is locked
        # Prevents "database is locked" errors during concurrent access
        cursor.execute("PRAGMA busy_timeout=5000")

        # Log PRAGMA results for debugging (frozen mode validation)
        try:
            logger = logging.getLogger('titan.database')
            logger.info(f"Database initialized: {self.db_path}")
            logger.info(f"PRAGMA journal_mode: {journal_mode}")
            logger.info(f"PRAGMA synchronous: {synchronous}")
            logger.info("PRAGMA busy_timeout: 5000")
        except (OSError, ValueError) as error:
            _database_event(
                "db_init_logging_skipped",
                level=logging.WARNING,
                db_path=str(self.db_path),
                error_class=type(error).__name__,
                error_message=str(error),
            )

        self.create_tables()

    def create_tables(self) -> None:
        """Create all database tables if they don't exist."""
        self.create_database()

    def create_database(self) -> None:
        """
        Initialize database with all tables.

        Table Schemas:
        - daily_metrics: Morning wellness data
        - training_log: Session details with load calculation
        - gear_usage: Shoe tracking with compression recovery
        - personal_bests: PR history
        """
        cursor = self.conn.cursor()

        # Table 1: Daily Metrics (Morning Check-in)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        """)

        # Table 2: Training Log (Complete History)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                FOREIGN KEY (shoe_id) REFERENCES gear_usage(id)
            )
        """)

        # Table 3: Gear Usage (Shoe Tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gear_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shoe_name TEXT NOT NULL,
                total_km REAL DEFAULT 0,
                last_used TEXT,
                compression_recovery_hours INTEGER DEFAULT 24,
                status TEXT DEFAULT 'ACTIVE',
                shoe_type TEXT,
                max_km_limit REAL DEFAULT 800
            )
        """)

        # Table 4: Personal Bests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personal_bests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                distance_km REAL NOT NULL,
                time_sec INTEGER NOT NULL,
                pace_sec_per_km REAL,
                date TEXT NOT NULL,
                race_name TEXT
            )
        """)

        # Table 5: CS Calibration Performances (Critical Speed / D' model)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cs_performances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                distance_m REAL NOT NULL,
                time_sec REAL NOT NULL,
                surface TEXT DEFAULT 'ROAD',
                wind_adjusted INTEGER DEFAULT 0
            )
        """)

        # Table 6: Override Audit Log (governance — discipline engine)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS override_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                prescribed_type TEXT,
                actual_type TEXT,
                reason TEXT
            )
        """)

        # Table 7: Override signals (ADR-0042 first-class override invariant)
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

        # Table 8: Governance outcomes (decision snapshot + post-session outcome)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS governance_outcomes (
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
        """)

        # Table 9: Per-athlete threshold offsets (ADR-0052 Stage 1)
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

        self.conn.commit()
        self._run_migrations(cursor)

    def _run_migrations(self, cursor) -> None:
        """Apply additive schema migrations guarded by PRAGMA user_version.

        Each migration is keyed by the target version it introduces. Only
        migrations with version > current user_version are applied.
        After all pending migrations run, user_version is updated to
        SCHEMA_VERSION. This replaces the old OperationalError-suppression
        approach with a deterministic version gate (T1-16).
        """
        current_version: int = cursor.execute("PRAGMA user_version").fetchone()[0]

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
        }

        if current_version < 1:
            self._apply_v1_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 1,
                    "columns_added": "hrr_60, hrr_120, glycogen_debt, garmin_activity_id",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )

        if current_version < 2:
            self._apply_v2_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 2,
                    "index_created": "idx_training_log_garmin_id",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )

        if current_version < 3:
            self._apply_v3_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 3,
                    "columns_added": "quality_flag (daily_metrics, training_log)",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )

        if current_version < 4:
            self._apply_v4_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 4,
                    "table_created": "sync_metadata",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 5:
            self._apply_v5_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 5,
                    "columns_added": (
                        "decision_was_followed, override_outcome_exclusion, "
                        "outcome_independence_ok, algorithm_version_snapshot"
                    ),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 6:
            self._apply_v6_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 6,
                    "table_created": "override_signals",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 7:
            self._apply_v7_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 7,
                    "table_created": "model_calibration_metadata",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 8:
            self._apply_v8_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 8,
                    "note": "garmin_activity_id NOT NULL check (T5-69 Stage 3)",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 9:
            self._apply_v9_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 9,
                    "table_created": "degraded_mode_state",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 10:
            self._apply_v10_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 10,
                    "tables_created": "auth_users, auth_tokens",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 11:
            self._apply_v11_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 11,
                    "columns_added": "governance_outcomes.athlete_id (T5-74)",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
        if current_version < 12:
            self._apply_v12_migrations(cursor)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_schema_migration",
                    "version": 12,
                    "table_created": "athlete_threshold_offsets (HD-09 / ADR-0052 Stage 1)",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )

        # Suppress unused-variable warning for _migrations (kept as documentation).
        _ = _migrations

        cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

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
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )
            return

        # All rows have garmin_activity_id and at least one row exists.
        # Recreate table with NOT NULL + athlete_id column.
        # SQLite does not support ALTER COLUMN — use the standard rename approach.
        cursor.execute("""
            CREATE TABLE training_log_v8_new (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id         TEXT NOT NULL DEFAULT 'default',
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
                "timestamp": datetime.utcnow().isoformat() + "Z",
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

    # --- Per-athlete threshold offsets (ADR-0052 Stage 1) ---

    def save_threshold_offset(
        self,
        athlete_id: str,
        threshold_key: str,
        delta_value: float,
        source: str,
        confidence: float,
        updated_at: str,
    ) -> None:
        """Persist a per-athlete threshold offset (ADR-0052).

        Raises ValueError if threshold_key is in HARD_STOP_THRESHOLD_KEYS —
        hard-stop gates H1–H5 are permanently excluded from adaptation.
        The ±20 % ceiling is ThresholdAdapter's responsibility (Stage 2);
        this layer enforces only the H1–H5 exclusion invariant.

        The INSERT ... ON CONFLICT DO UPDATE provides UPSERT semantics:
        a second call with the same (athlete_id, threshold_key) replaces
        delta_value, source, confidence, and updated_at.

        Args:
            athlete_id:    Athlete identifier (non-empty string).
            threshold_key: Identifier for the threshold being offset.
            delta_value:   Additive offset (positive or negative float).
            source:        Origin — 'manual' or 'calibration'.
            confidence:    Confidence score in [0.0, 1.0].
            updated_at:    UTC ISO-8601 timestamp string.
        """
        from titan.config.thresholds import HARD_STOP_THRESHOLD_KEYS  # local import avoids circular
        if threshold_key in HARD_STOP_THRESHOLD_KEYS:
            raise ValueError(
                f"threshold_key '{threshold_key}' is a hard-stop gate "
                f"and cannot be adapted (ADR-0052)."
            )
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO athlete_threshold_offsets
                    (athlete_id, threshold_key, delta_value,
                     updated_at, source, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (athlete_id, threshold_key)
                DO UPDATE SET
                    delta_value = excluded.delta_value,
                    updated_at  = excluded.updated_at,
                    source      = excluded.source,
                    confidence  = excluded.confidence
                """,
                (athlete_id, threshold_key, delta_value, updated_at, source, confidence),
            )
            if self._transaction_depth == 0:
                self.conn.commit()

    # --- Auth User / Token CRUD (HD-04 / T5-70) ---

    def upsert_auth_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        role: str,
        athlete_id: str | None,
        is_active: bool = True,
    ) -> None:
        """Insert or replace an auth user record."""
        with self._lock:
            self.conn.cursor().execute(
                "INSERT OR REPLACE INTO auth_users "
                "(id, username, password_hash, role, athlete_id, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, password_hash, role, athlete_id, int(is_active)),
            )
            self.conn.commit()

    def get_auth_user_by_id(self, user_id: str) -> dict | None:
        """Return the auth_users row for the given user_id, or None."""
        with self._lock:
            row = self.conn.cursor().execute(
                "SELECT id, username, password_hash, role, athlete_id, is_active "
                "FROM auth_users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "role": row[3],
            "athlete_id": row[4],
            "is_active": bool(row[5]),
        }

    def get_auth_user_by_username(self, username: str) -> dict | None:
        """Return the auth_users row for the given username, or None."""
        with self._lock:
            row = self.conn.cursor().execute(
                "SELECT id, username, password_hash, role, athlete_id, is_active "
                "FROM auth_users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "role": row[3],
            "athlete_id": row[4],
            "is_active": bool(row[5]),
        }

    def insert_auth_token(
        self, jti: str, user_id: str, issued_at: str, expires_at: str
    ) -> None:
        """Insert a new refresh token row (revoked=0 by default)."""
        with self._lock:
            self.conn.cursor().execute(
                "INSERT OR REPLACE INTO auth_tokens "
                "(id, user_id, issued_at, expires_at, revoked) VALUES (?, ?, ?, ?, 0)",
                (jti, user_id, issued_at, expires_at),
            )
            self.conn.commit()

    def get_auth_token(self, jti: str) -> dict | None:
        """Return the auth_tokens row for the given jti, or None."""
        with self._lock:
            row = self.conn.cursor().execute(
                "SELECT id, user_id, issued_at, expires_at, revoked "
                "FROM auth_tokens WHERE id = ?",
                (jti,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "user_id": row[1],
            "issued_at": row[2],
            "expires_at": row[3],
            "revoked": bool(row[4]),
        }

    def set_auth_token_revoked(self, jti: str) -> None:
        """Mark a refresh token as revoked."""
        with self._lock:
            self.conn.cursor().execute(
                "UPDATE auth_tokens SET revoked = 1 WHERE id = ?",
                (jti,),
            )
            self.conn.commit()

    def delete_expired_auth_tokens(self, before_iso: str) -> None:
        """Delete auth_tokens with expires_at < before_iso (housekeeping)."""
        with self._lock:
            self.conn.cursor().execute(
                "DELETE FROM auth_tokens WHERE expires_at < ?",
                (before_iso,),
            )
            self.conn.commit()

    def get_active_auth_tokens_for_user(self, user_id: str, now_iso: str) -> list[dict]:
        """Return active (non-revoked, non-expired) tokens for a user, by issued_at."""
        with self._lock:
            rows = self.conn.cursor().execute(
                "SELECT id, issued_at FROM auth_tokens "
                "WHERE user_id = ? AND revoked = 0 AND expires_at > ?",
                (user_id, now_iso),
            ).fetchall()
        return [{"id": r[0], "issued_at": r[1]} for r in rows]

    # --- Degraded Mode State (HD-06) ---

    def get_all_degraded_mode_states(self, athlete_id: str = "default") -> list[tuple[str, str]]:
        """Return all (failure_type, degraded_since) rows for the given athlete."""
        with self._lock:
            return self.conn.cursor().execute(
                "SELECT failure_type, degraded_since "
                "FROM degraded_mode_state WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchall()

    def upsert_degraded_mode_state(
        self, failure_type: str, degraded_since: str, athlete_id: str = "default"
    ) -> None:
        """Insert or replace a degraded-mode row keyed by failure_type."""
        with self._lock:
            self.conn.cursor().execute(
                "INSERT OR REPLACE INTO degraded_mode_state "
                "(failure_type, degraded_since, athlete_id) VALUES (?, ?, ?)",
                (failure_type, degraded_since, athlete_id),
            )
            self.conn.commit()

    def delete_degraded_mode_state(
        self, failure_type: str, athlete_id: str = "default"
    ) -> None:
        """Delete the degraded-mode row for a failure_type (degradation resolved)."""
        with self._lock:
            self.conn.cursor().execute(
                "DELETE FROM degraded_mode_state "
                "WHERE failure_type = ? AND athlete_id = ?",
                (failure_type, athlete_id),
            )
            self.conn.commit()

    # --- BACKUP ---

    def backup_database(self, backup_dir: Path | None = None, keep: int = 30) -> Path | None:
        """Create a hot backup of the database using sqlite3.backup().

        Safe to call while the DB is open and active — sqlite3.backup() uses
        the SQLite online backup API which does not require exclusive access.

        One backup per calendar day is created. If today's backup already exists
        the call is a no-op and returns None. Old backups beyond ``keep`` days
        are pruned.

        Args:
            backup_dir: Directory for backup files. Defaults to
                ``<db_dir>/backups/``.
            keep: Number of daily backups to retain (default 30).

        Returns:
            Path to the backup file created today, or None if already exists.
        """
        if backup_dir is None:
            backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        dest = backup_dir / f"titan_{date_str}.db"

        if dest.exists():
            return None  # today's backup already done

        try:
            with self._lock:
                self._ensure_open_locked()
                with sqlite3.connect(str(dest)) as dst_conn:
                    self.conn.backup(dst_conn)
            _log.info(
                json.dumps({
                    "flow": "database",
                    "action": "db_backup_created",
                    "dest": str(dest),
                    "date": date_str,
                })
            )
        except Exception as exc:
            _log.warning(
                json.dumps({
                    "flow": "database",
                    "action": "db_backup_failed",
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                })
            )
            return None

        self._prune_old_backups(backup_dir, keep=keep)
        return dest

    def _prune_old_backups(self, backup_dir: Path, keep: int) -> None:
        """Remove oldest daily backup files beyond the ``keep`` limit."""
        backups = sorted(backup_dir.glob("titan_????-??-??.db"))
        for old in backups[:-keep] if len(backups) > keep else []:
            with suppress(OSError):
                old.unlink()

    # --- DAILY METRICS ---

    @contextmanager
    def transaction(self):
        """Execute a group of writes atomically.

        Commits once when the outermost scope succeeds and rolls back on any
        exception.
        """
        with self._lock:
            self._ensure_open_locked()
            is_outermost = self._transaction_depth == 0
            if is_outermost:
                self.conn.execute("BEGIN")
            self._transaction_depth += 1
            try:
                yield
            except Exception:
                self._transaction_depth -= 1
                if is_outermost:
                    self.conn.rollback()
                raise
            else:
                self._transaction_depth -= 1
                if is_outermost:
                    self.conn.commit()

    def save_daily_metric(
        self,
        date: str,
        weight: float | None = None,
        hrv: float | None = None,
        rhr: int | None = None,
        sleep_hours: float | None = None,
        sleep_quality: int | None = None,
        soreness: int | None = None,
        fatigue: int | None = None,
        mood: int | None = None,
        notes: str | None = None,
        quality_flag: str | None = None,
    ) -> None:
        """
        Save morning check-in data.

        Args:
            date: Date in ISO format (YYYY-MM-DD)
            weight: Weight in kg
            hrv: HRV RMSSD in ms
            rhr: Resting heart rate in bpm
            sleep_hours: Sleep duration in hours
            sleep_quality: Sleep quality score (0-100)
            soreness: Soreness level (0-5 scale)
            fatigue: Fatigue level (0-5 scale)
            mood: Mood score (0-5 scale)
            notes: Optional text notes
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            # T5-66: Per-column UPSERT semantics.
            # Garmin-sourced columns (hrv_rmssd, resting_hr, sleep_hours,
            # sleep_quality, weight_kg, quality_flag) are overwritten on re-sync.
            # Manual subjective fields (soreness, fatigue_level, mood, notes) are
            # preserved when a row already exists — a Garmin re-sync must not zero
            # values the athlete manually entered.
            cursor.execute("""
                INSERT INTO daily_metrics
                (date, weight_kg, hrv_rmssd, resting_hr, sleep_hours, sleep_quality,
                 soreness, fatigue_level, mood, notes, quality_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    weight_kg    = CASE WHEN excluded.weight_kg    IS NOT NULL THEN excluded.weight_kg    ELSE weight_kg    END,
                    hrv_rmssd    = CASE WHEN excluded.hrv_rmssd    IS NOT NULL THEN excluded.hrv_rmssd    ELSE hrv_rmssd    END,
                    resting_hr   = CASE WHEN excluded.resting_hr   IS NOT NULL THEN excluded.resting_hr   ELSE resting_hr   END,
                    sleep_hours  = CASE WHEN excluded.sleep_hours  IS NOT NULL THEN excluded.sleep_hours  ELSE sleep_hours  END,
                    sleep_quality= CASE WHEN excluded.sleep_quality IS NOT NULL THEN excluded.sleep_quality ELSE sleep_quality END,
                    quality_flag = CASE WHEN excluded.quality_flag IS NOT NULL THEN excluded.quality_flag ELSE quality_flag END
            """, (date, weight, hrv, rhr, sleep_hours, sleep_quality, soreness, fatigue, mood, notes, quality_flag))
            if self._transaction_depth == 0:
                self.conn.commit()

    def save_daily_metric_if_missing(self, date: str, hrv: float | None = None) -> None:
        """Persist HRV for a historical date only if no row exists yet.

        Uses INSERT OR IGNORE so that manually entered data for past dates is
        never overwritten by backfill from Garmin sync.

        Args:
            date: Date in ISO format (YYYY-MM-DD)
            hrv: HRV RMSSD in ms
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO daily_metrics (date, hrv_rmssd)
                VALUES (?, ?)
                """,
                (date, hrv),
            )
            if self._transaction_depth == 0:
                self.conn.commit()

    # --- TRAINING LOG ---

    def _ensure_open_locked(self) -> None:
        if self._closed:
            raise RuntimeError("Database connection is closed")

    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        avg_hr: int | None = None,
        max_hr: int | None = None,
        rpe: int | None = None,
        shoe_id: int | None = None,
        surface: str | None = None,
        temperature_c: float | None = None,
        notes: str | None = None,
        garmin_activity_id: str | None = None,
        quality_flag: str | None = None,
        training_load: int | None = None,
        # Backward-compatible alias — will be removed in a future version
        temperature: float | None = None,
    ) -> None:
        """
        Save training session.

        Args:
            date:          Date in ISO format (YYYY-MM-DD)
            session_type:  Type of session (EASY, TEMPO, INTERVALS, etc.)
            distance_km:   Distance in kilometres
            duration_sec:  Duration in seconds
            avg_hr:        Average heart rate in bpm
            max_hr:        Maximum heart rate in bpm
            rpe:           Rate of Perceived Exertion (1-10 scale)
            shoe_id:       ID of shoe used
            surface:       Running surface (TRACK, ROAD, TRAIL, etc.)
            temperature_c: Air temperature in °C  ← canonical name
            notes:         Optional text notes
            garmin_activity_id: Stable Garmin external activity identity
            temperature:   Deprecated alias for temperature_c

        Training Load Calculation:
            sRPE (session RPE) = RPE × duration (minutes)
            Based on Foster et al. (2001)
        """
        # Resolve deprecated alias; temperature_c takes precedence
        if temperature_c is None and temperature is not None:
            import warnings
            warnings.warn(
                "save_session(temperature=...) is deprecated; use temperature_c= instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            temperature_c = temperature

        # Calculate training load: prefer explicit override, fall back to sRPE
        computed_load = (rpe * (duration_sec / 60)) if rpe else 0
        training_load = training_load if training_load is not None else int(computed_load)

        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO training_log
                (date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
                 training_load, shoe_id, surface, temperature_c, notes, garmin_activity_id,
                 quality_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
                  training_load, shoe_id, surface, temperature_c, notes, garmin_activity_id,
                  quality_flag))
            if cursor.rowcount == 1 and shoe_id and distance_km:
                cursor.execute("""
                    UPDATE gear_usage SET total_km = total_km + ?, last_used = ? WHERE id = ?
                """, (distance_km, date, shoe_id))
            if self._transaction_depth == 0:
                self.conn.commit()

    def get_training_load_history(self, days: int | None = None) -> list[tuple[str, float]]:
        """
        Get training load for last N days (for TSB calculation).

        Args:
            days: Number of days to retrieve (default 42 for CTL)

        Returns:
            List of tuples (date, training_load)
        """
        lookback_days = CTL_DECAY_DAYS if days is None else days

        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT date, training_load
                FROM training_log
                WHERE date >= date('now', '-' || ? || ' days')
                ORDER BY date DESC
            """, (lookback_days,))
            rows = cursor.fetchall()

        from titan.science.physiological_bounds import (
            validate_single,  # deferred: avoids circular import
        )
        validated: list[tuple[str, float]] = []
        for date_str, training_load in rows:
            clean = validate_single("training_load", float(training_load), "training_load_history")
            if clean is not None:
                validated.append((date_str, clean))
        return validated

    def get_ctl_atl_tsb(self) -> tuple[float, float, float]:
        """
        Calculate Training Stress Balance from database history.

        Implements the Banister/Coggan model:
        - CTL (Chronic Training Load): 42-day exponential moving average (Fitness)
        - ATL (Acute Training Load): 7-day exponential moving average (Fatigue)
        - TSB (Training Stress Balance): CTL - ATL (Form)

        TSB Interpretation:
            -10 to +5: Race ready (optimal freshness)
            -30 or lower: Overtraining risk
            +25 or higher: Detraining risk

        Returns:
            Tuple of (CTL, ATL, TSB)

        Scientific Basis:
            - Banister et al. (1975) - Systems model of training
            - Coggan (2003) - Training Stress Score/Balance
            - Busso (2003) - Variable dose-response model
        """
        loads = self.get_training_load_history(CTL_DECAY_DAYS)

        if not loads:
            return 0.0, 0.0, 0.0

        # Training history query returns newest-first (DESC). EMA must be
        # applied oldest→newest to reflect how fitness/fatigue evolve over time.
        chronological_loads = list(reversed(loads))

        # Calculate CTL (42-day EMA)
        ctl = 0.0
        ctl_decay = 2 / (CTL_DECAY_DAYS + 1)

        for _date, load in chronological_loads:
            ctl = (load * ctl_decay) + (ctl * (1 - ctl_decay))

        # Calculate ATL (7-day EMA, recent 7 entries)
        recent_loads = [load for _d, load in chronological_loads][-ATL_DECAY_DAYS:]
        atl = 0.0
        atl_decay = 2 / (ATL_DECAY_DAYS + 1)

        for load in recent_loads:
            atl = (load * atl_decay) + (atl * (1 - atl_decay))

        # Calculate TSB
        tsb = ctl - atl

        from titan.science.physiological_bounds import (
            validate_single,  # deferred: avoids circular import
        )
        ctl_out = validate_single("ctl", round(ctl, 1), "ctl_atl_tsb")
        atl_out = validate_single("atl", round(atl, 1), "ctl_atl_tsb")
        # Return zero-safe defaults when validation nulls a value (ADR-0023 §3)
        return (
            ctl_out if ctl_out is not None else 0.0,
            atl_out if atl_out is not None else 0.0,
            round(tsb, 1),
        )

    # --- GEAR MANAGEMENT ---

    def update_shoe_mileage(self, shoe_id: int, distance_km: float, date: str) -> None:
        """
        Update shoe mileage after a run.

        Args:
            shoe_id: ID of the shoe
            distance_km: Distance added in km
            date: Date of the run (ISO format)
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE gear_usage
                SET total_km = total_km + ?, last_used = ?
                WHERE id = ?
            """, (distance_km, date, shoe_id))
            self.conn.commit()

    def add_shoe(self, name: str, shoe_type: str = "DAILY", max_km: int = 800) -> int:
        """
        Add new shoe to database.

        Args:
            name: Descriptive name (e.g., "Nike Pegasus 40")
            shoe_type: Type of shoe ("DAILY", "RACE", "RECOVERY", "TRAIL")
            max_km: Maximum recommended mileage

        Returns:
            ID of the newly added shoe
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO gear_usage (shoe_name, shoe_type, max_km_limit)
                VALUES (?, ?, ?)
            """, (name, shoe_type, max_km))
            self.conn.commit()
        return cursor.lastrowid

    def get_active_shoes(self) -> list[tuple]:
        """
        Get all active shoes.

        Returns:
            List of tuples: (id, name, total_km, max_km, last_used, type)
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, shoe_name, total_km, max_km_limit, last_used, shoe_type
                FROM gear_usage
                WHERE status = 'ACTIVE'
                ORDER BY shoe_name
            """)
            return cursor.fetchall()

    def check_shoe_availability(self, shoe_id: int) -> tuple[bool, str]:
        """
        Check if shoe is available for use.

        Considers:
        1. Mileage limit (shoe lifespan)
        2. Compression recovery (24h rest for foam to decompress)

        Foam compression science:
        - EVA foam takes 24-48h to fully recover shape
        - Using shoes on consecutive days accelerates breakdown
        - Rotation extends shoe life by ~20-30%

        Args:
            shoe_id: ID of the shoe to check

        Returns:
            Tuple of (is_available, message)

        References:
            - Malisoux et al. (2013) - Shoe rotation and injury prevention
            - Kong et al. (2009) - Running shoe cushioning degradation
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT last_used, compression_recovery_hours, total_km, max_km_limit
                FROM gear_usage
                WHERE id = ?
            """, (shoe_id,))
            result = cursor.fetchone()

        if not result:
            return False, "Shoe not found"

        last_used, recovery_hours, total_km, max_km = result

        # Check mileage limit
        if total_km >= max_km:
            return False, f"Shoe exceeded mileage limit ({total_km}/{max_km} km)"

        # Check compression recovery
        if last_used:
            last_used_date = datetime.fromisoformat(last_used)
            hours_since = (datetime.now(UTC) - last_used_date).total_seconds() / 3600

            if hours_since < recovery_hours:
                hours_left = recovery_hours - hours_since
                return False, f"Foam needs {hours_left:.1f}h recovery (compression set)"

        return True, "Available"

    # --- PERSONAL BESTS ---

    def save_personal_best(
        self,
        distance_km: float,
        time_sec: int,
        date: str,
        race_name: str | None = None
    ) -> None:
        """
        Save a personal best.

        Args:
            distance_km: Distance in kilometers
            time_sec: Time in seconds
            date: Date of the performance (ISO format)
            race_name: Optional race name
        """
        pace_per_km = time_sec / distance_km

        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO personal_bests
                (distance_km, time_sec, pace_sec_per_km, date, race_name)
                VALUES (?, ?, ?, ?, ?)
            """, (distance_km, time_sec, pace_per_km, date, race_name))
            self.conn.commit()

    def get_pr(self, distance_km: float) -> tuple[int, str, str | None] | None:
        """
        Get personal best for a distance.

        Args:
            distance_km: Distance in kilometers

        Returns:
            Tuple of (time_sec, date, race_name) or None if no PR exists
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT time_sec, date, race_name
                FROM personal_bests
                WHERE distance_km = ?
                ORDER BY time_sec ASC
                LIMIT 1
            """, (distance_km,))
            return cursor.fetchone()

    # --- HRR (Heart Rate Recovery) ---

    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0) -> None:
        """
        Save Heart Rate Recovery values for a date.
        Updates existing daily_metrics row (call after save_daily_metric).

        Args:
            date:    Date in ISO format (YYYY-MM-DD)
            hrr_60:  BPM recovered at 60 seconds post-effort
            hrr_120: BPM recovered at 120 seconds post-effort
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE daily_metrics SET hrr_60 = ?, hrr_120 = ? WHERE date = ?",
                (hrr_60, hrr_120, date),
            )
            self.conn.commit()
            if cursor.rowcount == 0:
                _database_event(
                    "save_hrr_no_row_updated",
                    level=logging.WARNING,
                    date=date,
                    hrr_60=hrr_60,
                    hrr_120=hrr_120,
                )

    def get_hrr_history(self, days: int = 28) -> list[tuple[str, int, int]]:
        """
        Get HRR history for the last N days.

        Returns:
            List of (date, hrr_60, hrr_120) tuples, ordered DESC.
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT date, hrr_60, hrr_120 FROM daily_metrics
                   WHERE hrr_60 IS NOT NULL AND hrr_60 > 0
                   AND date >= date('now', '-' || ? || ' days')
                   ORDER BY date DESC""",
                (days,),
            )
            return cursor.fetchall()

    # --- GLYCOGEN DEBT ---

    def update_glycogen_debt(self, date: str, debt_score: float) -> None:
        """
        Persist today's glycogen debt score (0–10) to daily_metrics.
        Updates existing row for the date.
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE daily_metrics SET glycogen_debt = ? WHERE date = ?",
                (round(debt_score, 2), date),
            )
            self.conn.commit()
            if cursor.rowcount == 0:
                _database_event(
                    "update_glycogen_debt_no_row_updated",
                    level=logging.WARNING,
                    date=date,
                    debt_score=debt_score,
                )

    # --- CS CALIBRATION PERFORMANCES ---

    def log_cs_performance(
        self,
        date: str,
        distance_m: float,
        time_sec: float,
        surface: str = 'ROAD',
        wind_adjusted: bool = False,
    ) -> None:
        """
        Log a time-trial / race performance for CS/D' model calibration.

        Args:
            date:         Date in ISO format
            distance_m:   Distance in metres (e.g. 3000, 5000, 10000)
            time_sec:     Elapsed time in seconds
            surface:      ROAD / TRACK / TRAIL
            wind_adjusted: True if pace was corrected for wind
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO cs_performances
                   (date, distance_m, time_sec, surface, wind_adjusted)
                   VALUES (?, ?, ?, ?, ?)""",
                (date, distance_m, time_sec, surface, int(wind_adjusted)),
            )
            self.conn.commit()

    def get_cs_performances(self, limit: int = 10) -> list[tuple[str, float, float]]:
        """
        Retrieve most recent CS calibration performances.

        Returns:
            List of (date, distance_m, time_sec) tuples, ordered DESC.
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT date, distance_m, time_sec FROM cs_performances
                   ORDER BY date DESC LIMIT ?""",
                (limit,),
            )
            return cursor.fetchall()

    # --- OVERRIDE AUDIT LOG ---

    def log_override(
        self,
        date: str,
        prescribed: str,
        actual: str,
        reason: str = '',
    ) -> None:
        """
        Record a session override (athlete deviated from prescribed session).
        Used by GovernanceEngine to calculate override_ratio.

        Args:
            date:       Date in ISO format
            prescribed: Prescribed session type (e.g. 'REST')
            actual:     Actual session performed (e.g. 'INTERVALS')
            reason:     Optional athlete-supplied reason
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO override_log (date, prescribed_type, actual_type, reason)
                   VALUES (?, ?, ?, ?)""",
                (date, prescribed, actual, reason),
            )
            self.conn.commit()

    def record_override_signal(
        self,
        *,
        decision_id: str,
        athlete_id: str,
        override_source: str,
        override_reason: str,
        created_at: str,
    ) -> None:
        """Persist structured override signal entries (ADR-0042)."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO override_signals (
                       decision_id, athlete_id, override_source, override_reason, created_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (decision_id, athlete_id, override_source, override_reason, created_at),
            )
            self.conn.commit()

    def get_override_ratio(self, days: int = 14) -> float:
        """
        Calculate the fraction of days in the last N days with an override.

        Returns:
            Float 0.0–1.0 (1.0 = overrode every day in the window).
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) FROM override_log
                   WHERE date >= date('now', '-' || ? || ' days')""",
                (days,),
            )
            row = cursor.fetchone()
        overrides = row[0] if row else 0
        return round(overrides / days, 3)

    def get_override_log(self, limit: int = 50) -> list[dict[str, str]]:
        """Return recent override audit rows (oldest first) for operator review."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT date, prescribed_type, actual_type, reason
                   FROM override_log
                   ORDER BY id ASC
                   LIMIT ?""",
                (limit,),
            )
            rows = cursor.fetchall()
        return [
            {
                'date': row[0],
                'prescribed_type': row[1],
                'actual_type': row[2],
                'reason': row[3],
            }
            for row in rows
        ]

    # --- GOVERNANCE OUTCOMES ---

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        """Persist a governance decision snapshot into governance_outcomes."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO governance_outcomes (
                       athlete_id,
                       date, session_planned, session_post_governance,
                       locks_applied_json, governance_clean, phase, vlg_color,
                       apl_priority_vector_json, lock_thresholds_active_json,
                       acwr, tsb_value, readiness_score, glycogen_debt, afi_value,
                       outcome_rpe, outcome_completed, outcome_session_type_actual, outcome_notes,
                       decision_was_followed, override_outcome_exclusion,
                       outcome_independence_ok, algorithm_version_snapshot
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.get('athlete_profile_id', 'default'),
                    decision['date'],
                    decision['session_planned'],
                    decision['session_post_governance'],
                    json.dumps(decision.get('locks_applied', []), default=str),
                    int(bool(decision.get('governance_clean', False))),
                    decision.get('phase', ''),
                    decision.get('vlg_color', ''),
                    json.dumps(decision.get('apl_priority_vector', {}), default=str),
                    json.dumps(decision.get('lock_thresholds_active', {}), default=str),
                    float(decision.get('acwr', 0.0)),
                    float(decision.get('tsb_value', 0.0)),
                    float(decision.get('readiness_score', 0.0)),
                    float(decision.get('glycogen_debt', 0.0)),
                    decision.get('afi_value'),
                    decision.get('outcome_rpe'),
                    int(decision['outcome_completed']) if decision.get('outcome_completed') is not None else None,
                    decision.get('outcome_session_type_actual'),
                    decision.get('outcome_notes'),
                    int(bool(decision.get('decision_was_followed', True))),
                    int(bool(decision.get('override_outcome_exclusion', False))),
                    int(bool(decision.get('outcome_independence_ok', True))),
                    json.dumps(decision.get('algorithm_version_snapshot', {}), default=str),
                ),
            )
            self.conn.commit()

    def update_governance_outcome(
        self,
        date: str,
        rpe: int | None = None,
        completed: bool | None = None,
        actual_session_type: str | None = None,
        notes: str | None = None,
        decision_was_followed: bool | None = None,
        override_outcome_exclusion: bool | None = None,
        outcome_independence_ok: bool | None = None,
        algorithm_version_snapshot: dict[str, str] | None = None,
    ) -> bool:
        """Update latest governance decision for date with post-session outcome."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """UPDATE governance_outcomes
                   SET outcome_rpe = ?,
                       outcome_completed = ?,
                       outcome_session_type_actual = ?,
                       outcome_notes = ?,
                       decision_was_followed = COALESCE(?, decision_was_followed),
                       override_outcome_exclusion = COALESCE(?, override_outcome_exclusion),
                       outcome_independence_ok = COALESCE(?, outcome_independence_ok),
                       algorithm_version_snapshot = COALESCE(?, algorithm_version_snapshot)
                   WHERE id = (
                       SELECT id FROM governance_outcomes
                       WHERE date = ?
                       ORDER BY id DESC
                       LIMIT 1
                   )""",
                (
                    rpe,
                    int(completed) if completed is not None else None,
                    actual_session_type,
                    notes,
                    int(decision_was_followed) if decision_was_followed is not None else None,
                    int(override_outcome_exclusion) if override_outcome_exclusion is not None else None,
                    int(outcome_independence_ok) if outcome_independence_ok is not None else None,
                    json.dumps(algorithm_version_snapshot, default=str)
                    if algorithm_version_snapshot is not None
                    else None,
                    date,
                ),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_governance_decisions(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Fetch governance decisions ordered by insertion order (oldest first)."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT date, session_planned, session_post_governance,
                          locks_applied_json, governance_clean, phase, vlg_color,
                          apl_priority_vector_json, lock_thresholds_active_json,
                          acwr, tsb_value, readiness_score, glycogen_debt, afi_value,
                          outcome_rpe, outcome_completed, outcome_session_type_actual, outcome_notes,
                          decision_was_followed, override_outcome_exclusion,
                          outcome_independence_ok, algorithm_version_snapshot
                   FROM governance_outcomes
                   ORDER BY id ASC
                   LIMIT ?""",
                (limit,),
            )

            rows = cursor.fetchall()
        decisions: list[dict[str, Any]] = []
        for row in rows:
            decisions.append({
                'date': row[0],
                'session_planned': row[1],
                'session_post_governance': row[2],
                'locks_applied': _safe_json(row[3], [], 'locks_applied_json'),
                'governance_clean': bool(row[4]),
                'phase': row[5],
                'vlg_color': row[6],
                'apl_priority_vector': _safe_json(row[7], {}, 'apl_priority_vector_json'),
                'lock_thresholds_active': _safe_json(row[8], {}, 'lock_thresholds_active_json'),
                'acwr': float(row[9]),
                'tsb_value': float(row[10]),
                'readiness_score': float(row[11]),
                'glycogen_debt': float(row[12]),
                'afi_value': float(row[13]) if row[13] is not None else None,
                'outcome_rpe': row[14],
                'outcome_completed': bool(row[15]) if row[15] is not None else None,
                'outcome_session_type_actual': row[16],
                'outcome_notes': row[17],
                'decision_was_followed': bool(row[18]),
                'override_outcome_exclusion': bool(row[19]),
                'outcome_independence_ok': bool(row[20]),
                'algorithm_version_snapshot': _safe_json(
                    row[21], {}, 'algorithm_version_snapshot'
                ),
            })
        return decisions

    def annotate_governance_outcome(self, date: str, note: str) -> bool:
        """Attach or replace manual operator note for latest governance decision on date."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """UPDATE governance_outcomes
                   SET outcome_notes = ?
                   WHERE id = (
                       SELECT id FROM governance_outcomes
                       WHERE date = ?
                       ORDER BY id DESC
                       LIMIT 1
                   )""",
                (note, date),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_baseline_rhr(self, days: int = 7) -> float | None:
        """Return rolling N-day average resting HR from daily_metrics, or None."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
            cursor.execute(
                """SELECT AVG(resting_hr) FROM daily_metrics
                   WHERE date >= ? AND resting_hr IS NOT NULL AND resting_hr > 0""",
                (cutoff,),
            )
            row = cursor.fetchone()
        if row and row[0]:
            from titan.science.physiological_bounds import (
                validate_single,  # deferred: avoids circular import
            )
            raw = round(float(row[0]), 1)
            return validate_single("rhr_bpm", raw, "baseline_rhr")
        return None

    def get_hrv_history(self, days: int = 14) -> list[tuple[str, float]]:
        """Return (date, hrv_rmssd) rows from the last N days, newest-first.

        Values are validated against physiological bounds (ADR-0023 / T1-18).
        Rows with sensor-artefact HRV (nulled by bounds check) are excluded.
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT date, hrv_rmssd FROM daily_metrics
                   WHERE hrv_rmssd IS NOT NULL AND hrv_rmssd > 0
                   ORDER BY date DESC LIMIT ?""",
                (days,),
            )
            rows = cursor.fetchall()

        from titan.science.physiological_bounds import (
            validate_single,  # deferred: avoids circular import
        )
        validated = []
        for date_str, rmssd in rows:
            clean = validate_single("hrv_ms", float(rmssd), "hrv_history")
            if clean is not None:
                validated.append((date_str, clean))
        return validated

    def get_recent_hrv_mean(self, days: int = 30) -> float | None:
        """Return rolling mean HRV over recent days, or None when unavailable."""
        hrv_history = self.get_hrv_history(days=days)
        if not hrv_history:
            return None

        values = [entry[1] for entry in hrv_history]
        return round(sum(values) / len(values), 2)

    def upsert_model_calibration_metadata(
        self,
        *,
        model_name: str,
        calibrated_at: str,
        athlete_id: str = "default",
        calibrated_for: str = "default",
        baseline_hrv_ms: float | None = None,
        baseline_vo2: float | None = None,
        schema_version: int = SCHEMA_VERSION,
    ) -> None:
        """Insert or update model calibration metadata for a named model."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO model_calibration_metadata (
                        model_name,
                        athlete_id,
                        calibrated_at,
                        calibrated_for,
                        baseline_hrv_ms,
                        baseline_vo2,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(model_name, athlete_id) DO UPDATE SET
                        calibrated_at = excluded.calibrated_at,
                        calibrated_for = excluded.calibrated_for,
                        baseline_hrv_ms = excluded.baseline_hrv_ms,
                        baseline_vo2 = excluded.baseline_vo2,
                        schema_version = excluded.schema_version""",
                (
                    model_name,
                    athlete_id,
                    calibrated_at,
                    calibrated_for,
                    baseline_hrv_ms,
                    baseline_vo2,
                    schema_version,
                ),
            )
            if self._transaction_depth == 0:
                self.conn.commit()

    def get_model_calibration_metadata(
        self,
        model_name: str,
        athlete_id: str = "default",
    ) -> dict[str, Any] | None:
        """Return calibration metadata for a model, or None when no row exists."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT model_name, athlete_id, calibrated_at, calibrated_for,
                          baseline_hrv_ms, baseline_vo2, schema_version
                     FROM model_calibration_metadata
                     WHERE model_name = ? AND athlete_id = ?""",
                (model_name, athlete_id),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "model_name": str(row[0]),
            "athlete_id": str(row[1]),
            "calibrated_at": str(row[2]),
            "calibrated_for": str(row[3]),
            "baseline_hrv_ms": float(row[4]) if row[4] is not None else None,
            "baseline_vo2": float(row[5]) if row[5] is not None else None,
            "schema_version": int(row[6]),
        }

    def record_sync_outcome(
        self,
        *,
        source: str,
        attempted_at: datetime,
        success: bool,
        error_class: str | None = None,
    ) -> None:
        """Persist latest sync attempt outcome for a source system."""
        attempted_iso = attempted_at.astimezone(UTC).isoformat()
        success_iso = attempted_iso if success else None

        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO sync_metadata (
                        source,
                        last_attempt_ts,
                        last_success_ts,
                        last_sync_ok,
                        last_error_class
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_attempt_ts = excluded.last_attempt_ts,
                        last_success_ts = CASE
                            WHEN excluded.last_sync_ok = 1 THEN excluded.last_success_ts
                            ELSE sync_metadata.last_success_ts
                        END,
                        last_sync_ok = excluded.last_sync_ok,
                        last_error_class = excluded.last_error_class""",
                (source, attempted_iso, success_iso, 1 if success else 0, error_class),
            )
            self.conn.commit()

    def get_last_sync_outcome(self, source: str) -> dict[str, Any] | None:
        """Return latest sync outcome metadata for a source."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT last_attempt_ts, last_success_ts, last_sync_ok, last_error_class
                   FROM sync_metadata WHERE source = ?""",
                (source,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        attempted_at = None
        success_at = None
        if row[0]:
            with suppress(ValueError, TypeError):
                attempted_at = datetime.fromisoformat(row[0])
        if row[1]:
            with suppress(ValueError, TypeError):
                success_at = datetime.fromisoformat(row[1])

        return {
            "last_attempt_ts": attempted_at,
            "last_success_ts": success_at,
            "last_sync_ok": bool(row[2]),
            "last_error_class": row[3],
        }

    def get_last_garmin_sync_timestamp(self) -> datetime | None:
        """Return a datetime representing the most recent data written by Garmin sync.

        Checks the latest date in both daily_metrics and training_log and returns
        the more recent of the two, parsed as a midnight-UTC datetime.

        Returns None if no data exists in either table.
        """
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT MAX(date) FROM daily_metrics WHERE date IS NOT NULL"
            )
            dm_row = cursor.fetchone()
            cursor.execute(
                "SELECT MAX(date) FROM training_log WHERE date IS NOT NULL"
            )
            tl_row = cursor.fetchone()

        latest: str | None = None
        for row in (dm_row, tl_row):
            if row and row[0] and (latest is None or row[0] > latest):
                latest = row[0]

        if not latest:
            return None

        try:
            return datetime.fromisoformat(latest).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None

    def get_weight_history(self, days: int = 30) -> list[tuple[str, float]]:
        """Return (date, weight_kg) rows from the last N days, newest-first."""
        with self._lock:
            self._ensure_open_locked()
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT date, weight_kg FROM daily_metrics
                   WHERE weight_kg IS NOT NULL AND weight_kg > 0
                   ORDER BY date DESC LIMIT ?""",
                (days,),
            )
            rows = cursor.fetchall()

        from titan.science.physiological_bounds import (
            validate_single,  # deferred: avoids circular import
        )
        validated = []
        for date_str, weight_kg in rows:
            clean = validate_single("weight_kg", float(weight_kg), "weight_history")
            if clean is not None:
                validated.append((date_str, clean))
        return validated

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._closed:
                return

            self._closed = True
            if self.conn:
                self.conn.close()


class PostgreSQLDatabaseManager:
    """PostgreSQL-backed persistence for Phase 8A storage topology."""

    def __init__(self, dsn: str):
        if psycopg2 is None:
            raise ModuleNotFoundError("psycopg2 is required for PostgreSQL backend")

        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False
        self.create_tables()

    def create_tables(self) -> None:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS training_log (
                    id BIGSERIAL PRIMARY KEY,
                    date TEXT NOT NULL,
                    session_type TEXT,
                    distance_km DOUBLE PRECISION,
                    duration_sec INTEGER,
                    avg_hr INTEGER,
                    max_hr INTEGER,
                    rpe INTEGER,
                    training_load INTEGER,
                    shoe_id INTEGER,
                    surface TEXT,
                    temperature_c DOUBLE PRECISION,
                    zone_distribution TEXT,
                    notes TEXT,
                    garmin_activity_id TEXT,
                    quality_flag TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_training_log_garmin_id
                ON training_log(garmin_activity_id)
                WHERE garmin_activity_id IS NOT NULL
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS governance_outcomes (
                    id BIGSERIAL PRIMARY KEY,
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
                    acwr DOUBLE PRECISION NOT NULL,
                    tsb_value DOUBLE PRECISION NOT NULL,
                    readiness_score DOUBLE PRECISION NOT NULL,
                    glycogen_debt DOUBLE PRECISION NOT NULL,
                    afi_value DOUBLE PRECISION,
                    outcome_rpe INTEGER,
                    outcome_completed INTEGER,
                    outcome_session_type_actual TEXT,
                    outcome_notes TEXT,
                    decision_was_followed INTEGER NOT NULL DEFAULT 1,
                    override_outcome_exclusion INTEGER NOT NULL DEFAULT 0,
                    outcome_independence_ok INTEGER NOT NULL DEFAULT 1,
                    algorithm_version_snapshot TEXT
                )
                """
            )
        self._conn.commit()

    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        avg_hr: int | None = None,
        max_hr: int | None = None,
        rpe: int | None = None,
        shoe_id: int | None = None,
        surface: str | None = None,
        temperature_c: float | None = None,
        notes: str | None = None,
        garmin_activity_id: str | None = None,
        quality_flag: str | None = None,
        training_load: int | None = None,
        temperature: float | None = None,
    ) -> None:
        if temperature_c is None and temperature is not None:
            temperature_c = temperature

        computed_load = (rpe * (duration_sec / 60)) if rpe else 0
        training_load = training_load if training_load is not None else int(computed_load)
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO training_log (
                    date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
                    training_load, shoe_id, surface, temperature_c, notes,
                    garmin_activity_id, quality_flag
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (garmin_activity_id) DO NOTHING
                """,
                (
                    date,
                    session_type,
                    distance_km,
                    duration_sec,
                    avg_hr,
                    max_hr,
                    rpe,
                    training_load,
                    shoe_id,
                    surface,
                    temperature_c,
                    notes,
                    garmin_activity_id,
                    quality_flag,
                ),
            )
        self._conn.commit()

    def get_training_load_history(self, days: int | None = None) -> list[tuple[str, float]]:
        lookback_days = CTL_DECAY_DAYS if days is None else days
        start_date = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT date, training_load
                FROM training_log
                WHERE date >= %s
                ORDER BY date DESC
                """,
                (start_date,),
            )
            rows = cursor.fetchall()
        return [(str(row[0]), float(row[1])) for row in rows]

    def get_ctl_atl_tsb(self) -> tuple[float, float, float]:
        loads = self.get_training_load_history(CTL_DECAY_DAYS)
        if not loads:
            return 0.0, 0.0, 0.0

        chronological_loads = list(reversed(loads))
        ctl = 0.0
        ctl_decay = 2 / (CTL_DECAY_DAYS + 1)
        for _date, load in chronological_loads:
            ctl = (load * ctl_decay) + (ctl * (1 - ctl_decay))

        recent_loads = [load for _d, load in chronological_loads][-ATL_DECAY_DAYS:]
        atl = 0.0
        atl_decay = 2 / (ATL_DECAY_DAYS + 1)
        for load in recent_loads:
            atl = (load * atl_decay) + (atl * (1 - atl_decay))

        return round(ctl, 1), round(atl, 1), round(ctl - atl, 1)

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO governance_outcomes (
                    athlete_id,
                    date, session_planned, session_post_governance, locks_applied_json,
                    governance_clean, phase, vlg_color, apl_priority_vector_json,
                    lock_thresholds_active_json, acwr, tsb_value, readiness_score,
                    glycogen_debt, afi_value, outcome_rpe, outcome_completed,
                    outcome_session_type_actual, outcome_notes, decision_was_followed,
                    override_outcome_exclusion, outcome_independence_ok, algorithm_version_snapshot
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    decision.get("athlete_profile_id", "default"),
                    decision["date"],
                    decision["session_planned"],
                    decision["session_post_governance"],
                    json.dumps(decision.get("locks_applied", []), default=str),
                    int(bool(decision.get("governance_clean", False))),
                    decision.get("phase", ""),
                    decision.get("vlg_color", ""),
                    json.dumps(decision.get("apl_priority_vector", {}), default=str),
                    json.dumps(decision.get("lock_thresholds_active", {}), default=str),
                    float(decision.get("acwr", 0.0)),
                    float(decision.get("tsb_value", 0.0)),
                    float(decision.get("readiness_score", 0.0)),
                    float(decision.get("glycogen_debt", 0.0)),
                    decision.get("afi_value"),
                    decision.get("outcome_rpe"),
                    int(decision["outcome_completed"]) if decision.get("outcome_completed") is not None else None,
                    decision.get("outcome_session_type_actual"),
                    decision.get("outcome_notes"),
                    int(bool(decision.get("decision_was_followed", True))),
                    int(bool(decision.get("override_outcome_exclusion", False))),
                    int(bool(decision.get("outcome_independence_ok", True))),
                    json.dumps(decision.get("algorithm_version_snapshot", {}), default=str),
                ),
            )
        self._conn.commit()

    def get_governance_decisions(self, limit: int = 1000) -> list[dict[str, Any]]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT date, session_planned, session_post_governance, locks_applied_json,
                    governance_clean, phase, vlg_color, apl_priority_vector_json,
                    lock_thresholds_active_json, acwr, tsb_value, readiness_score,
                    glycogen_debt, afi_value, outcome_rpe, outcome_completed,
                    outcome_session_type_actual, outcome_notes, decision_was_followed,
                    override_outcome_exclusion, outcome_independence_ok, algorithm_version_snapshot
                FROM governance_outcomes
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        return [
            {
                "date": row[0],
                "session_planned": row[1],
                "session_post_governance": row[2],
                "locks_applied": json.loads(row[3]) if row[3] else [],
                "governance_clean": bool(row[4]),
                "phase": row[5],
                "vlg_color": row[6],
                "apl_priority_vector": json.loads(row[7]) if row[7] else {},
                "lock_thresholds_active": json.loads(row[8]) if row[8] else {},
                "acwr": row[9],
                "tsb_value": row[10],
                "readiness_score": row[11],
                "glycogen_debt": row[12],
                "afi_value": row[13],
                "outcome_rpe": row[14],
                "outcome_completed": bool(row[15]) if row[15] is not None else None,
                "outcome_session_type_actual": row[16],
                "outcome_notes": row[17],
                "decision_was_followed": bool(row[18]),
                "override_outcome_exclusion": bool(row[19]),
                "outcome_independence_ok": bool(row[20]),
                "algorithm_version_snapshot": json.loads(row[21]) if row[21] else {},
            }
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()


def get_database_manager(
    backend: str | None = None,
    db_name: str = "titan_core.db",
    db_dir: Path | None = None,
    postgres_dsn: str | None = None,
) -> DatabaseManager | PostgreSQLDatabaseManager:
    selected_backend = (backend or os.environ.get("TITAN_DB_BACKEND", "sqlite")).lower()
    if selected_backend == "sqlite":
        return DatabaseManager(db_name=db_name, db_dir=db_dir)
    if selected_backend == "postgres":
        dsn = postgres_dsn or os.environ.get("TITAN_POSTGRES_DSN")
        if not dsn:
            raise ValueError("TITAN_POSTGRES_DSN must be set for PostgreSQL backend")
        return PostgreSQLDatabaseManager(dsn=dsn)
    raise ValueError(f"Unsupported TITAN_DB_BACKEND: {selected_backend}")


class AthleteDatabase:
    """
    Multi-athlete management with JSON storage.

    Manages multiple athlete profiles with file-based persistence.
    Each athlete is stored as a separate JSON file for easy portability.

    Directory Structure:
        athletes/
        ├── ATH_20260213120000.json
        ├── ATH_20260213120100.json
        └── ...
    """

    def __init__(self, db_path: str = "athletes"):
        """
        Initialize athlete database.

        Args:
            db_path: Directory name for athlete storage
        """
        # Get the directory where the script is running
        file_path = globals().get("__file__")
        try:
            base_dir = Path(file_path).parent.parent.parent.absolute()
        except TypeError as error:
            # Fallback for IDLE/Jupyter
            _database_event(
                "athlete_db_base_directory_fallback",
                level=logging.WARNING,
                error_class=type(error).__name__,
                error_message=str(error),
            )
            base_dir = Path.cwd()

        self.db_path = base_dir / db_path
        self.db_path.mkdir(exist_ok=True)
        self.athletes: dict[str, UniversalAthleteProfile] = {}
        self.current_athlete_id: str | None = None
        self.load_all()

    def create_athlete(
        self,
        name: str,
        gender: str,
        age: int,
        height_cm: float,
        weight_kg: float
    ) -> UniversalAthleteProfile:
        """
        Create a new athlete profile.

        Args:
            name: Athlete's name
            gender: "M" or "F"
            age: Age in years
            height_cm: Height in centimeters
            weight_kg: Weight in kilograms

        Returns:
            Created UniversalAthleteProfile instance
        """
        profile = UniversalAthleteProfile(name=name)
        profile.set_demographics(gender, age, height_cm, weight_kg)

        self.athletes[profile.athlete_id] = profile
        self.current_athlete_id = profile.athlete_id
        self.save_athlete(profile)

        return profile

    def switch_athlete(self, athlete_id: str) -> UniversalAthleteProfile | None:
        """
        Switch to a different athlete.

        Args:
            athlete_id: ID of the athlete to switch to

        Returns:
            UniversalAthleteProfile instance or None if not found
        """
        if athlete_id in self.athletes:
            self.current_athlete_id = athlete_id
            return self.athletes[athlete_id]
        return None

    def get_current(self) -> UniversalAthleteProfile | None:
        """
        Get current active athlete.

        Returns:
            UniversalAthleteProfile instance or None if no athlete selected
        """
        if self.current_athlete_id and self.current_athlete_id in self.athletes:
            return self.athletes[self.current_athlete_id]
        return None

    def list_all(self) -> list[dict[str, Any]]:
        """
        List all athletes with basic info.

        Returns:
            List of dictionaries with athlete summary data
        """
        athletes_list = []
        for aid, prof in self.athletes.items():
            athletes_list.append({
                "id": aid,
                "name": prof.name,
                "age": prof.age,
                "gender": prof.gender,
                "goal": prof.current_goal
            })
        return athletes_list

    def save_athlete(self, profile: UniversalAthleteProfile) -> None:
        """
        Save athlete profile to JSON file.

        Args:
            profile: UniversalAthleteProfile to save
        """
        filepath = self.db_path / f"{profile.athlete_id}.json"
        with open(filepath, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)

    def load_all(self) -> None:
        """Load all athlete profiles from disk."""
        if not self.db_path.exists():
            return

        for filepath in self.db_path.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)

                if isinstance(data, dict) and not str(data.get('name', '')).strip():
                    data['name'] = 'Default Athlete'

                _validate_athlete_dict(data)

                self._validate_profile_schema(data)

                profile = UniversalAthleteProfile.from_dict(data)
                self.athletes[profile.athlete_id] = profile
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as e:
                _database_event(
                    "athlete_file_skipped",
                    level=logging.WARNING,
                    filename=filepath.name,
                    error_class=type(e).__name__,
                    error_message=str(e),
                    field_hint=_derive_field_hint(e),
                )

    @staticmethod
    def _validate_profile_schema(data: Any) -> None:
        """Validate shape/types for athlete JSON before profile deserialization."""
        if not isinstance(data, dict):
            raise TypeError("Athlete profile must be a JSON object")

        required_fields = {
            "athlete_id": str,
            "name": str,
        }
        for field, expected_type in required_fields.items():
            value = data.get(field)
            if not isinstance(value, expected_type) or not value.strip():
                raise ValueError(f"Invalid field: {field}")

        typed_fields = {
            "gender": str,
            "age": int,
            "height_cm": (int, float),
            "weight_kg": (int, float),
            "resting_hr": int,
            "max_hr": int,
            "threshold_hr": int,
            "vo2_max": (int, float),
            "race_day": str,
            "current_goal": str,
            "target_time": str,
            "personal_bests": dict,
            "weight_floor": (int, float),
            "paces": dict,
            "critical_speed_m_per_s": (int, float),
            "d_prime_m": (int, float),
        }
        for field, expected_type in typed_fields.items():
            if field in data and data[field] is not None and not isinstance(data[field], expected_type):
                raise TypeError(f"Invalid type for field: {field}")

        if "race_day" in data and data["race_day"] is not None:
            datetime.fromisoformat(data["race_day"])
