# Operator Console — Session Explorer Spec

| Field | Value |
|-------|-------|
| **Status** | Implemented (Phase 6 task 2) |
| **Layer** | `titan/ui/` |
| **Module** | `titan/ui/operator_console.py` |
| **Tests** | `tests/test_operator_console_dashboard.py` |
| **Related ADR** | [0011-operator-console-session-explorer.md](../adr/0011-operator-console-session-explorer.md) |

## Purpose
Provide a stable payload for operator log review with governance decision trail and manual annotations.

## Inputs
- `DatabaseManager.get_governance_decisions(limit=N)`

## Outputs
- `sessions[]`
  - `date`, `phase`, `vlg_color`
  - `manual_annotation`
  - `decision_trail[]` with `planned`, `post_governance`, and optional `completed` steps
- `summary`
  - `samples`
  - `annotated_sessions`
  - `sessions_with_locks`

## Mutation Boundary
- `OperatorConsoleService.add_manual_annotation()` writes only `outcome_notes` through
  `DatabaseManager.annotate_governance_outcome()`.
- No governance/science decision logic is changed.
