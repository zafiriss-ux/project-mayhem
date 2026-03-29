# ADR-0044 — PostgreSQL Migration as Phase 8A Entry Gate

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Strategic review session 2026-03-06 — multi-athlete data topology decision
**Phase:** Phase 8A — prerequisite before any multi-athlete feature work
**Supplements:** ADR-0015 (SQLite retention — this ADR fulfills the Phase 8 storage topology gate
defined there), ADR-0022 (Phase 8 entry gate — G10 added here), ADR-0033 (multi-athlete
architecture — Layer 3 implementation prerequisite), ADR-0040 (athlete identity invariant),
ADR-0043 (product direction — companion decision)

---

## Context

ADR-0015 accepted SQLite as the current single-athlete, single-lifetime database and
explicitly deferred the storage topology decision to Phase 8, stating:

> "Before any multi-athlete work begins, a dedicated ADR must define and lock:
> storage topology decision (per-athlete SQLite files vs shared database)"

This ADR is that dedicated decision.

### Why the storage topology decision must precede all Phase 8 feature work

The coach dashboard (Phase 8B), device adapters (Phase 8C), and autonomous calibration
(Phase 9) all operate on multi-athlete data. If the storage topology decision is made
after those features begin, either:

a) Each feature makes its own implicit assumption about storage (some assume per-athlete
   SQLite, some assume shared database), creating irreconcilable technical debt at first
   integration.
b) All features are built on SQLite and then migrated — requiring a full rewrite of all
   new code at the migration point.

Neither outcome is acceptable. The topology decision is Phase 8A work — done before the
first multi-athlete feature line is written.

### SQLite limitations at multi-athlete scale

| Constraint | Single-athlete (current) | Multi-athlete (Phase 8) |
|---|---|---|
| Concurrent writes | One writer (main thread + daemons) | 50 athletes × 3 daemon threads = 150 concurrent writers |
| Database size | Single file, ~MB range | Per-athlete data × 50+ athletes = GB range |
| Schema migration | `PRAGMA user_version` (T1-16) | Multi-tenant migrations require atomic coordination |
| Backup | Single file copy (T1-17) | Per-athlete snapshots + point-in-time recovery |
| Row-level isolation | Not needed (single tenant) | Required — athlete A's data must never affect athlete B |
| Connection pooling | Not needed | Required for web API layer (Phase 8B React + FastAPI) |
| GDPR / data deletion | Single DB delete + file delete | Requires per-athlete data isolation for right-to-erasure |

SQLite's single-writer concurrency model is a hard ceiling for multi-athlete workloads.
Per-athlete SQLite files address concurrency but introduce a new class of operational
complexity: schema migrations must be run against every athlete file individually; a
cross-athlete coach query (e.g., "all athletes with VLG RED today") requires opening
and querying N files; backup and restore procedures multiply by N.

PostgreSQL solves all of these at once: ACID concurrency with row-level locking,
single schema migration path, native connection pooling, row-level security for
athlete isolation, and a mature backup/restore ecosystem.

---

## Decision

**TITAN OS will migrate its persistence layer from SQLite to PostgreSQL as Phase 8A
work, before any multi-athlete feature code is written.**

### Storage topology: shared PostgreSQL database with `athlete_id` row-level isolation

- One PostgreSQL instance (self-hosted or managed cloud: Supabase, RDS, etc.)
- All tables carry `athlete_id` as a foreign key (ADR-0040 Rule A40-4, already active)
- Row-Level Security (RLS) policies enforce that a query with `SET LOCAL app.athlete_id
  = 'X'` cannot read rows belonging to athlete Y
- Coach-facing queries use a dedicated `coach` role that can read across athletes but
  not write
- GDPR right-to-erasure: `DELETE FROM * WHERE athlete_id = ?` + RLS ensures completeness

### Abstraction layer: SQLAlchemy Core (not ORM)

The `DatabaseManager` class (`titan/core/database.py`) is replaced with a
`PersistenceAdapter` that uses SQLAlchemy Core for connection management and query
execution. SQLAlchemy Core is chosen over the ORM because:

- TITAN OS queries are already written as explicit SQL strings — no object-relational
  mapping is needed.
- SQLAlchemy Core's `text()` and `Connection.execute()` map directly to the current
  `DatabaseManager` interface.
- The abstraction allows future backend swaps (e.g., CockroachDB for global distribution
  in a hypothetical Phase 11) without rewriting queries.

```python
# titan/core/persistence.py  (replaces titan/core/database.py at Phase 8A)
from sqlalchemy import create_engine, text
from contextlib import contextmanager

class PersistenceAdapter:
    """
    ADR-0044: PostgreSQL-backed persistence layer.
    Replaces DatabaseManager for multi-athlete Phase 8A+.
    Interface is backward-compatible with DatabaseManager for single-athlete paths.
    """
    def __init__(self, dsn: str):
        self._engine = create_engine(dsn, pool_size=10, max_overflow=20)

    @contextmanager
    def athlete_session(self, athlete_id: str):
        """Context manager that sets RLS athlete scope for the duration of the block."""
        with self._engine.connect() as conn:
            conn.execute(text(f"SET LOCAL app.athlete_id = :aid"), {"aid": athlete_id})
            yield conn
            conn.commit()
```

### Migration tooling: Alembic

All schema changes are managed via Alembic migration scripts:
- `alembic/versions/` contains numbered migration files.
- `alembic upgrade head` is the single deployment command.
- No direct `CREATE TABLE` in application code (current `DatabaseManager._create_tables()`
  is retired).
- `PRAGMA user_version` (T1-16) is superseded by Alembic's version tracking.

### Phase 8A deliverables (binary — all required before Phase 8B begins)

| # | Deliverable | Verification |
|---|---|---|
| D1 | `PersistenceAdapter` implemented, all existing queries ported | `python -m pytest -q` → 0 failures, same count as Phase 7 baseline |
| D2 | Alembic migration for all 5 current tables (`daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, `governance_outcomes`) | `alembic upgrade head` → no errors on fresh DB |
| D3 | `athlete_id` column on all 5 tables (`DEFAULT 'default'` for backward compat) | Schema inspection test green |
| D4 | Row-Level Security policies active and tested | `tests/test_athlete_rls_isolation.py` → green |
| D5 | `model_calibration_metadata` table migrated (ADR-0033 T5-07 Layer 1) | Schema inspection test green |
| D6 | SQLite `DatabaseManager` retained as a `LegacyDatabaseManager` under a feature flag `TITAN_DB_BACKEND=sqlite\|postgres` (default: `postgres` in Phase 8A+) | Both backends pass `python -m pytest -q` |
| D7 | Hot backup strategy updated for PostgreSQL: `pg_dump` replaces SQLite file copy (T1-17 re-implementation) | `python -m pytest tests/ -k backup -v` → green |
| D8 | `TECHNICAL_DEBT.md` T5-08 marked RESOLVED | Manual check |

D6 (feature flag with SQLite fallback) is critical for development continuity: tests
and local development can continue to use SQLite via `TITAN_DB_BACKEND=sqlite` during
the Phase 8A migration window. No test refactoring is required until the SQLite
fallback is formally retired (no earlier than Phase 8B close).

### What changes for existing single-athlete operation

For a developer running TITAN OS locally for a single athlete with `TITAN_DB_BACKEND=sqlite`
set in `.env`, **nothing changes**. The legacy `DatabaseManager` path remains active.

For a production multi-athlete deployment, PostgreSQL is mandatory from Phase 8A forward.

### GDPR / Data Handling Note

Multi-athlete deployment implies health data for multiple individuals. From Phase 8A
forward:

- Athlete data must never cross `athlete_id` boundaries (enforced by RLS).
- Right-to-erasure requests must be satisfied by `DELETE FROM * WHERE athlete_id = ?`
  which RLS verifies is complete.
- No raw physiological data (HRV, RHR, sleep scores) may be used for cross-athlete
  model training without explicit per-athlete consent recorded in a `consent_log` table.
- The `consent_log` table schema (columns: `athlete_id`, `consent_type`, `granted_at`,
  `revoked_at`) is a Phase 8A deliverable (D9, added to Alembic migration).

---

## Phase 8 Entry Gate Update (ADR-0022 Addendum)

Two new gate criteria are added to ADR-0022's Phase 8 entry gate (G9, G10). These are
prerequisites that must pass before Phase 8B (coach dashboard) begins, not before Phase 8A
begins. Phase 8A is itself the mechanism that satisfies them.

| # | Gate Criterion | Verification |
|---|---|---|
| G9 | ADR-0018 Phase B implemented — Effect Runner extracted as stateless decision function | `python -m pytest tests/test_effect_runner.py -v` → green |
| G10 | ADR-0044 Phase 8A deliverables D1–D9 all complete | `python -m pytest -q` → 0 failures; `alembic upgrade head` clean |

---

## Debt Items Created

- **T5-08** — Storage topology decision not yet implemented — PostgreSQL migration, Alembic
  setup, `PersistenceAdapter`, RLS policies, and consent schema not built (Tier 5; Phase 8A;
  ADR-0044; all of D1–D9 above; ~3–4 weeks of focused engineering)

---

## Alternatives Considered

**Alternative A — Per-athlete SQLite files**
Rejected. Addresses concurrency but introduces N-file operational complexity (migrations,
cross-athlete queries, backup, GDPR erasure). The engineering cost of managing N SQLite
files is higher than operating a single PostgreSQL instance, especially as N grows from 10
to 50 to 500.

**Alternative B — Keep SQLite, use a connection pool shim (WAL mode + connection limit)**
Rejected. SQLite WAL mode supports concurrent readers but still enforces a single-writer
constraint. With 50 athletes each running daemon threads, write contention will cause
failures under load. This is a workaround, not a solution.

**Alternative C — Use DuckDB (OLAP) instead of PostgreSQL (OLTP)**
Rejected. TITAN OS workload is OLTP: frequent small writes (daily metrics, governance
outcomes), occasional reads (morning briefing, weekly planning). DuckDB is optimized
for analytical batch queries — the wrong tool for this access pattern.

**Alternative D — Defer PostgreSQL migration to Phase 9**
Rejected. ADR-0015 explicitly gates Phase 8 implementation on this decision. Building
the coach dashboard on SQLite and then migrating everything to PostgreSQL at Phase 9
doubles the migration cost and introduces a window where the coach dashboard is
architecturally inconsistent with the target topology.

---

## Consequences

- Positive: All Phase 8B+ feature work begins on a topology that supports 10–500 athletes
  without architectural rework.
- Positive: GDPR right-to-erasure is structurally guaranteed from Phase 8A forward — not
  a feature to add later.
- Positive: Alembic replaces ad-hoc `CREATE TABLE IF NOT EXISTS` calls — schema evolution
  is now versioned and reversible.
- Positive: `TITAN_DB_BACKEND=sqlite` feature flag means zero disruption to current
  single-athlete development workflow during the migration window.
- Negative (acceptable): Phase 8A adds ~3–4 weeks of infrastructure work before the first
  user-visible feature. This cost is front-loaded deliberately.
- Negative (acceptable): PostgreSQL requires a running database server in production.
  For self-hosted deployments, this means Docker Compose or a managed cloud instance
  (Supabase free tier is sufficient for early Phase 8 scale). This is not a significant
  operational burden for a coach-facing product.
- Constraint: T5-08 must be fully resolved before Phase 8B begins. No coach dashboard
  code may be written against SQLite.

---

## Review Trigger

This ADR should be reviewed when:
- Phase 8A implementation begins (T5-08 resolved), to confirm the migration sequence is still accurate.
- A managed cloud database provider other than Supabase is proposed for production hosting.
- Alembic is proposed to be replaced by a different schema migration tool.
- The `TITAN_DB_BACKEND` feature flag is proposed for removal (i.e., SQLite support is dropped entirely).
