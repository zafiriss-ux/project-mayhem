# Runbook — Database Recovery

**Version:** 1.1
**Date:** 2026-05-24
**Owner:** Engineering
**Trigger:** SQLite corruption, accidental deletion, DailyCoach degraded-conservative mode, or failed write detected in logs

---

## Backup Location

Automated daily backups are taken only by the Docker `titan-worker`, at startup and once a day: at
07:00 UTC with only the owner, on the first round of the UTC day (about 00:00) with
`TITAN_MULTI_ATHLETE=1`. Local mode (launcher or `python -m titan`) takes no automatic backups.

- **Container:** `/backups/titan_YYYY-MM-DD.db` on the `titan-backups` volume (`TITAN_BACKUP_DIR=/backups`)
- **Retention:** 7 daily + 4 weekly (`BACKUP_RETENTION_DAILY_DAYS`, `BACKUP_RETENTION_WEEKLY_COUNT` in `.env`)
- Full Docker procedure: [`docs/RUNBOOK_DR.md`](../RUNBOOK_DR.md)

Manual on-demand backup:

```bash
bash scripts/backup.sh [data_dir]
# Default data_dir: ~/Documents/TITAN
# Creates: <data_dir>/backups/titan_core.db.YYYYMMDD
```

---

## Recovery Procedure

### From automated backup (Docker)

The backups live in the `titan-backups` volume, not on the host. Follow «Επαναφορά (Docker)» in
[`docs/RUNBOOK_DR.md`](../RUNBOOK_DR.md): it lists the backups, checks the chosen one with
`scripts/restore_drill.py`, keeps the current file as `titan_core.db.before-restore` and restarts.

---

## Symptoms

- Application log contains `persistence_failure` or `database_error` structured event
- `DailyCoach` emits a "degraded conservative mode" Telegram message (ADR-0020)
- `sqlite3.DatabaseError: database disk image is malformed`
- Operator Console shows missing or zero entries for recent sessions

---

## Database Location

Path: `titan_core.db` in the data directory — `/data/titan_core.db` in Docker,
`~/Documents/TITAN/titan_core.db` locally. There is no environment variable that moves it.

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
# The checkpoint below changes the damaged file. If you may restore a backup, first keep the
# damaged database with its -wal/-shm (the first three lines of Scenario B).
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

# Keep the damaged database WITH its -wal/-shm: the last writes may exist only in the -wal
cp titan_core.db titan_core.db.before-restore
[ -f titan_core.db-wal ] && cp titan_core.db-wal titan_core.db.before-restore-wal
[ -f titan_core.db-shm ] && cp titan_core.db-shm titan_core.db.before-restore-shm  # informational; SQLite rebuilds it

# Remove the old -wal/-shm, otherwise SQLite replays them on top of the backup (RC-02)
rm -f titan_core.db-wal titan_core.db-shm

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

Automated: `titan-worker` calls `DatabaseManager.backup_database(keep=7, keep_weekly=4)` at each cycle start (startup, then once a UTC day: 07:00 with only the owner, the first round of the day with `TITAN_MULTI_ATHLETE=1`), with the values from `.env`. No cron setup required in Docker deployments.

Manual on-demand:

```bash
bash scripts/backup.sh [data_dir]
```

---

## Backup Verification

Before restoring, verify the backup file is not corrupt:

```bash
# Worker backups (titan_YYYY-MM-DD.db), Docker
docker compose run --rm --no-deps titan-worker python scripts/restore_drill.py
# Exit 0 = OK, exit 1 = failed — try an earlier backup

# Manual backups from scripts/backup.sh (titan_core.db.YYYYMMDD) only
python3 scripts/verify_backup.py ~/Documents/TITAN
```

`verify_backup.py` looks only for `titan_core.db.*` files, so it does not see the worker's
backups. If a check fails, try the next most-recent file.

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
