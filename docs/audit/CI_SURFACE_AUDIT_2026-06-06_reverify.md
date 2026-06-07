# CI Execution Surface Audit — TITAN OS (Re-verification Pass)

- **Mode:** ARCHITECT · **Operating Contract:** v7.8 §9C · **Date:** 2026-06-06
- **Scope:** `scripts/ci_bootstrap.sh`, `scripts/titan_ci.sh`, their full transitive
  reference/dependency closure, the adjacent `scripts/**/*.sh` CI surface, and verification
  of the Code (cloud) execution environment against the canonical bootstrap.
- **Method:** Independent static discovery + live probing + **cold-start, end-to-end
  reproduction** in a fresh Code session — the canonical entrypoint was executed *to
  completion* (full G2), which is what surfaced the headline finding.
- **Relationship to prior audits:** Independent re-audit *after* the ADR-0059 remediation
  chain (`#828`→`#832`) landed on `claude/pensive-lovelace-jPGUB`. It **verifies** the
  environment claims of `CI_SURFACE_AUDIT_2026-06-06.md` (now correct) and **corrects** its
  suite-health claim: the §9C entrypoint was in fact **RED**.

---

## 1. Executive Summary

The environment half of the surface is **healthy and reproducible**: on cold start the
SessionStart hook (`.claude/hooks/session-start.sh`) runs the canonical bootstrap
(`scripts/ci_bootstrap.sh`), builds `.venv` with the exact pins (`pytest 9.0.3`,
`ruff 0.15.13`, full closure), and persists it to `PATH`. The Code environment **matches** the
canonical bootstrap on every axis the 2026-06-05/06-06 audits found divergent (§3).

**But the canonical §9C gate was RED.** This is the first audit to run `bash scripts/titan_ci.sh`
*to completion* in any environment after the P15-ARCH5 migration steps (`#825`→`#827`); the
prior audits validated only `--collect-only` + G1/G3/G4/G5/G6 and **assumed** G2's health from
the Phase-24 snapshot. Run in full, **G2 failed: 45 failed, 2968 passed, 6 skipped**.

**Root cause (single):** the in-progress **P15-ARCH5 pydantic-settings migration** put
`@functools.lru_cache(maxsize=1)` on `get_settings()` (`titan/config/settings.py:34`). Because
every env-derived read now funnels through that cached singleton, the migration introduced
three failure modes, all in test/robustness behaviour (production runtime, where env is fixed
at process start, is unaffected):

1. **Cross-test cache leak (~43 tests).** A `get_settings()` call in one test caches a settings
   object built from the *then-current* environment; later tests' `monkeypatch.setenv(...)` are
   silently shadowed. Failures are therefore *collection-order dependent* (auth/JWT, audit
   middleware, Garmin token encryption, ML kill-switch, telegram, schemathesis).
2. **Intra-test env toggling (1 test).** `test_is_dev_environment_detection` flips `TITAN_ENV`
   four times in one body; the cache snapshots the first value.
3. **Production robustness regression (1 test).** A single malformed `GARMIN_SYNC_TIMEOUT_S`
   (e.g. `"abc"`) now makes `TitanSettings()` *raise at construction* (typed-`int` field), so
   `_resolve_sync_timeout_seconds()` crashes instead of falling back to the default — and, more
   broadly, one bad env var breaks **every** `get_settings()` consumer in the process.

All three are fixed in this PR (with owner approval), restoring G2 to green. The remaining
items are two LOW–MED hardening gaps in the entrypoint's own preflight (patched, behaviour-
neutral) and the previously-deferred, **governance-locked** AGENTS.md divergences.

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| **C1** | **CRITICAL** | §9C gate `titan_ci.sh` G2 RED (45 fail) — P15-ARCH5 `lru_cache(get_settings)` regression: cross-test leak + intra-test toggling + malformed-env crash | ✅ Fixed (P1a/P1b/P1c) — verified §7 |
| **C2** | **HIGH** | **Process gap:** no audit (nor the CLAUDE.md "3021 green" snapshot) had executed the §9C entrypoint's full G2 post-`#827`; "green" was assumed from a subset → a CRITICAL regression shipped undetected | ✅ Surfaced; see Recommendation |
| V1 | **CRITICAL→RESOLVED** | Code env == canonical bootstrap (cold-start hook self-heals) | ✅ Verified §3/§7 |
| V2 | **MED** | `titan_ci.sh` preflight under-covers the gate closure: omits `pytest_cov` (hard-required by `--no-cov` in G3–G6) and `hypothesis` (collection-time in G2) | ✅ Patched (P2) |
| V3 | **LOW** | G2 `--ignore` rationale undocumented (it is a deliberate cross-platform hedge, not an accidental hole) | ✅ Patched (P3, comment-only) |
| V4 | **MED** | §9C local entrypoint ⊊ remote `ci.yml` (gate subset; 3.11-only vs 3.11/3.12 matrix; `--strict-markers` asymmetry) | ⚠ By design per §9C; documented |
| V5 | **MED** | `AGENTS.md:489` dead `-c constraints.txt`; §2.0 mandates `setup_env.sh` while §9C/ADR-0059 canonical bootstrap is `ci_bootstrap.sh` (dual bootstrap) | ⚠ Deferred — governance-locked (ADR-gated) |
| V6 | **LOW** | `titan_check.sh` derives PASS/FAIL by `grep`-ing lowercase `error` over pytest output; the captured exit code is discarded via `|| true` | ⚠ Deferred — pre-commit gate-of-record |
| V7 | **LOW/INFO** | Supply-chain: `ci_bootstrap.sh` installs pinned-but-**unhashed** deps; no CVE/drift gate in the local bootstrap (present only in remote `ci.yml`) | ⚠ Documented |
| V8 | **LOW/INFO** | `ci_bootstrap.sh` reuses an existing `.venv` without re-validating its interpreter against the 3.11+ guard | ⚠ Documented |

---

## 2. Discovered CI Execution Surface (dependency closure)

Neither entrypoint `source`s another script; both have shallow, well-bounded graphs. No
`scripts/**/*.d/*` directories exist. The full closure (autonomously discovered):

```
.claude/hooks/session-start.sh        (Code-web only: CLAUDE_CODE_REMOTE=true)
  └─ scripts/ci_bootstrap.sh          (canonical bootstrap)
       ├─ python3 (3.11+ guard) ; python3 -m venv .venv
       ├─ .venv/bin/pip install -r requirements.txt      (pinned ==)
       └─ .venv/bin/pip install -r requirements-dev.txt  (pinned ==)
  └─ CLAUDE_ENV_FILE ← export VIRTUAL_ENV + PATH=.venv/bin:$PATH   (session-wide)

scripts/titan_ci.sh   (§9C VERIFY entrypoint; cd "$REPO_ROOT")
  ├─ interpreter resolution: $VIRTUAL_ENV → repo .venv → PATH python3/python
  ├─ dependency preflight  (import closure probe + python -m ruff --version)
  ├─ G1 $PY -m ruff check .
  ├─ G2 $PY -m pytest --strict-markers --ignore{backup,backup_verification,complexity_budget}
  ├─ G3–G6 targeted pytest … --no-cov
  ├─ conftest.py (root)   → freezegun (collection-time) + autouse get_settings cache reset (NEW)
  ├─ tests/conftest.py    → titan.* factories ; pytest_addoption --update-golden
  └─ pyproject.toml [tool.pytest.ini_options]  → testpaths=["."], markers, filterwarnings (no addopts)

Implicit runtime dep the gate exercises (newly relevant to C1):
  titan/config/settings.py :: get_settings()  @functools.lru_cache(maxsize=1)
    └─ read by ml_safety, api/auth, api/audit, integrations/garmin_sync, … (env-derived config)
```

All referenced test paths exist. The first implicit dep that bites a bare interpreter is the
root `conftest.py` (`freezegun`); the dep that bit the *gate* is the cached `get_settings()`.

---

## 3. Environment Verification vs Canonical Bootstrap (Task §4) — MATCH

| Tool / dep | Canonical (`ci_bootstrap.sh`) | Live Code env (this session) | Match |
|---|---|---|---|
| bootstrap artifact | repo-local `.venv` | present | ✅ |
| `python -m pytest` / `-m ruff` | resolves (venv python) | `pytest 9.0.3` / `ruff 0.15.13` | ✅ |
| freezegun / hypothesis / sqlalchemy / fastapi / pytest-cov | installed | importable | ✅ |
| import-linter / mutmut / pip-audit / schemathesis | installed | present in `pip freeze` | ✅ |
| `VIRTUAL_ENV` on PATH | persisted by hook | `=.venv`; `which python`→`.venv/bin/python` | ✅ |

**Conclusion (Task §4):** the Code environment matches the canonical bootstrap, reproducibly,
*because* the hook runs that exact bootstrap on every cold start. No sandbox-only artifacts
remain in the active interpreter. (This was the inverse of the pre-`#832` state.) Crucially,
**environment parity is necessary but not sufficient** — the gate still failed on a *code*
regression (C1) that only an end-to-end run exposed.

---

## 4. Findings

### C1 — CRITICAL · §9C gate RED: P15-ARCH5 `lru_cache(get_settings)` regression (FIXED)
**Evidence:** `bash scripts/titan_ci.sh` → G2 `45 failed, 2968 passed, 6 skipped`. Reduced to
the mechanism by bisection: `test_kill_switch_disabled_when_env_is_zero` **passes alone** but
**fails after a sibling runs** — the sibling's `is_ml_kill_switch_enabled()` populates the
`get_settings` `lru_cache` with the default `TITAN_ML_KILL_SWITCH="1"`, which then shadows the
test's `monkeypatch.setenv("TITAN_ML_KILL_SWITCH","0")`. A direct probe confirms the production
logic is correct (fresh cache + `env=0` → disabled). **Root cause:** `titan/config/settings.py:34`
`@functools.lru_cache(maxsize=1)` on `get_settings()` makes settings a process-global snapshot;
the env-sensitive test suite (and one production fallback path) assumed live per-call reads. The
existing idiom in `tests/test_garmin_sync.py` (`get_settings.cache_clear()` + finalizer) shows
the intended contract — it simply was not applied suite-wide when the cache was introduced.
**Sub-causes & fixes (owner-approved):**
- **P1a (test infra):** autouse `get_settings.cache_clear()` fixture in root `conftest.py`,
  before+after every test → fixes the ~43 cross-test-leak failures.
- **P1b (test):** `test_is_dev_environment_detection` clears the cache between its four
  `TITAN_ENV` toggles (matching the `test_garmin_sync.py` idiom).
- **P1c (production robustness):** `_resolve_sync_timeout_seconds()` catches the `ValueError`
  (pydantic `ValidationError` ⊂ `ValueError`) from a non-numeric `GARMIN_SYNC_TIMEOUT_S` and
  falls back to `_DEFAULT_SYNC_TIMEOUT_S` (90), restoring pre-migration per-field resilience.
**Result:** G2 green; full `titan_ci.sh` exit 0 (§7).

### C2 — HIGH · Process gap: the §9C entrypoint's full G2 was never executed post-migration
**Evidence:** `CI_SURFACE_AUDIT_2026-06-06.md §7` explicitly defers G2 ("its health … was
established in CI_SURFACE_AUDIT_2026-06-05 §7 and is unchanged by these script-only patches");
06-05 §7 ran `--collect-only` + G1/G3/G4/G5/G6 only. The P15-ARCH5 cache (`#825`→`#827`) landed
between the Phase-24 green snapshot and these audits, so "3021 green" (CLAUDE.md) was a stale
assumption, not a measurement. **Root cause:** verifying a *subset* (collection + fast gates)
as a proxy for the *whole* §9C gate. Per Operating Contract §9C, commit authorization hinges on
"the captured exit code of an actually-executed `scripts/titan_ci.sh`" — i.e. the **full** run,
G2 included. **Recommendation:** treat any "green" claim as valid only when produced by a
complete `titan_ci.sh` run; never substitute `--collect-only` or a gate subset for G2.

### V1 — CRITICAL→RESOLVED · Code env equals the canonical bootstrap (verified)
The `#832` SessionStart hook + entrypoint interpreter-resolution + preflight are live and
effective; this session confirms `.venv` with the exact pins and `$PY`→`.venv/bin/python` with
no manual `source`. Closed. (Was 06-06 F1/F2/F3/F4.)

### V2 — MED · `titan_ci.sh` preflight under-covers the gate closure (PATCHED, P2)
The preflight imported `pytest, freezegun, sqlalchemy, fastapi` + `ruff`, but **G3–G6** pass
`--no-cov` (registered **only** by `pytest-cov`; absent ⇒ pytest exit 4 `unrecognized arguments:
--no-cov`, surfaced as a misleading "G3 FAIL") and **G2** imports `hypothesis` at collection
(`test_property_based.py`, `tests/test_governance_monotonicity.py`). A partial closure passed
preflight and failed cryptically mid-gate. **Fix:** probe
`import pytest, pytest_cov, freezegun, hypothesis, sqlalchemy, fastapi`. Additive; behaviour
unchanged on a complete closure.

### V3 — LOW · G2 `--ignore` rationale undocumented (PATCHED, P3, comment-only)
The three `--ignore`d files **pass** on Linux (9 passed in 0.63s) and are all
`@pytest.mark.integration` tests that shell out (`find` / `bash scripts/backup.sh` /
`python3 scripts/verify_backup.py`) — fragile on the documented Windows dev box. The ignore is a
deliberate cross-platform hedge (GitHub's ubuntu `test` job runs them); it just carried no
comment. **Fix:** documented the rationale and the entrypoint's §9C local-pre-commit scope.

### V4 — MED · §9C local entrypoint ⊊ remote `ci.yml` ("green-local ≠ green-remote")
`titan_ci.sh` = G1 + a curated `pytest` subset; `ci.yml` runs ~25 jobs (semgrep, pylint,
vulture, `lint-imports`, CVE/drift, the G-CI invariants, alembic, backup-verify, determinism,
complexity-budget, docs/claude-md/phase8 checks, phase4) **and a 3.11+3.12 matrix**. Per §9C,
`titan_ci.sh` is the *local pre-commit* gate (AGENTS.md governs its definition), deliberately
distinct from the remote full CI — so the subset is by design, but a green local run is **not**
sufficient for GitHub-green (the 3.12 leg in particular is unobservable locally). Remote `ci.yml`
remains the authoritative merge gate. (Carried 06-05 F7 / 06-06 F6.)

### V5 — MED · `AGENTS.md` dual bootstrap + dead `constraints.txt` (DEFERRED — governance-locked)
`AGENTS.md:489` still runs `pip install -r requirements.txt -c constraints.txt`;
`constraints.txt` is absent (verified) → that step errors on a clean clone. `AGENTS.md §2.0`
(line 205) names `scripts/setup_env.sh` as the bootstrap "mandatory before anything else" while
§9C/ADR-0059/the hook make `ci_bootstrap.sh` canonical (dual model). AGENTS.md is "DO NOT EDIT
without ADR" (CLAUDE.md). **Deferred — recommend an ADR addendum** to drop `-c constraints.txt`
and name `ci_bootstrap.sh` as the single bootstrap. (Carried 06-06 F5/R1.)

### V6 — LOW · `titan_check.sh` PASS/FAIL parsing is over-broad (DEFERRED)
Gates 2/3 `grep -qE '(FAILED|ERROR|error)'` over `pytest` output (discarding the captured exit
code via `|| true`); lowercase `error` matches benign strings (e.g. a failing nodeid in
`tests/test_ctl_atl_data_error.py`, warning summaries). `titan_ci.sh` does this correctly (exit
codes via `run_gate`). **Recommendation:** capture `rc=$?` before `|| true` and drive PASS/FAIL
from `rc`. Deferred — pre-commit gate-of-record. (Carried 06-06 F10/R3.)

### V7 / V8 — LOW/INFO · Bootstrap hardening
V7: `ci_bootstrap.sh` installs pinned-but-unhashed deps (no `--require-hashes`); the CVE
(`pip-audit`) and unpinned-dep gates exist only in remote `ci.yml`. V8: `ci_bootstrap.sh` reuses
an existing `.venv` without re-validating its interpreter against the 3.11+ guard → a stale-
Python venv could persist across re-provisioning. Both acceptable for a dev/pre-commit lane.

**POSIX portability.** All closure scripts are `#!/usr/bin/env bash` and use arrays, `[[ … ]]`,
`BASH_SOURCE` — bash-required (consistent with the shebang and `ci.yml` `shell: bash`); only
hazard is `sh scripts/titan_ci.sh`. `"${FAILED_GATES[@]}"` empty-array expansion under `set -u`
is safe (FAIL branch only).

**Security.** The entrypoint closure is free of `eval`, injection, and `curl|bash`. P1c widens
an `except` to `ValueError` but is tightly scoped to the timeout-resolver fallback path. Wider
surface: `secret-scan.yml` installs gitleaks via `curl … | tar` with no checksum (remote, out
of closure).

---

## 5. Patches

### Applied here (validated; full `titan_ci.sh` exit 0)
| ID | File | Change |
|----|------|--------|
| P1a | `conftest.py` | Autouse `get_settings.cache_clear()` (before+after each test) — fixes the C1 cross-test cache leak suite-wide. |
| P1b | `tests/test_td01_td03_td05.py` | `test_is_dev_environment_detection` clears the cache between `TITAN_ENV` toggles. |
| P1c | `titan/integrations/garmin_sync.py` | `_resolve_sync_timeout_seconds()` falls back to the default on a non-numeric `GARMIN_SYNC_TIMEOUT_S` (pre-migration resilience). |
| P2 | `scripts/titan_ci.sh` | Preflight probes the real gate closure (`pytest_cov`, `hypothesis`) → actionable remediation, not a cryptic mid-gate failure (V2). |
| P3 | `scripts/titan_ci.sh` | Document the G2 `--ignore` rationale + the §9C local-pre-commit scope (V3). |

*(P1a–P1c committed under `P15-ARCH5: fix settings cache isolation and GARMIN_SYNC_TIMEOUT_S
robustness`; P2/P3 + this report under the CI-surface commit.)*

### Required but deferred (governance-gated / gate-of-record)
| ID | Target | Action | Why deferred |
|----|--------|--------|--------------|
| R1 | `AGENTS.md:489` + §2.0 | Drop `-c constraints.txt`; name `ci_bootstrap.sh` as the single bootstrap | AGENTS.md is "DO NOT EDIT without ADR" (V5) |
| R2 | `scripts/titan_check.sh` | Drive PASS/FAIL from the captured exit code, not `grep error` | Pre-commit gate-of-record (V6) |
| R3 | `ci_bootstrap.sh` / settings | `--require-hashes` + local `pip-audit`; `.venv` interpreter re-validation; consider a settings-level `field_validator` so one malformed env var can't fail all of `get_settings()` | Hermeticity / P15-ARCH5 design (V7/V8/C1-systemic) |

---

## 6. Reproducibility Risk Register

| Risk | Driver | Mitigation / Status |
|------|--------|---------------------|
| **§9C gate RED under in-progress migration** | C1: `lru_cache(get_settings)` w/o isolation + strict int field | ✅ Fixed P1a/P1b/P1c; G2 green |
| **"Green" assumed from a subset, not measured** | C2: full G2 never run post-`#827` | ✅ Surfaced; run full `titan_ci.sh` for any green claim |
| Code env can't run any gate | bare image, no canonical bootstrap | ✅ Closed — hook == bootstrap |
| Cryptic gate failure on partial closure | V2: preflight under-covers `pytest_cov`/`hypothesis` | ✅ Mitigated — P2 |
| "Green local ≠ green remote" | V4: gate subset; 3.12 matrix; `--strict-markers` | ⚠ By design — remote `ci.yml` is authoritative |
| One malformed env var breaks all settings | C1 systemic: `TitanSettings()` raises on any bad field | ⚠ P1c fixes the timeout path; R3 (settings-level) for the rest |
| Broken bootstrap instruction on clean clone | V5: dead `constraints.txt` in AGENTS.md | ⚠ R1 (ADR-gated) |

---

## 7. Validation Evidence

**Cold-start hook (this session, exit 0):** `ci_bootstrap.sh` → `Python 3.11.15 — OK`, `.venv`
built/reused, closure installed; `.venv/bin/python -m ruff --version`→`0.15.13`,
`-m pytest --version`→`9.0.3`; `import pytest, pytest_cov, freezegun, hypothesis, sqlalchemy,
fastapi`→OK.

**C1 bisection:** kill-switch test alone → **1 passed**; whole file → **1 failed** (sibling
populates the cache); manual fresh-cache `env=0` → `enabled: False` (logic correct).

**Pre-fix full gate:** `G2 45 failed, 2968 passed, 6 skipped` → `❌ TITAN CI: 1 FAILURE(S)`.

**Post-fix targeted (previously-failing areas):**
`pytest tests/titan/api tests/titan/integrations tests/titan/science tests/test_td01_td03_td05.py`
→ **482 passed** (was 480 passed / 2 failed). `ruff check` on changed files → clean.

**Post-fix full §9C gate:** `bash scripts/titan_ci.sh` → **G1–G6 all PASS; exit 0** (see PR/CI).

**Conclusion:** environment parity was already in place (`#832`); the residual blocker was a
*code* regression from the in-progress P15-ARCH5 migration that only a complete `titan_ci.sh`
run exposed. With P1a–P1c the §9C gate is green; P2/P3 harden the entrypoint; V4–V8 remain
correctly governance-deferred to an ADR.
