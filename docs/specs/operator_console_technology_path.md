# Operator Console Technology Path

## Scope
Define the delivery path for the Operator Console UI layer while preserving
existing kernel and service boundaries.

## Decision
The UI rollout follows two stages:

1. **Stage A (Prototype): Streamlit**
   - Goal: rapid operator feedback on payload usefulness.
   - Reads `OperatorConsoleService` payloads only.
   - No governance/science logic is duplicated in the UI.

2. **Stage B (Production): React + FastAPI**
   - Goal: multi-user, role-aware, production-grade web experience.
   - FastAPI acts as a thin API facade over existing TITAN services.
   - React consumes the API for dashboard/explorer/calibration/override flows.

## Non-negotiable Constraints
- `OperatorConsoleService` remains the source of business payload contracts.
- Governance decisions stay in core science modules.
- UI layers may format, filter, and paginate but must not re-implement safety gates.
- Manual override writes always persist through existing database/audit APIs.

## Exit Criteria
- Stage A validated with internal operator usage.
- Stage B accepted when all Phase 6 payloads are reachable through API endpoints
  with equivalent contract semantics.
