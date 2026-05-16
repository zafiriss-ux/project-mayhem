"""
Import Garmin lap data from a CSV export and store in activity_laps table.

Usage:
    python scripts/import_activity_laps.py \\
      --csv activity_22896346850.csv \\
      --date 2026-05-10 \\
      [--dry-run]

Reads a Garmin lap-detail CSV (Greek locale), computes cardiac drift from
the lap HR data, writes rows into the activity_laps table, and back-fills
the cardiac_drift column on the matching training_log row.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Column indices (0-based) in the Garmin lap CSV
# ---------------------------------------------------------------------------
COL_LAP_NUMBER    = 0   # lap number; "Σύνοψη" rows are skipped
COL_LAP_TIME      = 1   # "1:13,6" → mm:ss,d → total seconds
COL_DISTANCE_KM   = 3   # "0,20" → float (comma decimal)
COL_AVG_PACE      = 4   # "6:08" → total seconds
COL_AVG_HR        = 6   # integer
COL_MAX_HR        = 7   # integer
COL_AVG_CADENCE   = 14  # integer
COL_STRIDE_M      = 17  # "0,94" → float (comma decimal)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_float(s: str) -> float:
    """'0,94' or '0.94' → 0.94.  Empty / '--' → 0.0."""
    if not s or s == "--":
        return 0.0
    return float(s.replace(",", "."))


def _parse_int(s: str) -> int:
    """Integer field; empty / '--' → 0."""
    if not s or s == "--":
        return 0
    try:
        return int(float(s.replace(",", ".")))
    except (ValueError, AttributeError):
        return 0  # Unparseable field value (e.g. non-numeric text) — safe default


def _parse_lap_time(s: str) -> int:
    """'1:13,6' → 73 seconds  (mm:ss,d, decimal part dropped)."""
    if not s or s == "--":
        return 0
    # Discard decimal part of seconds if present
    s = s.replace(",", ".")
    if "." in s:
        s = s[: s.index(".")]
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, IndexError):
        return 0  # Malformed time string (non-numeric segment) — safe default
    return 0


def _parse_pace(s: str) -> int:
    """'6:08' → 368 seconds per km.  Empty / '--' → 0."""
    if not s or s == "--":
        return 0
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return 0  # Unparseable pace value (malformed/non-numeric) — safe default
    return 0


# ---------------------------------------------------------------------------
# Cardiac drift computation (importable for testing)
# ---------------------------------------------------------------------------

def compute_cardiac_drift(laps: list[dict]) -> float:
    """Compute cardiac drift from lap HR data.

    Algorithm:
    - Filter out any laps where avg_hr == 0 (GPS/sensor drop-out artefact).
    - Skip the first 2 of the remaining laps (warm-up artefact) when deciding
      the *working* range for the quartile boundaries, but the 25 % size is
      calculated from the full valid-HR list so that the first quarter can
      anchor at the early-run baseline (which includes warm-up HR).
    - Take the first 25 % of all valid-HR laps → first_quarter_avg.
    - Take the last 25 % of all valid-HR laps → last_quarter_avg.
    - drift = (last_quarter_avg - first_quarter_avg) / first_quarter_avg × 100

    Args:
        laps: List of dicts with at least an ``avg_hr`` key.

    Returns:
        Cardiac drift percentage as a float.  Returns 0.0 when there is not
        enough valid data (fewer than 4 valid-HR laps).
    """
    # Filter zero-HR laps (sensor drop-out / GPS artefact)
    valid = [lap for lap in laps if lap.get("avg_hr", 0) > 0]

    if len(valid) < 4:
        return 0.0

    quarter = max(1, len(valid) // 4)
    first_q = valid[:quarter]
    last_q = valid[-quarter:]

    first_quarter_avg = sum(lap["avg_hr"] for lap in first_q) / len(first_q)
    last_quarter_avg = sum(lap["avg_hr"] for lap in last_q) / len(last_q)

    if first_quarter_avg == 0:
        return 0.0

    return (last_quarter_avg - first_quarter_avg) / first_quarter_avg * 100.0


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

def read_laps_from_csv(csv_path: Path) -> list[dict]:
    """Parse a Garmin lap CSV and return a list of lap dicts."""
    laps: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not row:
                continue
            lap_field = row[COL_LAP_NUMBER].strip()
            # Skip header rows and summary rows
            if lap_field == "Σύνοψη" or not lap_field.isdigit():
                continue
            try:
                laps.append(
                    {
                        "lap_number": int(lap_field),
                        "lap_time_sec": _parse_lap_time(row[COL_LAP_TIME] if len(row) > COL_LAP_TIME else ""),
                        "distance_km": _parse_float(row[COL_DISTANCE_KM] if len(row) > COL_DISTANCE_KM else ""),
                        "avg_pace_sec": _parse_pace(row[COL_AVG_PACE] if len(row) > COL_AVG_PACE else ""),
                        "avg_hr": _parse_int(row[COL_AVG_HR] if len(row) > COL_AVG_HR else ""),
                        "max_hr": _parse_int(row[COL_MAX_HR] if len(row) > COL_MAX_HR else ""),
                        "avg_cadence": _parse_int(row[COL_AVG_CADENCE] if len(row) > COL_AVG_CADENCE else ""),
                        "stride_m": _parse_float(row[COL_STRIDE_M] if len(row) > COL_STRIDE_M else ""),
                    }
                )
            except (IndexError, ValueError):
                # Malformed row — skip silently
                continue
    return laps


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _ensure_activity_laps_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_laps (
            id              INTEGER PRIMARY KEY,
            activity_date   TEXT NOT NULL,
            activity_id     TEXT NOT NULL,
            lap_number      INTEGER NOT NULL,
            lap_time_sec    INTEGER,
            distance_km     REAL,
            avg_hr          INTEGER,
            max_hr          INTEGER,
            avg_pace_sec    INTEGER,
            avg_cadence     INTEGER,
            stride_m        REAL,
            cardiac_drift   REAL,
            UNIQUE(activity_id, lap_number)
        )
        """
    )


def _ensure_training_log_cardiac_drift_column(conn: sqlite3.Connection) -> None:
    """Add cardiac_drift column to training_log if it does not exist yet."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(training_log)")}
    if "cardiac_drift" not in cols:
        conn.execute(
            "ALTER TABLE training_log ADD COLUMN cardiac_drift REAL"
        )


def _insert_laps(
    conn: sqlite3.Connection,
    laps: list[dict],
    activity_id: str,
    activity_date: str,
    cardiac_drift: float,
) -> int:
    """Insert lap rows and return the count of rows actually inserted."""
    inserted = 0
    for lap in laps:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO activity_laps
                (activity_date, activity_id, lap_number, lap_time_sec,
                 distance_km, avg_hr, max_hr, avg_pace_sec, avg_cadence,
                 stride_m, cardiac_drift)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_date,
                activity_id,
                lap["lap_number"],
                lap["lap_time_sec"],
                lap["distance_km"],
                lap["avg_hr"],
                lap["max_hr"],
                lap["avg_pace_sec"],
                lap["avg_cadence"],
                lap["stride_m"],
                cardiac_drift,
            ),
        )
        inserted += cur.rowcount
    return inserted


def _update_activity_laps_drift(
    conn: sqlite3.Connection, activity_id: str, cardiac_drift: float
) -> None:
    conn.execute(
        "UPDATE activity_laps SET cardiac_drift = ? WHERE activity_id = ?",
        (cardiac_drift, activity_id),
    )


def _update_training_log_drift(
    conn: sqlite3.Connection, activity_date: str, cardiac_drift: float
) -> int:
    cur = conn.execute(
        "UPDATE training_log SET cardiac_drift = ? WHERE date = ?",
        (cardiac_drift, activity_date),
    )
    return cur.rowcount


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import Garmin lap CSV into activity_laps table."
    )
    parser.add_argument("--csv", required=True, help="Path to Garmin lap CSV file.")
    parser.add_argument(
        "--date", required=True, help="Activity date in YYYY-MM-DD format."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and compute drift; print summary without writing to DB.",
    )
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    activity_date = args.date
    # Derive activity_id from filename: strip path and extension
    activity_id = csv_path.stem  # e.g. "activity_22896346850"

    print(f"CSV:          {csv_path}")
    print(f"Activity ID:  {activity_id}")
    print(f"Date:         {activity_date}")

    # Parse laps
    laps = read_laps_from_csv(csv_path)
    if not laps:
        print("ERROR: No valid lap rows found in CSV.")
        return 1

    print(f"Laps parsed:  {len(laps)}")

    # Compute cardiac drift
    cardiac_drift = compute_cardiac_drift(laps)
    print(f"Cardiac drift: {cardiac_drift:.2f}%")

    if args.dry_run:
        print("\n[dry-run] No database writes performed.")
        for lap in laps:
            print(f"  Lap {lap['lap_number']:>3}: "
                  f"time={lap['lap_time_sec']}s  "
                  f"dist={lap['distance_km']:.2f}km  "
                  f"HR={lap['avg_hr']}")
        return 0

    # Resolve DB path using the same default as DatabaseManager
    home = Path.home()
    db_path = home / "Documents" / "TITAN" / "titan_core.db"

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_activity_laps_table(conn)
        _ensure_training_log_cardiac_drift_column(conn)

        inserted = _insert_laps(conn, laps, activity_id, activity_date, cardiac_drift)
        _update_activity_laps_drift(conn, activity_id, cardiac_drift)
        tl_updated = _update_training_log_drift(conn, activity_date, cardiac_drift)

        conn.commit()

        print(f"\nInserted {inserted} new lap row(s) into activity_laps.")
        print(f"Updated  {tl_updated} training_log row(s) with cardiac_drift={cardiac_drift:.2f}%.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
