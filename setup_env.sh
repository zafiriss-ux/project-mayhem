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

# ── Project venv setup ────────────────────────────────────────────────────────
setup_project_venv() {
  echo "[setup] Setting up project venv..."
  if [ ! -f ".venv/bin/activate" ]; then
    python -m venv .venv
  fi
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
  if [ -f requirements-dev.txt ]; then
    .venv/bin/pip install --quiet -r requirements-dev.txt
  fi
  .venv/bin/pip install --quiet pytest pytest-cov
  .venv/bin/pip install --quiet "import-linter>=2.1"
  .venv/bin/pip install --quiet "schemathesis==4.15.2"
  echo "[setup] Project venv ready: $(.venv/bin/python --version)"
}

echo "=== TITAN OS Environment Bootstrap ==="
echo "[1/3] Installing system-level dependencies (best-effort)..."
pip install -r requirements.txt -q || true
pip install -r requirements-dev.txt -q || true
echo "[2/3] Setting up project venv..."
setup_project_venv
echo "[3/3] Verifying collection..."
errors=$(.venv/bin/pytest --collect-only -q --no-cov 2>&1 | grep "^ERROR" | wc -l)
if [ "$errors" -gt 0 ]; then
  echo "FAIL: $errors collection error(s) remain:"
  .venv/bin/pytest --collect-only -q --no-cov 2>&1 | grep "^ERROR"
  exit 1
fi
echo "OK: zero collection errors."
echo "=== Bootstrap complete ==="
