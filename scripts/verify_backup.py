"""
verify_backup.py — Verify the latest manual TITAN backup is a usable TITAN database.

A backup passes only when it is a TITAN database that a restore can start from
(#1451, BKP-NEW-01): ``PRAGMA integrity_check`` is ``ok``, ``PRAGMA user_version``
is a TITAN schema version this code can open (1 … SCHEMA_VERSION; an older one is
migrated on start, a newer one is refused by this code), the core tables are
present and hold at least one athlete (the owner's row, D-104). An empty or unfinished
file (0 bytes, no schema, no athletes) fails, and so does a symlink.

Run manually or in CI against a sample backup.
Exit 0 = OK. Exit 1 = not usable or missing.

Usage:
    python3 scripts/verify_backup.py [data_dir]
    # Default data_dir: ~/Documents/TITAN
"""

import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from titan.core.database import SCHEMA_VERSION, _verify_backup_artifact  # noqa: E402

# The same core tables the restore drill requires (scripts/restore_drill.py, DR-03).
CORE_TABLES = ("athletes", "training_log", "daily_metrics")
# Only finished manual backups: titan_core.db.YYYYMMDD (scripts/backup.sh). A file still
# being written is hidden (.titan_core.db.YYYYMMDD.partial.XXXXXX) and a SQLite sidecar
# (-journal, -wal) never matches.
BACKUP_NAME = re.compile(r"^titan_core\.db\.\d{8}$")


def problem_with(path: Path) -> str | None:
    """None when *path* is a usable TITAN backup, else what is wrong with it."""
    if path.is_symlink() or not path.is_file():
        return "not a regular file"
    if path.stat().st_size == 0:
        return "empty file (0 bytes)"
    try:
        problem = _verify_backup_artifact(path)
        if problem is not None:
            return problem
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            present = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            athletes = (
                conn.execute("SELECT COUNT(*) FROM athletes").fetchone()[0] if "athletes" in present else 0
            )
        finally:
            conn.close()
    except (OSError, sqlite3.Error, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"
    if version < 1:
        return "not a TITAN database (user_version 0)"
    if version > SCHEMA_VERSION:
        return f"schema version {version} is newer than this code ({SCHEMA_VERSION})"
    missing = [table for table in CORE_TABLES if table not in present]
    if missing:
        return f"missing tables: {', '.join(missing)}"
    if athletes < 1:
        # Every TITAN database has at least the owner's row (D-104): none is an empty shell.
        return "no athletes (empty database)"
    return None


def main(argv: list[str]) -> int:
    data_dir = Path(argv[1]) if len(argv) > 1 else Path.home() / "Documents/TITAN"
    backup_dir = data_dir / "backups"
    backups = sorted(
        (p for p in backup_dir.glob("titan_core.db.*") if BACKUP_NAME.match(p.name)), reverse=True,
    )
    if not backups:
        print(f"No backups found in {backup_dir}")
        return 1
    latest = backups[0]
    print(f"Verifying: {latest}")
    problem = problem_with(latest)
    if problem is not None:
        print(f"FAIL: {problem}")
        return 1
    print(f"OK — {latest.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
