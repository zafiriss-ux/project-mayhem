#!/usr/bin/env bash
# TITAN OS — Deterministic environment setup for Codex Cloud sandboxes.
# Run this once at the start of every cloud task before any test or lint command.
# Safe to run multiple times (idempotent).
set -euo pipefail

# ── Python version guard ──────────────────────────────────────────────────────
PY_MINOR=$(python -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  echo "ERROR: TITAN OS requires Python 3.11+. Found: $(python --version)"
  echo "Switch to Python 3.11 before running setup_env.sh."
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
