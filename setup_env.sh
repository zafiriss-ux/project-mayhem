#!/usr/bin/env bash
# TITAN OS — Environment Bootstrap
# Usage: bash setup_env.sh
# AGENTS.md §2 (Environment First)
set -e

# ── Python 3.11 activation via pyenv (if available) ──────────────────────────
if command -v pyenv &>/dev/null; then
  PY311=$(pyenv versions --bare 2>/dev/null | grep "^3\.11\." | sort -V | tail -1)
  if [ -n "$PY311" ]; then
    pyenv local "$PY311"
    hash -r
    echo "pyenv: activated Python $PY311"
  else
    echo "WARNING: pyenv found but no 3.11.x version installed."
    echo "Run: pyenv install 3.11.14"
  fi
fi

# ── Python version guard ──────────────────────────────────────────────────────
PY_MAJOR=$(python -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  echo "ERROR: TITAN OS requires Python 3.11+. Found: $(python --version)"
  echo "Fix: pyenv install 3.11.14 && pyenv local 3.11.14"
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
