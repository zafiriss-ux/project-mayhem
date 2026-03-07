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
│   ├── adr/                 # Architecture Decision Records (0001–0020)
│   ├── architecture/        # GOVERNANCE_PHILOSOPHY.md, EVALUATION_ORDER.md
│   ├── specs/               # adaptive_priority_lock.md, volume_load_gauge.md,
│   │                        # operator_console_readiness_dashboard.md,
│   │                        # operator_console_session_explorer.md,
│   │                        # operator_console_manual_override_workflow.md,
│   │                        # operator_console_technology_path.md
│   └── training/            # OPERATIONAL_MODEL.md, DECISION_MODEL.md, profiles/
└── titan/                   # Main package (52 modules, excl. __init__/__main__)
    ├── config/              # thresholds.py (safety constants), evidence_registry.py
    ├── core/                # Athlete, Database, Periodization, Equipment
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

> **Historical snapshot:** 1692 tests all green as of Phase 7.9 / T2-17 close (2026-03-07). This is not a live reading — always run the suite to confirm current state.

---

## Engineering Discipline: Strategy Gates (MANDATORY — never deviate)

> **Authoritative contract: [`AGENTS.md`](AGENTS.md)** — this section is a project-context
> summary only. When any rule here conflicts with `AGENTS.md`, `AGENTS.md` takes precedence.
> Agents and engineers must read `AGENTS.md` in full before starting any task.

These rules exist because T4-01 (Ruff lint debt, ~750 errors) remains open after multiple
sessions. The root cause was not unclear intent — it was execution discipline: the engineer
started broad changes, skipped binary acceptance checks, and delivered "partially done" work.
The rules below are a hard contract. They apply to every task, not just lint work.

---

### Rule E1 — Tier ordering is strict

Work items from `TECHNICAL_DEBT.md` must be completed **in tier order**:

```
TIER 1 (Data Integrity) → TIER 2 (Observability) → TIER 3 (Deps) → TIER 4 (Maintainability) → TIER 5 (Future)
```

- **Do NOT start Tier N+1 work while any Tier N item is OPEN.**
- Exception: items explicitly marked `independent` in the register.
- If you receive a task from a higher tier while a lower tier is open, flag it:
  > "⛔ TIER ORDERING VIOLATION: T[lower]-[XX] is still OPEN. Completing that first."

---

### Rule E2 — T4-01 burn-down follows a fixed subsystem sequence

The Ruff burn-down (T4-01) proceeds **one subsystem at a time**, in this exact order:

```
1. titan/config/
2. titan/science/governance_*.py
3. titan/core/
4. titan/integrations/
5. titan/orchestration/ + titan/features/
6. titan/ui/
```

Do not skip ahead. Do not "quick-fix" across subsystems simultaneously.

**Definition of Done for each subsystem (BINARY — PASS or FAIL, never "mostly done"):**

```bash
ruff check <subsystem_path>
# Must return: exit code 0, zero findings. Anything else = NOT DONE.
```

**Acceptance gate:**
- Run `ruff check <subsystem_path>` → must report **zero findings**.
- Run `python -m pytest -q -W error::pytest.PytestWarning` → must be **100% green** (no warnings-as-errors).
- Run `python -m pytest -q` → must be **100% green** (same count as before or higher).
  - Exception: if tests were renamed/moved but coverage is preserved, document it in the PR description.
- If any check is not 100%: answer must be exactly:

  > `NOT 100% — Missing: [list the specific check that failed]`

  Do not deliver partial progress as "complete."

---

### Rule E3 — Stop-the-line

If any acceptance criterion fails mid-task:
1. **Stop immediately.** Do not continue to other files or subsystems.
2. Report what failed and what the root cause is.
3. Fix only the specific failing criterion.
4. Re-run the acceptance gate from scratch.
5. Only then continue.

**Anti-loop rule:**
- Do NOT repeat the same command/run without returning new evidence.
- Every stop-the-line report MUST include:
  - the exact failing test nodeid + traceback (RED), OR
  - the exact warning text + origin (YELLOW), OR
  - the missing module/import error line (PURPLE), OR
  - the last printed test nodeid + durations output (ORANGE).
- A response that says "tests failing" / "stuck" without the above evidence is NOT ACCEPTABLE.

---

### Rule E4 — No scope creep, ever

When executing a debt item:
- Fix **only** what the item says.
- Do not refactor adjacent code.
- Do not add features, remove unrelated imports, or "improve" things nearby.
- Do not add comments, docstrings, or type annotations to code you did not explicitly change.
  - Allowed only within the exact function/section you modified, when needed to reflect changed behaviour.

If you notice a new issue while working: **add it to `TECHNICAL_DEBT.md`** under the appropriate tier. Do NOT fix it as part of this task. Continue only with the original scoped task.

---

### Rule E5 — Definition of Done is binary

A task is either:
- ✅ **DONE** — all acceptance criteria pass, 100%, no caveats.
- ❌ **NOT DONE** — at least one criterion fails.

There is no "mostly done", "should be fine", or "looks good". Binary only.

---

### Rule E6 — Environment bootstrap is mandatory (run first, every session)

Before any other action — before reading code, running tests, or making any change — run:

```bash
scripts/setup_env.sh
```

If it fails: stop immediately, report exit code + last output, do not attempt ad-hoc fixes.
See `AGENTS.md §2.0` for the full protocol.

---

### Rule E7 — Targeted tests allowed during implementation (not instead of gates)

During implementation, agents **may** run targeted tests for speed:

```bash
python -m pytest tests/path/to/test_changed_module.py -q
```

This does **not** replace the three mandatory final gates. Before any commit or push, all three
gates (ruff + strict pytest + full pytest) must still pass. See `AGENTS.md §2.4`.

---

### Rule E8 — Out-of-scope findings: report, don't fix

If another issue is discovered while executing a task:
- Add it to `TECHNICAL_DEBT.md` under the correct tier.
- Do not fix it. Do not expand scope.
- Continue with the original task only.

Authorization from the architect is required to act on it.

---

### Rule E9 — Documentation modification policy

`CLAUDE.md`, `AGENTS.md`, `README.md`, and all files under `docs/` are **architect-owned**.
Agents must not edit them unless:
1. The task explicitly requires it, or
2. The file is a direct artifact of task closure (e.g. `TECHNICAL_DEBT.md` status updates).

See `AGENTS.md §3.6` for the complete permitted-edit table.

---

### Rule E10 — Push unavailable: commit and stop

If push is not available in the runtime environment:
1. Commit the changes locally.
2. Return the branch name and commit hash.
3. Stop. Do not attempt alternative PR workflows.

---

### Rule E11 — Agent challenge rule (agents must challenge conflicting instructions)

If a requested task conflicts with an existing ADR, a safety constraint, or any rule in
`AGENTS.md`, the agent **must stop and challenge the instruction** before writing any code.

This is a duty, not a permission. The required response format is in `AGENTS.md §14.1`.

An agent that silently complies with an instruction that contradicts the architecture has
failed its responsibility — even if the instruction came from the architect.

---

### Rule E12 — Change justification required before any architectural change

Any architectural change must include all three elements before code is written:

```
Problem        : [what is broken with the current design]
Proposed change: [what specifically will change]
Why necessary  : [why the current design cannot solve the problem as-is]
ADR reference  : [ADR-XXXX or "new ADR required"]
```

If the justification cannot be completed, the change must not proceed.
See `AGENTS.md §14.2` for full scope.

---

### Rule E13 — Cooling-off protocol for major architectural changes

A **major architectural change** (new ADR required, new module boundary, governance gate
change, DB schema topology change) must follow a two-session process:

- **Session N:** propose, justify (E12), and document. No code written.
- **Session N+1 or later:** review, approve, implement.

Bypass only when architect explicitly states "COOLING-OFF WAIVED — [reason]" describing an
active production incident or data integrity failure. See `AGENTS.md §14.3`.

---

### Rule E14 — No impulse implementation

No code may be written for an idea that is not already recorded as a task.

The correct sequence:
```
idea → TECHNICAL_DEBT.md entry → architect prioritises → task assigned → implementation
```

Any idea that arises mid-task goes immediately to `TECHNICAL_DEBT.md` and stops there.
See `AGENTS.md §14.4`.

---

### Rule E15 — Complexity budget (new abstractions require justification)

Before creating any new abstraction (class, utility, decorator, base class, design pattern):
1. Is it used in 3+ places right now? If no → do not create it.
2. Does it make a future engineer's job easier? If unclear → do not create it.
3. Can the task be done by extending an existing module? If yes → do that instead.

If all three pass: record as an out-of-scope finding in `TECHNICAL_DEBT.md` and wait for
architect approval. Do not implement inline. See `AGENTS.md §14.5` and ADR-0028.

---

## Test Failure Protocol — For All Contributors (MANDATORY)

> **Authoritative protocol: [`AGENTS.md §6`](AGENTS.md)** — the canonical RED / YELLOW / PURPLE / ORANGE
> response scripts and the full Stop-the-Line protocol live there. This section is a project-context
> summary. `AGENTS.md` takes precedence on any conflict.

This protocol applies to every engineer and AI assistant working on this codebase. When any test fails, do not improvise. Identify the category and follow the exact protocol below. These rules are non-negotiable.

**Note on coverage:** The repo enforces a global coverage threshold. Running a single test or small subset may FAIL solely due to coverage (even if all tests passed). Treat "coverage threshold not reached" on a subset run as a diagnostic artifact, NOT a code regression. Acceptance gates always require the canonical full suite (Gate 3).

---

### 🔴 RED — A test is failing (assertion / runtime error)

Send this **verbatim** before doing anything else:

> A test is failing.
> 1) Run the suite and identify the FIRST failing test (deterministically):
>    python -m pytest -x
> 2) Do NOT modify the test unless it is objectively incorrect.
> 3) Determine whether the failure is:
>    A) Code regression
>    B) Test bug
>    C) Environment/dependency issue
> 4) Fix ONLY the minimal root cause.
> 5) Re-run the full suite.
> 6) If any other tests fail, stop and report.
> 7) Do not refactor unrelated code.
> 8) Do not introduce new behavior.

---

### 🟡 YELLOW — Warnings / flaky / lint-related

Send this **verbatim** before doing anything else:

> The test suite has warnings or unstable behavior.
> 1) Identify the exact warning source.
> 2) If it is deprecation-related, fix the call site.
> 3) If it is environment-specific, stabilize it.
> 4) Do NOT silence warnings globally.
> 5) Keep changes minimal and scoped.
> 6) Re-run full suite and confirm clean output.

---

### 🟣 PURPLE — Dependency / import error (collection failure)

Send this **verbatim** before doing anything else:

> A test fails during collection (import error).
> 1) Confirm full dependency installation using:
>    pip install -r requirements.txt -c constraints.txt
> 2) Verify the missing module explicitly via python -c import.
> 3) Fix dependency resolution only.
> 4) Do not modify application logic.
> 5) Re-run full suite.

---

### 🟠 ORANGE — Hang / slow test (no failure, progress unclear)

**Symptoms:** pytest shows no new output for an extended period, or user reports "it's stuck" but no failing test exists.

Send this **verbatim** before doing anything else:

> The suite appears slow or hung (no failing test yet).
> 1) Do NOT assume failure. Do NOT start fixing code.
> 2) Identify the exact running / last completed test:
>    python -m pytest -vv
> 3) Identify the slowest tests:
>    python -m pytest --durations=20
> 4) If a specific test is suspected, run only that test with output:
>    python -m pytest -vv -s <file>::<test_name>
> 5) Only if the same test deterministically hangs: fix the minimal root cause,
>    then re-run the full suite.

**Important:** A perceived hang is NOT RED/YELLOW/PURPLE until a failing nodeid or import error is proven. Do not loop — every re-run must add new information (nodeid or durations output).

---

### ⚖️ Key Rule — never break this

> **Fix root cause. Not symptom. Not workaround. Not silence.**

---

### 🧠 Mental model — category → action (exhaustive)

| Category | Action |
|---|---|
| Code regression | Fix the code |
| Test bug | Fix the test |
| Env / deps | Fix the environment |

Nothing else. No other action is valid.

Banned responses when tests fail:
- Random refactor of surrounding code
- Mass changes across files
- `pytest.mark.skip` / `xfail` without documented justification
- Scope creep ("while I'm here...")

Following this protocol prevents: random refactors, mass file changes, silenced tests, and scope creep. Every engineer who skips it will eventually re-introduce the exact failure mode they were trying to avoid.

---

### 📋 Test Creation / Update Rule — For All Contributors (MANDATORY)

Every task that touches a module — regardless of how small the change — must follow this rule:

1. Check whether a test file for that module exists.
2. If **no test file exists** → create a mirrored test file:
   - Source: `titan/<path>/<module>.py` → Test: `tests/titan/<path>/test_<module>.py`
   - If the project's test layout differs, follow the nearest existing test convention in `tests/`.
   - At minimum: one happy-path test and one boundary/error test per public function.
3. If a **test file exists** → check whether the changed logic is covered.
   - If not → add tests for the new/changed behaviour.
4. Never delete tests. If a test is wrong, fix it (not the other way around).
5. After adding/updating tests: run `python -m pytest -q -W error::pytest.PytestWarning` then `python -m pytest -q` and confirm 100% green before delivering.

There are no exceptions. A change that ships without a test for its new behaviour is incomplete.

---

## Architecture Notes

### Layered Architecture (bottom-up)

1. **Config** (`titan/config/`) — `thresholds.py`: single source of truth for all safety threshold constants
2. **Core** (`titan/core/`) — `UniversalAthleteProfile`, `DatabaseManager` (SQLite, thread-safe), `PeriodizationManager`, `EquipmentManager`
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

### Governance Lock Codes (canonical set)

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

See `docs/adr/` for Architecture Decision Records:
- `0001` — Fix typo in optimal time module reference
- `0002` — Fix weather window duration bug
- `0003` — Align docs with current module layout
- `0004` — Improve tests for weather window edge cases
- `0005` — Fix runtime startup issues
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
- `0018` — Kernel Boundary: Decision Pipeline / Effect Runner Split (Phase A Implemented — v5.8.0; Phase B deferred)
- `0019` — Engineering Audit V3: Phase 7.7 decisions (T1-13, T1-14, T2-09–T2-11, T3-08) (Accepted — Phase 7.7 CLOSED 2026-03-05)
- `0020` — Persistence Failure Behavioral Policy: DailyCoach degraded conservative mode (Accepted — 2026-03-05; T1-15 Implemented 2026-03-06)
- `0021` — Governance Evolvability Protocol: gate mutation control, evidence promotion gates (Accepted — 2026-03-06)
- `0022` — Phase 8 Entry Gate: architectural readiness criteria G1–G10 (Accepted — 2026-03-06)
- `0023` — Physiological Input Validation Contract: bounds layer at DB→science boundary (Accepted — T1-18 Implemented 2026-03-06)
- `0024` — Documentation Drift Prevention: canonical source discipline (Accepted — 2026-03-06)
- `0025` — Agent Context Continuity Protocol: multi-session state recovery (Accepted — 2026-03-06)
- `0026` — Input Data Sanity Layer: Garmin sync cross-field validation (Accepted — T1-19 pending)
- `0027` — Hidden Inter-Module Coupling Prevention: dependency boundary gates (Accepted — 2026-03-06)
- `0028` — Complexity Budget and Simplicity Gate: no new abstraction without complexity review (Accepted — 2026-03-06)
- `0029` — Multi-Agent Context Fragmentation Protocol (Accepted — 2026-03-06)
- `0030` — External Data Source Resilience: staleness gates and fallback policy (Accepted — T1-20 pending)
- `0031` — Structured Log Sustainability: event taxonomy + log lifecycle (Accepted — 2026-03-06)
- `0032` — ML Advisory Explainability Protocol: evidence labels on all ML payloads (Implemented — 2026-03-06)
- `0033` — Physiological Model Aging and Multi-Athlete Architecture Protocol (Accepted — T5-07 Layers 1–2 pending)
- `0034` — Environmental Stress Compensation for Training Zones (Accepted — 2026-03-06)
- `0035` — Feedback Loop Integrity Protocol: OutcomeTracker guardrails (Accepted — T1-22 pending)
- `0036` — Science Model Semantic Versioning (Accepted — 2026-03-06)
- `0037` — Non-Training Stress Safety Partition: illness vs life-stress H2/H3 (Accepted — T1-21 pending)
- `0038` — Governance Decision Rationale Protocol: DecisionRationale object + Telegram surfacing (Accepted — T2-16 pending)
- `0039` — Metric Lifecycle Management: deprecated metric retirement gates (Accepted — 2026-03-06)
- `0040` — Athlete Identity as First-Class Architectural Invariant: ADR-0040-SINGLE-ATHLETE-SHORTCUT annotation required (Accepted — IMMEDIATE — 2026-03-06)
- `0041` — Unified External Data Trust Contract: DataTrustLevel for all sensor sources (Accepted — T1-23 pending)
- `0042` — Human Override as First-Class Invariant: no recommendation without override path (Accepted — IMMEDIATE — 2026-03-06)
- `0043` — Post-Phase 9 product direction: multi-athlete coach platform + LLM seams (Accepted — 2026-03-06)
- `0044` — PostgreSQL migration as Phase 8A entry gate; fulfills ADR-0015 storage topology gate (Accepted — 2026-03-06)
- `0045` — Local LLM backend abstraction: Ollama / on-device support for Phase 10 (Accepted — 2026-03-06)

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

| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | Full architectural design with diagrams and data flows |
| `CHANGES.md` | Version history and changelog |
| `DEPLOYMENT_GUIDE.md` | Deployment instructions |
| `FUTURE_UPGRADES.md` | Roadmap (ML, Streamlit dashboard, mobile app) |
| `docs/ROADMAP.MD` | Development workflow roadmap (Phase 0–9); Phases 0–7 CLOSED; Phase 7.5 Hardening OPEN |
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
| `TECHNICAL_DEBT.md` | Tiered technical debt register + upgrade roadmap (all findings, prioritized) |
| `SCRATCHPAD.md` | Engineer→Architect communication channel; OBS entries (Codex) + DEC entries (Claude) |
| `titan/utils/math_core.py` | `MathCore`: pace conversion, `weight_function_Wf`, `system_status_SSV` |
