# CI Execution Surface Audit — TITAN OS

- **Mode:** ARCHITECT · **Operating Contract:** v7.8 §9C · **Date:** 2026-06-06
- **Scope:** `scripts/ci_bootstrap.sh`, `scripts/titan_ci.sh`, their full transitive
  reference/dependency closure, and verification of the Code (cloud) execution
  environment against the canonical bootstrap.
- **Method:** Static discovery + live probing + **empirical end-to-end reproduction**
  (bootstrap → run patched entrypoint) in this Code environment.
- **Supersedes:** `CI_SURFACE_AUDIT_2026-06-05.md` (re-audit after the ADR-0059 migration
  landed in `#830`/`#831` on 2026-06-06). F1 has materially changed and **regressed**.

---

## 1. Executive Summary

The ADR-0059 "unified `python -m pytest`" migration **landed in the scripts today**
(`916e977` #830 → `.venv` model + `titan_ci.sh` to `python -m`; `44c23ab` #831 → CLAUDE.md
+ `titan_check.sh`). The script half of ADR-0059 shipped; **the environment half did not.**
The Code sandbox is still the generic uv-tool image with no `.venv` and no project
dependencies in the interpreter `python` resolves to.

**Net effect — a regression.** Before the migration the canonical entrypoint ran **1 of 6**
gates here (`ruff check .` as a bare uv-tool); after it, the entrypoint invokes
`python -m ruff` / `python -m pytest`, and the active `python` owns **neither** module — so
**0 of 6** gates are now runnable. The previously-working G1 now fails too:

```
$ python -m ruff check .     → exit 1   "/usr/local/bin/python: No module named ruff"
$ python -m pytest …         → exit 1   "/usr/local/bin/python: No module named pytest"
$ pytest …  (bare uv shim)   → exit 4   conftest.py:7 ModuleNotFoundError: No module named 'freezegun'
```

A second, harder constraint surfaced during remediation: the system interpreter carries
**Debian-managed packages** (`PyJWT 2.7.0`, `cryptography 41.0.7`, `requests`) with no
`RECORD` file, so `pip install -r requirements.txt` *into the system interpreter* aborts
(`Cannot uninstall PyJWT 2.7.0, RECORD file not found`). The 2026-06-05 audit's recommended
fix (R4: pip-install the closure into system Python via a SessionStart hook) **would fail
here.** The only robust path in this image is a **venv** — which is exactly what
`scripts/ci_bootstrap.sh` already builds.

This audit ships a working, validated fix and closes the in-repo robustness gaps:

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| F1 | **CRITICAL** | ADR-0059 migration regressed the Code env: `python -m {ruff,pytest}` → "No module named …"; **0/6 gates runnable** | ✅ Fixed (P-A,P-B,P-C) — validated §7 |
| F2 | **HIGH** | System interpreter has Debian-managed pkgs (no `RECORD`) → `pip install -r requirements.txt` into system Python fails; R4 (06-05) is unviable | ✅ Mitigated (P-A venv) |
| F3 | **HIGH** | `titan_ci.sh`/`titan_check.sh` assumed an *activated* venv; bare `python -m` neither activates nor locates `.venv` (breaks fresh/automation shells) | ✅ Fixed (P-B,P-C) |
| F4 | **MED** | Live tool drift vs pins: `pytest 9.0.2`≠`9.0.3`, `ruff 0.15.8`≠`0.15.13`; uv set (black/flake8/mypy/poetry/pyright) not from any repo bootstrap | ✅ Resolved by venv bootstrap |
| F5 | **MED** | `AGENTS.md:489` still installs with deleted `-c constraints.txt`; bootstrap model still dual (`setup_env.sh` vs `ci_bootstrap.sh`) | ⚠ Deferred (governance-locked) |
| F6 | **MED** | `titan_ci.sh` gate set ⊊ GitHub CI; G2 `--ignore`s 3 files GitHub runs → green-local ≠ green-remote | ⚠ Documented (design call) |
| F7 | LOW | pre-commit hooks still call **bare** `ruff` (ADR-0059 residue) | ✅ Aligned (P-D) |
| F8 | LOW | ADR-0059 implementation checklist all unchecked though items are done | ✅ Reconciled (P-E) |
| F9 | LOW | `--no-cov` (G3–G6) couples gates to `pytest-cov`; no coverage `addopts` exists → flag is defensive-only | ⚠ Documented |
| F10 | INFO | `titan_check.sh` pass/fail parsing greps lowercase `error` (over-broad) | ⚠ Documented |

---

## 2. Discovered CI Execution Surface (dependency graph)

Neither entrypoint `source`s another script; both have shallow, well-bounded graphs.

```
scripts/ci_bootstrap.sh
  ├─ python3 (3.11+ guard — added P-B)
  ├─ python3 -m venv .venv
  └─ .venv/bin/pip install -r requirements.txt
                          -r requirements-dev.txt   (pinned; full closure)

scripts/titan_ci.sh   (cd "$REPO_ROOT"; resolves $PY → venv|system — added P-B)
  ├─ $PY -m ruff                       # G1
  ├─ $PY -m pytest                     # G2–G6
  ├─ conftest.py (root)                # imports freezegun  ← collection-time hard dep
  ├─ tests/conftest.py                 # imports titan.* (+ pytest_addoption --update-golden)
  ├─ pyproject.toml [tool.pytest.ini_options]  # testpaths, markers, filterwarnings (no addopts)
  ├─ G2: full suite --ignore {test_backup, test_backup_verification, test_complexity_budget}
  ├─ G3: tests/test_schema_equivalence.py
  ├─ G4: tests/test_architectural_invariants.py
  ├─ G5: tests/test_adr0058_fitness.py
  └─ G6: tests/test_db_schema_contracts.py  tests/titan/core/
```

All referenced test paths exist. The **implicit** dependency that bites first is the root
`conftest.py:7` (`from freezegun import freeze_time`) — a collection-time import every
`pytest` invocation triggers regardless of the selected gate.

---

## 3. Environment Verification vs Canonical Bootstrap (Task §4)

`ci_bootstrap.sh` builds a `.venv` from `requirements.txt` + `requirements-dev.txt`
(`pytest==9.0.3`, `ruff==0.15.13`, `freezegun==1.5.5`, `sqlalchemy`, `fastapi`, …). The
live Code environment **as provisioned** does not match on any axis:

| Tool / dep | Canonical (`ci_bootstrap.sh`) | Live Code env (as provisioned) | Match |
|---|---|---|---|
| bootstrap artifact | repo-local `.venv` | **absent** | ❌ |
| `python -m pytest` | resolves (venv python) | **`No module named pytest`** | ❌ |
| `python -m ruff` | resolves (venv python) | **`No module named ruff`** | ❌ |
| pytest | `9.0.3` | `9.0.2` (uv tool, bare) | ❌ |
| ruff | `0.15.13` | `0.15.8` (uv tool, bare) | ❌ |
| freezegun / sqlalchemy / fastapi / hypothesis | installed | **absent** in active interpreter | ❌ |
| tool set | pytest+closure, ruff (venv) | `black, flake8, mypy, poetry, pyright, pytest, ruff` (uv tools) | ❌ |
| `import-linter` / `mutmut` / `pip-audit` | installed (in requirements.txt) | **absent** | ❌ |

**Sandbox-only artifacts / divergences:**
- `uv tool list` ⇒ `black v26.3.1, flake8 v7.3.0, mypy v1.19.1, poetry v2.3.3, pyright
  v1.1.408, pytest v9.0.2, ruff v0.15.8` — **none** installed by `ci_bootstrap.sh`. Proof the
  env came from a generic toolchain image, not the repo bootstrap.
- `pytest`/`ruff` are *bare* uv tools (their own isolated venvs); they cannot import titan's
  third-party deps, and `python -m pytest` fails outright (pytest not in the active interpreter).
- The system interpreter (`/usr/local/bin/python` 3.11.15) reads Debian `dist-packages`
  carrying `PyJWT 2.7.0`, `cryptography 41.0.7`, `requests` **without `RECORD` files** → not
  pip-upgradable (F2). `pip`-on-PATH is `/usr/bin/pip` (a *different* interpreter), so even a
  successful `pip install` need not land in the interpreter `python` resolves to.

**Empirical confirmation (live env, before fix):** see §1 transcript; plus
`python3 -c "import sqlalchemy"` → `ModuleNotFoundError`, `ls .venv` → absent.

**Conclusion (Task §4):** the Code environment did **not** match the canonical bootstrap.
The fix (P-A) makes a SessionStart hook **run `ci_bootstrap.sh`**, so the environment now
*is* the canonical bootstrap (validated §7).

---

## 4. Findings

### F1 — CRITICAL · ADR-0059 migration regressed the Code env (0/6 gates runnable)
**Evidence:** §1, §3. **Root cause:** ADR-0059 has two halves — (a) migrate artifacts to
`python -m pytest`/`python -m ruff`, and (b) ensure a `python` that owns the closure exists
(canonical order: `bash scripts/ci_bootstrap.sh` → `source .venv/bin/activate`). Half (a)
landed in `#830`/`#831`; half (b) never ran in the Code sandbox (no `.venv`; nothing
activated; the harness re-initialises each tool shell from profile, so an activation would
not persist anyway). The migration therefore moved the failure *earlier* — from "G1 runs,
G2–G6 fail at collection" to "every gate fails at interpreter resolution" — a strict
regression for this environment. **Impact:** `bash scripts/titan_ci.sh` (the §9C VERIFY
artifact) cannot reach a single assertion; an agent following CLAUDE.md (`python -m pytest
--no-cov -q`) gets an unrelated hard failure. **Fix:** P-A (SessionStart hook runs
`ci_bootstrap.sh` + persists `.venv` to PATH), P-B/P-C (entrypoints auto-locate `.venv`).

### F2 — HIGH · System-interpreter Debian packages block a system-Python bootstrap
**Evidence:** `python -m pip install -r requirements.txt` → `ERROR: Cannot uninstall PyJWT
2.7.0, RECORD file not found. Hint: The package was installed by debian.` (pip 24.0 itself is
likewise OS-managed). **Root cause:** the base image installs `PyJWT`/`cryptography`/`requests`
as distro packages without `RECORD`, so pip refuses to replace them with the pinned versions.
**Impact:** the 2026-06-05 audit's R4 ("SessionStart hook: `pip install -r requirements.txt
-r requirements-dev.txt`" into system Python) is **not viable in this image** — it aborts
mid-install, leaving a half-populated, version-skewed interpreter. **Fix:** P-A bootstraps a
**venv** (no `--system-site-packages`), which is isolated from `dist-packages` and installs
the pins cleanly (validated: venv yields `pyjwt 2.13.0`, `pytest 9.0.3`, `ruff 0.15.13`).

### F3 — HIGH · Entrypoints assumed an *activated* venv; not self-locating
ADR-0059's canonical order relies on a human running `source .venv/bin/activate` between
bootstrap and verify. CI runners, the Code harness (per-call shells), and any "just run the
script" automation skip that step, so bare `python -m pytest` hits the **system** interpreter
and fails. `titan_ci.sh`/`titan_check.sh` neither activated nor located `.venv`. **Fix:**
P-B/P-C add interpreter resolution — prefer `$VIRTUAL_ENV`, else repo-local `.venv/bin/python`,
else PATH `python3`/`python` — so `bash scripts/ci_bootstrap.sh && bash scripts/titan_ci.sh`
works with **no** manual activation. This keeps the ADR-0059 `python -m` model (the module is
still run via `-m`), only making the interpreter explicit. A dependency **preflight** was
added to `titan_ci.sh`: a missing closure now prints remediation instead of `No module named
ruff`.

### F4 — MED · Live tool/version drift vs pins
Live `pytest 9.0.2` / `ruff 0.15.8` vs canonical `9.0.3` / `0.15.13`. Ruff lint rules change
across patch releases, so a green local `ruff check .` under `0.15.8` can disagree with the
`0.15.13` GitHub gate (`ci.yml` pins `0.15.13`). The uv tool set also includes `black`,
`flake8`, `poetry`, `pyright` that no repo path installs. **Fix:** the venv bootstrap (P-A)
installs the exact pins; post-fix the env reports `ruff 0.15.13` / `pytest 9.0.3`.

### F5 — MED · `AGENTS.md:489` dead `constraints.txt`; dual bootstrap model (⚠ deferred)
`AGENTS.md:489` still runs `pip install -r requirements.txt -c constraints.txt`;
`constraints.txt` was deleted (TD-NEW-05) and is absent, so the command errors. AGENTS.md
§2.0 (line 205) also mandates `scripts/setup_env.sh` "before anything else", while ADR-0059's
canonical bootstrap is `scripts/ci_bootstrap.sh` — the **bootstrap model is still dual**
(`setup_env.sh` pyenv+system-pip vs `ci_bootstrap.sh` venv) even though the *execution* model
was unified. **Deferred:** AGENTS.md is "DO NOT EDIT without ADR" (CLAUDE.md). Recommend an
ADR addendum to (a) drop `-c constraints.txt` at line 489 and (b) name `ci_bootstrap.sh` as
the single bootstrap, demoting `setup_env.sh` or converging it.

### F6 — MED · `titan_ci.sh` gate set ⊊ GitHub CI (⚠ documented design call)
`titan_ci.sh` = G1 + a curated `pytest` subset. It **omits ~18 GitHub jobs**: semgrep,
pylint, vulture, `lint-imports`, the pip-audit CVE gate, the AST/grep invariants (G-CI-02…07),
alembic integrity + freeze guard, backup-verify, determinism (3×), complexity-budget,
docs-consistency, claude-md-integrity, phase8-ci-checks, phase4-observability, **and the
Python 3.12 matrix leg**. Critically, G2 `--ignore`s `test_backup.py`,
`test_backup_verification.py`, `test_complexity_budget.py` (all `@pytest.mark.integration`,
shelling out to `find` / `scripts/backup.sh` / `verify_backup.py`), but GitHub's `test` job
runs plain `pytest --tb=short -q` over `testpaths=["."]` — **so those three files gate the PR
remotely yet never run in the "canonical" local entrypoint.** A green `titan_ci.sh` is
therefore *not* sufficient for GitHub-green, despite §9C positioning it as the VERIFY
authority. **Recommendation:** either (a) explicitly document `titan_ci.sh` as a *fast
pre-flight subset* (not parity), or (b) drop the three `--ignore`s and add the missing
non-pytest gates behind a `--full` flag. (Carried from 06-05 F7; unchanged.)

### F7 — LOW · pre-commit hooks still call bare `ruff` (✅ aligned, P-D)
`scripts/git_hooks/pre-commit:29` (`if ruff check .`) and `.pre-commit-config.yaml:9`
(`entry: ruff check .`) are ADR-0059 residue — the ADR decided on `python -m ruff`. Functional
under an activated venv but inconsistent with the unified model. **Patch:** both switched to
`python -m ruff check .`.

### F8 — LOW · ADR-0059 checklist unchecked though implemented (✅ reconciled, P-E)
Every box in `docs/adr/0059-pytest-execution-model.md` is `[ ]`, yet `ci_bootstrap.sh`
(venv), `titan_ci.sh`/`titan_check.sh` (`python -m`), CLAUDE.md, and the root `setup_env.sh`
deletion are all done. A reader cannot tell ADR-0059 shipped. **Patch:** ticked the completed
items with the implementing references (`#830`, `#831`, this PR).

### F9 — LOW · `--no-cov` couples G3–G6 to `pytest-cov` (⚠ documented)
G3–G6 pass `--no-cov`; valid **only** when `pytest-cov` is installed (else "unrecognized
arguments: --no-cov", exit 4). `pyproject [tool.pytest.ini_options]` defines **no `addopts`**
and `setup.cfg` is `[mutmut]`-only, so coverage is never auto-on and `--no-cov` is purely
defensive. Canonical bootstraps include `pytest-cov` (requirements-dev), so this is latent —
but it makes a small, surprising hard dependency. CLAUDE.md's "run with `--no-cov`" framing
implies a default-on coverage that does not exist.

### F10 — INFO · `titan_check.sh` pass/fail parsing is over-broad
Gates 2/3 classify failure via `grep -qE '(FAILED|ERROR|error)'` over `pytest` output. The
lowercase `error` token matches benign strings — e.g. failure nodeids/paths containing
"error" (`tests/test_ctl_atl_data_error.py`), warning summaries, deprecation text — risking
misclassification. The robust signal (process exit code) is already captured (`… 2>&1) ||
true`) but discarded in favour of grep. `titan_ci.sh` does this correctly (uses exit codes
via `run_gate`). **Recommendation:** drive `titan_check.sh` PASS/FAIL from the captured exit
code; keep the count grep only for reporting.

**POSIX portability.** Both entrypoints are `#!/usr/bin/env bash` and use arrays, `[[ … ]]`,
and `BASH_SOURCE` — they **require bash**, not POSIX `sh`. Acceptable given the shebang and
`ci.yml` `defaults.run.shell: bash`; the only risk is invoking `sh scripts/titan_ci.sh`.
`"${FAILED_GATES[@]}"` empty-array expansion under `set -u` is safe — it is referenced only in
the FAIL branch (array non-empty there), and bash ≥4.4 tolerates empty-array expansion anyway.

**Security.** The `titan_ci.sh` closure is free of `eval`/injection/`curl|bash`. Notes on the
wider surface: `scripts/setup_env.sh`'s public-PyPI fallback sets `PIP_TRUSTED_HOST`
(weakens TLS validation for `pypi.org`/`files.pythonhosted.org`) — acceptable (canonical host,
fallback-only) but a hermeticity caveat; `.github/workflows/secret-scan.yml` installs gitleaks
via `curl … | tar` with **no checksum** (version-pinned only) — supply-chain note (GitHub
surface, outside the `titan_ci.sh` closure). The current `ci_bootstrap.sh` is venv-only — the
06-05 note about `uv tool install --force` mutating shared global state no longer applies
(rewritten in `#830`).

---

## 5. Patches

### Applied in this PR (validated; each completes documented maintainer intent)
| ID | File | Change |
|----|------|--------|
| P-A | `.claude/hooks/session-start.sh` + `.claude/settings.json` | **New** SessionStart hook (web): runs `scripts/ci_bootstrap.sh` and persists `.venv` to PATH via `CLAUDE_ENV_FILE`. Makes the Code env == canonical bootstrap (F1/F2). |
| P-B | `scripts/titan_ci.sh` | Interpreter resolution (`$VIRTUAL_ENV` → `.venv` → PATH) + dependency preflight with remediation; gates now run `"$PY" -m …` (F1/F3). |
| P-B′ | `scripts/ci_bootstrap.sh` | Enforce the documented Python 3.11+ prerequisite before building `.venv`. |
| P-C | `scripts/titan_check.sh` | Mirror the interpreter resolution; gates run `"$PY" -m …` (F3). |
| P-D | `scripts/git_hooks/pre-commit`, `.pre-commit-config.yaml` | Bare `ruff check .` → `python -m ruff check .` (ADR-0059 consistency, F7). |
| P-E | `docs/adr/0059-pytest-execution-model.md` | Tick the implementation checklist (done in `#830`/`#831`/this PR), F8. |

### Required but deferred (governance-gated / design)
| ID | Target | Action | Why deferred |
|----|--------|--------|--------------|
| R1 | `AGENTS.md:489` + §2.0 | Drop `-c constraints.txt`; name `ci_bootstrap.sh` as the single bootstrap | AGENTS.md is "DO NOT EDIT without ADR" (F5) |
| R2 | `titan_ci.sh` / governance | Document as *fast subset* OR add the ~18 missing gates + drop the 3 `--ignore`s behind `--full` | §9C VERIFY semantics; ADR call (F6) |
| R3 | `titan_check.sh` | Drive PASS/FAIL from exit code, not `grep error` | Low risk but touches a pre-commit gate-of-record (F10) |

---

## 6. Reproducibility Risk Register

| Risk | Driver | Mitigation |
|------|--------|------------|
| **Code env can't run any gate** | F1: ADR-0059 script-half only; generic image | ✅ P-A SessionStart hook (validated §7) |
| **System-Python bootstrap aborts** | F2: Debian pkgs without `RECORD` | ✅ P-A uses venv (isolated from dist-packages) |
| **Fresh/automation shell hits system python** | F3: implicit-activation assumption | ✅ P-B/P-C auto-locate `.venv` |
| **Lint disagreement local↔GitHub** | F4: live ruff `0.15.8` vs pinned `0.15.13` | ✅ venv installs the pin |
| **"Green local ≠ green GitHub"** | F6: gate-set divergence; 3 ignored integration tests | ⚠ R2 (document subset / add gates) |
| **Broken bootstrap instruction on clean clone** | F5: dead `constraints.txt` in AGENTS.md | ⚠ R1 (ADR-gated) |
| **`--no-cov` hard-fails if `pytest-cov` absent** | F9: defensive flag, plugin coupling | bootstrap includes `pytest-cov`; documented |

---

## 7. Validation Evidence

**Hook → canonical bootstrap (this Code env), exit 0:**
```
CLAUDE_CODE_REMOTE=true ./.claude/hooks/session-start.sh
  → scripts/ci_bootstrap.sh: "Python 3.11.15 — OK"; creates .venv; installs closure
  → persisted VIRTUAL_ENV + PATH to CLAUDE_ENV_FILE
  → .venv/bin/python -m ruff --version   → ruff 0.15.13     (pin restored)
  → .venv/bin/python -m pytest --version → pytest 9.0.3      (pin restored)
  → import freezegun, sqlalchemy, fastapi, hypothesis → OK
  real ~25s
```

**Patched gates with NO venv activated (`VIRTUAL_ENV` unset → exercises `.venv`
auto-detection in P-B); interpreter resolves to `.venv/bin/python` 3.11.15:**
```
G1 ruff check .                          → exit 0   (ruff 0.15.13)
G3 test_schema_equivalence.py            → 24 passed
G4 test_architectural_invariants.py      → 7 passed
G5 test_adr0058_fitness.py               → 9 passed
G6 test_db_schema_contracts.py + core/   → 188 passed
```
(G2 is the full ~3028-test suite; its health/collection — 3021 pass + 7 skip — was
established in CI_SURFACE_AUDIT_2026-06-05 §7 and is unchanged by these script-only patches.)

**Negative test (preflight):** against the system interpreter (no closure), the P-B preflight
correctly fails fast and prints the `bash scripts/ci_bootstrap.sh` remediation instead of a
bare `No module named ruff`.

**Conclusion:** the suite and gate logic are healthy; the environment divergence (F1/F2) was
the sole blocker, and it is closed by P-A (env == canonical bootstrap) and made
self-healing by P-B/P-C (entrypoints locate the venv without manual activation).
</content>
