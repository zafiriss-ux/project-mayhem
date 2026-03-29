# Runbook — Garmin Sync Failure

**Version:** 1.0
**Date:** 2026-03-29
**Owner:** Engineering
**Trigger:** `garmin_api_degraded` CRITICAL event; two consecutive zero-result syncs; morning briefing with stale data warning

---

## Symptoms

- Telegram briefing contains stale workout data or explicitly warns "Garmin data unavailable"
- `garmin_api_degraded` CRITICAL structured event in application log
- `GarminSyncResult` shows `activities=0, sleep=0, hrv=0, weight=0` for two or more consecutive syncs
- Log line: `connect_token_assumed_valid` without a subsequent `sync_complete` event with non-zero counts

---

## Severity Assessment

| Condition | Severity | Action |
|-----------|----------|--------|
| Single zero-result sync, next sync succeeds | Low | Monitor; no action required |
| Two consecutive zero-result syncs | Medium | Follow this runbook |
| Zero-result syncs for > 12 hours | High | Follow this runbook + check Garmin API status |
| Governance pipeline running on data > 48h stale | P1 | Suspend coaching recommendations until sync restored |

---

## Diagnostic Steps

### Step 1 — Check the application log

```bash
# Find the most recent sync result
grep "garmin_sync\|garmin_api_degraded\|connect_token" ~/Documents/TITAN/titan.log | tail -30
```

Look for:
- `connect_token_assumed_valid` — stale token + 429 path (most common, see Path Z1)
- `sync_timeout` — network timeout
- `connect_failed` — authentication failure
- `garmin_api_degraded` — confirmed degradation event

### Step 2 — Check Garmin Connect API status

Visit https://connect.garmin.com — if the site is down or returning errors, the issue
is upstream. Wait and retry in 30 minutes.

### Step 3 — Identify the failure path

**Path Z1 (most common): Stale token + 429 rate-limit false positive**

Indicators:
- `connect_token_assumed_valid` in log
- `.garth_token` file exists and is > 7 days old

Fix:
```bash
rm ~/Documents/TITAN/.garth_token
# Restart TITAN OS to trigger full re-authentication
python main.py
```

**Path Z2: Valid connection, API call failures**

Indicators:
- `connect_success` in log but `sync_activities_failed` or similar
- HTTP 5xx errors in log

Fix: Wait for Garmin API to recover. If persistent (> 2 hours), check `requirements.txt`
to confirm `garminconnect` is pinned to the validated version (ADR-0050).

**Path Z3: Timeout**

Indicators:
- `sync_status=timeout_cancelled` in log

Fix: Check network connectivity. Increase timeout if on slow connection (config override).

**Path Z4: Authentication failure**

Indicators:
- `connect_failed` in log
- May indicate password change or Garmin account lockout

Fix: Verify credentials in `~/Documents/TITAN/.env`. Update if changed.

### Step 4 — Verify recovery

After applying the fix, restart TITAN OS and confirm:

```bash
# Wait for the next sync cycle (up to 6 hours) or trigger manually via Telegram /sync command
# Check log for:
grep "sync_complete" ~/Documents/TITAN/titan.log | tail -5
```

A successful sync logs `sync_complete` with non-zero counts for at least activities or HRV.

---

## Escalation

If sync is not restored after 24 hours and Garmin Connect is accessible:

1. Check for `garminconnect` library version mismatch (ADR-0050 pinning policy).
2. File an issue in the project repository with the log snippet containing the failure event.
3. Consider manually importing recent Garmin data via CSV export as a temporary measure.

---

## Post-Recovery Checklist

- [ ] Sync restored — `sync_complete` event with non-zero data counts
- [ ] Morning briefing delivers current data on next scheduled run
- [ ] No stale-data warning in Telegram message
- [ ] If token was deleted: new `.garth_token` created automatically on re-auth
- [ ] Log the incident if downtime exceeded 6 hours

---

## Related

- `docs/post-mortems/2026-03-22-garmin-zero-sync.md` (reference incident)
- ADR-0050 — Garmin API Fragility Mitigation
- ADR-0030 — External Data Source Resilience
- `docs/SLO.md` — SLO-01 (Garmin Sync Freshness)
- `titan/integrations/garmin_sync.py`
