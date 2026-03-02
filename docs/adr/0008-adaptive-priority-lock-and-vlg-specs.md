# ADR 0008: Adaptive Priority Lock — Layer Placement and Architectural Role

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2026-02-20 |
| **Author** | Architectural audit — `claude/audit-kernel-architecture-CuZiG` |
| **Files** | `docs/adr/0007-adaptive-priority-lock-placement.md` (this file), `docs/specs/adaptive_priority_lock.md`, `docs/specs/volume_load_gauge.md` |
| **Companion specs** | [APL spec](../specs/adaptive_priority_lock.md) · [VLG spec](../specs/volume_load_gauge.md) |

---

## Context

An architectural audit of branch `claude/kernel-restructure-training-plan-0UZmS`
mapped the full modular structure of TITAN v5.7 (Closed-Loop Sovereign) and
identified a gap in the governance pipeline.

### Current governance model

`GovernanceEngine` (`titan/science/governance_engine.py`) evaluates three hard
binary gates in a **fixed sequence** with **static thresholds**:

1. `PARASYMPATHETIC_GUARD` — triggered when HRV >> baseline + HRR impaired
2. `OVERRIDE_LOCKDOWN` — triggered when 14-day quality session ratio > 80%
3. `CS_CONFIDENCE_LOCK` — triggered when Critical Speed model confidence < 70%

This model is correct and its hard-gate semantics must be preserved. However,
two limitations exist:

**Limitation 1 — Fixed evaluation order.**
A PEAK-phase athlete with a confident CS model faces the same gate priority
sequence as a BASE-phase athlete accumulating volume. In PEAK, CS accuracy is
critical for race simulation sessions; `CS_CONFIDENCE_LOCK` should rank above
`OVERRIDE_LOCKDOWN`. The fixed sequence cannot express this.

**Limitation 2 — Static thresholds.**
The ACWR ceiling, TSB floor, and CS confidence minimum are fixed inside
`GovernanceEngine`. A TAPER athlete (intentionally lowering load) and a BUILD
athlete at peak weekly volume warrant different threshold values. Static
constants cannot adapt.

### Volume Load Gauge gap

Three load-state engines (`TSBEngine`, `ACWREngine`, `GlycogenDebtAccumulator`)
are invoked independently in `DailyCoach.run_morning_routine()`. No single
object represents the composite load state of the athlete. Any consumer that
needs "how loaded is the athlete right now?" must import and query three separate
engines. This creates fan-out coupling as new consumers are added.

---

## Decision

### 1. Introduce `VolumeLoadGauge` in `titan/science/`

A new module `titan/science/volume_load_gauge.py` will aggregate `TSBEngine`,
`ACWREngine`, and `GlycogenDebtAccumulator` outputs into a single `VLGState`
dataclass. It performs no new computation — it is a pure aggregator.

**Justification for `titan/science/` placement:**

- It is a computation module, not UI (`titan/ui/`), not integration
  (`titan/integrations/`), not a sequence step (`titan/orchestration/`).
- All other load-state engines live in `titan/science/`.
- It has no DB access and no side effects — consistent with science layer
  contract.

### 2. Introduce `AdaptivePriorityLock` in `titan/science/`

A new module `titan/science/adaptive_priority_lock.py` will act as a
pre-governance priority resolver. It consumes `VLGState`, AFI constraints,
training phase, and CS confidence, and produces a `priority_vector` dict and
adaptive `lock_thresholds` dict.

**Justification for `titan/science/` placement (over alternatives):**

| Candidate layer | Verdict | Reason |
|-----------------|---------|--------|
| `titan/science/` | **Selected** | APL performs physiological reasoning; no I/O, no sequencing |
| `titan/orchestration/` | Rejected | Orchestration sequences; it does not compute priorities |
| `titan/features/` | Rejected | Features generate plans; APL resolves meta-governance constraints |
| Inside `governance_engine.py` | Rejected | GovernanceEngine's contract is binary hard gates; injecting phase-awareness violates single responsibility |
| Inside `daily_coach.py` | Rejected | Would make the orchestrator a computation engine |

**Justification for NOT placing APL inside the state machine layer
(`autonomic_engine.py`):**
The autonomic engine is the source of AFI and parasympathetic guard signals.
APL is a consumer of those signals, not a producer. Merging them would couple
two distinct responsibilities: autonomic state computation and gate
prioritisation.

**Justification for NOT placing APL inside the gate system
(`governance_engine.py`):**
The governance engine's design principle (documented in `daily_coach.py`
docstring: "non-bypassable gate") requires it to remain a binary enforcer.
APL is advisory (it produces priority ordering) while governance is mandatory
(it enforces locks). These must remain separate.

**Justification for NOT placing APL inside the metrics engine (VLG):**
VLG is a pure aggregator with no reasoning. APL is a resolver with phase-aware
logic. Merging them would give the aggregator responsibilities it should not
have, and would prevent reuse of VLGState by other future consumers.

**Justification for NOT placing APL inside the phase manager
(`core/periodization.py`):**
The phase manager determines training phase from race calendar data. It is a
core data module with no knowledge of governance or gate systems. APL uses
phase as one of four inputs; it must not be embedded in its source.

---

## Consequences

### Positive

- `GovernanceEngine` gate logic is unchanged — all three hard gates remain
  binary and non-bypassable.
- `DailyCoach` remains an orchestrator — it passes pre-computed inputs to APL
  and injects the output into governance context.
- Phase-aware and load-aware priority resolution is possible without modifying
  any existing engine.
- `VLGState` provides a reusable single-source-of-truth for composite load
  state, ready for future consumers (ML, web dashboard, team analytics).
- APL is stateless and has no DB access — trivially testable in isolation.

### Negative / Trade-offs

- Two new modules add to the science layer (currently 17 modules after v5.7
  additions). The science layer grows but remains coherent.
- `GovernanceEngine.apply_constraints()` must be extended to read
  `context.get('priority_vector', {})`. This is a one-line read with a safe
  default; backward compatibility is preserved if APL is not injected.
- Implementation requires careful coordination: VLG must be implemented before
  APL; APL must be implemented before `GovernanceEngine` reads it.

### Not changed

- No existing Python files are modified by this ADR.
- No existing gate conditions, EMA constants, or engine interfaces are altered.
- No runtime behaviour changes until implementation is complete and APL is
  injected into `DailyCoach`.

---

## Layer Summary

```
titan/science/
  volume_load_gauge.py          NEW — aggregates TSB + ACWR + Glycogen → VLGState
  adaptive_priority_lock.py     NEW — resolves gate priority + thresholds → priority_vector

titan/orchestration/
  daily_coach.py                UNCHANGED (future: receives optional APL injection)

titan/science/
  governance_engine.py          UNCHANGED (future: reads priority_vector from context)
```

---

## References

- `titan/orchestration/daily_coach.py` — 12-step morning routine; Step 9b is
  the governance call site
- `titan/science/governance_engine.py` — three hard gates, current static logic
- `titan/science/autonomic_engine.py` — AFI computation, para guard
- `titan/science/tsb_engine.py` — CTL/ATL/TSB source
- `titan/science/acwr_engine.py` — ACWR source
- `titan/science/glycogen_model.py` — glycogen debt source
- `titan/core/periodization.py` — phase source
- `titan/science/critical_speed.py` — CS confidence source
- [APL full specification](../specs/adaptive_priority_lock.md)
- [VLG specification](../specs/volume_load_gauge.md)
