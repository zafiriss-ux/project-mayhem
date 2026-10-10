# ADR-0064: H2 fires on an HRV drop of 15 ms or 30% of baseline, whichever comes first

**Status:** PROPOSED (accepted on merge of this PR)
**Date:** 2026-10-10
**Author:** Zaf (Owner, decision) / Claude (implementation)
**Related:** ADR-0009 (governance_engine architecture lock), ADR-0052 (hard-stop thresholds are
not adapted per athlete), SV-10 in `docs/validation/synthetic-athlete-report.md`, D-059 in
`DECISIONS.md`

---

## Context

The H2 hard stop (HRV collapse → REST) fired when today's HRV was `HARD_STOP_HRV_DELTA` (15 ms) or
more below the baseline. An absolute number weighs differently per athlete: 15 ms is 30% of a
50 ms baseline but 43% of a 35 ms one. The synthetic athlete `senior_m` dropped from 34.6 to
20.2 ms (−42%, 14.4 ms) and H2 did not fire (finding SV-10). Vesterinen et al. 2016 define the
meaningful HRV change per athlete, not in absolute ms.

`governance_engine.py` is architecture-locked (ADR-0009, AGENTS §8). On 2026-10-10 Zaf chose, on
a decision card, "15 ms or 30%": rest on whichever threshold is reached first.

---

## Decision

1. **New threshold.** `HARD_STOP_HRV_DROP_PCT = 0.30` in `titan/config/thresholds.py`, with an
   evidence entry (HEURISTIC). It joins `HARD_STOP_THRESHOLD_KEYS`, so it is never adapted per
   athlete (ADR-0052).
2. **One rule, three places.** `GovernanceEngine.h2_drop_threshold_ms(baseline)` returns
   `min(15 ms, 30% × baseline)`, or 15 ms when the baseline is not positive. The H2 gate, the
   stress-context classifier (`UNEXPLAINED_MODERATE`) and the H2 audit finding all use it, so the
   decision, the classification and the explanation agree.
3. The boundary stays inclusive (a drop equal to the threshold fires). Missing or non-numeric HRV
   keeps the ADR-0051 EASY ceiling. H1, H3–H5 do not change.

---

## Consequences

- H2 is stricter only for baselines below 50 ms; at 50 ms and above the threshold is still 15 ms.
  It never becomes looser for anyone.
- In the characterization goldens no decision changes. The 11/3 H2 explanation shows the
  athlete's threshold (14.88 ms at a 49.6 ms baseline) instead of 15.0.
- The evidence entry for `HARD_STOP_HRV_DELTA` describes "a 15% drop" with a dual HRV+RHR trigger,
  while the code has always used 15 ms with OR semantics. That text is left as is here and noted
  for the end-of-phase docs check.

## Not changed

- `HARD_STOP_HRV_DELTA` (15 ms), H1, H3–H5, the 2-of-4 rule, the HRV drift detector.
- `CANONICAL_LOCK_CODES`.
