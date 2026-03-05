# ADR-0019 — Engineering Audit V3: Architectural Decisions

**Date:** 2026-03-05
**Status:** Accepted
**Deciders:** Architect + Engineering Lead
**Source:** Engineering Audit V3 (2026-03-05) + supplementary analyst review (2026-03-05)
**Phase:** 7.7 — Audit V3 Hardening Sprint
**Supersedes:** Nothing. Supplements ADR-0018.

---

## Context

Engineering Audit V3 (2026-03-05) performed a full read-only assessment of the system
after Phase 7.6 closed (ADR-0018 A1/A2/A3 implemented). The audit confirmed:

- Test suite: 1435 tests, 100% green, strict-warning mode
- Coverage: ~92.5%
- ADR-0018 A1 (cursor race): resolved for the 6 originally scoped write methods
- ADR-0018 A2 (routine thread join): resolved — `main.py` joins before `db.close()`
- ADR-0018 A3 (atomic persistence): resolved — `_persist_garmin_data()` uses transaction

The audit also identified **five new issues** not previously tracked in `TECHNICAL_DEBT.md`.
An additional **sixth issue** (startup hydration confidence gap) was surfaced by supplementary
analyst review and not caught by the automated audit. These six issues form the basis of the
Phase 7.7 hardening sprint.

---

## Findings Summary

| ID | Priority | Finding | Tracked as |
|---|---|---|---|
| C1 | P0 | Garmin activity duplicate persistence — no idempotency key | T1-14 |
| C2 | P1 | Weather + Telegram shutdown: no post-join alive escalation | T3-08 |
| C1-ext | P0 | 6 governance/science DB write methods: cursor outside lock | T1-13 |
| M1 | P1 | Runtime `print()` in main/orchestration/integrations bypasses log pipeline | T2-09 (remaining) |
| M3 | P1 | Telegram fallback exposes message content in stdout (privacy risk) | T2-11 |
| S1 | P1 | Startup engine hydration has no data-confidence gate | T2-10 |

---

## Architectural Decisions

### Decision 1 — Garmin Activity Idempotency Contract

**Context:** `training_log` has no stable external identity column for Garmin-sourced
activities. A re-sync over an overlapping date window or a retry after timeout inserts
duplicate rows, inflating `training_load` and corrupting CTL/ATL/TSB baselines.

**Decision:**
- **Identity key:** `garmin_activity_id TEXT` nullable column on `training_log`.
  Nullable because manually entered sessions have no Garmin ID.
- **Uniqueness enforcement:** Partial unique index:
  `CREATE UNIQUE INDEX IF NOT EXISTS idx_training_log_garmin_id ON training_log(garmin_activity_id) WHERE garmin_activity_id IS NOT NULL`
  This enforces uniqueness for Garmin-sourced rows while allowing unlimited manual entries.
- **Upsert strategy:** `INSERT OR IGNORE`. If an activity with the same `garmin_activity_id`
  already exists, the insert is silently skipped. **Do not upsert/overwrite** — historical
  records are immutable. A deliberate correction requires a manual operator override via the
  `log_override()` path, not an automatic field update.
- **Rationale for INSERT OR IGNORE over UPSERT:** The primary failure mode is data inflation
  (duplicate rows), not stale fields. The system's science baselines (CTL/ATL/TSB) depend on
  stable row counts, not field freshness. Overwriting historical distance or HR could
  retroactively corrupt load calculations and threshold calibrations. INSERT OR IGNORE is the
  safer choice.
- **Migration:** Add column + index via `_run_migrations()` using the existing
  `ALTER TABLE IF NOT EXISTS` pattern. No data loss on migration.

**Consequences:**
- `save_session()` gains an optional `garmin_activity_id: str | None = None` parameter.
- `_persist_garmin_data()` passes `garmin_activity_id=act.get('activity_id')` (or the
  equivalent field from the Garmin SDK response) to `save_session()`.
- Replay tests (re-sync same date window twice) must show identical `training_log` row counts.

---

### Decision 2 — Uniform Worker Shutdown Escalation Contract

**Context:** T3-06 established the shutdown escalation pattern for `garmin_sync.py`.
T1-11 (ADR-0018-A2) applied it to `DailyCoach._routine_thread`. The `weather_api.py`
and `telegram_bot.py` stop paths lack post-join alive checks and structured escalation
events — creating an inconsistent lifecycle contract across workers.

**Decision:**
- **Contract standard** (applies to all 4 background workers, uniformly):
  1. Signal stop: `_stop_event.set()` (or equivalent)
  2. Signal library stop (Telegram only): `bot.stop_polling()`
  3. Join with timeout: `thread.join(timeout=N)` where N ∈ {5, 30} depending on worker
  4. Post-join alive check: `if thread.is_alive():`
  5. Structured escalation: emit `worker_shutdown_timeout` event at ERROR level with
     `(worker_name, timeout_seconds, still_alive=True)`
  6. Continue shutdown — do not block or hard-fail (daemon threads; OS will clean up)
- **Do not forcibly kill threads.** Python provides no safe mechanism. Document
  escalation-only approach.
- **Worker names** (canonical, for log correlation):
  - `"GarminSync"` (T3-06, resolved)
  - `"DailyCoachRoutine"` (T1-11, resolved)
  - `"WeatherUpdater"` (T3-08, open)
  - `"TelegramScheduler"` and `"TelegramPoller"` (T3-08, open)

**Consequences:**
- `weather_api.stop_background_updates()`: add alive check + `_weather_event(...)` after join.
- `telegram_bot.stop_bot()`: add alive check + `_telegram_event(...)` after each join
  (both `_sched_thread` and `_poll_thread`).
- Tests must simulate hung thread (mock `join` to not clear alive flag) and assert event
  emission.

---

### Decision 3 — Observability Policy: `print()` Boundary

**Context:** Audit V3 identified operational `print()` calls in `titan/main.py`,
`titan/orchestration/daily_coach.py`, and `titan/integrations/telegram_bot.py` that bypass
the structured log pipeline. These events are invisible to log aggregators and make incident
RCA harder.

**Decision:**
- **`print()` is permitted only in `titan/ui/`** — interactive terminal UI paths where
  user-facing text must reach stdout directly (menus, prompts, formatted output).
- **All other `print()` calls in the package must be replaced** with the subsystem's
  structured event emitter (`log.*`, `_coach_event`, `_telegram_event`, `_weather_event`,
  `_garmin_event`).
- **Acceptance criterion:** `rg -n "print\(" titan/` excluding `titan/ui/` returns zero matches.
- **Enforcement:** Add `test_<module>_has_no_print_calls` assertion for each completed module.

**Boundary clarification:**
- `titan/main.py` startup banner (`print("\n🔒 TITAN OS v5.8.0")`) → replace with `log.info`.
- `titan/main.py` shutdown confirmation → replace with `log.info` or structured event.
- `titan/orchestration/daily_coach.py` hydration warnings → replace with `_coach_event`.
- `titan/integrations/telegram_bot.py` fallback and error prints → replace with
  `_telegram_event`. Content redaction (T2-11) is part of this replacement.

---

### Decision 4 — Telegram Fallback: Content Redaction

**Context:** Audit V3 M3. When the Telegram bot is unavailable, the fallback logs up to 200
characters of coaching message content to stdout. Coaching messages contain HRV values, TSB
scores, session prescriptions, and fatigue ratings — personal health data.

**Decision:**
- **Zero coaching or health content in any log path.** The fallback must emit metadata only.
- Replace: `print(f"📱 [Telegram] {text[:200]}")`
- With: `_telegram_event("fallback_send", level="warning", subsystem="send_message",
  message_length=len(text), bot_available=False)`
- The structured event must not contain any field derived from the message body.
- **Rationale:** TITAN OS handles personal biometric data. Even in development/testing
  environments, content must not leak into console logs. The length metadata is sufficient
  for debugging without content exposure.

---

### Decision 5 — Startup Hydration Confidence Gate

**Context:** Analyst supplementary review identified that `_hydrate_engines_from_db()`
catches broad exceptions silently and provides no downstream signal about hydration quality.
After a cold start or corruption, the governance engine operates on empty baselines without
knowing it — a semantic safety gap in a longevity-first system.

**Decision:**
- **Add `_startup_hydration_confidence: dict[str, bool]`** to `DailyCoach`. Populated during
  `_hydrate_engines_from_db()`. Keys: `"hrv"`, `"weight"`, `"load"`, `"hrr"`, `"cs"`.
  Value `True` = engine loaded ≥1 data point; `False` = empty DB or exception.
- **Emit `startup_hydration_report`** structured event at startup listing confidence dict.
- **Conservative-mode trigger:** if fewer than 3/5 engines hydrated (`True` count < 3),
  emit `startup_low_confidence` event at WARNING level and set `data_confidence_low=True`
  in the `GovernanceContext` for the first morning routine.
- **Conservative-mode effect:** When `GovernanceContext.data_confidence_low is True`,
  `GovernanceEngine` applies an intensity ceiling: cap at EASY (no VO2max, no tempo).
  This is **not a hard stop** (which would prevent training entirely). It is a
  precautionary downgrade — appropriate when the system cannot verify the athlete's
  recent load history.
- **Conservative mode duration:** Only the first `run_morning_routine()` call after startup
  uses the confidence flag. Subsequent calls use live engine data.
- **Threshold choice (3/5):** Rationale — HRV (gate H2) and training load (CTL/ATL/TSB,
  gates H4/H5) are the two most safety-critical inputs. If both are missing (`"hrv"` and
  `"load"` are False), the system should always trigger conservative mode regardless of
  other engines. A 3/5 threshold with load + HRV as required anchors achieves this.

**Implementation note:** `GovernanceContext` must be extended with a
`data_confidence_low: bool = False` field. The governance engine's intensity ceiling logic
should be separated from gate logic — it is an advisory constraint, not a lock code.

---

## Engineer Directives (Phase 7.7 execution order)

These are binding implementation instructions. Apply CLAUDE.md Rule E5 (binary done/not done)
and Rule E2 (one subsystem at a time) throughout.

### Tier 1 — Execute in order; do not start T1-14 until T1-13 passes acceptance gate

**T1-13 (first):**
1. Identify all 6 remaining methods: `update_glycogen_debt`, `log_cs_performance`,
   `log_override`, `save_governance_decision`, `update_governance_outcome`,
   `annotate_governance_outcome`.
2. For each: move `cursor = self.conn.cursor()` inside `with self._lock:`, immediately after
   `self._ensure_open_locked()`.
3. Run: `ruff check titan/core/database.py` → must be zero findings.
4. Run: `python -m pytest -q` → must be 100% green.
5. Add concurrent-close tests for each method (mirror T1-10 test matrix in ADR-0018 §A1).
6. Binary gate: both checks pass → T1-13 DONE. Any failure → stop, fix root cause, restart.

**T1-14 (after T1-13 gate passes):**
1. Add `garmin_activity_id TEXT` migration to `_run_migrations()` in `database.py`.
2. Add partial unique index (see Decision 1 above).
3. Update `save_session()` signature and `INSERT OR IGNORE` semantics.
4. Update `_persist_garmin_data()` to pass activity ID from Garmin SDK response.
5. Add idempotency tests (duplicate replay, null ID, load stability under replay).
6. Binary gate: `ruff check titan/core/database.py titan/orchestration/daily_coach.py` zero
   findings + `pytest -q` 100% green + idempotency test passes → T1-14 DONE.

### Tier 2 — Execute in any order after T1-13 passes (not blocked on T1-14)

**T2-09 completion (one module at a time):**
- Sequence: `titan/main.py` → `titan/orchestration/daily_coach.py` → `titan/integrations/telegram_bot.py`
- For each: find all `print(` calls in non-UI paths → replace with structured emitter → add
  `test_<module>_has_no_print_calls` → gate: `ruff check <module>` zero + `pytest -q` 100%
  green + `rg -n "print\(" <module>` zero.
- Note: T2-11 (content redaction) must be done as part of the `telegram_bot.py` pass.

**T2-10 (startup confidence gate):**
- Extend `_hydrate_engines_from_db()` to return `dict[str, bool]`.
- Add `_startup_hydration_confidence` field to `DailyCoach`.
- Emit `startup_hydration_report` event.
- Extend `GovernanceContext` with `data_confidence_low: bool = False`.
- Add conservative-mode ceiling in `GovernanceEngine`.
- Tests: cold start, partial hydration, full hydration, conservative-mode ceiling.
- Gate: `ruff check titan/orchestration/daily_coach.py titan/science/governance_engine.py`
  zero + `pytest -q` 100% green.

**T2-11 (Telegram content redaction):**
- Done as part of T2-09 telegram_bot.py pass (same module, same gate).
- Ensure: zero content fields in fallback event payload.

### Tier 3 — Execute after T1-13 passes

**T3-08 (weather + telegram shutdown escalation):**
- `weather_api.stop_background_updates()`: add alive check + `_weather_event(...)`.
- `telegram_bot.stop_bot()`: add alive check + `_telegram_event(...)` for each thread.
- Tests: simulate hung thread → assert `worker_shutdown_timeout` event emitted.
- Gate: `ruff check titan/integrations/weather_api.py titan/integrations/telegram_bot.py`
  zero + `pytest -q` 100% green.

### Phase 7.7 close gate (all must pass simultaneously)

```bash
python -m pytest -q -W error::pytest.PytestWarning   # ≥1435 tests, 100% green
ruff check .                                          # zero findings
python -m pytest --cov=titan --cov-fail-under=92     # ≥92% coverage
rg -n "print\(" titan/ --glob "!titan/ui/*"          # zero matches
```

Plus manual invariant checks:
- Garmin replay test passes (T1-14)
- Cold-start confidence event emitted (T2-10)
- Telegram fallback zero content (T2-11)
- Shutdown hung-thread escalation events emitted for Weather and Telegram (T3-08)

---

## Deferred — Not in Phase 7.7 Scope

These items were noted in the audit but are **not** Phase 7.7 work. Add to `TECHNICAL_DEBT.md`
under the appropriate tier if not already tracked.

**M4 — Monolithic composition root (main.py):**
Already discussed in ADR-0017. Accepted as-is for current scale. Refactor (staged bootstrap
phases, typed lifecycle contracts) is a Phase 9 concern or earlier if Phase 8 complexity
demands it. Do not start without a new ADR.

**ADR-0018 Phase B — Decision Pipeline / Effect Runner split:**
Architecture design only at this stage. Implementation deferred beyond Phase 8.

---

## Status

This ADR is accepted. Phase 7.7 execution begins immediately. Phase 8 feature work is gated
on T1-13 and T1-14 completion at minimum.
