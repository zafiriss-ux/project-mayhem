# ADR-0040 — Athlete Identity Isolation

**Status:** Accepted
**Date:** 2026-05-08
**Refs:** ADR-0033 (multi-athlete architecture), ADR-0046 (DailyCoach multi-athlete model),
         INV-04, `AGENTS.md §16.10`, `titan/core/persistence.py`

## Context

TITAN OS supports multiple athlete profiles (ADR-0033 Layer 3). Without explicit
isolation, a query or governance decision for athlete A can silently return data
belonging to athlete B. This class of bug is invisible to unit tests that run
with only a single seeded athlete and would only manifest in production with
two or more registered athletes.

The invariant (INV-04) was enforced informally during ADR-0046 implementation
but was never captured as a formal architectural decision. This ADR formalises
the contract and the CI enforcement mechanism.

## Decision

### Rule A40-1 — Query binding

Every database query that returns athlete-scoped data MUST include a
`WHERE athlete_id = ?` binding with a runtime-supplied `athlete_id` parameter.
There are no exceptions to this rule for production query paths.

### Rule A40-2 — PersistenceAdapter contract

The `PersistenceAdapter` ABC (`titan/core/persistence.py`) exposes no method that
returns athlete-scoped data without accepting `athlete_id: str` as a required
positional parameter. Implementations that omit the parameter are rejected at
ABC enforcement time.

### Rule A40-3 — DailyCoach binding

`coaching_pipeline()` in `titan/orchestration/daily_coach.py` binds `athlete_id`
at the outermost call site. All inner calls receive it explicitly; no call may
look it up from ambient state, class attributes, or environment variables.

### Rule A40-4 — Exemption annotation

Modules that intentionally operate without an `athlete_id` binding (system
initialisation, schema migrations, owner-shortcut single-athlete mode) MUST
carry the comment:

    # ADR-0033-L3-D-RESOLVED: single-athlete shortcut

This annotation is machine-readable; the G-CI-07 CI gate (`ci.yml`) asserts
that every unannotated DB access in governance-critical paths carries an
explicit `athlete_id` binding.

## Exemption register

The maintained exemption list and annotation protocol are in `AGENTS.md §16.10`.
Changes to the exemption list require an architect decision entry in
`SCRATCHPAD.md` before the annotation is added.

## Enforcement

- **Runtime**: `PersistenceAdapter` ABC enforces the parameter contract.
- **CI (G-CI-07)**: `tests/test_athlete_isolation_invariant.py` + `ci.yml`
  `invariant-athlete-isolation` job. Runs on every push to `main` and `claude/**`.
- **Code review**: any new DB method returning athlete data without `athlete_id`
  is a mandatory rejection in PR review.

## Consequences

- New DB methods that return athlete-scoped data must accept `athlete_id: str`
  as a required parameter.
- Schema migrations must include `athlete_id` column on all new athlete-facing
  tables (default `'owner'` for backwards compatibility with single-athlete
  installations).
- Multi-athlete reporting (e.g. coach dashboards) that legitimately aggregates
  across athletes must be implemented in a dedicated reporting layer, not by
  omitting the `athlete_id` filter from existing methods.
