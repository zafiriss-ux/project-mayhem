# T5-12 Pass 1 — Garmin Unofficial API Fragility Mitigation Design (Audit-Only)

## Scope and constraints

This document defines the **Pass 1 mitigation design only** for T5-12. It is intentionally limited to four design areas:
1. Structured Garmin-degraded event definition
2. Coach dashboard indicator specification
3. `garminconnect` library pinning strategy
4. Multi-device fallback interface sketch

Pass 1 is design-only and does **not** include runtime implementation, adapter implementation, UI implementation, CI implementation, or ADR authorship.

**Task state declaration (required):**
- **T5-12 remains OPEN after this Pass 1 design artifact.**
- **Pass 2 implementation is BLOCKED until an architect-accepted design ADR is in place.**

## Current-state constraints informing this design

- `GarminSync` currently emits structured events via `_garmin_event(...)` with component `"garmin_sync"`, and classifies failures into stable classes (`GARMIN_AUTH_FAIL`, `GARMIN_RATE_LIMIT`, `GARMIN_PAYLOAD_MALFORMED`, `GARMIN_TIMEOUT`, `GARMIN_API_UNAVAILABLE`).
- `sync_all(...)` can return timeout/degraded-style status (`"timeout_cancelled"`) and already emits SLO/timeout-related events.
- T5-12 explicitly requires a CRITICAL Garmin-degraded signal, an operator-facing dashboard indicator, pinned `garminconnect` dependency control, and a fallback interface sketch.
- ADR-0016 requires a unified adapter contract gate before multi-provider expansion.
- ADR-0041 requires external source trust emission under a unified trust contract (`DataTrustLevel` / `DataTrustReport`) and governance-consumable trust semantics.

---

## A) Structured Garmin-degraded event definition

### Event name
- **`garmin_api_degraded`** (structured event action)

### Trigger conditions
Emit `garmin_api_degraded` when any of the following conditions hold:
1. Authentication failure class is detected (`GARMIN_AUTH_FAIL`) during `connect()` or any sync operation.
2. `sync_all(...)` exits with `status="timeout_cancelled"` or a timeout failure class.
3. Repeated Garmin provider failures exceed a bounded threshold window (design constant to be defined in implementation ADR) indicating non-transient degradation.
4. Garmin trust evaluation for the current sync cycle resolves to `DataTrustLevel.INVALID` due to freshness/structural invalidity conditions.

### Severity
- **CRITICAL** (mandatory, per T5-12 requirement).

### Required payload fields
Minimum payload contract:
- `component`: `"garmin_sync"`
- `action`: `"garmin_api_degraded"`
- `severity`: `"CRITICAL"`
- `failure_class`: one of canonical Garmin failure classes
- `sync_status`: e.g., `connect_failed`, `timeout_cancelled`, `sync_failed`
- `error_class`: exception class name when available
- `error_message`: sanitized error detail
- `last_successful_sync_at`: ISO timestamp or `null`
- `data_age_hours`: float hours since last successful Garmin data ingest
- `trust_level`: `INVALID` (or current trust level if degradation pre-invalid)
- `reasons`: list of normalized reason codes
- `degraded_mode_expected`: boolean (true when downstream should enter/maintain conservative mode)
- `emitted_at`: ISO timestamp

### Emission point
- Primary emitter: `titan/integrations/garmin_sync.py` at failure aggregation points (connection failure and `sync_all` terminal failure handling).
- Secondary propagation: orchestration layer consumes the event/trust outcome and ensures degraded-mode tracker registration/visibility.

### Downstream consumer expectations
- **DailyCoach / orchestration:** treat as degraded-data condition and enforce conservative output behavior.
- **Operator console/dashboard:** display active Garmin degradation status with freshness metadata.
- **Observability/alerting:** route as high-priority incident signal, preserving failure class and freshness context.
- **Governance input trust path:** treat trust outcome as authoritative input for recommendation confidence constraints.

---

## B) Coach dashboard indicator specification

### Indicator wording
- **Primary text:** `Garmin sync degraded — last valid data: <N>h ago.`

### Minimum displayed fields
1. `status`: Degraded / Active
2. `last_successful_sync_at`
3. `data_age_hours`
4. `failure_class`
5. `current_sync_status` (e.g., auth failure, timeout, API unavailable)
6. `trust_level`
7. `updated_at`

### Stale-data wording
- If no successful historical sync exists: `Garmin sync degraded — no valid Garmin baseline available.`
- If stale beyond suspect threshold but below invalid threshold: `Garmin data stale — operating with caution.`
- If invalid threshold crossed: `Garmin data invalid/stale — conservative coaching mode expected.`

### Appearance condition
Indicator appears when either condition is true:
1. Latest Garmin degradation event is active and not cleared.
2. Garmin `DataTrustLevel` is `SUSPECT` or `INVALID` for current coaching context.

### Clear condition
Indicator clears only when all are true:
1. At least one successful Garmin sync completes after degraded state entry.
2. Trust recovers to `TRUSTED` for Garmin source.
3. Data freshness is within trusted threshold window.

### Expected operator action
- Confirm whether degradation is transient or persistent.
- If persistent, monitor coaching outputs for conservative-mode behavior and communicate reduced confidence to athlete.
- Trigger escalation runbook if degradation exceeds operational SLO window.

---

## C) `garminconnect` library pinning strategy

### Pinning policy
- Pin `garminconnect` to an exact tested version in the dependency lock/pinned requirements surface used by runtime.
- Treat unpinned or ranged upgrades as non-compliant for this integration.

### Change-alert / verification mechanism
Design requirement:
1. Automated dependency drift detection checks whether resolved runtime version differs from approved pinned version.
2. Verification job executes Garmin integration contract smoke checks against the pinned version.
3. Any version drift or smoke-check break marks integration health as failed and requires explicit re-validation before adoption.

(Implementation mechanism may be CI tooling such as `pip-audit`/`pip-check` + contract checks, but Pass 1 defines policy, not tooling implementation.)

### Behavior when pinned version becomes invalid/breaks
- Immediate operational posture: keep version pinned; do **not** auto-upgrade in production.
- Emit/maintain Garmin-degraded signal if runtime behavior fails.
- Open controlled upgrade workflow: validate candidate versions in isolation, run integration contract checks, then promote via explicit approval.
- If no working version is available, system remains in degraded-data posture with operator-visible indicator until remediated.

---

## D) Multi-device fallback interface sketch (ADR-0016 / ADR-0041 aligned)

### Boundary definition (interface-only)
Define a provider-agnostic **Biometric Source Adapter boundary** that exposes:
1. Capability declaration (which biometrics are available from source)
2. Fetch of normalized biometric snapshot/time-series
3. Emission of source trust report (`DataTrustReport`)
4. Source identity and timestamp metadata

No concrete provider adapters are defined in Pass 1.

### Candidate fallback sources (design shortlist only)
- **Polar**
- **Whoop**
- **COROS**

These are candidate providers for future adapter implementation in Pass 2+ and are listed here only to define the intended multi-device expansion boundary.

### High-level contract/data shape
Proposed conceptual contracts (names illustrative):
- `SourceCapabilities`
  - `source_name`
  - `supports_hrv`
  - `supports_resting_hr`
  - `supports_sleep`
  - `supports_activity_load`
- `NormalizedBiometricSample`
  - `source_name`
  - `sampled_at`
  - `hrv_rmssd`
  - `resting_hr`
  - `sleep_hours`
  - `provenance`
- `BiometricSourceSyncResult`
  - `samples`
  - `sync_status`
  - `failure_class`
  - `data_trust_report` (ADR-0041 aligned)

### ADR-0016 interaction
- Fallback boundary must conform to ADR-0016 unified adapter gate: one shared adapter contract before multi-provider ingestion expansion.
- Pass 1 defines boundary semantics only; provider implementation remains blocked until architect-approved ADR step for Pass 2.

### ADR-0041 interaction
- Every fallback source must emit `DataTrustReport` with canonical trust semantics (`TRUSTED`, `SUSPECT`, `INVALID`).
- Governance and operator surfaces consume trust uniformly regardless of originating source.
- Fallback does not bypass trust checks; it must satisfy onboarding gate constraints before activation.

### Explicitly out of scope for Pass 1
- Implementing Polar/Whoop/COROS adapters
- Implementing source switching logic
- Implementing arbitration/fusion policies between Garmin and fallback sources
- Implementing runtime event emission code
- Implementing dashboard UI
- Implementing CI pipelines/tooling changes
- Closing T5-12 (remains OPEN until Pass 2 implementation + acceptance)

---

## Pass 1 completion statement

This document provides the required architect-reviewable mitigation design for T5-12 Pass 1 only.
No production code, tests, adapters, or UI behavior are implemented in this pass.
T5-12 remains OPEN after this pass, and Pass 2 is blocked pending architect acceptance of the design ADR.
