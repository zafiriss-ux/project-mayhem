# TITAN OS — Governance Principles

**Version:** 1.0
**Date:** 2026-03-13
**Canonical location:** `GOVERNANCE_PRINCIPLES.md` (project root)
**Referenced by:** `AGENTS.md §1`, `CLAUDE.md §Key Files`

> These principles are extracted from the engineering contract (`AGENTS.md`) and the
> scratchpad protocol (`SCRATCHPAD.md`). They are not new policy. They are the existing
> rules stated in standalone form so they can be referenced without reading the full contract.
>
> On any conflict between this document and `AGENTS.md`: **`AGENTS.md` wins.**

---

## 1. Owner Proposal Guardrail

The project owner may propose any change. No proposal is self-authorising.

Every proposal to change the architecture — whether from an agent, an engineer, or the
architect — must complete the three-part Change Justification before any code is written
(`AGENTS.md §14.2`):

```
CHANGE JUSTIFICATION
Problem        : What is broken or insufficient with the current design?
Proposed change: What specifically will change?
Why necessary  : Why is the current design insufficient?
ADR reference  : ADR-XXXX — or "new ADR required" if none exists
```

If the justification cannot be completed in full, the change does not proceed.

Good intentions are not sufficient authorisation. Urgency framing ("just quickly",
"let's just change") is a recognised conflict signal (`AGENTS.md §14.1`), not an override.

---

## 2. Engineering Ctrl-Z

Every major change to core governance must be reversible before it is merged.

The Cooling-Off Protocol (`AGENTS.md §14.3`) is the minimum form of reversibility
insurance: a major change is proposed in Session N, reviewed in Session N+1 or later,
and only then approved and implemented. No code is written in Session N.

**Definition of major architectural change:** any change that requires a new ADR,
introduces a new module boundary, changes DB schema topology, or affects governance gate
logic.

The one-session pause costs nothing when the change is truly necessary. It catches
nearly everything that is not.

**Bypass condition (narrow):** The cooling-off period may be waived only when the
architect explicitly states `COOLING-OFF WAIVED — [reason]` and the reason describes
an active production incident or data integrity failure.

Minor changes (bug fixes, test additions, constant additions) are always exempt.

---

## 3. Architect Constrained by Invariants

The architect role does not grant authority to bypass safety invariants, governance
gates, or tier ordering.

From `AGENTS.md §14` (preamble):
> These rules exist to protect the project from the most common source of architectural
> damage: good intentions executed at the wrong moment. **They apply to agents and to the
> architect alike.**

An implementation agent MUST challenge any instruction — including architect instructions
— that contradicts the current architecture, an existing ADR, or any rule in `AGENTS.md`
(`AGENTS.md §14.1`). Silence is not compliance; it is a failure of responsibility.

The physiological governance gates (`titan/science/governance_engine.py`) are likewise
non-bypassable: hard stops cannot be suppressed by any role, any session, or any
framing (`AGENTS.md §16.1`, `titan/config/thresholds.py`).

---

## 4. Rules Decide

Outcomes are determined by documented rules, not by role authority, session context,
or urgency framing.

From `AGENTS.md` (opening statement):
> Rules are non-negotiable. Deviations are bugs in the engineering process, not
> acceptable trade-offs.

When a rule and a role instruction conflict, the rule prevails. When two rules appear
to conflict, the resolution order is:

1. `AGENTS.md` — process rules (highest authority on process)
2. `TECHNICAL_DEBT.md` — operational state (highest authority on task status and phase state)
3. `CLAUDE.md` — context snapshot (authoritative for architecture notes and module inventory)
4. This document — extracted principles (consistent with the above; subordinate to all three)

No role (owner, architect, agent) may unilaterally declare a rule inapplicable without
following the ADR process to formally revise it.

---

## Cross-References

| Principle | Canonical source in AGENTS.md |
|-----------|-------------------------------|
| Owner Proposal Guardrail | §14.2 Change Justification Requirement |
| Engineering Ctrl-Z | §14.3 Cooling-Off Protocol |
| Architect Constrained by Invariants | §14 preamble + §14.1 Agent Challenge Rule |
| Rules Decide | Opening statement + §4 Tier Ordering + §16.1 Governance Evolution Protocol |

For the out-of-scope routing rule (Engineer → SCRATCHPAD → DEC → TECHNICAL_DEBT),
see `SCRATCHPAD.md §Canonical Routing Rule`.
