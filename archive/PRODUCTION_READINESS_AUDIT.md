# TITAN OS — Production Readiness Audit

**Date:** 2026-05-15
**Branch:** `claude/production-readiness-audit-BKBd3`
**Scope:** Architecture, CI/CD, tests, security, observability, ops, scalability, supply chain.
**Reviewer posture:** Principal Architect / QA Lead / DevOps Auditor / Production Engineering Consultant.

This audit is intentionally adversarial. It does not enumerate what works well unless that
context is needed to ground a risk. The repo has a mature *engineering* discipline and a
hobbyist *operational* posture; this report calls out the gap.

---

## A. Executive Summary

**Top critical problems (ranked by realistic blast radius):**

1. **Coach-Athlete RBAC is aspirational, not enforced.** `titan/api/dependencies.py:41-46`
   short-circuits every `COACH` role to "access granted" without consulting the
   `coach_athlete_assignments` table that ADR-0054 was built around. The HTTP API is
   *currently* a flat-trust system. Any feature that puts more than one athlete behind the
   API is a privacy breach by default.
2. **DailyCoach is a 1,747-line god-orchestrator with 18 injected dependencies and
   unprotected concurrent read paths.** Cron, Telegram `/sync`, and Garmin background
   threads can all enter the morning routine while writes are in flight; the only guard is
   a `monotonic` check on a single in-process thread handle
   (`titan/orchestration/daily_coach.py:1516`). The reader path of `DatabaseManager`
   carries no lock — SQLite's `check_same_thread=False` is used as a permission, not as
   an isolation contract.
3. **No deployable artifact and no operational target.** "Deployment" is `git clone` +
   `pip install` + a hand-edited `~/Documents/TITAN/.env`. There is no container, no
   systemd unit, no immutable build, no rollback target, no secrets manager. The
   `DEPLOYMENT_GUIDE.md` describes a single laptop user.
4. **Alembic is shipped but frozen** (`tests/test_d2_alembic_freeze.py`). Schema lives in
   `database.py` migrations (1→17) *and* in `alembic/`; PostgreSQL is wired in
   `persistence.py` but the `backup_database` path explicitly raises `NotImplementedError`
   (`docs/PARITY_MATRIX.md:125`). The Phase 8 PostgreSQL migration story is therefore
   partially written and not exercised in CI.
5. **Governance "override lockdown" fails open on cold start.** When
   `db.get_override_ratio()` returns `None` (new athlete, no `governance_outcomes` yet),
   the lockdown gate evaluates as *unlocked*. The safest configuration is currently the
   one where the calibration data is missing — exactly the case where the user is most
   exposed.

**Production-readiness estimate:** ~ **45/100**. Strong engineering controls, weak
production substrate. Suitable for *single user, single laptop* operation with manual
recovery. Not suitable for "multi-athlete coaching mode" as described, and not safe to put
behind a public HTTPS endpoint without the fixes in §F and §I.

**Maturity level estimate (CALMS / DORA-adjacent):** L2 (Repeatable) for code quality and
test hygiene; L1 (Initial) for operations, deploy, and observability. The mismatch is the
report's central finding.

---

## B. Critical Risks

For each risk: *why it matters* → *probable failure mode* → *production consequence*.

### B1 [CRITICAL] Coach RBAC not enforced — flat-trust API
- **Where:** `titan/api/dependencies.py:41-46`. Any user with `role == "COACH"` is granted
  access to any `athlete_id`. The `coach_athlete_assignments` table (DB v16, T5-110) is
  populated but never queried at the request boundary.
- **Why it matters:** ADR-0054 is the entire reason multi-tenant coaching is allowed in
  the architecture. If the gate it justifies does not exist, the ADR is a placebo.
- **Failure mode:** First "real" coach with two athletes can `GET
  /athletes/{any_id}/...` and pull HRV, sleep, location-correlated weather, override log.
- **Consequence:** Confidentiality breach of health-adjacent PII. If the system is ever
  marketed to coach-athlete pairs, this is GDPR Art. 5/32 territory and HIPAA-adjacent.

### B2 [CRITICAL] Unprotected concurrent reads on SQLite + 3 daemon threads
- **Where:** `titan/core/database.py:175` (`self._lock = threading.RLock()`) — held only
  on writes. `get_training_load_history`, `get_baseline_rhr`, `get_override_ratio`, and
  the entire `_persist_*` reading layer are unguarded. `check_same_thread=False` is used
  to *permit* cross-thread access without arbitrating it.
- **Why it matters:** Garmin sync (6h), weather (1h), morning routine (07:00), and
  Telegram `/sync` all read+write the same DB instance concurrently. The morning routine
  rehydrates CTL/ATL on startup from a table written by Garmin sync.
- **Failure mode:** WAL mode + concurrent writer + reader without busy-wait → reader sees
  the snapshot at its `BEGIN` and may miss the row Garmin just inserted, producing a
  silently incorrect CTL. The mistake compounds over weeks because today's CTL feeds
  tomorrow's CTL.
- **Consequence:** Governance decisions (intensity gates, ACWR, TSB floor) computed on
  off-by-one training-load history. Silent corruption is the worst class — the system
  keeps making confident decisions on wrong inputs.

### B3 [HIGH] Override-lockdown fails open with no outcome history
- **Where:** `titan/science/governance_engine.py:129-160` (gate logic);
  `titan/core/database.py:1332-1375` (`get_override_ratio`).
- **Failure mode:** New athlete or freshly migrated DB → `governance_outcomes` empty →
  ratio is `None` → gate returns `{"locked": False}`. The safety control intended to
  protect calibration-confused athletes is inert exactly when calibration is most
  uncertain.
- **Consequence:** Worst-case sequence: athlete just installed the app, overrides 3
  conservative recommendations in a week, sustains an injury, and the audit trail shows
  the lockdown gate as "evaluated, not triggered" with no surfaced reason. This is the
  kind of finding that ends a coaching product.

### B4 [HIGH] DailyCoach orchestrator is monolithic and side-effect heavy
- **Where:** `titan/orchestration/daily_coach.py` — 1,747 lines, 18 injectable deps, a
  330-line `run_morning_routine()` mixing API I/O, DB writes, science calls, and Telegram
  side effects.
- **Failure mode:** A single transient failure inside step 5 (e.g., `RCPEngine` raises)
  takes out steps 6–12. `_feed_load_engines` and `send_alert` paths each carry their own
  try/except, but the seam is "best-effort except / continue", not transactional. Partial
  state (load fed but governance never evaluated, or governance run but Telegram never
  sent) is silently the new normal.
- **Consequence:** Operators cannot answer "did the morning briefing actually run today?"
  without grepping logs. There is no `morning_routine_id` per execution, no per-step
  spans, no idempotent re-run.

### B5 [HIGH] Async morning routine has no deduplication lock
- **Where:** `titan/orchestration/daily_coach.py:1516, 1525-1532`. The guard against
  concurrent runs is a single `thread.is_alive()` check. A `/sync` from Telegram at
  06:59:45 and the cron at 07:00:00 will both pass the check if the first hasn't yet
  spawned its thread.
- **Failure mode:** Two morning routines run in parallel; both call `_feed_load_engines`;
  both write today's daily metric; the `UNIQUE` constraint on `daily_metrics.date` makes
  the second fail loudly, but the *partial side effects of the first half of step N* are
  already committed.
- **Consequence:** Duplicate Telegram briefings, doubled training-load contributions on
  edge days, and a foggy audit log.

### B6 [HIGH] No deployable build; secrets in plaintext on disk
- **Where:** `DEPLOYMENT_GUIDE.md`; `.env` loaded from `~/Documents/TITAN/.env`;
  `titan/integrations/garmin_sync.py:59-90` (`_encrypt_token` falls back to plaintext
  when `TITAN_GARTH_TOKEN_KEY` is unset and logs a warning).
- **Failure mode:** Any backup of `~/Documents` exfiltrates Garmin credentials, Telegram
  bot token, and (once configured) the JWT private key. Windows ACL on `.env` is not
  enforced (the README acknowledges this).
- **Consequence:** A leaked Telegram bot token allows an attacker to send messages as the
  coach. A leaked Garmin password allows full session takeover (Garmin enforces 2FA only
  weakly for API clients).

### B7 [HIGH] CodeQL findings are not uploaded; secret scan is shallow
- **Where:** `.github/workflows/codeql.yml` runs but `upload: never`; gitleaks scans
  `HEAD~1..HEAD` only (`.github/workflows/secret-scan.yml`) and `.gitleaks.toml`
  allowlists `tests/**` and `test_*.py` wholesale.
- **Failure mode:** A real key copy-pasted into a fixture file is whitelisted by path;
  CodeQL severity trends are not visible, so no policy gate is possible.
- **Consequence:** A future secret leak is a question of *when*, not *if*.

### B8 [MEDIUM] Schema lives in two places (`database.py` migrations + `alembic/`)
- **Where:** `SCHEMA_VERSION = 17` is enforced by hand-rolled migration functions
  (`titan/core/database.py:1032-1167`). Alembic exists for PostgreSQL but is frozen on
  SQLite (`tests/test_d2_alembic_freeze.py`).
- **Failure mode:** Phase 8A PostgreSQL switch silently lands with an Alembic schema that
  diverges from the SQLite schema. Downstream queries (`INSERT OR REPLACE`, partial
  uniqueness constraints, NULL defaults from earlier migrations) are SQLite-specific.
- **Consequence:** Cutover to PostgreSQL will be the worst day in this project's history
  if not rehearsed against a populated SQLite dump.

### B9 [MEDIUM] `coach_audit_log` exists but is rarely written
- **Where:** Table created v17 (`titan/core/database.py:1155-1167`);
  `insert_coach_audit_log` at line 1540; only one call site visible. Most API endpoints
  do not emit audit records.
- **Failure mode:** Coach reads athlete data → no audit log entry → no answer to "who saw
  my HRV last Tuesday?".
- **Consequence:** Forensic blind spot. For any multi-tenant deployment, this is the
  evidence path you wish you had built from day one.

### B10 [MEDIUM] 172 raw `print()` calls remain in `titan/`, mixed with structured logger
- **Where:** `grep "print(" titan/ -r` → 172 hits. `titan/core/structured_events.py`
  defines a real structured-event emitter, but `print` and `logger.info` and
  `_event(...)` coexist.
- **Failure mode:** Some events are JSON, some are free-text, some go to stdout only.
  When logs are shipped, half the events are unparseable.
- **Consequence:** Aggregation, alerting, and per-flow latency calculations break for
  any non-structured event.

---

## C. Architectural Weaknesses

1. **Composition root is a constructor with 18 parameters.** Wiring 18 dependencies by
   hand is fine *now*, fragile *next year*. There is no container, no factory, no
   per-athlete instance pattern. `self.db = db or DatabaseManager()` allows a hidden
   shared-singleton DB across all tests and modes.
2. **PersistenceAdapter ABC is a Potemkin abstraction.** `titan/core/persistence.py`
   defines an interface that nobody calls; `DatabaseManager` is the de-facto interface
   for 3,200 lines. A frozen abstraction is worse than no abstraction — it implies a
   contract that does not bind.
3. **Threshold values live in three places.** `thresholds.py`, hardcoded literals in
   `volume_load_gauge.py`, and mirrored-with-comment in `adaptive_priority_lock.py` (per
   the older `AUDIT_REPORT.md`, still applicable to current code as of this branch).
   Silent divergence is one of the few things you cannot regression-test for; you can
   only detect after the values disagree in the wild.
4. **Governance engine pulls outcome history at decision time.** A decision system that
   reads its own past decisions to gate its present decision is a feedback loop without
   a damping term. Cold-start, post-DB-wipe, post-migration: all three put the system
   into a regime the gate logic does not have a defined answer for.
5. **`athlete_id` is not consistently parameterized into the science layer.** The
   architectural invariant (ADR-0040 / ADR-0033) says "athlete identity flows through
   every layer". The implementation says "athlete identity flows through database
   filters; the engines operate on whatever rows you handed them". The invariant test
   exists (`tests/test_athlete_isolation_invariant.py`) — verify it actually catches
   regressions if a developer omits `athlete_id` in a future query.
6. **Telegram is a transport *and* a control plane.** The bot accepts override commands
   that mutate the safety state of the system. There is no separate authenticated path;
   trust is the Telegram chat ID. If a household member opens the bot, they can override
   a hard-stop.
7. **No clear seam between "decision pipeline" and "effect runner".** ADR-0018 calls for
   this split; the daily_coach.py code shows partial extraction. Without the seam, you
   cannot dry-run the system against historical data or replay a day's decisions.

---

## D. QA / Test Weaknesses

Strengths (briefly, to ground the gaps): there are real concurrency tests
(`tests/test_concurrency_consistency.py`, 533 lines), chaos tests
(`tests/test_chaos_scenarios.py`, 156 lines), adversarial tests
(`tests/test_adversarial_scenarios.py`, 365 lines), property-based tests
(`test_property_based.py`), an architectural invariants suite, and mutation-testing
config for the governance engine. This is not a token test suite.

Gaps:

1. **No real integration tests against the live Garmin/Telegram/Weather APIs**, and no
   `vcrpy`/`pytest-recording` cassettes checked in (the ROADMAP mentions "stale vcrpy
   cassettes" as a known issue — `docs/ROADMAP.MD:166`). The "integration tests" are
   almost certainly fakes. That is fine for unit isolation, but it means the system has
   never been tested end-to-end against a real Garmin auth failure / rate limit / token
   expiry / 2FA flow.
2. **`test_concurrency_consistency.py` is 533 lines but uses an in-memory or fresh
   on-disk SQLite.** It does not test the *actual* daemon-thread interaction (Garmin sync
   thread + Daily Coach thread + Telegram poller thread on a shared `DatabaseManager`
   instance with WAL).
3. **`test_chaos_scenarios.py` is 156 lines — small for the name.** Verify it actually
   injects faults (kill, hang, partial writes, clock skew, disk full) versus testing
   "code path X with input Y".
4. **No fuzz testing on the external boundary.** `data_sanity.py` validates Garmin input
   cross-fields, but there is no `hypothesis` test that throws malformed Garmin
   responses at the parser.
5. **No mutation testing budget beyond governance_engine.** `setup.cfg` configures
   `mutmut` for one module. The mutation score for `daily_coach.py`, `database.py`, and
   `intensity_governor.py` is unknown.
6. **Test count is reported as "2746 passing"** in CLAUDE.md. Per AGENTS.md, the gates are
   `ruff check`, `pytest -W error`, `pytest`. None of the gates enforce a **minimum
   coverage** for the orchestration or persistence layers; only the governance engine
   has an 80% floor. Critical paths are tested *because the team chose to*, not because
   CI demands it.
7. **No load test, no performance regression test.** SLO-02 declares a P99 latency
   target of 2s for the 7-gate evaluation. There is no test that fails when latency
   exceeds it.
8. **No DB-corruption recovery test.** SLO-04 declares "zero unhandled write failures";
   there is no test simulating a corrupted SQLite page header, a half-written WAL, or a
   filesystem-full ENOSPC during write.
9. **Test isolation depends on `freezegun` and `frozen_date` fixture, but SQLite's
   `date('now')` is not patched** (the fixture's own docstring admits this). Tests that
   cross the `freezegun`/SQLite boundary at midnight UTC may be flaky.
10. **No contract test against the Telegram callback payload schema.** The bot stores
    pending overrides in a process-memory dict keyed by `chat_id`. There is no replay,
    no nonce, no `decision_id` validation in the reason-recording path
    (`titan/integrations/telegram_bot.py:470-512`).

---

## E. Operational Weaknesses

1. **There is no deploy.** There is `python -m titan` and "leave it running". No
   supervisor, no restart-on-crash, no log rotation contract, no PID file, no graceful
   shutdown protocol for the three daemon threads.
2. **Health check is a script, not an endpoint.** `system_check.py` is run by hand. The
   FastAPI app in `titan/api/main.py` does not expose a documented `/healthz` /
   `/readyz`; if it does, it is not surfaced in the deployment guide.
3. **Structured-event infrastructure is present but partial.**
   `titan/core/structured_events.py` is well-designed, but coverage is uneven. Some
   modules emit JSON events; others still `print()`. No central event taxonomy doc
   beyond what is implied by the emitters.
4. **No metrics export.** `grep -r "prometheus\|opentelemetry\|statsd\|datadog\|sentry"`
   on `titan/` and `requirements.txt` → **zero hits**. The SLO doc describes targets
   that no instrument is measuring. SLO-01 (Garmin freshness ≥99% per 6h window over 30
   days) is not actually computed anywhere.
5. **No distributed tracing on the 12-step morning routine.** There is no per-routine
   correlation ID; you cannot answer "what did the 07:00 routine on May 9 actually do?"
   beyond reading the logs.
6. **Backup strategy is "manual copy of `titan.db`".** No retention policy enforcement,
   no restore drill, no validation that the copied file is consistent. ADR-0015 calls
   out the data-lifecycle gate for Phase 8; the gate is unimplemented.
7. **Runbooks are referenced in `docs/SLO.md` (`docs/runbooks/garmin-sync-failure.md`,
   `database-recovery.md`) but the directory does not exist** as of this audit. Either
   the runbooks were planned and never written, or they were moved.
8. **Alerting is push-to-Telegram-when-degraded.** The degraded-mode tracker
   (`titan/orchestration/daily_coach.py:95-172`) calls `telegram.send_alert`. If
   Telegram is the alert channel and Telegram is down, the alert is lost. There is no
   second channel and no quorum of channels.
9. **Two daemon threads start at process boot with no startup ordering.** A Telegram
   poller that wakes before the DB schema migration finishes will see "table not found"
   errors.
10. **Process lifecycle assumes "user is at the terminal".** No mention of unattended
    survival across reboots; no Windows service definition; no Linux systemd unit; no
    container.

---

## F. Security Weaknesses

(Augmenting the dedicated security agent's findings, which were broadly correct.)

1. **Critical — Coach RBAC bypass** (see B1). Not theoretical.
2. **High — Garmin token plaintext default** (see B6). The encryption is a feature flag
   the user must opt in to; the default is unsafe.
3. **High — Telegram override flow has no replay protection.** A long-running bot whose
   pending-prompts dict is in process memory will accept a stale override after a
   restart loses the state. The `awaiting_reason` flag is a string-typed truthy check
   (`"1"`), not a per-decision nonce. (`titan/integrations/telegram_bot.py:470-512`)
4. **High — JWT key startup validation is opt-in.** `validate_jwt_keys_at_startup()`
   exists but only fires if explicitly called from the FastAPI lifespan. Forgetting to
   wire it == silent acceptance of empty / malformed keys.
5. **Medium — Health PII in logs.** HRV, RHR, weight, and sleep are emitted into
   structured events. There is no pseudonymization or field-level redaction. Log files
   are written to `~/Documents/TITAN/logs/` with default umask.
6. **Medium — Gitleaks allowlist is path-based, not pattern-based.** A real secret in
   `test_*.py` is allowlisted by location. Use entropy-based or pattern-based rules with
   path exceptions, not whole-tree exemption.
7. **Medium — CodeQL upload disabled.** Findings are produced but not stored; trend
   analysis impossible; no policy gate.
8. **Medium — No MFA.** Bcrypt + JWT + 15-min access tokens are fine for a single coach
   logging in occasionally; weak for any actually-public deployment. Health data is
   sensitive enough to merit TOTP at minimum.
9. **Medium — `pip-audit` is declared in `requirements.txt` but not run as a gate.**
   The Starlette CVE chain was patched in 0.136.1 by hand. Next CVE will require the
   same manual surveillance.
10. **Low — `subprocess.run(command, ...)` in `persistence.py:1206`.** It is `pg_dump`
    invocation; `command` looks constructed from validated env config, but worth a
    review under a hardening pass.

---

## G. Scalability Concerns

The system is designed for **one athlete on one process on one machine**. The
architectural docs gesture at multi-athlete coaching (ADR-0046, ADR-0054); the code
reality is:

1. `DailyCoach` is constructed once and holds engine state in instance attributes.
   Adding athlete N+1 means another `DailyCoach` instance, another set of 14 engines,
   another set of daemon threads. The morning routine is invoked by a singleton
   `CoachingScheduler` that is itself wired in `main.py` to a single instance.
2. SQLite WAL handles concurrent reads; it serializes writes. Garmin sync, Telegram
   responses, and 14 science engines all write to the same DB. Per-athlete contention
   is bounded by the number of concurrent athletes; cross-athlete contention is
   unbounded because everyone shares the same file.
3. Telegram bot is single-chat-ID per process. The multi-athlete model requires either
   per-bot processes (operational nightmare) or a router on a single bot
   (architectural rewrite).
4. The 6-hour Garmin sync interval is fine for one athlete. At N athletes, each Garmin
   account has its own session token and 2FA timing; the sync thread becomes a sequential
   scan that scales linearly. Garmin Connect's rate limits are not engineered for it.
5. No caching layer for weather (one Open-Meteo call per athlete is fine; one call per
   coach × athlete is a hot spot).
6. The 12-step routine performs DB reads in a fan-out pattern. Cost per routine scales
   with athlete history; at year 3 of one athlete, individual calls may already exceed
   the SLO-02 2-second budget. There is no measurement to know.
7. SQLite max database size is 281 TB, but practical performance degrades long before
   that. There is no archival / partitioning strategy. ADR-0015 mentions one;
   implementation is pending.

---

## H. Missing Enterprise Practices

| Practice | Status |
|---|---|
| ADRs | **Present and well-maintained.** 29 ADRs with rationale, status, dates. |
| RFC / proposal process | **Partial.** SCRATCHPAD.md is a real channel; not a formal RFC. |
| Code ownership (CODEOWNERS) | **Missing.** No file. |
| Required-reviewer policy | **Implied by AGENTS.md; not enforced via branch protection in repo.** |
| Staging environment | **Missing.** Dev = prod = the user's laptop. |
| Synthetic monitoring | **Missing.** No probe checks that the system is up. |
| Load testing | **Missing.** No locust, no k6, no perf budget. |
| Reproducible environments | **Partial.** `uv.lock` is present, but no container. |
| Immutable infrastructure | **Missing.** |
| Environment parity | **Missing.** No dev/staging/prod config split. |
| Internal tooling (CLI, ops) | **Partial.** `scripts/` has audit and gate scripts. |
| Governance policies (in code) | **Strong.** Importlinter, semgrep custom rules, invariant tests. |
| Audit trail | **Half-built.** `coach_audit_log` table without write coverage. |
| Release trains | **Missing.** No release cadence, no tagged builds. |
| Progressive delivery | **Missing.** No flags, canaries, blue/green. |
| Rollback drills | **Missing.** |
| Backup verification | **Missing.** Backup is `cp`; restore is untested. |
| Data lineage | **Missing.** |
| Platform engineering practices | **Not applicable at scale of one athlete; will be needed when N>1.** |
| Operational maturity scoring | **This document is one.** |

---

## I. Recommended Improvements

### Immediate (this sprint, no architecture decision needed)

1. **Enforce coach-athlete assignment.** Replace the `if role == "COACH": return` in
   `titan/api/dependencies.py:41-46` with a query against
   `coach_athlete_assignments`. Add an integration test that a `COACH` user cannot
   access an unassigned athlete. **This is the single highest ROI fix in the repo.**
2. **Wire `validate_jwt_keys_at_startup()` into the FastAPI lifespan** so unsigned-JWT
   fallback is impossible.
3. **Promote `TITAN_GARTH_TOKEN_KEY` to a required variable.** Fail the launcher at
   startup if it is missing in production mode.
4. **Add a deduplication lock around the async morning routine.** Replace the
   `is_alive()` check at `titan/orchestration/daily_coach.py:1516` with a
   `threading.Lock` acquired non-blocking; refuse the second caller with a logged event.
5. **Add a reader lock (or migrate to a per-thread connection + WAL) for
   `DatabaseManager` reads.** Audit the 10 unguarded read methods and decide between
   acquiring `self._lock` for reads or per-call connections.
6. **Default the override-lockdown gate to *locked* on cold start.** If
   `get_override_ratio` returns `None`, require explicit operator acknowledgement before
   serving non-conservative recommendations.
7. **Migrate the 172 raw `print()` calls in `titan/` to `structured_events`.** Add a
   `ruff` rule that bans `print()` outside `scripts/` and `system_check.py`.
8. **Stop allowlisting whole test paths in `.gitleaks.toml`.** Move to commit-message
   `nosec` markers or pattern allowlists.
9. **Enable `upload: always` in `codeql.yml`** and add a severity policy.

### Short-term (next 1–2 phases)

10. **Containerize.** A two-stage Dockerfile + `docker-compose.yml` for SQLite-mode and
    PostgreSQL-mode. Pin via `uv.lock`. Build artifact = single immutable image tag.
11. **Move secrets out of `.env`-on-disk.** Wire `keyring` as the default, with `.env`
    fallback only when explicitly opted in. Document `0600` permissions enforcement on
    Linux, document Windows ACL requirements, exit if either is wrong.
12. **Stand up a real `/healthz` and `/readyz`.** `/healthz` returns 200 if process is
    alive; `/readyz` returns 200 only if the last Garmin sync, DB write, and Telegram
    ping all succeeded in their SLO window.
13. **Write the runbooks that `docs/SLO.md` references.** Create `docs/runbooks/` with:
    `garmin-sync-failure.md`, `governance-hard-stop-unexpected.md`,
    `database-recovery.md`. At minimum, list "first thing to check" → "second thing to
    check" → "escalation contact".
14. **Decompose `DailyCoach`.** Extract a `MorningRoutine` orchestrator with explicit
    step objects, each with a per-step structured event, retry policy, and idempotency
    key (`athlete_id`+`routine_date`). This is what ADR-0018 already calls for.
15. **Pin the schema in one place.** Either retire the hand-rolled migrations in
    `database.py` or retire `alembic/`. Choose one and align CI.
16. **Add a backup-and-restore CI job.** Generate a known-good DB; back it up; restore
    it; assert row counts. Fail the job on divergence.
17. **Wire `pip-audit` into CI** with a `HIGH` severity gate (today it is a manual run).
18. **Add fuzzed Garmin response tests.** A `hypothesis` strategy over the Garmin
    activity dict that the data-sanity layer must always reject or accept consistently.
19. **Add a coach-action audit middleware** that writes `coach_audit_log` on every
    `/athletes/{id}/...` GET and POST.

### Long-term (Phase 8+ and beyond)

20. **Build a real CD pipeline.** Tagged release → built image → deployed to a staging
    box → smoke tests → manual promote → production. With rollback as a button push.
21. **Migrate to PostgreSQL and treat it as the only path.** SQLite stays for dev
    only. Drop the parity matrix; choose one.
22. **Adopt OpenTelemetry.** Spans for the 12-step routine, metrics for SLO-01 through
    SLO-06 emitted to a backend (Grafana Cloud, Datadog, OTel collector — anything).
    The SLO doc has no teeth without instruments.
23. **Multi-tenant rearchitecture.** Per-athlete coaching context as a first-class
    object passed through the science layer; per-tenant rate limits; per-tenant
    Telegram routing; per-tenant background scheduling.
24. **Disaster recovery drill, quarterly.** Wipe the DB, restore from backup, run a
    smoke routine, document the RTO/RPO observed. Reference Stripe's "GameDay" and
    Cloudflare's chaos exercises as the model.
25. **Move the human-override path off Telegram.** Telegram is one possible UI; the
    *contract* is "an authenticated override that mutates safety state". Build that as
    a REST endpoint with proper auth, log all overrides immutably, and let Telegram be
    one of N clients.

---

## J. What Large Companies Would Probably Do

- **Google**: Treat the 7-gate governance system as a *control plane* with its own
  binary, its own SLOs, and its own error budget. Force every consumer (DailyCoach,
  WeeklyPlanner, manual override) through gRPC calls so the gate logic cannot be
  inlined or bypassed. Add a *Borgmon-style* fitness function (one already exists in
  spirit at `tests/test_architectural_invariants.py`).
- **Netflix**: Replace SQLite with a regional Cassandra cluster; introduce *Chaos
  Monkey* against the Garmin sync thread and the morning routine; require every release
  to pass a canary at 1% of athletes before promotion.
- **Stripe**: Idempotency keys on every external call (Garmin, Telegram, Open-Meteo)
  *and* on every internal mutation (`save_daily_metric`, `save_governance_outcome`). A
  morning routine becomes a deterministic replay against any historical day.
- **Cloudflare**: Move the bot off polling, put it behind their Workers; use Durable
  Objects for per-athlete state; treat the rate-limit budget as a first-class signal.
- **Amazon (Working Backwards)**: Author a press release for "what TITAN-as-a-service
  looks like in 2027"; reject the multi-athlete features that don't survive the press
  release. Spoiler: most don't, until RBAC, audit, and tenancy are real.
- **Meta**: Wrap the Telegram bot in a feature-flag system (Murmur / Gatekeeper
  equivalent). No safety-altering command lands without a kill switch.
- **Datadog**: Instrument before deploying. Six SLOs without a metric pipeline is six
  promises with no enforcement.
- **GitLab**: CODEOWNERS, signed commits, merge train, dogfood the CD pipeline; their
  handbook-style culture is a good match for this repo's existing AGENTS.md ethos.
- **OpenAI**: Treat the LLM coaching narratives (the `OPENAI_API_KEY` env var hint in
  the README) as a *capability* with its own eval suite, rate limit, prompt-version
  registry, and rollback. Today it is a config knob; there is no prompt repo and no
  benchmarking dataset.
- **High-performance SaaS (Linear, Vercel, Notion-class)**: A single tagged release
  every Monday; one-click rollback; an internal "what changed since Friday" digest
  built from commits + ADRs + SCRATCHPAD entries.

---

## K. Technical Debt Register

| # | Item | Impact | Urgency | Complexity | Suggested mitigation |
|---|---|---|---|---|---|
| TD-01 | Coach RBAC not enforced (B1) | Critical (PII leak) | Now | Low | Query `coach_athlete_assignments`; add test. |
| TD-02 | Unprotected SQLite reads (B2) | Critical (silent corruption) | Now | Medium | Reader lock or per-thread connections; chaos test under load. |
| TD-03 | Override-lockdown fails open (B3) | High (safety) | Now | Low | Default-deny on `None` ratio; require operator ack. |
| TD-04 | DailyCoach god-orchestrator (B4) | High (testability) | This phase | High | Extract MorningRoutine + step objects; per-step events. |
| TD-05 | Async routine dedup race (B5) | High (data integrity) | Now | Low | `threading.Lock` non-blocking acquire. |
| TD-06 | No deployable artifact (B6) | High (ops) | This phase | Medium | Two-stage Dockerfile + uv.lock; CI publishes image. |
| TD-07 | CodeQL upload disabled (B7) | Medium (security trends) | Soon | Trivial | Flip to `always`; add severity gate. |
| TD-08 | Schema in two places (B8) | Medium (migration risk) | Pre-Phase-8 | High | Pick one source of truth; align CI. |
| TD-09 | `coach_audit_log` not written (B9) | Medium (forensics) | Soon | Low | Audit middleware on all coach routes. |
| TD-10 | 172 `print()` calls (B10) | Medium (observability) | Continuous | Low | Ruff rule + migration sweep. |
| TD-11 | No metrics export (E4) | High (SLO inert) | Phase 8 | Medium | OpenTelemetry; one backend; six metrics. |
| TD-12 | Runbooks referenced but missing (E7) | Medium (oncall) | Soon | Low | Author three runbooks called out in `docs/SLO.md`. |
| TD-13 | Threshold values mirrored, not imported | Medium (silent divergence) | Now | Trivial | Import canonical constants; remove duplicates. |
| TD-14 | Persistence ABC unused (C2) | Low (cleanup) | Optional | Low | Delete or activate; do not leave half. |
| TD-15 | No load/perf test (D7) | Medium (SLO-02 unmonitored) | Phase 8 | Medium | Locust suite for the morning routine path. |
| TD-16 | No DB-corruption recovery test (D8) | Medium (DR) | Pre-Phase-8 | Medium | Chaos test with corrupted WAL + ENOSPC. |
| TD-17 | Telegram replay protection (F3) | High (safety control) | Now | Low | Per-decision nonce; persist pending state. |
| TD-18 | Garmin plaintext token default (F2) | High (creds) | Now | Trivial | Require key in non-dev mode. |
| TD-19 | Gitleaks allowlist too broad (F6) | Medium (leak risk) | Soon | Low | Move to pattern-based, not path-based. |
| TD-20 | No CODEOWNERS file (H) | Medium (review gating) | Soon | Trivial | Add `.github/CODEOWNERS`. |

---

## L. Production Readiness Score

Each dimension scored 0–10 with a one-line justification.

| Dimension | Score | Justification |
|---|---|---|
| Architecture | 5 | Strong contracts, layered design, ADR discipline; god-orchestrator and unused abstractions drag it down. |
| Testing | 6 | High test count, adversarial/chaos/property suites, invariants enforced; no real integration, no load, no DR tests. |
| Observability | 4 | Structured events module exists; no metrics, no traces, partial adoption, runbooks missing. |
| Operations | 3 | No deploy unit, no supervisor, no rollback; "user is at the terminal" model. |
| Scalability | 3 | Designed for one athlete; multi-tenant story is aspirational. |
| Maintainability | 6 | Clean code style, ruff/semgrep/importlinter active; 1.7 kLOC god class hurts. |
| Security | 4 | Auth scaffolding solid; RBAC, audit, secrets handling, replay protection all underbuilt. |
| Automation | 6 | CI is genuinely good (16 jobs, gates, mutation testing scaffold); CD is nonexistent. |
| Documentation | 7 | ADRs, AGENTS.md, ARCHITECTURE.md, SLOs, parity matrix — far above hobby norms; some drift (README in Greek + module count mismatches). |

**Weighted overall: ~4.8/10.** Operational and security dimensions hold the score down.

---

## M. Brutal Honesty — What Will Fail First In Real Production

In order of probability, with the failure mode and the first user-visible symptom:

1. **Garmin auth flow breaks for the first user.** Garmin changes their login flow
   regularly. The `garminconnect==0.3.2` library is a thin wrapper; when Garmin
   rotates, the morning routine silently degrades to "no fresh data", governance enters
   conservative mode (correctly), and the user gets a generic "easy day" recommendation
   for a week before anyone notices. ADR-0050 acknowledges this fragility but the
   mitigation (BiometricRouter + ManualEntryAdapter) only buys you the fallback if the
   user knows to enter data manually.
2. **SQLite database corruption on power loss / ungraceful shutdown.** WAL helps but is
   not magic. The system has no integrity check on startup, no `PRAGMA
   integrity_check`, no `quick_check`. The first time the laptop loses power mid-write,
   the next morning's routine reads a torn page; behavior is undefined.
3. **A coach is given access to an athlete and quietly reads every other athlete's
   data.** See B1. This is the failure mode that ends the product.
4. **Telegram bot token leaks.** Either via a backup of `~/Documents/TITAN/` or via a
   chat ID being shared in a screenshot. There is no token rotation runbook; revocation
   is "go to @BotFather and regenerate", but the new token is then pasted into
   `.env` and survives the next backup.
5. **Two morning routines run in parallel** (cron + manual `/sync`). User sees
   duplicate Telegram messages, double-counted training load for the day. Recoverable,
   but the data integrity rounding error compounds.
6. **CTL/ATL drifts off-true** because of read/write races (B2). No alarm fires; the
   athlete just trains slightly wrong for months.
7. **A Phase 8 PostgreSQL switch hits a schema-divergence bug** because
   `database.py` migrations and `alembic/` migrations are not the same.
8. **Cron skips a day** because the Daily Coach scheduler is in-process and the process
   crashed at 03:00. There is no external scheduler, no missed-run detection.
9. **Token expiry under `TITAN_GARTH_TOKEN_KEY` rotation.** When the key changes, every
   existing token becomes unreadable. There is no migration tool for the on-disk
   encrypted token files. The user just loses Garmin auth one day.
10. **Out-of-disk on the laptop.** SQLite WAL grows; logs grow; no rotation policy;
    governance writes start failing; degraded-mode tracker fires the alert to the
    same logs that can't be written.

The pattern across all 10 failure modes: **the system has carefully built safety
controls inside the application, and almost no safety controls around the
application.** Engineering discipline does not survive contact with operational
neglect. The fix is to extend the same rigor outward — to the deploy pipeline, the
observability stack, the secrets layer, and the multi-tenant data plane — before
adding more features inside.

---

*End of audit. Findings should be promoted into `TECHNICAL_DEBT.md` through the
SCRATCHPAD OBS → DEC protocol described in `CLAUDE.md §Architect Scratchpad Review
Protocol`. The 20 entries in §K are the recommended starting set.*
