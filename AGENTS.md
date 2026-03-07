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
| **Implementation Engineer (Codex / agent)** | Execution of scoped tasks only — no design decisions, no ADR authorship |

Agents execute. They do not design.

An agent **must not**:
- Author or amend an ADR (Architecture Decision Record)
- Redesign, restructure, or re-architect any system component
- Add new abstraction layers or introduce new module boundaries
- Change tier ordering or phase sequencing
- Make database schema topology decisions beyond what the task explicitly specifies
- Alter governance gate logic without an ADR reference and architect approval

When you believe a redesign or architectural decision is needed: write it up as an **Out of Scope Finding** in `TECHNICAL_DEBT.md`. Do NOT implement it. Do NOT draft an ADR. See §13 for the full protocol.

---

## 2. Deliverable Workflow — Canonical Sequence

### 2.0 Environment Setup — Mandatory (Run First, Every Session)

Before any other action — before reading code, running tests, running lint, or making any change — run:

```bash
scripts/setup_env.sh
```

This step is **unconditionally mandatory**. It must execute successfully before proceeding.

**If the setup script fails:**
1. **Stop immediately.** Do not attempt any task steps.
2. Report the failure verbatim (exit code + last output lines).
3. Do not attempt ad-hoc dependency installation unless explicitly instructed by the architect.

**Environment repair** is permitted only when both conditions hold:
1. `scripts/setup_env.sh` completed successfully, AND
2. a required dependency is still missing in the runtime environment.

If repair is permitted:
- Fix the environment only (dependency resolution, version pinning).
- Do not modify application code or tests.
- Re-run all three Mandatory Gates after repair before continuing.

### SESSION_START (mandatory — before any code change)

Run all five checks below and record outputs in your first response:

```bash
S1. Read CLAUDE.md completely (not summary).
S2. grep -c "OPEN\|PARTIALLY RESOLVED" TECHNICAL_DEBT.md
S3. python -m pytest -q --no-header 2>&1 | tail -1
S4. ruff check . --statistics 2>&1 | tail -5
S5. State explicitly: "Current open Tier N items: [list]"
```

Do not begin implementation until you have confirmed:
- Open debt items (S2)
- Baseline test count (S3)
- Lint status (S4)
- Active tier and open items (S5)

Failure to run these checks before implementation is a PROCESS VIOLATION.

---

Every task follows this sequence exactly. No step may be skipped.

```
0.  Run scripts/setup_env.sh (Section 2.0) — mandatory before anything else
0.5 Run scripts/check_scratchpad.sh — exit 1 = BLOCKING queue non-empty; stop and await architect
1.  Read task description completely (Section 3.5 scope declaration before any code)
2.  Write code / tests
3.  Run Gate 1: ruff check .
4.  Run Gate 2: python -m pytest -q -W error::pytest.PytestWarning
5.  Run Gate 3: python -m pytest -q
6.  ✅ All three gates GREEN → proceed to step 7
    ❌ Any gate fails → STOP (Section 7), fix root cause, restart from step 3
7.  Create commit (message format: T<tier>-<id>: <short title>)
8.  Push (if push-enabled environment)
9.  Open PR (if push-enabled environment)
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

### 2.4 Optional fast iteration rule (targeted tests during implementation)

During implementation, the agent **may** run targeted tests for the changed module(s) to speed up local iteration:

```bash
python -m pytest tests/path/to/test_changed_module.py -q
```

**This does NOT replace the mandatory final validation gates.**

Before any commit, push, or PR, the agent **must** still run all three gates in order:
```bash
ruff check .
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

Targeted runs during implementation are diagnostic only. Reporting "targeted tests pass" as the deliverable is a violation of §HARD GATE.

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

### 3.6 Documentation Edit Policy — Hard Restriction

Documentation files are **architect-owned**. Agents may not edit them freely.

**Covered files:** `CLAUDE.md`, `AGENTS.md`, `README.md`, any file under `docs/`

**The only permitted documentation edits are:**

| Permitted update | Trigger | Section |
|---|---|---|
| Test count snapshot in `CLAUDE.md` | Tests added/removed in current task | §12.3 |
| ADR index table row in `CLAUDE.md` | Integrating a new architect-authored ADR | §12.4 |
| Debt entry body in `TECHNICAL_DEBT.md` | Task closure (mark RESOLVED) | §12.1 |
| New debt entry in `TECHNICAL_DEBT.md` | Out-of-scope finding discovered | §12.2 |
| Tracking table row in `TECHNICAL_DEBT.md` | Either of the two rows above | §12.1 / §12.2 |

**Everything else is prohibited:**
- Do not reword, restructure, or "improve" existing documentation.
- Do not add sections, paragraphs, or notes beyond what the task explicitly requires.
- Do not update `CLAUDE.md` for minor wording corrections or to reflect your interpretation of the system.
- Do not edit `AGENTS.md` at all — it is maintained exclusively by the architect.

If you believe a documentation update is needed beyond the table above, add it as an out-of-scope finding in `TECHNICAL_DEBT.md` and stop.

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
| Editing `CLAUDE.md`, `AGENTS.md`, `README.md`, or `docs/` outside §3.6 permitted list | Unauthorized scope creep; documents diverge from architect's intent |
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
[ ] I marked the completed debt item ✅ RESOLVED with date + commit hash in its entry body (§12).
[ ] I updated the tracking table at the bottom of TECHNICAL_DEBT.md (§12).
[ ] If test count changed: I updated the historical snapshot in CLAUDE.md (§12).
[ ] If a new ADR was written: I updated the ADR index table in CLAUDE.md (§12).
[ ] I did NOT make any architectural decision without explicit architect approval (§13).
[ ] I did NOT edit CLAUDE.md, AGENTS.md, README.md, or docs/ beyond what §3.6 and §12 explicitly permit.
[ ] I ran scripts/check_scratchpad.sh at Step 0.5 and it returned exit 0.
[ ] If any trigger condition (T-SCRATCHPAD-1 through T-SCRATCHPAD-5) was met during this task, I wrote an OBS entry in the correct queue (BLOCKING or NON-BLOCKING) and set STATUS: REVIEW_REQUESTED.
[ ] I did NOT write proposed solutions in OBS entries — only engineering observations (facts, file:line refs, architectural question).
```

**All 27 boxes must be checked. A PR with any unchecked box is NOT DONE.**

---

## 12. Debt Register Discipline — Mandatory on Every Task Close

The debt register (`TECHNICAL_DEBT.md`) and the project overview (`CLAUDE.md`) are
**living documents**. Every agent is responsible for keeping them current as a condition
of task completion. Stale register entries are as harmful as stale code.

### 12.1 On task closure (always)

When a task reaches ✅ DONE (all three gates green, commit created):

1. **Mark the debt entry** in `TECHNICAL_DEBT.md`:
   - Change the heading status from `🔴 OPEN` to `✅ RESOLVED <YYYY-MM-DD>`
   - Change the `**Status:**` line to: `✅ RESOLVED <YYYY-MM-DD>. Commit: <short-hash>.`
   - Rename `**Problem:**` to `**Original state (pre-fix):**` and convert present-tense verbs to past tense.
   - Add a `**Resolution:**` block summarising what was changed (modules, approach, test count at closure).

2. **Update the tracking table** at the bottom of `TECHNICAL_DEBT.md`:
   - Change the row for this item from `OPEN` to `✅ RESOLVED` and fill in the date column.

Both updates are **required**. Updating one without the other is incomplete.

### 12.2 On out-of-scope finding (always)

When you discover an issue outside the current task scope:

1. Add a new entry to `TECHNICAL_DEBT.md` under the correct tier (follow existing entry format).
2. Add a row to the tracking table at the bottom.
3. Do NOT fix it in the current task (§3.4 / Rule E4).

### 12.3 When test count changes

After any task that adds or removes tests:

- Update the **historical snapshot line** in `CLAUDE.md`:
  > `**Historical snapshot:** N tests all green as of Phase X.Y / T<tier>-<id> close (<date>).`
- Use the count from the final `python -m pytest -q` run of the current task.

### 12.4 When a new ADR is written

ADR authorship is an architect privilege (see §13). When the architect writes a new ADR and
the agent integrates it:

- Add the new ADR to the **Key Architectural Decisions table** in `CLAUDE.md` with a one-line
  description and status (e.g. `Accepted — <date>`).
- The table entry must match the format of existing rows exactly.

---

## 13. Architecture Decision Boundary — Hard Prohibition

Agents **execute tasks**. Architecture decisions belong to the architect.

### 13.1 Prohibited without explicit architect approval

The following actions are **unconditionally prohibited** unless the architect has written an
explicit instruction ("implement ADR-XXXX", "design a new module for X", "draft an ADR for Y"):

| Prohibited action | Why |
|---|---|
| Authoring or amending an ADR | ADRs are immutable design contracts; incorrect ADRs corrupt the architecture history |
| Adding new module boundaries or packages | Module topology is an architectural invariant |
| Introducing a new abstraction layer | Abstractions have long-term cost; the architect must evaluate before adding |
| Changing tier ordering or phase sequencing | Tier ordering enforces data-integrity-first discipline; agents cannot override it |
| Modifying governance gate logic without an ADR | Safety regression (ADR-0009, ADR-0021) |
| Changing DB schema topology (e.g. new tables, normalization) | Migrations are permanent; schema decisions require architectural sign-off |
| Deciding between design alternatives on the agent's own judgement | Guessing on trade-offs leads to silent technical debt |

### 13.2 What to do when an architectural decision is required

If you hit a point where completing the task **requires** an architectural decision not
covered by the task description or an existing ADR:

1. **STOP immediately.** Do not write code past this point.
2. **Report the decision point** precisely:
   - What exact choice needs to be made
   - What options you see (list them — do not pick one)
   - Why each option has different architectural implications
3. **Wait for explicit architect approval** before continuing.
4. Do NOT infer, approximate, or "make a reasonable call" on architectural questions.

> The correct response to an architectural ambiguity is always **stop and ask**, never **proceed and explain later**.

### 13.3 What is NOT an architectural decision (agents may proceed)

| Permitted without approval |
|---|
| Adding a column to an existing table via the versioned migration pattern |
| Adding a new method to an existing class (within the class's existing responsibility) |
| Adding tests for existing or new behaviour |
| Adding constants to `thresholds.py` or `evidence_registry.py` |
| Adding structured log events following the existing pattern |
| Fixing a bug in existing logic without changing its contract |

When in doubt: stop and ask.

---

## 14. Project Safeguard Protocols — Protecting the Project from Well-Intentioned Mistakes

> These rules exist to protect the project from the most common source of architectural damage:
> good intentions executed at the wrong moment. They apply to agents and to the architect alike.

---

### 14.1 Agent Challenge Rule — Agents MUST challenge conflicting instructions

If a requested task appears to **contradict the current architecture, an existing ADR, or any
rule in this document**, the agent MUST stop and challenge the instruction before proceeding.

This is an **obligation**, not a permission. An agent that silently complies with an instruction
that violates architecture is failing its responsibility.

**Required response when a conflict is detected:**

```
⚠️ ARCHITECTURE CONFLICT DETECTED

Requested: [describe the instruction]
Conflicts with: [ADR-XXXX / AGENTS.md §X / Rule EX / thresholds.py / ...]
Specific conflict: [one sentence describing why they are incompatible]

Options:
  A) Proceed anyway — requires explicit architect override + ADR reference
  B) Modify the request to [describe a compliant alternative]
  C) Record as future work in TECHNICAL_DEBT.md and stop

How would you like to proceed?
```

The agent must **not** proceed without receiving an explicit answer. Silence is not consent.

**What counts as a conflict (agent must challenge):**
- A task that modifies `governance_engine.py` without an ADR reference
- A task that adds a new module boundary, abstraction layer, or package
- A task that starts Tier N+1 work while a Tier N item is OPEN
- A task that hardcodes a threshold instead of using `thresholds.py`
- A task that changes DB schema topology outside the versioned migration pattern
- A task that changes tier ordering or phase sequencing
- Any instruction that begins with "just quickly" or "let's just change" combined with an architectural element

**What is NOT a conflict (agent proceeds normally):**
- A task that fixes a bug within existing contracts
- A task that adds tests
- A task that adds constants to `thresholds.py` or `evidence_registry.py`
- A task explicitly referencing an ADR that authorises the change

---

### 14.2 Change Justification Requirement — Structured rationale before any architecture change

Any proposal to change the architecture — whether from the agent or the architect — must include
all three of the following before any code is written:

```
CHANGE JUSTIFICATION
Problem        : [What is broken or insufficient with the current design?]
Proposed change: [What specifically will change?]
Why necessary  : [Why is the current design insufficient to solve the problem?
                  What would happen if we did nothing?]
ADR reference  : [ADR-XXXX — or "new ADR required" if none exists]
```

**If the justification cannot be completed in full, the change must not proceed.**

This requirement applies to:
- Any new module, package, or abstraction layer
- Any change to governance gate logic
- Any DB schema topology change
- Any change to tier ordering or phase sequencing
- Any change that affects more than 3 files beyond direct task scope

It does NOT apply to:
- Bug fixes within existing contracts
- Adding tests
- Adding constants
- Executing a task that is already covered by an existing ADR

---

### 14.3 Cooling-Off Protocol — Major changes must wait one session

**Definition of "major architectural change":** any change that would require a new ADR,
introduces a new module boundary, changes DB schema topology, or affects governance gate logic.

**Protocol:**
1. In Session N: the change is **proposed, justified (§14.2), and documented** (ADR draft or
   `TECHNICAL_DEBT.md` entry with full justification). No code is written.
2. In Session N+1 or later: the change is reviewed and, if still sound, **approved and implemented**.

**Rationale:** 80% of architectural regressions originate from changes that seemed obviously
correct in the moment but were not re-evaluated after reflection. A one-session pause costs
nothing when the change is truly necessary, and catches nearly everything that is not.

**Bypass condition:** The cooling-off period may be waived only when:
- The architect explicitly states: "COOLING-OFF WAIVED — [reason]" in the session prompt, AND
- The reason describes an active production incident or data integrity failure.

Minor changes (bug fixes, test additions, constant additions) are always exempt.

---

### 14.4 No Impulse Implementation Rule — Record before coding

**No code may be written for an idea that is not already recorded as a task.**

Specifically:
- Every implementation must trace to a `TECHNICAL_DEBT.md` entry OR an explicit architect
  instruction in the current session prompt.
- If an idea arises mid-task ("while I'm here, I could also..."), it must be recorded in
  `TECHNICAL_DEBT.md` immediately and left there. The current task continues unchanged.
- An agent must never begin implementing something "obvious" that was not scoped in the task.

**The correct sequence:**
```
idea → TECHNICAL_DEBT.md entry → architect prioritises → task assigned → implementation
```

**Never:**
```
idea → immediate implementation
```

This rule catches what Rule E4 (no scope creep) does not: the impulse to implement a *new*
idea rather than expanding the scope of a current one.

---

### 14.5 Complexity Budget Rule — New abstractions require justification

Before introducing any new abstraction (helper class, utility function, mixin, protocol,
base class, decorator, or design pattern not currently present in the codebase):

The agent must answer:
1. **Is this abstraction used in three or more places right now?** If no → do not create it.
2. **Does the abstraction make a future engineer's job easier or harder?** If unclear → do not create it.
3. **Can the task be completed by adding to an existing module instead?** If yes → do that instead.

If all three questions pass: record the abstraction proposal as an out-of-scope finding in
`TECHNICAL_DEBT.md` and wait for architect approval. Do not implement inline.

This rule enforces ADR-0028 (Complexity Budget and Simplicity Gate) at the agent level.

---

## 15. Engineering Scratchpad Protocol — Codex Obligations

> **The scratchpad (`SCRATCHPAD.md`) is the structured communication channel from Codex to the
> architect (Claude). It is NOT a to-do list, NOT a design document, and NOT a place for
> solutions. It is a place for raw engineering findings that require an architectural decision.**

Codex writes **Observation (OBS)** entries to `SCRATCHPAD.md` when the trigger conditions
below are met. After writing, Codex sets the document status to `REVIEW_REQUESTED` and stops
until the architect clears it to `IDLE`.

### 15.1 Trigger Conditions (MANDATORY — not optional)

#### T-SCRATCHPAD-1: Subsystem Engineering Review (T4-01 burn-down)

**When:** After completing each subsystem in the T4-01 Ruff burn-down sequence.
**Subsystems:** `titan/config/` → `titan/science/governance_*.py` → `titan/core/` →
`titan/integrations/` → `titan/orchestration/ + titan/features/` → `titan/ui/`

Codex MUST write an OBS entry covering:
- How many violations were found and their categories (unused imports, bare-except, etc.)
- Any pattern that appeared in 3+ files (e.g., repeated `except Exception: pass`)
- Whether any violation suggests a deeper systemic issue (not just a lint problem)
- Files where the fix required more than a mechanical change

**Status change:** Set `STATUS: REVIEW_REQUESTED` after writing.
**Codex must stop:** Do not begin the next subsystem until architect clears to `IDLE`.

#### T-SCRATCHPAD-2: Tier Boundary Review

**When:** Before crossing from Tier N into Tier N+1 work.

Codex MUST write an OBS entry covering:
- Count of items closed in Tier N and their commit hashes
- Any Tier N items that revealed coupling to Tier N+1 concerns
- Whether any OPEN items in TECHNICAL_DEBT.md should be re-prioritised based on what Tier N revealed
- Any safety or data-integrity risk that emerged during Tier N execution that is not yet tracked

**Status change:** Set `STATUS: REVIEW_REQUESTED` after writing.
**Codex must stop:** Do not start any Tier N+1 task until architect reviews and clears.
This is in addition to Rule E1 (tier ordering). It does not replace it.

#### T-SCRATCHPAD-3: Pattern Concentration

**When:** Codex adds 3 or more out-of-scope findings (§3.4 / §12.2) to `TECHNICAL_DEBT.md`
within a single session, AND those findings share a common module, subsystem, or failure mode.

Codex MUST write an OBS entry synthesising the pattern:
- List the related findings (T<N>-<id> references)
- Describe the common failure mode or architectural weakness they share
- Estimate blast radius: how many modules are likely affected
- Ask the concrete architectural question the pattern raises

**Status change:** Set `STATUS: REVIEW_REQUESTED`.
**Codex may continue** with the current task (this is non-blocking for the current subtask).
Codex must NOT start a new top-level task until the architect clears it.

#### T-SCRATCHPAD-4: Phase Retrospective

**When:** When a Phase is declared CLOSED (e.g., "Phase 7.8 CLOSED") — either by the architect
or by Codex confirming the last item in a phase sequence is resolved.

Codex MUST write a retrospective OBS entry covering:
- Every Tier 1 item closed in the phase: what the root cause was (one sentence each)
- Every out-of-scope finding added during the phase (T-ref + one-line summary)
- Whether any finding was added but not yet triaged by the architect
- Any pattern in the Phase that suggests the next Phase's Tier 1 list is incomplete

**Status change:** Set `STATUS: REVIEW_REQUESTED`.
**Codex must stop:** Do not begin any item from the next Phase until architect clears.

#### T-SCRATCHPAD-5: Architectural Decision Point (parallel to §13.2)

**When:** Every time Codex invokes the §13.2 stop-and-report protocol (architectural decision
required during implementation).

Codex MUST simultaneously write an OBS entry with:
- The exact code location where the decision is needed (file:line)
- The two or more options Codex identified (factual, no preference expressed)
- The architectural implication of each option (contract change / schema change / gate change / none)
- Which existing ADR, if any, is closest to this decision point
- Whether proceeding without a decision would cause a data-integrity risk

**Status change:** Set `STATUS: REVIEW_REQUESTED`.
The §13.2 stop protocol and the OBS entry are both required. Neither replaces the other.

---

### 15.2 OBS Entry Rules

1. **One OBS per trigger event.** Do not bundle multiple unrelated findings into one OBS.
2. **Facts only.** No proposed solutions in OBS entries. No design sketches. No preferences.
3. **Specific code references.** Every OBS must include at least one `file:line` reference.
4. **Sequential IDs.** New OBS IDs always increment from the highest existing ID (including
   REVIEWED entries in the archive). Never reuse an ID.
5. **Follow the exact format** defined in `SCRATCHPAD.md`. Missing fields = incomplete OBS.
6. **Urgency classification is mandatory:**
   - `BLOCKING` — Codex cannot proceed without an architect decision
   - `NON-BLOCKING` — finding is recorded for architect awareness; current task can continue

### 15.3 What Codex MUST NOT Do

- Do NOT write proposed solutions or design alternatives in OBS entries.
- Do NOT write OBS entries for things already covered by an open TECHNICAL_DEBT.md entry.
- Do NOT set status back to `IDLE` — only the architect (Claude) changes status to `IDLE` or `CLEARED`.
- Do NOT interpret `CLEARED` as permission to skip future trigger conditions.
- Do NOT treat the scratchpad as a substitute for `TECHNICAL_DEBT.md`. The scratchpad feeds
  decisions; `TECHNICAL_DEBT.md` is the canonical task register.

### 15.4 Pre-Delivery Checklist

The three scratchpad items are incorporated directly into the §11 pre-delivery checklist
(items 25–27). They appear there and are enforced there. No separate action needed here.

---

## 16. Domain-Specific Engineering Contracts

These contracts were distilled from process-rule ADRs (0021, 0022, 0024, 0025, 0028, 0029,
0031, 0035, 0036, 0039, 0040) during the ADR triage of 2026-03-07. The original ADR files
have been removed from `docs/adr/`; this section is now the canonical location for these rules.

---

### 16.1 Governance Evolution Protocol (ex-ADR-0021)

Any PR that modifies `governance_engine.py` must include **all three** of the following:

1. An ADR reference justifying the change (existing or new ADR).
2. An `evidence_registry.py` diff — update the threshold's `_LAST_REVIEWED` date and `_RATIONALE`.
3. A `tests/test_governance_mutation.py` diff — boundary-ON and boundary-OFF tests for the changed gate.

All three are required. Providing only two is NOT DONE.

The comment at `governance_engine.py:1` must read:

```python
# Gate parameters: see thresholds.py + evidence_registry.py.
# To change gate logic: (1) write ADR entry, (2) update evidence_registry.py,
# (3) update tests/test_governance_mutation.py. All three are required.
```

This is the machine-enforced replacement for the original comment-lock.

---

### 16.2 Phase 8 Entry Gate (ex-ADR-0022)

**No Phase 8 code may be written until all criteria below are TRUE (binary — all required).**

| # | Gate Criterion | Verification |
|---|---|---|
| G1 | All `TECHNICAL_DEBT.md` Tier 1–4 items CLOSED | `grep -E "OPEN\|PARTIALLY" TECHNICAL_DEBT.md` → zero |
| G2 | `tests/test_architectural_invariants.py` 100% green (T4-19 complete) | `python -m pytest tests/test_architectural_invariants.py -v` |
| G3 | ADR-0018 Phase B accepted and scoped implementation plan documented | ADR-0018 status = "Phase B Accepted" |
| G4 | ADR-0017 composition root audit: all fan-in paths documented | ADR-0017 status = "Phase B Documented" |
| G5 | Schema version tracking active (`PRAGMA user_version`) bumped on every migration (T1-16) | `user_version > 0` |
| G6 | Hot backup strategy operational (T1-17) | `python -m pytest tests/ -k backup -v` → green |
| G7 | Full test suite green with count ≥ 1708 (Phase 7.9 baseline) | `python -m pytest -q` → 0 failures |
| G8 | `docs/adr/0022-review-phase8-go.md` exists (architect sign-off document) | File exists |
| G9 | ADR-0018 Phase B implemented: Effect Runner extracted as stateless decision function | Required for multi-athlete parallel DailyCoach execution |
| G10 | ADR-0044 accepted and Phase 8A implementation plan documented | ADR-0044 already accepted |
| G11 | Phase 8 Simplicity Review conducted and output documented in `0022-review-phase8-go.md` | Even if output is "nothing to consolidate", review must have occurred |

**Enforcement:** Before any Phase 8 branch is created:
1. The responsible engineer runs all verification commands above.
2. Results are pasted into `docs/adr/0022-review-phase8-go.md`.
3. The architect reviews and approves the go/no-go decision.

A PR with Phase 8 code without `docs/adr/0022-review-phase8-go.md` is a **PROCESS VIOLATION**
and must be closed without merge.

---

### 16.3 Documentation Consistency (ex-ADR-0024)

**Canonical lock code location:** `CANONICAL_LOCK_CODES` is a Python `frozenset` in
`titan/config/thresholds.py` — not in CLAUDE.md prose. When adding a new governance lock code:

1. Add it to `CANONICAL_LOCK_CODES` in `thresholds.py`.
2. Add it to `_CANONICAL_LOCK_CODES` in `tests/test_architectural_invariants.py`.
3. The T4-21 CI check (`tests/test_documentation_consistency.py`) verifies the two sets match.

**ADR index:** `docs/adr/README.md` must have exactly as many index rows as there are `.md`
files in `docs/adr/` (excluding `README.md` itself). A mismatch fails the T4-21 CI check.

**Evidence registry:** Every constant in `thresholds.py` must have a corresponding entry in
`evidence_registry.py`. Adding a new threshold without an evidence entry fails the CI check.

**CLAUDE.md anti-decay:** Any PR that modifies `CLAUDE.md` must:
1. Be reviewed by the architect (not auto-merged).
2. Pass `tests/test_claude_md_integrity.py` (T4-22 CI check).
3. Include a diff showing exactly what changed and why.

---

### 16.4 Agent Context Continuity (ex-ADR-0025)

The SESSION_START protocol (§2.0) is the primary mechanism. These rules supplement it:

**S0 — Advisor-originated tasks:** If a task was sourced from an advisory AI session
(ChatGPT, Gemini, Claude Chat), identify the recommendation explicitly and verify it does not
contradict any open or closed ADR **before** running S1–S5.

**CLAUDE.md integrity CI check (T4-22):** `tests/test_claude_md_integrity.py` asserts:
- ADR count in CLAUDE.md matches actual files in `docs/adr/`.
- Module count in CLAUDE.md matches actual `titan/` module count.
- CLAUDE.md does not claim "CLOSED" for phases with open debt items.

---

### 16.5 Multi-Agent Context Protocol (ex-ADR-0029)

When working in a multi-agent environment (Codex + Claude Code + advisory tools):

**Rule M1 — Advisor Context Gate:** Before giving any AI advisor a task touching architecture,
provide the relevant `docs/context-snapshot.md` section and the applicable ADRs. Any recommendation
that contradicts an existing ADR requires an explicit ADR amendment — not direct implementation.

**Rule M2 — Implementation Pre-Task:** If a task originated from an advisor recommendation,
verify it does not contradict any ADR before writing code (this is S0 in §16.4).

**Rule M3 — Single Source of Truth:** Architectural decisions live exclusively in `docs/adr/`.
ChatGPT/Gemini conversation history, Slack/Telegram messages, and GitHub issue comments are
ephemeral. If an advisory session produces an architectural decision, capture it as an ADR
before implementation begins.

**Rule M4 — Conflict Resolution:** If two agents produce contradictory implementations:
1. Stop both. Do not merge either PR until the conflict is resolved.
2. The architect identifies which is consistent with the ADR register.
3. The consistent one merges. The other is closed with an ADR reference.
4. If neither is fully consistent, a new ADR resolves the conflict.

The `docs/context-snapshot.md` file (generated by `scripts/generate_context_snapshot.py`, T4-28)
provides a machine-generated snapshot of open debt items, latest ADRs, test baseline, and
`CANONICAL_LOCK_CODES` for use in advisory sessions.

---

### 16.6 Structured Log Sustainability (ex-ADR-0031)

Every structured event emitted via `_emit_structured_event()` must carry a `severity` field:

| Severity | Usage | Telegram delivery |
|---|---|---|
| `CRITICAL` | Governance hard stop; requires immediate operator action | Always |
| `WARNING` | Soft downgrade, degraded mode, auth failure | Always |
| `INFO` | Routine operational telemetry; no action required | Never (log file only) |
| `DEBUG` | High-cardinality events; only at `LOG_LEVEL=DEBUG` | Never |

**Alert deduplication:** The same `(event_type, lock_code)` pair is suppressed within
`ALERT_DEDUP_WINDOW_HOURS = 20` (in `thresholds.py`). After `ALERT_PERSIST_SUMMARY_HOURS = 72`
of continuous same condition, a summary message is re-sent.

**Log rotation:** `RotatingFileHandler` with `LOG_MAX_BYTES = 10_485_760` (10 MB) and
`LOG_BACKUP_COUNT = 5` (50 MB max). Both are overridable via `.env`.

**New events:** Any new `_emit_structured_event()` call must include the `severity` parameter.
Omitting it is a contract violation (T2-14).

---

### 16.7 OutcomeTracker Integrity (ex-ADR-0035)

The `governance_outcomes` table has four integrity guardrails. **Do not remove or bypass them.**
Corrupted calibration data is a Tier 1 data integrity issue.

1. **Independence flag:** `decision_was_followed INTEGER` (1=followed, 0=athlete overrode).
   Override outcomes (`= 0`) are excluded from Phase 9 calibration training by default.
   `override_outcome_exclusion INTEGER DEFAULT 0` marks rows excluded for survivorship bias.

2. **Independence window:** `OutcomeTracker.record_outcome()` rejects outcomes where
   `outcome_timestamp − decision_timestamp < OUTCOME_INDEPENDENCE_WINDOW_DAYS * 86400`.
   `OUTCOME_INDEPENDENCE_WINDOW_DAYS = 2` is in `thresholds.py`.

3. **Calibration diversity gate:** Before any Phase 9 calibration run, the dataset must contain:
   ≥20% high-intensity decisions, ≥20% easy/recovery decisions, ≥10% HARD_STOP events.
   If the gate fails: emit `calibration_diversity_insufficient` at WARNING and defer calibration.

4. **Calibration circuit breaker:** No single calibration event may change any threshold by more
   than `CALIBRATION_MAX_THRESHOLD_DELTA_PCT = 0.10` (10%). Minimum evidence set:
   `CALIBRATION_MIN_OUTCOME_COUNT = 10`. Both constants are in `thresholds.py`.

---

### 16.8 Science Model Versioning (ex-ADR-0036)

Every module in `titan/science/` must declare at module level:

```python
MODULE_VERSION = "MAJOR.MINOR.PATCH"   # e.g., "1.0.0"
```

**Version increment rules:**

| Change | Increment | ADR required? |
|---|---|---|
| Bug fix, no output change for same inputs | PATCH | No |
| New optional parameter, backward-compatible | MINOR | No — CHANGES.md entry sufficient |
| Same inputs produce different output | **MAJOR** | **Yes** |
| Threshold constant change affecting gate semantics | MAJOR | Yes |

**MAJOR version increment additionally requires:**
1. New ADR: what changed, functions affected, whether existing `OutcomeTracker` data is still
   valid for Phase 9 calibration, and if not — a migration or reset plan.
2. `model_calibration_metadata.schema_version` updated for the affected model.
3. Structured event `science_model_breaking_change` emitted at next DailyCoach startup.
4. `algorithm_version_snapshot TEXT` column in `governance_outcomes` populated at decision time
   (JSON: `{"hrv_engine": "1.0.0", "governance_engine": "2.1.0", ...}`).

The CI check `tests/test_science_model_versions.py` (T4-30) asserts `MODULE_VERSION` exists
on every science module and is a valid semver string. A module missing `MODULE_VERSION` fails CI.

---

### 16.9 Metric Lifecycle (ex-ADR-0039)

Every metric computed by a science engine has a lifecycle state:

| State | Meaning | Required action |
|---|---|---|
| **Active** | Consumed by ≥1 governance gate, coaching output, or Operator Console payload | Continue; maintain in `evidence_registry.py` |
| **Under Review** | Computed but governance role unclear or predictive value unvalidated | Flag in `metrics_lifecycle_report` event; architect review within one phase |
| **Deprecated** | Confirmed redundant, superseded, or without validated governance role | Remove from computation; archive historical DB values; update evidence registry |

**New metric gate (hard — no exceptions):** No new metric may be added to the computation path without:
1. An `evidence_registry.py` entry specifying evidence quality and literature reference.
2. An explicit governance role: which gate, coaching output, or Operator Console payload consumes it.
3. A test asserting the metric is consumed (not just computed).

A metric added without meeting all three criteria fails code review.

**Phase boundary review:** At each phase boundary, the architect reviews all "Under Review" metrics
and classifies each as Active or Deprecated. Proposes at least one Deprecation per phase if metric
count exceeds 20.

**Deprecation protocol:** A metric may only be deprecated after ≥1 full phase in "Under Review"
state, with architect review confirming no downstream dependency, historical DB values preserved,
and the deprecation documented in `CHANGES.md` and the evidence registry.

---

### 16.10 Athlete Identity Invariant (ex-ADR-0040)

**Effective from 2026-03-06 forward. Applies to new code only.** Existing violations are documented
in the exemption register (module-level comment in `titan/core/database.py` and other exempt files).

**Rule A40-1 — No new implicit athlete queries:** New database access methods must accept
`athlete_id: str = "default"` as a parameter. The parameter must exist in the signature.

**Rule A40-2 — No new cross-athlete calibration defaults:** New science module constants
introduced as calibration defaults must be annotated:
```python
HRV_REFERENCE_BASELINE_MS = 55.0   # ADR-0040: single-athlete default; Phase 9 per-athlete
```

**Rule A40-3 — No new test fixtures without athlete_id:** New test fixtures that create athlete
data must include `athlete_id = "test_athlete_01"` (or similar).

**Rule A40-4 — New schema columns require athlete_id:** Any new table or column added after
2026-03-06 that stores per-athlete data must include `athlete_id TEXT NOT NULL DEFAULT 'default'`.

**Exempt modules** must carry this comment at module level:
```python
# ADR-0040-SINGLE-ATHLETE-SHORTCUT: This module assumes a single active athlete.
# Multi-athlete isolation is deferred to Phase 9 (ADR-0033 Layer 3, T5-07).
# Do NOT introduce new structural coupling that would be harder to isolate later.
```

The CI check `tests/test_athlete_isolation_invariant.py` (T4-31) enforces Rules A40-1 to A40-4
for non-exempt modules.

---

### 16.11 Complexity Budget (ex-ADR-0028)

The total `titan/` module count (excl. `__init__`/`__main__`) must not exceed **60**. If a phase
would push the count above 60, the architect must either retire/merge existing modules before adding
new ones, or explicitly revise the ceiling in a new ADR update.

The CI check in `tests/test_documentation_consistency.py` (T4-21/T4-27) asserts this ceiling:
```bash
python -c "
import pkgutil, titan
mods = list(pkgutil.walk_packages(titan.__path__, 'titan.'))
real = [m for m in mods if '__' not in m.name]
assert len(real) <= 60, f'COMPLEXITY BUDGET EXCEEDED: {len(real)} modules'
"
```

**ADR retirement:** At each phase close, update any ADR marked `Implemented` that is fully
superseded by a later ADR to `Superseded by [NNNN]`. Do not delete ADRs — the history is valuable.

**Phase boundary Simplicity Review:** Before any phase begins, the architect performs a Simplicity
Review: "Which existing modules could be merged, simplified, or removed without reducing capability?"
Output is documented (even if the answer is "nothing to consolidate"). This review is part of the
Phase 8 Entry Gate (G11 in §16.2).

---

*Last updated: 2026-03-07 (Phase 7.9 — §14 Project Safeguard Protocols added: Agent Challenge Rule §14.1, Change Justification Requirement §14.2, Cooling-Off Protocol §14.3, No Impulse Implementation Rule §14.4, Complexity Budget Rule §14.5; §2.0 Environment Setup mandatory pre-task gate added; §2.4 Optional fast iteration rule added; canonical sequence in §2 updated to include Step 0; §3.6 Documentation Edit Policy added; §10 Common Mistakes + §11 Pre-Delivery Checklist updated to 24 items; §12 Debt Register Discipline, §13 Architecture Decision Boundary, §1 role boundary hardening; §15 Engineering Scratchpad Protocol added 2026-03-07; §16 Domain-Specific Engineering Contracts added 2026-03-07 — process rules from ADR-0021, 0022, 0024, 0025, 0028, 0029, 0031, 0035, 0036, 0039, 0040 distilled here; ADR triage: 7 historical ADRs retired, 11 process ADRs moved to §16, 27 architectural ADRs remain in docs/adr/). Authoritative for all agents and engineers operating on TITAN OS.*
