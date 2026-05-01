# ADR-0040: Athlete Identity Isolation

Date: 2026-04-28
Status: Pending — referenced by INV-04 and titan/core/persistence.py. Author in Phase 13.

## Context
`TECHNICAL_DEBT.md` and `AGENTS.md §16.10` reference ADR-0040 as the decision
record for the athlete identity isolation invariant (INV-04). This invariant
requires that no governance decision, training recommendation, or persistence
call can proceed without a verified `athlete_id` bound to the session context.

The invariant is enforced by:
- `titan/core/persistence.py` — PersistenceAdapter ABC parameter contract
- `titan/orchestration/daily_coach.py` — coaching_pipeline athlete_id binding
- `tests/test_athlete_isolation_invariant.py` — CI enforcement (G-CI-07)

This ADR number was reserved to document the architectural decision but was not
formally authored during the initial multi-athlete implementation (ADR-0046).

## Decision
N/A — pending formal authoring in Phase 13.

## Consequences
Until this ADR is authored, the invariant is enforced by the CI gate
`G-CI-07` in `ci.yml` and by `AGENTS.md §16.10` (rules A40-1 to A40-4).
Any relaxation of the invariant requires this ADR to be authored first and
must reference the specific A40-x rule being modified.
