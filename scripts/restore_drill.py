"""Restore drill for TITAN OS backups (AGENTS DR-03, docs/RUNBOOK_DR.md).

Copies the latest daily backup to a scratch directory, opens the copy, and
checks that it is a usable TITAN database:

* ``PRAGMA integrity_check`` returns ``ok``;
* ``PRAGMA user_version`` equals the code's ``SCHEMA_VERSION`` (or ``--expect-version``);
* the core tables are present, and every table and column of a fresh database of
  this code is there too (#1452);
* the code opens the copy and reads it: an athlete's activities and a refresh-token
  lookup (#1452);
* the backup's pending-audit queue copy, when there is one, is restored beside it and
  every withdrawal in it is written to the copy, leaving each stopped athlete with no
  current consent (#1251, ADR-0079).

The original backup is never opened for writing. Prints one JSON line and
exits 0 on success, 1 on any failure.

Usage:
    python scripts/restore_drill.py                      # TITAN_BACKUP_DIR, else <TITAN_DATA_DIR>/backups
    python scripts/restore_drill.py --backup-dir /backups
    docker compose exec titan-worker python scripts/restore_drill.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from titan.config.settings import get_settings  # noqa: E402
from titan.core.database import SCHEMA_VERSION, _verify_backup_artifact  # noqa: E402

CORE_TABLES = ("athletes", "training_log", "daily_metrics")


def default_backup_dir() -> Path:
    settings = get_settings()
    if settings.TITAN_BACKUP_DIR:
        return Path(settings.TITAN_BACKUP_DIR)
    return Path(settings.TITAN_DATA_DIR) / "backups"


def latest_backup(backup_dir: Path) -> Path | None:
    backups = sorted(backup_dir.glob("titan_????-??-??.db"))
    return backups[-1] if backups else None


def _schema(path: Path) -> dict[str, set[str]]:
    """Table name → column names of the database at *path*, opened read-only."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {t: {col[0] for col in conn.execute("SELECT name FROM pragma_table_info(?)", (t,))} for t in tables}
    finally:
        conn.close()


def _schema_problem(restored: Path, scratch: Path) -> str | None:
    """None when *restored* has every table and column a fresh database of this code has (#1452).

    The reference is a new, empty database that this code creates in the scratch directory,
    so the check follows the code's own schema and needs no hand-kept list.
    """
    from titan.core.database import DatabaseManager

    reference_dir = scratch / "reference"
    DatabaseManager(db_name="titan_core.db", db_dir=reference_dir).close()
    expected = _schema(reference_dir / "titan_core.db")
    present = _schema(restored)
    missing = [t for t in CORE_TABLES if t not in present]
    missing += sorted(t for t in expected if t not in present and t not in CORE_TABLES)
    if missing:
        return f"missing tables: {', '.join(missing)}"
    columns = sorted(f"{t}.{c}" for t, cols in expected.items() for c in cols - present[t])
    if columns:
        shown = ", ".join(columns[:10]) + (" …" if len(columns) > 10 else "")
        return f"missing columns: {shown}"
    return None


def _owner_problem(restored: Path) -> str | None:
    """None when the restored copy has the owner's athlete row (#1452).

    Checked on the copy before the code opens it, because opening seeds that row.
    """
    conn = sqlite3.connect(f"file:{restored}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT 1 FROM athletes WHERE athlete_id = 'owner'").fetchone()
    finally:
        conn.close()
    return None if row else "no owner athlete row"


def _check_consumer(restored: Path) -> int:
    """Open the restored copy with the code and read it as it does at start (#1452).

    Then write the restored pending-audit queue to it as the worker does at start, and
    require that nothing stays queued and that no athlete with a withdrawal has a current
    consent (#1251). Returns how many withdrawals were in the queue. Raises when any of
    this fails; the caller reports that as a failure. Only the scratch copy is opened for
    writing; the backup itself is never touched.
    """
    from titan.api.auth import AuthStore
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name=restored.name, db_dir=restored.parent)
    try:
        AuthStore(db).is_refresh_token_active("restore-drill-probe")
        db.get_recent_activities(limit=1, athlete_id="owner")
        queue = db.pending_audit
        withdrawals = queue.pending() if queue is not None else []
        if db.drain_pending_audit():
            raise RuntimeError("withdrawals from the pending-audit queue could not be written")
        stopped = {item["athlete_id"] for item in withdrawals} - {"owner"}
        still = sorted(a for a in stopped if db.has_current_consent(a))
        if still:
            raise RuntimeError(f"consent still current after a queued withdrawal: {', '.join(still)}")
        return len(withdrawals)
    finally:
        db.close()


def run_drill(backup_dir: Path, expect_version: int = SCHEMA_VERSION) -> dict:
    """Restore the latest backup into a scratch copy and verify it. Never raises.

    Beyond integrity and version, the copy must have this code's schema (every table and
    column of a fresh database) and the code must open it and read it: an athlete's
    activities and a refresh-token lookup (#1452, BKP-NEW-02). The schema and read checks
    always use this code's current schema, whatever *expect_version* says.
    """
    result: dict = {"backup_dir": str(backup_dir), "ok": False}
    backup = latest_backup(backup_dir)
    if backup is None:
        result["error"] = "no backup found"
        return result
    result["backup"] = backup.name
    with tempfile.TemporaryDirectory(prefix="titan_restore_") as scratch:
        restored = Path(scratch) / "restored" / "titan_core.db"
        try:
            restored.parent.mkdir()
            shutil.copy2(backup, restored)
            queue_copy = backup.with_name(backup.stem + ".pending_audit.jsonl")
            if queue_copy.exists():
                shutil.copyfile(queue_copy, restored.parent / "pending_audit.jsonl")
            problem = _verify_backup_artifact(restored, expected_user_version=expect_version)
            if problem is None:
                problem = _schema_problem(restored, Path(scratch))
            if problem is None:
                problem = _owner_problem(restored)
            if problem is None:
                withdrawals = _check_consumer(restored)
                tables = len(_schema(restored))
        except Exception as exc:  # the drill reports every failure, never raises
            problem = f"{type(exc).__name__}: {exc}"
    if problem is not None:
        result["error"] = problem
        return result
    result.update(ok=True, user_version=expect_version, tables=tables, withdrawals=withdrawals)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--expect-version", type=int, default=SCHEMA_VERSION)
    args = parser.parse_args(argv)
    result = run_drill(args.backup_dir or default_backup_dir(), args.expect_version)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
