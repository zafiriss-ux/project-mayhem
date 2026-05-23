# ── base ─────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base
LABEL org.opencontainers.image.title="TITAN OS"
LABEL org.opencontainers.image.description="Athletic Training Intelligence System"

WORKDIR /app

# Εγκατάσταση curl (για healthcheck) — μία φορά, σωστά
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Requirements (μία φορά)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Κώδικας (μία φορά)
COPY . .

ENV TITAN_DATA_DIR=/data
ENV TITAN_DB_BACKEND=sqlite

# ── api ──────────────────────────────────────────────────────────────────────
FROM base AS api

RUN mkdir -p /home/appuser/Documents/TITAN && chmod 777 /home/appuser/Documents/TITAN

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-c", "from pathlib import Path; from titan.core.database import DatabaseManager; from titan.api.main import create_app; import uvicorn; db = DatabaseManager(db_dir=Path('/data')); app = create_app(db=db); uvicorn.run(app, host='0.0.0.0', port=8000)"]

# ── worker ───────────────────────────────────────────────────────────────────
FROM base AS worker
CMD ["python", "-m", "titan.worker"]
