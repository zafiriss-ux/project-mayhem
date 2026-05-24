# Alembic — FREEZE (Phase 8A Only)

This Alembic tree targets the PostgreSQL migration
(ADR-0044, Phase 8A). It is NOT wired to the
current SQLite runtime.

**Current SQLite schema:** SCHEMA_VERSION 17
managed via PRAGMA user_version in
titan/core/database.py. The 17 incremental
_apply_vN_migrations() methods are the
authoritative SQLite migration history.

**Before Phase 8A:** An Alembic baseline migration
must be created that acknowledges SCHEMA_VERSION 17
as the starting point for Postgres. See ADR-0044 §D2.

**Do not run alembic upgrade head against SQLite.**
The Alembic migrations target PostgreSQL dialect only.
