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

# The backups hold health data: only the owner of the files can read them (#1451 review).
umask 077
mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
  echo "ERROR: $DB_FILE not found"
  exit 1
fi

# SQLite online backup API — safe during concurrent writes.
# Written under a hidden name of its own and renamed only when complete and sound, so an
# interrupted or overlapping run never leaves a titan_core.db.YYYYMMDD that looks finished
# (#1451, BKP-NEW-01). A leftover partial is removed by the prune below.
PARTIAL_FILE="$(mktemp "$BACKUP_DIR/.titan_core.db.$DATE.partial.XXXXXX")"
python3 -c "
import sqlite3, sys
src = sys.argv[1]
dst = sys.argv[2]
con = sqlite3.connect(src)
bak = sqlite3.connect(dst)
with bak:
    con.backup(bak)
ok = bak.execute('PRAGMA integrity_check').fetchone()
pages = bak.execute('PRAGMA page_count').fetchone()
bak.close()
con.close()
if ok is None or ok[0] != 'ok':
    sys.exit(f'Backup FAILED integrity_check: {ok}')
if not pages or pages[0] < 1:
    sys.exit('Backup FAILED: empty database')
" "$DB_FILE" "$PARTIAL_FILE" || { rm -f "$PARTIAL_FILE" "$PARTIAL_FILE-journal"; exit 1; }
mv -f "$PARTIAL_FILE" "$BACKUP_FILE"
echo "Backup OK: $BACKUP_FILE"

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
  \( -name "titan_core.db.*" -o -name ".titan_core.db.*.partial.*" -o -name "pending_audit.jsonl.*" \) \
  -mtime +$KEEP_DAYS \
  -delete

echo "Backup complete: $BACKUP_FILE"
ls -lh "$BACKUP_DIR/" 2>/dev/null || true
