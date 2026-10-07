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
| `titan-worker` | Background daemon (Garmin sync, Telegram, morning routine) |

## Data

Named volume `titan-data` → `/data/titan_core.db` (SQLite, WAL mode).

Worker advisory lock: `/data/worker.lock` — prevents duplicate workers on restart. The file holds the PID of the running worker. The kernel releases the lock when that process dies, so a crashed worker never blocks the next start.

Worker health (INV-23): the worker writes `/data/worker.heartbeat` every 60 s. `docker compose ps` shows `titan-worker` as unhealthy once the heartbeat is older than 120 s: the loop has stopped, the scheduler thread could not be restarted, or the morning routine has run past `WORKER_ROUTINE_BUDGET_S` (30 min, logged as CRITICAL `worker_routine_overrun`). Check it by hand with `docker compose exec titan-worker python scripts/worker_healthcheck.py`. Plain Docker Compose reports unhealthy but does not restart the container.

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

- Set `TELEGRAM_BOT_TOKEN` in `.env`
- `docker compose up -d titan-worker`
- Send `/start` to bot — verify response within 30s

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
