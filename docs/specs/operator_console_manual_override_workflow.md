# Operator Console Manual Override Workflow — Spec

| Field | Value |
|---|---|
| **Status** | Implemented (Phase 6 task 4) |
| **Owner** | TITAN OS Core |
| **Last Updated** | 2026-03-02 |

## Goal
Surface the existing override audit trail (already persisted in `override_log`) through
Operator Console payloads, so operators can review recent manual overrides and their
frequency without direct DB access.

## Scope
- `OperatorConsoleService.manual_override_workflow(limit=50, days=14)` returns:
  - `summary.samples`
  - `summary.override_ratio_window_days`
  - `summary.override_ratio`
  - `summary.latest_override_date`
  - `overrides[]` entries with `date`, `prescribed_type`, `actual_type`, `reason`
- `OperatorConsoleService.record_manual_override(...)` persists override rows.

## Data Source
- `override_log` table (`titan/core/database.py`)
- Existing ratio calculation: `DatabaseManager.get_override_ratio(days=14)`

## Non-Goals
- No changes to governance decision logic.
- No UI rendering implementation in this phase.
- No new persistence schema.
