# ADR-0061: Owner Working Rules — documents updated in the same PR, DECISIONS.md and CHANGELOG.md

**Status:** PROPOSED (accepted on merge of this PR by Zaf)
**Date:** 2026-10-09
**Author:** Zaf (Owner) / Claude (Design Authority)
**Related:** AGENTS §1.2 (RP-7), §3.6, §12.3, §12.4; `PROGRESS.md`; plan "Phase 2" of 2026-10-09

---

## Context

On 2026-10-09 Zaf (Owner, Architect) set the working rules for the rest of the refactor and
for the work after it. Among them:

- every task is one branch and one small PR; merge only on Zaf's explicit instruction; never
  push to `main`, never force-push, never rewrite history;
- each PR updates, in the same PR: `PROGRESS.md` (what was done, what remains, open PRs, open
  decisions), `DECISIONS.md` (technical decisions: what, why, rejected alternatives), the
  README and `docs/` whenever structure, run commands or behavior change, and `CHANGELOG.md`
  (one line per PR);
- at the end of each phase, all documents are checked against the code.

AGENTS §3.6 makes documentation Architect-owned and allows agent edits only for four listed
cases (test-count snapshot, ADR index row, debt entries, scratchpad OBS). Updating the README,
`docs/`, `DECISIONS.md` or `CHANGELOG.md` inside a task PR is outside that list, so every PR
that follows Zaf's rules would conflict with §3.6. Operating contract v7.9 §1.5 accepts
an ADR as the carrier of an Architect authorization; this is that ADR.

`DECISIONS.md` and `CHANGELOG.md` do not exist today. Decisions are spread over ADRs,
`PROGRESS.md` and `TECHNICAL_DEBT.md`; `CHANGES.md` stops at March 2026.

---

## Decision

### D1. Documents follow the change, in the same PR

An agent PR updates, in the same PR, the documents its own change makes untrue or incomplete:
`README.md`, files under `docs/`, `CLAUDE.md`, `PROGRESS.md`, `DECISIONS.md` and
`CHANGELOG.md`. The edit is limited to what the PR's change affects. Rewriting a document for
its own sake is a task of its own, named in the plan.

### D2. Two required records

- `DECISIONS.md` at the repository root: one entry per technical decision taken by an agent —
  what was decided, why, and which alternatives were rejected. Architectural decisions stay in
  ADRs; `DECISIONS.md` links to them instead of copying them.
- `CHANGELOG.md` at the repository root: one line per merged PR.

Both are created by the next task of the plan.

### D3. What does not change

- `AGENTS.md` and the operating contract stay Architect-owned (RP-7). An agent changes
  `AGENTS.md` only with verbatim text from an ADR, as this ADR does for the §3.6 row below.
- `governance_engine.py` stays architecture-locked (ADR-0009).
- Merge only on Zaf's explicit instruction. No push to `main`, no force-push, no history
  rewrite.

### D4. AGENTS §3.6 row (verbatim)

The following row is added to the table in AGENTS §3.6:

| Permitted edit | Trigger | Ref |
|---|---|---|
| `README.md`, `docs/`, `CLAUDE.md`, `PROGRESS.md`, `DECISIONS.md`, `CHANGELOG.md` — only what the PR's own change makes untrue or incomplete | Any task PR | ADR-0061 |

---

## Consequences

**Positive:** the documents stay true after every PR instead of drifting until a clean-up pass.
Every agent decision has one place to be found. Zaf's rules and AGENTS §3.6 no longer conflict.

**Neutral:** each PR carries a few extra lines of documentation.

**Negative:** documentation diffs appear in PRs that previously touched only code; reviewers
read slightly more.

---

## Approval

Approval: merge of this PR by Zaf (Architect).
