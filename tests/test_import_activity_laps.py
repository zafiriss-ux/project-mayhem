"""Tests for scripts/import_activity_laps.py."""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_activity_laps import (
    _parse_float,
    _parse_int,
    _parse_lap_time,
    _parse_pace,
    compute_cardiac_drift,
    main,
)

# ---------------------------------------------------------------------------
# Unit tests — parsing helpers
# ---------------------------------------------------------------------------

def test_parse_float_comma_decimal():
    assert _parse_float("0,94") == pytest.approx(0.94)


def test_parse_float_dot_decimal():
    assert _parse_float("1.05") == pytest.approx(1.05)


def test_parse_float_empty():
    assert _parse_float("") == 0.0
    assert _parse_float("--") == 0.0


def test_parse_int_normal():
    assert _parse_int("144") == 144


def test_parse_int_comma_decimal():
    assert _parse_int("21,8") == 21


def test_parse_int_empty():
    assert _parse_int("") == 0
    assert _parse_int("--") == 0


def test_parse_lap_time_mm_ss():
    assert _parse_lap_time("1:13") == 73


def test_parse_lap_time_mm_ss_decimal():
    # Decimal part of seconds is dropped
    assert _parse_lap_time("1:13,6") == 73


def test_parse_lap_time_empty():
    assert _parse_lap_time("") == 0
    assert _parse_lap_time("--") == 0


def test_parse_pace_mm_ss():
    assert _parse_pace("6:08") == 368


def test_parse_pace_empty():
    assert _parse_pace("") == 0
    assert _parse_pace("--") == 0


# ---------------------------------------------------------------------------
# Unit tests — cardiac drift
# ---------------------------------------------------------------------------

def test_cardiac_drift_calculation():
    """Expected drift: (131.5 - 120) / 120 * 100 ≈ 9.58 %"""
    laps = [{"avg_hr": h} for h in [120, 120, 120, 125, 130, 130, 132, 132, 132, 132]]
    drift = compute_cardiac_drift(laps)
    assert 9.0 < drift < 11.0


def test_cardiac_drift_positive_for_rising_hr():
    """Drift should be positive when HR rises across the activity."""
    laps = [
        {"avg_hr": 140},
        {"avg_hr": 141},
        {"avg_hr": 142},
        {"avg_hr": 143},
        {"avg_hr": 144},
        {"avg_hr": 150},
        {"avg_hr": 152},
        {"avg_hr": 154},
    ]
    drift = compute_cardiac_drift(laps)
    # First quarter (2 laps): [140, 141] → 140.5; last quarter: [152, 154] → 153
    # drift ≈ (153 - 140.5) / 140.5 * 100 ≈ 8.9 %
    assert drift > 0.0


def test_cardiac_drift_skips_zero_hr_laps():
    laps = [{"avg_hr": h} for h in [120, 120, 0, 130, 130, 130, 145, 145, 145, 145]]
    drift = compute_cardiac_drift(laps)
    assert drift > 0.0


def test_cardiac_drift_insufficient_laps_returns_zero():
    laps = [{"avg_hr": h} for h in [120, 130, 140]]
    assert compute_cardiac_drift(laps) == 0.0


def test_cardiac_drift_all_zero_hr_returns_zero():
    laps = [{"avg_hr": 0} for _ in range(10)]
    assert compute_cardiac_drift(laps) == 0.0


# ---------------------------------------------------------------------------
# Integration tests — dry-run
# ---------------------------------------------------------------------------

def _make_lap_csv(tmp_path: Path, num_laps: int = 10) -> Path:
    """Write a minimal Garmin lap CSV fixture."""
    csv_path = tmp_path / "activity_12345.csv"
    # Build rows: enough columns to reach COL_STRIDE_M (index 17)
    header = [
        "Αρ. Γύρου",      # 0  lap number
        "Χρόνος",         # 1  lap time
        "Col2",           # 2  (unused)
        "Απόσταση",       # 3  distance km
        "Μέσος ρυθμός",   # 4  avg pace
        "Col5",           # 5
        "Μέσοι ΚΠ",       # 6  avg HR
        "Μέγιστοι ΚΠ",    # 7  max HR
        "Col8",  "Col9",  "Col10",  "Col11",  "Col12",  "Col13",
        "Μέσο σκορ",      # 14 avg cadence
        "Col15", "Col16",
        "Διασκελισμός",   # 17 stride length
    ]
    rows = [header]
    # Summary row (should be skipped)
    rows.append(["Σύνοψη"] + ["--"] * 17)
    for i in range(1, num_laps + 1):
        hr = 140 + i  # gradually rising HR to produce positive drift
        rows.append([
            str(i),    # lap number
            "1:05",    # lap time
            "--",
            "0,20",    # distance km
            "5:25",    # avg pace
            "--",
            str(hr),   # avg HR
            str(hr + 5),  # max HR
            "--", "--", "--", "--", "--", "--",
            "170",     # avg cadence
            "--", "--",
            "0,94",    # stride length
        ])
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)
    return csv_path


def test_import_activity_laps_dry_run(tmp_path, capsys):
    """Dry-run must print summary without touching any database."""
    csv_path = _make_lap_csv(tmp_path, num_laps=10)
    result = main(["--csv", str(csv_path), "--date", "2026-05-10", "--dry-run"])
    assert result == 0
    captured = capsys.readouterr()
    assert "dry-run" in captured.out
    assert "Cardiac drift" in captured.out
    assert "Laps parsed" in captured.out


def test_import_activity_laps_writes_to_db(tmp_path):
    """Full run inserts rows into activity_laps and updates training_log."""
    csv_path = _make_lap_csv(tmp_path, num_laps=10)
    db_path = tmp_path / "titan_core.db"

    # Bootstrap a minimal training_log so the UPDATE can fire
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE training_log (id INTEGER PRIMARY KEY, date TEXT, "
        "session_type TEXT, distance_km REAL, duration_sec INTEGER, "
        "avg_hr INTEGER, training_load INTEGER, athlete_id TEXT)"
    )
    conn.execute(
        "INSERT INTO training_log (date, session_type, athlete_id) "
        "VALUES ('2026-05-10', 'EASY', 'owner')"
    )
    conn.commit()
    conn.close()

    # Patch the DB path resolution inside the script
    with patch("scripts.import_activity_laps.Path.home", return_value=tmp_path):
        # The script resolves: Path.home() / "Documents" / "TITAN" / "titan_core.db"
        db_dir = tmp_path / "Documents" / "TITAN"
        db_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(db_path), str(db_dir / "titan_core.db"))

        result = main(["--csv", str(csv_path), "--date", "2026-05-10"])

    assert result == 0

    # Verify activity_laps rows were inserted
    actual_db = db_dir / "titan_core.db"
    conn = sqlite3.connect(str(actual_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM activity_laps WHERE activity_id = 'activity_12345'"
    ).fetchone()[0]
    conn.close()
    assert count == 10
