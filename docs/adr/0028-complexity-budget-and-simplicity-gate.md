# ADR-0028 — Complexity Budget and Simplicity Gate

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Architect Observations V6 — Risk #4 (Complexity Accumulation) + Risk #8 (Over-Engineering Plateau)
**Phase:** 7.8 Hardening

---

## Context

### The Accumulation Problem

At Phase 7 close, TITAN OS comprises:
- **46 modules** (excl. `__init__`/`__main__`)
- **1122+ tests** across 21 test files
- **26 ADRs**
- **21 debt items** resolved, 11 open
- **7-gate governance engine** with mutation test coverage

This is not yet problematic — it reflects genuine requirements. The risk is
**trajectory**: each phase adds modules, tests, and docs proportionally to scope.
Phase 8 (multi-sport adapters) and Phase 9 (lifecycle supervisor) each carry significant
scope. Without a complexity budget, the system risks:

1. **Test maintenance overhead exceeding feature velocity.** When changing one module
   requires updating 8 test files, engineers (and agents) start taking shortcuts.

2. **Module proliferation without consolidation.** New features create new modules;
   old modules that have been superseded or can be merged are never removed. The module
   count becomes a cognitive load problem (Risk #7 in the Master Risk Matrix).

3. **Governance overhead ossifying the system.** ADRs, debt items, checklist gates, and
   CI jobs are all valuable individually. Collectively, if each phase adds 5–7 new
   governance artifacts with no retirement mechanism, the governance system itself
   becomes the bottleneck.

4. **Over-engineering plateau.** New features are over-engineered because the precedent
   set by existing (correctly complex) components like `GovernanceEngine` gets applied
   to simpler problems that do not warrant the same investment.

### Observable Early Signals

- ADR-0017 (composition root audit) is "assessment only" — the finding was documented
  but the recommended refactor was explicitly deferred. This is correct engineering, but
  it means the complexity it identified has accumulated for 2+ phases without resolution.
- ADR-0018 Phase B (effect runner split) is deferred. The `DailyCoach` god-orchestrator
  (12 tightly-coupled steps) grows with each phase.
- Phase 8 will require multi-sport adapters: if added to `DailyCoach` directly, it
  reaches ~20 steps. This is the point at which changes become risky.

---

## Decision

**Introduce a Complexity Budget as a formal governance constraint, enforced at phase
boundaries and measured by four metrics.**

### Metric 1 — Module Count Ceiling

**Current:** 46 modules. **Budget ceiling:** 60 modules at Phase 8 close.

If Phase 8 would push the count above 60, the architect must either:
(a) identify modules to merge or retire before the new modules are added, OR
(b) explicitly accept the exception in an ADR update (with a revised ceiling).

**Rationale:** 60 is not an arbitrary limit — it is the point at which a single engineer
can no longer hold the full module graph in working memory without reference. The
current 46 is within comfortable range; the ceiling creates a trigger for consolidation
before the system becomes cognitively unmanageable.

**Measurement:**
```bash
python -c "
import pkgutil, titan
mods = list(pkgutil.walk_packages(titan.__path__, 'titan.'))
real = [m for m in mods if '__' not in m.name]
print(f'Module count: {len(real)}')
assert len(real) <= 60, f'COMPLEXITY BUDGET EXCEEDED: {len(real)} modules'
"
```

This check is added to `tests/test_documentation_consistency.py` (T4-21).

### Metric 2 — Test-to-Code Ratio Guard

**Target:** 1 test file per production module (or shared test file per subsystem).
**Budget violation:** Any production module with >200 lines that has zero direct test
coverage (excluding integration tests).

This is already partially enforced by the Test Creation Rule in `CLAUDE.md`. The
complexity budget makes it explicit: high line-count modules without direct tests are
a complexity debt indicator, not just a coverage gap.

### Metric 3 — ADR Retirement Protocol

ADRs accumulate. Once a decision is superseded, the original ADR should be marked
`Superseded by [NNNN]` rather than left as `Implemented`. This is already the convention
but not consistently applied.

**New rule:** Every phase close review must check:
- Are there ADRs marked `Implemented` that are now fully superseded by a later ADR?
- If yes, update status to `Superseded by [NNNN]`.
- Do not delete ADRs — the history is valuable. Only update the status.

This is a 15-minute phase-close task, not an engineering item.

### Metric 4 — Phase Boundary Simplicity Review

Before any phase begins (not just Phase 8), the architect performs a **Simplicity
Review**:

> "Given what we know now, which existing modules could be merged, simplified, or
> removed without reducing capability? What did we over-engineer in the last phase?"

The output is one of:
- "Nothing to consolidate — proceed."
- "Module X can be merged into Y — add T-item before Phase N work begins."
- "ADR-000N Phase B can be deferred permanently — update status to Superseded."

This review is not a veto — it is a forcing function to surface consolidation
opportunities before new complexity is added on top of unnecessary existing complexity.

### Complexity Gate for Phase 8 (supplement to ADR-0022)

Add to the **Phase 8 Entry Gate** (ADR-0022):

> **G9 — Simplicity Review:** The Phase 8 Simplicity Review has been conducted and
> its output documented in `docs/adr/0022-review-phase8-go.md`. Even if the output is
> "nothing to consolidate", the review must have been performed.

---

## What This ADR Does NOT Do

- It does not impose a line-count limit on individual modules. Function-level complexity
  belongs to code review, not architectural governance.
- It does not mandate refactoring existing modules below the ceiling. The ceiling is a
  trigger for review, not a mandatory reduction target.
- It does not retire the governance engine or reduce test coverage. The existing
  governance investment is correct and must be preserved (Appendix B of
  `TECHNICAL_DEBT.md`).

---

## Options Considered

### Option A — No formal complexity budget (current state)
Complexity is managed informally through code review and ADR process.

**Rejected.** The trajectory is clear: each phase adds ~5–8 modules. Without a
ceiling, Phase 9 reaches 65+ modules. The informal process has not triggered a
consolidation review in 7 phases.

### Option B — Strict module count freeze
No new modules may be added unless an existing module is removed.

**Rejected.** Too rigid. Phase 8 legitimately requires new adapter modules. The budget
should trigger a review, not block progress.

### Option C — Ceiling + retirement protocol + phase boundary review (SELECTED)
Creates a review trigger without blocking legitimate growth. Consistent with the
binary gate philosophy: the simplicity review either finds opportunities (consolidate)
or clears the phase (proceed). No ambiguity.

---

## Consequences

**Positive:**
- Complexity growth is tracked, not just observed retrospectively.
- Phase boundaries become natural consolidation checkpoints.
- The module count metric is machine-measurable in CI.

**Neutral:**
- The Simplicity Review adds ~30 minutes to each phase transition. This is
  intentional overhead — less than the cost of one debugging session caused by
  unnecessary complexity.

**Negative:**
- The 60-module ceiling is heuristic. It may need revision if Phase 8 scope expands
  significantly. The revision process is: update this ADR with a new ceiling and
  document the rationale.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0022 | Phase 8 Entry Gate. G9 (Simplicity Review) is added as a gate criterion. |
| ADR-0017 | Composition root audit — the deferred finding is a concrete candidate for the Phase 8 Simplicity Review. |
| ADR-0018 | Phase B deferral — another Simplicity Review candidate. |

---

## Status

Accepted. Engineering execution: **T4-27** (CI module count check; ~1h).
Phase boundary Simplicity Review: process artifact (no code item).
