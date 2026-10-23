# ADR-0055 — Garmin Fallback Adapter Interface

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-05-09 |
| Refs | ADR-0016 (multi-sport), ADR-0041 (DataTrustLevel), ADR-0050 (Garmin fragility), T5-100, T5-12 |

## Context

Garmin is a single point of failure for all biometric data. When Garmin authentication
breaks, or data is stale beyond 48 hours, the system has no alternative data source for
HRV, RHR, sleep, and weight. T5-12 Pass 2 delivered observability (O1–O7) for detecting
staleness. T5-100 (D4) delivers the source-switching layer.

## Decision

Introduce a `BiometricSourceAdapter` protocol that Garmin and ManualEntry both implement.
A `BiometricRouter` arbitrates between them at read time based on Garmin data age.

**Source arbitration rules:**
1. Garmin is preferred when `data_age_hours < 48`
2. `ManualEntryAdapter` is used when Garmin data is unavailable or stale (≥ 48h)
3. `DataTrustLevel` degradation follows ADR-0041 (unchanged — governed by `evaluate_garmin_trust`)

**Interface:**

```python
class BiometricSourceAdapter(Protocol):
    def get_hrv(self, date: str) -> float | None: ...
    def get_rhr(self, date: str) -> float | None: ...
    def get_sleep_hours(self, date: str) -> float | None: ...
    def get_weight_kg(self, date: str) -> float | None: ...
    def source_name(self) -> str: ...
    def data_age_hours(self) -> float: ...
```

**ManualEntryAdapter** reads from `daily_metrics WHERE data_source = 'manual_entry'`
(the `data_source` column was introduced in T5-115; the `manual_entry` value is set by
the `/manual_entry` Telegram command, T5-116).

**BiometricRouter** is constructed with the Garmin `data_age_hours` scalar and a
`ManualEntryAdapter` instance. DailyCoach uses the router to route HRV and RHR reads
after `garmin_trust` is evaluated.

## Consequences

- New module: `titan/integrations/biometric_router.py`
  - `BiometricSourceAdapter` (Protocol, runtime-checkable)
  - `ManualEntryAdapter` (reads `daily_metrics WHERE data_source='manual_entry'`)
  - `BiometricRouter` (arbitration + structured warning on source switch)
- `DatabaseManager.get_daily_metric(date, athlete_id)` added to `titan/core/database.py`
  to support `ManualEntryAdapter` reads
- `DailyCoach.run()` wires `BiometricRouter` after `garmin_trust` is computed; routes
  `today_hrv` and `today_rhr` through the router; annotates `context_payload` with
  `biometric_source` and `biometric_fallback_active`
- Governance gate logic (H1–H5) is **not changed** — the router only affects data
  delivery, not gate evaluation
- `GarminSync` sync thread is **not changed** — sync still uses GarminSync directly

## Addendum (2026-10-23, ADR-0070): what the code does

- `DailyCoach` builds the `BiometricRouter` and calls `get_hrv` and `get_rhr`, but it does not use the
  values they return. `today_hrv` and `today_rhr` still come from the Garmin data
  (`titan/orchestration/daily_coach.py`, the block that sets `biometric_source`).
- The router therefore only fills `biometric_source` and `biometric_fallback_active` in the context.
  A manual HRV or RHR does not reach H2 or H3 through the router.
- Wiring the values in is open as P4-10 in `TECHNICAL_DEBT.md`. It changes what H2 and H3 see, so it
  needs its own decision (ADR-0009).
