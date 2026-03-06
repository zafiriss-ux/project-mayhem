# ADR-0040 — Athlete Identity as First-Class Architectural Invariant

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Architect Directive V8 — Decision 1: Lock athlete profile as system core
**Phase:** IMMEDIATE — effective from this commit forward, all phases
**Supplements:** ADR-0033 (multi-athlete architecture — Layer 3 implementation); ADR-0015
(SQLite retention); ADR-0016 (multi-sport scope)

---

## Context

TITAN OS was built for one athlete. Every module, every SQL query, every test fixture
assumes there is exactly one athlete and makes no effort to isolate that assumption.
This is acceptable today. It is **not acceptable as a forward architectural posture**.

ADR-0033 correctly deferred the multi-athlete *implementation* to Phase 9. However
ADR-0033 did not establish a hard invariant that the codebase must not grow new
cross-athlete assumptions in the interim. The result: every commit between now and
Phase 9 is a potential deposit of single-athlete assumptions that will become
surgical debt at Phase 9 entry.

### What "athlete isolation" means architecturally

Not "support multiple athletes now."

It means: **no module may embed a structural assumption that there is only one athlete,
if that assumption is not explicitly documented as a known single-athlete shortcut.**

Concretely:

| Pattern | Status |
|---|---|
| `db.get_hrv_today()` — implicit athlete_id = the only athlete | **Banned for new code** |
| `db.get_hrv_today(athlete_id="default")` — explicit, documented default | Allowed (single-athlete current default) |
| Hardcoded calibration constant with no athlete reference | **Banned for new science code** |
| Hardcoded calibration constant annotated `# single-athlete default; see ADR-0040` | Allowed |
| `governance_outcomes` rows with no `athlete_id` column | **Banned after T1-22 closes** |
| Test fixtures that assume a single athlete without marking the assumption | **Banned for new tests** |

This is not about building multi-athlete features. It is about **not building isolation
debt into new code** while the multi-athlete architecture is pending.

---

## Decision

**Declare athlete identity isolation an architectural invariant, effective immediately.
All new code added after this ADR must be isolation-aware. Existing violations are
tracked debt (not blocking), but must not be compounded.**

### Invariant Statement (machine-verifiable)

> No public method in any `titan/` module may read, write, or evaluate athlete
> physiological data without accepting or deriving an `athlete_id` parameter,
> **except** in modules explicitly annotated with `# ADR-0040-SINGLE-ATHLETE-SHORTCUT`
> and listed in the exemption register below.

### Exemption Register (current single-athlete shortcuts — known and documented)

The following modules are exempt until Phase 9 isolation work (T5-07 Layer 3):

| Module | Shortcut | Reason |
|---|---|---|
| `titan/core/database.py` | All queries implicit to the single athlete | Phase 9 migration target |
| `titan/orchestration/daily_coach.py` | No athlete_id threading | Phase 9 migration target |
| `titan/science/*.py` | No athlete_id in method signatures | Phase 9 migration target |
| `titan/features/*.py` | No athlete_id in method signatures | Phase 9 migration target |
| `titan/integrations/garmin_sync.py` | Syncs single athlete's Garmin account | Phase 9 migration target |

**Every file in the exemption register must carry this exact comment at module level:**
```python
# ADR-0040-SINGLE-ATHLETE-SHORTCUT: This module assumes a single active athlete.
# Multi-athlete isolation is deferred to Phase 9 (ADR-0033 Layer 3, T5-07).
# Do NOT introduce new structural coupling that would be harder to isolate later.
```

### Rules for New Code (HARD — no exceptions without explicit ADR approval)

**Rule A40-1 — No new implicit athlete queries**
New database access methods must accept `athlete_id: str = "default"` as a parameter.
The default value of `"default"` is acceptable in Phase 7.9–8. The parameter must
exist in the signature.

**Rule A40-2 — No new cross-athlete calibration defaults**
New science module constants introduced as calibration defaults must be annotated:
```python
HRV_REFERENCE_BASELINE_MS = 55.0   # ADR-0040: single-athlete default; Phase 9 per-athlete
```

**Rule A40-3 — No new test fixtures without athlete_id**
New test fixtures that create athlete data must include `athlete_id = "test_athlete_01"`
(or similar) even if the system today ignores it. This ensures fixture data is
isolation-ready when the schema changes.

**Rule A40-4 — New schema columns require athlete_id**
Any new table or new table column added after this ADR that stores per-athlete data
must include `athlete_id TEXT NOT NULL DEFAULT 'default'`. No exceptions.

### CI Enforcement (T4-31)

A new test `tests/test_athlete_isolation_invariant.py` must:

1. Parse all `titan/` Python files.
2. For any file NOT in the exemption register, assert no raw SQL query string
   contains a `SELECT/UPDATE/DELETE` without a `WHERE athlete_id = ?` clause
   (heuristic — catches the most common violation pattern).
3. Assert all new columns in new migration blocks include `athlete_id`.
4. The exemption register in this ADR is the source of truth. A file not in the
   exemption register that contains implicit athlete queries fails the CI check.

This is a linting-level check — not a runtime check. Its purpose is to prevent
new implicit coupling, not to enforce full isolation on existing code.

### What This Does NOT Require

- Rewriting existing modules to add `athlete_id` parameters (Phase 9 work).
- Supporting multiple athletes (Phase 9 feature).
- Changing the database schema for existing tables (except as required by T1-22
  and T4-30 which already mandate new columns).
- Any change to the current test suite beyond adding the CI invariant check.

---

## Debt Items Created

- **T4-31** — No athlete isolation invariant CI check — new code may silently introduce
  cross-athlete assumptions without detection (Tier 4, independent; CI check only)

---

## Consequences

- Positive: From this commit forward, the codebase does not accumulate new isolation
  debt. Phase 9 multi-athlete work starts with a clean boundary — only the documented
  exemption register needs migration.
- Positive: New database methods, new science modules, and new test fixtures are
  isolation-ready by default. The cost at Phase 9 is proportional only to the
  exemption register, not to the entire codebase.
- Positive: The exemption register makes the isolation debt explicit and bounded.
  Architects reviewing PRs know exactly which files are permitted to be non-isolated.
- Negative (acceptable): New code requires slightly more thought when writing DB
  access methods. The `athlete_id: str = "default"` pattern adds one parameter to
  new method signatures.
- Negative (acceptable): Requires module-level comments in the exemption register
  files — a one-time addition.
- Constraint: ADR-0040 is **effective immediately**. No waiting for a phase boundary.
  The first PR after this ADR must comply with Rules A40-1 through A40-4 for any
  new code it introduces.
