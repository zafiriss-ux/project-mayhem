# CLAUDE.md — TITAN OS

## Project Overview

**TITAN OS** (v5.8.0) is a closed-loop, longevity-first athletic operating system for runners. It integrates with Garmin Connect to sync training data and wearables, applies science-based algorithms (HRV, TSB/CTL/ATL, ACWR, lactate threshold, drift analysis, autonomic fusion), enforces safety-first governance gates, generates weekly training plans, calculates optimal workout timing based on weather/dew point, optimizes nutrition macros, and delivers coaching via a Telegram bot.

- **Language**: Python 3.11+ (mandatory — uses `tomllib`, UTF-8 mode PEP 686)
- **Database**: SQLite (thread-safe, via `DatabaseManager`)
- **External APIs**: Garmin Connect, Open-Meteo (weather), Telegram Bot API (via `pyTelegramBotAPI`)

---

## Repository Layout

```
project-mayhem/
├── main.py                  # Root launcher (delegates to titan/main.py)
├── system_check.py          # Module health check
├── requirements.txt         # Production + dev dependencies (pinned)
├── pyproject.toml           # pytest + coverage config
├── test_core_modules.py     # Core module tests
├── test_new_modules.py      # Additional module tests
├── test_titan_logic.py      # Science logic tests
├── test_main_smoke.py       # Entry point smoke tests
├── test_menu_system.py      # Menu system tests
├── test_daily_coach_extended.py  # Extended daily coach tests
├── test_error_paths.py      # Error path tests
├── test_logic_pytest.py     # Logic tests (pytest)
├── test_telegram_bot.py     # Telegram integration tests
├── test_property_based.py   # Property-based tests (hypothesis)
├── tests/                   # Integration + hygiene tests (21 files)
│   ├── test_governance_integration.py       # Contract + boundary tests (27 tests)
│   ├── test_p0_safety_gates.py              # P0 hard-stop gate tests (20 tests)
│   ├── test_apl_integration.py              # APL contract + invariant tests (64 tests)
│   ├── test_phase3_hygiene.py               # Phase 3 branch-coverage sweep (27 tests)
│   ├── test_phase4_hygiene.py               # Phase 4 observability sweep (24 tests)
│   ├── test_e2e_regression_suite.py         # Gold-path E2E regression scenarios
│   ├── test_outcome_tracker_persistence.py  # OutcomeTracker DB persistence
│   ├── test_science_engines.py              # Comprehensive science engine tests
│   ├── test_athlete_database_schema_validation.py  # Schema validation
│   ├── test_telegram_calibration_command.py # /calibration Telegram command
│   ├── test_phase4_observability_flows.py   # Structured flow log tests
│   ├── test_phase4_slo_alerts.py            # SLO alert firing tests
│   ├── test_todo_fix_recommendations.py    # P0/P1/P2 gate coverage (boundary tests)
│   ├── test_operator_console_dashboard.py  # Operator Console service payload tests (Phase 6)
│   ├── test_phase6_hygiene.py              # Phase 6 branch-coverage sweep (24 tests)
│   ├── test_automated_periodization.py     # AutomatedPeriodizationEngine contract tests (Phase 7)
│   ├── test_injury_risk_model.py           # InjuryRiskEnsembleModel contract tests (Phase 7)
│   ├── test_load_prediction_shadow.py      # LoadPredictionShadowModel contract tests (Phase 7)
│   ├── test_ml_kill_switch.py              # ML kill-switch env toggle tests (Phase 7)
│   ├── test_phase7_hardening.py            # Phase 7 version + DailyCoach hardening tests
│   └── test_phase7_hygiene.py             # Phase 7 branch-coverage sweep (31 tests)
├── .github/workflows/       # CI pipelines (ci.yml, codeql.yml, secret-scan.yml)
├── docs/
│   ├── adr/                 # Architecture Decision Records (0006–0046, 29 ADRs)
│   ├── architecture/        # GOVERNANCE_PHILOSOPHY.md, EVALUATION_ORDER.md
│   ├── specs/               # adaptive_priority_lock.md, volume_load_gauge.md,
│   │                        # operator_console_readiness_dashboard.md,
│   │                        # operator_console_session_explorer.md,
│   │                        # operator_console_manual_override_workflow.md,
│   │                        # operator_console_technology_path.md
│   └── training/            # OPERATIONAL_MODEL.md, DECISION_MODEL.md, profiles/
└── titan/                   # Main package (54 modules, excl. __init__/__main__)
    ├── config/              # thresholds.py (safety constants), evidence_registry.py
    ├── core/                # Athlete, Database, Periodization, Equipment, PersistenceAdapter
    ├── science/             # 26 modules (engines + governance + ML scaffold)
    ├── features/            # Weekly planner, optimal time, nutrition optimizer
    ├── integrations/        # Garmin, Weather API, Telegram bot
    ├── orchestration/       # DailyCoach v5.8 (12-step morning routine)
    ├── ui/                  # Menu system, setup wizard, OperatorConsole
    └── utils/               # MathCore, constants
```

---

## Development Setup

```bash
# Requires Python 3.11+
python --version

# Install dependencies
pip install -r requirements.txt

# Run the system check
python system_check.py

# Launch via root launcher
python main.py

# Or launch directly (skips launcher validation, requires .env to be configured)
python -m titan
```

### Environment Configuration

The system reads from `~/Documents/TITAN/.env`. Required variables:

```bash
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
WEATHER_API_KEY=unused           # kept for backwards-compat; Open-Meteo requires no key
WEATHER_LOCATION=Athens,GR

# Optional overrides
DATABASE_PATH=titan.db
LOG_LEVEL=INFO
GARMIN_SYNC_INTERVAL_HOURS=6
WEATHER_CACHE_DURATION_HOURS=1
```

---

## Running Tests

### Engineering Definition of Done (non-negotiable for any PR)

All three gates must pass before any commit, push, or `make_pr`. This is a hard requirement — not a guideline.

```bash
# Gate 1 — Lint (zero findings required)
ruff check .

# Gate 2 — Strict test run (warnings are failures)
python -m pytest -q -W error::pytest.PytestWarning

# Gate 3 — Canonical test run (100% green, count same or higher)
python -m pytest -q
```

No PR may be opened, and no `make_pr` may be called, until all three commands above return clean. See AGENTS.md §HARD GATE.

### Additional test commands (use only after Gates 1–3 pass)

```bash
# With coverage (only when coverage report is explicitly requested)
python -m pytest -q --cov=titan --cov-report=term-missing

# Governance integration tests
python -m pytest tests/test_governance_integration.py -v

# Governance coverage threshold (CI requirement)
python -m pytest --cov=titan.science.governance_engine \
       --cov=titan.science.governance_contracts \
       --cov-fail-under=80 -q

# APL integration tests
python -m pytest tests/test_apl_integration.py -v

# Phase hygiene sweeps
python -m pytest tests/test_phase3_hygiene.py tests/test_phase4_hygiene.py tests/test_phase6_hygiene.py tests/test_phase7_hygiene.py -v

# Specific test files
python -m pytest test_core_modules.py
python -m pytest test_titan_logic.py
python -m pytest tests/test_p0_safety_gates.py
python -m pytest tests/test_science_engines.py
```

Test configuration is in `pyproject.toml`. Tests discover all `test_*.py` files in the root directory and `tests/`.

> **Historical snapshot:** 1918 tests all green as of Phase 8 / T5-27 close (2026-03-14). This is not a live reading — always run the suite to confirm current state.

---

## Engineering Rules — Reference Map (canonical: AGENTS.md)

`AGENTS.md` is the authoritative engineering contract for all agents and engineers.
When anything here conflicts with `AGENTS.md`: **`AGENTS.md` wins.**

| Rule | Topic | AGENTS.md |
|------|-------|-----------|
| E1 | Tier ordering — T1→T2→T3→T4→T5, never skip | §4 |
| E2 | T4-01 Ruff burn-down: fixed subsystem sequence | §4.1 |
| E3 | Stop-the-Line: fail → stop → fix root cause → re-run all | §7 |
| E4 | No scope creep: fix only what the item says | §3 |
| E5 | Definition of Done is binary: DONE or NOT DONE | §5 |
| E6 | Environment bootstrap (`scripts/setup_env.sh`) first, every session | §2.0 |
| E7 | Targeted tests during implementation (not instead of final gates) | §2.4 |
| E8 | Out-of-scope findings → `SCRATCHPAD.md` OBS entry first, then `TECHNICAL_DEBT.md` via architect DEC | §3.4 / §15 |
| E9 | Docs modification policy — architect-owned files | §3.6 |
| E10 | Push unavailable → commit, report branch + hash, stop | §2.2 |
| E11 | Agent challenge rule — must challenge conflicting instructions | §14.1 |
| E12 | Change justification required before any architectural change | §14.2 |
| E13 | Cooling-off protocol — major changes wait one session | §14.3 |
| E14 | No impulse implementation — idea → TECHNICAL_DEBT.md → task → code | §14.4 |
| E15 | Complexity budget — new abstractions require justification | §14.5 + §16.11 |
| E16 | Path declared before start — Path A or B set before Codex begins | §17.4 |
| E17 | No mid-item path switching — restart from step 1 if path changes | §17.4 |
| E18 | Workflow drift is a process violation — same severity as HARD GATE | §17.4 |
| E19 | DoR gate mandatory — Definition of Ready before implementation begins | §17.5 |
| — | Governance evolution protocol (3 required steps) | §16.1 |
| — | Phase 8 Entry Gate (G1–G11 binary criteria) | §16.2 |
| — | Phase 8 per-item workflow (Path A standard / Path B QA-assisted) | §17 |
| — | Athlete identity invariant (rules A40-1 to A40-4) | §16.10 |
| — | Subsystem ownership (Owner-of-Record per subsystem) | §1.1 |
| — | Task Learning — required field in every TECHNICAL_DEBT.md resolution | §12.1 |
| — | Bottleneck/Owner/Unblock — optional metadata for blocked items | §17.6 |

---

## Test Failure Protocol — Reference (canonical: AGENTS.md §6)

> Full verbatim scripts (RED / YELLOW / PURPLE / ORANGE), Stop-the-Line rules, and the
> test-creation mandate are in **`AGENTS.md §6`**. The summary below is for quick orientation only.
> On any conflict, `AGENTS.md` wins.

| Signal | Condition | First action |
|--------|-----------|-------------|
| 🔴 RED | Test assertion / runtime error | `pytest -x` → identify first failure → fix root cause |
| 🟡 YELLOW | Warnings / flaky / lint | Identify exact warning source → fix call site → no global silencing |
| 🟣 PURPLE | Import / collection error | `pip install -r requirements.txt -c constraints.txt` → fix deps only |
| 🟠 ORANGE | Hung / no output | `pytest -vv` → `pytest --durations=20` → add evidence before re-running |

**Invariant:** Fix root cause. Not symptom. Not workaround. Not silence.

**Coverage note:** "coverage threshold not reached" on a subset run is a diagnostic artifact, not a regression. Gate 3 always requires the full suite.

**Test creation rule (AGENTS.md §6 ⚠️ ABSOLUTE RULE):** Every change to a module must be accompanied by tests for the new/changed behaviour. `titan/<path>/<module>.py` → `tests/titan/<path>/test_<module>.py`. No exceptions.

---

## Architecture Notes

### Layered Architecture (bottom-up)

1. **Config** (`titan/config/`) — `thresholds.py`: single source of truth for all safety threshold constants
2. **Core** (`titan/core/`) — `UniversalAthleteProfile`, `DatabaseManager` (SQLite, thread-safe), `PeriodizationManager`, `EquipmentManager`, `PersistenceAdapter` (T5-08-B D1 ABC)
3. **Science** (`titan/science/`) — 26 modules:
   - Foundational engines (11): HRV, TSB/CTL/ATL, ACWR, lactate, drift, efficiency, durability, TRIMP, glycogen, fatigue, readiness
   - Autonomic & critical (4): `AutonomicFusionEngine` (AFI), `CriticalSpeedEngine`, `RCPEngine`, `BiomechanicsEngine`
   - Advanced (1): `AdaptiveMemory`
   - Governance infrastructure (6): `GovernanceEngine`, `GovernanceContracts`, `IntensityGovernor`, `VolumeLoadGauge`, `AdaptivePriorityLock`, `OutcomeTracker`
   - ML scaffold — shadow/advisory mode (4): `LoadPredictionShadowModel`, `InjuryRiskEnsembleModel`, `AutomatedPeriodizationEngine`, `MLSafety` (kill-switch)
4. **Governance Layer** (within science/) — 7-gate safety system; must run before every session recommendation; non-bypassable
5. **Integrations** (`titan/integrations/`) — `GarminSync` (6h background thread), `WeatherAPI` (1h cache, 48h forecast), `TitanTelegramBot`
6. **Features** (`titan/features/`) — `WeeklyPlanGenerator`, `OptimalTimeCalculator`, `NutritionOptimizer`
7. **Orchestration** (`titan/orchestration/`) — `DailyCoach` v5.7: 12-step morning routine, hydrates engines from DB on startup

### Key Safety Constants (`titan/config/thresholds.py`)

```python
HARD_STOP_HRV_DELTA       = 15.0   # ms drop (>=) triggering H2 gate
HARD_STOP_RHR_DELTA       = 8.0    # bpm rise (>=) triggering H3 gate
HARD_STOP_TSB_FLOOR       = -50.0  # TSB floor (<=) triggering H4 gate
SUBJECTIVE_FATIGUE_EXTREME = 8     # RPE/10 score (>=) triggering H5 gate
SUBJECTIVE_FATIGUE_2OF4   = 6      # Score for 2-of-4 soft downgrade
VO2_ACWR_MIN              = 0.80
VO2_ACWR_MAX              = 1.30
VO2_READINESS_MIN         = 65.0
VO2_GLYCOGEN_DEBT_MAX     = 7.0
VO2_MIN_DAYS_SINCE_LAST   = 2
```

### Governance Lock Codes (reference snapshot only)

> **Reference snapshot only.** Canonical source: `CANONICAL_LOCK_CODES` frozenset in
> `titan/config/thresholds.py`. The list below is for quick orientation and may lag the
> canonical set. Always use `thresholds.py` as the authoritative source when adding,
> renaming, or checking lock codes.

`HARD_STOP_SAFETY_GATES`, `VO2_ELIGIBILITY_GATE`, `FUELING_GATE_LOCK`,
`FUELING_GATE_FLAG`, `READINESS_2OF4_DOWNGRADE`, `INTENSITY_GATE_RED`,
`INTENSITY_GATE_YELLOW`, `PARASYMPATHETIC_GUARD`, `OVERRIDE_LOCKDOWN`,
`CS_CONFIDENCE_LOCK`

### Threading

Three daemon background threads run when the system is live:
- **Garmin Sync** — every 6 hours
- **Weather Update** — every 1 hour
- **Daily Coach / Scheduler** — cron-style (07:00 morning briefing, 20:00 Sunday weekly plan)

All SQLite writes use `threading.Lock` (`check_same_thread=False`).

### Database

Five SQLite tables: `daily_metrics`, `training_log`, `gear_usage`, `personal_bests`, `governance_outcomes`.
- `governance_outcomes` — created by `OutcomeTracker` (v5.7.1); stores paired governance decisions + post-session outcomes for threshold calibration.
Canonical column name for temperature: `temperature_c`.
`get_training_load_history()` is used to rebuild CTL/ATL on startup.

### Key Architectural Decisions

See `docs/adr/` for Architecture Decision Records (28 total — architectural decisions only).
Process rules are in `AGENTS.md §16`. Historical bug-fix records are in `CHANGES.md`.

- `0006` — Architectural hardening: cold start and engine sync
- `0007` — Intensity governance architecture audit (read-only assessment)
- `0008` — Adaptive Priority Lock and VLG specs (VLG: implemented; APL: implemented — v5.7.1)
- `0009` — Safety gate hardening: C1 & C2 resolution (OR semantics + gate reorder — v5.7.4)
- `0010` — Operator Console: Readiness Dashboard MVP payload (Implemented — v5.8.0)
- `0011` — Operator Console: Session Explorer payload + manual annotation (Implemented — v5.8.0)
- `0012` — Operator Console: Manual Override Workflow (Accepted — v5.8.0)
- `0013` — Operator Console: Technology path — Streamlit → React + FastAPI (Accepted — v5.8.0)
- `0014` — Phase 7 ML scaffold: shadow/advisory mode, kill-switch, evidence labels (Implemented — v5.8.0)
- `0015` — SQLite retention strategy and Phase 8 data lifecycle gate (Accepted — v5.8.0)
- `0016` — Phase 8 multi-sport scope and unified adapter gate (Accepted — v5.8.0)
- `0017` — Composition root fan-in and DailyCoach god-orchestrator audit (Accepted — assessment only, 2026-03-04)
- `0018` — Kernel Boundary: Decision Pipeline / Effect Runner Split (Phase A Implemented — v5.8.0; Phase B Implemented — v5.8.0 2026-03-08)
- `0020` — Persistence Failure Behavioral Policy: DailyCoach degraded conservative mode (Accepted — 2026-03-05; T1-15 Implemented 2026-03-06)
- `0022` — Phase 8 Entry Gate Review and Architect Sign-off (Accepted — Phase 8 OPEN 2026-03-08)
- `0023` — Physiological Input Validation Contract: bounds layer at DB→science boundary (Accepted — T1-18 Implemented 2026-03-06)
- `0026` — Input Data Sanity Layer: Garmin sync cross-field validation (Implemented — T1-19 Implemented 2026-03-07)
- `0027` — Hidden Inter-Module Coupling Prevention: dependency boundary gates (Accepted — 2026-03-06)
- `0030` — External Data Source Resilience: staleness gates and fallback policy (Implemented — T1-20, T2-15 Implemented 2026-03-07)
- `0032` — ML Advisory Explainability Protocol: evidence labels on all ML payloads (Implemented — 2026-03-06)
- `0033` — Physiological Model Aging and Multi-Athlete Architecture Protocol (Accepted — Layers 1–2 implemented 2026-03-13 commit b6bea2a; Layer 3 deferred Phase 9)
- `0034` — Environmental Stress Compensation for Training Zones (Accepted — 2026-03-06)
- `0037` — Non-Training Stress Safety Partition: illness vs life-stress H2/H3 (Implemented — T1-21 Implemented 2026-03-07)
- `0038` — Governance Decision Rationale Protocol: DecisionRationale object + Telegram surfacing (Implemented — T2-16 Implemented 2026-03-07)
- `0041` — Unified External Data Trust Contract: DataTrustLevel for all sensor sources (Implemented — T1-23 Implemented 2026-03-07)
- `0042` — Human Override as First-Class Invariant: no recommendation without override path (Accepted — IMMEDIATE — 2026-03-06)
- `0044` — PostgreSQL migration as Phase 8A entry gate; fulfills ADR-0015 storage topology gate (Accepted — 2026-03-06)
- `0045` — Local LLM backend abstraction: Ollama / on-device support for Phase 10 (Accepted — 2026-03-06)
- `0046` — DailyCoach multi-athlete execution model: stateless coaching_pipeline + CoachingScheduler (Accepted — T5-16 closed 2026-03-08)
- `0047` — Architecture Fitness Functions: cyclomatic complexity gate (F1), intra-layer coupling ratio gate (F2), dependency topology DAG gate (F3); engineering execution T8-01 (Accepted — 2026-03-09)

### Future Design Notes

> These are architect-recorded design directions that have been evaluated and approved at the
> skeleton level but are **not yet ADRs and not implementation instructions**. They must not be
> converted to ADRs, implementation tasks, or policy changes without a further explicit
> architectural decision. Detailed open concerns and source material are in `SCRATCHPAD.md §Future Design Notes`.

#### FDN-001 — Orchestration Modeling: 3-Layer Architecture Skeleton (2026-03-13)

**Status:** Architecture Note — not an ADR, not an implementation instruction.
**Source:** Approved synthesis (Architect evaluation + Red-team review), 2026-03-13.

The approved skeleton for future orchestration modeling is a 3-layer separation:

1. **Layer 1 — Pillar Scoring**: Pure observation layer. Accepts raw metrics; returns a pillar vector. No knowledge of decisions or risk.
2. **Layer 2 — Profile Abstraction**: Compresses the pillar vector into an abstracted athlete state (primary limiter, secondary limiter, bottleneck count, dominant strengths, risk_weight). Emits no prescriptions and has no knowledge of sessions.
3. **Layer 3 — Decision Policy**: The only layer with knowledge of sessions, intensity, and volume. Accepts the abstracted state; returns session prescription.

The **5 pillars × 3 ordinal states** (243 raw states) model is the accepted athlete-representation direction for Layers 1–2. Not all 243 states are physiologically reachable; phantom / unreachable states must not drive handcrafted orchestration logic.

**Locked at this stage:** 3-layer architectural skeleton; ordinal (not continuous) representation principle; Layer 2 prescription-free boundary rule.

**Not locked — open design concerns (see SCRATCHPAD.md FDN-001):**
- Exact pillar set (5 pillars are indicative; final set requires data support)
- Thresholds for weak / moderate / strong states per pillar
- Exact pillar-to-metric mappings (Layer 1 input mapping)
- `risk_weight` definition (scalar vs categorical; independent vs derived)
- Decision family definitions and vector → family mapping rules
- Final prioritization logic
- Data confidence / quality signal propagation through layers
- Temporal dimension and pillar state transition rules
- Staleness / recency of pillar inputs
- Layer 2 / Layer 3 boundary enforcement (prescription bias must not leak into Layer 2 output)
- Override / human input path through the layer model

**Prerequisite for ADR promotion:** Input mapping, state threshold definitions, `risk_weight` formalization, and decision family mapping rules must be resolved first.

---

## Architect Scratchpad Review Protocol

> **The scratchpad (`SCRATCHPAD.md`) is the structured channel through which Codex surfaces
> raw engineering observations for architectural review. Claude is the sole decision-maker
> on all OBS entries. No OBS becomes a task until Claude has verified it and written a DEC.**

This section defines when and how Claude reads the scratchpad, verifies findings, and converts
them into clean tasks in `TECHNICAL_DEBT.md`.

### Trigger Conditions — When Claude MUST Review the Scratchpad

#### A-SCRATCHPAD-1: Every Session Start (mandatory, no exceptions)

Before assigning any task to Codex, Claude MUST:
1. Run `scripts/check_scratchpad.sh` — exit code 1 means BLOCKING queue is non-empty; stop immediately.
2. Read `SCRATCHPAD.md` and check the `STATUS` field.
3. If `STATUS: IDLE` → proceed to task assignment normally.
4. If `STATUS: CLARIFICATION_NEEDED` → the previous DEC is awaiting Codex input; prompt Codex to provide it before continuing.
5. If `STATUS: REVIEW_REQUESTED` or `UNDER_REVIEW`:
   - Do NOT assign a new task to Codex yet.
   - Process BLOCKING Queue first, then NON-BLOCKING Queue (see §Review Process below).
   - Only after all pending OBS entries are cleared may new tasks be assigned.

**Rationale:** Codex has accumulated observations that may change what task should be assigned
next, or may reveal that the planned task has a higher-tier dependency. Assigning tasks over
unreviewed observations leads to the same error pattern as T4-01 (broad changes, skipped gates).

#### A-SCRATCHPAD-2: Before Any New TECHNICAL_DEBT.md Planning Block

When Claude is about to add a new cluster of tasks to `TECHNICAL_DEBT.md` (e.g., a new Phase
execution sequence):
1. Check `SCRATCHPAD.md` for PENDING OBS entries.
2. If any exist, process them first — they may inform the planned tasks or contradict them.
3. If IDLE, proceed with the planning block.

**Rationale:** Codex's observations from recent implementation often contain ground-truth data
that was not visible during high-level Phase planning.

#### A-SCRATCHPAD-3: Before Declaring Any Phase CLOSED

Before writing "Phase X.Y CLOSED" anywhere (TECHNICAL_DEBT.md, CHANGES.md, CLAUDE.md):
1. Confirm `SCRATCHPAD.md STATUS: IDLE`.
2. If not IDLE, complete all pending OBS reviews first.
3. A Phase with unreviewed OBS entries is NOT closed — it is PENDING REVIEW.

---

### Review Process — Canonical Sequence

When status is `REVIEW_REQUESTED`, Claude follows this exact sequence:

```
1. Set STATUS: UNDER_REVIEW
2. Process BLOCKING Queue first (in ID order), then NON-BLOCKING Queue (in ID order):
   a. Read the observation fully.
   b. Verify the claim independently:
      - Read the referenced file:line locations.
      - Cross-reference with existing ADRs.
      - Cross-reference with open TECHNICAL_DEBT.md entries (is this already tracked?).
      - Run a targeted search if the pattern might be broader than Codex observed.
   c. Make a decision (exactly one of five outcomes):
      - NEW_DEBT_ENTRY: create a clean entry in TECHNICAL_DEBT.md (correct tier, correct format)
      - ADR_NEEDED: do not create a debt entry until the ADR is authored first
      - NO_ACTION: document why no action is needed (existing coverage, acceptable risk, etc.)
      - DEFERRED: assign to a future Phase with a written justification
      - CLARIFICATION_NEEDED: write partial DEC with one specific question; set STATUS: CLARIFICATION_NEEDED;
        wait for Codex to append answer; then resume from step 2 for this OBS (at most once per OBS)
   d. Write a DEC entry in SCRATCHPAD.md (format defined in SCRATCHPAD.md).
   e. Mark the OBS as REVIEWED (or PENDING_CLARIFICATION if CLARIFICATION_NEEDED).
3. After all OBS entries are processed:
   a. Move all REVIEWED OBS + PROCESSED DEC pairs to the Archive section of SCRATCHPAD.md.
   b. Set STATUS: IDLE.
4. Return to task assignment.
```

**Per-phase archive:** When a Phase is declared CLOSED (A-SCRATCHPAD-3), move all Archive
section entries from `SCRATCHPAD.md` to `archive/scratchpad_phase_X.Y.md`. The main
`SCRATCHPAD.md` Archive section remains lean. The archive files are never deleted.

### Architect Verification Standards

Claude must independently verify every OBS claim before writing a DEC. Accepted verification methods:

| Claim type | Verification method |
|---|---|
| "File X has pattern Y at line Z" | Read the file at that line; confirm with Grep if widespread |
| "This affects multiple modules" | Grep the pattern across the codebase; count actual occurrences |
| "This was already fixed in task T-X" | Check TECHNICAL_DEBT.md resolution entry + commit hash |
| "This violates ADR-XXXX" | Read the ADR; confirm the specific clause that is violated |
| "This is a data integrity risk" | Trace the data path through the governance pipeline |

**Claude must not take Codex's assessment at face value.** The OBS is a starting point for
investigation, not a confirmed finding. The DEC records Claude's independent conclusion.

### TECHNICAL_DEBT.md Entry Quality Gate

When a DEC creates a NEW_DEBT_ENTRY, that entry must meet the following standards before
it is written:

1. **Tier assignment is justified** — entry belongs in Tier N because of a specific data
   integrity / observability / dependency / maintainability reason, not by default.
2. **Acceptance criteria are binary** — the entry describes a single, verifiable DONE condition.
3. **Scope is minimal** — the entry does not bundle multiple independent fixes.
4. **No scope creep** — the entry does not include "while we're there" improvements.
5. **No architectural ambiguity** — if the fix requires an architectural decision, the entry
   is blocked behind an ADR (record as ADR_NEEDED, not NEW_DEBT_ENTRY).

A debt entry that fails any of these five criteria is sent back to design (ADR_NEEDED or DEFERRED).

### What Claude MUST NOT Do

- Do NOT convert an OBS directly to a task without independent verification.
- Do NOT write vague DEC entries ("seems fine" / "looks addressed"). Every DEC must be specific.
- Do NOT leave OBS entries in PENDING state across sessions. Every session start clears the queue.
- Do NOT write NEW_DEBT_ENTRies for findings already covered by an open TECHNICAL_DEBT.md item.
  Instead, note the duplicate in the DEC and add a cross-reference comment to the existing entry.
- Do NOT set STATUS: IDLE before all OBS entries in the queue are REVIEWED.

---

## Git Workflow

- **Never push directly to `main`**
- Work on feature branches (prefix: `claude/`)
- Use `git status`, `git log`, `git diff` for inspection
- Use `git push -u origin <branch-name>` for pushes
- **Do not create a commit or call `make_pr` until all three Mandatory Gates pass** (see AGENTS.md §HARD GATE)
- Canonical commit message format: `T<tier>-<id>: <short title>`

---

## Key Files for Reference

> **Documentation hierarchy**
> `TECHNICAL_DEBT.md` is the **canonical operational state** — authoritative for phase
> status, task status, and ADR list. `CLAUDE.md` is a **context snapshot** — authoritative
> for architecture notes, module inventory, and engineering rules. On any conflict between
> the two, `TECHNICAL_DEBT.md` wins for operational state; `AGENTS.md` wins for process
> rules. `tests/test_claude_md_integrity.py` enforces this invariant in CI.

| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | Full architectural design with diagrams and data flows |
| `CHANGES.md` | Version history and changelog |
| `DEPLOYMENT_GUIDE.md` | Deployment instructions |
| `FUTURE_UPGRADES.md` | Roadmap (ML, Streamlit dashboard, mobile app) |
| `docs/ROADMAP.MD` | Development workflow roadmap (Phase 0–9); Phases 0–7.9 CLOSED; Phase 8 OPEN (2026-03-08) |
| `docs/training/DECISION_MODEL.md` | Authoritative 7-gate decision pipeline |
| `docs/training/OPERATIONAL_MODEL.md` | Generic endurance framework (profile-agnostic) |
| `docs/specs/adaptive_priority_lock.md` | APL spec (implemented; v5.7.1) |
| `docs/specs/volume_load_gauge.md` | VLG spec (implemented) |
| `CORE_MIGRATION_SUMMARY.md` | v50 → v51 migration notes |
| `titan/config/thresholds.py` | Safety threshold constants (single source of truth) |
| `titan/config/evidence_registry.py` | Parameter provenance for all thresholds (STRONG/MODERATE/HEURISTIC) |
| `titan/science/adaptive_priority_lock.py` | APL: phase × load matrix → priority vector + lock thresholds |
| `titan/science/outcome_tracker.py` | Decision→outcome correlation; calibration analytics; `governance_outcomes` DB |
| `titan/ui/operator_console.py` | `OperatorConsoleService`: dashboard, session explorer, override workflow, calibration review (v5.8.0) |
| `titan/utils/constants.py` | `SESSION_TYPES`, `DEFAULT_CONFIG` (note: `ACWR_SAFE_MIN/MAX` are dead — use `thresholds.py`) |
| `titan/science/ml_safety.py` | ML kill-switch (`TITAN_ML_KILL_SWITCH` env); enforced by all Phase 7 engines |
| `titan/science/load_prediction_shadow.py` | LSTM shadow load predictor (shadow mode only; kill-switch enforced) |
| `titan/science/injury_risk_model.py` | Ensemble injury risk model (advisory; recall > 80% target; kill-switch enforced) |
| `titan/science/automated_periodization.py` | Genetic-algorithm periodization suggester (suggest-only; kill-switch enforced) |
| `titan/core/persistence.py` | `PersistenceAdapter` ABC — storage-backend contract for Phase 8A (T5-08-B D1 scaffold) |
| `GOVERNANCE_PRINCIPLES.md` | Standalone governance principles: Owner Proposal Guardrail, Engineering Ctrl-Z, Architect Constrained by Invariants, Rules Decide (extracted from `AGENTS.md`; `AGENTS.md` wins on conflict) |
| `TECHNICAL_DEBT.md` | Tiered technical debt register + upgrade roadmap (all findings, prioritized) |
| `SCRATCHPAD.md` | Engineer→Architect communication channel; OBS entries (Codex) + DEC entries (Claude); canonical out-of-scope routing rule |
| `titan/utils/math_core.py` | `MathCore`: pace conversion, `weight_function_Wf`, `system_status_SSV` |
