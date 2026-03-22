# OBS-025: Garmin Integration Deterministic Audit

**Date:** 2026-03-22
**Auditor:** Opus (Category-A Deterministic Audit)
**Scope:** All TITAN OS v5.8 Garmin-related components
**Status:** REVIEW_REQUESTED

---

## 1. Executive Summary

This audit examined 11 production modules and 3 test files across the Garmin data pipeline: sync → science engines → governance → persistence → orchestration. **37 findings** were identified, of which **5 are HIGH severity**, **8 are MEDIUM**, and the remainder are LOW or informational.

The most critical finding is a **data pipeline shape mismatch** (F-29) where `sync_sleep()` returns flattened keys (`sleep_score`, `total_sleep_hours`) but `_persist_garmin_data` expects raw Garmin keys (`restingHeartRate`, `sleepScores.overall.value`, `sleepTimeSeconds`). This causes silent fallback to optimistic defaults (RHR=0, sleep_score=75), which cascades through governance gates. Tests mask this because they construct payloads in the raw format directly.

---

## 2. Scope and Methodology

**Files audited (in order):**
1. `titan/integrations/garmin_sync.py` (674 lines)
2. `titan/science/hrv_engine.py` (200 lines)
3. `titan/science/drift_engine.py` (70 lines)
4. `titan/science/tsb_engine.py` (84 lines)
5. `titan/science/trimp_engine.py` (149 lines)
6. `titan/science/lactate_logic.py` (57 lines)
7. `titan/science/efficiency_engine.py` (150 lines)
8. `titan/science/governance_engine.py` (1107 lines)
9. `titan/science/governance_contracts.py` (138 lines)
10. `titan/core/database.py` (Garmin-relevant sections)
11. `titan/orchestration/daily_coach.py` (Garmin orchestration sections)
12. `tests/titan/integrations/test_garmin_sync.py` (559 lines)
13. `tests/test_garmin_sync.py` (705 lines)
14. `tests/test_garmin_sync_worker_lifecycle.py` (80 lines)

**Method:** Line-by-line read of all production code; Garmin-focused grep of test files; cross-referencing data shapes between pipeline stages.

---

## 3. HIGH Severity Findings

### F-13: TRIMP calculated using session maxHR instead of athlete HRmax
**Location:** `titan/science/trimp_engine.py:49`, called from `titan/integrations/garmin_sync.py:335-339`
**Impact:** Edwards TRIMP zones are defined as %HRmax. `garmin_sync.sync_activities()` passes the session's `maxHR` (peak HR during that specific activity) to `TRIMPEngine.calculate_edwards_trimp()`, not the athlete's physiological HRmax. This systematically misclassifies training zones — a recovery jog with session max of 130bpm would compute `avg_hr/130*100` instead of `avg_hr/185*100`, shifting zone classification upward. TRIMP values feed into TSB/CTL/ATL calculations downstream.

### F-27/F-32: Multi-day HRV sync data discarded — only today persisted
**Location:** `titan/orchestration/daily_coach.py:1184-1189`
**Impact:** `sync_hrv(days_back=7)` fetches 7 days of HRV from Garmin, but `_persist_garmin_data` only persists the entry matching `today_str` to `daily_metrics`. Historical days are loaded into the in-memory `hrv_engine` but never reach the database. On restart, the HRV baseline calculation in `get_hrv_history()` can only see the single persisted day, not the full 7-day window needed for meaningful baseline computation.

### F-29: Sleep field mapping mismatch — persist expects raw format, sync returns flattened
**Location:** `titan/orchestration/daily_coach.py:1158-1181`
**Impact:** `sync_sleep()` returns `{"total_sleep_hours": 7.0, "sleep_score": 80, ...}`. `_persist_garmin_data` looks for `entry.get('restingHeartRate')`, `entry.get('sleepScores', {}).get('overall', {}).get('value')`, and `entry.get('sleepTimeSeconds')`. None of these keys exist in the flattened output. Result: `today_rhr` defaults to 0, `today_sleep_score` defaults to 75, `today_sleep_hours` defaults to 7.5 — all hardcoded optimistic defaults. **The H3 gate (RHR spike) cannot fire because baseline_rhr is always 0.** The 2-of-4 sleep indicator never triggers because sleep_score defaults to 75 (above the 60 threshold).

### F-33/F-34: Tests mask F-29 by using raw Garmin format in fixtures
**Location:** `tests/titan/orchestration/test_daily_coach.py:83, 401`
**Impact:** All `_persist_garmin_data` tests construct payloads with `{"restingHeartRate": 50, "sleepScores": {"overall": {"value": 80}}}` — the raw Garmin API format, not what `sync_sleep()` actually returns. Tests pass but do not test the real production data path. No end-to-end test exists for the `sync_sleep() → _persist_garmin_data()` pipeline.

---

## 4. MEDIUM Severity Findings

### F-02: No `days_back` bounds validation on sync methods
**Location:** `garmin_sync.py:319, 382, 417, 478`
**Impact:** Negative values produce future start dates; large values trigger per-day API hammering in sleep/HRV syncs.

### F-03: Success events emitted after outer exception in sync_sleep/sync_hrv
**Location:** `garmin_sync.py:469, 531`
**Impact:** Telemetry records successful sync count even when outer exception was caught.

### F-07: Population SD instead of sample SD in HRV baseline
**Location:** `hrv_engine.py:66`
**Impact:** Divides by N instead of N-1. For 7-day window, underestimates SD by ~8%, making suppression thresholds 8% tighter than intended (Plews et al.).

### F-08: No deduplication of HRV measurements
**Location:** `hrv_engine.py:55`
**Impact:** Overlapping Garmin syncs inflate HRV log; duplicate entries skew baseline/trend calculations.

### F-17: ZeroDivisionError when Garmin pace is 0
**Location:** `efficiency_engine.py:56`
**Impact:** `1000.0 / avg_pace_sec_per_km` raises unguarded ZeroDivisionError for stationary activities.

### F-20: Garmin data age not propagated into governance gates
**Location:** `governance_engine.py` (context dict)
**Impact:** ADR-0041 DataTrustLevel exists at sync layer but governance cannot distinguish fresh vs. 24-hour-stale data.

### F-21/F-22: Missing Garmin data defaults to optimistic values in governance
**Location:** `governance_engine.py:198, 205`
**Impact:** Missing sleep_score defaults to 100; missing readiness_score defaults to 100. Safety-first system should use conservative defaults.

### F-26: INSERT OR REPLACE overwrites manual data on re-sync
**Location:** `database.py:758`
**Impact:** `save_daily_metric` replaces entire row; manually entered mood/notes are lost if Garmin-triggered save omits them.

### F-30: Optimistic sleep default compounds with governance defaults
**Location:** `daily_coach.py:1151`, `governance_engine.py:198`
**Impact:** Failed sleep extraction → score=75 → governance default=100 → sleep indicator never fires.

### F-31: All Garmin activities classified as session_type='EASY'
**Location:** `daily_coach.py:1256`
**Impact:** `sync_activities()` never sets `session_type`; default 'EASY' is used for all activities in DB.

### F-36: No test for TRIMP accuracy with session vs. athlete HRmax
**Location:** Test gap
**Impact:** Systematic TRIMP bias (F-13) has no test coverage.

---

## 5. LOW Severity Findings

| ID | Summary | Location |
|----|---------|----------|
| F-01 | `_garmin_error_event` logs at ERROR but emits WARNING severity | garmin_sync.py:77 |
| F-04 | ThreadPoolExecutor created per sync_all call | garmin_sync.py:571 |
| F-05 | Post-timeout elapsed check is dead code | garmin_sync.py:611-621 |
| F-06 | Credential whitespace not stripped | garmin_sync.py:53 |
| F-09 | HRV log in-memory only (mitigated by DB hydration) | hrv_engine.py:50 |
| F-10 | DriftEngine: no Garmin coupling (clean) | drift_engine.py |
| F-11 | TSBEngine: no Garmin coupling (clean) | tsb_engine.py |
| F-12 | TSB double-calculation (no caching) | tsb_engine.py:63-71 |
| F-14 | max_hr < 100 guard rejects valid low-HR sessions | trimp_engine.py:46 |
| F-15 | Banister TRIMP hr_reserve can go negative | trimp_engine.py:89 |
| F-16 | LactateLogic: no Garmin coupling (clean) | lactate_logic.py |
| F-18 | EF history in-memory only | efficiency_engine.py:33 |
| F-19 | H2 trigger dual representation maintenance risk | governance_engine.py:279/806 |
| F-23 | 2-of-4 evaluated before hard stops (safe direction) | governance_engine.py:943 |
| F-24 | No Garmin-specific input contract in governance | governance_contracts.py |
| F-25 | INSERT OR IGNORE silently drops updated re-syncs | database.py:831 |
| F-28 | garmin_activity_id not in CREATE TABLE (migration-dependent) | database.py:250 |
| F-35 | No test for days_back validation | Test gap |
| F-37 | Duplicate test coverage across two test files | Test organization |

---

## 6. Data Pipeline Map

```
Garmin API
  │
  ├─ sync_activities() → [{date, distance_km, duration_sec, avg_hr, max_hr, ...}]
  │     └─ TRIMPEngine.calculate_edwards_trimp(duration, avg_hr, session_max_hr) ← F-13: wrong HRmax
  │
  ├─ sync_weight() → [{date, weight_kg, bmi, source}]
  │
  ├─ sync_sleep() → [{date, total_sleep_hours, deep_sleep_hours, rem_sleep_hours, sleep_score}]
  │     └─ ⚠ F-29: _persist_garmin_data expects {restingHeartRate, sleepScores.overall.value, sleepTimeSeconds}
  │
  └─ sync_hrv() → [{date, rmssd, status, source}]
        └─ ⚠ F-32: only today's entry persisted to DB; 6 days discarded

DailyCoach._persist_garmin_data()
  │
  ├─ activities → db.save_session(session_type='EASY' always ← F-31)
  ├─ sleep → today_rhr (0 ← F-29), today_sleep_score (75 ← F-29)
  ├─ hrv → latest_rmssd (today only ← F-32)
  └─ weight → latest_weight

GovernanceEngine.apply_constraints(context)
  │
  ├─ H2: today_hrv vs baseline_hrv  ← baseline may be 1-day only (F-32)
  ├─ H3: today_rhr vs baseline_rhr  ← today_rhr=0 when F-29 active
  ├─ 2-of-4: sleep_score ← defaults to 100 when missing (F-21)
  └─ 2-of-4: readiness_score ← defaults to 100 when missing (F-22)
```

---

## 7. Garmin Sync Module Assessment

**garmin_sync.py** is well-structured with:
- Proper credential redaction (`_CredentialSecret`)
- Comprehensive structured event logging
- Rate-limit retry with exponential backoff
- Token persistence with staleness handling
- Session invalidation on auth failures
- Timeout protection via ThreadPoolExecutor
- Data trust evaluation at sync boundary (ADR-0041)

**Weaknesses:** No input validation on `days_back`, success events after outer exceptions, severity mismatch in error event helper.

---

## 8. Science Engine Assessment

**hrv_engine.py:** Population SD (should be sample SD per Plews et al.); no deduplication; in-memory only.
**drift_engine.py:** Clean, no Garmin coupling.
**tsb_engine.py:** Clean, no Garmin coupling; minor double-calculation inefficiency.
**trimp_engine.py:** Session maxHR misuse is the critical finding; otherwise sound implementation.
**lactate_logic.py:** Clean, no Garmin coupling.
**efficiency_engine.py:** Missing zero-pace guard.

---

## 9. Governance Engine Assessment

**governance_engine.py** is thorough with multi-gate safety, structured logging, APL integration, and decision rationale generation. The key concern is that Garmin data absence silently produces optimistic defaults rather than conservative ones, undermining the safety-first design philosophy.

---

## 10. Database Layer Assessment

**database.py** has proper WAL mode, thread-safe locking, schema migrations, and physiological bounds validation on reads. The INSERT OR REPLACE/IGNORE semantics create data freshness concerns on re-syncs.

---

## 11. Orchestration Assessment

**daily_coach.py** `_persist_garmin_data` is the critical junction where Garmin data is transformed and stored. The sleep field mapping mismatch (F-29) and single-day HRV persistence (F-32) are the two most impactful bugs in the system.

---

## 12. Test Coverage Assessment

**Strengths:** 56+ Garmin-related tests across 3 files; good coverage of connection lifecycle, timeout, retry, structured events, auth failure.
**Critical gap:** No end-to-end test validates the full `sync_*() → _persist_garmin_data()` pipeline. Test fixtures bypass `sync_sleep()` by constructing raw-format payloads, masking the F-29 shape mismatch.

---

## 13. Severity Distribution

| Severity | Count | Finding IDs |
|----------|-------|-------------|
| HIGH | 5 | F-13, F-27/F-32, F-29, F-33, F-34 |
| MEDIUM | 8 | F-02, F-03, F-07, F-08, F-17, F-20, F-21/F-22, F-26, F-30, F-31, F-36 |
| LOW | 14 | F-01, F-04, F-05, F-06, F-09, F-12, F-14, F-15, F-18, F-19, F-23, F-24, F-25, F-28, F-35, F-37 |
| N/A (clean) | 3 | F-10, F-11, F-16 |

---

## 14. Recommended Priority Actions

1. **P0 — Fix F-29 (sleep field mapping mismatch):** Align `_persist_garmin_data` sleep extraction with `sync_sleep()` output keys. This single fix restores RHR extraction and sleep score propagation to governance.
2. **P0 — Fix F-32 (persist all HRV days):** Loop over all HRV entries in `_persist_garmin_data`, not just today's. This restores baseline calculation fidelity.
3. **P1 — Fix F-13 (TRIMP HRmax):** Pass athlete's true HRmax (from profile) to TRIMP calculation, not session maxHR.
4. **P1 — Add end-to-end test (F-34):** Create integration test that runs `sync_sleep() → _persist_garmin_data()` with realistic mock data.
5. **P1 — Fix F-21/F-22 (governance defaults):** Change missing sleep/readiness defaults from 100 to conservative values (e.g., 40).
6. **P2 — Fix remaining MEDIUM findings:** F-02, F-03, F-07, F-08, F-17, F-20, F-26, F-30, F-31, F-36.

---

## 15. Modules Confirmed Clean (No Garmin Issues)

- `titan/science/drift_engine.py` — Pure computation, no Garmin dependency
- `titan/science/tsb_engine.py` — Pure EMA computation, no Garmin dependency
- `titan/science/lactate_logic.py` — Pure decision logic, no Garmin dependency
- `titan/science/governance_contracts.py` — VO2 output contract only (no Garmin input contract)

---

*End of OBS-025 Garmin Integration Audit*
