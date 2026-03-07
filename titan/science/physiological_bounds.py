"""
Physiological Bounds Validation — ADR-0023 / T1-18.

Single validation layer at the database→science pipeline boundary.
Engines receive values that are either within physiological range or None.
They never receive zeros, NaN, Inf, or sensor artefact values.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

_log = logging.getLogger(__name__)

# ADR-0040-SINGLE-ATHLETE-SHORTCUT: This module assumes a single active athlete.
# Multi-athlete isolation is deferred to Phase 9 (ADR-0033 Layer 3, T5-07).
# Do NOT introduce new structural coupling that would be harder to isolate later.

# Physiological plausibility ranges for each measured field.
# Evidence: HEURISTIC (see evidence_registry.py § Physiological Bounds).
# These are NOT governance thresholds — they are input sanity guards.
BOUNDS: dict[str, tuple[float, float]] = {
    "hrv_ms":         (0.1, 300.0),   # RMSSD: 0.1 excludes sensor-zero; 300 exceeds max recorded
    "rhr_bpm":        (25.0, 120.0),  # extreme athlete low; optical artefact ceiling
    "ctl":            (0.0, 300.0),   # TSS/day; >200 = elite peak load
    "atl":            (0.0, 500.0),   # acute load; higher ceiling for sprint/race weeks
    "acwr":           (0.0, 3.0),     # 0 if no chronic load; cap runaway values
    "glycogen_debt":  (0.0, 20.0),    # negative impossible; >7 = fueling lock threshold
    "temperature_c":  (-40.0, 55.0),  # operational climate range
    "dew_point_c":    (-40.0, 40.0),  # operational dew-point range
    "weight_kg":      (25.0, 300.0),  # physiological plausibility for adult athlete mass
    "sleep_hours":    (0.0, 16.0),    # daily sleep duration guardrail
    "training_load":  (0.0, 2500.0),  # sRPE-based daily load plausibility ceiling
}


@dataclass
class BoundsViolation:
    field: str
    value: float
    lo: float
    hi: float
    action: str  # "clamped" | "nulled"


def validate_and_clamp(
    data: dict[str, float | None],
    context: str,
) -> tuple[dict[str, float | None], list[BoundsViolation]]:
    """
    Validate physiological values against BOUNDS.

    Violation policy (ADR-0023 §3):
    - hrv_ms = 0.0 exactly  → None unconditionally (sensor failure)
    - value outside bounds by ≤ span → clamp to bound + emit bounds_violation
    - value outside bounds by >  span → None + emit bounds_violation + data_quality_warning
    - value within bounds           → unchanged

    Returns (cleaned_data, violations).
    """
    result: dict[str, float | None] = {}
    violations: list[BoundsViolation] = []

    for field, value in data.items():
        if field not in BOUNDS or value is None:
            result[field] = value
            continue

        lo, hi = BOUNDS[field]

        # hrv_ms = 0 is always sensor failure — null unconditionally
        if field == "hrv_ms" and value == 0.0:
            v = BoundsViolation(field, value, lo, hi, "nulled")
            violations.append(v)
            _emit(context, v, extra="data_quality_warning")
            result[field] = None
            continue

        if lo <= value <= hi:
            result[field] = value
            continue

        span = hi - lo
        excess = (lo - value) if value < lo else (value - hi)

        if excess <= span:
            clamped = max(lo, min(hi, value))
            v = BoundsViolation(field, value, lo, hi, "clamped")
            violations.append(v)
            _emit(context, v)
            result[field] = clamped
        else:
            v = BoundsViolation(field, value, lo, hi, "nulled")
            violations.append(v)
            _emit(context, v, extra="data_quality_warning")
            result[field] = None

    return result, violations


def validate_single(
    field: str,
    value: float | None,
    context: str,
) -> float | None:
    """Validate a single named physiological value. Returns clamped value or None."""
    if value is None:
        return None
    out, _ = validate_and_clamp({field: value}, context)
    return out[field]


def _emit(context: str, v: BoundsViolation, extra: str | None = None) -> None:
    payload: dict = {
        "flow": "physiological_bounds",
        "action": "bounds_violation",
        "context": context,
        "field": v.field,
        "value": v.value,
        "lo": v.lo,
        "hi": v.hi,
        "violation_action": v.action,
    }
    _log.warning(json.dumps(payload))
    if extra:
        _log.warning(json.dumps({**payload, "action": extra}))
