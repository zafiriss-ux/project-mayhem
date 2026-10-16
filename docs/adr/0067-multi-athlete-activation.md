# ADR-0067: Multi-athlete activation — data lifecycle, consent, accounts and the per-athlete morning

**Status:** ACCEPTED (2026-10-16, merge of #1028)
**Date:** 2026-10-16
**Author:** Zaf (Owner, Architect: rules and product decisions) / Claude (drafting, technical choices)
**Related:** ADR-0015 (Phase 8 data-lifecycle gate, append-only tables), ADR-0040 and AGENTS §16.10
(athlete identity), ADR-0046 (multi-athlete model), ADR-0050 (Garmin), ADR-0054 (coach RBAC),
ADR-0060 (durable worker state, D1 amended here), AGENTS §8.6 (INV-15, amended here), D-085
(SQLite stays), issue #926 (plan task 20 on hold), Phase 4 plan
(https://claude.ai/code/artifact/524b1de2-bf53-464e-a08c-d5bc93139b88)

---

## Context

TITAN runs one athlete, the owner, from one `.env`. The database and the decision pipeline are
already keyed by `athlete_id`, but the outside world is not: one Garmin account
(`GarminSync()` with no arguments), one `TELEGRAM_CHAT_ID`, one `ATHLETE_*` profile, one
`WEATHER_LOCATION`. A second athlete today would get the owner's data and the owner would get the
second athlete's message. That is why plan task 20 is on hold (issue #926).

Phase 4 lets the same installation coach more athletes. Zaf ordered a written plan, audited it on
2026-10-16 and locked its rules. He then answered three cards:

| Card | Answer |
|---|---|
| When is an athlete's data deleted after `/stop`? | In 30 days, sooner if the athlete asks |
| Is new consent after `/stop` allowed in this phase? | Yes, explicitly, within the 30 days |
| May ADR-0067 change two AGENTS.md rules to fit the locked rules? | Yes, in the same PR |

ADR-0015 §3 makes a dedicated ADR on retention, storage topology, export format and restore a hard
prerequisite before any multi-athlete implementation. No later ADR closes it. This ADR is that
ADR, and it also records the locked rules so that steps 2–12 build on one text.

What the code on `main` (d21eefb) shows, checked on 2026-10-16:

- `consent_log` (v23) has `athlete_id TEXT NOT NULL DEFAULT 'default'`, `consent_type`,
  `granted_at`, `revoked_at`. It has no text version, and no code reads or writes it.
- `DELETE /coach/athlete-data` (`titan/api/main.py:546`) writes the audit record and returns
  `{"status": "deleted"}` without deleting anything. `GET /coach/export` (`:539`) returns
  `{"status": "export_ready"}` without exporting anything.
- ADR-0015 declares `governance_outcomes` and `training_log` append-only. No trigger enforces it.
- `worker_routine_executions` (ADR-0060 D1) claims the day before the routine runs. A crash
  leaves `completed_at` NULL and the day is not run again.
- `UniversalAthleteProfile.from_env()` reads `ATHLETE_NAME`, `ATHLETE_AGE`, `ATHLETE_WEIGHT`,
  `ATHLETE_HEIGHT`, `ATHLETE_MAX_HR`, `ATHLETE_THRESHOLD_HR`, `TRAINING_PHASE`, `TRAINING_GOAL`,
  each with a default. The profile's gender is fixed to `"M"` (`titan/core/athlete.py:60`).
- The Garmin token key `TITAN_GARTH_TOKEN_KEY` sits in the data folder's `.env`, next to the token.
  The `0600` mode from #883 does nothing on Windows.
- Backups keep 7 daily and 4 weekly copies, in Docker only (#906). Logs rotate by
  `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT`.

---

## Decision

### D1. Scope

1. **In:** athletes added by Zaf, each with their own profile, Garmin account, private Telegram
   chat, location and consent, on the same installation and the same morning routine.
2. **Out:** athletes outside UTC morning time zones; athletes under 18 (rejected at registration);
   the athlete as an API user; self-registration, mobile app, payments; PostgreSQL unless the
   step-10 measurement shows the single writer cannot keep up (D-085); `CohortProfile` (needs at
   least 3 active athletes with history).
3. **Unchanged:** `governance_engine.py` (ADR-0009) and every safety rule, which apply to each
   athlete as they do to the owner. The owner keeps reading `.env` and behaves as today, except for
   the crash rule in D8, which applies to everyone.
4. `TITAN_MULTI_ATHLETE` stays off by default. It is switched on only for the step-10 test and a
   pilot.

### D2. Storage topology, retention, export and restore (ADR-0015 §3 gate)

1. **Topology:** one shared SQLite database with a single writer; routines run one after another
   (D-085, ADR-0046). No per-athlete database files.
2. **Retention while active:** no automatic pruning, for any athlete, as today.
3. **Retention after `/stop`:** D4.
4. **Append-only exception:** `governance_outcomes` and `training_log` stay append-only. The one
   exception is the deletion of a whole athlete (D6). No row of an athlete who still exists is
   ever deleted or updated outside the code paths that do so today.
5. **Export format:** one JSON document per athlete, every row of every table that has an
   `athlete_id` column, tables discovered from the schema. Produced by `athletes export <id>` on
   the routine machine. The athlete asks Zaf for it; Zaf sends it. `GET /coach/export` either
   returns this document to an assigned coach or is removed in step 8; it does not stay a stub.
6. **Backups:** SQLite snapshots as today (7 daily, 4 weekly). A deleted athlete's rows can live
   in a backup for up to 35 days after deletion; the deletion record (D6.3) makes a restore
   delete them again.
7. **Restore and audit read:** restore per `docs/RUNBOOK_DR.md`, then re-apply every deletion
   record before the worker starts. An archived athlete's data is read only from that athlete's
   JSON export, never by restoring a backup into production.
8. **Logs:** a log line carries `athlete_id`, never a name, chat id or Garmin e-mail. Rotation stays
   as today.

### D3. Isolation

1. Existing rows that lack `athlete_id` (`sync_metadata`, `override_log`) get `'owner'` only after a
   check shows they are the owner's and not installation state. `login_lockout` stays per user.
2. A new `athlete_id` column or table has **no DEFAULT**, even when that needs a table rebuild. An
   insert without `athlete_id` fails. Keys become `(athlete_id, …)`.
3. The G-CI-07 gate (`tests/test_athlete_isolation_invariant.py`) covers the new columns and
   tables.
4. Every step that touches isolation runs the owner's existing tests, not a new suite. A
   baseline of the owner's decisions is taken on unchanged `main` before step 2. If a step changes
   it, work stops until Zaf decides.
5. **Athlete ids:** the owner is `'owner'`. Any other athlete gets a generated id, `a-` followed by 8
   lowercase hex characters, so the id is opaque and safe in a path (`[a-z0-9_-]+`). The name lives
   only in `athletes.display_name`.

**AGENTS amendment (authorized by Zaf on the card of 2026-10-16):** AGENTS §16.10 A40-4 no longer
requires `DEFAULT 'default'` on new per-athlete columns; it forbids a default. Existing columns keep
theirs, and the INV-18 sanctioned forms stay as they are.

### D4. Consent

1. The athlete gives consent themself, in their private Telegram chat, to one numbered version of
   the consent text. A "yes" typed by Zaf in the CLI is not consent. The text lives in the
   repository (`docs/consent/`, one file per version, created in step 7); its wording is reviewed by a lawyer before
   the first real athlete.
2. Without a current consent an athlete is not run: no Garmin, weather or Telegram call, no write.
3. `/stop` revokes consent and stops the routine at once. The data stays frozen for 30 days: no
   calls, no writes, no message. On day 30 the athlete is deleted (D6), or earlier if the athlete
   asks.
4. Within the 30 days the athlete may give consent again, explicitly, to the current text version.
   The routine resumes from the next UTC day and the history is kept. After deletion the athlete
   can only return as a new athlete without history.
5. The owner is exempt from the consent check only.
6. Health data of anyone but the owner is special-category data from the first such athlete.

**`consent_log` redesign (migration v30, step 2):** the table is rebuilt with `athlete_id TEXT
NOT NULL` (no default), `consent_type`, `text_version TEXT NOT NULL`, `granted_at`, `revoked_at`
and `channel` (`'telegram'`). A new consent is a new row; a revocation sets `revoked_at` on the
current row. The table holds no rows today, so the rebuild copies nothing. The two tests that
reference it (`test_alembic_d9_consent_log_migration.py`, `test_schema_equivalence.py`) and the
five documents that mention it (ROADMAP, PARITY_MATRIX, AI_GOVERNANCE, ADR-0044, ADR-0045) are
updated in step 2.

### D5. Profile, location and history

1. Required for a new athlete, all without defaults: name, date of birth (age is computed;
   under 18 is rejected), sex, weight, height, maximum HR, threshold HR, training phase, goal,
   location (city and country for the weather API). Values pass the same range checks as #911.
2. Sex is stored but the decision rules do not change in this phase; the fixed `"M"` stays an open
   item (SV-18).
3. An athlete with any field missing is not run (D7.1).
4. On registration the athlete's history is fetched from Garmin as for a new owner: 210 days of
   activities (`LOAD_HISTORY_DAYS`, D-055). Consent covers this fetch, so it runs only after D4.1.

### D6. Deletion

1. First the athlete leaves the scheduler. Then one transaction deletes every row of that athlete
   in every table that has an `athlete_id` column, plus coach assignments, and the athlete's token
   file is removed. Tables are discovered from the schema, never from a list.
2. `DELETE /coach/athlete-data` does this, or is removed in step 8.
3. A deletion record keeps only the opaque athlete id and the time. It lives in a file outside the
   data folder and outside the backups, and a restore re-applies it. Without it no promise is made
   that a restore keeps a deleted athlete deleted.

### D7. Two kinds of failure

1. An athlete without profile, location, Garmin, Telegram or consent is not run, calls nothing and
   never receives the owner's values. Zaf is told once per UTC day.
2. A complete athlete whose Garmin or weather is down is handled as the owner is today, with the
   names the code already has (degraded mode, stale data).

### D8. Scheduler and the crash rule

1. Through step 8 the loop runs only the owner. Step 9 adds every ready athlete in a fixed order,
   the owner first.
2. The claim stays one row per athlete, UTC day and routine (`worker_routine_executions`).
3. A day whose message was delivered is never sent again.
4. **Amended:** a crash before the message is delivered does not count as a finished day. On the
   next cycle of the same UTC day the routine resumes: if the athlete's decision for that day is
   already in `governance_outcomes`, it is not computed again and the stored decision is sent;
   otherwise the routine runs. `governance_outcomes` is never written twice for one athlete and day.
   After 3 attempts in one day the day is left, with a CRITICAL log and one message to Zaf. The
   delivery marker and attempt count are DDL for step 9, under this ADR.
5. Each athlete's routine runs in its own child process with a time limit. When the limit is hit
   the process is killed, SQLite rolls back its open transaction, the attempt counts, and the loop
   moves to the next athlete. A thread is not used for this because it cannot be stopped safely.
6. 07:00 UTC for everyone. Every athlete's briefing counts as one scheduled briefing in
   `docs/SLO.md` ("delivered by 07:05 UTC"); the SLO text does not change. If step 10 shows it
   does not hold, Zaf decides.

**Amends ADR-0060 D1 item 3** (no retry of an incomplete day), for the owner too.
**AGENTS amendment (authorized by Zaf on the card of 2026-10-16):** AGENTS §8.6 INV-15 lets an
incomplete claim resume on the same UTC day without a second `governance_outcomes` write.

### D9. Garmin accounts

1. The password is never stored. The athlete types it on the routine machine, with MFA if the
   account has it. If the athlete cannot be present, no login happens and the athlete stays
   incomplete (D7.1); the password is never sent to Zaf or through Telegram.
2. Each athlete has their own encrypted token file under `<data>/garmin/<athlete_id>/`. The
   encryption key for athletes lives outside the data folder, in a file named by
   `TITAN_TOKEN_KEY_FILE`, so a copy of the data folder alone does not decrypt the tokens. The
   owner's token and key stay where they are today.
3. Linux: token and key files are `0600`. Windows: the same files get an ACL that grants access
   only to the account running TITAN (inheritance removed). If the ACL cannot be set the token is
   not written.
4. One Garmin account binds to one athlete only; a second binding is refused.
5. Token expiry pauses the athlete, tells Zaf, and is fixed by `athletes relogin <id>`.
6. Every morning uses the stored token, never a fresh login, and athletes run one at a time
   (ADR-0050).

### D10. Telegram

1. One bot, one process, one private chat per athlete. Laptop and server never run at the same
   time.
2. A chat that is not registered gets no reply and learns nothing about other athletes.
3. An athlete has `/sync` and `/stop` only. Every command that changes state writes its audit
   record first (INV-22).

### D11. Steps

Twelve PRs, one per step, plus a thirteenth only if there is a pilot: 1 this ADR; 2 migration v30
(owner baseline first); 3 profile from the database; 4 Garmin per athlete; 5 Telegram per athlete;
6 weather per athlete; 7 consent; 8 add, relogin, remove and export; 9 worker runs ready athletes;
10 owner and two synthetic athletes for 14 days; 11 documents and runbook; 12 phase-close check;
13 server (pilot only).

---

## Consequences

- Steps 2–12 can start; ADR-0015 §3 is satisfied.
- A worker crash before the morning message now resumes the day, for the owner as well. The
  calibration data stays single-written.
- `DELETE /coach/athlete-data` and `GET /coach/export` stop being stubs, or are removed.
- New per-athlete columns have no default, so a forgotten `athlete_id` is an error, not a row
  under the wrong athlete.

## Not changed

- `governance_engine.py`, the H1–H5 hard stops, the 2-of-4 rule, every threshold.
- The owner's `.env`, profile, Garmin token and Telegram chat.
- The SLO text. Any SLO change needs Zaf's approval.

## Open, outside this ADR

- The consent text itself and the lawyer's review (before the first real athlete).
- Whether there is a pilot, with whom, and on which server (step 13 only).
