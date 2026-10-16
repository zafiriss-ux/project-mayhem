"""Consistency rules of the validation plan, checked on every synthetic morning.

Each rule returns the violations it finds as ``(profile, scenario, date, detail)``. The
rules and their sources (``docs/validation/synthetic-athlete-validation.md``, "Κανόνες
συνέπειας", and the ADRs named below) are listed in the report,
``docs/validation/synthetic-athlete-report.md``.
"""
from __future__ import annotations

import re
from typing import Any

from tests.synthetic.world import Morning, Outcome
from titan.science.physiological_bounds import BOUNDS

Violation = tuple[str, str, str, str]

# Session intensity order, taken from GovernanceEngine._DOWNGRADE_MAP_2OF4 (every
# downgrade goes one step down this order) and _QUALITY_SESSIONS. LONG_RUN is not a
# quality session and is not in the map; it sits between EASY and the quality sessions.
RANK = {
    "REST": 0, "RECOVERY": 1, "EASY": 1, "LONG_RUN": 2,
    "PROGRESSIVE": 3, "TEMPO": 3, "INTERVALS": 4, "HAMMER": 4, "RACE": 5,
}

# Pace limits that any running session must fall within (min/km). A pace outside them
# means distance and duration do not belong to the same run.
PACE_MIN_KM = (2.5, 10.0)

# Telegram text: a number with five or more decimals is a float printed raw.
_RAW_FLOAT = re.compile(r"\d+\.\d{5,}")

# daily_metrics column -> physiological_bounds key (ADR-0023).
_STORED_BOUNDS = {
    "hrv_rmssd": "hrv_ms",
    "resting_hr": "rhr_bpm",
    "sleep_hours": "sleep_hours",
    "weight_kg": "weight_kg",
    "glycogen_debt": "glycogen_debt",
}


def _type(m: Morning) -> str:
    return str((m.session or {}).get("session_type", "")).upper()


def _num(d: dict[str, Any] | None, key: str) -> float:
    try:
        return float((d or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _v(o: Outcome, m: Morning, detail: str) -> Violation:
    return (o.profile.key, o.scenario.key, m.date, detail)


def no_morning_raises(outcomes: list[Outcome]) -> list[Violation]:
    return [_v(o, m, m.raised) for o in outcomes for m in o.mornings if m.raised]


def rest_has_no_volume(outcomes: list[Outcome]) -> list[Violation]:
    """REST means 0 km and 0 min, and anything else is a run with some volume."""
    out = []
    for o in outcomes:
        for m in o.mornings:
            km, minutes = _num(m.session, "distance_km"), _num(m.session, "duration_min")
            if _type(m) == "REST" and (km or minutes):
                out.append(_v(o, m, f"REST {km:g} km {minutes:g} min"))
            if _type(m) not in ("REST", "") and not km and not minutes:
                out.append(_v(o, m, f"{_type(m)} with 0 km and 0 min"))
    return out


def reduction_reduces_volume(outcomes: list[Outcome]) -> list[Violation]:
    """A session moved down the intensity order is also shorter than the one planned."""
    out = []
    for o in outcomes:
        for m in o.mornings:
            planned = str((m.planned or {}).get("session_type", "")).upper()
            final = _type(m)
            if planned not in RANK or final not in RANK or final == "REST":
                continue
            if RANK[final] < RANK[planned]:
                p_min, f_min = _num(m.planned, "duration_min"), _num(m.session, "duration_min")
                if p_min and f_min >= p_min:
                    out.append(_v(o, m, f"{planned} {p_min:g}' -> {final} {f_min:g}'"))
    return out


def gate_modifier_reduces_volume(outcomes: list[Outcome]) -> list[Violation]:
    """D-043: the intensity gate's volume modifier (YELLOW 0.8, RED 0.0) shrinks the session."""
    out = []
    for o in outcomes:
        for m in o.mornings:
            modifier = (m.session or {}).get("volume_modifier")
            p_min, f_min = _num(m.planned, "duration_min"), _num(m.session, "duration_min")
            if modifier is None or not 0 <= float(modifier) < 1 or not p_min:
                continue
            if f_min > round(p_min * float(modifier)):
                out.append(_v(o, m, f"{_type(m)} {f_min:g}' with modifier {modifier} of {p_min:g}'"))
    return out


def governance_never_raises_intensity(outcomes: list[Outcome]) -> list[Violation]:
    """Governance only restricts: the final session is never above the planned one."""
    out = []
    for o in outcomes:
        for m in o.mornings:
            planned = str((m.planned or {}).get("session_type", "")).upper()
            final = _type(m)
            if planned in RANK and final in RANK and RANK[final] > RANK[planned]:
                out.append(_v(o, m, f"{planned} -> {final}"))
    return out


def pace_is_plausible(outcomes: list[Outcome]) -> list[Violation]:
    """Distance and duration of a session describe a runnable pace."""
    out = []
    for o in outcomes:
        for m in o.mornings:
            km, minutes = _num(m.session, "distance_km"), _num(m.session, "duration_min")
            if km > 0 and minutes > 0:
                pace = minutes / km
                if not PACE_MIN_KM[0] <= pace <= PACE_MIN_KM[1]:
                    out.append(_v(o, m, f"{_type(m)} {km:g} km in {minutes:g}' = {pace:.2f} min/km"))
    return out


# Stored runs: slower than 15:00 min/km is a walk, faster than 2:00 min/km is above
# every world record from 1500 m up (the fastest average is about 2:26 min/km).
STORED_PACE_S_KM = (120.0, 900.0)


def stored_runs_are_runnable(outcomes: list[Outcome]) -> list[Violation]:
    """A run written to training_log has a pace a person can run, or a quality flag."""
    out = []
    for o in outcomes:
        for run in o.runs:
            pace = float(run.get("avg_pace_sec_per_km") or 0)
            if pace and not STORED_PACE_S_KM[0] <= pace <= STORED_PACE_S_KM[1] and not run.get("quality_flag"):
                out.append((o.profile.key, o.scenario.key, str(run["date"]),
                            f"{run['distance_km']} km in {run['duration_sec']} s, no quality flag"))
    return out


def stored_values_in_bounds(outcomes: list[Outcome]) -> list[Violation]:
    """What is written to daily_metrics stays inside physiological_bounds (ADR-0023)."""
    out = []
    for o in outcomes:
        for m in o.mornings:
            for column, key in _STORED_BOUNDS.items():
                value = (m.metrics_row or {}).get(column)
                lo, hi = BOUNDS[key]
                if value is not None and not lo <= float(value) <= hi:
                    out.append(_v(o, m, f"{column}={value}"))
    return out


def risk_never_more_aggressive(outcomes: list[Outcome]) -> list[Violation]:
    """With data that point to more stress, the last morning is never harder or longer
    than the same athlete's last morning in the ordinary week."""
    baseline = {o.profile.key: o.last for o in outcomes if o.scenario.key == "ordinary_week"}
    out = []
    for o in outcomes:
        base = baseline.get(o.profile.key)
        if not o.scenario.risk or base is None:
            continue
        m = o.last
        if _type(m) in RANK and _type(base) in RANK and RANK[_type(m)] > RANK[_type(base)]:
            out.append(_v(o, m, f"{_type(m)} vs ordinary {_type(base)}"))
        if _num(m.session, "duration_min") > _num(base.session, "duration_min"):
            out.append(_v(o, m, f"{_num(m.session, 'duration_min'):g}' vs ordinary "
                                f"{_num(base.session, 'duration_min'):g}'"))
    return out


def sleep_debt_eases_the_day(outcomes: list[Outcome]) -> list[Violation]:
    """ADR-0066 (SV-16): after three nights in a row with a sleep score under 60 the last
    morning is EASY (or REST) and keeps at most 70% of the planned duration."""
    out = []
    for o in outcomes:
        last3 = o.nights[-3:]
        if len(last3) < 3 or not all(n is not None and n.sleep_score is not None and n.sleep_score < 60
                                     for n in last3):
            continue
        m = o.last
        if _type(m) not in ("EASY", "RECOVERY", "REST"):
            out.append(_v(o, m, f"{_type(m)} after three bad nights"))
            continue
        p_min, f_min = _num(m.planned, "duration_min"), _num(m.session, "duration_min")
        if _type(m) != "REST" and p_min and f_min > round(p_min * 0.7):
            out.append(_v(o, m, f"{p_min:g}' planned -> {f_min:g}' after three bad nights"))
    return out


def acwr_known_after_six_weeks(outcomes: list[Outcome]) -> list[Violation]:
    """ADR-0051: ACWR may be None only for insufficient history; six weeks are enough."""
    return [_v(o, o.last, "acwr is None") for o in outcomes
            if o.scenario.group != "data" and (o.last.trace or {}).get("acwr") is None]


def phase_follows_the_athlete(outcomes: list[Outcome]) -> list[Violation]:
    """The routine (APL thresholds) uses the athlete's TRAINING_PHASE."""
    out = []
    for o in outcomes:
        phase = str((o.last.trace or {}).get("phase", ""))
        if o.scenario.key == "ordinary_week" and phase != o.profile.phase:
            out.append(_v(o, o.last, f"{phase} instead of {o.profile.phase}"))
    return out


def missing_reading_not_replaced(outcomes: list[Outcome]) -> list[Violation]:
    """ADR-0051: a missing HRV reading propagates; another day's value is not used."""
    out = []
    for o in outcomes:
        m = o.last
        row = m.metrics_row or {}
        hrv_used = (m.trace or {}).get("hrv")
        if row.get("hrv_rmssd") is None and hrv_used:
            out.append(_v(o, m, f"today has no HRV, decision used {hrv_used}"))
    return out


def telegram_numbers_are_formatted(outcomes: list[Outcome]) -> list[Violation]:
    out = []
    for o in outcomes:
        for m in o.mornings:
            for text in m.telegram:
                for raw in sorted(set(_RAW_FLOAT.findall(text))):
                    out.append(_v(o, m, raw))
    return out


RULES = {
    "no_morning_raises": no_morning_raises,
    "rest_has_no_volume": rest_has_no_volume,
    "reduction_reduces_volume": reduction_reduces_volume,
    "gate_modifier_reduces_volume": gate_modifier_reduces_volume,
    "governance_never_raises_intensity": governance_never_raises_intensity,
    "pace_is_plausible": pace_is_plausible,
    "stored_values_in_bounds": stored_values_in_bounds,
    "stored_runs_are_runnable": stored_runs_are_runnable,
    "risk_never_more_aggressive": risk_never_more_aggressive,
    "sleep_debt_eases_the_day": sleep_debt_eases_the_day,
    "acwr_known_after_six_weeks": acwr_known_after_six_weeks,
    "phase_follows_the_athlete": phase_follows_the_athlete,
    "missing_reading_not_replaced": missing_reading_not_replaced,
    "telegram_numbers_are_formatted": telegram_numbers_are_formatted,
}
