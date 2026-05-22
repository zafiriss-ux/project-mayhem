# ADR-0056: Nutrition Personalization

Status: Accepted — 2026-05-22
Author: Claude (Architect)

## Context

NutritionOptimizer produces correct macro totals (Burke/Jeukendrup) but meal timing and
structure are static. No mechanism exists to incorporate athlete preferences or biological
factors.

## Decisions

D1: `nutrition_preferences` table (SCHEMA_VERSION 21)
D2: Entry via Settings menu (option 2 within Ρυθμίσεις Αθλητή)
D3: 6 questions (Q1–Q6); Q6 conditional on Q5=female
D4: Fallback to current behavior when `prefs=None` (zero breaking change)
D5: `NutritionPreferences` dataclass as optional param in `calculate_daily_nutrition()`
D6: Macro totals unchanged — only timing and distribution change
D7: `biological_sex` field for physiological accuracy (not gender identity)
D8: `low_carb` overridden on TEMPO/INTERVALS/HAMMER/LONG_RUN/RACE (glycogen mandatory for quality sessions)

## Evidence base

- Female REE: Arciero et al 1993
- Luteal phase +200 kcal: Benton & Young 2012, Davidsen et al 2007
- Protein female: Morton et al 2018
- Hydration sex diff: Watson et al 1980

## Consequences

Positive: actionable meal plans, zero breaking change, extensible (Q7+ later)
Negative: +1 DB table (SCHEMA_VERSION 19 → 21), `NutritionOptimizer` signature change (backward compatible)
