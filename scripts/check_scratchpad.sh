#!/usr/bin/env bash
# TITAN OS — Scratchpad status gate.
# Mechanically enforces the A-SCRATCHPAD-1 check (CLAUDE.md) at Step 0.5.
# Returns exit code 0 if Codex may proceed; exit code 1 if BLOCKING queue is non-empty.
# Safe to run multiple times (idempotent).
#
# Usage: scripts/check_scratchpad.sh
# Called automatically at Step 0.5 in the canonical task sequence (AGENTS.md §2).

set -euo pipefail

SCRATCHPAD="SCRATCHPAD.md"

if [ ! -f "$SCRATCHPAD" ]; then
    echo "⚠️  SCRATCHPAD.md not found — skipping status check."
    exit 0
fi

# --- Check 1: BLOCKING Queue structural gate ---
# Count OBS entries (lines starting with "### [OBS-") inside the BLOCKING Queue section.
# awk reads from the BLOCKING Queue header until the NON-BLOCKING Queue header.
BLOCKING_COUNT=$(awk '
    /^## BLOCKING Queue/ { in_block=1 }
    /^## NON-BLOCKING Queue/ { in_block=0 }
    in_block && /^### \[OBS-/ { count++ }
    END { print count+0 }
' "$SCRATCHPAD")

if [ "$BLOCKING_COUNT" -gt 0 ]; then
    echo ""
    echo "⛔  SCRATCHPAD GATE FAILED — BLOCKING queue is non-empty."
    echo "    $BLOCKING_COUNT blocking observation(s) require architect review before any task may start."
    echo "    → Read SCRATCHPAD.md §BLOCKING Queue and wait for Claude to clear it."
    echo ""
    exit 1
fi

# --- Check 2: STATUS field advisory (non-blocking queue / under review) ---
# Reads the STATUS value from the document header code block.
STATUS=$(awk '/^STATUS:/ { print $2; exit }' "$SCRATCHPAD")

case "$STATUS" in
    IDLE|CLEARED|"")
        echo "✓  SCRATCHPAD: clear — STATUS: ${STATUS:-IDLE}"
        ;;
    CLARIFICATION_NEEDED)
        echo "⚠️  SCRATCHPAD STATUS: CLARIFICATION_NEEDED"
        echo "    Claude has requested additional context on a pending OBS entry."
        echo "    Codex must append the clarification to the OBS and reset STATUS: REVIEW_REQUESTED."
        echo "    Do NOT start a new top-level task until this is resolved."
        # Non-blocking exit (Codex can respond to clarification request)
        ;;
    REVIEW_REQUESTED|UNDER_REVIEW)
        echo "⚠️  SCRATCHPAD STATUS: $STATUS"
        echo "    Non-blocking observations are pending architect review."
        echo "    Do NOT start a new top-level task until Claude sets STATUS: IDLE."
        # Non-blocking exit (current subtask may continue; new top-level task must not start)
        ;;
    *)
        echo "⚠️  SCRATCHPAD STATUS: '$STATUS' (unrecognised value — check SCRATCHPAD.md)"
        ;;
esac

exit 0
