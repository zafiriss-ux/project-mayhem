# TITAN OS — SCRATCHPAD Archive
# Pre-2026-04-01 observations and decisions archived from SCRATCHPAD.md.
# This file is read-only history.
# Active scratchpad: SCRATCHPAD.md
---

## NON-BLOCKING Queue

### [OBS-030] `_classify_hrv_drop` converts None ACWR to 1.0 post T5-51

**Date:** 2026-03-28
**Trigger:** T-SCRATCHPAD-3 — 3+ related out-of-scope findings in one audit session
**Session context:** Pass 1 audit / Phase 8C / Subsystem: GovernanceEngine HRV classification
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/science/governance_engine.py` — `_classify_hrv_drop` lines 235–238

**Observation:**
`_classify_hrv_drop()` at line 235–238:
```python
try:
    acwr = float(context.get("acwr", 1.0))
except (TypeError, ValueError):
    acwr = 1.0
```
After T5-51 fixed DailyCoach to propagate `None` for missing ACWR, governance context may now carry `acwr=None`. `_classify_hrv_drop` converts None (and any TypeError) to 1.0.

The method then checks `if acwr > VO2_ACWR_MAX` (1.30) at line 240 to classify the drop as TRAINING_EXPLAINED. With acwr=1.0, that check fails. The HRV drop falls through to `hrv_delta` and `rhr_delta` checks. If those are also borderline, the drop may be classified as TRAINING_EXPLAINED rather than ILLNESS_PATTERN or UNEXPLAINED_MODERATE.

Impact is confined to the classification label returned by this helper; it feeds into narrative output but not directly into hard-stop gate decisions.

**Pattern / scope:**
Single method. The same ACWR default pattern (None→1.0) appears in the VO2 gate (OBS-028), `_classify_hrv_drop`, and the original pre-T5-51 DailyCoach call site. Three locations total, all now post-T5-51 carry None risk.

**Architectural question raised:**
Should `_classify_hrv_drop` treat None ACWR as "unknown explanation" (return UNKNOWN or skip classification), or default to the most conservative label? The current behaviour silently produces TRAINING_EXPLAINED when ACWR is unavailable.

**Codex assessment (data only, no decision):**
Impact appears limited to the narrative classification label (TRAINING_EXPLAINED vs ILLNESS_PATTERN), not to any gate decision. Urgency is NON-BLOCKING. However, it is the third location where None ACWR→1.0 survives after T5-51.

**Status:** REVIEWED

---

### [OBS-031] `save_daily_metric` INSERT OR REPLACE silently destroys manual field entries

**Date:** 2026-03-28
**Trigger:** T-SCRATCHPAD-3 — 3+ related out-of-scope findings in one audit session
**Session context:** Pass 1 audit / Phase 8C / Subsystem: DatabaseManager
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/core/database.py` — `save_daily_metric` line 758 (INSERT OR REPLACE semantics)

**Observation:**
`save_daily_metric` uses `INSERT OR REPLACE INTO daily_metrics ...` (line 758). INSERT OR REPLACE in SQLite deletes the existing row and inserts a new one. Any columns not explicitly provided in the new INSERT are reset to their DEFAULT values (typically NULL or 0).

If an athlete has manually entered subjective data (mood score, soreness, notes, perceived effort) into `daily_metrics` for a date, and Garmin-triggered save is called for the same date without including those manual fields, the subjective fields are silently overwritten with NULL/default.

This was identified as F-26 (MEDIUM) in OBS-025 (2026-03-22). No T5 item has been registered for it. The pattern is distinct from the INSERT OR IGNORE used elsewhere (`database.py:831` uses INSERT OR IGNORE for historical HRV, fixed by T5-61).

**Pattern / scope:**
Single call site (`save_daily_metric`). The INSERT OR IGNORE vs INSERT OR REPLACE inconsistency within the same file reflects an unresolved policy decision about data freshness vs data preservation.

**Architectural question raised:**
Should `save_daily_metric` use INSERT OR IGNORE (preserve existing manual entries), an UPSERT with per-column merge (preserve manual fields, overwrite Garmin fields), or INSERT OR REPLACE (current, overwrites all)? This is a data integrity policy decision.

**Codex assessment (data only, no decision):**
F-26 from OBS-025 was identified at MEDIUM severity. The subjective fields at risk are the primary source of athlete-reported fatigue signals. Silently overwriting them compromises the 2-of-4 gate inputs on re-sync days.

**Status:** REVIEWED

---

### [OBS-032] `sync_sleep` and `sync_hrv` emit success events after outer exception is caught

**Date:** 2026-03-28
**Trigger:** T-SCRATCHPAD-3 — 3+ related out-of-scope findings in one audit session
**Session context:** Pass 1 audit / Phase 8C / Subsystem: GarminSync observability
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/integrations/garmin_sync.py` — `sync_sleep` line 469, `sync_hrv` line 531

**Observation:**
In both `sync_sleep` and `sync_hrv`, the structured "synced" and "skip_summary" events are emitted **outside** the outer `try/except` block. If the outer except catches a fatal exception (e.g., network error mid-sync), the method still emits a success event before returning an empty list.

Pattern (both methods are identical):
```python
try:
    ... # sync logic
except Exception as e:
    _garmin_event(...)  # error event inside except
sessions = []  # or hrv_data = []
_garmin_event("synced", count=len(sessions), ...)  # ← emitted unconditionally
return sessions
```
`len([])` = 0, so the event says "synced 0 items" — technically not a lie in value, but semantically misleading because it suggests the sync completed normally rather than was aborted by an exception.

This was identified as F-03 (MEDIUM) in OBS-025. No T5 item was registered.

**Pattern / scope:**
Two methods (`sync_sleep`, `sync_hrv`). `sync_activities` and `sync_weight` follow the same structural pattern and may have the same issue.

**Architectural question raised:**
Should success events be gated on the absence of exceptions (moved inside the try block or behind a flag), or is "synced 0 items" acceptable as a terminal state regardless of cause?

**Codex assessment (data only, no decision):**
Impact is observability/telemetry correctness. SLO alerting built on "synced 0 items" events will not distinguish normal zero-activity days from exception-aborted syncs.

**Status:** REVIEWED

---

### [OBS-033] `MISSING_DATA_POLICY` ADR registered as ADR_NEEDED in DEC-025 but not yet created

**Date:** 2026-03-28
**Trigger:** T-SCRATCHPAD-3 — 3+ related out-of-scope findings in one audit session
**Session context:** Pass 1 audit / Phase 8C / Subsystem: Governance policy architecture
**Urgency:** NON-BLOCKING
**Files involved:**
- `SCRATCHPAD.md` — DEC-025 (OBS-027 response), ADR_NEEDED decision recorded 2026-03-27
- `docs/adr/` — no `MISSING_DATA_POLICY` ADR present

**Observation:**
DEC-025 (response to OBS-027, 2026-03-27) recorded:
> "NO_ACTION | `MISSING_DATA_POLICY` canonical convention (OBS-027 architectural question) — deferred; ADR_NEEDED before any policy codification"

As of this audit pass (2026-03-28), no ADR for `MISSING_DATA_POLICY` exists in `docs/adr/`. The last ADR is ADR-0050. T5-44 through T5-59 fixed individual module defaults to conservative values, but they did so independently — each module author chose their own conservative default without a shared policy document.

Consequence: future modules that introduce Garmin-sourced fields will encounter the same ambiguity (what default is conservative?) with no canonical reference. OBS-028 and OBS-030 in this batch are direct evidence that the per-module fix approach missed code paths.

**Pattern / scope:**
Systemic policy gap. Not a single-file finding. ADR_NEEDED is a precondition before the VO2 gate fixes (OBS-028) and _classify_hrv_drop fix (OBS-030) can be implemented with consistent semantics.

**Architectural question raised:**
Is the ADR for `MISSING_DATA_POLICY` a prerequisite before OBS-028 and OBS-030 can be resolved, or can those items be fixed with a conservative constant while the ADR is authored in parallel?

**Codex assessment (data only, no decision):**
The absence of this ADR is why OBS-028 was possible — the VO2 eligibility gate author had no policy to consult. Without the ADR, each new fix risks being inconsistent with the others.

**Status:** REVIEWED

---

### [OBS-034] No test coverage for VO2 eligibility gate with None ACWR or None readiness inputs

**Date:** 2026-03-28
**Trigger:** T-SCRATCHPAD-3 — 3+ related out-of-scope findings in one audit session
**Session context:** Pass 1 audit / Phase 8C / Subsystem: GovernanceEngine test surface
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/science/governance_engine.py` — `_check_vo2_eligibility_gate` lines 431–450
- `tests/test_p0_safety_gates.py` — VO2 eligibility gate tests
- `tests/test_governance_integration.py` — integration-level gate tests

**Observation:**
T5-49 added tests verifying that the **2-of-4 gate** fires correctly when sleep_score/readiness_score are absent (default 40). T5-51 added tests verifying that DailyCoach passes `None` (not `1.0`) for missing ACWR.

No test exists for the scenario: governance context carries `acwr=None` or `readiness_score=None` AND a VO2 session is planned. In that scenario, `_check_vo2_eligibility_gate` silently returns eligible (V1 + V2 pass with defaults 1.0 and 100 respectively), as documented in OBS-028.

A test constructing a governance context with `{"acwr": None, "session_type": "VO2MAX", ...}` and asserting that the gate returns ineligible (or a specific locked state) does not exist.

**Pattern / scope:**
Test gap affecting a single gate method. Structurally similar to the F-34 finding in OBS-025 (test fixtures bypassing real data paths).

**Architectural question raised:**
Should a test for OBS-028 be authored before or after the fix? If the fix requires an ADR (OBS-033), should the test be written to the to-be-defined policy, or to the current (broken) behavior as a regression marker?

**Codex assessment (data only, no decision):**
Without a test, the OBS-028 fix could be silently reverted (similar pattern to the T5-52 apparent regression in OBS-029). A test is needed to lock the corrected behavior.

**Status:** REVIEWED

---

### [OBS-035] ESI default dew_point (12.0°C) is a hardcoded magic number in daily_coach.py

**Date:** 2026-03-28
**Trigger:** T-SCRATCHPAD-3 — 3+ related out-of-scope findings in one audit session
**Session context:** Pass 1 audit / Phase 8C / Subsystem: DailyCoach ESI computation
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/orchestration/daily_coach.py` — line 713
- `titan/config/thresholds.py` — no ESI dew_point constant defined

**Observation:**
`daily_coach.py:713`:
```python
dew_point_c=_safe_float(garmin_data.get("dew_point"), 12.0),
```
When Garmin data does not include `dew_point`, `_compute_esi` receives 12.0°C. The ESI formula is `ESI = temperature_c + 0.5 * dew_point_c`. At 12.0°C dew point and 30°C air temp, ESI = 30 + 6 = 36 (HIGH). At the correct conservative default of 18.0°C (the T5-59 / `_calculate_hydration` sticky threshold), ESI = 30 + 9 = 39 (HIGH boundary). The difference is real but small.

The concern is the constant 12.0:
- Not present in `thresholds.py` or `evidence_registry.py`
- ADR-0034 governs environmental stress compensation but does not specify a "safe default dew_point" constant
- T5-59 established 25.0°C as the conservative default for NutritionOptimizer dew_point; daily_coach.py uses 12.0 for the same physical quantity in a different pipeline step

Same unconstantized-literal pattern as the findings resolved in T5-04, T5-20, and OBS-026 B1-F02.

**Pattern / scope:**
Single call site. But the inconsistency between NutritionOptimizer's 25.0°C conservative default (T5-59) and daily_coach.py's 12.0°C default for the same physical quantity (dew_point) on the ESI path is a calibration inconsistency, not just a style issue.

**Architectural question raised:**
Should a canonical `DEFAULT_DEW_POINT_C` (or `ESI_DEW_POINT_FALLBACK`) constant be added to `thresholds.py`? And should it be 12.0, 15.0, or 25.0, given that T5-59 used 25.0 for the nutrition path?

**Codex assessment (data only, no decision):**
Two different fallback values for the same physical quantity (dew_point) in the same DailyCoach pipeline (ESI: 12.0; NutritionOptimizer: 25.0) will produce internally inconsistent thermal stress assessments.

**Status:** REVIEWED

---

### [OBS-036] `garmin_activity_id` not persisted — duplicate activity detection impossible at DB layer

**Date:** 2026-03-28
**Trigger:** T-SCRATCHPAD-3 — 3+ related out-of-scope findings in one audit session
**Session context:** Pass 1 audit / Phase 8C / Subsystem: DatabaseManager / GarminSync
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/core/database.py` — `training_log` table schema, `save_session` method
- `titan/integrations/garmin_sync.py` — `sync_activities` return value
- `titan/orchestration/daily_coach.py` — `_persist_garmin_data` activity persistence path

**Observation:**
`sync_activities()` returns dicts with fields: `date`, `distance_km`, `duration_sec`, `avg_hr`, `max_hr`, `activity_type`, `trimp`. No `activity_id` (Garmin's unique activity identifier) is extracted or returned.

`database.py` `training_log` schema does not include an `activity_id` column. `save_session` has no deduplication logic based on activity identity.

Consequence: if `sync_activities(days_back=7)` is called twice in overlapping windows (e.g., a 6h re-sync and a manual /sync command), the same activity can be inserted twice into `training_log`. This inflates TSB/CTL/ATL calculations because `get_training_load_history()` reads all rows without deduplication.

T5-46 established per-date deduplication for HRV entries in `add_hrv_measurement`. No equivalent protection exists for activity records. F-28 (LOW) from OBS-025 noted the schema gap; no T5 item was registered.

**Pattern / scope:**
Two files (garmin_sync.py — no id extraction; database.py — no id column/deduplication). The pattern is analogous to the pre-T5-46 HRV deduplication gap.

**Architectural question raised:**
Should `sync_activities` extract `activityId` from the Garmin payload and `save_session` use it as a unique constraint (INSERT OR IGNORE / UPSERT), following the T5-46 HRV deduplication pattern? Or is per-date deduplication sufficient for activities?

**Codex assessment (data only, no decision):**
Duplicate activity records in `training_log` cause silent TSB/CTL/ATL inflation. A single strenuous long run double-counted would add ~50 TRIMP points to the load calculation, potentially pushing ATL above a HARD_STOP_TSB_FLOOR check falsely.

**Status:** REVIEWED

---


## NON-BLOCKING Queue

### [OBS-008] Scratchpad continuation rule conflicts with stop rule

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — §15 intro states global stop after writing OBS
- `AGENTS.md` — T-SCRATCHPAD-3 explicitly permits continuation of current subtask
- `SCRATCHPAD.md` — Document status guidance describes stop/wait behaviour

**Observation:**
The protocol contains conflicting execution guidance after writing an OBS. `AGENTS.md` §15 states that after writing an OBS, Codex sets `STATUS: REVIEW_REQUESTED` and stops until cleared. In the same section, trigger T-SCRATCHPAD-3 states Codex may continue the current task and only blocks new top-level tasks. `SCRATCHPAD.md` status guidance also frames `REVIEW_REQUESTED` as a stop/wait gate for new task assignment, which creates ambiguity about whether in-flight execution must halt immediately.

References: AGENTS.md:884-885, AGENTS.md:929-931, SCRATCHPAD.md:26-31.

**Pattern / scope:**
Process-state semantics for `REVIEW_REQUESTED` are defined across multiple sections and are not fully consistent. This affects all future OBS usage, not a single task.

**Architectural question raised:**
For `STATUS: REVIEW_REQUESTED`, is Codex required to stop all in-flight work immediately, or only prohibited from starting a new top-level task?

**Codex assessment (data only, no decision):**
Current wording permits two valid but different operator interpretations, which can produce inconsistent behaviour between sessions.

**Status:** REVIEWED

### [OBS-009] Enforcement burden concentrated in manual checklist discipline

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — §11 pre-delivery checklist with 29 manual confirmations
- `AGENTS.md` — §2 and HARD GATE define mandatory sequencing and prohibitions
- `SCRATCHPAD.md` — protocol requires status transitions and queue discipline

**Observation:**
Large parts of workflow acceptance depend on manual self-attestation rather than explicit automated gates. The process requires 29 checklist assertions and multiple sequencing rules, but only a subset are mechanically enforced by executable commands. Several obligations (scope declaration completeness, task-learning block presence, some status semantics, and protocol narrative conformance) rely on procedural adherence.

References: AGENTS.md:566-585, AGENTS.md:45-63, SCRATCHPAD.md:14-31.

**Pattern / scope:**
This is systemic and spans task start, implementation, validation, and closure stages.

**Architectural question raised:**
Which workflow obligations are intended to be hard-enforced by automation versus treated as manual governance requirements?

**Codex assessment (data only, no decision):**
Reliability of process compliance currently depends on operator consistency for multiple high-frequency steps.

**Status:** REVIEWED

### [OBS-010] Architect approval is a single-point workflow bottleneck

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — scratchpad protocol requires stop for review/clear events
- `SCRATCHPAD.md` — Claude-only ownership of DEC and status transitions to IDLE/CLEARED

**Observation:**
The framework serializes progression through architect-controlled review checkpoints. Codex records OBS entries but cannot clear them, while Claude is the only actor who can process DEC decisions and move status back to `IDLE`/`CLEARED`. This creates a single-point dependency for workflow continuation whenever review status is raised.

References: AGENTS.md:884-885, AGENTS.md:901-903, SCRATCHPAD.md:4, SCRATCHPAD.md:20-31.

**Pattern / scope:**
Applies to all trigger paths that set `REVIEW_REQUESTED`, with stronger effect if observation frequency increases.

**Architectural question raised:**
Is the current architect-only clearance model intended to remain strictly serialized under concurrent task load?

**Codex assessment (data only, no decision):**
Throughput for multi-task execution is coupled to architect review latency at each review-requested checkpoint.

**Status:** REVIEWED

### [OBS-011] Mandatory full-suite repetition introduces scaling pressure

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow framework reliability review / Process governance
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — HARD GATE requires strict + full pytest runs for every deliverable
- `AGENTS.md` — §2 canonical sequence requires rerun of all gates after any failure

**Observation:**
The acceptance model mandates two full-suite pytest executions per task (`-W error::pytest.PytestWarning` and canonical full run), plus complete re-execution after any single gate failure. As suite size grows, this imposes compounding validation cost per change and increases queue time before commit/PR eligibility.

References: AGENTS.md:45-63, AGENTS.md:153-170.

**Pattern / scope:**
System-wide effect on all tasks; cost grows with total test count and with concurrent branch activity.

**Architectural question raised:**
Is full-suite dual-run on every task intended to remain unchanged at larger suite sizes and higher parallel development volume?

**Codex assessment (data only, no decision):**
Current gate design prioritizes consistency, but it also creates predictable scaling pressure in large-suite/high-concurrency conditions.

**Status:** REVIEWED


### [OBS-012] Out-of-scope routing split between debt register and scratchpad

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Governance consistency / Cross-document correlation
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — §3.4 and §12.2 require Codex to add out-of-scope findings directly to `TECHNICAL_DEBT.md`
- `AGENTS.md` — §15 defines scratchpad as Codex→Claude observation channel with architect decision handoff
- `SCRATCHPAD.md` — purpose/lifecycle state Claude converts OBS into debt tasks
- `CLAUDE.md` — Engineering Rules map E8 points to direct debt-register route

**Observation:**
The framework defines two different routing paths for out-of-scope findings. One path requires Codex to directly create `TECHNICAL_DEBT.md` entries (`AGENTS.md` §3.4 and §12.2). The other path frames Codex as observation-only and assigns debt conversion decisions to Claude through DEC processing in `SCRATCHPAD.md` and AGENTS §15. `CLAUDE.md` rule map also points to direct debt-entry behaviour (E8), reinforcing one branch of the split.

References: AGENTS.md:292-294, AGENTS.md:616-622, AGENTS.md:877-885, SCRATCHPAD.md:4-7, SCRATCHPAD.md:69-77, CLAUDE.md:182.

**Pattern / scope:**
This appears as a repeated governance seam across all out-of-scope handling touchpoints (policy section, closure section, scratchpad protocol, and rule index). It is not isolated to one subsection.

**Architectural question raised:**
For out-of-scope findings, which route is canonical in active operation: direct `TECHNICAL_DEBT.md` creation by Codex, or observation-first escalation through `SCRATCHPAD.md` with architect conversion?

**Codex assessment (data only, no decision):**
Parallel routing instructions can produce inconsistent execution records across sessions (some findings captured as debt items immediately, others only as OBS), reducing governance trace consistency.

**Status:** REVIEWED

### [OBS-013] Debt-clear enforcement signal is non-executable in session-start gate

**Date:** 2026-03-09
**Trigger:** User-requested engineering workflow reliability review
**Session context:** Workflow reliability / Early drift detection
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — SESSION_START mandates S1–S5 checklist
- `AGENTS.md` — §12.5 states Codex MUST report debt-clear counter via S2b signal
- `AGENTS.md` — S2b snippet outputs open debt count while counter is tracked manually by architect

**Observation:**
The debt-clear window introduces a mandatory counter-reporting requirement, but the executable session-start checklist does not include S2b, and the provided S2b command does not compute the counter itself. The snippet prints only open debt count and explicitly delegates counter tracking to manual architect reading of the tracking table.

References: AGENTS.md:128-138, AGENTS.md:658-669.

**Pattern / scope:**
This is a false-confidence pattern: a requirement is phrased as mandatory and signaled by a command, but enforcement remains manual. The same pattern can recur in other policy areas where command snippets expose only proxies.

**Architectural question raised:**
Is debt-clear counter compliance intended to be a strict executable gate at session start, or an informational/manual governance check outside codified gate enforcement?

**Codex assessment (data only, no decision):**
Because the counter is not produced by a deterministic command in the mandatory startup sequence, sessions can claim compliance while applying different manual interpretations.

**Status:** REVIEWED


### [OBS-014] Process MUST-rules exceed machine-enforced governance checks

**Date:** 2026-03-09
**Trigger:** User-requested engineering framework enforcement audit
**Session context:** Governance QA / Documentation-to-enforcement consistency
**Urgency:** NON-BLOCKING
**Files involved:**
- `AGENTS.md` — defines mandatory startup/session checks, hard-gate sequencing, and 29-item pre-delivery checklist
- `scripts/check_scratchpad.sh` — enforces BLOCKING queue only, while REVIEW_REQUESTED/UNDER_REVIEW remain advisory exit 0
- `tests/test_claude_md_integrity.py` — enforces selected CLAUDE.md integrity invariants only
- `tests/test_documentation_consistency.py` — enforces selected documentation drift invariants only

**Observation:**
The governance contract contains many MUST-level process obligations that do not have a corresponding executable guard. Examples include the mandatory SESSION_START S1–S5 protocol, first-response reporting requirement, complete pre-delivery checklist assertions, and PR scope-declaration completeness. The current executable controls verify a narrower subset: lint/test gates, selected documentation integrity invariants, and BLOCKING scratchpad queue detection. `scripts/check_scratchpad.sh` returns non-blocking exit code 0 for `REVIEW_REQUESTED`/`UNDER_REVIEW`, and there is no test that validates session-start command execution, checklist completion, or PR-body conformance.

References: AGENTS.md:130-146, AGENTS.md:560-587, AGENTS.md:247-259, scripts/check_scratchpad.sh:29-58, tests/test_claude_md_integrity.py:25-159, tests/test_documentation_consistency.py:129-196.

**Pattern / scope:**
System-wide process-enforcement gap between policy text and executable verification surface. This affects all sessions and all task closures, not a single subsystem.

**Architectural question raised:**
Which MUST-level workflow obligations are intentionally manual governance duties versus intended hard gates with deterministic enforcement evidence?

**Codex assessment (data only, no decision):**
Process rigor appears stronger in policy wording than in currently automated checks; compliance for several high-importance obligations depends on operator self-attestation.

**Status:** REVIEWED

---

### [OBS-015] Phase 8B retrospective — D6 status gap in T5-08-B closure record

**Date:** 2026-03-16
**Trigger:** T-SCRATCHPAD-4 — Phase Retrospective (Phase 8B close)
**Session context:** Phase 8B closure / Architect Instructions 2026-03-16
**Urgency:** NON-BLOCKING
**Files involved:**
- `TECHNICAL_DEBT.md` — T5-08-B status block (line 1613) and resolution summary table (line 2938)
- `titan/core/persistence.py` — `get_database_manager()` with `TITAN_DB_BACKEND` env var (line 122)
- `titan/core/database.py` — original `get_database_manager()` with `TITAN_DB_BACKEND` env var (line 1975)

**Observation:**
Phase 8B closed the following Tier 5 items: T5-08-B (RESOLVED 2026-03-15), T5-09 (RESOLVED
2026-03-16), T5-11 (RESOLVED 2026-03-15), T5-13 (RESOLVED 2026-03-16), T5-14 (RESOLVED
2026-03-16), T5-16-A (RESOLVED 2026-03-15), T5-17 through T5-35 threshold burn-down (RESOLVED
2026-03-14), T5-25 (RESOLVED 2026-03-15), T5-36 (RESOLVED 2026-03-15), T5-37 (RESOLVED
2026-03-15), T5-38 (RESOLVED 2026-03-15). Also: T4-27-C (RESOLVED 2026-03-15), T5-06-A
(RESOLVED 2026-03-15). ADR-0049 accepted; AGENTS.md §18–§22 added.

**D6 status verification (explicit, per architect instruction):**
T5-08-B tracking table (TECHNICAL_DEBT.md line 1630) records D6 as `✓ DONE (T5-08)`. The
T5-08-B status body (line 1613) lists "D6 DONE (T5-08)" in the closure claim. However, the
resolution summary table (line 2938) lists only: D1, D2a, D2b, D2c, D3, D4, D5, D7, D9 —
**D6 is absent from the summary table**. Code verification: `get_database_manager()` in
`titan/core/database.py:1975` and `titan/core/persistence.py:122` both implement
`TITAN_DB_BACKEND` env-var switching. D6 (the feature flag) is therefore present in both
locations. However, D6 was completed as part of T5-08 (scaffold commit 54e95d9), not T5-08-B.
T5-08-B's deliverable table carried D6 as a pre-existing ✓ DONE reference only. The closure
body erroneously included "D6 DONE (T5-08)" in a list framed as "All deliverables complete" —
implying D6 was a T5-08-B deliverable — when it was not. The resolution summary table omits D6
correctly (D6 was not a T5-08-B implementation deliverable).

**Pattern / scope:**
Isolated to the T5-08-B closure record. The inconsistency is between the status body (which
includes D6 in the "all deliverables" list) and the resolution summary table (which excludes
D6, correctly). D6 itself is implemented and verified. The gap is a records-accuracy issue, not
a functional gap.

**Architectural question raised:**
Should the T5-08-B closure claim be corrected to read "D1, D2a/b/c, D3, D4, D5, D7, D9 —
RESOLVED 2026-03-15; D6 was a T5-08 deliverable (pre-T5-08-B), not a T5-08-B implementation
deliverable"? The resolution summary table already reflects this correctly; only the status
body needs alignment.

**Codex assessment (data only, no decision):**
D6 is functionally present and correct. The inconsistency is a records-accuracy issue: the
status body claims "D6 DONE (T5-08)" as part of "All deliverables complete," which conflates
the pre-existing D6 (from T5-08) with T5-08-B's own deliverables. The resolution summary
table (line 2938) is the more accurate record; the status body should be aligned with it.

**Status:** REVIEWED

---

### [OBS-007] Task closure declared RESOLVED without verifying ADR deliverable checklist

**Date:** 2026-03-08
**Trigger:** QA FAIL on T5-08 (Opus QA verdict) — ADR scope vs implementation drift
**Session context:** T5-08 / Phase 8A / PostgreSQL migration scaffold
**Urgency:** NON-BLOCKING
**Files involved:**
- `TECHNICAL_DEBT.md` — T5-08 entry (status was RESOLVED, now corrected to PARTIAL)
- `docs/adr/0044-postgresql-migration-phase8a-entry-gate.md` — D1–D9 deliverable table
- `titan/core/database.py` — scaffold implementation (commit 54e95d9)

**Observation:**
T5-08 was declared ✅ RESOLVED in `TECHNICAL_DEBT.md` (commit 54e95d9, 2026-03-08) without
verifying that ADR-0044 deliverables D1–D9 were complete. The implementation delivered:
- D6 (feature flag `TITAN_DB_BACKEND`) ✓
- Backend parity tests for CTL/ATL and governance persistence ✓

But D1–D5, D7–D9 were not implemented: no `persistence.py`, no `alembic/`, no `athlete_id`
columns, no RLS, no `consent_log`, no `pg_dump` backup. The acceptance gate in the task entry
referenced `persistence.py`, `alembic/`, and `tests/test_athlete_rls_isolation.py` — none of
which existed at closure time. The gate was not run; status was set by assertion.

**Pattern / scope:**
Isolated to T5-08 closure. No other task shows evidence of this pattern in the current
Phase 8 queue. However, T5-08 is the first task in Phase 8 that references an ADR with an
explicit numbered deliverable table (D1–D9). Future tasks with similar ADR deliverable tables
(T5-08-B, T5-09, T5-11, T5-13, T5-16-A) carry the same risk.

**Architectural question raised:**
Should a mandatory ADR Deliverable Checklist be part of the task closure protocol — requiring
each ADR-referenced deliverable to be checked off (✓ done / ✗ not done) before status is set
to RESOLVED — to prevent recurrence of ADR scope vs implementation drift?

**Codex assessment (data only, no decision):**
The drift was detectable at closure time: the acceptance gate referenced files that did not
exist. The process had no mechanism to catch this — the gate was written but not enforced.
The proposed checklist would make the drift structurally visible before the closure commit.

**Status:** REVIEWED

---

<!-- REVIEWED entries moved to Archive — 2026-03-08 -->
<!-- OBS-004/005/006 written by architect (Claude) 2026-03-08 — future tripwires for Phase 8 entry events -->

### [OBS-004] Governance engine instantiation semantics under CoachingScheduler

**Date:** 2026-03-08
**Trigger:** Architect-originated future tripwire (Phase 8 risk pre-registration)
**Session context:** Phase 8 / ADR-0046 multi-athlete execution model (T5-16 closed)
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/orchestration/daily_coach.py` — current single-athlete instantiation model
- `tests/test_athlete_isolation_invariant.py` — profile-level isolation guard (existing)
- ADR-0046 — CoachingScheduler + stateless coaching_pipeline design

**Observation:**
`test_athlete_isolation_invariant.py` verifies that athlete profile data (DB reads,
metrics) does not bleed between athletes. It does not verify that engine instances
(e.g. `GovernanceEngine`, `HRVEngine`) are instantiated per-athlete-run rather than
shared across runs. If `CoachingScheduler` reuses engine instances between athlete
coaching cycles, cached intermediate state within an engine could produce cross-athlete
contamination that bypasses the existing profile isolation test.

**Pattern / scope:**
Isolated risk point — becomes concrete only when CoachingScheduler implementation begins.
Current single-athlete model has no analogous risk. Pattern does not yet exist in code.

**Architectural question raised:**
When CoachingScheduler is implemented, will engine instances be created fresh per
athlete-run (safe), or shared/pooled across runs (requires explicit stateless proof)?

**Codex assessment (data only, no decision):**
Not applicable — this OBS is architect-originated. No code has been written yet for
the multi-athlete scheduler. The question is a design-time invariant to enforce at
implementation time.

**Status:** REVIEWED

---

### [OBS-005] Concurrency semantics delta at PostgreSQL migration boundary

**Date:** 2026-03-08
**Trigger:** Architect-originated future tripwire (Phase 8 risk pre-registration)
**Session context:** Phase 8 / ADR-0044 PostgreSQL migration gate
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/core/database.py` — `threading.Lock` + `check_same_thread=False` concurrency model
- `tests/test_database_manager_thread_safety.py` — SQLite-specific threading tests
- `tests/test_harden_db_concurrency.py` — SQLite-specific concurrency stress tests
- ADR-0044 — PostgreSQL migration as Phase 8A entry gate

**Observation:**
The current concurrency model (`threading.Lock` + `check_same_thread=False`) is
SQLite-specific. Existing threading tests verify correctness of this model against
SQLite semantics. When the PostgreSQL migration task opens, a new database layer will
be introduced with fundamentally different concurrency semantics (connection pooling,
different transaction isolation, no `check_same_thread` concept). The existing tests
will continue to pass against the SQLite code path but will not exercise the new
PostgreSQL layer. No current test covers PostgreSQL connection pool behaviour under
concurrent writes.

**Pattern / scope:**
Isolated to the database adapter boundary. Will not manifest until the PostgreSQL
migration task opens. The gap is structural: two code paths will exist simultaneously
during migration, with only one covered by concurrency tests.

**Architectural question raised:**
When the PostgreSQL migration task opens, should concurrency validation tests for the
new adapter be an explicit acceptance criterion in the task definition, to prevent
the threading tests from providing false coverage confidence?

**Codex assessment (data only, no decision):**
Not applicable — architect-originated. The observation is a pre-registration of a
known structural gap that becomes active at migration task start.

**Status:** REVIEWED

---

### [OBS-006] OperatorConsole payload round-trip serialization gap at FastAPI boundary

**Date:** 2026-03-08
**Trigger:** Architect-originated future tripwire (Phase 8 risk pre-registration)
**Session context:** Phase 8 / ADR-0013 Operator Console technology path (React + FastAPI)
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/ui/operator_console.py` — `OperatorConsoleService` payload construction
- `tests/test_operator_console_dashboard.py` — payload shape tests (Python dict assertions)
- ADR-0013 — Streamlit → React + FastAPI technology path (Accepted)

**Observation:**
`test_operator_console_dashboard.py` verifies payload contracts as Python dict shapes.
These tests run entirely within Python and do not exercise JSON serialization. When the
FastAPI layer is introduced, payloads will pass through `json.dumps` / Pydantic
serialization. Python types without a direct JSON equivalent (`datetime`, `Decimal`,
`Enum`, `None` in typed fields) may be silently coerced or dropped. The existing
tests will continue to pass (Python-side only) while the API-side contract is broken.
No round-trip serialization test (Python dict → JSON → dict → assert) currently exists.

**Pattern / scope:**
Isolated to the OperatorConsole payload boundary. Becomes concrete when FastAPI
implementation begins. The guard needed is a round-trip test per payload type
(dashboard, session explorer, override workflow, calibration review).

**Architectural question raised:**
When the FastAPI implementation task opens, should round-trip serialization tests
for all four payload types be an explicit acceptance criterion, to prevent the
existing dict-shape tests from providing false coverage confidence?

**Codex assessment (data only, no decision):**
Not applicable — architect-originated. The observation is a pre-registration of a
known gap that becomes active at FastAPI task start.

**Status:** REVIEWED

---

### [OBS-001] Test suite has no pytest layer markers

**Date:** 2026-03-08
**Trigger:** T-SCRATCHPAD-3 — future maintenance observations submitted by engineer
**Session context:** Phase 8 / CI safeguards post-review
**Urgency:** NON-BLOCKING
**Files involved:**
- `pyproject.toml` — markers config: only `timeout` defined, no `unit`/`integration`/`governance`
- `tests/` — 105 test files; `test_*.py` root — 13 files; no `@pytest.mark.unit` etc. in use

**Observation:**
The test suite (118 files, ~1780+ tests) has grown substantially across Phase 0–8.
Test categorisation is done only by filename convention (e.g. `test_governance_integration.py`,
`test_p0_safety_gates.py`). No pytest marks for layer (unit / integration / governance / invariant)
are registered or applied. `pyproject.toml` defines only `markers = ["timeout: ..."]`.

**Pattern / scope:**
Isolated to the test infrastructure configuration — no individual test file is responsible.
The pattern is uniform across all ~118 test files.

**Architectural question raised:**
Should a formal marker taxonomy (e.g. `unit`, `integration`, `governance`) be registered and
applied to all existing tests to enable selective execution and faster failure diagnostics?

**Codex assessment (data only, no decision):**
Without markers, `pytest -m governance` is impossible. When a governance gate test fails, the
developer must scan filename-by-filename to identify test layer. As the suite grows beyond 2000
tests this will slow diagnostics. Impact is currently low but increases proportionally with suite size.

**Status:** REVIEWED

---

### [OBS-002] Doc-integrity regex patterns tightly coupled to exact markdown wording

**Date:** 2026-03-08
**Trigger:** T-SCRATCHPAD-3 — future maintenance observations submitted by engineer
**Session context:** Phase 8 / CI safeguards post-review
**Urgency:** NON-BLOCKING
**Files involved:**
- `tests/test_claude_md_integrity.py` — 6+ regex patterns against exact markdown formatting

**Observation:**
`test_claude_md_integrity.py` uses patterns that require exact markdown surface form:
- `r"Main package \((\d+) modules, excl\. __init__/__main__\)"` — exact phrase in CLAUDE.md
- `r"^- `([0-9]{4})`"` — requires backtick-wrapped ADR IDs in a specific list format
- `r"\*\*Historical snapshot:\*\*\s*(\d+) tests all green"` — exact bold wording
- `r"\|\s*`docs/ROADMAP\.MD`\s*\|([^\|]+)\|"` — table cell format for ROADMAP row
- `r"^Phase (\S+) OPEN\b"` in TECHNICAL_DEBT.md — requires "Phase N OPEN" at line start

A legitimate doc reformatting (e.g. renaming "Main package" → "Core package" for clarity,
or switching ADR list from backtick to plain text) would produce a CI failure even if the
information is factually unchanged.

**Pattern / scope:**
6 patterns in a single file. Isolated, not replicated elsewhere.

**Architectural question raised:**
Is this brittleness an acceptable trade-off of the integrity test design, or should a schema
layer (e.g. YAML frontmatter, or a structured CLAUDE.md section) replace the fragile regex?

**Codex assessment (data only, no decision):**
The tests are effective exactly because they are tight — loosening them reduces their ability
to catch real drift. The brittleness risk is real but the formatting of these doc sections
has been stable since they were introduced. No false positive has been observed to date.

**Status:** REVIEWED

---

### [OBS-003] Documentation snapshot drift already substantially automated

**Date:** 2026-03-08
**Trigger:** T-SCRATCHPAD-3 — future maintenance observations submitted by engineer
**Session context:** Phase 8 / CI safeguards post-review
**Urgency:** NON-BLOCKING
**Files involved:**
- `tests/test_claude_md_integrity.py` — 5 automated drift guards already implemented

**Observation:**
`test_claude_md_integrity.py` contains the following automated snapshot-drift guards:
1. `test_adr_count_in_claude_md_matches_files` — ADR list vs actual ADR files in `docs/adr/`
2. `test_module_count_in_claude_md_matches_filesystem` — declared titan module count vs `rglob`
3. `test_historical_snapshot_matches_full_suite_collection` — CLAUDE.md test count vs collected
4. `test_key_files_section_points_to_existing_paths` — all `Key Files` paths exist on disk
5. `test_phase_state_label_consistent_between_tech_debt_and_claude_md` — phase OPEN/CLOSED parity

**Pattern / scope:**
Isolated finding. The concern raised (snapshot drift) is already the primary purpose of this file.

**Architectural question raised:**
Is there a residual snapshot-drift gap not covered by the existing 5 guards that warrants a
new automated check, or is the current coverage sufficient for Phase 8?

**Codex assessment (data only, no decision):**
No specific gap has been identified. The concern appears to be a general "keep this pattern going"
observation rather than identification of a concrete uncovered risk.

**Status:** REVIEWED

---


### [OBS-016] Phase 8B retrospective coverage + D6 verification

**Date:** 2026-03-16
**Trigger:** T-SCRATCHPAD-4 — Phase Retrospective (Phase 8B close)
**Session context:** Phase 8B retrospective audit-only pass
**Urgency:** NON-BLOCKING
**Files involved:**
- `TECHNICAL_DEBT.md` — Phase 8B closure records, open/deferred carry-overs, and timeline notes
- `SCRATCHPAD.md` — Phase retrospective OBS log
- `titan/core/database.py` — factual verification target for T5-08-B D6 feature-flag implementation
- `titan/core/persistence.py` — factual verification target for T5-08-B D6 feature-flag implementation

**Observation:**
Phase 8B closed-item retrospective (root cause / what each item fixed):
- Itemization note: `T5-17` through `T5-35` are intentionally enumerated individually below (no grouped burn-down cluster line in this OBS).
- **T5-08-B:** Phase 8 blocked on incomplete PostgreSQL migration path; this item completed adapter parity, Alembic migration chain, RLS/consent schema wiring, and closure gating records for migration readiness.
- **T5-09:** No unified athlete-context seam existed; this item added a single `get_athlete_context()` query contract to prevent duplicated multi-query assembly.
- **T5-11:** API endpoints lacked authentication/authorization; this item implemented JWT auth, role checks, and endpoint protection for health-data access control.
- **T5-13:** Coach actions were not auditable; this item added coach audit trail coverage for accountability on health-data processing actions.
- **T5-14:** Environmental compensation thresholds were not externalized; this item extracted/standardized ESI overlay threshold handling into governed config usage.
- **T5-16-A:** DailyCoach multi-athlete state-isolation guardrails were under-specified; this item fixed execution-model contract and state isolation acceptance criteria.
- **T5-17:** ACWR thresholds were hardcoded in-module; this item centralized those constants into `thresholds.py`.
- **T5-18:** Adaptive Memory Category-A thresholds were inline; this item moved the governed constants to `thresholds.py` while preserving category boundaries.
- **T5-19:** Adaptive Memory multiplier constants lacked category classification; this item closed the ambiguity by classifying them Category-B (NO_ACTION for extraction).
- **T5-20:** APL integration coverage was missing for DailyCoach argument wiring; this item added/closed the resolve-contract integration test gap.
- **T5-21:** Athlete profile IDs risked timestamp collision; this item hardened identifier generation to prevent same-timestamp collisions.
- **T5-22:** Athlete profile serialization omitted `weight_ceiling`/`weight_panic`; this item fixed round-trip field parity.
- **T5-23:** Autonomic fusion documentation claimed an incorrect range; this item corrected the contract documentation to match implemented formula bounds.
- **T5-24:** Biomechanics orchestration contract was typed as `object`; this item resolved the contract typing gap with explicit orchestration-facing typing.
- **T5-25:** PersistenceAdapter SQLite/PostgreSQL behavior classes were undocumented; this item delivered the parity matrix artifact used by migration closure controls.
- **T5-26:** Drift engine lacked a public `analyze_cardiac_drift` wrapper; this item closed the API-surface contract gap.
- **T5-27:** Durability-engine Category-A thresholds were hardcoded; this item centralized those thresholds in `thresholds.py`.
- **T5-28:** Fatigue soreness threshold remained inline; this item moved it to governed threshold configuration.
- **T5-29:** Garmin live sync had inconsistent partial-failure policy semantics for sleep/HRV paths; this item aligned the policy contract.
- **T5-30:** Governance-engine class-local thresholds diverged from central config; this item centralized those values into `thresholds.py`.
- **T5-31:** Intensity-governor thresholds were inline literals; this item centralized them under governed thresholds.
- **T5-32:** Lactate-logic thresholds were inline literals; this item centralized those constants in `thresholds.py`.
- **T5-33:** Periodization/Automated coupling concern lacked a justified remediation path; this item triaged and closed it as NO_ACTION with documented rationale.
- **T5-34:** Setup wizard had dual-bootstrap contract divergence between titan and launcher paths; this item aligned bootstrap contract behavior.
- **T5-35:** Volume-load-gauge thresholds were inline literals; this item centralized them in `thresholds.py`.
- **T5-36:** Phase 8B API had no authenticated rate limiting; this item implemented per-user/per-role limiting to close DoS exposure.
- **T5-37:** Deterministic validation findings were not converted into CI gates; this item recorded the CI hardening debt lane for governance automation follow-through.
- **T5-38:** CI hardening gates lacked validating meta-tests; this item recorded the paired validation debt lane for T5-37 gate reliability.

Out-of-scope findings added during Phase 8B (T-ref + one-line summary):
- **T5-36:** API rate-limiting gap identified during auth records pass; registered as separate DoS-risk debt entry.
- **T5-37:** Opus QA scope-reduction process identified Category A findings that must become CI-enforced gates.
- **T5-38:** Need for meta-tests to validate newly added CI gates was identified as a distinct follow-up finding.

Findings added but not yet triaged:
- No un-triaged Phase 8B out-of-scope finding is recorded in `SCRATCHPAD.md` as PENDING with missing architect DEC; however, in the debt register, **T5-12** remains OPEN with mitigation-design deferral to Phase 8C (not yet implementation-triaged).

Potential Phase 8C incompleteness pattern (factual):
- Phase 8B produced multiple late-registered follow-up debt items from audit/records passes (T5-36/T5-37/T5-38), indicating that closure-adjacent review continues to surface scope-critical controls after core implementation completes.

Explicit verification note for **T5-08-B D6** (factual only):
- D6 (`TITAN_DB_BACKEND` backend-switch feature flag) is implemented in:
  - `titan/core/database.py` via `get_database_manager()`
  - `titan/core/persistence.py` via `get_database_manager()`
- D6 is documented as a **T5-08 pre-existing deliverable** carried in T5-08-B records, not a T5-08-B implementation deliverable.
- This retrospective records only verification facts and does not open a new implementation lane.

**Pattern / scope:**
Phase 8B closure evidence is internally consistent for implemented deliverables; residual risk concentration sits in deferred/open entries and in findings discovered during records/audit passes near closure.

**Architectural question raised:**
Should the Phase 8C planning list be re-baselined against the late-discovery pattern (T5-36/T5-37/T5-38 + T5-12 open deferral) before sequencing implementation lanes?

**Codex assessment (data only, no decision):**
The data indicates Phase 8B closure was functionally complete for shipped items, but the timing of follow-up finding registration suggests the Phase 8C candidate list may not yet be exhaustive.

**Status:** REVIEWED

### [OBS-017] Evidence registry includes out-of-contract parameter set

**Date:** 2026-03-16
**Trigger:** Architect-authorized bounded audit/records correction pass (`titan/config/`)
**Session context:** Audit-only pass 1 / Subsystem: `titan/config/`
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/config/evidence_registry.py` — declares one-entry-per-`thresholds.py` contract and stores registry entries
- `titan/config/thresholds.py` — canonical threshold constant set used as registry reference target

**Observation:**
`evidence_registry.py` declares that every constant in `thresholds.py` has a corresponding registry entry and labels the registry section as "one entry per constant in thresholds.py". In the same file, eight `PHYS_BOUNDS_*` entries are included inside `EVIDENCE_REGISTRY` while no `PHYS_BOUNDS_*` constants exist in `thresholds.py`; `thresholds.py` defines governance/safety constants and lock codes but not this prefix family.

File-local evidence:
- Contract statement and registry framing: `evidence_registry.py` lines 4 and 55.
- Additional registry keys: `evidence_registry.py` lines 416, 431, 446, 461, 476, 490, 504, 518.
- Bounds note says runtime location is elsewhere (`titan/science/physiological_bounds.BOUNDS`): `evidence_registry.py` lines 410-412.
- No `PHYS_BOUNDS_*` symbol family appears in `thresholds.py` (module lines 1-135).

**Pattern / scope:**
Isolated to the bounded config scope in this pass: contract wording in the evidence registry and the concrete key-set composition of `EVIDENCE_REGISTRY` are not aligned 1:1 with the symbol family present in `thresholds.py`.

**Architectural question raised:**
Should `EVIDENCE_REGISTRY` be treated as a strict mirror of `thresholds.py` constants only, or as a broader provenance registry that may include non-threshold runtime bounds sourced from other modules?

**Codex assessment (data only, no decision):**
Observed key-set composition indicates mixed provenance scope in a registry documented as thresholds-only; this creates contract-interpretation ambiguity for future audit/automation checks that assume strict parity.

**Status:** REVIEWED


### [OBS-018] Governance modules lack mirrored `tests/titan/science/` test files

**Date:** 2026-03-16
**Trigger:** Architect-authorized bounded audit pass 2 (`titan/science/governance_*.py`)
**Session context:** Audit-only / observer-only / execution unit: governance-scoped science modules
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/science/governance_engine.py` — audited governance module in scope
- `titan/science/governance_contracts.py` — audited governance module in scope
- `tests/test_governance_integration.py` — current governance coverage located outside mirrored `tests/titan/science/` layout
- `tests/test_governance_mutation.py` — current governance coverage located outside mirrored `tests/titan/science/` layout
- `AGENTS.md` — defines mirrored test-file requirement for changed modules

**Observation:**
Within the scoped governance modules, no mirrored test files are present under `tests/titan/science/` for either `governance_engine.py` or `governance_contracts.py` (expected mirrored names: `test_governance_engine.py`, `test_governance_contracts.py`). Existing governance-focused tests are present in top-level test files (`tests/test_governance_integration.py`, `tests/test_governance_mutation.py`) rather than mirrored module-path locations.

References: AGENTS.md:10-14, titan/science/governance_engine.py:1-2, titan/science/governance_contracts.py:1-3, tests/test_governance_integration.py:1-2, tests/test_governance_mutation.py:1-3, tests/titan/science/test_tsb_engine.py:6-7, tests/titan/science/test_override_signal.py:5.

**Pattern / scope:**
Single finding for this execution unit: test-placement contract mismatch specific to governance-scoped modules in `titan/science/governance_*.py`.

**Architectural question raised:**
For governance-scoped modules, should the mirrored-path requirement be enforced strictly at `tests/titan/science/test_<module>.py` even when substantial governance coverage exists in non-mirrored top-level test files?

**Codex assessment (data only, no decision):**
The observed placement creates a contract-interpretation ambiguity between documented mirrored-test policy and current governance test-file layout.

**Status:** REVIEWED


### [OBS-019] ML explainability module path is stale/ambiguous

**Date:** 2026-03-16
**Trigger:** Architect-authorized bounded audit pass (Audit Pass 3 correction lane)
**Session context:** Audit Pass 3 / audit-only / observer-only / execution unit: `titan/science/` ML modules
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/science/ml_safety.py` — contains the shared `ExplainableOutput` contract
- `titan/science/injury_risk_model.py` — consumes explainability contract and builds explainability payloads
- `tests/test_ml_explainability.py` — explainability test file name points to a module path not present in the scoped module list
- `TECHNICAL_DEBT.md` — records a prior deliverable statement that names `titan/science/ml_explainability.py`

**Observation:**
Within this execution unit, the scoped module list includes `titan/science/ml_explainability.py`, but no such file is present in `titan/science/`. Explainability behaviour is currently implemented across `ml_safety.py` and `injury_risk_model.py` (`ExplainableOutput` definition in `ml_safety.py`; explainability payload construction in `injury_risk_model.py`), while the test file is still named `tests/test_ml_explainability.py` and validates injury-risk explainability through `InjuryRiskEnsembleModel` rather than a dedicated `ml_explainability` module. The debt/register record for T5-06-A also names `titan/science/ml_explainability.py` as if it exists.

References: titan/science/ml_safety.py:13-21, titan/science/injury_risk_model.py:13,145-170, tests/test_ml_explainability.py:1, TECHNICAL_DEBT.md:1448,1464-1477.

**Pattern / scope:**
Single finding in this pass: module-path identity for explainability is inconsistent across scoped file list, implementation locations, test naming, and debt/register wording.

**Architectural question raised:**
For the ML explainability contract, what is the architect-approved canonical module boundary and naming contract (`ml_explainability.py` as a dedicated module vs explainability hosted in existing ML modules)?

**Codex assessment (data only, no decision):**
Observed artifacts indicate a stale/ambiguous module-path contract that can cause audit/test-routing ambiguity in subsequent bounded passes.

**Status:** REVIEWED

### [OBS-020] AdaptivePriorityLock threshold source contract is ambiguous

**Date:** 2026-03-16
**Trigger:** Architect-authorized bounded audit pass 4 (`titan/science/` remaining modules)
**Session context:** Audit Pass 4 / audit-only / observer-only / execution unit: remaining science modules (non-governance, non-ML lane)
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/science/adaptive_priority_lock.py` — defines default/override gate thresholds used for priority-vector output
- `titan/config/thresholds.py` — canonical threshold registry used by science modules

**Observation:**
`adaptive_priority_lock.py` declares that its `_DEFAULT_THRESHOLDS` mirror GovernanceEngine static constants, but it mixes imported threshold constants with inline literals in both defaults and phase overrides. Specifically, `cs_min_confidence` is defined inline as `0.70` while the thresholds module already exposes `GOVERNANCE_CS_CONFIDENCE_THRESHOLD = 0.70`; additional phase overrides are encoded inline (`1.10`, `-20.0`, `0.85`, `1.15`, `-40.0`, `0.60`, `1.25`, `-15.0`, `0.80`) rather than sourced from `thresholds.py`.

References: `titan/science/adaptive_priority_lock.py`:29-42, `titan/config/thresholds.py`:96.

**Pattern / scope:**
Single-module finding in this execution unit: threshold-source contract is mixed (imported + inline) inside a science module that controls governance-adjacent threshold values.

**Architectural question raised:**
For `AdaptivePriorityLock`, should phase/default threshold values be governed strictly by `thresholds.py` as canonical inputs, or is module-local literal override policy architect-approved for this component?

**Codex assessment (data only, no decision):**
Current implementation expresses the threshold contract in two source locations (`thresholds.py` and module-local literals), which creates threshold-origin ambiguity during future drift audits.

**Status:** REVIEWED


### [OBS-021] `get_athlete_context` athlete_id contract is output-only in adapter calls

**Date:** 2026-03-16
**Trigger:** Architect-authorized bounded audit pass 5 (`titan/core/`)
**Session context:** Audit Pass 5 / audit-only / observer-only / execution unit: `titan/core/`
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/core/persistence.py` — `get_athlete_context()` signature accepts `athlete_id` but adapter reads are invoked without athlete scoping arguments
- `tests/titan/core/test_persistence.py` — `get_athlete_context` tests validate payload shape/flags but do not assert athlete scoping at adapter call boundary

**Observation:**
Within `titan/core/` scope, `get_athlete_context(athlete_id, ...)` stores the provided `athlete_id` in the returned payload, but all underlying adapter fetches are called without passing athlete identity (`get_baseline_rhr`, `get_hrv_history`, `get_weight_history`, `get_ctl_atl_tsb`, `get_training_load_history`, `get_governance_decisions`). The abstract adapter contract for these reads also has no `athlete_id` parameter in method signatures, so the boundary does not encode whether reads are athlete-scoped or global. Existing tests assert that `result["athlete_id"]` matches input and that optional sections are present/omitted, but they do not assert call-level athlete scoping semantics.

References: `titan/core/persistence.py`:66-109,163-173,200-207,311-313; `tests/titan/core/test_persistence.py`:395-407,421-451.

**Pattern / scope:**
Single finding in this execution unit: contract ambiguity + suspicious coupling between multi-athlete-facing API (`athlete_id` input) and backend read contract (no athlete identity in signatures).

**Architectural question raised:**
For `PersistenceAdapter` read-path methods used by `get_athlete_context`, is athlete isolation intended to be explicit in the adapter contract (method-level identity) or implicitly delegated to backend/session state?

**Codex assessment (data only, no decision):**
Observed boundary currently permits an output payload tagged with a requested `athlete_id` even when adapter read-method contracts do not express athlete identity at call time.

**Status:** REVIEWED


### [DEC-024] Response to OBS-024 — Operator console test topology: root-level placement is intentional and enforced

**Date:** 2026-03-17
**Architect:** Claude
**OBS verified:** YES — read `tests/test_phase6_hygiene.py`:252–258: confirms explicit import
  of `tests.test_operator_console_dashboard` as part of Phase 6 hygiene enforcement.
  Read `tests/titan/ui/test_menu_system.py`:1–8 and `tests/titan/ui/test_setup_wizard.py`:1–8:
  confirmed mirrored-path placement for adjacent UI modules. Read
  `titan/ui/__init__.py`:3–5: `operator_console` is exported as part of the `titan.ui`
  public surface. The hygiene gate test at `test_phase6_hygiene.py`:252–258 explicitly imports
  the root-path module — any migration to `tests/titan/ui/` would break an active CI gate
  without a coordinated update to the hygiene test.

**Architect finding:**
OBS-024 is factually correct. The operator console test sits at the root level
(`tests/test_operator_console_dashboard.py`) while adjacent UI modules use mirrored
`tests/titan/ui/` placement. The root-level placement is not a drift artifact — it was
the original placement when the operator console was introduced (Phase 6), and the
Phase 6 hygiene gate was written to enforce it explicitly. Migrating the file without
updating the hygiene gate would silently break CI. The mixed topology is therefore an
actively enforced contract, not a register-level inconsistency.

Normalization to the mirrored-path convention is a valid future housekeeping item
(requiring coordinated update of both the test location and the hygiene gate import),
but it has zero functional benefit and non-trivial CI-break risk if done without care.
Phase 8 is the wrong time for this hygiene refactor.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Root-level placement for operator console test is intentional and enforced by `test_phase6_hygiene.py`; no restructuring warranted in Phase 8 |

**Rationale:**
The observation correctly identifies a convention split, but the hygiene gate explicitly
enforces the current topology. Treating this as a drift to be corrected would require
a two-file coordinated change (test move + hygiene gate update) with no correctness benefit.
Deferred to Phase 9 housekeeping if normalization is desired at that point.

**OBS-024 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-025] Response to OBS-027 — Wave 1/2 sequencing: five safety-default fixes resolved; remaining findings staged for Wave 2

**Date:** 2026-03-26
**Architect:** Claude
**OBS verified:** YES — verified PRs #526–#530 merged to main 2026-03-26. Read PR bodies and confirmed:
  - PR #526 (T5-47): `EfficiencyEngine` pace zero-guard; commit `52537ed`.
  - PR #527 (T5-53): `ReadinessEngine` null-HRV guard; commit `0d9f852`.
  - PR #528 (T5-58): `_apply_hrv_adjustments` `is not None` guard; commit `d0dbd67`.
  - PR #529 (T5-52): CS confidence default `1.0 → 0.0`; commit `19f9a1d`.
  - PR #530 (T5-51): ACWR `None` propagation; commit `5f68fc5`.
  All five are code-complete with tests and all three gates passed.

**Architect finding:**
OBS-027 surfaced a system-wide optimistic-defaulting pattern across 9 modules. Wave 1 targeted
the five items with the clearest fix scope and no architectural ambiguity (T5-47, T5-51, T5-52,
T5-53, T5-58). These are now RESOLVED. The remaining open items from OBS-027 (T5-44–T5-50,
T5-54–T5-57, T5-59) require either deeper architectural decisions (e.g. T5-49 conservative
defaults policy, T5-44 TRIMP HRmax source) or broader scope (T5-57 mid-week plan
re-evaluation) and are deferred to Wave 2 sequencing under normal Phase 8 prioritization.

**Decision:**
| Action | Detail |
|---|---|
| RESOLVED | T5-47, T5-51, T5-52, T5-53, T5-58 — all closed via Wave 1 PRs #526–#530 |
| DEFERRED | T5-44–T5-50, T5-54–T5-57, T5-59 — remain OPEN; Wave 2 sequencing per Phase 8 tier order |
| NO_ACTION | `MISSING_DATA_POLICY` canonical convention (OBS-027 architectural question) — deferred; ADR_NEEDED before any policy codification |

**OBS-027 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-026] Response to OBS-028 — VO2 eligibility gate optimistic defaults: T5-63 RESOLVED

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `titan/science/governance_engine.py`:431–450 (pre-fix): confirmed
  `context.get("acwr", 1.0)` and `float(1.0 if acwr_raw is None else acwr_raw)` both resolve
  None/absent to 1.0. Confirmed `context.get("readiness_score", 100)` and equivalent None→100
  path. Confirmed V1 gate (`VO2_ACWR_MIN=0.80 ≤ acwr ≤ VO2_ACWR_MAX=1.30`) passes with 1.0;
  V2 gate (`readiness >= VO2_READINESS_MIN=65.0`) passes with 100. Fix applied in PR #556
  (T5-63, branch `claude/fix-obs-028-blocking-u6CuQ`, commit confirmed merged). Post-fix code:
  `context.get("acwr")` (returns None when absent); `if acwr_raw is None: acwr_invalid = True`.
  Same pattern applied to `readiness_score`. Tests added in `TestVo2EligibilityMissingDataPolicy`
  (5 tests) in `tests/test_governance_integration.py`. All three gates passed.

**Architect finding:**
OBS-028 was a legitimate safety defect. The two-layer optimistic defaulting (`.get()` with
a safe-range default, then `None`-to-safe-value coercion) made it structurally impossible for
the V1/V2 eligibility gates to fail on missing data. The fix is minimal, correct, and covered
by regression tests. The MISSING_DATA_POLICY ADR (OBS-033 / DEC-031) was blocked on the ADR;
T5-63 was implemented first to address the BLOCKING safety risk, with the ADR to be authored
in parallel per DEC-031.

**Decision:**
| Action | Detail |
|---|---|
| RESOLVED | T5-63 — VO2 eligibility gate conservative-default fix; PR #556 merged 2026-03-28 |
| ADR_NEEDED | MISSING_DATA_POLICY ADR-0051 authored in this same pass (DEC-031) |

**Rationale:**
BLOCKING safety defect — scheduling a VO2MAX session when Garmin data is absent violates
the governance safety-first principle. Fix is bounded (one method, two fields), covered by
5 regression tests, and consistent with the conservative-substitution pattern (T5-44–T5-59).

**OBS-028 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-027] Response to OBS-029 — cs_confidence default 1.0 regression: T5-64 RESOLVED

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `titan/orchestration/daily_coach.py`:768 (pre-fix): confirmed
  `_safe_float(getattr(self.cs_tracker, 'confidence', 1.0), 1.0)`. Confirmed T5-52 resolution
  record states "CS confidence default changed to 0.0; `CS_CONFIDENCE_LOCK` now fires for
  uncalibrated trackers (PR #529, commit 19f9a1d)". Resolution record and live code are
  contradictory — live code still reads 1.0. Investigated: PR #529 applied the fix to
  `titan/science/governance_engine.py` (internal `getattr(cs_tracker, 'confidence', 0.0)`)
  but did not address the parallel call at `daily_coach.py:768` which feeds the APL. The
  T5-52 record was therefore partially correct (governance engine fixed) but the daily_coach
  APL feed was never updated. Fix applied in PR #557 (T5-64, branch
  `claude/fix-obs-029-cs-confidence-u6CuQ`). Post-fix: `_safe_float(getattr(..., 0.0), 0.0)`.
  Regression tests added in `tests/titan/orchestration/test_daily_coach.py`. All three gates
  passed.

**Architect finding:**
OBS-029 is factually correct. T5-52 closed with incomplete scope — it fixed the governance
engine's internal cs_confidence read but not the daily_coach APL feed. With `cs_confidence=1.0`
the APL tightening path (confidence < 0.50 → `cs_min_confidence` raised to 0.85) was never
reachable for new athletes. This is a BLOCKING safety defect. The T5-52 resolution record
should be annotated to reflect that the fix was incomplete; T5-64 closes the remaining scope.

**Decision:**
| Action | Detail |
|---|---|
| RESOLVED | T5-64 — daily_coach APL cs_confidence default 1.0→0.0; PR #557 merged 2026-03-28 |

**Rationale:**
BLOCKING — APL tightening bypassed for all new athletes with no cs_tracker calibration.
The OBS correctly identified that the resolution record and the live code contradicted each
other. T5-64 closes the scope T5-52 missed.

**OBS-029 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-028] Response to OBS-030 — `_classify_hrv_drop` None ACWR → 1.0: NEW_DEBT_ENTRY T5-65

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `titan/science/governance_engine.py`:235–238: confirmed
  `float(context.get("acwr", 1.0))` with `except (TypeError, ValueError): acwr = 1.0`.
  Post-T5-51, `context["acwr"]` may be `None` when Garmin data is unavailable; `float(None)`
  raises `TypeError` → `acwr = 1.0`. Confirmed at line 240: `if acwr > VO2_ACWR_MAX` —
  threshold check that drives TRAINING_EXPLAINED classification. Impact confirmed as
  narrative label only (not a hard-stop gate decision). Confirmed OBS-030 is a third
  instance of the None→1.0 pattern alongside the VO2 gate (fixed T5-63) and the pre-T5-51
  DailyCoach call site.

**Architect finding:**
OBS-030 is factually correct and non-blocking. The classification label mismatch
(TRAINING_EXPLAINED vs ILLNESS_PATTERN when ACWR is unavailable) does not drive any hard-stop
gate; it feeds only narrative output surfaced via Telegram. However, a systematic pattern of
None→1.0 coercion in governance engine methods is established (three locations identified).
The conservative correct behavior is: None ACWR → return UNKNOWN_ACWR classification, not
TRAINING_EXPLAINED. ADR-0051 (DEC-031) will codify the policy; T5-65 registers the fix.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-65 — `_classify_hrv_drop` None ACWR returns TRAINING_EXPLAINED; fix to return UNKNOWN or conservative label; implement after ADR-0051 |

**Rationale:**
Non-blocking but a direct consequence of the same policy gap that created OBS-028. After
ADR-0051 is accepted, the correct behavior for None ACWR in classification is unambiguous.
T5-65 is scoped to one method; binary acceptance criterion: `_classify_hrv_drop(acwr=None)`
returns a label that does not assert TRAINING_EXPLAINED.

**OBS-030 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-029] Response to OBS-031 — `save_daily_metric` INSERT OR REPLACE data loss: NEW_DEBT_ENTRY T5-66

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `titan/core/database.py`:758: confirmed `INSERT OR REPLACE INTO
  daily_metrics`. SQLite INSERT OR REPLACE semantics: deletes existing row and inserts new one;
  any column not in the new INSERT is reset to DEFAULT (NULL/0). Confirmed this is distinct
  from INSERT OR IGNORE at line 831 (used for HRV historical entries, fixed by T5-61).
  Cross-referenced OBS-025 F-26 (MEDIUM): finding pre-registered but no T5 item created.
  Confirmed subjective fields at risk: `mood_score`, `soreness_score`, `notes`,
  `perceived_effort` — all are primary 2-of-4 gate inputs. Re-sync on any day will silently
  zero these fields if not included in the Garmin-sync call.

**Architect finding:**
OBS-031 is factually correct. F-26 from OBS-025 was never converted to a debt entry. The
INSERT OR REPLACE policy is a data integrity risk at the 2-of-4 gate boundary: subjective
inputs are overwritten by automated sync without preservation. The correct fix is a
column-merge UPSERT: Garmin fields (Garmin-source columns) are overwritten; manual subjective
fields are preserved. This requires a SQL policy decision (INSERT OR REPLACE vs per-column
UPSERT) but no new ADR is needed — the data integrity principle is already established.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-66 — `save_daily_metric` INSERT OR REPLACE silently destroys subjective fields on re-sync; fix to per-column UPSERT preserving manual entries |

**Rationale:**
MEDIUM severity per OBS-025 F-26. A re-sync on a high-fatigue day erases the athlete's
self-reported fatigue score, which is a primary 2-of-4 gate input. The downstream consequence
is that the gate cannot fire on re-sync days, creating an observability and safety gap.

**OBS-031 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-030] Response to OBS-032 — `sync_sleep`/`sync_hrv` misleading success events: NEW_DEBT_ENTRY T5-67

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `titan/integrations/garmin_sync.py`:469 (`sync_sleep`) and
  531 (`sync_hrv`): confirmed success event `_garmin_event("synced", count=len(sessions), ...)`
  is emitted unconditionally after the outer `try/except`, not gated on success. Confirmed
  that after an exception, `sessions = []`, so the emitted event carries `count=0`. Also
  confirmed F-03 (MEDIUM) from OBS-025 was never converted to a debt entry. Checked
  `sync_activities` and `sync_weight` — same structural pattern confirmed in both methods.
  Four affected methods total.

**Architect finding:**
OBS-032 is factually correct. "synced 0 items" on exception-abort and "synced 0 items" on
a zero-activity day are indistinguishable in the event stream. SLO alerting that queries for
zero-sync events will produce false negatives on exception days. The fix is to gate the
success event on absence of exception (boolean flag or move inside try block). This is a
targeted observability fix with no governance logic impact.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-67 — `sync_sleep`, `sync_hrv`, `sync_activities`, `sync_weight` emit success events unconditionally; gate on exception absence |

**Rationale:**
MEDIUM observability risk per OBS-025 F-03. Misleading success events undermine SLO alerting
reliability. Fix is bounded to four call sites in one file; no architectural decision required.

**OBS-032 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-031] Response to OBS-033 — MISSING_DATA_POLICY ADR not created: ADR-0051 authored this pass

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — searched `docs/adr/` for any `MISSING_DATA_POLICY` ADR: none found.
  Last ADR in directory is ADR-0050. DEC-025 (OBS-027 response, 2026-03-26) recorded
  ADR_NEEDED; no ADR was authored in the intervening two days. T5-63 and T5-64 were
  implemented as BLOCKING fixes without the policy ADR (per §26 No Mixed-Pass Rule, BLOCKING
  fixes cannot wait for ADR authoring). OBS-028 and OBS-030 both reference the same policy
  gap. ADR-0051 authored as part of this Pass 2 records-only session.

**Architect finding:**
OBS-033 is factually correct. DEC-025 correctly recorded ADR_NEEDED but the ADR was not
created before T5-63/T5-64 were implemented. This was the right sequencing choice: BLOCKING
safety defects must be fixed before policy formalization, not after. The de facto policy
applied by T5-63 and T5-64 is: None/absent safety-critical input → conservative fail outcome.
ADR-0051 codifies this policy retroactively, covering both implemented fixes and establishing
the pattern for future modules.

**Decision:**
| Action | Detail |
|---|---|
| ADR_NEEDED → RESOLVED | ADR-0051 `docs/adr/0051-missing-data-policy.md` authored in this pass |

**Rationale:**
The MISSING_DATA_POLICY fills the architectural gap that made OBS-028, OBS-029, and OBS-030
possible. Without it, future module authors have no canonical reference for conservative
defaulting behavior on None/absent inputs. ADR-0051 is the governing document for T5-65
(OBS-030 fix) and any future findings in this category.

**OBS-033 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-032] Response to OBS-034 — VO2 eligibility gate None coverage gap: RESOLVED by T5-63

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `tests/test_governance_integration.py`: confirmed new class
  `TestVo2EligibilityMissingDataPolicy` added by T5-63, with 5 tests covering:
  `acwr=None` in context, `acwr` key absent, `readiness_score=None` in context,
  `readiness_score` key absent, and both None together. Tests assert `eligible is False`
  and appropriate `failed_conditions` entries (V1, V2). Also confirmed updated
  `test_contract_on_invalid_numeric_path` asserts V1 and V2 in `failed_conditions`.
  Three-gate suite passed post-T5-63.

**Architect finding:**
OBS-034 was a valid test coverage gap at the time it was recorded. T5-63 included the
required test coverage as part of its deliverables (per AGENTS.md §6 test creation mandate).
The gap is now closed. No additional debt entry needed.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Test coverage gap closed by T5-63 regression tests; 5 new tests in `TestVo2EligibilityMissingDataPolicy` |

**Rationale:**
The OBS correctly identified the gap; the fix included the tests as required by the
mirrored-test policy. No separate tracking item is warranted.

**OBS-034 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-033] Response to OBS-035 — ESI dew_point 12.0 magic number: NEW_DEBT_ENTRY T5-68

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `titan/orchestration/daily_coach.py`:713: confirmed
  `dew_point_c=_safe_float(garmin_data.get("dew_point"), 12.0)`. Searched `thresholds.py`
  for `dew_point` or `DEW_POINT`: no constant found. Read `titan/config/evidence_registry.py`:
  no `DEW_POINT` entry. Cross-referenced T5-59 (`NutritionOptimizer`): found `25.0°C` used
  as conservative hydration default. Confirmed two different default values (12.0 vs 25.0) for
  the same physical quantity (`dew_point_c`) in the same DailyCoach pipeline. ADR-0034 governs
  environmental stress compensation; does not specify a default dew_point constant.
  The 12.0°C default is below the 18.0°C threshold used in T5-59 hydration logic; the
  two defaults produce measurably different ESI values (ESI = temp + 0.5 × dew_point).

**Architect finding:**
OBS-035 is factually correct. The 12.0°C literal is a Category A threshold that should be
externalized per ADR-0034 and the T5-04/T5-20 burn-down precedent. The correct canonical
value requires a calibration decision: should ESI conservative default be 12.0 (low humidity,
underestimates thermal stress) or 18.0/25.0 (higher humidity, conservative)? For a safety-first
system, the conservative choice is a higher default (overestimates thermal stress, leading to
more cautious pacing). This is a config decision with a clean implementation path; no new ADR
is required beyond annotating ADR-0034.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-68 — `daily_coach.py:713` ESI dew_point 12.0°C magic number; extract to `ESI_DEW_POINT_FALLBACK_C` in `thresholds.py` with conservative value (≥18.0°C per safety-first principle); annotate ADR-0034 |

**Rationale:**
Category A threshold governance gap. Two different fallback values for the same physical
quantity in the same pipeline produces internally inconsistent thermal stress assessments.
The conservative default should be documented and justified in `evidence_registry.py`.

**OBS-035 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-034] Response to OBS-036 — `garmin_activity_id` not persisted: NEW_DEBT_ENTRY T5-69

**Date:** 2026-03-28
**Architect:** Claude
**OBS verified:** YES — read `titan/integrations/garmin_sync.py` `sync_activities()` return
  value: confirmed fields are `date`, `distance_km`, `duration_sec`, `avg_hr`, `max_hr`,
  `activity_type`, `trimp`; no `activity_id`. Read `titan/core/database.py` `training_log`
  schema: no `activity_id` column. Read `save_session()`: no deduplication logic. Confirmed
  F-28 (LOW) from OBS-025 was never converted to a debt entry. Cross-referenced T5-46 (HRV
  deduplication): confirmed per-date INSERT OR IGNORE is the implemented pattern for HRV.
  Confirmed `get_training_load_history()` reads all rows without deduplication — duplicate
  activities directly inflate CTL/ATL/TSB. Verified: a 6h re-sync + manual /sync within the
  same window can produce duplicate rows for the same activity.

**Architect finding:**
OBS-036 is factually correct. The absence of `activity_id` in the sync payload and schema
creates a structural duplicate-activity risk. Unlike HRV (where per-date deduplication is
sufficient because there is at most one HRV measurement per day), activities can legitimately
have multiple sessions on the same date (double-day training). Per-date deduplication would
incorrectly drop valid sessions; activity-ID deduplication is the correct approach. The impact
(silent TSB/CTL/ATL inflation) is a safety concern: a doubled TRIMP load could falsely trigger
or bypass hard-stop gates. Registering as T5-69 at appropriate tier.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-69 — `sync_activities` does not extract `activityId`; `training_log` schema lacks `activity_id` column; `save_session` has no activity-identity deduplication; fix following T5-46 HRV pattern |

**Rationale:**
Data integrity risk: duplicate activity records silently inflate CTL/ATL/TSB calculations.
A doubled strenuous session TRIMP pushes load metrics into false hard-stop territory or
masks real overtraining signals. The fix pattern (extract ID, add column, INSERT OR IGNORE
on activity_id) is established by T5-46 and requires no new architectural decisions.

**OBS-036 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-035] Response to OBS-037 — AuthStore wiring gap: NEW_DEBT_ENTRY T5-70

**Date:** 2026-04-04
**Architect:** Claude
**OBS verified:** YES — read `titan/api/auth.py`:26–114: confirmed `self._users: dict` and
  `self._tokens: dict` at lines 30–31; no database imports; all methods operate on in-process
  dicts only. Read `alembic/versions/20260316_01_t5_11_add_auth_tables.py`:1–46: confirmed
  `auth_users` and `auth_tokens` tables were created by T5-11 migration (revision
  `20260316_01`, 2026-03-16). Read `titan/api/main.py`:144: `AuthStore()` instantiated with
  no DB argument; no persistence initialization. Read `docs/adr/0048-api-authentication-layer.md`:40:
  ADR-0048 explicitly states "Refresh token: Long-lived (7 days), stored server-side in
  `auth_tokens` table (PostgreSQL)". Cross-referenced TECHNICAL_DEBT.md T5-11 entry: marked
  RESOLVED 2026-03-15; resolution record does not mention in-memory vs persistent storage
  alignment — the persistence gap was not caught at T5-11 closure.

**Architect finding:**
OBS-037 is factually correct. The `auth_users` and `auth_tokens` tables exist in the SQLite
schema (created by T5-11) but are orphaned — no production code path reads from or writes to
them. `AuthStore` implements bcrypt, JWT, and token-rotation logic entirely in process-local
Python dicts. A process restart silently invalidates all authenticated sessions.

The architectural question raised (SQLite vs Redis vs PostgreSQL) is answered by existing ADRs
without requiring a new one:
1. **ADR-0048 §2.1** explicitly mandates server-side storage in `auth_tokens` table. The
   interface was accepted and the tables were created; the implementation deviated from the ADR.
   This is a conformance gap, not an open design question.
2. **ADR-0044** accepts PostgreSQL (D2) as future target, but D1 (SQLite) is the active tier
   and D2 has not landed. Wiring to SQLite now fulfills ADR-0048 at the D1 tier.
3. Redis introduces a new infrastructure dependency; nothing else in the system uses it;
   out of scope for current tier.

No new ADR is needed. The implementation must conform to ADR-0048 using the current D1 storage
tier. When ADR-0044 D2 lands, the `AuthStore` persistence layer is a one-abstraction swap to
SQLAlchemy — it does not require re-opening ADR-0048.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-70 — `AuthStore` stores users and tokens in process-local dicts; wire to existing SQLite `auth_users`/`auth_tokens` tables via `DatabaseManager`; bcrypt and JWT logic is already correct and must not change; scope: `titan/api/auth.py` (AuthStore CRUD methods) + `titan/core/database.py` (auth query helpers) |

**Rationale:**
The fix is bounded and schema-free: the migration already exists (T5-11). The change is:
replace dict reads/writes in AuthStore with DatabaseManager calls. The existing bcrypt and
token-rotation logic (`MAX_ACTIVE_REFRESH_TOKENS = 3`, `_trim_active_refresh_tokens`) is
correct and carries over unchanged. Tests must cover persistence across AuthStore
re-instantiation (the key failure mode OBS-037 identifies).

**OBS-037 marked:** REVIEWED
**Status:** PROCESSED

---


### [DEC-023] Response to OBS-023 — Nutrition public API test gap: T5-42 registered

**Date:** 2026-03-16
**Architect:** Claude
**OBS verified:** YES — read `titan/features/nutrition_optimizer.py`:35–216: confirmed
  `add_weight_entry()`, `analyze_weight_trend()`, `calculate_daily_nutrition()` as public
  methods. Read `tests/titan/features/test_nutrition_optimizer.py`:1–65: confirmed tests
  cover `analyze_weight_trend()` scenarios only; no tests for `add_weight_entry()` retention
  behavior or `calculate_daily_nutrition()` output contract / branching.

**Architect finding:**
OBS-023 is factually correct. The mirrored test file exists but has incomplete public-method
coverage: two public methods (`add_weight_entry()` and `calculate_daily_nutrition()`) have no
test coverage in the mirrored file. This is a straightforward test coverage gap — not an
architectural ambiguity. Both methods have meaningful behavioral contracts (weight entry
persistence, daily macro calculation with branching) that are testable without architectural
decisions. Debt entry registered as T5-42.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-42 registered: `NutritionOptimizer` public API test coverage gap — `add_weight_entry()` and `calculate_daily_nutrition()` lack explicit tests in `tests/titan/features/test_nutrition_optimizer.py` |

**Rationale:**
The mirrored-test policy requires meaningful coverage of public methods in changed/audited
modules. Two of three public methods are untested. The fix is test-only (no production code
changes required), bounded to one file, and has no architectural dependencies. T5-42 is the
correct tier and scope for this finding.

**OBS-023 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-022] Response to OBS-022 — Integration contract/threshold gaps: T5-40 + T5-41 registered

**Date:** 2026-03-16
**Architect:** Claude
**OBS verified:** YES — read `titan/integrations/notification_gateway.py`:75–95:
  confirmed `TelegramChannel.send()` calls `self._bot.send_daily_coaching(payload)` and
  returns `True` unconditionally unless exception raised; the boolean returned by
  `send_daily_coaching()` is discarded. Read `titan/integrations/telegram_bot.py`:444–467:
  confirmed `send_daily_coaching()` returns boolean from `send_message()`. Read
  `tests/titan/integrations/test_notification_gateway.py`:15–139: confirmed no test for
  the `False`-without-exception branch. Read `titan/integrations/weather_api.py`:158–170
  and 529–537: confirmed independent inline dew-point literal clusters in
  `classify_heat_stress()` and `find_optimal_training_windows()`.

**Architect finding:**
OBS-022 identifies two distinct actionable gaps in the integration layer:

1. **Boolean-return silent failure (T5-40):** `TelegramChannel.send()` discards the boolean
   result of `send_daily_coaching()`. A `False` return (delivery failure without exception)
   is silently treated as success at the channel boundary. This is a real behavioral contract
   gap — not a design choice — and requires both a code fix (consume the boolean) and a test
   for the `False`-without-exception branch.

2. **Dew-point literal duplication (T5-41):** Two independent inline literal clusters for the
   same decision domain (dew-point bands) in `weather_api.py` violate the Category A
   threshold-governance policy. The same threshold values appear in two places with no shared
   source. Category A extraction to `thresholds.py` is required.

Finding 3 (missing mirrored test for the False branch) is subsumed by T5-40's test requirement.
No new ADR is required for either finding; both are bounded implementation fixes.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-40 registered: `TelegramChannel.send()` boolean return silent-failure path + branch coverage test |
| NEW_DEBT_ENTRY | T5-41 registered: dew-point decision band literals in `weather_api.py`:158–170, 529–537 → extract to `thresholds.py` named constants (Category A) |

**Rationale:**
Both findings are within the Category A threshold-governance and behavioral-contract-gap
patterns established in Phase 8B. Both are bounded to the integration layer, require no
architectural decisions, and have binary acceptance criteria. T5-40 and T5-41 are the correct
tier and scope for these findings.

**OBS-022 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-021] Response to OBS-021 — `get_athlete_context` athlete_id contract: single-athlete mode is correct current design

**Date:** 2026-03-17
**Architect:** Claude
**OBS verified:** YES — read `titan/core/persistence.py`:66–109: confirmed `get_athlete_context()`
  stores `athlete_id` in returned payload but all underlying adapter fetches (`get_baseline_rhr`,
  `get_hrv_history`, `get_weight_history`, `get_ctl_atl_tsb`, `get_training_load_history`,
  `get_governance_decisions`) are called without an `athlete_id` argument. Read
  `tests/titan/core/test_persistence.py`:395–451: confirmed tests assert payload shape and
  optional-section presence but not call-level athlete scoping. Confirmed ADR-0046 and T5-16
  govern the multi-athlete execution model — CoachingScheduler is the planned isolation boundary;
  single-athlete read paths are not required to carry athlete identity at the adapter level
  until CoachingScheduler is implemented.

**Architect finding:**
OBS-021 is factually correct: the adapter read methods do not carry `athlete_id` in their
signatures, and the tests do not assert call-level scoping. However, this is not a design
flaw — it is the correct current state for a single-athlete system. The TITAN OS currently
operates with one athlete profile per database. In this context, all adapter reads are
implicitly scoped to that single athlete; passing `athlete_id` through every read method
would add mechanical boilerplate with no behavioral benefit at this scale.

The multi-athlete scoping concern is actively tracked and governed: ADR-0046 accepted the
CoachingScheduler model as the future isolation boundary. T5-16-A closed the state-isolation
acceptance criteria for that model (2026-03-15). The `athlete_id` in `get_athlete_context()`
output is correct — it tags the returned payload with the requested identity for downstream
consumers. There is no architectural inconsistency here.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Single-athlete adapter contract is correct for current system scope; multi-athlete scoping is Phase 9 scope per ADR-0046 / T5-16 |

**Rationale:**
The observation correctly identifies an asymmetry between the output contract (tagged with
`athlete_id`) and the adapter read contract (no identity). This asymmetry is intentional and
correct for single-athlete mode. The multi-athlete extension path is governed by ADR-0046.
No new debt entry is warranted — the existing ADR-0046 and T5-16 closure record cover the
forward design constraint.

**OBS-021 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-019] Response to OBS-019 — ML explainability module path: records correction for T5-06-A

**Date:** 2026-03-17
**Architect:** Claude
**OBS verified:** YES — searched `titan/science/` for `ml_explainability.py`: file does not
  exist. Read `titan/science/ml_safety.py`:13–21: confirmed `ExplainableOutput` dataclass
  defined here. Read `titan/science/injury_risk_model.py`:13 and 145–170: confirmed
  explainability payload construction in `InjuryRiskEnsembleModel`. Read
  `tests/test_ml_explainability.py`:1: confirmed test file name references
  non-existent module but tests validate explainability through `InjuryRiskEnsembleModel`.
  Read `TECHNICAL_DEBT.md`:1448 and 1464–1477: confirmed T5-06-A references
  `titan/science/ml_explainability.py` in its module-path wording.

**Architect finding:**
OBS-019 is factually correct. The T5-06-A debt entry and surrounding text reference
`titan/science/ml_explainability.py` as if it is a standalone module. No such module exists.
The explainability contract (`ExplainableOutput`) lives in `titan/science/ml_safety.py`; the
payload construction lives in `titan/science/injury_risk_model.py`. The test file name
(`test_ml_explainability.py`) is a naming artifact from when a dedicated module was
anticipated; it validly tests the explainability behaviour via `InjuryRiskEnsembleModel`.

This is a records-accuracy issue: the T5-06-A closure entry should reference the correct
module paths rather than a phantom path. T5-06-A is already RESOLVED (2026-03-15); the
correction is editorial only and does not affect the RESOLVED status or any implementation.
No new debt entry is needed.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION (new debt) | T5-06-A is already RESOLVED; no implementation gap exists |
| NO_ACTION (functional) | `ExplainableOutput` is correctly implemented in `ml_safety.py`; `InjuryRiskEnsembleModel` correctly builds explainability payloads |
| Records correction authorised | T5-06-A entry updated to reference `titan/science/ml_safety.py` (ExplainableOutput source) and `titan/science/injury_risk_model.py` (payload construction) instead of phantom `ml_explainability.py` |

**Rationale:**
The correction is editorial: replacing a phantom module-path reference with the actual
implementation locations. It does not change any acceptance criteria, implementation scope,
or debt status. The test file naming is intentional and does not require renaming
(renaming tests is scope creep with no functional benefit at this stage).

**OBS-019 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-018] Response to OBS-018 — Governance test placement: root-level coverage is intentional and adequate

**Date:** 2026-03-17
**Architect:** Claude
**OBS verified:** YES — searched `tests/titan/science/` for `test_governance_engine.py`
  and `test_governance_contracts.py`: neither file exists. Read
  `tests/test_governance_integration.py`:1–2: confirmed root-level placement with substantial
  governance coverage. Read `AGENTS.md`:10–14: confirmed mirrored-path requirement is stated
  as "every change to a module must be accompanied by tests for the new/changed behaviour"
  in `tests/titan/<path>/test_<module>.py`. The policy triggers on changed modules — it is
  not a retroactive restructuring mandate.

**Architect finding:**
OBS-018 is factually correct: no mirrored `tests/titan/science/test_governance_*.py` files
exist. However, the finding does not constitute a policy violation. The AGENTS.md mirrored-path
rule applies when a module is changed in a task — it requires new tests to be placed in the
mirrored path for that change. It does not require retroactive migration of pre-existing
governance tests from their current root-level location.

The governance test files (`tests/test_governance_integration.py`,
`tests/test_governance_mutation.py`) provide comprehensive governance coverage and are part of
CI. Migrating them to `tests/titan/science/` would be a pure housekeeping refactor with no
coverage gain and a non-trivial risk of hygiene gate breakage. The trigger for migration would
be a governance-module change task — at that point the new tests for the changed behaviour
would go into the mirrored path (per policy), while the existing root-level tests remain as
regression coverage.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Root-level governance test placement is not a policy violation; mirrored-path rule applies to new/changed behaviour, not retroactive restructuring |

**Rationale:**
AGENTS.md §6 requires mirrored test placement for new/changed behaviour. It does not mandate
retroactive migration of existing test files. The existing governance coverage at root level
is extensive, maintained, and CI-active. No new debt entry warranted.

**OBS-018 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-017] Response to OBS-017 — Evidence registry contract: records correction for broader provenance scope

**Date:** 2026-03-17
**Architect:** Claude
**OBS verified:** YES — read `titan/config/evidence_registry.py`:4 and 55: confirmed contract
  statement "one entry per constant in thresholds.py" and section framing. Read
  `titan/config/evidence_registry.py`:410–518: confirmed eight `PHYS_BOUNDS_*` entries present
  inside `EVIDENCE_REGISTRY`. Read `titan/config/thresholds.py`:1–135: confirmed no
  `PHYS_BOUNDS_*` symbols defined there. Read `titan/config/evidence_registry.py`:410–412:
  confirmed inline comment states bounds runtime location is `titan/science/physiological_bounds.BOUNDS`.

**Architect finding:**
OBS-017 is factually correct. The `EVIDENCE_REGISTRY` contract statement ("one entry per
constant in thresholds.py") does not match the actual key-set composition, which includes
eight `PHYS_BOUNDS_*` entries whose runtime home is `titan/science/physiological_bounds.py`,
not `thresholds.py`. The registry was designed as a provenance tracker for scientifically
governed constants; its scope naturally covers constants in adjacent config-adjacent modules
(physiological bounds) even if those constants do not live in `thresholds.py`.

The design intent is sound: provenance tracking for all governed science constants, regardless
of which config module they live in. The problem is the contract statement, which is too narrow.
The fix is editorial: update the contract statement to describe the actual scope — governed
science constants from `thresholds.py` **and** governed physiological bounds from
`physiological_bounds.py`.

No functional gap exists. The `PHYS_BOUNDS_*` entries are legitimate provenance records.
No new debt entry is warranted.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION (new debt) | Registry design is correct; no implementation gap exists |
| Records correction authorised | Contract statement in `evidence_registry.py` updated to describe broader provenance scope (thresholds.py + physiological_bounds.py governed constants) |

**Rationale:**
The registry's actual scope is broader than its stated contract. The contract statement is
the only artifact that needs updating — it must describe what the registry actually covers.
The `PHYS_BOUNDS_*` entries are correctly included; the framing was never updated after the
physiological bounds constants were added to the registry.

**OBS-017 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-016] Response to OBS-016 — Phase 8B retrospective: Phase 8C opens; T5-12 Pass 1 authorized

**Date:** 2026-03-17
**Architect:** Claude
**OBS verified:** YES — reviewed `TECHNICAL_DEBT.md` Phase 8B closure records for all
  items listed in OBS-016 (T5-08-B through T5-38). Verified T5-36, T5-37, T5-38 all carry
  RESOLVED status with dated closure records. Verified T5-12 status: OPEN with explicit
  Phase 8C deferral and a written architect brief (Pass 1 + Pass 2 structure, ADR gate).
  Verified D6 status via DEC-015 (already PROCESSED 2026-03-16). Confirmed no un-triaged
  findings remain in SCRATCHPAD.md after this pass.

**Architect finding:**
OBS-016 presents a factually accurate retrospective of Phase 8B. The closure evidence is
internally consistent for all shipped items. The late-discovery pattern
(T5-36/T5-37/T5-38 + T5-12 deferral) does not indicate Phase 8C is under-scoped:

- T5-36 (API rate limiting), T5-37 (CI gates), T5-38 (meta-tests) were all identified,
  registered, and resolved within Phase 8B before closure. They did not escape into Phase 8C.
- T5-12 has a fully-formed architect brief with Pass 1 (design) and Pass 2 (implementation)
  already defined; its deferral to Phase 8C is by design, not by oversight.
- No un-triaged findings remain in SCRATCHPAD.md after the 8-pass bounded audit program
  (OBS-017 through OBS-024, all REVIEWED in this records pass).

The question posed by OBS-016 — whether Phase 8C planning needs re-baselining against the
late-discovery pattern — is answered: **no re-baselining is required.** The Phase 8C
candidate list as currently recorded is complete. The bounded audit program (8 passes, 8
OBS entries, 4 new debt items) did not surface any Phase 8C scope gaps beyond what is
already tracked. Audit batch T5-39–T5-42 is fully closed. Phase 8C may now open.

**Phase 8C opening — effective 2026-03-17:**
- Phase 8C is **OPEN** as of this records pass.
- First canonical execution unit: **T5-12 Pass 1 — Mitigation Design Pass** (no code changes;
  produces written mitigation design document as defined in the T5-12 architect brief).
- T5-12 Pass 2 (implementation) remains **blocked** until the design ADR is accepted by
  the architect (per T5-12 brief: ADR required before implementation begins).
- No other Phase 8C items are currently open beyond T5-12.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION (re-baselining) | Phase 8C candidate list is complete; no re-baselining needed |
| Phase 8C OPEN | Effective 2026-03-17; T5-12 Pass 1 is the first authorized execution unit |
| TECHNICAL_DEBT.md update | Phase 8C opening noted in update log and sequencing block |

**Rationale:**
Phase 8B produced a clean closure: all shipped items resolved, three late-registered findings
(T5-36/T5-37/T5-38) registered and resolved before Phase 8B close, T5-12 deferred with a
complete design brief. The bounded audit program confirmed no further scope gaps. Phase 8C
inherits a single open item (T5-12) with a defined execution structure. The conditions for
Phase 8C opening are met.

**OBS-016 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-020] Response to OBS-020 — APL threshold source: Category A extraction required for `cs_min_confidence = 0.70`; phase overrides remain inline (Category B)

**Date:** 2026-03-16
**Architect:** Claude
**OBS verified:** YES — read `titan/science/adaptive_priority_lock.py`:29–42 and
  `titan/config/thresholds.py`:96. Confirmed: `_DEFAULT_THRESHOLDS["cs_min_confidence"]`
  is inline `0.70` with comment `# GovernanceEngine.CS_CONFIDENCE_THRESHOLD` at line 35.
  Confirmed: `GOVERNANCE_CS_CONFIDENCE_THRESHOLD = 0.70` exists at `thresholds.py`:96.
  Phase override literals (`PEAK` 0.85, `BUILD_OVERLOAD` 0.60, `TAPER` 0.80) at lines 40–42
  are phase-specific tuning values with no direct canonical equivalent in `thresholds.py` —
  confirmed no `GOVERNANCE_CS_CONFIDENCE_*_PEAK` or similar constants exist in thresholds.

**Architect finding:**
OBS-020 is factually correct and the Category A / Category B partition is clear:

- `_DEFAULT_THRESHOLDS["cs_min_confidence"] = 0.70` (line 35) is a **Category A** duplicate.
  The comment on the same line explicitly acknowledges the canonical source
  (`GovernanceEngine.CS_CONFIDENCE_THRESHOLD`), confirming the author's intent was to mirror
  the canonical value. This is threshold-source contract divergence: a future change to
  `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` would silently miss the APL default path. This must
  be corrected by import replacement.

- Phase override literals `PEAK: 0.85`, `BUILD_OVERLOAD: 0.60`, `TAPER: 0.80` (lines 40–42)
  are **Category B** — algorithm-local phase tuning values with no canonical equivalent in
  `thresholds.py`. Extracting them would require new constants whose semantic scope is
  APL-internal. No extraction is warranted; they remain inline. This is an explicit scope
  exclusion from T5-39.

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-39: replace `cs_min_confidence = 0.70` inline literal at `adaptive_priority_lock.py`:35 with `GOVERNANCE_CS_CONFIDENCE_THRESHOLD` import from `thresholds.py`. Category A extraction. Workflow Path A. ~30 min. No ADR required. |
| NO_ACTION (phase overrides) | `PEAK`/`BUILD_OVERLOAD`/`TAPER` per-phase `cs_min_confidence` values are Category B (algorithm-local APL tuning). Remain inline. Explicitly excluded from T5-39 scope. |

**Rationale:**
The inline `0.70` at line 35 is an acknowledged duplicate with a comment pointing directly to
the canonical source. The canonical value already exists and is imported elsewhere in the science
layer. The fix is a single import addition and one reference substitution — a well-bounded
Category A extraction with no architectural ambiguity. Phase overrides are APL-internal policy
and have no cross-module governance contract; centralising them would require inventing new
threshold names without evidence-based provenance, violating the Category A/B discipline
established by DEC-1/T5-19.

**OBS-020 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-015] Response to OBS-015 — Phase 8B retrospective: D6 records correction authorised

**Date:** 2026-03-16
**Architect:** Claude
**OBS verified:** YES — read `titan/core/persistence.py:122` and `titan/core/database.py:1975`:
  both implement `TITAN_DB_BACKEND` env-var switching via `get_database_manager()`. Confirmed
  T5-08-B tracking table (TECHNICAL_DEBT.md line 1630): D6 `✓ DONE (T5-08)`. Confirmed
  resolution summary table (TECHNICAL_DEBT.md line 2938): D6 absent — correctly excludes it
  as a T5-08-B deliverable. Cross-referenced T5-08 status (line 1554): RESOLVED 2026-03-15
  via T5-08-B, scaffold commit 54e95d9. D6 origin is T5-08, not T5-08-B.

**Architect finding:**
OBS-015 is factually correct. D6 (`TITAN_DB_BACKEND` feature flag) was implemented in T5-08
(commit 54e95d9, 2026-03-08). T5-08-B's tracking table correctly recorded D6 as `✓ DONE
(T5-08)` — a pre-existing deliverable, not a T5-08-B implementation deliverable. The
resolution summary table (line 2938) correctly omits D6 from the T5-08-B deliverable list.
The inconsistency is in the T5-08-B status body (line 1613), which includes "D6 DONE (T5-08)"
in a list framed as "All deliverables complete," creating the erroneous impression that D6 was
a T5-08-B deliverable. The correction required: the status body must be updated to enumerate
only T5-08-B's own deliverables (D1, D2a/b/c, D3, D4, D5, D7, D9) and add a separate note
that D6 was a T5-08 pre-existing deliverable carried into T5-08-B's tracking table for
completeness only. D6 is functionally implemented and correct in both `persistence.py` and
`database.py`. No functional gap exists; this is a records-accuracy correction only.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION (functional) | D6 is implemented and verified in both `persistence.py` and `database.py`. No code change required. |
| NO_ACTION (new debt) | No new TECHNICAL_DEBT.md entry needed — this is a records correction to an existing RESOLVED entry, executed inline. |

**Records correction authorised (executed inline in TECHNICAL_DEBT.md, 2026-03-16):**
T5-08-B status body corrected: "D6 DONE (T5-08)" removed from the "all deliverables" claim.
Status line now reads: D1, D2a/b/c, D3, D4, D5, D7, D9 — marked RESOLVED 2026-03-15. D6
status note added separately as a pre-existing T5-08 deliverable. Resolution summary table
(line 2938) already reflects the correct enumeration; no change to the summary table needed.

**Rationale:**
The records inconsistency between the status body and the resolution summary table is a
documentation accuracy issue. The resolution summary table (which was written later and is
more precise) represents the authoritative enumeration of T5-08-B deliverables. The status
body must align with it. No architectural decision is needed for a records alignment of a
RESOLVED entry.

**OBS-015 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-008] Response to OBS-008 — In-flight continuation rule: conflict already resolved

**Date:** 2026-03-13
**Architect:** Claude
**OBS verified:** YES — read AGENTS.md §15 intro (lines 900–904): "completes any current subtask
  already in progress, then stops. Codex does not start any new top-level task until the architect
  clears the status to IDLE. See SCRATCHPAD.md §Document Status for the single authoritative
  in-flight work policy." Read T-SCRATCHPAD-3 (lines 948–950): "Codex may continue with the
  current task (this is non-blocking for the current subtask). Codex must NOT start a new
  top-level task." Read SCRATCHPAD.md §Document Status line 19: single authoritative statement
  present.

**Architect finding:**
The conflict described in OBS-008 does not exist in the current documents. Both AGENTS.md §15
intro and T-SCRATCHPAD-3 are semantically consistent: "completes current subtask, then stops"
(§15 intro) and "may continue with the current task" (T-SCRATCHPAD-3) express the same policy
with different emphasis. The word "stops" in §15 intro refers to stopping from starting new
top-level tasks — not halting a mid-flight subtask. AGENTS.md §15 explicitly defers to
SCRATCHPAD.md §Document Status as the "single authoritative in-flight work policy," which
resolves any residual ambiguity. The OBS was written against an earlier version; the documents
have since been aligned.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Conflict does not exist in current documents; resolution already present in AGENTS.md §15 intro + SCRATCHPAD.md §Document Status |

**Rationale:**
All three source locations (AGENTS.md §15 intro, T-SCRATCHPAD-3, SCRATCHPAD.md §Document
Status) agree: complete current subtask, stop, no new top-level task until IDLE. The
authoritative single statement is in SCRATCHPAD.md, explicitly acknowledged by AGENTS.md.
No policy change, no documentation change, no debt entry is warranted.

**OBS-008 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-009] Response to OBS-009 — Manual checklist enforcement: intentional design

**Date:** 2026-03-13
**Architect:** Claude
**OBS verified:** YES — read AGENTS.md §11 pre-delivery checklist (lines 560–587): 29 items,
  majority are self-attestation. Read AGENTS.md §2 HARD GATE: three executable commands (ruff,
  pytest -W error, pytest). Confirmed via grep that check_scratchpad.sh and the three gate
  commands constitute the full automated enforcement surface. Manual items confirmed as
  intentional (scope declaration, task-learning block, narrative conformance).

**Architect finding:**
The observation is factually correct. The gap between MUST-level policy language and automated
enforcement is real, but it is not a deficit — it is the intended design. The three executable
gates (ruff, pytest -W error, pytest) cover the artifact correctness surface that can be
mechanically verified. The remaining 26 checklist items require human judgment: was scope
correctly declared? was the right task completed? is the PR body conformant? These cannot be
verified by a script without building process introspection tooling that would be
disproportionate to the project's current stage. The deliberate architecture is: hard gates
for correctness, manual governance for judgment-dependent process obligations.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Manual governance balance is intentional design; no automation gap requires remediation at Phase 8 scale |

**Rationale:**
Automating judgment-dependent obligations (scope declaration correctness, checklist narrative
conformance, PR body adequacy) is not tractable at acceptable cost. The correct enforcement
model is human governance backed by the three mechanical gates. The observation is valid as a
long-term scaling concern but raises no actionable item for Phase 8.

**OBS-009 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-010] Response to OBS-010 — Architect-only clearance: intentional serialization

**Date:** 2026-03-13
**Architect:** Claude
**OBS verified:** YES — read SCRATCHPAD.md §Document Status and §How This Document Works:
  "Architect-owned: YES — Codex writes OBS entries; Claude writes DEC entries and controls
  status." DEC clearance and STATUS transitions to IDLE/CLEARED are sole architect
  responsibilities by explicit design.

**Architect finding:**
The serialization described in OBS-010 is the governance model's core invariant, not a
bottleneck to fix. The purpose of requiring architect clearance is precisely to prevent
unbounded task accumulation without architectural oversight — the same risk that T4-01
(broad changes, skipped gates) was designed to prevent. If Codex could self-clear OBS
entries, the scratchpad protocol would provide no value: it would be a log, not a
governance gate. The throughput dependency is a direct consequence of the design goal.
High OBS frequency (which could amplify the bottleneck) is controlled by the trigger
conditions and the in-flight work policy, which limit the rate of OBS accumulation.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Single-actor clearance is an intentional architectural invariant; high review latency is mitigated by trigger condition design, not by relaxing the clearance model |

**Rationale:**
The architect-only DEC model is not a single point of failure — it is a single point of
accountability, which is what governance requires. The alternative (distributed clearance)
removes the cross-session continuity check that prevents incremental scope drift. No change
warranted.

**OBS-010 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-011] Response to OBS-011 — Full-suite dual-run: accepted cost, Phase 9 review point

**Date:** 2026-03-13
**Architect:** Claude
**OBS verified:** YES — read AGENTS.md §2 HARD GATE: Gate 2 (`pytest -q -W error::pytest.PytestWarning`)
  and Gate 3 (`pytest -q`) are both mandatory per task. Re-run-all-after-failure rule confirmed.
  Suite size at this review: 1841 tests (CLAUDE.md historical snapshot).

**Architect finding:**
The observation is correct: two full-suite runs per task with complete re-execution on any
failure imposes compounding cost as suite size grows. This is an accepted trade-off at current
scale. Gate 2 and Gate 3 serve different purposes: Gate 2 catches warning-level regressions
that Gate 3 would pass silently; Gate 3 is the canonical green-state baseline. Collapsing
them into one run would eliminate the warning-sensitivity gate, which has caught real regressions
in Phase 7. At 1841 tests the dual-run is not a material bottleneck. The concern becomes
actionable when the suite significantly exceeds this volume (estimated threshold: ~3000 tests).

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Dual-run cost is acceptable at 1841 tests; this becomes a Phase 9 reconsideration point if suite exceeds ~3000 tests |

**Rationale:**
No architectural change warranted now. The scaling concern is noted as a Phase 9 review
trigger: if the suite reaches ~3000 tests, the gate design should be reviewed for options
(e.g., Gate 2 scoped to changed modules only, cached baseline for Gate 3). This is not a
debt entry — it is an informational marker. When the trigger is met, a proper ADR-first
evaluation applies.

**OBS-011 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-012] Response to OBS-012 — Out-of-scope routing conflict: OBS factually incorrect

**Date:** 2026-03-13
**Architect:** Claude
**OBS verified:** YES — read AGENTS.md §3.4 (line 301–305): "Write a SCRATCHPAD OBS entry
  (§15). Do NOT add it directly to TECHNICAL_DEBT.md without an architect DEC." Read AGENTS.md
  §12.2 (lines 631–639): "Do NOT add a TECHNICAL_DEBT.md entry directly — the architect
  creates or authorises debt entries via a DEC." Read AGENTS.md pre-delivery checklist line 584:
  "Out-of-scope findings are in SCRATCHPAD.md OBS entries (§15), not in code or directly in
  TECHNICAL_DEBT.md." Read SCRATCHPAD.md §Canonical Routing Rule (lines 41–58): "Single
  authoritative path. No alternative routes permitted. Direct TECHNICAL_DEBT.md entry by Codex
  without a preceding architect DEC is forbidden. On any conflict, this statement prevails."

**Architect finding:**
The conflict described in OBS-012 does not exist in the current documents. The OBS claims that
"AGENTS.md §3.4 and §12.2 require Codex to add out-of-scope findings directly to TECHNICAL_DEBT.md."
This is factually incorrect as of the current document state. Both §3.4 and §12.2 explicitly
prohibit direct TECHNICAL_DEBT.md entry and mandate the SCRATCHPAD.md → architect DEC → debt
entry path. The pre-delivery checklist (line 584) reinforces this. The SCRATCHPAD.md Canonical
Routing Rule is explicitly declared as the single authoritative statement that prevails on any
conflict. The OBS may have been written against an earlier version of AGENTS.md where the
conflict existed; the documents have since been fully aligned.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Claimed conflict does not exist in current documents; AGENTS.md §3.4, §12.2, and SCRATCHPAD.md §Canonical Routing Rule are fully consistent |

**Rationale:**
All routing instructions in AGENTS.md and SCRATCHPAD.md are aligned: OBS-first, architect
DEC, then debt entry. No residual ambiguity. No documentation change, no debt entry warranted.
The CLAUDE.md Engineering Rules table entry E8 also points to §3.4 / §15, which are now
consistent with the canonical routing rule.

**OBS-012 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-013] Response to OBS-013 — Debt-clear counter: intentionally manual

**Date:** 2026-03-13
**Architect:** Claude
**OBS verified:** YES — read AGENTS.md §12.5 (lines 672–683): debt-clear counter description
  and S2b snippet. Confirmed the S2b command outputs open debt count via grep on TECHNICAL_DEBT.md
  and explicitly states counter tracking is manual ("Counting: The debt-clear counter resets
  to 0 after a debt item is resolved. The counter increments on every task close").

**Architect finding:**
The observation is factually correct. The S2b command provides the open-debt-count proxy;
the debt-clear counter itself is tracked by the architect through manual reading of the
TECHNICAL_DEBT.md tracking table. This is intentional, not a gap. The debt-clear counter
is an architect-level governance signal — it reflects the rate of technical debt reduction
per session, which requires architectural judgment to interpret (not all closures have equal
weight, partial resolutions need context). A fully automated counter would produce a number
without the judgment layer that makes it useful. The "mandatory" language in §12.5 applies to
the requirement that Codex runs S2b and reports the output — not that the counter itself be
computed by script.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Manual debt-clear counter tracking is intentional; S2b provides the correct input signal; full automation would bypass the judgment layer that gives the counter architectural meaning |

**Rationale:**
The S2b command's role is to surface raw data (open count) that feeds the architect's
manual counter tracking. This is the correct division of labor: mechanical data extraction
(automatable) + architectural interpretation (not automatable). No change to the protocol
is warranted.

**OBS-013 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-014] Response to OBS-014 — MUST-rules vs machine enforcement: intentional design

**Date:** 2026-03-13
**Architect:** Claude
**OBS verified:** YES — read AGENTS.md §2 HARD GATE: three executable gates identified.
  Read scripts/check_scratchpad.sh: confirmed exit 1 on BLOCKING queue only, exit 0 for
  REVIEW_REQUESTED/UNDER_REVIEW (advisory, not blocking). Confirmed via grep of
  tests/test_claude_md_integrity.py and tests/test_documentation_consistency.py that these
  cover only selected structural invariants, not session-start protocol execution or
  checklist completeness.

**Architect finding:**
The observation is factually correct and consistent with OBS-009's finding. The gap between
MUST-level policy language and automated enforcement is system-wide and real. The architect
finding is the same as DEC-009: this is intentional design. The three hard gates (ruff,
pytest -W error, pytest) represent the set of governance obligations that are both (a) high
failure risk without automation and (b) mechanically verifiable at low cost. All other
MUST-level obligations — session-start protocol execution, PR body conformance, scope
declaration completeness, checklist narrative — require human judgment and cannot be
automated without disproportionate tooling investment. The `check_scratchpad.sh` returning
exit 0 for REVIEW_REQUESTED (rather than exit 1) is also intentional: the scratchpad gate
blocks new task starts via the in-flight work policy, not via a hard CI failure, because
the blocking condition depends on whether a new task is being started — not on the bare
presence of the REVIEW_REQUESTED state.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | The enforcement topology (three hard automated gates + manual governance for judgment-dependent obligations) is intentional and correct for Phase 8; no new automation warranted |

**Rationale:**
Identical to DEC-009 rationale. OBS-014 raises the same architectural question with a wider
scope. The answer is the same: hard mechanical gates for correctness artifacts; manual
governance for judgment-dependent process obligations. The `check_scratchpad.sh` behavior
(exit 0 for REVIEW_REQUESTED) is a deliberate design choice — making it exit 1 for all
non-IDLE states would block CI on any session that had a pending review, including sessions
where the review has not yet been performed but no task has started. That is a false-positive
gate. The current design correctly separates the CI gate (BLOCKING queue) from the protocol
gate (REVIEW_REQUESTED → architect review before new task).

**OBS-014 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-004] Response to OBS-004 — Engine instantiation semantics: deferred to multi-athlete task

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_athlete_isolation_invariant.py`; confirmed that
  guards cover profile data isolation (DB reads, metric dicts) but do not assert engine
  instance lifecycle (fresh-per-run vs. shared). ADR-0046 accepted but implementation not
  yet started (T5-16 closed = ADR accepted, not code delivered).

**Architect finding:**
The gap is real and correctly identified. The existing isolation invariant tests profile
data, not engine state. If CoachingScheduler pools engine instances, any mutable
intermediate state (e.g. cached physiological metrics, lock states in APL) would be a
source of cross-athlete contamination that the current test cannot detect. The risk is
currently zero because the multi-athlete scheduler does not yet exist. It becomes active
the moment CoachingScheduler implementation begins.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Trigger: CoachingScheduler implementation task opens — engine-instantiation lifecycle (fresh-per-run vs. shared) must be an explicit acceptance criterion in that task |

**Rationale:**
No guard is warranted now — there is no code to guard against. The correct action is to
ensure the design question is answered at the start of the implementation task and that
a corresponding test is added as part of that task's Definition of Done. This OBS serves
as the institutional memory that makes that requirement explicit when the task is assigned.
The task author must reference OBS-004 when writing acceptance criteria for CoachingScheduler.

**OBS-004 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-005] Response to OBS-005 — PostgreSQL concurrency gap: deferred to migration task

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `titan/core/database.py`; confirmed `threading.Lock` +
  `check_same_thread=False` pattern is SQLite-specific. Read
  `tests/test_database_manager_thread_safety.py` and `tests/test_harden_db_concurrency.py`;
  confirmed both test exclusively against SQLite connection semantics. ADR-0044 accepted,
  migration task not yet open.

**Architect finding:**
The gap is correctly identified and structurally significant. The threading tests are
SQLite-correct and will remain green during migration even if the PostgreSQL adapter has
broken concurrency semantics, because they test a different code path. This is the classic
"test passes, feature broken" pattern at an abstraction boundary. The gap is not a current
defect — it is a future defect that becomes possible the moment a second DB adapter exists.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Trigger: PostgreSQL migration task opens — concurrency validation for the new adapter must be an explicit acceptance criterion in that task's Definition of Done |

**Rationale:**
Writing PostgreSQL concurrency tests now would require a live PostgreSQL instance in CI,
which is premature and outside scope before the migration task is open. The correct action
is to ensure the migration task's acceptance criteria explicitly include: (a) concurrency
stress tests for the PostgreSQL adapter equivalent to the existing SQLite suite, and (b)
a note that the SQLite tests do not provide coverage for the new adapter. This OBS is the
institutional memory that surfaces that requirement when the task is assigned.

**OBS-005 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-006] Response to OBS-006 — Payload round-trip gap: deferred to FastAPI task

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_operator_console_dashboard.py`; confirmed all
  assertions are Python dict / value comparisons with no JSON serialization step.
  Read `titan/ui/operator_console.py`; confirmed payloads contain `datetime` fields
  (e.g. `last_updated`, session timestamps) that have no direct JSON representation
  and would require explicit serializer configuration in FastAPI. ADR-0013 accepted,
  FastAPI implementation not yet started.

**Architect finding:**
The gap is real and correctly scoped. The four payload types in `OperatorConsoleService`
(dashboard, session explorer, override workflow, calibration review) all contain Python
types that require explicit serialization handling in FastAPI (`datetime` → ISO 8601 string,
`Enum` → value string, `None` in typed fields → `null`). The existing dict-shape tests
will pass regardless, providing false confidence. A round-trip test (Python payload →
`json.dumps` → `json.loads` → assert shape + value) is a lightweight, deterministic guard
that will catch exactly this class of failure.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Trigger: FastAPI implementation task opens — round-trip serialization tests for all four OperatorConsole payload types must be an explicit acceptance criterion in that task |

**Rationale:**
The guard is well-defined (≤ 30 lines per payload type, deterministic, actionable failure
messages) and meets all four criteria for an automated guard. It is not written now because
the FastAPI layer does not exist yet — there is no serialization boundary to test against.
When the task opens, this OBS provides the precise requirement: one round-trip test per
payload type, covering `datetime`, `Enum`, and `None`-typed field serialization. No ADR
is required — this is an implementation-time test coverage requirement, not an architectural
decision.

**OBS-006 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-007] Response to OBS-007 — ADR deliverable drift: process rule added to AGENTS.md

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `TECHNICAL_DEBT.md` T5-08 Resolution section: lists only
  `PostgreSQLDatabaseManager`, backend parity tests, and `get_database_manager()`. Read
  `docs/adr/0044-postgresql-migration-phase8a-entry-gate.md` D1–D9 table: confirms D1–D5,
  D7–D9 have no corresponding implementation. Grepped codebase for `persistence.py`,
  `alembic/`, `test_athlete_rls_isolation`: none found. Acceptance gate in T5-08 entry
  references these non-existent paths — gate was not run at closure time.

**Architect finding:**
The observation is factually correct and fully verified. The drift is:
1. **Real:** D1–D5, D7–D9 of ADR-0044 are not implemented.
2. **Caused by a process gap:** The task closure protocol has no step that requires verifying
   each numbered ADR deliverable before setting status to RESOLVED. The acceptance gate is
   written as a shell command block, not as a per-deliverable checklist — making it possible
   to skip gate execution by inspection-only closure.
3. **Detected correctly by QA:** The Opus QA verdict (FAIL) was the correct signal.

T5-08 status has been corrected to ⚠️ PARTIAL. T5-08-B has been created in `TECHNICAL_DEBT.md`
with D1–D5, D7–D9 as binary acceptance criteria and an explicit concurrency acceptance
criterion per OBS-005 (which had already registered this risk as a trigger for the migration task).

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | Process rule: ADR Deliverable Checklist — mandatory at task closure when task references an ADR with a numbered deliverable table. Recorded in AGENTS.md §HARD GATE addendum (see below). |

**Process rule — effective immediately:**

When any task (Tn-xx) references an ADR that contains a numbered deliverable table (e.g.
ADR-0044 D1–D9, ADR-0018 Phase A/B checklist), the task entry in `TECHNICAL_DEBT.md` MUST
include an **ADR Deliverable Checklist** section before it may be set to RESOLVED:

```markdown
**ADR Deliverable Checklist (ADR-XXXX):**
| # | Deliverable | Status |
|---|---|---|
| D1 | <description> | ✓ DONE / ✗ NOT DONE |
| D2 | <description> | ✓ DONE / ✗ NOT DONE |
...
```

Rules:
- Any ✗ NOT DONE deliverable blocks RESOLVED status. Task must be PARTIAL or OPEN.
- If a task intentionally implements a subset, status is PARTIAL + a successor task covers
  the remaining deliverables (the T5-08 → T5-08-B split is the canonical pattern).
- The checklist is filled in by Codex at closure time, verified by QA, not set by assertion.

This rule is a **HARD GATE addendum** — same severity as the existing three-gate protocol
(ruff / pytest-W / pytest). It applies to all open Phase 8 tasks that reference ADRs with
deliverable tables: T5-08-B (ADR-0044), T5-16-A (ADR-0046).

**Rationale:**
The three existing mandatory gates (ruff, pytest -W error, pytest) verify code correctness
but cannot verify that all ADR deliverables were implemented — that requires a semantic
cross-reference that only a human checklist can provide. The process gap revealed by T5-08
is structural: a task can pass all three gates and still miss 7 of 9 ADR deliverables.
The ADR Deliverable Checklist closes this gap at the lowest possible cost (one table per ADR,
filled at closure time) without adding new tooling or CI complexity.

**OBS-007 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-001] Response to OBS-001 — Test layer markers: deferred to Phase 9 housekeeping

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `pyproject.toml` markers config (only `timeout` registered);
  confirmed via grep that no `@pytest.mark.unit/integration/governance` calls exist in the
  118 test files across root and `tests/`.

**Architect finding:**
The observation is factually correct. The suite has no layer taxonomy beyond filename
conventions. However, the cost/benefit ratio at this point in the project is unfavourable:
adding markers retroactively to ~118 files and ~1780 tests is a mechanical but large-scope
refactor with no change to test logic. The diagnostic benefit (faster `pytest -m governance`)
is real but not pressing at 1780 tests — the current `tests/test_phase*.py` / `tests/test_p0_*.py`
naming convention provides adequate targeted-run granularity via `pytest tests/test_p0*.py`.
Phase 8 priorities (PostgreSQL migration gate, multi-sport adapter, operator console) outweigh
a marker taxonomy refactor. This is a valid Phase 9 / housekeeping item.

**Decision:**
| Action | Detail |
|---|---|
| DEFERRED | Assigned to Phase 9 housekeeping — T5 marker taxonomy for unit/integration/governance layers |

**Rationale:**
Phase 8 is OPEN with G1–G11 entry gate criteria. A test infrastructure refactor of this scope
belongs in a dedicated housekeeping slot, not as a Phase 8 item. The existing filename convention
is sufficient for now. When the suite exceeds ~3000 tests (likely Phase 9), the cost of unmarked
tests becomes more acute and the refactor investment pays off more clearly. No ADR is required —
this is an engineering convenience, not an architectural decision.

**OBS-001 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-002] Response to OBS-002 — CI pattern brittleness: accepted trade-off, no action

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_claude_md_integrity.py` lines 31, 42–44, 83,
  92, 133, 141–149; confirmed 6 regex patterns tightly coupled to exact markdown surface form.

**Architect finding:**
The observation is factually correct. The brittleness is real and intentional. Doc integrity
tests are effective precisely because they are tight: a loose pattern (e.g. matching any number
near the word "modules") would miss the exact drift cases these tests were designed to catch.
The trade-off was made explicitly when these tests were introduced (T4-22 / ADR-0025): the
accepted cost is that legitimate reformatting of doc sections requires updating the test.
This is the correct engineering choice — it forces any doc reformatting to be a conscious act
that also updates the guard, rather than silently breaking the invariant.

No false positive has been observed. The markdown sections guarded by these patterns
(CLAUDE.md Key Files, ADR list, TECHNICAL_DEBT.md Phase header) have a de-facto stable
format because they are also machine-read by the test suite — there is no incentive to
reformat them casually.

A schema layer (YAML frontmatter, structured sections) would be a heavier investment with
no meaningful safety gain over the current approach for a project of this size and team.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | Pattern brittleness is an accepted, deliberate trade-off of doc integrity test design (ADR-0025); no change warranted |

**Rationale:**
Loosening the patterns would reduce detection sensitivity. Introducing a schema layer is
disproportionate to the risk. The current approach is the right balance for Phase 8.
The observation is noted for Phase 9 reconsideration only if false-positive rate increases.

**OBS-002 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-003] Response to OBS-003 — Snapshot drift already covered, no gap identified

**Date:** 2026-03-08
**Architect:** Claude
**OBS verified:** YES — read `tests/test_claude_md_integrity.py` lines 25–158; confirmed
  5 independent automated drift guards covering: ADR count, module count, test count,
  key file path existence, and phase state label parity between CLAUDE.md and TECHNICAL_DEBT.md.

**Architect finding:**
The observation is correct that snapshot drift is a risk — and also correct that it is already
substantially addressed. The 5 existing guards in `test_claude_md_integrity.py` cover every
quantifiable snapshot element in CLAUDE.md:
- Counts (ADR, module, test) → machine-checked
- File existence (Key Files table) → machine-checked
- Phase state (OPEN/CLOSED parity) → machine-checked

The remaining un-automated content (narrative descriptions, algorithm references, module
descriptions) is inherently prose and cannot be automatically validated against code without
building a documentation generator — which is disproportionate. The CLAUDE.md is explicitly
designated a "context snapshot" not a live specification; its narrative content is expected
to require periodic manual review, which is appropriate.

No specific gap has been identified by the OBS that is not already covered. The observation
is a confirmation that the current approach is sound, not a finding that requires new work.

**Decision:**
| Action | Detail |
|---|---|
| NO_ACTION | All quantifiable snapshot elements are already machine-checked; no residual gap identified |

**Rationale:**
Extending automated coverage to prose content would require a documentation generator or
LLM-based diff, which is out of scope for Phase 8 and disproportionate to the risk.
The existing 5 guards are the correct stopping point. The observation validates the existing
design — it does not reveal a deficit.

**OBS-003 marked:** REVIEWED
**Status:** PROCESSED

---


## Future Design Notes (Architect)

> This section is architect-authored. It records approved design directions that are not yet
> ADRs, not implementation instructions, and not OBS/DEC lifecycle entries. Content here must
> not be converted to ADRs, implementation tasks, or policy changes without a further explicit
> architectural decision. The STATUS field of this document is not affected by entries in this
> section.

---

### [FDN-001] Orchestration Modeling: 3-Layer Architecture Skeleton

**Date:** 2026-03-13
**Architect:** Claude
**Category:** Future Design Note — Architecture Note
**Source:** Approved synthesis — Architect evaluation (Sonnet) + Red-team review (Opus), 2026-03-13
**Status:** Architecture Note. Not an ADR. Not an implementation instruction.

**Approved skeleton:**

The approved direction for future orchestration modeling is a 3-layer architecture:

1. **Layer 1 — Pillar Scoring**
   Pure observation layer. Accepts raw metrics; returns a pillar vector.
   Boundary rule: if something concerns "what we do with this", it does not belong here.
   No knowledge of decisions, risk, or sessions.

2. **Layer 2 — Profile Abstraction**
   Compresses the pillar vector into an abstracted athlete state containing:
   primary limiter, secondary limiter, bottleneck count, dominant strengths, risk_weight.
   Boundary rule: Layer 2 output is pure state description — no prescriptions, no session bias.
   Prescription bias must not leak into Layer 2 output (noted risk from architect evaluation).

3. **Layer 3 — Decision Policy**
   The only layer with knowledge of sessions, intensity, and volume.
   Accepts the abstracted state; returns session prescription.
   Decision families (e.g. VO₂-limited, durability-limited) live here exclusively.

**5 pillars × 3 ordinal states model:**

The 5 pillars × 3 ordinal states model (243 raw states) is accepted as the
athlete-representation direction for Layers 1–2. Ordinal states (weak / moderate / strong)
are preferred over continuous scores given the precision characteristics of available
athletic metrics.

Not all 243 states are physiologically reachable. Pillars with strong positive correlations
(e.g. aerobic base and threshold capacity) make certain combinations near-impossible in
practice. Phantom / unreachable states must not drive handcrafted orchestration logic.

**Locked at skeleton level:**
- 3-layer architectural separation
- Ordinal (not continuous) representation principle
- Layer 2 prescription-free boundary rule

**Not locked — open design concerns:**

The following items are explicitly unresolved and must remain open until further
architectural decisions are made. No implementation should proceed against any of these:

| Concern | Description |
|---|---|
| Exact pillar set | 5 pillars are indicative; final set requires sufficient data support. Not fixed. |
| State thresholds | Thresholds for weak / moderate / strong are undefined per pillar. |
| Layer 1 input mapping | Exact pillar-to-metric mappings are vague. Must be specified before any ADR. |
| `risk_weight` definition | Not clear if scalar or categorical; not clear if independent or derived from other pillars / signals. Risk of becoming a dumping ground for ambiguous signals if not defined tightly. |
| Decision family definitions | No mapping rule from pillar vector to decision family exists yet. |
| Final prioritization logic | Unspecified. |
| Data confidence propagation | No mechanism defined for propagating data quality / confidence signals through the layers. |
| Temporal dimension | No model for how the pillar vector changes over time or how transitions between states are detected. |
| Staleness / recency | No staleness or recency policy for pillar inputs. |
| Layer 2 / Layer 3 boundary enforcement | Requires structural enforcement to prevent prescription semantics from leaking into Layer 2. |
| Override / human input path | Not modeled in the layer architecture. |

**Prerequisite for ADR promotion:**
The following must be resolved before this note can be promoted to a formal ADR:
- Layer 1 input mapping (which metrics feed which pillar)
- State threshold definitions (what constitutes weak / moderate / strong per pillar)
- `risk_weight` formalization (type, derivation rule, bounded range)
- Decision family definitions and the vector → family mapping rule

Until these are resolved, this note captures the skeleton only. No ADR, no implementation
task, and no policy change should be derived from this note alone.

---

## Governance Audit Triage Record (Owner-Approved)

> **What this section is:**
> This is a preservation / audit record for a governance audit triage pass completed
> 2026-03-13. It is NOT an OBS entry. It is NOT a DEC entry. It does NOT change the
> SCRATCHPAD STATUS. It does NOT create new tasks or new policy. It exists solely to
> preserve the full audit triage classification so no finding ID or category is lost.
>
> **Authoritative input:** Owner-approved synthesis, 2026-03-13.
> **Classification authority:** Owner/Architect (Claude), architectural session 2026-03-13.
> **Documents updated in this pass:** `AGENTS.md`, `CLAUDE.md`.

---

### A — Implemented Now (document clarifications applied)

| Finding | Scope | Change applied |
|---|---|---|
| **F-001** (+ F-NEW-001, F-NEW-002) | `AGENTS.md §14.1` Option C, `§14.4`, `§14.5` | Removed direct-to-TECHNICAL_DEBT.md routing. All three sections now route through SCRATCHPAD OBS → architect DEC → TECHNICAL_DEBT.md. Option C in §14.1 challenge template now says "Write a SCRATCHPAD OBS entry and stop". §14.4 correct-sequence now shows full canonical chain. §14.5 abstraction-proposal routing now says SCRATCHPAD OBS → architect DEC. **Blast-radius note (Opus extension):** F-001 expanded blast radius to §14.5 (F-NEW-001) and §14.1 Option C (F-NEW-002); both are addressed in this same pass. |
| **F-003** | `AGENTS.md §15` intro | Wording aligned with SCRATCHPAD.md authoritative statement. "Completes any current subtask already in progress, then stops" replaced with explicit MAY/MAY NOT language matching the canonical in-flight work policy. |
| **F-005** | `AGENTS.md §13.3` | Added definitional clarification distinguishing "additive column on existing table" (permitted) from "schema topology change" (requires §14.2). Prevents §13.3 from being used to bypass §14.2. Classification / definitional only — no new policy layer created. |
| **F-010** | `AGENTS.md §1` Role Boundaries table | Separated Owner row from Architect row. Added explicit paragraph: Owner instructions do not automatically carry Architect authority. Architect role is exercised by Claude operating in an architectural session (§3.6). Legitimate owner authority preserved. |
| **F-011** | `AGENTS.md §16.2` G10 | G10 Verification note updated to make explicit that it functions as an ongoing Phase 8B prerequisite, not only a historical Phase 8 entry gate. No new gate created — existing boundary made explicit. |

### B — Low-Risk Cleanup Applied

| Finding | Scope | Change applied |
|---|---|---|
| **F-002** | `AGENTS.md §9` Key Files table | Duplicate `titan/orchestration/daily_coach.py` row removed. Combined description retained in the single remaining row. No full dual-table migration performed. |
| **F-008** | `CLAUDE.md` Governance Lock Codes section | Section header updated to "reference snapshot only". Added note that canonical source is `CANONICAL_LOCK_CODES` in `titan/config/thresholds.py`. |
| **F-009** | `AGENTS.md §3.6` permitted edits table | Added "Clarification append to existing OBS entry in SCRATCHPAD.md" as an explicit permitted action, triggered by Claude's CLARIFICATION_NEEDED state. Clarification-of-existing-flow only; no new workflow logic. |

### C — Preserved / Not Changed

#### C1 — Leave As-Is (not changed now; reason recorded)

| Finding | Reason (owner-approved) |
|---|---|
| **F-004** | Consistent duplication across multiple locations; not worth touching now due to risk of policy drift if edited. |
| **F-006** | Debt-clear counter concern is valid but wrong time to address; revisit in a later session. |
| **F-007** | PILOT-01 Phase 9 ambiguity is valid but not urgent now. |
| **F-012** | Historical PR: TBD pattern; no governance value in retroactive archaeology. |
| **F-014** | Historical appendix snapshot; opportunistic note only; no dedicated change warranted now. |
| **F-015** | Self-correcting failure mode; no dedicated change warranted now. |

#### C2 — Rejected / No Action

| Finding | Reason (owner-approved) |
|---|---|
| **F-013** | False positive; reference is valid; no change required. |

---

### Classification completeness statement

All findings F-001 through F-015 are accounted for in this triage record:
- Implemented (A): F-001 (expanded to F-NEW-001 + F-NEW-002), F-003, F-005, F-010, F-011
- Cleanup applied (B): F-002, F-008, F-009
- Leave as-is (C1): F-004, F-006, F-007, F-012, F-014, F-015
- Rejected (C2): F-013

No finding ID has been dropped. No classification has been changed from the owner-approved synthesis.

---

---

## Binder1 Audit Triage — Architect Records Sync (2026-03-13)

**Records steward pass.** No implementation performed. No new architectural decisions.

### Status

```
Binder1 architectural triage: COMPLETE
Records layer: SYNCED
Codex execution: AUTHORIZED (subject to preconditions below)
SCRATCHPAD STATUS: IDLE
```

### Coverage

| DEC | Modules covered | Date |
|---|---|---|
| DEC-1 | ACWR Engine, Adaptive Memory, Adaptive Priority Lock | 2026-03-13 |
| DEC-2 | Remaining 29 modules from Binder1 audit corpus | 2026-03-13 |

Binder1 architectural triage is complete. All findings have been classified (S1–S5) and either approved for execution, recorded as debt entries, or explicitly blocked.

### Debt Entries Registered

T5-NEW-01 through T5-NEW-19 have been registered in `TECHNICAL_DEBT.md` as **T5-17 through T5-35** (sequential assignment, 2026-03-13). See the TECHNICAL_DEBT.md Tier 5 section and Tracking table for full details.

| DEC ID | TECHNICAL_DEBT.md ID | Module | Type | Status |
|---|---|---|---|---|
| T5-NEW-01 | T5-17 | ACWR Engine | Threshold Governance | OPEN |
| T5-NEW-02 | T5-18 | Adaptive Memory | Threshold Governance | OPEN (partial — T5-19 blocked) |
| T5-NEW-03 | T5-19 | Adaptive Memory | Open Question | BLOCKED |
| T5-NEW-04 | T5-20 | APL | Test Gap | OPEN |
| T5-NEW-05 | T5-21 | Athlete Profile | Code Hardening | OPEN |
| T5-NEW-06 | T5-22 | Athlete Profile | Serialization Contract | OPEN |
| T5-NEW-07 | T5-23 | Autonomic Fusion | Documentation | OPEN |
| T5-NEW-08 | T5-24 | Biomechanics | Architecture Debt | OPEN (blocked — brief required) |
| T5-NEW-09 | T5-25 | Database Manager | Architecture Debt | OPEN (blocked — brief required) |
| T5-NEW-10 | T5-26 | Drift Engine | API Contract | OPEN (P1) |
| T5-NEW-11 | T5-27 | Durability Engine | Threshold Governance | OPEN |
| T5-NEW-12 | T5-28 | Fatigue Engine | Threshold Governance | OPEN |
| T5-NEW-13 | T5-29 | Garmin Live Sync | Behavior Contract | OPEN |
| T5-NEW-14 | T5-30 | Governance Engine | Threshold Governance | OPEN (ADR-0009 ref required) |
| T5-NEW-15 | T5-31 | Intensity Governor | Threshold Governance | OPEN |
| T5-NEW-16 | T5-32 | Lactate Logic | Threshold Governance | OPEN |
| T5-NEW-17 | T5-33 | Periodization | Architecture Debt | OPEN (blocked — brief required) |
| T5-NEW-18 | T5-34 | Setup Wizard | Architecture Debt | OPEN (blocked — brief required) |
| T5-NEW-19 | T5-35 | Volume Load Gauge | Threshold Governance | OPEN |

### Duplicate / Cross-Reference Findings

The following cross-references were identified during registration. No renumbering or reinterpretation was performed. All entries confirmed DISTINCT and NEW except where noted.

| New Entry | Potential Overlap | Assessment |
|---|---|---|
| T5-17 | T1-04 (RESOLVED), T1-05 (RESOLVED) | DISTINCT. T1-05 covers dead duplicates in `constants.py` utility file; T5-17 covers inline Category A policy literals inside the ACWR science module. |
| T5-24 | T4-26 (RESOLVED) | DISTINCT. T4-26 addressed the orchestration contract layer broadly. T5-24 specifically captures the `biomechanics: object` annotation gap not covered by T4-26 resolution scope. |
| T5-25 | T5-08-B (OPEN) | RELATED but DISTINCT. T5-08-B covers full PostgreSQL migration implementation. T5-25 covers interface parity matrix as an architectural contract document. |
| T5-30 | T1-04 (RESOLVED) | DISTINCT. T1-04 resolved general hardcoded safety thresholds. T5-30 covers governance_engine.py class-local thresholds (0.80, 0.70) that were missed in T1-04's resolution scope. |
| T5-34 | T4-07 (RESOLVED), T4-12 (RESOLVED) | DISTINCT. T4-07/T4-12 addressed wizard UX and test coverage. T5-34 addresses architectural divergence between titan wizard and launcher wizard bootstrap contracts. |

### Blocked Items

| Item | Module | Blocked On |
|---|---|---|
| T5-19 | Adaptive Memory | Architect classification of `2.5/2.0/1.5` multipliers (Category A or B?) — DEC-1 §4.2 |
| T5-24 | Biomechanics | Typed orchestration contract brief required |
| T5-25 | Database Manager | Interface parity matrix design brief required |
| T5-33 | Periodization | Core/automated coupling contract brief required |
| T5-34 | Setup Wizard | Dual wizard bootstrap contract brief required |
| All S4 threshold extraction tasks (T5-17, T5-18, T5-27, T5-28, T5-30, T5-31, T5-32, T5-35) | Multiple | Blocked behind S1–S3 execution completion; each requires **separate PR** |
| Telegram gateway wiring (DEC-2 §Telegram) | Telegram | Requires green test net before wiring change |

### Codex Execution Preconditions (from DEC-2 §9)

Codex **MAY START** execution ONLY after ALL of the following are confirmed:

1. **Deterministic baseline confirmed:** `pytest -q` returns ≥1845 passed (deterministic). If nondeterministic — stop and report before anything else.
2. **All T5-17 through T5-35 entries registered:** ✅ Done (this pass, 2026-03-13).
3. **Out-of-scope failing tests resolved first (before module fixes):**
   - `tests/test_phase4_slo_alerts.py` — mentioned in DEC-2 §HRV Engine note (out of HRV scope; fix first per RED protocol)
   - `test_property_based.py::test_volume_load_gauge_resilient_to_non_numeric_acwr` — mentioned in DEC-2 §Optimal Time Calculator note (fix first per RED protocol)
4. **Execution order per module:** failing test → minimal code fix → gate run. Never code fix without failing test first.
5. **S4 threshold extraction tasks:** separate PRs only. Never bundled with S1–S3 execution items.
6. **S5 blocked items:** remain blocked until explicit architect unblock.

*Binder1 records sync completed: 2026-03-13. Records steward: Claude.*

---

*Protocol v1.1 — Last updated: 2026-03-07. Structural upgrade: BLOCKING/NON-BLOCKING queues
(mechanical gate via `scripts/check_scratchpad.sh`), CLARIFICATION_NEEDED state, per-phase
archive policy. Replaces STATUS-field-only v1.0.*

### [OBS-022] Audit Pass 6 — integrations contract/threshold/test-surface observations

**Date:** 2026-03-16
**Trigger:** Audit Pass 6 assignment (observer-only, `titan/integrations/`)
**Session context:** Bounded audit execution unit for integration modules
**Urgency:** NON-BLOCKING

**DoR (pre-OBS):**
- SCOPE CLEAR: PASS
- FILES IDENTIFIED: PASS
- CRITERIA BINARY: PASS
- TESTS KNOWN: PASS

**Files inspected:**
- `titan/integrations/garmin_sync.py`
- `titan/integrations/weather_api.py`
- `titan/integrations/telegram_bot.py`
- `titan/integrations/notification_gateway.py`
- `titan/integrations/__init__.py`
- `tests/titan/integrations/test_garmin_sync.py`
- `tests/titan/integrations/test_weather_api.py`
- `tests/titan/integrations/test_notification_gateway.py`
- `tests/titan/integrations/test_telegram_bot_observability.py`
- `tests/titan/integrations/test_telegram_bot_rationale.py`
- `tests/test_garmin_sync.py`
- `tests/test_garmin_sync_worker_lifecycle.py`
- `tests/test_telegram_scheduler_lifecycle.py`
- `tests/test_telegram_calibration_command.py`
- `tests/test_requirements_telegram_dependency_alignment.py`
- `tests/test_secret_handling_integrations.py`

**Observation (factual):**
1. **Contract ambiguity / suspicious coupling (notification fallback semantics):**
   - `TelegramChannel.send()` invokes `self._bot.send_daily_coaching(payload)` and returns `True` unless an exception is raised.
   - `TitanTelegramBot.send_daily_coaching()` returns the boolean result of `send_message()`.
   - Because `TelegramChannel.send()` does not read that returned boolean, a `False` return path from bot delivery is not represented at channel contract level unless the bot raises. This creates a contract-shape mismatch between boolean-returning downstream API and exception-only upstream success semantics.
   - References: `titan/integrations/notification_gateway.py:75-95`, `titan/integrations/telegram_bot.py:444-467`.

2. **Hidden threshold drift / repeated anti-pattern (inline environmental decision bands):**
   - Dew-point bands are encoded inline in `classify_heat_stress()` (`>24`, `>21`, `>18`, `>15`, `>12`, `>8`).
   - Additional dew-point scoring bands are encoded separately in `find_optimal_training_windows()` (`>21`, `>18`, `>15`, `<12`) with independent scoring weights.
   - The same decision domain (dew-point based training condition handling) is represented by multiple independent literal clusters in the same module.
   - References: `titan/integrations/weather_api.py:158-170`, `titan/integrations/weather_api.py:529-537`.

3. **Missing mirrored tests (behavioural branch coverage gap):**
   - Mirrored integration test file exists for notification gateway (`tests/titan/integrations/test_notification_gateway.py`), and it validates exception-path fallback.
   - Existing tests do not exercise the branch where bot call returns `False` without raising; current stubs return `None`/success or raise exceptions.
   - This leaves an unverified behavioural path at the channel boundary where boolean-returning downstream API contracts can differ from exception-driven assumptions.
   - References: `tests/titan/integrations/test_notification_gateway.py:15-139`, `titan/integrations/notification_gateway.py:75-97`, `titan/integrations/telegram_bot.py:359-417`, `titan/integrations/telegram_bot.py:444-467`.

**Pattern / scope:**
These findings are all within `titan/integrations/` and concern delivery/decision contract surfaces and literal policy encoding in integration-layer runtime logic.

**Architectural question raised:**
For integration modules, should runtime delivery contracts be treated as boolean-semantic interfaces end-to-end, exception-semantic interfaces, or explicitly mixed with documented precedence?

**Codex assessment (data only, no decision):**
Current integration-layer behavior shows mixed contract semantics and duplicated policy literals in weather decision logic, with one uncovered behavioral branch in notification gateway tests.

**Status:** REVIEWED

### [OBS-023] Audit Pass 7 — nutrition public API test-surface gap

**Date:** 2026-03-16
**Trigger:** Audit Pass 7 assignment (observer-only, `titan/features/`)
**Session context:** Bounded audit execution unit for feature modules
**Urgency:** NON-BLOCKING

**DoR (pre-OBS):**
- SCOPE CLEAR: PASS
- FILES IDENTIFIED: PASS
- CRITERIA BINARY: PASS
- TESTS KNOWN: PASS

**Files inspected:**
- `titan/features/nutrition_optimizer.py`
- `titan/features/weekly_planner.py`
- `titan/features/optimal_time_calculator.py`
- `titan/features/__init__.py`
- `tests/titan/features/test_nutrition_optimizer.py`
- `tests/titan/features/test_weekly_planner.py`
- `tests/titan/features/test_optimal_time_calculator.py`

**Observation (factual):**
1. **Missing mirrored tests (public-method coverage gap in nutrition feature module):**
   - `NutritionOptimizer` exposes public methods `add_weight_entry()`, `analyze_weight_trend()`, and `calculate_daily_nutrition()`.
   - Current mirrored nutrition tests cover `analyze_weight_trend()` scenarios only; there are no tests targeting `add_weight_entry()` retention behavior or `calculate_daily_nutrition()` output contract/branching.
   - References: `titan/features/nutrition_optimizer.py:35-216`, `tests/titan/features/test_nutrition_optimizer.py:1-65`.

**Pattern / scope:**
Isolated to `titan/features/nutrition_optimizer.py` within this execution unit; mirrored test file exists but does not exercise all public methods.

**Architectural question raised:**
For audit registration in this lane, should partial mirrored coverage in an existing module-level test file be tracked as a standalone debt item when uncovered public methods include recommendation and hydration contract outputs?

**Codex assessment (data only, no decision):**
The feature module currently has untested public API surface in its mirrored test file, while adjacent feature modules in the same scope include broader method coverage.

**Status:** REVIEWED

### [OBS-024] Audit Pass 8 — UI test topology drift around operator console

**Date:** 2026-03-16
**Trigger:** Audit Pass 8 assignment (observer-only, `titan/orchestration/` + `titan/ui/`)
**Session context:** Bounded audit execution unit for orchestration/UI modules
**Urgency:** NON-BLOCKING

**DoR (pre-OBS):**
- SCOPE CLEAR: PASS
- FILES IDENTIFIED: PASS
- CRITERIA BINARY: PASS
- TESTS KNOWN: PASS

**Files inspected:**
- `titan/orchestration/daily_coach.py`
- `titan/orchestration/contracts.py`
- `titan/orchestration/__init__.py`
- `titan/ui/menu_system.py`
- `titan/ui/operator_console.py`
- `titan/ui/setup_wizard.py`
- `titan/ui/__init__.py`
- `tests/titan/orchestration/test_daily_coach.py`
- `tests/titan/orchestration/test_daily_coach_observability.py`
- `tests/titan/orchestration/test_contracts.py`
- `tests/titan/ui/test_menu_system.py`
- `tests/titan/ui/test_setup_wizard.py`
- `tests/test_operator_console_dashboard.py`
- `tests/test_phase6_hygiene.py`

**Observation (factual):**
1. **Missing mirrored tests / environment-test fragility signal (operator console test location diverges from local convention):**
   - Within the same `titan/ui/` scope, mirrored tests exist under `tests/titan/ui/` for `menu_system.py` and `setup_wizard.py`.
   - `titan/ui/operator_console.py` is part of the `titan.ui` public API surface via `titan/ui/__init__.py`, but its behavior-focused tests are located at repository-root test path `tests/test_operator_console_dashboard.py` rather than under `tests/titan/ui/`.
   - A hygiene gate test explicitly imports that root-path module (`tests.test_operator_console_dashboard`) as part of Phase 6 validation, meaning this non-mirrored path is part of current enforcement assumptions.
   - References: `tests/titan/ui/test_menu_system.py:1-8`, `tests/titan/ui/test_setup_wizard.py:1-8`, `titan/ui/__init__.py:3-5`, `tests/test_operator_console_dashboard.py:1-15`, `tests/test_phase6_hygiene.py:252-258`.

**Pattern / scope:**
Isolated within this execution unit to `titan/ui/operator_console.py` test topology; adjacent UI modules in the same scope follow mirrored `tests/titan/ui/` placement.

**Architectural question raised:**
For UI modules in this subsystem, is mixed test topology (mirrored-path for some modules, root-level path for operator console with explicit hygiene import dependency) an intentional contract or a register-level inconsistency to be normalized by architect decision?

**Codex assessment (data only, no decision):**
Current enforcement relies on both mirrored and root-level test module placement for `titan/ui` components, creating a scope-local convention split that is observable in active hygiene checks.

**Status:** REVIEWED

---

### [OBS-027] Garmin audit program — findings summary (OBS-025 + OBS-026 + zero-sync investigation)

**Date:** 2026-03-23
**Trigger:** Garmin audit program registration (OBS-025 deterministic audit + OBS-026 data-to-action audit + zero-sync root-cause investigation)
**Session context:** Garmin data pipeline correctness audit / safety-gate integrity
**Urgency:** NON-BLOCKING
**Files involved:**
- `docs/OBS-025-garmin-audit.md` — line-by-line audit of sync + science engines (37 findings)
- `docs/OBS-026-garmin-action-audit.md` — data-to-action pipeline audit (27 findings)
- `docs/garmin_zero_sync_investigation.md` — root-cause analysis of silent 0/0/0/0 sync bug
- `titan/integrations/garmin_sync.py`
- `titan/science/trimp_engine.py`, `titan/science/hrv_engine.py`, `titan/science/efficiency_engine.py`
- `titan/science/governance_engine.py`
- `titan/science/critical_speed.py`, `titan/science/autonomic_engine.py`
- `titan/orchestration/daily_coach.py`
- `titan/features/weekly_plan.py`, `titan/features/nutrition_optimizer.py`

**Observation:**
Three audit documents produced a consolidated set of findings across the full Garmin data pipeline. The dominant failure mode is **optimistic defaulting**: when Garmin data is missing, stale, or null, the pipeline substitutes "healthy" or "optimal" values, systematically bypassing the safety gates the system was designed to enforce.

**HIGH severity findings (not yet fixed):**
- OBS-025 F-13: TRIMP uses session maxHR instead of athlete HRmax → misclassified training zones, skewed TSB/CTL/ATL
- OBS-025 F-29: Sleep field mapping mismatch (`sync_sleep()` → `_persist_garmin_data`) → RHR defaults to 0, H3 gate cannot fire (separate decision pending)
- OBS-025 F-27/F-32: HRV multi-day sync discards 6 of 7 days → baseline from single day on restart (separate decision pending)
- OBS-026 B1-F04: ACWR defaults to 1.0 (sweet spot) when Garmin fails → VO2 eligibility and intensity gates see "all clear"
- OBS-026 B2-F01: CS confidence defaults to 1.0 when `cs_tracker` is None → CS_CONFIDENCE_LOCK never fires
- Zero-sync Z1+Z2: Stale token assumed valid on 429 + empty sync recorded as success → silent 0/0/0/0 loop (separate decision pending)

**MEDIUM severity findings registered as T5-44–T5-59:**
- OBS-025 F-07: Population SD in HRV baseline (should be sample SD per Plews et al.) → `hrv_engine.py:66`
- OBS-025 F-08: No HRV deduplication — overlapping syncs inflate baseline log → `hrv_engine.py:55`
- OBS-025 F-17: Unguarded ZeroDivisionError when Garmin pace=0 → `efficiency_engine.py:56`
- OBS-025 F-20: Garmin data age not propagated into governance context → `governance_engine.py` context dict
- OBS-025 F-21/F-22: Missing sleep/readiness defaults to 100 (safety-first requires conservative) → `governance_engine.py:198,205`
- OBS-025 F-31: All Garmin activities classified as EASY regardless of actual session type → `daily_coach.py:1256`
- OBS-026 B1-F03: ReadinessEngine TypeError on null HRV (unguarded null propagation crash path)
- OBS-026 B1-F05: drift_pct defaults to 0.0 (perfect efficiency) when Garmin fails → `daily_coach.py:708`
- OBS-026 B2-F02: `apply_thermal()` uses dry-bulb temperature only; ignores dew point despite ESI model in thresholds.py → `critical_speed.py:218-234`
- OBS-026 B2-F03: AFI confidence not degraded for sparse HRR data → `autonomic_engine.py:120`
- OBS-026 B3-F01: Weekly plan never re-evaluated on mid-week Garmin data changes → `weekly_plan.py`
- OBS-026 B3-F02: `_apply_hrv_adjustments` TypeError on null HRV values → `weekly_plan.py`
- OBS-026 B3-F04: NutritionOptimizer dew_point defaults to 15°C (optimistic) → `nutrition_optimizer.py:188`

**Pattern / scope:**
System-wide optimistic-default pattern across 9 modules in 4 architectural layers. No project-wide convention for "missing Garmin data → conservative assumption." Each module independently chose an optimistic default.

**Architectural question raised:**
Should a canonical `MISSING_DATA_POLICY` convention be established in `thresholds.py` that encodes the safety-first rule "missing Garmin data → conservative assumption, never optimistic"?

**Codex assessment (data only, no decision):**
All HIGH findings directly undermine active safety gates (H2, H3, CS_CONFIDENCE_LOCK, VO2 eligibility). F-29 and B1-F04 combine to allow VO2 eligibility to pass when it should fail due to absent data. The zero-sync bug silently produces stale/default-driven governance on every startup. MEDIUM findings registered as T5-44–T5-59 in TECHNICAL_DEBT.md.

**Status:** REVIEWED

---

