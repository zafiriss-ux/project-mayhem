#!/usr/bin/env bash
# TITAN OS — Targeted Mutation Testing (T5-84)
# Runs mutmut ONLY on governance_engine.py (H1-H5 gates).
# NOT for CI — run manually before phase close.
# Usage: bash scripts/mutation_test_governance.sh [--quick]
# --quick: 300s timeout (sampling mode, ~5 mutants)
#
# Config: setup.cfg [mutmut] — paths_to_mutate + tests_dir
# Requires: mutmut==3.5.0 (mutmut 2.x not installable: glob2 dep fails to build)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

QUICK="${1:-}"

echo ""
echo "═══ TITAN OS Governance Mutation Testing (T5-84) ═══"
echo "Target: titan/science/governance_engine.py"
echo "Tests:  tests/test_governance_integration.py"
echo "        tests/test_p0_safety_gates.py"
echo "        tests/test_combined_gate_interactions.py"
echo "Config: setup.cfg [mutmut]"
echo ""

# Install mutmut if missing
if ! command -v mutmut &>/dev/null; then
    echo "[setup] Installing mutmut==3.5.0..."
    pip install --quiet "mutmut==3.5.0"
fi

# mutmut 3.x is fully config-driven (setup.cfg [mutmut]).
# paths_to_mutate and tests_dir are read from there — no CLI flags needed.
if [ "$QUICK" = "--quick" ]; then
    echo "Quick mode: 300s timeout (partial run)"
    echo ""
    timeout 300 mutmut run || true
else
    mutmut run
fi

echo ""
echo "── Mutation Score ──"
mutmut results 2>/dev/null || echo "No results yet"

echo ""
echo "── CI/CD Stats ──"
mutmut export-cicd-stats 2>/dev/null || true

echo ""
echo "Survived mutants (candidates for stronger tests):"
mutmut results --all true 2>/dev/null | grep -i "survived\|killed\|timeout" | head -40 || true
