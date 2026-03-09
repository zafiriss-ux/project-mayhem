# ADR-0047 — Architecture Fitness Functions

**Date:** 2026-03-09
**Status:** Accepted
**Deciders:** Architect
**Source:** Process review memo — Debt-Clear Window session (2026-03-09); Architect DEC (NEW_DEBT_ENTRY deferred to ADR_NEEDED)
**Phase:** Phase 8 — pre-implementation gate; no engineering execution before ADR is accepted
**Related:** ADR-0027 (Hidden Inter-Module Coupling Prevention), ADR-0022 (Phase 8 Entry Gate)

---

## Context

TITAN OS currently has two lightweight structural tests that function as implicit fitness
functions:

1. `tests/test_claude_md_integrity.py` — enforces that `TECHNICAL_DEBT.md` is the
   canonical operational state and that `CLAUDE.md` does not claim phases closed while
   debt items remain OPEN.
2. `tests/test_architectural_invariants.py` — enforces cross-layer import boundaries
   (science must not import from orchestration, etc.) per ADR-0027.

These are point solutions, not a systematic fitness function framework. As the codebase
grows into Phase 8 (multi-sport, multi-athlete, PostgreSQL migration), three structural
risks emerge that are not currently covered:

**Risk F1 — Cyclomatic complexity drift:**
`DailyCoach.run_morning_routine()` is a 12-step orchestrator with known intentional
complexity (ADR-0017: god-orchestrator audit). However, science modules are expected to
remain low-complexity. Without a threshold gate, complexity accumulates invisibly across
the 26-module science layer.

**Risk F2 — Inter-module coupling ratio growth:**
ADR-0027 prevents illegal cross-layer imports but does not measure coupling density
within layers. As Phase 8 adds adapters, the science layer's internal coupling surface
could grow beyond the point where individual modules can be tested in isolation.

**Risk F3 — Dependency drift from approved topology:**
The TITAN module topology is defined by the layered architecture (Config → Core →
Science → Governance → Features → Integrations → Orchestration → UI). New Phase 8
modules must not introduce dependency edges that invert this ordering in ways that
ADR-0027's import test does not catch (e.g., a new adapter that creates a circular
dependency through a shared utility).

---

## Decision

**Introduce a structured Architecture Fitness Function suite as a new test file
(`tests/test_architecture_fitness.py`), with three gates covering the three risks
above. No single module is exempt by default — exemptions are declared explicitly.**

### Gate F1 — Cyclomatic Complexity Threshold

**Tool:** `radon` (already available in the Python ecosystem; lightweight, no new
runtime dependency if added to `requirements.txt` as a dev dependency).

**Rule:** No module in `titan/science/`, `titan/features/`, `titan/core/`, or
`titan/config/` may contain a function with cyclomatic complexity > 10.

**Exemptions (explicit, not default):**
- `titan/orchestration/daily_coach.py` — `run_morning_routine()` is architecture-locked
  at its current complexity per ADR-0017. Exempt until ADR-0017 is superseded.
- `titan/ui/operator_console.py` — UI dispatch functions are permitted up to complexity
  15 (UI fan-out is structural, not logical branching).

**Test implementation sketch:**
```python
# tests/test_architecture_fitness.py
import radon.complexity as radon_cc
import ast, pathlib

COMPLEXITY_LIMIT = 10
EXEMPT_PATHS = {
    "titan/orchestration/daily_coach.py": 999,   # ADR-0017 exemption
    "titan/ui/operator_console.py": 15,           # UI fan-out exemption
}

def test_cyclomatic_complexity_gate():
    root = pathlib.Path("titan")
    violations = []
    for path in root.rglob("*.py"):
        limit = EXEMPT_PATHS.get(str(path), COMPLEXITY_LIMIT)
        source = path.read_text()
        blocks = radon_cc.cc_visit(source)
        for block in blocks:
            if block.complexity > limit:
                violations.append(f"{path}::{block.name} complexity={block.complexity} > {limit}")
    assert not violations, "Complexity violations:\n" + "\n".join(violations)
```

### Gate F2 — Intra-layer Coupling Ratio

**Tool:** Custom AST import walker (no new dependency; uses `ast` from stdlib).

**Rule:** No module within `titan/science/` may import from more than 6 other
`titan/science/` modules. This caps the fan-in coupling density per science module.

**Rationale for 6:** Current maximum in the science layer is `GovernanceEngine` which
legitimately imports from ~5 science engines. The limit of 6 allows one additional
import for Phase 8 expansion before triggering a review. Any module needing more than
6 intra-layer imports is a candidate for decomposition.

**Exemptions:** None. `GovernanceEngine` is currently at ~5; if a new Phase 8 engine
approaches 6, that is an early warning signal that decomposition is needed.

### Gate F3 — Dependency Topology Integrity

**Tool:** Extends the existing `tests/test_architectural_invariants.py` coupling test
(ADR-0027, G4b) with an additional directed-graph check.

**Rule:** The import graph of all `titan/` modules must be a DAG (directed acyclic
graph) when analyzed at the package level. Any cycle — even one mediated through a
shared utility — is a violation.

**Implementation:** Use `importlab` or a custom `ast`-based walker to build the import
graph and assert acyclicity. The existing cross-layer import test in
`test_architectural_invariants.py` is complementary (it checks direction); this gate
checks cyclicity.

---

## Options Considered

### Option A — `lizard` instead of `radon` for complexity
`lizard` supports more languages and has a richer CLI. Rejected: TITAN is Python-only
and `radon` has a more Pythonic API for integration into pytest. No advantage for
this codebase.

### Option B — Full `pylint` / `wily` integration
`pylint` and `wily` offer comprehensive metrics dashboards. Rejected for gate use:
they produce too many non-binary outputs and require configuration investment that
goes beyond the current scope. `wily` is appropriate for trend tracking (deferred
to Phase 9 / DORA-adjacent tooling).

### Option C — Per-function coupling metrics (afferent/efferent coupling, CBO)
Class-level coupling metrics (like CBO from the C&K metrics suite) would be more
precise. Rejected: TITAN uses module-level organisation, not class hierarchies.
Module-level import count is the right granularity for this codebase's structure.

### Option D — No fitness functions (status quo)
Rejected. At Phase 8 scale (multi-sport adapters, multi-athlete model, PostgreSQL),
the two existing point tests are insufficient. The three risks above are not
hypothetical — they are projectable from the current module count trajectory.

---

## Consequences

**Positive:**
- Structural regressions (complexity creep, coupling growth, topology violations) become
  test failures — caught in CI before merge, not post-hoc in architecture reviews.
- Exemptions are explicit and traceable — the test file is the single source of truth
  for what is permitted to be complex or coupled, and why.
- Gate F1 and F2 are additive tests — they do not change any existing module behaviour.

**Neutral:**
- `radon` must be added to `requirements.txt` as a dev dependency. It is actively
  maintained, MIT-licensed, and has no transitive dependencies beyond the stdlib.
- Gate F3 shares implementation surface with ADR-0027's coupling test — these must
  be kept coherent. Owner-of-Record for both: Architecture subsystem.

**Negative:**
- Exemptions require maintenance. If `run_morning_routine()` is refactored (Phase 8B
  per ADR-0018), the exemption entry must be removed or updated. This is a process
  obligation, not a technical risk.
- The complexity limit of 10 is a heuristic (McCabe 1976 recommendation), not a
  derivation from TITAN-specific data. It will need recalibration after Gate F1
  runs on the full codebase for the first time.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0027 | Gate F3 extends the G4b coupling audit. Complementary — ADR-0027 checks import direction; this ADR checks cycle presence and intra-layer density. |
| ADR-0022 | Phase 8 Entry Gate. Gate F1, F2, F3 are recommended as additional criteria for G4 once the fitness suite is established and baseline-calibrated. |
| ADR-0017 | God-orchestrator audit. `DailyCoach` complexity exemption in Gate F1 is explicitly tied to ADR-0017's assessment; removing the exemption requires updating ADR-0017 or superseding it. |
| ADR-0018 | Kernel boundary (Phase B). If Phase B fully splits `DailyCoach`, the Gate F1 exemption for `daily_coach.py` should be removed at that point. |

---

## Engineering Execution

**Task:** T8-01 (Tier 1 — new test file; no module changes; independent)

**Acceptance criteria (binary):**
1. `radon` added to `requirements.txt` as a dev dependency (pinned to current stable version).
2. `tests/test_architecture_fitness.py` created with Gate F1, F2, F3 tests.
3. All three gates pass on the current codebase (zero violations or exemptions applied).
4. `python -m pytest tests/test_architecture_fitness.py -v` → all green.
5. Full canonical suite (`python -m pytest -q`) count same or higher.

**Workflow Path:** Path A (standard)

**Owner-of-Record:** Architecture subsystem

---

## Status

Accepted. Engineering execution: **T8-01** (Tier 1 — independent; no existing-module changes).
Task to be written in `TECHNICAL_DEBT.md` by architect before assignment to Codex.
