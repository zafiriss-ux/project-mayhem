# ADR-0020 — Persistence Failure Behavioral Policy: DailyCoach Morning Routine

**Date:** 2026-03-05
**Status:** Accepted
**Deciders:** Architect + Engineering Lead
**Source:** Engineering Audit V4 (2026-03-05) — Analyst review of C2 fail-open gap
**Phase:** 7.8 — Post-Phase-7.7 Hardening
**Supplements:** ADR-0019 (Phase 7.7 decisions), ADR-0018 (kernel boundary)

---

## Context

ADR-0018-A3 (T1-12) established that `_persist_garmin_data()` wraps all DB writes in a
single SQLite transaction — either all writes succeed or none do. This was implemented and
verified in PR #261.

However, a behavioral gap remains: when the transaction rolls back (i.e., `with
self.db.transaction():` raises), the outer `except Exception` in `_persist_garmin_data()`
logs structured events and then **returns normally** with default values
`(today_rhr=0, today_sleep_score=75, today_sleep_hours=7.5)`. It does not re-raise.

Consequence chain:
1. `_run_step(2, "persist_garmin_data", ...)` sees a normal return → emits
   `step_event step_2 outcome="SUCCESS"` — this is **factually wrong**: persistence failed.
2. The morning routine continues without any signal to the governance engine.
3. `governance_context` has no `persistence_degraded` field → no conservative mode applied.
4. Athlete receives a full training prescription as if all data were persisted correctly.
5. No Telegram alert is sent → operator has no indication that today's session data
   was not written to the database.

**Secondary traceability risk:** If the process restarts tonight, the next startup
hydration will lack today's activities and daily metrics. CTL/ATL/TSB baselines will be
computed without today's load, producing a systematically underestimated training load.
For a longevity-first system this is an undercount of fatigue — the more dangerous error.

**Note on H3 gate safety:** `today_rhr` is extracted from `garmin_data` **before** the
transaction block (not from the DB write path). If Garmin returned sleep data, `today_rhr`
is correct even on persistence failure. If Garmin returned no sleep data, `today_rhr=0`
causes H3 to not fire — but this is not a regression introduced by the persistence failure;
it is pre-existing behavior when Garmin sleep sync yields no data. H3 is not acutely
bypassed by C2. The primary risk remains traceability and future baseline degradation.

---

## Options Considered

### Option A — Abort delivery on persistence failure

If persistence fails, cancel the morning routine entirely. No prescription delivered.

**Rejected.** Too conservative. `garmin_data` was successfully synced; in-memory engine
state is fresh. Aborting delivery penalizes the athlete for an infrastructure failure
unrelated to their training readiness. Also, a Garmin sync failure (T2-01 failure classes)
already has its own handling — persistence failure is a separate concern.

### Option B — Degraded conservative mode (SELECTED)

Persistence failure sets a `persistence_degraded` flag. The governance engine applies a
conservative intensity ceiling (same as `data_confidence_low`, ADR-0019 Decision 5): cap
at EASY. Delivery proceeds. Telegram alert sent. Athlete gets guidance; conservative
capping prevents overreach without abandoning the session.

**Rationale:**
- Consistent with the system's longevity-first philosophy: degrade gracefully, never silently.
- Follows the existing `data_confidence_low` pattern (ADR-0019 Decision 5) — same ceiling,
  same architectural slot in GovernanceContext.
- Today's delivery uses fresh in-memory data (correct) with an explicit conservative cap.
- Alert provides traceability for the athlete and operator.
- The problem is self-healing: next successful sync will persist the data; no permanent
  loss if the process runs continuously (data remains in memory for the current session).

### Option C — Continue as-is (accept trade-off)

Leave the current behavior. T1-12 handles atomicity; T2-02 provides event taxonomy.

**Rejected.** The structured events emitted by `_persist_garmin_data()` are not visible
at the step-level (step 2 shows SUCCESS). No Telegram alert reaches the athlete/operator.
No conservative mode is applied. This makes a persistence failure a silent operational
incident — inconsistent with the system's observability standards.

---

## Decision

**Adopt Option B: degraded conservative mode on persistence failure.**

### Implementation Contract

**1. Return signature extension:**

`_persist_garmin_data()` must signal the persistence outcome to its caller. Add a boolean
return field:

```python
# Current signature (implicit):
return today_rhr, today_sleep_score, today_sleep_hours

# New return:
return today_rhr, today_sleep_score, today_sleep_hours, persist_ok  # bool
```

`persist_ok = True` on clean commit; `persist_ok = False` on any exception in the
transaction block. The exception must still be caught internally (do not re-raise —
the routine continues in degraded mode, not aborted).

**2. Step 2 event correction:**

When `persist_ok=False`, the `_run_step` wrapper must be bypassed or the step must
manually emit `step_event step_2 outcome="FAILED" failure_class=PERSIST_ERROR`. The
current pattern of `_run_step` emitting SUCCESS when no exception escapes must be fixed
for step 2. Options:

- Preferred: have `_persist_garmin_data()` raise a sentinel exception
  `PersistenceFailure(today_rhr, today_sleep_score, today_sleep_hours)` so `_run_step`
  catches it and emits FAILED — then catch `PersistenceFailure` in the outer routine
  and extract the values + set `persistence_degraded=True`.
- Alternative: return a result object with `ok: bool` and handle outside `_run_step`.

The preferred approach keeps `_run_step`'s step-event emission correct.

**3. GovernanceContext extension:**

Add `persistence_degraded: bool = False` to `DailyCoachContextContract` and
`_build_governance_context()`. Follow the same extension pattern as `data_confidence_low`
(optional kwarg, added to payload after construction).

**4. GovernanceEngine ceiling:**

When `governance_context.get("persistence_degraded") is True`, apply the same
conservative intensity ceiling as `data_confidence_low`: cap session intensity at EASY
(no VO2max, no tempo). This is an **advisory constraint, not a lock code** — it does not
create a new governance lock. It operates at the intensity recommendation layer.

**5. Telegram alert:**

When `persist_ok=False`, emit a Telegram alert via the existing alert path:
> `⚠️ Persistence failure — today's session data was not written to the database.
> Training prescription is conservative (EASY). Data will be re-synced on next cycle.`

This alert fires regardless of whether Telegram is available (fallback is already handled
by T2-11 / `fallback_send` metadata event).

**6. Conservative mode scope:**

Applies to the current morning routine only. The flag is not persisted. If the next
sync and persist succeed, subsequent routines run normally.

---

## Consequences

- `_persist_garmin_data()` return type changes from `tuple[int, int, float]` to
  `tuple[int, int, float, bool]` (or sentinel exception approach).
- `run_morning_routine()` must unpack the fourth return value and propagate it.
- `_build_governance_context()` gains a `persistence_degraded: bool | None = None`
  parameter.
- `DailyCoachContextContract` gains `persistence_degraded: bool` field.
- `GovernanceEngine` gains a `persistence_degraded` check in the intensity path
  (alongside `data_confidence_low`).
- Tests: all existing step-2 tests must be updated if they assert `step_event SUCCESS`
  on persistence failure.

---

## Engineer Directives (T1-15 execution)

This ADR governs T1-15 in `TECHNICAL_DEBT.md`. Execution sequence:

1. In `_persist_garmin_data()`: implement sentinel exception `PersistenceFailure` (or
   return-tuple approach). Ensure the outer `try/except` sets `persist_ok=False` and
   the inner events fire correctly. Do not re-raise — the routine must continue.
2. In `run_morning_routine()`: catch `PersistenceFailure` (or check `persist_ok`),
   set `persistence_degraded=True`, send Telegram alert, continue.
3. In `_build_governance_context()`: add `persistence_degraded` parameter.
4. In `GovernanceEngine`: add ceiling check for `persistence_degraded`.
5. Update `DailyCoachContextContract`.
6. Write tests:
   - `test_persist_garmin_data_rollback_returns_persist_ok_false` — mock transaction
     to raise, assert `persist_ok=False` returned, assert `PERSIST_ERROR` step event.
   - `test_run_morning_routine_persistence_failure_sets_degraded_flag` — mock step 2
     to fail, assert `persistence_degraded=True` in governance context.
   - `test_governance_engine_persistence_degraded_caps_intensity_at_easy` — assert
     intensity ceiling when `persistence_degraded=True`.
   - `test_run_morning_routine_persistence_failure_sends_telegram_alert` — assert alert.
7. **Acceptance gate (binary):**
   ```bash
   ruff check titan/orchestration/daily_coach.py titan/science/governance_engine.py
   python -m pytest -q -W error::pytest.PytestWarning   # 100% green
   python -m pytest -q                                    # 100% green, count ≥ previous
   ```

---

## Status

Accepted. T1-15 is the engineering execution item. Phase 7.8 sprint begins after this
ADR is merged.
