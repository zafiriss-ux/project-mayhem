#!/usr/bin/env bash
# TITAN OS — Database Backup
# Uses SQLite .backup() via Python (safe during live writes — WAL mode)
# Usage:
#   bash scripts/backup.sh [data_dir]
# Default data_dir: ~/Documents/TITAN

set -euo pipefail

DATA_DIR="${1:-${TITAN_DATA_DIR:-$HOME/Documents/TITAN}}"
DB_FILE="$DATA_DIR/titan_core.db"
BACKUP_DIR="$DATA_DIR/backups"
DATE=$(date +%Y%m%d)
BACKUP_FILE="$BACKUP_DIR/titan_core.db.$DATE"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
  echo "ERROR: $DB_FILE not found"
  exit 1
fi

# SQLite online backup API — safe during concurrent writes
python3 -c "
import sqlite3, sys
src = sys.argv[1]
dst = sys.argv[2]
con = sqlite3.connect(src)
bak = sqlite3.connect(dst)
with bak:
    con.backup(bak)
bak.close()
con.close()
print(f'Backup OK: {dst}')
" "$DB_FILE" "$BACKUP_FILE"

# The pending-audit queue of consent withdrawals goes with the database (ADR-0079).
# The copy is taken under the shared queue lock when flock is available.
QUEUE_FILE="$DATA_DIR/pending_audit.jsonl"
if [ -f "$QUEUE_FILE" ]; then
  QUEUE_BACKUP="$BACKUP_DIR/pending_audit.jsonl.$DATE"
  ( umask 077
    if command -v flock >/dev/null 2>&1; then
      flock -s "$DATA_DIR/pending_audit.lock" cp "$QUEUE_FILE" "$QUEUE_BACKUP"
    else
      cp "$QUEUE_FILE" "$QUEUE_BACKUP"
    fi )
  echo "Pending-audit queue copied: $QUEUE_BACKUP"
fi

# Prune old backups (keep last 7)
find "$BACKUP_DIR" \
  \( -name "titan_core.db.*" -o -name "pending_audit.jsonl.*" \) \
  -mtime +$KEEP_DAYS \
  -delete

echo "Backup complete: $BACKUP_FILE"
ls -lh "$BACKUP_DIR/" 2>/dev/null || true
