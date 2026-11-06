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
QUEUE_PARTIAL="$PARTIAL_FILE.queue"
QUEUE_BACKUP="$BACKUP_DIR/pending_audit.jsonl.$DATE"
trap 'rm -f "$PARTIAL_FILE" "$PARTIAL_FILE-journal" "$QUEUE_PARTIAL"' EXIT
# The database and the pending-audit queue of consent withdrawals (ADR-0079) are copied
# under one shared queue lock (fcntl, as TITAN takes it), so no drain can move a
# withdrawal from the queue into the database between the two copies (#1252). The
# integrity check runs after the lock is let go.
python3 -c "
import fcntl, os, shutil, sqlite3, sys
data, dst, queue_dst = sys.argv[1], sys.argv[2], sys.argv[3]
lock = os.open(os.path.join(data, 'pending_audit.lock'), os.O_RDWR | os.O_CREAT, 0o600)
try:
    fcntl.flock(lock, fcntl.LOCK_SH)
    con = sqlite3.connect(os.path.join(data, 'titan_core.db'))
    bak = sqlite3.connect(dst)
    with bak:
        con.backup(bak)
    bak.close()
    con.close()
    queue = os.path.join(data, 'pending_audit.jsonl')
    if os.path.exists(queue):
        shutil.copyfile(queue, queue_dst)
finally:
    os.close(lock)
bak = sqlite3.connect(dst)
ok = bak.execute('PRAGMA integrity_check').fetchone()
pages = bak.execute('PRAGMA page_count').fetchone()
bak.close()
if ok is None or ok[0] != 'ok':
    sys.exit(f'Backup FAILED integrity_check: {ok}')
if not pages or pages[0] < 1:
    sys.exit('Backup FAILED: empty database')
" "$DATA_DIR" "$PARTIAL_FILE" "$QUEUE_PARTIAL"

# The queue copy is in place before the database copy gets its dated name, so a dated
# backup never stands beside a queue copy it was not taken with (#1252).
if [ -f "$QUEUE_PARTIAL" ]; then
  mv -f "$QUEUE_PARTIAL" "$QUEUE_BACKUP"
  echo "Pending-audit queue copied: $QUEUE_BACKUP"
else
  rm -f "$QUEUE_BACKUP"
fi
mv -f "$PARTIAL_FILE" "$BACKUP_FILE"
trap - EXIT
echo "Backup OK: $BACKUP_FILE"

# Prune old backups (keep last 7)
find "$BACKUP_DIR" \
  \( -name "titan_core.db.*" -o -name ".titan_core.db.*.partial.*" -o -name "pending_audit.jsonl.*" \) \
  -mtime +$KEEP_DAYS \
  -delete

echo "Backup complete: $BACKUP_FILE"
ls -lh "$BACKUP_DIR/" 2>/dev/null || true
