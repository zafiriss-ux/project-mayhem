# Repository Audit — 2026-03-01

Requested scope: full-project scan for errors and weak points.

## What I ran

```bash
pytest -q
python -m compileall -q .
ruff check . --statistics
```

## Results summary

- ✅ **Runtime tests**: `275 passed`.
- ✅ **Syntax compile check**: no syntax/import-time compile failures.
- ❌ **Static analysis (ruff)**: `203` findings across `28` files.

### Ruff rule breakdown

- `71` × `E701` — multiple statements on one line (`if ...: do_something` style).
- `39` × `F401` — unused imports.
- `38` × `E722` — bare `except:` blocks.
- `27` × `F541` — f-strings with no placeholders.
- `19` × `F841` — assigned but unused variables.
- `4` × `E402` — imports not at top of file.
- `3` × `E741` — ambiguous variable names.
- `1` × `F811` — redefinition while unused.
- `1` × `E401` — multiple imports on one line.

## Highest-impact files (by issue count)

1. `TITAN_v50_FULL_KERNEL_FINAL.py` — **101** findings.
2. `titan/science/readiness_engine.py` — **15** findings.
3. `titan/science/acwr_engine.py` — **13** findings.
4. `titan/ui/menu_system.py` — **10** findings.
5. `titan/integrations/telegram_bot.py` — **8** findings.
6. `titan/science/tsb_engine.py` — **8** findings.
7. `system_check.py` — **7** findings.

## Concrete error examples

- `titan/integrations/weather_api.py` still contains TODO placeholders for real API integration and returns simulated data (`get_current_conditions`, `get_hourly_forecast`).
- `titan/science/*` and `TITAN_v50_FULL_KERNEL_FINAL.py` contain many one-line control statements and bare `except:` blocks, which reduce readability and can hide real failures.
- `titan/ui/menu_system.py` has several dead assignments and no-op f-strings, indicating cleanup debt.

## Prioritized remediation plan

1. **Stability-first:** Replace bare `except:` with explicit exceptions (`E722`) in core runtime paths.
2. **Readability/safety:** Split one-line compound statements (`E701`) in engine modules.
3. **Noise reduction:** Remove unused imports/variables (`F401`, `F841`) to make real warnings visible.
4. **Legacy containment:** Decide whether `TITAN_v50_FULL_KERNEL_FINAL.py` is production-critical; if not, isolate or exclude it from lint scope.
5. **Integrations:** Implement real weather API calls or mark module as simulation-only in docs/config.

