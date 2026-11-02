#!/usr/bin/env bash
# =============================================================================
# TITAN OS — Canonical CI Entrypoint
# Operating Contract v7.9 §9C: all VERIFY fields reference this script.
# Usage: bash scripts/titan_ci.sh
# Exit 0 = all gates pass. Non-zero = at least one gate failed.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Interpreter resolution (ADR-0059: `python -m pytest` / `python -m ruff`) ───
# Make this §9C VERIFY entrypoint runnable regardless of how the dependency
# closure was provisioned: an already-activated venv, a repo-local .venv created
# by scripts/ci_bootstrap.sh (no manual `source` required), or the system
# interpreter (GitHub CI / Code SessionStart hook). Without this, a fresh shell
# with no venv activated fails every gate with "No module named pytest/ruff".
if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PY="${VIRTUAL_ENV}/bin/python"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PY="${REPO_ROOT}/.venv/bin/python"
else
    PY="$(command -v python3 || command -v python || true)"
fi
if [[ -z "${PY}" ]]; then
    echo "❌ No Python interpreter found. Install Python 3.12+ and run scripts/ci_bootstrap.sh." >&2
    exit 1
fi

# ── Dependency preflight: actionable remediation, not a cryptic ImportError ────
# Keep the established dependency closure check before running the full gates.
if ! "${PY}" -c "import pytest, pytest_cov, freezegun, hypothesis, sqlalchemy, fastapi" >/dev/null 2>&1 \
   || ! "${PY}" -m ruff --version >/dev/null 2>&1; then
    echo "❌ CI dependency closure missing for interpreter: ${PY}" >&2
    echo "   Bootstrap first:  bash scripts/ci_bootstrap.sh   (creates .venv, installs all deps)" >&2
    echo "   Then re-run:      bash scripts/titan_ci.sh" >&2
    exit 1
fi

run_gate() {
    local name="$1"
    local status
    shift
    echo ""
    echo "══ $name ══"
    if "$@"; then
        echo "  ✅ PASS — $name"
    else
        status=$?
        echo "  ❌ FAIL — $name (exit $status)" >&2
        exit "$status"
    fi
}

echo "═══ TITAN OS Local CI ═══"
echo "Date: $(date '+%Y-%m-%d')"
echo "Repo: $REPO_ROOT"
echo "Interpreter: $PY"
echo "Environment fingerprint:"
bash "$REPO_ROOT/scripts/env_fingerprint.sh" "$PY"

run_gate "G1 Ruff" "$PY" -m ruff check .
run_gate "G2 Strict pytest" "$PY" -m pytest -q -W error::pytest.PytestWarning
run_gate "G3 Full pytest" "$PY" -m pytest -q

echo ""
echo "  ✅ TITAN CI: ALL GATES PASS"
