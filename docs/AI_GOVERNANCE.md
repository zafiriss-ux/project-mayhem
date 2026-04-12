# TITAN OS — AI Governance Document

**Version:** 1.1
**Date:** 2026-03-17
**Revision:** 2026-04-12 — §1/§2 agent role updated per AGENTS.md §28; §5 RLS operational caveat added; Opus audit findings recorded.
**Canonical location:** `docs/AI_GOVERNANCE.md`
**Authored by:** Architect (Claude operating in architectural session)
**Change Type:** architect-decision
**Referenced by:** `AGENTS.md §1`, `AGENTS.md §23`

> This document describes how AI agents are used in the TITAN OS engineering process,
> what decisions each role can and cannot make, where human oversight is enforced, and
> how decisions are traced. It is a traceability artifact — not a compliance filing.
>
> On any conflict between this document and `AGENTS.md`: **`AGENTS.md` wins.**

---

## §1 Agent Surface Map

TITAN OS uses three distinct AI agent surfaces in its engineering and operational process.
Each surface has a defined role, layer, and scope boundary.

| Agent | Role | Layer | Scope |
|-------|------|-------|-------|
| **Claude (Architect)** | Architectural advisor operating in sessions with the project owner | Design authority | ADR authorship, governance interpretation, task sequencing, escalation decisions, this document |
| **Codex / Claude Code** | Implementation engineer | Execution | Scoped task implementation, tests, mandatory gates, audit observations — Implementation Engineer for routine operations. Under AGENTS.md §28 (effective 2026-03-17), also holds architect authority for status closures, gate verification, and records passes. On any conflict: AGENTS.md wins. |
| **Opus QA** | Advisory test quality reviewer (PILOT-01) | Quality advisory | Category B test quality review for Path B tasks — verdict only, no implementation authority |

No AI agent has unilateral authority over canonical documents, ADRs, or governance gate logic.
All such changes require explicit architect authorization followed by human review via PR.

---

## §2 Role-to-Function Mapping

### What each role can decide

| Role | Can decide | Cannot decide without explicit authorization |
|------|-----------|----------------------------------------------|
| **Owner** | Work priorities, strategic direction, task assignment, deployment context | Architectural decisions, ADR authorship, governance gate changes — these require the Architect role |
| **Architect** (Claude in architectural session) | System design, ADR authorship, tier ordering, governance interpretation, scope approval, this document | Cannot bypass safety invariants, governance gates, or tier ordering — rules apply to architect equally (GOVERNANCE_PRINCIPLES.md §3) |
| **Codex** | Implementation of explicitly scoped tasks, test authorship, mandatory gate execution, audit observations | Design decisions, ADR authorship, canonical document edits beyond §3.6 and §12 permissions, closure wording, commit hash recording in canonical docs |
| **Records Steward** | `TECHNICAL_DEBT.md` closure wording, commit hash recording, OPEN↔RESOLVED integrity | Sequencing decisions, governance interpretation, architectural decisions |
| **Opus QA** | QA PASS / QA FAIL verdict with rationale for Path B tasks | Commit/push instructions, RESOLVED marking, next-task directives — these are out of QA role scope |

### The boundary that does not move

No AI agent may authorize its own scope expansion.
An agent that encounters an architectural decision point must stop and report — it may not proceed on its own judgment.
See `AGENTS.md §13.2` and `§14.1`.

---

## §3 Human Oversight Checkpoints

The following decision categories require explicit human authorization before any AI agent proceeds.
"Human authorization" means the project owner confirming the action in the architectural session — not an instruction inferred from prior context.

| Decision category | Authorization required | Mechanism |
|-------------------|----------------------|-----------|
| Governance gate logic changes | Human-authorized | ADR required; architect authors; human reviews PR |
| ADR authorship | Human-authorized | Architect role exercised in session with owner; owner confirms |
| Schema topology changes | Human-authorized | ADR required; Cooling-Off Protocol applies (AGENTS.md §14.3) |
| Tier ordering changes | Human-authorized | Architect ruling required; cannot be inferred from task description |
| Phase boundary transitions | Human-authorized | Architect confirms all gate criteria met before Codex begins next Phase |
| Codex implementation | AI-executed, human-reviewed | Codex implements; owner reviews PR before merge to main |
| Opus QA verdict | AI-advisory, human-authorized to act | Verdict is input; architect decides whether to proceed, fix, or escalate |
| Records closure (RESOLVED marking) | AI-assisted (Records Steward), human-confirmed via PR | Records Steward prepares; owner merges |
| Deployment to third-party athletes | Human decision | Requires risk re-assessment (see §5) before any such deployment |

### What does not require human authorization per-instance

Routine Codex execution within an architect-confirmed brief (code, tests, gates) does not require per-step human authorization.
The authorization is the brief itself.
The human oversight checkpoint is the PR review before merge to `main`.

---

## §4 Decision Traceability

TITAN OS maintains a three-artifact audit trail for all engineering and governance decisions.
These artifacts are version-controlled and constitute the canonical record.

| Artifact | What it traces | Location |
|----------|---------------|----------|
| `TECHNICAL_DEBT.md` | All open and resolved technical debt items; task status; closure records with commit hashes; task learnings | Project root |
| `SCRATCHPAD.md` | Engineering observations (OBS) from Codex; architect decisions (DEC) in response; routing from finding to debt entry | Project root |
| ADR register (`docs/adr/`) | All architectural decisions with context, rationale, alternatives considered, and consequences | `docs/adr/README.md` index |

**Traceability chain for any implementation decision:**

Finding (OBS in SCRATCHPAD.md)
→ Architect DEC (SCRATCHPAD.md)
→ Debt entry (TECHNICAL_DEBT.md)
→ Architect brief (TECHNICAL_DEBT.md task entry)
→ Codex implementation (PR)
→ Closure record (TECHNICAL_DEBT.md, Records Steward)

**Traceability chain for any architectural decision:**

Architectural question (session or SCRATCHPAD OBS)
→ Architect ruling (session output or DEC)
→ ADR (docs/adr/)
→ AGENTS.md or TECHNICAL_DEBT.md reference
→ Implementation brief (if applicable)

No decision that affects governance gate logic, schema topology, or tier ordering exists outside these artifacts.
Ephemeral session messages, chat logs, and GitHub issue comments are not canonical — if a decision matters, it is in one of the three artifacts above.

---

## §5 Deployment Context and Risk Re-Assessment Trigger

### Current deployment context

TITAN OS is currently operating as a **single-athlete, owner-operated proving ground**.

- One athlete (the owner)
- No third-party data subjects
- No commercial deployment
- AI Act risk classification: not yet applicable at current scale
- GDPR exposure: minimal (owner's own health data, self-hosted)

### Target deployment context

The canonical architecture targets **future multi-athlete, third-party deployment** once the governance and operating model stabilize (Phase 9+).

At that point:
- Multiple athletes whose health data is processed by the system
- Coach role with access to third-party athlete data
- Commercial relationship between operator and athletes
- GDPR exposure: significant (health data of third parties, right-to-erasure, consent)
- AI Act exposure: requires re-assessment (see below)

### Risk re-assessment trigger

**Before any deployment involving third-party athletes** (i.e., athletes who are not the system owner), the following must be completed:

1. AI Act risk classification review — determine whether TITAN OS qualifies as a high-risk AI system under Annex III, or falls under GPAI provisions, given the specific deployment context at that time.
2. GDPR Data Protection Impact Assessment (DPIA) — required when processing health data (special category under Art. 9 GDPR) of third parties at scale.
3. Consent mechanism verification — `consent_log` table (T5-08-B D9) must be operational and consent must be recorded before any third-party athlete data is processed.
4. Audit trail completeness check — verify that `coach_audit_log` (T5-13) and override logs (ADR-0042) are operational and complete.

This re-assessment is not scheduled — it is **triggered by the deployment decision**.
No compliance action is required before that trigger fires.

### What is already in place

The following governance infrastructure is already implemented and satisfies baseline traceability requirements for future compliance:

| Requirement | Implementation |
|-------------|---------------|
| Athlete data isolation | PostgreSQL RLS (ADR-0044) + application-level isolation check (ADR-0048) (schema-level implementation; operational only under PostgreSQL backend — current single-athlete deployment uses SQLite) |
| Right-to-erasure readiness | `DELETE FROM * WHERE athlete_id = ?` + RLS completeness guarantee |
| Consent recording | `consent_log` table (T5-08-B D9) |
| Coach action audit trail | `coach_audit_log` (T5-13) |
| Human override record | Override log + `record_override_signal` (ADR-0042) |
| AI decision traceability | `governance_outcomes` table + OutcomeTracker (ADR-0035) |
| Model calibration metadata | `model_calibration_metadata` table (T5-07, ADR-0033) |

---

## §6 Revision Log

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-03-17 | Architect | Initial creation — Friday Governance Pass output; minimal traceability backbone |
| 1.1 | 2026-04-12 | Claude Code (records pass) | §1/§2 agent role updated per AGENTS.md §28; §5 RLS operational caveat added; Opus audit findings recorded. |
