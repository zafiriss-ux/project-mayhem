# ADR-0065: A session downgraded by a gate without its own modifier keeps 70% and at most 60 minutes

**Status:** PROPOSED (accepted on merge of this PR)
**Date:** 2026-10-10
**Author:** Zaf (Owner, decision) / Claude (implementation)
**Related:** ADR-0009 (governance_engine architecture lock), ADR-0051 (missing data, the 0.7
conservative modifier), ADR-0062 (RED keeps 70%), D-043 (the intensity gate's modifier is applied),
SV-04 in `docs/validation/synthetic-athlete-report.md`, D-060 in `DECISIONS.md`

---

## Context

D-043 (#982) made the intensity gate's volume modifier shrink the session (YELLOW 0.8, RED 0.7).
The other gates that downgrade a session have no modifier: the 2-of-4 rule, the hard stops (H4
"mandatory load reduction" turns a session into EASY, the ADR-0051 data-missing ceilings), the VO2
eligibility gate and the fueling gate. A session they downgrade kept its planned volume. The
synthetic athletes showed `INTERVALS 66' -> EASY 66'`, `RACE 168' -> EASY 168'`, and an H4 day
that kept 22 km / 132' (finding SV-04, rule `reduction_reduces_volume`, 40 mornings).

`governance_engine.py` is architecture-locked (ADR-0009, AGENTS §8). On 2026-10-10 Zaf chose, on a
decision card, "70%, up to 60'".

---

## Decision

1. **Which downgrades.** `GovernanceEngine.apply_constraints` records the session type after the
   intensity gate. If, after the 2-of-4 rule, the hard stops, the VO2 gate and the fueling gate,
   the type is different and is not REST, the session was downgraded by one of them.
2. **How much.** Such a session gets `volume_modifier = 0.7`
   (`INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE`, ADR-0051), or the intensity gate's modifier when
   that is smaller, and `max_duration_min = 60` (new `GOVERNANCE_DOWNGRADE_MAX_DURATION_MIN`, with an
   evidence entry). A `DOWNGRADE_VOLUME` / `REDUCED` gate event records it.
3. **Where it is applied.** `daily_coach._apply_volume_modifier` already scales distance and
   duration by the modifier (D-043). It now also caps the duration at `max_duration_min` and
   shrinks the distance in the same proportion: 22 km / 132' becomes 92', then 60' and 10 km.
4. Not in scope: the intensity gate (it has its own modifier), REST (no volume), and the later
   ceilings (parasympathetic guard, override lockdown, startup data confidence, persistence
   degraded), which Zaf's question did not cover. No lock code is added (ADR-0024).

---

## Consequences

- Downgraded mornings get shorter. In the characterization goldens no session type or lock code
  changes; the VO2 downgrades (`INTERVALS -> TEMPO`) go from 12 km / 66' to 8.4 km / 46', and the
  hard-stop EASY days from 15 km to 10.5 km. None of them reaches the 60' cap after 70%; a unit
  test covers the cap.
- The rule `reduction_reduces_volume` of the synthetic athletes has no violations, so SV-04 leaves
  the `KNOWN` ledger, which is now empty.

## Not changed

- The gates' decisions (session types, zones, lock codes), H1–H5 thresholds, the intensity gate.
