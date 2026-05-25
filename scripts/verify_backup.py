"""
verify_backup.py — Verify the latest TITAN backup is readable and passes integrity_check.

Run manually or in CI against a sample backup.
Exit 0 = OK. Exit 1 = corrupt or missing.

Usage:
    python3 scripts/verify_backup.py [data_dir]
    # Default data_dir: ~/Documents/TITAN
"""

import sqlite3
import sys
from pathlib import Path

DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Documents/TITAN"
BACKUP_DIR = DATA_DIR / "backups"

backups = sorted(BACKUP_DIR.glob("titan_core.db.*"), reverse=True)

if not backups:
    print(f"No backups found in {BACKUP_DIR}")
    sys.exit(1)

latest = backups[0]
print(f"Verifying: {latest}")

try:
    conn = sqlite3.connect(str(latest))
    result = conn.execute("PRAGMA integrity_check").fetchone()
    conn.close()
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)

if result and result[0] == "ok":
    size = latest.stat().st_size
    print(f"OK — {size:,} bytes")
    sys.exit(0)
else:
    print(f"FAIL: integrity_check returned {result}")
    sys.exit(1)
