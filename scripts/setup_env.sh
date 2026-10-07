#!/usr/bin/env bash
# TITAN OS — Deterministic environment setup for Codex Cloud sandboxes.
# Run this once at the start of every cloud task before any test or lint command.
# Safe to run multiple times (idempotent).
set -euo pipefail

install_runtime_dependencies() {
  if pip install -r requirements.txt --quiet; then
    return 0
  fi

  echo "WARNING: Runtime dependency install failed on the first attempt."

  if [ -n "${PIP_INDEX_URL:-}" ]; then
    echo "ERROR: PIP_INDEX_URL is set to '$PIP_INDEX_URL' and install still failed."
    echo "Fix your proxy/index and rerun scripts/setup_env.sh"
    return 1
  fi

  echo "Retrying runtime dependency install against public PyPI..."
  PIP_INDEX_URL="https://pypi.org/simple" \
  PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org" \
    pip install -r requirements.txt --quiet
}

# ── Python 3.12 activation via pyenv (if available) ──────────────────────────
if command -v pyenv &>/dev/null; then
  PY312=$(pyenv versions --bare 2>/dev/null | grep "^3\.12\." | sort -V | tail -1)
  if [ -n "$PY312" ]; then
    pyenv local "$PY312"
    hash -r
    echo "pyenv: activated Python $PY312"
  else
    echo "WARNING: pyenv found but no 3.12.x version installed."
    echo "Run: pyenv install 3.12"
  fi
fi

# ── Python version guard ──────────────────────────────────────────────────────
PY_MAJOR=$(python -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
  echo "ERROR: TITAN OS requires Python 3.12+. Found: $(python --version)"
  echo "Fix: pyenv install 3.12 && pyenv local 3.12"
  exit 1
fi
echo "Python $(python --version) — OK"

echo "==> Upgrading pip"
python -m pip install --upgrade pip --quiet

echo "==> Installing runtime dependencies"
install_runtime_dependencies

echo "==> Installing dev/test dependencies"
pip install -r requirements-dev.txt --quiet

echo "==> Verifying key tools"
python -c "import pytest; import ruff" 2>/dev/null || pip install pytest pytest-cov ruff --quiet

echo "==> Installing mutation testing tooling (T5-84)"
pip install mutmut==3.5.0 --quiet

echo "==> Environment ready"
echo "    Python: $(python --version)"
echo "    pytest: $(python -m pytest --version)"
echo "    ruff:   $(ruff --version)"
