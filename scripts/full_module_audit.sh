#!/usr/bin/env bash
# TITAN OS — Full Module Audit Runner
# Runs module_audit.sh for every titan/ module (excluding __init__ / __main__).
# Usage: bash scripts/full_module_audit.sh [--fail-fast]
# Exit code: 0 = all modules pass, 1 = any module fails
#
# Output: per-module PASS/FAIL lines + final summary with totals.
# Findings reported here are candidates for SCRATCHPAD OBS entries before fixes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

FAIL_FAST=0
if [ "${1:-}" = "--fail-fast" ]; then
  FAIL_FAST=1
fi

PASS_COUNT=0
FAIL_COUNT=0
FAILED_MODULES=()

echo ""
echo "═══ TITAN OS Full Module Audit ═══"
echo ""

while IFS= read -r MODULE; do
  if bash "$SCRIPT_DIR/module_audit.sh" "$MODULE"; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILED_MODULES+=("$MODULE")
    if [ "$FAIL_FAST" -eq 1 ]; then
      echo ""
      echo "FAIL-FAST: stopping at first failure."
      break
    fi
  fi
  echo ""
done < <(find titan/ -name "*.py" \
           ! -name "__init__.py" \
           ! -name "__main__.py" \
           | sort)

echo "═══ Full Module Audit Summary ═══"
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "  Failed modules:"
  for m in "${FAILED_MODULES[@]}"; do
    echo "    ❌ $m"
  done
  echo ""
  echo "  → Write a SCRATCHPAD OBS for each finding before implementing fixes."
  exit 1
fi

echo "  ✅ ALL MODULES PASS"
exit 0
