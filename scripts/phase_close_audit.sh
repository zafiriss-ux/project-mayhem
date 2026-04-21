#!/usr/bin/env bash
# TITAN OS — Phase Close Automated Audit Suite (D-25 / T5-97)
# Runs all governance checks required at a phase boundary.
# Usage: bash scripts/phase_close_audit.sh [phase_number]
# Example: bash scripts/phase_close_audit.sh 9
#
# Covers everything in hard_audit.sh PLUS:
#   K. FMEA presence check
#   L. INV test coverage completeness
#   M. ADR index freshness
#   N. Semgrep governance rules
#   O. Gate Coverage Matrix summary

set -euo pipefail
PHASE="${1:-UNKNOWN}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo "═══ TITAN OS Phase $PHASE Close Audit ═══"
echo "Date: $(date '+%Y-%m-%d')"
echo ""

# Run base hard_audit first (captures its exit code without aborting)
set +e
bash "$SCRIPT_DIR/hard_audit.sh"
BASE_EXIT=$?
set -e

FAILURES=0
_pass() { echo "  ✅ PASS — $1"; }
_fail() { echo "  ❌ FAIL — $1"; FAILURES=$((FAILURES + 1)); }
_section() { echo ""; echo "══ $1 ══"; }

# ── K. FMEA presence ──────────────────────────────────────────────────────────
_section "K. FMEA presence"

FMEA_COUNT=$(grep -c "^## FMEA:" TECHNICAL_DEBT.md 2>/dev/null || echo 0)
if [ "$FMEA_COUNT" -gt 0 ]; then
    _pass "FMEA section(s) found: $FMEA_COUNT"
else
    _fail "No FMEA section found in TECHNICAL_DEBT.md (G12 gate)"
fi

if [ "$PHASE" != "UNKNOWN" ]; then
    if grep -q "FMEA.*Phase $PHASE\|FMEA: Phase $PHASE" TECHNICAL_DEBT.md 2>/dev/null; then
        _pass "FMEA: Phase $PHASE present"
    else
        _fail "FMEA: Phase $PHASE missing — G12 OPEN"
    fi
fi

# ── L. INV test coverage completeness ─────────────────────────────────────────
_section "L. Invariant test coverage (INV-01 through INV-10)"

MISSING_INV=$(python3 - <<'PYEOF'
import re, sys
from pathlib import Path

try:
    agents_text = Path("AGENTS.md").read_text(encoding="utf-8")
except FileNotFoundError:
    print("WARN: AGENTS.md not found")
    sys.exit(0)

missing = []
for inv_num in range(1, 11):
    pattern = rf'INV-0?{inv_num}\b'
    if not re.search(pattern, agents_text):
        missing.append(f"INV-{inv_num:02d}")

if missing:
    print(f"MISSING: {', '.join(missing)}")
PYEOF
)

if [ -z "$MISSING_INV" ]; then
    _pass "All INV-01 through INV-10 referenced in AGENTS.md"
else
    _fail "INV entries missing in AGENTS.md: $MISSING_INV"
fi

# ── M. ADR index freshness ────────────────────────────────────────────────────
_section "M. ADR index freshness"

ADR_FILES=$(find docs/adr/ -name "*.md" ! -name "README.md" \
    2>/dev/null | wc -l | tr -d ' ')
echo "  → ADR files on disk: $ADR_FILES"

LATEST_ADR_FILE=$(find docs/adr/ -name "0*.md" 2>/dev/null | sort | tail -1)
if [ -n "$LATEST_ADR_FILE" ]; then
    LATEST_NUM=$(basename "$LATEST_ADR_FILE" | grep -o "^[0-9]*" || echo "0")
    echo "  → Latest ADR file: $LATEST_ADR_FILE"
    if grep -qE "ADR-0*${LATEST_NUM}|0${LATEST_NUM}" CLAUDE.md 2>/dev/null; then
        _pass "Latest ADR (0${LATEST_NUM}) referenced in CLAUDE.md"
    else
        _fail "Latest ADR (0${LATEST_NUM}) not found in CLAUDE.md index"
    fi
else
    echo "  ⏭  No ADR files found in docs/adr/ — skipping"
fi

# ── N. Semgrep governance scan ────────────────────────────────────────────────
_section "N. Semgrep governance scan"

if command -v semgrep &>/dev/null; then
    set +e
    SEMGREP_COUNT=$(semgrep --config .semgrep/titan_rules.yaml \
        titan/ --quiet 2>&1 | grep -c "^titan/" || true)
    set -e
    if [ "${SEMGREP_COUNT:-0}" -eq 0 ]; then
        _pass "Semgrep: 0 violations"
    else
        _fail "Semgrep: $SEMGREP_COUNT violation(s) — run: semgrep --config .semgrep/titan_rules.yaml titan/"
    fi
else
    echo "  ⏭  Semgrep not installed — skipping (pip install semgrep)"
fi

# ── O. Gate Coverage Matrix summary ──────────────────────────────────────────
_section "O. Gate Coverage Matrix"
set +e
bash "$SCRIPT_DIR/gate_coverage_matrix.sh" 2>&1 | grep -E "TOTAL|⚠️|✅|ℹ️" | head -5
GCM_EXIT=$?
set -e
if [ "$GCM_EXIT" -ne 0 ]; then
    _fail "Gate Coverage Matrix script failed (exit $GCM_EXIT)"
fi

# ── Final summary ─────────────────────────────────────────────────────────────
_section "PHASE $PHASE CLOSE SUMMARY"

TOTAL_FAILURES=$((BASE_EXIT + FAILURES))
if [ "$TOTAL_FAILURES" -eq 0 ]; then
    echo ""
    echo "  ✅ PHASE $PHASE CLOSE AUDIT: PASS"
    echo "  → All gates satisfied. Ready for Opus review."
    echo ""
    exit 0
else
    echo ""
    echo "  ❌ PHASE $PHASE CLOSE AUDIT: $TOTAL_FAILURES FAILURE(S)"
    echo "  → Resolve all failures before Phase $PHASE close."
    echo ""
    exit 1
fi
