# ADR 0053: Data-Void Conservative Governance Gate

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Accepted |
| **Date** | 2026-05-02 |
| **Commits** | TBD |
| **Files** | `titan/config/thresholds.py`, `titan/science/governance_engine.py`, `titan/core/database.py` |

## Context

When the Garmin sync has not produced data for >48 hours, the TSB/CTL/ATL values decay toward zero mathematically, making the athlete appear "fresh" to the governance engine. This creates a silent fail-open condition: the system may recommend high-intensity sessions when it has no objective evidence of the athlete's actual state.

This gap was identified during a Gemini architectural audit on 2026-05-02. The conservative-fail principle (ADR-0051) requires that missing data must not allow the system to silently permit higher intensity.

Related: ADR-0051 (Conservative Fail), INV-05.

## Decision

Add a data-void governance gate (H6) that fires when Garmin data is stale beyond a configurable threshold.

**Gate logic:**

```
IF last_garmin_sync_age_hours > DATA_VOID_THRESHOLD_HOURS (48)
AND no daily_metrics row exists for athlete in last 48h:
    → emit DATA_VOID_CONSERVATIVE lock code
    → cap session at Zone 2 (max_zone ≤ 2)
    → set context["data_void_active"] = True
```

This is a **soft gate** (not a hard stop like H1–H5). Conservative but not session-blocking.

**Constants** (`titan/config/thresholds.py`):

```python
DATA_VOID_THRESHOLD_HOURS: float = 48.0
DATA_VOID_ZONE_CAP: int = 2
```

**Lock code:** `DATA_VOID_CONSERVATIVE`
**Gate ID:** H6 (soft gate, same tier as FUELING/INTENSITY)

## Implementation

- **Stage 1** — ADR + constants + lock code registration
- **Stage 2** — `governance_engine.py` gate logic (H6)
- **Stage 3** — `database.py` staleness query + tests

## Consequences

**Positive:**
- Prevents hallucinated high-intensity recommendations during Garmin outages or API bans.
- Consistent with ADR-0051 conservative-fail principle.
- Makes data-void state observable via a named lock code (audit trail).

**Neutral:**
- Zone 2 cap still allows recovery and easy aerobic work — not a session block.

**Negative:**
- Requires at least one sync per 48h for full coaching capability.
- Athletes with manual-only workflow always hit this gate until T5-116 (manual entry path) is implemented.
