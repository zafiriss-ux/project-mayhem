# ADR-0022 — Phase 8 Entry Gate: Architectural Readiness Criteria

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Master Risk Matrix — Risk #16 (Phase Transition Risk P1→P2)
**Phase:** 7.8 Hardening — Pre-Phase-8 gate definition

---

## Context

ADR-0016 accepted the multi-sport scope for Phase 8 and defined a high-level adapter
pattern. ADR-0015 locked single-athlete scope for the current SQLite kernel. However,
neither ADR defines the *entry criteria* that the kernel must satisfy before Phase 8
implementation work begins.

Risk #16 in the Master Risk Matrix is classified as **Low probability, Critical severity**
and ranked #1 overall because structural deficiencies introduced before a phase transition
are invisible until the transition amplifies them. The current kernel has:

- A `DailyCoach` god-orchestrator with 12 tightly-coupled steps (ADR-0017 audit: Phase B
  deferred).
- A `DatabaseManager` with a single SQLite file and no schema migration versioning at the
  application level until T1-16 (resolved 2026-03-06).
- A composition root (`main.py`) that instantiates all engines directly, making adapter
  injection non-trivial (ADR-0018 Phase B: deferred).
- Three background daemon threads without a unified lifecycle supervisor (ADR-0018
  Phase B: deferred).

Attempting Phase 8 work while these structural items are deferred concentrates the
blast radius of architectural rework: schema changes, adapter injection, and lifecycle
management all become load-bearing at once.

---

## Decision

**Phase 8 implementation is gated.** No Phase 8 code may be written until all criteria
in the binary gate below are TRUE.

### Phase 8 Entry Gate (all items required — binary)

| # | Gate Criterion | Verification |
|---|---|---|
| G1 | All `TECHNICAL_DEBT.md` Tier 1–4 items CLOSED (no OPEN/PARTIALLY RESOLVED) | `grep -E "OPEN|PARTIALLY" TECHNICAL_DEBT.md` → zero matches |
| G2 | `tests/test_architectural_invariants.py` 100% green (T4-19 complete) | `python -m pytest tests/test_architectural_invariants.py -v` |
| G3 | `ADR-0018 Phase B` accepted and a scoped implementation plan documented | ADR-0018 status = "Phase B Accepted" |
| G4 | `ADR-0017` composition root audit complete: all fan-in paths documented, no new god-object paths introduced | ADR-0017 status updated with "Phase B Documented" |
| G5 | Schema version tracking active (`PRAGMA user_version`) and bumped on every migration (T1-16) | `python -c "import titan.core.database; d=titan.core.database.DatabaseManager(':memory:'); print('ok')"` → no error; DB has `user_version > 0` |
| G6 | Hot backup strategy operational (T1-17) | `python -m pytest tests/ -k backup -v` → green |
| G7 | Full test suite green with count ≥ 1122 (Phase 7 close baseline) | `python -m pytest -q` → 0 failures, 0 errors |
| G8 | A new **ADR-0022-review** written by architect acknowledging all gates above as PASSED | File `docs/adr/0022-review-phase8-go.md` exists |

### Gate Enforcement

This gate is not automated in CI — it is a **human architectural checkpoint**. Before
any Phase 8 branch is created:

1. The responsible engineer runs all verification commands in the table above.
2. The results are pasted into a `docs/adr/0022-review-phase8-go.md` file.
3. The architect reviews and approves the go/no-go decision.
4. Only after approval is a Phase 8 feature branch created.

A PR that contains Phase 8 code without the `0022-review-phase8-go.md` file is a
**PROCESS VIOLATION** and must be closed without merge.

---

## Options Considered

### Option A — Start Phase 8 immediately after Phase 7 closes
**Rejected.** ADR-0017 and ADR-0018 Phase B remain deferred. Injecting adapters into a
god-orchestrator mid-phase creates rework debt that compounds exponentially.

### Option B — Define a soft recommendation (not a hard gate)
**Rejected.** "Soft recommendation" is the failure mode that produced T4-01 (750 Ruff
errors). Hard gates with binary outcomes are the only proven mechanism in this codebase.

### Option C — Binary entry gate with architect review (SELECTED)
Matches the existing discipline in CLAUDE.md Rules E1–E5. Consistent with the tier
ordering model. Low overhead: the gate only needs to be checked once, at the phase
boundary.

---

## Consequences

**Positive:**
- Prevents architectural debt from compounding across a phase boundary.
- Creates a mandatory architectural checkpoint before scope expands.
- Forces ADR-0017 Phase B and ADR-0018 Phase B to be addressed before Phase 8.

**Neutral:**
- Delays Phase 8 start date until all gates pass. This is intentional.
- The gate review document becomes part of the permanent architectural record.

**Negative:**
- None. The only "cost" is writing the gate review document, which is a 30-minute task.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0015 | SQLite retention — G5 (schema version tracking) depends on T1-16 completion. |
| ADR-0016 | Multi-sport scope — Phase 8 implementation scope. This ADR gates its start. |
| ADR-0017 | Composition root audit — G4 requires Phase B documentation. |
| ADR-0018 | Kernel boundary — G3 requires Phase B acceptance. |

---

## Status

Accepted. No engineering execution item — this is a process gate. Reference this ADR
when evaluating Phase 8 readiness.
