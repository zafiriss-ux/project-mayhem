# Garmin Zero-Sync Investigation

**Symptom:** Every startup, Garmin sync completes but returns 0 activities / 0 sleep / 0 HRV / 0 weight. No crash — runs silently with empty results.

**Date:** 2026-03-22

---

## Batch 1 Findings: `titan/integrations/garmin_sync.py`

### Code Path Analysis

**Connection flow (`connect()`, lines 185–292):**
1. If credentials missing → logs event, returns `False`
2. If `.garth_token` file exists → loads token, does a verification ping via `connectapi("userprofile-service/socialProfile")`
3. **CRITICAL PATH (lines 210–224):** If the verification ping gets a 429 rate-limit, the code *assumes the token is valid* (`connect_token_assumed_valid`) and sets `is_connected = True`. If the token is actually expired/invalid but classified as rate-limited, the client object is set but may fail silently on subsequent API calls.
4. If token load fails (non-429) → deletes token, falls through to full login
5. Full login with retry on 429 (up to 3 retries with 60/120/240s backoff)
6. On any exception in outer try → `is_connected = False`, returns `False`

**Key observation on `_ensure_connected()` (line 294–297):**
- Only checks `self.is_connected` and `self.client is None`
- If connect() was previously called and set `is_connected = True` (e.g., via the 429-assumed-valid path), subsequent calls skip re-auth entirely

**Individual sync methods — all follow the same pattern:**
- `sync_activities()` (319–377): On any exception in the outer try, catches it, logs, returns whatever `activities` list was built (could be empty `[]`). **Does NOT re-raise.**
- `sync_weight()` (382–412): Same pattern — catches outer exception, returns `entries` (could be `[]`).
- `sync_sleep()` (417–473): Same — catches per-day exceptions AND outer exception. Returns `sessions` (could be `[]`).
- `sync_hrv()` (478–541): Same — catches per-day exceptions AND outer exception. Returns `hrv_data` (could be `[]`).

### Identified Silent-Zero Paths

**Path Z1: Stale token + 429 on verification ping**
- Token file exists but is expired
- Verification ping returns 429 → code assumes token valid (line 212–224)
- `is_connected = True`, `self.client` is set with expired token
- All subsequent API calls (`get_activities_by_date`, `get_sleep_data`, etc.) fail
- Each sync method catches the exception silently and returns `[]`
- Net result: 0/0/0/0 with no visible error to user

**Path Z2: Valid connection, but API calls fail silently**
- Connection succeeds (token or fresh login)
- Individual API calls fail (network issue, Garmin server error, etc.)
- Each method catches the exception → returns empty list
- `sync_all()` assembles 4 empty lists into a GarminSyncResult
- Net result: 0/0/0/0 — logged at INFO level only

**Path Z3: Timeout path (lines 566–622)**
- `sync_all()` wraps `_sync_operation()` in a 20-second timeout
- If timeout fires → returns empty GarminSyncResult with `status="timeout_cancelled"`
- Net result: 0/0/0/0

**Path Z4: `_ensure_connected()` returns False**
- If connection fails, every sync method returns `[]` immediately (lines 320–321, etc.)
- But this path at least logs a connection failure event

### Most Likely Root Cause Candidate (Batch 1)

**Path Z1 is the strongest candidate.** The 429-rate-limit-on-verification-ping path (lines 212–224) creates a client with a potentially expired token and marks `is_connected = True`. All subsequent data-fetching API calls then fail silently because each sync method has a broad `except Exception` that returns empty lists without propagating the error.

The comment on line 201–203 even acknowledges this exact problem:
> "garth.loads() only deserialises from disk — it does NOT check the server. A single lightweight call here ensures we catch expired tokens before any sync attempt, preventing the silent 0/0/0 failure."

But the 429 handling on line 212 **undermines this exact safeguard** by skipping the verification when rate-limited.

---

## Batch 2 Findings: `titan/orchestration/daily_coach.py`

### How DailyCoach Calls GarminSync

**Line 370:** `garmin_data: GarminSyncResult = _run_step(1, "sync_garmin", self.garmin.sync_all)`
- Calls `sync_all()` which returns a `GarminSyncResult` dict
- `_run_step()` wraps the call and logs success/failure, but does NOT validate the content of the result

### Critical: Success Determination is Flawed (lines 404–412)

```python
sync_status = str(garmin_data.get("status", "ok"))
sync_ok = sync_status != "timeout_cancelled"
sync_error_class = "GARMIN_TIMEOUT" if not sync_ok else None
self.db.record_sync_outcome(
    source="garmin",
    attempted_at=datetime.now(tz=UTC),
    success=sync_ok,
    error_class=sync_error_class,
)
```

**BUG:** `sync_ok` only checks if the status is `"timeout_cancelled"`. If all four sync methods return empty lists (0/0/0/0) but no timeout occurred, `sync_ok = True` and the system records a **successful** sync.

This means:
1. The staleness check (lines 414–428) will **never trigger** because `record_sync_outcome(success=True)` keeps updating `last_success_ts`
2. The `garmin_data_stale` flag stays `False`
3. The system proceeds with empty data as if it's valid
4. No alert is sent to Telegram about the zero data

### No Guard Against Empty-But-"Successful" Sync

There is NO check anywhere in the morning routine that validates:
- `len(garmin_data.get('activities', [])) > 0`
- `len(garmin_data.get('hrv', [])) > 0`
- etc.

The system trusts that if `sync_all()` returned without timeout, the data is valid.

### Amplifying Factor: Persistence Silently Succeeds on Empty Data

**Line 1155:** `activities = garmin_data.get('activities', [])` — if empty, the persistence step just writes nothing to the DB and "succeeds."

---

## Batch 3 Findings: Token/Credential Files

### No Separate Auth Module

There is no `garmin_auth.py`. All authentication logic lives in `garmin_sync.py:connect()` (lines 185–292).

### Token Persistence

- Token file: `~Documents/TITAN/.garth_token` (line 38: `_GARTH_TOKEN_FILENAME = ".garth_token"`)
- Token is a serialized garth session (via `client.garth.dumps()` / `client.garth.loads()`)
- `garminconnect==0.2.13` is the pinned version

### Stale Token → Silent Failure Chain

The token lifecycle creates a persistent zero-sync loop:

1. **First successful login:** Token saved to `.garth_token` via `client.garth.dumps()` (line 266)
2. **Later startup:** Token loaded via `client.garth.loads(token_data)` (line 199)
3. **Verification ping** (`connectapi("userprofile-service/socialProfile")`, line 204): This is the ONLY check that the token is still valid server-side
4. **If verification ping gets 429:** Token assumed valid (lines 212–224), even if expired
5. **All data API calls fail** because server rejects the expired token
6. **Each sync method catches the exception** and returns `[]`
7. **DailyCoach records `success=True`** because there was no timeout (line 405)
8. **Token file is NOT deleted** (only deleted on non-429 token load failure, line 232–233)
9. **Next startup:** Same stale token is loaded → same 429 on verification → same 0/0/0/0

**This creates a self-reinforcing loop:** The stale token is never deleted because the 429 path preserves it, and the sync is never recorded as failed because DailyCoach only checks for timeout status.

### `_classify_failure` Can Misclassify Auth Errors as Rate Limits

The `_classify_failure()` function (lines 83–109) checks for "429" in the combined error string. If Garmin returns a 429 that is actually an auth-related rate limit (e.g., too many failed auth attempts), it will be classified as `GARMIN_RATE_LIMIT` rather than `GARMIN_AUTH_FAIL`, preventing session invalidation.

---

## Batch 4 Findings: Tests and Evidence

### Existing Test Confirms the 429-Assumed-Valid Path

`tests/titan/integrations/test_garmin_sync.py:477` — `test_connect_token_ping_rate_limited_assumes_valid_and_returns_true`:
- This test **intentionally verifies** the 429 bypass behavior
- It asserts `result is True`, `is_connected is True`, `login_called["n"] == 0`
- It asserts the token file is NOT deleted
- This test documents the design decision but does NOT test what happens when subsequent API calls fail with that assumed-valid token

### No Test for the Complete 0/0/0/0 Scenario

There is no test that:
1. Sets up a stale token
2. Has the verification ping return 429
3. Has subsequent data API calls fail (because token is actually expired)
4. Verifies that the system reports this as a failure (it currently doesn't)

### No "Already Synced Today" Skip Logic

There is no deduplication or skip-if-already-synced logic anywhere in the codebase. Every call to `sync_all()` always runs all four sync methods.

### `sync_ok` Determination Has No Test Coverage for Empty-Data Path

No test verifies that DailyCoach correctly handles the case where `sync_all()` returns a valid GarminSyncResult with all-empty lists and no `"timeout_cancelled"` status.

---

## ROOT CAUSE ANALYSIS

**Symptom:** 0 activities / 0 sleep / 0 HRV / 0 weight on every startup. Sync completes silently.

### Root Cause: Two-Bug Chain

**Bug 1 (Primary) — `garmin_sync.py:212–224`: Stale token assumed valid on 429**

When the Garmin API rate-limits the token verification ping (429), the code assumes the token is still valid and sets `is_connected = True`. If the token is actually expired, all subsequent data-fetching API calls fail. Each sync method (`sync_activities`, `sync_sleep`, `sync_hrv`, `sync_weight`) catches the exception in a broad `except Exception` and returns an empty list `[]` — the failure is never propagated.

The token file is preserved (not deleted), so the next startup loads the same stale token and hits the same 429 → assumed-valid → silent-failure loop.

**Bug 2 (Amplifier) — `daily_coach.py:404–412`: Success determined by absence of timeout, not by data presence**

```python
sync_ok = sync_status != "timeout_cancelled"
```

DailyCoach only considers a sync "failed" if it timed out. A sync that returns 0/0/0/0 with no timeout is recorded as `success=True`. This prevents the staleness detection mechanism (lines 414–428) from ever triggering, because `last_success_ts` is continuously updated. No alert is sent to Telegram.

### Why It Returns Empty Silently

1. `garmin_sync.py` sync methods use `except Exception` as a catch-all (lines 371, 406, 466, 528) — exceptions from expired-token API calls are logged but never raised
2. `sync_all()` assembles the four empty lists into a valid `GarminSyncResult` with no error status
3. `daily_coach.py` checks only `status != "timeout_cancelled"` — empty data is not a failure condition
4. `record_sync_outcome(success=True)` resets the staleness timer
5. The stale `.garth_token` is never deleted because the 429 path explicitly preserves it

### Fix Required

**Fix 1 — `garmin_sync.py:212–224`:** When the verification ping gets a 429, do NOT blindly assume the token is valid. Instead:
- Attempt one data-fetching API call as a secondary validation
- If that also fails with an auth error, invalidate the session and delete the token
- Alternatively: always attempt a fresh login after a 429 on the verification ping (with appropriate backoff)

**Fix 2 — `daily_coach.py:404–412`:** Add an empty-data check:
```python
total_records = (
    len(garmin_data.get('activities', []))
    + len(garmin_data.get('sleep', []))
    + len(garmin_data.get('hrv', []))
    + len(garmin_data.get('weight', []))
)
sync_ok = sync_status != "timeout_cancelled" and total_records > 0
```
When `total_records == 0`, record the sync as failed so that the staleness mechanism triggers and alerts the user.

**Fix 3 — `garmin_sync.py` sync methods:** On auth-classified exceptions, call `_invalidate_session()` AND propagate a distinguishable error (or set a status field in the result) so the caller knows the sync was not just "empty" but "broken."

### Severity

**HIGH** — This is a safety-critical bug. The governance engine depends on fresh HRV, sleep, and activity data to enforce hard-stop gates (H2, H3, H4, H5). When all data returns 0, the governance system operates on stale or default values, potentially allowing unsafe training recommendations.
