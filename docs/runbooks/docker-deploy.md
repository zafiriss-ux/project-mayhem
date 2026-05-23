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

Worker advisory lock: `/data/worker.lock` — prevents duplicate workers on restart.

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
