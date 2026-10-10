# ADR-0063: A long run without confirmed fueling stays a long run, with a reminder

**Status:** PROPOSED (accepted on merge of this PR)
**Date:** 2026-10-10
**Author:** Zaf (Owner, decision) / Claude (implementation)
**Related:** ADR-0009 (governance_engine architecture lock), ADR-0024 (lock codes),
SV-05 in `docs/validation/synthetic-athlete-report.md`, D-058 in `DECISIONS.md`

---

## Context

The fueling gate in `GovernanceEngine._check_fueling_gate` locked every `LONG_RUN` of 90 minutes
or more to `PROGRESSIVE` when `fueling_confirmed` was false. Nothing ever sets it to true: Garmin
does not report fueling and the app does not ask. So every long run became `PROGRESSIVE`, which
is a harder session than `LONG_RUN`. A gate meant to lower risk raised intensity. The synthetic
athletes showed it on 50 mornings, every long run (finding SV-05, rule
`governance_never_raises_intensity`).

`governance_engine.py` is architecture-locked (ADR-0009, AGENTS §8). On 2026-10-10 Zaf chose, on
a decision card, "Reminder": keep the long run and tell the athlete to carry food or gels.

---

## Decision

1. **The long run stays.** A `LONG_RUN` of 90 minutes or more without confirmed fueling gets a
   phase-4 `FLAG` (`session_unchanged: True`) instead of a `LOCK` to `PROGRESSIVE`. The lock code
   applied is `FUELING_GATE_FLAG`, an existing canonical code; no code is added or removed.
2. **The morning message reminds.** `send_daily_coaching` adds
   "🍌 *Fueling:* carry food or gels for this long run." when the fueling gate result is a
   phase-4 `FLAG`.
3. Nothing else in the fueling gate changes: `HAMMER`/`RACE` still lock to `TEMPO`, quality
   sessions of 90 minutes or more still lock to `EASY`, and the 60–89 minute flags are the same.

---

## Consequences

- Long runs of 90 minutes or more keep their type and distance. In the characterization goldens
  the Saturday long runs (22 km) are `LONG_RUN` instead of `PROGRESSIVE`, and the nutrition plan
  follows the long-run session (630 g carbs instead of 420 g).
- SV-05 leaves the `KNOWN` ledger of the synthetic-athlete test: `governance_never_raises_intensity`
  has no explained violations left.
- If fueling confirmation is added later (for example a Telegram question), the reminder stops
  on mornings when it is confirmed, with no further change here.

## Not changed

- H1–H5 hard stops, the 2-of-4 rule, the intensity gate, VO2 and APL gates.
- `CANONICAL_LOCK_CODES`.
