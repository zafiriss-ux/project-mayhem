# ADR-0013: Operator Console Technology Path

- **Status**: Accepted
- **Date**: 2026-03-02
- **Decision Makers**: TITAN OS Core

## Context
Phase 6 deliverables 1–4 established stable service payloads for dashboard,
session explorer, calibration review, and manual override workflow. A formal
technology path is required before production UI investment.

## Decision
Adopt a two-step path for UI delivery:

1. **Streamlit prototype** for rapid operational validation.
2. **React + FastAPI production stack** for scalable deployment.

The API/UI layer stays outside governance/science logic and consumes existing
service contracts from `titan/ui/operator_console.py`.

## Consequences
- Closes Phase 6 task 5 in roadmap without architectural refactor.
- Preserves kernel boundaries and keeps decision logic centralized.
- Enables incremental rollout: prototype learning first, production hardening next.

## References
- `docs/specs/operator_console_technology_path.md`
- `docs/ROADMAP.MD`
