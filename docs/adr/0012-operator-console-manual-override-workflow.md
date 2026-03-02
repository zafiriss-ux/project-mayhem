# ADR-0012: Operator Console Manual Override Workflow

- **Status**: Accepted
- **Date**: 2026-03-02
- **Decision Makers**: TITAN OS Core

## Context
Phase 6 requires a manual override workflow with audit trail visibility.
The audit data already exists in `override_log`, but it is not exposed via
Operator Console service payloads.

## Decision
Expose override audit trail through `OperatorConsoleService` and keep all
writes/reads on top of the existing `DatabaseManager` API:

1. Add `DatabaseManager.get_override_log(limit)` for ordered audit retrieval.
2. Add `OperatorConsoleService.manual_override_workflow(limit, days)` payload.
3. Add `OperatorConsoleService.record_manual_override(...)` to persist entries.

## Consequences
- Operator Console can review override discipline without direct SQL usage.
- Existing governance architecture and DB schema remain unchanged.
- Phase 6 task 4 is complete; task 5 (technology path) remains.
