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
- Run `python -m pytest -q`
- Confirm: 100% green, test count same or higher than before your change
  - Exception: if tests were renamed/moved but coverage is preserved, document it in the PR description.
- If any test fails: stop, follow Section 6, fix root cause first

**Never delete tests.** If a test is wrong, fix the test — never remove it.

---

## 1. Role Boundaries

| Role | Responsibility |
|------|---------------|
| **Architect (Claude / owner)** | System design, ADR authorship, tier ordering, scope approval |
| **Implementation Engineer (Codex / agent)** | Execution of scoped tasks only — no design decisions |

Agents must not redesign, restructure, or re-architect any system component unless explicitly instructed by the architect. When you believe a redesign is needed, write it up as an "Out of Scope Finding". Do NOT implement it as part of this task. 
---

## 2. Runtime & Git Rules

### 2.1 Environment
- Repository root: `/workspace/project-mayhem`
- Python: **3.11+** (mandatory — uses `tomllib`, UTF-8 mode PEP 686)
- Do NOT add or remove git remotes
- Do NOT fetch or push in runtime / non-push-enabled environments.
- Do NOT use `gh` CLI or call GitHub APIs from inside Codex runtime

### 2.2 Deliverable format (push-enabled environments)
- Run `python -m pytest -q` before delivering — do NOT proceed if any test fails
- You MAY create commits and push, but ONLY to branches matching `claude/*`
- You MUST NOT push to `main` or `master` — this is a hard rule, not a guideline
- You MUST NOT force push or rewrite history on any remote branch
- After pushing, open exactly one PR (base=`main`, compare=`claude/<branch>`) and paste the PR link in your response
- Commit message format: `T<tier>-<id>: <short title>` — example: `T2-08: Add startup observability`

### 2.2b Deliverable format (non-push environments — fallback only)
- Run `python -m pytest -q` before delivering
- Provide a single unified patch: `git diff` or `git diff --staged`
- Do NOT create commits. Do NOT push. Do NOT open PRs.
- Label response clearly: `[DIFF ONLY — push not available]`

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
```

A PR without a Scope Declaration will not be reviewed.

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
1. Run `python -m pytest -q` (full suite — canonical, deterministic)
2. Confirm zero failures, zero new errors
3. Confirm test count is same or higher than before your change
   - Exception: if tests were renamed/moved but coverage is preserved, document it in the PR description.
4. If any test fails: follow the protocol below before doing anything else

### 6.2 🔴 RED — Assertion / runtime error

Respond **verbatim** before doing anything:

```
A test is failing.
1) Run the full suite and identify the FIRST failing test.
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

### 6.4 🟣 PURPLE — Dependency / import error (collection failure)

Respond **verbatim** before doing anything:

```
A test fails during collection (import error).
1) Confirm full dependency installation:
   pip install -r requirements.txt -c constraints.txt
2) Verify the missing module: python -c "import <module>"
3) Fix dependency resolution only.
4) Do not modify application logic.
5) Re-run full suite.
```

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

---

## 7. Stop-the-Line Protocol

If any acceptance criterion fails mid-task:
1. **Stop immediately.** Do not continue to other files or subsystems.
2. Report what failed and the root cause.
3. Fix only the specific failing criterion.
4. Re-run the acceptance gate from scratch.
5. Only then continue.

---

## 8. Architecture Constraints (Do Not Break)

| Pattern | Location | Why it must not change |
|---|---|---|
| Governance gate ordering | `governance_engine.py` → Step 9 of `DailyCoach` | Non-bypassable safety; altering order corrupts coaching decisions |
| CTL/ATL chronological rebuild | `garmin_sync.py` + `database.py` | Oldest-first EMA; reversing gives wrong fitness values |
| SQLite WAL + busy_timeout + write lock | `database.py` | Thread-safety across 3 daemon threads |
| Idempotent additive migrations | `database.py _run_migrations()` | Safe to run on every startup; breaking idempotency causes schema corruption |
| Thresholds from `thresholds.py` only | All science modules | Single source of truth; hardcoding duplicates diverge silently on recalibration |
| ML kill-switch default-ON | All Phase 7 engines | Correct failure mode; never remove or invert |
| Evidence labels on ML payloads | Phase 7 engines | Provenance discipline; do not remove |

**`titan/science/governance_engine.py` is architecture-locked.** See ADR-0009.
Do not modify it without an ADR reference in your commit message and explicit architect approval.

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
| `docs/adr/` | Architecture Decision Records (0001–0014) |
| `docs/ROADMAP.MD` | Phase history (Phases 0–7 CLOSED) |
| `pyproject.toml` | pytest + ruff + mypy config |

---

## 10. Common Mistakes — Do Not Repeat

| Mistake | Consequence |
|---|---|
| Shipping a change without creating or updating tests | Silent regression guarantee |
| Fixing multiple subsystems in one pass | Partial work delivered as "done"; debt reaccumulates |
| Skipping `ruff check` / `pytest` binary gate | Incomplete fix shipped |
| Broad `except Exception: pass` left in place | Silent data loss in governance inputs (T1-02, T1-03) |
| Hardcoding thresholds instead of importing from `thresholds.py` | Values diverge on recalibration (T1-04) |
| Modifying `governance_engine.py` without ADR | Silent safety regression (ADR-0009) |
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
[ ] ruff check <changed_paths>  → zero findings
[ ] python -m pytest -q         → 100% green, count same or higher
[ ] I created or updated tests for every changed public function.    ← MANDATORY, NO EXCEPTIONS
[ ] I did NOT modify governance_engine.py without an ADR reference.
[ ] I did NOT hardcode any threshold (used thresholds.py).
[ ] Out-of-scope findings are in TECHNICAL_DEBT.md, not in code.
[ ] I pushed to a claude/* branch only — NOT to main or master.
[ ] I opened exactly one PR and pasted the PR link in my response.
[ ] My PR description contains a Scope Declaration (Section 3.3).
```

---

*Last updated: 2026-03-04. Authoritative for all agents and engineers operating on TITAN OS.*
