# TITAN OS — Codebase Audit Report

**Date:** 2026-03-02
**Branch:** `claude/codebase-audit-MyVsC`
**Auditor:** Claude (automated)
**Scope:** Full codebase audit — dead code, imports, TODOs, duplicates, docs vs code, deps, tests, ADRs, config

---

## Executive Summary

| Category | Findings | Severity |
|---|---|---|
| Wrong Telegram library in requirements.txt | 1 critical | 🔴 P0 |
| Hardcoded magic numbers bypassing thresholds.py | 3 locations | 🟠 P1 |
| Duplicate ACWR constants (thresholds.py vs constants.py) | 2 constants | 🟠 P1 |
| `__init__.py` re-exports never used externally | ~40 imports | 🟡 P2 |
| CLAUDE.md module count wrong (49 claimed, 56 actual) | 1 | 🟡 P2 |
| Science module count wrong (23 claimed, 26 actual) | 4 undocumented | 🟡 P2 |
| Tests not listed in CLAUDE.md | 6 files | 🟡 P2 |
| Phase 7 completely absent from CLAUDE.md/ROADMAP | 1 phase | 🟡 P2 |
| `adaptive_priority_lock.py` mirrors thresholds with comment but doesn't import | 2 values | 🟠 P1 |
| `telebot.types` unused import | 1 | 🟢 P3 |
| `from __future__ import annotations` unused | 2 files | 🟢 P3 |
| `outcome_tracker.py`: `field` imported, unused | 1 | 🟢 P3 |
| `adaptive_priority_lock.py`: `Optional` imported, unused | 1 | 🟢 P3 |
| No TODO/FIXME found in codebase | ✅ Clean | — |
| pyproject.toml testpaths=["."] misses explicit tests/ | 🟡 minor | 🟡 P2 |

---

## 1. CRITICAL — Wrong Telegram Library (P0)

**File:** `requirements.txt:16`
**File:** `titan/integrations/telegram_bot.py:31`

```
# requirements.txt declares:
python-telegram-bot==21.0.1   # ← python-telegram-bot package

# But the code imports:
import telebot                # ← pyTelegramBotAPI package (DIFFERENT library!)
from telebot import types
```

`telebot` is the API of **pyTelegramBotAPI** (pip name: `pyTelegramBotAPI`).
`python-telegram-bot` is a completely different package with a different API (`telegram.*`).

**Impact:** The installed package (`python-telegram-bot`) cannot satisfy `import telebot`. The Telegram bot will fail to import on any fresh install.

**Fix:**
```diff
- python-telegram-bot==21.0.1
+ pyTelegramBotAPI==4.21.0
```

---

## 2. HIGH — Hardcoded Magic Numbers Bypassing `thresholds.py` (P1)

### 2a. `titan/science/volume_load_gauge.py:22`

```python
if tsb_value <= -50:   # ← should be HARD_STOP_TSB_FLOOR from thresholds.py
```

`volume_load_gauge.py` does **not** import from `titan.config.thresholds`. The value `-50.0` is hardcoded. If `HARD_STOP_TSB_FLOOR` is ever tuned, `VolumeLoadGauge` silently diverges.

**Fix:**
```python
from titan.config.thresholds import HARD_STOP_TSB_FLOOR
# ...
if tsb_value <= HARD_STOP_TSB_FLOOR:
```

### 2b. `titan/science/adaptive_priority_lock.py:31-32`

```python
_DEFAULT_THRESHOLDS = {
    'acwr_ceiling': 1.30,   # comment says: "VO2_ACWR_MAX from thresholds.py"
    'tsb_floor':   -50.0,   # comment says: "HARD_STOP_TSB_FLOOR from thresholds.py"
    ...
}
```

The comment acknowledges these mirror `thresholds.py` but the file does **not import** them. They will drift silently.

**Fix:**
```python
from titan.config.thresholds import HARD_STOP_TSB_FLOOR, VO2_ACWR_MAX

_DEFAULT_THRESHOLDS = {
    'acwr_ceiling': VO2_ACWR_MAX,
    'tsb_floor':    HARD_STOP_TSB_FLOOR,
    ...
}
```

---

## 3. HIGH — Duplicate ACWR Constants (P1)

Two separate constant definitions for the same values:

| Constant | File | Value |
|---|---|---|
| `VO2_ACWR_MIN` | `titan/config/thresholds.py:17` | 0.80 |
| `ACWR_SAFE_MIN` | `titan/utils/constants.py:74` | 0.8 |
| `VO2_ACWR_MAX` | `titan/config/thresholds.py:18` | 1.30 |
| `ACWR_SAFE_MAX` | `titan/utils/constants.py:75` | 1.3 |

`ACWR_SAFE_MIN/MAX` in `constants.py` are **defined but never imported** anywhere outside their own `__init__.py` re-export (which is itself unused). They are dead constants. `governance_engine.py` correctly uses `VO2_ACWR_MIN/MAX` from `thresholds.py`.

**Fix:** Remove `ACWR_SAFE_MIN`, `ACWR_SAFE_MAX` from `constants.py` (dead, duplicate).

Additionally, `volume_load_gauge.py:30-33` has its own inline ACWR thresholds (`0.7`, `0.8`, `1.3`, `1.5`) — these should also reference the canonical constants.

---

## 4. MEDIUM — `__init__.py` Re-exports Are Unused Public API (P2)

All `__init__.py` files expose re-exports that no code imports from the package level. The only consumer of `from titan.science import ...` is `system_check.py:74` (2 classes). All other production code imports directly from submodules.

### `titan/science/__init__.py` — 20+ re-exports, 2 used externally
### `titan/utils/__init__.py` — 30+ re-exports, 0 used externally
### `titan/core/__init__.py` — 4 re-exports, 0 used externally
### `titan/ui/__init__.py` — 1 re-export, 0 used externally

**Recommendation:** Either clean up `__init__.py` files to only expose genuinely public API, or document that these are intentional public API surface (add `__all__`). Currently they create maintenance overhead without benefit.

---

## 5. MEDIUM — Documentation Inconsistencies (P2)

### 5a. Module Count: CLAUDE.md claims 49 modules, actual is 56

```
CLAUDE.md: "└── titan/                   # Main package (49 modules)"
Actual:    56 .py files in titan/
           46 non-__init__/__main__ modules
```

### 5b. Science Module Count: CLAUDE.md claims 23, actual is 26

CLAUDE.md lists modules in 3 categories (11 foundational + 4 autonomic + 2 advanced + 6 governance = 23).
Actual science modules: **26** (3 extra). Missing from documentation:

| Module | Purpose |
|---|---|
| `titan/science/automated_periodization.py` | Phase 7 — AutomatedPeriodizationEngine |
| `titan/science/injury_risk_model.py` | Phase 7 — InjuryRiskEnsembleModel |
| `titan/science/load_prediction_shadow.py` | Phase 7 — LoadPredictionShadowModel |
| `titan/science/ml_safety.py` | Phase 7 — ML kill-switch |

**Root cause:** Phase 7 was implemented but CLAUDE.md was never updated.

### 5c. Phase 7 Completely Absent from CLAUDE.md and docs/ROADMAP.MD

`docs/ROADMAP.MD` says "Phases 0–6 CLOSED". Phase 7 modules exist (4 modules, 3 test files) but are not mentioned anywhere in CLAUDE.md architecture section, roadmap, or ADR index.

### 5d. Tests/ Directory: 6 test files not listed in CLAUDE.md

CLAUDE.md lists 15 test files in `tests/`. Actual count: **21 files**. Missing:

```
tests/test_automated_periodization.py
tests/test_injury_risk_model.py
tests/test_load_prediction_shadow.py
tests/test_ml_kill_switch.py
tests/test_phase7_hardening.py
tests/test_phase7_hygiene.py
```

### 5e. `docs/architecture/` contents mismatch

CLAUDE.md (`docs/architecture/`) lists `GOVERNANCE_PHILOSOPHY.md` and `EVALUATION_ORDER.md` — both exist ✅. No gap here.

### 5f. `docs/specs/` — undocumented spec files

CLAUDE.md lists `adaptive_priority_lock.md` and `volume_load_gauge.md`. Actual directory has 4 more:
```
operator_console_manual_override_workflow.md
operator_console_readiness_dashboard.md
operator_console_session_explorer.md
operator_console_technology_path.md
```
(These correspond to ADR 0010–0013, just not listed in CLAUDE.md.)

---

## 6. MEDIUM — `requirements.txt` / `pyproject.toml` Issues (P2)

### 6a. Wrong Telegram Package (see §1 — P0)

### 6b. `scikit-learn` and `pandas` — only in archived code

```
scikit-learn==1.4.2   # used only in archive/TITAN_v50_FULL_KERNEL_FINAL.py
pandas==2.2.1         # used only in archive/TITAN_v50_FULL_KERNEL_FINAL.py
```

Neither `sklearn` nor `pandas` are imported anywhere in `titan/` package. They are production dependencies for an archived monolith, not the current codebase.

### 6c. `pyinstaller` and `pywin32` — build-only tools in main requirements

```
pyinstaller==6.4.0     # build tool — should be in a [build] extras or separate file
pywin32==306           # Windows-only — platform-conditional already (sys_platform check)
```

These are not runtime dependencies. They bloat the install for Linux/macOS deployments.

### 6d. `pyyaml==6.0.1` — zero usage in `titan/`

```python
# grep result: no "import yaml" or "from yaml" in titan/
# Only reference: comment string in menu_system.py:593 mentioning "config.yaml"
```

PyYAML is declared as a production dependency but never imported.

### 6e. `pyproject.toml` — `testpaths = ["."]` works but is imprecise

```toml
testpaths = ["."]  # discovers all test_*.py recursively from root
```

Works correctly (pytest recurses into `tests/`), but explicit paths would be clearer:
```toml
testpaths = [".", "tests"]
```

### 6f. `pyproject.toml` — Ruff and Mypy configured but not in requirements.txt

`pyproject.toml` has full `[tool.ruff]` and `[tool.mypy]` configurations but neither `ruff` nor `mypy` appear in `requirements.txt`. They must be installed separately.

---

## 7. CONFIG INCONSISTENCIES — `thresholds.py` vs `evidence_registry.py` (P2)

### 7a. All `thresholds.py` constants have evidence entries ✅

All 9 constants in `thresholds.py` have corresponding entries in `evidence_registry.py`. The registry is complete.

### 7b. Value sync confirmed ✅

| Constant | thresholds.py | evidence_registry.py | Match |
|---|---|---|---|
| `HARD_STOP_HRV_DELTA` | 15.0 | 15.0 | ✅ |
| `HARD_STOP_RHR_DELTA` | 8.0 | 8.0 | ✅ |
| `HARD_STOP_TSB_FLOOR` | -50.0 | -50.0 | ✅ |
| `SUBJECTIVE_FATIGUE_EXTREME` | 8 | 8 | ✅ |
| `SUBJECTIVE_FATIGUE_2OF4` | 6 | 6 | ✅ |
| `VO2_ACWR_MIN` | 0.80 | 0.80 | ✅ |
| `VO2_ACWR_MAX` | 1.30 | 1.30 | ✅ |
| `VO2_READINESS_MIN` | 65.0 | 65.0 | ✅ |
| `VO2_GLYCOGEN_DEBT_MAX` | 7.0 | 7.0 | ✅ |
| `VO2_MIN_DAYS_SINCE_LAST` | 2 | 2 | ✅ |

### 7c. Constants missing from `thresholds.py` (hardcoded elsewhere)

Values that exist only as hardcoded literals, with no entry in `thresholds.py` or `evidence_registry.py`:

| Value | Location | Should be constant |
|---|---|---|
| `OVERRIDE_LOCKDOWN_THRESHOLD = 0.80` | `governance_engine.py:31` | Yes — override ratio threshold |
| `_acwr_color: 1.5, 0.7` | `volume_load_gauge.py:30-31` | Yes — VLG soft/hard ACWR bounds |
| `_tsb_color: -30` | `volume_load_gauge.py:24` | Yes — VLG TSB yellow threshold |
| `_glycogen_color: 4` | `volume_load_gauge.py:40` | Yes — VLG glycogen yellow threshold |
| `recall_target: float = 0.80` | `injury_risk_model.py:22` | Consider |
| `cs_min_confidence: 0.85` | `adaptive_priority_lock.py:265` | Consider |

---

## 8. ADR FILES vs IMPLEMENTATION (P2)

| ADR | Title | Status in code |
|---|---|---|
| 0001 | Fix typo in optimal time module reference | ✅ `optimal_time_calculator.py` exists |
| 0002 | Fix weather window duration bug | ✅ `weather_api.py` exists |
| 0003 | Align docs with module layout | ⚠️ Partially — Phase 7 still missing |
| 0004 | Improve weather window edge case tests | ✅ |
| 0005 | Fix runtime startup issues | ✅ |
| 0006 | Architectural hardening: cold start + engine sync | ✅ |
| 0007 | Intensity governance audit (read-only) | ✅ `intensity_governor.py` exists |
| 0008 | APL and VLG specs | ✅ Both implemented |
| 0009 | Safety gate hardening C1/C2 | ✅ OR semantics in `governance_engine.py` |
| 0010 | Operator Console: Readiness Dashboard | ✅ `operator_console.py` implemented |
| 0011 | Operator Console: Session Explorer | ✅ `operator_console.py` implemented |
| 0012 | Operator Console: Manual Override Workflow | ✅ `operator_console.py` implemented |
| 0013 | Operator Console: Technology path (Streamlit → React+FastAPI) | ⚠️ No FastAPI/React in codebase — decision accepted but not started |

**ADR 0013 gap:** The ADR was accepted for React+FastAPI migration of the Operator Console, but the current implementation is still Python-only (`operator_console.py`). This is expected for an "Accepted" (not "Implemented") ADR — but should be noted.

---

## 9. ORPHANED / UNDOCUMENTED TESTS (P3)

All test files correctly import from existing `titan.*` modules — no orphaned imports found.

Tests that exist but are **not documented** in CLAUDE.md (all Phase 7):
```
tests/test_automated_periodization.py  → titan.science.automated_periodization ✅
tests/test_injury_risk_model.py        → titan.science.injury_risk_model ✅
tests/test_load_prediction_shadow.py   → titan.science.load_prediction_shadow ✅
tests/test_ml_kill_switch.py           → titan.science.ml_safety ✅
tests/test_phase7_hardening.py         → version consistency + DailyCoach ✅
tests/test_phase7_hygiene.py           → Phase 7 branch coverage ✅
```

All 6 are valid tests for valid modules. They are **not orphaned** — they are simply undocumented because CLAUDE.md was not updated after Phase 7.

---

## 10. UNUSED IMPORTS — Genuine Issues (P3)

Excluding `__init__.py` re-exports (which are intentional public API surface, discussed in §4):

| File | Line | Import | Issue |
|---|---|---|---|
| `titan/integrations/telegram_bot.py` | 32 | `from telebot import types` | `types` never used in the file |
| `titan/config/evidence_registry.py` | 30 | `from __future__ import annotations` | Not needed (no PEP 563 forward refs used) |
| `titan/ui/operator_console.py` | 3 | `from __future__ import annotations` | Not needed |
| `titan/science/outcome_tracker.py` | 25 | `from dataclasses import field` | `field()` never used |
| `titan/science/adaptive_priority_lock.py` | 20 | `from typing import Optional` | `Optional` never used |

---

## 11. DUPLICATE CODE (P3)

### `PeriodizationManager` (core) vs `AutomatedPeriodizationEngine` (science)

- `titan/core/periodization.py` — `PeriodizationManager`: race goal tracking, phase calculation, manual periodization management
- `titan/science/automated_periodization.py` — `AutomatedPeriodizationEngine`: Phase 7 ML-backed suggestion engine (suggest-only)

These serve different purposes and are **not duplicates** — the core manager handles data state; the science engine generates advisory suggestions. However, the naming (`Periodization*` in both packages) could confuse future developers.

### No other significant code duplication found.

---

## 12. TODO/FIXME STATUS

**Result: Zero TODO, FIXME, HACK, or XXX comments found in the entire codebase.**

The codebase is clean of pending markers. This is a positive finding.

---

## Prioritized Action List

### P0 — Fix immediately (breaks on fresh install)
1. **Fix requirements.txt**: Replace `python-telegram-bot==21.0.1` with `pyTelegramBotAPI==4.21.0`

### P1 — Fix soon (silent divergence risks)
2. **`volume_load_gauge.py`**: Import and use `HARD_STOP_TSB_FLOOR` instead of hardcoded `-50`
3. **`adaptive_priority_lock.py`**: Import and use `HARD_STOP_TSB_FLOOR` and `VO2_ACWR_MAX` instead of hardcoded values
4. **Remove `ACWR_SAFE_MIN/MAX`** from `constants.py` (dead duplicates of `thresholds.py` values)

### P2 — Fix in next maintenance window
5. **Update CLAUDE.md**: Module counts (49→56 actual), science count (23→26), Phase 7 modules, Phase 7 test files, docs/specs/ contents
6. **Update docs/ROADMAP.MD**: Add Phase 7 as CLOSED
7. **`requirements.txt`**: Remove `scikit-learn`, `pandas`, `pyyaml` (not used in `titan/`); move `pyinstaller`/`pywin32` to a separate `requirements-build.txt`
8. **Add `ruff` and `mypy` to `requirements.txt`** (dev section) since `pyproject.toml` configures them
9. **Add Phase 7 ADR** (0014?) documenting the ML scaffold decision

### P3 — Low priority cleanup
10. Remove `from telebot import types` (unused, `telegram_bot.py:32`)
11. Remove `from __future__ import annotations` from `evidence_registry.py` and `operator_console.py`
12. Remove `from dataclasses import field` from `outcome_tracker.py`
13. Remove `from typing import Optional` from `adaptive_priority_lock.py`
14. Consider adding `__all__` to `__init__.py` files to make public API explicit

---

*Generated by automated codebase audit on 2026-03-02*
