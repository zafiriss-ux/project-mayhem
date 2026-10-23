# AGENTS.md — TITAN OS Engineering Contract

> Governs every AI agent and human engineer on this codebase. Rules are non-negotiable.
> Deviations are bugs in the engineering process, not acceptable trade-offs.

**Revision:** 2026-10-23 r6 (documents reconciled with the code after the MA/OW/P4 audits, ADR-0070)
**Governing contract:** TITAN Operating Contract v7.9 (document revision r3)

**Contract relationship.** v7.9 constrains LLM patch behavior. This document is the canonical
home of everything v7.9 §13 SCOPE BOUNDARY delegates: operational invariants, runtime contracts,
infrastructure, release/DR, observability, and engineering enforcement. Conflict resolution
follows the single total order in v7.9 §1.3 (safety-invariant/clearance → contract; patch-level
LLM behavior → contract; runtime/infrastructure/code-quality → this document; residual → the
stricter constraint). This document wins over all derived views and summaries. Later sections
amend earlier ones; §31 is an index of reconciliations, not a competing text. Cross-document
citations are always document-qualified ("v7.9 §1.2" / "AGENTS §1.2") — both documents carry
low-numbered subsections and an unqualified number is ambiguous (v7.9 §1.3; lint L7).

**Lane naming (binding).** The implementation lane defined by §HARD GATE + §2 + §17 **is the
"Sonnet Code lane" referenced by v7.9 §9C.** "Codex", "Implementation Engineer", "Claude Code
(implementer)", and "Sonnet Code" name the same role in this document.

**ID namespaces (binding).** `INV-nn` = invariant (§8.3). `RE/DR/RBP/MPC-nn` = §8.9–§8.12
contracts. `RP-n` = Architect Reserved Powers (§1.2). `T-PRA-nn` = TECHNICAL_DEBT items from
§30. `B-n`, `K:PRA-nn`, `C-n`, `D-n`, `E-n`, `F-n`, `G-n` = findings native to
`docs/audit/PRODUCTION_READINESS_AUDIT_2026-06-10.md`. `SA:*` = findings native to the
Consolidated Static Audit. **`T-PRA-nn` (debt) and `K:PRA-nn` (audit item) are unrelated
numberings — never cross-cite them by number alone.**

---

## ⚠️ ABSOLUTE RULE — TESTS (Read First, Apply Always)

**What:** Every task ships tests for its changed behaviour — no exceptions.
- No test file for the changed module → create the mirrored file
  (`titan/<path>/<module>.py` → `tests/titan/<path>/test_<module>.py`; follow nearest existing convention).
- Test file exists → update it to cover the new/changed behaviour.
- Minimum per changed public function: one happy-path test + one boundary/error-path test.
- **Never delete tests.** A wrong test is fixed, not removed.
- `pytest.mark.skip`/`xfail` require a documented justification **including a debt-id**.
  Deferred-TDD placeholders MUST be `xfail(strict=True)` tied to the debt item — a bare
  `pytest.skip("not yet implemented")` passes CI forever and is forbidden. [D-6, T-PRA-36]

**Why:** A task without tests for its behaviour is incomplete by definition; silent regression is guaranteed.

**Verify:** Gates 2–3 below; reviewer confirms mirrored test exists and count is same-or-higher.

---

## 🚫 HARD GATE — NO COMMIT / NO PR BEFORE GREEN

**This gate is absolute. It applies to every commit of every Change Type (§19) — implementation,
records-only, policy-only, correction. The only passes with no gate are passes that create no
commits (audit-only).**

| Gate | Command | Required result |
|---|---|---|
| 1 Lint | `ruff check .` | Exit 0, zero findings |
| 2 Strict | `python -m pytest -q -W error::pytest.PytestWarning` | 100% green, warnings are failures |
| 3 Full | `python -m pytest -q` | 100% green, count same or higher |

**Canonical CI entrypoint (binding — fulfills v7.9 §9, §9C, §12):**
- `scripts/titan_ci.sh` runs exactly Gates 1→2→3 in order, aborts on first failure, exits with the
  failing stage's captured exit code. It is the entrypoint named by v7.9 §9 (`VERIFY:`), §9C, §12.
  Per v7.9 §9C, **this section is the canonical gate definition (the Sonnet Code lane).** Gate 1
  includes `scripts/governance_lint.py` (checks L1–L9, §2.4; T-PRA-37) once it lands.
- `scripts/titan_check.sh` MUST be identical to, or a thin `exec` wrapper of, `scripts/titan_ci.sh`.
  Divergence in gate content is a GATE VIOLATION.
- EXECUTION-mode responses set `VERIFY: bash scripts/titan_ci.sh`, `VERIFY_EXIT: 0`. Only an
  orchestrator-captured execution of `scripts/titan_ci.sh` — recorded as a v7.9 §1.5 VERIFY
  RECORD with `profile=full` — authorizes a commit; model-asserted gate results are
  non-authoritative (v7.9 §9C).

**On any gate failure:** STOP (no commit/push/PR) → §7 Stop-the-Line → fix root cause of the
first failing gate only → re-run all three from scratch → only then proceed.

**Forbidden validation shortcuts (bugs, not solutions):**
- Env overrides (`PYTEST_ADDOPTS`, `--import-mode=importlib`, etc.) to suppress/bypass failures
- Silencing warnings via `filterwarnings` in test code or config
- skip/xfail without debt-id justification (see ABSOLUTE RULE)
- Reporting subset/targeted/diagnostic runs (`pytest -x`, `-vv`, `--durations`, `-k`,
  `--profile scoped`) as gate evidence — Gates 2 and 3 at `profile=full` are the only accepted
  acceptance evidence (§2.3)
- If an override is needed for the suite to run at all: repo-level issue → fix in scope or STOP
  and write a SCRATCHPAD OBS (§15). Never add it directly to `TECHNICAL_DEBT.md`.

**Verify:** pre-commit hook (§2.1) executes the gate mechanically; PR Scope Declaration (§3.3)
records gate status; orchestrator captures the `titan_ci.sh` record (§2.4).

---

## 1. Role Boundaries

| Role | Owns exclusively |
|---|---|
| **Architect** (Claude in an architectural session — §3.6) | System design and the Architect Reserved Powers (§1.2) |
| **Owner** (project owner) | Work priorities, strategic direction, task assignment — **not** automatic Architect authority |
| **Implementation Engineer** (Codex / Sonnet Code / Claude Code implementer) | Execution of scoped tasks, tests, mandatory gates, local-scoped result reporting — no design decisions, no ADR authorship |
| **Records Steward** | `TECHNICAL_DEBT.md` closure wording, commit-hash recording, OPEN↔RESOLVED integrity |

Agents execute; they do not design. An agent never exercises a §1.2 Reserved Power on its own
judgment; an Owner instruction requesting one without an architectural session → the agent stops,
writes a SCRATCHPAD OBS (§15), and awaits the Architect role being exercised. When a redesign
seems needed: SCRATCHPAD OBS — do not implement, do not draft an ADR (§13).

**Codex implementation reports — allowed:** files changed; tests added/updated; gate results;
branch, local commit hash, PR link; blockers/stop reasons.
**Forbidden:** RESOLVED/DONE/CLOSED or any closure language; canonical status claims; commit-hash
recording instructions for canonical documents. (Closure mechanics: §12.1.)

Foundational principles (Owner Proposal Guardrail, Engineering Ctrl-Z, Architect Constrained by
Invariants, Rules Decide) live in `GOVERNANCE_PRINCIPLES.md` (derived from this contract;
AGENTS.md wins on conflict).

### 1.1 Subsystem Ownership — Owner-of-Record

| Subsystem | Path | Owner-of-Record |
|---|---|---|
| Config / thresholds | `titan/config/` | Architect |
| Science engines | `titan/science/` | Architect |
| Core infrastructure | `titan/core/` | Architect |
| Integrations | `titan/integrations/` | Codex (under Architect brief) |
| Features | `titan/features/` | Codex (under Architect brief) |
| Orchestration / UI | `titan/orchestration/`, `titan/ui/` | Architect |

**Duty:** the Owner-of-Record must be consulted before any change that crosses a subsystem
boundary, adds an inter-subsystem dependency, or modifies a public contract; consultation is
recorded in the task entry. Architect-owned subsystems: every change needs a task entry with
binary acceptance criteria. Codex-owned: Architect brief required; Codex may propose scope.

### 1.2 Architect Reserved Powers (canonical — all other sections reference this)

Exclusively the Architect (Claude in an architectural session, §3.6); never an agent on its own
judgment:

  RP-1  ADR authorship / amendment / acceptance
  RP-2  Governance gate logic (`governance_engine.py` gates, gate ordering)
  RP-3  Schema topology (new/removed tables, normalization, FK-graph or query-pattern-altering
        indexes); the §13.3 additive-column carve-out is the only agent-permitted schema change
  RP-4  Tier / phase sequencing and phase open/close
  RP-5  New module boundaries, packages, or abstraction layers
  RP-6  DEC decisions and new TECHNICAL_DEBT registration
  RP-7  AGENTS.md and TITAN Operating Contract content (§3.6; contract per v7.9 §1.4)
  RP-8  Module-ceiling VALUES (§16.11; agents may apply the mechanical test-constant edit only
        after the Architect confirms the value)
  RP-9  Any clearance verdict constrained by v7.9 §14
  RP-10 Scope approval, escalation decisions, governance interpretation

Choosing between design alternatives on agent judgment is reserved (it reduces to RP-1/RP-5).

---

## 2. Deliverable Workflow — Canonical Sequence

### 2.0 Environment Setup — Mandatory (Run First, Every Session)

Run `scripts/setup_env.sh` before any other action. On failure: STOP, report exit code + last
output lines verbatim; no ad-hoc dependency installation unless the Architect instructs it.
Environment repair is permitted only when setup succeeded AND a dependency is still missing —
fix environment only (no app/test code), then re-run all three gates.
**Elevated-risk tasks** (CI-heavy, multi-module integration, Architect-flagged): confirm setup
success → verify critical imports → run one clean-state full gate before implementing; a failing
clean-state run is an environment issue — stop and report, do not implement. (Sole home of this
rule; ex-§25.)

### SESSION_START (mandatory — before any code change)

```bash
# Step 1 — Scratchpad gate: exit 1 = BLOCKING queue non-empty → stop, await Architect
scripts/check_scratchpad.sh
# Step 2 — Gate confirmation (all three gates green before work begins)
scripts/titan_check.sh
# Step 3 — System state summary (print all five lines)
grep -cE '🔴 OPEN|PARTIALLY RESOLVED' TECHNICAL_DEBT.md        # open debt items (status markers only)
python -m pytest --collect-only -q 2>&1 | tail -1              # current test count
ruff check . --statistics 2>&1 | tail -5                       # lint status
grep -E '^STATUS:|^Phase' SCRATCHPAD.md | head -3              # phase + scratchpad status
awk '/## Tracking Table/,0' TECHNICAL_DEBT.md | grep -c 'RESOLVED 2026' # debt-clear context (§12.5)
```

Do not implement until: scratchpad clear, gates green, state printed. Skipping this is a
PROCESS VIOLATION. This block is the frozen source for `scripts/session_start.sh` (T-PRA-35);
until that script lands, run these commands exactly.

**Sequence for every task:** setup_env → scratchpad gate → read task fully (§3.5) → code+tests →
Gate 1 → Gate 2 → Gate 3 → all green → commit (`T<tier>-<id>: <short title>`) → push → PR.
Any gate failure → STOP (§7), fix root cause, restart from Gate 1. Steps after the gates are
unreachable until all three pass.

### 2.1 Pre-Commit Enforcement

`.git/hooks/pre-commit` must run `scripts/titan_check.sh`; exit 1 blocks the commit. Source lives
in `scripts/pre-commit-hook` (`#!/bin/bash` + `exec scripts/titan_check.sh`). Re-link after every
clone: `cp scripts/pre-commit-hook .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`.

### 2.2 Deliverable & Git Rules

- Run all three gates before any commit / `make_pr`.
- Branches: `claude/*` only. **Never push to `main`/`master`. Never force-push or rewrite remote history.**
- One issue = one PR (bundling: §26.1). Every PR includes a Scope Declaration (§3.3).
- Push available → push branch, open exactly one PR (base=main), paste the PR link.
- Push unavailable → stop after local commit; report branch + hash; Owner pushes/opens PR.
  Diff-only fallback: deliver `git diff`, label `[DIFF ONLY — push not available]`, no commits.

### 2.3 Targeted Runs Are Diagnostic Only

During implementation, targeted runs (`pytest tests/...py -q`, `ruff check path/`, and
`scripts/titan_ci.sh --profile scoped` — changed-scope selection, T-PRA-38) are permitted for
iteration speed. They never substitute for Gates 1–3 and never appear as acceptance evidence in
a delivery report. Acceptance, commit authorization, and FIXED dispositions require
`profile=full` evidence (v7.9 §1.5). Full gates are mandatory before every commit/PR and after
every fix cycle. Note: the repo enforces a global coverage threshold — a subset run failing only
on coverage is a diagnostic artifact, not a regression; acceptance always uses Gate 3.

### 2.4 Orchestrator & Evidence Obligations

The orchestrator (the human or harness driving a contract-governed session) is a governed
component. Its obligations:

1. **Evidence emission.** Every captured `scripts/titan_ci.sh` execution is recorded into
   context as a v7.9 §1.5 VERIFY RECORD, including `profile` and the environment fingerprint
   from `scripts/env_fingerprint.sh` (python version + venv hash + host id; T-PRA-38). The LLM
   never composes records (v7.9 §12).
2. **Clearance completeness.** A session in which a clearance verdict may issue over scope S
   includes the current §30 register (or its excerpt covering S). The register is the
   completeness manifest; without it the LLM treats clearance as unavailable and restates
   findings (v7.9 §14).
3. **Governance ledger.** Append one JSONL line per patch attempt, REJECT, escalation, retry,
   mode use, and disposition to `docs/governance/ledger.jsonl` (fields: ts, session, mode,
   patch-id, reject-code|null, escalate-code|null, disposition-type|null). Consumed by the
   §16.11 / §21 / §22 reviews and lint summaries (T-PRA-39).

A session lacking (1) or (2) still proceeds for ordinary work; it cannot mint commits or
clearance verdicts — fail-closed on evidence, not on progress.

---

## 3. Scope Control

**3.1 Allowed:** modify only files named in the task; touch additional files only when strictly
required for correct integration (imports, interfaces, tests, wiring, config).
**3.2 Not allowed:** refactoring unrelated code; style/formatting outside the task; architectural
redesign; comments/docstrings/type annotations outside the exact code you changed.

### 3.3 Scope Declaration (mandatory in every PR description)

```
## Scope
**Task:** T<tier>-<id> — <title>
**Files changed:** <list>
**Files NOT changed:** governance_engine.py, [other locked files]
**Tests added/modified:** <list or "none — existing coverage sufficient">
**ADR reference:** ADR-XXXX (required if governance_engine.py touched)
**Gates passed:** ruff ✅ | pytest strict ✅ | pytest full ✅
```

A PR without this block and confirmed gate status is not reviewed.

### 3.4 Out-of-Scope Findings — Canonical Routing (single statement)

Discover an issue outside scope → **do not fix it.** Write a SCRATCHPAD OBS (§15), set
`STATUS: REVIEW_REQUESTED`, continue the scoped task only. The one routing path everywhere in
this document: **SCRATCHPAD OBS → Architect DEC → `TECHNICAL_DEBT.md` entry.** Agents never add
debt entries directly. (Other sections reference this rule; none redefines it.)

**3.5 Before writing a line of code:** list every file that must change + one sentence why; if a
needed file isn't named in the task, explain the dependency before touching it.

### 3.6 Documentation Edit Policy — Hard Restriction

Documentation is **Architect-owned** (`CLAUDE.md`, `AGENTS.md`, the TITAN Operating Contract,
`README.md`, everything under `docs/`). The only permitted agent edits:

| Permitted edit | Trigger | Ref |
|---|---|---|
| Test-count snapshot in `CLAUDE.md` (via updater script) | Tests added/removed | §12.3 |
| ADR index row in `CLAUDE.md` | Integrating a new Architect-authored ADR | §12.4 |
| Debt entry body / tracking row in `TECHNICAL_DEBT.md` | Task closure (Records Steward) | §12.1 |
| New OBS / clarification append in `SCRATCHPAD.md` | Out-of-scope finding / `CLARIFICATION_NEEDED` | §15 |
| `README.md`, `docs/`, `CLAUDE.md`, `PROGRESS.md`, `DECISIONS.md`, `CHANGELOG.md` — only what the PR's own change makes untrue or incomplete | Any task PR | ADR-0061 |

Everything else is Architect-only per §1.2 (RP-7 covers this document and the operating
contract). A `policy-only` pass (§19) that touches `AGENTS.md` is executed by the Architect, or
applies verbatim Architect-authored text with the authorizing instruction quoted in the PR —
Codex never originates AGENTS.md content. Need a doc change beyond the table → SCRATCHPAD OBS
and stop.

---

## 4. Tier Ordering — Mandatory

```
TIER 1 (Data Integrity) → TIER 2 (Observability) → TIER 3 (Deps) → TIER 4 (Maintainability) → TIER 5 (Future)
```

Do NOT start Tier N+1 while any Tier N item is OPEN. **The only exemption is an item explicitly
marked `independent` in `TECHNICAL_DEBT.md`** — there is no other carve-out, including for phase
work. On receiving a higher-tier task while a lower tier is open, respond exactly:
`⛔ TIER ORDERING VIOLATION: T[N]-[XX] is still OPEN. I must complete that first.`

**4.1 T4-01 ruff burn-down order:** `titan/config/` → `titan/science/governance_*.py` →
`titan/core/` → `titan/integrations/` → `titan/orchestration/ + titan/features/` → `titan/ui/`.
No skipping, no cross-subsystem quick fixes. Per-subsystem acceptance: `ruff check <path>` exit 0
AND full suite green; otherwise answer exactly `NOT 100% — Missing: [failing check]`.

## 5. Definition of Done — Binary

✅ DONE = all acceptance criteria pass, 100%, no caveats. ❌ NOT DONE = anything else.
No "mostly done", no "should be fine".

## 6. Test Failure Protocol

Before delivering: run Gate 2, then Gate 3; confirm count same-or-higher (renames documented in
the PR). On any failure, classify and act — fix root cause, not symptom, not silence:

| Class | Symptom | First action (evidence required) | Fix target |
|---|---|---|---|
| 🔴 RED | Assertion / runtime error | `python -m pytest -x` → first failing nodeid + traceback | Code regression → fix code; test bug → fix test (only if objectively wrong); never modify a correct test |
| 🟡 YELLOW | Warnings / flaky / lint | Identify exact warning + origin | Fix call site (deprecations) / stabilise env cause; never silence globally — strict gate treats warnings as failures |
| 🟣 PURPLE | Import/collection error | `bash scripts/ci_bootstrap.sh`; `python -c "import <module>"` | Dependency resolution only — no app/test code edits |
| 🟠 ORANGE | Hang / no progress, no failure yet | `pytest -vv` (last nodeid) + `--durations=20`; reproduce the specific test with `-vv -s` | Only a deterministically hanging test gets a minimal root-cause fix |

After any fix: re-run the full suite; if other tests fail, stop and report. Do not refactor
unrelated code or introduce new behaviour. A perceived hang is not RED until a failing nodeid or
import error is proven; never loop a command without new evidence.
**Banned responses:** random refactors; mass multi-file changes; undocumented skip/xfail; global
warning suppression; env overrides to force green.

## 7. Stop-the-Line Protocol

Any acceptance criterion fails mid-task → STOP immediately; report what failed + root cause; fix
only that criterion; re-run the gate from scratch; only then continue. Every stop-the-line report
carries the class evidence from the §6 table (nodeid+traceback / warning+origin / import line /
last-nodeid+durations). "Tests failing" / "stuck" without evidence is NOT ACCEPTABLE. Never
re-run the same command without returning new evidence.

---

## 8. Architecture Constraints (Do Not Break)

| Pattern | Location | Why |
|---|---|---|
| Governance gate ordering | `governance_engine.py` → Step 9 of `DailyCoach` | Non-bypassable safety; reorder corrupts decisions |
| CTL/ATL chronological rebuild | `garmin_sync.py` + `database.py` | Oldest-first EMA; reversal gives wrong fitness |
| SQLite WAL + busy_timeout + write lock | `database.py` | Intra-process thread safety (cross-container: §8.12) |
| Idempotent versioned migrations | `database.py _run_migrations()` + `PRAGMA user_version` | Each `_apply_vN` runs exactly once; breaking idempotency corrupts schema |
| Thresholds from `thresholds.py` only | All science modules | Single source of truth (T4-19 enforced) |
| ML kill-switch default-ON; evidence labels on ML payloads | Phase 7 engines | Correct failure mode + provenance; never invert/remove |
| `PersistenceFailure` propagation | `daily_coach.py _persist_garmin_data()` | DB rollback must surface as degraded mode (ADR-0020) |
| Alerts about an athlete via `alert_operator` | Alert paths that concern a coached athlete (`titan/integrations/telegram_bot.py`) | The owner's bot sends directly; an athlete's alert goes to the athlete and to the owner's chat (D-107). Alerts only for the owner (worker-level) may call the owner bot's `send_alert`. `NotificationGateway` was deleted (ADR-0069 §7, D-139) |
| `DegradedModeTracker` registration | `run_morning_routine()` | New degraded conditions must fire the 24h SLO alert (T2-13) |
| Hard-stop key rejection is dual-layered from ONE frozenset | `ThresholdAdapter` + `DatabaseManager.save_threshold_offset` | Both reject H1–H5 from the same `frozenset`; introducing a second key source lets the layers diverge (verified-clean property — keep it) [SA] |

**`titan/science/governance_engine.py` is architecture-locked** (ADR-0009, §16.1) and
machine-enforced: `tests/test_governance_mutation.py` (T4-18, boundary-ON/OFF per gate) and
`tests/test_architectural_invariants.py` (T4-19, no inline thresholds, canonical lock codes).
Adding a gate requires: ADR reference in the commit + boundary tests + lock code added to
`CANONICAL_LOCK_CODES` (thresholds.py), `_CANONICAL_LOCK_CODES` (test), and the CLAUDE.md table.

### §8.1 Execution Priority Order (non-negotiable)

`LAYER 5 (Hard-Stops H1–H5) > LAYER 4 (Invariants INV-01→INV-25) > LAYER 3 (Governance gates)
> LAYER 2 (Fallback/degraded) > LAYER 1 (Normal output)`. Higher layer always wins; no exception
path may bypass a higher layer.

### §8.2 Severity → Mandatory Runtime Response and Enforcement Class

| Severity | Detection | Runtime response | Enforcement class |
|---|---|---|---|
| CRITICAL | Invariant check L4/L5 | BLOCK + HARD-STOP + Telegram CRITICAL | **CI gate** — invariant test fails the commit gate |
| HIGH | Pre-decision sanity gate | DEGRADE to EASY + WARNING escalation | **CI gate** |
| MEDIUM | Runtime pipeline | FALLBACK conservative | **Review-blocking** — Architect ack recorded in the PR before merge |
| LOW | Periodic audit | LOG-ONLY | **Log-only** |

Enforcement classes are exactly three plus log-only: **CI gate** (Gates 1–3 via `titan_ci.sh`),
**review-blocking** (PR cannot merge without the named review evidence), **phase-close gate**
(recorded result required at phase close, §16.3 check 5). Do not label review/phase-close
obligations "HARD GATE" — that term names the CI commit gate only.

**Violation-severity vocabulary** (maps every "X violation" phrase to a class and the §7
consequence; lint L6 rejects undefined phrases):

| Term | Class | Consequence |
|---|---|---|
| GATE VIOLATION | CI-gate | Blocks the commit; §7 Stop-the-Line |
| REVIEW VIOLATION | review-blocking | Blocks merge until the named review evidence is recorded |
| PHASE-CLOSE VIOLATION | phase-close | Phase is NOT COMPLETE (§16.3) |
| PROCESS VIOLATION | procedural | Breach of a non-gated procedural rule; resolved + recorded with a §20 mini-postmortem when it recurs or touched a canonical document |

### §8.3 Invariant Register (non-bypassable)

Any PR creating a code path that bypasses an invariant is a GATE VIOLATION. Full definitions:
§8.4–§8.14 as referenced. Verification = the named Category-A test unless marked otherwise.

| ID | Rule (summary) | Verification |
|---|---|---|
| INV-01 | `math.isfinite()` before every governance-gate float comparison | pre-existing T4-19 suite |
| INV-02 | All governance/sync `datetime` UTC-aware | pre-existing |
| INV-03 | `athlete_id` present in every per-athlete DB write | pre-existing |
| INV-04 | Per-athlete calibration isolation (ADR-0033 L3) | `tests/test_athlete_calibration_isolation.py` (T5-07-L3-B) |
| INV-05 | No governance gate defaults an absent field optimistically (ADR-0051) | pre-existing |
| INV-06 | HRV drift check on startup → WARNING + `data_confidence_low=True` past threshold | pre-existing |
| INV-07 | Activity dedup by `garmin_activity_id` (`INSERT OR IGNORE`) | pre-existing |
| INV-08 | Sync success only when no exception **and fresh data landed**; any attempt ending without fresh data — including retry/backoff/429 exhaustion — registers as a sync failure for degradation tracking and increments `garmin_sync_failure_total` [K:PRA-13, E-4] | extend sync tests (T-PRA-26) |
| INV-09 | `INSERT OR REPLACE` forbidden on multi-source tables | pre-existing |
| INV-10 | Rate-limiter key count bounded by `RATE_LIMITER_MAX_KEYS` | pre-existing |
| INV-11 | Coach routes accepting `athlete_id` use `Depends(require_coach_athlete_access)`, never role-only `require_coach`; the dependency fails closed (403) when the datastore is unavailable — assignment that cannot be verified is denied (§8.4) [B-1, SA:C-1, ADR-0054] | `tests/test_td01_td03_td05.py` (route + fail-closed coverage) |
| INV-12 | Safety-path exception handlers fail closed: governance exception → forced EASY/zone-2 + logged CRITICAL; decision-pipeline exception → caught at the coaching_pipeline boundary, fail-safe alert, no silent death (§8.5) [B-4, SA:m-1/m-2] | `tests/test_fail_closed_exception_paths.py` |

**New-code gate (any new governance/safety/auth path):** (a) fail-closed exception test (INV-12);
(b) assignment-scoping verification if per-athlete coach access (INV-11); (c) ADR reference in the
commit if authorization topology changes.

### §8.4 Authorization Routing — INV-11

**What:** Every FastAPI route under `/coach/*` whose handler accepts `athlete_id` (path, query, or
body) uses `Depends(require_coach_athlete_access)`. `require_coach` is legal only on routes that
touch no per-athlete data. Exceptions require an Architect-approved ADR addendum. **Stub routes
are not exempt** — the live dependency on a stub is the authorization model the implementation
inherits (the exact B-1 failure).
**Why:** ADR-0054 — a coach may act only on assigned athletes; role-only checks let any coach
export/override/delete any athlete [B-1, SA:C-1].
**Verify:** `tests/test_authorization_routing.py` imports the app and asserts, for every `/coach/*`
route with `athlete_id`: assignment-scoped dependency present, role-only dependency never sole
authorization. Category A; must fail on known-bad input (T5-38 meta-test).
**v7.9 §13 backstop:** a patch replacing the scoped dependency with `require_coach` is a
safety-invariant violation → `ESCALATE: CONSTRAINT_CONFLICT` naming ADR-0054/INV-11 (§13 governs).
**Tracked improvement:** centralizing the per-route dependency choice into one policy layer
(so a developer cannot pick the weak check) is an ADR candidate noted in T-PRA-01.

### §8.5 Fail-Closed Exception Contract — INV-12 / INV-13 / INV-24

**Safety-path function:** anything that applies/evaluates a governance constraint, computes or
reads degradation state, computes data-staleness or sync-age inputs to degradation
(`hours_since_last_sync`) [SA:m-2], makes a session-intensity decision, or applies a threshold
adaptation.

**INV-12 — exceptions fail closed.** A safety-path function that raises MUST produce the MORE
restrictive outcome: about to ALLOW → DENY/REST/LOCK; computing degradation → preserve prior
degraded state; applying a constraint → apply the most conservative one; reading prior state →
treat absence as most conservative. Handlers MUST log the exception (CRITICAL or WARNING) and
never return an optimistic value — **even when the substituted sentinel is conservative
(e.g., `inf` sync-age), silent substitution is a violation: log it.** Silent
`except Exception: return` in a safety path is a GATE VIOLATION equivalent to a gate bypass.
An exception inside `apply_constraints()` / hard-stop evaluation forces `session_type = EASY`
and `max_zone = 2` (the system's canonical conservative floor), logs CRITICAL, and appends
`GOVERNANCE_EXCEPTION_FAIL_CLOSED` [B-4]. **Safety-relevant methods are invoked directly, never via
`getattr(obj, "name", None)` optional dispatch** — a renamed method must fail loudly, not no-op
forever [C-6]. Enforced by a semgrep/AST rule plus removal of the existing instance (T-PRA-26
conformance sweep) — the repo already runs semgrep, so this is a rule addition, not new
infrastructure.

**INV-13 — hydration semantics (binding disambiguation).**
`DailyCoach._hydrate_from_db()`: on read **failure** → log CRITICAL, preserve any in-memory state;
with no prior state → forced `DEGRADED`. A **successful** read returning no degradation rows →
HEALTHY (cold start is not stress). The forced-conservative state MUST clear on the next
successful read (never sticky — emit structured events on enter/clear); a startup DB blip must
not pin the athlete to EASY.

**INV-24 — computed trust is enforced.** When the data-trust arbitration yields
`overall_trust = INVALID` (or below the configured threshold), the coaching decision MUST clamp
to REST/EASY through the same mechanism as staleness. A verdict that is computed, logged, and
ignored is forbidden [B-14]. Verify: `tests/test_data_trust_enforcement.py` injects an INVALID
verdict and asserts the clamp.

**Verify (INV-12/13):** `tests/test_fail_closed_exception_paths.py` injects exceptions into each
safety-path function and asserts the restrictive outcome + emitted log/event.

### §8.6 Worker State Durability & Crash Safety — INV-15 / INV-17

**Why:** the worker can die at any time (`restart: unless-stopped` guarantees the restart);
in-memory idempotency/authorization state replays the morning routine and clears replay
protection — poisoning `governance_outcomes`, the calibration data source [B-3, B-5].

**Authority:** creating `worker_routine_executions` and `telegram_override_nonces` is a
**schema-topology change** — Architect-gated (RP-3; §13.3 + §14.2 + ADR), introduced via §13.4
Stage-1 mechanics. The "additive column" permission never covers new tables.

**INV-15 binding semantics:** durable table `worker_routine_executions`, PRIMARY KEY
`(athlete_id, execution_date, routine_type)` (athlete_id per §16.10 A40-4), with
`started_at`/`completed_at` markers. Before any routine: `INSERT`; unique-constraint hit on a
completed row → skip (idempotent). An incomplete row (`completed_at` NULL, crash before delivery)
resumes on the same UTC day, at most 3 attempts: a decision already in `governance_outcomes` is
re-sent, not recomputed, so that table is never written twice for one athlete and day
(ADR-0067 D8). On completion: `UPDATE completed_at`. On startup: reconstruct today's state from
this table — never from a dict. **Full DDL is owned by the authorizing ADR (T-PRA-03
deliverable); this section binds keys and semantics only** — schema topology is ADR territory
per §13.3, and a second DDL copy here is a guaranteed drift pair.

**INV-17 binding semantics:** durable table `telegram_override_nonces` keyed on `nonce`,
carrying `command_type`, `athlete_id`, `issued_at`, `consumed_at`, `expires_at`. Expiry and
replay checks (`expires_at < now()`, `consumed_at IS NOT NULL`) are **in-query**, not application
logic (no TOCTOU). Nonces bind to the decision/command they authorize [F-3]. Startup may prune
expired nonces; unconsumed unexpired nonces remain valid. DDL: authorizing ADR (T-PRA-03).

**Verify:** `tests/test_worker_state_durability.py` simulates restart (fresh instance, no carried
memory) and asserts dedup + nonce behavior; `governance_outcomes` is never double-written on
restart (couples to §16.7).

### §8.7 Database Integrity — INV-14 / INV-18 / INV-25

**INV-14 — FK enforcement with mandatory safe rollout.** Every `DatabaseManager`
connection executes `PRAGMA foreign_keys = ON` immediately after open, before any operation, on
every connection; `_run_migrations` asserts FK is active before applying migrations. **Blind
enablement is forbidden** — the production DB carries known drift (`'default'`/`'owner'` across
v7–v18; `degraded_mode_state` never backfilled — the v18 backfill covered `training_log` only
[B-9]). Ordered, separately-PR'd sequence (each Tier 1):
1. **Reconcile** (Stage-2 migration): normalize `athlete_id` to `TITAN_DEFAULT_ATHLETE_ID` across
   **all per-athlete tables explicitly including `degraded_mode_state`**, repair/delete orphans,
   add the `data_source` CHECK constraint [I-13]. No pragma change yet.
2. **Verify clean:** the migration ends with `PRAGMA foreign_key_check;` asserted to return
   **zero rows**, plus a zero-rows query for any non-canonical `athlete_id`. Non-empty → abort.
3. **Enable** (Stage 3): connection factory issues the pragma only when
   `PRAGMA user_version >= FK_ENABLE_VERSION` (older environments not bricked).
4. The pragma is a no-op inside a transaction — issue it on a fresh connection before `BEGIN`.
Enabling without a recorded green step-2 check is a GATE VIOLATION (the INV-14 test fails the gate).
**Verify:** `tests/test_db_integrity.py::test_foreign_keys_enforced` uses a known-bad FK
relationship from the real schema (not synthetic) and expects `IntegrityError`.

**INV-18 — canonical athlete-id.** New code references `TITAN_DEFAULT_ATHLETE_ID`
(`titan/config/settings.py`). Literals `'default'`/`'owner'` are banned in new code except:
migration files (`migrations/versions/*` history) and fixtures testing the migration-era drift —
plus the two §16.10-sanctioned forms (column `DEFAULT 'default'`, signature
`athlete_id: str = "default"`). Verify: AST check in `test_architectural_invariants.py`.

**INV-25 — schema-version forward guard [B-8].** At startup/connect:
`if user_version > SCHEMA_VERSION: raise` (process exits non-zero). Without this, a rolled-back
binary silently miswrites a newer schema — the rollback path (RE-03, §13.4 downgrade) is
incomplete without it. Verify: T-PRA-04 extension opens a DB stamped `SCHEMA_VERSION + 1` and
asserts refusal.

### §8.8 Worker Observability — INV-19 / INV-21

**The gap (stated to evidence, no over-claim):** `titan-api` exposes `/metrics` [F-13 correction];
**no scrape/alerting stack exists yet**, and `titan-worker` — where the morning routine, Garmin
sync, and governance run — exposes nothing. SLO.md targets are currently measured by nothing
[E-2, E-3, SA:m-4].

**Canonical metrics contract (single source — all names final, all registered per INV-19a):**

| Metric | Type | Incremented / set |
|---|---|---|
| `worker_cycle_error_total` | Counter | Unhandled exception in worker daemon loop |
| `coaching_routine_executed_total{athlete_id}` | Counter | Morning routine completes |
| `garmin_sync_success_total` | Counter | Sync lands fresh data without exception (INV-08) |
| `garmin_sync_failure_total{error_type}` | Counter | Any failed/exhausted sync attempt incl. 429 exhaustion (INV-08) |
| `degraded_mode_active` | Gauge | 1 while any athlete degraded |
| `governance_outcome_written_total` | Counter | Each `governance_outcomes` write |
| `worker_thread_died_total{thread}` | Counter | Watchdog detects supervised thread death (INV-23) |
| `audit_write_failure_total{surface}` | Counter | Failed durable audit write, api or worker (INV-22) |
| `backup_failure_total` | Counter | Failed backup run (DR-02) |

**INV-19a (CI):** the worker registers every collector above at import time —
`tests/test_worker_observability.py` asserts each name in the `MetricsCollector` registry; pure
unit, no live Prometheus. **INV-19b (phase-close):** with the Architect-selected transport in
force (own `/metrics` endpoint, Pushgateway, or API-scraped shared file — selection recorded as a
GATING ADR addendum before T-PRA-05 starts), all metrics are queryable while the worker runs;
recorded at phase close per §16.3 check 5, absence = phase NOT COMPLETE. The transport is the
only free choice; observability of the named metrics is not.

**Alert routing [E-3]:** every alert-class condition is emitted as a structured event with
`severity`, and the ones that must reach a person are sent directly by the worker: through `alert_operator`
when they concern a coached athlete, or the owner bot's `send_alert` when only the owner needs
them (ADR-0069 §7). JSON log lines that nothing routes do not satisfy any alerting
requirement. Open gap: `slo_alert` events are still log lines only (P4-09).

**INV-21 — chain verified end-to-end:** Garmin failure → `DegradedModeTracker` → CRITICAL alert →
`alert_operator` Telegram send. Test `tests/test_degradation_alert_chain.py` (Category B, mocks
allowed, full chain mandatory) does not exist yet (T-PRA-10); the parts are covered by
`tests/test_degraded_tracker_persistence.py` and `tests/test_missing_input_alert_p4_01.py`. Note the chain's entry condition is INV-08: if retry exhaustion never registers as
failure, the chain never starts — that is the audited first-incident path [M-1 chain].

### §8.9 Release Engineering — RE-01..06

Enforcement class: phase-close gate (§16.3 check 5) unless a CI test is named. Why: no versioned
artifacts = no answer to "what is running?" and no rollback [B-7]; unscanned supply chain ships
vulnerabilities for up to a week [B-12].

- **RE-01** Version sourced from `pyproject.toml` at runtime
  (`importlib.metadata.version("titan-os")`); no hardcoded `"0.1.0"` literals.
  **Verify (CI):** `tests/test_release_engineering.py` asserts runtime version == package
  metadata and no version literal in `titan/` (T-PRA-09).
- **RE-02** Every production deployment originates from a git tag `v<MAJOR>.<MINOR>.<PATCH>`;
  untagged commits are never deployed. (`git tag -a v<x> -m "Release v<x>" <hash> && git push origin v<x>`)
- **RE-03** `docs/RUNBOOK_ROLLBACK.md` exists and defines: prior-tag identification; image/tag
  rollback; success verification command; data rollback strategy (Alembic downgrade, §13.4
  downgrade routine, or backup restore — state which). **Tested at each phase boundary against
  staging; result recorded** (§16.3). An untested runbook is not a rollback path.
- **RE-04** Production compose references registry-pinned image tags
  (`image: registry…/titan-api:vX.Y.Z`), never `build: .`.
- **RE-05** Scan cadence: CodeQL runs on PR/push (not weekly-only); gitleaks scans the full pushed
  range (not `HEAD~1..HEAD`) [B-12, F-11]. **Verify (CI-config check):** workflow files assert the
  triggers (T-PRA-27).
- **RE-06** Release artifacts ship with SBOM + image scan (e.g., Trivy); dependency pins are
  parity-checked between `pyproject.toml` and `requirements.txt`; every `pip-audit` CVE ignore
  carries an expiry date — permanent ignores are forbidden [F-12] (T-PRA-27).

### §8.10 Disaster Recovery — DR-01..04

Why: backups on the DB volume + untested restores = total loss on one disk failure — the
highest-value fix per unit cost in the audit [B-6, M-4].

- **DR-01** Backups written off-volume: separate Docker volume, S3-compatible store, or remote
  filesystem on separate hardware. Same-volume backup is a PHASE-CLOSE VIOLATION (DR-01 is
  verified at §16.3 check 5).
- **DR-02** Retention via `.env`: `BACKUP_RETENTION_DAILY_DAYS=7`, `BACKUP_RETENTION_WEEKLY_COUNT=4`.
  Every backup run executes `PRAGMA integrity_check` on the produced artifact [I-7]; success logs
  INFO with size, failure logs CRITICAL + increments `backup_failure_total`. The verify job runs
  against the **latest real backup**, never a toy fixture DB [B-6].
- **DR-03** Restore verification at every phase close: copy latest backup → open → run
  `python -m pytest tests/ -k db_integrity -v` → confirm `PRAGMA user_version` matches source →
  record the result. A phase close without a restore result is NOT COMPLETE. An untested backup
  is not a backup.
- **DR-04** `docs/RUNBOOK_DR.md` declares RPO, RTO, responsible party, escalation path,
  verification command. Single-athlete minimums (Architect-set defaults — revise via ADR; the
  audit evidence establishes only that they must exist): RPO ≤ 24h, RTO ≤ 4h; if the current
  procedure cannot meet them, the gap is a Tier-1 debt entry.

### §8.11 Request Boundary Protection — RBP-01..05

- **RBP-01** Maximum request body size enforced in middleware before body parsing → HTTP 413.
  Default `API_MAX_BODY_SIZE_BYTES = 1_048_576` (`.env`-configurable). Enforce via Content-Length
  pre-check **plus** a streamed-read cap (chunked requests without Content-Length are still
  bounded). Why: unauthenticated memory exhaustion + bcrypt over unbounded passwords [B-13].
  **Verify:** `tests/test_request_boundary.py` (T-PRA-11) sends oversized → asserts 413.
- **RBP-02 (= INV-16 behavioral form).** Unconfigured trust = lockout, never open access:
  `_is_trusted()` returns `False` and logs CRITICAL (`titan.telegram.no_trusted_chat_configured`)
  whenever no trusted chat id is configured; strict equality otherwise. Implementation shape
  lives in the fix PR and `tests/test_telegram_auth.py`, not here.
- **RBP-03** Rate-limiter eviction is LRU under `RATE_LIMITER_MAX_KEYS` — arbitrary eviction lets
  anonymous flooding displace known actors' state [B-13].
- **RBP-04** Required key material — JWT keys, and `TITAN_GARTH_TOKEN_KEY` whenever Garmin
  token storage is enabled — is validated at app construction/import and startup **fails** on
  invalid/absent keys; never deferred to the lifespan hook, never silently optional
  [F-4, F-10] (T-PRA-28).
- **RBP-05** Uniform authentication failure responses (no 423-vs-401 account-existence oracle);
  lockout keyed on hybrid IP+username; CSRF cookie set `HttpOnly` (the body copy serves clients)
  [F-5, F-7] (T-PRA-28).

### §8.12 Multi-Process Consistency — MPC-01 / MPC-02 / INV-20

**MPC-01** The `DatabaseManager` `RLock` is **intra-process only**; `titan-api` and `titan-worker`
are separate processes sharing one SQLite file — cross-container safety rests solely on WAL +
`busy_timeout` (`DB_BUSY_TIMEOUT_MS` in `thresholds.py`, recommended 5000; never hardcoded).
Any comment/doc attributing cross-container safety to the RLock violates v7.9 §12 (capability
over-claim) [B-10].

**MPC-02 — single-replica deployment invariant.** Until ADR-0044 (PostgreSQL) executes, the
supported topology is exactly **one API replica + one worker**: rate-limiter state, degradation
counters, scheduler state, and nonce caches are process-local by design, and a second replica
silently breaks all four [G-2]. A compose-topology assertion (no `deploy.replicas` > 1; exactly
one worker service) makes this mechanically checkable — in T-PRA-14's scope, so the rule
satisfies §21(b) rather than standing as prose. Horizontal scale-out is gated on ADR-0044, whose
**execution date is an open Architect scheduling decision** recorded in `TECHNICAL_DEBT.md`
(T-PRA-14) — the audit verdict: it "needs a date, not just acceptance" [C-1, G-1].

**INV-20** `busy_timeout` expiry (`SQLITE_BUSY` / "database is locked") is caught at the
`DatabaseManager` write boundary and re-raised as `PersistenceFailure` (ADR-0020) — never
swallowed or merely logged — so cross-container collisions surface as degraded mode, not silent
data loss.

### §8.13 Transactional Auditability — INV-22

**What:** Every authorized state-changing surface — `/coach/overrides`, `/coach/notes`, any
future authorized mutation, **and Telegram-initiated state changes (`/sync`, `/manual_entry`,
`/override`, `/today`, `/injury`, `/agree`, `/stop`)** — writes its audit record (1) **durably** and
(2) **ordered before the externally visible effect**. Audit-write failure → the action fails
closed (HTTP 5xx / command rejected, no mutation) and emits `audit_write_failure_total` at
CRITICAL. Best-effort post-response auditing is forbidden.
**Why:** the most authorization-sensitive actions are exactly the B-1 routes; an override whose
audit record can vanish makes ADR-0042's "first-class audit" fiction and disputes unresolvable
[B-11, F-8].
**Verify:** `tests/test_audit_durability.py` (T-PRA-21) injects an audit-store failure on a
mutating route and asserts: no state change, failure status, metric emitted.
**Export and delete** no longer have HTTP routes (D-097). They run from the command line, which
writes its own audit record: `python scripts/athletes.py export <id> [--out FILE]`,
`python scripts/athletes.py remove <id> [--yes]`, `purge-expired`, `reapply-deletions`; the worker
re-applies deletions at start and on every round.

### §8.14 Worker Liveness & Watchdog — INV-23

1. **Compose healthcheck:** `docker-compose.yml` defines `healthcheck:` for `titan-worker`,
   driven by a heartbeat the worker writes (DB row or file) each cycle. **Heartbeat absence
   beyond 2× the cycle interval is itself the unhealthy condition** (the worker's silence is the
   alert) — orchestrator restarts/alerts [E-2].
2. **Thread watchdog:** every long-lived daemon thread (Telegram poller, `CoachingScheduler`
   loop) is supervised; on death → CRITICAL structured event + `worker_thread_died_total{thread}`,
   then restart the thread or exit non-zero so the healthcheck takes over. Silent thread death is
   forbidden [B-15].
3. **Callback isolation:** scheduler per-athlete callbacks are wrapped — a raising callback is
   logged + metered and the loop continues for other athletes [SA:m-3].
4. **Singleton-lock recovery:** the `flock` single-instance lock has stale-lock/PID recovery — a
   dead holder's lock never permanently wedges the worker [B-3].
5. **Resource limits & log rotation:** `titan-worker` SHOULD declare memory/CPU limits and rotate
   container logs; observed state is **recorded in the phase-close entry** (§16.3 check 5).

**Verify:** `tests/test_worker_liveness.py` (T-PRA-22) asserts watchdog registration per declared
daemon thread and that simulated thread death produces the event + metric. Compose `healthcheck:`
presence and the limits/rotation observation are §16.3 check-5 phase-close items.

---

## 9. Key Files Quick Reference

| File | Purpose |
|---|---|
| `CLAUDE.md` | Project overview / orientation (not authoritative for live state — §18) |
| `TECHNICAL_DEBT.md` | Tiered debt register — consult before every task |
| `titan/config/thresholds.py` | Single source of truth for safety constants + `CANONICAL_LOCK_CODES` |
| `titan/config/evidence_registry.py` | Parameter provenance (STRONG / MODERATE / HEURISTIC) |
| `titan/science/governance_engine.py` | 7-gate safety system — **architecture-locked** (ADR-0009, §16.1) |
| `titan/orchestration/daily_coach.py` | Morning-routine orchestration; `DegradedModeTracker`; `PersistenceFailure` |
| `titan/integrations/telegram_bot.py` | `_is_trusted()` fail-closed (INV-16 / RBP-02); `alert_operator`, the alert path for a coached athlete (§16.6) |
| `titan/api/dependencies.py` | `require_coach` vs `require_coach_athlete_access` (INV-11) |
| `titan/api/main.py` | App factory — `/coach/*` routes use assignment-scoped deps; audit middleware (INV-22) |
| `titan/core/database.py` | `DatabaseManager` — FK rollout (INV-14), version guard (INV-25), busy_timeout (INV-20), RLock boundary (§8.12) |
| `titan/worker/__init__.py` | Worker daemon — DB-persisted dedup (INV-15), heartbeat/watchdog (INV-23) |
| `scripts/titan_ci.sh`, `scripts/governance_lint.py`, `scripts/env_fingerprint.sh` | Canonical gate; governance-document sensors L1–L9 (T-PRA-37); environment fingerprint for v7.9 §1.5 records (T-PRA-38) |
| `docs/governance/ledger.jsonl` | Governance telemetry (§2.4; T-PRA-39) |
| `tests/test_governance_mutation.py` / `tests/test_architectural_invariants.py` | Gate-boundary + structural invariant enforcement (T4-18/T4-19) |
| `tests/test_authorization_routing.py`, `tests/test_fail_closed_exception_paths.py`, `tests/test_worker_state_durability.py`, `tests/test_db_integrity.py`, `tests/test_worker_observability.py`, `tests/test_degradation_alert_chain.py`, `tests/test_audit_durability.py`, `tests/test_worker_liveness.py`, `tests/test_data_trust_enforcement.py`, `tests/test_request_boundary.py`, `tests/test_release_engineering.py` | INV-11..25 / RBP / RE Category-A enforcement (T-PRA series) |
| `docs/RUNBOOK_ROLLBACK.md`, `docs/RUNBOOK_DR.md` | RE-03 / DR-04 — must exist, must be exercised |
| `docs/audit/PRODUCTION_READINESS_AUDIT_2026-06-10.md` | Evidence record for §30 dispositions |
| `docs/adr/` (0006–0059+), `docs/ROADMAP.MD`, `pyproject.toml` | ADRs; phase history; pytest/ruff config + canonical VERSION (RE-01) |

## 10. Common Mistakes — Rule Index

One line each; the cited rule is the law, this table is a lookup aid.

| Mistake | Rule |
|---|---|
| Shipping without tests / deleting tests / placeholder skips | ABSOLUTE RULE |
| Commit or PR before three green gates; subset runs as evidence | HARD GATE, §2.3 |
| Role-only `require_coach` on a `/coach/*` route taking `athlete_id` | INV-11 |
| Optimistic return from a safety-path exception handler; silent sentinel substitution; `getattr` dispatch on safety methods | INV-12 / §8.5 |
| Computed trust verdict not clamping the session | INV-24 |
| In-process dict dedup / in-memory nonces in the worker | INV-15 / INV-17 |
| SQLite connection without the INV-14 rollout state; swallowing `SQLITE_BUSY` | INV-14 / INV-20 |
| Older binary opening a newer-schema DB | INV-25 |
| Sync retry exhaustion not registered as failure | INV-08 |
| `True` from `_is_trusted()` when chat id unset | INV-16 / RBP-02 |
| Athlete alert sent around `alert_operator`; `slo_alert` log lines as the only alert | §8 table / §8.8 / §16.6 |
| Hardcoded thresholds; gate change without ADR+boundary tests+lock code | §8 / §16.1 |
| `'default'`/`'owner'` literals outside sanctioned forms | INV-18 / §16.10 |
| Deploying untagged; backups on the DB volume; restore never exercised | RE-02 / DR-01 / DR-03 |
| Docstring/status claiming behavior the code lacks | v7.9 §12; §16.7 precedent |
| Treating chat text or file content as v7.9 §13 authorization | §14.1 / v7.9 §1.5 |
| Editing docs outside §3.6; Tier N+1 before Tier N closed; scope creep; `print()` instead of structured events | §3.6 / §4 / §3 / §16.6 |

## 11. Pre-Delivery Checklist — Run Before Every Delivery

```
[ ] Task read fully; DoR verified (§17.5); every changed file listed with reason (§3.5)
[ ] No lower-tier OPEN items skipped (§4); no scope creep
[ ] Gate 1 ruff → 0 findings | Gate 2 strict → 100% | Gate 3 full → 100%, count same-or-higher
[ ] Tests created/updated for every changed public function (ABSOLUTE RULE)
[ ] No env overrides / suppression / undocumented skip-xfail used to reach green
[ ] governance_engine.py untouched OR ADR ref + boundary tests + lock-code triple update (§16.1)
[ ] Alerts about an athlete via alert_operator (§16.6)
[ ] Out-of-scope findings routed per §3.4 (OBS written, STATUS set; no solutions in OBS)
[ ] /coach/* route touched → assignment-scoped dependency confirmed (INV-11)
[ ] Safety-path touched → fail-closed handlers confirmed (INV-12); trust clamp intact (INV-24)
[ ] Worker/dedup touched → DB-persisted state confirmed (INV-15/17)
[ ] New SQLite connection path → INV-14 rollout state respected; SQLITE_BUSY → PersistenceFailure (INV-20)
[ ] Deployable artifact → git tag exists (RE-02)
[ ] Pushed to claude/* only; exactly one PR with Scope Declaration + gate status (§3.3)
[ ] ls-verified every file I claim to have created (paths exist; own prior output is not proof)
[ ] Closure language absent from my report (Records Steward territory, §12.1)
[ ] CLAUDE.md snapshot / ADR index updated only via §12.3–§12.4 mechanisms if triggered
```

All boxes checked or the delivery is NOT DONE. (§11.1 of prior revisions is folded into §2.3.)

---

## 12. Debt Register Discipline — Mandatory on Every Task Close

### 12.1 On task closure

**Role split:** Codex delivers implementation evidence only (files, tests, gate results, branch,
local hash, blockers) — never RESOLVED/DONE/CLOSED language. The **Records Steward** performs all
canonical closure after **remote verification** (push completed, commit confirmed on remote):
1. Debt entry: heading `🔴 OPEN` → `✅ RESOLVED <date>`; `**Status:**` line gains date + short
   hash; `**Problem:**` → `**Original state (pre-fix):**` (past tense); add `**Resolution:**`
   and a required `**Task learning:**` block (1–3 sentences of non-obvious insight, or
   `No new engineering insight — routine implementation.`).
2. Tracking table row → `✅ RESOLVED` + date. Both updates required; one without the other is incomplete.

**Verify-first invariant:** no hash is recorded in any canonical document before remote
verification succeeds. If verification fails: report branch + local hash, stop; an unverified
candidate hash is never reused.

**Heavy tasks** (≥4 production modules, OR ≥2 of {orchestration, governance, output} surfaces,
OR implementation+canonical-record risk in one pass, OR Architect-flagged): before Steward
handoff Codex confirms (1) implementation exists at the claimed location, (2) all three gates
green in the current run, (3) remote state verified. Any unconfirmed → evidence-only delivery,
closure deferred. Non-push environments: always evidence-only; closure deferred to the Steward.

### 12.2 On out-of-scope finding
Apply §3.4 (the single routing rule). Debt entries are created only after an Architect DEC.

### 12.3 When test count changes — sensor, not memory
The `CLAUDE.md` historical-snapshot line is **generated/updated by the repo updater script**
(target: `scripts/update_claude_snapshot.py`, T-PRA-35) from the final Gate-3 run and verified by
`tests/test_claude_md_integrity.py` (T4-22). Agents run the script; hand-typed counts are the
audited drift source [D-1, K:PRA-16] and are forbidden once the script lands. Until then: update
the line from the final `pytest -q` count in the same commit and expect T4-22 to verify it.

### 12.4 When a new ADR is written
ADR authorship is Architect-only (RP-1). Integrating agent adds the ADR row to the CLAUDE.md
Key Architectural Decisions table, matching existing row format exactly.

### 12.5 Debt-Clear Window
Every 5 task closes (counted from tracking-table close dates), the Architect schedules ≥1 debt
item — lowest open tier, unblocked — before any new feature/phase work. Counter resets when a
debt item resolves; it is **derived from the tracking table** (close dates since the last
debt-item close), printed at SESSION_START (Step-3 final line) — never tracked from memory.
If all OPEN items are blocked, the window suspends; the Architect notes the suspension in the
task assignment. Why: a register that only grows is a governance failure, not a backlog.

---

## 13. Architecture Decision Boundary — Hard Prohibition

### 13.1 Prohibited without explicit Architect approval
Exercising any §1.2 Reserved Power (RP-1..RP-10). §13.3 lists what is NOT architectural.

### 13.2 When a task requires an architectural decision
STOP before writing code past the point. Report: the exact choice, the options (listed, none
chosen), each option's architectural implication. Wait for explicit approval. Simultaneously
write the §15 T-SCRATCHPAD-5 OBS. The correct response to architectural ambiguity is always
**stop and ask**, never proceed-and-explain. (Contract-lane form: §14.1.)

### 13.3 NOT architectural (proceed without approval)
Additive column to an existing table via the versioned migration pattern (nullable or
default-valued; structure/relationships/query patterns unchanged); new method within a class's
existing responsibility; tests; constants in `thresholds.py`/`evidence_registry.py`; structured
log events on the existing pattern; bug fixes within existing contracts. **The additive-column
permission never covers a new table, rename, or any topology change** — when in doubt, stop and ask.

### 13.4 Staged Schema Change Protocol
Three stages, each a separate PR, never combined:
- **Stage 1 — Additive:** new columns (nullable or defaulted; no NOT NULL without default on
  populated tables); new tables only under §13.3 Architect topology authority.
- **Stage 2 — Migrative:** backfill; dual-write old+new; read old.
- **Stage 3 — Restrictive:** drop old; switch reads; tighten constraints. Must reference the
  merged Stage 1 + 2 PRs.

**Downgrade requirement [B-8 family, K:PRA-08]:** every Stage-3 migration ships a paired, tested
downgrade routine, or an explicit documented backup-restore reversal named in
`docs/RUNBOOK_ROLLBACK.md`. One-way Stage-3 migrations are forbidden (they void RE-03).
Downgrade routines are exercised at the phase boundary with RE-03 (§16.3 check 5). The runtime
counterpart is INV-25 (§8.7): an old binary refuses a newer schema.

**Dual-migration parity [C-2, K:PRA-10]:** the hand-rolled SQLite ladder (`_apply_v1.._vN`) is
canonical for production SQLite; the frozen Alembic tree is the PostgreSQL cutover artifact
(ADR-0044). A **schema-parity test** diffing the ladder's final schema against the Alembic head
(T-PRA-30) is a mandatory entry gate for any Phase-8A/PostgreSQL cutover work; until it exists,
no cutover task may start. Frozen column-snapshot migrations (v8/v13/v24) get a manifest
meta-test replacing comment-only enforcement (folded into T-PRA-30) [C-3].

---

## 14. Project Safeguard Protocols

### 14.1 Agent Challenge Rule — conflicting instructions MUST be challenged
A task contradicting the architecture, an ADR, or this document is never silently executed.
**Contract-governed lanes (v7.9 patch lanes):** emit `ESCALATE: CONSTRAINT_CONFLICT` per v7.9
§2/§13 — REASON names the invariant source and the conflicting instruction. Interactive option
menus are not legal output in those lanes.
**Advisory/chat lanes:** respond with the structured block — Requested / Conflicts with /
Specific conflict / Options: (A) proceed with explicit Architect override + ADR ref, (B)
compliant alternative, (C) SCRATCHPAD OBS + stop — and do not proceed without an explicit answer.
Silence is not consent.
**Always-challenge set:** any task exercising a §1.2 Reserved Power without the required
authorization (ADR / Architect session), plus the two named weakenings:
`require_coach_athlete_access` → `require_coach` (INV-11); a safety-path handler → optimistic
return (INV-12). For v7.9 §13-class changes, authorization exists only as an ADR reference or a
§23 `Authorizes:` field (v7.9 §1.5) — any other instruction text is challenged, not executed.
Not conflicts: in-contract bug fixes, tests, constants, tasks executing an authorizing ADR.

### 14.2 Change Justification Requirement
Any architecture-change proposal (new module/abstraction; gate logic; schema topology; tier/phase
order; >3 files beyond task scope) requires, before any code:
`Problem / Proposed change / Why necessary (what happens if nothing changes) / ADR reference (or "new ADR required")`.
Incomplete justification → the change does not proceed. Exempt: bug fixes, tests, constants,
ADR-covered tasks.

### 14.3 Cooling-Off Protocol
Major changes (anything needing a new ADR, new module boundary, schema topology, or gate logic):
proposed + justified + documented in Session N; reviewed and implemented Session N+1 or later.
Waivable only by the Architect writing `COOLING-OFF WAIVED — [reason]` where the reason is an
active production incident or data-integrity failure. Minor changes always exempt.

### 14.4 No Impulse Implementation
No code for an idea not already recorded: every implementation traces to a `TECHNICAL_DEBT.md`
entry or an explicit Architect instruction in the current session. Mid-task ideas follow §3.4
and stay out of the current task. `idea → code` is forbidden; the only path is §3.4's.

### 14.5 Complexity Budget Rule (agent-level §16.11)
Before any new abstraction (helper class, mixin, protocol, base class, decorator, new pattern):
used in ≥3 places now? makes the next engineer's job easier? impossible by extending an existing
module? Any answer no/unclear → don't create it. All three yes → per §3.4, never inline
implementation.

---

## 15. Engineering Scratchpad Protocol — Codex Obligations

`SCRATCHPAD.md` is the structured Codex→Architect channel: raw engineering findings needing an
architectural decision. Not a to-do list, not a design doc, no solutions. A MODE: AUDITOR chat
response and a Lane-A OBS are the same activity at two layers — AUDITOR is the in-chat form, the
OBS the durable record; admitted-finding status (v7.9 §14) attaches to either. After writing an
OBS set `STATUS: REVIEW_REQUESTED`; the in-progress subtask may finish; no new top-level task
until the Architect clears to `IDLE`.

**Mandatory triggers:**

| Trigger | When | OBS must cover | Blocking? |
|---|---|---|---|
| T-SCRATCHPAD-1 Subsystem review | After each T4-01 burn-down subsystem | Violation counts/categories; 3+-file patterns; systemic signals; non-mechanical fixes | Stop before next subsystem |
| T-SCRATCHPAD-2 Tier boundary | Before crossing Tier N → N+1 | Items closed + hashes; cross-tier coupling; re-prioritisation candidates; untracked safety risks | Stop before Tier N+1 (adds to §4, doesn't replace it) |
| T-SCRATCHPAD-3 Pattern concentration | ≥3 out-of-scope OBS in one session sharing a module/failure mode | Related OBS ids; common failure mode; blast radius; the concrete architectural question | Current task may continue; no new top-level task |
| T-SCRATCHPAD-4 Phase retrospective | A Phase declared CLOSED | Tier-1 root causes (one sentence each); findings added; untriaged items; signals the next phase's Tier-1 list is incomplete | Stop before next phase |
| T-SCRATCHPAD-5 Decision point | Every §13.2 stop | file:line; options (factual, no preference); implication of each; nearest ADR; data-integrity risk of proceeding | Per §13.2 (both required) |

**OBS rules:** one OBS per trigger event; facts only with ≥1 `file:line`; sequential never-reused
IDs; exact `SCRATCHPAD.md` format; urgency `BLOCKING` or `NON-BLOCKING` mandatory.
**Codex must not:** propose solutions/designs in OBS; duplicate open debt entries; set status to
`IDLE`/`CLEARED` (Architect-only); treat `CLEARED` as skipping future triggers; use the
scratchpad as a debt-register substitute.

---

## 16. Domain-Specific Engineering Contracts

Distilled from process ADRs (0021/0022/0024/0025/0028/0029/0031/0035/0036/0039/0040; originals
retired 2026-03-07) — this section is their canonical home.

### 16.1 Governance Evolution Protocol (ex-ADR-0021)
A PR modifying `governance_engine.py` includes all three, or it is NOT DONE: (1) ADR reference;
(2) `evidence_registry.py` diff (`_LAST_REVIEWED`, `_RATIONALE`); (3) boundary-ON and
boundary-OFF tests in `tests/test_governance_mutation.py`. The file-head comment stating this
triple requirement stays at `governance_engine.py:1`.
A multi-pass governance revision (audit ladder over this document, the operating contract, or
policy ADRs) is adopted only after (1) `governance_lint` is green on the merged text and (2) one
fresh-context conformance read — no prior pass findings in context — emitting only STATUS: CLEAN
or FINDING blocks over the merged documents. The ladder ends at convergence, not at pass count.

### 16.2 Phase Entry Gate (generic) + FMEA
**What:** No code for Phase N may be written until that phase's entry criteria — defined in
`TECHNICAL_DEBT.md § Phase N — Entry Criteria & Scope` — are all TRUE (binary), the verification
commands and results are pasted into the phase's go/no-go document under `docs/adr/`, and the
Architect signs off. A PR with Phase-N code and no signed go/no-go document is a PROCESS
VIOLATION, closed without merge. Status-grep template (correct form):
`grep -cE '🔴 OPEN|PARTIALLY RESOLVED' TECHNICAL_DEBT.md`.
**FMEA gate (mandatory, any phase — including Phase 13 and later):** a phase introducing feedback
loops, auto-calibration/self-modifying thresholds, ML stage promotion (ADR-0014), or an LLM
advisory layer is OPEN until a completed FMEA table (template `docs/templates/FMEA_TEMPLATE.md`)
covering all new components and the top-3 severity failure modes + mitigations exists in
`TECHNICAL_DEBT.md` under `## FMEA: Phase [N] — [date]`.
**History:** the Phase-8-specific criteria G1–G11 (ADR-0022) were satisfied at Phase 8 close
(2026-03-17, `docs/adr/0022-review-phase8-go.md`) and are retired from this document; G12 is the
FMEA rule above, now phase-generic.

### 16.3 Documentation Consistency (ex-ADR-0024)
- Lock codes: add to `CANONICAL_LOCK_CODES` (`thresholds.py`) + `_CANONICAL_LOCK_CODES` (test);
  T4-21 (`tests/test_documentation_consistency.py`) verifies the sets match.
- ADR index: `docs/adr/README.md` row count == ADR file count (T4-21).
- Evidence registry: every `thresholds.py` constant has an `evidence_registry.py` entry (CI).
- CLAUDE.md changes: Architect-reviewed, pass `tests/test_claude_md_integrity.py` (T4-22), diff+reason included.
- Governance documents (this file + the operating contract): `scripts/governance_lint.py`
  checks L1–L9 in Gate 1 (T-PRA-37) — section labeling/monotonicity, reference integrity,
  count consistency, revision-header ↔ changelog-head equality, RP single-sourcing, severity
  vocabulary, qualified citations, clearance hygiene, governance-mass reporting.
- **Phase-close audit-trail freshness (Records Steward, every phase boundary) — all six or the
  close is NOT COMPLETE:**
  1. CLAUDE.md test-count snapshot matches collection — **sensor: T4-22** (generator per §12.3,
     T-PRA-35). Steward action: confirm the sensor is green, never re-derive by hand.
  2. Every admitted finding from the governing audits has a §30 disposition, **and every ≥HIGH
     TRACKED disposition cites a debt item that is OPEN, Tier 1/2, with a target phase ≤ the
     next phase — or carries a fresh Architect re-disposition recorded at this close. A stale
     TRACKED reverts its finding to undispositioned (v7.9 §14). Sensor: lint L8 (T-PRA-37).**
  3. ADR status fields current (no stale `Proposed`) — **sensor: ADR-status linter (T-PRA-35
     bundle)**; manual only until it lands.
  4. README / DEPLOYMENT_GUIDE / CLAUDE.md agree on single- vs multi-athlete scope.
  5. **Operational gate records (phase-close class):** `docs/RUNBOOK_ROLLBACK.md` +
     `docs/RUNBOOK_DR.md` exist; recorded rollback-test result (RE-03) **including the Stage-3
     downgrade exercise (§13.4)**; recorded restore-verification result with `integrity_check`
     (DR-03); recorded INV-19b worker-metrics observability result; **`titan-worker`
     `healthcheck:` present in compose** + resource-limits/log-rotation observation (INV-23).
  6. Module-count ceiling: §16.11's stated value equals the T4-21 assertion — **sensor: T4-21
     extension (T-PRA-35 bundle)**.
  Checks 2/4/5 are judgment- or runtime-class and stay manual where unsensored; 1/3/6 are
  sensor-backed — at phase close the Steward confirms green sensors instead of re-deriving facts.

### 16.4 Agent Context Continuity (ex-ADR-0025)
SESSION_START (§2.0) is primary. S0 supplement: a task sourced from an advisory AI session is
checked against open/closed ADRs **before** SESSION_START proceeds. T4-22 asserts: CLAUDE.md ADR
count and module count match reality; no phase claimed CLOSED with open debt items.

### 16.5 Multi-Agent Context Protocol (ex-ADR-0029)
M1: advisors get the relevant `docs/context-snapshot.md` section + applicable ADRs; advisor
recommendations contradicting an ADR require an ADR amendment, never direct implementation.
M2: advisor-originated tasks are ADR-checked pre-code (= S0). M3: architectural decisions live
only in `docs/adr/` — chat/Slack/issue history is ephemeral; capture decisions as ADRs before
implementation. M4: contradictory agent implementations → stop both; Architect merges the
ADR-consistent one, closes the other with an ADR reference; if neither fits, a new ADR resolves
it. `scripts/generate_context_snapshot.py` (T4-28) produces the snapshot.

### 16.6 Structured Log Sustainability (ex-ADR-0031)
Every `_emit_structured_event()` carries `severity`: CRITICAL (hard stop; Telegram always),
WARNING (soft downgrade/degraded/auth failure; Telegram always), INFO (telemetry; log only),
DEBUG (high-cardinality; only at `LOG_LEVEL=DEBUG`). Omitting `severity` is a GATE VIOLATION
(T2-14). Dedup: same `(event_type, lock_code)` suppressed within `ALERT_DEDUP_WINDOW_HOURS=20`;
summary re-sent after `ALERT_PERSIST_SUMMARY_HOURS=72`. Rotation: `RotatingFileHandler`,
`LOG_MAX_BYTES=10_485_760`, `LOG_BACKUP_COUNT=5` (env-overridable). **Alert-class conditions are
emitted as structured events with severity; the worker sends the ones a person must see directly,
through `alert_operator` when they concern a coached athlete (ADR-0069 §7, D-139). A JSON log line nothing consumes satisfies no
alerting requirement** [E-3]. `slo_alert` events are not routed yet (P4-09).

### 16.7 OutcomeTracker Integrity (ex-ADR-0035)
`governance_outcomes` guardrails — never remove or bypass (corrupted calibration data is Tier 1):
(1) independence flag `decision_was_followed` (overrides excluded from calibration by default;
survivorship-bias marker column); (2) independence window —
`record_outcome()` rejects outcomes younger than `OUTCOME_INDEPENDENCE_WINDOW_DAYS=2`;
(3) calibration diversity gate (≥20% high-intensity, ≥20% easy, ≥10% HARD_STOP, else defer with
WARNING); (4) circuit breaker — `CALIBRATION_MAX_THRESHOLD_DELTA_PCT=0.10`,
`CALIBRATION_MIN_OUTCOME_COUNT=10` (constants in `thresholds.py`).
**ADR-0052 status (honest, per audit):** calibration *machinery* exists (Stages 1–4); the
adapter-bound engine is **discarded** in `coaching_pipeline.py` and `run_calibration_cycle()` is
invoked only by tests → the closed loop is **NOT wired in production**; the system runs on
conservative base thresholds (fail-safe). Acceptable interim state; describing it as a completed
loop violates v7.9 §12. Wiring: TRACKED **T-PRA-18**. Coupling: INV-15 dedup is load-bearing here —
a restart double-write corrupts the diversity-gate counts.

### 16.8 Science Model Versioning (ex-ADR-0036)
Every `titan/science/` module declares `MODULE_VERSION = "MAJOR.MINOR.PATCH"`. PATCH = bug fix,
same outputs; MINOR = backward-compatible optional parameter (CHANGES.md entry); MAJOR = same
inputs/different outputs or gate-semantic threshold change → **ADR required** + calibration-data
validity statement (migration/reset plan if invalid) + `model_calibration_metadata.schema_version`
bump + `science_model_breaking_change` event at next startup + `algorithm_version_snapshot`
populated in `governance_outcomes` at decision time. CI: `tests/test_science_model_versions.py`
(T4-30) asserts presence + valid semver.

### 16.9 Metric Lifecycle (ex-ADR-0039)
States: Active (consumed by a gate/output/console — maintain in evidence registry), Under Review
(computed, role unclear — Architect review within one phase), Deprecated (remove from
computation, archive history, update registry; only after ≥1 full phase Under Review with
confirmed no downstream dependency, documented in CHANGES.md). **New-metric gate (hard):**
evidence-registry entry + explicit governance consumer + a test asserting the metric is consumed.
Phase boundary: Architect classifies all Under Review metrics; proposes ≥1 deprecation per phase
when count > 20.

### 16.10 Athlete Identity Invariant (ex-ADR-0040; new code from 2026-03-06)
**Canonical value: `'default'`, exposed as `TITAN_DEFAULT_ATHLETE_ID`.**
- A40-1: new DB access methods accept `athlete_id: str = "default"` in the signature.
- A40-2: new cross-athlete calibration defaults annotated
  `# ADR-0040: single-athlete default; per-athlete in the multi-athlete activation phase`.
- A40-3: new athlete-data test fixtures set an explicit `athlete_id` (e.g. `"test_athlete_01"`).
- A40-4: new per-athlete tables/columns include `athlete_id TEXT NOT NULL` with **no DEFAULT**; an
insert without `athlete_id` fails (ADR-0067 D3). Columns created before ADR-0067 keep
`DEFAULT 'default'` (or the recorded `'owner'` drift).
The literal `'default'` is permitted **only** in the A40-1 signature form and the pre-ADR-0067 A40-4 DDL form;
everywhere else use the constant (INV-18). **Recorded drift:** `persistence.py` read methods were
standardized on `athlete_id: str = "owner"` (ADR-0033-L3-D, 2026-04-17) — that value conflicts
with the canonical `'default'` and is normalized as part of the INV-14 reconciliation migration
(T-PRA-04 scope) [B-9]. Exempt single-athlete modules carry the module-level
ADR-0040-SINGLE-ATHLETE-SHORTCUT comment (phase reference per §16.12 register, not a hardcoded
phase number). CI: `tests/test_athlete_isolation_invariant.py` (T4-31).

### 16.11 Complexity Budget (ex-ADR-0028)
The `titan/` module ceiling is enforced by
`tests/test_documentation_consistency.py::test_module_count_within_budget`; **the asserted value
in that test is canonical, and this section MUST state that exact number** (§16.3 check-6 sensor).
Stated ceiling: **90** (the test constant; 89 of 90 used with the 12 subpackages, D-139).
The 71 and 80 of earlier records are stale; the test assertion governs. Raising the
ceiling: T4-27-C protocol — the Architect confirms the new value in the task's acceptance criteria
**before** implementation (RP-8); the test constant updates in the same commit; retroactive
corrections are PROCESS VIOLATIONS. ADR retirement at phase close (`Superseded by [NNNN]`, never
deleted). Phase-boundary Simplicity Review: documented answer to "what can be merged/simplified/
removed without losing capability" citing the current lint L9 governance-mass line; a phase that
raises total mass states which rule was evaluated for retirement and why it stays.

### 16.12 Phase Status Register (authoritative; update on every open/close)

| Phase | Status | Date |
|---|---|---|
| 0–7.9 | CLOSED | 2026-03-08 |
| 8 | CLOSED | 2026-03-17 (ADR-0022 sign-off) |
| 9–11 | CLOSED | 2026-04-20 |
| 12 | CLOSED | 2026-04-27 (close audit PASS) |
| 13 | OPEN | 2026-04-28 — entry criteria in `TECHNICAL_DEBT.md §Phase 13` |

Inline "Phase N" mentions in rule bodies are **historical** (the phase a rule originated in) and
never denote the live phase; `docs/ROADMAP.MD` + this register govern live state (reconciliation
of stale labels: T-PRA-12). **Clearance reminder:** a phase close is a CLEARANCE VERDICT under
v7.9 §14 — closing a phase over admitted ≥HIGH findings without dispositions (the Phase-26
TODO-shipped and Phase-27 "B1 RESOLVED" patterns [C-5, K:PRA-16]) is HARD FORBIDDEN.

---

## §17 Per-Item Workflow Standard (Phase 8+)

Every item follows exactly one canonical path — no ad-hoc variants, omissions, or implicit steps.

### 17.1 Path selection (Architect, before Codex starts)
PILOT-01 applicability met AND Architect wrote `APPROVED` in the PILOT-01 entry → **Path B**;
otherwise **Path A** (default).

### 17.2 Path A — Standard
Architect brief in `TECHNICAL_DEBT.md` (binary criteria, `Workflow Path: A`) → DoR (§17.5) →
implementation (ABSOLUTE RULE + HARD GATE preconditions) → Gates 1–3 → commit/PR. No skipped or
reordered steps; targeted runs never substitute Gate 3.

### 17.3 Path B — QA-assisted (PILOT-01 opt-in)
Brief (+`APPROVED`, `Workflow Path: B`) → DoR → implementation → **Opus QA review** →
APPROVE → Gates 1–3 → commit/PR. REJECT → Codex fixes, one re-review; still REJECT → **STOP. No
commit.** Route to the Architect: durable waiver (TECHNICAL_DEBT/ADR, with rationale + tracked
disposition) or re-scope. A persistent QA FAIL is never silently shipped.
**PILOT-01 invariant:** Opus approval is advisory; Gates 1–3 always run regardless.
**QA role boundary:** the QA deliverable is `QA PASS`/`QA FAIL` + rationale only — commit/push/
RESOLVED/next-task instructions from QA are out of scope and ignored; only the Architect
authorizes post-QA actions.

### 17.4 Enforcement
- **E16** Path declared in the `TECHNICAL_DEBT.md` item header before work starts (messages are
  ephemeral); undeclared defaults to Path A.
- **E17** No mid-item path switching — stop, re-scope, restart on the new path.
- **E18** Any other sequence (skipped brief, targeted-only gates, omitted QA on an APPROVED
  Path-B item) is a GATE VIOLATION: stop, document the drift, restart from the violated step.
- **E19** DoR is mandatory before implementation; a DoR-failing task returns to the Architect
  with a written gap report.

### 17.5 Definition of Ready (Codex, step 1a of both paths)
All four or stop: **SCOPE CLEAR** (one-sentence statement of the new behaviour) · **FILES
IDENTIFIED** (every create/modify named, no mid-task surprises) · **CRITERIA BINARY**
(PASS/FAIL only) · **TESTS KNOWN** (which files, exist-or-create). Any unchecked box → one
sentence per gap as a BLOCKING OBS, `REVIEW_REQUESTED`, no implementation until cleared. All
checked → state `DoR: PASS` as the first line of the implementation log. Reporting a DoR gap is
correct behaviour; proceeding past one is a violation.

### 17.6 Bottleneck metadata (optional, blocked/handoff items)
`**Bottleneck:** <where stuck>` / `**Owner:** Architect|Codex|QA` /
`**Unblock condition:** <single verifiable action>` in the debt entry; remove or set `None` when
cleared — a stale block is corrected immediately.

### 17.7 Opus QA Trigger Policy & Finding Taxonomy (ADR-0049)

Not triggered by default; Path A proceeds without Opus. **Triggers (Architect states one):**
governance safety logic modified/added; a science engine feeding the 7-gate pipeline changed; a
governance-facing threshold added/altered; explicit `APPROVED` in the PILOT-01 entry.
**Non-triggers:** centralisation-only wiring; records/doc passes; audit-only; debt-only without
implementation handoff; any Path A item lacking `APPROVED`.

**Finding taxonomy (ADR-0049):** Category A = machine-checkable → belongs in CI, never re-checked
by Opus; any Category-A finding in an Opus verdict is evidence of a CI gap → write the CI test
(T5-37) with a paired known-bad meta-test (T5-38). Category B = judgment-required → Opus scope.
Multi-pattern migration lanes use the Hybrid Sequential Model (ADR-0049 §7): audit pass →
sequential one-pattern units → single final closure; no child issues or units before the audit
pass is recorded; T5-37/38 stay OPEN until the finalized list completes.

**Opus reviews (Category B only):** tests targeted at acceptance criteria; boundary coverage per
brief; regression-passable gaps; failure-mode-appropriate design; parametrize/property use where
warranted. **Out of scope:** re-running Gates 1–3; architecture/ADRs; style (ruff); performance;
migrated Category-A patterns. **Verdicts:** `QA PASS` (advance to gates) / `QA FAIL` (listed gaps;
Codex fixes; auto re-invocation covering only the listed gaps — no new trigger needed). Persistent
FAIL handling: §17.3.

---

## §18 Canonical Source Map

| Category | Canonical source | Other sources |
|---|---|---|
| Task status, sequencing, open/closed state | `TECHNICAL_DEBT.md` | All else = snapshots |
| Process rules, workflow, enforcement | **`AGENTS.md`** (this document) | `CLAUDE.md` rules section = index; AGENTS.md wins |
| Architecture decisions | `docs/adr/` | CLAUDE.md ADR index = summary |
| Backend interface contract (SQLite/PostgreSQL parity) | `docs/PARITY_MATRIX.md` | Inline notes = summaries |
| Orientation, snapshots, module inventory | `CLAUDE.md` | Read-only; not authoritative for live state |
| Patch-level LLM behavior | TITAN Operating Contract v7.9 — Architect-owned (RP-7); revised via the governance-authoring lane (v7.9 §1.1) and landed as a `policy-only` pass | This doc = runtime/infra invariants; v7.9 = patch behavior |
| Audit findings + dispositions | §30 (dispositions); `docs/audit/…2026-06-10.md` + Consolidated Static Audit (evidence) | — |
| Governance telemetry | `docs/governance/ledger.jsonl` (§2.4) | Lint L9 summaries = derived |
| Governance principles / hardening framework | `GOVERNANCE_PRINCIPLES.md`, `TITAN_HARDENING_FRAMEWORK_v1.md` | **Derived/historical** — extracted from or superseded by this document; AGENTS.md wins |
| Weekly Governance Log, handoff blocks, session summaries | Derived operational views | Corrected to canonical sources at next records pass |

**v7.9 delegation (non-negotiable):** v7.9 §13 SCOPE BOUNDARY assigns durability, idempotency,
FK enforcement, backups, DR, release engineering, observability, and multi-process consistency to
AGENTS.md / TECHNICAL_DEBT. §8.4–§8.14 and §30 are the canonical fulfillment of that delegation.
Nothing here duplicates v7.9 normatively; v7.9 pointers in this document are orientation only.

## §19 Mandatory Change-Type Field (Phase 8+)

Every new item carries `Change Type:` in its `TECHNICAL_DEBT.md` header at brief time:

| Value | Meaning | Gate rule |
|---|---|---|
| `implementation` | Code/tests change | Full HARD GATE (Path A/B) |
| `records-only` | Canonical-document updates, no production code | **Full HARD GATE** — every commit runs `titan_ci.sh` (the hook enforces it); commit prefix `records:` |
| `policy-only` | AGENTS.md / operating-contract / process docs only — Architect-executed or verbatim Architect text (§3.6) | **Full HARD GATE** |
| `architect-decision` | ADR/design artefacts, no Codex handoff | Gates apply iff a code artefact is produced |
| `audit-only` | Read-only assessment; no file changes | No commits → no gates |

One gate, every commit; there are no per-Change-Type carve-outs. Backfill of `Change Type:` on
old items only when the Architect explicitly orders it.

## §20 Mini Drift Postmortem Rule
When a resolved process violation (a) recurs, or (b) touched a canonical document, the resolving
record includes: `Drift / Why it escaped / Guard now in place` (one sentence each). Single-shot
derived-view fixes need no postmortem. Purpose: convert process gaps into durable guards.

## §21 Governance Friction Principle
A new governance rule — in this document, the operating contract, or the invariant/register
namespaces (INV, RP, T-PRA, §30) — is accepted only if it (a) replaces an existing rule (net
count not up) or (b) measurably reduces manual synchronisation/ambiguity with a mechanically
verifiable form. The introducing record states which. Lint L9 reports governance mass (normative
lines + rule count per namespace); the §16.11 Simplicity Review cites it. (Applies from
2026-03-15; §8.4–§8.14 + §30 qualify under (b) — each converts an audited absent invariant into
a verifiable rule.)

## §22 Friday Governance Review Output Rule
Every Friday Governance Review appends a written entry to the `TECHNICAL_DEBT.md` Weekly
Governance Log (template there); "State: healthy — no changes" suffices. No written entry = the
review did not happen and may not be cited. First item each phase: the ledger's per-mode and
per-code usage counts (§2.4) — a wire construct (mode, field, REJECT code) with zero legitimate
use across a full phase is a retirement candidate routed per §3.4. A §23.1 bounded audit's
summary is recorded here; the weekly entry is the lighter health check.

## §23 Canonical Handoff & Delivery

### Handoff template (required for every Architect→Codex pass; absent field = DoR FAIL — request clarification, never infer)

```
Pass type:                <audit | records | implementation | correction-only>
Change Type:              <per §19>
Workflow Path:            <Path A | Path B | N/A>
Execution unit:           <exact deliverable / scope slice for this pass>
Deliverable:              <specific output>
Stop condition:           <success criteria terminating the pass>
Closure rule:             <parent task stays OPEN | becomes closure-capable>      [ex-§24]
Canonical doc update:     <which document must reflect this pass's outcome>       [ex-§24]
Authorizes:               <exact v7.9 §13-class change licensed, or ABSENT>       [v7.9 §1.5]
Allowed / Forbidden:      <explicit action lists>
Expected response format: <structured summary | OBS entries | gate output | records confirmation>
```

### Fixed lanes (citing a lane name imports its template)

| Lane | Pass type | Deliverable | Key Forbidden |
|---|---|---|---|
| A audit-only | audit (read-only) | OBS entries in SCRATCHPAD.md (`REVIEW_REQUESTED`), file:line cited, no recommendations (in-chat form: v7.9 §10 AUDITOR — see §15) | Any file change outside SCRATCHPAD.md; DECs (Architect-only) |
| B records-only | records | Specified canonical docs updated (`TECHNICAL_DEBT.md`, `CLAUDE.md`, `CHANGES.md`) | Code changes; ADR authorship; new tasks; **AGENTS.md edits (§3.6 — Architect-only)** |
| C implementation | implementation | Working code + paired tests, three gates green | Scope creep; records closure unless Architect declares Bundled |
| D correction-only | correction | Root-cause fix of the named defect, no new behaviour | Opportunistic improvements; scope expansion; unbundled records |

### Delivery report (single canonical format — all pass types; free-form text outside it is ignored)

```markdown
DELIVERY REPORT — <T-id> — <YYYY-MM-DD>

## Scope Declaration
Change type / Tasks / ADR reference / Workflow Path
Files created:   ✅ <path> (<bytes>)   ← each ls-verified; unverifiable ⇒ INCOMPLETE
Files modified:  ✅ <path>
Files verified ABSENT (scope exclusions): — <path> NOT touched

## Gate Results
| G1 ruff | <exact last line> |
| G2 strict | <exact last line> |
| G3 full | <exact last 2 lines> |
Branch: claude/<name>   Commit: <short-hash>

## Changes Summary
<one sentence per task: module + behaviour delta>

## Acceptance & Self-Assessment
✅/❌ <each criterion, verbatim from the brief>
SELF-ASSESSMENT: COMPLETE | INCOMPLETE (+ exactly what is missing, file:line)

## Task Learning
<non-obvious discovery, or "No new findings.">
```

Any missing section, unverified file claim, or non-clean gate ⇒ `INCOMPLETE`; the Records Steward
returns INCOMPLETE reports without action. Branches are `claude/*` only.

### 23.1 Periodic Bounded Audit Ritual (trigger-based, not calendar-based)
Triggers (Architect declares one): phase-boundary close; a lane touching ≥4 production modules;
T5 register low; Architect discretion (reason stated). Output path: OBS → DECs → Weekly
Governance Log summary. A bounded audit never produces implementation directly — findings route
per §3.4; implementation needs a separate brief.

## §26 No Mixed-Pass Rule
One pass = one pass type (audit | implementation | records | closure). Combining two requires the
brief to name both and state why; the `Change Type:` field matches. Drifting into a second type
unauthorized is a PROCESS VIOLATION (scope-creep class).

### §26.1 Wave Bundling Exception
Same-ADR implementation tasks may share one PR iff: all implementation-type; no schema change
(§13.4 stays separate); each task ID declared in the Scope Declaration; each task has a distinct
test section. In doubt: separate PRs. Never bundles mixed pass types.

## §27 Canonical Records Separation Rule
Heavy tasks (§12.1): records pass separate by default. The brief declares **Bundled** (reason
required) or **Separated**; undeclared = separate. Closure language in a heavy-task
implementation report without a Bundled declaration is a PROCESS VIOLATION.

## §28 — Architect Role Distribution (effective 2026-03-17)
Claude Code operates autonomously for routine operations — records passes (excluding AGENTS.md),
gate verification, delivery reports, Records-Steward closure mechanics post-remote-verification —
under existing rules. Chat-Architect-only, always: the §1.2 Reserved Powers (RP-1..RP-10); Codex
may apply the mechanical module-ceiling test-constant edit only after the Architect confirms the
value (RP-8). Conflicts with §13 / v7.9 §13 resolve by v7.9 §1.3 (this document's "stricter rule
governs" is its rule 4).

## §29 — Context Window Degradation Protocol
Signals (any one): inconsistent application of a rule within a session; references to stale file
state; closure language without gate output; report contradicting gate output. Response: STOP (no
inline patching) → SCRATCHPAD OBS ("Context degradation detected; rule/file; observed
inconsistency") → request a new session with clean handoff → no task closed until the new session
re-confirms gate output. A new session is cheaper than a corrupted baseline.

---

## §30 Production Risk Register Integration

**Purpose:** the governance bridge from the audit evidence
(`docs/audit/PRODUCTION_READINESS_AUDIT_2026-06-10.md` [B-n, K:PRA-nn, C/D/E/F/G-n] and the
Consolidated Static Audit [SA:*]) to enforcement. Every admitted finding has a disposition here;
an undispositioned admitted finding is a governance violation registered immediately.
**Admission rule:** appeared as a finding in either governing audit. The audits are the EVIDENCE
record; §30 is the DISPOSITION record. **Namespace:** rows cite source-native IDs; `T-PRA-nn`
debt IDs are unrelated to `K:PRA-nn` audit items (header note).

**Disposition vocabulary (v7.9 §14-conformant):**
- `INVARIANT:<§>` — rule exists here **and** the code fix is verified by an orchestrator-captured
  v7.9 §1.5 record (`exit=0 profile=full`) for `scripts/titan_ci.sh` after the fix.
- `INVARIANT-SPECIFIED:<§> + TRACKED:<debt-id>` — rule defined; code fix pending. Writing a rule
  ≠ resolving a finding.
- `TRACKED:<debt-id>` — registered for implementation; a TRACKED with no debt-id is itself a
  violation. **For ≥HIGH findings the cited debt item MUST be Tier 1 or 2 and name a target
  phase; otherwise TRACKED is not a legal disposition (v7.9 §14). Liveness is re-affirmed at
  every phase close (§16.3 check 2).**
- `WAIVED:<adr-ref>` — pre-existing Architect waiver only; the LLM never originates waivers.
A mapped rule must actually **detect** its finding; non-detecting mappings are v7.9 §12
over-claims.

| Source finding | Summary | Sev | Disposition | Rule / Debt |
|---|---|---|---|---|
| B-1 / SA:C-1 | Coach RBAC role-only on overrides/export/delete | CRIT | INVARIANT:§8.4 (verified PR #869) + TRACKED:T-PRA-01 (owner-bypass removal, B-1b) | INV-11 |
| B-2 | `PRAGMA foreign_keys` never enabled | CRIT | INVARIANT-SPECIFIED:§8.7 + TRACKED:T-PRA-04 (safe rollout mandatory) | INV-14 |
| B-3 | Worker replay on crash; flock without stale-lock recovery | CRIT | INVARIANT-SPECIFIED:§8.6/§8.14 + TRACKED:T-PRA-03, T-PRA-22 | INV-15, INV-23(4) |
| B-4 | `apply_constraints` fail-open + decision-pipeline silent-death on exception | CRIT | INVARIANT:§8.5 (verified PR #865) | INV-12 |
| B-5 / SA:M-1 | Telegram fail-open trust; volatile nonces | CRIT | INVARIANT-SPECIFIED:§8.11/§8.6 + TRACKED:T-PRA-02, T-PRA-03 | INV-16, INV-17 |
| B-6 | Same-volume backups; restore untested; toy verify DB | CRIT | TRACKED:T-PRA-08 (phase-close-gated) | DR-01..04 |
| B-7 | No versioned artifacts / rollback | CRIT | TRACKED:T-PRA-09 (RE-01 now CI-testable) | RE-01..04 |
| B-8 | No schema-version forward guard; forward-only migrations | HIGH | INVARIANT-SPECIFIED:§8.7 + TRACKED:T-PRA-25; §13.4 downgrade TRACKED:T-PRA-23 | INV-25, §13.4 |
| B-9 / SA-adj | `athlete_id` drift incl. `degraded_mode_state`; v18 partial backfill | HIGH | INVARIANT-SPECIFIED:§8.7 + TRACKED:T-PRA-04 (named reconcile scope; `persistence.py` `"owner"` signatures included) | INV-14 step 1, INV-18, §16.10 |
| B-10 / C-1, G-1/G-2 | Cross-process SQLite ceiling; RLock intra-process only; replica unsafety | HIGH | INVARIANT-SPECIFIED:§8.12 + TRACKED:T-PRA-14 + ADR-0044 **scheduling decision TRACKED** | MPC-01, MPC-02 |
| B-11 / F-8 | Audit log best-effort, post-response | HIGH | INVARIANT-SPECIFIED:§8.13 + TRACKED:T-PRA-21 | INV-22 |
| B-12 / F-11, F-12 / K:PRA-18 | Scan cadence (gitleaks last-commit; CodeQL weekly); SBOM/image scan/pin parity/CVE-ignore absent | HIGH | TRACKED:T-PRA-27 | RE-05, RE-06 |
| B-13 / F-6, F-7 / K:PRA-17 | No body limits; lockout enumeration; limiter eviction | HIGH | INVARIANT-SPECIFIED:§8.11 + TRACKED:T-PRA-11, T-PRA-28 | RBP-01, RBP-03, RBP-05 |
| B-14 / K:PRA-14 | Data-trust verdict computed, unenforced | HIGH | INVARIANT-SPECIFIED:§8.5 + TRACKED:T-PRA-24 | INV-24 |
| B-15 / SA:m-3 | Polling thread dies silently; no watchdog; callback not isolated | HIGH | INVARIANT-SPECIFIED:§8.14 + TRACKED:T-PRA-22 (callback isolation folded in) | INV-23 |
| F-4 | JWT key validation deferred to lifespan | MED | INVARIANT-SPECIFIED:§8.11 + TRACKED:T-PRA-28 | RBP-04 |
| F-5 | CSRF cookie not HttpOnly | MED | TRACKED:T-PRA-28 | RBP-05 |
| F-10 | `TITAN_GARTH_TOKEN_KEY` optional → plaintext Garmin tokens | MED | INVARIANT-SPECIFIED:§8.11 + TRACKED:T-PRA-28 | RBP-04 |
| SA:M-2 | Scheduler registers only `owner` under multi-athlete flag; docstring over-claims | HIGH | RESOLVED: the worker round runs every ready athlete (ADR-0067, `athlete_accounts`); T-PRA-06 closed (ADR-0070) | v7.9 §14 index |
| SA:m-1 | `_hydrate_from_db` silent swallow | MED | INVARIANT-SPECIFIED:§8.5 + TRACKED:T-PRA-02 | INV-13 |
| SA:m-2 | Sync-age collapses errors to `inf` silently | LOW | INVARIANT-SPECIFIED:§8.5 (safety-path classification) + TRACKED:T-PRA-26 | INV-12 |
| SA:m-4 / E-2 | Worker metrics dark; **no scrape/alert stack exists** [F-13 corrected] | MED | INVARIANT-SPECIFIED:§8.8 + TRACKED:T-PRA-05 | INV-19a/b |
| K:PRA-13 / E-4 | Garmin 429/retry exhaustion invisible to degradation tracker | MED | INVARIANT-SPECIFIED:§8.3 INV-08 ext + TRACKED:T-PRA-26 | INV-08 |
| E-3 | `slo_alert` events routed by nothing; alert mosaic | MED | INVARIANT-SPECIFIED:§16.6/§8.8 + TRACKED:P4-09 (T-PRA-31 superseded, D-139) | `alert_operator` |
| SA:BENIGN1/2 | Calibration loop unwired (engine discarded; write path test-only) | MED | TRACKED:T-PRA-18 (fail-safe today; §16.7 corrected) | §16.7 |
| K:PRA-15 / C-5 | EngineRegistry CS/APL cold-start TODOs shipped; Phase 26 closed over them | MED | TRACKED:T-PRA-32 + §16.12 clearance reminder | v7.9 §14 |
| SA:BENIGN3 | Diagnostic scripts hardcode wrong DB path | LOW | TRACKED:T-PRA-20 | — |
| C-3 | Frozen-snapshot migrations guarded by comments only | MED | TRACKED:T-PRA-30 (manifest meta-test folded in) | §13.4 |
| C-6 | `getattr`-optional dispatch hides dead safety features | MED | INVARIANT-SPECIFIED:§8.5 + TRACKED:T-PRA-26 (semgrep guard + removal) | INV-12 rule |
| C-7 | Module ceiling 80 (manual, stale) vs §16.11's 71 (claimed CI) | MED | TRACKED:T-PRA-12 (reconcile CLAUDE.md/audit to the enforced value; §16.3 check 6) | §16.11 |
| C-2 / K:PRA-10 | Dual migration systems, no parity test | MED | INVARIANT-SPECIFIED:§13.4 + TRACKED:T-PRA-30 (pre-8A gate) | §13.4 |
| D-2, D-4 / K:PRA-12 | Stub-only e2e; no compose/restart/concurrency test; migration chain untested on realistic data | HIGH | TRACKED:T-PRA-29, T-PRA-30 | QA contract |
| D-6 | Skip-placeholder tests pass forever | MED | INVARIANT-SPECIFIED:ABSOLUTE RULE + TRACKED:T-PRA-36 | strict-xfail rule |
| D-1 / K:PRA-16 / B-list 8 | Governance record drift: counts, "B1–B7 RESOLVED" over open B-1, ADR-0057 stale, B2/B5 untracked, scope-doc contradiction | HIGH | TRACKED:T-PRA-12 + §16.3 checks 1–4 + sensor automation TRACKED:T-PRA-35 | v7.9 §14, §12.3 |
| SA:RBAC1 | Rate-limiter eviction policy unspecified | LOW | INVARIANT:§8.11 | RBP-03 |

**Debt items this register mandates in `TECHNICAL_DEBT.md`** (Tier-1 set opens before any
non-`independent` Phase-13 implementation — §4 tier ordering applies with no other carve-out):

| Debt ID | Source | Description | Tier |
|---|---|---|---|
| T-PRA-01 | B-1 | INV-11: scoped dependency on the 3 coach routes + `test_authorization_routing.py`; note ADR candidate for centralized policy layer; B-1b: owner-bypass removal (scoped follow-up) | **1** |
| T-PRA-02 | B-5, SA:m-1 | INV-16 + INV-13 fail-closed; extend telegram auth tests + `test_fail_closed_exception_paths.py` | **1** |
| T-PRA-03 | B-3, B-5 | INV-15 + INV-17 tables (§8.6; Architect ADR + Stage-1) + `test_worker_state_durability.py` | **1** |
| T-PRA-04 | B-2, B-9 | INV-14 safe rollout (reconcile incl. `degraded_mode_state` + `persistence.py` `"owner"` defaults + `data_source` CHECK; verify; gated enable) + `test_db_integrity.py` | **1** |
| T-PRA-05 | SA:m-4, E-2 | INV-19: transport ADR addendum + collectors + `test_worker_observability.py` | 2 |
| T-PRA-06 | SA:M-2 | Multi-athlete scheduler registration from `athletes` table; docstring corrected — RESOLVED (ADR-0067, ADR-0070) | RESOLVED |
| T-PRA-07 | B-4 | INV-12 fail-closed governance guard — RESOLVED 2026-06-12 (PR #865): apply_constraints inner wrapper + coaching_pipeline boundary guard, both forcing EASY/zone-2. REST-forcing sub-scope deliberately superseded — EASY/zone-2 is the existing fail-safe value and avoids a step-10/11 divide-by-zero that literal REST would risk. | RESOLVED |
| T-PRA-08 | B-6 | DR-01..04: off-volume backup, retention, `integrity_check`, real-backup verify, restore drill, `RUNBOOK_DR.md` | **1** |
| T-PRA-09 | B-7 | RE-01..04 + `test_release_engineering.py` (version-from-metadata CI test) | 2 |
| T-PRA-10 | SA chain | INV-21 `test_degradation_alert_chain.py` end-to-end | 2 |
| T-PRA-11 | B-13 | RBP-01 body-size middleware + `test_request_boundary.py` | 2 |
| T-PRA-12 | D-1/K:PRA-16, C-7 | Records pass: snapshot fix, B2/B5 entries, ADR-0057 status (absorbs T-PRA-16), scope-doc + phase-label reconcile, module-ceiling audit-value (80) vs enforced test value reconcile, one-time grep for stale INV-20 keying (absorbs T-PRA-17) | 2 |
| T-PRA-14 | B-10 | MPC doc+comment corrections; **ADR-0044 execution-date decision before the Architect** | 2 |
| T-PRA-18 | SA:BENIGN1/2 | Wire ADR-0052 calibration loop (consume `_threshold_adapter`); wiring test | 2 |
| T-PRA-20 | SA:BENIGN3 | Diagnostic-script DB path → config constant | 3 |
| T-PRA-21 | B-11 | INV-22 durable ordered-before-effect audit + `test_audit_durability.py` | **1** |
| T-PRA-22 | B-15, B-3, SA:m-3 | INV-23: healthcheck, heartbeat, watchdog, callback isolation, stale-lock recovery, limits/rotation + `test_worker_liveness.py` | **1** |
| T-PRA-23 | B-8 family | §13.4 Stage-3 downgrade routines / documented reversal, phase-boundary tested | 2 |
| T-PRA-24 | B-14 | INV-24 trust-verdict clamp + `test_data_trust_enforcement.py` | **1** |
| T-PRA-25 | B-8 | INV-25 `user_version > SCHEMA_VERSION` startup guard + test | **1** |
| T-PRA-26 | K:PRA-13, SA:m-2, C-6 | Sync & safety-path conformance sweep: 429/retry-exhaustion failure registration (INV-08 ext), sync-age pre-`inf` logging, getattr-dispatch removal + semgrep guard | 2 |
| T-PRA-27 | B-12, K:PRA-18 | RE-05/06: CodeQL on PR/push, gitleaks full-range, SBOM, image scan, pin parity, dated CVE ignores | 2 |
| T-PRA-28 | F-4/5/7/10 | RBP-04/05 bundle: JWT-at-construction, uniform auth failures, hybrid lockout, HttpOnly CSRF, token-key required | 2 |
| T-PRA-29 | D-2 | One real e2e: compose up in CI → write → restart containers → assert persistence + `/readyz`; promote `docker_smoke_test.sh` into the gate | 2 |
| T-PRA-30 | D-4, C-2, C-3 | Migration-chain v1→vN realistic-data test + SQLite↔Alembic schema-parity test (pre-Phase-8A gate) + frozen-migration (v8/v13/v24) column-manifest meta-test (absorbs T-PRA-33) | 2 |
| T-PRA-31 | E-3 | Route all `slo_alert`/alert-class events through `NotificationGateway` chokepoint — SUPERSEDED (gateway deleted, D-139); the `slo_alert` gap is P4-09 | SUPERSEDED |
| T-PRA-32 | K:PRA-15 | Finish EngineRegistry CS/APL hydration (TODO-P26-04b/c); correct Phase-26 record | 2 |
| T-PRA-35 | D-1, C-7, I-22 | Governance sensor bundle: snapshot generator + T4-22 wiring, `scripts/session_start.sh`, ceiling doc-agreement assert (T4-21 ext), ADR-status linter | 3 |
| T-PRA-36 | D-6 | Convert the 6 skip-placeholders to strict xfail bound to debt items **+ meta-test forbidding undocumented skips** (standing enforcement, not one-time cleanup) | 3 |
| T-PRA-37 | Ladder Pass 3 | `scripts/governance_lint.py` — checks L1–L9 over this document + the operating contract, wired into `titan_ci.sh` Gate 1 (§16.3) | 2 |
| T-PRA-38 | Ladder Pass 3 | `titan_ci.sh --profile scoped|full` + `scripts/env_fingerprint.sh`; v7.9 §1.5 record fields (§2.3, §2.4) | 2 |
| T-PRA-39 | Ladder Pass 3 | `docs/governance/ledger.jsonl` orchestrator append + phase-close summary (§2.4, §22) | 3 |

**Folded/Removed IDs (retained for audit-ID stability; every fold preserves its disposition):**
T-PRA-13 → T-PRA-03 (nonce durability) · T-PRA-15 → T-PRA-26 · T-PRA-16 → T-PRA-12 ·
T-PRA-19 → T-PRA-22 · T-PRA-33 → T-PRA-30 · T-PRA-34 → T-PRA-26 · T-PRA-17 removed
(speculative — replaced by a one-time verification inside T-PRA-12).

Opening these is the Records Steward's next action after this revision is accepted. **Tier-1 set:
T-PRA-01, 02, 03, 04, 06, 07, 08, 21, 22, 24, 25.** Live items: 32 (7 folded/removed IDs listed
above; lint L3 verifies these counts against the table).

---

## §31 — Reconciliation Index

The body text is the binding text; this index preserves anchors only. Detailed change keys live
in git history.

| Pass (date) | Anchor keys | Landed in |
|---|---|---|
| Pass-2 QA hardening (2026-06-10) | C1–C14 | §HARD GATE (C1), §8.5 (C5), §8.6/§13.3 (C4), §8.7 (C3), §8.8 (C6), §8.2 (C12), §16.7 (C11), §16.10 (C13), §17.3 (C7), §28 (C8), §30 (C2, C9/C10, C14) |
| Pass-3 QA + consolidation (2026-06-11) | G-1..G-16 | single gate law (§19/§HARD GATE), single delivery format (§23), lane challenge split (§14.1), metrics contract (§8.8), generic phase gate (§16.2), athlete-id end-state (§16.10), enforcement classes (§8.2), tier carve-out removal (§30), policy-only constraint (§3.6) |
| Pass-4 minimization (2026-06-11) | H-1..H-10 | §2.0 (H-1, H-4), §8.6 DDL→ADR (H-2), §8.11 (H-3), §16.3 sensors (H-5), §30 folds (H-6), §8.12 compose check (H-7), §8.10/§8.11 (H-8), invariant-ID verdicts (H-9), semgrep/meta-test enforcement (H-10) |
| Governance ladder Pass 1–3 (2026-06-12) | AF-01..10 · AG2-01..10 · AG3-01..08 | §1.2 Reserved Powers; §2.3/§2.4 evidence + profiles; §3.6/§13.1/§14.1/§28 → §1.2 pointers; §8.2 violation vocabulary; §16.1 ladder termination; §16.3 lint + TRACKED liveness; §16.11 ceiling + mass-cited review; §16.12 → v7.9 §14; §17.7 (ex-unnumbered QA policy); §18 contract ownership row; §19 single gate law inlined; §21 scope extension; §22 ledger review; §23 `Authorizes:` field + §23.1; §30 vocabulary + T-PRA-37..39; tombstones extracted; inline pass-annotations retired; contract revised to v7.9-r3 |

§24 merged into the §23 handoff template (`Closure rule`, `Canonical doc update` fields);
§25 folded into §2.0. Anchors retired; absent declarations remain DoR FAIL.

---

*Changelog (newest first; full history in git):*
- *2026-10-23 r6 — Documents reconciled with the code after the MA/OW/P4 audits (policy-only,
  ADR-0070): §16.6 and the alert rows without `NotificationGateway` (ADR-0069 §7); §8.13 INV-22
  surfaces; §16.11 ceiling 90; §30 SA:M-2/T-PRA-06 resolved, T-PRA-31 superseded.*
- *2026-06-12 r5 — Governance ladder Pass 1–3 consolidation (policy-only): structural cleanup
  (Pass 1), authority/clearance/severity single-sourcing (Pass 2), evidence-record +
  orchestrator-obligation + lint/telemetry layer (Pass 3). Debt register 29 → 32 live items.
  Governing contract: v7.9-r3.*
- *2026-06-11 r4 — Pass-4 minimization/placement/operationalization (policy-only): H-1..H-10;
  prose rules converted to sensors; DDL relocated to ADR layer; zero coverage loss.*
- *2026-06-11 r3 — Pass-3 QA + consolidation (policy-only): full production-readiness audit
  incorporated; INV-24/25, INV-08 ext, RE-05/06, RBP-04/05, MPC-02, DR amendments; T-PRA-24..36;
  document reduced ~50% with all controls preserved.*
- *2026-06-10 r2 — Pass-2 QA hardening: §31-C1..C14; INV-21/22/23; §13.4 downgrade; honest §30
  vocabulary; T-PRA-17..23.*
- *2026-06-10 r1 — Governance Alignment Reconstruction: v7.9 alignment; §8.4–§8.12; INV-11..20;
  §30 register; T-PRA-01..16.*
- *Earlier (2026-03 era): §28; §23–§27 lanes/rules; ADR-0049 taxonomy; §20–§22; §17 workflow;
  §12.5; DoR/E-rules; §2.0/§3.6/§12–§16 foundations.*

*Authoritative for all agents and engineers operating on TITAN OS.*
