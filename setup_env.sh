#!/usr/bin/env bash
# TITAN OS — Environment Bootstrap
# Usage: bash setup_env.sh
# AGENTS.md §2 (Environment First)
set -e
echo "=== TITAN OS Environment Bootstrap ==="
echo "[1/2] Installing dependencies..."
pip install -r requirements.txt -q
pip install -r requirements-dev.txt -q
echo "[2/2] Verifying collection..."
errors=$(python -m pytest --collect-only -q 2>&1 | grep "^ERROR" | wc -l)
if [ "$errors" -gt 0 ]; then
  echo "FAIL: $errors collection error(s) remain:"
  python -m pytest --collect-only -q 2>&1 | grep "^ERROR"
  exit 1
fi
echo "OK: zero collection errors."
echo "=== Bootstrap complete ==="
