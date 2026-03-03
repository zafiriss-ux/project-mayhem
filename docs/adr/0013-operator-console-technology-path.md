# ADR-0013: Operator Console Technology Path

- **Status**: Accepted
- **Date**: 2026-03-02
- **Decision Makers**: TITAN OS Core

## Context
Phase 6 deliverables 1–4 established stable service payloads for dashboard,
session explorer, calibration review, and manual override workflow. A formal
technology path is required before production UI investment.

## Decision
Adopt a three-phase UI evolution path:

1. **Phase A (Terminal facelift)**: retro-HUD startup snapshot, action rail
   (primary + secondary actions), and status cards showing VLG color plus
   readiness score.
2. **Phase B (Streamlit prototype)** for rapid operational validation using
   `OperatorConsoleService` payloads directly.
3. **Phase C (React + FastAPI production stack)** for scalable deployment.

Phase A is explicitly **deferred**: no terminal cosmetic investment proceeds
until Tier 1–2 hardening is complete. Data integrity and observability remain
higher priority than terminal styling.

The API/UI layer stays outside governance/science logic and consumes existing
service contracts from `titan/ui/operator_console.py`.

## Consequences
- Closes Phase 6 task 5 in roadmap without architectural refactor.
- Preserves kernel boundaries and keeps decision logic centralized.
- Enables incremental rollout from terminal parity to prototype learning and
  finally production hardening.

## References
- `docs/specs/operator_console_technology_path.md`
- `docs/ROADMAP.MD`
