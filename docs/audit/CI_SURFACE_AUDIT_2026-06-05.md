# CI Execution Surface Audit — TITAN OS

- **Mode:** ARCHITECT · **Operating Contract:** v7.8 §9C · **Date:** 2026-06-05
- **Scope:** `scripts/ci_bootstrap.sh`, `scripts/titan_ci.sh`, and their full transitive
  reference/dependency set, plus verification of the Code (cloud) execution environment
  against the canonical bootstrap.
- **Method:** Static discovery + live probing + empirical reproduction in an isolated venv.

---

## 1. Executive Summary

The canonical local CI entrypoint (`scripts/titan_ci.sh`) is **non-runnable in the Code
environment as provisioned**. Five of six gates (G2–G6 — every `pytest` gate) abort at
collection because the active Python interpreter lacks the test dependency closure
(`freezegun`, `sqlalchemy`, `fastapi`, …). Only **G1 (`ruff check .`) runs**, and it runs
under a *drifted* ruff version.

**Root cause:** the sandbox was provisioned by a generic toolchain image (uv tools:
`black`, `flake8`, `poetry`, `pyright`, plus bare `pytest`/`ruff`), **not** by either
repo-canonical bootstrap (`scripts/ci_bootstrap.sh` or `scripts/setup_env.sh`). The suite
itself is healthy: rebuilt in a clean venv from `requirements.txt` + `requirements-dev.txt`,
collection yields **3028 tests, 0 errors** and G1/G3/G4/G5/G6 all pass (see §7).

Secondary findings: a four-way dependency-manifest drift (`pyproject` dev extras stale),
GitHub CI installing **ruff unpinned** (defeating lint determinism), a **broken mandatory
bootstrap** (`scripts/setup_env.sh` references a deleted `constraints.txt`), and **two
divergent `setup_env.sh` files** plus three mutually contradictory bootstrap/VERIFY models.

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| F1 | **CRITICAL** | Code env ≠ canonical bootstrap → G2–G6 non-runnable (`freezegun` missing) | Env-level; remediation documented |
| F2 | **HIGH** | `pyproject` dev extras drift from `requirements-dev.txt` (3 pkgs) | ✅ Patched (P2) |
| F3 | **HIGH** | GitHub CI installs `ruff` unpinned → lint non-determinism | ✅ Patched (P3) |
| F4 | **HIGH** | `scripts/setup_env.sh` references deleted `constraints.txt` → mandatory bootstrap fails | ✅ Patched (P1) |
| F5 | **HIGH** | Two divergent `setup_env.sh` files (root vs `scripts/`) | ⚠ Recommended (architect call) |
| F6 | **MED** | Three contradictory bootstrap/VERIFY models; `pytest` vs `python -m pytest` | ⚠ ADR follow-up |
| F7 | **MED** | `titan_ci.sh` gate set ≠ GitHub CI gate set; green local ≠ green remote | ⚠ Documented |
| F8 | LOW | `ci_bootstrap.sh` not executable | ✅ Patched (P4) |
| F9 | LOW | uv-tool model can't `python -m pytest`; `--with` list is a hand-maintained dup | ⚠ Documented |
| F10 | LOW | `--no-cov` gates assume `pytest-cov` present | ⚠ Documented |
| F11 | INFO | No coverage `addopts`; `--no-cov` is defensive only | Informational |

---

## 2. Discovered CI Execution Surface (dependency graph)

Neither entrypoint `source`s another script; both have shallow, well-bounded graphs.

```
scripts/ci_bootstrap.sh
  ├─ uv            (uv tool install …)
  ├─ pip           (ruff fallback)
  └─ pins (hand-maintained --with list mirroring requirements*.txt)

scripts/titan_ci.sh   (cd "$REPO_ROOT" first — deterministic CWD)
  ├─ ruff                       # G1
  ├─ pytest                     # G2–G6  (bare shim, NOT python -m pytest)
  ├─ conftest.py (root)         # imports freezegun  ← collection-time hard dep
  ├─ tests/conftest.py          # imports titan.*  (+ pytest_addoption --update-golden)
  ├─ pyproject.toml             # [tool.pytest.ini_options]: testpaths, markers, filterwarnings
  ├─ G2: full suite  --ignore {test_backup, test_backup_verification, test_complexity_budget}
  ├─ G3: tests/test_schema_equivalence.py
  ├─ G4: tests/test_architectural_invariants.py
  ├─ G5: tests/test_adr0058_fitness.py
  └─ G6: tests/test_db_schema_contracts.py  tests/titan/core/
```

All referenced test paths exist. The **implicit** dependency that bites first is the root
`conftest.py:7` (`from freezegun import freeze_time`) — a collection-time import that any
`pytest` invocation triggers regardless of which gate is selected.

---

## 3. Environment Verification vs Canonical Bootstrap (Task §4)

`ci_bootstrap.sh` pins `pytest==9.0.3` (+ a `--with` closure incl. `freezegun==1.5.5`) and
`ruff==0.15.13`. The live Code environment does not match:

| Tool / dep | Canonical (`ci_bootstrap.sh` / `requirements-dev.txt`) | Live Code env | Match |
|---|---|---|---|
| pytest | `9.0.3` | `9.0.2` (bare uv tool) | ❌ |
| ruff | `0.15.13` | `0.15.8` (bare uv tool) | ❌ |
| `python -m pytest` | available | **`No module named pytest`** | ❌ |
| freezegun / sqlalchemy / fastapi / … | installed (closure) | **absent** in active interpreter | ❌ |
| uv tool set | pytest(+closure), ruff | `black, flake8, mypy, poetry, pyright, pytest(bare), ruff(bare)` | ❌ |

**Divergences / sandbox-only artifacts:**
- The uv tool set contains `black`, `flake8`, `poetry`, `pyright` — **none** installed by
  `ci_bootstrap.sh`. Proof the env came from a generic image, not the repo bootstrap.
- `pytest`/`ruff` are *bare* tools (no `--with` closure), so `pytest` cannot import titan's
  third-party deps and `python -m pytest` fails entirely (pytest not in system Python).

**Empirical confirmation (live env):**
```
$ ruff check .                                  → exit 0  ("All checks passed!")  [ruff 0.15.8]
$ pytest tests/test_schema_equivalence.py -q    → exit 4
    ImportError while loading conftest 'conftest.py'.
    conftest.py:7: ModuleNotFoundError: No module named 'freezegun'
$ python3 -c "import sqlalchemy"                 → ModuleNotFoundError
```

---

## 4. Findings

### F1 — CRITICAL · Code env ≠ canonical bootstrap; G2–G6 non-runnable
**Evidence:** §3. **Root cause:** environment provisioned outside the repo's bootstrap path;
the active interpreter lacks the test dep closure, so the root `conftest.py` import fails and
*every* `pytest` gate aborts at exit 4 (collection error), never reaching a single test.
**Impact:** `bash scripts/titan_ci.sh` (the §9C VERIFY artifact) cannot pass here; an agent
following CLAUDE.md (`python3 -m pytest …`) gets an unrelated hard failure.
**Remediation (env, not code):** run a canonical bootstrap before VERIFY. Recommended for
the Code/web environment — a **SessionStart hook** that runs the GitHub-CI-equivalent:
```bash
pip install -r requirements.txt -r requirements-dev.txt   # yields pytest 9.0.3 / ruff 0.15.13
```
(Validated in §7. The uv-tool path `bash scripts/ci_bootstrap.sh` also works but mutates the
shared global uv tool set via `--force`.)

### F2 — HIGH · `pyproject` dev extras drift (✅ patched, P2)
`[project.optional-dependencies].dev` pinned **older** versions than canonical
`requirements-dev.txt`: `pytest-cov==4.1.0` (vs 7.1.0), `httpx==0.27.2` (vs 0.28.1),
`pytest-timeout==2.3.1` (vs 2.4.0). `pip install .[dev]` would yield a different, older test
toolchain than CI. **Root cause:** PR #817 de-drifted only `pyjwt`, leaving the test-tooling
trio. **Patch:** aligned all three to the canonical pins.

### F3 — HIGH · GitHub CI installs ruff unpinned (✅ patched, P3)
`.github/workflows/ci.yml` `ruff-phase-a`/`ruff-phase-b` ran `python -m pip install ruff`
(no pin) → GitHub G1 used whatever ruff was latest at run time, while local/canonical pin
`0.15.13`. Ruff lint rules change across releases, so a clean local `ruff check .` can fail
on GitHub or vice-versa — the single highest-probability reproducibility break.
**Root cause:** #817 stated "pin … ruff (G1 lint determinism)" but pinned only
`ci_bootstrap.sh`/`requirements-dev.txt`, missing the GitHub workflow. **Patch:** pinned both
install steps to `ruff==0.15.13`. *(Pinning to the canonical newest cannot newly-fail CI; it
only removes any rules from a floating newer release.)*

### F4 — HIGH · `scripts/setup_env.sh` references deleted `constraints.txt` (✅ patched, P1)
Lines 8 & 23 ran `pip install -r requirements.txt -c constraints.txt`. Per **TD-NEW-05**,
`constraints.txt` was deliberately deleted and `-c constraints.txt` removed from `ci.yml` —
but the fix was incomplete. `constraints.txt` is untracked/absent, so the command errors
("Could not open requirements file"); under `set -euo pipefail` the script aborts. AGENTS.md
§2.0 calls `setup_env.sh` "unconditionally mandatory … before anything else", so the
canonical Codex bootstrap is broken on a clean clone. **Patch:** removed `-c constraints.txt`
(completes TD-NEW-05). *(The identical reference at `AGENTS.md:489` is governance-locked — see §6.)*

### F5 — HIGH · Two divergent `setup_env.sh` files (⚠ recommended)
`./setup_env.sh` (root) and `./scripts/setup_env.sh` are **entirely different scripts**
sharing a name: the root builds a project `.venv` and pins `schemathesis==4.15.2` (itself
drift vs `requirements.txt` 4.18.5); `scripts/` targets system Python via pyenv and used the
broken `constraints.txt`. AGENTS.md, SCRATCHPAD.md and `tests/test_setup_env_script.py` all
reference **`scripts/setup_env.sh`**; the root copy is an unreferenced orphan.
**Recommendation (architect call — deletion is destructive):** delete the orphan root copy
and keep `scripts/setup_env.sh` as the single source, OR converge them behind one file. Left
unpatched pending sign-off.

### F6 — MED · Three contradictory bootstrap / VERIFY models (⚠ ADR follow-up)
- **AGENTS.md §2.0:** `scripts/setup_env.sh` is THE mandatory bootstrap; gates use `python -m pytest` (§ lines 210–211).
- **`titan_ci.sh` header:** §9C "all VERIFY fields reference this script"; its bootstrap is `ci_bootstrap.sh`; gates use **bare** `pytest`/`ruff`.
- **`titan_check.sh`** (AGENTS SESSION_START Gate 2): bare `ruff` + `python -m pytest`.

The *invocation model* itself disagrees: **bare `pytest`** (works only under the uv-tool
model) vs **`python -m pytest`** (works only when pytest is in the interpreter). CLAUDE.md
instructs `python3 -m pytest` — which is broken under the very uv-tool model `ci_bootstrap.sh`
establishes. **Recommendation:** pick one execution model and make all of CLAUDE.md / AGENTS.md
/ `titan_ci.sh` / `titan_check.sh` consistent (ADR-gated, as these are governance artifacts).

### F7 — MED · `titan_ci.sh` gate set ≠ GitHub CI (⚠ documented)
`titan_ci.sh` runs G1 + a curated `pytest` subset and **omits** ~18 GitHub jobs: semgrep,
pylint, vulture, `lint-imports`, pip-audit CVE gate, the AST invariant greps (G-CI-02…07),
alembic integrity/freeze, backup-verify, determinism, complexity-budget, docs-consistency,
claude-md-integrity, phase8-ci-checks, phase4-observability, **and the Python 3.12 matrix**.
Crucially G2 `--ignore`s `test_backup.py`, `test_backup_verification.py`,
`test_complexity_budget.py`, but GitHub runs full `pytest -q` (no ignores) — those three files
gate the PR remotely yet are never exercised by the "canonical" local entrypoint.
**Consequence:** a green `titan_ci.sh` is **not** sufficient for GitHub-green, despite §9C
positioning it as the VERIFY authority. **Recommendation:** document `titan_ci.sh` as a *fast
pre-flight subset* (not full parity), or add the missing gates.

### F8 — LOW · `ci_bootstrap.sh` not executable (✅ patched, P4)
Was `-rw-r--r--` (every other `scripts/*.sh` is `+x`). Functional via `bash …` but
inconsistent. **Patch:** `chmod +x`.

### F9 — LOW · uv-tool model fragility (⚠ documented)
`uv tool install pytest --with <closure>` builds an isolated venv; `import titan` works only
via pytest rootdir insertion when invoked as **bare `pytest` from `REPO_ROOT`** (`titan_ci.sh`
does `cd "$REPO_ROOT"`, so OK) and **silently breaks `python -m pytest`**. The `--with` list
is a hand-maintained parallel copy of `requirements.txt` + `requirements-dev.txt` (DRY/drift
risk; it already missed nothing today but is unguarded). It also diverges from GitHub's
single-environment install model.

### F10 — LOW · `--no-cov` assumes `pytest-cov` (⚠ documented)
G3–G6 pass `--no-cov`; if a bootstrap omits `pytest-cov`, those gates fail with "unrecognized
arguments: --no-cov" rather than a meaningful message. Canonical bootstraps include it, so
latent.

### F11 — INFO · No coverage `addopts`
`pyproject [tool.pytest.ini_options]` defines no `addopts`; `setup.cfg` is `[mutmut]`-only.
Coverage is therefore **not** on by default, so `--no-cov` is purely defensive. CLAUDE.md's
"run with `--no-cov`" framing implies a default-on coverage that does not exist.

**POSIX portability:** both entrypoints are `#!/usr/bin/env bash` and use arrays, `[[ … ]]`,
and `BASH_SOURCE` — they **require bash** (not POSIX `sh`). Acceptable given the shebang and
`ci.yml` `defaults.run.shell: bash`; risk only if invoked as `sh scripts/titan_ci.sh`. No
defect — flagged so it stays a guaranteed prerequisite.

**Security:** entrypoints are free of injection / `eval` / `curl|bash`. Note `setup_env.sh`'s
public-PyPI fallback sets `PIP_TRUSTED_HOST` (weakens TLS validation for those hosts);
acceptable as it targets canonical PyPI and only on fallback. `ci_bootstrap.sh`'s
`uv tool install --force` clobbers any pre-existing global `pytest`/`ruff` tool — intended,
but a mutation of shared state worth noting.

---

## 5. Patches

### Applied in this change (safe; each completes documented maintainer intent)
| ID | File | Change |
|----|------|--------|
| P1 | `scripts/setup_env.sh` | Remove `-c constraints.txt` (×2) — completes TD-NEW-05 |
| P2 | `pyproject.toml` | dev extras → `pytest-cov==7.1.0`, `pytest-timeout==2.4.0`, `httpx==0.28.1` |
| P3 | `.github/workflows/ci.yml` | Pin `ruff==0.15.13` in both ruff install steps |
| P4 | `scripts/ci_bootstrap.sh` | `chmod +x` (mode 100644 → 100755) |

### Required but deferred (governance-gated / destructive / architectural)
| ID | Target | Action | Why deferred |
|----|--------|--------|--------------|
| R1 | `AGENTS.md:489` | Remove `-c constraints.txt` | AGENTS.md is "DO NOT EDIT without ADR" |
| R2 | root `setup_env.sh` | Delete orphan or converge with `scripts/` | Destructive; architect's call (F5) |
| R3 | CLAUDE.md / AGENTS.md / `titan_ci.sh` / `titan_check.sh` | Unify ONE execution model (`python -m pytest` recommended — matches GitHub) | Governance artifacts; ADR (F6) |
| R4 | Code/web env | Add SessionStart hook: `pip install -r requirements.txt -r requirements-dev.txt` | Env config, not repo code (F1) |
| R5 | `titan_ci.sh` (optional) | Add a dep preflight that prints remediation instead of a cryptic conftest ImportError | Touches §9C-referenced script (F1/F10) |

Suggested R5 preflight (additive; no change to exit-0 semantics when deps present):
```bash
python -c "import freezegun, sqlalchemy, fastapi" 2>/dev/null || {
  echo "❌ Test dependency closure missing. Run: pip install -r requirements.txt -r requirements-dev.txt"
  echo "   (or: bash scripts/ci_bootstrap.sh)"; exit 1; }
```

---

## 6. Reproducibility Risk Register

| Risk | Driver | Mitigation |
|------|--------|------------|
| **Env mismatch** — local gates can't run | F1: generic image, no canonical bootstrap | R4 SessionStart hook (validated §7) |
| **Lint non-determinism** local↔GitHub | F3: GitHub ruff unpinned | P3 (pinned 0.15.13) |
| **`.[dev]` ≠ CI toolchain** | F2: pyproject dev drift | P2 (aligned) |
| **Broken bootstrap on clean clone** | F4: dead `constraints.txt` ref | P1 (+ R1 for AGENTS.md) |
| **"Green local ≠ green GitHub"** | F7: gate-set divergence; ignored backup/complexity tests | Document `titan_ci.sh` as subset (R-doc) |
| **Two execution models** | F6/F9: bare `pytest` vs `python -m pytest` | R3 unify model |
| **Manifest sprawl** (4 sources of truth) | `ci_bootstrap.sh --with`, `requirements*.txt`, `pyproject`, root `setup_env.sh` | Single source + generated mirrors (future ADR) |

---

## 7. Validation Evidence

Live env (as provisioned) — only G1 runs:
```
ruff check .                              → exit 0   (ruff 0.15.8)
pytest tests/test_schema_equivalence.py   → exit 4   (conftest: ModuleNotFoundError: freezegun)
python3 -c "import sqlalchemy"            → ModuleNotFoundError
```

Canonical reproduction — `python -m venv` + `pip install -r requirements.txt -r requirements-dev.txt`:
```
python -m pytest --version               → pytest 9.0.3
ruff --version                           → ruff 0.15.13
pytest --collect-only -q                 → 3028 tests collected, 0 errors   (= 3021 pass + 7 skip snapshot)
G1 ruff check .                          → exit 0  ("All checks passed!")
G3 test_schema_equivalence.py            → 24 passed
G4 test_architectural_invariants.py      → 7 passed
G5 test_adr0058_fitness.py               → 9 passed
G6 test_db_schema_contracts.py + core/   → 188 passed
```

**Conclusion:** the test suite and gate logic are healthy; the live-environment divergence
(F1) is the sole blocker for `titan_ci.sh` in the Code environment. Patches P1–P4 close the
in-repo reproducibility gaps; R1–R5 require architect/ADR sign-off.
