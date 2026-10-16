# TITAN OS — Docker Setup

## Quick start (5 minutes)

### Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Your `.env` file configured (see `docs/DEPLOYMENT_GUIDE.md`)

### Start TITAN in Docker

```bash
# Build and start
docker-compose up -d

# Check it's running
docker-compose ps
docker-compose logs -f titan-api      # ή titan-worker

# Stop
docker-compose down
```

## Data persistence

All data (`titan_core.db`, `.garth_token`) is stored in the `titan-data` Docker volume.
Backups go to the separate `titan-backups` volume.

```bash
docker volume inspect titan-data
```

## Backup

The `titan-worker` takes a verified backup every day (`/backups/titan_YYYY-MM-DD.db` on the
`titan-backups` volume, 7 daily + 4 weekly). Checking, restoring and copying a backup off the
machine: [`RUNBOOK_DR.md`](RUNBOOK_DR.md).

## Environment variables

Edit your `.env` file, then restart:

```bash
docker-compose up -d
```

## Upgrade

```bash
git pull
docker-compose build --no-cache
docker-compose up -d
```

## Switch back to native (no Docker)

```bash
python -m titan
```

Data lives in the Docker volume — export it first if needed.
