# Operator Console Technology Path

## Scope
Define the delivery path for the Operator Console UI layer while preserving
existing kernel and service boundaries.

## Decision
The UI rollout follows three phases:

1. **Phase A (Terminal facelift):**
   - Goal: improve immediate operator readability in the existing terminal UI.
   - Scope: retro-HUD dashboard snapshot on startup, action rail (primary /
     secondary actions), status cards with VLG colour + readiness score.
   - Constraint: do not execute this cosmetic work until Tier 1–2 hardening is
     complete.

2. **Phase B (Prototype): Streamlit**
   - Goal: rapid operator feedback on payload usefulness.
   - Reuses `OperatorConsoleService` payloads directly.
   - No governance/science logic is duplicated in the UI.

3. **Phase C (Production): React + FastAPI**
   - Goal: multi-user, role-aware, production-grade web experience.
   - FastAPI acts as a thin API facade over existing TITAN services.
   - React consumes the API for dashboard/explorer/calibration/override flows.

## Non-negotiable Constraints
- `OperatorConsoleService` remains the source of business payload contracts.
- Governance decisions stay in core science modules.
- UI layers may format, filter, and paginate but must not re-implement safety gates.
- Manual override writes always persist through existing database/audit APIs.
- Data integrity and observability hardening take precedence over all terminal
  cosmetic updates.

## Exit Criteria
- Phase A is unblocked only after Tier 1–2 hardening completion is verified.
- Phase B validated with internal operator usage.
- Phase C accepted when all Phase 6 payloads are reachable through API endpoints
  with equivalent contract semantics.
