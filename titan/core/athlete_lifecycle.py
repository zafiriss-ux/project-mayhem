"""Export, deletion and the 30-day purge of an athlete other than the owner (ADR-0067 D2, D4.3, D6).

- Tables are discovered from the schema: every table with an ``athlete_id`` column, never a list.
- Deletion writes its record first, then deletes every row of the athlete in one transaction,
  then removes the athlete's Garmin token folder. The record (athlete id and time only) lives
  in TITAN_DELETION_RECORD_FILE, outside the data folder and the backups, so a restore can
  delete the athlete again (D6.3).
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from titan.config.settings import get_settings
from titan.core.athlete import CONSENT_FREEZE_DAYS, OWNER_ATHLETE_ID

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

_log = logging.getLogger(__name__)

DELETION_RECORD_ENV = "TITAN_DELETION_RECORD_FILE"
# routine_type of the owner's row that marks the day's "not run" notice about an athlete (D-099).
NOT_READY_NOTICE_PREFIX = "not_ready:"
_ATHLETE_ID = re.compile(r"a-[0-9a-f]{8}")  # ADR-0067 D3.5
_EXPORT_FORMAT = "titan-athlete-export/1"
# Columns never written to an export: the password hash and the override nonces (D-108,
# TK-04). A column whose name says it holds a secret is left out too, so a new one is not missed.
_EXPORT_EXCLUDED_COLUMNS = frozenset({"password_hash", "nonce"})
_SECRET_COLUMN = re.compile(r"(password|secret|token_hash|api_key|private_key)", re.IGNORECASE)


def _exported_column(name: str) -> bool:
    return name not in _EXPORT_EXCLUDED_COLUMNS and not _SECRET_COLUMN.search(name)


def _check_athlete_id(athlete_id: str) -> None:
    if athlete_id == OWNER_ATHLETE_ID:
        raise ValueError("the owner is never exported or deleted by this tool")
    if not _ATHLETE_ID.fullmatch(athlete_id or ""):
        raise ValueError(f"not an athlete id: {athlete_id!r}")


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def athlete_tables(db: DatabaseManager) -> list[str]:
    """Every table with an ``athlete_id`` column, read from the schema (ADR-0067 D2.5, D6.1)."""
    names = [name for name in db.get_table_names() if not name.startswith("sqlite_")]
    with db._lock:
        db._ensure_open_locked()
        cursor = db.conn.cursor()
        # Identifiers come from sqlite_master and are quoted; no input reaches this SQL.
        return [
            name for name in names
            if any(col[1] == "athlete_id" for col in cursor.execute(f"PRAGMA table_info({_quoted(name)})"))  # nosec B608
        ]


def new_athlete_id() -> str:
    """``a-`` and 8 lowercase hex characters: opaque and safe in a path (ADR-0067 D3.5)."""
    return f"a-{secrets.token_hex(4)}"


def add_athlete(
    db: DatabaseManager,
    display_name: str,
    profile: dict[str, Any],
    telegram_chat_id: str | int,
    *,
    now: datetime | None = None,
) -> str:
    """Register an athlete other than the owner; return the new id (ADR-0067 D5.1, D10.1).

    Nothing is written when the name, profile or chat is refused. Garmin is bound later by
    ``athletes relogin``, on the routine machine with the athlete present (D9.1).
    """
    from titan.core.athlete import profile_problems

    name = (display_name or "").strip()
    if not name:
        raise ValueError("a display name is required")
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    problems = profile_problems(profile, moment.date())
    if problems:
        raise ValueError("profile refused: " + "; ".join(problems))
    chat = str(telegram_chat_id).strip()
    if not chat:
        raise ValueError("a Telegram chat id is required")
    if db.get_athlete_for_telegram_chat(chat) is not None:
        raise ValueError("this Telegram chat is already bound to an athlete")
    athlete_id = new_athlete_id()
    while athlete_exists(db, athlete_id):
        athlete_id = new_athlete_id()
    with db._lock:
        db._ensure_open_locked()
        db.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, ?)",
            (athlete_id, name, moment.isoformat()),
        )
        db.conn.commit()
    try:
        db.save_athlete_profile(athlete_id, profile)
        db.bind_telegram_chat(athlete_id, chat)
    except Exception:
        _delete_rows(db, athlete_id)
        raise
    _log.info("athlete_added", extra={"athlete_id": athlete_id})
    return athlete_id


def athlete_exists(db: DatabaseManager, athlete_id: str) -> bool:
    with db._lock:
        db._ensure_open_locked()
        row = db.conn.execute("SELECT 1 FROM athletes WHERE athlete_id = ?", (athlete_id,)).fetchone()
    return row is not None


def export_athlete(db: DatabaseManager, athlete_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    """One JSON-ready document with every row of the athlete in every athlete table (D2.5)."""
    _check_athlete_id(athlete_id)
    if not athlete_exists(db, athlete_id):
        raise LookupError(f"no athlete {athlete_id}")
    tables: dict[str, list[dict[str, Any]]] = {}
    with db._lock:
        db._ensure_open_locked()
        cursor = db.conn.cursor()
        for table in athlete_tables(db):
            cursor.execute(f"SELECT * FROM {_quoted(table)} WHERE athlete_id = ?", (athlete_id,))  # nosec B608
            columns = [d[0] for d in cursor.description]
            tables[table] = [
                {col: value for col, value in zip(columns, row, strict=True) if _exported_column(col)}
                for row in cursor.fetchall()
            ]
    return {
        "format": _EXPORT_FORMAT,
        "athlete_id": athlete_id,
        "exported_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "tables": tables,
    }


def export_json(document: dict[str, Any]) -> str:
    """The export as text; bytes and other values that JSON lacks are written as text."""
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def deletion_record_path() -> Path:
    """TITAN_DELETION_RECORD_FILE, which must be outside the data folder and the backups (D6.3)."""
    raw = os.environ.get(DELETION_RECORD_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{DELETION_RECORD_ENV} is not set, so a deletion could not survive a restore")
    path = Path(raw).expanduser().resolve()
    settings = get_settings()
    for label, folder in (("data", settings.TITAN_DATA_DIR), ("backup", settings.TITAN_BACKUP_DIR)):
        if not folder:
            continue
        base = Path(folder).expanduser().resolve()
        if path == base or base in path.parents:
            raise RuntimeError(f"{DELETION_RECORD_ENV} must be outside the {label} folder")
    return path


def read_deletion_records() -> list[dict[str, str]]:
    path = deletion_record_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_deletion_record(athlete_id: str, deleted_at: str) -> None:
    path = deletion_record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"athlete_id": athlete_id, "deleted_at": deleted_at}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _token_folder(athlete_id: str) -> Path:
    # Same folder as titan.integrations.garmin_sync.athlete_token_path (ADR-0067 D9.2).
    return Path(get_settings().TITAN_DATA_DIR) / "garmin" / athlete_id


def _delete_rows(db: DatabaseManager, athlete_id: str) -> dict[str, int]:
    """Delete every row of the athlete in one transaction; return the count per table."""
    tables = athlete_tables(db)
    # Children first, the athletes row last; foreign keys are checked at commit.
    ordered = [t for t in tables if t != "athletes"] + (["athletes"] if "athletes" in tables else [])
    counts: dict[str, int] = {}
    with db._lock:
        db._ensure_open_locked()
        conn = db.conn
        if conn.in_transaction:
            conn.commit()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("PRAGMA defer_foreign_keys = ON")
            if "auth_users" in tables:
                # A refresh token row names its user, not always the athlete (its athlete_id
                # is not filled), so it goes by user before the user goes (D-108, TK-03).
                cursor = conn.execute(
                    "DELETE FROM auth_tokens WHERE user_id IN (SELECT id FROM auth_users WHERE athlete_id = ?)",
                    (athlete_id,),
                )
                counts["auth_tokens"] = cursor.rowcount
            for table in ordered:
                cursor = conn.execute(f"DELETE FROM {_quoted(table)} WHERE athlete_id = ?", (athlete_id,))  # nosec B608
                counts[table] = counts.get(table, 0) + cursor.rowcount
            # The worker's once-a-day "not run" notices to Zaf name the athlete (D-099).
            cursor = conn.execute(
                "DELETE FROM worker_routine_executions WHERE athlete_id = 'owner' AND routine_type = ?",
                (f"{NOT_READY_NOTICE_PREFIX}{athlete_id}",),
            )
            counts["worker_routine_executions"] = counts.get("worker_routine_executions", 0) + cursor.rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return counts


def delete_athlete(db: DatabaseManager, athlete_id: str, *, now: datetime | None = None) -> dict[str, int]:
    """Delete the athlete: record first, then every row in one transaction, then the token (D6).

    The worker lists the athletes again on every round, so once the rows are gone the
    athlete has left the scheduler (D6.1).
    """
    _check_athlete_id(athlete_id)
    deleted_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    deletion_record_path()  # fail before anything changes when the record cannot be kept
    _append_deletion_record(athlete_id, deleted_at)
    try:
        counts = _delete_rows(db, athlete_id)
    except Exception as exc:
        # The record is already written, so a restart of the worker or `reapply-deletions`
        # deletes the rows again; the failure is said, never silent (D-097, D-108).
        _log.error(
            "athlete_delete_failed",
            extra={"athlete_id": athlete_id, "error_class": type(exc).__name__, "deletion_record_kept": True},
        )
        raise
    _remove_token_folder(athlete_id)
    _log.warning("athlete_deleted", extra={"athlete_id": athlete_id, "rows": sum(counts.values())})
    return counts


def _remove_token_folder(athlete_id: str) -> None:
    """Remove the athlete's Garmin token folder; a failure is logged and raised, never hidden (TK-08)."""
    folder = _token_folder(athlete_id)
    try:
        shutil.rmtree(folder)
    except FileNotFoundError:
        return
    except OSError as exc:
        _log.error(
            "athlete_token_folder_delete_failed",
            extra={"athlete_id": athlete_id, "error_class": type(exc).__name__},
        )
        raise RuntimeError(
            f"the rows of {athlete_id} are deleted, but the Garmin token folder {folder} was not "
            f"({type(exc).__name__}); remove it by hand"
        ) from exc


def reapply_deletions(db: DatabaseManager) -> list[str]:
    """After a restore, delete again every athlete in the deletion record (D2.7, D6.3)."""
    if not os.environ.get(DELETION_RECORD_ENV, "").strip():
        return []
    again: list[str] = []
    for record in read_deletion_records():
        athlete_id = record["athlete_id"]
        tables = athlete_tables(db)
        with db._lock:
            db._ensure_open_locked()
            left = any(
                db.conn.execute(f"SELECT 1 FROM {_quoted(t)} WHERE athlete_id = ? LIMIT 1", (athlete_id,)).fetchone()  # nosec B608
                for t in tables
            )
        if left:
            _delete_rows(db, athlete_id)
            _remove_token_folder(athlete_id)
            again.append(athlete_id)
            _log.warning("athlete_deletion_reapplied", extra={"athlete_id": athlete_id})
    return again


def expired_athletes(db: DatabaseManager, *, now: datetime | None = None) -> list[str]:
    """Athletes whose 30 days after /stop have passed with no consent since (D4.3)."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    with db._lock:
        db._ensure_open_locked()
        rows = db.conn.execute(
            "SELECT athlete_id, MAX(revoked_at), SUM(revoked_at IS NULL) FROM consent_log "
            "WHERE athlete_id != ? GROUP BY athlete_id",
            (OWNER_ATHLETE_ID,),
        ).fetchall()
    return [
        athlete_id for athlete_id, last_revoked, open_rows in rows
        if last_revoked and not open_rows
        and moment - datetime.fromisoformat(last_revoked) > timedelta(days=CONSENT_FREEZE_DAYS)
    ]


def purge_expired_athletes(db: DatabaseManager, *, now: datetime | None = None) -> list[str]:
    """Delete every athlete whose 30 days after /stop have passed (D4.3, D6)."""
    purged: list[str] = []
    for athlete_id in expired_athletes(db, now=now):
        delete_athlete(db, athlete_id, now=now)
        purged.append(athlete_id)
    return purged
