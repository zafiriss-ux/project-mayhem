"""Tests for scripts/import_garmin_csv.py helper functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_garmin_csv import (
    _synthetic_garmin_id,
    compute_trimp_simple,
    infer_session_type,
    parse_distance,
    parse_duration,
    parse_hr,
)


def test_parse_distance_comma_decimal():
    assert parse_distance("16,10") == 16.10


def test_parse_distance_missing():
    assert parse_distance("--") == 0.0


def test_parse_distance_empty():
    assert parse_distance("") == 0.0


def test_parse_distance_integer():
    assert parse_distance("10") == 10.0


def test_parse_duration_hms():
    assert parse_duration("01:17:40") == 4660


def test_parse_duration_missing():
    assert parse_duration("--") == 0


def test_parse_duration_minutes_only():
    assert parse_duration("30:00") == 1800


def test_parse_hr_normal():
    assert parse_hr("144") == 144


def test_parse_hr_missing():
    assert parse_hr("--") == 0


def test_infer_session_type_long_run():
    assert infer_session_type("Long Run", 21.0, 7200) == "LONG_RUN"


def test_infer_session_type_easy():
    assert infer_session_type("Easy Run", 10.0, 3600) == "EASY"


def test_infer_session_type_intervals():
    assert infer_session_type("5x1km Intervals", 8.0, 2400) == "INTERVALS"


def test_infer_session_type_tempo():
    assert infer_session_type("Tempo run", 12.0, 3600) == "TEMPO"


def test_infer_session_type_distance_threshold():
    # exactly 18 km → LONG_RUN
    assert infer_session_type("Afternoon Run", 18.0, 6000) == "LONG_RUN"
    # 17.9 km → EASY
    assert infer_session_type("Afternoon Run", 17.9, 6000) == "EASY"


def test_compute_trimp():
    # 60 min, avg_hr 144, max_hr 160 → 60 * (144/160) = 54.0
    t = compute_trimp_simple(3600, 144, 160)
    assert 50 < t < 60


def test_compute_trimp_zero_hr():
    assert compute_trimp_simple(3600, 0, 160) == 0.0
    assert compute_trimp_simple(3600, 144, 0) == 0.0


def test_synthetic_garmin_id_stable():
    id1 = _synthetic_garmin_id("2024-01-15", 16.1, 4660)
    id2 = _synthetic_garmin_id("2024-01-15", 16.1, 4660)
    assert id1 == id2


def test_synthetic_garmin_id_unique():
    id1 = _synthetic_garmin_id("2024-01-15", 16.1, 4660)
    id2 = _synthetic_garmin_id("2024-01-16", 16.1, 4660)
    assert id1 != id2


def test_synthetic_garmin_id_prefix():
    sid = _synthetic_garmin_id("2024-01-15", 16.1, 4660)
    assert sid.startswith("csv_")
