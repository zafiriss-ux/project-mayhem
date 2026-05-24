#!/usr/bin/env bash
# TITAN OS — Docker Smoke Test (Tier 2 validation)
# Usage: bash scripts/docker_smoke_test.sh
# Requires: Docker daemon running, repo root as working directory

set -euo pipefail

# Ensure .env exists before any grep checks
touch .env

# Auto-generate JWT keys if missing
if ! grep -q "TITAN_JWT_PRIVATE_KEY" \
    .env 2>/dev/null; then
  echo "[$(date +%H:%M:%S)] Generating JWT keys..."
  bash scripts/generate_jwt_keys.sh
fi

COMPOSE="docker compose"
API_URL="http://localhost:8000"
TIMEOUT=60

log()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { log "FAIL: $*"; $COMPOSE down -v 2>/dev/null || true; exit 1; }

# ── 1. Build + start ──────────────────────────────────────────────────────────
log "Building containers..."
$COMPOSE build --quiet

log "Starting services..."
$COMPOSE up -d

# ── 2. Wait for API /health ───────────────────────────────────────────────────
log "Waiting for API (timeout ${TIMEOUT}s)..."
elapsed=0
until curl -sf "$API_URL/health" > /dev/null 2>&1; do
    sleep 2; elapsed=$((elapsed + 2))
    [ $elapsed -ge $TIMEOUT ] && \
        fail "/health did not respond in ${TIMEOUT}s"
done
log "✅ /health OK"

# ── 3. /readyz check ─────────────────────────────────────────────────────────
READY=$(curl -sf "$API_URL/readyz" 2>/dev/null || echo "{}")
echo "$READY" | grep -q '"ready":true' || \
    fail "/readyz returned not-ready: $READY"
log "✅ /readyz OK: $READY"

# ── 4. Verify titan_core.db (not titan.db) ───────────────────────────────────
$COMPOSE exec -T titan-api test -f /data/titan_core.db || \
    fail "titan_core.db not found in volume"
$COMPOSE exec -T titan-api bash -c \
    "[ ! -f /data/titan.db ] || (echo 'stale titan.db found' && exit 1)" || \
    fail "stale titan.db exists in volume"
log "✅ DB file: titan_core.db only"

# ── 5. Worker lock file + startup event ──────────────────────────────────────
sleep 5  # give worker time to acquire lock
$COMPOSE exec -T titan-worker test -f /data/worker.lock || \
    fail "worker.lock not found — worker not running"
log "✅ worker.lock present"

WORKER_LOG=$($COMPOSE logs titan-worker 2>&1 | grep "worker_started" || true)
if [ -z "$WORKER_LOG" ]; then
    log "⚠️  WARN: worker_started event not found in logs — worker may be stub"
else
    log "✅ worker_started confirmed"
fi

# ── 6. Persistence test ───────────────────────────────────────────────────────
log "Testing volume persistence..."
$COMPOSE exec -T titan-api python3 -c "
import sys; sys.path.insert(0, '.')
import os
os.environ['TITAN_DATA_DIR'] = '/data'
from titan.core.database import DatabaseManager
db = DatabaseManager('titan_core.db')
db.conn.execute(
    \"INSERT OR IGNORE INTO sync_metadata (date, activity_count, weight_count, \
sleep_count, hrv_count, status) VALUES ('smoke_test_marker', 0, 0, 0, 0, 'smoke_test')\")
db.conn.commit()
print('marker written')
"

$COMPOSE restart titan-api
sleep 5

elapsed=0
until curl -sf "$API_URL/health" > /dev/null 2>&1; do
    sleep 2; elapsed=$((elapsed + 2))
    [ $elapsed -ge 30 ] && fail "API did not recover after restart"
done

$COMPOSE exec -T titan-api python3 -c "
import sys; sys.path.insert(0, '.')
import os
os.environ['TITAN_DATA_DIR'] = '/data'
from titan.core.database import DatabaseManager
db = DatabaseManager('titan_core.db')
row = db.conn.execute(
    \"SELECT status FROM sync_metadata WHERE date='smoke_test_marker'\").fetchone()
assert row and row[0] == 'smoke_test', \
    f'Persistence FAILED — marker lost (got {row})'
print('Persistence OK')
"
log "✅ Persistence after restart: OK"

# ── 7. Degraded readiness simulation ─────────────────────────────────────────
log "Simulating degraded readiness (worker stop)..."
$COMPOSE stop titan-worker
HEALTH=$(curl -sf "$API_URL/health" 2>/dev/null || echo "down")
echo "$HEALTH" | grep -q "ok" || \
    fail "API down after worker stop"
log "✅ API survives worker failure"

$COMPOSE start titan-worker
sleep 3

# ── 8. Teardown ───────────────────────────────────────────────────────────────
log "Tearing down..."
# Safety: never nuke volumes in production
if [ "${TITAN_ENV:-}" = "production" ]; then
    log "⚠️  PROD env detected — skipping volume teardown"
    $COMPOSE down
else
    $COMPOSE down -v  # -v removes volume
fi

log ""
log "══════════════════════════════════"
log "✅ ALL SMOKE TESTS PASSED"
log "══════════════════════════════════"
