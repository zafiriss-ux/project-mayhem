# ADR-0015 — SQLite Retention Strategy and Phase 8 Data Lifecycle Gate

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-03-03 |
| Owners | TITAN OS architecture/governance |
| Scope | `governance_outcomes`, `training_log`, Phase 8 multi-athlete feasibility |

## Context

`governance_outcomes` and `training_log` currently grow without a retention policy.
This is acceptable for the current runtime only if TITAN OS remains intentionally
single-athlete and single-lifetime.

Phase 8 introduces multi-athlete workloads (10–50 athletes) and therefore changes
SQLite growth, backup, and operational-risk assumptions. If this decision is not
made early, retention and archival behavior will be decided ad-hoc under delivery
pressure.

## Decision

### Decision record for T5-01

The explicit decision requested in T5-01 is **YES**:
TITAN OS is intentionally constrained to a **single-athlete, single-lifetime**
operating model for the current architecture phase.

If/when this becomes **NO** (Phase 8 multi-athlete execution), the Phase 8 gate
below becomes a hard prerequisite before implementation work can start.

1. **Current architectural constraint (effective now):** TITAN OS is treated as
   **single-athlete, single-lifetime** until Phase 8 execution starts.
2. **Retention policy for current scope:**
   - No automatic pruning is introduced now.
   - `governance_outcomes` and `training_log` remain append-only.
   - SQLite is expected to handle this scale for one athlete over multiple years.
3. **Phase 8 gate (mandatory before implementation):**
   Before any multi-athlete work begins, a dedicated ADR must define and lock:
   - Raw-data retention window (for example: rolling N months + archive)
   - Storage topology decision (per-athlete SQLite files vs shared database)
   - Archival/export format (CSV, JSON, or SQLite snapshot/copy)
   - Restore and audit-read procedure for archived data

No Phase 8 implementation may start until that ADR is accepted.

**Closed by ADR-0067 D2 (2026-10-16):** shared SQLite, no pruning while active, deletion 30 days
after `/stop`, one JSON export per athlete, restore followed by the deletion records.

## Consequences

### Positive
- Prevents rushed data-lifecycle choices under Phase 8 pressure.
- Preserves current simplicity for the single-athlete operating model.
- Makes Phase 8 feasibility explicitly gated by data architecture.

### Neutral
- Existing tables continue to grow as designed in current scope.
- No runtime behavior changes are introduced by this ADR alone.

### Negative / Risks
- If single-athlete scope expands unexpectedly before the Phase 8 gate is met,
  DB growth and operational burden may increase without lifecycle controls.

## Verification

- Roadmap includes Tier 5 note and references this ADR.
- Test coverage asserts that ADR-0015 documents:
  - single-athlete constraint
  - Phase 8 precondition gate
  - lifecycle decision dimensions (retention window, DB topology, archive format)

---

## Review Trigger

This ADR should be reviewed when:
- The Phase 8A PostgreSQL migration gate (ADR-0044) is declared complete.
- Daily row write rate in any SQLite table exceeds 10,000 rows/day for a sustained period.
- A second athlete profile is added to the system, invalidating the single-athlete scope assumption.
- A GDPR right-to-erasure request is received and cannot be fulfilled under the current schema.
