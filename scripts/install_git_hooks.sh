#!/usr/bin/env bash
# TITAN OS — Git hooks installer
# Run once per clone to activate local pre-commit gate enforcement.
#
# Usage:
#   bash scripts/install_git_hooks.sh
#
# What this does:
#   Symlinks scripts/git_hooks/pre-commit → .git/hooks/pre-commit
#   so git automatically runs the 3 mandatory engineering gates before
#   every commit (ruff, pytest strict, pytest full).

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$ROOT/scripts/git_hooks/pre-commit"
HOOK_DST="$ROOT/.git/hooks/pre-commit"

if [ ! -f "$HOOK_SRC" ]; then
    echo "ERROR: Hook script not found at $HOOK_SRC" >&2
    exit 1
fi

chmod +x "$HOOK_SRC"

if [ -e "$HOOK_DST" ] && [ ! -L "$HOOK_DST" ]; then
    echo "WARNING: $HOOK_DST already exists and is not a symlink."
    echo "Backing up to $HOOK_DST.bak"
    mv "$HOOK_DST" "$HOOK_DST.bak"
fi

ln -sf "$HOOK_SRC" "$HOOK_DST"
echo "✓ Pre-commit hook installed: $HOOK_DST → $HOOK_SRC"
echo ""
echo "The three mandatory gates will now run automatically before every commit:"
echo "  Gate 1: ruff check ."
echo "  Gate 2: pytest -q -W error::pytest.PytestWarning"
echo "  Gate 3: pytest -q"
echo ""
echo "To skip in an emergency (not recommended): git commit --no-verify"
