# TITAN OS — Repository Guide

## Quick Start

```bash
pip install -r requirements.txt
python launcher/main.py
```

## Tests

```bash
python3 -m pytest --no-cov -q
python3 -m pytest --no-cov -q -k "name"
```

**Historical snapshot:** 3023 tests all green

Update after every commit adding/removing tests:

```bash
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

Failure to update causes snapshot failures.

## Module Map

Main package (66 modules, excl. __init__/__main__), ceiling 73.

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
| `docs/ROADMAP.MD` | Phase 24 OPEN (ACTIVE, 2026-05-29) |
| `docs/SLO.md` | SLOs + runbooks |
| `titan/config/thresholds.py` | Safety threshold constants |
| `titan/core/database.py` | DatabaseManager, migrations |
| `titan/orchestration/daily_coach.py` | DailyCoach v5.8 |

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

## Docker

See `docs/runbooks/docker-deploy.md` (ADR-0057).

```bash
docker compose up --build -d
```

`titan-api` :8000 + `titan-worker`; `titan-data`→`/data/titan_core.db`.
Smoke: `bash scripts/docker_smoke_test.sh`. Readiness: `GET /readyz`→200.

## CI Gates

**Blocking:** `ruff check .` and `python3 -m pytest -q`.

**Advisory:** pylint >=7.0, vulture >=80%.

## Schema

SCHEMA_VERSION 23, `_apply_v*_migrations`. `athlete_id='owner'` (single-athlete).

## Phase 19 CLOSED (2026-05-24)

phase_close_audit.sh 19 exit 0; 2942 tests passing; TD-NEW-15 RESOLVED; TD-04 RESOLVED;
TD-NEW-10 RESOLVED; TD-08 DEFERRED Phase 20; TD-NEW-18 DEFERRED Phase 20.

## Phase 20 CLOSED (2026-05-24)

phase_close_audit.sh 20 exit 0; 2955 tests passing; FMEA G12 SATISFIED;
TD-08 DEFERRED Phase 21; TD-NEW-18 DEFERRED Phase 21; TD-04 Phase B DEFERRED Phase 21.

## Phase 21 CLOSED (2026-05-24)

phase_close_audit.sh 21 exit 0; 2959 tests passing; governance consolidation complete;
TECHNICAL_DEBT.md archived to <1500 LOC; SCRATCHPAD.md archived to 916 LOC;
TD-08 DEFERRED Phase 22; TD-NEW-18 DEFERRED Phase 22; TD-04B DEFERRED Phase 22; T5-15 DEFERRED Phase 22.

## Phase 22 CLOSED (2026-05-25)

phase_close_audit.sh 22 exit 0; 2975 tests passing; FMEA G12 SATISFIED;
TD-08 DEFERRED Phase 23; TD-04B DEFERRED Phase 23; T5-15 Phase B DEFERRED Phase 23;
P15-ARCH5 DEFERRED Phase 23; TD-CI-SELFHOSTED DEFERRED Phase 23.

## Phase 23 CLOSED (2026-05-29)

phase_close_audit.sh 23 exit 0; 2974 tests passing; 7 skipped; ADR-0058 construction-site
violation caught and fixed; TD-08/TD-04B/T5-15B/P15-ARCH5/TD-CI-SELFHOSTED DEFERRED Phase 24.

## Phase 24 OPEN (ACTIVE, 2026-05-29)

1. TD-08: Schema single source of truth — extract CREATE TABLE into titan/core/schema.py (XL) — requires Opus pre-audit
2. TD-04B: EffectBus extraction (ADR-0058 Phase B) — 27-file blast radius, needs ADR amendment
3. T5-15 Phase B: Retroactive pytest markers (100+ remaining files, mechanical)
4. P15-ARCH5: pydantic-settings migration
5. TD-CI-SELFHOSTED: Alembic runner topology — pending runner inventory docs

## Pitfalls

1. **DB path**: Pass `db=` arg. Never call `DatabaseManager()` inside pipeline.
2. **Column**: `training_load` (not `trimp`) in `training_log`.
3. **`get_training_load_history()`**: `CTL_DECAY_DAYS` window (42 days).
4. **`parse_hr()` locale**: `round(float(str(s).replace(",", ".")))`.
5. **Telegram 409**: Two bots—kill python, restart.
6. **`db_name='titan_core.db'`**: Never use `titan.db` — stale file.
