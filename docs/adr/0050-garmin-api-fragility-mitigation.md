# ADR-0050 — Garmin API Fragility Mitigation

**Date:** 2026-03-17
**Status:** Accepted
**Type:** Integration Resilience
**Scope:** T5-12 Pass 2 implementation gate
**Related:** ADR-0016 (unified adapter gate), ADR-0041 (DataTrustLevel contract), T5-12

---

## Context

TITAN OS depends on `garminconnect`, an unofficial reverse-engineered Python library that
scrapes Garmin Connect's web authentication flow. This library has broken at least twice in
the past three years when Garmin changed its authentication mechanism.

T5-12 Pass 1 (2026-03-17) produced a mitigation design document
(`titan/integrations/T5-12-pass1-mitigation-design.md`) covering four areas:

1. Structured Garmin-degraded event definition
2. Coach dashboard indicator specification
3. `garminconnect` library pinning strategy
4. Multi-device fallback interface sketch

This ADR formalizes the decisions from that design document and unblocks T5-12 Pass 2
implementation.

---

## Decisions

### D1 — Structured `garmin_api_degraded` event

A new structured event `garmin_api_degraded` is emitted at **CRITICAL** severity when any
of the following conditions hold:

1. Authentication failure (`GARMIN_AUTH_FAIL`) during `connect()` or any sync operation
2. `sync_all()` exits with `status="timeout_cancelled"`
3. Repeated provider failures exceed `GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT` (new
   constant in `thresholds.py`) within a rolling window
4. Garmin trust evaluation resolves to `DataTrustLevel.INVALID`

**Minimum payload contract:**

- `component`: `"garmin_sync"`
- `action`: `"garmin_api_degraded"`
- `severity`: `"CRITICAL"`
- `failure_class`: canonical Garmin failure class
- `sync_status`: one of `connect_failed`, `timeout_cancelled`, `sync_failed`
- `error_class`: exception class name
- `error_message`: sanitized error detail
- `last_successful_sync_at`: ISO timestamp or `null`
- `data_age_hours`: float
- `trust_level`: `INVALID` or current trust level
- `reasons`: list of normalized reason codes
- `degraded_mode_expected`: boolean
- `emitted_at`: ISO timestamp

**New constant required (thresholds.py):**

```python
GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT = 3  # consecutive failures → non-transient
```

### D2 — Coach dashboard indicator

Indicator text and appearance/clear conditions per Pass 1 design document:

- Primary: `Garmin sync degraded — last valid data: <N>h ago.`
- No baseline: `Garmin sync degraded — no valid Garmin baseline available.`
- Stale: `Garmin data stale — operating with caution.`
- Invalid: `Garmin data invalid/stale — conservative coaching mode expected.`

Appearance condition: latest degradation event active OR trust level SUSPECT/INVALID

Clear condition (all three required):

1. At least one successful sync after degraded state entry
2. Trust recovers to TRUSTED
3. Data freshness within trusted threshold window

### D3 — `garminconnect` library pinning

- Pin `garminconnect` to an exact tested version in `requirements.txt`
- Any version upgrade requires explicit architect approval and isolation validation
- CI dependency drift check (pip-audit pattern per T4-25) covers this pin
- If pinned version breaks: maintain pin, emit `garmin_api_degraded`, open controlled
  upgrade workflow — do not auto-upgrade in production

Approved pinned version at ADR acceptance: `garminconnect==0.2.13` (current version in
`requirements.txt` as of 2026-03-17)

### D4 — Multi-device fallback interface boundary

A provider-agnostic `BiometricSourceAdapter` boundary is defined with three contracts:

```python
# Capability declaration
@dataclass
class SourceCapabilities:
    source_name: str
    supports_hrv: bool
    supports_resting_hr: bool
    supports_sleep: bool
    supports_activity_load: bool

# Normalized biometric snapshot
@dataclass
class NormalizedBiometricSample:
    source_name: str
    sampled_at: str  # ISO-8601
    hrv_rmssd: float | None
    resting_hr: int | None
    sleep_hours: float | None
    provenance: str

# Sync result
@dataclass
class BiometricSourceSyncResult:
    samples: list[NormalizedBiometricSample]
    sync_status: str
    failure_class: str | None
    data_trust_report: dict  # ADR-0041 DataTrustReport
```

ADR-0016 constraint: Fallback boundary must conform to ADR-0016 unified adapter gate —
one shared adapter contract before multi-provider ingestion expansion.

ADR-0041 constraint: Every fallback source must emit `DataTrustReport` with canonical
trust semantics (TRUSTED, SUSPECT, INVALID).

Explicitly deferred (not in T5-12 Pass 2 scope):

- Polar / Whoop / COROS concrete adapter implementations
- Source switching logic
- Arbitration / fusion policies between Garmin and fallback sources

---

## Implementation obligations for T5-12 Pass 2

| Obligation | Location |
|---|---|
| O1 | Add `GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT` to `thresholds.py` + evidence entry | `titan/config/thresholds.py`, `titan/config/evidence_registry.py` |
| O2 | Emit `garmin_api_degraded` at CRITICAL in `garmin_sync.py` at failure aggregation points | `titan/integrations/garmin_sync.py` |
| O3 | Define `SourceCapabilities`, `NormalizedBiometricSample`, `BiometricSourceSyncResult` dataclasses | `titan/integrations/garmin_sync.py` or new `titan/integrations/biometric_source.py` |
| O4 | `DegradedModeTracker` registration for Garmin degradation condition | `titan/orchestration/daily_coach.py` |
| O5 | Coach dashboard indicator wording in `OperatorConsoleService` | `titan/ui/operator_console.py` |
| O6 | Tests for `garmin_api_degraded` emission (trigger conditions × 4) | `tests/titan/integrations/test_garmin_sync.py` |
| O7 | Tests for dashboard indicator appearance/clear conditions | `tests/titan/ui/test_operator_console.py` |

---

## Consequences

**Positive:**

- Garmin degradation is now a first-class CRITICAL signal visible to operator
- Dashboard indicator gives operator actionable context during outages
- Pinning policy prevents silent library upgrades from breaking auth
- Fallback boundary is defined and governed — ready for Phase 9 provider expansion

**Trade-offs:**

- `garmin_api_degraded` adds a new CRITICAL event to the alert surface
- Fallback boundary contracts add 3 new dataclasses
- Concrete fallback providers remain unimplemented until Phase 9

**Neutral:**

- `garminconnect==0.2.13` pin is already the current version — no change required
- `DataTrustLevel` integration follows existing ADR-0041 pattern

---

## Acceptance criteria for ADR

- `GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT` named in `thresholds.py`
- `garmin_api_degraded` CRITICAL event emitted on all 4 trigger conditions
- Dashboard indicator wording implemented per D2
- `BiometricSourceSyncResult` (and related dataclasses) defined per D4
- All T5-12 Pass 2 tests green
- This ADR file exists in `docs/adr/`
