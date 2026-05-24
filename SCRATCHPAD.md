# TITAN OS — Engineering Scratchpad (Πρόχειρο)

**Protocol version:** 1.1
**Architect-owned:** YES — Codex writes OBS entries; Claude writes DEC entries and controls status.
**Purpose:** Structured communication channel between Codex (engineer) and Claude (architect).
Codex writes raw engineering observations here. Claude reads, verifies, decides, and converts
them to clean tasks in `TECHNICAL_DEBT.md`. Neither party acts on observations alone.

---

## Document Status

```
STATUS: IDLE
```

Valid states:
- `IDLE` — no pending observations; Codex may proceed with assigned tasks
- `REVIEW_REQUESTED` — Codex has written one or more OBS entries; Claude must review before new tasks are assigned. **In-flight work policy (single authoritative statement):** Codex MAY complete any subtask already in progress at the moment of writing the OBS. Codex MAY NOT start any new top-level task. Trigger-specific notes in `AGENTS.md §15` are consistent with this rule and do not override it.
- `UNDER_REVIEW` — Claude is currently processing the pending OBS entries
- `CLARIFICATION_NEEDED` — Claude has written a partial DEC and requires additional context from Codex before deciding
- `CLEARED` — all OBS entries processed; Codex may continue (Claude will reset to IDLE after clearing)

**IMPORTANT — Codex:** Run `scripts/check_scratchpad.sh` at Step 0.5 (after `setup_env.sh`). The
script will fail with exit code 1 if the BLOCKING Queue is non-empty. Do not bypass it.
When you set STATUS to `REVIEW_REQUESTED`, **complete any current subtask already in progress,
then stop**. Do not begin any new top-level task until Claude sets status to `IDLE` or `CLEARED`.
This is not optional.

**IMPORTANT — Claude:** When status is `REVIEW_REQUESTED` at session start, process all PENDING
OBS entries before assigning any new task to Codex. Run `scripts/check_scratchpad.sh` to
confirm the gate is clear before proceeding. See §A-SCRATCHPAD-1 in `CLAUDE.md`.

**CLARIFICATION flow:** When Claude writes a DEC with decision `CLARIFICATION_NEEDED`, Claude
sets STATUS to `CLARIFICATION_NEEDED`. Codex appends the requested context to the original OBS
entry (labelled `**Clarification (YYYY-MM-DD):**`) and then resets STATUS to `REVIEW_REQUESTED`.
Claude then resumes the DEC. This flow may repeat at most once per OBS entry.

---

## Canonical Routing Rule — Out-of-Scope Findings

**Single authoritative path. No alternative routes permitted.**

```
Engineer discovers out-of-scope finding
  → writes SCRATCHPAD OBS entry (this document)
  → sets STATUS: REVIEW_REQUESTED
  → completes current subtask, then stops
  → architect reads, verifies, writes DEC
  → DEC decision NEW_DEBT_ENTRY → TECHNICAL_DEBT.md entry created
```

**Direct `TECHNICAL_DEBT.md` entry by Codex without a preceding architect DEC is forbidden.**

This section is the single source of truth for out-of-scope routing. All references to
out-of-scope handling in `AGENTS.md` (§3.4, §12.2, §15) and `CLAUDE.md` (Rule E8) point
here. On any conflict, this statement prevails.

---

## How This Document Works

### Codex → Claude (OBS entries)

Codex writes **Observation (OBS)** entries when specific trigger conditions are met
(see §15 in `AGENTS.md`). Each OBS entry is a raw engineering finding — Codex does NOT make
architectural decisions here. Codex only:
- Describes what was found (facts, patterns, code locations)
- States what architectural question it raises
- Flags urgency (BLOCKING / NON-BLOCKING)

OBS entries use sequential IDs: `OBS-001`, `OBS-002`, etc.
New OBS IDs always increment from the highest existing ID, including REVIEWED entries.

**BLOCKING OBS** go in the `## BLOCKING Queue` section.
**NON-BLOCKING OBS** go in the `## NON-BLOCKING Queue` section.

### Claude → Codex (DEC entries)

Claude writes **Decision (DEC)** entries in response to OBS entries. Each DEC:
- References the OBS it responds to
- States the architect's verified finding
- Records the decision taken (new debt entry / ADR / no action / defer / clarification needed)
- Marks the corresponding OBS as `REVIEWED`

DEC IDs match the OBS they respond to: `DEC-001` responds to `OBS-001`.

### Lifecycle of an OBS entry

```
Codex writes OBS → places in BLOCKING or NON-BLOCKING queue → sets STATUS: REVIEW_REQUESTED
  → Claude runs check_scratchpad.sh (Step 0.5) — confirms gate state
  → Claude reads + independently verifies findings (BLOCKING first, then NON-BLOCKING)
  → [optional] Claude writes partial DEC → STATUS: CLARIFICATION_NEEDED
      → Codex appends clarification → STATUS: REVIEW_REQUESTED → Claude resumes DEC
  → Claude writes final DEC + creates TECHNICAL_DEBT.md entries if needed
  → Claude marks OBS as REVIEWED + marks DEC as PROCESSED
  → When all OBS cleared: status → IDLE
```

---

## Trigger Reference (quick summary)

| Trigger | Who | When |
|---|---|---|
| T-SCRATCHPAD-1 | Codex | After each T4-01 subsystem completion |
| T-SCRATCHPAD-2 | Codex | Before crossing into a new Tier |
| T-SCRATCHPAD-3 | Codex | When 3+ related out-of-scope findings accumulate in one session |
| T-SCRATCHPAD-4 | Codex | When a Phase is declared CLOSED |
| T-SCRATCHPAD-5 | Codex | Alongside every §13.2 architectural decision-point stop |
| A-SCRATCHPAD-1 | Claude | At every session start (run check_scratchpad.sh before assigning tasks) |
| A-SCRATCHPAD-2 | Claude | Before writing any new TECHNICAL_DEBT.md planning block |
| A-SCRATCHPAD-3 | Claude | Before declaring any Phase CLOSED |

Full trigger specifications: Codex → `AGENTS.md §15`; Claude → `CLAUDE.md §Architect Scratchpad Review Protocol`.

---

## OBS Entry Format

```markdown
### [OBS-XXX] <short title (≤ 10 words)>

**Date:** YYYY-MM-DD
**Trigger:** T-SCRATCHPAD-N — <trigger name>
**Session context:** T<tier>-<id> / Phase X.Y / Subsystem: <name>
**Urgency:** BLOCKING | NON-BLOCKING
**Files involved:**
- `path/to/file.py` — <one-line reason>

**Observation:**
<Factual description of what was found. Code snippets inline if helpful.
No opinions on the fix. No design proposals. Facts only.>

**Pattern / scope:**
<Is this isolated or does it appear in multiple places? Quantify if possible.>

**Architectural question raised:**
<The specific question Codex cannot answer without architect approval.
Must be a single, concrete question — not a vague concern.>

**Codex assessment (data only, no decision):**
<What Codex believes the impact is, based on observable evidence.
No proposed solution. If unsure, say so.>

**Status:** PENDING
```

---

## DEC Entry Format

```markdown
### [DEC-XXX] Response to OBS-XXX — <short title>

**Date:** YYYY-MM-DD
**Architect:** Claude
**OBS verified:** YES — <how verified: code read / test run / cross-reference with ADR-XXXX>
           | NO — <why observation is factually incorrect>

**Architect finding:**
<What the architect confirmed after independent verification. This supersedes the OBS
assessment. If the OBS was incorrect, explain why.>

**Decision:**
| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T<N>-<id> created in TECHNICAL_DEBT.md — <one-line description> |
| ADR_NEEDED | ADR-XXXX to be authored before implementation |
| NO_ACTION | <reason: existing coverage / acceptable risk / out of scope> |
| DEFERRED | Assigned to Phase X — <reason for deferral> |
| CLARIFICATION_NEEDED | <exact question for Codex — one sentence, answerable by reading code> |

**Rationale:**
<Why this decision was made. Reference ADRs, existing constraints, or risk analysis.
If CLARIFICATION_NEEDED: explain what is missing and why it blocks the decision.>

**OBS-XXX marked:** REVIEWED | PENDING_CLARIFICATION
**Status:** PROCESSED | AWAITING_CLARIFICATION
```

---

## BLOCKING Queue

> *All OBS entries in this queue have been reviewed and archived (2026-04-04/2026-04-05).
> See Architect Review Log: DEC-026 (OBS-028), DEC-027 (OBS-029), DEC-035 (OBS-037),
> DEC-036 (OBS-038), DEC-037 (OBS-039), DEC-038 (OBS-041), DEC-039 (OBS-040). New debt entries:
> HD-05 (OBS-038, TECHNICAL_DEBT.md), HD-08 (OBS-041, TECHNICAL_DEBT.md).*

## NON-BLOCKING Queue

### [OBS-040] HD-08 — DailyCoach decision pipeline runs on mixed data epochs after partial persistence failure

**Date:** 2026-04-04
**Trigger:** T-SCRATCHPAD-5 — architectural decision-point stop (§13.2)
**Session context:** Phase 9 hardening Wave 4 / Subsystem: titan/orchestration/daily_coach.py
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/orchestration/daily_coach.py` — `_persist_garmin_data`, `_run_governance`, `_build_coaching_context`, the 12-step morning routine pipeline (steps 1–12)

**Observation:**
The DailyCoach 12-step morning routine runs sequentially. Each step either succeeds (writes to DB, updates engine state) or partially fails (logs error, continues). ADR-0020 established `PERSISTENCE_DEGRADED_CEILING` — a confidence ceiling applied when persistence fails — but it addresses only the case where ALL persistence fails. It does not address the case where SOME steps succeed and SOME fail within a single morning routine run.

Concrete mixed-epoch scenario: Step 4 (HRV sync + persist) succeeds, writing fresh HRV data (epoch T). Step 6 (sleep sync + persist) fails, leaving stale sleep data (epoch T-7d) in the DB. Steps 8–10 (governance, session recommendation) now read: fresh HRV from epoch T, stale sleep from epoch T-7d. The governance engine receives a mixed-epoch context — not an all-fresh or all-stale context — and cannot distinguish this from a fully fresh one.

The `PERSISTENCE_DEGRADED_CEILING` fires when the persistence adapter itself raises (ADR-0020 policy). It does NOT fire when individual sync methods return partial data (empty lists due to inner exceptions) that is then saved alongside fresh data from other sources.

No "data epoch coherence check" exists. The governance context has no `mixed_epoch` flag or `data_freshness_confidence` field that would cause downstream gates to apply additional conservatism.

**Pattern / scope:**
The pattern affects the full 12-step pipeline in `daily_coach.py`. The fix scope is unclear: it could range from (a) a per-step epoch tag attached to each data source in the governance context, to (b) a pipeline abort-on-partial-failure policy (conservative but potentially over-restrictive), to (c) a data freshness confidence penalty applied proportionally to the number of failed sync steps. Each option has different safety/availability tradeoffs.

**Architectural question raised:**
What is the architect-approved scope for the HD-08 Frankenstein-state fix? Specifically: (1) Should a mixed-epoch state be detected and surfaced as a flag in the governance context, or should it trigger a pipeline abort? (2) Is a per-source freshness timestamp in the governance context (already partially present via `garmin_data_age_hours`) sufficient, or is a new coherence check needed? (3) What is the appropriate conservative response: apply `PERSISTENCE_DEGRADED_CEILING`, downgrade to REST recommendation, or emit an alert and proceed?

**Codex assessment (data only, no decision):**
`garmin_data_age_hours` (T5-48) already propagates a single age timestamp to governance context. However, it represents the age of the LAST sync, not a per-source freshness map. If HRV was synced 1h ago but sleep was synced 7 days ago, `garmin_data_age_hours` reflects 1h — masking the stale sleep path. A per-source freshness dict would capture this, but requires schema changes to the governance context payload.

**Status:** REVIEWED

---
## Architect Review Log

### [DEC-036] Response to OBS-038 — AuthenticatedRateLimiter key accumulation: NEW_DEBT_ENTRY HD-05

**Date:** 2026-04-04
**Architect:** Claude
**OBS verified:** YES — read `titan/api/main.py`:49–57: confirmed `self._requests: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)` with no eviction policy. Confirmed expired timestamps are pruned per-deque but empty deque keys are never removed. Cross-referenced TECHNICAL_DEBT.md: T5-36 covers rate-limiting implementation but does not address key eviction. No existing task covers this gap.

**Architect finding:**
OBS-038 is factually correct. The `defaultdict(deque)` accumulates one entry per unique `(user_id, role, method:path)` triplet indefinitely. An adversary issuing requests across many unique paths or rotating through many user accounts can inflate `self._requests` without bound. Option C (Redis) is out of Phase 9 scope. Option B (periodic sweep) introduces a background thread. Option A (LRU ceiling with a constant) is the cleanest architectural guarantee — a fixed ceiling cannot be exhausted by timing-based attacks.

**Decision:** Option A — fixed max-keys ceiling with LRU eviction.

| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | HD-05 — `AuthenticatedRateLimiter._requests` grows unboundedly; add `RATE_LIMITER_MAX_KEYS = 10_000` to `thresholds.py` and LRU eviction to `AuthenticatedRateLimiter` when key count exceeds ceiling; files: `titan/api/main.py`, `titan/config/thresholds.py` |

**OBS-038 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-037] Response to OBS-039 — DegradedModeTracker persistence: NO_ACTION (already implemented by HD-06)

**Date:** 2026-04-04
**Architect:** Claude
**OBS verified:** YES — read `titan/orchestration/daily_coach.py`:87–140: confirmed
  `DegradedModeTracker.__init__` accepts `db: DatabaseManager | None`; `_hydrate_from_db()`
  restores timers from `degraded_mode_state` SQLite table on startup; `_persist_state()` upserts/
  deletes per failure-type rows via `DatabaseManager`. Class docstring: "State is persisted to
  the `degraded_mode_state` SQLite table so that degradation timers survive process restarts
  (HD-06 / OBS-039)."

**Architect finding:** OBS-039 describes a gap that has already been closed by the HD-06 implementation. No further action required.

| Action | Detail |
|---|---|
| NO_ACTION | HD-06 already resolved OBS-039. `DegradedModeTracker` persists to `degraded_mode_state` via `_hydrate_from_db()` + `_persist_state()`. |

**OBS-039 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-038] Response to OBS-041 — PersistenceFailure mixed state: NEW_DEBT_ENTRY HD-08

**Date:** 2026-04-04
**Architect:** Claude
**OBS verified:** YES — read `titan/orchestration/daily_coach.py`:534–601: confirmed
  `_step3_feed_hrv_hrr()` calls `self.db.save_hrr()` without `persistence_degraded` guard;
  step 6 calls `self.db.update_glycogen_debt(today_str, ...)` unconditionally. Both UPDATE
  operations silently affect 0 rows when `daily_metrics` has no row for `today_str`. No event
  emitted for the 0-row case. H3 gate: `today_rhr` (ephemeral) vs `baseline_rhr` (DB-derived)
  confirmed as mixed-epoch. `PERSISTENCE_DEGRADED_CEILING` runs last in `apply_constraints`.

**Architect finding:** Three bounded phenomena: (1) silent no-ops in `save_hrr`/`update_glycogen_debt` — fix: emit `_daily_coach_event` when `persistence_degraded=True`; (2) mixed-epoch H3 input — fix: add `persistence_degraded: bool` to governance context (gates unchanged — they are safety-critical); (3) gate ordering for `PERSISTENCE_DEGRADED_CEILING` is intentional (REST from H2/H3 is already maximally conservative) but observability is missing — fix: add `persistence_degraded` field to `coaching_data` payload and annotate Telegram message. No new ADR needed; ADR-0020 covers the policy; these are implementation completeness items.

| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | HD-08 — Three bounded PersistenceFailure observability/coherence fixes: emit skip events when persist calls are no-ops; propagate `persistence_degraded` bool to governance context and coaching payload; annotate Telegram output. Files: `daily_coach.py` (steps 3, 6, payload); `governance_engine.py` (context passthrough only — no gate logic changes). |

**OBS-041 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-039] Response to OBS-040 — HD-08 pipeline phenomena: NO_ACTION

**Date:** 2026-04-05
**Architect:** Claude
**OBS verified:** YES — OBS-040 raises three phenomena in the DailyCoach 12-step pipeline after
  partial persistence failure: (1) silent no-ops in `save_hrr`/`update_glycogen_debt` when
  `persistence_degraded=True`; (2) mixed-epoch H2/H3 inputs (ephemeral today-data vs DB-derived
  baseline); (3) `PERSISTENCE_DEGRADED_CEILING` ordering at end of `apply_constraints`. All three
  phenomena were already identified and fully resolved by DEC-038 (T5-71 / HD-08):
  `data_confidence_low=True` propagated when `persistence_degraded=True`; WARNING events emitted
  for no-op persist calls; `persistence_degraded: bool` added to governance context and
  `coaching_data` payload; Telegram message annotated when degraded. OBS-040 adds no new finding
  beyond existing DEC-038 / HD-08 coverage.

**Architect finding:** OBS-040 is substantively answered by DEC-038 (T5-71 / HD-08). The three
phenomena (silent no-ops, H2/H3 ephemeral data, PERSISTENCE_DEGRADED_CEILING ordering) are
addressed via `data_confidence_low=True` when `persistence_degraded=True`. No further
architectural action required.

| Action | Detail |
|---|---|
| NO_ACTION | Substantively answered by DEC-038 (T5-71/HD-08). All three phenomena addressed via `data_confidence_low=True` when `persistence_degraded=True`. No new finding beyond existing coverage. |

**OBS-040 marked:** REVIEWED
**Status:** PROCESSED

---
## Archive

> **Per-phase archive policy:** When a Phase is declared CLOSED (A-SCRATCHPAD-3), all REVIEWED
> OBS + PROCESSED DEC pairs for that phase are moved to a dedicated archive file:
> `archive/scratchpad_phase_X.Y.md`. The Archive section below retains only the last Phase's
> entries for immediate reference. Earlier phases live in `archive/`. The archive is never
> deleted — it is the engineering memory of cross-session findings that shaped
> `TECHNICAL_DEBT.md` decisions.

> **Archive note (2026-03-08):** OBS-001 / OBS-002 / OBS-003 and their DECs were processed
> during Phase 8 (session: future-maintenance-notes). OBS-001 resulted in a DEFERRED Phase 9
> debt entry (test layer marker taxonomy). OBS-002 and OBS-003 resulted in NO_ACTION.
> Full entries remain in NON-BLOCKING Queue section above (marked REVIEWED) until Phase 8 CLOSED.

---
### [OBS-041-CI] del athlete_id in persistence.py — pre-existing FP-08

**Date:** 2026-04-05
**Reported by:** CI gate G-CI-04 (invariant-athlete-id-drop)
**File:** `titan/core/persistence.py:992,1070`

`del athlete_id` found at both locations. These are pre-existing uses predating
the G-CI-04 gate. Pattern is FP-08 (sentinel deletion, not data loss).

**Status:** REVIEWED

**DEC:** Pre-existing debt. G-CI-04 correctly flags these. Fix scoped to Phase 9.
Assign new T5-xx: remove `del athlete_id` from `persistence.py:992,1070` and
replace with explicit comment documenting why the variable is not used, or
restructure to avoid the deletion. Does not block current merge.

---

### [OBS-042-CI] naive datetime.now() in non-governance modules — pre-existing HR-01 debt

**Date:** 2026-04-05
**Reported by:** CI gate G-CI-02 (original broad-scope run before scope reduction)
**Files:** `titan/integrations/telegram_bot.py`, `titan/ui/menu_system.py`,
`titan/integrations/weather_api.py`, `titan/science/critical_speed.py`,
`titan/science/outcome_tracker.py`, `titan/core/periodization.py`,
`titan/core/athlete.py`

29 naive `datetime.now()` calls across 7 non-governance modules. All pre-existing.
HR-01 (timezone-aware datetimes) applies to new code going forward. Governance-critical
scope (governance_engine, hrv_engine, daily_coach, garmin_sync, database) is CLEAN.

**Status:** REVIEWED

**DEC:** Pre-existing debt. G-CI-02 scope has been reduced to governance-critical
modules only (5 files). Full cleanup of remaining 7 modules = separate Phase 9
debt item. HR-01 enforcement for new code remains active. Does not block current merge.

---

### [OBS-043] H2/H3 except blocks: FAIL-OPEN on None/invalid input

**Date:** 2026-04-05
**Trigger:** Architect-authorized enforcement integrity audit (bypass path verification)
**Session context:** Audit pass / read-only / enforcement integrity audit
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/science/governance_engine.py` — `_check_hard_stops()` lines 309–322 (H2) and 341–354 (H3)

**Observation:**
`_check_hard_stops()` H2 and H3 exception handlers:

```python
# H2
except (TypeError, ValueError):
    h2_trigger = False   # line 321–322

# H3
except (TypeError, ValueError):
    h3_trigger = False   # line 353–354
```

When `context.get("today_hrv")` or `context.get("baseline_hrv")` is `None`,
`float(None)` raises `TypeError`, caught here → `h2_trigger = False`. No REST is
forced, no degraded flag is emitted. A session entering `apply_constraints()` as
INTERVALS remains INTERVALS if both HRV keys are absent.

Same pattern for H3 with `today_rhr`/`baseline_rhr`.

**Mitigation in normal path:** DailyCoach uses `_safe_float(hrv_summary.get('latest_hrv'), 0.0)` (line 553) and `_safe_float(hrv_summary.get('baseline'), 50.0)` (line 554) before passing to governance, so `today=0.0, baseline=50.0 → delta=50.0 ≥ 15.0 → H2 fires`. Conservative-fail in the DailyCoach path.

**Bypass path:** Direct callers of `apply_constraints({"today_hrv": None, ...})` — e.g., operator console, tests, API adapters — receive no REST and no warning. FAIL-OPEN for these call sites.

**Pattern / scope:**
H2 (line 321–322), H3 (line 353–354). H4 (line 421–422) and H5 (line 446–447) have the same pattern but are softer gates (EASY ceiling, not REST).

**Architectural question raised:**
Should `_check_hard_stops()` treat `TypeError`/`ValueError` on HRV/RHR input as
missing safety-critical data and apply a conservative fallback (e.g., emit a
DATA_MISSING_CONSERVATIVE log + apply EASY ceiling), consistent with ADR-0051?

**Codex assessment (data only, no decision):**
Governance-critical. DailyCoach path is safe via _safe_float(). External / direct
callers are FAIL-OPEN without visibility. No code change in this audit pass.

**Status:** REVIEWED

---

### [OBS-044] PostgreSQL training_log INSERT missing ON CONFLICT DO NOTHING

**Date:** 2026-04-05
**Trigger:** Architect-authorized enforcement integrity audit (bypass path verification)
**Session context:** Audit pass / read-only / enforcement integrity audit
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/core/database.py` — `PostgreSQLDatabaseManager.save_activity()` line 2201

**Observation:**
`PostgreSQLDatabaseManager.save_activity()` at line 2201:

```python
cursor.execute("""
    INSERT INTO training_log (
        date, session_type, ... garmin_activity_id, quality_flag
    ) VALUES (%s, ...)
""", ...)
```

No `ON CONFLICT DO NOTHING` or `ON CONFLICT (garmin_activity_id) DO NOTHING`.

A `UNIQUE INDEX` on `garmin_activity_id` exists (line 2139, partial where NOT NULL),
so duplicate Garmin activities are blocked at DB level — no duplicate data is stored.
However, a duplicate insert raises `psycopg2.IntegrityError` which propagates
uncaught through `save_activity()` to `_persist_garmin_data()` to `run_morning_routine()`.

Contrast with SQLite path (line 1190): `INSERT OR IGNORE INTO training_log` — duplicate
is silently skipped.

**INV-07 status:** BYPASSABLE in the sense that the PostgreSQL adapter errors rather
than silently deduplicates, creating asymmetric behavior between the two backends.
Data integrity (no actual duplicates) is preserved, but exception propagation from a
duplicate sync differs.

**Pattern / scope:**
One location. SQLite path is clean. PostgreSQL-specific gap.

**Architectural question raised:**
Should `save_activity()` on the PostgreSQL adapter use `ON CONFLICT (garmin_activity_id)
DO NOTHING` to match SQLite `OR IGNORE` semantics? Or is exception propagation the
intended behavior for PG (forcing investigation of double-sync root cause)?

**Codex assessment (data only, no decision):**
No duplicate data is stored in either backend. The behavioral asymmetry (silent skip
vs. exception) is the finding. No code change in this audit pass.

**Status:** REVIEWED

---

### [OBS-045] governance_outcomes: athlete_id absent from SQLite schema and INSERT

**Date:** 2026-04-05
**Trigger:** Architect-authorized enforcement integrity audit (bypass path verification)
**Session context:** Audit pass / read-only / enforcement integrity audit
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/core/database.py` — `create_tables()` line 332–357 (SQLite schema), `save_governance_decision()` lines 1684–1692 (SQLite INSERT), lines 2265–2272 (PostgreSQL INSERT)
- `titan/science/outcome_tracker.py` — `record_decision()` line 240, 253

**Observation:**
`GovernanceDecision` dataclass has field `athlete_profile_id` (set to "DEFAULT" in
`record_decision()` at line 240). `self._db.save_governance_decision(asdict(decision))`
is called at line 253.

Both `save_governance_decision()` implementations omit `athlete_profile_id`/`athlete_id`
from the INSERT column list:

- SQLite INSERT (line 1684–1692): 22 columns, no `athlete_id`.
- PostgreSQL INSERT (line 2265–2272): same 22 columns, no `athlete_id`.
- SQLite schema (line 332–357): `governance_outcomes` table has no `athlete_id` column.
- PostgreSQL Alembic D3 migration: `athlete_id TEXT NOT NULL DEFAULT 'default'` was
  added to `governance_outcomes` (TECHNICAL_DEBT.md line 1667), but the INSERT still
  does not specify it — it relies on the DEFAULT value.

**INV-03 status:** BYPASSABLE for SQLite path (column absent entirely). PostgreSQL
path has the column but uses default rather than explicit insert. The `athlete_profile_id`
field in `GovernanceDecision` is silently dropped on every DB write.

**Pattern / scope:**
Confined to `governance_outcomes` table. Other governance tables (`override_signals`)
have `athlete_id NOT NULL` correctly included. This is isolated to outcome tracking.

**Architectural question raised:**
Should `save_governance_decision()` explicitly include `athlete_id`/`athlete_profile_id`
in the INSERT, and should the SQLite schema add the column (matching Alembic D3)?

**Codex assessment (data only, no decision):**
Single-athlete system currently (ADR-0033 Layer 3 deferred Phase 9). The DEFAULT
'default' works for PostgreSQL. SQLite schema parity gap is a pre-Phase-9 risk. No
code change in this audit pass.

**Status:** REVIEWED

---

### [OBS-046] BE-02 (Readiness Gaming): DETECTION-ONLY, no system action

**Date:** 2026-04-05
**Trigger:** Architect-authorized enforcement integrity audit (bypass path verification)
**Session context:** Audit pass / read-only / enforcement integrity audit
**Urgency:** NON-BLOCKING
**Files involved:**
- `tests/test_adversarial_scenarios.py` — `TestBE02ReadinessGaming` lines 177–280
- `titan/science/outcome_tracker.py` — `record_decision()` / `record_outcome()` (detection mechanism)

**Observation:**
BE-02 (Readiness Gaming): five days of readiness=95 + RPE=9 divergence are recorded
by `OutcomeTracker.record_outcome()` but produce no governance lockdown, no block, and
no throttle on the subsequent governance run. Test `test_readiness_outcome_divergence_recorded_without_block`
explicitly verifies `governance_clean=True` on day 6.

**Detection mechanism:** OutcomeTracker stores the divergence data. Analytics surface
divergence via `get_calibration_analytics()`. No threshold-based lockdown is wired to
high divergence patterns.

**System action:** NONE. DETECTION-ONLY.

**Pattern / scope:**
By design (test class docstring: "detection only"). No system action wired.

**Architectural question raised:**
Is DETECTION-ONLY the intended long-term policy for BE-02, or is a future enforcement
mechanism (e.g., automatic flag after N consecutive divergence events) planned?

**Codex assessment (data only, no decision):**
Intentional by current design. OutcomeTracker records data for future threshold
calibration (ADR-0052 deferred Phase 9). No code change in this audit pass.

**Status:** REVIEWED

---

### [OBS-047] BE-03 (Green Means Go): DETECTION-ONLY, no streak-based lockdown

**Date:** 2026-04-05
**Trigger:** Architect-authorized enforcement integrity audit (bypass path verification)
**Session context:** Audit pass / read-only / enforcement integrity audit
**Urgency:** NON-BLOCKING
**Files involved:**
- `tests/test_adversarial_scenarios.py` — `TestBE03GreenMeansGo` lines 286–372
- `titan/science/governance_engine.py` — `apply_constraints()` (no streak tracking logic)

**Observation:**
BE-03 (Green Means Go): four consecutive governance_clean=True days produce no
auto-block or advisory lockdown in `GovernanceEngine.apply_constraints()`. Test
`test_four_consecutive_green_days_no_auto_block` verifies `governance_clean=True`
on day 4. Test `test_green_streak_does_not_add_quality_session_streak_lock` verifies
no lock codes added.

`governance_engine.py` contains no streak counter, no state, no escalation logic
for consecutive GREEN days. Each call to `apply_constraints()` is stateless.

**System action:** NONE. DETECTION-ONLY (advisory logged, no system block).

**Pattern / scope:**
By design (test class docstring: "consecutive GREEN days do not auto-block governance").
GovernanceEngine is intentionally stateless per call.

**Architectural question raised:**
Is DETECTION-ONLY the permanent policy for consecutive GREEN streaks, or is a future
advisory emission (logged WARNING after N days) planned?

**Codex assessment (data only, no decision):**
Intentional by current design. GovernanceEngine is stateless. No code change in this
audit pass.

**Status:** REVIEWED

---

### [DEC-040] Response to OBS-043 — H2/H3 FAIL-OPEN on None input: NEW_DEBT_ENTRY T5-72

**Date:** 2026-04-05
**Architect:** Claude
**OBS verified:** YES — read `titan/science/governance_engine.py` lines 309–322 (H2) and
  341–354 (H3): confirmed `except (TypeError, ValueError): h2_trigger = False` and
  `except (TypeError, ValueError): h3_trigger = False`. Confirmed DailyCoach path is safe
  via `_safe_float(hrv_summary.get('latest_hrv'), 0.0)` (line 553) and
  `_safe_float(hrv_summary.get('baseline'), 50.0)` (line 554) — delta=50.0 ≥ 15.0 fires
  H2 correctly. Confirmed no external direct callers exist in current single-process
  deployment; operator console and API adapters pass context through DailyCoach pipeline.
  FAIL-OPEN risk is latent, not active.

**Architect finding:** The finding is real and correctly categorised under ADR-0051
(Conservative-Fail Principle). DailyCoach path is safe via `_safe_float()` defensive
guard. The exception handler silently swallowing `TypeError` on missing HRV/RHR inputs
violates ADR-0051 policy for safety-critical gate inputs. Fix scope is narrow: replace
`h2_trigger = False` with a DATA_MISSING_CONSERVATIVE WARNING event + EASY ceiling
application (matching H4/H5 conservative behaviour rather than FAIL-OPEN). Same
pattern for H3. No ADR required — ADR-0051 already governs this. Phase 9 timing is
appropriate: no active bypass path exists in current deployment.

| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-72 — `_check_hard_stops()` H2/H3: replace `TypeError`/`ValueError` except→False with DATA_MISSING_CONSERVATIVE WARNING emit + EASY ceiling application. Files: `governance_engine.py` lines 321–322, 353–354. ADR-0051 extension. Phase 9. |

**OBS-043 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-041] Response to OBS-044 — PostgreSQL save_activity() missing ON CONFLICT: NEW_DEBT_ENTRY T5-73

**Date:** 2026-04-05
**Architect:** Claude
**OBS verified:** YES — read `titan/core/database.py` line 2201: confirmed plain `INSERT INTO
  training_log` without `ON CONFLICT` clause. Read line 2139: confirmed `UNIQUE INDEX` on
  `garmin_activity_id` (partial, WHERE NOT NULL). Read SQLite path line 1190: confirmed
  `INSERT OR IGNORE INTO training_log`. PostgreSQL path will raise `psycopg2.IntegrityError`
  on duplicate garmin_activity_id; SQLite path silently skips. Data integrity is preserved
  in both backends — no duplicate rows are stored. Behavioral asymmetry (exception vs. silent
  skip) is the actual gap. ADR-0044 confirmed: PostgreSQL migration = Phase 9 lane; D2 stage.

**Architect finding:** No data integrity failure; UNIQUE constraint fires in both paths.
The gap is exception propagation asymmetry: SQLite callers are immune to duplicate sync
errors; PostgreSQL callers are not. The fix is a single-line `ON CONFLICT
(garmin_activity_id) DO NOTHING` addition that makes PostgreSQL semantics match SQLite.
No architectural ambiguity; no ADR required beyond ADR-0044. Scoped to Phase 9
PostgreSQL migration lane.

| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-73 — `PostgreSQLDatabaseManager.save_activity()`: add `ON CONFLICT (garmin_activity_id) DO NOTHING` to match SQLite `OR IGNORE` semantics. File: `database.py` line ~2201. Phase 9 (PostgreSQL migration lane). |

**OBS-044 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-042] Response to OBS-045 — governance_outcomes athlete_id absent: NEW_DEBT_ENTRY T5-74

**Date:** 2026-04-05
**Architect:** Claude
**OBS verified:** YES — read `titan/core/database.py` lines 332–357 (SQLite schema): confirmed
  `governance_outcomes` table has no `athlete_id` column. Read lines 1684–1692 (SQLite INSERT):
  confirmed 22 columns, no `athlete_id`. Read lines 2265–2272 (PostgreSQL INSERT): same 22
  columns, no `athlete_id`; relies on `DEFAULT 'default'` from Alembic D3 migration. Read
  `titan/science/outcome_tracker.py` line 240: `GovernanceDecision.athlete_profile_id = "DEFAULT"`
  set but silently dropped at DB write. ADR-0033 Layer 3 (multi-athlete) confirmed as Phase 9.
  Current single-athlete system: no functional impact.

**Architect finding:** The `athlete_profile_id` field in `GovernanceDecision` is set correctly
but discarded at the DB boundary in both backends. PostgreSQL path works via DEFAULT; SQLite
schema lacks the column entirely — a schema parity gap that will require a migration when
ADR-0033 Layer 3 activates. No active functional failure in single-athlete deployment. Fix
must land before Phase 9 multi-athlete work begins; it is a prerequisite for ADR-0033 Layer 3.

| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-74 — `governance_outcomes`: add `athlete_id` column to SQLite `create_tables()` schema; include explicit `athlete_id` in both SQLite and PostgreSQL `save_governance_decision()` INSERTs. Phase 9 (ADR-0033 Layer 3 prerequisite). |

**OBS-045 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-043] Response to OBS-046 — BE-02 DETECTION-ONLY: NO_ACTION

**Date:** 2026-04-05
**Architect:** Claude
**OBS verified:** YES — read `tests/test_adversarial_scenarios.py` lines 177–280: confirmed
  `TestBE02ReadinessGaming` class docstring ("detection only") and test
  `test_readiness_outcome_divergence_recorded_without_block` verifies `governance_clean=True`
  on day 6. Read `titan/science/outcome_tracker.py` `record_outcome()`: confirmed divergence
  data is stored without any lockdown trigger. Cross-referenced ADR-0052: ThresholdAdapter
  feedback loop and enforcement wiring are explicitly Phase 9 scope (Stage 4).

**Architect finding:** DETECTION-ONLY is the correct and intended policy for BE-02 in the
current phase. `OutcomeTracker` accumulates divergence data to populate the feedback loop
that ADR-0052 Stage 4 will act upon. Wiring enforcement before the ThresholdAdapter exists
would couple the governance engine to incomplete ML calibration infrastructure. No debt entry
warranted — this is an architectural boundary decision, not a gap.

| Action | Detail |
|---|---|
| NO_ACTION | DETECTION-ONLY is by design per ADR-0052. Enforcement wiring (lockdown / flag after N consecutive divergence events) is Phase 9 Stage 4 scope. No new debt entry required; ADR-0052 already tracks the obligation. |

**OBS-046 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-044] Response to OBS-047 — BE-03 DETECTION-ONLY stateless governance: NO_ACTION

**Date:** 2026-04-05
**Architect:** Claude
**OBS verified:** YES — read `titan/science/governance_engine.py` `apply_constraints()`:
  confirmed no streak counter, no session-level state, no escalation logic for consecutive
  GREEN days. Read `tests/test_adversarial_scenarios.py` lines 286–372: confirmed
  `test_four_consecutive_green_days_no_auto_block` verifies `governance_clean=True` on day 4
  and `test_green_streak_does_not_add_quality_session_streak_lock` verifies empty lock codes.
  GovernanceEngine is stateless by explicit architectural decision.

**Architect finding:** Stateless governance is the correct design for the current phase.
Each call to `apply_constraints()` is independent; no cross-session state is accumulated
inside the engine. Advisory WARNING emission after N consecutive GREEN days would require
persistent streak state — a complexity cost that is not yet justified by OutcomeTracker
data. If future data from ADR-0052 calibration shows consecutive-GREEN streaks correlate
with readiness overestimation, this becomes a Phase 9 feature candidate. No debt entry
warranted now.

| Action | Detail |
|---|---|
| NO_ACTION | Stateless governance is correct design for current phase. Streak-based advisory emission = Phase 9 feature candidate, contingent on OutcomeTracker data support. No new debt entry required. |

**OBS-047 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-045] Response to OBS-048 — Structural bypass-path + central-gate test gap: NEW_DEBT_ENTRY T5-75

**Date:** 2026-04-11
**Architect:** Claude
**OBS verified:** YES — confirmed via OBS-048 structural audit: `coaching_pipeline.py` and
  `GovernanceEngine.apply_constraints()` have no AST-based or import-graph test covering
  (a) single call-site invariant for `_decision_pipeline()` and (b) full gate-method
  reachability from `apply_constraints()` body. Behavior is correct today; regression
  protection is absent. Pattern confirmed as a structural test gap, not a runtime defect.

**Architect finding:** An AST-based structural invariant test suite is warranted before
Phase 9 multi-athlete entry. A refactor that silently bypasses `_decision_pipeline()` or
drops a `_gate_*` method from `apply_constraints()` would not be caught by the current
test suite. Two distinct invariants are being asserted: (1) single call-site for the
decision pipeline, and (2) all gate methods are reachable. These are a single cohesive
test item scoped to `tests/test_architectural_invariants.py` (new file).

| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-75 — AST structural invariant tests: `_decision_pipeline()` has exactly one call site in production code; every `_gate_*` method in `GovernanceEngine` is called from `apply_constraints()`. File: `tests/test_architectural_invariants.py`. Phase 9 entry gate (structural). |

**OBS-048 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-046] Response to OBS-049 — Interleaved decision+write + crash-midway + determinism gap: NEW_DEBT_ENTRY T5-76 + T5-77

**Date:** 2026-04-11
**Architect:** Claude
**OBS verified:** YES — confirmed via OBS-049 audit: no test covers concurrent
  `coaching_pipeline()` runs with shared DB, no test covers SIGTERM between steps 8
  and 9, and no test covers deterministic output under seeded conditions. Three scenario
  classes are ungapped. ADR-0046 confirmed: Phase 9 multi-athlete architecture elevates
  concurrent-pipeline execution from theoretical to operational risk.

**Architect finding:** The three scenarios split into two distinct debt items:
  (a) Concurrent pipeline execution (T5-76): mandatory Phase 9 ADR-0046 entry gate;
  a test must demonstrate that two concurrent `coaching_pipeline()` calls sharing
  `DatabaseManager` do not corrupt governance state or produce interleaved writes.
  (b) SIGTERM mid-pipeline (T5-77): independent data integrity concern — partial
  `governance_outcomes` trace must not leave the DB in an inconsistent state;
  this invariant is independent of multi-athlete scope.
  (c) Output determinism (OBS-049 scenario 3): deferred — not a current data integrity
  risk; regression-diff workflows are Phase 10 scope. No debt entry for (c).

| Action | Detail |
|---|---|
| NEW_DEBT_ENTRY | T5-76 — Concurrent `coaching_pipeline()` test: two parallel calls sharing `DatabaseManager` must not corrupt governance state; ADR-0046 Phase 9 entry gate criterion. |
| NEW_DEBT_ENTRY | T5-77 — SIGTERM mid-pipeline invariant: process termination between pipeline steps must not leave an orphaned (unpaired) `governance_outcomes` trace; data integrity test required. |

**OBS-049 marked:** REVIEWED
**Status:** PROCESSED

---

### [DEC-047] Response to OBS-050 — tests/titan/api/* importorskip hygiene: NO_ACTION

**Date:** 2026-04-11
**Architect:** Claude
**OBS verified:** YES — read `requirements.txt`: confirmed `fastapi` is listed as a pinned,
  non-optional production dependency. A collection crash in the absence of `fastapi` is an
  environment bootstrap failure, not a test hygiene gap. The `importorskip` guard is
  appropriate only for truly optional dependencies; adding it here would mask an environment
  misconfiguration rather than handle a legitimate optional-dep scenario.

**Architect finding:** `fastapi` is not optional. If it is absent from the environment,
the correct signal is a PURPLE (import/collection error) directing the engineer to fix
the environment via `pip install -r requirements.txt`. Wrapping a mandatory dependency in
`importorskip` would suppress that signal and produce a false green. No hygiene change
required.

| Action | Detail |
|---|---|
| NO_ACTION | `fastapi` is a pinned non-optional dependency in `requirements.txt`. A collection crash on absent `fastapi` is an environment error, not a test hygiene gap. An `importorskip` guard would suppress a legitimate PURPLE signal. No change required. |

**OBS-050 marked:** REVIEWED
**Status:** PROCESSED

---

### [OBS-048] Structural bypass-path + central-gate test gap

**Date:** 2026-04-11
**Trigger:** Lane B structural audit — test-gap documentation
**Session context:** Records-only audit pass / no code changes
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/orchestration/coaching_pipeline.py`
- `titan/science/governance_engine.py`
- `tests/test_architectural_invariants.py`

**Observation:**
Κανένα test δεν πιστοποιεί (a) ότι `_decision_pipeline()` έχει ακριβώς 1 call site στο
production code, (b) ότι κάθε `_gate_*` method στο `GovernanceEngine` καλείται από το
`apply_constraints()` body. Behavior είναι σωστό σήμερα. Regression protection απούσα.

**Pattern / scope:**
Structural invariants (single call-site, full gate coverage) are currently verified only
by manual inspection. No AST-based or import-graph test enforces these properties. A
refactor or copy-paste error that bypasses `_decision_pipeline()` or skips a gate method
would not be caught by the current test suite before reaching CI.

**Architectural question raised:**
Πρέπει να προστεθούν AST-based structural invariant tests πριν Phase 9 multi-athlete
entry; If yes, should they live in `tests/test_architectural_invariants.py` (new file) or
in an existing phase-hygiene sweep?

**Codex assessment (data only, no decision):**
No code change made. Observation is data-only. Decision deferred to architect review.

**Status:** REVIEWED

---

### [OBS-049] Interleaved decision+write + crash-midway + determinism gap

**Date:** 2026-04-11
**Trigger:** Lane B structural audit — test-gap documentation
**Session context:** Records-only audit pass / no code changes
**Urgency:** NON-BLOCKING
**Files involved:**
- `titan/orchestration/coaching_pipeline.py`
- `titan/orchestration/daily_coach.py`
- `tests/test_concurrency_consistency.py`

**Observation:**
Κανένα test δεν καλύπτει: (a) δύο παράλληλα `coaching_pipeline()` runs με shared DB,
(b) SIGTERM μεταξύ step 8 και step 9 χωρίς governance trace, (c) deterministic plan
output για seeded input υπό race conditions.

**Pattern / scope:**
Three distinct scenario classes are ungapped: (a) concurrent multi-athlete pipeline
execution sharing the SQLite DatabaseManager lock, (b) mid-pipeline process termination
leaving a partial governance trace in `governance_outcomes`, (c) output determinism under
seeded-random or fixed-clock conditions (required for regression-diff workflows).
Phase 9 multi-athlete architecture (ADR-0046) elevates scenarios (a) and (c) from
theoretical to operational risk.

**Architectural question raised:**
Ποια από τα 3 scenarios είναι mandatory για Phase 9 multi-athlete entry gate? Specifically:
(1) Is concurrent-pipeline coverage a P9 entry gate criterion per ADR-0046?
(2) Is partial-trace SIGTERM handling in scope for T5-74 or a separate debt entry?
(3) Is output determinism required for the regression suite or deferred to a later phase?

**Codex assessment (data only, no decision):**
No code change made. Observation is data-only. Decision deferred to architect review.

**Status:** REVIEWED

---

### [OBS-050] tests/titan/api/* importorskip hygiene

**Date:** 2026-04-11
**Trigger:** Lane B structural audit — test-gap documentation
**Session context:** Records-only audit pass / no code changes
**Urgency:** NON-BLOCKING
**Files involved:**
- `tests/titan/api/test_rate_limiter_ceiling.py`
- `tests/titan/api/test_audit.py`
- `tests/titan/api/test_auth.py`
- `tests/titan/api/test_auth_store_sqlite.py`

**Observation:**
4 test files κάνουν top-level import από `titan.api.main` χωρίς
`pytest.importorskip("fastapi")`. Σε CI environment χωρίς fastapi (π.χ. lock-file drift),
collection crashes αντί για graceful skip.

**Pattern / scope:**
If `fastapi` is absent from the environment (e.g., requirements drift, alternative CI
matrix row, or developer setup without optional deps), pytest collection fails at import
time for all four files rather than emitting a skip. This causes a PURPLE signal (import /
collection error) that masks actual test failures in unrelated modules.

**Architectural question raised:**
Πρέπει να προστεθεί `importorskip` σε αυτά τα 4 files; If yes, should the guard be
`pytest.importorskip("fastapi")` at module level, or a per-test `skipif` decorator? Is
fastapi listed as a non-optional dependency in `requirements.txt` (in which case a
collection crash is an environment error, not a test hygiene gap)?

**Codex assessment (data only, no decision):**
No code change made. Observation is data-only. Decision deferred to architect review.

**Status:** REVIEWED
