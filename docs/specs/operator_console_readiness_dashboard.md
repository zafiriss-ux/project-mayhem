# Operator Console — Readiness & Load Dashboard Spec

| Field | Value |
|-------|-------|
| **Status** | Implemented (MVP payload service) |
| **Layer** | `titan/ui/` |
| **Module** | `titan/ui/operator_console.py` |
| **Tests** | `tests/test_operator_console_dashboard.py` |
| **Related ADR** | [0010-operator-console-readiness-dashboard-mvp.md](../adr/0010-operator-console-readiness-dashboard-mvp.md) |

## Purpose
Provide a stable payload for the Phase 6 operator dashboard, exposing timeline and summary data from persisted `governance_outcomes` decisions.

## Inputs
- `DatabaseManager.get_governance_decisions(limit=N)`

## Outputs
- `timeline[]`: `date`, `tsb`, `acwr`, `readiness_score`, `vlg_color`, `phase`
- `summary`: sample count, averages, latest VLG color, VLG distribution

## Integration Boundary
- Read-only boundary: UI/console layer consumes `DatabaseManager`; no writes, no governance logic changes.
- Downstream renderer (Streamlit/React) is external to this service and consumes returned dict payload.
