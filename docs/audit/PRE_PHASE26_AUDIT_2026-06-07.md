# TITAN OS — PRE-PHASE-26 GOVERNANCE & SAFETY AUDIT

**Auditor mode:** TITAN AUDITOR v7.8 · **Date:** 2026-06-07 · **Target:** `zafirisska/project-mayhem` @ SCHEMA_VERSION 23
**Scope:** P15-ARCH5 migration · TitanSettings security · Phase 26 entry prerequisites · CI surface post-ADR-0059
**Method:** static read of 16 mandatory sites + 2 governance grep sweeps; no code mutated (read-only pre-phase audit).

Severity legend: 🔴 CRITICAL (blocks) · 🟠 HIGH · 🟡 MEDIUM · 🔵 LOW · ⚪ INFO/positive

---

## AREA 1 — P15-ARCH5 Migration Completeness

**Settings inventory:** 16 vars declared in `TitanSettings`. Cross-referencing `get_settings()` consumers vs. the `os.environ` sweep:
13 are consumed via the settings object; **3 are declared but have zero `get_settings()` consumers** — their only live reads remain raw `os.environ` in the explicitly-skipped files.

### 🟡 A1-F1 — Three declared settings are never sourced from the settings object
- **Question:** 1(a)
- **Observation:** `TITAN_DB_BACKEND`, `TITAN_POSTGRES_DSN`, `WEATHER_LOCATION` are declared in `TitanSettings` (settings.py:17,18,21) but consumed **only** via `os.environ` at their live sites. The declaration (canonical default) and the consumption (raw env) are disconnected — dual-sourced with two independent default literals.
- **Evidence:** `titan/core/persistence.py:130,134` · `titan/core/database.py:3344` · `titan/integrations/weather_api.py:114`. The `get_settings()` sweep shows **no** consumer for these three.
- **Default reconciliation (1c check):** `sqlite`==`sqlite`, `None`==`None`, `"Athens,GR"`==`"Athens,GR"` — all **match today**, so no behavioral conflict. Risk is drift: editing one default literal silently desyncs the canonical from the live value.
- **Governance trace:** P15-ARCH5 Step 3 ("composition roots wired; credential/safety-critical sites migrated"). These three are non-credential and were in the skipped set, so this is *incomplete migration*, not a regression.
- **Remediation:** Either route the skipped sites through `get_settings()`, or annotate in settings.py that these three are declaration-only (canonical-default registry) to stop the drift surface.

### 🟡 A1-F2 — `ATHLETE_MAX_HR` default divergence (160 vs 191) across entry paths
- **Question:** 1(a)/1(c) — *the headline migration finding*
- **Observation:** The same env var `ATHLETE_MAX_HR`, when **unset**, resolves to two different defaults:
  - **160** via the worker — `int(str(get_settings().ATHLETE_MAX_HR))` (worker/__init__.py:99), TitanSettings default `160` (settings.py:19)
  - **191** via the interactive launcher — `UniversalAthleteProfile.from_env()` parses `ATHLETE_MAX_HR` with default `_defaults.max_hr`, and the class default is `self.max_hr = 191` (athlete.py:67, used at athlete.py:364)
- **Risk:** `athlete_max_hr` is the **zone-boundary ceiling for Edwards TRIMP** (garmin_sync.py:587). A lower ceiling compresses HR-reserve zones and **inflates** training load → divergent CTL/ATL/TSB → divergent governance decisions for the *same athlete* depending on which entry path computed the load. The worker (160) is precisely the runtime Phase 26 activates as the production multi-athlete host.
- **Evidence:** `titan/config/settings.py:19` (=160) vs `titan/core/athlete.py:67` (=191) → `athlete.py:364`; consumed at `worker/__init__.py:99-102` → `GarminSync.athlete_max_hr`.
- **Governance trace:** ADR-0016 (multi-sport adapter) HRmax provenance; Pitfall #2 (DB path) class of "two sources of truth." Intersects Phase 26 scope item 2 (per-athlete isolation) — a *single global* `ATHLETE_MAX_HR` cannot serve N athletes with distinct physiological HRmax, so this default must be resolved per-athlete, not globally, during Phase 26.
- **Remediation:** Pick one canonical default; in the per-athlete refactor, source HRmax from each athlete's profile row, not a global env var.

### 🟡 A1-F3 — `get_settings()` executes at **module import time** (two sites)
- **Question:** 1(d)
- **Observation:** Module-level constants call `get_settings()` at import:
  - `titan/integrations/garmin_sync.py:51` — `_DATA_DIR = Path(get_settings().TITAN_DATA_DIR)`
  - `titan/worker/__init__.py:26` — `LOCK_FILE = Path(get_settings().TITAN_DATA_DIR) / "worker.lock"`
- **Does it block loading?** Under default/sqlite, **no** — all fields have defaults and `TitanSettings()` succeeds. **But** with `TITAN_DB_BACKEND=postgres` and no `TITAN_POSTGRES_DSN`, the `@model_validator` (settings.py:29) raises `ValidationError` **at import of `garmin_sync`** — a very widely-imported module — converting a config error into a cryptic import-time crash rather than a controlled startup failure (contrast `validate_jwt_keys_at_startup`).
- **Secondary:** These module constants are frozen at first import; the conftest autouse `cache_clear` (2d) **cannot** rebind them, so tests that `monkeypatch` `TITAN_DATA_DIR` won't see `_DATA_DIR`/`_GARTH_TOKEN_PATH`/`LOCK_FILE` change — a test-isolation footgun that escapes the P15-ARCH5 fixture.
- **Governance trace:** P15-ARCH5 "lru_cache test isolation (autouse cache_clear)"; ADR-0030 (external resilience — fail at a controlled gate, not at import).
- **Remediation:** Make `_DATA_DIR`/`LOCK_FILE` lazy (compute inside functions) so they re-read per call and respect cache_clear.

### 🔵 A1-F4 — `TITAN_DATA_DIR` (/data) not enforced at the `database.py` default site
- **Question:** 1(e)
- **Observation:** The canonical `/data` default is honored at **2 of 3** roots by explicit pass-through: `worker/__init__.py:149` and `scripts/run_api.py:14`. The **third** site — `DatabaseManager`'s own default `db_dir` — does **not** read `TITAN_DATA_DIR`; it resolves via `launcher.validator.get_data_directory()` → `~/Documents/TITAN` (validator.py:31-43), with a `~/Documents/TITAN` fallback (database.py:190-197). So `DatabaseManager()` with no `db_dir` (e.g. `main.py:416`) writes outside `/data`.
- **Risk:** Low for Phase 26 — the Docker production roots (worker/api) pass `/data` explicitly; only the interactive/local launcher diverges (documented dev behavior, Pitfall #1/#6).
- **Governance trace:** ADR-0057 (Docker deployment, `titan-data`→`/data`); ADR-0015 (SQLite retention).
- **Remediation:** Optional — have `database.py` consult `get_settings().TITAN_DATA_DIR` as its default base_dir for a true single source of truth.

### 🔵 A1-F5 — `TITAN_GARTH_TOKEN_KEY` (safety-critical Fernet key) remains a raw `os.environ` read
- **Question:** 1(b) — garmin_sync.py
- **Observation:** garmin_sync.py is otherwise fully migrated (GARMIN_EMAIL/PASSWORD/TITAN_ENV/GARMIN_SYNC_TIMEOUT_S/TITAN_DATA_DIR via `get_settings()`). The **one** remaining site is `os.environ.get(_TITAN_TOKEN_KEY_ENV)` (garmin_sync.py:61) for `TITAN_GARTH_TOKEN_KEY` — a token-encryption key. It is **not** among the 16 TitanSettings vars, so by the fixed-16 scope it's intentional, but it is a *credential/safety-critical* value (the class P15-ARCH5 Step 3 targets) read outside the typed/SecretStr surface.
- **Mitigation present:** dev/prod guard is correct — refuses to store unencrypted in production (garmin_sync.py:88-92).
- **Governance trace:** ADR-0050 (Garmin mitigation), TD-18 (token encryption).
- **Remediation:** Consider promoting to `TitanSettings` as `SecretStr` for parity with the other credentials.

### ⚪ A1-F6 — `main.py:_parse_env_number` is unused in production
- **Observation:** Defined at main.py:363, exercised only by tests; `main()` builds the profile via `UniversalAthleteProfile.from_env()` (its own `_parse`). Dead-ish duplicate.
- **Remediation:** Remove or wire; cosmetic.

**In-scope files confirmed COMPLETE:** `titan/api/auth.py` (JWT keys via settings, no os.getenv), `titan/science/ml_safety.py` (kill-switch via settings), `titan/integrations/telegram_bot.py` (token+chat_id via settings). `titan/main.py` in-scope vars (`TITAN_LOG_PATH`, `TITAN_ENABLE_API` via `__main__.py:18`) migrated.

---

## AREA 2 — TitanSettings Security Surface

### ⚪ A2-F1 — JWT key declarations are **stronger** than the ADR spec (positive deviation)
- **Question:** 2(a)
- **Observation:** ADR spec said both keys `str`. Actual: `TITAN_JWT_PRIVATE_KEY: SecretStr` (settings.py:15) — **more secure**; `TITAN_JWT_PUBLIC_KEY: str` (settings.py:16) — appropriate (public keys aren't secret). Consumed correctly: `get_settings().TITAN_JWT_PRIVATE_KEY.get_secret_value()` (auth.py:140), public read plainly (auth.py:147).
- **Log-leak guard:** The sweep found **zero `model_dump()` calls** anywhere in the repo, and the private key is `SecretStr` (auto-redacts to `'**********'`) — so no settings-to-log exposure path exists. **No guard needed.**
- **Governance trace:** ADR-0048 (API auth). *Action:* update the ADR text to match impl (str→SecretStr) so spec and code agree.

### 🟡 A2-F2 — `_postgres_dsn_required` validator is **untested** and **bypassed** on the live path
- **Question:** 2(c)
- **Observation:** The `@model_validator` (settings.py:27-31) rejects `postgres` backend without DSN. But the **actual** backend-selection path reads raw env and never constructs `TitanSettings`: `persistence.py:130,134` and `database.py:3344`. `persistence.py:135-136` carries its **own** duplicate guard (`raise ValueError` if no DSN), so the *safety outcome* is preserved by defense-in-depth — but the canonical validator is **not** the enforcement point.
- **Test coverage:** The only tests importing `config.settings` (`test_td01_td03_td05.py`, `test_garmin_sync.py`) use just `get_settings.cache_clear()`. No test constructs `TitanSettings()` with postgres / exercises the validator. **Validator is unverified.**
- **Cross-ref:** The validator's only *incidental* live trigger is the import-time path in A1-F3.
- **Governance trace:** ADR-0044 (PostgreSQL gate), ADR-0020 (persistence policy).
- **Remediation:** Add a direct test of the validator (postgres+no-DSN → raises; postgres+DSN → ok), and decide whether the backend selector should go through `get_settings()` to make the validator authoritative.

### STATUS: 2(b) SecretStr credentials — CLEAN
`GARMIN_EMAIL`/`GARMIN_PASSWORD`/`TELEGRAM_BOT_TOKEN` declared `SecretStr` (settings.py:11-13); `get_secret_value()` sites correct (garmin_sync.py:297-298; telegram_bot.py:122). No plaintext leakage.

### STATUS: 2(d) lru_cache + autouse cache_clear — CLEAN (with A1-F3 caveat)
`get_settings()` is `lru_cache(maxsize=1)` (settings.py:34); the **root** `conftest.py:10-28` autouse fixture clears it before and after every test and is therefore visible to all 199 test files. Correct. Caveat: module-level `get_settings()` constants (A1-F3) capture a value before the fixture can act.

---

## AREA 3 — Phase 26 Entry Prerequisites

### ⚪ A3-F1 — CoachingScheduler not instantiated in production (expected)
- **Question:** 3(a)
- **Observation:** `CoachingScheduler(` appears **only** in `tests/titan/orchestration/test_coaching_scheduler.py`. No production composition root instantiates it. Matches CLAUDE.md "F4.1 — unwired since Phase 19."
- **Activation path:** wire into the worker composition root (`worker/__init__.py`), registering one per-athlete callback via `register_athlete()`. Note: `_run_athlete_cycle` uses `lock.acquire(blocking=False)` and silently **skips** an athlete whose prior cycle is still running (coaching_scheduler.py:43-44) — intended overlap protection, but should be surfaced as a metric when activated.
- **Governance trace:** Phase 26 scope item 1.

### ⚪ A3-F2 — `EngineRegistry.from_db` still stateless; TODO-Phase9 markers present (expected)
- **Question:** 3(b)
- **Observation:** `from_db(db, athlete_id="owner")` accepts both args but constructs all 10 engines via bare constructors (engine_registry.py:72-83). Hydration is still the separate `DailyCoach._hydrate_engines_from_db()` (daily_coach.py:399). **TODO-Phase9 markers confirmed present** at engine_registry.py:57 and :68.
- **Governance trace:** ADR-0058 Phase A; TD-08 → Phase 9 scope. This is the Phase 26 work item, not a defect.

### 🟡 A3-F3 — Phase 9 corpus gate is documented but **not measurable**
- **Question:** 3(c)
- **Observation:** Condition is documented consistently — `≥3 athlete profiles × ≥90 paired decisions each` (ROADMAP.MD:27, :106, :124). However, **no automated counter/gate** exists: the sweep for corpus/paired-decision counting in `titan/` found only the `governance_outcomes` table DDL (database.py), no code that computes corpus size or gates Phase 9/26 entry on it.
- **Risk:** The prerequisite cannot be *verified* — entry would rest on a manual claim. Phase 26 scope item 3 ("corpus gate prerequisite") should deliver the measurement, not assume it.
- **Governance trace:** ADR-0014 (shadow/advisory; "≥30 paired decisions per phase" precedent), ADR-0046 (multi-athlete model).
- **Remediation:** Add a measurable gate (e.g., a query/test asserting `COUNT(DISTINCT athlete_id) ≥ 3` and per-athlete paired-outcome `≥ 90` in `governance_outcomes`).

### 🔵 A3-F4 — B2c fallback still present in code despite "removed" status
- **Question:** 3(d)
- **Observation:** The `else:` fallback that constructs `EngineRegistry` from individual engine params **remains** at daily_coach.py:365-378, with inline TODO "Fallback path … (Phase 25: remove)." But CLAUDE.md states "**Phase 25 CLOSED … B2c fallback removed.**" → **doc/code drift.**
- **Production reality:** Truly **test-only by invocation** — both production roots take the pure-consumer path (`engines is not None`): worker/__init__.py:105-123 (omits individual params) and main.py:460-473 (passes `engines=_engine_reg`; the redundant individual params are ignored). Only `engines=None` test factories hit the fallback.
- **Risk:** None functional; inert in production. It's stale debt + an inaccurate close-note.
- **Governance trace:** ADR-0058 Phase A/B (B2c).
- **Remediation:** Either delete the else-branch in Phase 26 (and the redundant main.py params) or correct the CLAUDE.md close-note to "removed from production paths; test-only shim retained."

### ⚪ A3-F5 — TD-08-R1 (PG adapter DDL divergence) does **not** affect Phase 26
- **Question:** 3(d)
- **Observation:** TD-08-R1 is PostgreSQL-adapter DDL divergence (ROADMAP.MD:323, V7-01). Phase 26 runs on SQLite single-athlete (`athlete_id='owner'`, SCHEMA_VERSION 23). PG is gated separately (ADR-0044). **No block.** (It does share the PG-path concern surfaced in A2-F2, also out of Phase 26 scope.)

### 🔵 A3-F6 — F5: AGENTS.md references deleted `constraints.txt` (governance-locked, deferred)
- **Question:** 3(d)
- **Observation:** `AGENTS.md:489` instructs `pip install -r requirements.txt -c constraints.txt` inside a **"Respond verbatim"** remediation block, but `constraints.txt` was deleted under TD-NEW-05 — the command errors on a clean clone. Logged as CI_SURFACE_AUDIT_2026-06-06 **F5 (MED), "⚠ Deferred (governance-locked)"** because AGENTS.md is DO-NOT-EDIT-without-ADR.
- **Risk to Phase 26:** **None functional** — the canonical bootstrap (`ci_bootstrap.sh` → `requirements.txt` + `requirements-dev.txt`, no `-c`) and the SessionStart hook bypass AGENTS.md entirely. It is a stale governance-doc instruction.
- **Governance trace:** F5; TD-NEW-05; ADR-0059. **Remediation:** ADR addendum to drop `-c constraints.txt` and name `ci_bootstrap.sh` as the single bootstrap (the deferred R1 action).

---

## AREA 4 — CI Surface Post-ADR-0059 — STATUS: CLEAN

- **4(a) ✅** `scripts/titan_ci.sh` uses interpreter-explicit invocation throughout: `"$PY" -m ruff check .` (line 71), `"$PY" -m pytest …` (lines 84,90,93,96,99). No bare `pytest`/`ruff`. Interpreter resolves venv → repo `.venv` → system (lines 19-29). Conforms to ADR-0059.
- **4(b) ✅** `.claude/hooks/session-start.sh` **exists** and bootstraps `.venv` via `scripts/ci_bootstrap.sh`, then persists it to PATH via `CLAUDE_ENV_FILE` (gated on `CLAUDE_CODE_REMOTE=true`). **Verified live this session** — the startup banner shows clean bootstrap + `ruff 0.15.13` / `pytest 9.0.3` resolving. Addresses CI_SURFACE_AUDIT_2026-06-06 F1.
- **4(c) ✅** Dependency preflight (titan_ci.sh:38-44) probes the real gate closure (`pytest, pytest_cov, freezegun, hypothesis, sqlalchemy, fastapi` + `ruff --version`) and emits actionable remediation ("Bootstrap first: bash scripts/ci_bootstrap.sh") instead of a cryptic mid-gate `ImportError` / pytest exit-4.
- **4(d) ✅** Gate set is explicitly **documented as a pre-flight subset**, not ci.yml parity (titan_ci.sh:74-83: "curated subset … remote workflow remains the authoritative merge gate"). This is the documented resolution of the F6 gate-divergence concern.

---

## GOVERNANCE TRACE SUMMARY

| ID | Sev | Area | Phase 26 impact | Governance ref |
|----|-----|------|-----------------|----------------|
| A1-F1 | 🟡 | 1a | Drift surface, no behavior change | P15-ARCH5 Step 3 |
| A1-F2 | 🟡 | 1a/1c | Per-athlete HRmax must be resolved in-scope | ADR-0016 |
| A1-F3 | 🟡 | 1d | Import-time crash iff postgres-misconfigured; test-isolation gap | ADR-0030 / P15-ARCH5 |
| A1-F4 | 🔵 | 1e | None (prod roots explicit) | ADR-0057 |
| A1-F5 | 🔵 | 1b | None (guard correct) | ADR-0050 / TD-18 |
| A2-F1 | ⚪ | 2a | Positive (SecretStr > spec) | ADR-0048 |
| A2-F2 | 🟡 | 2c | None (PG out of scope); test gap | ADR-0044 |
| A3-F3 | 🟡 | 3c | Prerequisite not verifiable until instrumented | ADR-0014/0046 |
| A3-F4 | 🔵 | 3d | None (inert); doc drift | ADR-0058 |
| A3-F6 | 🔵 | 3d | None (canonical bootstrap unaffected) | F5 / TD-NEW-05 |
| A3-F1/F2/F5 | ⚪ | 3a/3b/3d | Expected pre-Phase-26 state | Phase 26 scope / ADR-0058 |

**No 🔴/🟠 findings.** Areas with the most weight (A1-F2 ATHLETE_MAX_HR, A3-F3 corpus measurability) are *Phase 26 design items*, not preconditions to starting.

---

## VERDICT

### ✅ **VERDICT: GO — Phase 26 safe to proceed**

The system is in the **expected** pre-Phase-26 state: CoachingScheduler unwired (A3-F1), `EngineRegistry.from_db` stateless with TODO-Phase9 markers intact (A3-F2), CI surface fully conformant to ADR-0059 (Area 4 CLEAN), and credentials correctly `SecretStr`-typed with no log-leak path (A2-F1, 2b/2d CLEAN). No blocker (🔴/🟠) was found.

**Conditions to fold into the Phase 26 work plan (not gates to entry):**

1. **[A1-F2 / Phase 26 item 2]** Resolve the `ATHLETE_MAX_HR` 160↔191 default divergence *as part of* per-athlete isolation — source HRmax per athlete, retire the global env default. This is the one finding that directly intersects Phase 26 correctness.
2. **[A3-F3 / Phase 26 item 3]** Deliver a **measurable** corpus gate (`COUNT(DISTINCT athlete_id) ≥ 3` ∧ per-athlete paired `governance_outcomes ≥ 90`) — today the prerequisite is documented but unverifiable.
3. **[A1-F3]** Make the module-level `get_settings()` constants in `garmin_sync.py:51` / `worker/__init__.py:26` lazy before relying on multi-athlete worker imports under a postgres config.
4. **[A2-F2]** Add a direct test for `_postgres_dsn_required`; decide whether the backend selector should flow through `get_settings()`.
5. **[A3-F4 + CLAUDE.md]** Reconcile the "B2c fallback removed" close-note with the still-present test-only else-branch.
6. **[A3-F6 / F5]** Land the deferred ADR addendum fixing `AGENTS.md:489` (governance-locked; does not block).

All six are MEDIUM-or-lower and most are explicitly *within* Phase 26's declared scope. Proceed.
