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

# ── Python version guard (documented prerequisite: 3.11+) ─────────────────────
# Enforce the prereq stated in this script's header so a stale/old python3 fails
# loudly here instead of producing a subtly-wrong .venv that breaks gates later.
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on PATH. Install Python 3.11+ first." >&2
    exit 1
fi
if [[ "$(python3 -c 'import sys; print(1 if sys.version_info[:2] >= (3, 11) else 0)')" != "1" ]]; then
    echo "ERROR: TITAN OS requires Python 3.11+. Found: $(python3 --version 2>&1)" >&2
    exit 1
fi
echo "Python $(python3 --version 2>&1) — OK"
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
