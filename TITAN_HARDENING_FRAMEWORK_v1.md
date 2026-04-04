# TITAN OS — System Hardening Framework v1.0

**Date:** 2026-04-03
**Source:** Full audit synthesis — Adversarial, Behavioral, Temporal, Compliance, Chaos, Poisoning, Dependency, Security, QA audits + SCRATCHPAD OBS-001→OBS-036 + TECHNICAL_DEBT T1→T5 + live code validation
**Status:** Execution-ready. Single source of truth for Phase 9 hardening.

---

## 1. Technical Debt Register (Phase 9 Hardening)

### 1.1 OPEN Items (require implementation)

| ID | Title | Root Cause | Files | Failure Class | Severity | Impact |
|---|---|---|---|---|---|---|
| T5-67 | Sync methods emit success events after exception | Success event outside try block | `garmin_sync.py` (4 methods) | Observability | MED | SLO alerting blind to exception-aborted syncs |
| T5-12-P2 | Garmin API fragility mitigation (implementation) | No fallback on auth mechanism change; ADR-0050 accepted | `garmin_sync.py`, `daily_coach.py` | External Dep | P3 | Total biometric data loss on API break |
| HD-01 | Rolling baseline poisoning — no drift detector | HRV/RHR baselines adapt WITH progressive deterioration | `hrv_engine.py`, `governance_engine.py` | Safety Logic | HIGH | 7–14 day overtraining invisible to governance |
| HD-02 | Mixed naive/aware datetime across sync + orchestration | `datetime.now()` vs `datetime.now(UTC)` coexist | `garmin_sync.py`, `daily_coach.py`, `database.py` | Data Integrity | HIGH | Day-bucket misassignment near DST/midnight |
| HD-03 | NaN bypass in float comparisons across governance | `float("nan")` comparisons return False; except blocks miss NaN | `governance_engine.py` (all gates) | Safety Logic | HIGH | Hard-stop gates silently pass on NaN |
| HD-04 | In-memory AuthStore — restart fragility | Users + refresh tokens process-local only | `auth.py` | Security | HIGH | Mass 401 on restart |
| HD-05 | Unbounded rate-limiter key growth | No eviction policy on `(user, role, path)` keys | `api/main.py` | Security | HIGH | Memory DoS |
| HD-06 | DegradedModeTracker in-memory only | Resets on restart; 24h SLO evidence lost | `daily_coach.py` | Concurrency | MED | Alert timer silently resets |
| HD-07 | Date-only truncation destroys ordering fidelity | Activity date = first 10 chars of startTimeLocal | `garmin_sync.py` | Data Integrity | MED | Wrong day-bucket for sessions near midnight |
| HD-08 | Decision pipeline runs on mixed data epochs | Partial failures → fallback defaults mixed with fresh data | `daily_coach.py` | Data Integrity | MED | Frankenstein state in coaching decision |
| HD-09 | No population-specific threshold adaptation | Static thresholds regardless of age/fitness; half-life ~10–16 weeks | `thresholds.py` | Safety Logic | MED | Elite/beginner/masters governed identically |

### 1.2 RESOLVED Items (traceability preserved)

| ID | Resolution | Failure Class |
|---|---|---|
| T5-63 | VO2 gate: None→ineligible; 5 regression tests (PR #556) | Fail-Open |
| T5-64 | cs_confidence: 1.0→0.0 in daily_coach APL feed (PR #557) | Fail-Open |
| T5-65 | _classify_hrv_drop: UNKNOWN_ACWR per ADR-0051 | Fail-Open |
| T5-66 | save_daily_metric: per-column UPSERT preserving manual fields | Data Integrity |
| T5-69 | activityId extracted; unique index; INSERT OR IGNORE | Data Integrity |
| T5-44 | TRIMP: session maxHR→athlete HRmax; DailyCoach wiring | Safety Logic |
| T5-45 | HRV baseline: N→N-1 (sample SD per Plews et al.) | Safety Logic |
| T5-46 | HRV dedup by timestamp at ingestion | Data Integrity |
| T5-51 | ACWR: None propagation; governance sees "unknown" | Fail-Open |
| T5-52 | CS confidence: default 0.0; CS_CONFIDENCE_LOCK fires | Fail-Open |
| T5-60 | Sleep fields: reads flattened keys; default 75→50 | Data Integrity |
| T5-61 | Multi-day HRV: loops all entries; INSERT OR IGNORE | Data Integrity |
| T5-62 | Zero-sync: 429→invalidate; empty sync=failure | Observability |
| T5-68 | ESI_DEW_POINT_FALLBACK_C=18.0 in thresholds.py | Data Integrity |

---

## 2. Problematic File Analysis

### Tier 1 — Critical (governance/safety path)

| File | Confirmed Findings | Dominant Pattern | Risk |
|---|---|---|---|
| `governance_engine.py` | 8 | NaN bypass, optimistic defaults, non-finite comparison | Safety gate silent failure |
| `daily_coach.py` | 12 | Mixed datetime, Frankenstein state, field mapping, fallback defaults | Wrong coaching decisions |
| `garmin_sync.py` | 7 | Naive datetime, unconditional success events, auth fragility | Data pipeline deception |
| `database.py` | 5 | Date-only uniqueness, INSERT OR REPLACE, TZ-naive queries | Cross-athlete contamination |

### Tier 2 — High (data pipeline)

| File | Confirmed Findings | Dominant Pattern | Risk |
|---|---|---|---|
| `persistence.py` | 3 | athlete_id dropped in PG adapter, dual-stack drift | Multi-athlete data corruption |
| `auth.py` | 3 | In-memory store, token in response body, no eviction | Security, session instability |
| `api/main.py` | 2 | Unbounded limiter, audit gap | Memory DoS |
| `hrv_engine.py` | 2 (both resolved) | Population SD, no dedup | Baseline inflation (fixed) |

### Tier 3 — Medium (feature/integration)

| File | Confirmed Findings | Dominant Pattern | Risk |
|---|---|---|---|
| `weather_api.py` | 2 (resolved) | Inline dew-point literals, TZ parsing | Threshold drift (fixed T5-41) |
| `nutrition_optimizer.py` | 1 (resolved) | Optimistic dew_point default | Hydration underestimation (fixed T5-59) |
| `weekly_plan.py` | 2 (resolved) | Static plan, null HRV TypeError | No mid-week re-eval (fixed T5-57/T5-58) |

---

## 3. Failure Pattern Synthesis

### FP-01: Fail-Open / Optimistic Defaulting

**Pattern:** Missing/null safety inputs default to values that PASS gates instead of FAIL them.
**Mechanism:** `.get("field", OPTIMAL_VALUE)` or `float(1.0 if x is None else x)` where OPTIMAL_VALUE is within safe range.
**Findings:** OBS-028/029/030, T5-44→T5-59, T5-63/64/65, Chaos-F, Poisoning§1
**Debt:** ADR-0051 (policy) → T5-63/64/65 (RESOLVED) + HD-01/HD-03 (OPEN)
**Status:** Partially resolved. VO2 gate, cs_confidence, HRV classification fixed. NaN bypass + baseline poisoning remain.

### FP-02: Time Inconsistency

**Pattern:** Mixed naive/aware datetime objects across ingestion, orchestration, persistence.
**Mechanism:** `datetime.now()` (naive) in sync; `datetime.now(UTC)` (aware) in metadata; `date('now')` (SQLite-local) in queries; ISO truncation losing TZ offset.
**Findings:** Chaos-A/B/C, Dependency-Risk-3, QA-garmin_sync
**Debt:** HD-02, HD-07 (OPEN)
**Status:** Unresolved. No UTC-only enforcement.

### FP-03: NaN Propagation / Non-Finite Bypass

**Pattern:** `float("nan")` passes conversion but makes all comparisons False, suppressing gate triggers.
**Mechanism:** Except blocks catch TypeError/ValueError; NaN is a valid float. `acwr <= VO2_ACWR_MAX` → no-op.
**Findings:** Security-R2-NaN, Chaos-J, 10k§5
**Debt:** HD-03 (OPEN)
**Status:** Unresolved. Property tests explicitly exclude NaN (`allow_nan=False`).

### FP-04: Partial State Continuation (Frankenstein State)

**Pattern:** Decision pipeline continues on mixed-epoch data after partial failures.
**Mechanism:** PersistenceFailure → degraded defaults injected → remaining steps run with old DB + partial fresh + placeholders.
**Findings:** Chaos-D/K, Poisoning§4
**Debt:** HD-08 (OPEN)
**Status:** Mitigated (PERSISTENCE_DEGRADED_CEILING locks to EASY). Not fully resolved: downstream steps still compute on mixed state.

### FP-05: In-Memory State Reliance

**Pattern:** Critical operational state exists only in process memory; lost on restart.
**Mechanism:** AuthStore, rate-limiter buckets, DegradedModeTracker — all process-local.
**Findings:** Security-R1, Chaos-E, 10k§4
**Debt:** HD-04, HD-05, HD-06
**Status:** Unresolved. Single-process deployment masks the problem.

### FP-06: Loose Contracts / Dict-Based Context

**Pattern:** Governance context is a mutable dict; field absence indistinguishable from explicit None.
**Mechanism:** `context.get("field", default)` without runtime TypedDict enforcement.
**Findings:** Chaos transactional integrity, Dependency-Risk§3, OBS-021
**Debt:** Existing DailyCoachContextContract (partial; advisory only)
**Status:** Partially resolved. TypedDict contracts exist but remain advisory at runtime.

### FP-07: Rolling Baseline Poisoning

**Pattern:** HRV/RHR baselines are rolling means; gradual deterioration shifts the baseline with the athlete.
**Mechanism:** `mean(hrv_log[-7:])`. Daily -3ms stays below HARD_STOP_HRV_DELTA=15ms; cumulative 7-day drop = -21ms.
**Findings:** Poisoning§1, Temporal-Degradation§1
**Debt:** HD-01 (OPEN). T5-07 provides infrastructure but no active drift detector.
**Status:** Unresolved. Half-life ~10–16 weeks without recalibration.

### FP-08: Cross-Athlete Contamination

**Pattern:** Date-only uniqueness without athlete_id; multi-athlete writes collide.
**Mechanism:** `daily_metrics.date UNIQUE` (no athlete_id); PG adapter `del athlete_id`.
**Findings:** 10k§1 (P0), Dependency-Risk-1, OBS-021
**Debt:** ADR-0040 + T4-31 (active for new code); existing schema not migrated.
**Status:** Mitigated for new code. Phase 9 blocker if existing schema not addressed.

### FP-09: Observability Deception

**Pattern:** Pipeline reports success when data quality is degraded.
**Mechanism:** Success events emitted outside try/except (T5-67); empty sync recorded as success (T5-62 fixed).
**Findings:** OBS-032, T5-67 (OPEN), T5-62 (RESOLVED)
**Debt:** T5-67 (OPEN)
**Status:** Partially resolved.

---

## 4. Audit vs Reality Validation

### Confirmed

| Finding | Validation | Evidence | Status |
|---|---|---|---|
| VO2 gate optimistic defaults (OBS-028) | `governance_engine.py:431-450` pre-fix | `.get("acwr", 1.0)` + `float(1.0 if None)` | ✅ RESOLVED T5-63 |
| cs_confidence 1.0 regression (OBS-029) | `daily_coach.py:768` pre-fix | `_safe_float(getattr(..., 1.0), 1.0)` | ✅ RESOLVED T5-64 |
| INSERT OR REPLACE destroys fields (OBS-031) | `database.py:758` pre-fix | `INSERT OR REPLACE INTO daily_metrics` | ✅ RESOLVED T5-66 |
| Sync success unconditional (OBS-032) | `garmin_sync.py:469,531` current | Event emitted after except block | 🟡 OPEN T5-67 |
| No activity dedup (OBS-036) | Schema + code audit | No `activity_id` column | ✅ RESOLVED T5-69 |
| Mixed naive/aware datetime (Chaos-A) | Grep `datetime.now()` vs `datetime.now(UTC)` | garmin_sync: naive; daily_coach: mixed; database._run_migrations: `utcnow()` | 🔴 OPEN |
| NaN bypass (Security-R2) | All gates use `float()` + comparison | `float("nan") <= threshold` → False | 🔴 OPEN |
| Rolling baseline adapts with drift (Poisoning§1) | `hrv_engine.py` | `mean(hrv_log[-days:])` includes poisoned values | 🔴 OPEN |
| AuthStore in-memory (Security-R1) | `auth.py` | `self._users: dict`, `self._tokens: dict` | 🔴 OPEN |
| Rate-limiter unbounded (Security-R1) | `api/main.py` | `_requests` dict without eviction | 🔴 OPEN |
| DegradedModeTracker in-memory (Chaos-E) | `daily_coach.py` | `self._degraded_since: dict` resets on restart | 🔴 OPEN |
| PG adapter drops athlete_id (Dep-Risk§1) | `persistence.py` | `del athlete_id` in write paths | 🔴 OPEN |
| Property tests exclude NaN (Security-R2) | `test_property_based.py` | `allow_nan=False` in all strategies | 🔴 OPEN |

### Partial

| Finding | Detail |
|---|---|
| Structural sanity narrow (Chaos-F) | DataSanityChecker exists but covers limited set; logical impossibilities pass as `degraded` |
| Fail-open mixed posture (Chaos) | ADR-0051 covers governance; non-governance paths still degrade-and-continue |
| GDPR consent gap (Compliance§2) | `consent_log` table exists; runtime hooks not implemented |
| Medical disclaimer (Compliance§5) | No disclaimer in Telegram message composition |

### Invalid (finding does not match current code)

| Finding | Reason |
|---|---|
| ACWR defaults 1.0 in DailyCoach (B1-F04) | RESOLVED T5-51 |
| CS confidence 1.0 in governance (B2-F01) | RESOLVED T5-52 |
| Sleep reads raw Garmin keys (F-29) | RESOLVED T5-60 |
| Multi-day HRV discards history (F-27/F-32) | RESOLVED T5-61 |
| Stale token assumed valid on 429 (Z1) | RESOLVED T5-62 |
| Out-of-scope routing conflict (OBS-012) | NO_ACTION DEC-012: docs aligned |
| Scratchpad continuation conflict (OBS-008) | NO_ACTION DEC-008: single authoritative statement |

---

## 5. Governance Gap Analysis

### AGENTS.md Gaps

| Gap | Section | Impact |
|---|---|---|
| No NaN/non-finite guard mandate | §8 Architecture Constraints | Gates silently bypassed by NaN |
| No UTC-only timestamp mandate | §8 Architecture Constraints | Time inconsistency across layers |
| No periodic recalibration mandate | §16.7/§16.8 | Baselines drift without detection |
| No runtime contract enforcement | §8 | Dict context allows silent field absence |
| No in-memory state persistence mandate | §8 | Restart-fragile auth/degraded/limiter |

### Where Governance Permitted Failures

| Failure | Gap |
|---|---|
| T5-63/64 optimistic defaults persisted for weeks | No missing-data policy until ADR-0051 (reactive) |
| T5-52 fix incomplete (daily_coach missed) | No file-existence verification at closure (DEC-007 added checklist) |
| Rolling baseline poisoning undetected | No drift-detection mandate; recalibration deferred Phase 9 |
| NaN bypass undetected | Property tests excluded NaN; no governance rule required NaN coverage |

---

## 6. Governance Upgrades

### 6.1 Hard Rules

| ID | Rule | Rationale | Enforcement |
|---|---|---|---|
| HR-01 | **UTC-only timestamps** — `datetime.now()` (naive) FORBIDDEN in new code | Chaos-A/B/C | AST lint: flag `datetime.now()` without `tz=UTC` |
| HR-02 | **No NaN in governance** — `math.isfinite()` before every gate comparison; NaN→conservative fail | Security-R2, Chaos-J | Pre-decision sanity gate (§8) |
| HR-03 | **Fail-closed governance** — ADR-0051 applies to ALL inputs; None/absent→conservative | OBS-028/029/030 | ADR-0051 + invariant test |
| HR-04 | **NaN tests for every gate** — boundary-ON + boundary-OFF + NaN-input in `test_governance_mutation.py` | T4-18 NaN gap | Extend test matrix |
| HR-05 | **No critical in-memory-only state** — auth, limiter, degraded tracker MUST survive restart | Security-R1, Chaos-E | Phase 9 prerequisite |
| HR-06 | **Athlete-scoped writes** — every per-athlete DB write MUST include `athlete_id` | 10k§1 | T4-31 CI (active) |

### 6.2 Forbidden Patterns

| Pattern | Example | Source |
|---|---|---|
| `context.get("field", OPTIMAL_VALUE)` for safety fields | `context.get("acwr", 1.0)` | OBS-028 |
| `datetime.now()` without UTC | `self.last_sync = datetime.now().isoformat()` | Chaos-A |
| `float(x)` without `math.isfinite()` in governance | `acwr = float(context.get("acwr", 1.0))` | Chaos-J |
| `INSERT OR REPLACE` on multi-source tables | `INSERT OR REPLACE INTO daily_metrics` | OBS-031 |
| `del athlete_id` in adapter methods | PG adapter write paths | Dep-Risk§1 |
| Success events outside exception guard | `_garmin_event("synced")` after except | OBS-032 |
| Rolling mean as sole baseline without drift detection | `mean(hrv_log[-7:])` as H2 reference | Poisoning§1 |

### 6.3 Required Tests

| Category | Requirement | Target |
|---|---|---|
| NaN | Each governance gate: NaN input → conservative outcome | `test_governance_mutation.py` |
| Timezone | All production datetime objects are UTC-aware | `test_architectural_invariants.py` |
| Baseline Drift | 7-day gradual HRV decline triggers warning | New: `test_baseline_drift_detection.py` |
| Partial Failure | PersistenceFailure → EASY ceiling, no quality session | `test_daily_coach.py` |
| Cross-Athlete | Two athletes same date → no collision | `test_athlete_isolation_invariant.py` |
| Concurrency | DegradedModeTracker survives simulated restart | New: `test_degraded_tracker_persistence.py` |

### 6.4 State Rules

| State | Current | Required |
|---|---|---|
| AuthStore | In-memory dict | DB-backed persistent store |
| Rate-limiter | In-memory, no eviction | TTL-based eviction or DB-backed |
| DegradedModeTracker | In-memory, resets on restart | Persist `_degraded_since` to DB |
| Governance context | Mutable dict by reference | Frozen dataclass or validated TypedDict at boundary |

### 6.5 Data Integrity Rules

| Rule | Rationale |
|---|---|
| No lossy timestamp truncation — preserve full ISO-8601 with offset | Chaos-B |
| Per-column UPSERT for multi-source tables | T5-66 |
| INSERT OR IGNORE for historical backfill | T5-61 |
| Dedup by natural key (activity_id, timestamp) not date alone | T5-69 |

---

## 7. Invariant Enforcement

| # | Invariant | Enforcement Point | On Violation |
|---|---|---|---|
| INV-01 | Every governance gate input is finite (`math.isfinite()`) | Pre-decision sanity gate | **Reject**: conservative outcome; emit `governance_nan_rejected` CRITICAL |
| INV-02 | All datetime in governance path are UTC-aware | `_decision_pipeline()` entry | **Reject**: raise ValueError |
| INV-03 | `athlete_id` present in every per-athlete DB write | `save_daily_metric()`, `save_session()`, `save_governance_decision()` | **Reject**: raise IntegrityError |
| INV-04 | Governance context contains all required keys before gate eval | Pre-decision sanity gate | **Quarantine**: STARTUP_DATA_CONFIDENCE_CEILING |
| INV-05 | No governance gate defaults missing field to optimistic value | Every `.get()` in governance_engine.py | **Fail**: None/absent → conservative (ADR-0051) |
| INV-06 | HRV baseline drift rate ≤ threshold over 14-day window | Startup hydration or new drift checker | **Quarantine**: emit `hrv_baseline_drift_warning` WARNING |
| INV-07 | Activity dedup by `garmin_activity_id` — no duplicate TRIMP | `save_session()` unique index | **Reject**: skip duplicate (post-T5-69) |
| INV-08 | Sync success event ONLY when no exception in method | 4 sync methods | **Reject**: exception → failure/warning event only |
| INV-09 | `INSERT OR REPLACE` forbidden on multi-source tables | `save_daily_metric()` | **Reject**: code review + T4-19 extension |
| INV-10 | Rate-limiter key count bounded by ceiling | `api/main.py` | **Fail**: evict oldest; emit `limiter_eviction` |

---

## 8. Pre-Decision Sanity Gate

**Location:** `_decision_pipeline()` entry, BEFORE step 7 (readiness).

```
PRE-DECISION SANITY GATE
═════════════════════════

CHECK 1 — Data Completeness
  Required fields: acwr, readiness_score, today_hrv, baseline_hrv,
                   today_rhr, baseline_rhr, sleep_score, tsb_value
  IF any field is None or absent:
    → data_confidence_low = True
    → Emit: governance_input_incomplete (WARNING)

CHECK 2 — No NaN / Non-Finite
  For each numeric governance field:
    IF not math.isfinite(value):
      → Replace with None → triggers CHECK 1
      → Emit: governance_nan_rejected (CRITICAL)

CHECK 3 — Timestamp Consistency
  Assert sync timestamps are UTC-aware.
  Assert today_str = UTC date.
  IF naive datetime detected:
    → Emit: governance_naive_datetime (WARNING)
    → Convert to UTC (best-effort)

CHECK 4 — No Mixed State
  IF persistence_degraded:
    → Verify fallbacks are conservative (not optimistic)
  IF garmin_data_stale:
    → Verify staleness propagates to all gates

IF ANY CHECK FAILS:
  → STARTUP_DATA_CONFIDENCE_CEILING (EASY + max_zone 2)
  → Emit: governance_sanity_gate_fail
  → Continue in degraded-conservative mode
```

---

## 9. Failure Simulation Layer

### 9.1 Critical Scenarios

| # | Scenario | Input | Expected | Guards |
|---|---|---|---|---|
| FS-01 | NaN ACWR reaches VO2 gate | `acwr = float("nan")` | V1 FAILS; downgraded | INV-01, CHECK 2 |
| FS-02 | 7-day HRV decline (-3ms/day) | 60→57→54→51→48→45→42 | Drift warning by day 5 | INV-06 |
| FS-03 | Garmin returns valid empty JSON | `{"activities":[],"hrv":[],...}` | `sync_ok=False`; staleness timer NOT reset | T5-62 |
| FS-04 | PersistenceFailure mid-pipeline | DB rollback after partial persist | PERSISTENCE_DEGRADED_CEILING; EASY | PersistenceFailure handler |
| FS-05 | Two athletes same date shared DB | Both call `save_daily_metric("2026-04-03")` | Each row independent (athlete_id) | INV-03, ADR-0040 |
| FS-06 | TZ boundary: 23:59 local = next day UTC | `startTimeLocal: "2026-04-03T23:59:00+03:00"` | Correct UTC date assignment | HR-01, INV-02 |
| FS-07 | Restart during degraded mode | 20h accumulated; process restarts | Timer restored from DB | HD-06 fix |
| FS-08 | Stale + fresh data mixed | Today HRV fresh; sleep 3 days old | data_confidence_low = True | CHECK 4 |
| FS-09 | Rate-limiter key explosion | 10k unique (user, path) combos | Eviction at ceiling; memory bounded | INV-10 |
| FS-10 | Override threshold surfing | 79% overrides (below 80% lockdown) | WARNING emitted; lockdown at 80% | ADR-0038 |

### 9.2 Behavioral Exploitation Scenarios

| # | Scenario | Vector | Detection |
|---|---|---|---|
| BE-01 | Override laundering | Many small "reasonable" overrides | `override_rate_30d > 25%` |
| BE-02 | Readiness gaming | Strategic sleep/mood reporting | Readiness→outcome divergence (RPE≥8 after EXCELLENT) |
| BE-03 | Green-means-go | Consecutive GREEN → stacked intensity | Quality-session streak without recovery flag |

---

## 10. Observability Contract

| Risk | Metric | Event | Alert Condition |
|---|---|---|---|
| NaN in governance | `governance_nan_count` | `governance_nan_rejected` (CRITICAL) | Any occurrence |
| Baseline drift | `hrv_baseline_delta_14d` | `hrv_baseline_drift_warning` (WARNING) | `|delta| > 8.0ms` |
| Garmin failure streak | `garmin_consecutive_failures` | `garmin_api_degraded` (CRITICAL) | `count ≥ 3` |
| Stale Garmin data | `garmin_hours_since_success` | `garmin_data_stale` (CRITICAL) | `hours > 26` |
| False sync success | `garmin_false_success_count` | `garmin_sync_false_success` (WARNING) | Exception + success event |
| Empty sync | `garmin_empty_sync_count` | `garmin_sync_empty` (WARNING) | `records=0 AND status≠timeout` |
| Low startup confidence | `startup_confidence_score` | `startup_low_confidence` (WARNING) | `score < 3` |
| Persistence degraded | `persistence_degraded_hours` | `persistence_degraded_mode` (WARNING) | Any; escalate at 24h |
| Override drift | `override_rate_30d` | `operator_trust_drift` (WARNING) | `rate > 0.25` |
| Cross-athlete violation | `cross_athlete_write_blocked` | `athlete_isolation_violation` (CRITICAL) | Any occurrence |
| Auth state reset | `auth_store_reinitialized` | `auth_state_reset` (WARNING) | Restart + tokens=0 |
| Limiter eviction | `limiter_keys_evicted` | `limiter_eviction` (WARNING) | Eviction triggered |
| Frankenstein state | `mixed_epoch_decision` | `decision_mixed_state` (WARNING) | `persistence_degraded AND pipeline_completed` |

### Observability Invariants (confirmed in live code)

1. Every gate eval emits `garmin_data_age_hours` + `garmin_data_trust_level` — **CONFIRMED** (T5-48)
2. Every sync method emits success OR failure event (never both, never neither) — **OPEN** (T5-67)
3. Every PersistenceFailure emits `persistence_degraded_mode` + attempts alert — **CONFIRMED**
4. Every lock application emits `governance_locks_applied` — **CONFIRMED**

---

## 📜 INSTRUCTION ΠΡΟΣ ΤΗΡΗΤΗ ΕΓΓΡΑΦΩΝ

Κατέγραψε τα αποτελέσματα ως:

1. Technical Debt Register (Phase 9)
2. Governance Gap Report
3. Governance Upgrade Specification

### Requirements:

* Versioned documents (v1.0 + timestamp)
* Immutable records
* Risk classification
* Mapping: finding → debt → rule

### Governance Update:

Ενημέρωσε AGENTS.md και CLAUDE.md με:

* Hard Rules
* Forbidden Patterns
* Required Tests
* Invariants

### Enforcement:

Κανένα νέο code δεν επιτρέπεται αν:

* παραβιάζει invariants
* δεν καλύπτεται από required tests

### Prevention:

Καθιέρωσε:

* periodic audit cycle
* validation against governance rules

### Traceability:

Σύνδεσε:
audit → debt → governance → enforcement

Επιβεβαίωσε την καταγραφή.

---

## Appendix: Traceability Matrix

| Source | Pattern | Debt | Rule | Status |
|---|---|---|---|---|
| OBS-028 + Chaos-F | FP-01 | T5-63 | HR-03 / ADR-0051 | ✅ |
| OBS-029 | FP-01 | T5-64 | HR-03 / ADR-0051 | ✅ |
| OBS-030 | FP-01 | T5-65 | HR-03 / ADR-0051 | ✅ |
| OBS-031 | FP-01 + Integrity | T5-66 | §6.5 UPSERT | ✅ |
| OBS-032 | FP-09 | T5-67 | INV-08 | 🟡 |
| OBS-036 | Integrity | T5-69 | INV-07 | ✅ |
| Chaos-A/B/C | FP-02 | HD-02, HD-07 | HR-01 | 🔴 |
| Security-R2, Chaos-J | FP-03 | HD-03 | HR-02, INV-01 | 🔴 |
| Poisoning§1 | FP-07 | HD-01 | INV-06 | 🔴 |
| Security-R1 (auth) | FP-05 | HD-04 | HR-05 | 🔴 |
| Security-R1 (limiter) | FP-05 | HD-05 | INV-10 | 🔴 |
| Chaos-E | FP-05 | HD-06 | HR-05 | 🔴 |
| Chaos-D/K | FP-04 | HD-08 | §8 Gate | 🟡 |
| 10k§1 | FP-08 | ADR-0040 | HR-06, INV-03 | 🟡 |
| T5-44→T5-59 | FP-01 | All RESOLVED | HR-03 / ADR-0051 | ✅ |
| T5-12 Pass 2 | Ext Dep | T5-12 | ADR-0050 | 🟡 |
| Temporal§1 | FP-07 | HD-09 | Phase 9 | 🟡 |
| Compliance§2 | GDPR | T5-08-B D9 | Art. 9 | 🟡 |
| Behavioral§1-5 | FP-09 | ADR-0038 | §6.2 | 🟡 |

---

## 11. Enforcement Layer Specification

This section defines mechanisms that make rule/invariant bypass **structurally impossible** — not merely detectable.

### 11.1 CI Hard-Fail Conditions

Every PR must pass these gates before merge. Failure = hard block (no override path except AGENTS.md §7 architect-only waiver with DEC-XXX record).

| Gate | Check | Tool | Failure Action |
|---|---|---|---|
| G-CI-01 | All tests pass (0 failures) | `pytest --strict-markers -x` | **BLOCK merge** |
| G-CI-02 | No naive `datetime.now()` in production code | AST lint rule (custom ruff plugin or `grep -rn "datetime.now()" titan/ --include="*.py" \| grep -v "tz=\|UTC"`) | **BLOCK merge** |
| G-CI-03 | No `INSERT OR REPLACE` on multi-source tables | Grep + allowlist | **BLOCK merge** |
| G-CI-04 | No `del athlete_id` in persistence paths | Grep | **BLOCK merge** |
| G-CI-05 | Every governance gate has NaN boundary test | Test-name convention check: `test_*_nan_*` exists per gate | **BLOCK merge** |
| G-CI-06 | No `.get("field", OPTIMAL_VALUE)` in governance | AST lint: flag `.get()` with numeric literal default in `governance_engine.py` | **BLOCK merge** |
| G-CI-07 | Athlete isolation invariant test passes | `test_athlete_isolation_invariant.py` | **BLOCK merge** |
| G-CI-08 | `ruff check .` clean (0 errors) | ruff | **BLOCK merge** |
| G-CI-09 | Architecture invariant tests pass | `test_architectural_invariants.py` | **BLOCK merge** |

### 11.2 Compile-Time Constraints (Typing / Schema)

| Constraint | Mechanism | Scope |
|---|---|---|
| Governance context contract | `DailyCoachContextContract(TypedDict)` with `mypy --strict` on governance boundary | `governance_engine.py`, `daily_coach.py` |
| Non-optional athlete_id | `athlete_id: str` (not `Optional[str]`) in all persistence method signatures | `database.py`, `persistence.py` |
| UTC-aware datetime type | `from datetime import datetime, timezone` + type alias `UTCDatetime = datetime` with mypy plugin or `Annotated[datetime, UTCAware]` | All production modules |
| Finite float wrapper | `FiniteFloat = Annotated[float, AfterValidator(math.isfinite)]` for governance inputs (Pydantic v2 or custom) | `governance_engine.py` gate parameters |

### 11.3 Runtime Kill-Switch Logic

| Kill-Switch | Trigger | Action | Recovery |
|---|---|---|---|
| KS-01: NaN governance reject | `math.isfinite()` returns False on any gate input | Abort gate evaluation → force EASY + max_zone 2 | Next cycle with clean data |
| KS-02: Athlete isolation violation | DB write without `athlete_id` in WHERE/INSERT | Raise `IntegrityError` → rollback transaction → do NOT persist | Fix calling code |
| KS-03: Stale data hard ceiling | `garmin_hours_since_success > GARMIN_DATA_MAX_AGE_HOURS (26)` | Force STARTUP_DATA_CONFIDENCE_CEILING | Successful Garmin sync |
| KS-04: Override lockdown | `override_rate_30d > OPERATOR_TRUST_OVERRIDE_LOCKDOWN_RATE (0.80)` | Disable override capability entirely | Manual architect review |
| KS-05: Persistence failure ceiling | Any `PersistenceFailure` exception | PERSISTENCE_DEGRADED_CEILING (EASY) + Telegram alert | DB connectivity restored + manual verification |

### 11.4 Rejection Before Persistence

**Principle:** Invalid data is rejected BEFORE it reaches the database — not detected after.

| Rejection Point | What Is Rejected | Where |
|---|---|---|
| Garmin ingestion | Physiologically impossible payloads: `max_hr < avg_hr`, `rhr > 200`, `hrv < 0`, future timestamps | `DataSanityChecker` (extend per HD-03) |
| Governance input | NaN/inf/None in required fields | Pre-decision sanity gate (§8) |
| DB write | Missing `athlete_id` on per-athlete tables | Schema constraint (`NOT NULL`) + runtime guard |
| Activity persistence | Duplicate `garmin_activity_id` | `UNIQUE INDEX` + `INSERT OR IGNORE` (T5-69) |
| Override recording | Override without reason text | API validation layer |

---

## 12. Execution Priority Model

### 12.1 Deterministic Precedence Hierarchy

When multiple mechanisms conflict, the HIGHER-numbered layer wins (higher = more restrictive):

```
LAYER 5 ─ HARD-STOP SAFETY GATES (H1–H5)
         │  Unconditional. Cannot be overridden by any lower layer.
         │  NaN kill-switch (KS-01) operates HERE.
         │
LAYER 4 ─ INVARIANT ENFORCEMENT (INV-01 → INV-10)
         │  Pre-decision sanity gate (§8). Operates BEFORE governance.
         │  Rejects structurally invalid input. Cannot be relaxed by
         │  governance engine or fallback mechanisms.
         │
LAYER 3 ─ GOVERNANCE ENGINE (gates, locks, APL)
         │  Evaluates readiness, applies priority vector and lock
         │  thresholds. Can downgrade but NEVER upgrade past Layer 4/5
         │  ceilings.
         │
LAYER 2 ─ FALLBACK MECHANISMS (degraded mode, defaults)
         │  Activated when Layer 3 cannot run cleanly.
         │  Fallbacks are ALWAYS conservative (ADR-0051).
         │  Fallbacks NEVER produce outcomes more permissive than
         │  Layer 3 would with complete data.
         │
LAYER 1 ─ NORMAL OPERATION (coaching output, session planning)
         │  Produces recommendations only if Layers 2–5 have not
         │  constrained the output.
```

### 12.2 Conflict Resolution Rules

| Conflict | Resolution |
|---|---|
| Invariant says REJECT + Governance says APPROVE | **Invariant wins.** Governance never overrides an invariant violation. |
| Sanity gate says LOW_CONFIDENCE + Hard-stop says CLEAR | **Sanity gate wins.** STARTUP_DATA_CONFIDENCE_CEILING applies regardless of hard-stop evaluation. |
| Fallback produces EASY + Governance computed QUALITY | **Fallback wins.** If fallback activated, governance computation is advisory only; fallback ceiling is the binding output. |
| Governance says EASY + APL override says MODERATE | **Governance wins.** APL can adjust priority but cannot relax a governance-applied lock or downgrade. |
| Two hard-stops conflict (one fires, one doesn't) | **Most restrictive wins.** If H2 fires REST and H3 fires EASY, output = REST. |

### 12.3 Layer Interaction Diagram

```
Input Data
    │
    ▼
┌─────────────────────────┐
│  LAYER 5: Hard-Stops    │◄── If ANY fires → IMMEDIATE output (REST/MEDICAL)
│  H1 H2 H3 H4 H5        │    No further layers consulted.
└────────┬────────────────┘
         │ (no hard-stop fired)
         ▼
┌─────────────────────────┐
│  LAYER 4: Invariants    │◄── Pre-decision sanity gate
│  INV-01 → INV-10        │    NaN → reject + conservative ceiling
│  CHECK 1-4              │    Missing data → confidence ceiling
└────────┬────────────────┘
         │ (all invariants pass)
         ▼
┌─────────────────────────┐
│  LAYER 3: Governance    │◄── Normal gate evaluation
│  V1 CS APL locks        │    Applies locks, downgrades
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  LAYER 2: Fallback      │◄── Only if persistence/data degraded
│  Conservative defaults   │    ALWAYS ≤ Layer 3 permissiveness
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  LAYER 1: Output        │◄── Final coaching decision
│  Session recommendation  │
└─────────────────────────┘
```

---

## 13. Source of Truth Model

### 13.1 Canonical Data Authority

| Data Domain | Source of Truth | Authority Level | Staleness Threshold |
|---|---|---|---|
| Biometric telemetry (HRV, RHR, sleep) | **Garmin API → SQLite DB** | Primary (after ingestion + sanity check) | 26 hours (`GARMIN_DATA_MAX_AGE_HOURS`) |
| Athlete profile (age, HRmax, VO2max, goals) | **athlete_profile.json → in-memory AthleteProfile** | Primary (file-based, manual-edit authoritative) | N/A (updated by athlete) |
| Governance decisions | **SQLite `governance_outcomes` table** | Primary (append-only audit trail) | N/A (immutable records) |
| Training history | **SQLite `training_log` table** | Primary | N/A (historical) |
| Daily metrics (readiness, composite scores) | **SQLite `daily_metrics` table** | Primary (after per-column UPSERT) | Current day only |
| Baseline calculations (HRV mean, RHR mean) | **In-memory engine state, hydrated from DB** | Derived (recomputable from DB) | Recomputed each cycle |
| APL (priority vector, lock thresholds) | **In-memory, injected by OutcomeTracker** | Derived (recomputable) | Per-cycle |
| Weather/environmental | **External API → in-memory cache** | External (untrusted until validated) | `WEATHER_DATA_MAX_AGE_HOURS` |
| Auth tokens / sessions | **In-memory AuthStore** ⚠️ | Fragile (HD-04: must migrate to DB) | Session duration |

### 13.2 Conflict Resolution Rules

| Conflict Type | Rule | Example |
|---|---|---|
| DB vs in-memory divergence | **DB wins.** In-memory state is rehydrated from DB at startup and each cycle. | Baseline in memory ≠ DB → rehydrate from DB |
| Fresh Garmin data vs stale DB | **Fresh wins** for current-day fields only. Historical DB records are never overwritten by Garmin re-sync (INSERT OR IGNORE). | Today's HRV from Garmin replaces today's DB row; yesterday's stays |
| Manual athlete input vs Garmin | **Manual wins.** Per-column UPSERT preserves manually-entered subjective fields (fatigue, mood, notes). Garmin only updates Garmin-sourced columns. | Athlete enters fatigue=8; Garmin sync does not touch fatigue column |
| Multiple Garmin syncs same day | **Latest-timestamp wins** for current day (UPSERT). Historical entries deduplicated by `garmin_activity_id` (INSERT OR IGNORE). | Two syncs: first has 2 activities, second has 3 → 3 unique activities persisted |
| External API unavailable | **Conservative default wins.** Weather unavailable → `ESI_DEW_POINT_FALLBACK_C=18.0`, but `data_confidence_low=True` flagged. | No weather → safe window defaults + warning |

### 13.3 Stale vs Fresh Data Handling

| Data Age | Classification | System Behavior |
|---|---|---|
| < 6 hours | **Fresh** | Full governance evaluation; no confidence penalty |
| 6–26 hours | **Aging** | `garmin_data_trust_level` reduced; governance proceeds with `data_age_hours` in context |
| > 26 hours | **Stale** | `GARMIN_DATA_STALE` CRITICAL event; `STARTUP_DATA_CONFIDENCE_CEILING` applied; session = EASY + max_zone 2 |
| No data ever synced | **Missing** | `NO_GARMIN_DATA` state; all biometric gates evaluate as UNKNOWN → conservative fail (ADR-0051) |

---

## 14. Automated System Response Model

### 14.1 Response Actions Defined

| Action | Definition | User-Visible Effect |
|---|---|---|
| **BLOCK** | Transaction rejected; data not persisted; operation aborted | Error message; no coaching output until resolved |
| **HARD-STOP** | Governance forces REST or MEDICAL_CLEARANCE | Session cancelled; explicit safety message via Telegram |
| **DEGRADE** | Coaching proceeds with conservative ceiling | Session = EASY + max_zone 2; degraded flag in output |
| **FALLBACK** | Primary path failed; secondary path activated with conservative parameters | Output produced but with uncertainty markers |
| **ESCALATE** | Alert sent to operator/architect; system continues with safest option | Telegram CRITICAL alert; structured event logged |
| **LOG-ONLY** | Observation recorded; no behavioral change | Structured event emitted; metric incremented |

### 14.2 Violation → Response Mapping

| Violation Type | Immediate Action | If Persists (>24h) | If Recurrent (>3 in 7 days) |
|---|---|---|---|
| NaN in governance input | **BLOCK** gate + **DEGRADE** to EASY | **ESCALATE** to architect | Flag data source for investigation |
| Naive datetime in pipeline | **LOG-ONLY** (convert best-effort) | **ESCALATE** | CI gate blocks future code |
| Athlete isolation breach | **BLOCK** write + rollback | N/A (immediate block) | N/A |
| Garmin sync failure | **FALLBACK** (stale data + age penalty) | **DEGRADE** (confidence ceiling) | **ESCALATE** + suggest 24h cooldown |
| Garmin data stale >26h | **DEGRADE** to EASY | **ESCALATE** | Auto-downgrade until fresh data |
| PersistenceFailure | **DEGRADE** + **ESCALATE** (Telegram) | **HARD-STOP** (cannot trust state) | Architect review required |
| Override rate >25% (30d) | **LOG-ONLY** + WARNING | **ESCALATE** warning | At 80%: **BLOCK** override capability |
| Override rate >80% (30d) | **BLOCK** overrides entirely | Lockdown until architect review | N/A |
| HRV baseline drift detected | **LOG-ONLY** + WARNING | **DEGRADE** (flag in governance) | **ESCALATE** + recalibration trigger |
| Rate-limiter ceiling hit | **FALLBACK** (evict oldest keys) | **LOG-ONLY** | Infrastructure scaling review |
| Auth state reset (restart) | **FALLBACK** (re-auth required) | N/A (one-time per restart) | **ESCALATE** if frequent restarts |
| Property test NaN gap detected | N/A (CI time) | **BLOCK merge** | N/A |
| Empty Garmin sync | **FALLBACK** (staleness timer NOT reset) | **DEGRADE** | **ESCALATE** |

### 14.3 Escalation Chain

```
Detection → Structured Event → Metric Update
                                    │
                          ┌─────────┴──────────┐
                          │                    │
                    WARNING level          CRITICAL level
                          │                    │
                    Log + metric         Telegram alert
                          │              to operator
                          │                    │
                    If persists >24h     If unresolved >48h
                          │                    │
                    ESCALATE to          HARD-STOP system
                    architect            until manual review
```

---

## 15. Ground Truth Feedback Loop

### 15.1 Divergence Detection (Model vs Reality)

| Prediction | Ground Truth Source | Divergence Signal | Detection Window |
|---|---|---|---|
| Readiness score (predicted capacity) | Post-session RPE (athlete-reported) | `|predicted_zone - actual_RPE_zone| > 1` | Same day (post-session) |
| Session type recommendation | Actual session completed (Garmin) | Recommended EASY but athlete did QUALITY (or vice versa) | 24h (next sync) |
| Governance lock (REST/EASY) | Athlete outcome next 48h | Lock applied → athlete reports worse state next day = FALSE NEGATIVE (should have locked harder). Lock applied → athlete recovers fully = TRUE POSITIVE. | 48h |
| HRV trend direction | 7-day actual HRV trajectory | Predicted stable but actual declining (or predicted decline but actual stable) | 7 days |
| Override quality | Post-override session outcome | Override → RPE ≥ 8 or injury flag next 7d = BAD OVERRIDE | 7 days |

### 15.2 Feedback Integration (OutcomeTracker Pipeline)

```
Session Recommendation
        │
        ▼
   Athlete Executes
        │
        ▼
   Garmin Data + RPE
        │
        ▼
┌───────────────────────┐
│  OutcomeTracker       │
│  ┌─────────────────┐  │
│  │ Compare:        │  │
│  │  predicted vs   │  │
│  │  actual outcome │  │
│  └────────┬────────┘  │
│           │           │
│  ┌────────▼────────┐  │
│  │ Classify:       │  │
│  │  TRUE_POS       │  │
│  │  TRUE_NEG       │  │
│  │  FALSE_POS      │  │
│  │  FALSE_NEG      │  │
│  └────────┬────────┘  │
│           │           │
│  ┌────────▼────────┐  │
│  │ Feed back:      │  │
│  │  APL adjustment │  │
│  │  priority_vector│  │
│  │  lock_thresholds│  │
│  └─────────────────┘  │
└───────────────────────┘
        │
        ▼
   Next Cycle (adjusted)
```

### 15.3 Anti-Contamination Rules

| Rule | Mechanism | Rationale |
|---|---|---|
| Independence window | Outcome evaluation delayed by `OUTCOME_INDEPENDENCE_WINDOW_HOURS` (default 6h) | Prevent immediate self-reinforcement |
| Override isolation | Overridden sessions excluded from model calibration for `OVERRIDE_EXCLUSION_WINDOW_DAYS` (default 7) | Override outcomes do not validate the override pattern |
| Baseline freeze during feedback | Feedback-triggered APL adjustments do not modify hard-stop constants (H1–H5) | Hard-stops remain physiologically grounded, not data-fitted |
| Closed-loop circuit breaker | If FALSE_NEGATIVE rate > 20% over 30 days → flag for manual recalibration | Prevent governance from adapting to systematic under-detection |

---

## 16. Recalibration / Drift Management System

### 16.1 Recalibration Triggers

| Trigger | Condition | Action | Authority |
|---|---|---|---|
| **Scheduled** | Every 12 weeks (system half-life boundary) | Full threshold review against OutcomeTracker history | Architect |
| **Drift-detected** | INV-06 fires: `|hrv_baseline_delta_14d| > HRV_DRIFT_THRESHOLD_MS (8.0)` | Flag athlete for individual review; apply conservative bias until resolved | Automatic + architect review |
| **Population mismatch** | OutcomeTracker FALSE_POS rate > 30% (governance too conservative) OR FALSE_NEG rate > 15% (governance too permissive) over 30 days | Recalibrate priority_vector + lock_thresholds via APL | Architect (ADR required for threshold constant changes) |
| **Device/firmware change** | Garmin mean HRV shifts >10% without corresponding training load change over 14 days | Flag sensor drift; freeze baselines for 14-day recalibration window | Automatic detection + architect confirmation |
| **Athlete phase transition** | New training block, illness recovery, return from break (>14 days no data) | Reset rolling baselines from scratch (discard pre-transition data) | Automatic on data gap detection |
| **Season boundary** | Calendar-triggered (configurable; default every 16 weeks) | Review all static thresholds against accumulated outcome data | Architect |

### 16.2 Baseline Reset Protocol

```
BASELINE RESET PROTOCOL
════════════════════════

WHEN triggered (any §16.1 trigger):

1. FREEZE current baselines
   - Mark current HRV/RHR baselines as FROZEN in governance context
   - Governance uses FROZEN baselines + conservative bias (+10% stricter thresholds)

2. ACCUMULATE new data
   - Minimum 7 days of fresh biometric data required
   - Data must pass sanity checks (no NaN, no stale, no gaps >48h)

3. RECALCULATE baselines
   - HRV: sample mean ± sample SD (N-1) over accumulation window
   - RHR: sample mean over accumulation window
   - ACWR: requires 28-day chronic load history (cannot reset mid-block)

4. VALIDATE against outcomes
   - Compare new baselines with OutcomeTracker predictions
   - If FALSE_NEG rate > 10% in first 7 days → tighten by 5%
   - If FALSE_POS rate > 40% in first 7 days → loosen by 5% (max one step)

5. ACTIVATE new baselines
   - Emit structured event: baseline_recalibrated
   - Record old + new values in governance_outcomes for audit trail
   - Remove FROZEN flag
```

### 16.3 Threshold Update Governance

| Change Type | Process | Authority |
|---|---|---|
| Hard-stop constants (H1–H5) | ADR required; evidence-based justification; architect approval | Architect only |
| APL priority_vector adjustments | OutcomeTracker automatic within bounds; architect review if cumulative shift > 20% | Automatic + architect |
| Readiness scoring weights | ADR required; evidence from ≥30 days outcome data | Architect only |
| Gate activation thresholds | OutcomeTracker-recommended; architect approval for activation | Architect |
| Evidence registry confidence levels | Science review cycle; ADR if downgrade from STRONG to MODERATE | Architect |

---

## 17. Severity → Runtime Behavior Mapping

### 17.1 Severity Definitions

| Severity | Definition | System Half-Life Impact | Example |
|---|---|---|---|
| **CRITICAL** | Immediate safety risk; incorrect coaching decision possible NOW | Minutes | NaN bypass in governance; cross-athlete data collision |
| **HIGH** | Safety or data integrity risk under realistic conditions within days | Days | Rolling baseline poisoning; in-memory auth restart fragility |
| **MEDIUM** | Correctness risk under specific conditions; degraded quality | Weeks | DegradedModeTracker reset; date truncation at midnight |
| **LOW** | Observable anomaly; no immediate risk; quality could improve | Months | Static threshold staleness; property test NaN exclusion |

### 17.2 Severity → Enforcement Behavior

| Severity | Runtime Detection | Immediate System Response | CI/Merge Behavior | Observability |
|---|---|---|---|---|
| **CRITICAL** | Invariant check (Layer 4/5) | **BLOCK or HARD-STOP**: reject input, abort operation, force REST/EASY, send Telegram CRITICAL alert | **Hard-fail CI gate**: PR cannot merge if CRITICAL violation test fails | CRITICAL structured event + immediate metric spike alert |
| **HIGH** | Pre-decision sanity gate | **DEGRADE**: apply conservative ceiling (EASY + max_zone 2); pipeline continues in degraded mode; **ESCALATE** via Telegram WARNING | **Hard-fail CI gate**: PR blocked | WARNING structured event + 24h escalation timer |
| **MEDIUM** | Runtime detection in pipeline | **FALLBACK**: activate secondary path with conservative parameters; no hard ceiling unless data confidence drops below threshold | **Soft-fail CI gate**: warning in PR, merge allowed with architect ack | WARNING event + metric tracking |
| **LOW** | Periodic audit / OutcomeTracker | **LOG-ONLY**: emit structured event; increment metric; no behavioral change | **No CI gate**: tracked in TECHNICAL_DEBT.md | INFO event + dashboard metric |

### 17.3 Current Open Items — Severity-to-Response Applied

| Item | Severity | Current Response | Required Response (per §17.2) | Gap |
|---|---|---|---|---|
| HD-03 NaN bypass | CRITICAL | None (undetected) | **BLOCK** + CRITICAL event | 🔴 No `math.isfinite()` guard exists |
| HD-01 Baseline poisoning | HIGH | None (undetected) | **DEGRADE** + WARNING + 24h escalation | 🔴 No drift detector exists |
| HD-02 Mixed datetime | HIGH | None (silently continues) | **DEGRADE** + WARNING | 🔴 No UTC enforcement |
| HD-04 In-memory auth | HIGH | Restart = mass 401 | **FALLBACK** (re-auth) + **ESCALATE** | 🟡 Fallback exists; persistence missing |
| HD-05 Unbounded limiter | HIGH | Memory grows unbounded | **FALLBACK** (eviction) | 🔴 No eviction mechanism |
| T5-67 False success events | MEDIUM | Wrong metrics | **FALLBACK** (event outside guard) | 🟡 Detection possible; fix pending |
| HD-06 Degraded tracker reset | MEDIUM | Timer resets silently | **FALLBACK** (persist to DB) | 🔴 No persistence |
| HD-07 Date truncation | MEDIUM | Wrong day-bucket | **FALLBACK** + WARNING | 🔴 No full ISO preservation |
| HD-08 Frankenstein state | MEDIUM | Mixed computation | **FALLBACK** (confidence ceiling) | 🟡 Partial (ceiling exists; mixed state not fully prevented) |
| HD-09 Static thresholds | LOW | No adaptation | **LOG-ONLY** + periodic recalibration | 🟡 OutcomeTracker infrastructure exists; not active |

---

## Appendix B: Cross-Reference — Extensions to Core Sections

| Extension (§11–§17) | Core Section Reference | Relationship |
|---|---|---|
| §11 Enforcement Layer | §6 Governance Upgrades, §7 Invariants | §11 defines HOW §6/§7 are enforced at CI + runtime |
| §12 Priority Model | §8 Sanity Gate, §7 Invariants | §12 defines WHICH layer wins on conflict |
| §13 Source of Truth | §1 Debt Register (HD-04), §6.4 State Rules | §13 defines WHERE data authority lives |
| §14 Response Model | §9 Failure Simulation, §10 Observability | §14 defines WHAT the system DOES on detection |
| §15 Feedback Loop | §9 (BE-01/02/03), §10 (divergence metrics) | §15 defines HOW the system LEARNS from outcomes |
| §16 Recalibration | FP-07 Baseline Poisoning, HD-01, HD-09 | §16 defines WHEN and HOW thresholds update |
| §17 Severity Mapping | §1 Debt Register (all items), §14 Response | §17 defines severity→behavior deterministic link |
