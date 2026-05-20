# TITAN OS — Repository Guide

## Quick Start

```bash
pip install -r requirements.txt
python launcher/main.py
```

## Running Tests

```bash
# Full suite (canonical)
python3 -m pytest --no-cov -q

# Single test or pattern
python3 -m pytest --no-cov -q -k "name"
```

## Test Count Snapshot

**Historical snapshot:** 2860 tests all green

Update this number after every commit that adds or removes tests:

```bash
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

Failure to update causes snapshot test failures that waste CI time.

## Module Map

Main package (63 modules, excl. __init__/__main__)

```
titan/
  core/          DB, athlete profile, persistence, periodization
  science/       TSB, TRIMP, HRV, governance engine, physiological bounds,
                 adaptive priority lock, ML safety, data trust
  orchestration/ DailyCoach (main pipeline), coaching pipeline, contracts
  integrations/  Garmin sync, Telegram bot, weather API, biometric router
  ui/            Menu system, data browser, setup wizard
  api/           FastAPI routes, auth, models
  config/        Thresholds, constants
  features/      Nutrition optimizer, equipment manager
launcher/        Entry point, validator, errors, paths
scripts/         import_garmin_csv.py, import_activity_laps.py
system_check.py  Pre-flight validation
```

## Key Files for Reference

| File | Purpose |
|------|---------|
| `AGENTS.md` | Governance rules (DO NOT EDIT without ADR) |
| `TECHNICAL_DEBT.md` | Open debt items |
| `docs/ROADMAP.MD` | Development workflow roadmap; Phase 17 OPEN (ACTIVE, 2026-05-15) |
| `docs/SLO.md` | SLOs + runbooks |
| `titan/config/thresholds.py` | Safety threshold constants (single source of truth) |
| `titan/core/database.py` | DatabaseManager — SQLite backend, migrations |
| `titan/orchestration/daily_coach.py` | DailyCoach v5.8 — 12-step morning pipeline |

### Architecture Decision Records (`docs/adr/`)

- `0006` — Architectural hardening: cold start and engine sync
- `0007` — Intensity governance architecture audit
- `0008` — Adaptive Priority Lock and VLG specs
- `0009` — Safety gate hardening: C1 & C2 resolution
- `0010` — Operator Console: Readiness Dashboard MVP payload
- `0011` — Operator Console: Session Explorer payload
- `0012` — Operator Console: Manual Override Workflow
- `0013` — Operator Console: Technology path
- `0014` — Phase 7 ML scaffold: shadow/advisory mode
- `0015` — SQLite retention strategy and Phase 8 data lifecycle gate
- `0016` — Phase 8 multi-sport scope and unified adapter gate
- `0017` — Composition root fan-in and DailyCoach god-orchestrator audit
- `0018` — Kernel Boundary: Decision Pipeline / Effect Runner Split
- `0019` — Skipped — number reserved
- `0020` — Persistence Failure Behavioral Policy
- `0021` — Skipped — number reserved
- `0022` — Phase 8 Entry Gate Review and Architect Sign-off
- `0023` — Physiological Input Validation Contract
- `0024` — Canonical Lock Codes
- `0025` — Skipped — number reserved
- `0026` — Input Data Sanity Layer
- `0027` — Hidden Inter-Module Coupling Prevention
- `0028` — Skipped — number reserved
- `0029` — Skipped — number reserved
- `0030` — External Data Source Resilience
- `0031` — Skipped — number reserved
- `0032` — ML Advisory Explainability Protocol
- `0033` — Physiological Model Aging and Multi-Athlete Architecture Protocol
- `0034` — Environmental Stress Compensation for Training Zones
- `0035` — Skipped — number reserved
- `0036` — Skipped — number reserved
- `0037` — Non-Training Stress Safety Partition
- `0038` — Governance Decision Rationale Protocol
- `0039` — Skipped — number reserved
- `0040` — Athlete Identity Isolation
- `0041` — Unified External Data Trust Contract
- `0042` — Human Override as First-Class Invariant
- `0043` — Skipped — number reserved
- `0044` — PostgreSQL migration as Phase 8A entry gate
- `0045` — Local LLM backend abstraction
- `0046` — DailyCoach multi-athlete execution model
- `0047` — Architecture Fitness Functions
- `0048` — API Authentication detailed spec
- `0049` — Opus QA Scope Reduction
- `0050` — Garmin API Fragility Mitigation
- `0051` — Missing Data Policy (Conservative-Fail)
- `0052` — Population-Specific Threshold Adaptation via OutcomeTracker
- `0053` — Data-Void Conservative Governance Gate
- `0054` — Coach-Athlete RBAC Scoping
- `0055` — Garmin Fallback Adapter Interface

## CI Gates

**Blocking (must pass before any commit):**

```bash
ruff check .
python3 -m pytest -q
```

**Advisory (non-blocking):**
- pylint (threshold 7.0)
- vulture (min-confidence 80)

## Schema

Current SCHEMA_VERSION 18

Migrations: `titan/core/database.py` (`_apply_v*_migrations` methods).
`athlete_id` must always be `'owner'` for single-athlete deployments.

## Known Pitfalls

1. **Wrong DB path**: `DatabaseManager()` with no args uses `~/Documents/TITAN/`. Always
   pass the injected `db=` argument. Never call `DatabaseManager()` inside the pipeline.
2. **Column name**: `training_load` (not `trimp`) in `training_log`.
3. **`get_training_load_history()` default window**: 400 days (after PR #702, `CTL_DECAY_DAYS`).
4. **`parse_hr()` locale safety**: uses `int(float(s))` for locale-formatted decimals.
5. **Telegram 409 error**: two bot instances running simultaneously. Kill all python
   processes and restart.
