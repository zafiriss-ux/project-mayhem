# ADR-0030 — External Data Source Resilience Policy

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V7 — Risk: External Dependency Fragility (Single Point of Failure)
**Phase:** 7.9 Hardening
**Supplements:** ADR-0020 (Persistence Failure Policy), T1-09 (weather degraded mode — resolved), T3-09 (Telegram fallback — resolved)

---

## Context

TITAN OS depends on two external data sources for 100% of its physiological and
environmental inputs:

| Source | Usage | Auth | Stability |
|---|---|---|---|
| Garmin Connect | HRV, RHR, activities, training load | Username/password (unofficial API) | Fragile — unofficial scraping library (`garminconnect`); auth may expire, API endpoints change without notice |
| Open-Meteo | Weather forecast, dew-point, heat index | None | Stable — free public API; no auth required; but network-dependent |

### Current Mitigations (Insufficient)

- Garmin sync runs on a 6-hour daemon thread. If the sync fails, the exception is logged
  but there is no operator alert and no explicit governance gate.
- Weather API caches forecasts for 1 hour. A cache miss falls back to synthetic data
  (`_create_synthetic_fallback()`), which was gated in T1-09 (resolved).
- Telegram notification fallback added in T3-09 (resolved) — the *delivery channel*
  has a fallback, but the *data sources* do not.

### The SPOF Failure Mode

**Garmin unavailability scenario:**
1. Garmin changes its auth mechanism (has happened historically with the `garminconnect`
   library).
2. The 6-hour sync daemon starts failing silently (T1-02 resolved HRV day skips, but
   a full session failure may still go undetected beyond one log entry).
3. DailyCoach continues running morning routines using the last-synced SQLite data.
4. After 24–48 hours, the governance engine evaluates a "current" HRV that is actually
   2–3 days old. If the athlete recovered (HRV improved), gates may fire unnecessarily.
   If the athlete degraded (HRV dropped), gates may silently fail to fire.

**The T2-10 data-confidence gate (resolved)** checks freshness at startup. However:
- It does not run continuously during operation.
- It does not distinguish between "data is old because Garmin was unavailable" and
  "data is old because the athlete hasn't synced yet today".
- It does not set a governance-visible `DATA_CONFIDENCE` flag that propagates into
  coaching decisions.

**Open-Meteo unavailability scenario:**
The synthetic fallback (T1-09) exists, but it uses Athens, GR defaults. If the athlete
trains in a different location, the fallback silently produces wrong dew-point and
heat-stress inputs to `OptimalTimeCalculator`.

### Why This Is Tier 1

Data staleness is a data integrity issue. A governance system that evaluates gates on
stale physiological data without knowing it is stale may reach the same conclusion as if
it had evaluated on fresh data — but for the wrong reasons, and with a different outcome
in the cases that matter most (acute illness onset, recovery from deep fatigue). This is
the definition of "silent failure that corrupts coaching decisions."

---

## Decision

**Introduce explicit data-source staleness gates into the DailyCoach pipeline and
require degraded-mode behavior (per ADR-0020) when staleness thresholds are breached.**

### Staleness Thresholds (canonical — stored in `thresholds.py`)

```python
GARMIN_DATA_MAX_AGE_HOURS   = 26   # >26h since last successful Garmin sync → stale
WEATHER_DATA_MAX_AGE_HOURS  = 3    # >3h since last successful weather fetch → stale
```

**Rationale for 26h Garmin threshold:**
A single missed sync (6h interval) is recoverable. Missing 4+ consecutive syncs (24h)
means the system has been operating on yesterday's data for an entire day. 26h gives
one grace interval beyond the daily cycle before triggering.

### DailyCoach Integration

The `DailyCoach` morning routine (step 2 — data hydration) must:

1. Read the `last_garmin_sync_ts` and `last_weather_fetch_ts` from the database
   (or a lightweight metadata table).
2. Compute age: `now - last_sync_ts`.
3. If Garmin data age > `GARMIN_DATA_MAX_AGE_HOURS`:
   - Set `garmin_data_stale = True` on the coaching context.
   - Emit structured event: `garmin_data_stale` with age and last-sync timestamp.
   - Engage ADR-0020 degraded conservative mode: do not recommend high-intensity
     sessions; cap recommendation at "easy maintenance only" until data freshens.
   - Send Telegram alert (using T3-09 fallback-aware gateway).
4. If weather data age > `WEATHER_DATA_MAX_AGE_HOURS`:
   - Flag `weather_data_stale = True`.
   - `OptimalTimeCalculator` falls back to pre-computed safe window (06:00–09:00
     local time) rather than dew-point-optimised window.
   - Emit structured event: `weather_data_stale`.

### Garmin Sync Resilience Enhancement

The Garmin sync daemon must:

1. On each sync attempt, record outcome (`success` / `failure + error_class`) to a
   `sync_metadata` table row (or update `last_garmin_sync_ts` in `daily_metrics`
   metadata).
2. On `LoginException` or `GarminConnectTooManyRequestsError`:
   - Back off exponentially (already partially handled).
   - Emit `garmin_auth_failure` structured event.
   - If 3+ consecutive auth failures → send Telegram operator alert.
3. Do NOT enter a retry loop that blocks the daemon thread. Use
   `threading.Event.wait()` backoff (pattern established in T3-06/T4-14).

### Open-Meteo Synthetic Fallback Enhancement

When the synthetic fallback activates:
- Use the athlete's configured `WEATHER_LOCATION` to determine season/hemisphere
  (not hardcoded Athens defaults).
- Emit `weather_synthetic_fallback_activated` structured event with location context.
- The governance context must carry `weather_confidence = SYNTHETIC` so downstream
  consumers can gate on it.

### What This Does NOT Change

- The existing `garminconnect` library version pinning (T3-dependency hygiene).
- The Garmin authentication mechanism (out of scope — library choice reviewed in T4-25).
- The 6-hour sync interval (operational decision, not changed here).
- The synthetic fallback logic in `weather.py` (only the location context is updated).

---

## Debt Items Created

- **T1-20** — Garmin connectivity failure has no staleness gate in DailyCoach
  (implementation of this ADR, Tier 1, independent)
- **T2-15** — Weather synthetic fallback uses hardcoded location — staleness context
  missing from governance (Tier 2, after T1-20)

---

## Alternatives Considered

**Alternative A — Add a second data source (Strava, Apple Health)**
Rejected at this phase. Multi-source data fusion is a Phase 8+ concern (ADR-0016).
Adding a second data source now introduces schema complexity and integration risk
before the Phase 8 entry gate (ADR-0022) has been satisfied.

**Alternative B — No change; rely on existing T2-10 data-confidence gate**
Rejected. T2-10 runs at startup only and does not produce a governance-visible flag
for ongoing staleness. The failure mode is silent and continuous.

**Alternative C — Replace `garminconnect` with an official Garmin API**
Garmin does not provide an official public API for consumer health data. Rejected as
out of scope.

---

## Consequences

- Positive: DailyCoach will operate in documented degraded mode rather than silently
  on stale data. Operators will receive alerts within one morning briefing cycle of
  a Garmin outage.
- Positive: Weather staleness will no longer produce hidden location-incorrect inputs
  to `OptimalTimeCalculator`.
- Negative (acceptable): Adding a staleness gate requires a `sync_metadata` mechanism.
  This is a lightweight addition (single-row update per sync attempt) with no schema
  migration complexity beyond a new column or table.
- Constraint: T1-20 must be completed before T2-15 (see above).

---

## Implementation Notes

**OBS-032 / T5-67 (pending):** `sync_sleep()`, `sync_hrv()`, `sync_activities()`, and
`sync_weight()` in `titan/integrations/garmin_sync.py` all emit a `_garmin_event("synced",
count=0)` success event unconditionally after the outer `try/except` block. When the sync
method aborts due to an exception, the emitted event is structurally identical to a normal
zero-activity day. SLO alerting cannot distinguish the two states. Fix registered as T5-67:
gate success event emission on absence of exception (boolean flag or move inside try block).
This finding is directly related to ADR-0030's goal of making degraded-mode operations
visible to operators.
