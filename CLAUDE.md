# TITAN OS — Repository Guide

## Quick Start

```bash
pip install -r requirements.txt
python launcher/main.py
```

## Tests

```bash
python -m pytest --no-cov -q
python -m pytest --no-cov -q -k "name"
```

**Historical snapshot:** 4382 tests all green (4382 passed, 8 skipped, 4390 collected — 2026-10-23, full pytest)

Update after every commit adding/removing tests:

```bash
python -m pytest --collect-only -q 2>&1 | tail -3
```

Failure to update causes snapshot failures.

## Module Map

Main package (77 modules, excl. __init__/__main__), ceiling 90. The ceiling test also counts the 12 subpackages: 89 of 90, one slot left.

| Package | Responsibility |
|---------|----------------|
| `core/` | DB, profile, persistence |
| `science/` | TSB, HRV, governance |
| `orchestration/` | DailyCoach, pipeline |
| `integrations/` | Garmin, Telegram, weather |
| `ui/` | Menus, wizard |
| `api/` | FastAPI, auth |
| `config/` | Thresholds, constants |
| `features/` | Nutrition, equipment |
| `worker/` | Background runner |
| `launcher/` | Entry, validator |
| `scripts/` | CSV import |
| `observability/` | Structured metrics (MetricsCollector) |
| `system_check.py` | Pre-flight |

## Key Files for Reference

| File | Purpose |
|------|---------|
| `AGENTS.md` | Governance rules (DO NOT EDIT without ADR) |
| `TECHNICAL_DEBT.md` | Open debt items |
| `docs/ROADMAP.MD` | Phase 27 OPEN (ACTIVE, 2026-06-07) — GO 2026-06-09 |
| `docs/SLO.md` | SLOs + runbooks |
| `titan/config/thresholds.py` | Safety threshold constants |
| `titan/core/database.py` | DatabaseManager, SCHEMA_VERSION (steps in `titan/core/repositories/migrations.py`) |
| `titan/orchestration/daily_coach.py` | DailyCoach (morning pipeline) |

## ADRs (`docs/adr/`)

- `0006` — Cold start sync
- `0007` — Governance audit
- `0008` — Priority Lock, VLG
- `0009` — Safety gate C1/C2
- `0010` — Console: Dashboard
- `0011` — Console: Explorer
- `0012` — Console: Override
- `0013` — Console: Technology
- `0014` — ML shadow/advisory
- `0015` — SQLite retention
- `0016` — Multi-sport adapter
- `0017` — Composition root
- `0018` — Pipeline/Effect split
- `0019` — Skipped
- `0020` — Persistence Policy
- `0021` — Skipped
- `0022` — Phase 8 Gate
- `0023` — Input Validation
- `0024` — Lock Codes
- `0025` — Skipped
- `0026` — Data Sanity
- `0027` — Coupling Prevention
- `0028` — Skipped
- `0029` — Skipped
- `0030` — External Resilience
- `0031` — Skipped
- `0032` — ML Explainability
- `0033` — Model Aging, Multi-Athlete
- `0034` — Environmental Stress
- `0035` — Skipped
- `0036` — Skipped
- `0037` — Non-Training Stress
- `0038` — Decision Rationale
- `0039` — Skipped
- `0040` — Athlete Isolation
- `0041` — Data Trust
- `0042` — Human Override
- `0043` — Skipped
- `0044` — PostgreSQL gate
- `0045` — Local LLM
- `0046` — Multi-athlete model
- `0047` — Fitness Functions
- `0048` — API Auth
- `0049` — Opus QA
- `0050` — Garmin Mitigation
- `0051` — Missing Data
- `0052` — Population Thresholds
- `0053` — Data-Void Gate
- `0054` — Coach-Athlete RBAC
- `0055` — Garmin Fallback
- `0056` — Nutrition Layer
- `0057` — Docker Deployment
- `0058` — DailyCoach Decomposition (Phase A: EngineRegistry)
- `0059` — Unified pytest Execution Model
- `0060` — Durable Worker State
- `0061` — Owner Working Rules
- `0062` — RED intensity gate volume
- `0063` — Long-run fueling reminder
- `0064` — H2 relative HRV drop
- `0065` — Downgrade volume cap
- `0066` — Sleep debt EASY day
- `0067` — Multi-athlete activation
- `0068` — Governance gate fail-closed fixes
- `0069` — Audit Category B decisions
- `0070` — Documents reconciled after MA/OW/P4

## Docker

See `docs/runbooks/docker-deploy.md` (ADR-0057). Athletes other than the owner: `docs/runbooks/multi-athlete.md`.

```bash
docker compose up --build -d
```

`titan-api` :8000 + `titan-worker`; `titan-data`→`/data/titan_core.db`.
Smoke: `bash scripts/docker_smoke_test.sh`. Readiness: `GET /readyz`→200.

## CI Gates

**Blocking:** `python -m ruff check .` and `python -m pytest -q`.

**Advisory:** pylint >=7.0, vulture >=80%.

## Schema

SCHEMA_VERSION 34, `_apply_v*_migrations`. `athlete_id='owner'` for the owner; new `athlete_id` columns have no DEFAULT (ADR-0067).

## Phases 19–26 (CLOSED)

Phase-close notes for Phases 19–26: [`archive/claude_md_phase_history.md`](archive/claude_md_phase_history.md).
The refactor plan from 2026-10-07 on is tracked in `PROGRESS.md`; decisions in `DECISIONS.md`.

## Phase 27 OPEN (ACTIVE, 2026-06-07) — B1–B7 blocker-clear complete 2026-06-09; B-1 coach RBAC subsequently found open by static audit (SA:C-1); hardening track opened 2026-06-12 (CONTRACT 7.9)

1. Cohort calibration analytics: cross-athlete threshold delta distributions; population heuristics vs. individual outliers
2. `CohortProfile` — aggregated population-level calibration signal (HEURISTIC → MODERATE when ≥ 3 athletes confirm same delta)
3. Proactive load modulation (advisory first); H1–H5 write guard remains DB-enforced (ADR-0052)

## Pitfalls

1. **DB path**: Pass `db=` arg. Never call `DatabaseManager()` inside pipeline.
2. **Column**: `training_load` (not `trimp`) in `training_log`.
3. **`get_training_load_history()`**: `CTL_DECAY_DAYS` window (42 days) by default. CTL/ATL/TSB
   callers pass `LOAD_HISTORY_DAYS` (210 days, `tsb_engine.py`); the kernel fills rest days with 0 (D-051).
4. **`parse_hr()` locale**: `round(float(str(s).replace(",", ".")))`.
5. **Telegram 409**: Two bots—kill python, restart.
6. **`db_name='titan_core.db'`**: Never use `titan.db` — stale file.
