# ADR-0024 — Canonical Lock Codes

**Status:** Accepted
**Date:** 2026-05-08
**Refs:** ADR-0009 (governance lock architecture), `titan/config/thresholds.py:CANONICAL_LOCK_CODES`

## Context

Governance gate decisions emit string lock codes that are consumed by
`apply_constraints()`, the Telegram briefing formatter, and `OutcomeTracker`.
Without a canonical machine-readable register, any agent or developer could
introduce undocumented lock codes that:

- bypass CI consistency checks (no known-codes assertion exists),
- produce untestable Telegram output (strings that appear nowhere in the codebase),
- corrupt `OutcomeTracker` analytics (unknown codes stored in `governance_outcomes`).

The frozenset was informally created during Phase 5 governance hardening but was
never formally decided or documented. This ADR formalises the decision retroactively
and establishes the mutation-test enforcement contract.

## Decision

1. All lock codes are declared in `titan/config/thresholds.py:CANONICAL_LOCK_CODES`
   (a `frozenset[str]`). This is the single source of truth.

2. No governance method may emit a lock code that does not appear in
   `CANONICAL_LOCK_CODES`. CI tests (`test_documentation_consistency.py` and
   `test_governance_integration.py`) assert this invariant via AST parse and
   runtime enumeration.

3. Adding a new gate requires all three of:
   - New code added to `CANONICAL_LOCK_CODES` in `thresholds.py`,
   - Provenance entry in `titan/config/evidence_registry.py`,
   - Mutation test update in `tests/test_governance_integration.py`.

## Canonical lock codes (SCHEMA_VERSION 16)

| Code | Gate | Severity |
|---|---|---|
| `HARD_STOP_SAFETY_GATES` | H1-H5 hard-stop composite | Hard stop |
| `VO2_ELIGIBILITY_GATE` | VO2max session eligibility | Hard stop |
| `FUELING_GATE_LOCK` | Pre-workout fuelling deficit (block) | Hard stop |
| `FUELING_GATE_FLAG` | Pre-workout fuelling deficit (warn) | Soft flag |
| `READINESS_2OF4_DOWNGRADE` | 2-of-4 subjective soft downgrade | Downgrade |
| `INTENSITY_GATE_RED` | Intensity governor red band | Hard stop |
| `INTENSITY_GATE_YELLOW` | Intensity governor yellow band | Downgrade |
| `PARASYMPATHETIC_GUARD` | AFI parasympathetic suppression | Downgrade |
| `OVERRIDE_LOCKDOWN` | Active override lockdown sentinel | Hard stop |
| `CS_CONFIDENCE_LOCK` | Critical Speed model below confidence floor | Soft lock |
| `PERSISTENCE_DEGRADED_CEILING` | DB write failure - conservative ceiling active | Ceiling |
| `STARTUP_DATA_CONFIDENCE_CEILING` | Cold-start / insufficient data ceiling | Ceiling |
| `FAIL_SAFE_LOCK` | Unhandled engine exception fallback | Hard stop |
| `DATA_MISSING_CONSERVATIVE_H2` | HRV data absent - conservative H2 treatment | Conservative |
| `DATA_MISSING_CONSERVATIVE_H3` | RHR data absent - conservative H3 treatment | Conservative |
| `DATA_MISSING_CONSERVATIVE_H4` | TSB data absent - conservative H4 treatment | Conservative |
| `DATA_MISSING_CONSERVATIVE_H5` | Fatigue data absent - conservative H5 treatment | Conservative |
| `DATA_VOID_CONSERVATIVE` | All biometric inputs absent - full conservative mode | Conservative |

## Consequences

- New gates must follow the 3-step protocol above before any code can emit the new code.
- Renaming a lock code requires updating `CANONICAL_LOCK_CODES`, all emission sites,
  and all `OutcomeTracker` analytics queries in one atomic commit.
- `governance_outcomes.locks_applied_json` rows written before a rename are not
  back-migrated; analytics queries must handle both old and new names during any
  transition window (document in migration notes).
