# ADR-0062: RED intensity gate keeps 70% volume, and a 0.0 modifier stays 0.0

**Status:** PROPOSED (accepted on merge of this PR)
**Date:** 2026-10-10
**Author:** Zaf (Owner, decision) / Claude (implementation)
**Related:** ADR-0009 (governance_engine architecture lock), ADR-0051 (missing data),
SV-20 in `docs/validation/synthetic-athlete-report.md`, D-057 in `DECISIONS.md`

---

## Context

When the intensity gate (`IntensityGovernor`) returns RED, it sets `volume_modifier = 0.0` and
`session_override = "EASY"`. `GovernanceEngine` reads the modifier with
`float(gate.get("volume_modifier", CONSERVATIVE) or CONSERVATIVE)`. Because `0.0 or 0.7` is
`0.7`, every RED morning became EASY at 70% of the planned volume, not "EASY 0 km". The
synthetic athletes showed 130 RED mornings, all at 70% (finding SV-20, found in #982).

So the athlete-facing behavior was right by accident: the code said 0% and did 70%, and any
gate that one day sends a genuine 0.0 would silently get 70%.

`governance_engine.py` is architecture-locked (ADR-0009, AGENTS §8). On 2026-10-10 Zaf chose,
on a decision card, "EASY 70% (as now)": keep what the athlete sees and make the code say it.

---

## Decision

1. **RED keeps 70% volume, explicitly.** `IntensityGovernor` returns
   `INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE` (0.7, ADR-0051) for RED instead of 0.0. No new
   threshold: it is the existing conservative modifier.
2. **A modifier of 0.0 is read as 0.0.** `GovernanceEngine` falls back to the conservative
   modifier only when `volume_modifier` is missing (`None`), not when it is `0.0`.
3. Nothing else in `governance_engine.py` changes: no gate, threshold, lock code or order.

---

## Consequences

- Every morning decision stays the same (characterization goldens and the synthetic athletes
  are unchanged in sessions and volumes).
- `GateResult.volume_modifier` for RED is 0.7 in the audit and the trace, matching what is
  applied.
- A future gate that sends 0.0 gets 0.0. `test_zero_volume_modifier_is_not_replaced` pins it.

## Not changed

- H1–H5 hard stops, the 2-of-4 rule, VO2, fueling and APL gates.
- `CANONICAL_LOCK_CODES`; `INTENSITY_GATE_RED` is still applied on RED.
