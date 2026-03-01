# TITAN OS — Development Roadmap

## Philosophy
Stability first. Architecture before features. No uncontrolled iteration.

---

## Phase 0 — Stabilization (CLOSED)
- main branch cleaned and protected
- Docs-only APL/VLG specification created
- Issue tracking enabled

---

## Phase 1 — Product Definition (CLOSED)
Goal: Define TITAN OS official kernel baseline.

- Modular kernel branch promoted to main
- Clean runtime verified
- main branch protection rules locked
- Architecture frozen

---

## Phase 2 — Architectural Rails (CLOSED)
Goal: Prevent future architectural drift.

- ADR discipline enforced (ADRs 0001–0007)
- PR template with scope declaration
- docs-before-code rule established
- Issue templates (Feature / Engine / Refactor)

Deliverable: Controlled development pipeline

---

## Phase 3 — Engine Implementation (IN PROGRESS)
Goal: Introduce governance infrastructure and safety rails safely.

### Completed

- `volume_load_gauge.py` — IMPLEMENTED (pure aggregation: TSB + ACWR + glycogen → VLGState)
- `governance_engine.py` — REWROTE (corrupted V1–V5 gates fixed; thresholds from `config/thresholds.py`)
- `governance_contracts.py` — IMPLEMENTED (output shape + structural invariant validation at governance→orchestration boundary)
- `intensity_governor.py` — IMPLEMENTED (GREEN/YELLOW/RED graduated enforcement + GateResult dataclass)
- Governance integration — IMPLEMENTED (non-bypassable Step 9 in DailyCoach 12-step routine)
- Unit + integration tests — IMPLEMENTED (27 governance integration tests, 14 P0 safety gate tests)
- CI validation — IMPLEMENTED (ci.yml: test matrix, determinism job, env-policy job)
- Security: argv redaction in launcher — IMPLEMENTED
- Specs cherry-picked to main: `docs/specs/adaptive_priority_lock.md`, `docs/specs/volume_load_gauge.md`
- ADR-0008: Adaptive Priority Lock and VLG specs

### Remaining

- `adaptive_priority_lock.py` — NEXT (follow spec in `docs/specs/adaptive_priority_lock.md`)
  Non-negotiable rule: no gate modification before APL exists.

---

## Phase 4 — Observability & E2E (PLANNED)
Goal: Production-grade visibility and regression safety.

Order:
1. Structured logs for remaining flows (planner, scoring, Telegram handlers)
2. E2E gold-path scenarios (new athlete, weekly plan, recovery adaptation)
3. Snapshot tests for decision stability
4. Smoke checks post-release
5. SLO metrics (error rate, response latency, fallback frequency)

---

## Phase 5 — Web UI / Operator Console (PLANNED)
Goal: Operational visibility before advanced ML investment.

- Readiness + load dashboard
- TSB/CTL/ATL timeline
- Manual review/approve workflow for critical recommendations

---

## Phase 6 — ML Features (PLANNED, after Phase 5)
- LSTM load prediction (shadow mode first, then graduated rollout)
- Injury risk model (ensemble, 15+ features)
- Automated periodization (genetic algorithm)
- Kill-switch for all ML paths

---

## Core Rule

No feature development without:
1. Written specification
2. ADR entry
3. Clear integration boundary

---

This roadmap governs TITAN OS evolution.
Last updated: 2026-03-01
