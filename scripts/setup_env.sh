#!/usr/bin/env bash
# TITAN OS — Deterministic environment setup for Codex Cloud sandboxes.
# Run this once at the start of every cloud task before any test or lint command.
# Safe to run multiple times (idempotent).
set -euo pipefail

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
