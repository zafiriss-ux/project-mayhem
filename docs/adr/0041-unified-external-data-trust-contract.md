# ADR-0041 — Unified External Data Trust Contract

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Architect Directive V8 — Decision 2: Every external datum passes a health check before entering the system
**Phase:** IMMEDIATE — effective from this commit forward; T1-23 is the implementation gate
**Supplements:** ADR-0023 (physiological bounds validation), ADR-0026 (structural data sanity),
ADR-0030 (external data source staleness), ADR-0020 (degraded conservative mode)

---

## Context

Three separate ADRs address external data validation at different boundaries:

| ADR | Boundary | Validates | Gap |
|---|---|---|---|
| ADR-0023 | DB read path | Out-of-bounds physiological values (HRV=0, RHR=200) | Produces `None` but does not emit a unified trust level |
| ADR-0026 | DB write path (Garmin sync) | Structural inconsistencies (max_hr < avg_hr, future timestamps) | Reject/warn but does not tag the data with a trust level |
| ADR-0030 | DailyCoach Step 2 | Data staleness (Garmin > 26h, Weather > 3h) | Sets `garmin_data_stale = True` but uses an ad-hoc field |

The result is a **patchwork of validation**. Each boundary produces a different signal
with a different shape. Downstream consumers (governance engine, weekly planner,
Telegram briefing) must check three different ad-hoc fields to understand the
trustworthiness of the data they are evaluating.

### The Silent Error Risk

When no unified trust contract exists, every new external API added in Phase 8
(multi-sport adapter, additional biometric sources, multi-location weather) starts from
zero. The developer who adds the new API must independently decide:

- "Should I validate bounds? How?"
- "How do I flag staleness?"
- "What does the governance engine do with this data if it's unreliable?"

Without a contract, the default answer is: "I'll add a log line and move on." This is
exactly how silent errors accumulate — not through malice, but through the absence of
a mandatory pattern.

### What the Three ADRs Do Not Cover

ADRs 0023, 0026, 0030 address specific validation cases. They do not establish:

1. A **uniform trust signal** (`DataTrustLevel`) that all data sources must emit.
2. A **governance contract** specifying what each trust level means for recommendations.
3. A **new data source onboarding gate** — no new external API may be added without
   implementing the trust contract.

---

## Decision

**Establish `DataTrustLevel` as a first-class type in the TITAN OS data model.
Every external data source must emit a `DataTrustLevel` alongside its data.
The governance engine must consume `DataTrustLevel` and adjust its confidence
accordingly. No new external data source may be integrated without implementing
this contract.**

### The DataTrustLevel Enum

```python
# titan/science/data_trust.py  (new module)
from enum import Enum

class DataTrustLevel(Enum):
    TRUSTED   = "TRUSTED"    # Fresh, structurally valid, within physiological bounds
    SUSPECT   = "SUSPECT"    # One concern (stale OR boundary-adjacent OR single-field anomaly)
    INVALID   = "INVALID"    # Disqualifying condition (structural failure, extreme bound violation,
                             #  or freshness exceeded hard threshold)

class DataTrustReport:
    source: str              # e.g., "garmin", "weather", "manual_entry"
    trust_level: DataTrustLevel
    reasons: list[str]       # Human-readable explanation of any degradation
    checked_at: str          # ISO-8601 timestamp of the trust check
    data_age_hours: float    # Age of underlying data at check time
```

### Trust Level Semantics and Governance Response

| DataTrustLevel | Governance response |
|---|---|
| `TRUSTED` | Normal gate evaluation |
| `SUSPECT` | Gates evaluate, but coaching output must include a caveat: _"Data quality note: [reason]"_; hard-stops may still fire; VO₂max sessions blocked |
| `INVALID` | Engage ADR-0020 degraded conservative mode immediately; hard-stop all intensity recommendations; emit `data_trust_invalid` structured event (CRITICAL severity) |

**Rationale:** `INVALID` data does not mean "the athlete is fine." It means the system
cannot evaluate the athlete's state. The conservative response (degraded mode) is
safer than attempting evaluation on corrupted inputs.

### Mapping Existing Validation to DataTrustLevel

The three existing ADRs are unified under this contract:

| Existing signal | Maps to |
|---|---|
| ADR-0023: value out of 2× physiological bounds → `None` | `INVALID` |
| ADR-0023: value clamped within 2× tolerance | `SUSPECT` |
| ADR-0026: structural reject (max_hr < avg_hr, future timestamp) | `INVALID` |
| ADR-0026: structural warn (zero distance + duration) | `SUSPECT` |
| ADR-0030: Garmin data age > 26h | `INVALID` |
| ADR-0030: Garmin data age 12–26h | `SUSPECT` |
| ADR-0030: weather confidence = SYNTHETIC | `SUSPECT` |
| All other cases (fresh, valid, in-bounds) | `TRUSTED` |

### Coaching Context Integration

The `DailyCoach` coaching context must carry:

```python
coaching_ctx["data_trust"] = {
    "garmin": DataTrustReport(...),
    "weather": DataTrustReport(...),
    "overall": DataTrustLevel,      # Minimum (most degraded) of all sources
}
```

`overall` is the minimum trust level across all active sources. If any source is
`INVALID`, `overall = INVALID`. If any source is `SUSPECT` and none is `INVALID`,
`overall = SUSPECT`.

The governance engine evaluates `coaching_ctx["data_trust"]["overall"]` before
evaluating any physiological gate.

### New Data Source Onboarding Gate

**No new external data source may be merged into `main` without:**

1. A `DataTrustReport` emitter registered in `titan/science/data_trust.py`.
2. Staleness threshold constants in `thresholds.py`:
   ```python
   <SOURCE>_DATA_MAX_AGE_HOURS = <value>     # → INVALID threshold
   <SOURCE>_DATA_SUSPECT_AGE_HOURS = <value>  # → SUSPECT threshold
   ```
3. CI tests in `tests/test_data_trust_<source>.py` asserting:
   - Fresh valid data → `TRUSTED`
   - Stale data (age > SUSPECT threshold) → `SUSPECT`
   - Stale data (age > MAX threshold) → `INVALID`
   - Structurally invalid data → `INVALID`
4. `OperatorConsoleService` readiness dashboard updated to display all source trust levels.

This gate is enforced in PR review. The CI check (T1-23) validates that every
configured data source has a registered `DataTrustReport` emitter.

### What This Does NOT Change

- The specific validation logic in ADR-0023, ADR-0026, and ADR-0030 is unchanged.
  They are now *classified* under this contract, not replaced.
- The `garmin_data_stale` and `weather_confidence` ad-hoc fields remain for backward
  compatibility within their respective modules; `DataTrustLevel` is the canonical
  contract going forward.
- ADR-0020 degraded mode logic is unchanged — `INVALID` trust is now the unified
  trigger that activates it.

---

## Debt Items Created

- **T1-23** — No unified `DataTrustLevel` contract — external data sources emit
  ad-hoc trust signals that are not unified into a single governance-visible field;
  new data sources have no mandatory onboarding gate (Tier 1, data integrity;
  **IMMEDIATE** — blocks Phase 8 multi-source integration)

---

## Alternatives Considered

**Alternative A — Extend each existing ADR with a severity level**
Rejected. Parallel severity systems in three ADRs are equivalent to no system.
The value of this ADR is the **single, unified type** (`DataTrustLevel`) that all
downstream code checks once, at one place. Distributing severity across three ADRs
preserves the patchwork.

**Alternative B — Use a numeric confidence score (0.0–1.0) instead of an enum**
Rejected for the governance layer. Numeric scores require downstream calibration
("is 0.7 enough to recommend a hard session?") which is an open parameter. An enum
with three states maps directly to three governance responses — no calibration
required. Numeric scores are appropriate for *within* the ML advisory layer
(ADR-0032 `ExplainableOutput.confidence_interval`) but not for the deterministic
governance layer.

**Alternative C — Only apply trust levels at the governance gate, not at coaching
context level**
Rejected. Trust level must be visible at the coaching context level so it can be:
(a) logged in structured events, (b) surfaced in the Telegram briefing,
(c) included in the Session Explorer payload, and (d) used by the weekly planner
(which also consumes external data and must know its reliability).

---

## Consequences

- Positive: Every external data source speaks the same language. Adding a new source
  in Phase 8 is straightforward — implement `DataTrustReport`, register it, add tests.
  The trust contract is not optional and cannot be skipped.
- Positive: The governance engine has a single, explicit check for data quality
  (`overall = INVALID → degraded mode`) rather than three ad-hoc condition checks.
- Positive: Operators see a unified data trust dashboard in the Operator Console
  rather than scattered staleness flags.
- Negative (acceptable): Requires a new `titan/science/data_trust.py` module
  (thin — the enum + dataclass only; ~30 lines) and updates to the three existing
  validation boundaries to emit `DataTrustReport` objects.
- Constraint: T1-23 is **IMMEDIATE** — it must be completed before any Phase 8
  new data source integration begins. It is a Phase 8 entry gate criterion, to be
  added to ADR-0022 G1 set.
