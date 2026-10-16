# ADR-0066: Three nights of bad sleep in a row make the day EASY with 70% of its volume

**Status:** PROPOSED (accepted on merge of this PR)
**Date:** 2026-10-16
**Author:** Zaf (Owner, decision) / Claude (implementation)
**Related:** ADR-0009 (governance_engine architecture lock), ADR-0051 (missing data, the 0.7
conservative modifier), ADR-0065 (a downgraded session keeps 70%), SV-16 in
`docs/validation/synthetic-athlete-report.md`, D-066 in `DECISIONS.md`

---

## Context

Bad sleep reaches the decision only as one of the four 2-of-4 indicators in `governance_engine.py`
(I2: sleep score under 60). One indicator alone does not downgrade a session. The synthetic
athletes showed that three nights of 4.2 h sleep (score 34) changed the session for 1 of 6
athletes (finding SV-16, scenario `bad_sleep_3`).

On 2026-10-16 Zaf chose "3 nights" on a decision card.

---

## Decision

1. **When.** Tonight's sleep score (this morning's sync) and the stored scores of the two nights
   before it (`daily_metrics.sleep_quality`, same athlete) are all under 60
   (`SLEEP_DEBT_NIGHTS = 3`, `SLEEP_DEBT_SCORE_MAX = 60`, the I2 limit, both with evidence
   entries). A night without a score ends the run: a missing reading is not counted as a bad one
   (ADR-0051).
2. **What.** Any session that is not REST becomes EASY and keeps 70% of its duration and distance
   (`INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE`), an EASY session too. REST stays REST. A
   `sleep_debt_ease` event records it.
3. **Where.** `DailyCoach._decision_pipeline`, before governance, after the stale-data and
   INV-24 data-trust clamps. It is skipped when one of those clamps applied: the session is
   already capped, and stale data carry no fresh sleep.
4. `governance_engine.py` does not change. Governance still runs afterwards and can only restrict
   further.

---

## Consequences

- After three bad nights the morning is EASY with 70% of the plan; with fewer, nothing changes.
- The characterization goldens have no run of three bad nights and do not change.
- The synthetic athletes get a new rule, `sleep_debt_eases_the_day`, with no violations.
- `get_daily_metric` also returns `sleep_quality` (read only; the column already exists).

## Not changed

- The 2-of-4 rule and its I2 indicator, the H1–H5 hard stops, the intensity gate.
- No lock code is added (ADR-0024). The morning message is not changed.
