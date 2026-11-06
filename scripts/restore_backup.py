"""Restore a TITAN backup together with its pending-audit queue (#1251, ADR-0079).

A backup is the database file plus, when withdrawals were still waiting, the
pending-audit queue copied beside it. A withdrawal (/stop) in that queue may be
missing from the database, so restoring the database alone can turn a stopped
athlete's consent back on. A withdrawal written to the database after the backup
is missing from the backup too. This script keeps both:

1. checks the backup (``PRAGMA integrity_check``, a schema version this code can open)
   and reads its queue copy; an unreadable copy stops the restore before anything changes;
2. reads every consent withdrawal recorded in the database being replaced (and in a
   database kept by an earlier restore), from a scratch copy with its ``-wal``; when that
   database cannot be read, or ``PRAGMA quick_check`` on the copy is not ``ok``, the restore
   stops. With ``--skip-live-withdrawals`` it goes on, and instead every athlete of the
   backup other than the owner gets a withdrawal dated now, so no consent comes back that
   cannot be checked: each such athlete gives consent again with /agree within 30 days, or
   the worker deletes them (D4.3). A clock behind a consent time in the backup stops it (#1497);
3. under the queue lock: adds those withdrawals to the queue in the data directory,
   keeping every withdrawal already there (a withdrawal is applied once per id, and only
   to consents given at or before it, so one written twice is harmless); keeps the current
   database and its ``-wal`` as ``titan_core.db.before-restore`` (``-wal``); writes the
   backup beside the database, removes the old ``-wal``/``-shm`` and renames it into place.

The API and the worker must be stopped. On start the worker writes the queued
withdrawals to the restored database. Prints one JSON line; exits 0 on success,
1 on any failure. Files it writes are readable by their owner only.

Usage:
    python scripts/restore_backup.py /backups/titan_2026-10-06.db
    python scripts/restore_backup.py /backups/titan_2026-10-05.db --again   # a second try
    python scripts/restore_backup.py ~/Documents/TITAN/backups/titan_core.db.20261006 --data-dir ~/Documents/TITAN
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from titan.core.database import SCHEMA_VERSION, _verify_backup_artifact  # noqa: E402
from titan.core.repositories.access import PendingAuditQueue  # noqa: E402

DB_NAME = "titan_core.db"
KEPT = DB_NAME + ".before-restore"
OWNER = "owner"
CARRIED_ACTION = "CONSENT_WITHDRAWN_BEFORE_RESTORE"
UNVERIFIED_ACTION = "CONSENT_WITHDRAWN_RESTORE_UNVERIFIED"
_MANUAL = re.compile(r"^titan_core\.db\.(\d{8})$")


def queue_copy_for(backup: Path) -> Path:
    """The queue copy that belongs to *backup*, whether it exists or not.

    The worker writes ``titan_YYYY-MM-DD.pending_audit.jsonl`` beside ``titan_YYYY-MM-DD.db``;
    ``scripts/backup.sh`` writes ``pending_audit.jsonl.YYYYMMDD`` beside ``titan_core.db.YYYYMMDD``.
    """
    manual = _MANUAL.match(backup.name)
    if manual:
        return backup.with_name(f"pending_audit.jsonl.{manual.group(1)}")
    return backup.with_name(backup.stem + ".pending_audit.jsonl")


def _regular_file(path: Path) -> bool:
    """True for a regular file that is not a symlink; False when *path* does not exist."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name} is not a regular file")
    return True


def read_queue_copy(copy: Path) -> list[dict]:
    """The withdrawals still waiting in a queue copy; none when there is no copy.

    Read with the queue's own reader, so a line it cannot read raises and stops the restore.
    """
    if not _regular_file(copy):
        return []
    with tempfile.TemporaryDirectory(prefix="titan_queue_copy_") as scratch:
        shutil.copyfile(copy, Path(scratch) / PendingAuditQueue.FILE_NAME)
        return PendingAuditQueue(Path(scratch)).pending()


def recorded_withdrawals(database: Path) -> list[dict]:
    """Every athlete's latest consent withdrawal recorded in *database*, as queue items.

    Read from a scratch copy of the database and its ``-wal``, so the database itself is
    never opened. No database means none. Raises when the database cannot be read.
    """
    if not _regular_file(database):
        return []
    with tempfile.TemporaryDirectory(prefix="titan_live_copy_") as scratch:
        copy = Path(scratch) / DB_NAME
        shutil.copyfile(database, copy)
        wal = database.with_name(database.name + "-wal")
        if _regular_file(wal):
            shutil.copyfile(wal, Path(scratch) / (DB_NAME + "-wal"))
        conn = sqlite3.connect(copy)
        try:
            # A damaged index can return fewer rows without an error, which would lose a
            # withdrawal (#1497): the copy must pass quick_check, and the table is read
            # without its index.
            check = [row[0] for row in conn.execute("PRAGMA quick_check").fetchall()]
            if check != ["ok"]:
                raise sqlite3.DatabaseError("quick_check did not return ok")
            rows = conn.execute(
                "SELECT athlete_id, revoked_at FROM consent_log NOT INDEXED "
                "WHERE revoked_at IS NOT NULL AND athlete_id != ?",
                (OWNER,),
            ).fetchall()
        finally:
            conn.close()
    # The latest withdrawal of each athlete, compared as times, not as text (#1497). A time
    # the queue cannot read stops the restore.
    latest: dict[str, tuple[datetime, str]] = {}
    for athlete_id, revoked_at in rows:
        when = _as_utc(revoked_at)
        if athlete_id not in latest or when > latest[athlete_id][0]:
            latest[athlete_id] = (when, revoked_at)
    items = []
    for athlete_id, (_when, revoked_at) in sorted(latest.items()):
        key = hashlib.sha256(f"{athlete_id}\n{revoked_at}".encode()).hexdigest()[:32]
        items.append({"id": f"restore-{key}", "athlete_id": athlete_id, "revoked_at": revoked_at, "action": CARRIED_ACTION})
    return items


def _as_utc(text: str) -> datetime:
    """*text* as an aware time; a time without an offset is UTC, as the drain reads it."""
    when = datetime.fromisoformat(text)
    return when if when.tzinfo is not None else when.replace(tzinfo=UTC)


def _read_only(path: Path) -> sqlite3.Connection:
    """Open *path* read-only; the URI is built from the encoded path, so ``?``, ``#`` or ``%``
    in a file name cannot make SQLite open another file."""
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def unverified_withdrawals(backup: Path, now: datetime) -> list[dict]:
    """A withdrawal dated *now* for every athlete in *backup* other than the owner (#1497).

    Used when the withdrawals recorded in the current database cannot be read: a consent
    that cannot be checked is not restored, so each athlete gives consent again with /agree.
    A consent in the backup dated after *now* would not be withdrawn (the drain withdraws
    only consents given at or before the withdrawal), so a clock behind the backup stops
    the restore.
    """
    with closing(_read_only(backup)) as conn:
        athletes = sorted({
            row[0]
            for table in ("athletes", "consent_log")
            for row in conn.execute(f"SELECT DISTINCT athlete_id FROM {table} NOT INDEXED WHERE athlete_id != ?", (OWNER,))  # nosec B608 - fixed table names
        })
        times = [
            text
            for row in conn.execute("SELECT granted_at, revoked_at FROM consent_log NOT INDEXED WHERE athlete_id != ?", (OWNER,))
            for text in row
            if text
        ]
    if any(_as_utc(text) > now for text in times):
        raise ValueError("this computer's clock is behind a consent time in the backup: set the clock, then try again")
    revoked_at = now.isoformat()
    return [
        {
            "id": "restore-unverified-" + hashlib.sha256(f"{athlete_id}\n{revoked_at}".encode()).hexdigest()[:32],
            "athlete_id": athlete_id, "revoked_at": revoked_at, "action": UNVERIFIED_ACTION,
        }
        for athlete_id in athletes
    ]


def merge_withdrawals_locked(queue: PendingAuditQueue, withdrawals: list[dict]) -> int:
    """Add *withdrawals* to *queue*; return how many were new there. The caller holds the exclusive lock.

    The queue is rewritten with the withdrawals already waiting plus the new ones, so a
    "done" marker left in the file cannot hide a withdrawal the restored database lacks.
    An unreadable queue raises and nothing is changed.
    """
    waiting = queue.read_locked()
    known = {item["id"] for item in waiting}
    new = []
    for item in withdrawals:
        if item["id"] not in known:
            known.add(item["id"])
            new.append(item)
    if new:
        queue.rewrite_locked(waiting + new)
    return len(new)


def _private_copy(source: Path, target: Path) -> None:
    """Copy *source* to *target* readable by the owner only, and fsync it.

    A stale regular file left at *target* is removed first. A symlink, a hard link or any
    other file type there is refused, so the write never reaches another file (#1497).
    """
    try:
        info = target.lstat()
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"{target.name} is not a plain file: remove it, then try again (with --again once {KEPT} exists)")
        target.unlink()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        with source.open("rb") as src:
            while chunk := src.read(1 << 20):
                os.write(fd, chunk)
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def restore(backup: Path, data_dir: Path, *, again: bool = False, skip_live_withdrawals: bool = False) -> dict:
    """Restore *backup*, its queue copy and the recorded withdrawals into *data_dir*. Never raises."""
    result: dict = {"backup": str(backup), "data_dir": str(data_dir), "ok": False}
    target = data_dir / DB_NAME
    wal = data_dir / (DB_NAME + "-wal")
    kept = data_dir / KEPT
    kept_wal = data_dir / (KEPT + "-wal")
    try:
        if not _regular_file(backup):
            raise ValueError("the backup does not exist")
        # The shared backup check opens a raw "file:" URI (#1501), where these characters would
        # make SQLite check another file than the one restored: neither the path as given nor
        # the resolved one may hold them, and the check gets the resolved path.
        resolved = backup.resolve()
        if any(char in path for path in (str(backup), str(resolved)) for char in "?#%"):
            raise ValueError("the backup's path contains ?, # or %: move or rename it, then try again")
        problem = _verify_backup_artifact(resolved)
        if problem is not None:
            raise ValueError(f"the backup failed its check: {problem}")
        with closing(_read_only(backup)) as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise ValueError(f"the backup's schema version {version} is newer than this code's {SCHEMA_VERSION}")
        copy = queue_copy_for(backup)
        withdrawals = read_queue_copy(copy)
        result["queue_copy"] = str(copy)
        result["queue_copy_found"] = copy.exists()
        result["withdrawals_in_backup"] = len(withdrawals)
        if again:
            if not kept.exists():
                raise ValueError(f"--again needs {KEPT} from the first restore")
            if wal.exists() and not kept_wal.exists():
                raise ValueError(
                    f"{DB_NAME}-wal exists but {KEPT}-wal does not: keep it before trying again "
                    f"(after a first restore that stopped while keeping, copy {DB_NAME}-wal to {KEPT}-wal)"
                )
        elif kept.exists() or kept_wal.exists():
            raise ValueError(f"{KEPT} already exists: move it away with its -wal, or use --again")
        recorded: list[dict] = []
        try:
            for database in (target, kept):
                recorded += recorded_withdrawals(database)
        except Exception as exc:
            if not skip_live_withdrawals:
                raise ValueError(
                    f"the withdrawals in the current database cannot be read ({type(exc).__name__}); "
                    "pass --skip-live-withdrawals to restore with every athlete's consent withdrawn"
                ) from exc
            result["live_withdrawals_skipped"] = f"{type(exc).__name__}: {exc}"
            # Fail closed (#1497): no consent the current database might have withdrawn comes back.
            recorded = unverified_withdrawals(backup, datetime.now(UTC))
            result["consents_withdrawn_unverified"] = len(recorded)
        result["withdrawals_recorded"] = len(recorded)
        queue = PendingAuditQueue(data_dir)
        with queue.locked(exclusive=True):
            result["withdrawals_added"] = merge_withdrawals_locked(queue, withdrawals + recorded)
            # The database is kept before its -wal: a stop in between leaves the kept database,
            # and --again then names the one step left (copy the -wal) instead of being stuck.
            if not again and target.exists():
                _private_copy(target, data_dir / (KEPT + ".partial"))
                os.replace(data_dir / (KEPT + ".partial"), kept)
            if not again and wal.exists():
                _private_copy(wal, data_dir / (KEPT + "-wal.partial"))
                os.replace(data_dir / (KEPT + "-wal.partial"), kept_wal)
            staged = data_dir / f".{DB_NAME}.restoring"
            _private_copy(backup, staged)
            _fsync_dir(data_dir)
            for side in (wal, data_dir / (DB_NAME + "-shm")):
                side.unlink(missing_ok=True)
            os.replace(staged, target)
            _fsync_dir(data_dir)
    except Exception as exc:  # the restore reports every failure, never raises
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    if not result["queue_copy_found"]:
        print(f"note: no queue copy {copy.name} beside the backup; only recorded withdrawals were kept", file=sys.stderr)
    result["ok"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("backup", type=Path, help="the backup file to restore")
    parser.add_argument("--data-dir", type=Path, default=None, help="default: TITAN_DATA_DIR")
    parser.add_argument("--again", action="store_true", help=f"a later try: keep the existing {KEPT}")
    parser.add_argument(
        "--skip-live-withdrawals", action="store_true",
        help="restore even when the current database cannot be read; every athlete's consent is then withdrawn",
    )
    args = parser.parse_args(argv)
    data_dir = args.data_dir
    if data_dir is None:
        from titan.config.settings import get_settings

        data_dir = Path(get_settings().TITAN_DATA_DIR)
    result = restore(args.backup, data_dir, again=args.again, skip_live_withdrawals=args.skip_live_withdrawals)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
