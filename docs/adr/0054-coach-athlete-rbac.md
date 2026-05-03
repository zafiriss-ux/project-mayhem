# ADR-0054 — Coach-Athlete RBAC Scoping

**Status:** Accepted
**Date:** 2026-05-03
**Deciders:** Architect (Claude), Owner (Zaf)
**Refs:** ADR-0048 (auth layer), ADR-0033 (athlete isolation)

## Context
ADR-0048 established two roles: COACH (all athletes) and
ATHLETE (own data only). The COACH role currently has no
assignment mechanism — any coach can read any athlete's data.
T5-110 requires a scoping table so coaches are restricted
to explicitly assigned athletes.

## Decision
Introduce a `coach_athlete_assignments` table.
Every coach-facing DB read must filter by athlete_id
via this table. Application-level enforcement only
(PostgreSQL RLS is Phase 9 scope).

## Schema
```sql
CREATE TABLE IF NOT EXISTS coach_athlete_assignments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_id    TEXT NOT NULL,
    athlete_id  TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    UNIQUE(coach_id, athlete_id)
);
```

## Enforcement contract
- `get_assigned_athletes(coach_id) → list[str]`
  returns athlete_ids the coach may access.
- All coach-facing operator console queries
  MUST call this function and filter results.
- ATHLETE role: unchanged — still bound by JWT athlete_id claim.
- Owner athlete seeded at migration time:
  `coach_id='system', athlete_id='owner'`

## Consequences
- New table + migration (SCHEMA_VERSION 15→16).
- OperatorConsole methods gain athlete_id filtering.
- Single-athlete mode: unaffected (owner always assigned).
