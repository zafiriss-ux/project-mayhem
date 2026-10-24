# TITAN OS — Docker Deployment

Architecture: two containers sharing a named volume (`titan-data`). See ADR-0057.

## Quick start

```bash
docker compose up --build -d
```

## Services

| Service | Description |
|---------|-------------|
| `titan-api` | FastAPI/uvicorn — `http://localhost:8000` |
| `titan-worker` | Background daemon (Garmin sync, sending Telegram messages, morning routine; on Sunday the weekly plan, stored in `weekly_plans`, D-020; athletes' deletions re-applied at start and the 30-day purge after `/stop`, ADR-0067). With `TITAN_MULTI_ATHLETE=1` it also answers the athletes' Telegram commands (`/consent`, `/agree`, `/sync`, `/stop`, D-103); otherwise it answers no commands |

## Data

Named volume `titan-data` → `/data/titan_core.db` (SQLite, WAL mode).

Named volume `titan-secrets` → `/secrets` on `titan-worker` only: the athletes' Garmin token key
(`TITAN_TOKEN_KEY_FILE`, written once by `python scripts/athletes.py new-key`) and the deletion record
(`TITAN_DELETION_RECORD_FILE`). It is kept apart from `titan-data` and `titan-backups`, so a copy of
the data cannot decrypt the tokens and a restored backup cannot bring back a deleted athlete
(ADR-0067 D6.3, D9.2). `docker compose down -v` deletes it too. Athletes: [`multi-athlete.md`](multi-athlete.md).

Worker advisory lock: `/data/worker.lock` — prevents duplicate workers on restart. The file holds the PID of the running worker. The kernel releases the lock when that process dies, so a crashed worker never blocks the next start.

Worker health (INV-23): the worker writes `/data/worker.heartbeat` every 60 s. `docker compose ps` shows `titan-worker` as unhealthy once the heartbeat is older than 120 s: the loop has stopped, the scheduler thread could not be restarted, or, with only the owner, the morning routine has run past `WORKER_ROUTINE_BUDGET_S` (30 min, logged as CRITICAL `worker_routine_overrun`). With `TITAN_MULTI_ATHLETE=1` an athlete's attempt that runs past the budget is stopped instead (`worker_routine_killed`) and the worker stays healthy. Check it by hand with `docker compose exec titan-worker python scripts/worker_healthcheck.py`. Plain Docker Compose reports unhealthy but does not restart the container.

## Logs

```bash
docker compose logs -f titan-api
docker compose logs -f titan-worker
```

## Restart worker only

```bash
docker compose restart titan-worker
```

## Update

```bash
git pull
docker compose up --build -d
```

This builds from the checkout (development). Production runs tagged images instead: `docker compose -f docker-compose.yml -f docker-compose.release.yml up -d` with `TITAN_VERSION` set (AGENTS RE-02/RE-04). Upgrade and rollback steps: `docs/RUNBOOK_ROLLBACK.md`.

## Validation

### Automated smoke test (requires Docker)

```bash
bash scripts/docker_smoke_test.sh
```

Expected: `ALL SMOKE TESTS PASSED`

### Manual validation checklist

After `docker compose up -d`:

- [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `curl http://localhost:8000/readyz` → `{"ready":true,...}`
- [ ] `docker compose exec titan-worker ls /data/worker.lock` → file exists
- [ ] `docker compose exec titan-api ls /data/titan_core.db` → file exists (NOT `titan.db`)
- [ ] `docker compose stop titan-worker && curl http://localhost:8000/health` → still 200 (API independent)
- [ ] `docker compose start titan-worker` → worker recovers

### Telegram (manual, needs credentials)

- Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. If `TELEGRAM_CHAT_ID` is a group (a
  negative id), also set `TELEGRAM_OWNER_USER_ID` to the owner's own user id: in a group only the
  owner's messages are commands, and without it no group message is (M0-33, D-150).
- `docker compose up -d titan-worker`
- With one athlete the worker only sends messages; owner commands such as `/today` need local
  mode, `python -m titan`. With `TITAN_MULTI_ATHLETE=1` the worker listens (log line
  `command_listener_started`): athletes get their commands, and owner commands answer "not ready".
  Never run `python -m titan` with the same bot token at the same time (Telegram 409).
  Check that the 07:00 UTC morning message arrives.

### Morning routine (manual)

```bash
docker compose exec titan-worker python3 -c "
from titan.orchestration.daily_coach import DailyCoach
print('DailyCoach OK')
"
```

## Troubleshooting

**API not responding**

```bash
docker compose ps
# Check health status — should show "healthy"
```

**Worker not syncing**

```bash
docker compose exec titan-worker ls -la /data/worker.lock
# Lock file present = worker is running
```

**SQLite busy errors**

`PRAGMA busy_timeout` is set to 5000 ms in `DatabaseManager.__init__`. If busy
errors persist, check that only `titan-worker` is performing writes (API is
read-mostly by contract per ADR-0057 M1).

**Duplicate worker on restart**

The advisory lock (`worker.lock`) is released automatically when the process
exits. A crashed worker always releases the lock; `docker restart` picks it up
cleanly.
