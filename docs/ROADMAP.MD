# TITAN OS — Development Roadmap

## Philosophy
Stability first. Architecture before features. No uncontrolled iteration.

---

## Phase 0 — Stabilization (Completed)
- main branch cleaned and protected
- PR#4 reverted
- launcher removed
- Docs-only APL/VLG specification created
- Issue tracking enabled

Status: CLOSED

---

## Phase 1 — Product Definition
Goal: Define TITAN OS official kernel baseline.

Actions:
- Promote modular kernel branch to main
- Verify clean runtime
- Lock main branch protection rules
- Freeze architecture

Deliverable:
main = Modular TITAN OS kernel (authoritative baseline)

---

## Phase 2 — Architectural Rails
Goal: Prevent future architectural drift.

Actions:
- Enforce ADR discipline
- Enforce docs-before-code rule
- PR template with scope declaration
- Issue templates (Feature / Engine / Refactor)

Deliverable:
Controlled development pipeline

---

## Phase 3 — Engine Implementation (Post 26 Feb)
Goal: Introduce Adaptive Priority Lock safely.

Order:
1. volume_load_gauge.py (pure aggregation layer)
2. adaptive_priority_lock.py (priority resolver)
3. Governance integration (no gate logic modification)
4. Unit tests
5. CI validation

Non-negotiable rule:
No gate modification before VLG exists.

---

## Core Rule

No feature development without:
1. Written specification
2. ADR entry
3. Clear integration boundary

---

This roadmap governs TITAN OS evolution.