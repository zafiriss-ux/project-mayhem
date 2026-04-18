#!/usr/bin/env bash
# TITAN OS — Per-Module Audit
# Usage: bash scripts/module_audit.sh <path/to/module.py>
# Exit code: 0 = all checks pass, 1 = one or more failures
#
# Checks:
#   1. MODULE_VERSION declared (AGENTS.md §16.8) — science modules only
#   2. No ADR-0040-SINGLE-ATHLETE-SHORTCUT annotations remaining
#   3. No naive datetime.now() — governance-critical modules only (INV-02)
#   4. No silent except: pass
#   5. Mirrored test file exists
#   6. Per-athlete SQL queries include athlete_id scope

set -euo pipefail

MODULE="${1:-}"
if [ -z "$MODULE" ]; then
  echo "Usage: bash scripts/module_audit.sh <path/to/module.py>"
  exit 1
fi
if [ ! -f "$MODULE" ]; then
  echo "ERROR: File not found: $MODULE"
  exit 1
fi

FAILURES=0
MODULE_NAME=$(basename "$MODULE" .py)

# Compute subdir relative to titan/ (e.g. "science", "core", "")
RELATIVE="${MODULE#titan/}"
if [[ "$RELATIVE" == */* ]]; then
  SUBDIR="${RELATIVE%/*}"
else
  SUBDIR=""
fi

_pass() { echo "    ✅ $1"; }
_fail() { echo "    ❌ $1"; FAILURES=$((FAILURES + 1)); }
_skip() { echo "    ⏭  $1"; }

echo "── $MODULE ──"

# ── Check 1: MODULE_VERSION (science modules only) ───────────────────────────
if echo "$MODULE" | grep -q "titan/science/"; then
  VER=$(grep "^MODULE_VERSION" "$MODULE" 2>/dev/null | head -1 \
        | sed 's/^MODULE_VERSION[[:space:]]*=[[:space:]]*//' \
        | sed "s/[\"']//g" || true)
  if [ -n "$VER" ]; then
    _pass "MODULE_VERSION = \"$VER\""
  else
    _fail "MODULE_VERSION missing (AGENTS.md §16.8)"
  fi
else
  _skip "MODULE_VERSION (non-science module)"
fi

# ── Check 2: No ADR-0040-SINGLE-ATHLETE-SHORTCUT annotations ─────────────────
ANN_COUNT=$(grep -c "ADR-0040-SINGLE-ATHLETE-SHORTCUT" "$MODULE" 2>/dev/null || true)
if [ "$ANN_COUNT" -eq 0 ]; then
  _pass "No ADR-0040-SINGLE-ATHLETE-SHORTCUT annotations"
else
  _fail "ADR-0040-SINGLE-ATHLETE-SHORTCUT found: $ANN_COUNT occurrence(s)"
  grep -n "ADR-0040-SINGLE-ATHLETE-SHORTCUT" "$MODULE" | head -3 || true
fi

# ── Check 3: No naive datetime.now() (governance-critical modules) ───────────
GOVERNANCE_CRITICAL="governance_engine hrv_engine daily_coach garmin_sync \
  database coaching_pipeline"
if echo "$GOVERNANCE_CRITICAL" | grep -qw "$MODULE_NAME"; then
  DT_COUNT=$(grep -c "datetime\.now()" "$MODULE" 2>/dev/null || true)
  if [ "$DT_COUNT" -eq 0 ]; then
    _pass "No naive datetime.now()"
  else
    _fail "naive datetime.now(): $DT_COUNT occurrence(s) (INV-02)"
    grep -n "datetime\.now()" "$MODULE" | head -3 || true
  fi
else
  _skip "datetime.now() check (non-governance-critical)"
fi

# ── Check 4: No silent except: pass ──────────────────────────────────────────
SILENT_COUNT=$(python3 -c "
import ast, sys
try:
    tree = ast.parse(open(sys.argv[1]).read())
    count = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    )
    print(count)
except Exception:
    print(0)
" "$MODULE" 2>/dev/null || echo 0)
if [ "$SILENT_COUNT" -eq 0 ]; then
  _pass "No silent except: pass"
else
  _fail "Silent except: pass found: $SILENT_COUNT occurrence(s)"
fi

# ── Check 5: Mirrored test file exists ───────────────────────────────────────
# Primary: tests/titan/<subdir>/test_<module>.py (exact match)
# Secondary: any file in tests/titan/<subdir>/ containing the module name
# Fallback: any file in tests/ root containing the module name
if [ -n "$SUBDIR" ]; then
  TEST_EXACT="tests/titan/${SUBDIR}/test_${MODULE_NAME}.py"
  TEST_GLOB=$(find "tests/titan/${SUBDIR}/" -name "*${MODULE_NAME}*" \
              2>/dev/null | head -1 || true)
else
  TEST_EXACT="tests/titan/test_${MODULE_NAME}.py"
  TEST_GLOB=$(find "tests/titan/" -maxdepth 1 -name "*${MODULE_NAME}*" \
              2>/dev/null | head -1 || true)
fi
TEST_ROOT=$(find tests/ -maxdepth 1 -name "*${MODULE_NAME}*" 2>/dev/null | head -1 || true)

if [ -f "$TEST_EXACT" ]; then
  _pass "Mirrored test: $TEST_EXACT"
elif [ -n "$TEST_GLOB" ]; then
  _pass "Mirrored test (variant name): $TEST_GLOB"
elif [ -n "$TEST_ROOT" ]; then
  _pass "Root test: $TEST_ROOT"
else
  _fail "No mirrored test found (checked tests/titan/${SUBDIR:+$SUBDIR/}test_${MODULE_NAME}.py and variants)"
fi

# ── Check 6: Per-athlete SQL queries scoped with athlete_id ──────────────────
UNSCOPED=$(python3 -c "
import ast, sys
PER_ATHLETE_TABLES = {
    'governance_outcomes', 'daily_metrics', 'training_log',
    'athletes', 'athlete_threshold_offsets', 'model_calibration_metadata',
    'gear_usage', 'personal_bests',
}
OPS = ('SELECT', 'UPDATE', 'DELETE')
try:
    tree = ast.parse(open(sys.argv[1]).read())
    count = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and any(t.upper() in node.value.upper() for t in PER_ATHLETE_TABLES)
        and any(op in node.value.upper() for op in OPS)
        and 'ATHLETE_ID' not in node.value.upper()
    )
    print(count)
except Exception:
    print(0)
" "$MODULE" 2>/dev/null || echo 0)
if [ "$UNSCOPED" -eq 0 ]; then
  _pass "Per-athlete SQL queries scoped with athlete_id"
else
  _fail "Per-athlete SQL missing athlete_id scope: $UNSCOPED location(s)"
fi

# ── Result ────────────────────────────────────────────────────────────────────
if [ "$FAILURES" -eq 0 ]; then
  echo "  → PASS ($MODULE_NAME)"
  exit 0
else
  echo "  → FAIL ($MODULE_NAME): $FAILURES check(s) failed"
  exit 1
fi
