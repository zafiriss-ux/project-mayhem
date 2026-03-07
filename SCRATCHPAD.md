# TITAN OS — Engineering Scratchpad (Πρόχειρο)

**Protocol version:** 1.0
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
- `CLEARED` — all OBS entries processed; Codex may continue (Claude will reset to IDLE after clearing)

**IMPORTANT — Codex:** When you set status to `REVIEW_REQUESTED`, **stop and wait**. Do not begin
a new task until Claude sets status to `IDLE` or `CLEARED`. This is not optional.

**IMPORTANT — Claude:** When status is `REVIEW_REQUESTED` at session start, process all PENDING
OBS entries before assigning any new task to Codex. See §A-SCRATCHPAD-1 in `CLAUDE.md`.

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

### Claude → Codex (DEC entries)

Claude writes **Decision (DEC)** entries in response to OBS entries. Each DEC:
- References the OBS it responds to
- States the architect's verified finding
- Records the decision taken (new debt entry / ADR / no action / defer)
- Marks the corresponding OBS as `REVIEWED`

DEC IDs match the OBS they respond to: `DEC-001` responds to `OBS-001`.

### Lifecycle of an OBS entry

```
Codex writes OBS → status: REVIEW_REQUESTED
  → Claude reads + verifies findings
  → Claude writes DEC + creates TECHNICAL_DEBT.md entries if needed
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
| A-SCRATCHPAD-1 | Claude | At every session start (check status before assigning tasks) |
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

**Rationale:**
<Why this decision was made. Reference ADRs, existing constraints, or risk analysis.>

**OBS-XXX marked:** REVIEWED
**Status:** PROCESSED
```

---

## Pending Observations

*No pending observations.*

---

## Architect Review Log

*No architect reviews yet.*

---

## Archive (REVIEWED + PROCESSED entries)

*No archived entries yet.*

---

*This document is reset to IDLE state between phases. OBS/DEC entries for closed phases
are moved to the Archive section. The Archive is never deleted — it is the engineering
memory of cross-session findings that shaped TECHNICAL_DEBT.md decisions.*

*Last updated: 2026-03-07 — Document created. Protocol v1.0.*
