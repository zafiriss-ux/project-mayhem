#!/usr/bin/env bash
# Compatibility entrypoint for the mandatory canonical gates.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$REPO_ROOT/scripts/titan_ci.sh" "$@"
