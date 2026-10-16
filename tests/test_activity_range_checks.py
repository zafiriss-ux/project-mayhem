"""D-081: impossible activity values are rejected before the database.

The SQLite assessment (Test A06, A12) saw a negative distance and an HR of 400
accepted and stored, with no defined rule.
"""

from __future__ import annotations

import pytest

from titan.science.data_sanity import ACTIVITY_HR_BPM, DataSanityChecker

BASE = {"date": "2026-10-01", "distance_km": 10.0, "duration_sec": 3000,
        "avg_hr": 150, "max_hr": 170, "activity_type": "running"}


def _rules(**changes):
    row = {**BASE, **changes}
    return {(v.rule, v.field, v.severity) for v in DataSanityChecker().check_activity(row)}


@pytest.mark.unit
def test_a_normal_activity_passes() -> None:
    assert _rules() == set()


@pytest.mark.unit
@pytest.mark.parametrize("field", ["distance_km", "duration_sec"])
def test_a_negative_distance_or_duration_is_rejected(field) -> None:
    assert ("negative_value", field, "reject") in _rules(**{field: -5})


@pytest.mark.unit
@pytest.mark.parametrize("field,value", [("avg_hr", 400), ("max_hr", 400), ("avg_hr", 10)])
def test_a_heart_rate_outside_the_range_is_rejected(field, value) -> None:
    assert ("heart_rate_out_of_range", field, "reject") in _rules(**{field: value})


@pytest.mark.unit
def test_no_heart_rate_is_not_out_of_range() -> None:
    assert _rules(avg_hr=0, max_hr=None) == set()
    assert _rules(avg_hr=None, max_hr=0) == set()


@pytest.mark.unit
def test_the_range_edges_are_accepted() -> None:
    lo, hi = ACTIVITY_HR_BPM
    assert _rules(avg_hr=lo, max_hr=hi) == set()
