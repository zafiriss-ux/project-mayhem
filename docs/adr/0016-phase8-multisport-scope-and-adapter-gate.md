# ADR-0016 — Phase 8 Multi-sport Scope and Unified Adapter Gate

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-03-03 |
| Owners | TITAN OS architecture/governance |
| Scope | Garmin activity ingestion, Phase 8 connector expansion |

## Context

Current Garmin ingestion calls `get_activities_by_date(start, end, "running")` and is
therefore intentionally scoped to running activities.

Phase 8 roadmap already includes additional sync sources (Strava, Polar, Whoop,
COROS). Without a locked decision, additional sport support could be introduced
incrementally and inconsistently across providers.

## Decision

1. **Multi-sport is in scope for Phase 8** (not for current implementation scope).
2. **Current scope remains running-only** until Phase 8 execution begins.
   - The hardcoded Garmin running filter is retained for now.
   - No additional sport types are implemented in this ADR.
3. **Phase 8 implementation gate (mandatory):** before adding any non-running
   sport ingestion, define and approve a unified adapter interface that is shared
   across Garmin, Strava, Polar, Whoop, and COROS.
4. **Adapter contract minimum:** interface must standardize activity type mapping,
   required biometrics availability checks, and provider capability declaration.

No multi-sport implementation work may begin before that adapter interface is
documented and accepted.

## Consequences

### Positive
- Prevents provider-by-provider drift in sport taxonomy and payload semantics.
- Protects current running-focused behavior from accidental scope creep.
- Establishes a single precondition for all Phase 8 connector work.

### Neutral
- No runtime behavior changes are introduced now.
- Garmin sync continues to ingest running activities only.

### Negative / Risks
- Multi-sport athletes remain partially represented until Phase 8 adapter work starts.

## Verification

- Tier 5 roadmap section references ADR-0016 and marks T5-03 as decided.
- TECHNICAL_DEBT Tier 5 entry is updated from "Decision needed" to "Decision locked".
- Tests assert ADR-0016 existence and the Phase 8 adapter gate language.
