# TITAN OS — Technical Debt Register & Upgrade Roadmap

**Created:** 2026-03-02
**Source:** Full codebase audit + module-by-module engineering review (v5.8.0)
**Governance:** This document is the authoritative register for known technical debt.
All new findings must be added here. Items must not be "fixed" without a corresponding
issue/PR that references the tier and item number below.

---

## XA-T01 / #1166 — policy-only: ADR-0084, the later ceilings get the ADR-0065 volume cap (owner assignment, 2026-11-07)

**Status:** OPEN — in review; ADR-0084 is Proposed until the owner approves its text. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance gate (`governance_engine.py`, ADR-0009). **Severity:** HIGH (issue). **Change Type:** policy-only. **Workflow Path:** A (plan v5.1-R3, rank 2; Category Β: the ADR is Accepted before the code, ADR-0072).

Pass type: policy-only
Change Type: policy-only
Workflow Path: Path A
Execution unit: ADR-0084 only. It records the owner's choice "70%, έως 60΄, όπως ADR-0065" (decision card 2026-11-07, 09:48 UTC): when the parasympathetic guard, override lockdown, startup data confidence or persistence-degraded ceiling changes the session type (not to REST), the session keeps 0.7 (or a smaller modifier it already has) and at most 60 minutes (a smaller existing cap stays); a session already EASY or REST keeps its volume. The card and the reproduction are cited by the #1166 comment 6705138702. Records: the ADR index (README, CLAUDE.md), D-224, this brief, the BKP-NEW-05 reproduction status line, the ledger.
Deliverable: the ADR text, reviewed, and the owner's approval of it on a decision card; then one implementation PR with the tests the ADR names.
Stop condition: Any failed gate or blocking review stops commit/push/merge. No merge before the owner approves the ADR text.
Closure rule: this pass does not close #1166; it closes with the implementation PR and the Records Steward's disposition.
Canonical doc update: docs/adr/0084-late-ceiling-volume-cap.md, docs/adr/README.md, CLAUDE.md ADR list, DECISIONS.md D-224, this brief, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-07 to implement plan v5.1-R3 (#1434 comment 6703643099, rank 2 = #1166) and the owner's choice on the decision card of 2026-11-07, 09:48 UTC. The ADR becomes Accepted only by the owner's approval of its text on a decision card (ADR-0078). No code change, so contract §13 is not touched; the decision only tightens.
Allowed / Forbidden: the files above. No `titan/`, `scripts/`, test, threshold, schema or AGENTS.md change; ADR-0065 is not edited.

---

## BKP-NEW-05 / #1505 — reproduction only: the H1–H5 guard is checked by name only, and only by the drill (owner assignment, 2026-11-07)

**Status:** OPEN — merged in PR #1525, squash `cdc90e8`; main green; the fix waits for the owner's go-ahead (decision card of 2026-11-07). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance / data recovery (ADR-0052 guard). **Severity:** HIGH (issue; governance path, floor HIGH). **Change Type:** test-only. **Workflow Path:** A (plan v5.1-R3, rank 3: reproduction; the fix after the owner's go-ahead).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: BKP-NEW-05 at main `c12ab64`, no application or script code. In `tests/test_backup_dr.py`, on synthetic backups made by the code in `tmp_path`: (1) control: the intact H1–H5 guard triggers refuse a hard-stop offset by INSERT and by UPDATE, and each weakened copy with the same name lets it in (a never-firing INSERT guard; an UPDATE guard without one key); (2) control: the drill passes all four weakened copies today (the two triggers, and `uq_governance_outcomes_athlete_date` and `idx_training_log_garmin_id` made non-unique with the same name); this parametrized control replaces the single #1496 pin `test_1496_names_only_a_weakened_guard_with_the_same_name_still_passes`; (3) the drill fails each weakened copy — `xfail(strict=True, raises=AssertionError)`, four cases; (4) control: `restore_backup.restore` puts back an intact backup; (5) `restore_backup.restore` refuses a backup without the INSERT guard trigger, or with the never-firing one of the same name, and nothing is put in place — `xfail(strict=True, raises=AssertionError)`: the restore runs no schema check, and opening the database does not make the trigger again (#1496 test). Tests count 5089 collected (15 added, 1 replaced). For the fix PR: the four controls of (2) and the xfails of (3) assert opposite results on the same copies on purpose, so the fix inverts or removes those controls; the xfails pin only that the drill fails and the restore refuses, so the intact-backup drill and restore tests must stay green. Views and the other indexes are also compared by name only: the fix compares the definition of every object the drill lists, not only the four pinned here. No real backup, restore or data is touched (the plan's restore hold is for real restores).
Deliverable: the tests; an issue comment with the reproduction and the fix question for the owner.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1505; it closes with the fix PR and the Records Steward's disposition.
Canonical doc update: this brief, the XA-T01 reproduction status line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-07 to implement plan v5.1-R3 (#1434 comment 6703643099, rank 3 = #1505, reproduction; the fix after the owner's go-ahead). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/test_backup_dr.py`, the records above. No `titan/`, `scripts/`, runbook, threshold, schema, AGENTS.md or ADR change.

---

## XA-T01 / #1166 — reproduction only: a later ceiling turns LONG_RUN 180' into EASY 180' (owner assignment, 2026-11-07)

**Status:** OPEN — merged in PR #1524, squash `c12ab64`; main green; the fix waits for the owner's decision on the volume reduction (decision card of 2026-11-07) and an ADR. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance gate (`governance_engine.py`, architecture-locked, ADR-0009). **Severity:** HIGH (issue). **Change Type:** test-only. **Workflow Path:** A (plan v5.1-R3, rank 2: reproduction; the fix needs the owner's decision and an ADR, because ADR-0065 Decision 4 left these ceilings out of the cap).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: XA-T01 at main `485fb85`, no application code. In `tests/test_science_edge_cases.py`, with a GREEN intensity gate as `IntensityGovernor` returns it (modifier 1.0): (1) control: without a ceiling LONG_RUN 180' and TEMPO 75' keep their type, modifier 1.0 and no duration cap (passes); (2) control: the same LONG_RUN on an H4 day gets the ADR-0065 reduction (passes); (3) control: each later ceiling turns the session into EASY and records its lock (passes); (4) the session such a ceiling downgrades does not keep its full volume — `xfail(strict=True, raises=AssertionError)`, four cases: PERSISTENCE_DEGRADED_CEILING and STARTUP_DATA_CONFIDENCE_CEILING (the audited scenario), and the PARASYMPATHETIC_GUARD and OVERRIDE_LOCKDOWN siblings found at the same place (the override lockdown disables only quality sessions, so it is shown on TEMPO 75'). The xfails pin only "some reduction" (a modifier below 1.0 or a duration cap below the planned minutes); how much is the owner's decision. Fix scope, not pinned here: these ceilings also leave a session that is already EASY at full volume (e.g. the H4 data-missing EASY day that then gets STARTUP_DATA_CONFIDENCE_CEILING), while ADR-0068 SG-09 caps every non-REST H4 day even when it stays EASY; the owner's question covers both. Tests count 5075 collected (11 added).
Deliverable: the tests; an issue comment with the reproduction and the question for the owner.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1166; it closes with the fix PR and the Records Steward's disposition.
Canonical doc update: this brief, the XA-T04 reproduction status line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-07 to implement plan v5.1-R3 (#1434 comment 6703643099, rank 2 = #1166, reproduction; the fix after the owner's decision). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/test_science_edge_cases.py`, the records above. No `titan/`, `scripts/`, threshold, schema, AGENTS.md or ADR change.

---

## XA-T04 / #1169 — reproduction only: an unknown or non-numeric ACWR reads as GREEN in the load gauge (owner assignment, 2026-11-07)

**Status:** OPEN — merged in PR #1523, squash `485fb85`; main green; the fix waits for the owner's oracle for an unknown ACWR (decision card of 2026-11-07). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance input (VLG feeds the priority lock's load band). **Severity:** HIGH (issue). **Change Type:** test-only. **Workflow Path:** A (plan v5.1-R3, rank 1: reproduction; the fix needs the owner's oracle for an unknown ACWR).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: XA-T04 at the current main, no application code. In `tests/titan/science/test_volume_load_gauge.py`: (1) control: an infinite ACWR is RED (passes); (2) NaN and a non-number ACWR are not GREEN, as a non-finite TSB or glycogen debt already is — `xfail(strict=True, raises=AssertionError)`: `resolve` turns a non-number into 1.0 and NaN passes every comparison; (3) an unknown ACWR (None, what the morning passes when the load history is too short) is not reported as an in-range GREEN — strict xfail; which colour it takes is the owner's decision; (4) control: DailyCoach step 9a (`_step_load_priority`, real VLG and priority lock) with measured inputs gives GREEN / OPTIMAL (passes); (5) the same step with ACWR and TSB unknown is not GREEN / OPTIMAL — strict xfail: the unknown TSB becomes 0.0 (`_safe_float`) and the unknown ACWR 1.0. The governance gates already treat an unknown ACWR conservatively (H2 stress context `UNKNOWN_ACWR`, VO2 eligibility V1); this reproduction covers the load gauge and the priority lock's load band only. Consequence on main: unknown ACWR and TSB read as OPTIMAL, which in BUILD selects the default `acwr_ceiling` and `tsb_floor` instead of the stricter BUILD_OVERLOAD set and ranks CS_CONFIDENCE_LOCK ahead of OVERRIDE_LOCKDOWN. The xfails pin only "not GREEN" / "not OPTIMAL" (any non-GREEN colour, not a specific YELLOW or RED); the fix must return a colour, not raise, for a non-number. The fix scope also names the sibling GREEN defaults the owner sees when choosing the oracle: `getattr(vlg_state, 'color', 'GREEN')` and `trace.get("vlg_color", "GREEN")` in `daily_coach.py`, and the missing-colour default in `_vlg_to_load_band`; the stored `vlg_color` reaches the operator console and the outcome tracker.
Deliverable: the tests; an issue comment with the reproduction and the oracle question for the owner.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1169; it closes with the fix PR and the Records Steward's disposition.
Canonical doc update: this brief, the M0-01-R1 fix status line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-07 to implement plan v5.1-R3 (#1434 comment 6703643099, rank 1 = #1169, reproduction; the fix after the owner's oracle). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/titan/science/test_volume_load_gauge.py`, the records above. No `titan/`, `scripts/`, threshold, schema, AGENTS.md or ADR change.

---

## M0-01-R1 / #1264 — fix: a refused "sending" mark stops the briefing (owner assignment, 2026-11-07)

**Status:** OPEN — merged in PR #1522, squash `b7258d4`; main green; the canonical M0-01-R1 row and #1264 await the Records Steward's disposition (S4). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 (`M0-01-R1`). **Severity:** MEDIUM (source; owner review towards HIGH pending, the implementer does not change it). **Change Type:** implementation. **Workflow Path:** A (the registry's category Β: a design decision, taken by the owner on the decision card of 2026-11-07, "yes, as in admission card 0a"; the change itself only tightens).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: M0-01-R1 only, the briefing's send step. (1) `update_routine_resume` raises `RoutineAttemptSuperseded` (a `LookupError` subclass, so earlier callers are unchanged) when the fence refuses the write; a missing row stays a plain `LookupError`. (2) `worker._mark_briefing_sending` returns False when the fenced "sending" mark is refused, and True when it is written or any other error occurs (MA-F5, ADR-0069 §8, kept by the owner's choice). (3) `DailyCoach`'s send step does not send when the "before" hook returns False: it sets `attempt_lost`, logs `briefing_not_sent` (`attempt_superseded_at_mark`) and returns False; a hook that fails or returns anything else still sends (MA-F5). After a mark is written, a later attempt sees "sending" and sends only the MA-F5 reminder, never a second briefing. Out of scope: the stored-decision resends (`_send_stored_decision` from `_resume_stored_day`), which have no mark — #1521 (M0-01-R2, owner decision, it changes MA-F5 for resends); and the residual when the mark fails for another reason (such as "database is locked") during a takeover, which keeps sending by the owner's choice; a missing routine row at the mark also keeps sending, as on main (noted in #1521).
Deliverable: the change; the strict xfail of #1520 passes with the mark removed; new tests (the owner attempt marks before it sends; the refusal is told apart from a missing row; `_mark_briefing_sending` stops the send only when superseded; `DailyCoach` sends unless the mark is refused: refused, no answer, hook failed). Four tests fail on main: the refused case of the `DailyCoach` test, the told-apart test, the `_mark_briefing_sending` test and the former xfail test; the owner-attempt control and the two MA-F5 cases (no answer, hook failed) are guards that pass on main.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: the PR refers to #1264 and does not close it. M0-01-R1 and #1264 close only after merge, green main and the Records Steward's disposition (plan v5.1-R3, S4).
Canonical doc update: this brief, the reproduction brief's status line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl. The canonical M0-01-R1 row is left to the Records Steward (S4).
Authorizes: Owner instruction 2026-11-07 to implement plan v5.1-R3 (#1434 comment 6703643099, rank 0a) and the owner's choice "Ναι, όπως στη κάρτα 0a" on the decision card of 2026-11-07 (fix in a second PR; other database errors keep sending). Category Α in effect (tightening only, contract §13 not weakened: every new path sends less, none more). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `titan/core/repositories/operations.py`, `titan/worker/__init__.py`, `titan/orchestration/daily_coach.py`, `tests/test_worker_morning_retry.py`, the records above. No schema, new module, AGENTS.md or ADR change.

---

## M0-01-R1 / #1264 — reproduction only: a takeover after the send check still sends the old briefing (owner assignment, 2026-11-07)

**Status:** DONE 2026-11-07 — reproduction merged in PR #1520, squash `ffc24be`; main green; #1264 stays open for the fix (M0-01-R1 fix brief above). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 (`M0-01-R1`, canonical row below). **Severity:** MEDIUM (source; the admission card asks the owner to review it towards HIGH, the implementer does not change it). **Change Type:** test-only. **Workflow Path:** A (plan v5.1-R3, rank 0a: admission card on #1264, then reproduction).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: M0-01-R1 at the current main, no application code. In `tests/test_worker_morning_retry.py`, with a real `DatabaseManager`, the real worker binding (`_bind_day`) and the real `DailyCoach` record and send handlers: attempt 1 records TEMPO while it owns the day; attempt 2, in another connection and once, takes the day over right after attempt 1's ownership check in the send step passes, stores REST and marks the day delivered in the database (it sends nothing in the test). (1) Control: a takeover before the send check sends nothing (passes). (2) Control: the database refuses attempt 1's fenced "sending" mark after the takeover (`LookupError`, no mark; passes). (3) Attempt 1 does not send TEMPO after REST — `xfail(strict=True, raises=AssertionError)`: `_set_briefing_sending` and `_briefing_hook` swallow the refusal, so the send goes ahead. The fix (the refused fenced mark stops the send; other database errors keep the MA-F5 behaviour) is a separate PR: the owner answered "yes, as in admission card 0a" on the decision card of 2026-11-07. The stored-decision resend path (`_send_stored_decision`) has no fenced mark either; the fix PR states it as in or out of its scope.
Deliverable: the three tests; the admission card on #1264 (comment of 2026-11-07).
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1264 or M0-01-R1; they close with the fix PR and the Records Steward's disposition.
Canonical doc update: this brief, the E2E-01 fix closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-07 to implement plan v5.1-R3 (#1434 comment 6703643099, rank 0a = #1264 record/design, then a reproduction PR). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/test_worker_morning_retry.py`, the records above. No `titan/`, `scripts/`, schema, AGENTS.md or ADR change.

---

## E2E-01 / #1246 — fix: the CLI "Σημερινό Πλάνο" shows the owner's stored decision of the day as the instruction (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-07 — the owner answered "yes, fix it" on the decision card; PR #1518, squash `f622206`; main green; #1246 closed (the optimal-time block carried in #1519). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — the final instruction the athlete sees. **Severity:** HIGH (issue). **Change Type:** implementation. **Workflow Path:** A (category Α: the screen shows the governed decision instead of the ungoverned plan).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1246 only, in `titan/ui/menu_system.py` (`menu_daily_plan` and a new helper `_stored_decision_of_today`). The screen reads `get_governance_decision_on("owner", <UTC date>)` — a literal owner, the CLI being the owner's, and the same UTC day the morning stores under by default (`_routine_day`); a worker run claimed for another day stores under that day, so until today's morning runs the screen shows no instruction (the safe direction). (1) A stored decision is the instruction line (`ΠΡΟΠΟΝΗΣΗ: <session_post_governance>`); the weekly plan is shown beside it in brackets, as the plan's (the stored decision has no distance, and governance may cut the volume of the same session, so the plan's distance is never shown as the instruction's). (2) With no stored decision the plan is no longer shown as the instruction: the screen says there is no stored decision for today (also when there is no plan) and names the plan as the weekly plan. (3) When the decision cannot be read, the screen says so (the exception class only, never its text), does not claim there is no decision (it may exist, a REST say), tells the athlete not to follow the plan before seeing it, and does not show the plan as the instruction. Out of scope: the weather block's `today_session_type`, the Telegram `/today` path, and any other athlete (the CLI shows only the owner).
Deliverable: the change; the strict xfail of #1517 passes with the mark removed; new tests (a stored EASY replaces the planned LONG_RUN; the plan's distance is only shown as the plan's; no stored decision is not shown as the instruction; another athlete's decision is not shown; a decision that cannot be read is not replaced by the plan and is not called missing; no decision and no plan still says there is no decision; a malformed stored row, or one whose session is empty, is treated as unreadable). Each new test fails on main except the other-athlete test, which pins the owner scoping. The no-decision control of #1517 changes on purpose (point 2).
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1246 closes after merge and green main.
Canonical doc update: this brief, the reproduction brief's status line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, row 15 is reproduction only); merge waits for the owner's answer on the decision card of 2026-11-06. No authorization, consent or governance code changes (display only), so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `titan/ui/menu_system.py` (`menu_daily_plan` and its helper), `tests/test_menu_system.py`, the records above. No `daily_coach.py`, `titan/main.py`, `worker/__init__.py`, `telegram_bot.py`, schema, AGENTS.md or ADR change.

---

## E2E-01 / #1246 — reproduction only: the CLI "Σημερινό Πλάνο" shows the plan's session, not the stored decision of the day (owner assignment, 2026-11-06)

**Status:** DONE 2026-11-06 — reproduction merged in PR #1517, squash `0a39b7f`; main green; #1246 stays open for the fix (E2E-01 fix brief above). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — the final instruction the athlete sees. **Severity:** HIGH (issue). **Change Type:** test-only. **Workflow Path:** A (plan v3 row 15: reproduction, after rows 3–7, which are closed).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: #1246 reproduction at the current main, no application code. In `tests/test_menu_system.py`, with a real `DatabaseManager` in a temporary directory, the real `save_governance_decision` / `get_governance_decision_on` and the real `menu_daily_plan`, and a synthetic weekly plan whose session today is LONG_RUN 5.1 km: (1) control, the stored decision of today is REST (passes); (2) control, with no stored decision the screen shows the plan's session (passes; what a fix shows on a day with no decision yet is its own choice, and changing this control is then on purpose); (3) with REST stored, the instruction line is not the plan's `ΠΡΟΠΟΝΗΣΗ: LONG_RUN` and the screen shows REST (a fix may still name the planned session next to the decision) — `xfail(strict=True, raises=AssertionError)`: today `menu_daily_plan` reads only `last_weekly_plan` and never the stored decision. The fix (read the athlete's stored decision of the day first) is a separate PR and a separate decision.
Deliverable: the three tests; an issue comment with the reproduction at this SHA.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1246; it closes with the fix PR.
Canonical doc update: this brief, the SCI-NEW-03 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, row 15 = #1246, reproduction after rows 3–7). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/test_menu_system.py`, the records above. No `titan/`, `scripts/`, schema, AGENTS.md or ADR change.

---

## SCI-NEW-03 / #1419 — reproduction on the real database path: a fit with a negative D′ no longer lifts the CS lock (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1516, squash `6daa880`; main green; #1419 closed (fit quality and effort independence carried in #1514, item 5). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance input (CS_CONFIDENCE_LOCK). **Severity:** MEDIUM (GitHub label, kept as is per plan v3 row 14). **Change Type:** test-only. **Workflow Path:** A (plan v3 row 14: #1349, #1350, then #1419; reproduction, then guard).

Pass type: reproduction (a regression test on the real path: the guard of #1515 already holds, so nothing here fails on main)
Change Type: test-only
Workflow Path: Path A
Execution unit: #1419 at the current main, no application code. The issue's first dataset (3000/900, 5000/1200, 3000/880, 5000/1180, 3000/860, 5000/1160) through the real `parse_time_trial`, a real `DatabaseManager` (temporary directory) with `log_cs_performance`, the real CS hydration step, a real `CriticalSpeedTracker` and `check_cs_confidence_lock`. (1) Control: every prefix fit has CS > 0 and D′ < 0 (passes). (2) The trials keep the lock: the hydration step runs and rejects all five fits (`cs_hydrated` with 6 distinct trials and 5 rejected fits, no `cs_hydration_failed`), no update reaches the tracker and the lock is on (passes on main since the #1515 guard, which uses a fit only when CS > 0 and D′ > 0; fails on the code before #1515). The issue's other point — confidence does not weigh residuals or how independent the efforts are — is a design question, carried in #1514 (item 5 added there: fit quality such as residuals or R², and effort independence; owner decision). The issue gives its second dataset only as its fit (D′ −349 m), not its trials; any fit with D′ ≤ 0 is rejected by the same rule.
Deliverable: the two tests; an issue comment.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1419 closes after merge and green main.
Canonical doc update: this brief, the ING-NEW-03/04 guard closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, row 14). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/titan/orchestration/test_daily_coach.py`, the records above. No `titan/`, `scripts/`, schema, threshold, AGENTS.md or ADR change.

---

## ING-NEW-03 / #1349 and ING-NEW-04 / #1350 — guard: a repeated trial counts once and a fit with CS or D' at or below zero is not used (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1515, squash `37737fa`; main green; #1349 and #1350 closed (follow-up #1514). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance input (CS_CONFIDENCE_LOCK). **Severity:** HIGH (both issues; governance path, floor HIGH). **Change Type:** implementation. **Workflow Path:** A (category Α, tightening only).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1349 and #1350 only, in the CS step of `DailyCoach._hydrate_engines_from_db` (D-040). (1) ING-NEW-03: the trials are replayed oldest first with the same windows as before, but a window whose newest row repeats an earlier (date, distance, time) adds no tracker update, so a trial entered again adds no confidence. Distinct trials of the same day stay distinct. The updates made are a subset of the updates the previous code made for the same rows in the same order (same windows, same fits, some skipped), so the lock is on at least as often for any input. A first version that removed the repeats from the windows was dropped, because it changes the fits and, for a contrived set with one exact repeat, could turn a rejected exact-zero fit into an accepted one. Same-day rows have no defined order in the database (`ORDER BY date DESC` only), so the result for some same-day sets can depend on that order, as it already did; a sort was tried and dropped, because for a contrived same-day set (two trials of the same distance) it could unlock where the database order kept the lock — a fixed tie order is follow-up issue #1514. (2) ING-NEW-04: a fit is used only when CS > 0 and D' > 0; any other fit (negative, zero or none) is not passed to the tracker, so it adds neither an estimate nor confidence. Earlier valid estimates are kept. (3) The `cs_hydrated` event also reports `distinct_trials` and `rejected_fits`. Effect: fewer or equal tracker updates in every case, so CS_CONFIDENCE_LOCK stays on at least as often as before and never less. Out of scope: a UNIQUE constraint or duplicate check where trials are entered (`log_cs_performance`, Telegram and the menu; the stored rows are unchanged), a guard inside `CriticalSpeedTracker.update` (the hydration is its only caller in `titan/`), and near-repeats: the dedupe is exact, so a trial re-entered with a one-second difference or on another date counts as a new trial; a minimum spread of distance or dates before the lock lifts would be an owner decision (#1514) (the 70% threshold and the tracker's confidence formula are unchanged).
Deliverable: the change; the three strict-xfail tests of #1513 now pass with the marks removed; new tests (distinct same-day trials both count; repeats do not raise confidence; skipping a repeat never adds an update, the exact-zero case of the security review; a valid estimate is kept when a later fit is negative; a negative D' is not used; the event fields). Every new test fails on main, except the exact-zero test, which passes on main and pins that the fix adds no update (it fails with a version that removes repeats from the windows).
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1349 and #1350 close after merge and green main.
Canonical doc update: this brief, the reproduction brief's status line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, row 14 = #1349, #1350, reproduction then guard). Category Α (tightening only; contract §13 not weakened: no path from locked to unlocked is added). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `titan/orchestration/daily_coach.py` (the CS hydration step only), `tests/titan/orchestration/test_daily_coach.py`, the records above. No schema, threshold, `critical_speed.py`, `governance_engine.py`, AGENTS.md or ADR change.

---

## ING-NEW-03 / #1349 and ING-NEW-04 / #1350 — reproduction only: repeated or incompatible time trials lift the CS confidence lock (owner assignment, 2026-11-06)

**Status:** DONE 2026-11-06 — reproduction merged in PR #1513, squash `3be719c`; main green; #1349 and #1350 stay open for the guard (ING-NEW-03/04 guard brief above). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance input (CS_CONFIDENCE_LOCK). **Severity:** HIGH (both issues; governance path, floor HIGH). **Change Type:** test-only. **Workflow Path:** A (plan v3 row 14: reproduction, then a guard).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: #1349 and #1350 reproduction at the current main, no application code. In `tests/titan/orchestration/test_daily_coach.py`, with the real `DailyCoach._hydrate_engines_from_db` CS step (D-040), a real `CriticalSpeedTracker`, `CriticalSpeedEngine` and `GovernanceEngine.check_cs_confidence_lock`, and synthetic trials all dated today. #1349: (1) control, two distinct trials (3000 m / 600 s, 5000 m / 1100 s) give a positive CS and keep the lock (passes); (2) the same pair entered three times (six rows) keeps the lock — `xfail(strict=True, raises=AssertionError)`: today each repeat is one more tracker update, so the confidence passes 70% with no new evidence. #1350: (3) control, the six trials 3000+500·i m in 1200−50·i s (i = 0..5) each have a speed between 2 and 6 m/s and their fit is a negative speed (passes); (4) the negative speed does not reach the tracker — same strict xfail: today `if cs_raw and d_prime` lets −10.0 m/s in; (5) those trials keep the lock — same strict xfail: today the confidence counts updates, not the validity of the fit. The guards (one count per distinct trial; a fit with CS ≤ 0 is not used) are a separate PR and a separate decision; they touch `daily_coach.py` and/or `critical_speed.py`, so they wait for the one-PR rule.
Deliverable: the five tests; an issue comment on each issue with the reproduction at this SHA.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1349 or #1350; they close with the guard PR.
Canonical doc update: this brief, the ING-NEW-02 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, row 14 = #1349, #1350, reproduction then guard). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/titan/orchestration/test_daily_coach.py`, the records above. No `titan/`, `scripts/`, schema, threshold, AGENTS.md or ADR change.

---

## ING-NEW-02 / #1348 — reproduction only: the laps of an athlete's run are left out of their export and kept after their deletion (owner assignment, 2026-11-06)

**Status:** DONE 2026-11-06 — reproduction merged in PR #1512, squash `f26f501`; main green; #1348 stays open for the fix (the owner is asked on a decision card whether to fix it now). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — athlete data lifecycle (export / deletion, ADR-0067). **Severity:** HIGH (issue). **Change Type:** test-only. **Workflow Path:** A (plan v3 row 13: reproduction only).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: #1348 reproduction at the current main, no application code. In `tests/test_athlete_lifecycle.py`, with the real `add_athlete`, the offline lap import `_import_one`, `export_athlete` and `delete_athlete`: athlete B's only run (Garmin id 12345) and its 8-lap file. (1) Controls: the 8 laps are stored and are B's only through the file name (`activity_12345` is B's run with Garmin id 12345), and deleting B removes B's training rows (pass; after #1347 the drift is not written to B's training row). (2) B's export has the 8 laps — `xfail(strict=True, raises=AssertionError)`: today `activity_laps` has no `athlete_id`, so `athlete_tables` leaves it out. (3) Deleting B removes the laps — same strict xfail: today the 8 laps stay after B's training rows are gone. Scope: `activity_laps` is made only by the offline script (not by a migration), and the script always writes to the operator's home database `~/Documents/TITAN/titan_core.db` (no option changes it), so the exposure exists only where an operator imported lap files. The fix (an `athlete_id` on `activity_laps` with a migration, or refusing laps that match no owner run, or both) is a separate PR and a separate decision; the second option changes the control on purpose.
Deliverable: the four tests; an issue comment with the reproduction at this SHA.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1348; it closes with the fix PR.
Canonical doc update: this brief, the INT-NEW-01 fix closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, row 13 = #1347, #1348, reproduction only). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/test_athlete_lifecycle.py`, the records above. No `titan/`, `scripts/`, schema, AGENTS.md or ADR change.

---

## INT-NEW-01 / #1256 — fix: a run skipped as malformed makes the Garmin sync "partial", so H4 does not trust a TSB without it (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1510, squash `0e2fe19` (owner's decision card 2026-11-06: fix now); main green; issue #1256 closed (follow-up #1511: visibility of the skip, ADR-0080 text). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance input (H4). **Severity:** HIGH (issue; governance path, floor HIGH). **Change Type:** implementation. **Workflow Path:** A (category Α, tightening only).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1256 only. `GarminSync.sync_activities`: when the fetch succeeded but one or more runs were skipped as malformed, the activity fetch counts as failed for this sync, so `_sync_operation` returns `status="partial"` — the same status as a failed fetch (SD-04/SD-05). The morning then treats the TSB as unverified (`loads_complete` false): H4 applies `DATA_MISSING_CONSERVATIVE_H4` (EASY ceiling) unless the TSB already fires H4, which is stricter (ADR-0073 point 5, ADR-0080). The other runs are still returned and stored; the skip events are unchanged; the flag is per thread and reset at the start of each sync, so one bad morning does not mark the next. Trade-off, stated for the operator: a malformed run stays in Garmin's answer for as long as it is inside the sync window (`days_back`, 14 days for the morning), so each of those mornings is "partial" and capped at EASY unless H4 already fires; the run is never stored, so the TSB really lacks it. Out of scope: reading a malformed run instead of skipping it (a different change; the dropped-run test pins today's skip).
Deliverable: the change; the two strict-xfail cases of #1509 now pass with the mark removed; new tests (a sync without a skipped run is not partial; a skipped run in one sync does not mark the next). The partial-to-H4 step stays covered by `test_partial_sync_counts_tsb_as_missing_for_h4`.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1256 closes after merge and green main.
Canonical doc update: this brief, the reproduction brief's status line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3); merge waits for the owner's answer on fixing #1256 now (decision card of 2026-11-06, plan v3 row 10 is reproduction only). Category Α (tightening only, contract §13 not weakened: more mornings treat the TSB as unverified, none fewer). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `titan/integrations/garmin_sync.py` (`sync_activities` only), `tests/titan/integrations/test_garmin_sync.py`, the records above. No `daily_coach.py`, schema, threshold, AGENTS.md or ADR change.

---

## INT-NEW-01 / #1256 — reproduction only: a run skipped as malformed leaves the Garmin sync "ok" and its load out of the TSB (owner assignment, 2026-11-06)

**Status:** DONE 2026-11-06 — reproduction merged in PR #1509, squash `e13509f`; #1256 stays open for the fix (INT-NEW-01 fix brief above). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance input (H4). **Severity:** HIGH (issue; governance path, floor HIGH). **Change Type:** test-only. **Workflow Path:** A (plan v3 row 10: reproduction only, `REPRO_FIRST`).

Pass type: reproduction
Change Type: test-only
Workflow Path: Path A
Execution unit: #1256 reproduction at the current main, no application code. Three tests on the real `GarminSync._sync_operation` with a synthetic Garmin client: (1) control, a failed activity fetch makes the sync `partial` (passes); (2) a heavy run (25 km, average HR 175) with `duration="bad"` or a null `calories` is dropped from the activities, so its load never reaches the TSB, while the same run with `duration=9000` carries a load (passes); (3) a run skipped as malformed (`duration="bad"`, or a null `calories` as Garmin can send) makes the sync `partial` — `xfail(strict=True, raises=AssertionError)`, two cases: today the `status` key is absent, which the morning reads as complete loads (`loads_complete`, `daily_coach.py` step 5), so H4 can read CLEAR from a TSB without the run when the run would have moved the TSB past the floor. The skip is logged (`activity_skipped_malformed`, `activity_skip_summary`) but is not visible to the morning pipeline. Test (2) records today's drop; a fix that keeps the run changes it on purpose. The step from `partial` to `DATA_MISSING_CONSERVATIVE_H4` is already covered by `test_partial_sync_counts_tsb_as_missing_for_h4` (`tests/test_morning_baselines.py`). The fix is a separate PR; when it lands, the strict mark turns the third test red until it is removed.
Deliverable: the three tests (five cases); an issue comment with the reproduction at this SHA.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: this pass does not close #1256; it closes with the fix PR.
Canonical doc update: this brief, the AUTH-NEW-03 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, row 10 = #1256, reproduction only). No application change, so contract §13 is not touched. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `tests/titan/integrations/test_garmin_sync.py`, the records above. No `titan/`, `scripts/`, schema, AGENTS.md or ADR change.

---

## AUTH-NEW-03 / #1503 — a used refresh token replayed later ends every session of the user, also across API processes (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1508, squash `7d5def8`; main green; issue #1503 closed (tokens used before the change replay as a plain 401 until they expire; BOOLEAN wording is #1507). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — authentication. **Severity:** HIGH (issue; auth path, floor HIGH, ADR-0048). **Change Type:** implementation. **Workflow Path:** A (category Α, tightening only).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1503 only. A refresh token used by a refresh is marked `revoked = 2` (used); logout, the three-token limit and a revoke of every token still write `revoked = 1`. `/auth/refresh` sends a used token on to the rotation, which treats it as a replay: every unrevoked refresh token of the user is revoked and `REFRESH_TOKEN_REUSED` is logged (`sub` and an 8-character `jti` prefix only), however long after the first use it comes. A logged-out, limit-dropped, expired, unknown or other user's token is only refused (401, nothing else changes), so an old tab after logout ends no other session. The use, the new token, the three-token trim and the revoke are one `BEGIN IMMEDIATE` transaction (`rotate_auth_token`), so two API processes cannot leave the new token of a first use active after a second use. Logout revokes only an active token (`AND revoked = 0`), so a thief's logout with the old token cannot hide its replay; a logout that presents a used token revokes every refresh token of the user and logs `REFRESH_TOKEN_REUSED` (the victim's browser would never send it again), and a failure there is logged `LOGOUT_REPLAY_REVOKE_FAILED` while the logout still answers 200 and clears the cookies. Trade-off the issue asks for, stated for the operator: any replay of a used token ends every session of the user on every device, also a client's retry after a lost refresh response and a replay by anyone who holds a leaked old token (up to 7 days, at the refresh rate limit, or through logout, which has none); no grace window is added. The single-step helpers `consume_auth_token` and `revoke_auth_tokens_for_user` are removed (no caller left). `scripts/run_api.py` comment: the reuse check no longer needs one process; the in-memory rate limiters still do. Scope, on purpose: tokens used before this change carry `revoked = 1` and replay as a plain 401 until they expire (7 days at most). ADR-0048, `titan/core/schema.py` and the Alembic file declare `revoked` as BOOLEAN; the SQLite column is INTEGER without a CHECK and now holds 0, 1 or 2. The ADR text and the PostgreSQL gate (ADR-0044) item are a policy-only follow-up (#1507, LOW). No schema version or migration change.
Deliverable: the change and regression tests (a stolen token replayed later ends the thief's and every other session of the user and logs the reuse; a logged-out token and a token dropped by the three-token limit are only refused; a logout with a used token does not hide its replay; another user's token id is refused and changes nothing; two API processes on one database cannot leave the new token active; the victim's logout with a used token ends the thief's session; a failed revoke at logout still logs out), and the #1392/#1494 tests moved to the new rotation. 6 of the 8 new tests fail on main.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1503 closes after merge and green main.
Canonical doc update: this brief, the BKP-NEW-04 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3), and the owner's choice of 2026-11-06 to take #1503 right after #1496; category Α (tightening only, contract §13 not weakened: every new path answers 401 or revokes more, nothing refused today is accepted). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `titan/api/main.py` (refresh and logout), `titan/api/auth.py` (`AuthStore`, refresh-token encoding), `scripts/run_api.py` (comment only), `titan/core/database.py` and `titan/core/repositories/access.py` (auth-token methods), `tests/titan/api/test_auth.py`, `tests/test_db_repositories.py` (method list), the records above. No schema version, migration, token format, cookie, CSRF, AGENTS.md or ADR change.

---

## BKP-NEW-04 / #1496 — the restore drill fails a backup without this code's indexes, triggers or views, or with a trigger it does not make (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1506, squash `82e2c4c`; main green; issue #1496 closed (names only; the behaviour of the guard and the file `restore_backup.py` restores are #1505). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — governance / data recovery. **Severity:** HIGH (issue; governance path, floor HIGH, ADR-0052). **Change Type:** implementation. **Workflow Path:** A (category Α, tightening only).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1496 only. `scripts/restore_drill.py`: after the table and column check, every index, trigger and view (by type and name, SQLite's own `sqlite_…` objects left out) of a fresh database of this code must be in the restored copy, else the drill fails and names each one missing. It covers the H1–H5 guard triggers `trg_threshold_offsets_no_hard_stop_insert`/`_update` and the unique indexes `uq_governance_outcomes_athlete_date` and `idx_training_log_garmin_id`, which come only from the v34 step and are not made again when the database opens. A trigger the code does not make also fails it (it would run on every write once restored); an extra index or view does not. SQLite's own index names are left out with `substr`, not `LIKE`; no trigger or view is left out, whatever its name. The copy is read by its encoded path. Scope, on purpose: names only (a weakened trigger or a non-unique index with the right name passes, pinned by a test), and only the drill (`restore_backup.py` does not run it): follow-up #1505, HIGH.
Deliverable: the change and regression tests (a backup without each of those four objects fails and names it; opening the copy does not bring a dropped trigger back; every missing object is named; a trigger the code does not make fails; an extra index or view passes; the names-only limit; a trigger named like SQLite's own never passes). 6 tests fail on main.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1496 closes after merge and green main.
Canonical doc update: this brief, the AUTH-NEW-02 closure line, the RUNBOOK_DR step-1 sentence, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, next = #1496), category Α (tightening only, contract §13 not weakened: the drill fails on more backups, never on fewer). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `scripts/restore_drill.py`, `tests/test_backup_dr.py`, one sentence in `docs/RUNBOOK_DR.md`, the records above. No schema, migration, `titan/`, `scripts/restore_backup.py`, AGENTS.md or ADR change.

---

## AUTH-NEW-02 / #1494 — a refresh token used twice at the same moment revokes every refresh token of the user (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1504, squash `8d480f9`; main green; issue #1494 closed (overlapping uses only; a later replay is #1503). This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — authentication. **Severity:** HIGH (issue; auth path, floor HIGH, ADR-0048). **Change Type:** implementation. **Workflow Path:** A (category Α, tightening only).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1494 only. `/auth/refresh`: when the one-statement use of the refresh token finds it already used (the second request of a race, `REFRESH_TOKEN_REUSED`), every unrevoked refresh token of that user is revoked in one statement (`revoke_auth_tokens_for_user`), and the answer stays 401. `AuthStore.rotate_refresh_token` holds the store lock from the use to the new token, so the revoke for a second use runs after the first use's new token exists and revokes it too. A failure of the use, the new token or the revoke answers 401 and logs `REFRESH_ROTATION_FAILED`. The reuse log names `sub` and the first 8 characters of the `jti`, never the token or the whole `jti`. Scope, on purpose: only two uses that overlap (the second passes the active check before the first used the token) are caught; a later replay of a token already rotated still gets a plain 401 without the revoke, because rotation and logout are not told apart today (follow-up #1503, HIGH). A client that sends two refreshes at once, or a logout that overlaps a refresh, now ends every session of that user (password login again on every device); that is the trade-off the issue asks for. The lock order relies on one API process (`scripts/run_api.py`, comment added; several processes: #1503).
Deliverable: the change and regression tests (a reuse ends every session of the user, also the one the first use was given, and not another user's; the log has `sub` and a `jti` prefix only; a failed revoke still answers 401 with no cookie; the store revokes only that user's tokens; the #1392 race now leaves no active token). 5 tests fail on main.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1494 closes after merge and green main.
Canonical doc update: this brief, the DR-NEW-06 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, next = #1494), category Α (tightening only, contract §13 not weakened: every new path answers 401, nothing refused today is accepted). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `titan/api/main.py` (refresh only), `titan/api/auth.py` (`AuthStore`), `scripts/run_api.py` (comment only), `titan/core/database.py` and `titan/core/repositories/access.py` (one revoke method), `tests/titan/api/test_auth.py`, the records above. No schema, token format, cookie, CSRF, logout, AGENTS.md or ADR change.

---

## DR-NEW-06 / #1497 — a restore loses no consent withdrawal from a damaged database or with --skip-live-withdrawals (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1502, squash `79c3219`; main green; issue #1497 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — consent / data recovery. **Severity:** HIGH (issue; consent path, floor HIGH, ADR-0079). **Change Type:** implementation. **Workflow Path:** A (category Α, tightening only).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1497 only. `scripts/restore_backup.py`: the scratch copy of the database being replaced (and of a kept one) must pass `PRAGMA quick_check`, else it counts as unreadable and the restore stops; `consent_log` is read `NOT INDEXED`; each athlete's latest withdrawal is chosen by time, not text; with `--skip-live-withdrawals` every athlete of the backup but the owner gets a withdrawal dated now (`CONSENT_WITHDRAWN_RESTORE_UNVERIFIED`), so each gives consent again with /agree; the database is kept before its `-wal` and `--again` names the step left after a stop in between; a stale staging file (`.partial`/`.restoring`) is removed before an exclusive `O_NOFOLLOW` create, and a symlink or hard link there is refused; with the skip flag a clock behind a consent time in the backup stops the restore; a time without an offset is read as UTC; the backup is opened read-only by its encoded path, and a backup path with `?`, `#` or `%` is refused. The two runbook restore steps, including the 30-day re-consent window.
Deliverable: the change and regression tests (a damaged consent index stops the restore; the skip flag withdraws every athlete but the owner; a consent given after the restore is kept; the latest withdrawal compared as a time; a symlink at a staging name is refused; `--again` reads the kept database; a stop between keeping the database and its `-wal` can be finished; a clock behind the backup stops the skip; an athlete without a consent row is included; a damaged kept database stops `--again`; a time without an offset is read as UTC; the withdrawals are read without the index; a hard link at a staging name is refused; a backup path with URI characters is refused, also through a symlinked directory). 15 tests fail on main.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1497 closes after merge and green main.
Canonical doc update: this brief, the M0-13-R2 closure (brief, table row, docs/audits/FINDINGS.md), CLAUDE.md test snapshot, docs/governance/ledger.jsonl, the two runbook restore steps.
Authorizes: Owner instruction 2026-11-05 to fix the plan issues in order (#1434 plan v3, next = #1497), category Α (tightening only, contract §13 not weakened: an unreadable or damaged database still stops the restore, and the skip flag now withdraws consent instead of keeping it). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with independent review and the extra security review.
Allowed / Forbidden: `scripts/restore_backup.py`, `tests/test_restore_backup.py`, `docs/RUNBOOK_DR.md`, `docs/runbooks/database-recovery.md`, the records above. No schema, queue format, drain, `titan/`, AGENTS.md or ADR change.

---

## M0-13-R2 / #1268 — the Garmin account is also its stable profileId (ADR-0083 implementation, owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1500, squash `0ea806b`; main green; issue #1268 closed. This entry is only the brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — athlete isolation / authorization. **Severity:** HIGH (issue; authorization path, floor HIGH). **Change Type:** implementation. **Workflow Path:** B (category Β, ADR-0083 Accepted, D-223). Only tightens: every new check refuses, nothing that is refused today is accepted.

Pass type: implementation
Change Type: implementation
Workflow Path: Path B
Execution unit: #1268 only, exactly ADR-0083 points 1–7. Schema v36 (`athlete_accounts.garmin_profile_id` with CHECK and partial unique index; `owner_garmin_profile_history` with no-delete/no-update triggers; athletes bound without a profileId set to 'expired' on the version change). One shared validator (`valid_garmin_profile_id`). The owner's connection writes name and profileId independently in one `BEGIN IMMEDIATE` transaction with the point-6 expiry on the stored values. Relogin and `bind_garmin_account` refuse the owner's account by name or by any recorded profileId and stay closed while either is unknown; the bind and the final conditional 'ok' are `BEGIN IMMEDIATE` transactions; a refused 'ok' removes the token just written. `_token_account_matches` accepts a token only when both values are valid, equal to the bound ones and not the owner's; no database, an empty or unreadable owner record → refused. Both worker places pass `db=` and the profileId; a row without a profileId is unbound. No new module.
Deliverable: the change, the ADR's test list (tests/test_owner_garmin_profile_id.py, the schema-equivalence comparison of indexes, CHECKs and triggers between a fresh and a v35→v36 database, the runbook SQL block test), existing fixtures updated to bind with a profileId, runbook `multi-athlete.md` (§0 note, §4 logs, §6 manual step), full canonical gates, independent code review plus the extra security review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1268 closes after merge and green main; M0-13-R2 then RESOLVED in the table below and in docs/audits/FINDINGS.md.
Canonical doc update: this brief, the M0-13-R2 row, the ING-NEW-01 closure line, CLAUDE.md schema line and test snapshot, docs/governance/ledger.jsonl.
Authorizes: ADR-0083 (Accepted 2026-11-06, D-223) and the owner's instruction of 2026-11-06 to implement it in a separate PR after the ADR (#1434 plan v3, order 1). Merge: the owner's standing merge authorization of 2026-11-05 with its four conditions, including the extra security review for HIGH.
Allowed / Forbidden: `titan/core/athlete.py`, `titan/core/database.py`, `titan/core/repositories/access.py`, `titan/core/repositories/migrations.py`, `titan/core/schema.py`, `titan/integrations/garmin_sync.py`, `titan/worker/__init__.py`, `docs/runbooks/multi-athlete.md`, tests, the records above. No AGENTS.md or ADR text change, no H1–H5 or owner-morning change, no change to the owner's `.env` reading.

---

## ING-NEW-01 / #1347 — the lap import writes cardiac drift only to the owner's row of its own activity (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1498, squash `a6a43a1`; main green; issue #1347 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — athlete isolation / data integrity. **Severity:** HIGH (issue). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies ADR-0040 (athlete isolation) and ADR-0067 (multi-athlete).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1347 only. `scripts/import_activity_laps.py` writes the cardiac drift to `training_log` only where the Garmin activity id (the digits in the lap file name, unique) and the owner (`athlete_id = 'owner'`, the script works on the owner's database) both match; it no longer updates every row of the date, and the date is not used as an identity (training_log keeps the UTC day, the lap export the local one). No id in the file name or no matching row → nothing is written to `training_log`, the drift stays in `activity_laps` and the script says so. `activity_laps` writes are unchanged.
Deliverable: the change, regression tests (the issue's fixture: two owner runs and another athlete's run on one day → only the owner's row of that activity changes; a local date that differs from the stored UTC day still finds it; an activity with no training row, a file name without an id and another athlete's activity id change nothing), the existing write test updated to the real column, full canonical gates, independent review plus the extra security review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1347 closes after merge and green main.
Canonical doc update: this brief, the DR-NEW-02 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1347), category Α (tightening only). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions, including the extra security review for HIGH.
Allowed / Forbidden: `scripts/import_activity_laps.py`, `tests/test_import_activity_laps.py`, the records above. No schema, `titan/`, activity_laps format, AGENTS.md or ADR change.

---

## DR-NEW-02 / #1252 — the backup copies the database and the pending-audit queue as one snapshot (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1493, squash `ac1cd91`; main green; issue #1252 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — consent / data recovery. **Severity:** HIGH (issue; consent path, floor HIGH). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies ADR-0079 §4 (a withdrawal always takes effect; the queue lock is taken before the database lock).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1252 only. `backup_database` (`titan/core/repositories/operations.py`) copies the database and reads the queue file under one shared queue lock (queue lock, then `DatabaseManager._lock`, as everywhere); a drain takes the lock exclusively, so it cannot move a withdrawal from the queue into the database between the two copies. After verification the queue copy is written in full under a temporary name, fsynced and renamed BEFORE the database copy gets its dated name; with no queue an older same-day copy is removed; a queue that cannot be copied fails the backup like a bad database copy (CRITICAL, counted, `.corrupt`) instead of leaving a backup without its queue; the database copy is owner-only. `scripts/backup.sh` takes the same shared lock with Python `fcntl` (no `flock` binary needed) around both copies, checks integrity after letting go, renames the queue copy before the database copy and cleans its partial files on any failure.
Deliverable: the two changes, regression tests (a drain right after the database copy no longer loses the withdrawal on restore; a drain started during the copy waits; a queue that cannot be copied fails the backup; a backup without a queue removes an older copy and is owner-only; the shell backup waits for the queue lock before copying the database and its copy restores with the withdrawal), full canonical gates, independent review plus the extra security review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1252 closes after merge and green main. A rollback of token revocations (#1255) stays separate.
Canonical doc update: this brief, the DR-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1252), category Α (tightening only, contract §13 not weakened: no failure path skips the queue copy that existed before). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions, including the extra security review for HIGH.
Allowed / Forbidden: `titan/core/repositories/operations.py` (backup only), `scripts/backup.sh`, `tests/test_restore_backup.py`, the records above. No schema, queue format, drain, `daily_coach.py`, `titan/main.py`, `worker/__init__.py`, `telegram_bot.py`, AGENTS.md or ADR change.

---

## DR-NEW-01 / #1251 — a restore brings back the pending-audit queue with the database (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1492, squash `a89a5a1`; main green; issue #1251 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — consent / data recovery. **Severity:** HIGH (issue; consent path, floor HIGH). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies ADR-0079 (a withdrawal always takes effect, also after a restore) and AGENTS DR-03.

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1251 only. New `scripts/restore_backup.py` (a script, not a `titan/` module; the module ceiling is unchanged): checks the backup, reads its pending-audit queue copy with the queue's own reader (unreadable → nothing changed, exit 1), also reads every withdrawal recorded in the database being replaced (and in a kept one) from a scratch copy with its `-wal` (unreadable → stop, unless `--skip-live-withdrawals` after a manual check), then under the queue lock adds all of them to the data directory's queue keeping those already waiting, keeps the current `-wal` then database as `.before-restore` (owner-only, fsynced, renamed into place), stages the backup and only then removes the old `-wal`/`-shm` and renames it in; refuses a newer schema, a symlinked queue copy, overwriting a kept copy (`--again` for a later try) and an `--again` that would drop a `-wal` that was not kept. `scripts/restore_drill.py` restores the queue copy beside the scratch copy, writes it as the worker does at start, and fails when a withdrawal stays queued or a stopped athlete still has a current consent. The runbook restore steps (RUNBOOK_DR.md step 3, database-recovery.md Scenario B) call the script instead of copying the database alone; their RC-02/RC-03 tests now run that command.
Deliverable: the script, the drill check, the runbook steps, regression tests (a database-only restore turns consent back on — the finding; the script keeps the withdrawal, keeps one recorded after the backup, stops on an unreadable current database unless skipped, changes nothing on an unreadable live queue, refuses a symlinked copy and an unsafe `--again`, writes owner-only files, reports a missing queue copy, keeps the withdrawals already waiting, is not hidden by a "done" marker, stops on an unreadable copy, never overwrites a kept copy, pairs a manual backup with its copy, works from the command line; the drill writes the copy, fails on an unreadable one and when a stopped athlete keeps consent), full canonical gates, independent review plus the extra security review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1251 closes after merge and green main. A drain between the database and the queue snapshot (#1252) and a rollback of token revocations (#1255) are separate issues; the joint recovery acceptance D03 stays with them.
Canonical doc update: this brief, the BKP-NEW-02 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl, the two runbook restore steps.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1251), category Α (tightening only, contract §13 not weakened: a withdrawal is never dropped, an unreadable queue stops the restore). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions, including the extra security review for HIGH.
Allowed / Forbidden: `scripts/restore_backup.py` (new), `scripts/restore_drill.py`, `tests/test_restore_backup.py` (new), `tests/test_backup_dr.py`, `docs/RUNBOOK_DR.md`, `docs/runbooks/database-recovery.md`, the records above. No `titan/` change, no schema, backup producer, AGENTS.md or ADR change.

---

## BKP-NEW-02 / #1452 — the restore drill checks this code's schema and that the code can open the copy (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1491, squash `e10ae17`; main green; issue #1452 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 2 — data recovery. **Severity:** MEDIUM (issue). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies AGENTS DR-03 (the restore drill shows the latest real backup is a usable TITAN database).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1452 only: `scripts/restore_drill.py` keeps its checks (integrity, `user_version` equal to SCHEMA_VERSION, core tables) and adds three, all on the scratch copy: (1) every table and column of a fresh database that this code creates in the scratch directory is present in the copy (no hand-kept list; an upgraded database has the same tables and columns, `tests/e2e/test_legacy_db_upgrade.py`); (2) the owner's athlete row is present, checked read-only before the code opens the copy (opening would seed it); (3) the code opens the copy (`DatabaseManager`) and reads it: an athlete's activities and a refresh-token lookup (`AuthStore`). Any failure is reported and the drill exits 1. The backup itself is never opened for writing. The drill's role in phase close (AGENTS DR-03 phase-close evidence) is unchanged.
Deliverable: the three checks, regression tests (core table names without their columns, a missing operational table, a missing column in an operational and in a core table, a copy without the owner row, a copy the code cannot read → fail; a valid backup passes and is byte-for-byte unchanged), full canonical gates, independent review with the extra review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1452 closes after merge and green main. The joint recovery acceptance D03 (#1451 #1452 #1251 #1252 #1255) stays with those issues.
Canonical doc update: this brief, the BKP-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1452), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; condition (4) applies only to HIGH/CRITICAL, this issue is MEDIUM, and an extra review is still run.
Allowed / Forbidden: `scripts/restore_drill.py`, `tests/test_backup_dr.py`, the records above. No schema, worker backup, `verify_backup.py`, version policy or `titan/` change.

---

## BKP-NEW-01 / #1451 — a manual backup passes verification only when it is a usable TITAN database (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1490, squash `3432be7`; main green; issue #1451 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — data recovery. **Severity:** HIGH (issue). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies AGENTS DR-02/DR-03 (a backup is checked before it is relied on; the restore drill's core tables).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1451 only: (1) `scripts/backup.sh` writes the manual backup under a hidden `.titan_core.db.YYYYMMDD.partial` and renames it only after the copy finished, so an interrupted backup never has the finished name; (2) `scripts/verify_backup.py` checks only finished `titan_core.db.YYYYMMDD` files (never a partial or a SQLite sidecar) and passes one only when it is a usable TITAN database: not empty, integrity `ok`, `user_version` from 1 to SCHEMA_VERSION (older migrates on start as before; newer is refused, as the code itself refuses it), and the restore drill's core tables present. The runbook paragraph says so. No change to the worker's automated backups, the restore drill (#1452) or any compatibility policy beyond refusing what the code cannot open.
Deliverable: the two script changes, regression tests (0-byte, non-TITAN, TITAN version without core tables, no athletes, newer version, symlink → fail; older version and current → pass; a backup that stops before the rename leaves no finished file; a partial or sidecar file is never the one verified; a finished backup is owner-only and leaves no partial), full canonical gates, independent review with the extra review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1451 closes after merge and green main. The joint recovery acceptance D03 (#1451 #1452 #1251 #1252 #1255) stays with those issues.
Canonical doc update: this brief, the AUTH-NEW-01 closure line, `docs/runbooks/database-recovery.md` (Backup Verification paragraph), CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1451), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; HIGH issue, so condition (4) needs the extra independent review.
Allowed / Forbidden: `scripts/backup.sh`, `scripts/verify_backup.py`, `tests/test_backup_verification.py`, `docs/runbooks/database-recovery.md` (that paragraph), `.github/workflows/ci.yml` (only the backup-integrity step's test database, now a real synthetic TITAN database), the records above. No schema, worker backup, restore drill or `titan/` change.

---

## AUTH-NEW-01 / #1392 — a refresh token is used once, also by two refreshes at the same moment (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1489, squash `85e79b3`; main green; issue #1392 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — authentication. **Severity:** HIGH (issue; authentication path). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies ADR-0048 (refresh rotation on every use; the old token is invalidated).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1392 only: `/auth/refresh` uses the old refresh token up in one check-and-revoke SQL statement (`UPDATE ... WHERE id = ? AND revoked = 0`, row count 1). Only the request whose statement revoked it gets a new session; a concurrent second request with the same token gets 401 (`REFRESH_TOKEN_REUSED`). A failed statement rolls back and fails the request. Login, logout, the active check and token creation are unchanged.
Deliverable: the atomic consumption, regression tests (two refreshes with one token held together after the active check → one 200, one 401, one active token; the store consumes a token once, an unknown token never), full canonical gates, independent review with the extra security review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1392 closes after merge and green main.
Canonical doc update: this brief, the BIO-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1392), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is an authentication change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/core/repositories/access.py` (`consume_auth_token`), `titan/core/database.py` (its wrapper), `titan/api/auth.py` (`consume_refresh_token`), `titan/api/main.py` (`/auth/refresh` only), `tests/titan/api/test_auth.py`, `tests/test_db_repositories.py` (facade list), the records above. No schema, cookie, CSRF, rate-limit, token-lifetime or login change.

---

## BIO-NEW-01 / #1456 — a same-day HRV resync above 300 ms counts as missing; a stricter earlier result stays (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1488, squash `3055433`; main green; issue #1456 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — safety gate (H2). **Severity:** HIGH (issue; governance/safety-gate path). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies the accepted ADR-0073 point 2 (today's HRV above 300 ms counts as missing, H2 missing-data ceiling; an older stricter REST does not loosen).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1456 only: when the morning sync sends a reading for the routine's own day above the HRV ceiling, the coach tells governance (`today_hrv_rejected`), and H2 applies its missing-data EASY ceiling (`DATA_MISSING_CONSERVATIVE_H2`) even though the database and the HRV engine kept an earlier valid reading of the day. That earlier reading still runs every gate, so a REST it gives stays REST. The missing-input message names HRV. Without such a reading nothing changes; 300 ms stays a reading.
Deliverable: the flag, regression tests (real morning: earlier 76 then 400 → EASY ceiling with the lock; earlier 35 then 400 → REST with both locks; earlier 76 then 300 → no lock; the flag only for the routine's own day; governance boundary on/off), full canonical gates, independent review with the extra safety-gate review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1456 closes after merge and green main.
Canonical doc update: this brief, the TIME-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner decision 2026-11-06 on the decision card "Αν το ίδιο πρωί έρθει HRV πάνω από 300, τι μετρά;": option "Το αυστηρότερο" (the reading counts as missing, EASY; if the earlier reading already gave REST, REST stays). Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is a safety-gate change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/science/governance_engine.py` (H2 missing condition only), `titan/orchestration/contracts.py` (the context field), `titan/orchestration/daily_coach.py` (`_today_hrv_rejected`, the context call, `_missing_inputs` label only), `tests/test_morning_baselines.py`, `tests/test_governance_mutation.py`, the records above. No threshold, bounds, schema, persistence (UPSERT) or gate-order change.

---

## TIME-NEW-01 / #1442 — a morning that crosses UTC midnight keeps the claimed day's planned session (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1487, squash `623bfb2`; main green; issue #1442 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — training prescription. **Severity:** HIGH (issue). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies D-109 (the claimed day, not the clock, dates the whole routine) and D-020 (Sunday builds the plan of the week that starts on Monday).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1442 only: the weekly planner takes a planning day. The worker sets it to the claimed routine day before the plan is loaded, so the day's planned session, the Sunday plan's `week_start` and the recent-volume window all use the claimed day, also when the run crosses UTC midnight. Without a planning day (console, API) the planner keeps the UTC date as before.
Deliverable: the planning day, regression tests (claimed Sunday run at Sunday 23:59, Monday 00:01 and Monday 02:30 keeps Sunday's REST and builds the Monday week; the planner alone: session, week_start and volume window follow the planning day; control: without a planning day the clock day is kept), full canonical gates, independent review with the extra safety review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1442 closes after merge and green main.
Canonical doc update: this brief, the DEL-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1442), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; the issue is HIGH and changes the prescribed session, so condition (4) needs the extra independent safety review.
Allowed / Forbidden: `titan/features/weekly_planner.py` (`planning_day`, `_today` and its three readers), `titan/worker/__init__.py` (`_run_morning` only), `tests/test_worker_weekly_plan.py`, `tests/titan/features/test_weekly_planner.py`, the records above. No schema, threshold, gate, template or `daily_coach.py` change.

---

## DEL-NEW-01 / #1444 — a late delivery of a superseded attempt never closes the newer day (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1486, squash `cc65721`; main green; issue #1444 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — delivery record / safety. **Severity:** HIGH (issue). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies M0-01 (the attempt number is the fencing token) and ADR-0067 D8.3/D8.4 (a day is delivered once; after the last failed attempt Zaf is told and the day is left).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1444 only: a worker attempt records its delivery with its attempt number, checked in the same SQL statement: only while that attempt is still the day's latest and the day is open. A delivery that arrives after a later attempt took the day over closes nothing and leaves the later attempt's "sending" mark alone; the later attempt's own delivery or failure (and the last-attempt warning to Zaf) stays as it is. A delivery remembered as unrecorded keeps its attempt number. Calls without an attempt are unchanged.
Deliverable: the fence, regression tests (the issue's interleaving in two connections and threads: old acknowledgement then the newer REST refused, the day stays open and is then left with Zaf told; old acknowledgement then the newer REST accepted; the fence at the database: superseded, owning, already closed), full canonical gates, independent review with the extra safety review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1444 closes after merge and green main.
Canonical doc update: this brief, the CR-NEW-02 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1444), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is a delivery-record change on the safety path, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/core/repositories/operations.py` (`mark_routine_delivered` only), `titan/core/database.py` (its wrapper), `titan/worker/__init__.py` (`_mark_delivered`, `_UNRECORDED_SENDS` and the calls passing the attempt), `tests/test_worker_morning_retry.py`, the records above. No schema, retry, claim, budget or message change.

---

## CR-NEW-02 / #1248 — a superseded morning attempt never overwrites the newer decision (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1485, squash `f6c0f68`; main green; issue #1248 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — safety gate / governance record. **Severity:** HIGH (issue; governance path). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies M0-01 (the attempt number is the fencing token; an attempt that no longer owns the day records and sends nothing) and ADR-0067 D8.4 (one decision per athlete and day).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1248 only: a worker attempt writes the day's decision with a fence `(routine_type, attempt)`; the governance upsert, the in-place replace and the resume write check, in the writing SQL statement itself, that the attempt is still the day's latest and the day is open. A refused write records nothing (database or memory), marks the attempt lost, skips the resume hook, and the send step then sends nothing. The attempt's "sending" mark is fenced the same way, and a failed fenced write rolls back so no stale snapshot stays open on the shared connection. Writes outside the worker (no fence) are unchanged.
Deliverable: the fence, regression tests (the issue's interleaving with a second connection: attempt 1 passes its check, attempt 2 records and delivers REST, attempt 1 then writes TEMPO, for a first and a recomputed decision; refused writes for a superseded, delivered or left day; fenced decision without a database; the superseded attempt's sending mark; a failed fenced write leaves no transaction open; control: the owning attempt records), full canonical gates, independent review with the extra safety-gate review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1248 closes after merge and green main. #1444 (delivery ACK) and #1445 (weekly plan) are separate issues and stay open.
Canonical doc update: this brief, the CR-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1248), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is a governance-path change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/core/repositories/governance.py` (`save_governance_decision`, `replace_governance_decision_on` and the fence helper), `titan/core/repositories/operations.py` (`update_routine_resume` only), `titan/core/database.py` and `titan/core/persistence.py` (their wrappers and the adapter interface; the PostgreSQL adapter refuses a fenced write), `titan/science/outcome_tracker.py` (`record_decision` and `DecisionNotRecorded`), `titan/orchestration/daily_coach.py` (record-outcome handler and `_decision_fence` only), `titan/worker/__init__.py` (`_bind_day` and the sending-mark helpers only), `tests/test_worker_morning_retry.py`, the records above. No schema, gate, threshold, delivery-ACK or weekly-plan change.

---

## CR-NEW-01 / #1247 — a resent stored decision never sends a quality session while an injury is open (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1484, squash `3ae1903`; main green; issue #1247 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — safety gate (H1). **Severity:** HIGH (issue; governance/safety-gate path). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies the accepted ADR-0069 §3 (an open `/injury` triggers H1 and the morning is REST) and D-109 (a retry resends only while the inputs are unchanged).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1247 only: (1) the day's inputs hash (`routine_inputs_fingerprint`) also covers the athlete's open injury, only when one is open, so an injury opened after the stored decision makes a retry compute the day again through the gated pipeline; (2) every resend of a stored decision (retry, its at-most-EASY fallback, the console's `/today`) sends REST while an injury is open, and also when the injury state cannot be read (fail closed, as `DailyCoach._injury_flag`). Without an open injury nothing changes.
Deliverable: the two changes, regression tests (retry after an injury computes again, fallback sends REST not EASY, unreadable state sends REST, `/today` under an open injury and under an unreadable state, hash follows only this athlete's open injury; controls: no injury, another athlete's injury, closed injury), full canonical gates, independent review with the extra safety-gate review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1247 closes after merge and green main.
Canonical doc update: this brief, the PRIV-NEW-02 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1247; #1456 waits on the owner's decision), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is a safety-gate change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/core/repositories/operations.py` (`routine_inputs_fingerprint` only), `titan/worker/__init__.py` (`_send_stored_decision` and its new injury read only), `tests/test_worker_morning_retry.py`, `tests/test_today_command.py`, the records above. No schema, threshold, gate order, `/injury` command or `daily_coach.py` change.

---

## PRIV-NEW-02 / #1379 — a Garmin sync stores nothing after a /stop or deletion that landed during the fetch (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1483, squash `207493c`; main green; issue #1379 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — privacy/consent. **Severity:** HIGH (issue; consent path). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies the accepted ADR-0067 D4.3 and D6.1 and ADR-0079 (a withdrawal or deletion stops all processing).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1379 only: every Garmin write of `titan/orchestration/garmin_persistence.py` (`persist_garmin_data`, `backfill_training_history`, `rewrite_recent_hrv_once`) for an athlete other than the owner first checks, as the first read of its write transaction, that the athlete still exists, has no deletion recorded and has current consent (database and pending-audit queue). Otherwise nothing of the sync is written; any error counts as "may not". In WAL mode a /stop or deletion committed after that read makes the writes fail, so the whole sync rolls back. The athlete's /sync answers that nothing was stored. In the morning pipeline the refusal ends the morning for that athlete: nothing more is written or sent, and the worker's next attempt stops at its consent check. The owner is exempt (D4.5).
Deliverable: the check, the /sync reply (also when the token state can no longer be written for a deleted athlete), the end of the morning on a refusal, regression tests (/stop and deletion during the athlete's /sync through the worker, /stop during the morning's fetch, /stop before the write, /stop committed after the check, deletion, pending deletion, unreadable consent, backfill and HRV rewrite; controls: athlete with consent, owner), three existing per-athlete tests now enrol their athlete with consent, a precondition (assertions unchanged), full canonical gates, independent review with the extra consent-path review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1379 closes after merge and green main; with #1245 and #1380 already closed, this completes the joint acceptance D04 of plan v2.
Canonical doc update: this brief, the ISO-NEW-02 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1379), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is a consent-path change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/orchestration/garmin_persistence.py`, `titan/orchestration/daily_coach.py` (step 2 refusal only), `titan/worker/__init__.py` (`sync_athlete_on_request` only), `tests/titan/orchestration/test_garmin_persistence.py`, `tests/test_telegram_per_athlete.py`, `tests/test_morning_baselines.py`, `tests/test_garmin_per_athlete.py` and `tests/test_athlete_isolation_behavioral.py` (consent precondition only), the records above. No schema or foreign-key change, no consent rule, threshold or owner change.

---

## ISO-NEW-02 / #1245 — a /stop after an athlete's sender was built ends its sending (owner assignment, 2026-11-06)

**Status:** RESOLVED 2026-11-06 — PR #1482, squash `d94b344`; main green; issue #1245 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — consent/athlete isolation. **Severity:** HIGH (issue; consent path). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies the accepted ADR-0067 D4.3 (a withdrawal stops coaching) and ADR-0079 (the withdrawal always takes effect, a queued one already counts).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1245 only: `TitanTelegramBot.send_message` of an athlete other than the owner also requires the athlete's current consent before every send, through the existing `_has_consent` (database consent, pending-audit queue, recorded deletion; an unreadable answer counts as none). Without it nothing is sent, the send returns False and a CRITICAL is logged. The owner is exempt (D4.5).
Deliverable: the check, regression tests (/stop through the real handler after the sender was built, /stop held only in the pending-audit queue, recorded deletion, unreadable consent, unreadable deletion record, unreadable pending-audit queue; controls: operator alert still reaches the owner only, another athlete's /stop, owner not checked), full canonical gates, independent review with the extra consent-path review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1245 closes after merge and green main; the joint acceptance D04 of plan v2 (#1245, #1379, #1380) stays with #1379.
Canonical doc update: this brief, the ISO-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1245), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is a consent-path change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/integrations/telegram_bot.py` (`send_message` only), `tests/test_telegram_per_athlete.py`, the records above. No schema, consent rule, queue format, worker retry or message-content change.

---

## ISO-NEW-01 / #1244 — an athlete's sender sends only to the chat still bound to that athlete (owner assignment, 2026-11-05)

**Status:** RESOLVED 2026-11-06 — PR #1481, squash `ba9b660`; main green; issue #1244 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — athlete isolation. **Severity:** HIGH (issue; recipient authorization). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies the accepted ADR-0040 (athlete isolation) and ADR-0067 D10.1 (an athlete's messages go to their own private chat).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1244 only: `TitanTelegramBot.send_message` of an athlete other than the owner reads the athlete's binding again before every send and sends only when the stored canonical chat is still the sender's chat. Moved chat, chat now bound to another athlete, missing row, no database or a failed read: nothing is sent, the send returns False and a CRITICAL is logged (fail closed). The owner's sender (TELEGRAM_CHAT_ID from .env) is unchanged.
Deliverable: the check, regression tests (the issue's A→B rebind through the worker's own sender, moved chat, missing account, unreadable binding, no database, no stored chat, legacy non-canonical stored chat; controls: unchanged chat, new sender after the move, owner), full canonical gates, independent review with the extra authorization-path review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1244 closes after merge and green main.
Canonical doc update: this brief, the PRIV-NEW-03 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, next = #1244), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions; this is an authorization-path change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/integrations/telegram_bot.py` (`send_message` and its new check only), `tests/test_telegram_per_athlete.py`, the records above. No schema, binding rule, worker retry or message-content change.

---

## PRIV-NEW-03 / #1380 — a damaged deletion record leaves no recorded athlete ready (owner assignment, 2026-11-05)

**Status:** RESOLVED 2026-11-05 — PR #1479, squash `aedf0b2`; main green; issue #1380 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — privacy. **Severity:** HIGH (issue). **Change Type:** implementation (regression evidence). **Workflow Path:** A. Category Α.

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1380 only. Re-check on main `cf7b74e`: the fix for #1378 (PR #1477) already makes a damaged record stop every athlete but the owner (`deletion record unreadable`), and the failed replay is logged at CRITICAL (`worker_athlete_housekeeping_failed`) with Zaf told once a day per athlete. This pass adds the regression for the issue's own scenarios (damaged first line, middle line, interrupted tail), including the owner notice from the real scheduler path; no application code changes.
Deliverable: parametrized regression test (fails on `5d20bb8`, passes on `cf7b74e`), full canonical gates, independent review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1380 closes after merge and green main. The 30-day purge that the same failed replay skips is issue #1478.
Canonical doc update: this brief, the PRIV-NEW-01 closure line, CLAUDE.md test snapshot, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, order 3 = #1380), category Α. Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01) with its four conditions.
Allowed / Forbidden: `tests/test_athlete_lifecycle.py` and the records above. No application code, schema or record-format change.

---

## PRIV-NEW-01 / #1378 — a recorded deletion stops the athlete until it finishes (owner assignment, 2026-11-05)

**Status:** RESOLVED 2026-11-05 — PR #1477, squash `cf7b74e`; main green; issue #1378 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — privacy/data integrity. **Severity:** HIGH (issue; consent path). **Change Type:** implementation. **Workflow Path:** A. Fix category Α: only tightens, applies the accepted ADR-0067 D6.1 ("First the athlete leaves the scheduler").

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1378 only: an athlete named in the deletion record is not ready (worker `_require_consent`) and has no consent for its own Telegram commands (`_has_consent`) until `reapply_deletions` removes the rows; an unreadable record counts as pending (fail closed); the owner is exempt (D4.5) and nothing changes when no record file is set (no deletion can be recorded then).
Deliverable: `athlete_lifecycle.deletion_pending`, the two checks, no consent or audit row from `/agree` while pending, no new id taken from the record, regression tests (failed delete, regular housekeeping, restart, reapply, Telegram, `/agree`, new id, unreadable record, other-athlete and owner controls), runbook line, full canonical gates, independent review with the extra consent-path review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1378 closes after merge and green main; the joint acceptance D04 of plan v2 (#1245, #1379, #1380) stays with those issues.
Canonical doc update: this brief, the DB-NEW-01 closure line, CLAUDE.md test snapshot, docs/runbooks/multi-athlete.md, docs/governance/ledger.jsonl.
Authorizes: Owner instruction 2026-11-05 to fix the plan-v2 issues in order (#1434, order 2 = #1378), category Α (tightening only, contract §13 not weakened). Merge: the owner's standing merge authorization of 2026-11-05 (transcribed in DB-NEW-01 above) with its four conditions; this is a consent-path change, so condition (4) needs the extra independent security review.
Allowed / Forbidden: `titan/core/athlete_lifecycle.py`, `titan/worker/__init__.py` (`_require_consent` only), `titan/integrations/telegram_bot.py` (`_has_consent`, `/agree` and their shared check only), `add_athlete` id choice, `tests/test_athlete_lifecycle.py`, the records above. No schema, threshold, consent text, retention or deletion-timing change; no automatic re-deletion outside start and the CLI.

---

## DB-NEW-01 / #1412 — training writers respect the enclosing transaction (owner assignment, 2026-11-05)

**Status:** RESOLVED 2026-11-05 — PR #1475, squash `5d20bb8`; main green; issue #1412 closed. This entry is only the Path A brief AGENTS §17.2/§17.4 E16 requires. **Tier:** 1 — data integrity (SQLite transaction atomicity). **Severity:** MEDIUM (issue). **Change Type:** implementation. **Workflow Path:** A. Fix category Α (tightens, no policy change).

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: #1412 only: `add_shoe`, `update_shoe_mileage`, `save_personal_best`, `log_cs_performance` commit only when no transaction is open, as `save_session`/`save_daily_metric` already do.
Deliverable: Four guarded commits, regression tests (failed transaction rolls back, successful transaction keeps, standalone call still commits), full canonical gates, independent review, one PR.
Stop condition: Any failed gate or blocking review stops commit/push/merge.
Closure rule: #1412 closes only after owner-approved merge and green main.
Canonical doc update: this brief, CLAUDE.md test snapshot, docs/governance/ledger.jsonl. Detail and status live in issue #1412 and its PR, not here.
Authorizes: Owner instruction in the project thread, 2026-11-05 ('Ξεκίνα από το πρώτο πραγματικά επιλέξιμο issue του υφιστάμενου πλάνου'; plan v2 #1434 order 1 = #1412), within category Α of the standing instructions. Merge: standing owner authorization, project thread 2026-11-05 21:56 UTC, for all current and future PRs ('Σου παρέχω τη ρητή και πάγια εξουσιοδότησή μου να πραγματοποιείς αυτόνομα merge σε όλα τα υφιστάμενα και μελλοντικά Pull Requests'), only when all hold: (1) independent reviewer passed the final PR version with no unresolved or material notes; (2) all required CI checks green on the last commit; (3) no conflicts or branch-protection violations; (4) high-risk changes also passed the extra security checks of their category. Otherwise the agent fixes the cause and repeats the checks; it does not merge.
Allowed / Forbidden: `titan/core/repositories/training.py`, `tests/test_db_repositories.py` and the records above. No schema, threshold, golden, other writer or behavior change outside an open transaction.

---

## CI-01 / #1230 — enable and prove Gitleaks default rules (owner assignment, 2026-11-02)

**Status:** OPEN pending independently reviewed PR, successful merge and green main. **Tier:** 1 — security/data integrity. **Severity (source / effective):** HIGH / HIGH. Alias: SEC-01. No phase clearance.

Owner source: accepted plan places #1230 next after the prerequisite canonical-gate reconciliation delivered in PR #1453. Standing approval: “Εγκρίνω. Τα pr κάνε τα εσύ merge εάν βγαίνουν πράσινα και σύμφωνα με τους κανόνες που σου είχα δώσει”. Closure instruction: “Απλά, να κλείνεις και τα issues όταν περνάνε τα pr, με σχετική αναφορά του pr ή όπως αλλιώς νομίζεις καλύτερα”. Current assignment: “Προχώρα στα επόμενα, σύμφωνα με το σχέδιο και τις οδηγίες που σου έχουν δοθεί”. This records that bounded routine repair, not a new security policy or production-credential finding.

Pass type: implementation
Change Type: implementation (Bundled required task records)
Workflow Path: Path A
Execution unit: CI-01 / #1230 only: the existing required Gitleaks scanner must load its bundled default detection rules while retaining existing narrow fixture exceptions.
Deliverable: Configuration repair, an executable synthetic clean/positive scanner control in the existing required CI job, paired fail-closed regression tests, independent initial and fix review, captured full gates and one PR.
Stop condition: Any failed acceptance, full gate, blocking review, required check or triggered relevant conditional check blocks commit/push/merge; any suspected real credential is redacted and escalated, never allowlisted to obtain green. Completion requires reviewed green PR, merge pinned to its reviewed head, and verified green resulting main.
Closure rule: #1230 becomes closure-capable only when every criterion is evidenced after merge and green main; link the PR and evidence on closure. #1165, #1237, #1438 and all other parents/issues stay OPEN; no project/phase clearance.
Canonical doc update: TECHNICAL_DEBT.md task handoff; CLAUDE.md actual test-count snapshot; PROGRESS.md scoped result; docs/governance/ledger.jsonl actual orchestration events. Bundled because these records are required to make this owner-approved one-task/one-PR delivery reviewable; no unrelated records closure.
Authorizes: The Owner's accepted #1230 Category-A repair plan and standing merge/issue-closure authorization quoted above, renewed by the current proceed-next assignment. v7.9 §13 scope: only secret-scanner configuration and its synthetic failure-path proof; no auth/runtime error-path change, schema, scientific rule, clearance or branch-policy change.
Allowed / Forbidden: Only files listed below. Preserve all current narrow allowlist patterns and existing PR/push range selection, scanner version and required check identity. No broad exclusions, scanner bypass, credentials, real messages, production restore, Docker smoke, application modules, ADR/AGENTS/Contract amendments, ruleset changes, force push or admin merge.
Expected response format: AGENTS §23 delivery with actual file sizes, full gate results, independent review, PR/main evidence and explicit limitations.

**Allowed files and reasons:**
- `.gitleaks.toml`: extend the pinned scanner's default rules without broadening exceptions.
- `scripts/check_gitleaks.sh` (new): prove the actual configured scanner accepts a clean fixture and detects a constructed, non-real synthetic token; reject operational errors or missing/wrong report evidence.
- `.github/workflows/secret-scan.yml`: run that control after installing the existing pinned binary and before the unchanged real commit-range scan.
- `tests/test_gitleaks_control.py` (new): exercise control success and fail-closed boundary/error cases with a recording CLI double; prove the CI control is wired before the real scan. Actual binary proof is separately mandatory.
- `tests/test_secret_scan_workflow_at04.py`: preserve range tests and verify nonzero scanner exits block the actual scan step.
- The four task-specific record files named under Canonical doc update, for the stated reasons only.

**Binary acceptance:** (1) actual Gitleaks 8.18.4 detects a synthetic GitHub PAT under repo config and accepts clean content; original config demonstrably misses the same positive; (2) clean exit alone cannot satisfy the positive control, and operational errors, invalid/missing/empty/wrong-rule reports fail the control; (3) required gitleaks CI job runs the control before its existing redacted PR/push/history scan, which preserves failures; (4) existing narrow exceptions and pinned version remain; (5) tests cover both success and boundary/error paths, no skip/suppression or new runtime module; (6) all three full canonical gates, independent reviews and every required/triggered check pass before merge; resulting main is verified green before issue closure.

**Ordered edits:** fix config first, then add control and regression tests, then wire CI and add scan-failure propagation cases; tests target repaired behavior. The intentionally failing “before” proof runs only in an owned temporary fixture outside the checkout. No commits between edits; every commit is guarded by full canonical gates and the installed hook.

**READY:** complete §23 handoff above plus DoR §17.5: scope clear; all files identified; criteria binary; tests known. DoR: PASS. Independent initial diagnosis and clean-state full baseline must both be recorded before any implementation.

---


## CI-08 / #1237 — canonical local gates (owner authorization, 2026-11-02)

**Status:** OPEN. **Tier:** 2 — **independent**, approved as the first infrastructure task by the Owner. **Change Type:** implementation. **Workflow Path:** A.

The Owner approved the first independent #1237 reconciliation and its canonical §23 recording, with VERIFY `bash scripts/titan_ci.sh`, the three HARD GATE commands, the actual eleven required checks plus relevant conditional checks, and serial PR/merge. Approval: “Εγκρίνω. Τα pr κάνε τα εσύ merge εάν βγαίνουν πράσινα και σύμφωνα με τους κανόνες που σου είχα δώσει”. This records the Owner's decision; it does not declare a phase closed or create a new clinical/runtime policy.

Pass type: implementation
Change Type: implementation
Workflow Path: Path A
Execution unit: First independent CI-08 task: reconcile canonical local gates with AGENTS HARD GATE; no runtime behavior change.
Deliverable: Exact Ruff→strict-full→full runner, thin exec wrapper, machine environment fingerprint, focused regression tests, captured full verification, independent fix review and one PR.
Stop condition: Any failed acceptance/gate or blocking review stops commit/push/merge; success is reviewed patch with green PR and verified green main.
Closure rule: Parent task stays OPEN; no phase or issue clearance.
Canonical doc update: TECHNICAL_DEBT.md canonical brief/owner authorization; ADR-0071 owner-approved 11-context addendum; CLAUDE.md test-count snapshot; PROGRESS.md affected progress; docs/governance/ledger.jsonl actual orchestration events. These required records are Bundled with implementation because the owner explicitly approved canonical recording and the 11-context reconciliation as part of the first unit; no unrelated closure.
Authorizes: Owner approval in this conversation ('Εγκρίνω. Τα pr κάνε τα εσύ merge εάν βγαίνουν πράσινα και σύμφωνα με τους κανόνες που σου είχα δώσει') of the preceding three-point proposal: first independent #1237, record in canonical card/§23, VERIFY bash scripts/titan_ci.sh and the three AGENTS gates, use actual 11 required plus relevant conditional checks and record the 13-name difference. This handoff transcribes that accepted scope; it does not accept a new ADR or change AGENTS/Contract.
Allowed / Forbidden: Only listed files below. No app modules, schema, scientific thresholds, goldens, branch rules, credentials, live provider sends, force push or bypass.
Expected response format: AGENTS§23 delivery report with actual files/gate output/review/PR/main evidence, blockers and no invented clearance.


**Allowed files:** `scripts/titan_ci.sh`, `scripts/titan_check.sh`, `scripts/env_fingerprint.sh`, `tests/test_canonical_ci_contract.py`, `tests/test_env_fingerprint.py`, and the task-specific records named in Canonical doc update above. The fingerprint helper is required integration for AGENTS §2.4; no application package/module is added.

**Binary acceptance:** exact Ruff → strict full (`-W error::pytest.PytestWarning`) → full commands, no ignores; stop on first failure and preserve that exit; checker is an argv/status-preserving exec wrapper; actual stdlib environment fingerprint; paired success/failure regression tests; full verification and independent fix review; required and relevant triggered conditional checks green before authorized merge. No branch-rule changes or bypass.

**Bundled required records:** this brief/authorization, the Owner-approved ADR-0071 context-name addendum, actual test snapshot/progress and orchestration ledger. Bundled because the Owner expressly approved canonical recording and the context-name reconciliation in this first unit. **Closure:** parent stays OPEN; this pass does not authorize canonical closure.

---

## Triage Philosophy

> The same priority framework that governs training governs code: **safety of data
> integrity first, then observability, then everything else.** A silent failure that
> corrupts coaching decisions is more dangerous than a missing feature.

Items are organised into 5 tiers. Work within a tier must be completed before starting
on the next, except where explicitly marked as independent.

**PARTIAL → child item policy (mandatory):** When an item is partially resolved, a child
item must be created immediately to track the remaining scope. The parent item is marked
`PARTIALLY RESOLVED` with explicit scope boundaries. The child item is numbered sequentially
(e.g., T3-06 partial → T3-08 child). This prevents "mostly done" ambiguity and keeps the
register binary per Rule E5. See T3-06/T3-08 and T2-09/T2-11 as canonical examples.

Phase 9 OPEN — all G1–G12 cleared 2026-04-20. See AGENTS.md §16.2 and ADR-0022 for gate record.
Phase 16 CLOSED — phase_close_audit.sh 16 exit 0; 2774 tests passing; SCRATCHPAD IDLE (2026-05-15).
Phase 17 CLOSED — phase_close_audit.sh 17 exit 0; 2887 tests passing; TD-CTL-01 and TD-NUTRITION-01 registered (2026-05-22).
Phase 18 CLOSED — phase_close_audit.sh 18 exit 0; 2924 tests passing; TD-11 RESOLVED; TD-08 DEFERRED Phase 19 (2026-05-23).
Phase 19 CLOSED — phase_close_audit.sh 19 exit 0; 2942 tests passing; TD-NEW-15 RESOLVED; TD-04 RESOLVED; TD-08 DEFERRED Phase 20; TD-NEW-18 DEFERRED Phase 20 (2026-05-24).
Phase 20 CLOSED — phase_close_audit.sh 20 exit 0; 2955 tests passing; FMEA G12 SATISFIED; TD-08 DEFERRED Phase 21; TD-NEW-18 DEFERRED Phase 21 (2026-05-24).
Phase 21 CLOSED — phase_close_audit.sh 21 exit 0; 2959 tests passing; governance consolidation complete; TECHNICAL_DEBT.md archived to <1500 LOC; SCRATCHPAD.md archived; TD-08 DEFERRED Phase 22; TD-NEW-18 DEFERRED Phase 22; TD-04B DEFERRED Phase 22; T5-15 DEFERRED Phase 22 (2026-05-24).
Phase 22 CLOSED — phase_close_audit.sh 22 exit 0; 2975 tests passing; FMEA G12 SATISFIED; TD-08 DEFERRED Phase 23; TD-04B DEFERRED Phase 23; T5-15 Phase B DEFERRED Phase 23; P15-ARCH5 DEFERRED Phase 23; TD-CI-SELFHOSTED DEFERRED Phase 23 (2026-05-25).
Phase 23 CLOSED — phase_close_audit.sh 23 exit 0; 2974 tests passing; ADR-0058 construction-site violation caught and fixed; TD-08 DEFERRED Phase 24; TD-04B DEFERRED Phase 24; T5-15 Phase B DEFERRED Phase 24; P15-ARCH5 DEFERRED Phase 24; TD-CI-SELFHOSTED DEFERRED Phase 24 (2026-05-29).
Phase 24 CLOSED — phase_close_audit.sh 24 exit 0; 3021 tests passing; FMEA G12 SATISFIED; TD-08 RESOLVED (Opus-verified); TD-04B RESOLVED (TitanEffectBus live, ADR-0058 Phase B complete); TD-CI-SELFHOSTED RESOLVED; T5-15B DEFERRED Phase 25; P15-ARCH5 DEFERRED Phase 25 (2026-06-03).
Phase 25 CLOSED — phase_close_audit.sh 25 exit 0; 3022 tests passing; FMEA G12 SATISFIED; T5-15B RESOLVED; P15-ARCH5 RESOLVED; ADR-0059 RESOLVED; B2c fallback removed (2026-06-06).
Phase 26 CLOSED — phase_close_audit.sh 26 exit 0; 3025 tests passing, 6 skipped (3031 collected); FMEA G12 SATISFIED; P26-02/03/04/05/06/07 RESOLVED; P26-01 DEFERRED Phase 9; P26-08 DEFERRED pending ADR (2026-06-07).
Phase 27 OPEN — Cohort analytics + CohortProfile (population-level calibration signal) 2026-06-07; P27-01 RESOLVED 2026-06-09 (cohort_calibration_signals schema); P27-04 RESOLVED 2026-06-09 (PR #860) — completion-rate calibration rollback gate, advisory default, v1.

---

## Project Mayhem, Φάση 0 — ευρήματα κατηγορίας B (καταγραφή 2026-10-23)

Ο έλεγχος της Φάσης 0 (Project Mayhem, 2026-10-23) βρήκε ευρήματα που δεν διορθώνονται στη Φάση 1.
Καταγράφονται εδώ ως Tier 1 (ακεραιότητα δεδομένων, ασφάλεια, απομόνωση) ή Tier 2 (παρατηρησιμότητα,
διακυβέρνηση), με στόχο τη Phase 27. Τα αναλυτικά στοιχεία είναι στην αναφορά της Φάσης 0. Τα ευρήματα
σε μονοπάτια ασφάλειας ή απόφασης ανέβηκαν σε B λόγω του severity floor (CONTRACT 7.9 §10, έλεγχος
DOC-03). Καμία διόρθωση σε αυτή τη λίστα δεν γίνεται χωρίς έγκριση του owner ανά εύρημα (Φάση 2 του
σχεδίου). Ο έλεγχος είναι AI, όχι ανθρώπινη πιστοποίηση.

| # | Tier | Εύρημα | Στοιχεία | Κατάσταση |
|---|------|--------|----------|-----------|
| M0-07 | 2 | Τα έγγραφα διακυβέρνησης διαφωνούν: τέσσερις αριθμήσεις «Φάση», το SA:C-1 μένει ανοιχτό μέχρι να κλείσουν τα M0-05 και M0-26, και το μητρώο AGENTS §30 είναι παλιό. Όσο ισχύει αυτό, δεν δίνεται clearance | `AGENTS.md` §30, `docs/ROADMAP.MD`, `PROGRESS.md`, `CLAUDE.md` | OPEN · στόχος Phase 27 |
| M0-08 | 1 | Αν το Telegram αργήσει να απαντήσει ενώ το μήνυμα έφτασε, ξαναστέλνεται ολόκληρο το briefing | `telegram_bot.py` (send με timeout), `daily_coach.py` send handler | OPEN · στόχος Phase 27 · έλεγχος RC (D-185): επιβεβαιώθηκε με εκτέλεση· ξαναστέλνεται η σύντομη αποθηκευμένη απόφαση με σημείωση επανάληψης, όχι όλο το briefing |
| M0-09 | 2 | Οι αθλητές τρέχουν ένας ένας. Όσοι δεν ξεκινήσουν ως τις 12:00 UTC χάνουν τη μέρα χωρίς ειδοποίηση στον owner | `worker/__init__.py` (`ROUTINE_LAST_START_HOUR_UTC`, round) | OPEN · στόχος Phase 27 |
| M0-10 | 2 | Το εβδομαδιαίο πλάνο στέλνεται το πολύ μία φορά, και μια αποτυχημένη αποστολή δεν αναφέρεται | `worker/__init__.py` (`_prepare_weekly_plan`) | OPEN · στόχος Phase 27 |
| M0-11 | 1 | Η βάση RHR και το ιστορικό φορτίου μετράνε από το ρολόι, όχι από τη μέρα του πρωινού. Σε επανάληψη μετά τα μεσάνυχτα η H3 μπορεί να χάσει άνοδο RHR | `repositories/physiology.py`, `repositories/training.py` | RESOLVED · PR #1096 (D-154)· το ιστορικό φορτίου ήταν ήδη σωστό (D-131) |
| M0-14 | 1 | Το `/metrics` του API δεν ζητά πιστοποίηση και η θύρα 8000 ακούει σε όλο το δίκτυο | `api/main.py` (`/metrics`), `docker-compose.yml` (ports) | RESOLVED · PR #1125 (D-182)· 404 χωρίς `TITAN_METRICS_TOKEN`, 401 χωρίς σωστό Bearer· θύρα `127.0.0.1:8000` |
| M0-15 | 2 | 6 tests παραλείπονται μόνιμα | `tests/test_t5_50_session_type_map.py` | RESOLVED · PR #1126 (D-183)· τα 6 tests καλούν το `garmin_persistence._save_activities`, χωρίς skip· ένα test αποτυγχάνει αν ξαναμπεί skip στο αρχείο |
| M0-16 | 2 | Η σχεδίαση (ένας αθλητής τη φορά, ένα SQLite, 07:00–12:00 UTC) δεν φτάνει για πολλούς αθλητές. Για πιλότο λίγων αθλητών δεν είναι θέμα | `worker/__init__.py` (round) | OPEN · στόχος Phase 27 |
| M0-17 | 1 | Το φίλτρο που κρύβει στοιχεία από τα logs δεν τρέχει στο API και δεν καλύπτει όλες τις μορφές log (MA-F7 μερικώς) | `utils/secrets.py`, `scripts/run_api.py`, `telegram_bot.py` | RESOLVED · PR #1139 (D-196): handler με φίλτρο στο API· μορφές JSON/repr στο `register_secret` |
| M0-20 | 1 | Η κόπωση της πρώτης μέρας μετρά ως μετρημένη | `daily_coach.py` (fatigue) | OPEN · στόχος Phase 27 |
| M0-21 | 1 | Το rationale λέει CLEAR όταν η βάση HRV είναι άκυρη ή το TSB είναι NaN | `governance_engine.py` (rationale) | OPEN · στόχος Phase 27 |
| M0-22 | 1 | Αποτυχία ανανέωσης φορτίου καταπίνεται σιωπηλά | `daily_coach.py` (load refresh) | RESOLVED · PR #1107 (D-166, ADR-0073) |
| M0-23 | 1 | Η ετοιμότητα παίρνει RHR 50 ως προεπιλογή όταν λείπει | `daily_coach.py` (readiness) | OPEN · στόχος Phase 27 |
| M0-25 | 1 | Το `get_recent_hrv_mean` καλείται χωρίς `athlete_id`. Ο έλεγχος ρητού id καλύπτει μόνο worker και orchestration | `repositories/physiology.py` | RESOLVED · PR #1118 (D-175)· το `athlete_id` είναι υποχρεωτικό, χωρίς προεπιλογή owner |
| M0-33 | 1 | Το bot δέχεται εντολές owner από ομαδική συνομιλία όταν το `TELEGRAM_CHAT_ID` είναι ομάδα | `telegram_bot.py` (`_trusted_chat_id`) | RESOLVED · PR #1092 (D-150)· ο owner διάλεξε «ομάδα + έλεγχος αποστολέα» |
| M0-12 | 1 | Οι αποφάσεις αθλητή διαβάζονταν ως του owner | `outcome_tracker.py`, `repositories/governance.py` | RESOLVED · PR #1088 (D-147) |
| M0-13 | 1 | Ο λογαριασμός Garmin του owner μπορούσε να δεθεί σε αθλητή | `garmin_sync.py` (`relogin_athlete`) | RESOLVED · PR #1087 (D-146) |
| M0-26 | 1 | Το `POST /coach/notes` έλεγχε μόνο ρόλο | `api/main.py` | RESOLVED · PR #1086 (μαζί με M0-05, D-145) |

**Υπόλοιπα από τις διορθώσεις της Φάσης 1** (από τους ανεξάρτητους ελέγχους των PR):

| # | Tier | Υπόλοιπο | Κατάσταση |
|---|------|----------|-----------|
| M0-13-R1 | 1 | Έλεγχος μετά το login με το `displayName` του owner, που σήμερα δεν αποθηκεύεται. Καλύπτει την περίπτωση που ο owner αλλάξει το Garmin e-mail του και το `.env` κρατήσει το παλιό (D-146) | RESOLVED · PR #1124 (D-181)· σχήμα v35 `owner_garmin_identity`· η σύνδεση του owner που διαβάζει προφίλ γράφει το όνομα· relogin και `bind_garmin_account` αρνούνται το όνομα του owner και όσο είναι άγνωστο· αθλητής ήδη δεμένος → `expired` (ADR-0076)· υπόλοιπο: M0-13-R2 |
| M0-13-R2 | 1 | Η ταυτότητα του owner είναι το `displayName`, που αλλάζει. Αν ο owner αλλάξει username, ως την επόμενη σύνδεσή του που διαβάζει προφίλ η βάση κρατά το παλιό όνομα, και ένα relogin αθλητή με τον λογαριασμό του owner δεν πιάνεται από αυτόν τον έλεγχο (μένει ο έλεγχος e-mail του D-146). Λύση: σταθερό `profileId` σε `owner_garmin_identity`, `athlete_accounts`, relogin, `bind_garmin_account`, `_token_account_matches`. Ήδη γραμμένο στο ADR-0076 «Τι δεν ξέρουμε» (ανεξάρτητος έλεγχος του #1124, 2026-10-31) | RESOLVED 2026-11-06 · HIGH · Β: ADR-0083 Accepted (D-223, PR #1499)· υλοποίηση PR #1500 (squash `0ea806b`), main πράσινο, #1268 κλειστό |
| M0-12-R1 | 2 | Η διαδρομή PostgreSQL (`persistence.py` adapter, `database.py`) δεν επιστρέφει `athlete_profile_id` στις αποφάσεις governance. Δεν είναι σε χρήση (ADR-0044). Μαζί με το M0-27 | OPEN · πριν ενεργοποιηθεί το PostgreSQL |
| M0-01-R1 | 1 | Ο έλεγχος fencing και η αποστολή δεν είναι ατομικά: μένει παράθυρο κλασμάτων δευτερολέπτου (D-148, PR #1089) | OPEN · στόχος Phase 27 |

**Καταγραφή 2026-10-24 (D-156):** ευρήματα της προηγούμενης Φάσης 0 και του παλιού σχεδίου που ήταν
ανοιχτά χωρίς εγγραφή εδώ. Η σοβαρότητα είναι του μητρώου `docs/audits/FINDINGS.md`· οι έλεγχοι SD,
IS, RC, SP, AT τα επιβεβαιώνουν. Η κατηγορία (Α/Β/Γ) είναι του μητρώου. Το tier και ο στόχος είναι
πρόταση του Claude και τα αποφασίζει ο owner στη Φάση 2 του σχεδίου· ως τότε κανένα από αυτά δεν
μετρά ως TRACKED.

| # | Tier | Σοβαρότητα | Εύρημα | Στοιχεία | Κατάσταση |
|---|------|------------|--------|----------|-----------|
| M0-19 | 1 | HIGH | Η σύγκριση 24 ωρών του P4-01 είναι αυστηρή | `daily_coach.py:266–267` (`_DEGRADED_ALERT_THRESHOLD_HOURS`) | OPEN · στόχος Phase 27 · έλεγχος SD |
| M0-24 | 2 | LOW | Το `/week` στέλνει πλάνο που δεν αποθηκεύτηκε | `titan/main.py:217-232` (`/week`) | OPEN · στόχος Phase 27 · έλεγχος RC: επιβεβαιώθηκε με εκτέλεση (D-185) |
| M0-27 | 1 | HIGH | Το PostgreSQL χωρίς φίλτρο αθλητή και χωρίς σκανδάλες H1–H5. Δεν είναι σε χρήση (ADR-0044). Μαζί με το M0-12-R1 | `persistence.py` (PostgreSQL adapter) | OPEN · πριν ενεργοποιηθεί το PostgreSQL · έλεγχος IS |
| M0-28 | 2 | LOW | Το test ιδιωτικότητας των logs δεν ελέγχει τα πεδία των events | tests ιδιωτικότητας logs | RESOLVED · PR #1141 (D-198) |
| M0-29 | 1 | HIGH | Το API παίρνει τους κωδικούς Garmin και Telegram από το κοινό `.env`· ο έλεγχος SP βρήκε ότι παίρνει και το `TITAN_GARTH_TOKEN_KEY` και τον τόμο με το `.garth_token` του owner (D-192) | `docker-compose.yml`, `api/` | RESOLVED · PR #1138 (D-195): το API δεν έχει `env_file`· το `.garth_token` στο `titan-data` μένει επόμενο βήμα |
| M0-30 | 2 | LOW | Παλιό `--ignore-vuln` στο `ci.yml` | `.github/workflows/ci.yml` | RESOLVED · PR #1140 (D-197) |
| M0-31 | 2 | LOW | Κενά στο CI: φίλτρο docker-smoke, gitleaks μόνο στο τελευταίο commit, release χωρίς tests, coverage μόνο στο `titan.science` | `.github/workflows/` | OPEN · στόχος Phase 27 · επανελέγχθηκε στον AT (D-202): στέκει· το μέρος του gitleaks είναι το AT-04 (HIGH) |
| M0-32 | 2 | LOW | Παλιό HD-04· ο έλεγχος του CLAUDE.md ανέχεται ±50 tests | tests του CLAUDE.md | OPEN · στόχος Phase 27 · έλεγχος AT |
| F-06 | 1 | HIGH | Η `/injury` υπάρχει μόνο για τον owner· οι αθλητές δεν έχουν πηγή για την H1 (ADR-0067 D10.3) | `telegram_bot.py` (`/injury`) | OPEN · στόχος Phase 27 · έλεγχος SD |
| F-07 | 2 | LOW | Οι αθλητές διαβάζουν «let Zaf know» αντί για εντολή που έχουν | `worker/__init__.py` (`_CRASH_REMINDER_ATHLETE`) | OPEN · στόχος Phase 27 · έλεγχος SD |
| S0-01 | 2 | HIGH | Στο `ae30e4a` το `titan_ci.sh` δεν τελείωσε σε καμία από 3 εκτελέσεις, με ίδιες αποτυχίες· στο `4bcc3ee` πέρασε 11/11. Αιτία άγνωστη (υπόθεση: διαρροή ρολογιού του freezegun ανάμεσα σε tests) | `docs/audits/2026-10-24-phase0-plan.md` §2.1, `docs/audits/ci-step0/` | OPEN · στόχος Phase 27 · έλεγχος AT |

**Καταγραφή 2026-10-24, έλεγχος SD (D-159):** νέα ευρήματα του ελέγχου SD στο `28608d0`
([`docs/audits/2026-10-24-sd.md`](docs/audits/2026-10-24-sd.md)). Το tier και ο στόχος είναι πρόταση του
Claude και τα αποφασίζει ο owner· ως τότε κανένα δεν μετρά ως TRACKED.

| # | Tier | Σοβαρότητα | Εύρημα | Στοιχεία | Κατάσταση |
|------|------|------------|--------|----------|-----------|
| SD-01 | 1 | HIGH | HRV > 300 ms φτάνει στην H2 χωρίς έλεγχο ορίων → TEMPO, H2 CLEAR (επείγον) | `daily_coach.py:1119`, `:1579-1590` | RESOLVED · PR #1106 (D-165, ADR-0073) |
| SD-02 | 1 | HIGH | Τιμή εκτός ορίων κόβεται στο όριο και μετρά ως μετρημένη (RHR < 25 → 25, H3 CLEAR· επείγον) | `physiological_bounds.py:90-96` | RESOLVED για το RHR · PR #1104 (D-163, ADR-0073)· η κόπωση −3 δεν φτάνεται από το `/manual_entry` |
| SD-03 | 1 | HIGH | Η baseline RHR δέχεται μία μόνο προηγούμενη νύχτα (επείγον) | `physiology.py:262-279` | RESOLVED · PR #1105 (D-164, ADR-0073) |
| SD-04 | 1 | HIGH | Χαμένη λήψη δραστηριοτήτων: ο sync μετρά επιτυχία, η H4 CLEAR για ένα πρωινό (επείγον) | `garmin_sync.py:1054-1061`, `:1397-1404`, `data_trust.py:56-66` | RESOLVED · PR #1108 (D-167, ADR-0073) |
| SD-05 | 2 | HIGH | Σε timeout του Garmin η H4 λέει CLEAR από φορτία που δεν συγχρονίστηκαν | `governance_engine.py:1239-1247` | RESOLVED · PR #1160 (D-218, ADR-0080) |
| SD-06 | 2 | HIGH | Το μήνυμα κρύβει τις πύλες που δεν μετρήθηκαν όταν πιάσει lock· ωμοί κωδικοί lock | `governance_engine.py:1299-1303`, `:1142` | RESOLVED · PR #1164 (D-222, ADR-0081) |
| SD-07 | 2 | HIGH | Ετοιμότητα 100/100 χωρίς HRV και RHR (ADR-0051: 40) | `readiness_engine.py:35-61`, `daily_coach.py:1491-1497` | OPEN · στόχος Phase 27 · έλεγχος SD |
| SD-08 | 2 | HIGH | Η `/recovery` με σταθερές εισόδους και HRV οποιασδήποτε ηλικίας | `titan/main.py:252-268` | RESOLVED · PR #1103 (D-161) |
| SD-09 | 2 | HIGH | Αθλητής που δεν συγχρονίστηκε ποτέ δεν σημειώνεται ποτέ παλιός | `daily_coach.py:1070-1090` | RESOLVED · PR #1109 (D-168) |
| SD-10 | 2 | HIGH | Glycogen debt από πεδία που ο sync δεν επιστρέφει | `daily_coach.py:1183-1196` | OPEN · στόχος Phase 27 · έλεγχος SD |
| SD-11 | 2 | HIGH | Το max HR του owner δεν ελέγχεται για όρια | `athlete.py:509` | OPEN · στόχος Phase 27 · έλεγχος SD |
| SD-12 | 2 | HIGH | Η πύλη fueling δεν ικανοποιείται ποτέ (κλείνει πάντα) | `daily_coach.py:1690` | OPEN · στόχος Phase 27 · έλεγχος SD |
| SD-13 | 3 | LOW | TSB 0 και HRV οποιασδήποτε ηλικίας στο payload του coaching | `daily_coach.py:1901`, `:1913` | RESOLVED · PR #1114 (D-171) |
| SD-14 | 2 | HIGH | HRV πάνω από 300 ms μπαίνει ακατέργαστη στο log HRV (αυριανή baseline, απόκλιση, AFI) | `daily_coach.py` βήμα 3 | RESOLVED · PR #1113 (D-170, ADR-0074 επιλογή Α) |
| SD-14-R1 | 2 | HIGH | Ο adapter PostgreSQL `get_hrv_history` δεν ελέγχει όρια HRV (ούτε πάνω από 300 ούτε 0)· δεν χρησιμοποιείται (ADR-0044) | `titan/core/persistence.py` | OPEN · στόχος Phase 27, πριν ενεργοποιηθεί το PostgreSQL · από το #1113 (D-170) |
| SD-15 | 2 | HIGH | Κακοσχηματισμένες προπονήσεις παραλείπονται χωρίς σημάδι· τα φορτία της H4 μένουν ελλιπή | `garmin_sync.py:1132-1143` | OPEN · στόχος Phase 27 · έλεγχος Opus του ADR-0080 |
| SD-16 | 2 | HIGH | Το outcome κρατά το TSB που δεν ελέγχθηκε στα πρωινά M0-22, SD-04, SD-05 | `daily_coach.py` | OPEN · στόχος Phase 27 · έλεγχος Opus του #1160 |
| SD-17 | 2 | HIGH | Το rationale δείχνει CLEAR για H2–H5 με NaN, baseline ≤ 0 ή μη αριθμό, ενώ μπαίνει `DATA_MISSING_CONSERVATIVE_Hn` | `governance_engine.py` | OPEN · στόχος Phase 27 · έλεγχος Opus του ADR-0081 (D-221) |
| XA-T01…T12, XA-N01…N14 | 2 | HIGH (20) · MEDIUM (6) | Έλεγχος του owner για προπονήσεις και διατροφή: 26 ευρήματα, όλα επιβεβαιωμένα· ένα στοιχείο ανά εύρημα στο FINDINGS §13 | `weekly_planner.py`, `governance_engine.py`, `volume_load_gauge.py`, `nutrition_optimizer.py`, `daily_coach.py` | OPEN · στόχος Phase 27 · ιεράρχηση μετά τη Φάση 2 (D-219) |
| XB-01…XB-23 | 2 | HIGH (16) · MEDIUM (6) · LOW (1) | Επέκταση του ελέγχου του owner: 23 ευρήματα (τρία ήδη γνωστά: P4-11, T-PRA-18, P4-10)· ένα στοιχείο ανά εύρημα στο FINDINGS §14 | `weekly_planner.py`, `coaching_pipeline.py`, `threshold_adapter.py`, `outcome_tracker.py`, `daily_coach.py`, `telegram_bot.py`, `main.py` | OPEN · στόχος Phase 27 · ιεράρχηση μετά τη Φάση 2 (D-220) |
| XC-01…XC-08 | 2 | HIGH (6) · MEDIUM (2) | Μία αθλήτρια, 56 ημέρες: 8 ευρήματα (τρία ήδη γνωστά, δύο επέκταση γνωστών)· FINDINGS §15 | `daily_coach.py`, `readiness_engine.py`, `governance_engine.py`, `weekly_planner.py` | OPEN · στόχος Phase 27 · ιεράρχηση μετά τη Φάση 2 (D-220) |
| IS-01 | 2 | HIGH | Άγνωστο `athlete_id` γίνεται δεκτό σε εγγραφές· FK προς `athletes` μόνο σε 2 πίνακες | `database.py:169-197` | OPEN · Β, θέλει ADR · στόχος Phase 27 · έλεγχος IS (D-173) |
| IS-02 | 2 | HIGH | Απόν `athlete_id` γίνεται owner σε 45 συναρτήσεις· το sweep καλύπτει μόνο `worker/` και `orchestration/` | `tests/test_explicit_athlete_ids.py:15` | OPEN · Β για τις προεπιλογές, Α για την επέκταση του sweep · στόχος Phase 27 · έλεγχος IS (D-173) |
| IS-03 | 1 | HIGH | Ροή override Telegram: fallback `"unknown_athlete"`, nonce χωρίς έλεγχο έναντι της εκκρεμούς απόφασης· χωρίς καλούντα | `telegram_bot.py:853-955` | RESOLVED · PR #1121 (D-178)· χωρίς αθλητή ή απόφαση δεν γράφεται τίποτα· το nonce πρέπει να ανήκει στην εκκρεμή απόφαση |
| IS-04 | 3 | LOW | Ίδιο `garmin_activity_id` δεύτερου αθλητή χάνεται σιωπηλά | `training.py:337-380` | OPEN · στόχος Phase 27 · έλεγχος IS (D-173) |
| IS-05 | 1 | HIGH | Το PostgreSQL ενεργοποιείται με `TITAN_DB_BACKEND=postgres`· κλείνει μόνο με κανόνα (ADR-0044) | `persistence.py` `get_persistence_adapter` | RESOLVED · PR #1117 (D-174)· το `get_persistence_adapter` αρνείται το `postgres` όπως το `get_database_manager` |
| IS-06 | 1 | HIGH | Το `relogin_athlete` αφήνει τη βιβλιοθήκη να γράψει token στο `GARMINTOKENS` πριν από τις αρνήσεις | `garmin_sync.py:324-325` | RESOLVED · PR #1122 (D-179)· με `GARMINTOKENS` στο περιβάλλον το `relogin_athlete` σταματά πριν από το `Garmin(...)`, άρα η βιβλιοθήκη δεν διαβάζει ούτε γράφει token εκεί |
| IS-07 | 1 | HIGH | Το `relogin_athlete` δένει το `client.display_name` (μπορεί να είναι το e-mail του login) αντί για το `displayName` του `socialProfile` | `garmin_sync.py:326` | RESOLVED · PR #1123 (D-180)· το `relogin_athlete` διαβάζει το `socialProfile` μετά το login και δένει το `displayName` του (strip)· χωρίς τιμή αρνείται πριν από το δέσιμο και το token |
| — | — | — | **Καταγραφή 2026-10-31, έλεγχος RC (D-185):** το tier και ο στόχος είναι πρόταση του Claude και τα αποφασίζει ο owner· ως τότε κανένα δεν μετρά ως TRACKED | — | — |
| RC-01 | 1 | MEDIUM | Backup που σκοτώνεται στη μέση αφήνει άδειο `titan_<σήμερα>.db`· η ίδια μέρα δεν ξαναπαίρνει backup, χωρίς log, και η διατήρηση το κρατά | `operations.py:562`, `:616-642` | RESOLVED · PR #1129 (D-186)· το backup γράφεται ως `.partial` και μετονομάζεται μόνο μετά τον έλεγχο· επιβεβαιωμένο με test |
| RC-02 | 1 | MEDIUM | Η τοπική επαναφορά (Scenario B) δεν σβήνει το παλιό `-wal`· μετά από crash ξαναπαίζεται πάνω στο αντίγραφο | `docs/runbooks/database-recovery.md:111` | RESOLVED · PR #1130 (D-187)· το Scenario B κρατά τη βάση με τα `-wal`/`-shm` της και μετά τα σβήνει· επιβεβαιωμένο με test που τρέχει τις εντολές |
| RC-03 | 3 | LOW | Το `.before-restore` της επαναφοράς Docker κρατιέται χωρίς το `-wal` του | `docs/RUNBOOK_DR.md:72-74` | RESOLVED · PR #1131 (D-188)· το βήμα 3 κρατά το `-wal` ως `.before-restore-wal` και σβήνει το παλιό πριν από την αντιγραφή· επιβεβαιωμένο με test που τρέχει το script |
| RC-04 | 3 | LOW | Δεύτερη ζωντανή κονσόλα θεωρείται «διεργασία που επανεκκίνησε» και παίρνει την προσπάθεια 2· το fencing προστατεύει | `operations.py:21-33` | OPEN · Β · προτεραιότητες Φάσης 2 (πρόταση) · έλεγχος RC (D-185) |
| RC-05 | 2 | HIGH | Χωρίς `startTimeGMT` η μέρα της δραστηριότητας είναι η τοπική, όχι η UTC (κανόνας: είσοδος πυλών) | `garmin_sync.py:466-500` | OPEN · Β · Φάση 2, θέλει ADR (απόφαση Zaf, κάρτα 2026-10-31· D-191) · έλεγχος RC (D-185) |
| RC-06 | 2 | HIGH | Ημερομηνία χωρίς ώρα διαβάζεται ως 00:00 UTC και απορρίπτεται ως μελλοντική κοντά στα μεσάνυχτα UTC· ώρα χωρίς ζώνη διαβάζεται ως UTC (κανόνας: είσοδος πυλών) | `data_sanity.py:239-249`, `:342-350` | OPEN · Β · Φάση 2, θέλει ADR (απόφαση Zaf, κάρτα 2026-10-31· D-191) · έλεγχος RC (D-185) |
| RC-07 | 2 | HIGH | Κενό λειτουργίας πάνω από 14 μέρες δεν συμπληρώνεται ποτέ· τρύπα στο ιστορικό φορτίου (CTL/TSB/ACWR, H4)· η κατεύθυνση που μετρήθηκε είναι συντηρητική | `garmin_sync.py:1426`, `garmin_persistence.py:414` | RESOLVED · PR #1133 (D-190)· το backfill φέρνει τις μέρες από το τελευταίο επιτυχημένο sync· όρια στο D-190 |
| RC-08 | 3 | LOW | Το `multi-athlete.md` λέει ότι κονσόλα και worker στέλνουν δύο πρωινά· ο κώδικας κάνει claim και στις δύο πλευρές | `docs/runbooks/multi-athlete.md:114-116` | RESOLVED · PR #1132 (D-189)· η φράση διορθώθηκε, μένει η προειδοποίηση για το 409· επιβεβαιωμένο με test |
| — | — | — | **Καταγραφή 2026-10-31, έλεγχος SP (D-192):** το tier και ο στόχος είναι πρόταση του Claude και τα αποφασίζει ο owner· ως τότε κανένα δεν μετρά ως TRACKED | — | — |
| SP-01 | 1 | HIGH | Coach με id `system` βλέπει τον owner, από τη σπορά `('system','owner')` της μετανάστευσης· λανθάνον, κανένα endpoint δεν φτιάχνει χρήστη | `migrations.py:131-136`, `access.py:102-119` | RESOLVED για το Α · PR #1137 (D-194)· το upsert αρνείται το `system` και ο έλεγχος ανάθεσης αρνείται coach `system`· η αφαίρεση της σποράς μένει Β (προτεραιότητες Φάσης 2, πρόταση) |
| SP-02 | 1 | HIGH | Το `/auth/login` δίνει tokens σε απενεργοποιημένο λογαριασμό· τα tokens απορρίπτονται μετά | `auth.py:64-76`, `main.py:443-456` | RESOLVED · PR #1136 (D-193)· ο ανενεργός λογαριασμός παίρνει την απάντηση λάθος κωδικού, χωρίς tokens, και μετρά ως αποτυχία· επιβεβαιωμένο με test |
| SP-03 | 2 | HIGH | Το `/stop` απορρίπτεται όταν αποτυγχάνει μόνο το audit· ορίζεται από το INV-22 | `telegram_bot.py:800-848` | RESOLVED · PR #1158 (ADR-0079, D-215): η ανάκληση ισχύει πάντα, το audit που αποτυγχάνει πάει σε ουρά που δεν χάνεται· επιβεβαιωμένο με test που αποτύγχανε στο main · ADR #1157 (D-214) · μέρος Α (ειδοποίηση του owner) FIXED (#1144, D-201) · προτεραιότητες Φάσης 2 (πρόταση) · έλεγχος SP (D-192) |
| SP-04 | 2 | MEDIUM | Το redaction χάνει κωδικό σε μορφή `json.dumps`/`repr` (μέρος του M0-17) | `secrets.py:50-58` | RESOLVED · PR #1139 (D-196) |
| SP-05 | 3 | LOW | Chat id του owner στο event override-silence· το test δεν κοιτά πεδία events (μέρος του M0-28) | `telegram_bot.py:982-988` | RESOLVED · PR #1141 (D-198) |
| SP-06 | 3 | LOW | Το `.env` γράφεται πρώτα και μετά παίρνει 600 | `setup_wizard.py:249-250` | RESOLVED · PR #1142 (D-199) |
| SP-07 | 2 | HIGH | Άγνωστο username απορρίπτεται χωρίς bcrypt, πιο γρήγορα από λάθος κωδικό· πιθανό oracle χρονισμού (RBP-05)· από ανάγνωση κώδικα | `auth.py:66-67` | RESOLVED · PR #1143 (D-200) |
| — | — | — | **Καταγραφή 2026-10-31, έλεγχος AT (D-202):** το tier και ο στόχος είναι πρόταση του Claude και τα αποφασίζει ο owner· ως τότε κανένα δεν μετρά ως TRACKED | — | — |
| AT-01 | 2 | HIGH | 20 κλειδιά `garmin_data` που ο sync δεν βγάζει· η κόπωση δεν γίνεται ποτέ HIGH, η V4 δεν κόβει από κόπωση· τα fakes τα δίνουν (εν μέρει SD-10, D-058, D-088) | `daily_coach.py:1134, 1216, 1228-1231`, `fatigue_engine.py:9-29` | OPEN · Β, θέλει ADR (ADR-0009)· Α για test-συμβόλαιο · προτεραιότητες Φάσης 2 (πρόταση) · έλεγχος AT (D-202) |
| AT-02 | 2 | MEDIUM | Τα e2e τρέχουν με `StubGovernance` και σχήμα Garmin που ο sync δεν βγάζει | `tests/e2e/conftest.py:15-53` | RESOLVED · PR #1152 (D-209) σχήμα Garmin και παγωμένη ημέρα· PR #1153 (D-210) πραγματική governance, τα υπόλοιπα stubs λέγονται wiring smoke· επιβεβαιωμένο με test |
| AT-03 | 1 | HIGH | `/docs`, `/redoc`, `/openapi.json` χωρίς πιστοποίηση (κανόνας: authentication) | `titan/api/main.py:343` | RESOLVED · PR #1146 (D-203)· τα routes της τεκμηρίωσης είναι κλειστά και κάθε route έξω από την επιτρεπτή λίστα θέλει login· επιβεβαιωμένο με test· η λίστα του ADR-0048: PR #1155 (ADR-0077) |
| AT-04 | 1 | HIGH | Gitleaks στο push στο main μόνο `HEAD~1..HEAD`· HIGH στο AGENTS §30, LOW στο M0-31 | `secret-scan.yml:38-40` | RESOLVED · PR #1147 (D-204)· στο push ελέγχεται το εύρος από το προηγούμενο commit, αλλιώς όλο το ιστορικό· επιβεβαιωμένο με test που τρέχει το script |
| AT-05 | 3 | MEDIUM | Το pytest γράφει `titan.log`/`titan.log.1` στη ρίζα του repo | `titan/main.py:75-95` | RESOLVED · PR #1148 (D-205)· το log των tests πάει στον προσωρινό home, οι handlers καθαρίζουν μετά από κάθε test, το `.gitignore` πιάνει τα `*.log.N`· επιβεβαιωμένο με test |
| AT-06 | 3 | LOW | Δύο μετρήσεις modules και literal 90 στις πύλες ορίου | `test_complexity_budget.py:17-39` | RESOLVED · PR #1150 (D-207)· μία μέτρηση (`titan_modules()`, ίδια με το CI) και μία σταθερά σε όλες τις πύλες· επιβεβαιωμένο με test |
| AT-07 | 3 | LOW | Tests εξαρτώνται από τον φάκελο εκτέλεσης· 74 ελέγχοι string στον πηγαίο κώδικα | `test_opus_critical_fixes.py:10-53` | PARTIAL · PR #1154 (D-211) οι διαδρομές από το `REPO_ROOT`, με έλεγχο AST· μένουν οι 74 έλεγχοι string · έλεγχος AT (D-202) |
| AT-08 | 3 | LOW | Κανένα όριο χρόνου ανά test | `pyproject.toml` | RESOLVED · PR #1149 (D-206)· `timeout = 300` στο pytest· επιβεβαιωμένο με test |
| AT-09 | 3 | LOW | Διπλές `LOG_*`· το §16.6 «env-overridable» δεν ισχύει· νεκρό `should_replan` | `titan/main.py:65-66` | RESOLVED · το §16.6: PR #1155 (ADR-0077, D-212)· ο κώδικας: PR #1151 (D-208), ένας ορισμός `LOG_*`, το `should_replan` σημειωμένο ότι δεν καλείται· επιβεβαιωμένο με test |
| — | — | — | **Καταγραφή 2026-10-31, ADR-0078 (D-213):** τα ευρήματα AD του ελέγχου εγγράφων, που δεν είχαν γραμμή | — | — |
| AD-03 | 2 | HIGH | Τα ADR 0061–0066 και 0068 γράφουν «Proposed (accepted on merge)» | αρχεία ADR, ευρετήριο | OPEN · Β · ο owner τα επιβεβαιώνει ένα-ένα σε policy-only PR (ADR-0078 σημείο 5) · στόχος Phase 27 |
| AD-04 | 2 | MEDIUM | Το ADR-0057 είναι Accepted, αλλά η ενότητα Decision γράφει «PENDING — requires architect review» | `docs/adr/0057-*` | OPEN · Β · επιβεβαίωση από τον owner μαζί με το AD-03 · στόχος Phase 27 |
| AD-08 | 2 | HIGH | Ποιος είναι ο Architect (AGENTS §1, §1.2 έναντι ADR-0061, 0072–0077) | AGENTS §1, §1.2 | RESOLVED · PR #1156 (ADR-0078 Accepted 2026-10-31, D-213): ο owner είναι ο Architect, το Claude γράφει |

---

## TIER 1 — Data Integrity (All Resolved ✅)

All 23 Tier 1 items (T1-01 through T1-23) are **RESOLVED**.
Full history: [`archive/technical_debt_t1_t3_resolved.md`](archive/technical_debt_t1_t3_resolved.md)

| # | Item | Resolved |
|---|------|----------|
| T1-01 | Wrong Telegram library in requirements.txt | 2026-03-02 |
| T1-02 | HRV silent data loss in garmin_sync.py | 2026-03-02 |
| T1-03 | Migration observability gap in database.py | 2026-03-02 |
| T1-04 | Hardcoded safety thresholds bypassing thresholds.py | 2026-03-02 |
| T1-05 | Dead duplicate ACWR constants in constants.py | 2026-03-02 |
| T1-06 | DB concurrency: read paths unguarded + close() race | 2026-03-04 |
| T1-07 | DailyCoach daemon overlap — run_morning_routine_async() unserialised | 2026-03-04 |
| T1-08 | Silent hardcoded fallback in _get_baseline_rhr() | 2026-03-04 |
| T1-09 | Synthetic weather fallback without degraded-mode gate | 2026-03-04 |
| T1-10 | DB write methods: cursor outside lock — race window | 2026-03-05 |
| T1-11 | main.py shutdown: routine thread not joined before db.close() | 2026-03-05 |
| T1-12 | _persist_garmin_data(): non-atomic persistence | 2026-03-05 |
| T1-13 | DB write methods: cursor race in governance/science paths | 2026-03-06 |
| T1-14 | Garmin activity duplicate persistence — no idempotency key | 2026-03-06 |
| T1-15 | _persist_garmin_data() fail-open: persistence failure not propagated | 2026-03-06 |
| T1-16 | Schema version tracking absent | 2026-03-06 |
| T1-17 | No backup/recovery policy | 2026-03-06 |
| T1-18 | No physiological bounds validation | 2026-03-07 |
| T1-19 | No structural/temporal data sanity validation | 2026-03-07 |
| T1-20 | Garmin connectivity failure has no staleness gate | 2026-03-07 |
| T1-21 | Governance gates H2/H3 fire without distinguishing training vs illness stress | 2026-03-07 |
| T1-22 | OutcomeTracker schema lacks feedback-loop guardrails | 2026-03-07 |
| T1-23 | No unified DataTrustLevel contract | 2026-03-07 |

---

## TIER 2 — Observability (All Resolved ✅)

All 17 Tier 2 items (T2-01 through T2-17) are **RESOLVED**.
Full history: [`archive/technical_debt_t1_t3_resolved.md`](archive/technical_debt_t1_t3_resolved.md)

| # | Item | Resolved |
|---|------|----------|
| T2-01 | Error taxonomy: garmin_sync.py | 2026-03-02 |
| T2-02 | Error taxonomy: daily_coach.py | 2026-03-02 |
| T2-03 | Error taxonomy: telegram_bot.py | 2026-03-02 |
| T2-04 | Error taxonomy: governance_engine.py | 2026-03-02 |
| T2-05 | JSON guard for DB governance rows | 2026-03-02 |
| T2-06 | Athlete load error detail in database.py | 2026-03-02 |
| T2-07 | Launcher and startup error path observability | 2026-03-02 |
| T2-08 | Residual broad catches in DB best-effort branches | 2026-03-02 |
| T2-09 | Residual print() operational/error paths across integration modules | 2026-03-06 |
| T2-10 | Startup engine hydration has no data-confidence gate | 2026-03-06 |
| T2-11 | Telegram fallback logs message content — privacy risk | 2026-03-06 |
| T2-12 | UI path silent except Exception: pass | 2026-03-06 |
| T2-13 | Degraded mode duration not tracked | 2026-03-06 |
| T2-14 | Structured events lack severity levels; deduplication absent | 2026-03-07 |
| T2-15 | Weather synthetic fallback uses hardcoded location defaults | 2026-03-07 |
| T2-16 | Governance decisions lack human-readable rationale | 2026-03-07 |
| T2-17 | Metric lifecycle states not tracked | 2026-03-07 |

---

## TIER 3 — Dependency Hygiene (All Resolved ✅)

All Tier 3 items (T3-02 through T3-09) are **RESOLVED**.
Full history: [`archive/technical_debt_t1_t3_resolved.md`](archive/technical_debt_t1_t3_resolved.md)

| # | Item | Resolved |
|---|------|----------|
| T3-02 | Add ruff and mypy to dev requirements | 2026-03-02 |
| T3-03 | Secrets handling simplification | 2026-03-02 |
| T3-04 | Threading lifecycle: use threading.Event for clean stop | 2026-03-02 |
| T3-05 | Threading lifecycle: weather updater Event.wait() pattern | 2026-03-02 |
| T3-06 | Background worker shutdown without escalation | 2026-03-04 |
| T3-07 | scheduled_tasks list mutable and unsynchronized | 2026-03-04 |
| T3-08 | Weather + Telegram worker shutdown: no post-join alive escalation | 2026-03-06 |
| T3-09 | Telegram is single point of failure — no notification fallback | 2026-03-06 |

---

## TIER 4 — Maintainability (Sprint 4+)

### T4-01 · Ruff debt burn-down (lint hygiene) ✅ RESOLVED

**Status (2026-03-04):** Completed. `ruff check . --statistics` returns zero findings; burn-down closure criterion satisfied.

### T4-27-C · Define module ceiling update policy for feature additions ✅ RESOLVED 2026-03-15

**Status:** ✅ RESOLVED 2026-03-15. Commit: `e061042`.
**Source:** Architect Decision 2026-03-15 (T5-16-A records steward pass). T4-27 child item.
**Priority:** P3 (Tier 4 — maintainability). Independent.
**Workflow Path: A**

**Rationale:** Accepted features that add structural modules must update the ceiling explicitly
through a records/policy path, so future additions do not require ad hoc corrections.

**Original state (pre-fix):** T5-16-A closure was blocked because the complexity-budget guard ceiling (61) was
stale — it had not been updated when the CoachingScheduler stub was added as a legitimate
structural module. The ceiling update happened ad hoc as part of the closure records pass rather
than as part of the feature implementation workflow.

**Fix direction:**

Add a subsection to AGENTS.md §16.11 (or equivalent policy location) specifying:
1. When any task adds one or more new `titan/` modules as a deliberate structural choice
   (not a bug fix or rename), the implementing engineer must update the ceiling in
   `tests/test_documentation_consistency.py::test_module_count_within_budget` in the same
   commit, with a one-line comment attributing the ceiling increment to the task ID.
2. The architect must confirm the new ceiling value in the task acceptance criteria before
   implementation begins.
3. Ad hoc ceiling corrections after the fact are a process violation — same category as
   a failed mandatory gate.

**Acceptance criteria (binary):**
- AGENTS.md §16.11 (or designated policy section) contains the three-rule module ceiling
  update protocol described above.
- At least one sentence cross-references T4-27-C as the source of this rule.
- `python -m pytest -q` passes with no regressions.

**Resolution:** Updated `AGENTS.md` §16.11 to codify the three-rule T4-27-C protocol for module ceiling updates on accepted structural feature additions, including a direct cross-reference back to T4-27-C as the rule source.

**Status:** ✅ RESOLVED — 2026-04-13. `MODULE_COUNT_CEILING = 63` moved to
`thresholds.py` (importable); `tests/test_complexity_budget.py` replaces CI inline
literal; ceiling is now testable and self-documenting. `ci.yml` complexity-budget job
updated to import from `thresholds.py` instead of using a hardcoded literal.
*(C-W04 records correction 2026-04-24: ceiling value aligned to canonical full_module_audit.sh output — 63 modules.)*

**Task learning:** Policy-only safeguards still need explicit ownership timing (architect confirms before implementation; implementing engineer updates in-commit) to avoid post-hoc records fixes.

**Effort:** ~30 minutes. Policy text only — no implementation.

---


## TIER 5 — Future Optionality

### T5-01 · SQLite retention / archival strategy 🟢

**Decision status:** CLOSED. **Wording status:** LOCKED/CLOSED.
Decision locked (ADR-0015). No further decision is open in T5-01.
Scope remains single-athlete, single-lifetime. Phase 8 gate (mandatory): no implementation before ADR acceptance.

### T5-03 · Multi-sport scope decision 🟢

Decision status: CLOSED. Decision locked (ADR-0016).

---

### T5-04 · No science evidence review ritual — governance thresholds may become stale relative to new literature 🟢

**Decision status:** OPEN (deferred — Phase 9+).
**Source:** Master Risk Matrix — Risk #12 (Model Stagnation vs New Science). Architecture Review 2026-03-06.

**Original state (pre-fix):**

All thresholds in `thresholds.py` carry an evidence label (STRONG / MODERATE / HEURISTIC)
in `evidence_registry.py`. However, there is no scheduled review of whether the evidence
has been superseded by newer research (e.g., updated ACWR safe zone boundaries, revised
HRV interpretation protocols, new lactate threshold testing methods).

**Decision:**

Deferred to Phase 9. Gate criterion: `evidence_registry.py` must include a
`_LAST_REVIEWED` date for each entry. A scheduled CI job (quarterly) flags entries
whose `_LAST_REVIEWED` is older than 365 days. The flag is a warning, not a gate failure
— the architect decides whether to update the threshold or extend the review date.

**Phase 9 gate:** This item is a prerequisite for Phase 9 (lifecycle supervisor). No
implementation before Phase 8 closes.

---

### T5-05 · No athlete model recalibration mechanism — physiological models drift as athlete evolves 🟢

**Decision status:** OPEN (deferred — Phase 9+).
**Source:** Architect Observations V6 — Risk #3 (Model Aging). Architecture Review 2026-03-06.

**Original state (pre-fix):**

Physiological models (HRV baseline, CTL/ATL EMA constants, lactate thresholds,
critical speed) are calibrated on historical data and held constant once computed.
An athlete's body changes: fitness improves, injury changes biomechanics, age alters
recovery kinetics. The models remain accurate at first; over 6–12 months they may
produce coaching decisions that are correct by the model but wrong for the current
athlete.

The `OutcomeTracker` already collects decision→outcome pairs for this purpose
(ADR-0014, T2-10). The missing piece is a **recalibration trigger**: a mechanism
that detects systematic divergence between predicted and observed outcomes and
proposes model parameter updates.

**Observable early signal:** If the governance engine's VO2 eligibility gate (G6)
consistently predicts readiness but post-session RPE is ≥8 for 3+ consecutive sessions,
the readiness model is over-predicting. `OutcomeTracker` has the data; there is no
consumer that acts on it.

**Decision:**

Deferred to Phase 9. The `AutomatedPeriodizationEngine` (Phase 7 ML scaffold,
ADR-0014) is the intended consumer of `OutcomeTracker` calibration data. Phase 9
will implement the feedback loop: `OutcomeTracker` → divergence detector →
`AutomatedPeriodizationEngine` → parameter update proposal → architect review →
model update.

The feedback loop is advisory-only (not automatic) to preserve human oversight of
physiological model parameters. Consistent with ML scaffold philosophy (ADR-0014).

**Phase 9 gate:** Requires `OutcomeTracker` to have ≥90 days of decision→outcome
pairs before the divergence detector can produce statistically meaningful signals.
No implementation before Phase 8 closes and data accumulation criterion is met.

**Phase 9 calibration design constraints (DEC-FR-01 / DEC-FR-02 — 2026-03-08):**

When the Phase 9 calibration mechanism is designed, the following must be included
as hard requirements — not optional:

1. **Damping constant:** a maximum per-cycle adjustment percentage (e.g. ±5% per run)
   to prevent runaway feedback divergence. This is a named constant in `thresholds.py`,
   not a hard-coded float. Evidence registry entry required.
2. **Minimum observation count before modification:** no parameter may be adjusted unless
   the relevant observation pool exceeds a defined minimum (separate from the 90-day gate
   above — this applies per-parameter, not globally).
3. **CI test:** a test verifying that the damping constant is respected — i.e., a
   calibration run with a large input divergence must not produce an adjustment exceeding
   the damping bound.
4. **Domain baseline snapshot:** before any calibration loop is wired, a test must pin the
   input→output semantic contracts for core metrics (readiness score range [0,100], ACWR
   safe band [0.80,1.30], injury risk range [0.0,1.0]) as invariants. This ensures
   calibration cannot shift the meaning of these concepts without a test failure.

5. **Proxy metric alignment guard (DEC-FR-03 — 2026-03-08):** The calibration loop
   must not be evaluated solely on surrogate signals (e.g., lower lock rate, higher
   readiness scores, tighter ACWR band). Optimizing a proxy without anchoring to the
   real coaching goal risks Goodhart's Law: the system achieves better metric scores
   while drifting away from actual athlete benefit. Required safeguard:
   - At least one acceptance criterion in the Phase 9 calibration ADR must be stated
     in terms of **domain outcomes** (e.g., RPE alignment, injury incidence rate,
     athlete-reported feel), not governance metric movements alone.
   - The divergence detector must be validated against a held-out outcome set that
     was not used to tune the detector itself.
   - Any new proxy metric added to the calibration signal must include a written
     justification of its correlation with domain outcomes, filed in
     `titan/config/evidence_registry.py` before the metric is wired.

These constraints are architectural requirements for Phase 9 entry, not implementation details.
An ADR will be required before implementing the calibration adjustment mechanism.

---

### T5-06 · ML advisory models lack explainability contract — feature attribution and plain-text reason absent 🟢

**Decision status:** ⚠️ PARTIALLY RESOLVED 2026-03-15 — T5-06-A complete (Phase 8A early work). T5-06-B remains deferred Phase 9.
**Workflow Path (T5-06-A): A** *(touches ≥ 3 production modules — PILOT-01 excluded)*
**Source:** Risk Review V7 — Risk: ML Physiological Safety & Ethical Opacity. Architecture Review 2026-03-06. ADR-0032.

**Original state (pre-fix):**

`InjuryRiskEnsembleModel` operates in advisory mode and returns a probability score
(0.0–1.0) with no feature attribution. The governance engine cannot determine whether
a score of 0.73 is driven by an ACWR spike (rest one day), chronic TSB depression
(reduce load a week), a biomechanics anomaly (physio referral), or historical injury
proximity (monitor). These four scenarios warrant entirely different coaching responses.
The two shadow-mode models (`LoadPredictionShadowModel`, `AutomatedPeriodizationEngine`)
will have the same gap when promoted to advisory.

**T5-06-A — `InjuryRiskEnsembleModel` explainability (Phase 8A early work):**

Since `InjuryRiskEnsembleModel` is currently advisory, it must be brought into compliance
with the `ExplainableOutput` contract (ADR-0032) early in Phase 8, before Phase 8B begins.

Fix direction:
1. Add `ExplainableOutput` dataclass to `titan/science/ml_safety.py` (or a new
   `titan/science/ml_explainability.py` module).
2. Extend `InjuryRiskEnsembleModel.assess_injury_risk()` to return `ExplainableOutput`
   alongside the primary score: top-3 feature contributions, confidence range,
   `plain_text_reason` (template-based, not LLM-based), `data_freshness_ok`
   (using ADR-0030 staleness flag).
3. Update governance engine integration to log `plain_text_reason` and include
   feature contributions in the Operator Console session explorer payload (ADR-0011).
4. Add `tests/test_ml_explainability.py`:
   - `test_injury_risk_returns_explainable_output` — happy path contract.
   - `test_injury_risk_stale_data_discarded` — stale data → `data_freshness_ok=False`
     → advisory output discarded by governance.
   - `test_plain_text_reason_nonempty` — reason string non-empty for all test cases.


**Status (T5-06-A):** ✅ RESOLVED 2026-03-15. Commit: 9fe7e96.

**Resolution (T5-06-A):** Added deterministic `ExplainableOutput` support to the injury risk advisory payload (top-3 contributions, confidence range, template `plain_text_reason`, and `data_freshness_ok`); extended `InjuryRiskEnsembleModel` with `assess_injury_risk()` + stale-data discard helper; surfaced explainability data through payload boundaries used by Operator Console session explorer when present; and added dedicated explainability tests (`tests/test_ml_explainability.py`) plus contract updates in existing injury-risk tests. Final full-suite count at closure: 1941 passing tests.
**Implementation path note (DEC-019):** `ExplainableOutput` was added to `titan/science/ml_safety.py` — the first option listed in the fix direction. No separate `titan/science/ml_explainability.py` module was created, and none is expected going forward; `ml_safety.py` is the canonical home for this dataclass.

**Task learning:** Existing advisory model contracts are consumed by multiple stability tests, so explainability extensions should be additive and backward-compatible (`assess_risk()` delegating to `assess_injury_risk()`) to avoid integration churn while still meeting ADR contract obligations.

**T5-06-B — Shadow model promotion gate (deferred Phase 9):**
`LoadPredictionShadowModel` and `AutomatedPeriodizationEngine` must satisfy the
ADR-0032 promotion gate (criteria P1–P6) before being promoted to advisory mode.
No implementation before Phase 8 closes.

**Acceptance gate for T5-06-A (binary):**
```bash
ruff check titan/science/injury_risk_model.py titan/science/ml_safety.py \
            tests/test_ml_explainability.py
python -m pytest tests/test_ml_explainability.py -v
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

**Effort (T5-06-A):** ~4h. `ExplainableOutput` dataclass + ensemble attribution
logic + governance integration update + tests.

**Phase 8A early work:** T5-06-A must be RESOLVED before Phase 8B begins. (Phase 8 is already OPEN — G1–G11 all cleared 2026-03-08. T5-06-A is Tier 5 and was not a G1 blocking criterion.)

---

### T5-10 · Phase 10 LLM coach query layer not yet designed in detail 🟡 DEFERRED

**Status:** OPEN (deferred — Phase 10; implement only after Phase 9 closes with sufficient multi-athlete corpus).
**Source:** FUTURE_UPGRADES.md Phase 8/10 scope (Decision 3, Seam 3), ADR-0045 (LLM backend abstraction).
**Priority:** P5 (future optionality).

**Location:** `titan/integrations/llm_coach.py` (new module, Phase 10 only).

**Contract (do not deviate):**

```python
LLM_BACKEND = os.environ.get("TITAN_LLM_BACKEND", "none")  # none | claude | ollama

def coach_query(prompt: str, athlete_context: dict) -> str:
    if LLM_BACKEND == "none":
        return _deterministic_fallback_summary(athlete_context)
    # ADR-0045: route to Claude API or Ollama depending on LLM_BACKEND
```

**Hard invariants (CI must verify):**
- No governance module imports `llm_coach` (LLM never in safety path).
- `TITAN_LLM_BACKEND=none`: all paths return deterministic output.
- Every LLM recommendation passes through override handler registry (ADR-0042).

**Deferred until:** Phase 9 closes AND multi-athlete corpus ≥ 100 paired outcomes per athlete.

---

### T5-15 · Test suite has no pytest layer marker taxonomy — unit/integration/governance indistinguishable 🟡 DEFERRED

**Status:** DEFERRED (Phase 9 housekeeping).
**Recorded:** 2026-03-08 (DEC-001 / OBS-001 — future maintenance observation, architect review).
**Source:** Engineer observation post-Phase 7 CI safeguards review.
**Priority:** P4 (engineering quality-of-life; no functional or safety impact).

**Context:**
118 test files (~1780+ tests) have no pytest mark taxonomy beyond filename conventions.
`pyproject.toml` registers only `markers = ["timeout: ..."]`. No `unit`, `integration`,
or `governance` marks exist. Targeted subset runs rely on filename patterns
(`pytest tests/test_p0*.py`, `pytest tests/test_governance_integration.py`), which is
adequate at current scale but degrades as the suite grows toward ~3000 tests.

**Acceptance gate (binary):**
1. Register markers in `pyproject.toml`: `unit`, `integration`, `governance`, `invariant`.
2. Apply exactly one marker to every test function across all 118 test files.
3. `pytest -m governance -q` collects only governance tests (no `PytestUnknownMarkWarning`).
4. `pytest -m unit -q` completes in under 30 seconds on CI hardware.
5. All three mandatory gates pass: `ruff check .` → `pytest -q -W error::pytest.PytestWarning` → `pytest -q`.

**Scope note:** Mechanical refactor only — no test logic changes. Marker assignment follows
this taxonomy:
- `unit` — tests a single class/function in isolation (mocks all external deps)
- `integration` — tests interaction between 2+ modules or with SQLite
- `governance` — tests a governance gate contract or invariant (may overlap with integration)
- `invariant` — tests a doc/schema/CI invariant (e.g. `test_claude_md_integrity.py`)

**Effort:** ~2h mechanical pass. No architectural decision required.

**Phase 9 gate:** This item is a prerequisite for Phase 9 targeted-execution CI optimisation.
Do not implement during Phase 8 — it is a large-scope mechanical refactor with no Phase 8
safety or functional benefit.

---


### T5-46 — T5-73: All Resolved (2026-03-26 to 2026-04-04)

All 25 items fully resolved. See [`archive/technical_debt_history.md`](archive/technical_debt_history.md) for full entries.

| # | Item | Resolved |
|---|------|----------|
| T5-46 | HRV deduplication on overlapping Garmin syncs | 2026-03-27 |
| T5-47 | ZeroDivisionError on zero activity pace | 2026-03-26 |
| T5-48 | Garmin data age not propagated to governance context | 2026-03-28 |
| T5-49 | Governance defaults missing sleep/readiness to conservative | 2026-03-27 |
| T5-50 | All activities persisted with session_type EASY | 2026-03-27 |
| T5-51 | ACWR defaults to 1.0 on sync failure | 2026-03-26 |
| T5-52 | CS confidence defaults to 1.0 when tracker is None | 2026-03-26 |
| T5-53 | ReadinessEngine TypeError on null HRV | 2026-03-26 |
| T5-54 | drift_pct defaults to 0.0 on sync failure | 2026-03-27 |
| T5-55 | apply_thermal ignores dew_point — ESI unused | 2026-03-27 |
| T5-56 | AFI confidence not penalised for sparse HRR data | 2026-03-27 |
| T5-57 | Weekly plan never re-evaluated mid-week | 2026-03-27 |
| T5-58 | WeeklyPlanner TypeError on null HRV | 2026-03-26 |
| T5-59 | NutritionOptimizer dew_point defaults optimistic | 2026-03-27 |
| T5-60 | sleep field mapping mismatch in _persist_garmin_data | 2026-03-28 |
| T5-61 | multi-day HRV sync discards 6 of 7 days | 2026-03-28 |
| T5-62 | zero-sync silent failure on stale token | 2026-03-28 |
| T5-65 | classify_hrv_stress_context None ACWR returns wrong label | 2026-03-29 |
| T5-66 | save_daily_metric INSERT OR REPLACE destroys subjective fields | 2026-03-29 |
| T5-67 | sync methods emit success events unconditionally | 2026-04-04 |
| T5-68 | ESI dew_point 12.0°C magic number in daily_coach.py | 2026-03-29 |
| T5-69 | sync_activities lacks activityId / garmin_activity_id column | 2026-03-29 |
| T5-70 | AuthStore not wired to SQLite auth tables | 2026-04-04 |
| T5-72 | H2/H3 gates fail-open on missing HRV/RHR data | 2026-04-17 |
| T5-73 | PostgreSQL save_session lacks ON CONFLICT DO NOTHING | 2026-04-17 |

---
### HD-01 · HRVGuidedEngine lacks baseline drift detection — silent HRV baseline staleness ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md
**Severity:** HIGH
**Location:** `titan/science/hrv_engine.py` (`HRVGuidedEngine`)
**Resolution:** `check_baseline_drift()` added to `HRVGuidedEngine`; emits `hrv_baseline_drift_warning` event when baseline drift exceeds threshold; 8 tests green. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---

### HD-02 · database.py activity timestamp truncation — UTC handling incorrect ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md
**Severity:** HIGH
**Location:** `titan/core/database.py` (lines 1405, 1843)
**Resolution:** UTC fix applied at database.py:1405,1843; tz-aware timestamp handling corrected. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---

### HD-03 · H5/FUELING/INTENSITY gates missing NaN guards — silent governance bypass ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md / ADR-0009
**Severity:** HIGH
**Location:** `titan/science/governance_engine.py` (H5, FUELING, INTENSITY gates)
**Resolution:** NaN guards added to H5, FUELING_GATE, and INTENSITY_GATE_RED/YELLOW paths per ADR-0009; 3 new tests green. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---


### HD-04 · [INTENTIONALLY UNASSIGNED — slot retired]

**Status:** N/A — HD-04 slot was never assigned during TITAN_HARDENING_FRAMEWORK_v1.md authoring (2026-04-03).
HD-01 through HD-09 were assigned non-sequentially; HD-04 was skipped. No work item was lost.
Confirmed by architect review (Opus audit C-B03, 2026-04-20).

---

### HD-05 · AuthenticatedRateLimiter._requests accumulates keys unboundedly — memory DoS vector ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** DEC-036 / OBS-038
**Severity:** MEDIUM
**Workflow Path: A**
**Location:** `titan/api/main.py` (`AuthenticatedRateLimiter`), `titan/config/thresholds.py`
**Description:** `AuthenticatedRateLimiter._requests` is a `defaultdict(deque)` keyed by `(user_id, role, method:path)`. Expired timestamps are pruned within each deque on every request, but dict entries for empty deques are never evicted. An adversary issuing requests across many unique paths or rotating through user accounts inflates the dict without bound. At scale this is a memory DoS vector.

**Acceptance criteria (binary):** `RATE_LIMITER_MAX_KEYS = 10_000` constant added to `titan/config/thresholds.py`; `AuthenticatedRateLimiter` implements LRU eviction when `len(self._requests) >= RATE_LIMITER_MAX_KEYS` (oldest-by-last-request key evicted on new key insertion); tests verify the ceiling is enforced and legitimate state is preserved for active keys.

**Resolution:** `RATE_LIMITER_MAX_KEYS=10000` added to thresholds.py; LRU eviction implemented; `limiter_eviction` WARNING event emitted on eviction; 6 tests green. 2026-04-04.

---

### HD-06 · DegradedModeTracker state not persisted — degradation timers lost on process restart ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** DEC-037 / OBS-039
**Severity:** HIGH
**Location:** `titan/orchestration/daily_coach.py` (`DegradedModeTracker`)
**Resolution:** `DegradedModeTracker` persists to `degraded_mode_state` SQLite table via `_persist_state()`; hydrates timers from DB on startup via `_hydrate_from_db()`; degradation timers survive process restarts; 9 tests green. 2026-04-04. commit: not individually recorded (batch closure 2026-04-04)

---

### HD-08 · PersistenceFailure mixed state: silent no-ops, mixed-epoch H3, unobservable degraded coaching output ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-04-04
**Source:** DEC-038 / OBS-041
**Severity:** HIGH
**Workflow Path: A**
**Location:** `titan/orchestration/daily_coach.py` (steps 3, 6, payload assembly), `titan/science/governance_engine.py` (context passthrough only)
**Description:** Three bounded observability/coherence gaps under `PersistenceFailure`: (1) `save_hrr()` and `update_glycogen_debt()` silently affect 0 rows when `daily_metrics` has no row for `today_str` after a persistence rollback — no event is emitted; (2) H3 gate consumes mixed-epoch data (`today_rhr` is ephemeral, `baseline_rhr` is DB-derived) with no flag propagated to the governance context; (3) `coaching_data` payload has no `persistence_degraded` bool field, making it impossible for the Telegram message or Operator Console to distinguish a persistence-degraded decision from a normal one. Gate logic must NOT be changed — ADR-0020 intent is preserved.

**Acceptance criteria (binary):** `_daily_coach_event("hrr_persist_skipped")` and `("glycogen_persist_skipped")` are emitted when `persistence_degraded=True` and the respective UPDATE affects 0 rows; `persistence_degraded: bool` is added to the governance context dict and to `coaching_data` payload; the Telegram coaching message annotates the session type when `persistence_degraded=True`; no changes to any gate decision logic.

**Resolution:** `data_confidence_low=True` when `persistence_degraded=True`; silent no-op WARNING events emitted for hrr/glycogen persist skips; `persistence_degraded` field added to governance context and `coaching_data` payload; 8 tests green. 2026-04-04.

---

### HD-09 · No population-specific threshold adaptation — static thresholds regardless of age/fitness tier

**Status:** ✅ RESOLVED — 2026-04-12. ThresholdAdapter implemented in `titan/science/threshold_adapter.py` (MODULE_VERSION 1.0.0); `athlete_threshold_offsets` DB table (schema v12, Alembic migration 20260412_01); `GovernanceEngine.__init__` accepts optional `threshold_adapter` parameter; `GovernanceEngine._get_soft_threshold()` routes soft-gate lookups through adapter; ADR-0052 constants in `thresholds.py`; evidence_registry entries added. Tests: `tests/titan/science/test_threshold_adapter.py` (42 tests). All three gates passed: G1 ruff clean, G2 strict pytest 2482 passed, G3 full pytest 2482 passed.

**ADR-0052 Stage 3 (2026-04-17):** ThresholdAdapter wired into `coaching_pipeline()`. Instantiated per-athlete, per-run. `load()` called at pipeline entry. `GovernanceEngine` constructed with `threshold_adapter=` argument and injected into `DailyCoach._decision_pipeline()` via `governance_engine=` kwarg; `_decision_pipeline()` uses injected engine for step 9 (`apply_constraints`) and step 12 (`get_governance_report`), falling back to `self.governance` when `None`. Cold-start bypass enforced: adapter skipped entirely during cold-start per ADR-0033 L3-C. `propose_adaptation()` NOT called (Stage 4 scope). Tests: `tests/titan/orchestration/test_coaching_pipeline_adapter.py` (+5).

**ADR-0052 Stage 4 (2026-04-24):** ✅ IMPLEMENTED — `OutcomeTracker.run_calibration_cycle()` added to `titan/science/outcome_tracker.py`. Three ordered guards (diversity, circuit-breaker, CALIBRATION_AVAILABLE) gate the cycle. For each soft threshold in `base_values`, direction is computed from `false_positive_rate` (>0.30 → loosen) / `false_negative_rate` (>0.15 → tighten) and routed through `ThresholdAdapter.propose_adaptation()`. Hard-stop gates (H2–H5) are unconditionally skipped via `is_hard_stop_gate()`. Returns a 9-key structured event dict (status, athlete_id, adaptations_attempted, adaptations_applied, false_positive_rate, false_negative_rate, circuit_breaker_active, thresholds_evaluated, timestamp). Tests: `tests/test_adr0052_stage4_calibration_cycle.py` (7 tests). ADR-0052 all four stages complete.
**Source:** TITAN_HARDENING_FRAMEWORK_v1.md §1.1 / HD-09
**Severity:** MED
**Failure Class:** Safety Logic
**Location:** `titan/config/thresholds.py`, `titan/science/governance_engine.py`, `titan/science/outcome_tracker.py`
**Description:** TITAN OS applies identical governance thresholds (HRV delta, RHR delta, ACWR safe band, readiness floors) regardless of athlete age, fitness tier, or accumulated training history. Masters athletes (>45) produce systematic false positives; beginners produce systematic false negatives. Static threshold half-life (~10–16 weeks) is too long for elite athlete adaptation. The `OutcomeTracker` already collects `decision→outcome` pairs per athlete but the calibration loop back into threshold constants does not exist.
**Architecture decision:** ADR-0052 — per-athlete additive offset `δT` per threshold; `ThresholdAdapter` module; `GovernanceEngine` optional injection; `athlete_threshold_offsets` DB table; hard-stop gates (H1–H5) excluded from adaptation; circuit breaker at `FALSE_NEG > 20%` over 30 days; damping ±5% per cycle; |δT| ≤ 20% ceiling.

---

### PILOT-01 · Opus QA layer — automated test-quality review between Codex and mandatory gates 🟡 PILOT

**Status:** PILOT — not permanent. Activate on next Phase 8 sprint item; evaluate after one sprint.
**Recorded:** 2026-03-08 (E14 — idea captured before implementation).

**Applicability gate — classify the item before activating PILOT-01:**

PILOT-01 runs **by default** only when ALL of the following hold:
- Effort estimate ≤ 1 day (≤ ~6h).
- No schema changes (no `CREATE TABLE`, `ALTER TABLE`, column additions, or Alembic migration).
- No cross-subsystem dependency changes (does not alter import graph between packages).
- Scope limited to ≤ 2 modules (production code side).

PILOT-01 is **opt-in only** (requires explicit architect APPROVED note in this entry before
Codex activates it) when the item involves any of:
- Schema migration or database backend replacement (e.g. T5-07 Layer 1, T5-08 PostgreSQL).
- Architectural refactor — kernel boundary changes, subsystem extraction, god-object splits.
- Multi-tier change — touches governance infrastructure (Tier 1–4) across ≥ 2 tiers.
- Effort > 1 day or item is explicitly labelled P0.

**Fallback (non-negotiable):** If the applicability conditions are not met, PILOT-01 must not
run. Codex proceeds directly to the mandatory gates workflow. No QA step is inserted.

Rationale: the Opus QA reviewer operates on test quality within a bounded implementation
context. For migration and refactor items the reviewer lacks the schema diff, migration
sequence, and cross-module coupling context required to make a valid coverage judgement.
A REJECT in that context adds friction without diagnostic value and risks incorrect advice.

**Motivation:** Codex's test output passes gates mechanically (ruff + pytest) but may miss semantic
gaps: undertested edge cases, missing invariant coverage, acceptance criteria not fully exercised.
An automated QA pass before the gates can catch these earlier and reduce back-and-forth.

**Protocol design (pilot version):**

```
Codex implements item
  └─► Opus QA review (test quality only — see scope below)
        ├─ APPROVE  →  Codex runs mandatory gates → DONE
        └─ REJECT   →  Codex fixes, re-submits to Opus once
                          └─ Opus re-review (one re-review max)
                                └─ Codex runs mandatory gates → DONE
```

**Scope of Opus QA (bounded — do not expand without updating this entry):**
- Do the tests actually cover the acceptance criteria in the debt item?
- Are the critical edge cases exercised (boundary values, error paths, invariant violations)?
- Are regression tests present for any behaviour that was broken or changed?
- Are parametrize / property-based tests used where the input space warrants it?

**Out of scope for Opus QA (explicit exclusions):**
- Architectural decisions — those belong to Claude (architect role).
- Code style, naming, formatting — ruff handles this.
- Implementation correctness — mandatory gates (pytest) handle this.
- Overriding or substituting the mandatory gates — see invariant below.

**Mandatory gates invariant (non-negotiable):**
> Opus QA approval is an advisory signal only.
> The three mandatory gates (ruff, pytest strict, pytest full) are the **sole binding DONE criterion**.
> A PR is NOT done until all three gates are clean — regardless of Opus QA status.
> Opus QA approval does NOT mean gates have passed.

**Pilot success criteria (binary — evaluate after first Phase 8 sprint item):**
1. Opus QA identified at least one gap that would not have been caught by the gates alone.
2. The QA loop completed within one fix cycle (no more than one re-review required).
3. Total wall-clock overhead added to the sprint item ≤ 20% of implementation time.
4. No gate failures caused by Opus QA advice (i.e. Opus did not recommend changes that broke gates).

**If pilot passes all four criteria:** promote to permanent protocol in `AGENTS.md §17` +
update `CLAUDE.md` agent roster. Author ADR-0046 documenting the decision.

**If pilot fails:** close this entry as REJECTED, document root cause here, do not retry
without architectural discussion.

**Opus verdict logging rule (forward policy — applies from 2026-03-14 onward):**

Each Opus QA verdict must be logged next to the relevant task entry using this format:

```
[Opus QA] Task: <task-id> — QA PASS | QA FAIL — <one-line rationale>
```

This rule applies to all future verdicts. Historical tasks (T5-35 and earlier) are not retrofitted.

---

All Tier 5 decisions up to T5-16-A have been locked or deferred. T5-16-A resolved 2026-03-15 (stale ceiling 61→62 was the blocker, not functional regression; T4-27-C created). T5-17 through T5-35 are new entries from the Binder1 audit triage (DEC-1 + DEC-2, 2026-03-13). T5-19, T5-24, T5-25, T5-33, T5-34 are blocked pending architect input or brief. See Tracking table for completion dates and PRs.
Relevant ADRs: 0013 (UI path), 0014 (ML scaffold), 0015 (SQLite/multi-athlete), 0016 (multi-sport), 0022 (Phase 8 gate), 0028 (complexity budget), 0032 (ML explainability), 0033 (model aging), 0035 (feedback loop), 0036 (semantic versioning), 0043 (product direction + LLM seams), 0044 (PostgreSQL migration), 0045 (local LLM backend abstraction).

---

## Phase 15 — Multi-Device & Scale (CLOSED, 2026-05-15)

**Entry gate:**
- Phase 14 close audit: PASS ✅ (2026-05-09)
- Opus governance audit Phase 14: PASS ✅ (2026-05-09, 11 findings; P15-C2 through P15-OPS1)

**Scope:**
1. Opus governance audit (mandatory first step)
2. Polar/Whoop/COROS adapters
   (BiometricSourceAdapter protocol — ADR-0055 ready)
3. D6: Dockerfile + systemd unit
4. D13: decouple pipeline (long-term)
5. Real Garmin contract tests (vcrpy cassettes)

**Phase 15 CLOSED — 2026-05-15**
Close criteria met:
- phase_close_audit.sh 15 exit 0 ✅
- 2764 tests passing, 6 skipped ✅
- SCRATCHPAD STATUS: IDLE ✅
- All P1 items resolved:
  P15-C2 ✅ P15-C3 ✅ P15-D19 ✅ P15-D20 ✅
  P15-D21 ✅ P15-M5 ✅ P15-SEC8 ✅ P15-H3 ✅ P15-OPS1 ✅
- Deferred to Phase 16:
  P15-D22 (Telegram MarkdownV2 migration)
  TD-09 TD-10 TD-13 TD-17 TD-19 TD-06 (see Phase 16 scope)

---

### P15-C2 · API — validate_jwt_keys_at_startup not called at startup ✅ RESOLVED 2026-05-09

**Status:** ✅ RESOLVED 2026-05-09
**Source:** Opus audit 2026-05-09, finding C2. JWT keys validated lazily; runtime crash on first token operation if keys absent.
**Type:** Security / Fail-Fast
**Priority:** P1. Workflow Path: A.

**Fix:** Added FastAPI `lifespan` context manager to `create_app()` that calls `validate_jwt_keys_at_startup()` before the app accepts requests. Also added `db` parameter to `create_app()` for future DB audit persistence injection.

**Tests added:** `tests/titan/api/test_audit_middleware.py::test_jwt_startup_validation_raises_without_keys`

---

### P15-C3 · API — audit middleware reads request.state but JWT decode path missing ✅ RESOLVED 2026-05-09

**Status:** ✅ RESOLVED 2026-05-09
**Source:** Opus audit 2026-05-09, finding C3. Audit middleware had no fallback if request.state.current_user was unset; no DB persistence path.
**Type:** Observability / Correctness
**Priority:** P2. Workflow Path: A.

**Fix:** Added `_get_user_from_request()` helper that extracts user_id from JWT (decode-only, no re-validation) as a belt-and-suspenders path. Added optional DB persistence: `_audit_request` now writes to `DatabaseManager.log_coach_action()` when a `db` instance is injected via `create_app(db=...)`.

**Tests added:** `tests/titan/api/test_audit_middleware.py::test_authenticated_post_creates_audit_row`, `test_unauthenticated_request_no_audit_row`

---

### P15-C7 · DEPLOYMENT_GUIDE.md drift ✅ RESOLVED 2026-05-09

**Status:** ✅ RESOLVED 2026-05-09
**Source:** Opus audit 2026-05-09, finding C7. Guide had Python 3.8, stale branch refs, OpenWeatherMap references.
**Type:** Documentation Accuracy
**Priority:** P3. Workflow Path: A.

**Fix:** Updated Python version to 3.11+, replaced `git checkout claude/...` with `git checkout main`, replaced OpenWeatherMap section with Open-Meteo (free, no key), removed stale WEATHER_API_KEY references.

---

### P15-D19 · Duplicate _CredentialSecret class in integrations ✅ RESOLVED 2026-05-09

**Status:** ✅ RESOLVED 2026-05-09
**Source:** Opus audit 2026-05-09, finding D-19. `_CredentialSecret` duplicated in `garmin_sync.py` and `telegram_bot.py` — `SecretStr` in `titan/utils/secrets.py` is the canonical implementation.
**Type:** Code Duplication
**Priority:** P3. Workflow Path: A.

**Fix:** Removed `_CredentialSecret` class from both integration modules. Replaced all usages with `SecretStr` from `titan.utils.secrets`. Updated `.reveal()` call sites to `.get_secret_value()`. Updated 3 test files accordingly.

---

### P15-D20 · Archive monolith file ✅ RESOLVED 2026-05-09

**Status:** ✅ RESOLVED 2026-05-09
**Source:** Opus audit 2026-05-09, finding D-20. `archive/TITAN_v50_FULL_KERNEL_FINAL.py` (~v50 monolith) should not be tracked in git — bloats clone, confuses navigation.
**Type:** Repository Hygiene
**Priority:** P3. Workflow Path: A.

**Fix:** `git rm archive/TITAN_v50_FULL_KERNEL_FINAL.py`. Archive directory retained (other historical docs remain). Test updated to verify removal.

---

### P15-D21 · dependency-drift-audit CI job has continue-on-error: true ✅ RESOLVED 2026-05-09

**Status:** ✅ RESOLVED 2026-05-09
**Source:** Opus audit 2026-05-09, finding D-21. Dependency drift audit job set `continue-on-error: true` — failures were silently swallowed in CI.
**Type:** CI Reliability
**Priority:** P2. Workflow Path: A.

**Fix:** Removed `continue-on-error: true` from `dependency-drift-audit` job in `.github/workflows/ci.yml`. Drift failures now block the pipeline. Updated `tests/test_t4_25_dependency_drift_audit.py` to assert absence.

---

### P15-M5 · Rate-limit handlers return silently without user feedback ✅ RESOLVED 2026-05-09

**Status:** ✅ RESOLVED 2026-05-09
**Source:** Opus audit 2026-05-09, finding M5. Telegram command handlers that hit rate-limit said "please wait" without specifying the cooldown duration.
**Type:** UX
**Priority:** P3. Workflow Path: A.

**Fix:** Updated all 5 rate-limited handlers in `titan/integrations/telegram_bot.py` to reply "⏳ Please wait 30 seconds before repeating this command." Added `test_rate_limit_reply_message_sent` to `tests/titan/integrations/test_telegram_bot_observability.py`.

---

### P15-D22 · Telegram — legacy Markdown parse mode 🟡 OPEN

**Status:** 🟡 OPEN — deferred; _escape_markdown_v2 helper added as scaffold
**Source:** Opus audit 2026-05-09, finding D-22. Three explicit `parse_mode="Markdown"` call sites (lines 111, 444, 525 in `titan/integrations/telegram_bot.py`). Telegram's legacy Markdown parser is deprecated.
**Type:** Integration / UX
**Priority:** P3. Workflow Path: A.

**Blocker:** Line 652 actively uses `*bold*` Markdown syntax (`f"{emoji} *{title}*\n\n{message}"`). The TeleBot default at line 111 implicitly covers all `reply_to` call sites. A safe MarkdownV2 migration requires a full message audit to escape all special characters (`_*[]()~\`>#+-=|{}.!`) throughout all composed message strings before switching the parse mode.

**Acceptance criteria:** All message composition sites audited; all text passed to Telegram either uses `_escape_markdown_v2()` before `parse_mode="MarkdownV2"` or uses `parse_mode=None` (plain text). Zero `parse_mode="Markdown"` remaining. Test added to assert `parse_mode` arg equals `"MarkdownV2"` or `None`.

---

## Opus Audit 2026-05-09 — Open Findings Register

> Source: Production readiness audit (Opus), 2026-05-09.
> Items marked ✅ resolved in PR #675 or this pass.
> Items marked 🟡 OPEN are tracked for Phase 15+.

### Resolved in PR #675

| ID | Finding | Status |
|---|---|---|
| P15-C2 | JWT `validate_jwt_keys_at_startup()` never called at startup | ✅ RESOLVED |
| P15-C3 | Audit middleware no-op — no JWT decode fallback, no DB write | ✅ RESOLVED |
| P15-C7 | DEPLOYMENT_GUIDE.md: Python 3.8, stale branch ref, OpenWeatherMap | ✅ RESOLVED |
| P15-D19 | Duplicate `_CredentialSecret` × 3 → `SecretStr` | ✅ RESOLVED |
| P15-D20 | `archive/TITAN_v50_FULL_KERNEL_FINAL.py` 213 KB tracked in git | ✅ RESOLVED |
| P15-D21 | `dependency-drift-audit` CI job has `continue-on-error: true` | ✅ RESOLVED |
| P15-M5 | Rate-limit handlers return silently without user feedback | ✅ RESOLVED |

### Resolved in this pass (2026-05-09)

| ID | Finding | Status |
|---|---|---|
| P15-D22 | Telegram legacy `parse_mode="Markdown"` — `_escape_markdown_v2` helper added; mode change deferred | 🟡 OPEN (scaffold only — see P15-D22 entry above) |
| P15-SEC8 | No rate limit on `/auth/refresh` — `LoginRateLimiter(limit=5, window=60)` wired in | ✅ RESOLVED |
| P15-H3 | `datetime.utcnow()` in `database.py` — all 20 occurrences replaced with `datetime.now(UTC)` | ✅ RESOLVED |
| P15-OPS1 | No process supervisor — `docs/titan.service` + `docs/SYSTEMD_SETUP.md` added | ✅ RESOLVED |

### Open — Phase 15+ (implementation deferred)

| ID | Finding | Priority | Notes |
|---|---|---|---|
| P15-H1 | `daily_coach.py` god-orchestrator 1747 LOC | HIGH | ADR-0046 partial; split ongoing |
| P15-H2 | `database.py` monolith 3264 LOC | HIGH | Split by aggregate |
| P15-H6 | No HTTPS/TLS story for FastAPI | HIGH | Nginx/Caddy reference |
| P15-H9 | `DegradedModeTracker`: one alert then silence | MED | Continuous alerting signal |
| P15-D4 | SQLite SPOF — no automated backup | HIGH | ✅ RESOLVED 2026-05-24 — `titan-worker` calls `DatabaseManager.backup_database(keep=7)` every 24 h; `scripts/backup.sh` for manual ops; runbook updated |
| P15-D6 | No Dockerfile / process supervisor | MED | ✅ RESOLVED 2026-05-23 — ADR-0057 multi-stage Dockerfile + docker-compose.yml |
| P15-D8 | No load/performance tests | MED | k6 / locust |
| P15-D13 | Process-doc bloat (`AGENTS.md` 113 KB) | MED | Section caps / archival |
| P15-D14 | No metrics export | MED | Prometheus / OTel |
| P15-D15 | No distributed tracing | MED | OTel auto-instrument |
| P15-D16 | No Dockerfile | MED | ✅ RESOLVED 2026-05-23 — ADR-0057 (see P15-D6) |
| P15-D17 | Backup is `cp` cron — no restore drill | HIGH | ✅ RESOLVED 2026-05-24 — automated SQLite hot backup via `DatabaseManager.backup_database()`; runbook updated with restore procedure |
| P15-D22 | Telegram legacy `parse_mode="Markdown"` — full message audit needed | MED | See entry above |
| P15-D23 | No load tests | LOW | k6 against `/health` |
| P15-M2 | Garmin invalidation: no backoff retry | MED | Exponential backoff |
| P15-M3 | Telegram legacy `parse_mode` (alias of D22 in original report) | MED | Merged into P15-D22 |
| P15-M6 | `INSERT OR IGNORE` owner seed runs every startup | LOW | One-shot migration flag |
| P15-M10 | Auth state (rate limit, lockout) in-memory | MED | Accept or Redis |
| P15-SEC3 | Login trusts `request.client.host`, no `X-Forwarded-For` | HIGH | Proxy-aware IP extraction |
| P15-SEC7 | JWT no `kid` support — all tokens invalid on key rotation | MED | `kid` versioning |
| P15-OPS3 | No log aggregation | MED | vector / loki |
| P15-OPS5 | Schedule collision: Garmin 07:00 + DailyCoach 07:00 | MED | Coordinate schedule |
| P15-ARCH5 | Config split across 6+ surfaces | MED | pydantic-settings consolidation |
| P15-ARCH6 | Threading model has no happens-before invariant | MED | Document or enforce |

---

## FMEA: Phase 15 — Multi-Device & Scale

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F15-01 | Polar/Whoop API | Auth change → zero sync | MED | ADR-0055 protocol |
| F15-02 | Docker | Volume mount loss on deploy | LOW | Rehearsed restore procedure |
| F15-03 | vcrpy cassettes | Stale cassettes → false-green tests | MED | Monthly refresh gate |

---

## Phase 18 — Observability & Debt Clearance (CLOSED, 2026-05-23)

**Entry gate:**
- Phase 17 close audit: PASS ✅

**Close gate:**
- phase_close_audit.sh 18 exit 0 ✅ (2026-05-23)
- 2924 tests passing ✅

**Scope outcomes:**
1. TD-CTL-01: ✅ RESOLVED 2026-05-22 — per-day aggregation fix (PR #719).
2. TD-04: DailyCoach god-orchestrator split — DEFERRED Phase 19 (ADR-0058 required).
3. TD-08: Schema in two places — DEFERRED Phase 19 (500+ lines scope; Phase 19 work).
4. TD-11: ✅ RESOLVED 2026-05-23 — MetricsCollector stdlib JSON sink; 3 sites wired.
5. TD-NUTRITION-01: ✅ RESOLVED 2026-05-23 — carbs_range ±15% of adjusted target (PR #720).
6. TD-04: ✅ RESOLVED 2026-05-24 — ADR-0058 Phase A: EngineRegistry extracted; DailyCoach.engines holds all science engines. Phase B (EffectBus) + Phase C (daemon) deferred to Phase 20.

---

## FMEA: Phase 18 — Observability & Debt Clearance

**Phase:** 18 | **Date:** 2026-05-22 | **Author:** Architect

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F18-01 | TSBEngine hydration | CTL/ATL/TSB silently zero at UI render | HIGH | TD-CTL-01 |
| F18-02 | DailyCoach monolith | Regression risk on split without ADR gate | MED | TD-04 + ADR-0057 |
| F18-03 | SLOs unmeasured | Silent SLO violations in prod | HIGH | TD-11 |
| F18-04 | NutritionOptimizer | Carb display misleads athlete when low_carb active | LOW | TD-NUTRITION-01 |

---

## Phase 19 — Structured Debt & Scale (OPEN, 2026-05-23)

**Entry gate:**
- Phase 18 close audit: PASS ✅ (2026-05-23)

**Scope (priority order):**
1. TD-04: DailyCoach god-orchestrator split — ✅ RESOLVED 2026-05-24 (ADR-0058 Phase A: EngineRegistry).
2. TD-08 / TD-NEW-13: Schema single source of truth — extract CREATE TABLE into titan/core/schema.py; align alembic migrations (MED).
3. TD-NEW-15: Load/performance tests — benchmarks for DailyCoach pipeline, DB reads under concurrent load, API throughput (MED).
4. TD-NEW-11 OTel Phase 2: plug-in OpenTelemetry exporter via ADR into MetricsCollector (MED).
5. ADR-0044: PostgreSQL full parity gate.
6. ADR-0058: ✅ RESOLVED 2026-05-24 — Phase A implemented; Phase B (EffectBus) + Phase C (daemon) → Phase 20.

## FMEA: Phase 19 — Structured Debt & Scale

**Phase:** 19 | **Date:** 2026-05-23 | **Author:** Architect

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F19-01 | DailyCoach monolith | Split without ADR gate causes orchestration regression | HIGH | TD-04 + ADR-0058 |
| F19-02 | Schema extract | Broken migration if schema.py diverges from alembic | MED | TD-08 + review gate |
| F19-03 | OTel wiring | External dep introduced without ADR causes env breakage | MED | ADR gate required |

---

## FMEA: Phase 17 — Infrastructure & Scale

**Phase:** 17 | **Date:** 2026-05-15 | **Author:** Architect

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F17-01 | No Docker | Env drift between dev and prod | HIGH | TD-06 |
| F17-02 | Runbooks missing | Incident response gap | MED | ✅ TD-12 RESOLVED |
| F17-03 | SLOs unmeasured | Silent SLO violations | HIGH | TD-11 |
| F17-04 | DailyCoach monolith | Regression risk on split | MED | TD-04 |

---

## FMEA: Phase 16 — Operational Hardening

**Phase:** 16 | **Date:** 2026-05-15 | **Author:** Architect

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F16-01 | coach_audit_log | Audit trail silent: coach actions not written to DB on live requests | MED | TD-09 |
| F16-02 | Telegram bot | Replay attack: duplicate command execution on network retry | HIGH | TD-17 |
| F16-03 | All modules | print() leaks in prod logs: PII/debug noise in production output | MED | TD-10 |

---

## Tracking

When an item is completed, mark it here with date and PR reference:

| Item | Completed | PR |
|---|---|---|
| T1-T2, T3-02-09 | All 23+17+8 items RESOLVED. See archive/technical_debt_history.md | — |
| T3-01 | 2026-03-03 | [#172](https://github.com/zafiriss-ux/project-mayhem/pull/172) |
| T4-01 | 2026-03-03 | [#167](https://github.com/zafiriss-ux/project-mayhem/pull/167) |
| T4-02 | ✅ RESOLVED | PR: TBD |
| T4-03 | 2026-03-04 | PR: TBD |
| T4-04 | ✅ RESOLVED | PR: TBD |
| T4-05 | ✅ RESOLVED | PR: TBD |
| T4-06 | 2026-03-04 | PR: TBD |
| T5-01 | 2026-03-03 | [#173](https://github.com/zafiriss-ux/project-mayhem/pull/173), [#174](https://github.com/zafiriss-ux/project-mayhem/pull/174), [#175](https://github.com/zafiriss-ux/project-mayhem/pull/175) |
| T5-02 | 2026-03-03 | [#169](https://github.com/zafiriss-ux/project-mayhem/pull/169) |
| T5-03 | 2026-03-03 | [#170](https://github.com/zafiriss-ux/project-mayhem/pull/170) |
| T5-04 | 2026-03-03 | [#171](https://github.com/zafiriss-ux/project-mayhem/pull/171) |
| T4-07 | 2026-03-04 | PR: TBD |
| T4-08 | 2026-03-04 | PR: TBD |
| T4-09 | 2026-03-04 | PR: TBD |
| T4-10 | 2026-03-04 | PR: TBD |
| T4-11 | 2026-03-04 | PR: TBD |
| T4-12 | 2026-03-04 | PR: TBD |
| T4-13 | 2026-03-04 | PR: TBD |

| T4-14 | ✅ RESOLVED | 2026-03-06 (PR: TBD) |
| T4-15 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-16 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-17 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-18 | ✅ RESOLVED | 2026-03-06 |
| T4-19 | ✅ RESOLVED | 2026-03-06 |
| T4-20 | ✅ RESOLVED | 2026-03-06 |
| T4-21 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 07a9361) |
| T4-22 | ✅ RESOLVED (independent) | 2026-03-07 (commit: a2a9961) |
| T4-23 | ✅ RESOLVED | 2026-03-07 (commit: bd2da17) |
| T4-24 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 0590862) |
| T4-25 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 9dd54af) |
| T4-26 | ✅ RESOLVED (independent) | 2026-03-07 (commit: e40181a) |
| T4-27 | ✅ RESOLVED | 2026-03-07 (commit: 33e8255) |
| T4-27-C | ✅ RESOLVED | 2026-03-15 |
| T4-28 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 92555d3) |
| T5-04 | OPEN (deferred — Phase 9+) | — |
| T5-05 | OPEN (deferred — Phase 9+) | — |
| T5-06 | ⚠️ PARTIAL (T5-06-A ✅ RESOLVED 2026-03-15; T5-06-B deferred Phase 9) | 2026-03-15 |
| T5-14 | ✅ RESOLVED 2026-03-16 — ESI framework: constants in `thresholds.py`, ESI context in `DailyCoach`, VO₂ block via `VO2_ELIGIBILITY_GATE`, Telegram surfacing, `test_esi_compensation.py`; merge commit 31f8ef4 (PR #468) | 2026-03-16 |
| T5-15 | DEFERRED (Phase 9 housekeeping — test marker taxonomy) | — |
| T4-30 | ✅ RESOLVED (independent) | 2026-03-07 (commit: 4ddc184) |
| T4-31 | ✅ RESOLVED (IMMEDIATE — AGENTS.md §16.10 active) | 2026-03-07 (commit: eb20bb2) |
| T4-32 | ✅ RESOLVED | 2026-03-07 (commit: dfe8907) |
| T5-07 | ✅ RESOLVED — Layers 1–2: 2026-03-13 (commit: b6bea2a); Layer 3: L3-A ✅ ba9c804, L3-B ✅ 543a0c6, L3-C ✅ 1fc4f1a, L3-D ✅ 34fab6d — all RESOLVED 2026-04-17. ADR-0033 Layer 3 complete. | 2026-04-17 |
| T5-07-L3-A | ✅ RESOLVED 2026-04-14 — athletes table + owner seed + governance_outcomes owner backfill + calibrated_for removal; SCHEMA_VERSION 12→13; 8 new DB tests green | 2026-04-14 |
| T5-07-L3-B | ✅ RESOLVED 2026-04-17 — OutcomeTracker per-athlete query scoping; check_calibration_diversity(); get_calibration_analytics(); G-CI-07 AST gate; INV-04 ENFORCED; 11 new tests green | 2026-04-17 |
| T5-07-L3-C | ✅ RESOLVED 2026-04-17 (commit: 1fc4f1a) — cold-start protocol; is_athlete_cold_start(), check_and_exit_cold_start(), increment_cold_start_sessions(); coaching_pipeline() gate; 8 tests green | 2026-04-17 |
| T5-07-L3-D | ✅ RESOLVED 2026-04-17 (commit: 34fab6d) — all 6 adapter read methods accept athlete_id; ADR-0040 exemptions retired; 6 isolation tests green. ADR-0033 Layer 3 complete. | 2026-04-17 |
| T5-74 | ✅ RESOLVED 2026-04-14 — governance_outcomes.athlete_id confirmed in SQLite schema; explicit 'owner' fallback in both backends; v13 backfill; OBS-045 closed; bundled with T5-07-L3-A | 2026-04-14 |
| T5-08 | ✅ RESOLVED 2026-03-15 (via T5-08-B — ADR-0044 deliverables D1, D2a/b/c, D3, D4, D5, D7, D9 RESOLVED 2026-03-15; D6 was T5-08 pre-existing deliverable, not a T5-08-B implementation deliverable — DEC-015 2026-03-16; T5-08-B D8 closure record) | 2026-03-15 |
| T5-08-B | ✅ RESOLVED 2026-03-15 — D1 DONE (2026-03-08); D2a DONE (2026-03-13, commit: df449e7); D2b DONE (2026-03-13, commit: d7ad4b7); D2c DONE (2026-03-13, commit: f6901b6); D3 DONE (2026-03-13, commit: 6f641eb); D4 DONE (2026-03-13, commit: 4ccf36d); D5 DONE (2026-03-13, commit: ca8db90); D7 DONE (2026-03-15); D9 DONE (2026-03-15); **complete D2 finished**. D6 was a T5-08 pre-existing deliverable — not a T5-08-B implementation deliverable; D6 status not explicitly confirmed in T5-08-B closure record (DEC-015 2026-03-16: D6 functionally verified present in `persistence.py:122` + `database.py:1975`). | D1: 2026-03-08; D2a: 2026-03-13; D2b: 2026-03-13; D2c: 2026-03-13; D3: 2026-03-13; D4: 2026-03-13; D5: 2026-03-13; D7: 2026-03-15; D9: 2026-03-15 |
| T5-09 | ✅ RESOLVED 2026-03-16 — unified `get_athlete_context()` seam with JSON-safe payload + tests | 2026-03-16 |
| T5-10 | OPEN (deferred — Phase 10) | — |
| T5-11 | ✅ RESOLVED 2026-03-15 — JWT (RS256) + HTTP-only cookie auth layer; `auth_users` + `auth_tokens` tables; `get_current_user()` + `require_coach()` dependencies; isolation invariant enforced; Opus QA PASS; commit 3bd7147 | 2026-03-15 |
| T5-12 | ✅ VERIFIED COMPLETE 2026-04-26 — Pass 1 COMPLETE 2026-03-18; Pass 2 VERIFIED: O1–O7 implemented (b2cdc37 era); D4 → T5-100 (Phase 12) | 2026-04-26 |
| T5-100 | ✅ RESOLVED 2026-05-09 — BiometricRouter + ManualEntryAdapter; ADR-0055; HRV+RHR fallback wired in DailyCoach; 6 tests in tests/titan/integrations/test_biometric_router.py | 2026-05-09 |
| T5-101 | ✅ RESOLVED 2026-05-08 — token encryption (Fernet) already implemented; token path relocated to TITAN_DATA_DIR; legacy-root warning added; 4 tests in tests/test_t5_101_garth_encryption.py | 2026-05-08 |
| T5-102 | ✅ IMPLEMENTED 2026-05-01 — validate_jwt_keys_at_startup() added to auth.py; conditional call in __main__.py; 3 tests added to test_auth.py | 2026-05-01 |
| T5-103 | 🟡 OPEN — Phase 13 (OutcomeTracker → ThresholdAdapter calibration loop wiring; ADR-0052; P2) | — |
| T5-104 | 🟡 OPEN — Phase 13 (PersistenceAdapter ABC: wire OutcomeTracker consumer; ADR-0044; P2) | — |
| T5-105 | ✅ IMPLEMENTED 2026-05-01 — ruff-phase-a: removed continue-on-error, renamed to "Ruff Gate 1 (full repo)", scope expanded to .; blocking | 2026-05-01 |
| T5-106 | ✅ IMPLEMENTED 2026-05-01 — 12 ADR stubs created; 0024/0040 have real content; docs/adr/ now has 48 files (no gaps 0006–0052) | 2026-05-01 |
| T5-107 | ✅ IMPLEMENTED 2026-05-01 — CLAUDE.md lock-code list expanded to all 15 CANONICAL_LOCK_CODES | 2026-05-01 |
| T5-108 | ✅ IMPLEMENTED 2026-05-01 — CLAUDE.md line 238 DailyCoach v5.7 → v5.8 | 2026-05-01 |
| T5-109 | ✅ IMPLEMENTED 2026-05-01 — CLAUDE.md lines 65 and 229 science module count 27/26 → 31 | 2026-05-01 |
| T5-110 | ✅ RESOLVED 2026-05-04 — ADR-0054; coach_athlete_assignments table + RBAC enforcement stubs; commit 44986cb | — |
| T5-111 | ✅ RESOLVED 2026-05-08 — coach_audit_log persisted to SQLite; log_coach_action() + get_coach_audit_log() + get_table_names(); SCHEMA_VERSION 17; 4 tests; survives process restart | 2026-05-08 |
| D2-freeze | ✅ RESOLVED 2026-05-08 — Alembic freeze documented; alembic/README_FREEZE.md + env.py FREEZE NOTICE + CI guard + ADR-0044 D2-freeze note; baseline migration deferred to Phase 8A per ADR-0044 | 2026-05-08 |
| T5-112 | ✅ RESOLVED 2026-05-08 — CSRFMiddleware double-submit; /api/csrf-token endpoint; /health + /auth/login exempt; 5 tests in test_csrf.py | 2026-05-08 |
| T5-113 | 🟡 OPEN — Phase 13 (S-06 JWT missing iss/aud claims; LOW) | — |
| T5-114 | ✅ RESOLVED — Phase 13 (Data-void governance rule; all stages complete 2026-05-03) | — |
| T5-115 | ✅ RESOLVED — Phase 13 (data_source column; SCHEMA_VERSION 15; migration + UPSERT guard 2026-05-03) | — |
| T5-116 | ✅ RESOLVED — Phase 13 (/manual_entry Telegram command; 8 tests; data_source='manual_entry' 2026-05-03) | — |
| T5-117 | ✅ RESOLVED — PR #911 one profile source (max HR default 191); PR #970 `DailyCoach(athlete_profile=...)` takes the object in worker and console, the worker's Sunday plan reuses it (D-033). The console menus keep reading `to_context()`, a projection of the same object | 2026-10-09 |
| T5-118 | ✅ RESOLVED — Phase 13 (Garmin weight sync dual-format fix; dateWeightList primary + dailyWeightSummaries fallback; WARNING on unknown format; 4 tests; 2026-05-03) | — |
| T5-119 | ✅ RESOLVED — Phase 13 (Profile editor in menu; _save_athlete_profile_to_env; validation; 6 tests; 2026-05-04) | — |
| T5-13 | ✅ RESOLVED 2026-03-16 — coach audit trail + migration + non-bypassable middleware path | 2026-03-16 |
| T5-16 | ✅ RESOLVED — ADR-0046 accepted; T5-16-A implementation entry created | 2026-03-08 |
| T5-16-A | ⚠️ PARTIALLY RESOLVED 2026-03-15 — ADR-0018 Phase B complete; `coaching_pipeline.py` + `AthleteCoachingContext` + `CoachingScheduler` absent; see T5-16-B | 2026-03-15 |
| T5-16-B | ✅ RESOLVED 2026-03-17 — coaching_pipeline.py + coaching_scheduler.py extracted; DailyCoach delegates; state isolation oracle green; 2008 tests | 2026-03-17 |
| T5-17 | ✅ RESOLVED (Phase 8 — ACWR threshold extraction to thresholds.py; separate PR) | 2026-03-14 |
| T5-18 | ✅ RESOLVED (Phase 8 — Adaptive Memory 1.08 + time windows extraction; scope respected: 1.08 + 24/36/48/72 only; Category B 2.5/2.0/1.5 left inline per T5-19) | 2026-03-14 |
| T5-19 | ✅ CLOSED — NO_ACTION (2026-03-14): 2.5/2.0/1.5 confirmed Category B; remain inline; T5-18 unblocked | 2026-03-14 |
| T5-20 | ✅ RESOLVED | 2026-03-14 |
| T5-21 | ✅ RESOLVED (Phase 8 — Athlete Profile athlete_id uniqueness hardening; test-first) | 2026-03-14 |
| T5-22 | ✅ RESOLVED (Phase 8 — Athlete Profile serialization completeness incl guardrails + CS/D'; test-first) | 2026-03-14 |
| T5-23 | ✅ RESOLVED (Phase 8 — AFI no-HRR range docstring correction; formula unchanged) | 2026-03-14 |
| T5-24 | ✅ RESOLVED (BiomechanicsEngineProtocol in contracts.py; call-site audit complete; brief issued 2026-03-14) | 2026-03-14 (commit: ed1e20a) |
| T5-25 | ✅ RESOLVED 2026-03-15 — `docs/PARITY_MATRIX.md` v1.0 created; 32 methods classified; D7/D9 closure gates defined | 2026-03-15 |
| T5-26 | ✅ RESOLVED | 2026-03-14 |
| T5-27 | ✅ RESOLVED (Phase 8 — Durability Engine Category A threshold extraction to thresholds.py; separate PR scope) | 2026-03-14 |
| T5-28 | ✅ RESOLVED (Phase 8 — Fatigue Engine soreness threshold extraction to thresholds.py; separate PR) | 2026-03-14 |
| T5-29 | ✅ RESOLVED (Phase 8 — Garmin sync sleep/HRV partial-failure policy aligned; test-first) | 2026-03-14 |
| T5-30 | ✅ RESOLVED (Phase 8 — Governance Engine Category A threshold extraction to thresholds.py; separate PR) | 2026-03-14 |
| T5-31 | ✅ RESOLVED | 2026-03-14 |
| T5-32 | ✅ RESOLVED (Phase 8 — Lactate Logic threshold extraction; separate PR) | 2026-03-14 |
| T5-33 | ✅ CLOSED — NO_ACTION | 2026-03-14 |
| T5-34 | ✅ RESOLVED | 2026-03-14 |
| T5-35 | ✅ RESOLVED | 2026-03-14 |
| T5-36 | ✅ RESOLVED (P2 Phase 8B — authenticated per-role/per-user rate limiting implemented) | 2026-03-15 |
| T5-37 | ✅ RESOLVED (P1 — Opus Category A findings → CI gates; ADR-0049 Hybrid Sequential lane completed; Migration UNIT 1/2/3/4 CLOSED; progress 4/4) | 2026-03-15 |
| T5-38 | ✅ RESOLVED (P1 — validating meta-tests for each T5-37 CI gate; paired lane complete; Migration UNIT 1/2/3/4 CLOSED; progress 4/4) | 2026-03-15 |
| T5-39 | ✅ RESOLVED (P3 — Category A: `cs_min_confidence = 0.70` in `adaptive_priority_lock.py` → import `GOVERNANCE_CS_CONFIDENCE_THRESHOLD`; phase overrides remain inline per DEC-020) | 2026-03-17 |
| T5-40 | ✅ RESOLVED (P3 — `TelegramChannel.send()` boolean return consumed and propagated; `False`-without-exception branch has explicit test coverage; all gates green) | 2026-03-17 |
| T5-41 | ✅ RESOLVED (P3 — Category A: dew-point decision band literals in `weather_api.py`:158–170, 529–537 → extract to `thresholds.py` named constants) | 2026-03-17 |
| T5-42 | ✅ RESOLVED (P3 — `NutritionOptimizer` public API test coverage gap: `add_weight_entry()` and `calculate_daily_nutrition()` now have explicit happy-path + boundary tests; all gates green) | 2026-03-17 |
| T5-43 | ✅ RESOLVED 2026-03-17 — withings-sync pinned to 4.1.0 in constraints.txt; all 10 test files collectable; 1999 tests green | 2026-03-17 |
| T5-44 | ✅ RESOLVED 2026-03-28 — TRIMP zone calculation uses athlete HRmax; DailyCoach wiring complete (PRs #547, #548) | 2026-03-28 |
| T5-45 | ✅ RESOLVED 2026-03-27 — `HRVEngine.calculate_baseline` uses sample SD (N-1); ~8% suppression-threshold underestimation eliminated (PR #537) | 2026-03-27 |
| T5-46 | ✅ RESOLVED 2026-03-27 — HRV log deduplicates by timestamp at ingestion; baseline inflation from overlapping syncs eliminated (PR #538) | 2026-03-27 |
| T5-47 | ✅ RESOLVED 2026-03-26 — `EfficiencyEngine` returns `None` for zero/null pace; crash path eliminated (PR #526, commit 52537ed) | 2026-03-26 |
| T5-48 | ✅ RESOLVED 2026-03-28 — Garmin data age propagated to governance context and all gate events; timeout path bug fixed (PR #548) | 2026-03-28 |
| T5-49 | ✅ RESOLVED 2026-03-27 — Governance defaults missing sleep/readiness to 40 (conservative); 2-of-4 gate fires correctly on absent data (PR #535) | 2026-03-27 |
| T5-50 | ✅ RESOLVED 2026-03-27 — `sync_activities()` maps Garmin activity type to `session_type`; hardcoded `'EASY'` default eliminated (PR #539) | 2026-03-27 |
| T5-51 | ✅ RESOLVED 2026-03-26 — ACWR propagates `None` on sync failure; governance pipeline no longer sees optimistic sweet-spot (PR #530, commit 5f68fc5) | 2026-03-26 |
| T5-52 | ✅ RESOLVED 2026-03-26 — CS confidence default changed to 0.0; `CS_CONFIDENCE_LOCK` now fires for uncalibrated trackers (PR #529, commit 19f9a1d) | 2026-03-26 |
| T5-53 | ✅ RESOLVED 2026-03-26 — `ReadinessEngine` null-guards HRV diff; skips HRV component gracefully when either value is `None` (PR #527, commit 0d9f852) | 2026-03-26 |
| T5-54 | ✅ RESOLVED 2026-03-27 — drift_pct default changed from 0.0 to None; IntensityGovernor now treats missing drift as unknown not perfect efficiency (PR #541) | 2026-03-27 |
| T5-55 | ✅ RESOLVED 2026-03-27 — `apply_thermal()` now uses ESI formula (temp + 0.5*dew_point) when dew_point available; falls back to dry-bulb when absent (PR #544) | 2026-03-27 |
| T5-56 | ✅ RESOLVED 2026-03-27 — AFI confidence penalised to 0.7 when HRR history has fewer than 3 data points; absent HRR (None) carries no penalty (PR #542) | 2026-03-27 |
| T5-57 | ✅ RESOLVED 2026-03-27 — `should_replan()` predicate added; mid-week re-evaluation triggers on HRV drop >10ms, HARD_STOP event ≤24h, or illness flag (PR #545) | 2026-03-27 |
| T5-58 | ✅ RESOLVED 2026-03-26 — `_apply_hrv_adjustments` uses explicit `is not None` guards; crash path on null HRV eliminated (PR #528, commit d0dbd67) | 2026-03-26 |
| T5-59 | ✅ RESOLVED 2026-03-27 — `NutritionOptimizer` defaults `dew_point` to 25°C (conservative); sweat/electrolyte underestimation eliminated (PR #536) | 2026-03-27 |
| T5-60 | ✅ RESOLVED 2026-03-28 — sleep field mapping fixed; H3 gate restored (PR #552) | 2026-03-28 |
| T5-61 | ✅ RESOLVED 2026-03-28 — multi-day HRV persisted; INSERT OR IGNORE for historical (PR #553) | 2026-03-28 |
| T5-62 | ✅ RESOLVED 2026-03-28 — zero-sync silent failure fixed; stale token + empty sync detection (PR #551) | 2026-03-28 |
| T5-65 | ✅ RESOLVED 2026-03-29 — classify_hrv_stress_context returns UNKNOWN_ACWR for None/absent/unparseable ACWR; confirmed ADR-0051 compliant by architect 2026-03-29 | 2026-03-29 |
| T5-66 | ✅ RESOLVED 2026-03-29 — per-column UPSERT preserves mood/soreness/fatigue/notes on Garmin re-sync; 5 tests green | 2026-03-29 |
| T5-67 | ✅ RESOLVED 2026-04-04 — boolean flag gates success events in all 4 sync methods; 12 tests green | 2026-04-04 |
| HD-07 | ✅ RESOLVED 2026-04-04 — _activity_utc_date() replaces [:10] truncation; fromisoformat()+UTC for tz-aware timestamps; 10 tests green | 2026-04-04 |
| HD-01 | ✅ RESOLVED 2026-04-04 — check_baseline_drift() in HRVGuidedEngine; emits hrv_baseline_drift_warning; 8 tests green | 2026-04-04 |
| HD-02 | ✅ RESOLVED 2026-04-04 — database.py:1405,1843 UTC fix; fromisoformat()+UTC for tz-aware timestamps | 2026-04-04 |
| HD-03 | ✅ RESOLVED 2026-04-04 — H5/FUELING/INTENSITY NaN guards; ADR-0009; 3 new tests green | 2026-04-04 |
| HD-04 | N/A — slot intentionally unassigned (non-sequential HD numbering confirmed 2026-04-20) | — |
| HD-06 | ✅ RESOLVED 2026-04-04 — DegradedModeTracker persists to degraded_mode_state table; hydrates on startup; 9 tests green | 2026-04-04 |
| T5-70 | ✅ RESOLVED 2026-04-04 — AuthStore wired to SQLite via DatabaseManager; bcrypt/JWT unchanged; 19 tests green | 2026-04-04 |
| HD-05 | ✅ RESOLVED 2026-04-04 — RATE_LIMITER_MAX_KEYS=10000; LRU eviction; limiter_eviction WARNING event; 6 tests green | 2026-04-04 |
| HD-08 | ✅ RESOLVED 2026-04-04 — data_confidence_low=True when persistence_degraded; silent no-op WARNING events; 8 tests green | 2026-04-04 |
| T5-68 | ✅ RESOLVED 2026-03-29 — ESI_DEW_POINT_FALLBACK_C=18.0 in thresholds.py+evidence_registry; daily_coach.py:714 uses constant; ADR-0034 annotated; 6 tests green | 2026-03-29 |
| T5-69 | ✅ RESOLVED 2026-03-29 — activityId extracted; garmin_activity_id column + unique index via staged migration; INSERT OR IGNORE deduplication; record restored after merge conflict; Stage 3 merged PR #572 2026-03-29; NOT NULL constraint conditional (NULL rows skipped — manual sessions by design) | 2026-03-29 |
| ADR-0018 Phase B (G9) | ✅ IMPLEMENTED — G9 cleared | 2026-03-08 (commit: c51e217) |
| HD-09 | ✅ RESOLVED 2026-04-12 — ThresholdAdapter MODULE_VERSION 1.0.0; athlete_threshold_offsets schema v12; GovernanceEngine._get_soft_threshold() injection; ADR-0052 constants; 42 tests green | 2026-04-12 |
| T5-75 | ✅ RESOLVED 2026-04-12 — AST structural invariant: single _decision_pipeline call site + gate-method reachability; 2 tests green (commit: 29fcc49) | 2026-04-12 |
| T5-76 | ✅ RESOLVED 2026-04-12 — Concurrent coaching_pipeline() no cross-contamination test; ADR-0046 entry gate satisfied (commit: 29fcc49) | 2026-04-12 |
| T5-77 | ✅ RESOLVED 2026-04-12 — SIGTERM mid-pipeline: 3 tests confirm no orphaned governance trace (commit: 29fcc49) | 2026-04-12 |
| T5-78 | ✅ RESOLVED 2026-04-14 (commit: 11201df) — garminconnect upgraded 0.2.13→0.3.2; withings-sync dep removed; garmin_sync.py loads/dumps call sites updated; 0 collection errors | 2026-04-14 |
| T5-72 | ✅ RESOLVED 2026-04-17 — H2/H3 except: EASY ceiling + DATA_MISSING_CONSERVATIVE_H2/H3 lock codes; 2 tests green | 2026-04-17 |
| T5-73 | ✅ RESOLVED 2026-04-17 — PostgreSQLDatabaseManager.save_session() ON CONFLICT (garmin_activity_id) DO NOTHING confirmed present; source inspection test added | 2026-04-17 |
| T5-79 | ✅ RESOLVED 2026-04-19 (commit: 0d54612) — 6 mirrored test files created; full_module_audit.sh 0 FAILs; snapshot updated to 2546 | 2026-04-19 |
| T5-80 | ✅ RESOLVED 2026-04-19 (commit: 590639e) — ADR-0040 annotations retired (ADR-0033-L3-D-RESOLVED); silent except:pass replaced with _log.debug() in persistence.py + data_sanity.py | 2026-04-19 |
| T5-81 | 🟡 OPEN — del athlete_id sentinel pattern in persistence.py:992,1070; LOW priority | — |
| T5-82 | ✅ RESOLVED 2026-05-24 — 32 naive datetime.now() calls fixed across 8 modules; semgrep 0 findings | 2026-05-24 |
| T5-83 | 🟡 OPEN — slow tests with real network calls (810s, 102s, 10s sleep); MEDIUM priority | — |
| T5-84 | ✅ IMPLEMENTED 2026-04-27 — `scripts/mutation_test_governance.sh`; `setup.cfg [mutmut]`; `mutmut==3.5.0` in requirements.txt; targeted H1-H5 gates only | 2026-04-27 |
| T5-85 | 🟡 OPEN — Phase 10 (stateful Hypothesis property-based testing) | — |
| T5-86 | 🟡 OPEN — Phase 10 (differential fuzzing SQLite vs PostgreSQL) | — |
| T5-87 | 🟡 OPEN — Phase 10 (metamorphic testing for physiological models) | — |
| T5-88 | ✅ IMPLEMENTED 2026-04-21 (scripts/flakiness_tracker.sh) | 2026-04-21 |
| T5-89 | 🟡 OPEN — Phase 10 (chaos engineering) | — |
| T5-90 | 🟡 OPEN — Phase 10 (TLA+ formal methods for governance gates) | — |
| T5-91 | ✅ IMPLEMENTED 2026-04-21 (.semgrep/titan_rules.yaml) | 2026-04-21 |
| T5-92 | 🟡 OPEN — Phase 10 (OPA/Rego policy-as-code) | — |
| T5-93 | ✅ IMPLEMENTED 2026-04-25 (.importlinter — 5 contracts; import-linter==2.11) | 2026-04-25 |
| T5-94 | ✅ IMPLEMENTED 2026-04-25 (tests/titan/api/test_schemathesis_contracts.py — 5 contract tests; schemathesis>=3.27) | 2026-04-25 |
| T5-95 | 🟡 OPEN — Phase 10 (Great Expectations for Garmin data quality) | — |
| T5-96 | ✅ IMPLEMENTED 2026-04-21 (scripts/gate_coverage_matrix.sh) | 2026-04-21 |
| T5-97 | ✅ IMPLEMENTED 2026-04-21 (scripts/phase_close_audit.sh) | 2026-04-21 |
| T5-98 | ✅ IMPLEMENTED 2026-04-24 (project venv + .venv/bin/pytest in CI scripts; 12 → 0 collection errors) | 2026-04-24 |

---

## Weekly Governance Log


### Friday Review — 2026-04-17
State: healthy
Learnings:
- ADR-0033 Layer 3 fully complete (L3-A through L3-D, four commits)
- T5-72 / T5-73 resolved; governance FAIL-OPEN gap closed
- scripts/hard_audit.sh created — replaces 14+ manual audit patterns
- setup_env.sh now auto-activates pyenv 3.11
Required updates: TECHNICAL_DEBT.md (this entry)
Next-week tactic: Run hard_audit.sh at session start instead of
manual checks. ADR-0052 Stage 3 (ThresholdAdapter wiring) is next.
Opus governance audit warranted after ADR-0052 Stage 3 closes Phase 9.

### Governance Note — 2026-04-18
State: healthy
Learnings:
- scripts/module_audit.sh + scripts/full_module_audit.sh created (Lane C implementation)
- Full audit: 51 modules PASS, 11 modules FAIL — no crashes, clean finding list produced
- Findings (not yet SCRATCHPAD OBS): ADR-0040 annotation in data_sanity.py; silent
  except:pass in data_sanity.py + persistence.py; missing mirrored tests for
  governance_contracts.py, ml_safety.py, adaptive_memory.py, biometric_source.py,
  thresholds.py, api/dependencies.py, api/models.py; unscoped SQL in database.py +
  physiological_bounds.py
- hard_audit.sh unmodified and still passes (module audit integration deferred — optional)
Required updates: TECHNICAL_DEBT.md (this entry)
Next-week tactic: Route each module_audit finding through SCRATCHPAD OBS before
scheduling fixes. Priority: silent except:pass items (persistence.py, data_sanity.py)
are highest-risk and smallest scope.

### Governance Note — 2026-05-15
State: healthy
Learnings:
- Phase 15 close audit: ALL GATES PASS — A through P, 2764 tests, coverage 94%, SCRATCHPAD IDLE
- 9 P1 findings from Opus audit (2026-05-09) resolved within Phase 15; P15-D22 (Telegram MarkdownV2) deferred
- Phase 16 opened with 6 items: TD-09/13/17/19 (XS), TD-10 print() migration (M), TD-06 Dockerfile (M)
- Highest-severity open item entering Phase 16: F16-02 (Telegram replay, HIGH)
Required updates: TECHNICAL_DEBT.md (Phase 15 close + Phase 16 open), docs/ROADMAP.MD (phase table + sections), CLAUDE.md (ROADMAP.MD description)
Next-week tactic: Phase 16 execution begins with XS items (TD-09, TD-13, TD-19) to clear quick wins; TD-17 Telegram replay protection is the highest-priority S item.

---

---

### T5-81 · del athlete_id in persistence.py — pre-existing FP-08 pattern 🟡 OPEN

**Status:** OPEN — Phase 9 debt. Source: OBS-041-CI (2026-04-05), DEC from SCRATCHPAD.
**Severity:** LOW
**Location:** `titan/core/persistence.py:992, 1070`
**Description:** `del athlete_id` at two locations in persistence.py. These are pre-existing
sentinel deletion patterns (FP-08 — not data loss). G-CI-04 correctly flags them. Pattern is:
variable set, used, then deleted to signal "not available downstream". No data integrity risk;
naming clarity issue only.
**Fix direction:** Replace `del athlete_id` with explicit `athlete_id = None` or restructure to
avoid deletion. Add inline comment documenting intent.
**Priority:** LOW — no safety impact. Maintenance pass.
**Phase:** 9 maintenance (no phase boundary required).

---

### T5-83 · Slow tests with real network calls — no mock isolation 🟡 OPEN

**Status:** OPEN. Source: hard_audit.sh 2026-04-19.
**Severity:** MEDIUM (CI stability risk)
**Location:**
- `tests/test_phase4_slo_alerts.py:239` — 810s (GarminSync real network call)
- `tests/test_garmin_sync.py:420` — 102s (connect() retry loop without mock)
- `tests/titan/integrations/test_garmin_sync.py:854` — hardcoded `time.sleep(10)`
**Description:** Three tests issue real DNS/HTTPS calls or real sleeps without monkeypatching
the garminconnect library. Results in 13+ minute test runs and flaky CI under network
restrictions.
**Fix direction:** Monkeypatch `titan.integrations.garmin_sync.Garmin` before test execution,
or use existing conftest.py fixtures. Replace `time.sleep(10)` with parametrized timeout +
`sleep(0.1)`.
**Priority:** MEDIUM — affects CI wall-clock time significantly.
**Phase:** 9 maintenance.

---

## Opus Part D — State-of-the-Art Method Registrations (2026-04-21)

*Source: Opus Phase 9 Governance & Security Audit, Part D.*
*Items marked ✅ IMPLEMENTED were delivered in the same session.*
*Items marked 🟡 OPEN are tracked for future phases.*

### T5-85 · Stateful property-based testing (D-2) 🟡 OPEN

**Status:** OPEN — Phase 10.
**Method:** Hypothesis stateful testing for sequences of DailyCoach + Garmin sync operations.
**Rationale:** Current T4-23 tests are stateless. Stateful covers invariant drift across state transitions.
**Priority:** P3.

---

### T5-86 · Differential fuzzing SQLite vs PostgreSQL (D-3) 🟡 OPEN

**Status:** OPEN — Phase 10.
**Method:** Fuzz random valid inputs against both backends, compare outputs.
**Prerequisite:** ADR-0044 PostgreSQL migration complete.
**Priority:** P4.

---

### T5-87 · Metamorphic testing for physiological models (D-4) 🟡 OPEN

**Status:** OPEN — Phase 10.
**Method:** "If A→X then A+ε→X±δ" assertions for HRV engine, ACWR, critical speed.
**Rationale:** Catches silent regression in science engines where outputs are continuous.
**Priority:** P3.

---

### T5-89 · Chaos engineering (D-6) 🟡 OPEN

**Status:** OPEN — Phase 10 (requires production-like multi-athlete deployment).
**Method:** Netflix chaos-monkey pattern: random Garmin API kill, network latency injection, DB lock simulation.
**Priority:** P4.

---

### T5-90 · Formal methods TLA+ for governance gates (D-7) 🟡 OPEN

**Status:** OPEN — Phase 10.
**Method:** Model H1-H5, FUELING, INTENSITY, 2-of-4, VO2 gates in TLA+. Model checker verifies no input bypasses combined gates.
**Priority:** P2 (high safety value, high investment).

---

### T5-92 · Open Policy Agent / Rego (D-9) 🟡 OPEN

**Status:** OPEN — Phase 10.
**Method:** Policy-as-code for PILOT-01 applicability gate and complex governance rules.
**Priority:** P4.

---

### T5-95 · Great Expectations for Garmin data quality (D-12) 🟡 OPEN

**Status:** OPEN — Phase 10.
**Method:** Data contracts in YAML at Garmin boundary. Alert on distribution drift (ADR-0050 / ADR-0026).
**Priority:** P3.

---

### T5-103 · OutcomeTracker → ThresholdAdapter calibration loop wiring 🟡 OPEN

**Status:** 🟡 OPEN — Phase 13.
**Source:** Pre-upgrade architecture audit (2026-05-01), finding B2.
**Priority:** P2 (Medium — calibration DB fills but thresholds never move; ADR-0052 closed-loop contract broken).

**Scope:** Either (a) wire `OutcomeTracker.run_calibration_cycle()` to call `ThresholdAdapter.propose_adaptation()` from the DailyCoach orchestrator, or (b) add `# TODO(phase-13): wiring deferred` marker referencing ADR-0052 and update ADR-0052 status to reflect the deferral explicitly. Option (a) preferred.

**Acceptance criteria:** `run_calibration_cycle()` produces at least one `ThresholdAdapter.propose_adaptation()` call in integration test with synthetic outcome data; or ADR-0052 explicitly states the loop is deferred with a phase target.

**Location:** `titan/science/outcome_tracker.py:737`, `titan/science/threshold_adapter.py`.

---

### T5-104 · PersistenceAdapter ABC: wire at least one consumer 🟡 OPEN

**Status:** 🟡 OPEN — Phase 13 (blocked: Phase 8A entry gate).
**Source:** Pre-upgrade architecture audit (2026-05-01), finding B1. ADR-0044.
**Priority:** P2 (Medium — ADR-0044 Phase 8A contract is unproven; PostgreSQL migration is theoretical until at least one path routes through the adapter).

**Scope:** Migrate `OutcomeTracker` (narrowest read surface) to route all DB calls through `PersistenceAdapter` rather than `DatabaseManager` directly. Validate that the existing 64 APL integration tests still pass. Do not migrate other modules in this task.

**Acceptance criteria:** `OutcomeTracker.__init__` accepts a `PersistenceAdapter` instance; `DatabaseManager` is not imported directly in `outcome_tracker.py`; existing test suite passes.

**Location:** `titan/core/persistence.py:141-405`, `titan/science/outcome_tracker.py`.

---

### T5-113 · S-06 JWT missing iss/aud claims 🟡 OPEN

**Status:** 🟡 OPEN — Phase 13.
**Source:** FMEA Phase 13 security audit (2026-05-02), finding S-06.
**Priority:** P3 (Low — defence-in-depth; no active exploit path).

**Scope:** Add `iss` (issuer) and `aud` (audience) claims to all issued JWTs; validate both on decode. This prevents token reuse across services/environments.

**Acceptance criteria:** Decoded JWTs contain `iss="titan-os"` and `aud="titan-api"`; validation rejects tokens with wrong/missing claims.

**Location:** `titan/api/auth.py` (or equivalent JWT issuance path).

---

### T5-117 · Two parallel athlete profile systems (architectural debt) ✅ RESOLVED

**Status:** ✅ RESOLVED 2026-10-09 (PR #970, D-033). Originally 🟡 OPEN — Phase 13.
**Source:** Profile unification audit (2026-05-02).
**Priority:** MEDIUM (workaround: .env vars override canonical defaults as of this commit).

**Scope:** `titan/main.py` constructs `athlete_profile` dict from env vars independently of `UniversalAthleteProfile`. The two systems carry overlapping state (age, max_hr, threshold_hr, weight_kg, height_cm) with no synchronisation. Goal: Phase 13 unifies both into a single source of truth so the coaching pipeline always reads from `UniversalAthleteProfile`.

**ADR required:** Yes — architectural unification touches orchestration contracts and DB schema.

**Acceptance criteria:** `titan/main.py` Step 5 removed; `DailyCoach` and all downstream consumers read `UniversalAthleteProfile` directly; no duplicate profile dict in `TitanContext`.

**Location:** `titan/main.py`, `titan/core/athlete.py`, `titan/orchestration/contracts.py`, `titan/orchestration/daily_coach.py`.

**Progress 2026-10-07 (PR #911):** the Docker worker read `ATHLETE_MAX_HR` from `TitanSettings` (default 160) while the console read `UniversalAthleteProfile.from_env()` (default 191), so TRIMP differed by where it ran when the variable was unset. The worker now uses the profile too, `TitanSettings.ATHLETE_MAX_HR` is removed, and Zaf chose 191 as the one default. `TitanContext.athlete_profile` is built only by `UniversalAthleteProfile.to_context()`. No schema change, so no ADR. Still open: DailyCoach and downstream consumers take the context dict / `athlete_max_hr`, not the profile object.

**Resolved 2026-10-09 (PR #970, D-033):** `DailyCoach` takes `athlete_profile=` (the `UniversalAthleteProfile` object) from both composition roots (`titan/worker/__init__.py`, `titan/main.py`) and reads max HR from it; passing a different `athlete_max_hr` raises `ValueError`. The worker's Sunday plan uses `coach.athlete_profile` instead of a second `from_env()`. `TitanContext.athlete_profile` stays as the `to_context()` projection for the console menus: it is built from the same object, so it carries no values of its own. No schema change, so no ADR.

---

## Production Readiness Audit 2026-05-15 — Open Findings Register

> Source: Production Readiness Audit 2026-05-15.
> Items TD-01, TD-03, TD-05, TD-18, TD-20 resolved in first pass (branch `claude/implement-type-records-bundling-zS1yD`).
> TD-02 partially resolved in second pass (branch `claude/fix-drift-reader-lock-QPjeo`): 4 key read methods protected by RLock; full coverage deferred Phase 16.
> CI drift treadmill fixed in second pass: dependency-drift-audit job now uses CVE-only gate (pip-audit) instead of patch-version staleness check.
> Items TD-04 through TD-19 (excluding resolved items) tracked as Phase 16 open findings.

### Resolved in this pass

| ID | Finding | Status |
|---|---|---|
| TD-01 | RBAC flat-trust: COACH role bypassed assignment check entirely — `require_athlete_access` returned without verifying coach→athlete assignment | ✅ RESOLVED |
| TD-03 | Override lockdown fails open on cold start: `get_override_ratio()` returning `None` fell through to `float(None)` → `TypeError` → `_fail_safe` with error context; now explicit cold-start default-deny path | ✅ RESOLVED |
| TD-05 | Morning routine dedup race: `thread.is_alive()` check had a TOCTOU window where two concurrent callers could both pass before the first thread registered; replaced with non-blocking `threading.Lock` acquire | ✅ RESOLVED |
| TD-18 | Garmin token plaintext default in production: missing `TITAN_GARTH_TOKEN_KEY` silently stored token unencrypted; now raises `RuntimeError` in prod, degrades gracefully with warning in dev/test | ✅ RESOLVED |
| TD-20 | No CODEOWNERS file: architecture-critical paths had no required-reviewer enforcement | ✅ RESOLVED |
| TD-02 | SQLite unprotected reads: 4 highest-risk read methods (get_training_load_history, get_ctl_atl_tsb, get_override_ratio, get_baseline_rhr) confirmed under RLock; concurrent read+write test added; full-method coverage deferred Phase 16 | ✅ RESOLVED (partial) |

### Resolved in Phase 16 (CLOSED 2026-05-15)

| ID | Finding | Status |
|---|---|---|
| TD-09 | coach_audit_log not written | ✅ RESOLVED 2026-05-15 — `_get_user_from_request` now passes `"access"` to `decode_token`; `_audit_request` uses returned `TokenPayload.sub` for DB write |
| TD-13 | Threshold mirrors | ✅ RESOLVED 2026-05-15 — dew-point literals (18, 15) in nutrition_optimizer eliminated by weight-based hydration rewrite; governance_engine.py already imported all Category A constants |
| TD-17 | Telegram replay protection | ✅ RESOLVED 2026-05-15 — nonce-based one-time override confirmation; `_create_override_nonce` / `_consume_override_nonce` in telegram_bot.py; 5-min TTL; 5 replay tests in tests/test_td17_replay.py |
| TD-19 | Gitleaks allowlist too broad | ✅ RESOLVED 2026-05-15 — converted from path-based (`paths = [...]`) to regex-based patterns covering only known test fixture shapes |
| TD-10 | 172 print() calls | ✅ RESOLVED (partial) 2026-05-15 |

### Closed — Phase 17 (2026-05-22)

| ID | Finding | Status |
|---|---|---|
| TD-CTL-01 | TSBEngine `daily_loads` empty at UI render despite 15 rows in DB. All pipeline components verified: `get_training_load_history(42)` returns 15 rows, hydration code correct, no exceptions raised. Root cause: `get_training_load_history()` was returning per-activity rows without GROUP BY date — multiple rows per day caused silent deduplication/ordering failures downstream. Per-day aggregation (SUM + GROUP BY) fixed in PR #719. The multiple hydration/ordering fixes (#698–#712) were chasing symptoms. Added: 2026-05-20. | ✅ RESOLVED 2026-05-22 |
| TD-02 | SQLite unprotected reads | ✅ RESOLVED (partial — 4 key read methods locked; full coverage deferred Phase 17) |
| TD-04 | DailyCoach god-orchestrator | OPEN — carries to Phase 18 (ADR-0057 required) |
| TD-06 | No deployable artifact | ✅ RESOLVED 2026-05-15 — Dockerfile (two-stage, non-root), docker-compose.yml, .dockerignore, docs/DOCKER_SETUP.md; 5 existence tests in tests/test_td06_dockerfile.py |
| TD-07 | CodeQL upload disabled | MED — deferred |
| TD-08 | Schema in two places | DEFERRED to Phase 19 — 500+ lines of CREATE TABLE SQL span create_tables() and v1–v21 migrations; extraction without alembic support is Phase 19 scope (MED) |
| TD-11 | No metrics export | ✅ RESOLVED 2026-05-23 — MetricsCollector in titan/observability/metrics.py; 3 sites wired (ctl_recompute_ms histogram, garmin_sync_success counter, api_startup counter); Phase 19: plug-in OTel exporter |
| TD-12 | Runbooks missing | ✅ RESOLVED 2026-05-15 — 3 SLO-referenced runbooks authored: garmin-sync-failure.md, governance-hard-stop-unexpected.md, database-recovery.md (all with Symptoms / Diagnosis / Recovery / Escalation sections) |
| TD-14 | Persistence ABC unused | LOW — deferred |
| TD-15 | No load/perf tests | MED — deferred |
| TD-16 | No DB corruption recovery test | MED — deferred |
| TD-NUTRITION-01 | Carb display inconsistency when `low_carb` dietary style active: "Carbs: 375-525g (224.0 g)" — range shows generic band instead of `dietary_style`-adjusted target. Added: 2026-05-22. | ✅ RESOLVED 2026-05-23 — `carbs_range` now computed as ±15% of actual `carbs_g` (PR #720). Range is always consistent with the dietary-style-adjusted target regardless of Burke defaults. |

---

## Opus Audit 2026-05-22 — Phase 18 Open Findings

> Source: Opus architectural audit 2026-05-22 (pre-Phase 18 entry gate review).
> Items marked FIXED were resolved in the same pass (branch `claude/tender-curie-dGPEi`).
> Items marked OPEN carry to Phase 18 backlog.

### Resolved in this pass (Opus audit 2026-05-22)

| ID | Title | Severity | Status |
|---|---|---|---|
| TD-B7 | numpy removed — was unused dep (Opus audit B7, 2026-05-22) | LOW | ✅ RESOLVED 2026-05-22 — removed numpy==2.4.4 from requirements.txt; 0 import usages confirmed |

### Open Findings — Phase 18

| ID | Title | Severity | Source | Status |
|---|---|---|---|---|
| TD-NEW-01 | Override ratio cold-start dead code: `get_override_ratio` returned `round(overrides/days)` even when governance_outcomes table empty — misleading non-None result masking cold-start | HIGH | Opus audit 2026-05-22 (B1) | ✅ FIXED — added governance_outcomes count guard; returns None on cold-start |
| TD-NEW-02 | RBAC bypass in athlete dashboard route: `/athletes/{id}/dashboard` called `require_athlete_access` as plain function without `request`, causing `db=None` → coach assignment check silently skipped | HIGH | Opus audit 2026-05-22 (B2) | ✅ FIXED — route now uses `Depends(require_coach_athlete_access)` |
| TD-NEW-03 | PostgreSQL backend enabled without production readiness: `get_database_manager(backend='postgres')` silently constructed PostgreSQLDatabaseManager despite ADR-0044 parity not complete | HIGH | Opus audit 2026-05-22 (B3) | ✅ FIXED — raises NotImplementedError with ADR-0044 citation |
| TD-NEW-04 | Docker ENTRYPOINT points to TUI: container launches interactive menu instead of API server; FastAPI not reachable from container | HIGH | Opus audit 2026-05-22 (B4) | OPEN — ADR-0057 stub created; architect decision pending |
| TD-NEW-05 | constraints.txt empty but referenced in CI: `pip install -c constraints.txt` on empty file adds no value and risks pip version mismatches | LOW | Opus audit 2026-05-22 (B5) | ✅ FIXED — deleted constraints.txt; removed `-c constraints.txt` from ci.yml |
| TD-NEW-06 | Misleading ML model labels: `LSTM_SHADOW_BASELINE` and `RF_GB_ENSEMBLE_BASELINE` imply deep-learning models but code is pure EWMA/heuristic — misleads audit consumers | MED | Opus audit 2026-05-22 (B6) | ✅ FIXED — renamed to `EWMA_LOAD_PROXY_v1` and `HEURISTIC_RISK_PROXY_v1` |
| TD-NEW-07 | Unused numpy dependency: numpy==2.4.4 listed in requirements.txt with 0 import sites in titan/ | LOW | Opus audit 2026-05-22 (B7) | ✅ FIXED — removed from requirements.txt |
| TD-NEW-08 | Dockerfile HEALTHCHECK references stale db name: `DatabaseManager('/data/titan.db')` instead of `titan_core.db` — healthcheck always fails in production | MED | Opus audit 2026-05-22 (B8) | ✅ FIXED — updated to `titan_core.db` |
| TD-NEW-09 | CodeQL SARIF upload disabled: `upload: never` in codeql.yml means security findings never reach GitHub Security tab | MED | Opus audit 2026-05-22 (B9) | ✅ FIXED — changed to `upload: always` |
| TD-NEW-10 | DailyCoach god-orchestrator (carries from Phase 17): 12-step pipeline in single class violates ADR-0018 kernel boundary | HIGH | Opus audit 2026-05-22 | ✅ RESOLVED 2026-05-24 — ADR-0058 Phase A: EngineRegistry extracted; Phase B (EffectBus) + Phase C (daemon) deferred Phase 20 |
| TD-NEW-11 | No metrics/observability export: no Prometheus or structured metrics endpoint; SLO compliance unverifiable externally | HIGH | Opus audit 2026-05-22 | ✅ RESOLVED 2026-05-23 — MetricsCollector (stdlib JSON logging); OTel exporter deferred Phase 19 |
| TD-NEW-12 | SQLite concurrent read coverage incomplete: only 4 of N read methods protected by RLock (partial from TD-02) | MED | Opus audit 2026-05-22 | ✅ RESOLVED 2026-05-24 — all get_/fetch_/load_ methods wrapped with RLock; concurrent read/write test + lock fitness function added |
| TD-NEW-13 | Schema definition split across database.py and alembic migrations: two sources of truth for table structure risk drift | MED | Opus audit 2026-05-22 | DEFERRED Phase 19 — aligns with TD-08; 500+ lines extraction scope; ADR-0044 resolution track |
| TD-NEW-14 | Persistence ABC interface drift: abstract method signatures in persistence.py don't match DatabaseManager signatures (e.g. get_override_ratio athlete_id param) | MED | Opus audit 2026-05-22 | ✅ RESOLVED 2026-05-24 — all 9 ABC/DM drifts fixed; replay_tsb + is_db_reachable added to ABC; signature drift fitness function added |
| TD-NEW-15 | No load/performance tests: no benchmarks for DailyCoach pipeline, DB reads under concurrent load, or API throughput | MED | Opus audit 2026-05-22 | ✅ RESOLVED 2026-05-24 — scripts/load_test.py (stdlib-only runner); scripts/load_test_runner.sh; 5 pytest tests in tests/test_td_new_15_load.py; DB concurrent stress 0 errors; DailyCoach hydration p95 < 500ms |
| TD-NEW-16 | No DB corruption recovery test: PRAGMA integrity_check path untested; backup restore untested end-to-end | MED | Opus audit 2026-05-22 | ✅ RESOLVED 2026-05-24 — check_integrity() added to DatabaseManager; 4 corruption/backup tests added |
| TD-NEW-17 | TSBEngine daily_loads empty at UI render (carries TD-CTL-01): state mutation between pipeline hydration and menu render unresolved | HIGH | Opus audit 2026-05-22 | OPEN — Phase 18 priority |
| TD-NEW-18 | PostgreSQL migrations (alembic) untested: psycopg2-binary and sqlalchemy in requirements but no CI path exercises the postgres migration path | MED | Opus audit 2026-05-22 | ✅ RESOLVED 2026-05-24 — Alembic chain integrity CI-gated (`alembic-integrity` job); single-head, ≥10-revision, 1-root, and freeze-notice enforced by 4 pytest tests in `tests/test_alembic_ci.py`; PG activation deferred to ADR-0044 |
| TD-NEW-19 | Nutrition carb display inconsistency (carries TD-NUTRITION-01): low_carb dietary style shows generic band instead of adjusted target in menu | LOW | Opus audit 2026-05-22 | OPEN — Phase 18 backlog |
| TD-CTL-02 | Four separate EMA implementations across codebase: `DatabaseManager.get_ctl_atl_tsb`, `PostgreSQLDatabaseManager.get_ctl_atl_tsb`, `TSBEngine`, and any future adapters all duplicate the Banister EMA loop. Should be consolidated into a single `compute_banister_ema(loads, decay_days)` utility (Opus §5.2). | MED | Opus §5.2 audit 2026-05-22 | ✅ RESOLVED 2026-05-23 — 4 EMA implementations consolidated into `compute_ctl_atl_tsb()` in `titan/science/tsb_engine.py`; all 3 DB backends delegate to it; fitness function in `tests/test_ema_kernel.py` enforces single canonical site |
| TD-CTL-03 | No replay harness for CTL/ATL/TSB: there is no test that replays a known historical load sequence and asserts exact CTL/ATL values at specific dates. Without a replay harness, algorithmic regressions (e.g. decay constant drift, date-window bugs) cannot be caught deterministically (Opus §5.2). | MED | Opus §5.2 audit 2026-05-22 | ✅ RESOLVED 2026-05-23 — `replay_tsb()` implemented in `titan/science/tsb_engine.py`; `DatabaseManager.replay_tsb()` delegates to it; 4 harness tests in `tests/test_replay_harness.py` |

---

## Phase 19 — Structured Debt & Scale (CLOSED, 2026-05-24)

**Phase 19 CLOSED — phase_close_audit.sh 19 exit 0; 2942 tests passing; TD-NEW-15 RESOLVED;
TD-04 RESOLVED; TD-NEW-10 RESOLVED; TD-08 DEFERRED Phase 20; TD-NEW-18 DEFERRED Phase 20.**

### Resolved in this pass (Phase 19, 2026-05-24)

| ID | Finding | Status |
|---|---|---|
| TD-NEW-15 | Load/performance tests: scripts/load_test.py (stdlib-only), scripts/load_test_runner.sh, tests/test_td_new_15_load.py (5 tests); DB concurrent stress 0 errors; DailyCoach hydration p95 < 500ms | ✅ RESOLVED 2026-05-24 |
| TD-04 | DailyCoach god-orchestrator split: ADR-0058 Phase A EngineRegistry extracted | ✅ RESOLVED 2026-05-24 (see TD-NEW-10) |
| TD-NEW-10 | DailyCoach god-orchestrator: ADR-0058 Phase A EngineRegistry; Phase B (EffectBus) + Phase C (daemon) deferred Phase 20 | ✅ RESOLVED 2026-05-24 |

### Deferred to Phase 20

| ID | Finding | Rationale |
|---|---|---|
| TD-08 / TD-NEW-13 | Schema single source of truth: 500+ lines extraction; requires ADR-0044 PostgreSQL parity path before alembic alignment is safe | DEFERRED Phase 20 — XL scope; ADR-0044 resolution track |
| TD-NEW-18 | PostgreSQL migrations (alembic) untested: no CI path exercises postgres migration | DEFERRED Phase 20 — blocked on ADR-0044 |

### FMEA: Phase 19

| ID | Failure mode | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| F19-01 | DailyCoach split regression: EngineRegistry refactor causes orchestration regression | MED | HIGH | ADR-0058 gate + fitness function + full test suite | ✅ MITIGATED — ADR-0058 Phase A validated; regression tests green |
| F19-02 | Schema extract migration risk: schema.py diverges from alembic causing migration failure | LOW | HIGH | DEFERRED — extraction deferred Phase 20 until ADR-0044 resolved | ⚠️ DEFERRED |
| F19-03 | OTel dep without ADR gate | LOW | MED | DEFERRED — OTel Phase 2 deferred pending ADR | ⚠️ DEFERRED |
| F19-04 | Load test SLO false negative: in-process DB test misses production latency profile | LOW | MED | Scripts runner (load_test_runner.sh) available for Docker-based validation | ✅ ACCEPTABLE |

## Phase 20 Scope (CLOSED, 2026-05-24)

Closed 2026-05-24 — phase_close_audit.sh 20 exit 0; 2955 tests passing.
Deferred to Phase 21: TD-08, TD-NEW-18, TD-04 Phase B, P15-ARCH5, T5-15.

1. TD-08: Schema single source of truth — extract CREATE TABLE into titan/core/schema.py (XL) — DEFERRED Phase 21
2. TD-04 Phase B: EffectBus extraction (ADR-0058 Phase B) — DEFERRED Phase 21
3. TD-NEW-18: Alembic CI path — PostgreSQL migration CI gate (ADR-0044 resolution track) — DEFERRED Phase 21
4. P15-ARCH5: pydantic-settings migration — DEFERRED Phase 21
5. T5-15: Pytest marker taxonomy (unit/integration/governance) — DEFERRED Phase 21

## FMEA: Phase 20 — Hygiene & Backup

**Architect:** Claude | **Date:** 2026-05-24 | **Status:** G12 SATISFIED

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F20-01 | Backup script | Permission denied on /data/backups | MED | chown titan:titan in Dockerfile ✅ |
| F20-02 | Worker backup | DB locked during backup | LOW | SQLite online backup API is lock-safe ✅ |
| F20-03 | Naive datetime | Clock skew in metrics | LOW | timezone.utc enforced ✅ |
| F20-04 | Postgres adapter | Called accidentally | LOW | NotImplementedError gate ✅ |

**G12 gate:** SATISFIED.

## Phase 21 Scope (CLOSED, 2026-05-24)

Entry gate: Phase 20 close audit PASS (2026-05-24). Scope: governance consolidation.

1. TD-08: Schema single source of truth — extract CREATE TABLE into titan/core/schema.py (XL)
2. TD-04 Phase B: EffectBus extraction (ADR-0058 Phase B)
3. TD-NEW-18: Alembic CI path — PostgreSQL migration CI gate (ADR-0044 resolution track)
4. P15-ARCH5: pydantic-settings migration
5. T5-15: Pytest marker taxonomy (unit/integration/governance)

---

## Opus Security/Ops Audit — 2026-05-24 (TR/C/H series)

### Resolved

| ID | Finding | Resolution | Status |
|----|---------|------------|--------|
| TR-01 | Worker container runs stub loop only (no real work) | `run_forever()` wired to `DailyCoach.run_morning_routine()` on 24h schedule; `worker_started` log event added | ✅ RESOLVED 2026-05-24 |
| TR-03 | Runbook references stale `titan.db` filename throughout | All occurrences replaced with `titan_core.db` in `docs/runbooks/database-recovery.md` | ✅ RESOLVED 2026-05-24 |
| TR-05 | `assert` used for DB path validation in `create_app()` — disabled in optimised Python | Replaced with `raise RuntimeError` (TR-07 duplicate; unified fix) | ✅ RESOLVED 2026-05-24 |
| TR-06 | Module-level `app = create_app()` creates a no-DB app on every import | Replaced with `app = None`; callers must use `create_app()` factory | ✅ RESOLVED 2026-05-24 |
| TR-07 | `assert "titan_core.db" in _db_path` stripped by `-O` flag | Replaced with `raise RuntimeError(...)` | ✅ RESOLVED 2026-05-24 |
| TR-11 | Smoke test `down -v` would destroy production volumes if run against wrong env | Production guard added: `TITAN_ENV=production` skips `-v` teardown | ✅ RESOLVED 2026-05-24 |
| C-1 | Worker stub loop provides no actual value; ADR-0057 unfulfilled | Worker wired to `DailyCoach`; 24h `threading.Event` sleep for clean SIGTERM exit | ✅ RESOLVED 2026-05-24 |
| C-3 | Runbook uses `titan.db` (stale filename) — ops following it would target wrong file | Fixed — all 8 occurrences corrected to `titan_core.db` | ✅ RESOLVED 2026-05-24 |
| C-5 | `docker_smoke_test.sh` calls `down -v` unconditionally — data-loss risk in prod | Production guard added before teardown | ✅ RESOLVED 2026-05-24 |
| C-6 | `app = create_app()` at module level instantiates app without DB on import | Replaced with `app = None` sentinel | ✅ RESOLVED 2026-05-24 |
| C-7 | No factory guard — `app` imported directly bypasses DB injection | Same fix as C-6; Dockerfile already uses `create_app(db=...)` pattern | ✅ RESOLVED 2026-05-24 |
| H-3 | Audit DB persist failure silently swallowed; no metric emitted | `except` block now calls `get_metrics().counter("audit_write_failure")` and logs at ERROR with `exc_info` | ✅ RESOLVED 2026-05-24 |
| H-8 | `/readyz` calls `_db.conn.execute("PRAGMA user_version")` directly — bypasses `_lock` | Removed direct `conn` access; `is_db_reachable()` (lock-safe) covers liveness check | ✅ RESOLVED 2026-05-24 |

| TR-10 | `datetime.utcnow()` in `titan/observability/metrics.py` and `titan/integrations/notification_gateway.py` — deprecated API, naive UTC | Replaced with `datetime.now(timezone.utc)` in both files | ✅ RESOLVED 2026-05-24 |
| TR-16 | CI `|| true` on `system_check.py` silences module-health failures | Retained as informational (pytest suite is the real gate); added comment clarifying intent; pylint/vulture advisory `|| true` retained by design | ✅ RESOLVED 2026-05-24 |
| TR-17 | `.semgrep/titan_rules.yaml` existed but was not wired to CI | Added `semgrep` job to `.github/workflows/ci.yml`; exits non-zero on ERROR-severity findings; zero ERROR findings confirmed locally | ✅ RESOLVED 2026-05-24 |
| TR-18 | Dockerfile ran all containers as root | Added `titan` non-root user in base stage; `USER titan` in api and worker stages; `/data` and `/app/Documents/TITAN` chowned to `titan` | ✅ RESOLVED 2026-05-24 |

### Deferred

| ID | Finding | Rationale |
|----|---------|-----------|
| TR-09 | No integration test for worker boot-to-first-cycle | Requires Docker test harness; deferred to Phase 20 ops hardening track |
| TR-12 | Worker has no graceful SIGTERM handler beyond `threading.Event` unblock | Acceptable for Phase 20; SIGTERM exits the process naturally via Python default handler |
| TR-13 | `create_app()` `auth_store` / `audit_store` still instantiated without DB in test mode | Low risk — test mode uses `:memory:`; deferred until pydantic-settings migration (P15-ARCH5) |
| TR-15 | Smoke test worker validation is advisory (`⚠️ WARN`) not hard fail | Intentional — worker log timing is non-deterministic in CI; hard fail deferred pending structured wait |
| TR-19 | PostgreSQL adapter (`PostgreSQLAdapter`, `PostgreSQLDatabaseManager`) unused in all production paths; `TITAN_DB_BACKEND=postgres` raises `NotImplementedError`. Tracked as Opus TR-13 (2026-05-24). | Explicitly marked unmaintained with module header comment. `test_postgres_backend_raises` test added. ADR-0044 parity required before activation; deferred Phase 8A. |

---

## Phase 21 Security / Hygiene Delivery (2026-05-24)

Items identified by Opus Phase 20 audit, resolved in Phase 21.

### Resolved

| ID | Finding | Resolution | Status |
|----|---------|------------|--------|
| TD-SEC-02 | Auth lockout stored in process memory — lost on restart | `login_lockout` table added via SCHEMA_VERSION 22 migration; `DatabaseManager.record_failed_login`, `is_login_locked_out`, `clear_login_lockout` methods added; `AuthStore` delegates to DB; 2 new tests confirm persistence across restart | ✅ RESOLVED 2026-05-24 |
| TD-SEC-03 | No security headers on API responses (missing X-Content-Type-Options, X-Frame-Options, CSP, etc.) | `SecurityHeadersMiddleware` added to `titan/api/main.py`; sets X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Content-Security-Policy on every response; HSTS deferred until TLS termination (C-2); 1 new test confirms headers present | ✅ RESOLVED 2026-05-24 |
| TD-CI-02 | Governance CI gate only checked HEAD commit for ADR-0009 reference — multi-commit pushes could slip through | Gate rewritten to use `github.event.before` → `HEAD` range; all commits in push checked via `git log`; gate asserts on any commit lacking ADR-0009 when `governance_engine.py` changed | ✅ RESOLVED 2026-05-24 |
| TD-TEST-02 | `test_historical_snapshot_matches_full_suite_collection` used exact-match assertion — any test addition caused CI failure | Replaced with `±50` tolerance (`abs(actual - declared) <= 50`) + regression floor (`actual >= declared - 50`); CLAUDE.md snapshot updated to 2959 | ✅ RESOLVED 2026-05-24 |
| TD-DEP-01 | `psycopg2-binary` listed as active runtime dependency despite PostgreSQL adapter raising `NotImplementedError` | Commented out in `requirements.txt` with explanation; `database.py` soft-import (try/except ImportError) confirmed safe; `test_requirements_telegram_dependency.py` RUNTIME_DEPENDENCIES updated; no active production import found | ✅ RESOLVED 2026-05-24 |

---

## Phase 22 Scope (CLOSED, 2026-05-25)

Entry gate: Phase 21 close audit PASS (2026-05-24). Scope: schema extraction, EffectBus, Alembic CI, pydantic-settings, marker taxonomy, observability sink.
1. TD-08: Schema single source of truth — extract CREATE TABLE into titan/core/schema.py (XL) — DEFERRED Phase 23
2. TD-04 Phase B: EffectBus extraction (ADR-0058 Phase B) — DEFERRED Phase 23
3. TD-NEW-18: Alembic CI path — PostgreSQL migration CI gate (ADR-0044 resolution track) — ✅ RESOLVED 2026-05-24 (chain integrity CI-gated; PG activation deferred to ADR-0044)
4. P15-ARCH5: pydantic-settings migration — DEFERRED Phase 23
5. T5-15: Pytest marker taxonomy (unit/integration/governance) — 🟡 PARTIAL: Phase A complete (12 priority files marked). Phase B (100+ remaining files) DEFERRED Phase 23.
6. TD-OBS: Metrics time-series sink — 🟡 PARTIAL: Prometheus /metrics endpoint added; 5 instruments dual-emit JSON log + Prometheus. OTel exporter DEFERRED Phase 23.
7. TD-PYPROJECT-DEPS: pyproject.toml had empty dependencies = [] — ✅ RESOLVED 2026-05-25 (populated with 12 runtime deps from requirements.txt; dev-only packages excluded)
8. TD-UV-LOCK-UNUSED: uv.lock (592 lines) committed but unused in CI (pip install -r is the path) — ✅ RESOLVED 2026-05-25 (git rm uv.lock; .gitignore updated; CI install step annotated)
9. TD-BACKUP-VERIFY: No automated backup integrity verification — ✅ RESOLVED 2026-05-25 (scripts/verify_backup.py added; backup-verify CI job added; runbook updated with verification section; 3 tests in test_backup_verification.py)

---

## Phase 22 Critical-Fix Delivery (Opus TD-HEALTHCHECK pass, 2026-05-24)

### Resolved

| ID | Finding | Resolution | Status |
|----|---------|------------|--------|
| TD-HEALTHCHECK | HEALTHCHECK in Dockerfile and docker-compose.yml pointed to `/health` instead of the live `/readyz` endpoint | Changed both targets to `/readyz` | ✅ RESOLVED 2026-05-24 |
| H3 | Dockerfile CMD was an unreviewed inline python -c string — no composition root, no audit trail | Created `scripts/run_api.py` (reviewable entrypoint); Dockerfile CMD updated to `["python", "scripts/run_api.py"]` | ✅ RESOLVED 2026-05-24 |
| TD-WORKER-SCHED | Worker loop used raw `stop.wait(86400)` — fired at arbitrary offset from boot, not aligned to 07:00 UTC | Replaced with `_seconds_until_next_run(7, 0)` helper; loop sleeps exactly until 07:00 UTC each cycle | ✅ RESOLVED 2026-05-24 |
| TD-WORKER-LIFECYCLE | Worker had no SIGTERM handler — Docker stop sent SIGTERM with no graceful exit path | Added `_handle_sigterm` + module-level `_shutdown` event; `run_forever` accepts `shutdown_event` and returns cleanly on signal; `main()` logs `worker_stopped` in `finally` | ✅ RESOLVED 2026-05-24 |
| TD-RBAC-COACH | `require_coach_athlete_access` queried assignment table only when `db` was non-None — could silently allow access if db unavailable | Confirmed existing guard is correct; fitness test added to lock the behaviour | ✅ RESOLVED 2026-05-24 |
| TD-OVERRIDE-FAIL-OPEN | `GovernanceEngine` had no method exposing the None-ratio fail-closed path as a testable, context-mutating operation | Added `apply_override_lockdown(ctx)` method and `db` param to `__init__`; None ratio sets `context["override_locked"] = True` (fail closed); existing `check_override_lockdown` cold-start path unchanged | ✅ RESOLVED 2026-05-24 |
| TD-DEPLOY-DRIFT | No `docs/DEPLOYMENT_GUIDE.md` existed; risk of ops teams using local-dev steps for production deployments | Created file with canonical Docker banner at top; references `docs/runbooks/docker-deploy.md`; documents `titan_core.db` (not `titan.db`) | ✅ RESOLVED 2026-05-24 |
| H2 | `.env.example` contained stale `WEATHER_API_KEY`, wrong `DATABASE_PATH` (`titan.db`), and a `LOG_DIR` entry no longer used | Removed `WEATHER_API_KEY` and `LOG_DIR`; updated `DATABASE_PATH` to `titan_core.db` with Docker/local comments | ✅ RESOLVED 2026-05-24 |

### Open

| ID | Finding | Rationale |
|----|---------|-----------|
| TD-CI-SELFHOSTED | `alembic-integrity` CI job runs on `self-hosted` runner — topology unknown, cannot blindly switch to `ubuntu-latest` | `continue-on-error: true` added 2026-05-25 — advisory until runner inventory is audited. OPEN, not fixed. |

---

## FMEA: Phase 22 — Security/Observability

**Architect:** Claude | **Date:** 2026-05-25 | **Status:** G12 SATISFIED

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F22-01 | Auth lockout | DB write fails → lockout lost | MED | SQLite RLock + retry ✅ |
| F22-02 | /metrics endpoint | Prometheus registry collision across tests | LOW | Module-level instruments ✅ |
| F22-03 | Worker schedule | Clock skew shifts 07:00 window | LOW | UTC alignment documented ✅ |
| F22-04 | RBAC check | Assignment table empty → all access denied | LOW | ('system','owner') seed ✅ |
| F22-05 | Engine mutex | RLock deadlock if hydrate called twice | LOW | Lock() not RLock(), single call site ✅ |

**G12 gate:** SATISFIED.

---

## Phase 23 Scope (CLOSED, 2026-05-29)

Entry gate: Phase 22 close audit PASS (2026-05-25). Scope: schema extraction, EffectBus Phase B, retroactive pytest markers, pydantic-settings, alembic runner topology.

1. TD-08: Schema single source of truth — DEFERRED Phase 24
2. TD-04B: EffectBus extraction (ADR-0058 Phase B) — DEFERRED Phase 24
3. T5-15 Phase B: Retroactive pytest markers — DEFERRED Phase 24
4. P15-ARCH5: pydantic-settings migration — DEFERRED Phase 24
5. TD-CI-SELFHOSTED: Alembic runner topology — DEFERRED Phase 24

**CLOSED 2026-05-29**: phase_close_audit.sh 23 exit 0; 2974 tests passing; 7 skipped; ADR-0058 construction-site violation (worker engine construction bypassing EngineRegistry) caught and fixed; all governance invariants satisfied.

---

## Phase 24 Scope (CLOSED, 2026-06-03)

Entry gate: Phase 23 close audit PASS (2026-05-29). Scope: schema extraction, EffectBus Phase B, retroactive pytest markers, pydantic-settings, alembic runner topology.

1. TD-08: Schema single source of truth — ✅ RESOLVED 2026-06-02 (Opus-verified; schema.py canonical, SCHEMA_VERSION 23)
2. TD-04B: EffectBus extraction (ADR-0058 Phase B) — ✅ RESOLVED 2026-06-02 (TitanEffectBus live, delegation shim, 4 CI fitness gates)
3. T5-15 Phase B: Retroactive pytest markers (100+ remaining files, mechanical) — DEFERRED Phase 25
4. P15-ARCH5: pydantic-settings migration — DEFERRED Phase 25
5. TD-CI-SELFHOSTED: Alembic runner topology — ✅ RESOLVED (both gates moved to ubuntu-latest)

**CLOSED 2026-06-03**: phase_close_audit.sh 24 exit 0; 3021 tests passing, 7 skipped; FMEA G12 SATISFIED; all governance invariants satisfied.

---

## Phase 25 Scope (CLOSED, 2026-06-06)

### TD-08 Residual Debt (registered from Opus pre-Phase-25 audit 2026-06-03)

| ID | Severity | Description | Blocking |
|----|----------|-------------|---------|
| TD-08-R1 | LOW | PostgreSQLDatabaseManager.create_tables() still maintains independent raw DDL for training_log and governance_outcomes — not derived from titan/core/schema.py. PG training_log missing athlete_id and avg_pace_sec_per_km (latent INV-03 violation if PG backend activated). Ref: V7-01, ADR-0044, INV-03. | No — PG backend gated |
| TD-08-R2 | LOW | tests/test_db_schema_contracts.py is a third independent column authority (8 hardcoded column sets). Function rename done (Phase 25 advisory pass). Stale annotations corrected. Remaining: fold assertions into descriptor-derived path long-term. Ref: V7-02. | No |
| TD-08-R3 | LOW | v8/v13 rebuild snapshots in database.py annotated as frozen (Phase 25 advisory pass). No further action until schema descriptor final convergence. Ref: V7-03. | No — DONE |

### P15-ARCH5 Architectural Decision Record

**TITAN_DATA_DIR canonical default: `/data`** (decided 2026-06-03 by architect)
- Production default: `/data` (Docker path — authoritative)
- Dev override: set `TITAN_DATA_DIR=~/Documents/TITAN` in local environment
- Rationale: run_api.py:14 and worker/__init__.py:25 already use `/data`; garmin_sync.py:52 used `~/Documents/TITAN` as a local fallback only
- garmin_sync.py:52 must be updated to respect TITAN_DATA_DIR
- Settings model must expose: TITAN_DATA_DIR, GARMIN_EMAIL, GARMIN_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TITAN_JWT_PRIVATE_KEY, TITAN_JWT_PUBLIC_KEY, TITAN_DB_BACKEND, TITAN_POSTGRES_DSN (conditional), ATHLETE_MAX_HR, GARMIN_SYNC_TIMEOUT_S, WEATHER_LOCATION, TITAN_ML_KILL_SWITCH, TITAN_ENV, TITAN_LOG_PATH, TITAN_ENABLE_API
- TITAN_POSTGRES_DSN: required only when TITAN_DB_BACKEND=postgres — use @model_validator
- Implementation deferred until CI minutes restore (P15-ARCH5 touches 36 os.getenv sites across 12 files; silent regression risk without full test run)

Entry gate: Phase 24 close audit PASS (2026-06-03). Scope: retroactive pytest markers, pydantic-settings migration, B2c fallback removal.

1. T5-15 Phase B: Retroactive pytest markers (100+ remaining files, mechanical) — ✅ RESOLVED 2026-06-06
2. P15-ARCH5: pydantic-settings migration — ✅ RESOLVED 2026-06-06
3. B2c fallback: Remove DailyCoach test-compat fallback path (Phase 24 deferred) — ✅ RESOLVED 2026-06-06

**CLOSED 2026-06-06**: phase_close_audit.sh 25 exit 0; 3022 tests passing; FMEA G12 SATISFIED; T5-15B RESOLVED; P15-ARCH5 RESOLVED; ADR-0059 RESOLVED.

---

## Phase 26 Scope (CLOSED, 2026-06-07)

Entry gate: Phase 25 close audit PASS (2026-06-06). Scope: CoachingScheduler activation + per-athlete engine isolation (Phase 9 corpus gate prerequisite).

1. CoachingScheduler activation: wire the fully-tested CoachingScheduler (F4.1 — functional but unwired since Phase 19) as the production multi-athlete runtime; `run_forever` retained as single-athlete fallback behind a feature flag. ADR required. — ✅ RESOLVED 2026-06-07 (wired via `TITAN_MULTI_ATHLETE` flag; `_run_with_scheduler` in `titan/worker/__init__.py`; `run_forever` fallback retained).
2. Per-athlete engine isolation: `EngineRegistry.from_db(db, athlete_id)` performs real DB hydration (TSB load history, HRV baseline, CS performances, APL offsets); TODO-Phase9 markers resolved; each pipeline call receives a freshly hydrated, athlete-scoped registry. — ✅ RESOLVED 2026-06-07 (TSB + HRV hydration live, athlete-scoped; CS-performance/APL-offset hydration tracked as TODO-P26-04b/c handed to Phase 9 alongside per-athlete profile schema).
3. Phase 9 corpus gate prerequisite: ≥ 3 athlete profiles × ≥ 90 paired decisions before per-athlete auto-threshold calibration (MODERATE → STRONG) activates. — ✅ RESOLVED 2026-06-07 (advisory-mode corpus-gate query executable; gate mode behind `TITAN_PHASE9_CORPUS_GATE`).

**Scope table (Opus pre-Phase-26 audit, 2026-06-07 — see `docs/audit/PRE_PHASE26_AUDIT_2026-06-07.md`):**

| Item | Description | Status | Opus ref |
|------|-------------|--------|----------|
| P26-01 | ATHLETE_MAX_HR per-athlete resolution | RESOLVED (ADR-0070): `athlete_profiles.max_hr` (NOT NULL) holds each athlete's max HR since ADR-0067; the owner keeps the `.env` value (D-125). | A1-F2 (Opus pre-Phase-26 audit 2026-06-07), ADR-0016 |
| P26-02 | Corpus gate measurement — query COUNT(DISTINCT athlete_id) ≥ 3 AND per-athlete governance_outcomes ≥ 90 | ✅ RESOLVED 2026-06-07 (advisory-mode query in `tests/test_phase9_corpus_gate.py`; gate mode via `TITAN_PHASE9_CORPUS_GATE`) | A3-F3 |
| P26-03 | CoachingScheduler activation — wire into worker composition root | ✅ RESOLVED 2026-06-07 (`TITAN_MULTI_ATHLETE` flag selects `_run_with_scheduler`; `run_forever` single-athlete fallback retained) | A3-F1 |
| P26-04 | EngineRegistry.from_db DB hydration — implement TODO-Phase9 markers | ✅ RESOLVED 2026-06-07 (TSB load history + HRV baseline hydration, athlete-scoped; CS-performance/APL-offset hydration → TODO-P26-04b/c carried to Phase 9) | A3-F2 |
| P26-05 | Module-level get_settings() constants — make lazy in garmin_sync.py:51 and worker/__init__.py:26 | ✅ RESOLVED 2026-06-07 (constants resolved lazily at call site) | A1-F3 |
| P26-06 | postgres_dsn_required validator test | ✅ RESOLVED 2026-06-07 (`test_titan_settings_postgres_dsn_required` in `tests/test_db_schema_contracts.py`) | A2-F2 |
| P26-07 | B2c fallback — reconcile CLAUDE.md close-note vs code | ✅ RESOLVED 2026-06-07 (B2c fallback removed from `daily_coach.py`; `engines=` required) | A3-F4 |
| P26-08 | AGENTS.md constraints.txt ADR addendum | DEFERRED pending ADR | A3-F6 |

**CLOSED 2026-06-07**: phase_close_audit.sh 26 exit 0; 3025 tests passing, 6 skipped (3031 collected); FMEA G12 SATISFIED; P26-02/03/04/05/06/07 RESOLVED; P26-01 DEFERRED Phase 9; P26-08 DEFERRED pending ADR.

---

## Phase 27 Scope (OPEN, 2026-06-07)

Entry gate: Phase 26 close audit PASS (2026-06-07); ≥ 3 athlete profiles active with per-athlete-isolated `EngineRegistry`; ADR-0052 offset calibration producing per-athlete threshold deltas in production. Scope: cohort analytics + population intelligence (see ROADMAP Phase 27 section).

1. Cohort calibration analytics: cross-athlete threshold delta distributions; population heuristics vs. individual outliers classified.
2. `CohortProfile` — aggregated population-level calibration signal surface for evidence promotion: HEURISTIC → MODERATE when ≥ 3 athletes independently confirm the same delta.
3. Proactive load modulation: predictive volume reduction before metrics breach safety bands; advisory mode first (≥ 3 correct predictions before auto-apply). ADR-0014 promotion controls apply.
4. Multi-modal biometric ingestion: lab VO₂max, lactate curve, HRV4Training exports; weighted by provenance (lab > wearable > self-reported).
5. Rollback gate: revert calibrated threshold if `completion_rate` degrades or injury events increase within a 30-day observation window.

**Hard constraint:** H1–H5 write guard (ADR-0052) enforced at the DB layer; cohort-level signal cannot loosen hard stops regardless of population consensus.

**Opus pre-Phase-27 audit (2026-06-08):** NO-GO — see `docs/audit/PRE_PHASE27_AUDIT_2026-06-08.md`. Blockers registered below.

| ID | Severity | Description | Blocks | Status |
|----|----------|-------------|--------|--------|
| P27-B1 | HIGH | daily_metrics unique key must be (athlete_id, date) not date-alone; writer must set athlete_id. personal_bests and gear_usage need athlete_id column + descriptor correction. SCHEMA_VERSION 24 required. | Multi-athlete store | RESOLVED 2026-06-09 (PR #848) — SCHEMA_VERSION 24 |
| P27-B2 | MED-HIGH | update_governance_outcome unscoped write; get_hrr_history unscoped read | Isolation integrity | RESOLVED 2026-06-09 (PR #849) — write/read scoping |
| P27-B3 | HIGH | DailyCoach hardcodes 'owner' in _hydrate_engines_from_db, _feed_load_engines, OutcomeTracker construction — nullifies EngineRegistry.from_db(athlete_id) | Per-athlete isolation | RESOLVED 2026-06-09 (PR #850) — DailyCoach athlete_id |
| P27-B4 | HIGH | Behavioral two-athlete isolation fitness function missing; FMEA F26-02 mitigation is false assurance — static AST lint exempts database.py | Governance integrity | RESOLVED 2026-06-09 (PR #851) — behavioral isolation fitness |
| P27-B5 | HIGH | CoachingScheduler callback has no 07:00/daily cadence gate — fires every 60s, risks Garmin ban and corpus poisoning | Scheduler safety | RESOLVED 2026-06-09 (PR #847) — scheduler 07:00 gate |
| P27-B6 | MED | Per-athlete calibration cycle inert: FP/FN keys never emitted; OutcomeTracker DB hydration owner-only | Cohort signal | RESOLVED 2026-06-09 (PR #852) — FP/FN keys + tracker scoping |
| P27-B7 | HIGH | DailyCoach orchestration write path is owner/default-hardcoded: AthleteCoachingContext(athlete_id="default"), _persist_garmin_data (save_session/save_daily_metric/save_daily_metric_if_missing omit athlete_id), save_hrr/update_glycogen_debt use unscoped WHERE date=?, record_decision tags 'owner'. Also: permanent "default" cold-start renders ThresholdAdapter inert. Active on athlete #2. | Per-athlete corpus production | RESOLVED 2026-06-09 (PR #855/#856) — write path closed; save_hrr/update_glycogen_debt/save_daily_metric_if_missing athlete-scoped; AthleteCoachingContext fixed; record_decision passes athlete_profile_id; behavioral write test added; FMEA F27-01..F27-05 registered; GO verdict issued |
| P27-01 | MED | cohort_calibration_signals table absent; no schema surface for CohortProfile aggregation or population-heuristic promotion | Cohort analytics | RESOLVED 2026-06-09 (PR #858) — cohort_calibration_signals table, SCHEMA_VERSION 25, schema-only scaffolding; producer/reader deferred until athlete #2 (multi-athlete cohort) |
| P27-04 | MED | No rollback gate to revert a calibrated threshold if completion_rate degrades within the 30-day observation window | Calibration safety | RESOLVED 2026-06-09 (PR #860) — completion-rate calibration rollback gate, advisory default, v1 (completion-rate only; injury-event trigger deferred — no injury column yet, A2-04). Not yet wired into run_morning_routine. |

### T-PRA-18-CAL · Calibration pipeline end-to-end wiring 🔵 DEFERRED-FORMAL

**Tier:** 2.
**Status:** DEFERRED-FORMAL (2026-06-12).

**Scope:** `run_calibration_cycle` has no production caller; `GovernanceEngine(threshold_adapter=...)`
is discarded in `coaching_pipeline.py:99` ("Stage 4 will wire this"); CS/APL hydrate cold
(TODO-P26-04b/c).

**Re-entry criteria:** Formally deferred. Re-entry requires BOTH: (a) B-3 verified closed
(`worker_routine_executions` table, INV-15) AND (b) owner corpus gate met (≥
`CALIBRATION_MIN_OUTCOME_COUNT` paired decisions in `governance_outcomes` for `athlete_id='owner'`).

**Owner:** Architect. **Target phase:** post-B3.

---

### T-PRA register mirror (AGENTS §30) · added 2026-10-07

One row per T-PRA item in the AGENTS.md §30 register, so every §30 row has a debt entry
here (refactor plan task #11). AGENTS §30 stays the canonical register for scope and
dispositions; this table tracks status and where the work is scheduled. "FIX MERGED" means
the code change is on main and the item still needs the Architect's close; it is not a
RESOLVED disposition.

| ID | Source | Tier | Scope (short) | Status | Scheduled in |
|----|--------|------|---------------|--------|--------------|
| T-PRA-01 | B-1 | 1 | Coach-route scoped authorization (INV-11) + owner-bypass removal | OPEN | Not in the refactor plan yet; Architect to schedule |
| T-PRA-02 | B-5, SA:m-1 | 1 | Telegram fail-closed trust + durable nonces (INV-16, INV-13) | FIX MERGED: PR #904 (`_is_trusted()` denies when unconfigured; `DegradedModeTracker` hydration fails closed); durable nonces: branch `feat/adr0060-telegram-nonces` (T-PRA-03); Architect close pending | Refactor plan task #12 |
| T-PRA-03 | B-3, B-5 | 1 | Worker durable state tables (INV-15, INV-17) | RESOLVED (ADR-0070): `worker_routine_executions` and `telegram_override_nonces` exist since v26, the delivery marker since v31 (ADR-0060, D-098); `tests/test_worker_state_durability.py` | Refactor plan task #14 |
| T-PRA-04 | B-2, B-9 | 1 | FK enforcement safe rollout (INV-14) | FIX MERGED: PR #874 (`foreign_keys=ON` + `foreign_key_check` refusal at startup); Architect close pending | Refactor plan task #4 |
| T-PRA-05 | SA:m-4, E-2 | 2 | Worker observability transport (INV-19) | OPEN | Not scheduled |
| T-PRA-06 | SA:M-2 | 1 | Multi-athlete scheduler registration from `athletes` table | RESOLVED (ADR-0070): the worker round runs every ready athlete from `athlete_accounts` (ADR-0067); the #926 hold ended with ADR-0067 | Refactor plan task #20 |
| T-PRA-07 | B-4 | 1 | Fail-closed governance guard (INV-12) | RESOLVED 2026-06-12 (PR #865) | — |
| T-PRA-08 | B-6 | 1 | Off-volume backups, retention, integrity check, restore drill, `RUNBOOK_DR.md` | FIX MERGED: PR #906 (`titan-backups` volume, verified artifacts, 7 daily + 4 weekly retention, `scripts/restore_drill.py`, `docs/RUNBOOK_DR.md`); DR-03 drill result recorded at next phase close; Architect close pending | Refactor plan task #15 |
| T-PRA-09 | B-7 | 2 | Release engineering RE-01..04 | FIX MERGED: PR #909 (version only in `pyproject.toml`, read at runtime; `release.yml` builds `ghcr.io` images per `vX.Y.Z` tag on `main`; `docker-compose.release.yml` pins images; `docs/RUNBOOK_ROLLBACK.md`; `tests/test_release_engineering.py`); RE-03 staging drill pending the first tag; Architect close pending | Refactor plan task #16 |
| T-PRA-10 | SA chain | 2 | Degradation alert chain end-to-end test (INV-21) | RESOLVED 2026-10-23 (D-143): `tests/test_degradation_alert_chain.py` runs the real GarminSync failure count → DegradedModeTracker (SQLite) → effect-bus hook → `alert_operator` chain, owner and athlete | — |
| T-PRA-11 | B-13 | 2 | Request body-size middleware (RBP-01) | FIX MERGED: PR #928 (`BodySizeLimitMiddleware`: Content-Length pre-check + streamed-read cap → 413; `API_MAX_BODY_SIZE_BYTES` default 1 MiB; `tests/test_request_boundary.py`); Architect close pending | Refactor plan task #21 |
| T-PRA-12 | D-1/K:PRA-16, C-7 | 2 | Records pass (snapshot, ADR-0057 status, phase labels, module ceiling) | OPEN (module ceiling: AGENTS §16.11 states 90, the test value, ADR-0070; T-PRA rows mirrored here) | Refactor plan task #11 |
| T-PRA-14 | B-10 | 2 | MPC doc/comment corrections; ADR-0044 execution-date decision | OPEN | Refactor plan task #25 (Architect decision) |
| T-PRA-18 | SA:BENIGN1/2 | 2 | Wire ADR-0052 calibration loop (see T-PRA-18-CAL above) | DEFERRED-FORMAL | Refactor plan task #23 |
| T-PRA-20 | SA:BENIGN3 | 3 | Diagnostic-script DB path from config | FIX MERGED: PR #895 (`scripts/diagnostics/` read `TITAN_DATA_DIR`); Architect close pending | Refactor plan task #6 |
| T-PRA-21 | B-11 | 1 | Durable ordered-before-effect audit (INV-22) | FIX MERGED: PR #927 (API coach routes write `coach_audit_log` before the handler; write failure → 503 + `audit_write_failure`, no effect; `tests/test_audit_durability.py`). Telegram `/sync`, `/manual_entry`, `/override` in PR #930 (`coach_audit_log` row as `telegram:<chat_id>` before the effect; write failure or no DB → command rejected + `audit_write_failure`; `tests/test_telegram_audit_durability.py`); Architect close pending | Refactor plan task #21 |
| T-PRA-22 | B-15, B-3, SA:m-3 | 1 | Worker liveness: healthcheck, heartbeat, watchdog, stale-lock recovery (INV-23) | FIX MERGED: PR #908 (heartbeat + compose healthcheck, routine budget, CoachingScheduler watchdog + `worker_thread_died_total`, callback isolation, lock holder PID + kill-recovery test, worker log rotation); resource limits (§8.14(5), SHOULD) not set, recorded at phase close; Architect close pending | Refactor plan task #14 |
| T-PRA-23 | B-8 family | 2 | Schema downgrade routines / documented reversal | OPEN | Not scheduled |
| T-PRA-24 | B-14 | 1 | Data-trust verdict clamp (INV-24) | FIX MERGED: PR #905 (INVALID verdict caps the session at EASY / 45 min, REST stays REST; `data_trust_clamped` in the decision trace); Architect close pending | Refactor plan task #13 |
| T-PRA-25 | B-8 | 1 | `user_version > SCHEMA_VERSION` startup guard (INV-25) | FIX MERGED: PR #874 (startup refuses a newer DB); Architect close pending | Refactor plan task #4 |
| T-PRA-26 | K:PRA-13, SA:m-2, C-6 | 2 | Sync & safety-path conformance sweep | OPEN | Not scheduled |
| T-PRA-27 | B-12, K:PRA-18 | 2 | CodeQL on PR/push, gitleaks full-range, SBOM, image scan | OPEN (gitleaks on PRs and weekly CodeQL live since PR #879; CodeQL per PR needs a paid plan on a private repo, open Architect decision in PROGRESS.md) | Not scheduled |
| T-PRA-28 | F-4/5/7/10 | 2 | Auth bundle RBP-04/05 | FIX PARTIAL: PR #929 (RBP-05: locked account answers 401 `Invalid credentials` like a wrong password or unknown user; CSRF cookie `HttpOnly`). RBP-05 IP+username keying declined by Architect 2026-10-08 (username-only lockout kept). RBP-04 JWT half: branch `fix/rbp04-keys-at-construction` (`create_app()` checks both keys and signs/verifies a probe token, so a missing, malformed or mismatched pair stops construction; `tests/test_rbp04_key_validation.py`). Pending: F-10, an invalid `TITAN_GARTH_TOKEN_KEY` is still ignored with a WARNING (decision needed: the empty `TITAN_GARTH_TOKEN_KEY=` in `.env.example` takes the same path) | Refactor plan task #21 |
| T-PRA-29 | D-2 | 2 | Compose-up persistence e2e in CI | FIX PENDING — PR #916: `.github/workflows/docker-smoke.yml` runs `scripts/docker_smoke_test.sh` (both containers restarted, marker persists, `/readyz`, worker back); worker process kill/restart covered by `tests/e2e/test_worker_restart.py` (#914) | Refactor plan task #19 |
| T-PRA-30 | D-4, C-2, C-3 | 2 | Migration-chain realistic-data test + schema-parity test | PARTIAL — PR #912: v0→v25 on 8 weeks of real-release data + ladder-vs-fresh schema parity (`tests/e2e/test_legacy_db_upgrade.py`); 2 known drifts listed there (training_log.quality_flag affinity, governance_outcomes.athlete_id default 'default'). Open: SQLite↔Alembic parity, frozen-migration manifest | Refactor plan task #19 |
| T-PRA-31 | E-3 | 2 | Route alert-class events through `NotificationGateway` | SUPERSEDED (D-139: the gateway is deleted; the worker sends directly) | — |
| T-PRA-32 | K:PRA-15 | 2 | EngineRegistry CS/APL hydration (TODO-P26-04b/c) | RESOLVED (#979): PR #931 (04c: APL is stateless; offsets already hydrated per athlete by ThresholdAdapter in `coaching_pipeline()`, now test-locked). 04b: `cs_performances.athlete_id` added in v28 (PR #974, D-037, AGENTS §13.4 Stage 1); writes carry the athlete (#975, Stage 2); `DailyCoach` reads only its athlete's rows (#976, Stage 3). Writes: the owner chose manual entry; `/time_trial` and console Data Browser → 7 write `cs_performances` (#978, D-039). Hydration now replays the trials oldest first, one tracker update per trial from the second on (#979, D-040); five recent trials lift `CS_CONFIDENCE_LOCK`, test-locked | Refactor plan task #22 / task 11 |
| T-PRA-35 | D-1, C-7, I-22 | 3 | Governance sensor bundle | OPEN | Not scheduled |
| T-PRA-36 | D-6 | 3 | Skip-placeholders to strict xfail + meta-test | OPEN | Not scheduled |
| T-PRA-37 | Ladder Pass 3 | 2 | `scripts/governance_lint.py` wired into `titan_ci.sh` | OPEN | Not scheduled |
| T-PRA-38 | Ladder Pass 3 | 2 | `titan_ci.sh --profile` + `scripts/env_fingerprint.sh` | OPEN | Not scheduled |
| T-PRA-39 | Ladder Pass 3 | 3 | Governance ledger append + phase-close summary | OPEN | Not scheduled |

---

## FMEA: Phase 24 — Schema & EffectBus Phase C (CLOSED)

**Architect:** Claude | **Date:** 2026-06-02 | **Closed:** 2026-06-03 | **Status:** G12 SATISFIED

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F24-01 | titan/core/schema.py extraction (TD-08) | Migration mis-ordering drops column on legacy DB | HIGH | Opus pre-audit completed; schema.py canonical ✅ RESOLVED 2026-06-02 |
| F24-02 | TitanEffectBus (TD-04B) | 27-file blast radius breaks existing pipeline subscribers | HIGH | Delegation shim preserves API; 4 CI fitness gates green ✅ RESOLVED 2026-06-02 |
| F24-03 | pytest marker backfill (T5-15B) | Missing markers skip tests silently | LOW | Mechanical; CI catches uncollected tests — DEFERRED Phase 25 |
| F24-04 | pydantic-settings migration (P15-ARCH5) | Config loading breaks on env-var rename | MED | Additive alias approach planned — DEFERRED Phase 25 |
| F24-05 | Alembic runner (TD-CI-SELFHOSTED) | Self-hosted runner absent → Alembic gate never runs | LOW | `continue-on-error: true` advisory in place — DEFERRED Phase 25 |

**G12 gate:** SATISFIED.

---

## FMEA: Phase 26 — CoachingScheduler Activation & Per-Athlete Isolation

**Architect:** Claude | **Date:** 2026-06-07 | **Closed:** 2026-06-07 | **Status:** G12 SATISFIED

Phase 26 introduces feedback-loop and auto-calibration surfaces (multi-athlete
scheduler runtime, per-athlete engine hydration, threshold-offset calibration),
so G12 applies per AGENTS.md §16.2-G12.

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F26-01 | CoachingScheduler (`titan/orchestration/coaching_scheduler.py`) | Per-athlete callback thread silently dies → athlete misses morning routine with no signal | MED | `TITAN_MULTI_ATHLETE` gates activation; `run_forever` single-athlete fallback retained when flag unset; scheduler lifecycle covered by tests ✅ |
| F26-02 | EngineRegistry.from_db hydration (`engine_registry.py`) | Cross-athlete state bleed — wrong athlete's TSB/HRV history hydrates an engine | HIGH | **CORRECTED by Opus pre-Phase-27 audit 2026-06-08** — the claimed mitigation is false assurance: `DailyCoach._hydrate_engines_from_db`/`_feed_load_engines` re-hydrate from `'owner'` regardless of `athlete_id`, nullifying `EngineRegistry.from_db(athlete_id)`, and `test_athlete_isolation_invariant.py` is a static AST/SQL-string lint that exempts `database.py` and never exercises the hydration path behaviorally. Behavioral isolation test required (P27-B4). Behavioral isolation test added (P27-B4, PR #851); contamination path closed (P27-B3, PR #850); FMEA mitigation claim corrected 2026-06-09 ✅ |
| F26-03 | Partial hydration (CS performances / APL offsets — TODO-P26-04b/c) | Engine runs on incomplete inputs and emits a recommendation as if fully hydrated | MED | TSB + HRV hydration live and tested; CS-performance/APL-offset paths explicitly deferred (not silently skipped) and carried to Phase 9 with per-athlete profile schema ✅ |
| F26-04 | Threshold-offset calibration (ADR-0052, `athlete_threshold_offsets`) | Auto-calibration loosens an H1–H5 hard stop | HIGH | `HARD_STOP_THRESHOLD_KEYS` excludes HRV/RHR/TSB/fatigue/injury from per-athlete adaptation; damping (5%) and max-delta (±20%) bounds PROVISIONAL; MODERATE→STRONG promotion gated on corpus + confidence bounds ✅ |
| F26-05 | Phase 9 corpus gate (`test_phase9_corpus_gate.py`) | Calibration activates before ≥3 athletes × ≥90 paired decisions exist → premature personalization on thin data | MED | Corpus-gate query executable in advisory mode by default; enforcing gate mode behind `TITAN_PHASE9_CORPUS_GATE`; auto-threshold calibration held until corpus met ✅ |
| F26-06 | ATHLETE_MAX_HR divergence (P26-01) | Global default (160) vs profile default (191) skews TRIMP zone ceilings across athletes | LOW | RESOLVED with P26-01 (ADR-0070): `athlete_profiles.max_hr` per athlete |

**G12 gate:** SATISFIED.

---

## FMEA: Phase 27 — Write-Path Athlete Isolation (P27-B7)

**Architect:** Claude | **Date:** 2026-06-09 | **Status:** RESOLVED

DailyCoach write paths touched by the morning routine must tag all rows with the
correct `athlete_id`. Failure silently mis-attributes biometric data to the wrong
athlete, corrupting the per-athlete corpus and nullifying cohort calibration.

| ID | Component | Failure Mode | Sev | Mit |
|---|---|---|---|---|
| F27-01 | `DailyCoach._persist_garmin_data` | `save_session` / `save_daily_metric` / `save_daily_metric_if_missing` omit `athlete_id` → all writes land on `'owner'` regardless of which athlete the coach manages | HIGH | All three calls now pass `athlete_id=getattr(self, "athlete_id", "owner")`; `save_daily_metric_if_missing` updated to include `athlete_id` in INSERT ✅ RESOLVED 2026-06-09 |
| F27-02 | `DailyCoach.run_morning_routine` step 3 (`save_hrr`) | `save_hrr` WHERE clause was `WHERE date=?` — updates first matching row, could overwrite a different athlete's HRR | HIGH | `save_hrr` now accepts `athlete_id` and scopes `WHERE athlete_id=? AND date=?`; call site passes `self.athlete_id` ✅ RESOLVED 2026-06-09 |
| F27-03 | `DailyCoach.run_morning_routine` step 6 (`update_glycogen_debt`) | Same unscoped WHERE as F27-02 for glycogen debt | HIGH | `update_glycogen_debt` now scoped by `athlete_id` ✅ RESOLVED 2026-06-09 |
| F27-04 | `AthleteCoachingContext` construction | `athlete_id="default"` hardcoded — pipeline context tags decisions to wrong athlete | MED | Changed to `athlete_id=getattr(self, "athlete_id", "owner")` ✅ RESOLVED 2026-06-09 |
| F27-05 | `_make_record_outcome_handler` → `record_decision` | `athlete_profile_id` not passed → governance decisions persisted as `'owner'` for all athletes | MED | Handler closure now captures `athlete_profile_id` from `self.athlete_id` and passes it to `record_decision` ✅ RESOLVED 2026-06-09 |

**G12 gate:** SATISFIED.

---

## Φάση 4 του refactor — ανοιχτά στο κλείσιμο (2026-10-23, D-114)

Η Φάση 4 (πολλοί αθλητές, ADR-0067) έκλεισε με αυτά ανοιχτά. Κανένα δεν σταματά τον owner. Τα P4-01
και P4-02 αγγίζουν πύλες του governance, άρα αλλάζουν μόνο μέσω ADR-0009, και πρέπει να γίνουν πριν
από τον πιλότο (βήμα 13) με πραγματικό αθλητή.

| ID | Θέμα | Tier | Σοβαρότητα | Πότε |
|---|---|---|---|---|
| P4-01 | Η σημαία `data_confidence_low` του decision trace βγαίνει μόνο από τη βεβαιότητα της εκκίνησης, όχι από τις πύλες με έλλειψη δεδομένων (H2/H3/H4_MISSING). Ο `DegradedModeTracker` δεν ανοίγει χρονόμετρο για αυτές (Codex στο #1050) | 1 | HIGH | RESOLVED (D-137, ADR-0069 §5) |
| P4-02 | Το `HARD_STOP_SAFETY_GATES` μπαίνει και όταν λείπουν μόνο δεδομένα, όχι μόνο σε πραγματικό hard stop | 1 | HIGH | RESOLVED (D-138, ADR-0069 §6) |
| P4-03 | Προσπάθεια πρωινού που τρέχει πάνω από 15 λεπτά μπορεί να επικαλυφθεί από τη δεύτερη: χρειάζεται σήμα «σε εξέλιξη» στη βάση, σχήμα v34 (D-113) | 1 | MEDIUM | RESOLVED (D-135, ADR-0069 §4) |
| P4-04 | Σκανδάλη hard-stop για τα offsets κατωφλίων στη βάση, σχήμα v34 (D-112) | 1 | MEDIUM | RESOLVED (D-135, ADR-0069 §4) |
| P4-05 | Οι ειδοποιήσεις του worker δεν περνούν από το `NotificationGateway`, που δεν χρησιμοποιείται πουθενά στο `titan/` (AGENTS §16.6, D-113) | 2 | MEDIUM | RESOLVED (D-139, ADR-0069 §7)· το AGENTS §16.6 αλλάζει στο Κύμα 4 |
| P4-06 | PostgreSQL: η εγγραφή `athlete_id` πριν ανοίξει ξανά ο σκελετός (ISO-5, D-112) | 4 | HIGH (μητρώο, D-156) | Όταν ανοίξει το PostgreSQL (ADR-0044) |
| P4-07 | Προεπιλογή του H5 για νέο αθλητή (D-043) | 2 | MEDIUM | RESOLVED (D-133, ADR-0069 §2) |
| P4-08 | Έλεγχος του `docs/consent/v1.md` από δικηγόρο· να αναφέρει και το βάρος σώματος | — | — | Πριν από τον πιλότο |
| P4-09 | Τα γεγονότα `slo_alert` γράφονται μόνο στο log και δεν φτάνουν σε κανέναν (E-3· το T-PRA-31 αντικαταστάθηκε, D-139) | 2 | MEDIUM | RESOLVED · PR #1091 (D-149) |
| P4-10 | Οι τιμές HRV/RHR του `BiometricRouter` δεν φτάνουν στις H2/H3, ενώ το ADR-0055 το έλεγε (addendum ADR-0070) | 2 | HIGH (μητρώο, D-156) | OPEN· αλλάζει τι βλέπουν οι πύλες, θέλει ADR-0009 |
| P4-11 | Ο `cold_start_conservative_factor` του ADR-0033 μπαίνει στο context αλλά δεν τον διαβάζει καμία πύλη (addendum ADR-0070· ο ThresholdAdapter είναι το T-PRA-18) | 3 | HIGH (μητρώο, D-156) | OPEN |

---

## Ευρήματα των ελέγχων MA και OW (2026-10-23)

Οι έλεγχοι multi-athlete (MA-*) και owner (OW-*) στο 998220a. Κάθε εύρημα κλείνει στο PR του πλάνου του.

| ID | Θέμα | Σοβαρότητα | Κατάσταση |
|---|---|---|---|
| OW-L2 | Γραμμή του αρχείου διαγραφών με `owner` έσβηνε τα δεδομένα του owner μετά από επαναφορά | LOW | RESOLVED (D-115) |
| MA-F6 | Coach με κενό `?athlete_id=` περνούσε χωρίς έλεγχο ανάθεσης και χωρίς audit | HIGH | RESOLVED (D-116) |
| MA-F1 | Token Garmin αθλητή χρησιμοποιούνταν χωρίς έλεγχο ότι ανήκει στον δεμένο λογαριασμό Garmin | HIGH | RESOLVED (D-117) |
| MA-F2 | Χωρίς αρχείο token ο αθλητής περνούσε ως έτοιμος και έφευγε briefing | HIGH | RESOLVED (D-118) |
| MA-F9 | Το bot της κονσόλας δρομολογούσε chats αθλητών με σβηστή τη σημαία multi-athlete | HIGH | RESOLVED (D-119) |
| MA-F7 | Κομμάτι του token Telegram στο log όταν η μορφή του είναι άκυρη | LOW | RESOLVED (D-120) |
| OW-L4 | Προσωπικά στοιχεία στα `extra` των logs· σταθερό label `owner` στον μετρητή sync | LOW | RESOLVED (D-120) |
| MA-F8 | Ο `PostgreSQLAdapter` έγραφε αποφάσεις governance χωρίς `athlete_id` | HIGH | RESOLVED (D-121) |
| MA-F3 | Κενό ή απόν athlete id καταλήγει στον owner | HIGH | RESOLVED (D-122, D-123, D-124) |
| OW-L3 | Σιωπηλές προεπιλογές για max HR, threshold HR και φάση όταν λείπουν από το `.env` | LOW | RESOLVED (D-125) |
| MA-F4 | Το εβδομαδιαίο πλάνο ξαναστελνόταν σε retry της ίδιας μέρας | MEDIUM | RESOLVED (D-126) |
| OW-M1 | Δυναμικά πεδία χωρίς escaping έσπαγαν το legacy Markdown και το Telegram απέρριπτε το μήνυμα | MEDIUM | RESOLVED (D-127) |
| OW-F4 | Το `/today` της κονσόλας έγραφε δεύτερη απόφαση την ίδια μέρα, χωρίς claim, lock και audit | HIGH | RESOLVED (D-128) |
| OW-L1 | Το `/sync` του owner και το background sync δεν αποθήκευαν τα δεδομένα Garmin | LOW | RESOLVED (D-129) |
| OW-L5 (14α) | Η ημερομηνία του briefing ήταν του ρολογιού, όχι της μέρας του πρωινού | LOW | RESOLVED (D-130) |
| OW-L5 (14β) | HRV «τελευταίο» κατά σειρά άφιξης, TSB για τη μέρα του ρολογιού, δραστηριότητες σε τοπική ώρα | LOW | RESOLVED (D-131) |
| OW-F1 | Η H4 έβλεπε το TSB μία μέρα πίσω (πριν από την αποθήκευση του πρωινού sync) | HIGH | RESOLVED (D-132, ADR-0069 §1) |
| OW-F2 + P4-07 | Η κόπωση του /manual_entry δεν αποθηκευόταν πάνω σε υπάρχουσα γραμμή και δεν έφτανε στην H5 | HIGH | RESOLVED (D-133, ADR-0069 §2) |
| OW-F3 | Η H1 δεν έχει πηγή και το rationale έγραφε CLEAR για πύλες που δεν μετρήθηκαν | HIGH | RESOLVED (D-134, D-135, D-136, ADR-0069 §3)· η `/injury` είναι μόνο για τον owner (ADR-0067 D10.3) |
| OW-M2 | Άγνωστο TSB/ACWR γραφόταν 0,0 στο `governance_outcomes` και μετρούσε στον μέσο όρο της κονσόλας | MEDIUM | RESOLVED (D-135, ADR-0069 §4) |
| MA-F5 | Μετά από crash στη μέση της αποστολής η επόμενη προσπάθεια ξανάστελνε όλο το briefing | MEDIUM | RESOLVED (D-140, ADR-0069 §8)· οι αθλητές διαβάζουν «let Zaf know», γιατί δεν έχουν /today |
