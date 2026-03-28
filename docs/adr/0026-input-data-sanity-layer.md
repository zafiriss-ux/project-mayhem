# ADR-0026 — Input Data Sanity Layer

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Master Risk Matrix — Risk #10 (Input Data Sanity / Garbage In)
**Phase:** 7.8 Hardening

---

## Context

Risk #10 is classified as **Medium probability, High severity** and ranked #5 in the
top-5. It is the "silent degrader": data quality problems do not produce errors; they
produce subtly wrong coaching decisions.

### Relationship to ADR-0023

ADR-0023 (Physiological Input Validation Contract) addresses the *physiological bounds*
problem: values that are outside the plausible physical range for a human body (e.g.,
HRV = 0, RHR = 200).

ADR-0026 addresses a broader class of data sanity failures that ADR-0023 does not cover:

1. **Structural data corruption** — e.g., a Garmin activity row where `distance_km = 0`
   but `duration_seconds = 3600` (an hour with no movement). The value is physiologically
   plausible (HRV = 60ms is valid) but contextually impossible (a 1-hour activity with
   no distance cannot be a run).

2. **Temporal anomalies** — e.g., an activity timestamped in the future (Garmin timezone
   bug), or two activities with the same timestamp and overlapping durations.

3. **Cross-field inconsistencies** — e.g., `max_hr < avg_hr`, `distance_km > 0` but
   `duration_seconds = 0`, `elevation_gain_m < 0`.

4. **Stale data used as current** — e.g., the last Garmin sync was 72 hours ago and
   the system uses yesterday's HRV as today's. ADR-0023 cannot detect this because the
   value is physiologically valid; the problem is temporal.

5. **Missing mandatory fields** — e.g., a `daily_metrics` row where `date` is NULL.
   SQLite does not enforce NOT NULL on all columns by default.

### Current State

`garmin_sync.py` performs no structural or cross-field validation before writing to
the database. `DatabaseManager` performs no validation before returning records.
ADR-0023 adds physiological bounds validation at the read path. ADR-0026 defines
the broader structural validation layer.

---

## Decision

**Introduce a `DataSanityChecker` at the Garmin sync → database write boundary,
and a temporal freshness check at the database → DailyCoach hydration boundary.**

### Layer 1 — Write-Time Structural Validation (Garmin sync boundary)

A `DataSanityChecker` module validates each record before it is written to the database:

```python
# titan/science/data_sanity.py

@dataclass
class SanityViolation:
    record_type: str   # "activity" | "daily_metrics" | "hrv"
    field: str
    rule: str          # human-readable rule name
    value: Any
    severity: str      # "reject" | "warn"

class DataSanityChecker:
    def check_activity(self, row: dict) -> list[SanityViolation]: ...
    def check_daily_metrics(self, row: dict) -> list[SanityViolation]: ...
    def check_hrv(self, row: dict) -> list[SanityViolation]: ...
```

**Rules (reject-on-violation):**

| Record | Rule | Action |
|---|---|---|
| activity | `max_hr < avg_hr` | reject |
| activity | `distance_km > 0 and duration_seconds == 0` | reject |
| activity | `timestamp` in future (> now + 1h clock drift margin) | reject |
| activity | duplicate `(garmin_id, timestamp)` pair | reject (already handled by T1-14 idempotency key; sanity check is defence-in-depth) |
| daily_metrics | `date` is NULL | reject |
| daily_metrics | `rhr_bpm` present but `hrv_ms` absent AND the previous 7 days all had `hrv_ms` → suspect sensor | warn |
| hrv | `hrv_ms` = 0 exactly | reject (not warn — physiologically impossible) |

**Violations of severity `"reject"` cause the record to be skipped (not written). A
structured `data_sanity_reject` event is emitted.**

**Violations of severity `"warn"` cause the record to be written with a `quality_flag`
column set to `"degraded"`. A structured `data_sanity_warn` event is emitted.**

### Layer 2 — Temporal Freshness Check (DailyCoach hydration boundary)

At DailyCoach startup (Step 1 — engine hydration), add a freshness check:

```python
last_sync_ts = db.get_last_garmin_sync_timestamp()
hours_since_sync = (now - last_sync_ts).total_seconds() / 3600

if hours_since_sync > STALE_DATA_WARN_HOURS:       # 24h — warn
    log_structured("data_freshness_warn", hours=hours_since_sync)
if hours_since_sync > STALE_DATA_HARD_CEILING_HOURS:  # 72h — governance advisory
    # Emit data_confidence_low advisory (reuses existing T2-10 mechanism)
    set_data_confidence_low(reason="stale_garmin_data", hours=hours_since_sync)
```

**Constants** added to `thresholds.py` with evidence registry entries.

### Layer 3 — Schema NOT NULL Enforcement

Audit all SQLite `CREATE TABLE` statements in `DatabaseManager._run_migrations()` to
add `NOT NULL` constraints on mandatory fields (`date`, `garmin_id`, `timestamp`).
A migration adds the constraints to the existing schema. This prevents NULL values from
being written silently.

**This is a non-breaking migration if existing data is clean. If existing data contains
NULLs in mandatory columns, the migration must run a cleanup pass first.**

### Engineering Execution Item

**T1-18 note:** T1-18 (from ADR-0023) covers the physiological bounds validation.
ADR-0026 generates a *sibling* item:

**T1-19** (new Tier 1 item):
> Create `titan/science/data_sanity.py` (Layer 1).
> Integrate into `garmin_sync.py` before each DB write method.
> Add temporal freshness check to `DailyCoach` Step 1 (Layer 2).
> Add NOT NULL migration for mandatory columns (Layer 3).
> Add `tests/test_data_sanity.py` (structural + temporal + cross-field rules).

**Execution order:** T1-19 must execute after T1-18 (both Tier 1). T1-18 owns the
`physiological_bounds.py` module; T1-19 owns `data_sanity.py`. The two modules are
complementary and have no circular dependency.

---

## Options Considered

### Option A — Validate in Garmin sync only
Validate before writing; trust the database to be clean.

**Partially accepted** as Layer 1. However, existing data in the database may already
contain structural anomalies (the system has been running without validation). Layer 2
(freshness) and Layer 3 (NOT NULL constraints) are required to handle the historical
data problem.

### Option B — External data quality job (daily cron)
A separate process runs nightly and marks suspect rows in the database.

**Rejected.** Adds operational complexity (another background job). The defects are
detectable at write time; delaying detection to a batch job increases the window in
which corrupt data influences coaching decisions.

### Option C — Write-time + hydration-time + schema constraints (SELECTED)
Three layers, each catching a different class of defect. Defence in depth without
architectural complexity. Consistent with the existing pipeline structure.

---

## Consequences

**Positive:**
- Cross-field anomalies are caught before they enter the database.
- Stale data is explicitly flagged rather than silently used as current.
- NOT NULL constraints prevent a class of schema bugs from being introduced in migrations.

**Neutral:**
- Some legitimate edge cases (zero-distance indoor workouts, e.g., pool running on a
  treadmill) may trigger `warn`-level violations. The `quality_flag` column allows the
  operator console to surface these for manual review without blocking coaching output.

**Negative:**
- Layer 3 (NOT NULL migration) requires testing against existing DB content. If any
  existing row has NULL in a mandatory column, the migration must handle it (backfill
  or log-and-skip). This is a non-trivial migration step.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0023 | Physiological bounds validation — ADR-0023 handles the physiological range problem; this ADR handles structural and temporal sanity. The two modules (`physiological_bounds.py` and `data_sanity.py`) sit at different points in the pipeline. |
| ADR-0020 | Persistence failure policy — Layer 3 NOT NULL constraints are a prerequisite for the persistence failure policy to work correctly (you cannot enforce degraded-conservative mode if the schema allows silent NULLs). |
| ADR-0015 | SQLite retention — Layer 3 migration must be consistent with the additive-migration policy established in T1-16. |

---

## Status

Accepted. Engineering execution: **T1-19** (Tier 1 — data integrity; executes after
T1-18 in Phase 7.9+ sprint).

---

## Implementation Notes

**OBS-036 / T5-69 (pending):** `sync_activities()` does not extract Garmin's `activityId`
field, and `training_log` has no `activity_id` column. Overlapping sync windows (6h background
sync + manual /sync) can insert duplicate activity rows into `training_log`, silently inflating
CTL/ATL/TSB. This is the same structural gap that T1-19 / T5-46 closed for HRV entries
(INSERT OR IGNORE per date), but activities require activity-ID deduplication rather than
per-date deduplication (double-day training is valid). Fix registered as T5-69.
The schema migration must follow the additive-migration policy (ADR-0015).
