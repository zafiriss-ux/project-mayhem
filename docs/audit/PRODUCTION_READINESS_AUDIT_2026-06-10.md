# TITAN OS — Production Readiness Audit (2026-06-10)

**Scope:** Full repository — architecture, data layer, API/security, orchestration/integrations,
worker, observability, CI/CD, deployment, test architecture, governance/documentation.
**Method:** Six parallel domain reviews with file:line evidence, followed by manual verification
of all Critical findings against source. Claims that did not survive verification were corrected
or dropped (one was: see F-13 note on `/metrics`).
**Predecessor:** `PRODUCTION_READINESS_AUDIT.md` (2026-05-15, 45/100). This audit re-baselines
after Phases 25–27 work.

---

## A. Executive Summary

TITAN OS is an unusually disciplined solo-maintained system: 59 ADRs, ~3,050 tests, layered CI
gates, import-linter contracts, runbooks, SLO doc, structured events. The **code quality and
process discipline are well above hobby grade. The operational and security posture is not yet
production grade**, and several governance claims in CLAUDE.md are no longer true of the code.

**Top critical problems (verified):**

1. **Coach RBAC athlete-scoping is not enforced on the most dangerous routes.**
   `titan/api/main.py:460-468` — `/coach/overrides`, `/coach/export`, `/coach/delete` accept an
   `athlete_id` but gate only on `Depends(require_coach)` (role check). The assignment-scoped
   dependency `require_coach_athlete_access` (`titan/api/dependencies.py:71`) exists but is wired
   only to the dashboard route (`main.py:449`). Any coach can override governance for, export, or
   delete data of **any** athlete. This contradicts the Phase 27 GO verdict's "B1 RESOLVED".
2. **SQLite foreign-key enforcement is off everywhere.** `PRAGMA foreign_keys = ON` appears
   nowhere under `titan/`. All FK clauses in the DDL are decorative; orphaned rows and silent
   referential corruption are possible today.
3. **The morning routine is not crash-idempotent.** `titan/worker/__init__.py:177-195` keeps
   per-athlete `last_run_dates` in process memory; a worker crash/restart replays the routine
   (duplicate governance outcomes, double-counted load, duplicate Telegram sends). The
   `flock`-based single-instance lock has no stale-lock/PID recovery.
4. **Safety gates can be bypassed by the failure path.** An exception inside
   `governance.apply_constraints()` propagates out of `_run_step` (daily_coach.py) without
   downgrading the session plan to REST/EASY — the system fails open exactly where ADR-0009
   demands it fail closed. SLO-05 ("zero bypass events") is not enforceable by the current code.
5. **Telegram trust boundary fails open.** `titan/integrations/telegram_bot.py:181-183` — if
   `TELEGRAM_CHAT_ID` is unset, **every** Telegram sender is trusted (warning logged, then
   allowed), including override commands. Override nonces live in a module-level dict
   (`telegram_bot.py:37`) and evaporate on restart.
6. **No disaster recovery.** Backups are written to the *same* volume as the database
   (`scripts/backup.sh`), retention is 7 days, restores are never tested, and the CI
   backup-verify job exercises a 2-row toy DB. A single disk failure loses data **and** backups.
7. **No release engineering.** Version is hardcoded `0.1.0` in `pyproject.toml`; no release
   workflow, no tagged/immutable artifacts, no registry images, therefore **no rollback path**.
   Deployment is `git clone + pip install` or a locally built compose stack.
8. **The governance record has drifted from reality.** CLAUDE.md says 3,047 tests; collection is
   ~3,056. Phase 27 GO says "B1–B7 all RESOLVED" while B1 is demonstrably open (item 1 above)
   and B2/B5 from the May audit never received debt entries. ADR-0057 is still "Proposed" while
   shipped. The audit trail — this project's strongest asset — is rotting at the edges.

**Production readiness estimate:**
- **Single-athlete, self-hosted, benevolent operator: ~55/100.** Deployable with eyes open,
  after items 2, 3, 4, 6 are fixed.
- **Multi-athlete / any second human user: ~30/100 — blocked.** Item 1 is a privacy breach by
  construction; SQLite single-writer + shared-volume compose is an architecture ceiling that
  ADR-0044 (PostgreSQL gate) already acknowledges.

**Maturity level:** "Advanced solo project with enterprise-grade *process aspiration* and
small-team *operational reality*." Strong Level 2–3 on code/CI; Level 1 on ops, DR, release
engineering, and on-call readiness.

---

## B. Critical Risks

| # | Risk | Severity | Why it matters / probable failure mode | Realistic production consequence |
|---|------|----------|----------------------------------------|----------------------------------|
| B-1 | Coach RBAC scoping gap (`main.py:460-468`) | **Critical** | Role check without assignment check; `require_coach_athlete_access` exists but unused on override/export/delete | Cross-athlete health-data exfiltration and governance override; GDPR Art. 5/32 exposure the day a second athlete exists |
| B-2 | FK enforcement off (no `PRAGMA foreign_keys`) | **Critical** | DDL FKs silently unenforced (SQLite default) | Orphaned `training_log`/gear rows; corruption discovered months later during analytics, unrecoverable attribution |
| B-3 | Worker replay on crash (`worker/__init__.py:177`) | **Critical** | In-memory dedup; container `restart: unless-stopped` guarantees the restart that triggers it | Duplicate governance outcomes poison calibration/outcome tracking (Phase 27's core data), duplicate athlete messaging |
| B-4 | Fail-open governance on exception path | **Critical** | `_run_step` re-raises without forcing REST; partially-evaluated plan survives | Athlete receives a quality-session prescription on a day H2 (HRV collapse) should have hard-stopped — the exact harm the system exists to prevent |
| B-5 | Telegram fail-open trust + volatile nonces (`telegram_bot.py:37,181`) | **Critical** | One missing env var = open command surface; restart clears replay protection | Stranger in a group chat triggers `/override` on a hard stop; untraceable |
| B-6 | Same-volume backups, no restore testing | **Critical** | Backup ≠ DR; corruption is faithfully backed up; 7-day window | Disk failure or late-detected corruption = total loss of multi-year athlete history |
| B-7 | No versioned artifacts / rollback | **Critical** | Cannot answer "what is running in prod?" or "roll back to yesterday" | A bad migration (forward-only, see B-8) plus no rollback = extended outage with manual DB surgery |
| B-8 | Forward-only migrations without guard | **High** | No `if user_version > SCHEMA_VERSION: raise`; older binary opens newer DB silently | Post-rollback app misreads newer schema; silent miswrites |
| B-9 | `athlete_id` 'default'/'owner' drift (migrations v7–v18; `degraded_mode_state` never backfilled, database.py v9) | **High** | Remedial v18 backfill covered `training_log` only | Phase 27 cohort queries silently exclude legacy rows; degraded-mode state invisible per athlete |
| B-10 | Single `RLock` serializes all writes; API + worker share one SQLite file via compose volume | **High** | Two processes, one DB file, in-process lock does not span processes — protection is WAL + busy_timeout only | Lock contention/`SQLITE_BUSY` cascades at modest concurrency; ADR-0044 already names PostgreSQL as the exit, it is just unscheduled |
| B-11 | Audit log written best-effort after response (`main.py:295-298`) | **High** | Override executes, audit write fails, no record | ADR-0042's "first-class audit" is not — disputes about overrides become unresolvable |
| B-12 | Secret scan covers `HEAD~1..HEAD` on push; CodeQL weekly-only | **High** | Multi-commit pushes partially scanned; 7-day SAST window | Leaked credential or injection sits on main for up to a week |
| B-13 | No request body limits; lockout enables username enumeration; rate-limiter LRU eviction bypass (`main.py:95-149`) | **High** | Memory exhaustion via giant JSON; bcrypt on 1 MB password; per-key state evictable | Cheap single-host DoS; account enumeration |
| B-14 | Data-trust verdict computed but unenforced (daily_coach.py ~1117-1124) | **High** | `overall_trust=INVALID` does not downgrade the session; only staleness does | Athlete trains on data the system itself classified as invalid |
| B-15 | Telegram polling thread can die silently; no watchdog (`telegram_bot.py:889-916`) | **High** | Worker keeps running, deaf to `/sync`, `/override` | Operator's primary control channel offline for days, unnoticed |

---

## C. Architectural Weaknesses

1. **Process-shared SQLite is the load-bearing flaw.** `titan-api` and `titan-worker` are separate
   containers sharing `/data/titan_core.db`. Every in-process protection (the `RLock`, the
   transaction-depth counter in `database.py:2076-2098`) is invisible across that boundary.
   Cross-process integrity rests entirely on WAL + busy_timeout. ADR-0044 was right; it needs a
   date, not just acceptance.
2. **Dual migration systems.** Hand-rolled `_apply_v1.._v25` for SQLite plus a frozen Alembic tree
   for PostgreSQL, with `alembic.ini` pointing at a SQLite DSN that `README_FREEZE.md` forbids.
   Nothing tests parity between the two; Phase 8A cutover inherits silent divergence.
3. **Frozen column-snapshot migrations enforced by comments.** v8/v13/v24 table-recreation
   migrations carry "DO NOT ADD columns" comments (database.py:912, 1101, 1293) as the only
   guard against silently NULLing new columns. The comment exists because the bug already
   happened once (TD-08-R3).
4. **DailyCoach remains an orchestration god-object.** ADR-0058 Phases A/B genuinely extracted
   EngineRegistry and TitanEffectBus, but `daily_coach.py` still owns staleness gates, trust
   arbitration, degraded-mode flags, weather fallbacks, AFI buffering, and step sequencing.
   The frozen `EngineRegistry` dataclass is then mutated via `dataclasses.replace` setters —
   immutability theater that costs allocation churn without buying safety.
5. **Incomplete hydration is shipped as TODO.** `engine_registry.py:67-72` — CS tracker and APL
   start cold on every registry build (TODO-P26-04b/c), so CS confidence and APL adaptation are
   effectively disabled, yet Phase 26 is recorded CLOSED.
6. **`getattr`-defensive coupling hides dead features.** The HRV baseline-drift check is invoked
   via `getattr(self.hrv, "check_baseline_drift", None)` — if the method is absent or renamed,
   drift detection is a silent no-op forever.
7. **Module-count ceiling (80) is tracked manually** and was last verified months ago — a
   governance control with no sensor attached.

## D. QA / Test Weaknesses

1. **Test count is a KPI, and it is wrong.** CLAUDE.md snapshot (3,047) vs ~3,056 collected.
   Manual snapshot discipline with no hook/CI gate = guaranteed drift. Counting tests is the
   weakest possible quality signal to enshrine in governance.
2. **E2E layer is stubs all the way down.** `tests/e2e/conftest.py` defines 10+ hardcoded stubs
   (StubGovernance returns `governance_clean: True` unconditionally). Nothing validates that
   stubs match real engine contracts; nothing in pytest exercises the Docker path, container
   restart persistence, or concurrent API+worker access. The one real deployment test
   (`scripts/docker_smoke_test.sh`) is a bash script outside the suite.
3. **Zero contract testing for Garmin/Telegram/weather.** All integration tests mock the
   provider. Garmin breaking its response shape (it has before — see ADR-0050's existence)
   reaches production undetected.
4. **Migration chain untested end-to-end on realistic data.** Individual migrations have tests;
   no test builds v1 data, runs v1→v25, and asserts row-level survival — precisely where the v8
   frozen-snapshot class of bug lives.
5. **Root mega-files duplicate the `tests/` tree.** ~5.8k LOC across root `test_*.py` overlapping
   `tests/titan/**` (same classes, different fixtures). Every behavior change is a 2–3 place
   edit. ADR-0059 unified *execution*, not *layout*.
6. **6 skipped tests are deferred-TDD placeholders** (`tests/test_t5_50_session_type_map.py`)
   guarded by `pytest.skip("...not yet implemented")` — they pass CI forever even if the planned
   function is never built or is renamed.
7. **52 naked `datetime.now()` calls in tests**; `frozen_date` fixture exists but is opt-in.
   Midnight/DST flakiness is latent.
8. **Strengths worth keeping:** Hypothesis property tests for the math core, determinism
   snapshot (10× bit-identical morning routine), settings-singleton auto-reset, flakiness
   tracker and mutation scripts (run them on a schedule, not on demand).

## E. Operational Weaknesses

1. **No staging environment.** First execution of any change in a multi-container topology is
   production.
2. **Worker is unobservable.** API mounts `/metrics` (`main.py:473`) but the worker — where the
   morning routine, Garmin sync, and governance actually run — exposes no metrics endpoint, has
   no healthcheck in compose, and its lock file is the only liveness signal.
3. **Alerting is a mosaic.** Some failures send Telegram alerts (RHR baseline missing), some emit
   `slo_alert` JSON log lines that nothing routes (nutrition missing, HRV baseline missing), some
   are swallowed (staleness alert when Telegram itself is down — the failure mode most likely to
   co-occur). SLO.md defines targets nothing measures: no Prometheus rules, no Alertmanager, no
   error-budget computation.
4. **Garmin 429 exhaustion degrades silently** (`garmin_sync.py:466-490`): retries don't
   increment `_consecutive_failures`, so the degradation tracker stays green while the athlete
   gets a day of stale-data coaching.
5. **compose is not production-shaped:** no resource limits, no log rotation, no max-restart
   policy, no network isolation, no worker healthcheck.
6. **Runbooks are good but unlinked** — errors don't reference them; at 3am nobody greps
   `docs/runbooks/`.
7. **Bus factor = 1**, encoded in governance: phase closes, scratchpad rituals, and
   Architect-only approvals all assume one specific human is available.

## F. Security Weaknesses

(Verified highlights; see B-table for the criticals.)

- **F-1** RBAC scoping gap — B-1. The fix is one dependency swap per route plus tests.
- **F-2** Telegram allow-all on missing chat ID — should fail startup, or `_is_trusted` should
  return `False` when unconfigured (fail-secure), `telegram_bot.py:181`.
- **F-3** Override nonces in memory — persist to a `coach_override_nonces` table with
  `consumed_at`; validate nonce↔decision binding.
- **F-4** JWT key validation lives only in the lifespan hook (`main.py:264`) — make it blocking
  at import/app-construction.
- **F-5** CSRF cookie `httponly=False` (`main.py:337-343`) while the token is also returned in
  the body — set HTTPOnly; the body copy is sufficient for clients.
- **F-6** No request size limits; bcrypt over unbounded password field — enforce at middleware or
  reverse proxy.
- **F-7** Username-keyed lockout discloses account existence (423 vs 401 pattern) — hybrid
  IP+username limits, uniform responses.
- **F-8** Audit middleware post-response and best-effort (`main.py:295-298`) — write-ahead audit
  or fail the request on audit failure for override-class actions.
- **F-9** HSTS deliberately omitted pending TLS termination decision (C-2) — fine, but C-2 has no
  owner or deadline.
- **F-10** `TITAN_GARTH_TOKEN_KEY` optional → Garmin tokens storable in plaintext.
- **F-11** gitleaks push-scan covers last commit only; CodeQL weekly only (`secret-scan.yml`,
  `codeql.yml`).
- **F-12** No image scanning, no SBOM, no pin-parity check between `pyproject.toml` (unpinned
  `uvicorn`) and `requirements.txt` (pinned); `pip-audit` carries a permanent un-expiring CVE
  ignore (GHSA-gc5v-m9x4-r6x2).
- **F-13** *Correction to a prior internal claim:* API Prometheus metrics **are** exposed
  (`main.py:473`). The genuine gap is worker-side metrics and the absence of any scrape/alert
  stack, not a missing endpoint.
- **Strengths:** RS256 with enforced algorithm, refresh rotation with revocation and device cap,
  bcrypt, double-submit CSRF with timing-safe compare, sensible security headers, per-role rate
  limits, semgrep rule for naive datetimes, gitleaks + CodeQL existing at all.

## G. Scalability Concerns

1. **Hard ceiling: one SQLite file, one effective writer.** The compose topology already has two
   writer-capable processes. Anything beyond a handful of athletes makes `SQLITE_BUSY` and
   lock-wait latency the dominant failure mode. PostgreSQL (ADR-0044) is the only real answer;
   everything else is tuning.
2. **In-memory rate limiting, nonces, scheduler state, degradation counters** — all per-process.
   The first horizontal scale-out (second API replica) silently breaks all four.
3. **Worker is a singleton by design** (flock) with no work-queue abstraction; multi-athlete
   morning routines serialize through one thread with synchronous 60/120/240s Garmin backoffs
   blocking the loop.
4. **No load-test gate.** `scripts/load_test.py` exists with SLO definitions but runs only by
   hand; no latency regression is detectable in CI.
5. **Cohort analytics (Phase 27) on SQLite** means cross-athlete aggregation queries against a
   write-contended single file — measure before building.

## H. Missing Enterprise Practices

- Release trains / semantic versioning / immutable tagged artifacts; rollback drills
- Staging isolation + environment parity; canary or even blue-green for the API
- Feature flags (governance threshold changes ship as code deploys today)
- Offsite, encrypted, restore-tested backups; documented RPO/RTO (currently: undefined / undefined)
- Synthetic monitoring (a cron that hits `/readyz` and a fake-athlete morning routine daily)
- Alert routing (Alertmanager→Telegram/email) bound to the SLOs that already exist on paper
- SBOM + image scanning + dependency-drift automation (Renovate/Dependabot)
- Branch protection as code/documentation; required status checks enumerated
- Incident process: post-mortems folder exists (good) but no severity taxonomy, no on-call doc
- Chaos/fault-injection: kill the worker mid-routine in a test; nothing does this today
- CODEOWNERS with real subsystem ownership; deputy-architect escape hatch for bus factor

## I. Recommended Improvements

**Immediate (days — do before any further Phase 27 feature work):**
1. Swap `require_coach` → `require_coach_athlete_access` on `/coach/overrides|export|delete`; add
   cross-athlete denial tests. (B-1)
2. `PRAGMA foreign_keys = ON` at connect + one orphan-detection test. (B-2)
3. Fail-closed wrapper: any exception in `apply_constraints`/hard-stop evaluation forces
   `session_type=REST` with a structured event. (B-4)
4. `_is_trusted` → fail-secure; require `TELEGRAM_CHAT_ID` at startup. (B-5)
5. Persist scheduler `last_run_dates` (reuse `scheduler_state` table pattern). (B-3)
6. Add `if user_version > SCHEMA_VERSION: raise` guard. (B-8)
7. `PRAGMA integrity_check` after every backup; cron `verify_backup.py`; copy backups off-volume
   (even `rclone` to object storage is enough). (B-6)
8. Fix CLAUDE.md snapshot or automate it; reconcile the "B1–B7 RESOLVED" claim — B1 is open.

**Short-term (weeks):**
9. Release workflow: tag → build multi-arch image → Trivy scan → SBOM → push registry; deploy
   only tags; write the rollback runbook.
10. Persist Telegram override nonces; bind to decision IDs. (F-3)
11. Body-size middleware; uniform auth failures; HSTS once TLS termination (C-2) is decided —
    give C-2 an owner and a date.
12. Worker `/metrics` (or push-gateway) + compose healthcheck + polling-thread watchdog; route
    `slo_alert` events to Telegram via one chokepoint function.
13. Migration v26: backfill `degraded_mode_state` athlete_id; CHECK constraint on `data_source`;
    schema-parity test that diffs `database.py` final schema against Alembic head.
14. One real e2e: compose up in CI, write data, restart containers, assert persistence +
    `/readyz` (promote `docker_smoke_test.sh` into the gate).
15. Staging compose file + deploy-on-merge.
16. CodeQL on PR/push; gitleaks full-range scan on push.

**Long-term (quarters):**
17. Execute ADR-0044: PostgreSQL with the already-frozen Alembic tree; retire hand-rolled
    migrations; this dissolves B-2/B-8/B-10 and the dual-migration debt at once.
18. Feature-flag layer for governance thresholds; shadow-evaluate new gates (ADR-0014 already
    pioneered shadow mode for ML — generalize it).
19. Contract tests for Garmin/Telegram/weather (recorded fixtures + schema validation), nightly
    against live sandbox creds.
20. Consolidate root mega-tests into `tests/`; mark unit vs integration; fast `-m unit` gate.
21. Restore drills (monthly, scripted, results recorded); define RPO/RTO in SLO.md.
22. Reduce CLAUDE.md/TECHNICAL_DEBT.md to generated artifacts where possible (counts, phase
    status) — governance facts should come from sensors, not memory.

## J. What Large Companies Would Probably Do

- **Stripe/Google:** make the audit log transactional with the action (B-11) — an override that
  isn't durably audited *fails*. Authorization decisions centralized in one policy layer, not
  per-route `Depends` choices a developer can pick wrong (B-1 is exactly the bug this prevents).
- **Netflix:** assume the worker dies mid-routine — chaos test it weekly; idempotency keys on
  every external effect (Telegram send, outcome write), not in-memory date stamps.
- **Amazon:** no deploy without a rollback story; every artifact immutable and versioned; the
  "what is running right now?" question answerable from a tag, not `git log` on the host.
- **Cloudflare:** fail-closed on trust-boundary ambiguity — unset `TELEGRAM_CHAT_ID` would never
  mean "everyone", it would mean "no one".
- **Datadog:** the worker's silence is the alert — heartbeat metric with absence-alerting, so a
  dead poller pages within minutes rather than being discovered via a confused athlete.
- **GitLab:** runbooks linked from error strings and alerts; handbook-first means CLAUDE.md
  numbers are generated by CI, never typed by hand.
- **Meta:** kill the test-count KPI; measure mutation score and contract coverage instead.

## K. Technical Debt Register (new items surfaced by this audit)

| ID | Item | Impact | Urgency | Complexity | Mitigation |
|----|------|--------|---------|------------|------------|
| PRA-01 | RBAC scoping on coach override/export/delete | Privacy breach, governance bypass | Now | Low (dependency swap + tests) | I-1 |
| PRA-02 | `PRAGMA foreign_keys` off | Silent referential corruption | Now | Trivial + data audit | I-2 |
| PRA-03 | Fail-open governance exception path | Safety-critical miscoaching | Now | Low | I-3 |
| PRA-04 | Telegram fail-open trust; volatile nonces | Unauthorized control | Now | Low/Medium | I-4, I-10 |
| PRA-05 | Worker replay on restart; flock staleness | Data poisoning of Phase 27 calibration | Now | Medium | I-5 |
| PRA-06 | Same-volume backups; no restore tests; RPO/RTO undefined | Total data loss | High | Medium | I-7, I-21 |
| PRA-07 | No release/rollback pipeline | Unrecoverable bad deploys | High | Medium | I-9 |
| PRA-08 | Downgrade guard missing; forward-only migrations | Silent schema mismatch after rollback | High | Trivial | I-6 |
| PRA-09 | `athlete_id` legacy drift incl. `degraded_mode_state` | Cohort queries silently wrong | High | Low (v26 backfill) | I-13 |
| PRA-10 | Dual migration systems without parity test | Phase 8A cutover corruption | Medium | Medium | I-13, I-17 |
| PRA-11 | Worker unobservable; alerts unrouted | Multi-day silent failure | High | Medium | I-12 |
| PRA-12 | Stub-only e2e; no compose/concurrency/migration-chain tests | Prod-only failure classes | High | Medium | I-14, I-19, I-20 |
| PRA-13 | Garmin 429 exhaustion invisible to degradation tracker | Stale-data coaching, no alert | Medium | Low | E-4 fix |
| PRA-14 | Data-trust verdict unenforced | Training on invalid data | Medium | Low | enforce INVALID→REST |
| PRA-15 | EngineRegistry CS/APL cold-start TODOs shipped | Features silently inert | Medium | Medium | finish TODO-P26-04b/c |
| PRA-16 | Governance-doc drift (test counts, B1–B7 claim, ADR-0057 status, B2/B5 untracked) | Audit trail untrustworthy | High | Low (process) | I-8, I-22 |
| PRA-17 | DoS surface: body size, lockout enumeration, limiter eviction | Cheap availability attacks | Medium | Low | I-11 |
| PRA-18 | Supply chain: SBOM/scanning/pin-parity/CVE-ignore w/o expiry | Vulnerable images ship | Medium | Low | I-9, I-16 |

## L. Production Readiness Score

| Dimension | Score /10 | Note |
|-----------|-----------|------|
| Architecture | 6 | Clean layering & ADR discipline; SQLite-shared-by-two-processes and god-orchestrator cap it |
| Testing | 6.5 | Huge, partly excellent (property/determinism); inverted pyramid, stub-only e2e, count-as-KPI |
| Observability | 3.5 | Structured events + API `/metrics` exist; worker dark, nothing scrapes, nothing alerts |
| Operations | 3 | Runbooks good; no staging, no DR, bus factor 1, manual rituals |
| Scalability | 3 | Single-writer SQLite + in-memory state everywhere; honest ceiling acknowledged in ADR-0044, unscheduled |
| Maintainability | 6 | Strong conventions; doc sprawl, duplicate test trees, comment-enforced invariants |
| Security | 4.5 | Genuinely good crypto/auth core undermined by RBAC gap, fail-open trust, missing limits |
| Automation | 6.5 | Excellent CI gates; nothing automates release, deploy, backup verify, or governance bookkeeping |
| Documentation | 6 | Exceptional volume and ADR quality; drifting facts erode trust in all of it |
| **Overall** | **~5/10** | Single-athlete: deployable after Immediate fixes. Multi-athlete: blocked on PRA-01 + ADR-0044. |

## M. Brutal Honesty — What Fails First

1. **The first real incident will be invisible.** The most likely failure chain today: Garmin
   starts 429-ing → retries exhaust silently (degradation counter doesn't move) → staleness gate
   clamps to EASY → the Telegram alert about it fails because Telegram is the thing that's flaky →
   the athlete gets a week of EASY days and loses trust in the system before any human notices.
   Every link in that chain is a finding above (E-3, E-4, B-15).
2. **The first second user is a breach.** Add one coach account in current code and B-1 makes
   athlete data and governance overrides cross-readable by construction. This is not a
   hypothetical hardening item — it's the gap between the README's pitch and the code.
3. **The first crash during the morning routine corrupts Phase 27's foundation.** Calibration
   and cohort analytics consume `governance_outcomes`; worker replay (B-3) double-writes exactly
   that table. The project's flagship feature is being built on a table its own scheduler can
   poison.
4. **The first disk failure ends the project.** Years of training history, one volume, backups
   on the same volume, never restored. Nothing else in this report matters as much per dollar of
   fix cost.
5. **The governance system will be the last to know.** CLAUDE.md, the phase log, and the GO
   verdict already disagree with the code and with each other. The discipline that built this
   project is degrading into ceremony: numbers typed from memory, statuses that don't track
   implementation, rituals one person performs. Either wire the governance facts to sensors
   (CI-generated counts, status checks, ADR linters) or accept that the documentation will
   asymptotically describe a system that no longer exists.

The encouraging part: every Critical above has a small, well-localized fix, and the repo's own
ADRs (0044, 0042, 0009, 0050) already *predicted* most of these failure classes. The gap is not
knowledge — it is scheduling the unglamorous work ahead of the next feature phase.
