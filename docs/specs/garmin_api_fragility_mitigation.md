# T5-12 Pass 1 — Garmin API Fragility Mitigation Design

## 1) Structured event definition: `garmin_api_degraded`

### Trigger conditions
Emit `garmin_api_degraded` when at least one condition is true:
1. Garmin authentication flow fails (`connect()` failure class resolves to `GARMIN_AUTH_FAIL`).
2. `sync_all()` exits via timeout cancellation (`status="timeout_cancelled"`).
3. Consecutive Garmin provider failures cross configured degradation threshold.
4. Garmin trust evaluation resolves to `DataTrustLevel.INVALID`.

### Severity
- `CRITICAL` (non-bypassable operator signal).

### Required payload fields
- `component`: fixed value `"garmin_sync"`
- `action`: fixed value `"garmin_api_degraded"`
- `severity`: fixed value `"CRITICAL"`
- `failure_class`: canonical Garmin failure class
- `sync_status`: `connect_failed` | `timeout_cancelled` | `sync_failed`
- `error_class`: source exception class name
- `error_message`: sanitized error detail for operator visibility
- `last_successful_sync_at`: ISO-8601 timestamp or `null`
- `data_age_hours`: numeric
- `trust_level`: Garmin trust state (`TRUSTED` | `SUSPECT` | `INVALID`)
- `reasons`: normalized reason codes list
- `degraded_mode_expected`: boolean
- `emitted_at`: ISO-8601 timestamp

---

## 2) Coach dashboard indicator specification

### What the coach must see on Garmin sync failure
The dashboard must show an explicit degraded-state badge and text indicator tied to the latest Garmin degradation event.

### Staleness / last-data-age display
The indicator must always display the latest known valid Garmin data age in hours (`N h`) when available, derived from `last_successful_sync_at`.

### Wording states (aligned with ADR-0050)
1. `Garmin sync degraded — last valid data: <N>h ago.`
2. `Garmin sync degraded — no valid Garmin baseline available.`
3. `Garmin data stale — operating with caution.`

---

## 3) `garminconnect` pinning strategy

### Version pinning policy
- Pin `garminconnect` to an exact tested version in `requirements.txt`.
- No floating specifiers (`>=`, `~=`) for this dependency.
- Upgrades run only through explicit review and controlled validation (not opportunistic bumping).

### CI breakage detection approach
- Add CI check that fails on unreviewed `garminconnect` version drift from the pinned value.
- Add scheduled dependency health verification for the pinned version (import + smoke auth-path contract test in CI scope).
- On breakage signal: keep current pin, raise degradation event path, and open explicit upgrade task; no auto-upgrade behavior.

---

## 4) Multi-device fallback interface sketch (Polar / Whoop / COROS)

### Alignment constraints
- ADR-0016: fallback must use one unified adapter boundary before any provider-specific ingestion expansion.
- ADR-0041: every provider output must include trust semantics compatible with `DataTrustLevel` / `DataTrustReport`.

### Interface sketch
```python
@dataclass
class SourceCapabilities:
    source_name: str
    supports_hrv: bool
    supports_resting_hr: bool
    supports_sleep: bool
    supports_activity_load: bool

@dataclass
class NormalizedBiometricSample:
    source_name: str
    sampled_at: str
    hrv_rmssd: float | None
    resting_hr: int | None
    sleep_hours: float | None
    provenance: str

@dataclass
class BiometricSourceSyncResult:
    samples: list[NormalizedBiometricSample]
    sync_status: str
    failure_class: str | None
    data_trust_report: dict
```

### Pass 1 boundary note
This is an interface-only sketch. No fallback provider implementation, source switching logic, or arbitration policy is included in Pass 1.
