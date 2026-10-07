# ── base ─────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base
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
# `python scripts/run_api.py` puts /app/scripts, not /app, on sys.path.
ENV PYTHONPATH=/app

# Create non-root user and writable data + backup volumes (backups: AGENTS DR-01)
RUN groupadd -r titan && \
    useradd -r -g titan --home /app titan && \
    chown -R titan:titan /app && \
    mkdir -p /data /backups && \
    chown titan:titan /data /backups

# ── api ──────────────────────────────────────────────────────────────────────
FROM base AS api

# titan home is /app; FileChannel writes to /app/Documents/TITAN
RUN mkdir -p /app/Documents/TITAN && chown -R titan:titan /app/Documents/TITAN

USER titan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/readyz || exit 1

CMD ["python", "scripts/run_api.py"]

# ── worker ───────────────────────────────────────────────────────────────────
FROM base AS worker

USER titan

CMD ["python", "-m", "titan.worker"]
