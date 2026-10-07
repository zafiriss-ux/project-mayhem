"""Restore drill for TITAN OS backups (AGENTS DR-03, docs/RUNBOOK_DR.md).

Copies the latest daily backup to a scratch directory, opens the copy, and
checks that it is a usable TITAN database:

* ``PRAGMA integrity_check`` returns ``ok``;
* ``PRAGMA user_version`` equals the code's ``SCHEMA_VERSION`` (or ``--expect-version``);
* the core tables are present.

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


def run_drill(backup_dir: Path, expect_version: int = SCHEMA_VERSION) -> dict:
    """Restore the latest backup into a scratch copy and verify it. Never raises."""
    result: dict = {"backup_dir": str(backup_dir), "ok": False}
    backup = latest_backup(backup_dir)
    if backup is None:
        result["error"] = "no backup found"
        return result
    result["backup"] = backup.name
    with tempfile.TemporaryDirectory(prefix="titan_restore_") as scratch:
        restored = Path(scratch) / "titan_core.db"
        try:
            shutil.copy2(backup, restored)
            problem = _verify_backup_artifact(restored, expected_user_version=expect_version)
            if problem is not None:
                result["error"] = problem
                return result
            conn = sqlite3.connect(f"file:{restored}?mode=ro", uri=True)
            try:
                present = {
                    row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                conn.close()
        except (OSError, sqlite3.Error) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result
    missing = [t for t in CORE_TABLES if t not in present]
    if missing:
        result["error"] = f"missing tables: {', '.join(missing)}"
        return result
    result.update(ok=True, user_version=expect_version, tables=len(present))
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
