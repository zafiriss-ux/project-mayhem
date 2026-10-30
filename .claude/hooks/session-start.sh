#!/usr/bin/env bash
# =============================================================================
# TITAN OS — Claude Code (web) SessionStart bootstrap
# -----------------------------------------------------------------------------
# Makes the Code (cloud) environment match the canonical bootstrap defined by
# scripts/ci_bootstrap.sh (ADR-0059) so the canonical entrypoints —
# scripts/titan_ci.sh and scripts/titan_check.sh, which invoke
# `python -m ruff` / `python -m pytest` — resolve cleanly.
#
# Why this exists (docs/audit/CI_SURFACE_AUDIT_2026-06-06.md, finding F1):
#   The Code sandbox is provisioned from a generic uv-tool image (bare
#   pytest/ruff in isolated tool venvs) with NONE of the project deps in the
#   interpreter `python` resolves to. After the ADR-0059 migration to
#   `python -m …`, every titan_ci.sh gate aborts with "No module named
#   pytest/ruff". The system interpreter additionally carries Debian-managed
#   packages (PyJWT, cryptography, requests) that have no RECORD file and so
#   cannot be replaced by the pinned closure — `pip install -r requirements.txt`
#   into the system interpreter fails. A venv (ci_bootstrap.sh) sidesteps both.
#
# Strategy: run the canonical bootstrap, then put .venv/bin on PATH for every
# shell in this session (each tool shell is re-initialised from profile;
# CLAUDE_ENV_FILE is the documented mechanism to inject session env). This makes
# both `bash scripts/titan_ci.sh` and a bare `python -m pytest` work.
#
# Synchronous (no async): guarantees deps exist before the agent runs a gate.
# Idempotent: ci_bootstrap.sh reuses an existing .venv; pip is a no-op when the
# closure is already satisfied.
# =============================================================================
set -euo pipefail

# Only bootstrap in the remote (Claude Code on the web) environment. Local
# developers invoke scripts/ci_bootstrap.sh directly per ADR-0059.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

echo "TITAN OS SessionStart: running canonical bootstrap (scripts/ci_bootstrap.sh)…"
# Retry the bootstrap. A transient network failure mid-pip used to leave a
# half-built .venv (no pytest/ruff) and, under `set -e`, skipped the PATH step
# below, so every later gate failed with "No module named pytest". Up to 3
# attempts with 10s/20s backoff; each attempt is capped at 180s so a stalled pip
# cannot hang the session (worst case 570s, inside the 600s hook timeout set in
# .claude/settings.json). An attempt only counts if pytest and ruff import.
bootstrap_ok=0
for attempt in 1 2 3; do
  # ci_bootstrap.sh reuses any existing .venv directory. If an earlier attempt
  # (or session) was killed mid `venv`/`pip install --upgrade pip`, .venv can
  # exist with no working pip, and every retry would fail the same way. Rebuild
  # it from scratch in that case.
  if [ -d .venv ] && ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo "TITAN OS SessionStart: .venv has no working pip; recreating it." >&2
    rm -rf .venv
  fi
  if timeout 180 bash scripts/ci_bootstrap.sh && .venv/bin/python -c "import pytest, ruff" >/dev/null 2>&1; then
    bootstrap_ok=1
    break
  fi
  echo "TITAN OS SessionStart: bootstrap attempt ${attempt}/3 failed." >&2
  if [ "${attempt}" -lt 3 ]; then
    sleep $((attempt * 10))
  fi
done
if [ "${bootstrap_ok}" -ne 1 ]; then
  echo "TITAN OS SessionStart: bootstrap failed after 3 attempts; run 'bash scripts/ci_bootstrap.sh' manually." >&2
  exit 1
fi

# Persist the venv onto PATH for the whole session so `python` == .venv python.
# This lets the canonical entrypoints' `python -m pytest`/`python -m ruff` AND
# the agent's direct CLAUDE.md commands (`python -m pytest --no-cov -q`) resolve
# without a manual `source .venv/bin/activate`.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"${PWD}/.venv\""
    echo "export PATH=\"${PWD}/.venv/bin:\${PATH}\""
  } >> "${CLAUDE_ENV_FILE}"
  echo "TITAN OS SessionStart: persisted .venv to PATH via CLAUDE_ENV_FILE."
fi

echo "TITAN OS SessionStart: verifying canonical entrypoint resolves…"
.venv/bin/python -m ruff --version
.venv/bin/python -m pytest --version
echo "TITAN OS SessionStart: ready — .venv active for this session."
