"""
TITAN Database Management
Persistent storage for training data, athlete profiles, and performance metrics
"""
import functools
import json
import logging
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS
from titan.core.schema import get_table as _get_schema_table

try:
    import psycopg2
except ModuleNotFoundError:  # pragma: no cover - optional backend dependency
    psycopg2 = None
from titan.core.athlete import OWNER_ATHLETE_ID, UniversalAthleteProfile, profile_problems
from titan.core.repositories.access import AccessRepository
from titan.core.repositories.governance import GovernanceRepository
from titan.core.repositories.migrations import SchemaMigrations
from titan.core.repositories.operations import OperationsRepository
from titan.core.repositories.physiology import PhysiologyRepository
from titan.core.repositories.training import TrainingRepository
from titan.core.structured_events import EventSeverity, structured_event_payload

# TD-08: ordered list of tables whose DDL create_database() renders from the
# canonical descriptor (titan/core/schema.py). Migration-managed tables
# (auth_users, auth_tokens, model_calibration_metadata, consent_log,
# degraded_mode_state, login_lockout, alembic_version) are excluded — they
# are created by the migration ladder (v10–v23) or Alembic, not by create_database().
_BASE_TABLE_NAMES: tuple[str, ...] = (
    "daily_metrics",
    "training_log",
    "gear_usage",
    "personal_bests",
    "cs_performances",
    "override_log",
    "override_signals",
    "governance_outcomes",
    "athlete_threshold_offsets",
    "athletes",
    "coach_athlete_assignments",
    "coach_audit_log",
)


def _render_table_ddl(table_name: str) -> str:
    """Render CREATE TABLE IF NOT EXISTS DDL from the canonical schema descriptor.

    TD-08 / S1: makes create_database() derive all base table DDL from
    titan/core/schema.py rather than maintaining raw SQL strings inline.
    SQLAlchemy is imported lazily so database.py startup cost is unchanged.
    """
    from sqlalchemy.dialects import sqlite as _sqlite_dialect
    from sqlalchemy.schema import CreateTable

    table = _get_schema_table(table_name)
    return str(
        CreateTable(table, if_not_exists=True).compile(
            dialect=_sqlite_dialect.dialect()
        )
    )


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
SCHEMA_VERSION = 30

# Largest size the WAL file is kept at after a checkpoint resets it (D-078).
WAL_SIZE_LIMIT_BYTES = 64 * 1024 * 1024


def _verify_backup_artifact(path: Path, *, expected_user_version: int | None = None) -> str | None:
    """Return None if *path* is a sound SQLite backup, else a description of the problem.

    Checks ``PRAGMA integrity_check`` and, when given, that ``PRAGMA user_version``
    matches the source schema version (AGENTS DR-02 / DR-03).
    """
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            return f"integrity_check: {result[0] if result else 'no result'}"
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if expected_user_version is not None and version != expected_user_version:
            return f"user_version {version} != expected {expected_user_version}"
    finally:
        conn.close()
    return None


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

        # D-078: after a checkpoint resets the WAL, SQLite truncates the file back to
        # this size. Without it the WAL keeps its largest size; the SQLite assessment
        # saw it reach 861 MB beside a 107 MB database under continuous readers.
        cursor.execute(f"PRAGMA journal_size_limit={WAL_SIZE_LIMIT_BYTES}")

        # INV-14: enforce declared foreign keys. SQLite defaults FK enforcement OFF;
        # without this, the ForeignKey constraints in schema.py are decorative.
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA foreign_keys")  # read back to confirm enabled

        # INV-14 safe-rollout: a DB with pre-existing orphaned FKs must not be
        # silently enforced into write failures. Detect, log CRITICAL, raise —
        # never proceed with a known-violating DB.
        fk_violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            logging.getLogger('titan.database').critical(json.dumps({
                "flow": "database", "action": "fk_integrity_violation_on_open",
                "invariant": "INV-14",
                "violation_count": len(fk_violations),
                "violations": [list(map(str, row)) for row in fk_violations[:20]],
                "outcome": "REFUSED_TO_OPEN",
            }, default=str))
            raise RuntimeError(
                f"Foreign-key integrity violations detected on open "
                f"({len(fk_violations)} rows). Refusing to enable FK enforcement "
                f"on a violating database. Reconcile orphaned rows first."
            )

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

        # TD-08 Step 2: DDL rendered from canonical descriptor (titan/core/schema.py).
        # Ordering respects FK dependencies: gear_usage before training_log.
        for _tname in _BASE_TABLE_NAMES:
            cursor.execute(_render_table_ddl(_tname))

        self._migrations._seed_single_athlete_rows(cursor=cursor)

        self.conn.commit()
        self._run_migrations(cursor)

    # --- MIGRATIONS (titan/core/repositories/migrations.py) ---

    def _run_migrations(self, cursor) -> None:
        """Apply additive schema migrations guarded by PRAGMA user_version."""
        self._migrations._run_migrations(cursor=cursor)

    def _apply_v1_migrations(self, cursor) -> None:
        """Version 1: additive column migrations for daily_metrics and training_log."""
        self._migrations._apply_v1_migrations(cursor=cursor)

    def _apply_v2_migrations(self, cursor) -> None:
        """Version 2: unique index on training_log.garmin_activity_id."""
        self._migrations._apply_v2_migrations(cursor=cursor)

    def _apply_v3_migrations(self, cursor) -> None:
        """Version 3: quality_flag column on daily_metrics and training_log (ADR-0026)."""
        self._migrations._apply_v3_migrations(cursor=cursor)

    def _apply_v4_migrations(self, cursor) -> None:
        """Version 4: Garmin sync outcome metadata table (T1-20)."""
        self._migrations._apply_v4_migrations(cursor=cursor)

    def _apply_v5_migrations(self, cursor) -> None:
        """Version 5: OutcomeTracker guardrail metadata columns (T1-22)."""
        self._migrations._apply_v5_migrations(cursor=cursor)

    def _apply_v6_migrations(self, cursor) -> None:
        """Version 6: override_signals table for ADR-0042 override capture."""
        self._migrations._apply_v6_migrations(cursor=cursor)

    def _apply_v7_migrations(self, cursor) -> None:
        """Version 7: calibration metadata table (T5-07 Layer 1 scaffold)."""
        self._migrations._apply_v7_migrations(cursor=cursor)

    def _apply_v8_migrations(self, cursor) -> None:
        """Version 8: conditional NOT NULL on training_log.garmin_activity_id (T5-69 Stage 3)."""
        self._migrations._apply_v8_migrations(cursor=cursor)

    def _apply_v9_migrations(self, cursor) -> None:
        """Version 9: degraded_mode_state table for DegradedModeTracker persistence (HD-06)."""
        self._migrations._apply_v9_migrations(cursor=cursor)

    def _apply_v10_migrations(self, cursor) -> None:
        """Version 10: auth_users and auth_tokens tables (HD-04 / T5-70 / ADR-0048)."""
        self._migrations._apply_v10_migrations(cursor=cursor)

    def _apply_v11_migrations(self, cursor) -> None:
        """Version 11: athlete_id column on governance_outcomes (T5-74 / ADR-0033)."""
        self._migrations._apply_v11_migrations(cursor=cursor)

    def _apply_v12_migrations(self, cursor) -> None:
        """Version 12: athlete_threshold_offsets table (HD-09 / ADR-0052 Stage 1)."""
        self._migrations._apply_v12_migrations(cursor=cursor)

    def _apply_v13_migrations(self, cursor) -> None:
        """Version 13: athletes canonical table + owner seed + governance backfill"""
        self._migrations._apply_v13_migrations(cursor=cursor)

    def _apply_v14_migrations(self, cursor) -> None:
        """Version 14: athlete_id on daily_metrics and training_log (T5-07-L3-D / ADR-0033)."""
        self._migrations._apply_v14_migrations(cursor=cursor)

    def _apply_v15_migrations(self, cursor) -> None:
        """Version 15: data_source provenance column on daily_metrics (T5-115)."""
        self._migrations._apply_v15_migrations(cursor=cursor)

    def _apply_v16_migrations(self, cursor) -> None:
        """Version 16: coach_athlete_assignments RBAC scoping table (ADR-0054 / T5-110)."""
        self._migrations._apply_v16_migrations(cursor=cursor)

    def _apply_v17_migrations(self, cursor) -> None:
        """Version 17: coach_audit_log persistent action history (T5-111)."""
        self._migrations._apply_v17_migrations(cursor=cursor)

    def _apply_v18_migrations(self, cursor) -> None:
        """Version 18: backfill training_log rows where athlete_id='default'→'owner'."""
        self._migrations._apply_v18_migrations(cursor=cursor)

    def _apply_v19_migrations(self, cursor) -> None:
        """Version 19: add avg_pace_sec_per_km to training_log."""
        self._migrations._apply_v19_migrations(cursor=cursor)

    def _apply_v19_pace_backfill(self, cursor) -> None:
        """Backfill avg_pace_sec_per_km for rows with valid distance/duration but NULL pace."""
        self._migrations._apply_v19_pace_backfill(cursor=cursor)

    def _apply_v20_migrations(self, cursor) -> None:
        """Version 20: add biological_sex and menstrual_tracking to athletes."""
        self._migrations._apply_v20_migrations(cursor=cursor)

    def _apply_v21_migrations(self, cursor) -> None:
        """Version 21: nutrition_preferences table (ADR-0056)."""
        self._migrations._apply_v21_migrations(cursor=cursor)

    def _apply_v22_migrations(self, cursor) -> None:
        """Version 22: login_lockout table for SQLite-backed auth lockout (TD-SEC-02)."""
        self._migrations._apply_v22_migrations(cursor=cursor)

    def _apply_v23_migrations(self, cursor) -> None:
        """Version 23: consent_log table — SQLite reconciliation of Alembic d9 (TD-08 Step 5 / F3.4)."""
        self._migrations._apply_v23_migrations(cursor=cursor)

    def _apply_v24_migrations(self, cursor) -> None:
        """Version 24: multi-athlete schema isolation (P27-B1 / ADR-0033)."""
        self._migrations._apply_v24_migrations(cursor=cursor)

    def _apply_v25_migrations(self, cursor) -> None:
        """Version 25: cohort_calibration_signals table (P27-01 scaffolding)."""
        self._migrations._apply_v25_migrations(cursor=cursor)

    def _apply_v26_migrations(self, cursor) -> None:
        """Version 26: worker_routine_executions + telegram_override_nonces (ADR-0060)."""
        self._migrations._apply_v26_migrations(cursor=cursor)

    def _apply_v27_migrations(self, cursor) -> None:
        """Version 27: weekly_plans table (D-020)."""
        self._migrations._apply_v27_migrations(cursor=cursor)

    def _apply_v28_migrations(self, cursor) -> None:
        """Version 28: cs_performances.athlete_id (D-012, D-028)."""
        self._migrations._apply_v28_migrations(cursor=cursor)

    def _apply_v29_migrations(self, cursor) -> None:
        """Version 29: training_log (athlete_id, date) index (D-077)."""
        self._migrations._apply_v29_migrations(cursor=cursor)

    def _apply_v30_migrations(self, cursor) -> None:
        """Version 30: athlete_id without DEFAULT, consent per text version, profiles, accounts (ADR-0067)."""
        self._migrations._apply_v30_migrations(cursor=cursor)

    def record_failed_login(
        self, username: str, lockout_duration_seconds: float, max_attempts: int
    ) -> bool:
        """Increment failed login count for username; lock account when threshold reached."""
        return self._access.record_failed_login(
            username=username, lockout_duration_seconds=lockout_duration_seconds, max_attempts=max_attempts
        )

    def is_login_locked_out(self, username: str) -> bool:
        """Return True if the account has an active lockout that has not yet expired."""
        return self._access.is_login_locked_out(username=username)

    def clear_login_lockout(self, username: str) -> None:
        """Reset failed login count and lockout timestamp for username."""
        self._access.clear_login_lockout(username=username)

    def get_nutrition_preferences(self, athlete_id: str = 'owner') -> dict | None:
        """Return nutrition preferences for athlete_id, or None if not set."""
        return self._operations.get_nutrition_preferences(athlete_id=athlete_id)

    def save_nutrition_preferences(
        self, athlete_id: str = 'owner', prefs: dict = None
    ) -> None:
        """Upsert nutrition preferences for athlete_id."""
        self._operations.save_nutrition_preferences(athlete_id=athlete_id, prefs=prefs)

    # --- Per-athlete threshold offsets (ADR-0052 Stage 1), cold start, calibration
    #     rates (titan/core/repositories/governance.py) ---

    def save_threshold_offset(
        self,
        athlete_id: str,
        threshold_key: str,
        delta_value: float,
        source: str,
        confidence: float,
        updated_at: str,
    ) -> None:
        """Persist a per-athlete threshold offset (ADR-0052)."""
        self._governance.save_threshold_offset(
            athlete_id=athlete_id, threshold_key=threshold_key, delta_value=delta_value,
            source=source, confidence=confidence, updated_at=updated_at,
        )

    def get_athlete_threshold_offsets(self, athlete_id: str) -> list[dict]:
        """Return all threshold offset rows for an athlete."""
        return self._governance.get_athlete_threshold_offsets(athlete_id=athlete_id)

    def delete_threshold_offset(self, athlete_id: str, threshold_key: str) -> int:
        """Delete a calibration-sourced threshold offset row (P27-04 rollback gate)."""
        return self._governance.delete_threshold_offset(
            athlete_id=athlete_id, threshold_key=threshold_key
        )

    def get_completion_rate(
        self, athlete_id: str, start_date: str, end_date: str
    ) -> tuple[float | None, int]:
        """Return (completion_rate, sample_count) for athlete_id in [start_date, end_date]."""
        return self._governance.get_completion_rate(
            athlete_id=athlete_id, start_date=start_date, end_date=end_date
        )

    def get_athlete_profile(self, athlete_id: str) -> tuple[str, dict] | None:
        """Return (display_name, athlete_profiles row), or None when the athlete has no profile."""
        return self._governance.get_athlete_profile(athlete_id=athlete_id)

    def save_athlete_profile(self, athlete_id: str, record: dict) -> None:
        """Store the profile of an athlete other than the owner (ADR-0067 D5).

        Raises ValueError for the owner, whose profile stays in .env (D1.3), or for an
        incomplete or out-of-range record, so a stored profile is always usable.
        """
        if athlete_id == OWNER_ATHLETE_ID:
            raise ValueError("the owner's profile lives in .env, not in athlete_profiles")
        now = datetime.now(UTC)
        problems = profile_problems(record, now.date())
        if problems:
            raise ValueError(f"athlete profile rejected: {'; '.join(problems)}")
        normalized = {
            **record,
            "training_phase": str(record["training_phase"]).upper(),
            "training_goal": str(record["training_goal"]).upper(),
        }
        self._governance.save_athlete_profile(
            athlete_id=athlete_id, record=normalized, updated_at=now.isoformat()
        )

    def get_athlete_account(self, athlete_id: str) -> dict | None:
        """Return the athlete's external accounts (Garmin, Telegram), or None."""
        return self._access.get_athlete_account(athlete_id=athlete_id)

    def bind_garmin_account(self, athlete_id: str, garmin_user_id: str) -> None:
        """Bind a Garmin account to an athlete other than the owner (ADR-0067 D9.4).

        Raises ValueError for the owner, whose Garmin login stays in .env (D1.3), or
        when the account is already bound to another athlete.
        """
        if athlete_id == OWNER_ATHLETE_ID:
            raise ValueError("the owner's Garmin account lives in .env, not in athlete_accounts")
        if not str(garmin_user_id).strip():
            raise ValueError("a Garmin account id is required")
        self._access.bind_garmin_account(
            athlete_id=athlete_id, garmin_user_id=str(garmin_user_id).strip(),
            updated_at=datetime.now(UTC).isoformat(),
        )

    def set_garmin_token_state(self, athlete_id: str, state: str) -> None:
        """Record the athlete's Garmin token state: 'missing', 'ok' or 'expired' (ADR-0067 D9.5)."""
        if state not in ("missing", "ok", "expired"):
            raise ValueError(f"unknown Garmin token state: {state!r}")
        self._access.set_garmin_token_state(
            athlete_id=athlete_id, state=state, updated_at=datetime.now(UTC).isoformat()
        )

    def bind_telegram_chat(self, athlete_id: str, telegram_chat_id: str | int) -> None:
        """Bind a private Telegram chat to an athlete other than the owner (ADR-0067 D10.1).

        Raises ValueError for the owner, whose chat stays TELEGRAM_CHAT_ID in .env, for the
        owner's chat itself, or when the chat is already bound to another athlete.
        """
        from titan.config.settings import get_settings

        chat = str(telegram_chat_id).strip()
        if athlete_id == OWNER_ATHLETE_ID:
            raise ValueError("the owner's Telegram chat lives in .env, not in athlete_accounts")
        if not chat:
            raise ValueError("a Telegram chat id is required")
        if chat == str(get_settings().TELEGRAM_CHAT_ID or "").strip():
            raise ValueError("this Telegram chat is the owner's")
        self._access.bind_telegram_chat(
            athlete_id=athlete_id, telegram_chat_id=chat, updated_at=datetime.now(UTC).isoformat()
        )

    def get_athlete_for_telegram_chat(self, telegram_chat_id: str | int) -> str | None:
        """Return the athlete whose private chat this is, or None for an unregistered chat."""
        return self._access.get_athlete_for_telegram_chat(telegram_chat_id=str(telegram_chat_id).strip())

    def revoke_consent(self, athlete_id: str) -> int:
        """Revoke the athlete's current consent (ADR-0067 D4.3); return the rows revoked."""
        if athlete_id == OWNER_ATHLETE_ID:
            raise ValueError("the owner is exempt from consent (ADR-0067 D4.5)")
        return self._access.revoke_consent(athlete_id=athlete_id, revoked_at=datetime.now(UTC).isoformat())

    def is_athlete_cold_start(self, athlete_id: str) -> bool:
        """Return True if the athlete is in the cold-start bootstrapping period."""
        return self._governance.is_athlete_cold_start(athlete_id=athlete_id)

    def check_and_exit_cold_start(self, athlete_id: str) -> bool:
        """Check cold-start exit conditions and graduate the athlete if met."""
        return self._governance.check_and_exit_cold_start(athlete_id=athlete_id)

    def increment_cold_start_sessions(self, athlete_id: str) -> None:
        """Increment cold_start_sessions_count for a cold-start athlete."""
        self._governance.increment_cold_start_sessions(athlete_id=athlete_id)

    def get_false_negative_rate(self, athlete_id: str, window_days: int) -> float:
        """Return the false-negative rate for the athlete over the last window_days."""
        return self._governance.get_false_negative_rate(
            athlete_id=athlete_id, window_days=window_days
        )

    # --- Auth User / Token CRUD (HD-04 / T5-70) (titan/core/repositories/access.py) ---

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
        self._access.upsert_auth_user(
            user_id=user_id, username=username, password_hash=password_hash, role=role, athlete_id=athlete_id, is_active=is_active
        )

    def get_auth_user_by_id(self, user_id: str) -> dict | None:
        """Return the auth_users row for the given user_id, or None."""
        return self._access.get_auth_user_by_id(user_id=user_id)

    def get_auth_user_by_username(self, username: str) -> dict | None:
        """Return the auth_users row for the given username, or None."""
        return self._access.get_auth_user_by_username(username=username)

    def insert_auth_token(
        self, jti: str, user_id: str, issued_at: str, expires_at: str
    ) -> None:
        """Insert a new refresh token row (revoked=0 by default)."""
        self._access.insert_auth_token(
            jti=jti, user_id=user_id, issued_at=issued_at, expires_at=expires_at
        )

    def get_auth_token(self, jti: str) -> dict | None:
        """Return the auth_tokens row for the given jti, or None."""
        return self._access.get_auth_token(jti=jti)

    def set_auth_token_revoked(self, jti: str) -> None:
        """Mark a refresh token as revoked."""
        self._access.set_auth_token_revoked(jti=jti)

    def delete_expired_auth_tokens(self, before_iso: str) -> None:
        """Delete auth_tokens with expires_at < before_iso (housekeeping)."""
        self._access.delete_expired_auth_tokens(before_iso=before_iso)

    def get_active_auth_tokens_for_user(self, user_id: str, now_iso: str) -> list[dict]:
        """Return active (non-revoked, non-expired) tokens for a user, by issued_at."""
        return self._access.get_active_auth_tokens_for_user(user_id=user_id, now_iso=now_iso)

    # --- Coach-Athlete RBAC Scoping (ADR-0054 / T5-110) (titan/core/repositories/access.py) ---

    def _get_all_athlete_ids(self) -> list[str]:
        """Return all athlete_ids from the athletes table."""
        return self._access._get_all_athlete_ids()

    def get_assigned_athletes(self, coach_id: str) -> list[str]:
        """Return athlete_ids the coach is permitted to access."""
        return self._access.get_assigned_athletes(coach_id=coach_id)

    def assign_athlete_to_coach(self, coach_id: str, athlete_id: str) -> None:
        """Grant coach_id access to athlete_id (idempotent via INSERT OR IGNORE)."""
        self._access.assign_athlete_to_coach(coach_id=coach_id, athlete_id=athlete_id)

    # --- Coach audit log (T5-111) (titan/core/repositories/access.py) ---

    def log_coach_action(
        self,
        coach_id: str,
        action_type: str,
        target_athlete_id: str,
        action_detail: str = "",
        resource: str = "",
    ) -> None:
        """Persist coach action to coach_audit_log. Survives process restart (T5-111)."""
        self._access.log_coach_action(
            coach_id=coach_id, action_type=action_type, target_athlete_id=target_athlete_id, action_detail=action_detail, resource=resource
        )

    def get_coach_audit_log(
        self,
        coach_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve audit log entries ordered newest-first."""
        return self._access.get_coach_audit_log(coach_id=coach_id, limit=limit)

    def get_table_names(self) -> list[str]:
        """Return all table names present in the database."""
        return self._operations.get_table_names()

    # --- Degraded Mode State (HD-06) (titan/core/repositories/operations.py) ---

    def get_all_degraded_mode_states(self, athlete_id: str = "default") -> list[tuple[str, str]]:
        """Return all (failure_type, degraded_since) rows for the given athlete."""
        return self._operations.get_all_degraded_mode_states(athlete_id=athlete_id)

    def upsert_degraded_mode_state(
        self, failure_type: str, degraded_since: str, athlete_id: str = "default"
    ) -> None:
        """Insert or replace a degraded-mode row keyed by failure_type."""
        self._operations.upsert_degraded_mode_state(
            failure_type=failure_type, degraded_since=degraded_since, athlete_id=athlete_id
        )

    def delete_degraded_mode_state(
        self, failure_type: str, athlete_id: str = "default"
    ) -> None:
        """Delete the degraded-mode row for a failure_type (degradation resolved)."""
        self._operations.delete_degraded_mode_state(
            failure_type=failure_type, athlete_id=athlete_id
        )

    # --- WORKER ROUTINE CLAIMS (ADR-0060 D1) (titan/core/repositories/operations.py) ---

    def claim_routine_execution(
        self, *, athlete_id: str, execution_date: str, routine_type: str, started_at: datetime
    ) -> bool:
        """Claim one routine run; False if it already started on that date (INV-15)."""
        return self._operations.claim_routine_execution(
            athlete_id=athlete_id, execution_date=execution_date,
            routine_type=routine_type, started_at=started_at,
        )

    def complete_routine_execution(
        self, *, athlete_id: str, execution_date: str, routine_type: str, completed_at: datetime
    ) -> None:
        """Mark a claimed routine as returned (INV-15)."""
        self._operations.complete_routine_execution(
            athlete_id=athlete_id, execution_date=execution_date,
            routine_type=routine_type, completed_at=completed_at,
        )

    def get_incomplete_routine_executions(self, execution_date: str) -> list[tuple[str, str]]:
        """Return (athlete_id, routine_type) claims of that date that never completed."""
        return self._operations.get_incomplete_routine_executions(execution_date=execution_date)

    # --- WEEKLY PLANS (D-020) (titan/core/repositories/operations.py) ---

    def save_weekly_plan(self, *, athlete_id: str, week_start: str, plan: dict) -> None:
        """Store the plan of one week; a second plan for the same week replaces it."""
        self._operations.save_weekly_plan(athlete_id=athlete_id, week_start=week_start, plan=plan)

    def get_latest_weekly_plan(self, *, athlete_id: str, on_or_before: str) -> dict | None:
        """Return the newest stored plan whose week starts on or before that date."""
        return self._operations.get_latest_weekly_plan(athlete_id=athlete_id, on_or_before=on_or_before)

    # --- BACKUP (titan/core/repositories/operations.py) ---

    def backup_database(
        self,
        backup_dir: Path | None = None,
        keep: int = 30,
        keep_weekly: int = 0,
    ) -> Path | None:
        """Create a verified hot backup of the database using sqlite3.backup()."""
        return self._operations.backup_database(
            backup_dir=backup_dir, keep=keep, keep_weekly=keep_weekly
        )

    def _record_backup_failure(self, dest: Path, problem: str) -> None:
        """Quarantine a failed backup artifact; log CRITICAL and count the failure."""
        self._operations._record_backup_failure(dest=dest, problem=problem)

    def _prune_old_backups(self, backup_dir: Path, keep: int, keep_weekly: int = 0) -> None:
        """Keep the ``keep`` newest daily backups plus ``keep_weekly`` older weekly ones."""
        self._operations._prune_old_backups(
            backup_dir=backup_dir, keep=keep, keep_weekly=keep_weekly
        )

    def check_integrity(self) -> bool:
        """Runs PRAGMA integrity_check. Returns True if OK, False otherwise."""
        return self._operations.check_integrity()

    # --- TRANSACTIONS ---

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

    # --- DAILY METRICS (titan/core/repositories/physiology.py) ---

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
        data_source: str = "garmin_api",
        athlete_id: str = "owner",
    ) -> None:
        """Save morning check-in data."""
        self._physiology.save_daily_metric(
            date=date, weight=weight, hrv=hrv, rhr=rhr, sleep_hours=sleep_hours,
            sleep_quality=sleep_quality, soreness=soreness, fatigue=fatigue, mood=mood,
            notes=notes, quality_flag=quality_flag, data_source=data_source,
            athlete_id=athlete_id,
        )

    def save_daily_metric_if_missing(
        self, date: str, hrv: float | None = None, athlete_id: str = "owner"
    ) -> None:
        """Persist HRV for a historical date only if no row exists yet."""
        self._physiology.save_daily_metric_if_missing(date=date, hrv=hrv, athlete_id=athlete_id)

    def replace_garmin_hrv(self, date: str, hrv: float, athlete_id: str = "owner") -> None:
        """Set HRV for a date from Garmin, unless the row was entered by hand (D-056)."""
        self._physiology.replace_garmin_hrv(date=date, hrv=hrv, athlete_id=athlete_id)

    # --- TRAINING LOG (titan/core/repositories/training.py) ---

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
        athlete_id: str = "owner",
        avg_pace_sec_per_km: float | None = None,
        # Backward-compatible alias — will be removed in a future version
        temperature: float | None = None,
    ) -> None:
        """Save training session."""
        self._training.save_session(
            date=date, session_type=session_type, distance_km=distance_km,
            duration_sec=duration_sec, avg_hr=avg_hr, max_hr=max_hr, rpe=rpe,
            shoe_id=shoe_id, surface=surface, temperature_c=temperature_c, notes=notes,
            garmin_activity_id=garmin_activity_id, quality_flag=quality_flag,
            training_load=training_load, athlete_id=athlete_id,
            avg_pace_sec_per_km=avg_pace_sec_per_km, temperature=temperature,
        )

    def get_recent_activities(
        self, limit: int = 90, athlete_id: str = "owner"
    ) -> list[dict]:
        """Return recent training sessions from training_log for the data browser."""
        return self._training.get_recent_activities(limit=limit, athlete_id=athlete_id)

    def get_training_load_history(
        self, days: int | None = None, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        """Get training load for last N days (for TSB calculation)."""
        return self._training.get_training_load_history(days=days, athlete_id=athlete_id)

    def is_db_reachable(self) -> bool:
        """Probe that the DB connection is live (schema-introspection query)."""
        return self._operations.is_db_reachable()

    def get_ctl_atl_tsb(self, athlete_id: str = "owner") -> tuple[float, float, float]:
        """Calculate Training Stress Balance from database history."""
        return self._training.get_ctl_atl_tsb(athlete_id=athlete_id)

    def replay_tsb(
        self,
        athlete_id: str,
        as_of_date: date,
    ) -> tuple[float, float, float]:
        return self._training.replay_tsb(athlete_id=athlete_id, as_of_date=as_of_date)

    # --- GEAR MANAGEMENT (titan/core/repositories/training.py) ---

    @functools.cached_property
    def _training(self) -> TrainingRepository:
        return TrainingRepository(self)

    @functools.cached_property
    def _physiology(self) -> PhysiologyRepository:
        return PhysiologyRepository(self)

    @functools.cached_property
    def _governance(self) -> GovernanceRepository:
        return GovernanceRepository(self)

    @functools.cached_property
    def _operations(self) -> OperationsRepository:
        return OperationsRepository(self)

    @functools.cached_property
    def _access(self) -> AccessRepository:
        return AccessRepository(self)

    @functools.cached_property
    def _migrations(self) -> SchemaMigrations:
        return SchemaMigrations(self)

    def update_shoe_mileage(
        self, shoe_id: int, distance_km: float, date: str, athlete_id: str = "owner"
    ) -> None:
        """Add a run's distance to a shoe of *athlete_id* and set its last-used date."""
        self._training.update_shoe_mileage(shoe_id, distance_km, date, athlete_id=athlete_id)

    def add_shoe(
        self, name: str, shoe_type: str = "DAILY", max_km: int = 800, athlete_id: str = "owner"
    ) -> int:
        """Add a shoe for *athlete_id*; returns its id."""
        return self._training.add_shoe(name, shoe_type, max_km, athlete_id=athlete_id)

    def get_active_shoes(self, athlete_id: str = "owner") -> list[tuple]:
        """Active shoes of *athlete_id* as (id, name, total_km, max_km, last_used, type)."""
        return self._training.get_active_shoes(athlete_id=athlete_id)

    def check_shoe_availability(
        self, shoe_id: int, athlete_id: str = "owner"
    ) -> tuple[bool, str]:
        """(is_available, message) from the mileage limit and foam recovery time."""
        return self._training.check_shoe_availability(shoe_id, athlete_id=athlete_id)

    # --- PERSONAL BESTS (titan/core/repositories/training.py) ---

    def save_personal_best(
        self,
        distance_km: float,
        time_sec: int,
        date: str,
        race_name: str | None = None,
        athlete_id: str = "owner",
    ) -> None:
        """Save a personal best for *athlete_id*."""
        self._training.save_personal_best(
            distance_km=distance_km, time_sec=time_sec, date=date, race_name=race_name,
            athlete_id=athlete_id,
        )

    def get_pr(
        self, distance_km: float, athlete_id: str = "owner"
    ) -> tuple[int, str, str | None] | None:
        """Get the personal best of *athlete_id* for a distance."""
        return self._training.get_pr(distance_km=distance_km, athlete_id=athlete_id)

    # --- HRR (Heart Rate Recovery) (titan/core/repositories/physiology.py) ---

    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0, athlete_id: str = "owner") -> None:
        """Save Heart Rate Recovery values for a date."""
        self._physiology.save_hrr(date=date, hrr_60=hrr_60, hrr_120=hrr_120, athlete_id=athlete_id)

    def get_hrr_history(
        self, days: int = 28, athlete_id: str = "owner"
    ) -> list[tuple[str, int, int]]:
        """Get HRR history for the last N days."""
        return self._physiology.get_hrr_history(days=days, athlete_id=athlete_id)

    # --- GLYCOGEN DEBT (titan/core/repositories/physiology.py) ---

    def update_glycogen_debt(self, date: str, debt_score: float, athlete_id: str = "owner") -> None:
        """Persist today's glycogen debt score (0–10) to daily_metrics."""
        self._physiology.update_glycogen_debt(date=date, debt_score=debt_score, athlete_id=athlete_id)

    def get_previous_glycogen_debt(
        self, before_date: str, athlete_id: str = "owner",
    ) -> tuple[str, float] | None:
        """Return ``(date, debt)`` of the latest stored glycogen debt before *before_date*, or None."""
        return self._physiology.get_previous_glycogen_debt(before_date=before_date, athlete_id=athlete_id)

    # --- CS CALIBRATION PERFORMANCES (titan/core/repositories/training.py) ---

    def log_cs_performance(
        self,
        date: str,
        distance_m: float,
        time_sec: float,
        surface: str = 'ROAD',
        wind_adjusted: bool = False,
        athlete_id: str = "owner",
    ) -> None:
        """Log a time-trial / race performance for CS/D' model calibration."""
        self._training.log_cs_performance(
            date=date, distance_m=distance_m, time_sec=time_sec, surface=surface,
            wind_adjusted=wind_adjusted, athlete_id=athlete_id,
        )

    def get_cs_performances(
        self, limit: int = 10, athlete_id: str = "owner"
    ) -> list[tuple[str, float, float]]:
        """Retrieve the athlete's most recent CS calibration performances."""
        return self._training.get_cs_performances(limit=limit, athlete_id=athlete_id)

    # --- OVERRIDE AUDIT LOG (titan/core/repositories/governance.py) ---

    def log_override(
        self,
        date: str,
        prescribed: str,
        actual: str,
        reason: str = '',
        *,
        athlete_id: str,
    ) -> None:
        """Record a session override (athlete deviated from prescribed session)."""
        self._governance.log_override(
            date=date, prescribed=prescribed, actual=actual, reason=reason, athlete_id=athlete_id
        )

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
        self._governance.record_override_signal(
            decision_id=decision_id, athlete_id=athlete_id, override_source=override_source,
            override_reason=override_reason, created_at=created_at,
        )

    def get_override_ratio(self, athlete_id: str = "owner", days: int = 14) -> float | None:
        """Calculate the fraction of days in the last N days with an override."""
        return self._governance.get_override_ratio(athlete_id=athlete_id, days=days)

    def get_override_log(self, limit: int = 50, athlete_id: str = "owner") -> list[dict[str, str]]:
        """Return recent override audit rows (oldest first) for operator review."""
        return self._governance.get_override_log(limit=limit, athlete_id=athlete_id)

    # --- TELEGRAM OVERRIDE NONCES (ADR-0060 D2) (titan/core/repositories/governance.py) ---

    def issue_override_nonce(
        self,
        *,
        nonce: str,
        command_type: str,
        athlete_id: str,
        decision_id: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> None:
        """Store a one-time override nonce bound to its decision (INV-17)."""
        self._governance.issue_override_nonce(
            nonce=nonce, command_type=command_type, athlete_id=athlete_id,
            decision_id=decision_id, issued_at=issued_at, expires_at=expires_at,
        )

    def consume_override_nonce(self, *, nonce: str, command_type: str, now: datetime) -> str | None:
        """Consume a nonce in one statement; its decision_id, or None if not valid."""
        return self._governance.consume_override_nonce(nonce=nonce, command_type=command_type, now=now)

    def prune_expired_override_nonces(self, now: datetime) -> int:
        """Delete expired override nonces; returns how many were deleted."""
        return self._governance.prune_expired_override_nonces(now=now)

    # --- GOVERNANCE OUTCOMES (titan/core/repositories/governance.py) ---

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        """Persist a governance decision snapshot into governance_outcomes."""
        self._governance.save_governance_decision(decision=decision)

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
        athlete_id: str = "owner",
    ) -> bool:
        """Update latest governance decision for athlete_id/date with post-session outcome."""
        return self._governance.update_governance_outcome(
            date=date, rpe=rpe, completed=completed, actual_session_type=actual_session_type,
            notes=notes, decision_was_followed=decision_was_followed,
            override_outcome_exclusion=override_outcome_exclusion,
            outcome_independence_ok=outcome_independence_ok,
            algorithm_version_snapshot=algorithm_version_snapshot, athlete_id=athlete_id,
        )

    def get_governance_decisions(
        self, limit: int = 1000, athlete_id: str = "owner"
    ) -> list[dict[str, Any]]:
        """Fetch governance decisions ordered by insertion order (oldest first)."""
        return self._governance.get_governance_decisions(limit=limit, athlete_id=athlete_id)

    def annotate_governance_outcome(self, date: str, note: str) -> bool:
        """Attach or replace manual operator note for latest governance decision on date."""
        return self._governance.annotate_governance_outcome(date=date, note=note)

    def get_baseline_rhr(self, days: int = 7, athlete_id: str = "owner") -> float | None:
        """Return rolling N-day average resting HR from daily_metrics, or None."""
        return self._physiology.get_baseline_rhr(days=days, athlete_id=athlete_id)

    def get_hrv_history(self, days: int = 14, athlete_id: str = "owner") -> list[tuple[str, float]]:
        """Return (date, hrv_rmssd) rows from the last N days, newest-first."""
        return self._physiology.get_hrv_history(days=days, athlete_id=athlete_id)

    def get_recent_hrv_mean(self, days: int = 30) -> float | None:
        """Return rolling mean HRV over recent days, or None when unavailable."""
        return self._physiology.get_recent_hrv_mean(days=days)

    def upsert_model_calibration_metadata(
        self,
        *,
        model_name: str,
        calibrated_at: str,
        athlete_id: str = "owner",
        baseline_hrv_ms: float | None = None,
        baseline_vo2: float | None = None,
        schema_version: int = SCHEMA_VERSION,
    ) -> None:
        """Insert or update model calibration metadata for a named model."""
        self._governance.upsert_model_calibration_metadata(
            model_name=model_name,
            calibrated_at=calibrated_at,
            athlete_id=athlete_id,
            baseline_hrv_ms=baseline_hrv_ms,
            baseline_vo2=baseline_vo2,
            schema_version=schema_version,
        )

    def get_model_calibration_metadata(
        self,
        model_name: str,
        athlete_id: str = "owner",
    ) -> dict[str, Any] | None:
        """Return calibration metadata for a model, or None when no row exists."""
        return self._governance.get_model_calibration_metadata(
            model_name=model_name, athlete_id=athlete_id
        )

    def record_sync_outcome(
        self,
        *,
        athlete_id: str,
        source: str,
        attempted_at: datetime,
        success: bool,
        error_class: str | None = None,
    ) -> None:
        """Persist the athlete's latest sync attempt outcome for a source system."""
        self._operations.record_sync_outcome(
            athlete_id=athlete_id, source=source, attempted_at=attempted_at,
            success=success, error_class=error_class,
        )

    def get_last_sync_outcome(self, source: str, athlete_id: str = "owner") -> dict[str, Any] | None:
        """Return latest sync outcome metadata for a source."""
        return self._operations.get_last_sync_outcome(source=source, athlete_id=athlete_id)

    def get_last_garmin_sync_timestamp(self, athlete_id: str = "owner") -> datetime | None:
        """Return a datetime representing the most recent data Garmin sync wrote for the athlete."""
        return self._operations.get_last_garmin_sync_timestamp(athlete_id=athlete_id)

    def get_weight_history(self, days: int = 30, athlete_id: str = "owner") -> list[tuple[str, float]]:
        """Return (date, weight_kg) rows from the last N days, newest-first."""
        return self._physiology.get_weight_history(days=days, athlete_id=athlete_id)

    def get_daily_metric(self, date: str, athlete_id: str = "owner") -> dict | None:
        """Return a single daily_metrics row for *date* as a dict, or None if absent."""
        return self._physiology.get_daily_metric(date=date, athlete_id=athlete_id)

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
                    athlete_id TEXT NOT NULL DEFAULT 'owner',
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
                SELECT date, SUM(training_load) as training_load
                FROM training_log
                WHERE date >= %s
                  AND training_load IS NOT NULL
                  AND training_load > 0
                GROUP BY date
                ORDER BY date ASC
                """,
                (start_date,),
            )
            rows = cursor.fetchall()
        return [(str(row[0]), float(row[1])) for row in rows]

    def get_ctl_atl_tsb(self) -> tuple[float, float, float]:
        from titan.science.tsb_engine import LOAD_HISTORY_DAYS, compute_ctl_atl_tsb
        loads = self.get_training_load_history(LOAD_HISTORY_DAYS)
        return compute_ctl_atl_tsb(
            daily_loads=loads,
            ctl_decay_days=CTL_DECAY_DAYS,
            atl_decay_days=ATL_DECAY_DAYS,
        )

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
                    decision.get("athlete_profile_id", "owner"),
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
        raise NotImplementedError(
            "PostgreSQLDatabaseManager is not production-ready. "
            "TITAN_DB_BACKEND=postgres is disabled until ADR-0044 full parity is implemented. "
            "See TECHNICAL_DEBT.md T5-08."
        )
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
