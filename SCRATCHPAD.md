# TITAN OS — Engineering Scratchpad (Πρόχειρο)

**Protocol version:** 1.1
**Architect-owned:** YES — Codex writes OBS entries; Claude writes DEC entries and controls status.
**Purpose:** Structured communication channel between Codex (engineer) and Claude (architect).
Codex writes raw engineering observations here. Claude reads, verifies, decides, and converts
them to clean tasks in `TECHNICAL_DEBT.md`. Neither party acts on observations alone.

---

## Document Status

```
STATUS: IDLE
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

*No non-blocking observations.*

---

## Architect Review Log

*No architect reviews yet.*

---

## Archive

> **Per-phase archive policy:** When a Phase is declared CLOSED (A-SCRATCHPAD-3), all REVIEWED
> OBS + PROCESSED DEC pairs for that phase are moved to a dedicated archive file:
> `archive/scratchpad_phase_X.Y.md`. The Archive section below retains only the last Phase's
> entries for immediate reference. Earlier phases live in `archive/`. The archive is never
> deleted — it is the engineering memory of cross-session findings that shaped
> `TECHNICAL_DEBT.md` decisions.

*No archived entries yet.*

---

*Protocol v1.1 — Last updated: 2026-03-07. Structural upgrade: BLOCKING/NON-BLOCKING queues
(mechanical gate via `scripts/check_scratchpad.sh`), CLARIFICATION_NEEDED state, per-phase
archive policy. Replaces STATUS-field-only v1.0.*
