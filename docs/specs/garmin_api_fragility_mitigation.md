# T5-12 Pass 1 — Garmin API Fragility Mitigation Design

## 1) Structured event: `garmin_api_degraded`

### Trigger conditions
Emit `garmin_api_degraded` when any of the following occurs:
- Garmin authentication/login failure in `connect()` or an active sync path.
- Sync timeout/cancellation that prevents completion of the current cycle.
- Repeated Garmin provider failures crossing a non-transient threshold window.
- Trust assessment for the Garmin payload resolves to `INVALID` under ADR-0041 trust semantics.

### Severity
- Severity is **CRITICAL**.
- Event is operator-visible and treated as degraded-mode signal input.

### Required payload fields
- `component` (fixed: `garmin_sync`)
- `action` (fixed: `garmin_api_degraded`)
- `severity` (fixed: `CRITICAL`)
- `failure_class` (canonical failure type)
- `sync_status` (`connect_failed` | `timeout_cancelled` | `sync_failed`)
- `error_class` (exception class)
- `error_message` (sanitized detail)
- `last_successful_sync_at` (ISO-8601 or `null`)
- `data_age_hours` (float)
- `trust_level` (`TRUSTED` | `SUSPECT` | `INVALID`)
- `reasons` (normalized reason codes)
- `emitted_at` (ISO-8601)

## 2) Coach dashboard indicator spec

### What the user sees when Garmin sync fails
- A persistent degraded indicator in the coach dashboard when degradation is active.
- Indicator must reference both state and recency of last valid Garmin data.

### Staleness / last-data-age display
- Display `last successful Garmin data age` in hours.
- If no valid baseline exists, show explicit no-baseline wording.
- Indicator clears only after a successful post-failure sync and trust/freshness recovery.

### Three wording states (ADR-0050 aligned)
1. **Degraded with baseline:**
   - `Garmin sync degraded — last valid data: <N>h ago.`
2. **Degraded without baseline:**
   - `Garmin sync degraded — no valid Garmin baseline available.`
3. **Stale/invalid trust state:**
   - `Garmin data invalid/stale — conservative coaching mode expected.`

## 3) `garminconnect` pinning strategy

### Version pinning policy
- Pin `garminconnect` to an exact, tested version (no range specifier).
- Upgrades require explicit review/approval and controlled validation prior to merge.
- Runtime breakage does **not** trigger automatic package upgrades in production.

### CI change / breakage detection approach
- Add CI dependency drift surveillance for the pinned version.
- Fail CI when pin changes without explicit approval context.
- Add scheduled dependency health check to surface upstream breakage risk early.
- If breakage is detected, retain pin until controlled remediation is validated.

## 4) Multi-device fallback interface sketch

### Candidate providers
- Polar
- Whoop
- COROS

### Interface sketch (provider-agnostic boundary)
- `SourceCapabilities`: provider capability declaration (HRV, resting HR, sleep, load).
- `NormalizedBiometricSample`: normalized per-sample payload (`source_name`, timestamp, biometric fields, provenance).
- `BiometricSourceSyncResult`: sync outcome (`samples`, `sync_status`, optional `failure_class`, trust report).

### Alignment with ADR-0016 and ADR-0041
- ADR-0016: fallback must be implemented behind a unified adapter contract (single ingestion boundary before provider expansion).
- ADR-0041: each provider payload must produce canonical trust semantics (`TRUSTED` / `SUSPECT` / `INVALID`) and evidence-reason fields.
- Pass 1 scope ends at interface/spec level; concrete provider adapters are deferred to Pass 2+ after architect ADR acceptance.
