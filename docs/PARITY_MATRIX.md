# TITAN OS — SQLite / PostgreSQL Backend Parity Matrix

**Canonical artifact for:** T5-25 (Database Manager SQLite/PostgreSQL interface parity matrix)
**Status:** Accepted — 2026-03-15
**Owner:** Architect
**Prerequisite for:** T5-08-B D7 and D9 closure (both deliverables may not be declared DONE
without this document existing and being accepted)

---

## §1 Scope of Comparison

This document specifies which methods and behaviours of the `PersistenceAdapter` ABC
(`titan/core/persistence.py`) must be **identical** across the two concrete backends
(`SQLiteAdapter` and `PostgreSQLAdapter`), and what backend-specific divergence (if any)
is **explicitly permitted**.

**In scope:**
- All 32 abstract methods declared in `PersistenceAdapter` (as of 2026-03-15)
- Return type contracts (shape, not performance)
- Error / None semantics
- Ordering guarantees (newest-first where documented)
- Context-manager semantics for `transaction()`

**Out of scope (see §5):** SQL dialect, query plan, connection pooling, migration tooling,
backup mechanism, performance characteristics.

**Reference implementations:**
- `titan/core/persistence.py` — `PersistenceAdapter`, `SQLiteAdapter`, `PostgreSQLAdapter`
- `titan/core/database.py` — underlying `DatabaseManager` (SQLite) and `PostgreSQLDatabaseManager`

---

## §2 Classification Model (Legend)

| Code | Meaning |
|------|---------|
| **MUST_MATCH** | Return type, ordering, None-vs-value semantics, and error conditions must be identical across both backends. Any divergence is a contract violation. |
| **PERMITTED_DIVERGENCE** | Backend-specific behaviour is explicitly allowed. The permitted deviation and its rationale are documented in the Notes column. A PERMITTED_DIVERGENCE that is a temporary stub (pending a future deliverable) must be upgraded to MUST_MATCH when that deliverable closes, or the divergence must be explicitly re-confirmed as permanent at that time. |

---

## §3 Parity Matrix Table

Methods are grouped by functional area, matching the section headers in `persistence.py`.

### 3.1 Daily Metrics

| Method | Classification | Notes |
|--------|---------------|-------|
| `save_daily_metric` | **MUST_MATCH** | INSERT OR REPLACE semantics; all keyword arguments accepted and persisted identically. Governance pipeline reads this data at DailyCoach startup. |
| `get_baseline_rhr` | **MUST_MATCH** | Rolling median over last *days* days; None if no data. Used in governance gate H3 (RHR delta). |
| `get_hrv_history` | **MUST_MATCH** | `list[tuple[str, float]]`; ordered newest-first; empty list if no data. Used in governance gate H2 (HRV delta) and AFI computation. |
| `get_weight_history` | **MUST_MATCH** | `list[tuple[str, float]]`; ordered newest-first; empty list if no data. Consumed by NutritionOptimizer. |

### 3.2 Training Sessions

| Method | Classification | Notes |
|--------|---------------|-------|
| `save_session` | **MUST_MATCH** | INSERT OR IGNORE on duplicate (same date + session_type). Source of training load for CTL/ATL/ACWR reconstruction. |
| `get_training_load_history` | **MUST_MATCH** | `list[tuple[str, float]]`; ordered newest-first; critical path — CTL/ATL/ACWR reconstruction and all load-based governance gates depend on this return value being identical. |
| `get_ctl_atl_tsb` | **MUST_MATCH** | `tuple[float, float, float]` → `(CTL, ATL, TSB)`; Banister/Coggan exponential-decay model. Governance gate H4 (TSB floor) depends on this value. |

### 3.3 Gear

| Method | Classification | Notes |
|--------|---------------|-------|
| `add_shoe` | **MUST_MATCH** | Returns generated integer `id`. |
| `get_active_shoes` | **MUST_MATCH** | `list[tuple]`; returns `(id, name, type, total_km, max_km, status, …)` tuples for `status='ACTIVE'` rows. |
| `check_shoe_availability` | **MUST_MATCH** | `tuple[bool, str]` → `(available, reason_string)`; reason strings `shoe_not_found`, `shoe_inactive`, `shoe_retired`, `available` must be identical. |
| `update_shoe_mileage` | **MUST_MATCH** | Additive update (not set); `total_km += distance_km`. |

### 3.4 Personal Bests

| Method | Classification | Notes |
|--------|---------------|-------|
| `save_personal_best` | **MUST_MATCH** | Persists a PR row; does not enforce uniqueness on distance (historical records permitted). |
| `get_pr` | **MUST_MATCH** | `tuple[int, str, str | None] | None` → `(time_seconds, date, race_name)`; returns best (lowest time) for exact distance match; None if no record. |

### 3.5 Heart-Rate Recovery

| Method | Classification | Notes |
|--------|---------------|-------|
| `save_hrr` | **PERMITTED_DIVERGENCE** | SQLite: stores in dedicated `hrr_60`/`hrr_120` columns in `daily_metrics`. PostgreSQL: stores as `notes` field text `HRR60=X;HRR120=Y`. Permitted until D7 closes; must be upgraded to MUST_MATCH at D7 closure or explicitly re-confirmed as permanent. |
| `get_hrr_history` | **PERMITTED_DIVERGENCE** | PostgreSQL currently returns `[]` (empty list). SQLite returns `list[tuple[str, int, int]]` newest-first. Permitted until D7 closes; upgrade or confirm required at D7 closure. |

### 3.6 Glycogen / Critical Speed

| Method | Classification | Notes |
|--------|---------------|-------|
| `update_glycogen_debt` | **MUST_MATCH** | Writes debt score to `governance_outcomes` table by date; update semantics. |
| `log_cs_performance` | **PERMITTED_DIVERGENCE** | PostgreSQL is a no-op (no dedicated CS table). SQLite persists to `training_log` extension. Permitted until D7 closes; upgrade or confirm required at D7 closure. |
| `get_cs_performances` | **PERMITTED_DIVERGENCE** | PostgreSQL returns `[]`. Permitted until D7 closes; upgrade or confirm required at D7 closure. |

### 3.7 Override Log

| Method | Classification | Notes |
|--------|---------------|-------|
| `log_override` | **MUST_MATCH** | ADR-0042 human override invariant requires override records to be retrievable identically from either backend. |
| `record_override_signal` | **MUST_MATCH** | Raw signal record for ratio tracking; same contract as `log_override`. |
| `get_override_ratio` | **MUST_MATCH** | `float` in `[0.0, 1.0]`; fraction of sessions with overrides in last *days* days; 0.0 if no data. |
| `get_override_log` | **MUST_MATCH** | `list[dict[str, str]]`; each dict has keys `date`, `actual_type`, `reason`; ordered newest-first. |

### 3.8 Governance Outcomes

| Method | Classification | Notes |
|--------|---------------|-------|
| `save_governance_decision` | **MUST_MATCH** | OutcomeTracker integrity (ADR-0035 §16.7); calibration data correctness depends on identical persistence across backends. |
| `update_governance_outcome` | **MUST_MATCH** | Updates post-session outcome fields by date; must accept identical dict schema. |
| `get_governance_decisions` | **MUST_MATCH** | `list[dict[str, Any]]`; ordered newest-first; dict key set must be identical (see `PostgreSQLAdapter.get_governance_decisions` for canonical key list). |
| `annotate_governance_outcome` | **MUST_MATCH** | Appends annotation; returns `True` on success, `False` if row not found; append semantics (newline-separated) must match. |

### 3.9 Sync Tracking

| Method | Classification | Notes |
|--------|---------------|-------|
| `record_sync_outcome` | **PERMITTED_DIVERGENCE** | PostgreSQL is a no-op. Permitted until D7 closes; upgrade or confirm required at D7 closure. |
| `get_last_sync_outcome` | **PERMITTED_DIVERGENCE** | PostgreSQL returns `None`. Permitted until D7 closes; upgrade or confirm required at D7 closure. |
| `get_last_garmin_sync_timestamp` | **PERMITTED_DIVERGENCE** | PostgreSQL returns `None`. Permitted until D7 closes; upgrade or confirm required at D7 closure. |

### 3.10 Backup / Lifecycle

| Method | Classification | Notes |
|--------|---------------|-------|
| `backup_database` | **PERMITTED_DIVERGENCE** | SQLite: file-copy strategy (T1-17 pattern). PostgreSQL: `pg_dump` strategy (D7 scope). PostgreSQL currently raises `NotImplementedError("D7 pg_dump backup strategy is not part of D2b")`; this is the documented pre-D7 state. |
| `transaction` | **MUST_MATCH** | Must return a context manager that wraps multiple writes in a single atomic unit. SQLite: `threading.Lock`-based context. PostgreSQL: `engine.begin()` context. External semantics (atomicity, rollback on exception) must be identical. |
| `close` | **MUST_MATCH** | Releases all backend resources; must be idempotent (calling twice must not raise). |

---

## §4 Closure Rule for T5-08-B D7 and D9

**Rule: Neither D7 nor D9 may be declared DONE until this document exists and is accepted.**
This document was created as part of T5-25 (2026-03-15). The rule is now satisfied.

### D7 closure requirements (pg_dump backup strategy)

When D7 closes, the following PERMITTED_DIVERGENCE entries in §3 must be upgraded to
**MUST_MATCH** or explicitly re-confirmed as permanent permitted divergence in a new revision
of this document:

| § | Method(s) |
|---|-----------|
| 3.5 | `save_hrr`, `get_hrr_history` |
| 3.6 | `log_cs_performance`, `get_cs_performances` |
| 3.9 | `record_sync_outcome`, `get_last_sync_outcome`, `get_last_garmin_sync_timestamp` |
| 3.10 | `backup_database` — must no longer raise `NotImplementedError`; must return a valid backup path |

**D7 parity gate (binary):** The architect must review this matrix at D7 closure and either
(a) upgrade each row to MUST_MATCH with passing tests, or (b) re-confirm permanent divergence
with documented rationale. D7 is not DONE until the matrix reflects the post-D7 state.

### D9 closure requirements (consent_log table)

D9 adds a `consent_log` table. When D9 closes:

1. New `PersistenceAdapter` abstract methods covering `consent_log` must be added
   (at minimum: `save_consent_record`, `get_consent_status`).
2. Those methods must be classified as **MUST_MATCH** immediately (no new PERMITTED_DIVERGENCE
   for newly created tables — backends must be in parity at the time of addition).
3. This matrix must be revised to include the new methods in a new §3.11 section.

**D9 parity gate (binary):** This matrix must be updated before D9 is declared DONE.

---

## §5 Non-Goals

This document is **not**:

- A test specification. Backend parity tests live in `tests/titan/core/test_persistence.py`
  and `tests/titan/core/test_database.py`.
- A migration guide. See ADR-0044 and T5-08-B deliverable checklist.
- A performance comparison. Query latency and throughput are not governed by this matrix.
- A feature flag specification. The `TITAN_DB_BACKEND` env-var switch is documented in T5-08 (D6).
- A schema topology document. Table definitions and Alembic migrations are in `alembic/`.

---

## §6 Revision Log

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-03-15 | Architect | Initial creation — T5-25 closure; 32 methods classified across 10 areas; D7/D9 closure gates defined |
