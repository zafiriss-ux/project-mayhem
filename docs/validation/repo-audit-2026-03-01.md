# Repository Audit — 2026-03-01

Requested scope: full-project scan for errors and weak points.

## What I ran

```bash
pytest -q
python -m compileall -q .
ruff check . --statistics
ruff check . --fix
ruff check . --statistics
```

## Results summary

- ✅ **Runtime tests**: `275 passed`.
- ✅ **Syntax compile check**: no syntax/import-time compile failures.
- ⚠️ **Static analysis (ruff) before fixes**: `203` findings across `28` files.
- ✅ **Auto-fix pass** (`ruff --fix`): `63` findings fixed automatically.
- ⚠️ **Static analysis (ruff) after fixes**: `138` findings remain.

## Delta after auto-fix

- Findings reduced from `203` → `138` (**-65**, ~32% reduction).
- Most low-risk cleanup is now done (unused imports, no-op f-strings, minor dead code).

### Rule breakdown after fixes

- `71` × `E701` — multiple statements on one line (`if ...: do_something` style).
- `38` × `E722` — bare `except:` blocks.
- `19` × `F841` — assigned but unused variables.
- `5` × `F401` — unused imports.
- `3` × `E741` — ambiguous variable names.
- `2` × `E402` — imports not at top of file.

## Highest-impact remaining files (by issue count)

1. `TITAN_v50_FULL_KERNEL_FINAL.py` — highest concentration of remaining style and exception-handling debt.
2. `titan/science/readiness_engine.py` — multiple inline statements (`E701`).
3. `titan/science/acwr_engine.py` — inline statements + exception hygiene.
4. `titan/science/tsb_engine.py` — inline decision branches (`E701`).
5. `titan/ui/menu_system.py` — remaining unused variables.

## Concrete remaining error examples

- `titan/integrations/weather_api.py` still contains TODO placeholders for real API integration and returns simulated data (`get_current_conditions`, `get_hourly_forecast`).
- `titan/science/*` and `TITAN_v50_FULL_KERNEL_FINAL.py` still contain many one-line control statements and bare `except:` blocks, which reduce readability and can hide failures.

## Prioritized remediation plan (remaining work)

1. **Stability-first:** Replace bare `except:` with explicit exceptions (`E722`) in core runtime paths.
2. **Readability/safety:** Split one-line compound statements (`E701`) in engine modules.
3. **Finalize cleanup:** Remove remaining unused vars/imports (`F841`, `F401`).
4. **Legacy containment:** Decide whether `TITAN_v50_FULL_KERNEL_FINAL.py` is production-critical; if not, isolate or exclude it from lint scope.
5. **Integrations:** Implement real weather API calls or explicitly mark module as simulation-only.

---

## Refresh scan — 2026-03-01 (follow-up)

Re-ran the same checks to verify current state after merge/conflict handling.

### Commands re-run

```bash
pytest -q
python -m compileall -q .
ruff check . --statistics
```

### Follow-up results

- ✅ `pytest -q`: `275 passed`.
- ✅ `python -m compileall -q .`: no syntax/import-time failures.
- ⚠️ `ruff check . --statistics`: still `138` findings.

### Current highest-impact files (follow-up)

1. `TITAN_v50_FULL_KERNEL_FINAL.py` — 79 findings
2. `titan/science/readiness_engine.py` — 15 findings
3. `titan/science/acwr_engine.py` — 13 findings
4. `titan/science/tsb_engine.py` — 8 findings
5. `system_check.py` — 6 findings

### Concrete remaining examples (follow-up)

- `TITAN_v50_FULL_KERNEL_FINAL.py:111` — bare `except` (`E722`)
- `TITAN_v50_FULL_KERNEL_FINAL.py:101` — multiple statements on one line (`E701`)
- `launcher/errors.py:270` — assigned-but-unused variable (`F841`)
- `titan/core/database.py:396` — ambiguous variable name `l` (`E741`)
