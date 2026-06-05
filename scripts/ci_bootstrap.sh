#!/usr/bin/env bash
# =============================================================================
# TITAN OS — Local CI Bootstrap (ADR-0059: python -m pytest model)
# Creates a .venv and pip-installs all runtime + dev dependencies.
# Run once after a clean clone or Ubuntu install before scripts/titan_ci.sh.
#
# Prerequisites:
#   python3 (3.11+), pip
#
# Usage:
#   bash scripts/ci_bootstrap.sh
#   source .venv/bin/activate
#   bash scripts/titan_ci.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "═══ TITAN OS CI Bootstrap ═══"
echo "Date: $(date '+%Y-%m-%d')"
echo "Repo: $REPO_ROOT"
echo ""

# ── Create or reuse .venv ─────────────────────────────────────────────────────
if [[ ! -d .venv ]]; then
    echo "Creating .venv with python3..."
    python3 -m venv .venv
else
    echo ".venv already exists — reusing."
fi

# ── Install all dependencies ──────────────────────────────────────────────────
echo "Installing runtime + dev dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
.venv/bin/pip install --quiet -r requirements-dev.txt

echo ""
echo "Bootstrap complete."
echo ""
echo "Activate environment and verify:"
echo "  source .venv/bin/activate"
echo "  bash scripts/titan_ci.sh"
echo ""
echo "  ✅ Environment ready"
