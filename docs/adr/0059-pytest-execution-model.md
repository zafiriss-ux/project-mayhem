# ADR-0059: Unified pytest Execution Model

**Status:** ACCEPTED
**Date:** 2026-06-04
**Author:** Zaf (Owner) / Claude (Design Authority)
**Related:** ADR-0048 (CI gate taxonomy), scripts/titan_ci.sh, F6 (Opus CI audit 2026-06-04)

---

## Context

TITAN OS has three divergent pytest invocation models across its governance
artifacts, producing environment-dependent CI failures and "green local ≠ green
GitHub" divergence:

| Artifact | Model | Works when |
|----------|-------|-----------|
| `AGENTS.md §2.0` | `python -m pytest` | pytest installed in active interpreter |
| `CLAUDE.md` | `python3 -m pytest` | pytest installed in python3 interpreter |
| `scripts/titan_ci.sh` | bare `pytest` | pytest on PATH (uv-tool model) |
| `scripts/titan_check.sh` | bare `pytest` / `ruff` | uv-tool model |
| GitHub CI (`ci.yml`) | `pytest -q` / `python -m pytest` | GitHub-hosted env |

The uv-tool model (`bash scripts/ci_bootstrap.sh` → bare `pytest`) isolates the
test environment from the system interpreter but silently breaks `python -m pytest`
and `python3 -m pytest`. GitHub CI uses the single-environment model
(`pip install -r requirements.txt`) and invokes `pytest` as a bare binary.

The Opus CI audit (2026-06-04, F6) identified this as the highest-probability
reproducibility break and recommended unifying on one model.

---

## Decision

**Adopt `python -m pytest` as the single authoritative pytest invocation model.**

All governance artifacts, CI scripts, and VERIFY fields will use `python -m pytest`
(or `python3 -m pytest` on systems where `python` is not the Python 3 binary).

The uv-tool model (`bash scripts/ci_bootstrap.sh`) is retained as an optional
convenience bootstrap for environments where pip installation into the system
interpreter is restricted (PEP 668 / Ubuntu 26.04+), but `ci_bootstrap.sh` must
be updated to ensure `python -m pytest` resolves correctly in its environment
by creating a `.venv` and installing into it rather than the global uv tool store.

**Canonical invocation order (any environment):**

```bash
# 1. Bootstrap (first time or after clean clone)
bash scripts/ci_bootstrap.sh        # creates .venv, pip-installs all deps

# 2. Activate
source .venv/bin/activate           # ensures python -m pytest resolves

# 3. Verify
bash scripts/titan_ci.sh            # uses python -m pytest internally
```

---

## Consequences

**Positive:**
- Single model across local, Code sandbox, and GitHub CI.
- `python -m pytest` is environment-explicit — it always runs pytest from the
  active interpreter, eliminating the `pytest: command not found` / wrong-env
  class of failures.
- AGENTS.md §2.0 is already correct and becomes the canonical reference.
- GitHub CI is already correct and requires no changes.

**Negative:**
- `scripts/titan_ci.sh` must be updated to use `python -m pytest` (not bare `pytest`).
- `scripts/ci_bootstrap.sh` must be updated to create a `.venv` and expose
  `python -m pytest` rather than installing into the global uv tool store.
- `CLAUDE.md` must be updated from `python3 -m pytest` → `python -m pytest`.
- `scripts/titan_check.sh` must be updated from bare invocations.

**Implementation checklist:**

- [x] `scripts/ci_bootstrap.sh` — replace `uv tool install pytest --with …` with
      `python3 -m venv .venv && pip install -r requirements.txt -r requirements-dev.txt` *(#830)*
- [x] `scripts/titan_ci.sh` — replace bare `pytest` with `python -m pytest`
      and bare `ruff` with `python -m ruff` *(#830; interpreter resolution + preflight
      added in CI_SURFACE_AUDIT_2026-06-06 follow-up)*
- [x] `CLAUDE.md` — update `python3 -m pytest` → `python -m pytest` *(#831)*
- [x] `scripts/titan_check.sh` — update bare invocations *(#831; interpreter resolution
      added in CI_SURFACE_AUDIT_2026-06-06 follow-up)*
- [x] AGENTS.md — no change required (already uses `python -m pytest`)
- [x] `scripts/git_hooks/pre-commit`, `.pre-commit-config.yaml` — bare `ruff` →
      `python -m ruff` *(CI_SURFACE_AUDIT_2026-06-06 follow-up; was missed in #830/#831)*

**Orphan cleanup (safe, concurrent):**
- [x] Delete root `setup_env.sh` — legacy Codex-era artifact, unreferenced
      by any active CI path (F5, Opus CI audit 2026-06-04) *(removed; verified absent 2026-06-06)*

---

## References

- Opus CI audit 2026-06-04, findings F5, F6, F9
- ADR-0048: CI gate taxonomy
- TD-NEW-05: constraints.txt removal
- scripts/titan_ci.sh §9C entrypoint
- scripts/ci_bootstrap.sh
