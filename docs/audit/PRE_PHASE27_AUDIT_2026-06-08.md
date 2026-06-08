**This audit is read-only; no files were modified.**

---

# TITAN OS — PRE-PHASE-27 GOVERNANCE & SAFETY AUDIT

**Auditor mode:** TITAN AUDITOR · **Contract:** v7.8 · **Date:** 2026-06-08
**Scope:** Phase 26 deliverable quality + Phase 27 architectural prerequisites (read-only)
**Schema:** v23 · **Tests:** 3025 passing / 6 skipped · **Safety floor (H1–H5):** intact (verified — see A2c)

---

## AREA 1 — Phase 26 Implementation Quality

### FINDING A1-01 — Scheduler path has no once-per-day / 07:00 gate
- **SEVERITY:** HIGH
- **LOCATION:** `titan/worker/__init__.py:180-206` (`_make_athlete_callback`), `:173-175` (comment); `titan/orchestration/daily_coach.py:554` (`run_morning_routine` — no time guard)
- **OBSERVATION:** The callback calls `coach.run_morning_routine()` **unconditionally on every scheduler tick** (`interval_seconds=60.0`). The inline comment asserts *"coaching fires once per athlete per day at 07:00 UTC (controlled by the callback, not the scheduler interval)"* — but neither the callback nor `run_morning_routine()` contains any time gate or once-per-day dedup. The only guard in the file is `run_morning_routine_async`'s non-blocking mutex (concurrency, not daily cadence), and the callback uses the **synchronous** entrypoint. The single-athlete `run_forever` loop *does* gate correctly via `_seconds_until_next_run(7, 0)` (`:145`); the scheduler path drops that gate entirely.
- **IMPACT (Phase 27):** Under `TITAN_MULTI_ATHLETE=1`, each athlete's full morning routine (Garmin `sync_all`, Telegram briefing, `governance_outcomes` write, `daily_metrics` write) executes every 60s. Garmin rate-limit/ban exposure (ADR-0050), Telegram spam, and ~1,440 duplicate governance decisions/day/athlete — which directly poisons the very corpus Phase 27 calibration consumes.
- **GOVERNANCE TRACE:** ADR-0050 (Garmin Mitigation); ADR-0046 (Multi-athlete model); FMEA Phase 26 F26-01 (does not capture this cadence defect).
- **RECOMMENDATION:** Port the `_seconds_until_next_run`/daily-dedup gate into the scheduler callback (or into `run_morning_routine`) before any multi-athlete activation.

### FINDING A1-02 — Scheduler registers only `owner`; docstring overstates behavior
- **SEVERITY:** LOW
- **LOCATION:** `titan/worker/__init__.py:208` vs docstring `:155-157`; unused API `titan/core/database.py:1697` (`_get_all_athlete_ids`)
- **OBSERVATION:** Docstring claims it registers *"the owner athlete and any additional athletes from the athletes table"*, but only `scheduler.register_athlete("owner", …)` is wired. `_get_all_athlete_ids()` exists but is never called.
- **IMPACT (Phase 27):** Multi-athlete enumeration is greenfield (acceptable), but the docstring misrepresents current capability.
- **GOVERNANCE TRACE:** ADR-0046; AGENTS.md (doc-accuracy).
- **RECOMMENDATION:** Either wire `_get_all_athlete_ids()` (after A3-02/A1-03 are fixed) or correct the docstring.

### FINDING A1-03 — EngineRegistry.from_db hydration is discarded and re-done as `owner` by DailyCoach
- **SEVERITY:** HIGH
- **LOCATION:** `titan/orchestration/engine_registry.py:54-62` (from_db: TSB `days=90` + HRV `days=30`, **athlete-scoped**) vs `titan/orchestration/daily_coach.py:390` (`__init__` always re-hydrates) → `:1810` HRV `get_hrv_history(days=28)`, `:1860` TSB `get_training_load_history(days=CTL_DECAY_DAYS=42)` — **both without `athlete_id` → defaults `'owner'`**; plus `:1767` `_feed_load_engines` re-hydrates TSB a third time (42d, owner) during `run_morning_routine`.
- **OBSERVATION (answers Area 1b directly):**
  - **TSB window:** from_db=90 vs DailyCoach=42 → **NOT equivalent.**
  - **HRV window:** from_db=30 vs DailyCoach=28 → **NOT equivalent.**
  - **Ordering:** both iterate `reversed(rows)` (oldest-first) → equivalent. ✓
  - **Double-hydration corruption:** `_hydrate_engines_from_db_locked` calls `self.hrv.hrv_log.clear()` and `self.tsb.daily_loads.clear()` before re-adding → **no double-count** (state is safe). However the from_db hydration is **entirely discarded**; effective state is the DailyCoach (`owner`, 42d/28d) hydration.
  - **`DailyCoach` has no `athlete_id` at all** — its hydration is hard-coded to `'owner'` regardless of the registry handed in.
- **IMPACT (Phase 27):** The athlete-scoping in `EngineRegistry.from_db(athlete_id=X)` is nullified the instant a `DailyCoach` is constructed around it. For any non-`owner` athlete this hydrates **owner's** TSB/HRV (and weight/HRR/CS, which were never athlete-scoped). This is the cross-athlete contamination F26-02 claims is mitigated.
- **GOVERNANCE TRACE:** ADR-0058 Phase B (EngineRegistry hydration incomplete); ADR-0033 (Athlete Isolation); FMEA F26-02 (see A4-02).
- **RECOMMENDATION:** Make `DailyCoach` athlete-aware (accept `athlete_id`, thread it through `_hydrate_engines_from_db` + `_feed_load_engines`), OR have `__init__` trust a pre-hydrated registry and skip self-hydration when `engines=` is supplied. Reconcile the 90/42 and 30/28 windows.

### A1-c — Lazy constants → **STATUS: CLEAN**
`_get_data_dir()`/`_get_garth_token_path()` (`garmin_sync.py:50-61`) and `_get_lock_file()` (`worker/__init__.py:26-32`) all re-invoke `get_settings()` per call; no module-level capture. `get_settings()` is `lru_cache`d but re-readable/clearable (P15-ARCH5). Correctly lazy.

### A1-d — B2c TypeError clarity → **STATUS: CLEAN**
`daily_coach.py:365-369` message names the `engines=` requirement, the composition-root fix (`EngineRegistry.from_db(db=db)`), and explicitly states *"Test factories using DailyCoach.__new__ bypass __init__ and are unaffected."* Clear. The `db=` TypeError (`:348-353`) is equally clear.

---

## AREA 2 — Phase 27 Architectural Prerequisites

### A2-a — OutcomeTracker per-athlete scoping → mostly sound, one latent defect
`calibration_summary`, `get_decisions`, `get_lock_outcome_correlation`, `get_lock_rate_by_phase`, `check_calibration_diversity`, `get_calibration_analytics` are all filtered on `athlete_profile_id` (`outcome_tracker.py:389,408,430,487,567,617`). Per-athlete counts are suitable CohortProfile inputs.

### FINDING A2-01 — `run_calibration_cycle` reads FP/FN keys that `get_calibration_summary` never emits (no-op adaptation) + tracker hydrates only `owner`
- **SEVERITY:** MEDIUM
- **LOCATION:** `outcome_tracker.py:778-779` (`summary.get("false_positive_rate", 0.0)` / `"false_negative_rate"`) vs `get_calibration_summary` return dict (`:526-551`, keys absent); hydration `:204-212` calls `self._db.get_governance_decisions()` with **no `athlete_id`** → loads only `'owner'`.
- **OBSERVATION:** `false_positive_rate`/`false_negative_rate` are never present in the summary → both default `0.0` → `direction` is never set → `adaptations_attempted == applied == 0` **always**. The per-athlete ADR-0052 calibration loop is effectively inert. Separately, the DB-backed tracker only ever loads `owner` decisions, so `_get_moderate_promotion_candidates`' `profile_replication_count` is structurally ≤1.
- **IMPACT (Phase 27):** Phase 27 builds cohort promotion on top of per-athlete calibration that currently produces zero adaptations and cannot see >1 athlete from the DB. The "ADR-0052 offset calibration producing per-athlete threshold deltas in production" portion of the Phase 27 entry gate (TECHNICAL_DEBT.md:1636) is not actually exercised.
- **GOVERNANCE TRACE:** ADR-0052; ADR-0033 L3-B; ROADMAP Phase 27 §1-2.
- **RECOMMENDATION:** Emit FP/FN rates from `get_calibration_summary` (or change the cycle to use the keys that exist), and add cohort/per-athlete hydration to OutcomeTracker.

### A2-b — EvidenceRegistry promotion path
- **Promotion mechanism:** *candidate surfacing only.* `_get_heuristic_promotion_candidates` (HEURISTIC→MODERATE) requires `n_with≥5, n_without≥5, |completion_delta_pp|≥8`; `_get_moderate_promotion_candidates` (MODERATE→STRONG) requires `n≥8, |delta|≥10, ≥2 phases, ≥2 profiles`. Actual promotion is a **manual ADR + EvidenceRegistry edit** (fields `promoted_from_level`/`promotion_evidence_count`/`promotion_date` exist; no automated writer). This is the correct human-in-the-loop posture.
- **HEURISTIC candidates for cohort promotion:** wired set is `{SUBJECTIVE_FATIGUE_2OF4, HARD_STOP_TSB_FLOOR, VO2_READINESS_MIN}` (`_LOCK_TO_HEURISTIC_PARAMETERS`); registry flags `VO2_READINESS_MIN` as *"the highest-value calibration candidate."* `get_policy_parameters()` enumerates the full HEURISTIC set (the bulk of the registry).
- **NOTE A2-02 (INFO):** Phase 27's "≥3 athletes confirm same delta" rule is greenfield; the nearest analog (`profile_replication_count≥2`) is unusable today because the tracker is `owner`-only (A2-01).
- **NOTE A2-03 (LOW):** `_LOCK_TO_MODERATE_PARAMETERS` includes `HARD_STOP_HRV_DELTA` (an H1 component). Promoting its *evidence level* is legitimate (evidence ≠ threshold value); `ThresholdAdapter` still refuses to *adapt* it (A2-c). No defect; flagged for reviewer clarity.

### A2-c — ThresholdAdapter → **STATUS: CLEAN (safety floor verified)**
`propose_adaptation` (`threshold_adapter.py:81-128`) reads/writes `athlete_threshold_offsets` scoped by `athlete_id` (`UNIQUE(athlete_id, threshold_key)`), excludes `HARD_STOP_THRESHOLD_KEYS` (H1–H5), enforces ±5% damping / ±20% ceiling / non-finite guard. The circuit breaker (`get_false_negative_rate(athlete_id, window_days)`) is computed **per athlete** and **not pooled** — correct for multi-athlete aggregation; cohort logic must preserve this per-athlete breaker. Cold-start bypass (ADR-0033 L3-C) intact. **H1–H5 cannot be widened by any calibration path** — the system safety floor holds.

### A2-d — Greenfield confirmation → **STATUS: CLEAN**
Grep for `CohortProfile|cohort_profile|population_heuristic` returns only docstrings, comments, and log strings — **no class/function/schema exists.** Phase 27 is genuinely greenfield on this surface.

### FINDING A2-04 — Rollback gate has no injury-event data source; completion_rate derivable only
- **SEVERITY:** MEDIUM
- **LOCATION:** `titan/core/schema.py:171-198` (`governance_outcomes` — no `completion_rate`, no injury column); `:80-101` (`daily_metrics` — no injury_flag column)
- **OBSERVATION:** The Phase 27 rollback gate ("revert if completion_rate degrades **or injury events increase** within 30 days") has partial support: **completion_rate** is derivable from `outcome_completed` over a 30-day athlete-scoped window (the pattern already exists in `get_false_negative_rate`, `database.py:1534`), and `athlete_threshold_offsets.updated_at` can anchor the window. **Injury events have no persistence anywhere** — `governance_outcomes` has no injury column and `daily_metrics` has no `injury_flag` (only `soreness`/`fatigue_level`/`mood`); H1 `injury_flag` is a transient runtime input.
- **IMPACT (Phase 27):** The injury-trigger half of the rollback gate cannot be implemented against the current schema.
- **GOVERNANCE TRACE:** ROADMAP Phase 27 (rollback gate); ADR-0052; ADR-0026/0051 (conservative-fail).
- **RECOMMENDATION:** Add an injury-event column/table (SCHEMA_VERSION bump + descriptor + migration + equivalence test) as a Phase 27 prerequisite, or scope the rollback gate to completion_rate only in v1 with an explicit ADR.

---

## AREA 3 — Multi-Athlete Isolation Readiness

### FINDING A3-01 — `update_governance_outcome` is not athlete-scoped
- **SEVERITY:** MEDIUM-HIGH
- **LOCATION:** `titan/core/database.py:2689-2736`
- **OBSERVATION:** Update targets `WHERE id = (SELECT id FROM governance_outcomes WHERE date = ? ORDER BY id DESC LIMIT 1)` — **no `athlete_id` filter.** `OutcomeTracker.record_outcome` is in-memory athlete-scoped but the DB write is not. With ≥2 athletes holding a decision on the same date, an outcome can be written to the wrong athlete's row (whichever has the latest `id`).
- **GOVERNANCE TRACE:** ADR-0033 (L3-D resolved *read* path; write path unguarded); AGENTS.md §16.10 A40-1.
- **RECOMMENDATION:** Add `athlete_id` parameter + `WHERE athlete_id = ? AND date = ?` scoping.

### FINDING A3-02 — `daily_metrics` is structurally single-athlete (date-unique + unscoped write)
- **SEVERITY:** HIGH
- **LOCATION:** `titan/core/schema.py:100` (`UniqueConstraint("date", name="uq_daily_metrics_date")` — date **alone**); `database.py:1976-1989` (INSERT omits `athlete_id`, relies on `server_default 'owner'`, `ON CONFLICT(date)`)
- **OBSERVATION:** Although `daily_metrics` carries an `athlete_id` column (v14) and **reads** are scoped (`get_hrv_history`/`get_weight_history`/`get_daily_metric`/`get_baseline_rhr`), the unique key is on `date` only and the writer never sets `athlete_id`. **Two athletes cannot hold a row for the same date** — a second athlete's morning metrics UPSERT-collide onto the `owner` row.
- **IMPACT (Phase 27):** Hard structural blocker — the cohort cannot store >1 athlete's daily wellness data. This is the single largest Phase 27 isolation blocker.
- **GOVERNANCE TRACE:** ADR-0033; ADR-0040 (single-athlete shortcut); AGENTS.md §16.10.
- **RECOMMENDATION:** Migrate unique key to `(athlete_id, date)`, add `athlete_id` to the writer signature + INSERT + `ON CONFLICT(athlete_id, date)` (SCHEMA_VERSION bump + descriptor + equivalence test).

### FINDING A3-03 — `get_hrr_history` read path not athlete-scoped
- **SEVERITY:** MEDIUM
- **LOCATION:** `titan/core/database.py:2452-2469` (`def get_hrr_history(self, days=28)` — no `athlete_id`; query has no `WHERE athlete_id`)
- **OBSERVATION:** Unlike the other `daily_metrics` readers, HRR history pulls across all athletes. Consumed by `_hydrate_engines_from_db` → AutonomicFusionEngine.
- **GOVERNANCE TRACE:** ADR-0033 L3-D (read-path isolation — incomplete here).
- **RECOMMENDATION:** Add `athlete_id` param + filter (mirror `get_hrv_history`).

### FINDING A3-04 — `personal_bests` has no `athlete_id` (descriptor/comment drift)
- **SEVERITY:** MEDIUM
- **LOCATION:** `titan/core/schema.py:155-164` (no `athlete_id` column, despite comment `:152` *"Covers: … v20 (athlete_id)"*); `database.py:2373-2399` (`save_personal_best`) / `:2401-2417` (`get_pr`) — no `athlete_id`. Same comment/definition drift on `gear_usage` (`:134,137-148`).
- **OBSERVATION:** `personal_bests` is entirely single-athlete; its provenance comment claims a v20 `athlete_id` addition that is absent from the canonical descriptor.
- **IMPACT (Phase 27):** Per-athlete PBs (feed CS/durability) collide across athletes; also a descriptor-accuracy defect under the TD-08 "single authoritative source" contract.
- **GOVERNANCE TRACE:** TD-08 (schema descriptor authority); ADR-0033; ADR-0019.
- **RECOMMENDATION:** Either add `athlete_id` to `personal_bests`/`gear_usage` or correct the descriptor comments to match reality; reconcile with `test_schema_equivalence.py`.

### FINDING A3-05 — Cross-athlete contamination in the scheduler callback (consequence of A1-03)
- **SEVERITY:** HIGH (latent today; active on athlete #2)
- **LOCATION:** `titan/worker/__init__.py:186` (correct `from_db(db, athlete_id=athlete_id)`) → nullified by `daily_coach.py:390/1810/1860/1767` (`owner`-scoped re-hydration)
- **OBSERVATION:** Each callback correctly builds an athlete-scoped registry, then `DailyCoach` overwrites it with `owner` data (A1-03). Currently benign because only `owner` is registered (A1-02); becomes live contamination the moment Phase 27 onboards a second athlete. The `OutcomeTracker(db=self.db)` created in `__init__` (`:374`) likewise hydrates only `owner`.
- **GOVERNANCE TRACE:** ADR-0033; FMEA F26-02 (false mitigation, A4-02).
- **RECOMMENDATION:** Fix A1-03 first; gate multi-athlete registration behind it.

### A3-d — Shared DatabaseManager serialization → **STATUS: CLEAN (premise corrected)**
The SQLite `DatabaseManager` serializes all writes under `threading.RLock` (`database.py:216`), WAL mode, `check_same_thread=False`. **Correction to the audit premise:** `CoachingScheduler` is **not** a thread pool — `_run_loop` iterates all callbacks **sequentially in a single daemon thread** (`coaching_scheduler.py:35-39`). There is therefore no concurrent per-athlete write contention from the scheduler; the RLock additionally guards the other writers (Telegram poller, Garmin sync, `run_morning_routine_async`). Serialization is sound. **NOTE A3-06 (INFO):** the single-thread design means N athletes' routines run sequentially per tick — latency scales with N and compounds A1-01.

### A3-b — Corpus gate `outcome_completed IS NOT NULL` → correct
`tests/test_phase9_corpus_gate.py:33-39` correctly counts paired (decision+outcome) records per athlete (`WHERE outcome_completed IS NOT NULL GROUP BY athlete_id HAVING COUNT(*) >= 90`). **NOTE (LOW):** it counts *any* non-null outcome (including `outcome_completed=0`) and does **not** apply the `outcome_independence_ok`/`override_outcome_exclusion` reuse filters that `get_calibration_summary` uses — so the corpus count is more permissive than the *reusable*-outcome count. Acceptable for an entry-gate headcount; flag if Phase 27 wants reuse-grade corpus.

---

## AREA 4 — Corpus Gate & Phase 9 Entry

### A4-a — Advisory only; not CI-enforced → confirmed
Test passes unless `TITAN_PHASE9_CORPUS_GATE=1` in env (`test_phase9_corpus_gate.py:54-60`). Grep shows the flag appears **only** in the test and TECHNICAL_DEBT.md — **no CI job sets it.** Blocking CI = `ruff` + `pytest` (CLAUDE.md), which runs the test in advisory mode. As designed.

### A4-b — Corpus state (best estimate)
Not auditable without live data (ephemeral container; the test builds a fresh temp DB). Schema supports the query and `governance_outcomes` is athlete-scoped on write. Given single-athlete (`owner`) operation and the isolation blockers above, the realistic state is **0–1 of 3 qualifying athletes → corpus NOT met.** Onboarding ≥3 athletes is itself blocked by A3-02/A3-04/A1-03.

### FINDING A4-01 — `TITAN_PHASE9_CORPUS_GATE` not in `TitanSettings`
- **SEVERITY:** LOW
- **LOCATION:** `titan/config/settings.py:9-26` (absent); read via `os.getenv` in the test only
- **OBSERVATION:** An enforcement flag governing a phase gate lives outside the P15-ARCH5 centralized settings, untyped and undocumented in `TitanSettings`.
- **GOVERNANCE TRACE:** P15-ARCH5 (centralized settings); ADR-0059.
- **RECOMMENDATION:** Add to `TitanSettings` when the gate transitions to enforcing in Phase 27.

### FINDING A4-02 — FMEA F26-02 mitigation is false assurance; F26-01 misses the cadence defect
- **SEVERITY:** HIGH (governance integrity)
- **LOCATION:** `TECHNICAL_DEBT.md:1675` (F26-02), `:1674` (F26-01); cited test `tests/test_athlete_isolation_invariant.py`
- **OBSERVATION:** F26-02 claims mitigation *"athlete_id threaded into every DB query; per-athlete freshly-hydrated registry per pipeline call; athlete-isolation invariant tests ✅."* In reality (A1-03/A3-05) `DailyCoach._hydrate_engines_from_db` + `_feed_load_engines` re-hydrate from `'owner'` ignoring `athlete_id`, and the cited `test_athlete_isolation_invariant.py` is a **static AST/SQL-string lint** that (a) explicitly **exempts `database.py`** (`:75`) — where the unscoped writes A3-01/A3-02/A3-04 live — and (b) never exercises the hydration path behaviorally. F26-01 correctly flags silent thread death but **omits** the every-60s/no-07:00 cadence defect (A1-01). No FMEA entry exists for A3-02 (date-unique blocker), A3-04, A3-01, or A2-01.
- **GOVERNANCE TRACE:** ADR-0049 (Opus QA); ADR-0047 fitness functions; AGENTS.md (FMEA accuracy).
- **RECOMMENDATION:** Correct F26-02's mitigation claim, add F26 entries for A3-01/02/04 and A2-01, and add a **behavioral** two-athlete isolation test (assert athlete B's hydrated TSB/HRV ≠ athlete A's) — the current static lint cannot catch the live bug.

---

## VERDICT

### VERDICT: NO-GO — Phase 27 multi-athlete scope is blocked

Phase 27's own entry gate (TECHNICAL_DEBT.md:1636) requires *"≥3 athlete profiles active with per-athlete-isolated EngineRegistry; ADR-0052 offset calibration producing per-athlete threshold deltas in production."* Neither half holds: per-athlete isolation is broken **below** the EngineRegistry layer, and offset calibration is currently a no-op.

**Explicit blockers (must clear before onboarding athlete #2 / activating `TITAN_MULTI_ATHLETE`):**

1. **A3-02 (HIGH)** — `daily_metrics` unique-on-`date` + unscoped write makes the cohort store structurally single-athlete.
2. **A1-03 / A3-05 (HIGH)** — `DailyCoach` re-hydrates engines as `owner`, nullifying `EngineRegistry.from_db(athlete_id)` → cross-athlete contamination of cohort calibration data.
3. **A4-02 (HIGH)** — FMEA F26-02 mitigation is false; the cited isolation test cannot detect the contamination. Governance record must be corrected and a behavioral test added.
4. **A1-01 (HIGH)** — scheduler runs full morning routines every 60s (no 07:00/daily gate) → Garmin ban risk + corpus poisoning.
5. **A2-01 (MEDIUM)** — per-athlete calibration cycle is inert (FP/FN keys never emitted; tracker `owner`-only); Phase 27 cohort signal would build on a non-functioning base.

**Secondary prerequisites:** A3-01 (unscoped `update_governance_outcome`), A3-03 (`get_hrr_history` unscoped), A3-04 (`personal_bests` no `athlete_id` + descriptor drift), A2-04 (rollback gate has no injury-event data source), A4-01 (gate flag outside `TitanSettings`).

**What IS safe / unaffected:**
- **Single-athlete (`owner`) operation** — all isolation gaps are latent under owner-only; the `run_forever` while-True path retains the correct 07:00 gate.
- **The safety floor (H1–H5)** — `ThresholdAdapter` excludes `HARD_STOP_THRESHOLD_KEYS` from all adaptation; no calibration or cohort path can widen a hard-stop gate (A2-c verified). The DB write-guard for H1–H5 (ADR-0052) is intact.
- **Phase 27 greenfield surface** — no `CohortProfile`/cohort code exists (A2-d); clean slate.
- **Lazy constants (A1-c), B2c TypeError (A1-d), corpus-gate query correctness (A3-b), advisory-mode posture (A4-a)** — all clean.

**Governance note:** This audit was conducted read-only; no files were modified. Recommend resolving blockers 1–5 under a dedicated Phase 27 isolation-hardening work item with an accompanying ADR (schema bumps for A3-02/A3-04/A2-04) and a behavioral two-athlete isolation fitness function (A4-02) before the cohort-analytics deliverables proceed.
