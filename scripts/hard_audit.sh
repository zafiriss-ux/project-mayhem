#!/usr/bin/env bash
# TITAN OS — Bounded Hard Audit Runner
# Runs all manual audit patterns in sequence.
# Usage: bash scripts/hard_audit.sh
# Exit code: 0 = all audits pass, 1 = one or more failures
#
# Covers (in order):
#   A. Environment checks
#   B. Schema integrity
#   C. Governance invariants (AST)
#   D. Threshold source-of-truth
#   E. Dependency hygiene
#   F. Test suite gates
#   G. Coverage gate
#   H. Complexity budget
#   I. Documentation consistency
#   J. Scratchpad gate
#   P. Architectural dependency lint (import-linter)
#
# Pattern: each section prints PASS or FAIL.
# Script continues on FAIL (accumulates); exits 1 if any FAIL found.

set -euo pipefail
FAILURES=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PYTEST_BIN="${PYTEST_BIN:-.venv/bin/pytest}"
if [ ! -f "$PYTEST_BIN" ]; then
    if python -m pytest --version &>/dev/null 2>&1; then
        PYTEST_BIN="python -m pytest"
    elif python3 -m pytest --version &>/dev/null 2>&1; then
        PYTEST_BIN="python3 -m pytest"
    elif _pb=$(which pytest 2>/dev/null); then
        PYTEST_BIN="$_pb"
    fi
fi

_pass() { echo "  ✅ PASS — $1"; }
_fail() { echo "  ❌ FAIL — $1"; FAILURES=$((FAILURES + 1)); }
_section() { echo ""; echo "══ $1 ══"; }

# ─────────────────────────────────────────────────────────────────────────────
_section "A. Environment"
# ─────────────────────────────────────────────────────────────────────────────

PY_MINOR=$(python -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 12 ]; then
  _pass "Python $(python --version) ≥ 3.12"
else
  _fail "Python $(python --version) — requires 3.12+"
fi

# Capture collection output once; use awk to count errors (always exits 0).
COLLECT_OUT=$($PYTEST_BIN --collect-only -q --no-cov 2>&1 || true)
ERR_COUNT=$(echo "$COLLECT_OUT" | awk '/^ERROR/{c++}END{print c+0}')
if [ "$ERR_COUNT" -eq 0 ]; then
  _pass "Collection errors: 0"
else
  _fail "Collection errors: $ERR_COUNT"
  echo "$COLLECT_OUT" | grep "^ERROR" | head -10
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "B. Schema integrity"
# ─────────────────────────────────────────────────────────────────────────────

$PYTEST_BIN tests/test_db_schema_contracts.py -q --tb=short --no-cov 2>&1 | tail -3
if $PYTEST_BIN tests/test_db_schema_contracts.py -q --tb=no --no-cov \
     2>&1 | grep -q "passed"; then
  _pass "Schema contract tests"
else
  _fail "Schema contract tests"
fi

$PYTEST_BIN tests/titan/core/test_db_schema_v13.py \
       tests/titan/core/test_cold_start.py \
       -q --tb=no --no-cov 2>&1 | tail -2
if $PYTEST_BIN tests/titan/core/test_db_schema_v13.py \
          tests/titan/core/test_cold_start.py \
     -q --tb=no --no-cov 2>&1 | grep -q "passed"; then
  _pass "Phase 9 schema tests (v13/v14 + cold-start)"
else
  _fail "Phase 9 schema tests"
fi

SCHEMA_VERSION=$(python -c "
import titan.core.database as db
print(db.SCHEMA_VERSION)
" 2>/dev/null || echo "UNKNOWN")
echo "  → SCHEMA_VERSION = $SCHEMA_VERSION"

# ─────────────────────────────────────────────────────────────────────────────
_section "C. Governance invariants (AST)"
# ─────────────────────────────────────────────────────────────────────────────

if $PYTEST_BIN tests/test_architectural_invariants.py \
     tests/test_fitness_functions.py \
     tests/test_athlete_isolation_invariant.py \
     -q --tb=short --no-cov 2>&1 | grep -q "passed"; then
  _pass "AST architectural invariants"
else
  _fail "AST architectural invariants"
fi

if $PYTEST_BIN tests/test_governance_mutation.py \
     -q --tb=no --no-cov 2>&1 | grep -q "passed"; then
  _pass "Governance mutation tests"
else
  _fail "Governance mutation tests"
fi

if $PYTEST_BIN tests/test_governance_golden.py \
     -q --tb=no --no-cov 2>&1 | grep -q "passed"; then
  _pass "Governance golden file (decision regression)"
else
  _fail "Governance golden file"
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "D. Threshold source-of-truth"
# ─────────────────────────────────────────────────────────────────────────────

if $PYTEST_BIN tests/test_documentation_consistency.py \
     -q --tb=no --no-cov 2>&1 | grep -q "passed"; then
  _pass "Documentation consistency (threshold/evidence/ADR)"
else
  _fail "Documentation consistency"
fi

# Inline check: no ADR-0040 exemptions remain in persistence.py
OLD_ANN=$(grep -c "ADR-0040-SINGLE-ATHLETE-SHORTCUT" \
  titan/core/persistence.py 2>/dev/null || :)
if [ "$OLD_ANN" -eq 0 ]; then
  _pass "No ADR-0040 exemptions remain in persistence.py"
else
  _fail "ADR-0040 exemptions still present: $OLD_ANN occurrences"
fi

# Inline check: no active calibrated_for column references.
# Excludes: migration DDL/comments, drop steps, historical log strings.
# database.py migration history (v7 DDL, v13 drop) is intentional — not active use.
OLD_COL=$(
  { grep -rn "calibrated_for" titan/ --include="*.py" 2>/dev/null || true; } \
  | awk '!/# |log|[Dd]rop|T5-07|ADR-0033|columns_dropped|calibrated_for.*TEXT|not in/ \
         {c++} END {print c+0}'
)
if [ "$OLD_COL" -eq 0 ]; then
  _pass "No active calibrated_for references in source"
else
  _fail "Active calibrated_for references: $OLD_COL locations"
  { grep -rn "calibrated_for" titan/ --include="*.py" 2>/dev/null || true; } \
    | grep -v "# \|log\|[Dd]rop\|T5-07\|ADR-0033\|columns_dropped\|calibrated_for.*TEXT\|not in" \
    | head -5
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "E. Dependency hygiene"
# ─────────────────────────────────────────────────────────────────────────────

if $PYTEST_BIN tests/test_t4_25_dependency_drift_audit.py \
     -q --tb=no --no-cov 2>&1 | grep -q "passed"; then
  _pass "Dependency drift audit"
else
  _fail "Dependency drift audit"
fi

# Check no unpinned deps; awk avoids grep-exit-1-on-no-match with pipefail.
UNPINNED=$(awk '/^[a-zA-Z]/ && !/==/ {c++} END {print c+0}' requirements.txt)
if [ "$UNPINNED" -eq 0 ]; then
  _pass "All requirements.txt deps pinned with =="
else
  _fail "Unpinned deps in requirements.txt: $UNPINNED"
  grep -E "^[a-zA-Z]" requirements.txt | grep -v "=="
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "F. Test suite gates"
# ─────────────────────────────────────────────────────────────────────────────

echo "  Running G1 (ruff)..."
if ruff check . --quiet; then
  _pass "G1 ruff — 0 findings"
else
  _fail "G1 ruff — findings present"
fi

echo "  Running G2 (strict pytest)..."
G2_OUT=$($PYTEST_BIN -q -W error::pytest.PytestWarning --tb=no 2>&1 | tail -3)
echo "  $G2_OUT"
if echo "$G2_OUT" | grep -q "passed"; then
  _pass "G2 strict pytest"
else
  _fail "G2 strict pytest"
fi

echo "  Running G3 (full pytest)..."
G3_OUT=$($PYTEST_BIN -q --tb=no 2>&1 | tail -3)
echo "  $G3_OUT"
if echo "$G3_OUT" | grep -q "passed"; then
  _pass "G3 full pytest"
else
  _fail "G3 full pytest"
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "G. Coverage gate"
# ─────────────────────────────────────────────────────────────────────────────

COV=$($PYTEST_BIN --cov=titan --cov-report=term-missing -q --tb=no \
      2>&1 | { grep "TOTAL" || true; } | awk '{print $NF}' | tr -d '%')
if [ -n "$COV" ] && [ "$COV" -ge 80 ]; then
  _pass "Coverage: ${COV}% ≥ 80%"
else
  _fail "Coverage: ${COV:-UNKNOWN}% < 80%"
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "H. Complexity budget"
# ─────────────────────────────────────────────────────────────────────────────

MODULE_COUNT=$(find titan/ -name "*.py" \
  ! -name "__init__.py" ! -name "__main__.py" | wc -l | tr -d ' ')
CEILING=$(python -c \
  "from titan.config.thresholds import MODULE_COUNT_CEILING; \
   print(MODULE_COUNT_CEILING)" 2>/dev/null || echo "71")

echo "  → $MODULE_COUNT modules / ceiling $CEILING"

if [ "$MODULE_COUNT" -le "$CEILING" ]; then
  _pass "Module count $MODULE_COUNT ≤ ceiling $CEILING"
else
  _fail "Module count $MODULE_COUNT > ceiling $CEILING — raise ceiling via ADR"
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "I. Documentation consistency"
# ─────────────────────────────────────────────────────────────────────────────

if $PYTEST_BIN tests/test_claude_md_integrity.py \
     -q --tb=no --no-cov 2>&1 | grep -q "passed"; then
  _pass "CLAUDE.md integrity"
else
  _fail "CLAUDE.md integrity"
fi

# INV-04 enforcement check
INV04=$(grep -A2 "INV-04" AGENTS.md | { grep -c "ENFORCED" || :; })
if [ "$INV04" -gt 0 ]; then
  _pass "INV-04 ENFORCED in AGENTS.md"
else
  _fail "INV-04 not ENFORCED in AGENTS.md"
fi

# ADR-0033 Layer 3 complete check
L3_RESOLVED=$(grep -c "L3-A.*RESOLVED\|L3-B.*RESOLVED\|L3-C.*RESOLVED\|L3-D.*RESOLVED" \
  TECHNICAL_DEBT.md || :)
if [ "$L3_RESOLVED" -ge 4 ]; then
  _pass "ADR-0033 Layer 3: all 4 sub-decisions RESOLVED"
else
  _fail "ADR-0033 Layer 3: only $L3_RESOLVED/4 sub-decisions RESOLVED"
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "J. Scratchpad gate"
# ─────────────────────────────────────────────────────────────────────────────

if bash scripts/check_scratchpad.sh; then
  _pass "SCRATCHPAD — BLOCKING queue empty"
else
  _fail "SCRATCHPAD — BLOCKING queue non-empty"
fi

SCRATCHPAD_STATUS=$(grep "^STATUS:" SCRATCHPAD.md | head -1 | awk '{print $2}')
echo "  → SCRATCHPAD STATUS: $SCRATCHPAD_STATUS"

# ─────────────────────────────────────────────────────────────────────────────
_section "P. Architectural dependency lint (import-linter)"
# ─────────────────────────────────────────────────────────────────────────────

if [ -f ".venv/bin/lint-imports" ]; then
  LINTER=".venv/bin/lint-imports"
elif command -v lint-imports &>/dev/null; then
  LINTER="lint-imports"
fi
if [ -n "${LINTER:-}" ]; then
  LINT_OUT=$($LINTER --config .importlinter 2>&1)
  if echo "$LINT_OUT" | grep -q "0 broken"; then
    _pass "import-linter: all contracts kept"
  else
    _fail "import-linter: contract violation detected"
    echo "$LINT_OUT" | grep -E "BROKEN|KEPT|ERROR|broken" || true
  fi
else
  echo "  ⏭  import-linter not installed — skipping"
fi

# ─────────────────────────────────────────────────────────────────────────────
_section "SUMMARY"
# ─────────────────────────────────────────────────────────────────────────────

if [ "$FAILURES" -eq 0 ]; then
  echo ""
  echo "  ✅ ALL AUDITS PASSED"
  echo ""
  exit 0
else
  echo ""
  echo "  ❌ $FAILURES AUDIT(S) FAILED — see above"
  echo ""
  exit 1
fi
