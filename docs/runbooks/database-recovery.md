# Runbook — Database Recovery

**Version:** 1.1
**Date:** 2026-05-24
**Owner:** Engineering
**Trigger:** SQLite corruption, accidental deletion, DailyCoach degraded-conservative mode, or failed write detected in logs

---

## Backup Location

Automated daily backups run at each worker startup and every 24 h thereafter:

- **Container:** `/data/backups/titan_YYYY-MM-DD.db`
- **Local default:** `~/Documents/TITAN/backups/titan_YYYY-MM-DD.db`
- **Retention:** 7 days (configurable via `keep=` in `DatabaseManager.backup_database`)

Manual on-demand backup:

```bash
bash scripts/backup.sh [data_dir]
# Default data_dir: ~/Documents/TITAN
# Creates: <data_dir>/backups/titan_core.db.YYYYMMDD
```

---

## Recovery Procedure

### From automated backup

```bash
# List available backups
ls ~/Documents/TITAN/backups/

# Stop the system
docker compose stop titan-api titan-worker

# Restore (replace YYYY-MM-DD with the target date)
cp ~/Documents/TITAN/backups/titan_YYYY-MM-DD.db \
   ~/Documents/TITAN/titan_core.db

# Verify integrity
python3 -c "
import sqlite3
c = sqlite3.connect('$HOME/Documents/TITAN/titan_core.db')
print(c.execute('PRAGMA integrity_check').fetchone())
c.close()
"

# Restart
docker compose start titan-api titan-worker
```

---

## Symptoms

- Application log contains `persistence_failure` or `database_error` structured event
- `DailyCoach` emits a "degraded conservative mode" Telegram message (ADR-0020)
- `sqlite3.DatabaseError: database disk image is malformed`
- Operator Console shows missing or zero entries for recent sessions

---

## Database Location

Default path: `titan_core.db` in the data directory (or `DATABASE_PATH` env override).

```bash
echo $DATABASE_PATH  # if set; otherwise assume ./titan_core.db
```

---

## Severity Assessment

| Condition | Severity | Action |
|-----------|----------|--------|
| Single failed write, DB still accessible | Low | Restart; check lock contention |
| `database disk image is malformed` error | High | Stop immediately; assess corruption scope |
| `titan_core.db` file missing | High | Restore from backup or reinitialise |
| All write operations failing for > 5 min | P1 | Follow full recovery procedure |

---

## Immediate Actions

### 1 — Stop TITAN OS

```bash
# Kill the running process to prevent further writes to a potentially corrupt DB
pkill -f "python main.py" || pkill -f "python -m titan"
```

### 2 — Check database integrity

```bash
sqlite3 titan_core.db "PRAGMA integrity_check;"
# Expected output: "ok"
# If output contains errors: proceed to Step 3 (recovery)
```

### 3 — Check if WAL file is present and needs recovery

```bash
ls -la titan_core.db-wal titan_core.db-shm 2>/dev/null
# If WAL file exists and is non-empty, SQLite may recover automatically on next open
sqlite3 titan_core.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 titan_core.db "PRAGMA integrity_check;"
```

---

## Recovery Procedures

### Scenario A — Integrity check passes after WAL recovery

1. Restart TITAN OS: `python main.py`
2. Monitor first sync and governance run for errors.
3. No further action required.

### Scenario B — Corruption detected; backup available

```bash
# Stop TITAN OS (Step 1 above)
# Locate backup
ls ~/Documents/TITAN/backups/titan_core.db.*

# Restore most recent backup
cp ~/Documents/TITAN/backups/titan_core.db.YYYYMMDD titan_core.db

# Verify integrity of restored backup
sqlite3 titan_core.db "PRAGMA integrity_check;"

# Restart
python main.py
```

**Note:** Data written between the backup date and the corruption event will be lost.
Re-sync Garmin data to repopulate `daily_metrics` and `training_log` for the gap period.

### Scenario C — Corruption detected; no backup available

```bash
# Attempt SQLite dump-and-restore (recovers uncorrupted pages)
sqlite3 titan_core.db ".dump" > titan_dump.sql 2>&1

# Review dump for error markers
grep -i "error\|corrupt\|malformed" titan_dump.sql

# Recreate DB from dump (omit corrupt rows)
mv titan_core.db titan_core.db.corrupt
sqlite3 titan_new.db < titan_dump.sql
sqlite3 titan_new.db "PRAGMA integrity_check;"
mv titan_new.db titan_core.db
```

Rows from corrupt pages will be missing. Inspect the output and note which tables and
date ranges are affected. Partial loss of `training_log` is recoverable via Garmin
re-sync. Loss of `governance_outcomes` is permanent (calibration history will restart).

### Scenario D — DB file missing entirely

```bash
# Reinitialise the database (tables recreated from schema on first startup)
python main.py
# TITAN OS will create a fresh titan_core.db with empty tables
# All historical data is lost; re-sync Garmin to populate training_log and daily_metrics
```

---

## Backup Procedure

Automated: `titan-worker` calls `DatabaseManager.backup_database(keep=7)` at each cycle start (every 24 h). No cron setup required in Docker deployments.

Manual on-demand:

```bash
bash scripts/backup.sh [data_dir]
```

---

## Backup Verification

Before restoring, verify the backup file is not corrupt:

```bash
# Verify latest backup integrity
python3 scripts/verify_backup.py ~/Documents/TITAN
# Exit 0 = OK
# Exit 1 = corrupt — restore an earlier backup
```

The script prints the backup path and file size on success.
If it fails, try the next most-recent file in `~/Documents/TITAN/backups/`.

---

## Post-Recovery Checklist

- [ ] `PRAGMA integrity_check` returns `ok`
- [ ] TITAN OS starts without database errors
- [ ] First Garmin sync completes with non-zero result
- [ ] Governance pipeline runs and produces a `GovernanceDecision` (not degraded mode)
- [ ] Operator Console shows recent session data
- [ ] Incident logged if data loss occurred
- [ ] Backup procedure confirmed active

---

## Related

- ADR-0020 — Persistence Failure Behavioral Policy (degraded-conservative mode)
- ADR-0015 — SQLite Retention Strategy
- ADR-0044 — PostgreSQL migration (Phase 8A — will supersede this runbook for production)
- `docs/SLO.md` — SLO-04 (Database Write Availability)
- `titan/core/database.py`
