#!/usr/bin/env bash
# TITAN OS — Load Test Runner
# Starts Docker, runs load tests, tears down.
# Usage: bash scripts/load_test_runner.sh
# Requires: Docker daemon running

set -euo pipefail

API_URL="http://localhost:8000"  # DevSkim: ignore DS162092
RESULTS="/tmp/titan_load_results.json"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Start API container if not running
if ! curl -sf "$API_URL/health" > /dev/null 2>&1; then
    log "Starting titan-api..."
    docker compose up -d titan-api
    sleep 10
    curl -sf "$API_URL/health" || { log "API failed to start"; exit 1; }
fi
log "API ready"

# Run load tests
python3 scripts/load_test.py \
    --url "$API_URL" \
    --json-output "$RESULTS"

EXIT_CODE=$?
cat "$RESULTS" 2>/dev/null || true

if [ $EXIT_CODE -eq 0 ]; then
    log "✅ ALL LOAD TESTS PASSED"
else
    log "❌ LOAD TEST SLO VIOLATIONS"
fi
exit $EXIT_CODE
