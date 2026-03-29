#!/usr/bin/env bash
# scripts/titan_check.sh — TITAN OS mandatory gate runner
#
# Runs all three mandatory pre-commit gates in sequence.
# Exit 0 only if ALL three gates pass.
# Exit 1 as soon as any gate fails, identifying the failing gate.
#
# Usage:
#   scripts/titan_check.sh
#
# Output: condensed PASS/FAIL per gate + failure count; total test count on success.

set -euo pipefail

PASS="✅ PASS"
FAIL="❌ FAIL"

gate1_result="$PASS"
gate2_result="$PASS"
gate3_result="$PASS"
gate2_count=0
gate3_count=0
any_failure=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  TITAN OS Gate Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Gate 1: Lint ─────────────────────────────────────────
echo ""
echo "▶ Gate 1 — Lint (ruff check .)"
if ruff check . 2>&1; then
    gate1_result="$PASS"
else
    gate1_result="$FAIL"
    any_failure=1
fi

# ── Gate 2: Strict test run ───────────────────────────────
echo ""
echo "▶ Gate 2 — Strict test run (pytest -q -W error::pytest.PytestWarning)"
gate2_output=$(python -m pytest -q -W error::pytest.PytestWarning 2>&1) || true
echo "$gate2_output"
# Extract pass count from last meaningful line
gate2_count=$(echo "$gate2_output" | grep -Eo '^[0-9]+ passed' | grep -Eo '^[0-9]+' || echo "0")
if echo "$gate2_output" | grep -qE '(FAILED|ERROR|error)'; then
    gate2_result="$FAIL"
    any_failure=1
elif echo "$gate2_output" | grep -qE '^[0-9]+ passed'; then
    gate2_result="$PASS"
else
    gate2_result="$FAIL"
    any_failure=1
fi

# ── Gate 3: Full test run ────────────────────────────────
echo ""
echo "▶ Gate 3 — Full test run (pytest -q)"
gate3_output=$(python -m pytest -q 2>&1) || true
echo "$gate3_output"
gate3_count=$(echo "$gate3_output" | grep -Eo '^[0-9]+ passed' | grep -Eo '^[0-9]+' || echo "0")
if echo "$gate3_output" | grep -qE '(FAILED|ERROR)'; then
    gate3_result="$FAIL"
    any_failure=1
elif echo "$gate3_output" | grep -qE '^[0-9]+ passed'; then
    gate3_result="$PASS"
else
    gate3_result="$FAIL"
    any_failure=1
fi

# ── Summary ──────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Gate Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "  G1 Lint         %s\n" "$gate1_result"
printf "  G2 Strict       %s  (%s tests)\n" "$gate2_result" "$gate2_count"
printf "  G3 Full         %s  (%s tests)\n" "$gate3_result" "$gate3_count"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$any_failure" -eq 0 ]; then
    echo "  ALL GATES GREEN — $gate3_count tests passed"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
else
    if [ "$gate1_result" = "$FAIL" ]; then
        echo "  BLOCKED — Gate 1 (Lint) failed. Fix ruff findings before committing."
    elif [ "$gate2_result" = "$FAIL" ]; then
        echo "  BLOCKED — Gate 2 (Strict) failed. Fix all test/warning failures before committing."
    else
        echo "  BLOCKED — Gate 3 (Full) failed. Fix all test failures before committing."
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi
