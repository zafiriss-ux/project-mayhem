# ADR-0068: Governance gates never loosen: per-athlete override lockdown, REST stays REST, non-finite input is missing input

**Status:** PROPOSED (accepted on merge of this PR)
**Date:** 2026-10-17
**Author:** Zaf (Owner, decision 2026-10-17 05:41Z: «Διόρθωσε τα») / Claude (implementation)
**Related:** ADR-0009 (governance_engine architecture lock), ADR-0051 (missing data, the 0.7
conservative modifier), ADR-0064 (H2 relative drop), ADR-0065 (downgrade volume cap), ADR-0067
(multi-athlete activation, owner baseline D3.4), AGENTS §16.1, D-106 in `DECISIONS.md`; audit
findings SG-02, SG-03, SG-05, SG-07, SG-09, SG-10 (read-only audit of c068709)

---

## Context

Zaf audited `c068709` read-only. Six findings in `titan/science/governance_engine.py` let a gate
loosen a decision or ignore bad input:

- **SG-02 (HIGH).** `check_override_lockdown` and `apply_override_lockdown` called
  `db.get_override_ratio(days=14)` with no athlete, so the repository default `"owner"` was used:
  every athlete was locked or unlocked by the owner's override history (ADR-0067 isolation).
- **SG-03 (HIGH).** The parasympathetic guard wrote `EASY` / zone 2 over the plan, so a `REST`
  from a hard stop (H1–H3) became `EASY`: a lock raised intensity.
- **SG-05 (MEDIUM).** The exception fail-closed path wrote `EASY` / zone 2 and replaced the lock
  list: a `REST` day became `EASY` and the H1 lock was dropped.
- **SG-07 (MEDIUM).** A non-finite today HRV, baseline HRV, RHR or subjective fatigue was rejected
  (`NAN_REJECTED`) but treated as "no trigger", with no ceiling. An absent value got the ADR-0051
  ceiling; a `NaN` got nothing.
- **SG-09 (MEDIUM).** H4 (TSB ≤ −50, "mandatory load reduction") turned only quality sessions into
  EASY; `LONG_RUN` and `PROGRESSIVE` stayed, and an EASY day kept its full volume.
- **SG-10 (LOW).** Intensity-gate inputs failed open: a `NaN` `volume_modifier` became 1.0; a
  `max_zone` of 0 became 5 (`int(0 or 5)`).
- **H2 baseline.** With a baseline HRV of 0 (cold start, under 14 days) the H2 threshold was
  `min(15, 0.3 × 0) = 0 ms` and `0 − today ≥ 0` never held: H2 was silently off.

`governance_engine.py` is architecture-locked (ADR-0009, AGENTS §8). On 2026-10-17 05:41Z Zaf
wrote «Διόρθωσε τα» (fix them). Every change below is stricter, never looser.

---

## Decision

1. **SG-02: the lockdown reads the athlete's own ratio.** The governance context carries
   `athlete_id` (`DailyCoachContext`, from `DailyCoach.athlete_id`); `GovernanceEngine` also
   accepts one at construction, and `get_governance_report(..., athlete_id=)` passes it. The engine
   calls `db.get_override_ratio(athlete_id=<id>, days=14)`. With no `athlete_id` (None, empty,
   blank or not a string) the lockdown **fails closed** (`locked=True`, max zone 2, error code
   `ATHLETE_ID_MISSING`) and never falls back to the owner. A non-finite ratio also locks
   (`COMPUTATION_ERROR`).
2. **SG-03: a lock never raises intensity.** The parasympathetic guard gives
   `min(current, EASY)`: `REST` stays `REST` with its reason; any other session becomes EASY. The
   zone becomes `min(current, 2)`, so a lower zone is never raised. The override lockdown likewise
   takes `min(current zone, lock zone)`.
3. **SG-05: fail closed keeps what is already stricter.** When `apply_constraints` raises, the plan
   becomes `REST` / zone 1 if it is already REST, if an injury flag is set, or if a hard stop
   H1–H3 fires on the inputs (re-evaluated in isolation); otherwise EASY with
   `min(current zone, 2)`. The locks applied before the exception are kept, and
   `GOVERNANCE_EXCEPTION_FAIL_CLOSED` is appended.
4. **SG-07: non-finite is missing.** A non-finite today/baseline HRV gives `H2_MISSING`
   (`DATA_MISSING_CONSERVATIVE_H2`, EASY ceiling, `data_confidence_low`); a non-finite RHR gives
   `H3_MISSING`; a non-finite or non-numeric fatigue score gives `H5_MISSING` — the same ADR-0051
   ceilings an absent value already gets.
5. **H2 baseline.** A baseline HRV of 0 or less, `None` or non-finite is missing HRV: H2_MISSING
   with its EASY ceiling. A baseline ≤ 0 never disables H2. (Another task makes the HRV engine
   pass `None` instead of 0; both reach the same ceiling.)
6. **SG-09: H4 cuts every session above EASY.** At TSB ≤ −50 every session that is not REST or
   EASY becomes EASY (zone ≤ 2), and every non-REST H4 day gets the ADR-0065 cap: 70% of the
   volume (or the intensity gate's smaller modifier) and at most 60 minutes, also when the type did
   not change (EASY stays EASY but is shortened). REST stays REST with no volume.
7. **SG-10: intensity-gate inputs fail conservative.** A non-finite or non-numeric
   `volume_modifier` takes `INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE` (0.7); a modifier outside
   0..1 is clamped. A `max_zone` that is non-numeric or non-finite is zone 2; one out of range is
   clamped to 1..5 (0 → 1, never 5); an absent one stays 5 as before.

No threshold value changes, and no lock code is added (ADR-0024): `ATHLETE_ID_MISSING` is an error
code of the lockdown result, like `DB_READ_ERROR`.

---

## Consequences

- Per-athlete lock state: two athletes on one database each get their own override lockdown; a
  new athlete gets the cold-start lock, not the owner's ratio.
- The owner's mornings change in the characterization goldens (and so in the ADR-0067 D3.4 owner
  baseline fingerprints, re-fingerprinted by this ADR). In the cold-start week the HRV baseline is
  0, so H2_MISSING now applies: `HARD_STOP_SAFETY_GATES`, `DATA_MISSING_CONSERVATIVE_H2` and
  `STARTUP_DATA_CONFIDENCE_CEILING` join the locks, and `TEMPO` / `LONG_RUN` days become EASY with
  the ADR-0065 70% cap (e.g. `LONG_RUN 7.7 km → EASY 5.4 km`). An H4 EASY day goes from 6.9 km to
  4.8 km. Every changed morning is listed in D-106. No morning becomes less strict.
- A caller that builds a governance context without `athlete_id` now gets the conservative
  lockdown instead of the owner's ratio.

## Not changed

- H1–H5 thresholds, the 2-of-4 rule, the VO2 and fueling gates, gate priority (APL), the ADR-0065
  cap values, `governance_golden.json`.
