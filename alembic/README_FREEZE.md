# Alembic — FREEZE (Phase 8A Only)

This Alembic tree targets the PostgreSQL migration
(ADR-0044, Phase 8A). It is NOT wired to the
current SQLite runtime.

**Current SQLite schema:** SCHEMA_VERSION 31
managed via PRAGMA user_version (constant in
titan/core/database.py). The 31 incremental
_apply_vN_migrations() steps in
titan/core/repositories/migrations.py are the
authoritative SQLite migration history; they run
in one transaction with the user_version write
(D-104).

**Before Phase 8A:** An Alembic baseline migration
must be created that acknowledges the SQLite
SCHEMA_VERSION of that day as the starting point
for Postgres. See ADR-0044 §D2.

**Do not run alembic upgrade head against SQLite.**
The Alembic migrations target PostgreSQL dialect only.
