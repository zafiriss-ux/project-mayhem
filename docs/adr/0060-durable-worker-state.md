# ADR-0060: Durable Worker State — routine executions and Telegram override nonces

**Status:** ACCEPTED (Zaf, merge of #907, 2026-10-07)
**Date:** 2026-10-07
**Author:** Zaf (Owner) / Claude (Design Authority)
**Related:** AGENTS §8.6 (INV-15, INV-17), §8.14 (INV-23), §13.3, §13.4, §14.2, §14.3;
T-PRA-03 (B-3, B-5), T-PRA-22 (B-15); ADR-0057 (Docker worker), ADR-0042 (Human Override)

---

## Context

The Docker worker restarts on every crash (`restart: unless-stopped`). Two pieces of state
that must survive a restart live only in memory today:

| State | Where it lives now | What a restart does |
|---|---|---|
| "Has today's morning routine run?" | nowhere in the single-athlete loop; a `last_run_dates` dict in the multi-athlete scheduler (`titan/worker/__init__.py`) | the single-athlete loop runs the routine again on every start, so a crash loop writes `governance_outcomes` once per restart; the scheduler forgets the day it already ran |
| Telegram override nonces | `_PENDING_OVERRIDES` dict, `time.monotonic()` expiry (`titan/integrations/telegram_bot.py`) | every outstanding override button becomes invalid; a nonce consumed before the crash is unknowable afterwards |

`governance_outcomes` is the calibration data source, so a double write is a data-integrity
failure, not noise [B-3]. AGENTS §8.6 already binds the keys and semantics of both tables and
states that the DDL is owned by the authorizing ADR. This is that ADR.

### §14.2 Change Justification

- **Problem:** worker idempotency (INV-15) and override replay protection (INV-17) are
  in-memory; a restart replays the morning routine and loses the nonce registry.
- **Proposed change:** two new SQLite tables, introduced by one Stage-1 migration (v26), and
  the code that uses them.
- **Why necessary (if nothing changes):** every worker crash on a given day writes another
  morning decision into `governance_outcomes`, and the calibration that Phase 27 is built on
  learns from duplicates. Override buttons sent before a restart stop working with no reason.
- **ADR reference:** new ADR required: this document. New tables are a schema-topology change
  (RP-3); §13.3's additive-column permission does not cover them.

---

## Decision

### D1. Table `worker_routine_executions` (INV-15)

```sql
CREATE TABLE IF NOT EXISTS worker_routine_executions (
    athlete_id      TEXT NOT NULL,          -- 'owner' in single-athlete mode (§16.10 A40-4)
    execution_date  TEXT NOT NULL,          -- YYYY-MM-DD, UTC
    routine_type    TEXT NOT NULL,          -- 'morning' (only value today)
    started_at      TEXT NOT NULL,          -- ISO-8601 UTC
    completed_at    TEXT,                   -- NULL until the routine returns
    PRIMARY KEY (athlete_id, execution_date, routine_type)
);
```

Semantics, as AGENTS §8.6 binds them:

1. Before a routine: `INSERT` the row with `started_at`. A primary-key conflict means the
   routine already started today, so the worker skips it. The claim is the insert itself; there
   is no read-then-write.
2. When the routine returns: `UPDATE ... SET completed_at = ?` on that row.
3. A row with `completed_at IS NULL` is a routine that crashed midway. It is **not** retried the
   same day. This keeps the current "mark as run before execution" behaviour, which exists to
   avoid a retry storm and a second `governance_outcomes` write. The worker logs a WARNING
   `worker_routine_incomplete` with the date when it finds such a row at startup.
4. On startup, the worker decides from this table, never from a dict, whether today's routine
   is still due. The multi-athlete scheduler's `last_run_dates` dict is replaced by the same
   claim.
5. If the claim `INSERT` fails for any reason other than the key conflict (DB locked,
   disk full), the routine does **not** run that cycle: fail closed, log CRITICAL
   `worker_routine_claim_failed`, retry on the next cycle.

Rows are one per athlete per day and are kept; no pruning is needed.

### D2. Table `telegram_override_nonces` (INV-17)

```sql
CREATE TABLE IF NOT EXISTS telegram_override_nonces (
    nonce         TEXT PRIMARY KEY,         -- secrets.token_urlsafe(16)
    command_type  TEXT NOT NULL,            -- 'override' (only value today)
    athlete_id    TEXT NOT NULL,
    decision_id   TEXT NOT NULL,            -- the decision this nonce authorizes [F-3]
    issued_at     TEXT NOT NULL,            -- ISO-8601 UTC
    expires_at    TEXT NOT NULL,            -- issued_at + 300 s (unchanged TTL)
    consumed_at   TEXT                      -- NULL until consumed
);
CREATE INDEX IF NOT EXISTS idx_telegram_override_nonces_expires
    ON telegram_override_nonces (expires_at);
```

`decision_id` is added to the columns AGENTS §8.6 lists, because §8.6 also requires that a
nonce binds to the decision it authorizes, and the current code already carries it.

Consumption is one statement, so the expiry and replay checks are in the query (no TOCTOU):

```sql
UPDATE telegram_override_nonces
   SET consumed_at = :now
 WHERE nonce = :nonce
   AND command_type = :command_type
   AND consumed_at IS NULL
   AND expires_at > :now;
```

`rowcount == 1` means valid; the bot then reads `decision_id` for that nonce. `rowcount == 0`
means unknown, expired, replayed or wrong command, and the bot refuses exactly as today.
Times are wall-clock UTC, because `time.monotonic()` does not survive a restart.

Startup deletes rows with `expires_at < now`. Unconsumed, unexpired nonces stay valid across a
restart. If the bot has no database handle, or the insert or update raises, no override is
accepted (fail closed, CRITICAL log), consistent with INV-16.

### D3. Migration and rollout (§13.4)

- **Stage 1 only.** One migration, `_apply_v26_migrations`, with both `CREATE TABLE IF NOT
  EXISTS` statements; `SCHEMA_VERSION` 25 → 26. No existing table, column or row changes, so
  there is no Stage 2 or Stage 3 and no backfill.
- **Rollback:** an older binary ignores the two tables, so rolling the code back is safe. Data
  rollback is the DR restore in `docs/RUNBOOK_DR.md`. Dropping the two tables is the manual
  reversal and loses only today's dedup marker and pending override buttons.
- **PostgreSQL:** the Alembic tree is frozen for Phase 8A (`alembic/README_FREEZE.md`). The two
  tables join the schema-parity work in T-PRA-30, which is the entry gate for any cutover;
  they get no Alembic revision now.
- **Order of PRs:** (1) this ADR, approved by Zaf; (2) the v26 migration with
  `tests/test_worker_state_durability.py` (restart = fresh instance, asserts no second
  `governance_outcomes` write and nonce survival/replay refusal); (3) wiring the worker and the
  bot. (2) and (3) may be one PR if it stays reviewable.

### D4. Out of scope

Heartbeat, watchdog, stale-lock recovery and callback isolation (INV-23, T-PRA-22) need no
new table and proceed under T-PRA-22 without this ADR.

---

## Consequences

**Positive:** a worker crash or redeploy no longer replays the morning routine or double-writes
`governance_outcomes`. Override buttons keep working across a restart, and a consumed nonce
stays consumed. Closes the durable-state half of B-3 and B-5.

**Neutral:** two small tables (one row per day; a handful of nonces). `SCHEMA_VERSION` becomes
26.

**Negative:** a routine that crashed midway is not retried until the next day (same as today,
now explicit and logged). The worker and the bot now need a writable database to run a routine
or accept an override; without one they refuse instead of proceeding.

---

## Approval

Per AGENTS §14.3 (cooling-off), the implementation PRs open only after this ADR is approved
and in a later session. Approval: merge of this PR by Zaf (Architect).
