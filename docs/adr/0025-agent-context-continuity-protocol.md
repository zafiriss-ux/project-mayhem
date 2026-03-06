# ADR-0025 — Agent Context Continuity Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Master Risk Matrix — Risk #1 (Agent Context Drift) + Risk #17 (Self-Referential Prompt Decay)
**Phase:** 7.8 Hardening

---

## Context

### Risk #1 — Agent Context Drift (High probability, Medium severity)

AI agents (Claude Code and similar) assist with implementation on this codebase. Each
agent session begins with a fresh context window. The agent reads CLAUDE.md but has no
mechanism to verify that its mental model of the codebase matches the actual state.

Observable failure modes in previous sessions:
- Agent references module count ("49 modules") that was stale from an earlier audit.
- Agent proposes fix to an already-resolved debt item (e.g., T1-04 re-proposed after close).
- Agent generates lock code not in the canonical set ("DATA_CONFIDENCE_GATE" instead of
  a canonical code).
- Agent starts Tier N+1 work while Tier N items are still open (Rule E1 violation).

These failures are not agent intelligence failures — they are **context synchronisation
failures**. The agent operates on a stale map of the territory.

### Risk #17 — Self-Referential Prompt Decay (High probability, Medium severity)

CLAUDE.md is the primary context document. It is maintained by both humans and agents.
Over time, agents edit CLAUDE.md to reflect completed work — but the edits themselves
can introduce errors, stale references, or contradictions if the agent's context window
does not include the full current CLAUDE.md.

The failure mode is self-referential: an agent updates CLAUDE.md incorrectly → the next
agent reads the incorrect CLAUDE.md → produces work based on a corrupt prompt → updates
CLAUDE.md to reflect the corrupt work → decay accelerates.

### Current Mitigations (Insufficient)

1. `CLAUDE.md` — provides architecture context and rules E1–E5.
2. `TECHNICAL_DEBT.md` — authoritative debt register with status.
3. `AGENTS.md` — hard gate rules for commits and PRs.

These are static documents. They require the agent to read and interpret them correctly
at the start of every session. There is no machine-verifiable session start check.

---

## Decision

**Introduce a machine-verifiable Session Start Protocol and a CLAUDE.md integrity
check as part of the CI pipeline.**

### Protocol Component 1 — Mandatory Session Start Checklist (process)

Every agent session on this codebase begins with the following checks, in order:

```
AGENT SESSION START PROTOCOL
─────────────────────────────
S1. Read CLAUDE.md completely (not summary).
S2. Run: grep -c "OPEN\|PARTIALLY RESOLVED" TECHNICAL_DEBT.md
    → Confirms how many open debt items exist. All work must respect tier ordering.
S3. Run: python -m pytest -q --no-header 2>&1 | tail -1
    → Confirms baseline test count. Agent must not reduce this count.
S4. Run: ruff check . --statistics 2>&1 | tail -5
    → Confirms lint is clean. Agent must not introduce ruff errors.
S5. State explicitly: "Current open Tier N items: [list]"
    → Forces agent to surface the items before being given a task.
```

This checklist is machine-verifiable because the commands produce deterministic outputs.
An agent that skips S2–S4 is operating blind. The checklist is enforced via a
`AGENTS.md` update (see below).

### Protocol Component 2 — AGENTS.md Hard Gate Update

Add to `AGENTS.md` §SESSION_START:

```markdown
## SESSION START (mandatory — before any code change)

Run all five S1–S5 checks above and record the outputs in your first response.
Do not begin implementation until you have confirmed:
- Open debt items (S2)
- Baseline test count (S3)
- Lint is clean (S4)
- Active tier and open items (S5)

Failure to run these checks before implementation is a PROCESS VIOLATION.
```

### Protocol Component 3 — CLAUDE.md Integrity Check (CI)

Add a CI check that validates CLAUDE.md internal consistency:

```python
# tests/test_claude_md_integrity.py

def test_adr_count_in_claude_md_matches_files():
    """The ADR list in CLAUDE.md must match the actual files in docs/adr/."""
    adr_dir = Path("docs/adr")
    adr_files = sorted(f for f in adr_dir.glob("*.md") if f.name != "README.md")
    # Parse CLAUDE.md for ADR entries (lines matching "- `NNNN`")
    ...
    assert len(adr_files) == len(mentioned_adrs), (
        f"CLAUDE.md mentions {len(mentioned_adrs)} ADRs but {len(adr_files)} files exist"
    )

def test_module_count_in_claude_md_matches_filesystem():
    """The module count in CLAUDE.md must match actual titan/ module count."""
    ...

def test_open_tier_items_not_misrepresented():
    """CLAUDE.md phase status must not claim 'CLOSED' for phases with open items."""
    ...
```

This is the automation that prevents CLAUDE.md decay: if the document claims "Phase X:
CLOSED" but `TECHNICAL_DEBT.md` has open items from that phase, CI fails.

### Protocol Component 4 — Anti-Decay Rule for CLAUDE.md Edits

Any PR that modifies `CLAUDE.md` must:
1. Be reviewed by the architect (not auto-merged).
2. Pass `tests/test_claude_md_integrity.py` (new CI check).
3. Include a diff showing exactly what changed and why.

This is enforced via the PR template (T4-20, already in place).

### Engineering Execution Items

**T4-22** (new Tier 4 item):
> Create `tests/test_claude_md_integrity.py` with checks C1–C3 above.
> Update `AGENTS.md` with SESSION_START protocol.
> Add CI integration.

---

## Options Considered

### Option A — Human review of CLAUDE.md before each agent session
The architect reviews CLAUDE.md manually before authorising an agent session.

**Rejected as sole mitigation.** Does not scale. Every session requires architect
availability. Does not prevent in-session drift (agent modifying CLAUDE.md mid-session).

### Option B — Read-only CLAUDE.md (agents cannot modify it)
CLAUDE.md is treated as a read-only architectural document. Agents can propose changes
via PR only.

**Partially accepted.** This is the spirit of the PR template requirement. However,
the `test_claude_md_integrity.py` CI check makes this enforcement automatic. Both
mechanisms work together.

### Option C — Machine-verifiable session start + CI integrity check (SELECTED)
Minimal friction for the engineer; maximum signal for the architect. The session start
protocol is a checklist that takes <60 seconds. The CI check is automated and cannot
be skipped.

---

## Consequences

**Positive:**
- Agent context drift is detected at session start, not after a damaging PR is opened.
- CLAUDE.md decay is caught in CI before merge.
- The session start protocol creates a shared baseline between the agent and the
  architect at the start of every interaction.

**Neutral:**
- The session start protocol adds ~60 seconds of overhead to each agent session.
- Agents must be instructed to follow the protocol in each task description.

**Negative:**
- `test_claude_md_integrity.py` is somewhat fragile (depends on CLAUDE.md format).
  If CLAUDE.md is reformatted, tests may need updating. This is acceptable — the
  test update is the signal that the format changed.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0024 | Documentation drift prevention — this ADR focuses on CLAUDE.md specifically; ADR-0024 covers the broader technical docs. Complementary. |
| ADR-0021 | Governance evolvability — mutation tests detect semantic drift in gate code; this ADR detects context drift in agent behaviour. Complementary. |

---

## Status

Accepted. Engineering execution: **T4-22** (Tier 4 — maintainability; independent).
