#!/usr/bin/env bash
# TITAN OS — Deterministic environment setup for Codex Cloud sandboxes.
# Run this once at the start of every cloud task before any test or lint command.
# Safe to run multiple times (idempotent).
set -euo pipefail

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

echo "==> Upgrading pip"
python -m pip install --upgrade pip --quiet

echo "==> Installing runtime dependencies"
pip install -r requirements.txt -c constraints.txt --quiet

echo "==> Installing dev/test dependencies"
pip install -r requirements-dev.txt --quiet

echo "==> Verifying key tools"
python -c "import pytest; import ruff" 2>/dev/null || pip install pytest pytest-cov ruff --quiet

echo "==> Environment ready"
echo "    Python: $(python --version)"
echo "    pytest: $(python -m pytest --version)"
echo "    ruff:   $(ruff --version)"
