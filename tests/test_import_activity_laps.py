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
    _extract_numeric_id,
    _parse_float,
    _parse_int,
    _parse_lap_time,
    _parse_pace,
    compute_cardiac_drift,
    lookup_date,
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
    assert _parse_int("21,8") == 22


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


# ---------------------------------------------------------------------------
# [A] Date auto-detection helpers
# ---------------------------------------------------------------------------

def _make_activities_csv(tmp_path: Path, activity_id: str, date_str: str) -> Path:
    """Write a minimal Activities.csv with one row containing activity_id in the URL column."""
    acts_path = tmp_path / "Activities.csv"
    with acts_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Τίτλος", "Ημερομηνία", "Activity ID"])
        writer.writerow(["Morning run", date_str + " 07:30:00", activity_id])
    return acts_path


def test_extract_numeric_id_standard_filename():
    """activity_22896346850 → '22896346850'"""
    p = Path("activity_22896346850.csv")
    assert _extract_numeric_id(p) == "22896346850"


def test_extract_numeric_id_no_digits():
    assert _extract_numeric_id(Path("nodigits.csv")) is None


def test_lookup_date_from_activities_csv(tmp_path):
    """lookup_date returns the YYYY-MM-DD portion of the matching row."""
    acts = _make_activities_csv(tmp_path, "22896346850", "2026-05-10")
    lap_csv = tmp_path / "activity_22896346850.csv"
    lap_csv.write_text("")  # content irrelevant for lookup

    result = lookup_date(lap_csv, acts)
    assert result == "2026-05-10"


def test_lookup_date_id_not_found_raises(tmp_path):
    """SystemExit when activity ID is absent from Activities.csv."""
    acts = _make_activities_csv(tmp_path, "99999", "2026-01-01")
    lap_csv = tmp_path / "activity_12345678.csv"
    lap_csv.write_text("")

    with pytest.raises(SystemExit):
        lookup_date(lap_csv, acts)


def test_lookup_date_missing_activities_csv_raises(tmp_path):
    """SystemExit when Activities.csv path does not exist."""
    lap_csv = tmp_path / "activity_22896346850.csv"
    lap_csv.write_text("")

    with pytest.raises(SystemExit):
        lookup_date(lap_csv, tmp_path / "nonexistent.csv")


def test_date_required_when_no_activities_csv(tmp_path, capsys):
    """Running without --date and without --activities-csv exits with error."""
    csv_path = _make_lap_csv(tmp_path, num_laps=10)
    result = main(["--csv", str(csv_path)])
    assert result == 1
    captured = capsys.readouterr()
    assert "activities-csv" in captured.out or "date" in captured.out


def test_date_from_activities_csv_dry_run(tmp_path, capsys):
    """--activities-csv resolves the date so --date is not required."""
    csv_path = _make_lap_csv(tmp_path, num_laps=10)
    # Filename is activity_12345.csv → ID 12345
    acts = _make_activities_csv(tmp_path, "12345", "2026-05-15")

    result = main([
        "--csv", str(csv_path),
        "--activities-csv", str(acts),
        "--dry-run",
    ])
    assert result == 0
    captured = capsys.readouterr()
    assert "2026-05-15" in captured.out


# ---------------------------------------------------------------------------
# [B] Batch / folder mode
# ---------------------------------------------------------------------------

def test_folder_mode_dry_run(tmp_path, capsys):
    """--folder processes all activity_*.csv files and prints a batch summary."""
    # Create two lap CSVs and a matching Activities.csv
    csv1 = tmp_path / "activity_11111.csv"
    csv2 = tmp_path / "activity_22222.csv"
    # Copy content from helper (10 laps each)
    for path in (csv1, csv2):
        _make_lap_csv_at(tmp_path, path)

    acts_path = tmp_path / "Activities.csv"
    with acts_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Τίτλος", "Ημερομηνία", "Activity ID"])
        writer.writerow(["Run A", "2026-05-10 07:00:00", "11111"])
        writer.writerow(["Run B", "2026-05-11 07:00:00", "22222"])

    result = main([
        "--folder", str(tmp_path),
        "--activities-csv", str(acts_path),
        "--dry-run",
    ])
    assert result == 0
    captured = capsys.readouterr()
    assert "Batch" in captured.out
    assert "activity_11111" in captured.out
    assert "activity_22222" in captured.out


def test_folder_mode_no_csv_files(tmp_path, capsys):
    """Empty folder returns exit code 1 with a descriptive message."""
    result = main(["--folder", str(tmp_path), "--date", "2026-05-10"])
    assert result == 1
    captured = capsys.readouterr()
    assert "No activity_*.csv" in captured.out


def test_folder_mode_no_date_no_activities_csv(tmp_path, capsys):
    """Batch mode without date resolution exits with per-file error and code 1."""
    csv_path = tmp_path / "activity_99999.csv"
    _make_lap_csv_at(tmp_path, csv_path)

    result = main(["--folder", str(tmp_path)])
    assert result == 1
    captured = capsys.readouterr()
    assert "ERR" in captured.out


def _make_lap_csv_at(tmp_path: Path, target: Path, num_laps: int = 10) -> None:
    """Write a Garmin lap CSV to an explicitly named target path."""
    header = [
        "Αρ. Γύρου", "Χρόνος", "Col2", "Απόσταση", "Μέσος ρυθμός",
        "Col5", "Μέσοι ΚΠ", "Μέγιστοι ΚΠ",
        "Col8", "Col9", "Col10", "Col11", "Col12", "Col13",
        "Μέσο σκορ", "Col15", "Col16", "Διασκελισμός",
    ]
    rows = [header, ["Σύνοψη"] + ["--"] * 17]
    for i in range(1, num_laps + 1):
        hr = 140 + i
        rows.append([
            str(i), "1:05", "--", "0,20", "5:25", "--",
            str(hr), str(hr + 5),
            "--", "--", "--", "--", "--", "--",
            "170", "--", "--", "0,94",
        ])
    with target.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
