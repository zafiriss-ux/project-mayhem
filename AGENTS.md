# AGENTS.md — TITAN OS Engineering Contract

> This file governs every AI agent and human engineer working on this codebase.
> Rules are non-negotiable. Deviations are bugs in the engineering process, not acceptable trade-offs.

---

## ⚠️ ABSOLUTE RULE — TESTS (Read First, Apply Always)

> **For every task, without exception:**
> - If a test file for the changed module does **not** exist → **create** a mirrored test file:
>   - Source: `titan/<path>/<module>.py` → Test: `tests/titan/<path>/test_<module>.py`
>   - If the project's test layout differs, follow the nearest existing test convention in `tests/`.
> - If a test file **exists** → **update** it to cover the new or changed behaviour
>
> There are no exceptions to this rule.
> A task that ships without tests for its changed behaviour is **incomplete by definition**.

**Minimum test coverage per changed public function:**
1. One happy-path test (normal input, expected output)
2. One boundary or error-path test (edge input, exception, or guard condition)

**After adding or updating tests:**
- Run `python -m pytest -q -W error::pytest.PytestWarning` (strict gate — warnings are failures)
- Run `python -m pytest -q` (canonical gate — must be 100% green, count same or higher)
- If any test fails: stop, follow Section 6, fix root cause first

**Never delete tests.** If a test is wrong, fix the test — never remove it.

---

## 🚫 HARD GATE — NO COMMIT / NO PR BEFORE GREEN

**This gate is absolute. No exceptions. No partial credit.**

A commit, push, or `make_pr` call is **forbidden** unless ALL of the following have passed in the current session:

| Gate | Command | Required result |
|------|---------|-----------------|
| Lint | `ruff check .` | Exit code 0, zero findings |
| Strict test | `python -m pytest -q -W error::pytest.PytestWarning` | 100% green, zero warnings treated as errors |
| Full test | `python -m pytest -q` | 100% green, count same or higher than before |

**If any gate fails:**
1. **STOP immediately.** Do not create a commit. Do not push. Do not call `make_pr`.
2. Invoke Section 7 (Stop-the-Line Protocol).
3. Fix only the root cause of the first failing gate.
4. Re-run **all three gates from scratch**.
5. Only after all three pass: proceed to commit/push/PR.

**Forbidden validation shortcuts (these are bugs, not solutions):**
- Using `PYTEST_ADDOPTS=...` or any env override to suppress failures
- Using `--import-mode=importlib` or other flags to bypass collection errors
- Silencing warnings with `filterwarnings` in test code or config
- Using `pytest.mark.skip` / `xfail` without documented justification in the PR description
- Running a subset of tests and reporting "all pass"

If an override is required for the suite to run at all, that is a **repo-level issue**. Either fix it within the current task's scope, or STOP and report it as an out-of-scope finding in `TECHNICAL_DEBT.md` before continuing.

---

## 1. Role Boundaries

| Role | Responsibility |
|------|---------------|
| **Architect (Claude / owner)** | System design, ADR authorship, tier ordering, scope approval |
| **Implementation Engineer (Codex / agent)** | Execution of scoped tasks only — no design decisions |

Agents must not redesign, restructure, or re-architect any system component unless explicitly instructed by the architect. When you believe a redesign is needed, write it up as an "Out of Scope Finding". Do NOT implement it as part of this task.

---

## 2. Deliverable Workflow — Canonical Sequence

Every task follows this sequence exactly. No step may be skipped.

```
1. Read task description completely (Section 3.5 scope declaration before any code)
2. Write code / tests
3. Run Gate 1: ruff check .
4. Run Gate 2: python -m pytest -q -W error::pytest.PytestWarning
5. Run Gate 3: python -m pytest -q
6. ✅ All three gates GREEN → proceed to step 7
   ❌ Any gate fails → STOP (Section 7), fix root cause, restart from step 3
7. Create commit (message format: T<tier>-<id>: <short title>)
8. Push (if push-enabled environment)
9. Open PR (if push-enabled environment)
```

**Steps 7–9 are only reachable after step 6 is confirmed GREEN.**

### 2.2 Deliverable format (push-enabled environments)

Run all three Mandatory Gates (Section HARD GATE) before doing anything below.
Do NOT create a commit unless all three gates pass.
Do NOT call `make_pr` unless all three gates pass.

You MAY create commits and push, but ONLY to branches matching `claude/*`.

You MUST NOT push to `main` or `master` — this is a hard rule, not a guideline.

You MUST NOT force push or rewrite history on any remote branch.

If push is available in the runtime environment:
- Push the branch.
- Open exactly one PR (base=main, compare=claude/<branch>).
- Paste the PR link in your response.

If push is NOT available in the runtime environment:
- Stop after the commit is created.
- Report the branch name and commit hash.
- The repository owner will perform the push and open the PR.

Commit message format: `T<tier>-<id>: <short title>` — example: `T2-08: Add startup observability`

### 2.2b Deliverable format (non-push environments — fallback only)

Run all three Mandatory Gates before delivering.

Provide a single unified patch: `git diff` or `git diff --staged`.

Do NOT create commits. Do NOT push. Do NOT open PRs.

Label response clearly: `[DIFF ONLY — push not available]`

### 2.3 Git workflow (push-enabled environments)
- Never push directly to `main` or `master`
- All work branches must use prefix `claude/`
- Create branch if missing: `git checkout -b claude/<task-id-short>`
- Push with: `git push -u origin claude/<branch-name>`
- One issue = one PR. Do not bundle unrelated fixes.
- Every PR description MUST include a Scope Declaration (see Section 3.3)

---

## 3. Scope Control

### 3.1 Allowed
- Modify only the files directly named in the task
- Update additional files **only** when strictly required for correct integration (imports, interfaces, tests, wiring, configuration)

### 3.2 Not allowed
- Refactoring unrelated code
- Style or formatting changes outside the task
- Architectural redesign
- Adding comments, docstrings, or type annotations to code you did not explicitly change
- Allowed only within the exact function/section you modified, when needed to reflect changed behaviour.

### 3.3 Scope Declaration (mandatory in every PR description)

Every PR MUST include this block — no exceptions:

```
## Scope
**Task:** T<tier>-<id> — <title>
**Files changed:** <list>
**Files NOT changed:** governance_engine.py, [any other locked files]
**Tests added/modified:** <list or "none — existing coverage sufficient">
**ADR reference:** ADR-XXXX (required if governance_engine.py was touched)
**Gates passed:** ruff ✅ | pytest strict ✅ | pytest full ✅
```

A PR without a Scope Declaration and confirmed gate status will not be reviewed.

### 3.5 Before writing a single line of code
1. List every file that must change.
2. For each file, write one sentence explaining **why** it must change.
3. If a file appears necessary but isn't named in the task, explain the dependency before touching it.

### 3.4 Out of Scope Findings
If you discover another issue while working: **do not fix it.** Add it to `TECHNICAL_DEBT.md` under the appropriate tier. Do NOT fix it as part of this task. Continue only with the original scoped task.

**Principle: Minimal change, maximum stability.**

---

## 4. Tier Ordering — Mandatory

Technical debt work follows strict tier ordering from `TECHNICAL_DEBT.md`:

```
TIER 1 (Data Integrity) → TIER 2 (Observability) → TIER 3 (Deps) → TIER 4 (Maintainability) → TIER 5 (Future)
```

**Do NOT start Tier N+1 work while any Tier N item is OPEN.**

If you receive a task from a higher tier while a lower tier is open, respond:
> `⛔ TIER ORDERING VIOLATION: T[N]-[XX] is still OPEN. I must complete that first.`

Exception: items explicitly marked `independent` in `TECHNICAL_DEBT.md`.

### 4.1 T4-01 Ruff burn-down — fixed subsystem sequence

```
1. titan/config/
2. titan/science/governance_*.py
3. titan/core/
4. titan/integrations/
5. titan/orchestration/ + titan/features/
6. titan/ui/
```

Do not skip ahead. Do not quick-fix across subsystems simultaneously.

Acceptance gate per subsystem (binary — PASS or FAIL):
```bash
ruff check <subsystem_path>   # must return exit code 0, zero findings
python -m pytest -q           # must be 100% green, same count or higher
```

If either check is not 100%, the answer is exactly:
> `NOT 100% — Missing: [list the specific failing check]`

---

## 5. Definition of Done — Binary

A task is either:
- ✅ **DONE** — all acceptance criteria pass, 100%, no caveats
- ❌ **NOT DONE** — at least one criterion fails

There is no "mostly done", "should be fine", or "looks good". **Binary only.**

---

## 6. Test Failure Protocol

### 6.1 Before delivering any change
1. Run `python -m pytest -q -W error::pytest.PytestWarning` (strict — warnings are failures)
2. Run `python -m pytest -q` (canonical — zero failures, zero new errors)

**Note on coverage:**
- The repo enforces a global coverage threshold.
- Running a single test or small subset may FAIL solely due to coverage (even if all tests passed).
- Treat "coverage threshold not reached" on a subset run as a diagnostic artifact, NOT a code regression.
- Acceptance gates always require the canonical full suite (Gate 3).

3. Confirm test count is same or higher than before your change
   - Exception: if tests were renamed/moved but coverage is preserved, document it in the PR description.
4. If any test fails: follow the protocol below before doing anything else

### 6.2 🔴 RED — Assertion / runtime error

Respond **verbatim** before doing anything:

```
A test is failing.
1) Run the suite and identify the FIRST failing test (deterministically):
   python -m pytest -x
2) Do NOT modify the test unless it is objectively incorrect.
3) Determine whether the failure is:
   A) Code regression
   B) Test bug
   C) Environment/dependency issue
4) Fix ONLY the minimal root cause.
5) Re-run the full suite.
6) If any other tests fail, stop and report.
7) Do not refactor unrelated code.
8) Do not introduce new behaviour.
```

### 6.3 🟡 YELLOW — Warnings / flaky / lint-related

Respond **verbatim** before doing anything:

```
The test suite has warnings or unstable behaviour.
1) Identify the exact warning source.
2) If it is deprecation-related, fix the call site.
3) If it is environment-specific, stabilise it.
4) Do NOT silence warnings globally.
5) Keep changes minimal and scoped.
6) Re-run full suite and confirm clean output.
```

Note: Under the strict gate (`-W error::pytest.PytestWarning`), warnings are failures. Fix the warning source — do not suppress it.

### 6.4 🟣 PURPLE — Dependency / import error (collection failure)

Respond **verbatim** before doing anything:

```
A test fails during collection (import error).
1) Confirm full dependency installation:
   pip install -r requirements.txt -c constraints.txt
2) Verify the missing module: python -c "import <module>"
3) Fix dependency resolution only. Do not write code or edit test files.
4) Do not modify application logic.
5) Re-run full suite.
```

### 6.6 🟠 ORANGE — Hang / slow test (no failure, progress unclear)

**Symptoms:**
- pytest shows no new output for an extended period
- user reports "it's stuck" but no failing test exists

Respond **verbatim** before doing anything:

```
The suite appears slow or hung (no failing test yet).
1) Do NOT assume failure. Do NOT start fixing code.
2) Identify the exact running / last completed test:
   python -m pytest -vv
3) Identify the slowest tests:
   python -m pytest --durations=20
4) If a specific test is suspected, run only that test with output:
   python -m pytest -vv -s <file>::<test_name>
5) Only if the same test deterministically hangs: fix the minimal root cause,
   then re-run the full suite.
```

**Important:**
- A perceived hang is NOT RED/YELLOW/PURPLE until a failing nodeid or import error is proven.
- Do not loop. Every re-run must add new information (nodeid or durations output).

### 6.5 Category → action (exhaustive)

| Category | Action |
|---|---|
| Code regression | Fix the code |
| Test bug | Fix the test |
| Env / deps | Fix the environment |

Nothing else. **Fix root cause. Not symptom. Not workaround. Not silence.**

**Banned responses when tests fail:**
- Random refactor of surrounding code
- Mass changes across files
- `pytest.mark.skip` / `xfail` without documented justification
- Silencing warnings globally
- Using env overrides (`PYTEST_ADDOPTS`, `--import-mode`, etc.) to bypass failures

---

## 7. Stop-the-Line Protocol

If any acceptance criterion fails mid-task:
1. **Stop immediately.** Do not continue to other files or subsystems.
2. Report what failed and the root cause.
3. Fix only the specific failing criterion.
4. Re-run the acceptance gate from scratch.
5. Only then continue.

**Anti-loop rule:**
- Do NOT repeat the same command/run without returning new evidence.
- Every stop-the-line report MUST include:
  - the exact failing test nodeid + traceback (RED), OR
  - the exact warning text + origin (YELLOW), OR
  - the missing module/import error line (PURPLE), OR
  - the last printed test nodeid + durations output (ORANGE).
- A response that says "tests failing" / "stuck" without the above evidence is NOT ACCEPTABLE.

---

## 8. Architecture Constraints (Do Not Break)

| Pattern | Location | Why it must not change |
|---|---|---|
| Governance gate ordering | `governance_engine.py` → Step 9 of `DailyCoach` | Non-bypassable safety; altering order corrupts coaching decisions |
| CTL/ATL chronological rebuild | `garmin_sync.py` + `database.py` | Oldest-first EMA; reversing gives wrong fitness values |
| SQLite WAL + busy_timeout + write lock | `database.py` | Thread-safety across 3 daemon threads |
| Idempotent versioned migrations | `database.py _run_migrations()` + `PRAGMA user_version` | Version-gated; each `_apply_vN_migrations()` runs exactly once; breaking idempotency causes schema corruption |
| Thresholds from `thresholds.py` only | All science modules | Single source of truth; hardcoding duplicates diverge silently on recalibration — enforced by T4-19 |
| ML kill-switch default-ON | All Phase 7 engines | Correct failure mode; never remove or invert |
| Evidence labels on ML payloads | Phase 7 engines | Provenance discipline; do not remove |
| `PersistenceFailure` propagation | `daily_coach.py _persist_garmin_data()` | DB rollback must surface as degraded mode; silent fail-open corrupts governance inputs (ADR-0020) |
| Notifications via `NotificationGateway` | All notification paths | Telegram must have file fallback; direct bot calls bypass the fallback chain (T3-09) |
| `DegradedModeTracker` registration | `daily_coach.py run_morning_routine()` | New degraded-mode conditions must be registered to fire the 24h SLO alert (T2-13) |

**`titan/science/governance_engine.py` is architecture-locked.** See ADR-0009 and ADR-0021.
Do not modify it without an ADR reference in your commit message and explicit architect approval.

The lock is **machine-enforced**: `tests/test_governance_mutation.py` (T4-18) verifies boundary-ON
and boundary-OFF for every gate; `tests/test_architectural_invariants.py` (T4-19) verifies that
no inline threshold literals are added and that all lock codes remain canonical. Both test files
will fail immediately if gate logic is silently altered. Adding a new gate requires:
1. An ADR (reference in commit message)
2. Boundary tests in `test_governance_mutation.py`
3. Lock code added to `_CANONICAL_LOCK_CODES` in `test_architectural_invariants.py` and the table in CLAUDE.md

---

## 9. Key Files Quick Reference

| File | Purpose |
|---|---|
| `CLAUDE.md` | Full project overview, architecture, all engineering rules |
| `TECHNICAL_DEBT.md` | Tiered debt register — consult before every task |
| `titan/config/thresholds.py` | Single source of truth for all safety constants |
| `titan/config/evidence_registry.py` | Parameter provenance (STRONG / MODERATE / HEURISTIC) |
| `titan/science/governance_engine.py` | 7-gate safety system — **architecture-locked** |
| `titan/orchestration/daily_coach.py` | 12-step morning routine — orchestration entry point |
| `titan/ui/operator_console.py` | OperatorConsoleService (dashboard, session explorer, override) |
| `titan/science/ml_safety.py` | ML kill-switch (`TITAN_ML_KILL_SWITCH` env) |
| `titan/integrations/notification_gateway.py` | `NotificationGateway` — ordered fallback chain (Telegram → File) |
| `titan/orchestration/daily_coach.py` | 12-step morning routine — `DegradedModeTracker`, `PersistenceFailure` sentinel |
| `tests/test_governance_mutation.py` | Boundary-ON/OFF tests per governance gate (T4-18 / ADR-0021) |
| `tests/test_architectural_invariants.py` | AST-enforced structural constraints (T4-19) |
| `.github/pull_request_template.md` | PR checklist with 3-gate status + architecture guard items (T4-20) |
| `docs/adr/` | Architecture Decision Records (0001–0021) |
| `docs/ROADMAP.MD` | Phase history (Phases 0–7 CLOSED; Phase 7.8 Hardening CLOSED 2026-03-06) |
| `pyproject.toml` | pytest + ruff + mypy config |

---

## 10. Common Mistakes — Do Not Repeat

| Mistake | Consequence |
|---|---|
| Shipping a change without creating or updating tests | Silent regression guarantee |
| Creating a commit or PR before gates are green | Broken baseline delivered; next engineer inherits the failure |
| Fixing multiple subsystems in one pass | Partial work delivered as "done"; debt reaccumulates |
| Skipping `ruff check` / `pytest` binary gate | Incomplete fix shipped |
| Using env overrides to bypass test failures | Root cause hidden; regression guaranteed to recur |
| Broad `except Exception: pass` left in place | Silent data loss in governance inputs — flagged by T4-19 invariant test |
| Hardcoding thresholds instead of importing from `thresholds.py` | Values diverge on recalibration — flagged by T4-19 invariant test |
| Modifying `governance_engine.py` without ADR | Silent safety regression (ADR-0009 / ADR-0021) |
| Adding a gate without boundary tests in `test_governance_mutation.py` | Boundary regressions undetectable (T4-18 / ADR-0021) |
| Adding a lock code not in `_CANONICAL_LOCK_CODES` | Invariant test T4-19 will fail; add the code to both test and CLAUDE.md |
| Sending Telegram notifications via direct bot call (bypassing `NotificationGateway`) | No fallback path; message lost on Telegram failure (T3-09) |
| Failing to raise `PersistenceFailure` on DB rollback | Degraded mode never set; governance uses stale data (ADR-0020, T1-15) |
| "Improving" adjacent code while fixing a bug | Scope creep, unexpected regressions (Rule E4) |
| Delivering "mostly done" work | Debt reaccumulates; next engineer inherits broken baseline (Rule E5) |
| Starting Tier 2+ work before Tier 1 is closed | Data integrity issues persist in production (Rule E1) |
| Using `print()` instead of structured log events | Incidents cannot be diagnosed (T2-01 through T2-07) |

---

## 11. Pre-Delivery Checklist — Run Before Every Delivery

```
[ ] I read the task description completely before writing any code.
[ ] I listed every file I need to change and why (Section 3.5).
[ ] I confirmed no Tier N-1 items are OPEN before starting Tier N work.
[ ] I made only the changes required by the task (no scope creep).
[ ] ruff check .                                        → zero findings
[ ] python -m pytest -q -W error::pytest.PytestWarning  → 100% green, zero warnings-as-errors  ← GATE 2
[ ] python -m pytest -q                                 → 100% green, count same or higher      ← GATE 3
[ ] I created or updated tests for every changed public function.    ← MANDATORY, NO EXCEPTIONS
[ ] I did NOT use PYTEST_ADDOPTS or any override flag to force green.
[ ] I did NOT modify governance_engine.py without an ADR reference.
[ ] I did NOT hardcode any threshold (used thresholds.py).
[ ] If I changed a governance gate: boundary tests added to test_governance_mutation.py.
[ ] If I added a governance lock code: added to _CANONICAL_LOCK_CODES + CLAUDE.md table.
[ ] If I added a notification path: routed through NotificationGateway, not direct bot call.
[ ] Out-of-scope findings are in TECHNICAL_DEBT.md, not in code.
[ ] I pushed to a claude/* branch only — NOT to main or master.
[ ] I opened exactly one PR using .github/pull_request_template.md and pasted the PR link.
[ ] My PR description contains a Scope Declaration with gate status (Section 3.3).
```

**All 18 boxes must be checked. A PR with any unchecked box is NOT DONE.**

---

*Last updated: 2026-03-06 (Phase 7.8 — T4-18/T4-19/T4-20 enforcement, NotificationGateway, DegradedModeTracker, PersistenceFailure, schema versioning). Authoritative for all agents and engineers operating on TITAN OS.*
