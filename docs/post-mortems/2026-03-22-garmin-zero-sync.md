# Post-Mortem: Garmin Zero-Sync — Silent Empty-Result on Every Startup

**Date of Incident:** 2026-03-22
**Date of Post-Mortem:** 2026-03-29
**Severity:** P1 — user-facing data loss (no training data ingested; coaching pipeline ran on stale data)
**Status:** Final
**Author:** Architect

---

## Summary

On 2026-03-22, every TITAN OS startup completed Garmin sync without error but returned
zero activities, zero sleep sessions, zero HRV readings, and zero weight entries. The
coaching pipeline continued to run, issuing recommendations based on stale historical
data. No alert was raised; the failure was silent. Root cause was a stale Garmin OAuth
token combined with a 429 rate-limit response on the token-verification ping, which
caused the sync client to treat the expired token as valid and subsequently fail
silently on all data-fetch API calls.

---

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| ~06:50 | TITAN OS startup; `GarminSync.connect()` called |
| ~06:50 | Token file (`.garth_token`) present; verification ping returns HTTP 429 |
| ~06:50 | Code path: `connect_token_assumed_valid` — `is_connected = True` with expired token |
| ~06:51 | `sync_activities()`, `sync_sleep()`, `sync_hrv()`, `sync_weight()` all called |
| ~06:51 | Each method: API call with expired token → exception caught → returns `[]` |
| ~06:51 | `sync_all()` returns `GarminSyncResult` with 0/0/0/0 — logged at INFO |
| ~06:52 | `DailyCoach` morning briefing runs on stale DB data; no governance gate fired |
| ~10:30 | Athlete notices morning plan references a workout from 3 days prior |
| ~10:35 | Manual investigation begins; `docs/garmin_zero_sync_investigation.md` created |
| ~10:50 | Root cause identified: Path Z1 (stale token + 429 false-positive) |
| ~11:00 | Token file deleted manually; next startup performs full re-auth; sync restored |

---

## Root Cause

The Garmin sync client's token-verification flow (`titan/integrations/garmin_sync.py`,
lines 210–224) interprets an HTTP 429 (rate-limit) response on the verification ping as
evidence that the token is valid — because a 429 implies the server recognised the
request. When the token is expired or revoked, Garmin may still return a 429 before
evaluating the token (server-side rate limiting precedes auth checks in Garmin's API).
The code sets `is_connected = True` with the expired token. All subsequent data-fetch
calls (`get_activities_by_date`, `get_sleep_data`, etc.) receive an auth error, but
each sync method wraps its body in `except Exception: return []`, silently swallowing
the failure. The `sync_all()` assembles four empty lists into a `GarminSyncResult` with
`status="success"` and logs at INFO level. No structured error event is emitted; no
Telegram alert is sent.

**Why it went undetected:** The governance pipeline does not distinguish between "no
data available" and "data fetch failed". A sync returning 0 activities on a rest day is
legitimate; there was no zero-result anomaly detector.

---

## Contributing Factors

- Broad `except Exception: return []` in all four sync methods with no structured error emission.
- 429 rate-limit response incorrectly used as a token-validity proxy (lines 212–224).
- `sync_all()` `status` field set to `"success"` even when all sub-sync methods returned empty results.
- No Telegram alert configured for consecutive zero-result syncs.
- `DailyCoach` does not check data freshness before running the governance pipeline (no staleness gate at the coach entry point).

---

## Impact

- **Users affected:** 1 (single-athlete deployment)
- **Data integrity:** No data corruption; Garmin data was not ingested for the affected startup window. Historical data was intact.
- **Safety gates:** Governance pipeline ran on stale data. No hard-stop gate fired (metrics were within historical bounds, just stale). Coaching recommendations were suboptimal but not unsafe.
- **Duration:** ~3.5 hours from first silent failure to athlete detection.

---

## Detection

Detected by the athlete noticing the morning plan referenced a prior workout.
There was no automated alert. Detection lag: ~3.5 hours.

---

## Resolution

1. Deleted the stale `.garth_token` file manually.
2. Restarted TITAN OS; full Garmin re-authentication performed.
3. Sync restored; all four data streams returned current data.
4. `DailyCoach` re-run manually for the correct data set.

No code change was deployed at the time of resolution (manual workaround only).
Permanent fixes tracked in ADR-0050 and TECHNICAL_DEBT.md (T5-12 Pass 2, obligations O1–O7).

---

## What Went Well

- The token file could be deleted and re-auth triggered with a simple restart — no data migration required.
- The investigation notes (`docs/garmin_zero_sync_investigation.md`) were thorough and correctly identified all four silent-zero paths within 15 minutes.
- Historical data was fully intact; no athlete profile corruption.

---

## What Went Wrong

- The 429 rate-limit path was designed as a "best-effort availability" measure but inadvertently created a silent-failure path.
- Broad exception handling across all four sync methods eliminated all error signal.
- No anomaly detection for consecutive zero-result syncs.
- `DailyCoach` has no data-freshness precondition before running the governance pipeline.

---

## Action Items

| Item | Owner | Priority | Due | Status |
|------|-------|----------|-----|--------|
| Emit `garmin_api_degraded` CRITICAL structured event on zero-result sync | Engineering | P0 | Phase 8 | Open — ADR-0050 O1 |
| Remove 429-as-valid-proxy path; treat 429 as indeterminate, force re-auth | Engineering | P0 | Phase 8 | Open — ADR-0050 O2 |
| Replace `except Exception: return []` with specific error emission in all 4 sync methods | Engineering | P1 | Phase 8 | Open — ADR-0050 O3 |
| Add consecutive-zero-result anomaly detector with Telegram alert | Engineering | P1 | Phase 8 | Open — ADR-0050 O4 |
| Add data-freshness gate to `DailyCoach` startup (staleness check before governance pipeline) | Engineering | P1 | Phase 8 | Open — T1-20 |
| Add runbook: `docs/runbooks/garmin-sync-failure.md` | Engineering | P2 | Phase 8 | Closed — this commit |

---

## Lessons Learned

Silent empty-result failures are more dangerous than loud crashes in a safety-critical
coaching context, because the system continues to operate and the athlete has no signal
to investigate. Exception handlers that return empty collections without emitting a
structured error event are a systemic anti-pattern in TITAN OS integrations; ADR-0050
introduces the `garmin_api_degraded` event contract to close this class of failure.

---

## Related

- ADR-0050 — Garmin API Fragility Mitigation (obligations O1–O7)
- ADR-0030 — External Data Source Resilience
- `docs/runbooks/garmin-sync-failure.md`
- `docs/garmin_zero_sync_investigation.md` (raw investigation notes)
- TECHNICAL_DEBT.md — T5-12 Pass 2
