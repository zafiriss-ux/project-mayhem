#!/usr/bin/env bash
# =============================================================================
# TITAN OS — Canonical CI Entrypoint
# Operating Contract v7.8 §9C: all VERIFY fields reference this script.
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
    echo "❌ No Python interpreter found. Install Python 3.11+ and run scripts/ci_bootstrap.sh." >&2
    exit 1
fi

# ── Dependency preflight: actionable remediation, not a cryptic ImportError ────
if ! "${PY}" -c "import pytest, freezegun, sqlalchemy, fastapi" >/dev/null 2>&1 \
   || ! "${PY}" -m ruff --version >/dev/null 2>&1; then
    echo "❌ CI dependency closure missing for interpreter: ${PY}" >&2
    echo "   Bootstrap first:  bash scripts/ci_bootstrap.sh   (creates .venv, installs all deps)" >&2
    echo "   Then re-run:      bash scripts/titan_ci.sh" >&2
    exit 1
fi

PASS=0
FAIL=0
FAILED_GATES=()

run_gate() {
    local name="$1"
    shift
    echo ""
    echo "══ $name ══"
    if "$@"; then
        echo "  ✅ PASS — $name"
        PASS=$((PASS + 1))
    else
        echo "  ❌ FAIL — $name"
        FAIL=$((FAIL + 1))
        FAILED_GATES+=("$name")
    fi
}

echo "═══ TITAN OS Local CI ═══"
echo "Date: $(date '+%Y-%m-%d')"
echo "Repo: $REPO_ROOT"
echo "Interpreter: $PY"

# ── G1: Ruff Phase A (full repo, blocking) ────────────────────────────────────
run_gate "G1 Ruff Phase A" "$PY" -m ruff check .

# ── G2: Strict pytest (full suite) ───────────────────────────────────────────
run_gate "G2 Strict pytest" "$PY" -m pytest --tb=short -q --strict-markers \
    --ignore=tests/test_backup.py \
    --ignore=tests/test_backup_verification.py \
    --ignore=tests/test_complexity_budget.py

# ── G3: Schema equivalence (TD-08 fitness net) ───────────────────────────────
run_gate "G3 Schema equivalence" "$PY" -m pytest tests/test_schema_equivalence.py -q --no-cov

# ── G4: Governance invariants (AST) ──────────────────────────────────────────
run_gate "G4 Governance invariants" "$PY" -m pytest tests/test_architectural_invariants.py -q --no-cov

# ── G5: ADR-0058 fitness gates ────────────────────────────────────────────────
run_gate "G5 ADR-0058 fitness" "$PY" -m pytest tests/test_adr0058_fitness.py -q --no-cov

# ── G6: Schema contract tests ────────────────────────────────────────────────
run_gate "G6 Schema contracts" "$PY" -m pytest tests/test_db_schema_contracts.py tests/titan/core/ -q --no-cov

# ── SUMMARY ───────────────────────────────────────────────────────────────────
echo ""
echo "══ TITAN CI SUMMARY ══"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

if [[ $FAIL -eq 0 ]]; then
    echo ""
    echo "  ✅ TITAN CI: ALL GATES PASS"
    exit 0
else
    echo ""
    echo "  ❌ TITAN CI: $FAIL FAILURE(S)"
    for gate in "${FAILED_GATES[@]}"; do
        echo "    → $gate"
    done
    exit 1
fi
