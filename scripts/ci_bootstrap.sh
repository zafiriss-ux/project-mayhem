#!/usr/bin/env bash
# =============================================================================
# TITAN OS — Local CI Bootstrap
# One-time setup for the uv-managed pytest environment on Ubuntu/Linux.
# Run this once after a clean clone or Ubuntu install before scripts/titan_ci.sh
#
# Prerequisites:
#   uv installed (https://docs.astral.sh/uv/getting-started/installation/)
#   ruff installed (uv tool install ruff, or pip install ruff)
#
# Usage:
#   bash scripts/ci_bootstrap.sh
#   bash scripts/titan_ci.sh   # verify green
# =============================================================================
set -euo pipefail

echo "═══ TITAN OS CI Bootstrap ═══"
echo "Date: $(date '+%Y-%m-%d')"
echo ""

echo "Installing uv-managed pytest environment with all required dependencies..."

uv tool install "pytest==9.0.3" \
  --with "freezegun==1.5.5" \
  --with "hypothesis==6.152.7" \
  --with "pytest-timeout==2.4.0" \
  --with "garminconnect==0.3.2" \
  --with "requests==2.34.2" \
  --with "sqlalchemy==2.0.49" \
  --with "alembic==1.18.4" \
  --with "fastapi==0.136.1" \
  --with "uvicorn==0.34.3" \
  --with "pyjwt[crypto]==2.13.0" \
  --with "bcrypt==5.0.0" \
  --with "cryptography==48.0.0" \
  --with "prometheus-client==0.21.0" \
  --with "httpx==0.28.1" \
  --with "schemathesis==4.18.5" \
  --with "pytest-cov==7.1.0" \
  --with "pytelegrambotapi==4.33.0" \
  --with "mutmut==3.5.0" \
  --with "pip-audit==2.10.0" \
  --with "import-linter==2.11" \
  --with "pydantic-settings==2.9.1" \
  --force -q

echo ""
echo "Installing ruff (if not already present)..."
uv tool install "ruff==0.15.13" --force -q 2>/dev/null || pip install "ruff==0.15.13" --quiet

echo ""
echo "Bootstrap complete. Verify with:"
echo "  bash scripts/titan_ci.sh"
echo ""
echo "  ✅ Environment ready"
