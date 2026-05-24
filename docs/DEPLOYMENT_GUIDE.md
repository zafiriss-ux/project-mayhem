> ⚠️ CANONICAL DEPLOYMENT: Docker.
> See docs/runbooks/docker-deploy.md
> This guide describes LOCAL DEV ONLY.
> Database path: titan_core.db
> (NOT titan.db — that file is stale)

# TITAN OS — Local Development Guide

For the canonical Docker deployment, see [`docs/runbooks/docker-deploy.md`](runbooks/docker-deploy.md).

## Quick Start (Local Dev Only)

```bash
pip install -r requirements.txt
python launcher/main.py
```

## Database

- Docker: `/data/titan_core.db`
- Local: `~/Documents/TITAN/titan_core.db`
- **NEVER** use `titan.db` — that file is stale and must not be referenced in any runbook or script.
