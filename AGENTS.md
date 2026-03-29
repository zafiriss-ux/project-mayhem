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
- Substituting diagnostic runs (`pytest -vv`, `--durations=20`, `pytest -x`, targeted subsets) for Gate 2 or Gate 3. Diagnostic runs identify root causes — they never constitute acceptance evidence. Gate 2 and Gate 3 are the only accepted forms of gate evidence in a deliverable report.

If an override is required for the suite to run at all, that is a **repo-level issue**. Either fix it within the current task's scope, or STOP and write a SCRATCHPAD OBS entry (§15) before continuing. Do NOT add it directly to `TECHNICAL_DEBT.md`.

---

## 1. Role Boundaries

| Role | Responsibility |
|------|---------------|
| **Architect** (Claude operating in an architectural session — see §3.6) | System design, ADR authorship, tier ordering, scope approval |
| **Owner** (project owner directing work) | Work priorities, strategic direction, task assignment — not automatic Architect authority |
| **Implementation Engineer (Codex / agent)** | Execution of scoped tasks only — no design decisions, no ADR authorship |
| **Records Steward** | `TECHNICAL_DEBT.md` closure wording, commit hash recording, OPEN↔RESOLVED integrity |

Agents execute. They do not design.

**Operating responsibility split (written clarification of existing roles — non-negotiable):**

| Role | Owns exclusively |
|------|-----------------|
| **Codex** | Implementation, tests, mandatory gates (ruff + pytest), local-scoped result reporting |
| **Records Steward** | `TECHNICAL_DEBT.md` closure wording, commit hash recording, OPEN↔RESOLVED integrity |
| **Architect** | Process rules, task sequencing, escalation decisions, governance interpretation |

Codex does not write closure wording or record commit hashes in canonical documents — those are Records Steward territory. The Records Steward does not make sequencing or governance interpretation decisions — those are Architect territory. These boundaries are not guidelines; violating them is a process violation.

**Codex implementation reporting — explicit scope:**

Allowed in a Codex implementation report:
- Files changed
- Tests added or updated
- Gate results (ruff / pytest strict / pytest full)
- Branch name, local commit hash, PR link
- Blockers or stop reasons

Forbidden in a Codex implementation report:
- RESOLVED wording
- Canonical status claims (DONE, CLOSED, or equivalent)
- Commit hash recording instructions in canonical documents
- Any language implying the task is closed

**Owner authority vs Architect authority:** The project owner directs work and sets priorities.
However, owner instructions do not automatically carry Architect-level authority. The Architect
role is exercised by Claude operating in an architectural session with the project owner (§3.6).
ADR authorship, governance gate logic changes, schema topology decisions, and tier ordering
changes require the Architect role — not merely an owner instruction. An owner instruction
requesting any of these without an explicit architectural session means the agent must stop,
write a SCRATCHPAD OBS entry (§15), and await the Architect role being exercised.

The foundational principles governing all roles (Owner Proposal Guardrail, Engineering Ctrl-Z,
Architect Constrained by Invariants, Rules Decide) are stated in standalone form in
`GOVERNANCE_PRINCIPLES.md`. That document is extracted from this contract — on any conflict,
this document (`AGENTS.md`) wins.

An agent **must not**:
- Author or amend an ADR (Architecture Decision Record)
- Redesign, restructure, or re-architect any system component
- Add new abstraction layers or introduce new module boundaries
- Change tier ordering or phase sequencing
- Make database schema topology decisions beyond what the task explicitly specifies
- Alter governance gate logic without an ADR reference and architect approval

When you believe a redesign or architectural decision is needed: write a SCRATCHPAD OBS entry
(§15). Do NOT implement it. Do NOT draft an ADR. Do NOT add it directly to `TECHNICAL_DEBT.md`
without an architect DEC. See §13 for the full protocol.

### 1.1 Subsystem Ownership — Owner-of-Record

Each major subsystem has an Owner-of-Record responsible for its technical integrity:

| Subsystem | Path | Owner-of-Record | Scope |
|-----------|------|-----------------|-------|
| Config / thresholds | `titan/config/` | **Architect** | All safety constants, evidence registry, lock code set |
| Science engines | `titan/science/` | **Architect** | Engine contracts, governance gate logic, ML scaffold |
| Core infrastructure | `titan/core/` | **Architect** | DB schema, persistence adapter, athlete profile contract |
| Integrations | `titan/integrations/` | **Codex** (under Architect brief) | Garmin sync, weather API, Telegram bot |
| Features | `titan/features/` | **Codex** (under Architect brief) | Weekly planner, optimal time, nutrition optimizer |
| Orchestration / UI | `titan/orchestration/`, `titan/ui/` | **Architect** | DailyCoach pipeline, OperatorConsole, menu system |

**Owner-of-Record duties:** The Owner-of-Record must be consulted (or is) before any change that
crosses a subsystem boundary, adds a new dependency between subsystems, or modifies a public contract.
For Architect-owned subsystems, every change requires a task entry with binary acceptance criteria.
For Codex-owned subsystems, changes require an architect brief but Codex may propose scope.

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

**Role definition:** The architect is Claude (the AI operating in architectural sessions with the project owner). Codex is the implementation agent. Only the architect creates, restructures, or rewrites documentation. Codex may make only the narrow permitted edits listed below.

**Covered files:** `CLAUDE.md`, `AGENTS.md`, `README.md`, any file under `docs/`

**The only permitted documentation edits are:**

| Permitted update | Trigger | Section |
|---|---|---|
| Test count snapshot in `CLAUDE.md` | Tests added/removed in current task | §12.3 |
| ADR index table row in `CLAUDE.md` | Integrating a new architect-authored ADR | §12.4 |
| Debt entry body in `TECHNICAL_DEBT.md` | Task closure (mark RESOLVED) | §12.1 |
| New OBS entry in `SCRATCHPAD.md` | Out-of-scope finding discovered | §12.2 / §15 |
| Clarification append to existing OBS entry in `SCRATCHPAD.md` | Claude has set `CLARIFICATION_NEEDED`; Codex appends requested context to the existing OBS (no new OBS created) | `SCRATCHPAD.md §CLARIFICATION flow` |
| Tracking table row in `TECHNICAL_DEBT.md` | Either of the two debt rows above | §12.1 / §12.2 |

**Everything else is prohibited:**
- Do not reword, restructure, or "improve" existing documentation.
- Do not add sections, paragraphs, or notes beyond what the task explicitly requires.
- Do not update `CLAUDE.md` for minor wording corrections or to reflect your interpretation of the system.
- Do not edit `AGENTS.md` at all — it is maintained exclusively by the architect.

If you believe a documentation update is needed beyond the table above, write a SCRATCHPAD OBS
entry (§12.2 / §15) and stop. Do NOT add it directly to `TECHNICAL_DEBT.md`.

### 3.4 Out of Scope Findings
If you discover another issue while working: **do not fix it.** Write a SCRATCHPAD OBS entry
(§15). Do NOT add it directly to `TECHNICAL_DEBT.md` without an architect DEC. Continue only
with the original scoped task.

The canonical routing path is: SCRATCHPAD OBS → architect DEC → `TECHNICAL_DEBT.md` entry.
See `SCRATCHPAD.md §Canonical Routing Rule` for the single authoritative statement.

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

**`titan/science/governance_engine.py` is architecture-locked.** See ADR-0009 and §16.1.
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
| `titan/orchestration/daily_coach.py` | 12-step morning routine — orchestration entry point; `DegradedModeTracker`, `PersistenceFailure` sentinel |
| `titan/ui/operator_console.py` | OperatorConsoleService (dashboard, session explorer, override) |
| `titan/science/ml_safety.py` | ML kill-switch (`TITAN_ML_KILL_SWITCH` env) |
| `titan/integrations/notification_gateway.py` | `NotificationGateway` — ordered fallback chain (Telegram → File) |
| `tests/test_governance_mutation.py` | Boundary-ON/OFF tests per governance gate (T4-18 / §16.1) |
| `tests/test_architectural_invariants.py` | AST-enforced structural constraints (T4-19) |
| `.github/pull_request_template.md` | PR checklist with 3-gate status + architecture guard items (T4-20) |
| `docs/adr/` | Architecture Decision Records (0006–0045, 27 architectural ADRs) |
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
| Modifying `governance_engine.py` without ADR | Silent safety regression (ADR-0009 / §16.1) |
| Adding a gate without boundary tests in `test_governance_mutation.py` | Boundary regressions undetectable (T4-18 / §16.1) |
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
[ ] I verified the Definition of Ready (§17.5): scope clear, files identified, criteria binary, tests known.
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
[ ] Out-of-scope findings are in SCRATCHPAD.md OBS entries (§15), not in code or directly in TECHNICAL_DEBT.md.
[ ] I pushed to a claude/* branch only — NOT to main or master.
[ ] I opened exactly one PR using .github/pull_request_template.md and pasted the PR link.
[ ] My PR description contains a Scope Declaration with gate status (Section 3.3).
[ ] I marked the completed debt item ✅ RESOLVED with date + commit hash in its entry body (§12).
[ ] I added a **Task learning:** block to the TECHNICAL_DEBT.md resolution entry (§12.1).
[ ] I updated the tracking table at the bottom of TECHNICAL_DEBT.md (§12).
[ ] If test count changed: I updated the historical snapshot in CLAUDE.md (§12).
[ ] If a new ADR was written: I updated the ADR index table in CLAUDE.md (§12).
[ ] I did NOT make any architectural decision without explicit architect approval (§13).
[ ] I did NOT edit CLAUDE.md, AGENTS.md, README.md, or docs/ beyond what §3.6 and §12 explicitly permit.
[ ] I ran scripts/check_scratchpad.sh at Step 0.5 and it returned exit 0.
[ ] If any trigger condition (T-SCRATCHPAD-1 through T-SCRATCHPAD-5) was met during this task, I wrote an OBS entry in the correct queue (BLOCKING or NON-BLOCKING) and set STATUS: REVIEW_REQUESTED.
[ ] I did NOT write proposed solutions in OBS entries — only engineering observations (facts, file:line refs, architectural question).
[ ] I ran `ls <every file I claim to have created>` and confirmed each path exists. I did not rely on my own prior output as proof of existence.
```

**All 30 boxes must be checked. A PR with any unchecked box is NOT DONE.**

---

## 12. Debt Register Discipline — Mandatory on Every Task Close

The debt register (`TECHNICAL_DEBT.md`) and the project overview (`CLAUDE.md`) are
**living documents**. Every agent is responsible for keeping them current as a condition
of task completion. Stale register entries are as harmful as stale code.

### 12.1 On task closure (always)

**Role split at closure (non-negotiable):** Codex delivers implementation evidence only. The Records Steward performs all canonical closure actions. RESOLVED marking, commit hash recording, and tracking table update are Records-Steward-only actions — Codex must not perform them.

**Codex closure deliverable (Codex-only):** When all three mandatory gates are green, Codex reports: files changed, tests added/updated, gate results (ruff / pytest strict / pytest full), branch name, local commit hash, and any blockers or stop reasons. Codex does not write RESOLVED, DONE, CLOSED, or any equivalent closure language.

**Canonical closure actions (Records Steward-only):**

After remote verification succeeds (i.e., `git push` has completed without error and the commit is confirmed present on the remote), the Records Steward performs:

1. **Mark the debt entry** in `TECHNICAL_DEBT.md` (Records Steward action — not Codex):
   - Change the heading status from `🔴 OPEN` to `✅ RESOLVED <YYYY-MM-DD>`
   - Change the `**Status:**` line to: `✅ RESOLVED <YYYY-MM-DD>. Commit: <short-hash>.`
   - Rename `**Problem:**` to `**Original state (pre-fix):**` and convert present-tense verbs to past tense.
   - Add a `**Resolution:**` block summarising what was changed (modules, approach, test count at closure).
   - Add a `**Task learning:**` block (required — one to three sentences) capturing what this task
     revealed that is not obvious from the resolution itself. Focus on process, coupling, or failure-mode
     insights that would help the next engineer avoid the same trap. If the task was completely routine
     with no new insight, write: `Task learning: No new engineering insight — routine implementation.`

2. **Update the tracking table** at the bottom of `TECHNICAL_DEBT.md` (Records Steward action — not Codex):
   - Change the row for this item from `OPEN` to `✅ RESOLVED` and fill in the date column.

Both updates are **required**. Updating one without the other is incomplete.

**Verify-first invariant (non-negotiable):** No hash — closure hash, implementation hash, or any other commit reference — may be recorded in `TECHNICAL_DEBT.md` or any other canonical document before remote verification succeeds (i.e., `git push` has completed without error and the commit is confirmed present on the remote). If remote verification fails, stop and report the branch name and local commit hash. Every new implementation attempt starts fresh; a prior candidate hash that was not remotely verified must never be reused or recorded.

**Heavy-task pre-close checkpoint (mandatory — not a new process phase, a pre-condition to Records Steward closure actions):**

A task is **heavy** if any of the following is true:
- It touches ≥4 production modules.
- It crosses ≥2 of these 3 surfaces: orchestration / governance / output.
- It includes both implementation surface and canonical-record risk in the same pass.
- It is explicitly flagged as heavy by the architect in the task brief.

For heavy tasks, Codex must explicitly confirm all three of the following before handing off to the Records Steward:

1. Implementation exists at the claimed location — the file and module are present and correct.
2. All three mandatory gates are green — current run (ruff + pytest strict + pytest full), not a cached or prior-session result.
3. Remote state is verifiable — `git push` completed without error and the commit is confirmed present on the remote.

If any of the three cannot be confirmed: Codex does not write closure language. Codex delivers branch name and local commit hash only. Canonical closure is deferred to the Records Steward after remote verification.

**Non-push environment fallback:** In non-push environments, Codex does not write closure language. Codex delivers branch name and local commit hash only. Canonical closure is deferred to the Records Steward after remote verification.

### 12.2 On out-of-scope finding (always)

When you discover an issue outside the current task scope:

1. Write a SCRATCHPAD OBS entry (§15) describing the finding. Set STATUS: REVIEW_REQUESTED.
2. Do NOT add a `TECHNICAL_DEBT.md` entry directly — the architect creates or authorises debt
   entries via a DEC (Decision entry in `SCRATCHPAD.md`).
3. Do NOT fix it in the current task (§3.4 / Rule E4).

**Routing invariant:** `TECHNICAL_DEBT.md` entries for out-of-scope findings are created only
after an architect DEC. See `SCRATCHPAD.md §Canonical Routing Rule`.

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

### 12.5 Debt-Clear Window — Mandatory Periodic Debt Reduction

**Purpose:** Prevent `TECHNICAL_DEBT.md` from operating as a pure backlog parking lot.
Periodic mandatory clearance ensures the register remains an active governance instrument,
not a graveyard of deferred items.

**Rule:** Every 5 tasks completed (counted at the tracking table), the architect MUST
schedule at least 1 item from `TECHNICAL_DEBT.md` as the next assigned task, before any
new feature or Phase work is assigned. The item selected must be:

1. OPEN or PARTIALLY RESOLVED in the tracking table.
2. From the lowest open Tier (T1 before T2, T2 before T3, etc.) — tier ordering (Rule E1) applies.
3. Not blocked by an unresolved ADR or a higher-Tier prerequisite.

**Counting:** The debt-clear counter resets to 0 after a debt item is resolved. The counter
increments on every task close (§12.1), regardless of task type (feature, bug, test, process).

**Enforcement signal:** At session start (§2.0 environment check), Codex MUST report the
current debt-clear counter alongside the OPEN item count:

```
S2b. python -c "
import subprocess, re
result = subprocess.run(['grep', '-c', r'OPEN\|PARTIALLY RESOLVED', 'TECHNICAL_DEBT.md'],
                       capture_output=True, text=True)
print('Open debt items:', result.stdout.strip())
"
# Architect tracks the counter manually via the tracking table task-close dates.
```

**Exception:** If the only OPEN items are blocked (awaiting ADR or higher-Tier prerequisite),
the window is suspended until at least one item becomes unblocked. The architect must note
the suspension explicitly in the task assignment message.

**Rationale:** Debt compounds silently. A register with 40 OPEN items and no closed items
in the last 20 tasks is a governance failure — not a feature backlog. This rule enforces
the discipline that technical debt is not optional work; it is load-bearing maintenance.

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
| Modifying governance gate logic without an ADR | Safety regression (ADR-0009, §16.1) |
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
| Adding a column to an existing table via the versioned migration pattern *(see definition below)* |
| Adding a new method to an existing class (within the class's existing responsibility) |
| Adding tests for existing or new behaviour |
| Adding constants to `thresholds.py` or `evidence_registry.py` |
| Adding structured log events following the existing pattern |
| Fixing a bug in existing logic without changing its contract |

**Definition — additive column vs schema topology change:**
- **Additive column** (permitted in §13.3): adding a nullable or default-valued column to an
  existing table via the versioned migration pattern. The table structure, relationships, and
  query patterns are unchanged.
- **Schema topology change** (requires §14.2 justification): new tables, table removal,
  normalization, denormalization, foreign-key graph changes, or index restructuring that alters
  query patterns. These are permanent and require architectural sign-off.

§13.3 does not permit schema topology changes. An agent may not use the "additive column"
permission to justify creating a new table, renaming a table, or any other topology change.
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
  C) Write a SCRATCHPAD OBS entry (§15) and stop — the architect routes it to TECHNICAL_DEBT.md via DEC

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
- If an idea arises mid-task ("while I'm here, I could also..."), it must be written as a
  SCRATCHPAD OBS entry (§15) and left there. The current task continues unchanged. The
  architect converts it to a `TECHNICAL_DEBT.md` entry via DEC if appropriate.
- An agent must never begin implementing something "obvious" that was not scoped in the task.

**The correct sequence:**
```
idea → SCRATCHPAD OBS entry → architect DEC → TECHNICAL_DEBT.md entry → task assigned → implementation
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

If all three questions pass: record the abstraction proposal as a SCRATCHPAD OBS entry (§15)
and wait for architect DEC. Do not add it directly to `TECHNICAL_DEBT.md` and do not implement
inline. The canonical routing applies: SCRATCHPAD OBS → architect DEC → `TECHNICAL_DEBT.md` entry.

This rule enforces §16.11 (Complexity Budget and Simplicity Gate) at the agent level.

---

## 15. Engineering Scratchpad Protocol — Codex Obligations

> **The scratchpad (`SCRATCHPAD.md`) is the structured communication channel from Codex to the
> architect (Claude). It is NOT a to-do list, NOT a design document, and NOT a place for
> solutions. It is a place for raw engineering findings that require an architectural decision.**

Codex writes **Observation (OBS)** entries to `SCRATCHPAD.md` when the trigger conditions
below are met. After writing, Codex sets the document status to `REVIEW_REQUESTED`. Codex
**MAY** complete any current subtask already in progress at the moment of writing the OBS.
Codex **MAY NOT** start any new top-level task until the architect clears the status to
`IDLE`. See `SCRATCHPAD.md §Document Status` for the single authoritative in-flight work
policy.

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

**When:** Codex writes 3 or more out-of-scope OBS entries (§3.4 / §12.2 / §15) to `SCRATCHPAD.md`
within a single session, AND those findings share a common module, subsystem, or failure mode.

Codex MUST write an OBS entry synthesising the pattern:
- List the related OBS entry IDs (OBS-XXX references) from this session
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
| G10 | ADR-0044 accepted and Phase 8A implementation plan documented | ADR-0044 already accepted. Also an ongoing Phase 8B prerequisite: the Phase 8A implementation plan must be current and active before any Phase 8B work begins. |
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

The total `titan/` module count (excl. `__init__`/`__main__`) must not exceed **62**. If a phase
would push the count above 62, the architect must either retire/merge existing modules before adding
new ones, or explicitly revise the ceiling in a new ADR update.

The CI check in `tests/test_documentation_consistency.py` (T4-21/T4-27) asserts this ceiling:
```bash
python -c "
import pkgutil, titan
mods = list(pkgutil.walk_packages(titan.__path__, 'titan.'))
real = [m for m in mods if '__' not in m.name]
assert len(real) <= 62, f'COMPLEXITY BUDGET EXCEEDED: {len(real)} modules'
"
```

**T4-27-C module ceiling update protocol (feature additions):**
1. If a task adds one or more new `titan/` modules as a deliberate structural choice, the implementing engineer must update the module ceiling in `tests/test_documentation_consistency.py::test_module_count_within_budget` in the same commit.
2. Before implementation begins, the architect must confirm the new ceiling value explicitly in that task's acceptance criteria.
3. Ad hoc ceiling corrections after the fact are a process violation.

This protocol is sourced from `TECHNICAL_DEBT.md` item **T4-27-C** and is mandatory for all accepted feature additions that intentionally introduce new structural modules.

**ADR retirement:** At each phase close, update any ADR marked `Implemented` that is fully
superseded by a later ADR to `Superseded by [NNNN]`. Do not delete ADRs — the history is valuable.

**Phase boundary Simplicity Review:** Before any phase begins, the architect performs a Simplicity
Review: "Which existing modules could be merged, simplified, or removed without reducing capability?"
Output is documented (even if the answer is "nothing to consolidate"). This review is part of the
Phase 8 Entry Gate (G11 in §16.2).

---

## §17 Phase 8 Per-Item Workflow Standard

> **This section is a hard process rule, not a guideline.**
> Every Phase 8 sprint item — without exception — must follow one of the two canonical sequences
> below. No ad-hoc variations, no step omissions, no implicit assumptions.

### 17.1 Path Selection (architect decides before Codex starts)

Before assigning any Phase 8 item to Codex, the architect classifies it against the PILOT-01
applicability gate (defined in `TECHNICAL_DEBT.md` under PILOT-01):

| Condition | Path |
|-----------|------|
| ALL applicability criteria met **AND** architect has written "APPROVED" in the PILOT-01 entry | **Path B — QA-assisted** |
| Any criterion fails **OR** no APPROVED note present | **Path A — Standard** |

Path A is the default. Path B requires an explicit opt-in action from the architect each time.

---

### 17.2 Path A — Standard (default)

```
1. Architect brief       — task written in TECHNICAL_DEBT.md with binary acceptance criteria
                           and **Workflow Path: A** declared in the item header
1a. Definition of Ready  — Codex verifies DoR checklist before writing any code (see §17.5)
2. Codex implementation  — code + tests written per §ABSOLUTE RULE and HARD GATE preconditions
3. Mandatory gates       — ruff check . → pytest strict → pytest full (all three, all green)
4. Commit / PR           — canonical commit format; PR opened only after gate 3 passes
```

No step may be skipped. Steps 3–4 may not be reordered. "Targeted tests pass" is not a
substitute for step 3 (see §HARD GATE — Forbidden validation shortcuts).

---

### 17.3 Path B — QA-assisted (PILOT-01 opt-in only)

```
1. Architect brief       — task written in TECHNICAL_DEBT.md; PILOT-01 APPROVED note added;
                           **Workflow Path: B (APPROVED)** declared in the item header
1a. Definition of Ready  — Codex verifies DoR checklist before writing any code (see §17.5)
2. Codex implementation  — code + tests written per §ABSOLUTE RULE and HARD GATE preconditions
3. Opus QA review        — test quality review (scope bounded in TECHNICAL_DEBT.md PILOT-01)
     ├─ APPROVE  →  proceed to step 4
     └─ REJECT   →  Codex fixes, one re-review; if still REJECT, proceed to step 4 anyway
4. Mandatory gates       — ruff check . → pytest strict → pytest full (all three, all green)
5. Commit / PR           — canonical commit format; PR opened only after gate 4 passes
```

**PILOT-01 invariant (non-negotiable):** Opus QA approval is advisory only. Step 4 is always
required, regardless of Opus QA outcome. Opus QA approval does NOT satisfy the mandatory gates.

**QA role boundary (non-negotiable):** The QA reviewer's sole deliverable is a verdict: `QA PASS` or `QA FAIL` with rationale. The QA reviewer does **not** instruct commit, push, mark-RESOLVED, or next-task actions — those decisions belong exclusively to the Architect. A QA suggestion to "commit and push" or "mark RESOLVED" is out of role scope and must be ignored. Only the Architect may authorize post-QA actions.

---

### 17.4 Enforcement Rules

- **E16 — Path declared before start:** The architect must select Path A or Path B and record
  it in the `**Workflow Path:**` field of the TECHNICAL_DEBT.md item before Codex begins work.
  `TECHNICAL_DEBT.md` is the sole canonical record — a path stated only in the task assignment
  message is not valid (messages are ephemeral; debt entries are version-controlled).
  A task without a declared path defaults to Path A.

- **E17 — No mid-item path switching:** Once an item has started on Path A, it cannot switch
  to Path B (or vice versa) mid-implementation. If the architect determines a path change is
  needed, the item must be stopped, re-scoped, and restarted from step 1 on the new path.

- **E18 — Workflow drift is a process violation:** Delivering an item via any sequence other
  than Path A or Path B (e.g., skipping the architect brief, running gates only for targeted
  tests, omitting the QA step on an APPROVED Path B item) is a process violation with the same
  severity as a HARD GATE failure. Stop, document the deviation in `TECHNICAL_DEBT.md`, and
  restart from the violated step.

- **E19 — DoR gate is mandatory before implementation:** Codex must complete the Definition of
  Ready checklist (§17.5) before writing any implementation code for a Phase 8+ item. A task
  that fails the DoR check must be returned to the architect with a written gap report rather
  than proceeding with incomplete information.

---

### 17.5 Definition of Ready (DoR) — Pre-Implementation Gate

**Who:** Codex (Implementation Engineer) — runs this gate after reading the architect brief,
before writing any implementation code.

**When:** Step 1a of Path A and Path B (both paths).

**What:** Codex answers ALL four questions below. If any answer is NO, Codex stops and reports
the gap to the architect before proceeding.

```
DoR CHECKLIST — required before any implementation begins
─────────────────────────────────────────────────────────
[ ] SCOPE CLEAR       — The task description unambiguously defines what must change.
                        I can state in one sentence exactly what new behaviour I must produce.

[ ] FILES IDENTIFIED  — I can name every file that will be created or modified.
                        No file will be modified as a surprise mid-implementation.

[ ] CRITERIA BINARY   — The acceptance criteria are testable and binary (PASS / FAIL).
                        There is no criterion that requires subjective judgement to evaluate.

[ ] TESTS KNOWN       — I know which test file(s) will cover the new behaviour,
                        and whether they exist already or need to be created.
```

**If any box cannot be checked:** Codex writes one sentence per unchecked item describing the
gap and appends it to the SCRATCHPAD.md as a BLOCKING OBS with status `REVIEW_REQUESTED`.
Codex does **not** begin implementation until the architect clears the gap.

**If all four boxes can be checked:** Codex states `DoR: PASS` in the implementation brief
(first line of the implementation session log) and proceeds to step 2.

A DoR gap reported via SCRATCHPAD.md is non-punitive — it is the correct behaviour. Proceeding
past an unresolved DoR gap (and discovering the issue mid-implementation) is a process violation.

---

### 17.6 Bottleneck / Owner / Unblock — Optional Metadata for Complex Items

For items that involve multi-role handoffs or are blocked mid-execution, the architect may add
an optional `**Bottleneck:**` block to the TECHNICAL_DEBT.md entry to make the flow state
immediately visible. This is **not** required for routine items; it is a diagnostic tool for
items that are blocked or at a handoff point.

**Format (add to the TECHNICAL_DEBT.md entry when a bottleneck exists):**

```
**Bottleneck:** <one-sentence description of where the flow is stuck>
**Owner:**      <role responsible for unblocking: Architect | Codex | QA>
**Unblock condition:** <the single verifiable action that clears this bottleneck>
```

**Examples:**

```
**Bottleneck:** QA verdict pending — D1 implementation awaiting Opus QA review (Path B step 3)
**Owner:**      QA
**Unblock condition:** QA PASS or QA FAIL verdict written in the task entry

**Bottleneck:** Gate 3 (python -m pytest -q) failing — 3 tests RED in test_persistence.py
**Owner:**      Codex
**Unblock condition:** Full canonical test suite 100% green with count ≥ previous baseline

**Bottleneck:** ADR decision required — D2 schema topology has two options (see OBS-008)
**Owner:**      Architect
**Unblock condition:** Architect writes DEC-008 and designates the chosen schema topology
```

The Bottleneck block must be removed (or updated to `**Bottleneck:** None`) when the item is
no longer blocked. A stale Bottleneck block is misleading and must be corrected immediately.

---

## §18 Canonical Source Map

The following hierarchy defines which document is authoritative for each category of
information. When two documents conflict, the document listed as canonical for that
category wins.

| Category | Canonical document | Role of other sources |
|----------|-------------------|-----------------------|
| Task status, sequencing, and open/closed state | **`TECHNICAL_DEBT.md`** | All other documents reflect snapshots; `TECHNICAL_DEBT.md` is the live register |
| Process rules, workflow sequences, enforcement rules | **`AGENTS.md`** (this document) | `CLAUDE.md` §Engineering Rules is an index/reference; `AGENTS.md` wins on conflict |
| Architecture decisions (ADRs) | **`docs/adr/`** | `CLAUDE.md` ADR index is a summary; the ADR file in `docs/adr/` is authoritative |
| Backend interface contract (SQLite / PostgreSQL parity) | **`docs/PARITY_MATRIX.md`** | Inline notes in `TECHNICAL_DEBT.md` or `persistence.py` comments are summaries only |
| Orientation, historical snapshot, module inventory | **`CLAUDE.md`** | Read-only orientation — not authoritative for live state |
| Weekly Governance Log, Codex Handoff Blocks, session summaries | **Derived operational views** — not authoritative | These are convenience summaries; `TECHNICAL_DEBT.md` + `AGENTS.md` are the source |

**Conflict resolution rule:** When a derived view (Governance Log, Handoff Block, session
summary) contradicts the canonical source for its category, the canonical source wins and
the derived view must be corrected at the next records pass.

---

## §19 Mandatory Change-Type Field (Phase 8+)

Every new Phase 8+ item in `TECHNICAL_DEBT.md` must include a **`Change Type:`** field in
its item header. This field is required at the time the brief is written — not retrospectively.

**Valid values:**

| Value | Meaning |
|-------|---------|
| `implementation` | Code changes, new or modified modules, test changes |
| `records-only` | Documentation updates, `TECHNICAL_DEBT.md` records, no production code changes |
| `policy-only` | `AGENTS.md` or process contract changes only; no code changes |
| `architect-decision` | ADR authorship, architectural decisions, design artefacts; no Codex implementation handoff |
| `audit-only` | Read-only assessment, call-site audit, or triage pass; no changes to any file |

**Execution semantics:**

- `implementation`: Standard Path A or Path B workflow (§17.2 / §17.3). All three mandatory
  gates required.
- `records-only`: No production code changes permitted. Gates 1 and 3 still required; Gate 2
  (strict) required only if test files were touched. Commit message prefix: `records:`.
- `policy-only`: Only `AGENTS.md`, `CLAUDE.md`, or process documents may change. No code, no
  tests. All three gates still required to confirm no unintended side-effects.
- `architect-decision`: No Codex implementation handoff at this stage. Architect authors
  the artefact directly or under direct architect direction. May have no gate requirement
  (document-only output), or gates apply if the decision produces a code artefact.
- `audit-only`: No file modifications. Report-only output. No gates required.

**Backfill policy:** Only items where the architect explicitly orders backfill receive the
`Change Type:` field retroactively. Do not backfill older items beyond those explicitly
directed.

---

## §20 Mini Drift Postmortem Rule

When a process violation (workflow drift, skipped gate, scope creep, or instruction
contradiction) is discovered and resolved, the resolving record (in `TECHNICAL_DEBT.md`,
`AGENTS.md`, or `CHANGES.md` as appropriate) may include a mini drift postmortem in
the following format:

```
- Drift: <one sentence describing what the process violation was>
- Why it escaped: <one sentence explaining why the existing guard did not catch it>
- Guard now in place: <one sentence describing the corrective rule or check added>
```

**Scope — when postmortem IS required:**
- The same drift pattern appears for a second time (recurrence trigger).
- The drift concerns a canonical document (`AGENTS.md`, `TECHNICAL_DEBT.md`, `docs/adr/`).

**Scope — when postmortem is NOT required:**
- A single corrective pass that fixes a derived-view drift (Weekly Governance Log,
  Codex Handoff Block, session summary, `CLAUDE.md` snapshot). In these cases, the
  fix itself is sufficient; a postmortem is not required unless the pattern recurs.

**Purpose:** The mini postmortem is the mechanism by which process gaps are converted
into durable guard rules. It is triggered by recurrence or canonical-document impact —
not by every corrective pass.

---

## §21 Governance Friction Principle

Every new governance rule added to `AGENTS.md` must satisfy at least one of the
following conditions before it is accepted:

- **(a) Replacement:** The new rule explicitly replaces an existing rule (the old rule
  is removed or superseded, and the net rule count does not increase).
- **(b) Friction reduction:** The new rule measurably reduces manual synchronisation
  effort or operational friction (e.g., eliminates a recurring manual check, removes an
  ambiguity that has required ad-hoc clarification, or replaces an implicit convention
  with an explicit one that can be verified mechanically).

If a proposed rule satisfies neither (a) nor (b), it is not added. The rationale must
be stated in the record entry that introduces the rule.

**Application:** This principle applies to rules added from 2026-03-15 onwards. It does
not trigger retroactive review of existing rules.

---

## §22 Friday Governance Review Output Rule

Every Friday Governance Review must produce a written output entry. The entry must be
appended to the `## Weekly Governance Log` section in `TECHNICAL_DEBT.md` using the
template defined there.

**Minimum content:** Even if there is nothing substantive to record, a one-sentence
"State: healthy — no changes" entry is sufficient and satisfies this rule.

**Completion gate:** A Friday Governance Review that has no written output entry is not
considered completed. It must not be referenced as a completed review in any document
until the entry exists.

---

## §23 Canonical Codex Handoff Template

Every architect-to-Codex handoff for a Phase 8+ pass must include a structured brief using the
canonical template below. The template is reusable across all pass types and serves as the DoR
(Definition of Ready) contract for the pass.

### Canonical Handoff Template (required fields)

```
Pass type:                <audit | records | implementation | correction-only>
Change Type:              <policy-only | records-only | implementation | architect-decision | correction>
Workflow Path:            <Path A | Path B | N/A>
Execution unit:           <exact deliverable or scope slice for this pass>
Deliverable:              <specific output this pass must produce>
Stop condition:           <what terminates this pass — success criteria>
Allowed:                  <explicit list of permitted actions>
Forbidden:                <explicit list of prohibited actions>
Expected response format: <structured summary | OBS entries | gate output | records confirmation>
```

If any required field is absent, the pass is **DoR FAIL** — the implementer must request
clarification before beginning. The implementer does not infer missing fields.

### Fixed Lane Templates

The four canonical variants below are pre-approved patterns. When an architect brief cites one
of these lane names, the corresponding template is implicitly imported.

#### Lane A — audit-only

```
Pass type:                audit
Change Type:              N/A (read-only)
Workflow Path:            N/A
Execution unit:           [defined in brief]
Deliverable:              OBS entries in SCRATCHPAD.md
Stop condition:           All observations captured; SCRATCHPAD.md STATUS: REVIEW_REQUESTED
Allowed:                  Read files, run grep/tests for evidence gathering, write OBS entries
Forbidden:                Any file modification outside SCRATCHPAD.md; no DECs (DECs are architect-only)
Expected response format: Structured OBS list with file:line citations; no recommendations
```

#### Lane B — records-only

```
Pass type:                records
Change Type:              records-only
Workflow Path:            N/A
Execution unit:           [defined in brief]
Deliverable:              Updated canonical document(s) as specified
Stop condition:           All specified documents updated; gates not required (doc-only per §19)
Allowed:                  TECHNICAL_DEBT.md, AGENTS.md, CLAUDE.md, CHANGES.md — as specified
Forbidden:                Code changes; new ADR authorship; new task creation; implementation scope
Expected response format: Records confirmation listing each document updated and the specific change made
```

#### Lane C — implementation

```
Pass type:                implementation
Change Type:              implementation
Workflow Path:            Path A (default) or Path B (if architect declares APPROVED)
Execution unit:           [defined in brief]
Deliverable:              Working code + paired tests; all three gates passing
Stop condition:           Gate 1 clean + Gate 2 clean + Gate 3 green; records pass separate (§27)
Allowed:                  Code changes within declared scope; test authorship; targeted test runs during implementation
Forbidden:                Scope creep; records closure within implementation pass unless architect declares Bundled
Expected response format: Implementation summary with gate output + test count delta
```

#### Lane D — correction-only

```
Pass type:                correction-only
Change Type:              correction
Workflow Path:            Path A
Execution unit:           [specific defect or drift as named in brief]
Deliverable:              Corrected file(s) with root-cause fix; no new behaviour added
Stop condition:           Defect resolved; gates passing; no new scope introduced
Allowed:                  Minimal targeted fix for the named defect only
Forbidden:                Opportunistic improvements; scope expansion; records bundling unless architect declares Bundled
Expected response format: Correction summary: what was wrong, what was changed, gate confirmation
```

### Canonical Codex Delivery Format

Every Codex implementation report must use exactly this structure.
No free-form text outside this format. No exceptions.

```
DELIVERY REPORT — <T-id> — <YYYY-MM-DD>

FILES CREATED:
  ✅ <filepath> (<bytes> bytes)
  ✅ <filepath> (<bytes> bytes)

FILES MODIFIED:
  ✅ <filepath>

FILES VERIFIED ABSENT (scope exclusions):
  — <filepath> NOT touched

GATE OUTPUT:
  ruff:          [exact last line of: ruff check .]
  pytest strict: [exact last line of: pytest -q -W error::pytest.PytestWarning]
  pytest full:   [exact last 2 lines of: pytest -q]

BRANCH: claude/<name>
COMMIT: <short-hash>

ACCEPTANCE CRITERIA CHECK:
  ✅/❌ <criterion 1 — verbatim from TECHNICAL_DEBT.md brief>
  ✅/❌ <criterion 2 — verbatim from TECHNICAL_DEBT.md brief>

SELF-ASSESSMENT: COMPLETE / INCOMPLETE
  If INCOMPLETE: [exactly what is missing — file:line]
```

**Enforcement rules:**
- If any FILES CREATED entry cannot be filled → SELF-ASSESSMENT: INCOMPLETE
- If any gate is not clean → SELF-ASSESSMENT: INCOMPLETE
- INCOMPLETE report is not accepted — Records Steward returns it without action
- Branch must be `claude/*` — never `codex/*`
- Free-form text outside this structure is ignored by Records Steward

### Periodic Bounded Audit Ritual

A bounded audit pass is a structured, scope-limited read-only sweep of the codebase or a
specific subsystem. It is **trigger-based, not calendar-based**.

**Activation conditions (architect declares one):**
- After a Phase boundary close
- After a major implementation lane touching ≥4 production modules
- When the T5 register runs low on implementation candidates
- Architect discretion (must state reason in brief)

**Canonical output path:**
1. OBS entries captured in SCRATCHPAD.md
2. Architect issues DECs (per SCRATCHPAD.md review protocol)
3. Audit summary appended to the Weekly Governance Log in TECHNICAL_DEBT.md

**Scope constraint:** A bounded audit pass does not produce implementation tasks directly.
All findings route through SCRATCHPAD.md → architect DEC → TECHNICAL_DEBT.md entry. No
implementation begins during or immediately after an audit pass without a separate architect brief.

---

## §24 Bounded Execution Unit Rule

For any aggregate or multi-step lane, the architect brief must explicitly declare:

1. **Exact execution unit** for this pass (which deliverable, which sub-step, or which scope slice)
2. **Pass type** (audit / implementation / records / closure)
3. **Closure rule** (whether the parent task remains OPEN after this pass or becomes closure-capable)
4. **Required canonical doc update** (which document must reflect the outcome of this pass)

If any of the four declarations is absent: **DoR FAIL** — architect clarification is required before implementation begins. The implementer does not select the scope slice independently.

---

## §25 Environment First Rule

For tasks with elevated environment or dependency risk — CI-heavy lanes, multi-module integration, or any task explicitly flagged by the architect — before any implementation begins:

1. Confirm `scripts/setup_env.sh` completed successfully.
2. Verify all critical imports resolve without error.
3. Run the full gate suite once from a clean state (Gate 1: `ruff check .`; Gate 2: `python -m pytest -q -W error::pytest.PytestWarning`; Gate 3: `python -m pytest -q`).

This separates environment drift from code regression. If the clean-state gate run fails: **stop, report as environment issue, do not begin implementation**.

---

## §26 No Mixed-Pass Rule

A single Codex pass may execute only **one** of the following pass types:

- **audit** — read-only analysis, no document or code changes
- **implementation** — code changes, with or without paired tests
- **records** — document updates only (TECHNICAL_DEBT.md, AGENTS.md, CLAUDE.md, CHANGES.md)
- **closure** — formal closure declaration with all required canonical doc updates

Combining two pass types in a single pass is permitted **only** when the architect brief explicitly names the two pass types being combined and states the reason. The `Change Type:` field (§19) must match the declared pass type. A pass that drifts into a second type without explicit architect authorisation is a process violation equivalent in severity to scope creep.

---

## §27 Canonical Records Separation Rule

For **heavy tasks** (as defined in §12.1), the records pass is separate from the implementation pass **by default**.

The architect brief must declare one of:
- **Bundled** — records closure is permitted within the implementation pass (explicit reason required)
- **Separated** — records pass follows as a distinct subsequent pass

If neither is declared: records pass is assumed separate. A Codex implementation report for a heavy task that contains closure language — without an explicit architect bundling declaration — is a process violation.

---

## §28 — Architect Role Distribution (effective 2026-03-17)

Claude Code acts as both engineer and architect for all routine operations.
Claude (chat) retains architect authority only for:
- ADR authorship and acceptance
- New debt item registration (DEC decisions)
- Phase open/close declarations
- Sequencing changes that affect multiple items

For all other operations — records passes, gate verification, delivery
reports, module ceiling updates, status closures — Claude Code operates
autonomously under existing AGENTS.md governance rules without requiring
chat architect approval.

Rationale: Live repo access eliminates the latency and PDF-snapshot
ambiguity of the chat-based review loop for routine operations.

---

## Opus QA Trigger Policy

Opus QA is **not triggered by default**. Path A items proceed without Opus involvement unless the architect explicitly opts a task into Path B.

### Trigger criteria (architect must state one of the following)

- The task modifies or adds governance safety logic.
- The task changes a science engine that feeds the 7-gate decision pipeline.
- The task adds or alters a threshold constant with governance-facing output.
- The architect explicitly writes `APPROVED` in the PILOT-01 entry for the task.

### Non-trigger cases (Opus is NOT invoked)

- Threshold centralisation tasks (e.g., T5-17 pattern): no new logic, only import wiring.
- Documentation-only or records-steward passes.
- Audit-only handoffs (read-only tasks with no code changes).
- Debt-only items with no Codex implementation handoff.
- Any Path A item where the architect has not written `APPROVED`.

### Finding taxonomy — Category A / Category B (ADR-0049, Accepted 2026-03-15)

Opus QA findings are classified as one of two categories:

| Category | Definition |
|---|---|
| **A — machine-checkable** | Deterministic check: given this input, assert this property holds. No semantic judgment required. The check either passes or fails reproducibly. Belongs in CI (pytest), not in Opus QA. |
| **B — judgment-required** | Requires understanding of the task's acceptance criteria, architectural intent, failure modes, or test design appropriateness. A test runner cannot make this call. Belongs in Opus QA. |

**Migration policy (ADR-0049 §2.2):** A Category A finding that appears in any Opus QA verdict is evidence of a CI gap. The correct resolution is to write a CI test (T5-37), not to re-check the same pattern in future Opus reviews. As Category A patterns migrate to CI, Opus QA scope contracts to Category B only.

**Validating test requirement (ADR-0049 §2.3):** Every CI gate created to replace a Category A Opus finding must have a paired meta-test confirming the gate fires on known-bad input (T5-38). No CI gate is written without its meta-test.

**Multi-pattern migration lane rule (ADR-0049 §7):** Multi-pattern migration lanes (T5-37 / T5-38 pattern) use the **Hybrid Sequential Model**: audit pass first → sequential migration units (one pattern at a time) → single final closure. No child GitHub issues are created for individual migration units before the audit pass is complete. No migration unit begins before the audit pass is recorded. T5-37 and T5-38 remain OPEN until all migration units on the finalized list are complete.

### Scope of Opus QA review (Category B — judgment-required only)

Opus reviews **test quality** for the newly written or changed behaviour:
- Are the tests correctly targeted at the acceptance criteria?
- Do the tests cover boundary conditions specified in the task brief?
- Are there gaps that would allow a regression to pass undetected?
- Is the test design appropriate to prevent the specific failure modes the task addresses?
- Are parametrize / property-based tests used where the input space warrants it?

### Out of scope for Opus QA

- Re-running mandatory gates (Gates 1–3 are always run by Codex, not Opus).
- Architectural decisions or new ADR authorship.
- Code style or formatting (covered by ruff Gate 1).
- Performance benchmarking.
- **Category A (machine-checkable) patterns that have been migrated to CI gates under T5-37.** Once a pattern has a CI test, Opus does not re-check it.

### Verdict semantics

- **QA PASS** — test coverage is adequate for the acceptance criteria; implementation may advance to Gate 3.
- **QA FAIL** — one or more specific gaps identified; Codex must address the listed gaps and resubmit.

### Cooldown rule

If Opus issued **QA FAIL** for a task and Codex returns after fixing the identified gaps, **Opus is automatically re-invoked** for that task without requiring a new architect trigger. The re-invocation covers only the gaps listed in the original QA FAIL verdict.

---

*Last updated: 2026-03-17 — Architect Role Distribution pass (records + policy): §28 Architect Role Distribution added (Claude Code autonomous authority for routine operations; Claude chat retains ADR authorship, DEC decisions, phase open/close, sequencing changes). Change Type: records + policy. Previous: Friday Governance Pass records update (records-only): §23 Canonical Codex Handoff Template added (canonical handoff template, four fixed lane templates, periodic bounded audit ritual); existing §23–§26 renumbered to §24–§27 accordingly. Change Type: records-only. Previous: 2026-03-16 — Phase 8B Governance Pass (policy-only): §24 Bounded Execution Unit Rule, §25 Environment First Rule, §26 No Mixed-Pass Rule, §27 Canonical Records Separation Rule (formerly §23–§26). Change Type: policy-only. Previous: Architect Decision Execution Pass (T5-37/T5-38 Closure Model): Multi-pattern migration lane rule added to Opus QA Trigger Policy (ADR-0049 §7 Hybrid Sequential Model: audit pass → sequential migration units → single final closure; no child GitHub issues before audit pass; no mid-lane closure). Previous: T5-11 Path B Closure + Opus QA Scope Reduction Records Pass: Opus QA scope section updated with Category A / Category B finding taxonomy (ADR-0049 Accepted 2026-03-15); deterministic-to-CI migration policy added (Category A findings migrate to CI gates under T5-37; validating meta-test requirement per T5-38; ADR-0049 §2.2–2.3); Opus QA out-of-scope list updated: migrated Category A patterns explicitly excluded after T5-37 completion. Trigger policy unchanged — no additional trigger criteria added or removed. Previous: Records/Governance Update Pass: §20 Mini Drift Postmortem Rule refined (postmortem NOT required for every corrective pass — required only on recurrence or canonical-document impact; derived-view drift requires fix only); §21 Governance Friction Principle added (new rules must replace an old rule or reduce friction — otherwise not added); §22 Friday Governance Review Output Rule added (written output required; no output = review not completed). Previous: T5-25 Records Pass: §18 Canonical Source Map added (document hierarchy + conflict resolution rule); §19 Mandatory Change-Type Field added (5 valid values + execution semantics for Phase 8+ items); §20 Mini Drift Postmortem Rule added (3-field format: Drift / Why it escaped / Guard now in place). 2026-03-09 history: §12.5 Debt-Clear Window added — mandatory periodic debt reduction rule, 5-task cadence, tier-ordered selection, enforcement signal at session start. Workflow Governance Framework — §1.1 Subsystem Ownership table added; §12.1 Task Learning field added as required resolution component; §17.2/17.3 step-1a DoR gate added; §17.5 Definition of Ready checklist added; §17.6 Bottleneck/Owner/Unblock optional metadata added; E19 DoR enforcement rule added. Proposal 3 — Explicit Handoff statuses — declined: already covered by SCRATCHPAD.md STATUS + Path A/B step model. 2026-03-08 history: E16 tightened: `TECHNICAL_DEBT.md` is sole canonical path record — message-only declaration no longer valid; §17.2/17.3 step-1 now name the `**Workflow Path:**` field explicitly. Phase 8 OPEN — §17 Phase 8 Per-Item Workflow Standard added: canonical Path A (standard) and Path B (PILOT-01 QA-assisted) sequences; E16 Path declaration rule, E17 No mid-item path switching, E18 Workflow drift process violation. Phase 7.9 history: §14 Project Safeguard Protocols added: Agent Challenge Rule §14.1, Change Justification Requirement §14.2, Cooling-Off Protocol §14.3, No Impulse Implementation Rule §14.4, Complexity Budget Rule §14.5; §2.0 Environment Setup mandatory pre-task gate added; §2.4 Optional fast iteration rule added; canonical sequence in §2 updated to include Step 0; §3.6 Documentation Edit Policy added; §10 Common Mistakes + §11 Pre-Delivery Checklist updated to 24 items; §12 Debt Register Discipline, §13 Architecture Decision Boundary, §1 role boundary hardening; §15 Engineering Scratchpad Protocol added 2026-03-07; §16 Domain-Specific Engineering Contracts added 2026-03-07 — process rules from ADR-0021, 0022, 0024, 0025, 0028, 0029, 0031, 0035, 0036, 0039, 0040 distilled here; ADR triage: 7 historical ADRs retired, 11 process ADRs moved to §16, 27 architectural ADRs remain in docs/adr/). Authoritative for all agents and engineers operating on TITAN OS.*
