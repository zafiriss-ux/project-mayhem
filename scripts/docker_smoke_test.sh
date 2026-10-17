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
API_URL="http://localhost:8000"  # DevSkim: ignore DS162092
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

# ── 5b. Two athletes besides the owner (Phase 4 step 10, ADR-0067) ──────────
# Zaf adds them with scripts/athletes.py on the worker's volume. Without Garmin and
# consent they are not ready: the worker's readiness check says why, and nothing is
# claimed or written for them (D4.2, D7.1).
log "Adding two athletes..."
add_athlete() {  # name, Telegram chat id, city
    $COMPOSE exec -T titan-worker sh -c "cat > /tmp/smoke_profile.json" <<JSON
{"birth_date": "1990-05-01", "sex": "F", "weight_kg": 58, "height_cm": 165, "max_hr": 190,
 "threshold_hr": 172, "training_phase": "BASE", "training_goal": "10K",
 "location_city": "$3", "location_country": "GR"}
JSON
    $COMPOSE exec -T titan-worker python scripts/athletes.py add \
        --name "$1" --profile /tmp/smoke_profile.json --chat "$2" > /dev/null || \
        fail "athletes.py add $1 failed"
}
add_athlete "Smoke A" 900001 Larissa
add_athlete "Smoke B" 900002 Patras

count_athletes() {
    $COMPOSE exec -T titan-worker python scripts/athletes.py list | grep -c "consent=no" || true
}
[ "$(count_athletes)" = "2" ] || fail "athletes.py list does not show the two athletes"
log "✅ Two athletes added"

$COMPOSE exec -T titan-worker python3 - <<'PY' || fail "readiness check of the two athletes failed"
import sys; sys.path.insert(0, '.')
from pathlib import Path
from titan import worker
from titan.config.settings import get_settings
from titan.core.database import DatabaseManager
db = DatabaseManager(db_dir=Path(get_settings().TITAN_DATA_DIR))
others = [a for a in db.list_athletes_in_order() if a != 'owner']
assert len(others) == 2, others
for athlete_id in others:
    problem = worker._readiness_problem(db, athlete_id)
    assert problem == 'consent: none current', (athlete_id, problem)
claimed = db.conn.execute(
    "SELECT COUNT(*) FROM worker_routine_executions WHERE athlete_id != 'owner'").fetchone()[0]
assert claimed == 0, claimed
print('two athletes, both waiting for consent, nothing claimed for them')
PY
log "✅ Both athletes not ready (consent), nothing claimed for them"

# Runbook docs/runbooks/multi-athlete.md: the token key lives on titan-secrets (Phase 4 step 11).
$COMPOSE exec -T titan-worker python scripts/athletes.py new-key > /dev/null || \
    fail "athletes.py new-key failed"
log "✅ Athletes' token key written to /secrets"

# ── 6. Persistence test ───────────────────────────────────────────────────────
log "Testing volume persistence..."
$COMPOSE exec -T titan-api python3 -c "
import sys; sys.path.insert(0, '.')
import os
os.environ['TITAN_DATA_DIR'] = '/data'
from titan.core.database import DatabaseManager
db = DatabaseManager('titan_core.db')
db.conn.execute(
    \"INSERT OR IGNORE INTO sync_metadata (athlete_id, source, last_sync_ok, last_error_class) \
VALUES ('owner', 'smoke_test_marker', 0, 'smoke_test')\")
db.conn.commit()
print('marker written')
"

# T-PRA-29: restart both containers, not only the API.
$COMPOSE restart
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
    \"SELECT last_error_class FROM sync_metadata WHERE athlete_id='owner' AND source='smoke_test_marker'\").fetchone()
assert row and row[0] == 'smoke_test', \
    f'Persistence FAILED — marker lost (got {row})'
print('Persistence OK')
"
log "✅ Persistence after restart: OK"

[ "$(count_athletes)" = "2" ] || fail "the two athletes did not survive the restart"
log "✅ Two athletes after restart"

# The key survived the restart and is never replaced; one athlete is exported and removed,
# and the deletion record is on titan-secrets (runbook, Phase 4 step 11; ADR-0067 D6).
if $COMPOSE exec -T titan-worker python scripts/athletes.py new-key > /dev/null 2>&1; then
    fail "athletes.py new-key replaced the key after the restart"
fi
log "✅ Token key kept after restart"
SMOKE_B=$($COMPOSE exec -T titan-worker python scripts/athletes.py list | grep "Smoke B" | cut -d" " -f1)
[ -n "$SMOKE_B" ] || fail "Smoke B not found in athletes.py list"
$COMPOSE exec -T titan-worker python scripts/athletes.py export "$SMOKE_B" --out /tmp/smoke_b.json > /dev/null || \
    fail "athletes.py export failed"
$COMPOSE exec -T titan-worker python scripts/athletes.py remove "$SMOKE_B" --yes > /dev/null || \
    fail "athletes.py remove failed"
[ "$(count_athletes)" = "1" ] || fail "athletes.py remove left Smoke B in the list"
$COMPOSE exec -T titan-worker grep -q "$SMOKE_B" /secrets/deletions.jsonl || \
    fail "the deletion record does not name Smoke B"
$COMPOSE exec -T titan-worker python scripts/athletes.py reapply-deletions > /dev/null || \
    fail "athletes.py reapply-deletions failed"
log "✅ One athlete exported and removed, deletion recorded outside the data"

[ -n "$($COMPOSE ps --status running -q titan-worker)" ] || \
    fail "worker not running after restart"
log "✅ Worker running after restart"

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
