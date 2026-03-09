# TITAN OS — Engineering Scratchpad (Πρόχειρο)

**Protocol version:** 1.1
**Architect-owned:** YES — Codex writes OBS entries; Claude writes DEC entries and controls status.
**Purpose:** Structured communication channel between Codex (engineer) and Claude (architect).
Codex writes raw engineering observations here. Claude reads, verifies, decides, and converts
them to clean tasks in `TECHNICAL_DEBT.md`. Neither party acts on observations alone.

---

## Document Status

```
STATUS: REVIEW_REQUESTED
```

Valid states:
- `IDLE` — no pending observations; Codex may proceed with assigned tasks
- `REVIEW_REQUESTED` — Codex has written one or more OBS entries; Claude must review before new tasks are assigned
- `UNDER_REVIEW` — Claude is currently processing the pending OBS entries
- `CLARIFICATION_NEEDED` — Claude has written a partial DEC and requires additional context from Codex before deciding
- `CLEARED` — all OBS entries processed; Codex may continue (Claude will reset to IDLE after clearing)

**IMPORTANT — Codex:** Run `scripts/check_scratchpad.sh` at Step 0.5 (after `setup_env.sh`). The
script will fail with exit code 1 if the BLOCKING Queue is non-empty. Do not bypass it.
When you set STATUS to `REVIEW_REQUESTED`, **stop and wait**. Do not begin a new top-level
task until Claude sets status to `IDLE` or `CLEARED`. This is not optional.

**IMPORTANT — Claude:** When status is `REVIEW_REQUESTED` at session start, process all PENDING
OBS entries before assigning any new task to Codex. Run `scripts/check_scratchpad.sh` to
confirm the gate is clear before proceeding. See §A-SCRATCHPAD-1 in `CLAUDE.md`.

**CLARIFICATION flow:** When Claude writes a DEC with decision `CLARIFICATION_NEEDED`, Claude
sets STATUS to `CLARIFICATION_NEEDED`. Codex appends the requested context to the original OBS
entry (labelled `**Clarification (YYYY-MM-DD):**`) and then resets STATUS to `REVIEW_REQUESTED`.
Claude then resumes the DEC. This flow may repeat at most once per OBS entry.

---

## How This Document Works

### Codex → Claude (OBS entries)

Codex writes **Observation (OBS)** entries when specific trigger conditions are met
(see §15 in `AGENTS.md`). Each OBS entry is a raw engineering finding — Codex does NOT make
architectural decisions here. Codex only:
- Describes what was found (facts, patterns, code locations)
- States what architectural question it raises
- Flags urgency (BLOCKING / NON-BLOCKING)

OBS entries use sequential IDs: `OBS-001`, `OBS-002`, etc.
New OBS IDs always increment from the highest existing ID, including REVIEWED entries.

**BLOCKING OBS** go in the `## BLOCKING Queue` section.
**NON-BLOCKING OBS** go in the `## NON-BLOCKING Queue` section.

### Claude → Codex (DEC entries)

Claude writes **Decision (DEC)** entries in response to OBS entries. Each DEC:
- References the OBS it responds to
- States the architect's verified finding
- Records the decision taken (new debt entry / ADR / no action / defer / clarification needed)
- Marks the corresponding OBS as `REVIEWED`

DEC IDs match the OBS they respond to: `DEC-001` responds to `OBS-001`.

### Lifecycle of an OBS entry

```
Codex writes OBS → places in BLOCKING or NON-BLOCKING queue → sets STATUS: REVIEW_REQUESTED
  → Claude runs check_scratchpad.sh (Step 0.5) — confirms gate state
  → Claude reads + independently verifies findings (BLOCKING first, then NON-BLOCKING)
  → [optional] Claude writes partial DEC → STATUS: CLARIFICATION_NEEDED
      → Codex appends clarification → STATUS: REVIEW_REQUESTED → Claude resumes DEC
  → Claude writes final DEC + creates TECHNICAL_DEBT.md entries if needed
  → Claude marks OBS as REVIEWED + marks DEC as PROCESSED
  → When all OBS cleared: status → IDLE
```

---

## Trigger Reference (quick summary)

| Trigger | Who | When |
|---|---|---|
| T-SCRATCHPAD-1 | Codex | After each T4-01 subsystem completion |
| T-SCRATCHPAD-2 | Codex | Before crossing into a new Tier |
| T-SCRATCHPAD-3 | Codex | When 3+ related out-of-scope findings accumulate in one session |
| T-SCRATCHPAD-4 | Codex | When a Phase is declared CLOSED |
| T-SCRATCHPAD-5 | Codex | Alongside every §13.2 architectural decision-point stop |
| A-SCRATCHPAD-1 | Claude | At every session start (run check_scratchpad.sh before assigning tasks) |
| A-SCRATCHPAD-2 | Claude | Before writing any new TECHNICAL_DEBT.md planning block |
| A-SCRATCHPAD-3 | Claude | Before declaring any Phase CLOSED |

Full trigger specifications: Codex → `AGENTS.md §15`; Claude → `CLAUDE.md §Architect Scratchpad Review Protocol`.

---

## OBS Entry Format

```markdown
### [OBS-XXX] <short title (≤ 10 words)>

**Date:** YYYY-MM-DD
**Trigger:** T-SCRATCHPAD-N — <trigger name>
**Session context:** T<tier>-<id> / Phase X.Y / Subsystem: <name>
**Urgency:** BLOCKING | NON-BLOCKING
**Files involved:**
- `path/to/file.py` — <one-line reason>

**Observation:**
<Factual description of what was found. Code snippets inline if helpful.
No opinions on the fix. No design proposals. Facts only.>

**Pattern / scope:**
<Is this isolated or does it appear in multiple places? Quantify if possible.>

**Architectural question raised:**
<The specific question Codex cannot answer without architect approval.
Must be a single, concrete question — not a vague concern.>

**Codex assessment (data only, no decision):**
<What Codex believes the impact is, based on observable evidence.
No proposed solution. If unsure, say so.>

**Status:** PENDING
```

---

## DEC Entry Format

```markdown
### [DEC-XXX] Response to OBS-XXX — <short title>

**Date:** YYYY-MM-DD
**Architect:** Claude
**OBS verified:** YES — <how verified: code read / test run / cross-reference with ADR-XXXX>
           | NO — <why observation is factually incorrect>

**Architect finding:**
<What the architect confirmed after independent verification. This supersedes the OBS
assessment. If the OBS was incorrect, explain why.>

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T<N>-<id> created in TECHNICAL_DEBT.md — <one-line description> |
| ADR_NEEDED | ADR-XXXX to be authored before implementation |
| NO_ACTION | <reason: existing coverage / acceptable risk / out of scope> |
| DEFERRED | Assigned to Phase X — <reason for deferral> |
| CLARIFICATION_NEEDED | <exact question for Codex — one sentence, answerable by reading code> |

**Rationale:**
<Why this decision was made. Reference ADRs, existing constraints, or risk analysis.
If CLARIFICATION_NEEDED: explain what is missing and why it blocks the decision.>

**OBS-XXX marked:** REVIEWED | PENDING_CLARIFICATION
**Status:** PROCESSED | AWAITING_CLARIFICATION
```

---

## BLOCKING Queue

*No blocking observations.*

---

## NON-BLOCKING Queue

### [OBS-008] Scratchpad continuation rule conflicts with stop rule

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — §15 intro states global stop after writing OBS
- `AGENTS.md` — T-SCRATCHPAD-3 explicitly permits continuation of current subtask
- `SCRATCHPAD.md` — Document status guidance describes stop/wait behaviour

**Observation:**
The protocol contains conflicting execution guidance after writing an OBS. `AGENTS.md` §15 states that after writing an OBS, Codex sets `STATUS: REVIEW_REQUESTED` and stops until cleared. In the same section, trigger T-SCRATCHPAD-3 states Codex may continue the current task and only blocks new top-level tasks. `SCRATCHPAD.md` status guidance also frames `REVIEW_REQUESTED` as a stop/wait gate for new task assignment, which creates ambiguity about whether in-flight execution must halt immediately.

References: AGENTS.md:884-885, AGENTS.md:929-931, SCRATCHPAD.md:26-31.

**Pattern / scope:**
Process-state semantics for `REVIEW_REQUESTED` are defined across multiple sections and are not fully consistent. This affects all future OBS usage, not a single task.

**Architectural question raised:**
For `STATUS: REVIEW_REQUESTED`, is Codex required to stop all in-flight work immediately, or only prohibited from starting a new top-level task?

**Codex assessment (data only, no decision):**
Current wording permits two valid but different operator interpretations, which can produce inconsistent behaviour between sessions.

**Status:** PENDING

### [OBS-009] Enforcement burden concentrated in manual checklist discipline

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — §11 pre-delivery checklist with 29 manual confirmations
- `AGENTS.md` — §2 and HARD GATE define mandatory sequencing and prohibitions
- `SCRATCHPAD.md` — protocol requires status transitions and queue discipline

**Observation:**
Large parts of workflow acceptance depend on manual self-attestation rather than explicit automated gates. The process requires 29 checklist assertions and multiple sequencing rules, but only a subset are mechanically enforced by executable commands. Several obligations (scope declaration completeness, task-learning block presence, some status semantics, and protocol narrative conformance) rely on procedural adherence.

References: AGENTS.md:566-585, AGENTS.md:45-63, SCRATCHPAD.md:14-31.

**Pattern / scope:**
This is systemic and spans task start, implementation, validation, and closure stages.

**Architectural question raised:**
Which workflow obligations are intended to be hard-enforced by automation versus treated as manual governance requirements?

**Codex assessment (data only, no decision):**
Reliability of process compliance currently depends on operator consistency for multiple high-frequency steps.

**Status:** PENDING

### [OBS-010] Architect approval is a single-point workflow bottleneck

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — scratchpad protocol requires stop for review/clear events
- `SCRATCHPAD.md` — Claude-only ownership of DEC and status transitions to IDLE/CLEARED

**Observation:**
The framework serializes progression through architect-controlled review checkpoints. Codex records OBS entries but cannot clear them, while Claude is the only actor who can process DEC decisions and move status back to `IDLE`/`CLEARED`. This creates a single-point dependency for workflow continuation whenever review status is raised.

References: AGENTS.md:884-885, AGENTS.md:901-903, SCRATCHPAD.md:4, SCRATCHPAD.md:20-31.

**Pattern / scope:**
Applies to all trigger paths that set `REVIEW_REQUESTED`, with stronger effect if observation frequency increases.

**Architectural question raised:**
Is the current architect-only clearance model intended to remain strictly serialized under concurrent task load?

**Codex assessment (data only, no decision):**
Throughput for multi-task execution is coupled to architect review latency at each review-requested checkpoint.

**Status:** PENDING

### [OBS-011] Mandatory full-suite repetition introduces scaling pressure

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — HARD GATE requires strict + full pytest runs for every deliverable
- `AGENTS.md` — §2 canonical sequence requires rerun of all gates after any failure

**Observation:**
The acceptance model mandates two full-suite pytest executions per task (`-W error::pytest.PytestWarning` and canonical full run), plus complete re-execution after any single gate failure. As suite size grows, this imposes compounding validation cost per change and increases queue time before commit/PR eligibility.

References: AGENTS.md:45-63, AGENTS.md:153-170.

**Pattern / scope:**
System-wide effect on all tasks; cost grows with total test count and with concurrent branch activity.

**Architectural question raised:**
Is full-suite dual-run on every task intended to remain unchanged at larger suite sizes and higher parallel development volume?

**Codex assessment (data only, no decision):**
Current gate design prioritizes consistency, but it also creates predictable scaling pressure in large-suite/high-concurrency conditions.

**Status:** PENDING


### [OBS-012] Out-of-scope routing split between debt register and scratchpad

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Governance consistency / Cross-document correlation
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — §3.4 and §12.2 require Codex to add out-of-scope findings directly to `TECHNICAL_DEBT.md`
- `AGENTS.md` — §15 defines scratchpad as Codex→Claude observation channel with architect decision handoff
- `SCRATCHPAD.md` — purpose/lifecycle state Claude converts OBS into debt tasks
- `CLAUDE.md` — Engineering Rules map E8 points to direct debt-register route

**Observation:**
The framework defines two different routing paths for out-of-scope findings. One path requires Codex to directly create `TECHNICAL_DEBT.md` entries (`AGENTS.md` §3.4 and §12.2). The other path frames Codex as observation-only and assigns debt conversion decisions to Claude through DEC processing in `SCRATCHPAD.md` and AGENTS §15. `CLAUDE.md` rule map also points to direct debt-entry behaviour (E8), reinforcing one branch of the split.

References: AGENTS.md:292-294, AGENTS.md:616-622, AGENTS.md:877-885, SCRATCHPAD.md:4-7, SCRATCHPAD.md:69-77, CLAUDE.md:182.

**Pattern / scope:**
This appears as a repeated governance seam across all out-of-scope handling touchpoints (policy section, closure section, scratchpad protocol, and rule index). It is not isolated to one subsection.

**Architectural question raised:**
For out-of-scope findings, which route is canonical in active operation: direct `TECHNICAL_DEBT.md` creation by Codex, or observation-first escalation through `SCRATCHPAD.md` with architect conversion?

**Codex assessment (data only, no decision):**
Parallel routing instructions can produce inconsistent execution records across sessions (some findings captured as debt items immediately, others only as OBS), reducing governance trace consistency.

**Status:** PENDING

### [OBS-013] Debt-clear enforcement signal is non-executable in session-start gate

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow reliability / Early drift detection
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — SESSION_START mandates S1–S5 checklist
- `AGENTS.md` — §12.5 states Codex MUST report debt-clear counter via S2b signal
- `AGENTS.md` — S2b snippet outputs open debt count while counter is tracked manually by architect

**Observation:**
The debt-clear window introduces a mandatory counter-reporting requirement, but the executable session-start checklist does not include S2b, and the provided S2b command does not compute the counter itself. The snippet prints only open debt count and explicitly delegates counter tracking to manual architect reading of the tracking table.

References: AGENTS.md:128-138, AGENTS.md:658-669.

**Pattern / scope:**
This is a false-confidence pattern: a requirement is phrased as mandatory and signaled by a command, but enforcement remains manual. The same pattern can recur in other policy areas where command snippets expose only proxies.

**Architectural question raised:**
Is debt-clear counter compliance intended to be a strict executable gate at session start, or an informational/manual governance check outside codified gate enforcement?

**Codex assessment (data only, no decision):**
Because the counter is not produced by a deterministic command in the mandatory startup sequence, sessions can claim compliance while applying different manual interpretations.

**Status:** PENDING


### [OBS-014] Process MUST-rules exceed machine-enforced governance checks

**Date:** 2026-03-09
**Trigger:** User-requested engineering framework enforcement audit
**Session context:** Governance QA / Documentation-to-enforcement consistency
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — defines mandatory startup/session checks, hard-gate sequencing, and 29-item pre-delivery checklist
- `scripts/check_scratchpad.sh` — enforces BLOCKING queue only, while REVIEW_REQUESTED/UNDER_REVIEW remain advisory exit 0
- `tests/test_claude_md_integrity.py` — enforces selected CLAUDE.md integrity invariants only
- `tests/test_documentation_consistency.py` — enforces selected documentation drift invariants only

**Observation:**
The governance contract contains many MUST-level process obligations that do not have a corresponding executable guard. Examples include the mandatory SESSION_START S1–S5 protocol, first-response reporting requirement, complete pre-delivery checklist assertions, and PR scope-declaration completeness. The current executable controls verify a narrower subset: lint/test gates, selected documentation integrity invariants, and BLOCKING scratchpad queue detection. `scripts/check_scratchpad.sh` returns non-blocking exit code 0 for `REVIEW_REQUESTED`/`UNDER_REVIEW`, and there is no test that validates session-start command execution, checklist completion, or PR-body conformance.

References: AGENTS.md:130-146, AGENTS.md:560-587, AGENTS.md:247-259, scripts/check_scratchpad.sh:29-58, tests/test_claude_md_integrity.py:25-159, tests/test_documentation_consistency.py:129-196.

**Pattern / scope:**
System-wide process-enforcement gap between policy text and executable verification surface. This affects all sessions and all task closures, not a single subsystem.

**Architectural question raised:**
Which MUST-level workflow obligations are intentionally manual governance duties versus intended hard gates with deterministic enforcement evidence?

**Codex assessment (data only, no decision):**
Process rigor appears stronger in policy wording than in currently automated checks; compliance for several high-importance obligations depends on operator self-attestation.

**Status:** PENDING

### [OBS-007] Task closure declared RESOLVED without verifying ADR deliverable checklist

**Date:** 2026-03-08
**Trigger:** QA FAIL on T5-08 (Opus QA verdict) — ADR scope vs implementation drift
**Session context:** T5-08 / Phase 8A / PostgreSQL migration scaffold
**Urgency:** NON-BLOCKING
**Files involved:**
- `TECHNICAL_DEBT.md` — T5-08 entry (status was RESOLVED, now corrected to PARTIAL)
- `docs/adr/0044-postgresql-migration-phase8a-entry-gate.md` — D1–D9 deliverable table
- `titan/core/database.py` — scaffold implementation (commit 54e95d9)

**Observation:**
T5-08 was declared ✅ RESOLVED in `TECHNICAL_DEBT.md` (commit 54e95d9, 2026-03-08) without
verifying that ADR-0044 deliverables D1–D9 were complete. The implementation delivered:
- D6 (feature flag `TITAN_DB_BACKEND`) ✓
- Backend parity tests for CTL/ATL and governance persistence ✓

But D1–D5, D7–D9 were not implemented: no `persistence.py`, no `alembic/`, no `athlete_id`
columns, no RLS, no `consent_log`, no `pg_dump` backup. The acceptance gate in the task entry
referenced `persistence.py`, `alembic/`, and `tests/test_athlete_rls_isolation.py` — none of
which existed at closure time. The gate was not run; status was set by assertion.

**Pattern / scope:**
Isolated to T5-08 closure. No other task shows evidence of this pattern in the current
Phase 8 queue. However, T5-08 is the first task in Phase 8 that references an ADR with an
explicit numbered deliverable table (D1–D9). Future tasks with similar ADR deliverable tables
(T5-08-B, T5-09, T5-11, T5-13, T5-16-A) carry the same risk.

**Architectural question raised:**
Should a mandatory ADR Deliverable Checklist be part of the task closure protocol — requiring
each ADR-referenced deliverable to be checked off (✓ done / ✗ not done) before status is set
to RESOLVED — to prevent recurrence of ADR scope vs implementation drift?

**Codex assessment (data only, no decision):**
The drift was detectable at closure time: the acceptance gate referenced files that did not
exist. The process had no mechanism to catch this — the gate was written but not enforced.
The proposed checklist would make the drift structurally visible before the closure commit.

**Status:** REVIEWED

---

<!-- REVIEWED entries moved to Archive — 2026-03-08 -->
<!-- OBS-004/005/006 written by architect (Claude) 2026-03-08 — future tripwires for Phase 8 entry events -->

### [OBS-004] Governance engine instantiation semantics under CoachingScheduler

**Date:** 2026-03-08
**Trigger:** Architect-originated future tripwire (Phase 8 risk pre-registration)
**Session context:** Phase 8 / ADR-0046 multi-athlete execution model (T5-16 closed)
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/orchestration/daily_coach.py` — current single-athlete instantiation model
- `tests/test_athlete_isolation_invariant.py` — profile-level isolation guard (existing)
- ADR-0046 — CoachingScheduler + stateless coaching_pipeline design

**Observation:**
`test_athlete_isolation_invariant.py` verifies that athlete profile data (DB reads,
metrics) does not bleed between athletes. It does not verify that engine instances
(e.g. `GovernanceEngine`, `HRVEngine`) are instantiated per-athlete-run rather than
shared across runs. If `CoachingScheduler` reuses engine instances between athlete
coaching cycles, cached intermediate state within an engine could produce cross-athlete
contamination that bypasses the existing profile isolation test.

**Pattern / scope:**
Isolated risk point — becomes concrete only when CoachingScheduler implementation begins.
Current single-athlete model has no analogous risk. Pattern does not yet exist in code.

**Architectural question raised:**
When CoachingScheduler is implemented, will engine instances be created fresh per
athlete-run (safe), or shared/pooled across runs (requires explicit stateless proof)?

**Codex assessment (data only, no decision):**
Not applicable — this OBS is architect-originated. No code has been written yet for
the multi-athlete scheduler. The question is a design-time invariant to enforce at
implementation time.

**Status:** REVIEWED

---

### [OBS-005] Concurrency semantics delta at PostgreSQL migration boundary

**Date:** 2026-03-08
**Trigger:** Architect-originated future tripwire (Phase 8 risk pre-registration)
**Session context:** Phase 8 / ADR-0044 PostgreSQL migration gate
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/core/database.py` — `threading.Lock` + `check_same_thread=False` concurrency model
- `tests/test_database_manager_thread_safety.py` — SQLite-specific threading tests
- `tests/test_harden_db_concurrency.py` — SQLite-specific concurrency stress tests
- ADR-0044 — PostgreSQL migration as Phase 8A entry gate

**Observation:**
The current concurrency model (`threading.Lock` + `check_same_thread=False`) is
SQLite-specific. Existing threading tests verify correctness of this model against
SQLite semantics. When the PostgreSQL migration task opens, a new database layer will
be introduced with fundamentally different concurrency semantics (connection pooling,
different transaction isolation, no `check_same_thread` concept). The existing tests
will continue to pass against the SQLite code path but will not exercise the new
PostgreSQL layer. No current test covers PostgreSQL connection pool behaviour under
concurrent writes.

**Pattern / scope:**
Isolated to the database adapter boundary. Will not manifest until the PostgreSQL
migration task opens. The gap is structural: two code paths will exist simultaneously
during migration, with only one covered by concurrency tests.

**Architectural question raised:**
When the PostgreSQL migration task opens, should concurrency validation tests for the
new adapter be an explicit acceptance criterion in the task definition, to prevent
the threading tests from providing false coverage confidence?

**Codex assessment (data only, no decision):**
Not applicable — architect-originated. The observation is a pre-registration of a
known structural gap that becomes active at migration task start.

**Status:** REVIEWED

---

### [OBS-006] OperatorConsole payload round-trip serialization gap at FastAPI boundary

**Date:** 2026-03-08
**Trigger:** Architect-originated future tripwire (Phase 8 risk pre-registration)
**Session context:** Phase 8 / ADR-0013 Operator Console technology path (React + FastAPI)
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/ui/operator_console.py` — `OperatorConsoleService` payload construction
- `tests/test_operator_console_dashboard.py` — payload shape tests (Python dict assertions)
- ADR-0013 — Streamlit → React + FastAPI technology path (Accepted)

**Observation:**
`test_operator_console_dashboard.py` verifies payload contracts as Python dict shapes.
These tests run entirely within Python and do not exercise JSON serialization. When the
FastAPI layer is introduced, payloads will pass through `json.dumps` / Pydantic
serialization. Python types without a direct JSON equivalent (`datetime`, `Decimal`,
`Enum`, `None` in typed fields) may be silently coerced or dropped. The existing
tests will continue to pass (Python-side only) while the API-side contract is broken.
No round-trip serialization test (Python dict → JSON → dict → assert) currently exists.

**Pattern / scope:**
Isolated to the OperatorConsole payload boundary. Becomes concrete when FastAPI
implementation begins. The guard needed is a round-trip test per payload type
(dashboard, session explorer, override workflow, calibration review).

**Architectural question raised:**
When the FastAPI implementation task opens, should round-trip serialization tests
for all four payload types be an explicit acceptance criterion, to prevent the
existing dict-shape tests from providing false coverage confidence?

**Codex assessment (data only, no decision):**
Not applicable — architect-originated. The observation is a pre-registration of a
known gap that becomes active at FastAPI task start.

**Status:** REVIEWED

---

### [OBS-001] Test suite has no pytest layer markers

**Date:** 2026-03-08
**Trigger:** T-SCRATCHPAD-3 — future maintenance observations submitted by engineer
**Session context:** Phase 8 / CI safeguards post-review
**Urgency:** NON-BLOCKING
**Files involved:**
- `pyproject.toml` — markers config: only `timeout` defined, no `unit`/`integration`/`governance`
- `tests/` — 105 test files; `test_*.py` root — 13 files; no `@pytest.mark.unit` etc. in use

**Observation:**
The test suite (118 files, ~1780+ tests) has grown substantially across Phase 0–8.
Test categorisation is done only by filename convention (e.g. `test_governance_integration.py`,
`test_p0_safety_gates.py`). No pytest marks for layer (unit / integration / governance / invariant)
are registered or applied. `pyproject.toml` defines only `markers = ["timeout: ..."]`.

**Pattern / scope:**
Isolated to the test infrastructure configuration — no individual test file is responsible.
The pattern is uniform across all ~118 test files.

**Architectural question raised:**
Should a formal marker taxonomy (e.g. `unit`, `integration`, `governance`) be registered and
applied to all existing tests to enable selective execution and faster failure diagnostics?

**Codex assessment (data only, no decision):**
Without markers, `pytest -m governance` is impossible. When a governance gate test fails, the
developer must scan filename-by-filename to identify test layer. As the suite grows beyond 2000
tests this will slow diagnostics. Impact is currently low but increases proportionally with suite size.

**Status:** REVIEWED

---

### [OBS-002] Doc-integrity regex patterns tightly coupled to exact markdown wording

**Date:** 2026-03-08
**Trigger:** T-SCRATCHPAD-3 — future maintenance observations submitted by engineer
**Session context:** Phase 8 / CI safeguards post-review
**Urgency:** NON-BLOCKING
**Files involved:**
- `tests/test_claude_md_integrity.py` — 6+ regex patterns against exact markdown formatting

**Observation:**
`test_claude_md_integrity.py` uses patterns that require exact markdown surface form:
- `r"Main package \((\d+) modules, excl\. __init__/__main__\)"` — exact phrase in CLAUDE.md
- `r"^- `([0-9]{4})`"` — requires backtick-wrapped ADR IDs in a specific list format
- `r"\*\*Historical snapshot:\*\*\s*(\d+) tests all green"` — exact bold wording
- `r"\|\s*`docs/ROADMAP\.MD`\s*\|([^\|]+)\|"` — table cell format for ROADMAP row
- `r"^Phase (\S+) OPEN\b"` in TECHNICAL_DEBT.md — requires "Phase N OPEN" at line start

A legitimate doc reformatting (e.g. renaming "Main package" → "Core package" for clarity,
or switching ADR list from backtick to plain text) would produce a CI failure even if the
information is factually unchanged.

**Pattern / scope:**
6 patterns in a single file. Isolated, not replicated elsewhere.

**Architectural question raised:**
Is this brittleness an acceptable trade-off of the integrity test design, or should a schema
layer (e.g. YAML frontmatter, or a structured CLAUDE.md section) replace the fragile regex?

**Codex assessment (data only, no decision):**
The tests are effective exactly because they are tight — loosening them reduces their ability
to catch real drift. The brittleness risk is real but the formatting of these doc sections
has been stable since they were introduced. No false positive has been observed to date.

**Status:** REVIEWED

---

### [OBS-003] Documentation snapshot drift already substantially automated

**Date:** 2026-03-08
**Trigger:** T-SCRATCHPAD-3 — future maintenance observations submitted by engineer
**Session context:** Phase 8 / CI safeguards post-review
**Urgency:** NON-BLOCKING
**Files involved:**
- `tests/test_claude_md_integrity.py` — 5 automated drift guards already implemented

**Observation:**
`test_claude_md_integrity.py` contains the following automated snapshot-drift guards:
1. `test_adr_count_in_claude_md_matches_files` — ADR list vs actual ADR files in `docs/adr/`
2. `test_module_count_in_claude_md_matches_filesystem` — declared titan module count vs `rglob`
3. `test_historical_snapshot_matches_full_suite_collection` — CLAUDE.md test count vs collected
4. `test_key_files_section_points_to_existing_paths` — all `Key Files` paths exist on disk
5. `test_phase_state_label_consistent_between_tech_debt_and_claude_md` — phase OPEN/CLOSED parity

**Pattern / scope:**
Isolated finding. The concern raised (snapshot drift) is already the primary purpose of this file.

**Architectural question raised:**
Is there a residual snapshot-drift gap not covered by the existing 5 guards that warrants a
new automated check, or is the current coverage sufficient for Phase 8?

**Codex assessment (data only, no decision):**
No specific gap has been identified. The concern appears to be a general "keep this pattern going"
observation rather than identification of a concrete uncovered risk.

**Status:** REVIEWED

---

## Architect Review Log

### [DEC-004] Response to OBS-004 — Engine instantiation semantics: deferred to multi-athlete task

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_athlete_isolation_invariant.py`; confirmed that
  guards cover profile data isolation (DB reads, metric dicts) but do not assert engine
  instance lifecycle (fresh-per-run vs. shared). ADR-0046 accepted but implementation not
  yet started (T5-16 closed = ADR accepted, not code delivered).

**Architect finding:**
The gap is real and correctly identified. The existing isolation invariant tests profile
data, not engine state. If CoachingScheduler pools engine instances, any mutable
intermediate state (e.g. cached physiological metrics, lock states in APL) would be a
source of cross-athlete contamination that the current test cannot detect. The risk is
currently zero because the multi-athlete scheduler does not yet exist. It becomes active
the moment CoachingScheduler implementation begins.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Trigger: CoachingScheduler implementation task opens — engine-instantiation lifecycle (fresh-per-run vs. shared) must be an explicit acceptance criterion in that task |

**Rationale:**
No guard is warranted now — there is no code to guard against. The correct action is to
ensure the design question is answered at the start of the implementation task and that
a corresponding test is added as part of that task's Definition of Done. This OBS serves
as the institutional memory that makes that requirement explicit when the task is assigned.
The task author must reference OBS-004 when writing acceptance criteria for CoachingScheduler.

**OBS-004 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-005] Response to OBS-005 — PostgreSQL concurrency gap: deferred to migration task

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `titan/core/database.py`; confirmed `threading.Lock` +
  `check_same_thread=False` pattern is SQLite-specific. Read
  `tests/test_database_manager_thread_safety.py` and `tests/test_harden_db_concurrency.py`;
  confirmed both test exclusively against SQLite connection semantics. ADR-0044 accepted,
  migration task not yet open.

**Architect finding:**
The gap is correctly identified and structurally significant. The threading tests are
SQLite-correct and will remain green during migration even if the PostgreSQL adapter has
broken concurrency semantics, because they test a different code path. This is the classic
"test passes, feature broken" pattern at an abstraction boundary. The gap is not a current
defect — it is a future defect that becomes possible the moment a second DB adapter exists.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Trigger: PostgreSQL migration task opens — concurrency validation for the new adapter must be an explicit acceptance criterion in that task's Definition of Done |

**Rationale:**
Writing PostgreSQL concurrency tests now would require a live PostgreSQL instance in CI,
which is premature and outside scope before the migration task is open. The correct action
is to ensure the migration task's acceptance criteria explicitly include: (a) concurrency
stress tests for the PostgreSQL adapter equivalent to the existing SQLite suite, and (b)
a note that the SQLite tests do not provide coverage for the new adapter. This OBS is the
institutional memory that surfaces that requirement when the task is assigned.

**OBS-005 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-006] Response to OBS-006 — Payload round-trip gap: deferred to FastAPI task

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_operator_console_dashboard.py`; confirmed all
  assertions are Python dict / value comparisons with no JSON serialization step.
  Read `titan/ui/operator_console.py`; confirmed payloads contain `datetime` fields
  (e.g. `last_updated`, session timestamps) that have no direct JSON representation
  and would require explicit serializer configuration in FastAPI. ADR-0013 accepted,
  FastAPI implementation not yet started.

**Architect finding:**
The gap is real and correctly scoped. The four payload types in `OperatorConsoleService`
(dashboard, session explorer, override workflow, calibration review) all contain Python
types that require explicit serialization handling in FastAPI (`datetime` → ISO 8601 string,
`Enum` → value string, `None` in typed fields → `null`). The existing dict-shape tests
will pass regardless, providing false confidence. A round-trip test (Python payload →
`json.dumps` → `json.loads` → assert shape + value) is a lightweight, deterministic guard
that will catch exactly this class of failure.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Trigger: FastAPI implementation task opens — round-trip serialization tests for all four OperatorConsole payload types must be an explicit acceptance criterion in that task |

**Rationale:**
The guard is well-defined (≤ 30 lines per payload type, deterministic, actionable failure
messages) and meets all four criteria for an automated guard. It is not written now because
the FastAPI layer does not exist yet — there is no serialization boundary to test against.
When the task opens, this OBS provides the precise requirement: one round-trip test per
payload type, covering `datetime`, `Enum`, and `None`-typed field serialization. No ADR
is required — this is an implementation-time test coverage requirement, not an architectural
decision.

**OBS-006 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-007] Response to OBS-007 — ADR deliverable drift: process rule added to AGENTS.md

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `TECHNICAL_DEBT.md` T5-08 Resolution section: lists only
  `PostgreSQLDatabaseManager`, backend parity tests, and `get_database_manager()`. Read
  `docs/adr/0044-postgresql-migration-phase8a-entry-gate.md` D1–D9 table: confirms D1–D5,
  D7–D9 have no corresponding implementation. Grepped codebase for `persistence.py`,
  `alembic/`, `test_athlete_rls_isolation`: none found. Acceptance gate in T5-08 entry
  references these non-existent paths — gate was not run at closure time.

**Architect finding:**
The observation is factually correct and fully verified. The drift is:
1. **Real:** D1–D5, D7–D9 of ADR-0044 are not implemented.
2. **Caused by a process gap:** The task closure protocol has no step that requires verifying
   each numbered ADR deliverable before setting status to RESOLVED. The acceptance gate is
   written as a shell command block, not as a per-deliverable checklist — making it possible
   to skip gate execution by inspection-only closure.
3. **Detected correctly by QA:** The Opus QA verdict (FAIL) was the correct signal.

T5-08 status has been corrected to ⚠️ PARTIAL. T5-08-B has been created in `TECHNICAL_DEBT.md`
with D1–D5, D7–D9 as binary acceptance criteria and an explicit concurrency acceptance
criterion per OBS-005 (which had already registered this risk as a trigger for the migration task).

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | Process rule: ADR Deliverable Checklist — mandatory at task closure when task references an ADR with a numbered deliverable table. Recorded in AGENTS.md §HARD GATE addendum (see below). |

**Process rule — effective immediately:**

When any task (Tn-xx) references an ADR that contains a numbered deliverable table (e.g.
ADR-0044 D1–D9, ADR-0018 Phase A/B checklist), the task entry in `TECHNICAL_DEBT.md` MUST
include an **ADR Deliverable Checklist** section before it may be set to RESOLVED:

```markdown
**ADR Deliverable Checklist (ADR-XXXX):**
| # | Deliverable | Status |
|---|---|---|
| D1 | <description> | ✓ DONE / ✗ NOT DONE |
| D2 | <description> | ✓ DONE / ✗ NOT DONE |
...
```

Rules:
- Any ✗ NOT DONE deliverable blocks RESOLVED status. Task must be PARTIAL or OPEN.
- If a task intentionally implements a subset, status is PARTIAL + a successor task covers
  the remaining deliverables (the T5-08 → T5-08-B split is the canonical pattern).
- The checklist is filled in by Codex at closure time, verified by QA, not set by assertion.

This rule is a **HARD GATE addendum** — same severity as the existing three-gate protocol
(ruff / pytest-W / pytest). It applies to all open Phase 8 tasks that reference ADRs with
deliverable tables: T5-08-B (ADR-0044), T5-16-A (ADR-0046).

**Rationale:**
The three existing mandatory gates (ruff, pytest -W error, pytest) verify code correctness
but cannot verify that all ADR deliverables were implemented — that requires a semantic
cross-reference that only a human checklist can provide. The process gap revealed by T5-08
is structural: a task can pass all three gates and still miss 7 of 9 ADR deliverables.
The ADR Deliverable Checklist closes this gap at the lowest possible cost (one table per ADR,
filled at closure time) without adding new tooling or CI complexity.

**OBS-007 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-001] Response to OBS-001 — Test layer markers: deferred to Phase 9 housekeeping

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `pyproject.toml` markers config (only `timeout` registered);
  confirmed via grep that no `@pytest.mark.unit/integration/governance` calls exist in the
  118 test files across root and `tests/`.

**Architect finding:**
The observation is factually correct. The suite has no layer taxonomy beyond filename
conventions. However, the cost/benefit ratio at this point in the project is unfavourable:
adding markers retroactively to ~118 files and ~1780 tests is a mechanical but large-scope
refactor with no change to test logic. The diagnostic benefit (faster `pytest -m governance`)
is real but not pressing at 1780 tests — the current `tests/test_phase*.py` / `tests/test_p0_*.py`
naming convention provides adequate targeted-run granularity via `pytest tests/test_p0*.py`.
Phase 8 priorities (PostgreSQL migration gate, multi-sport adapter, operator console) outweigh
a marker taxonomy refactor. This is a valid Phase 9 / housekeeping item.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Assigned to Phase 9 housekeeping — T5 marker taxonomy for unit/integration/governance layers |

**Rationale:**
Phase 8 is OPEN with G1–G11 entry gate criteria. A test infrastructure refactor of this scope
belongs in a dedicated housekeeping slot, not as a Phase 8 item. The existing filename convention
is sufficient for now. When the suite exceeds ~3000 tests (likely Phase 9), the cost of unmarked
tests becomes more acute and the refactor investment pays off more clearly. No ADR is required —
this is an engineering convenience, not an architectural decision.

**OBS-001 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-002] Response to OBS-002 — CI pattern brittleness: accepted trade-off, no action

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_claude_md_integrity.py` lines 31, 42–44, 83,
  92, 133, 141–149; confirmed 6 regex patterns tightly coupled to exact markdown surface form.

**Architect finding:**
The observation is factually correct. The brittleness is real and intentional. Doc integrity
tests are effective precisely because they are tight: a loose pattern (e.g. matching any number
near the word "modules") would miss the exact drift cases these tests were designed to catch.
The trade-off was made explicitly when these tests were introduced (T4-22 / ADR-0025): the
accepted cost is that legitimate reformatting of doc sections requires updating the test.
This is the correct engineering choice — it forces any doc reformatting to be a conscious act
that also updates the guard, rather than silently breaking the invariant.

No false positive has been observed. The markdown sections guarded by these patterns
(CLAUDE.md Key Files, ADR list, TECHNICAL_DEBT.md Phase header) have a de-facto stable
format because they are also machine-read by the test suite — there is no incentive to
reformat them casually.

A schema layer (YAML frontmatter, structured sections) would be a heavier investment with
no meaningful safety gain over the current approach for a project of this size and team.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Pattern brittleness is an accepted, deliberate trade-off of doc integrity test design (ADR-0025); no change warranted |

**Rationale:**
Loosening the patterns would reduce detection sensitivity. Introducing a schema layer is
disproportionate to the risk. The current approach is the right balance for Phase 8.
The observation is noted for Phase 9 reconsideration only if false-positive rate increases.

**OBS-002 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-003] Response to OBS-003 — Snapshot drift already covered, no gap identified

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_claude_md_integrity.py` lines 25–158; confirmed
  5 independent automated drift guards covering: ADR count, module count, test count,
  key file path existence, and phase state label parity between CLAUDE.md and TECHNICAL_DEBT.md.

**Architect finding:**
The observation is correct that snapshot drift is a risk — and also correct that it is already
substantially addressed. The 5 existing guards in `test_claude_md_integrity.py` cover every
quantifiable snapshot element in CLAUDE.md:
- Counts (ADR, module, test) → machine-checked
- File existence (Key Files table) → machine-checked
- Phase state (OPEN/CLOSED parity) → machine-checked

The remaining un-automated content (narrative descriptions, algorithm references, module
descriptions) is inherently prose and cannot be automatically validated against code without
building a documentation generator — which is disproportionate. The CLAUDE.md is explicitly
designated a "context snapshot" not a live specification; its narrative content is expected
to require periodic manual review, which is appropriate.

No specific gap has been identified by the OBS that is not already covered. The observation
is a confirmation that the current approach is sound, not a finding that requires new work.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | All quantifiable snapshot elements are already machine-checked; no residual gap identified |

**Rationale:**
Extending automated coverage to prose content would require a documentation generator or
LLM-based diff, which is out of scope for Phase 8 and disproportionate to the risk.
The existing 5 guards are the correct stopping point. The observation validates the existing
design — it does not reveal a deficit.

**OBS-003 marked:** REVIEWED
**Status:** PROCESSED

---

## Archive

> **Per-phase archive policy:** When a Phase is declared CLOSED (A-SCRATCHPAD-3), all REVIEWED
> OBS + PROCESSED DEC pairs for that phase are moved to a dedicated archive file:
> `archive/scratchpad_phase_X.Y.md`. The Archive section below retains only the last Phase's
> entries for immediate reference. Earlier phases live in `archive/`. The archive is never
> deleted — it is the engineering memory of cross-session findings that shaped
> `TECHNICAL_DEBT.md` decisions.

> **Archive note (2026-03-08):** OBS-001 / OBS-002 / OBS-003 and their DECs were processed
> during Phase 8 (session: future-maintenance-notes). OBS-001 resulted in a DEFERRED Phase 9
> debt entry (test layer marker taxonomy). OBS-002 and OBS-003 resulted in NO_ACTION.
> Full entries remain in NON-BLOCKING Queue section above (marked REVIEWED) until Phase 8 CLOSED.

---

*Protocol v1.1 — Last updated: 2026-03-07. Structural upgrade: BLOCKING/NON-BLOCKING queues
(mechanical gate via `scripts/check_scratchpad.sh`), CLARIFICATION_NEEDED state, per-phase
archive policy. Replaces STATUS-field-only v1.0.*
