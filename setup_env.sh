#!/usr/bin/env bash
# TITAN OS — Environment Bootstrap
# Usage: bash setup_env.sh
# AGENTS.md §2 (Environment First)
set -e

# ── Python version guard ──────────────────────────────────────────────────────
PY_MINOR=$(python -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  echo "ERROR: TITAN OS requires Python 3.11+. Found: $(python --version)"
  echo "Switch to Python 3.11 before running setup_env.sh."
  exit 1
fi
echo "Python $(python --version) — OK"

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
