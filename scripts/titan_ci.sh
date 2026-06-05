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

# ── G1: Ruff Phase A (full repo, blocking) ────────────────────────────────────
run_gate "G1 Ruff Phase A" python -m ruff check .

# ── G2: Strict pytest (full suite) ───────────────────────────────────────────
run_gate "G2 Strict pytest" python -m pytest --tb=short -q --strict-markers \
    --ignore=tests/test_backup.py \
    --ignore=tests/test_backup_verification.py \
    --ignore=tests/test_complexity_budget.py

# ── G3: Schema equivalence (TD-08 fitness net) ───────────────────────────────
run_gate "G3 Schema equivalence" python -m pytest tests/test_schema_equivalence.py -q --no-cov

# ── G4: Governance invariants (AST) ──────────────────────────────────────────
run_gate "G4 Governance invariants" python -m pytest tests/test_architectural_invariants.py -q --no-cov

# ── G5: ADR-0058 fitness gates ────────────────────────────────────────────────
run_gate "G5 ADR-0058 fitness" python -m pytest tests/test_adr0058_fitness.py -q --no-cov

# ── G6: Schema contract tests ────────────────────────────────────────────────
run_gate "G6 Schema contracts" python -m pytest tests/test_db_schema_contracts.py tests/titan/core/ -q --no-cov

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
