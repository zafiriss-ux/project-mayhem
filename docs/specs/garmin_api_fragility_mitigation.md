# T5-12 Pass 1 — Garmin API Fragility Mitigation Design Document

| Field | Value |
|-------|-------|
| **Status** | Design-complete (Pass 1) — implementation blocked pending ADR acceptance |
| **Pass type** | Audit / design — no code changes |
| **Related ADR** | [ADR-0050](../adr/0050-garmin-api-fragility-mitigation.md) |
| **Related task** | T5-12 (Phase 8C) |
| **Related ADRs** | ADR-0016 (multi-sport unified adapter gate), ADR-0041 (DataTrustLevel contract) |
| **Date** | 2026-03-18 |

---

## 1. Problem Statement

`garminconnect` is an **unofficial, reverse-engineered** Python library that scrapes Garmin
Connect's web authentication flow, not an official API. Garmin has changed its authentication
mechanism at least twice in the past three years, breaking the library on each occasion.

**Risk scenario:** Garmin deploys a new login challenge (CAPTCHA, MFA enforcement, OAuth
mandate) → `garmin_sync.py` fails silently or with an exception → `DailyCoach` cold-starts
with zero biometric data → governance runs on stale data → wrong coaching decisions.

**Current mitigation gap:** T1-09 introduced synthetic weather fallback. No equivalent
structured degradation signal exists for Garmin data beyond `DailyCoach`'s existing handling
of missing today-data.

---

## 2. Scope (Pass 1 — Design Only)

This document defines four mitigation areas. No code changes are made in Pass 1:

1. **Structured Garmin-degraded event definition** — `garmin_api_degraded` CRITICAL event
2. **Coach dashboard indicator specification** — wording states and appearance/clear conditions
3. **`garminconnect` library pinning strategy** — version lock + change-alert policy
4. **Multi-device fallback interface sketch** — `BiometricSourceAdapter` boundary contracts

Pass 2 (implementation) is **blocked** until ADR-0050 is accepted by the architect.

---

## 3. Mitigation Area 1 — Structured `garmin_api_degraded` Event

### 3.1 Trigger Conditions

A `garmin_api_degraded` event at severity **CRITICAL** is emitted when any of the following
conditions hold:

| Condition ID | Trigger |
|---|---|
| C1 | Authentication failure (`GARMIN_AUTH_FAIL`) during `connect()` or any sync operation |
| C2 | `sync_all()` exits with `status="timeout_cancelled"` |
| C3 | Repeated provider failures exceed `GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT` within a rolling window |
| C4 | Garmin trust evaluation resolves to `DataTrustLevel.INVALID` (ADR-0041) |

**New constant required in `thresholds.py`:**

```python
GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT = 3  # consecutive failures → non-transient
```

### 3.2 Minimum Payload Contract

```python
{
    "component": "garmin_sync",
    "action": "garmin_api_degraded",
    "severity": "CRITICAL",
    "failure_class": "<canonical Garmin failure class>",
    "sync_status": "<connect_failed | timeout_cancelled | sync_failed>",
    "error_class": "<exception class name>",
    "error_message": "<sanitized error detail>",
    "last_successful_sync_at": "<ISO-8601 timestamp or null>",
    "data_age_hours": "<float>",
    "trust_level": "<INVALID or current DataTrustLevel>",
    "reasons": ["<normalized reason code>"],
    "degraded_mode_expected": "<boolean>",
    "emitted_at": "<ISO-8601 timestamp>"
}
```

### 3.3 Emission Points

- `GarminSync.connect()` — on authentication failure (C1)
- `GarminSync.sync_all()` — on timeout/cancellation (C2)
- Failure counter threshold crossing (C3) — checked after each failed sync attempt
- `DataTrustLevel` evaluation gate (C4) — when trust resolves to INVALID

---

## 4. Mitigation Area 2 — Coach Dashboard Indicator

### 4.1 Wording States

Three wording states cover the full degradation surface:

| State | Indicator text |
|---|---|
| Active degradation (baseline present) | `Garmin sync degraded — last valid data: <N>h ago.` |
| Active degradation (no baseline ever) | `Garmin sync degraded — no valid Garmin baseline available.` |
| Data stale but not hard-failed | `Garmin data stale — operating with caution.` |
| Trust SUSPECT or INVALID (data present) | `Garmin data invalid/stale — conservative coaching mode expected.` |

### 4.2 Appearance Condition

Indicator is shown when **either** of:
- Latest `garmin_api_degraded` event is active (no clear event received since last degradation)
- Current `DataTrustLevel` for Garmin source is SUSPECT or INVALID

### 4.3 Clear Condition

All three conditions must hold simultaneously to clear the indicator:

1. At least one successful sync has completed after the degraded-state entry
2. Trust recovers to TRUSTED (`DataTrustLevel.TRUSTED`)
3. Data freshness is within the trusted threshold window

---

## 5. Mitigation Area 3 — `garminconnect` Library Pinning Strategy

### 5.1 Pin Policy

- `garminconnect` is pinned to an **exact tested version** in `requirements.txt`
  (format: `garminconnect==X.Y.Z`)
- The pinned version at design time: `garminconnect==0.2.13` (current version as of 2026-03-17)
- Any version upgrade requires **explicit architect approval** and isolation validation
  before merging

### 5.2 CI Drift Detection

- Existing `pip-audit` pattern (T4-25) covers the pinned version for security advisories
- If the pinned version is flagged by pip-audit: emit `garmin_api_degraded`, open a
  controlled upgrade workflow — do **not** auto-upgrade in production

### 5.3 Upgrade Workflow (future)

If `garminconnect` auth breaks despite pinning:
1. Pin remains in place — do not upgrade without isolation validation
2. Emit `garmin_api_degraded` (C1 trigger)
3. Open a dedicated upgrade branch with the new version in isolation
4. Run full integration tests before promoting to main

---

## 6. Mitigation Area 4 — Multi-Device Fallback Interface Sketch

### 6.1 Architectural Constraints

The fallback boundary must conform to two existing ADRs:

- **ADR-0016** (multi-sport scope and unified adapter gate): one shared adapter contract
  is required before multi-provider ingestion expansion
- **ADR-0041** (unified external data trust contract): every fallback source must emit a
  `DataTrustReport` with canonical trust semantics (TRUSTED, SUSPECT, INVALID)

### 6.2 `BiometricSourceAdapter` Interface

Three dataclass contracts define the boundary:

```python
@dataclass
class SourceCapabilities:
    """Capability declaration per biometric source."""
    source_name: str
    supports_hrv: bool
    supports_resting_hr: bool
    supports_sleep: bool
    supports_activity_load: bool


@dataclass
class NormalizedBiometricSample:
    """Normalized biometric snapshot — source-agnostic."""
    source_name: str
    sampled_at: str          # ISO-8601
    hrv_rmssd: float | None
    resting_hr: int | None
    sleep_hours: float | None
    provenance: str          # ADR-0041 provenance label


@dataclass
class BiometricSourceSyncResult:
    """Result of a single sync attempt from any biometric source."""
    samples: list[NormalizedBiometricSample]
    sync_status: str         # "ok" | "degraded" | "failed"
    failure_class: str | None
    data_trust_report: dict  # ADR-0041 DataTrustReport payload
```

### 6.3 Explicit Deferrals (not in Pass 2 scope)

The following items are deferred to Phase 9 and are **not** part of T5-12 Pass 2:

- Concrete adapter implementations for Polar, Whoop, COROS
- Source switching logic (which source to prefer when Garmin degrades)
- Arbitration / fusion policies when multiple sources provide overlapping signals

---

## 7. Pass 2 Implementation Obligations

Defined in ADR-0050 §Implementation obligations:

| Obligation | Description | Location |
|---|---|---|
| O1 | Add `GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT` to `thresholds.py` + evidence entry | `titan/config/thresholds.py`, `titan/config/evidence_registry.py` |
| O2 | Emit `garmin_api_degraded` at CRITICAL in `garmin_sync.py` at failure aggregation points | `titan/integrations/garmin_sync.py` |
| O3 | Define `SourceCapabilities`, `NormalizedBiometricSample`, `BiometricSourceSyncResult` dataclasses | `titan/integrations/garmin_sync.py` or new `titan/integrations/biometric_source.py` |
| O4 | `DegradedModeTracker` registration for Garmin degradation condition | `titan/orchestration/daily_coach.py` |
| O5 | Coach dashboard indicator wording in `OperatorConsoleService` | `titan/ui/operator_console.py` |
| O6 | Tests for `garmin_api_degraded` emission (trigger conditions C1–C4) | `tests/titan/integrations/test_garmin_sync.py` |
| O7 | Tests for dashboard indicator appearance/clear conditions | `tests/titan/ui/test_operator_console.py` |

---

## 8. Acceptance Gate for Pass 1

Pass 1 is complete when:

- [x] This design document exists at `docs/specs/garmin_api_fragility_mitigation.md`
- [x] T5-12 status in `TECHNICAL_DEBT.md` reflects Pass 1 complete, Pass 2 blocked pending ADR
- [x] ADR-0050 exists at `docs/adr/0050-garmin-api-fragility-mitigation.md`
- [ ] Pass 2 implementation obligations O1–O7 remain OPEN (blocked on ADR architect acceptance)
