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
docker-compose logs -f titan

# Stop
docker-compose down
```

## Data persistence

All data (`titan.db`, `.garth_token`) is stored in the `titan-data` Docker volume.

```bash
docker volume inspect titan-data
```

## Backup

```bash
docker run --rm \
  -v titan-data:/data \
  -v $(pwd):/backup \
  python:3.11-slim \
  cp /data/titan.db /backup/titan_backup_$(date +%Y%m%d).db
```

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
