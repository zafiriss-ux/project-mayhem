"""OW-F1 (ADR-0069 §1): the morning's TSB includes the load the morning's own sync stored.

The coach loads the training history when it is built; the morning then syncs Garmin and
stores yesterday's run. The TSB that H4 reads must be computed after that, from the stored
loads, not from the history read before the sync. Synthetic watch data only.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from tests.test_daily_coach_characterization import (  # noqa: F401  (world is a fixture)
    _run_scenario,
    normal_day,
    world,
)
from titan.science.tsb_engine import compute_ctl_atl_tsb

_MORNING = date(2026, 3, 10)  # morning 9 of the scenario, after a run on the 9th


def _stored_loads(db_path) -> list[tuple[str, float]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT date, training_load FROM training_log WHERE athlete_id = 'owner'"
        ).fetchall()
    return [(str(day)[:10], float(load or 0.0)) for day, load in rows]


def _morning_tsb(result: dict, day: date) -> float:
    rows = [r for r in result["tables"]["governance_outcomes"] if r["date"] == day.isoformat()]
    assert rows, f"no governance outcome for {day}"
    return float(rows[-1]["tsb_value"])


def test_the_morning_tsb_includes_the_run_its_sync_stored(world):
    result = _run_scenario(world, [normal_day(i) for i in range(9)])
    loads = [(d, v) for d, v in _stored_loads(world["db_path"]) if d < _MORNING.isoformat()]
    assert any(d == "2026-03-09" for d, _ in loads), "the scenario stores a run on the 9th"
    _ctl, _atl, expected = compute_ctl_atl_tsb(loads, reference_date=_MORNING)
    assert _morning_tsb(result, _MORNING) == expected


def test_h4_sees_the_overload_of_the_day_before(world):
    """The golden morning of 10/3: TSB below −50 once yesterday's run counts (ADR-0069 §1)."""
    result = _run_scenario(world, [normal_day(i) for i in range(9)])
    assert _morning_tsb(result, _MORNING) <= -50
