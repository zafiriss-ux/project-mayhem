# ADR-0034 — Environmental Stress Compensation for Training Zones

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V8 — Risk: Static Thresholding (zones without Environmental Compensation)
**Phase:** 7.9 Hardening (decision record; T4-29 execution deferred Phase 8)
**Supplements:** ADR-0009 (safety gate hardening), ADR-0030 (external data source resilience), T1-09 (weather degraded mode — resolved)

---

## Context

TITAN OS applies training zone thresholds (heart rate zones, pace zones, lactate threshold
boundaries) as static constants. These constants are defined in `thresholds.py` and the
science engines apply them identically regardless of environmental conditions.

### The Problem

Physiological stress from exercise is not determined by heart rate or pace alone —
it is the combination of exercise intensity and environmental load. Two workouts at the
same target pace can produce vastly different physiological responses:

| Condition | Effective Stress | Governance Response (current) |
|---|---|---|
| 18°C, 40% RH, sea level | Baseline | Correct |
| 32°C, 80% RH (dew point 28°C) | +15–20% cardiac drift | **Identical — incorrect** |
| 0°C, strong wind | +10% metabolic cost (thermoregulation) | **Identical — incorrect** |

**The Dew Point Problem (most critical)**

`OptimalTimeCalculator` already uses dew point to recommend training *timing* (ADR-0002,
T1-09). However, if the athlete trains outside the optimal window — or if the system
generates a workout target — the training zones themselves are not adjusted. An athlete
doing a "Zone 2" run at a pace calibrated for 18°C at 28°C dew point is not doing
Zone 2 — they are doing Zone 3 or higher, with glycogen depletion and cardiac strain
consequences that the governance engine does not anticipate.

### The Temperature Problem

Cold-weather training increases metabolic cost through thermoregulation, which inflates
heart rate relative to pace at identical effort. This means pace-based targets remain
valid, but HR-based targets become misleading in either direction:
- Cold: HR underpredicts effort → athlete can overshoot intensity unknowingly
- Heat: HR overpredicts effort (cardiac drift) → athlete feels fine but is overloading

### Current State

The `WeatherAPI` module provides temperature, humidity, and dew point data. This data
is consumed by `OptimalTimeCalculator` but NOT passed to:
- `LactateThresholdEngine`
- `CriticalSpeedEngine`
- `WeeklyPlanGenerator` target generation
- `DailyCoach` recommendation context
- Governance gate evaluations

The integration exists (weather data is fetched); the consumption is incomplete.

---

## Decision

**Establish an Environmental Stress Index (ESI) as a first-class coaching context
field. Zone thresholds must carry an environmental adjustment factor when ESI exceeds
safe boundaries.**

### Environmental Stress Index (ESI)

```python
# In thresholds.py
ESI_DEW_POINT_MODERATE   = 16.0   # °C — first adjustment threshold
ESI_DEW_POINT_HIGH       = 21.0   # °C — significant impairment
ESI_DEW_POINT_EXTREME    = 24.0   # °C — hard cap on intensity
ESI_TEMP_COLD_THRESHOLD  = 5.0    # °C — cold compensation trigger
ESI_TEMP_HOT_THRESHOLD   = 28.0   # °C — heat compensation trigger
```

**ESI categories and zone adjustments:**

| ESI Level | Condition | Pace Adjustment | HR Zone Ceiling |
|---|---|---|---|
| NEUTRAL | Dew point < 16°C, temp 5–28°C | None | Normal |
| MODERATE | Dew point 16–21°C, OR temp > 28°C | +5–10 sec/km | Zone −1 |
| HIGH | Dew point 21–24°C, OR temp > 32°C | +10–20 sec/km | Zone −1, no Zone 4/5 |
| EXTREME | Dew point > 24°C, OR temp > 38°C | Easy only | Hard stop on any intensity ≥ Zone 3 |
| COLD | Temp < 5°C | Pace unchanged | HR ignored; pace-only targeting |

Adjustment values follow established exercise physiology (Cheuvront & Haymes, 2001;
Tucker et al., 2006). Evidence label: MODERATE (literature-supported ranges, not
athlete-specific).

### Integration Points

1. **`DailyCoach` coaching context** — ESI level added as a standard field:
   ```python
   coaching_ctx["esi_level"] = "HIGH"
   coaching_ctx["esi_pace_adjustment_sec_per_km"] = 15
   ```

2. **`WeeklyPlanGenerator`** — target zones adjusted by ESI before emission.
   The plan must state the ESI level and adjusted targets explicitly.

3. **Governance gate integration** — When ESI is HIGH or EXTREME:
   - Block `VO2_ELIGIBILITY_GATE` from approving VO₂max workouts (EXTREME only).
   - Emit `esi_intensity_restricted` structured event.
   - Flag in `INTENSITY_GATE_YELLOW` context rather than as a new lock code
     (to preserve lock code stability per ADR-0021).

4. **Telegram coaching message** — Include ESI adjustment in morning briefing:
   > "Today: dew point 22°C (HIGH stress). Pace targets adjusted +15 sec/km.
   > No threshold or VO₂ work recommended."

### What This Does NOT Change

- `OptimalTimeCalculator` timing recommendations are unchanged (already dew-point-aware).
- Governance hard-stop gates (H1–H7) are NOT modified — ESI operates as an overlay on
  intensity recommendations, not as a new safety gate.
- The existing `HARD_STOP_*` constants remain at their current values.

### Phase Deferral

Full implementation (T4-29) is deferred to Phase 8 (after Phase 8 entry gate passes).
The ESI framework is low-blast-radius (read-only from weather data, overlay on
recommendations) and does not require schema changes. It is classified Tier 4 because
it improves recommendation accuracy but is not a data integrity or safety-gate concern.

**Exception:** ESI EXTREME → VO₂ block is a safety behaviour. However, since VO₂
eligibility already has a multi-factor gate (`VO2_ELIGIBILITY_GATE`), ESI EXTREME is
an additional factor within that gate, not a new independent gate.

---

## Debt Items Created

- **T4-29** — Training zone thresholds not adjusted for environmental stress (temperature,
  dew point, humidity) — ESI framework not implemented (Tier 4, independent, deferred
  Phase 8)

---

## Alternatives Considered

**Alternative A — Adjust governance hard-stop thresholds by ESI**
Rejected. Modifying `HARD_STOP_HRV_DELTA` or `HARD_STOP_TSB_FLOOR` based on weather
would make the governance safety floor variable. The safety floor must remain constant
and independent of environmental context to remain verifiable.

**Alternative B — Block all recommendations in EXTREME ESI**
Rejected. Governance already has a hard-stop mechanism. ESI EXTREME blocking
zone-intensity recommendations within the intensity governor is the appropriate scope.
A full recommendation block in EXTREME conditions is excessive (the athlete may choose
to do a walk or easy stroll regardless of governance).

**Alternative C — Use WBGT (Wet Bulb Globe Temperature) instead of dew point**
WBGT is more scientifically precise for heat stress. However WBGT requires solar
radiation data that Open-Meteo does not provide in the free tier. Dew point is a
high-quality proxy and already available from the weather integration. WBGT is a
Phase 9 enhancement if solar radiation data becomes available.

---

## Consequences

- Positive: Training zone targets will be environmentally adjusted — athletes training
  in heat and humidity will receive pace targets that reflect actual physiological
  demand rather than lab-calibrated targets.
- Positive: Morning briefings will communicate ESI level explicitly — operators and
  athletes understand why targets were adjusted.
- Positive: VO₂max workouts will be blocked in extreme heat without requiring a new
  governance hard-stop gate.
- Negative (acceptable): ESI pace adjustments are heuristic (MODERATE evidence label).
  They are better than no adjustment but are not individually calibrated per athlete.
  Per-athlete ESI calibration is a Phase 9 item (see ADR-0033 Layer 3).
- Constraint: T4-29 is Phase 8 work. No implementation occurs in Phase 7.9.

---

## Implementation Notes

**OBS-035 / T5-68 (pending):** `titan/orchestration/daily_coach.py:713` uses the literal
`12.0` as the fallback dew_point when Garmin data does not include `dew_point`:
`dew_point_c=_safe_float(garmin_data.get("dew_point"), 12.0)`. This literal is not present
in `thresholds.py` or `evidence_registry.py`, violating ADR-0034's requirement that ESI
parameters be governed constants. Additionally, `NutritionOptimizer` uses `25.0°C` as the
conservative dew_point fallback (T5-59), creating an internal inconsistency between the ESI
path (12.0°C) and the nutrition hydration path (25.0°C) for the same physical quantity.

Fix registered as T5-68: extract `12.0` to `ESI_DEW_POINT_FALLBACK_C` in `thresholds.py`
with conservative value (≥18.0°C per safety-first principle); register in `evidence_registry.py`
with HEURISTIC provenance. The conservative direction is higher dew_point (overestimates
thermal stress → more cautious pacing).

