# ADR-0057: Docker API Deployment

**Status:** ACCEPTED
**Accepted:** 2026-06-07 (Phase 26 close)

## Context

B4 — The current Dockerfile ENTRYPOINT launches the TUI (`python3 -m titan`). The FastAPI server is not reachable from the container, making the REST API inaccessible in production deployments. Two execution modes are needed: an API server and a background worker (DailyCoach pipeline).

## Decision

PENDING — requires architect review.

## Options

**A: Single container** — `uvicorn` serves FastAPI; background worker runs via threads inside the same process.

**B: Two containers (API + Worker)** — Separate containers share a volume-mounted SQLite database. API container runs `uvicorn titan.api.main:app`. Worker container runs the DailyCoach morning pipeline on schedule.

## Gate

This ADR must be accepted before any Phase 18 Docker work begins. Relevant debt item: TD-NEW-04 (Opus audit 2026-05-22).
