# Garmin Audit — Incremental Findings

## Batch 1: garmin_sync.py, hrv_engine.py, drift_engine.py, tsb_engine.py

### garmin_sync.py (674 lines)

**F-01: `_garmin_error_event` severity mismatch (line 77)**
Function named `_garmin_error_event` emits at `EventSeverity.WARNING`, not ERROR. The function logs via `_log.error()` but the structured payload severity is WARNING. This is a semantic inconsistency — callers expect ERROR-level severity from a function with "error" in the name.
- Category: Observability / Semantic correctness
- Severity: LOW (misleading but not data-corrupting)

**F-02: No `days_back` bounds validation on sync methods (lines 319, 382, 417, 478)**
`sync_activities(days_back)`, `sync_weight(days_back)`, `sync_sleep(days_back)`, `sync_hrv(days_back)` accept any integer including negative or extremely large values. A negative `days_back` would produce a start date in the future. An excessively large value (e.g., 10000) would hammer the Garmin API with per-day requests in sleep/hrv syncs.
- Category: Input validation / API abuse prevention
- Severity: MEDIUM (sleep/hrv iterate day-by-day; no upper bound)

**F-03: `sync_sleep` and `sync_hrv` emit success event even after outer exception (lines 469, 531)**
In both `sync_sleep` and `sync_hrv`, the "synced" and "skip_summary" events are emitted *outside* the outer try/except block, so they fire even if the outer except caught a fatal error. The success event after a failure is a telemetry lie.
- Category: Observability / Correctness
- Severity: MEDIUM (misleading metrics)

**F-04: `ThreadPoolExecutor` created per `sync_all` call (line 571)**
Every `sync_all()` invocation creates a new `ThreadPoolExecutor(max_workers=1)`. For the 6-hour background sync this is fine, but if `sync_all` is called in a tight loop (e.g., from tests or retries), this leaks thread pool resources despite `shutdown(wait=False)`.
- Category: Resource management
- Severity: LOW (daemon thread, practical impact minimal)

**F-05: `sync_all` post-timeout elapsed check is unreachable (lines 611-621)**
After the `try/except FuturesTimeoutError/finally` block, lines 611-621 check `elapsed_s >= timeout_s`. But if a timeout occurred, the function already returned inside the `except` block. If no timeout occurred, `elapsed_s < timeout_s` is virtually guaranteed. The `>= timeout_s` branch on line 612 is dead code in practice (only reachable if the future completes at exactly the timeout boundary).
- Category: Dead code / Logic clarity
- Severity: LOW

**F-06: `_CredentialSecret.__bool__` delegates to `_Secret.__bool__` (line 53-54)**
Correctness depends on `_Secret.__bool__` returning `False` for empty strings. If `_Secret` wraps a non-empty whitespace string, `bool()` returns `True` but credentials are effectively empty. No whitespace stripping on the credential input.
- Category: Edge case / Defensive coding
- Severity: LOW

### hrv_engine.py (200 lines)

**F-07: Population SD used instead of sample SD (line 66)**
`calculate_baseline` divides by `len(recent)` (population variance) rather than `len(recent) - 1` (sample variance / Bessel's correction). For small windows (e.g., 7 days), this underestimates SD by ~8%, making the suppression thresholds tighter than scientifically intended (Plews et al. use sample SD).
- Category: Science accuracy
- Severity: MEDIUM (affects training recommendation thresholds)

**F-08: No deduplication of HRV measurements (line 55)**
`add_hrv_measurement` appends unconditionally. If Garmin sync runs multiple times for overlapping date ranges, duplicate entries inflate the log and skew baseline/trend calculations.
- Category: Data integrity
- Severity: MEDIUM (silent corruption of rolling statistics)

**F-09: `hrv_log` is in-memory only (line 50)**
The entire HRV log is a list of tuples in memory. On restart, all historical HRV data must be re-synced from Garmin. No persistence layer. If Garmin API is down at startup, baseline calculation returns None and governance gates lose HRV signal.
- Category: Architecture / Resilience
- Severity: LOW (DailyCoach hydrates from DB on startup per CLAUDE.md)

### drift_engine.py (70 lines)

**F-10: No Garmin-specific coupling identified**
DriftEngine is a pure computation module. It receives `hr_data` as a list of floats — no direct Garmin API dependency. No findings related to Garmin integration.
- Category: N/A (clean module)
- Severity: N/A

### tsb_engine.py (84 lines)

**F-11: No Garmin-specific coupling identified**
TSBEngine receives daily loads via `add_daily_load()`. No direct Garmin API dependency. EMA calculations use configurable decay constants from `thresholds.py`.
- Category: N/A (clean module)
- Severity: N/A

**F-12: Double-calculation in `get_tsb_status` and `get_latest_tsb` (lines 63-71)**
Both `get_tsb_status()` and `get_latest_tsb()` call `calculate_tsb()`, which internally calls both `calculate_ctl()` and `calculate_atl()`. No caching — if called in sequence, the full EMA is recomputed 4 times. Not a correctness bug but wasteful for large load histories.
- Category: Performance
- Severity: LOW

---

## Batch 2: trimp_engine.py, lactate_logic.py, efficiency_engine.py

### trimp_engine.py (149 lines)

**F-13: `calculate_edwards_trimp` uses avg_hr/max_hr ratio, not %HRmax (line 49)**
Edwards zones are defined as % of HRmax (50-60%, 60-70%, etc.). The code computes `hr_percent = (avg_hr / max_hr) * 100` which is correct only if `max_hr` is the athlete's true HRmax. However, Garmin's `maxHR` field in activity data is the *session* max HR, not the athlete's physiological HRmax. This means the zone classification in `garmin_sync.py:335-339` (which passes session `max_hr`) systematically misclassifies zones — the TRIMP value is computed against session max, not athlete max.
- Category: Science accuracy / Garmin data misuse
- Severity: HIGH (TRIMP values used downstream for TSB/CTL/ATL; systematic bias)

**F-14: `max_hr < 100` guard rejects valid low-HR sessions (line 46)**
For warm-up or recovery activities where session max HR stays below 100 bpm (rare but possible in highly trained athletes), the function returns `None, 0`. This causes `garmin_sync.py:340` to assign `estimated_load = 0.0` — the activity is recorded with zero training load.
- Category: Edge case / Data accuracy
- Severity: LOW (extremely rare in running)

**F-15: `calculate_banister_trimp` hr_reserve can be negative (line 89)**
If `avg_hr < resting_hr` (e.g., corrupted Garmin data), `hr_reserve` goes negative. The exponential `exp(y * hr_reserve)` then produces a value < 1, and the final TRIMP is negative. No guard against this.
- Category: Input validation
- Severity: LOW (Banister TRIMP not currently called from garmin_sync.py)

### lactate_logic.py (57 lines)

**F-16: No direct Garmin coupling identified**
LactateLogic is a pure decision module consuming `hr_percent_max`, `drift_percent`, `hr_stable`, and `rpe`. All thresholds come from `thresholds.py`. No Garmin-specific findings.
- Category: N/A (clean module)
- Severity: N/A

### efficiency_engine.py (150 lines)

**F-17: `calculate_efficiency_factor` division by zero when pace is 0 (line 56)**
If `avg_pace_sec_per_km = 0` (which Garmin can return for stationary activities or corrupted data), `1000.0 / 0` raises `ZeroDivisionError`. The guard on line 53 only checks `avg_hr == 0`.
- Category: Input validation / Runtime safety
- Severity: MEDIUM (unguarded ZeroDivisionError from Garmin data)

**F-18: EF history is in-memory only, same pattern as HRV (line 33)**
`ef_history` is a list of tuples with no persistence. Same architectural note as F-09.
- Category: Architecture
- Severity: LOW

---

## Batch 3: governance_engine.py, governance_contracts.py

### governance_engine.py (1107 lines)

**F-19: H2 trigger uses `<=` but description says `>=` delta (lines 279-282)**
The H2 hard stop fires when `today_hrv <= baseline_hrv - HARD_STOP_HRV_DELTA`. The comment on line 277 says "drop >= HARD_STOP_HRV_DELTA (inclusive boundary)". The logic is correct (a drop of exactly HARD_STOP_HRV_DELTA triggers), but `_build_decision_rationale` (line 806) uses `hrv_delta >= HARD_STOP_HRV_DELTA` where `hrv_delta = baseline - today`. These two formulations are mathematically equivalent, but the dual representation (subtraction comparison vs. inequality comparison) is a maintenance hazard — a future editor might "fix" one without understanding the other.
- Category: Code clarity / Maintenance risk
- Severity: LOW (functionally correct, dual representation)

**F-20: Garmin data flows into governance gates without explicit provenance tracking**
The `context` dict passed to `apply_constraints` contains `today_hrv`, `baseline_hrv`, `today_rhr`, `baseline_rhr`, `tsb_value`, `sleep_score`, `readiness_score` — all ultimately derived from Garmin sync. However, there is no `data_source` or `data_age_hours` field in the context dict reaching the governance engine. The governance engine cannot distinguish between fresh Garmin data (synced 1 hour ago) and stale data (synced 24 hours ago). ADR-0041 (DataTrustLevel) was implemented for the sync layer but does not propagate into governance gate evaluation.
- Category: Data trust / Staleness gap
- Severity: MEDIUM (governance decisions may be based on stale Garmin data without awareness)

**F-21: `_evaluate_2of4_indicators` sleep_score default is 100 (line 198)**
When `sleep_score` is missing from context, the default is 100 (perfect sleep). This means a missing Garmin sleep sync silently passes the sleep indicator. The fail-safe default should arguably be conservative (e.g., 0 or None with explicit handling), not optimistic.
- Category: Fail-safe design / Garmin data absence
- Severity: MEDIUM (missing sleep data = assumed perfect sleep)

**F-22: `_evaluate_2of4_indicators` readiness_score default is 100 (line 205)**
Same issue as F-21 for readiness. Missing readiness data defaults to 100 (fully ready). Conservative fail-safe would be more appropriate for a safety-first system.
- Category: Fail-safe design / Garmin data absence
- Severity: MEDIUM (missing readiness data = assumed full readiness)

**F-23: `apply_constraints` evaluates 2-of-4 before hard stops (lines 943 vs 966)**
The 2-of-4 soft downgrade is evaluated *before* hard stops (H1-H5). This means a session could be downgraded from INTERVALS to TEMPO by 2-of-4, and then H4 checks against the already-downgraded session. The H4 gate on line 363 checks `session_type in _QUALITY_SESSIONS` — if 2-of-4 already downgraded to EASY, H4's quality check becomes a no-op. This is safe (more conservative), but the gate ordering differs from DECISION_MODEL canonical order where hard stops should evaluate first.
- Category: Gate ordering / Spec compliance
- Severity: LOW (safe direction, but deviates from documented canonical order)

### governance_contracts.py (138 lines)

**F-24: No Garmin-specific contract coverage**
Governance contracts only validate VO2 eligibility output shape. There are no contracts for the Garmin-sourced fields in the governance context dict (today_hrv, baseline_hrv, today_rhr, sleep_score, etc.). Input validation is done ad-hoc with try/except in governance_engine.py rather than through a formal input contract.
- Category: Contract coverage gap
- Severity: LOW (input validation exists but is informal)

---

## Batch 4: database.py, daily_coach.py

### database.py (Garmin-relevant sections)

**F-25: `save_session` uses INSERT OR IGNORE — silent duplicate drops (line 831)**
When the same Garmin activity is synced twice (e.g., overlapping date ranges), `INSERT OR IGNORE` silently discards the duplicate. There is no UNIQUE constraint on `garmin_activity_id` in the `training_log` schema, so the IGNORE clause relies on the implicit rowid uniqueness. If the activity comes with slightly different data on a re-sync (e.g., Garmin recalculated HR zones), the updated data is silently dropped.
- Category: Data integrity / Garmin re-sync
- Severity: LOW (conservative — keeps first value, but stale)

**F-26: `save_daily_metric` uses INSERT OR REPLACE — full row replacement (line 758)**
When daily metrics are re-saved (e.g., Garmin HRV sync runs twice on the same day), the entire row is replaced. Any manually entered data (e.g., mood, notes) that was set independently of Garmin would be overwritten with NULL if the Garmin-triggered save doesn't include those fields.
- Category: Data integrity / Manual vs. Garmin data conflict
- Severity: MEDIUM (user-entered data silently lost on re-sync)

**F-27: `get_hrv_history` queries `daily_metrics` not Garmin HRV directly**
HRV data flows: Garmin → `garmin_sync.sync_hrv()` → DailyCoach `_persist_garmin_data` → `save_daily_metric(hrv=rmssd)` → `daily_metrics.hrv_rmssd`. The `get_hrv_history()` method reads from `daily_metrics`, not from a dedicated HRV table. This means if `_persist_garmin_data` only saves today's HRV (it does — line 1187 matches only `today_str`), historical HRV from Garmin sync is discarded and never reaches the database.
- Category: Data pipeline gap / HRV loss
- Severity: HIGH (multi-day HRV sync data is fetched from Garmin but only today's value is persisted; historical HRV used for baseline calculation is lost)

**F-28: `training_log` schema has no `garmin_activity_id` column in CREATE TABLE (line 250)**
The `save_session` method passes `garmin_activity_id` as a parameter (line 264), but the original CREATE TABLE statement for `training_log` (line 250) does not include this column. This relies on a migration adding the column.
- Category: Schema clarity
- Severity: LOW (migration handles it; but schema definition is misleading)

### daily_coach.py (Garmin orchestration)

**F-29: `_persist_garmin_data` sleep field mapping assumes Garmin raw format (lines 1163-1172)**
The method looks for `restingHeartRate`, `rhr`, and nested `sleepScores.overall.value` — but `garmin_sync.sync_sleep()` (garmin_sync.py:432-441) already extracts and flattens these into `total_sleep_hours`, `deep_sleep_hours`, `sleep_score`. The persist method is re-parsing the *raw* Garmin format rather than the *flattened* format returned by `sync_sleep()`. This means the sleep parsing in `_persist_garmin_data` likely sees the flattened keys (`total_sleep_hours`, `sleep_score`) and falls through to defaults.
- Category: Data pipeline mismatch / Bug
- Severity: HIGH (sleep score and RHR extraction from sync_sleep output likely fails silently; defaults to today_rhr=0, today_sleep_score=75)

**F-30: Default `today_sleep_score = 75` is optimistic for a safety-first system (line 1151)**
When sleep data extraction fails (see F-29), the default sleep score is 75. Combined with F-21 (governance defaults sleep_score to 100), the system never triggers the sleep indicator in the 2-of-4 downgrade unless Garmin provides perfect data.
- Category: Fail-safe defaults
- Severity: MEDIUM (compounds with F-21 and F-29)

**F-31: `session_type` mapped as 'EASY' for all Garmin activities (line 1256)**
`act.get('session_type', 'EASY')` — but `garmin_sync.sync_activities()` never sets a `session_type` field (see garmin_sync.py:341-355). All synced activities are stored as `session_type='EASY'` regardless of actual intensity. This affects TSB/CTL calculations that may use session type for filtering.
- Category: Data classification / Garmin sync gap
- Severity: MEDIUM (all Garmin activities classified as EASY in DB)

**F-32: Only today's HRV is persisted from multi-day sync (line 1187)**
`sync_hrv(days_back=7)` fetches 7 days of HRV data, but `_persist_garmin_data` only persists the entry matching `today_str`. The other 6 days of HRV data are used to populate the in-memory `hrv_engine` (line 454-455) but never reach the database. On restart, only the single day persisted in `daily_metrics` survives.
- Category: Data pipeline gap
- Severity: HIGH (confirms and specifies the mechanism behind F-27)

---

## Batch 5: Test Coverage Assessment

### tests/titan/integrations/test_garmin_sync.py (559 lines, 28 tests)

Good coverage of: connection lifecycle, token persistence, 429 retry logic, timeout handling, session invalidation on auth failure, HRV sync metrics contract, data_trust contract, training load estimation.

**F-33: Test payloads bypass sync_sleep flattening — F-29 masked (tests/titan/orchestration/test_daily_coach.py:83)**
Test fixtures use raw Garmin format `{"restingHeartRate": 50, "sleepScores": {"overall": {"value": 80}}, "sleepTimeSeconds": 25200}` directly in the garmin payload passed to `_persist_garmin_data`. In production, `sync_sleep()` returns `{"total_sleep_hours": 7.0, "sleep_score": 80}` — a completely different shape. The tests pass because they test `_persist_garmin_data` against the raw format, not the format actually produced by `sync_sleep()`. This masks the F-29 data pipeline mismatch.
- Category: Test fidelity / Integration gap
- Severity: HIGH (tests validate wrong data shape; production sleep/RHR extraction silently fails)

**F-34: No end-to-end test for sync_sleep → _persist_garmin_data pipeline**
There is no test that calls `sync_sleep()` and then passes its output through `_persist_garmin_data()`. All `_persist_garmin_data` tests construct their own payloads, bypassing the sync layer. The missing integration test is why F-29 was never caught.
- Category: Test gap
- Severity: HIGH (no coverage of the most critical data pipeline)

**F-35: No test for `days_back` validation on sync methods (F-02)**
No test verifies behavior with negative `days_back`, zero `days_back`, or extremely large `days_back` values for any sync method.
- Category: Test gap
- Severity: LOW

**F-36: No test for TRIMP calculation using session maxHR vs athlete HRmax (F-13)**
Tests for `sync_activities` verify that `estimated_training_load > 0` but do not verify the correctness of the TRIMP value. The systematic bias from using session maxHR instead of athlete HRmax is not tested.
- Category: Test gap
- Severity: MEDIUM

### tests/test_garmin_sync.py (705 lines, 28 tests)

Good coverage of: activity sync happy path, weight sync, sleep sync, HRV sync, error classification, structured event emission, auth failure handling, background worker lifecycle.

**F-37: Duplicate test coverage with tests/titan/integrations/test_garmin_sync.py**
Both files test overlapping functionality (e.g., both have `test_sync_weight_empty_all_day_summaries`, background worker tests). This is not a bug but creates maintenance burden.
- Category: Test organization
- Severity: LOW (informational)

### tests/test_garmin_sync_worker_lifecycle.py (80 lines)

Small focused file testing worker thread lifecycle. No Garmin-specific data findings.

---
