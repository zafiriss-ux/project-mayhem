"""
One-time historical import from Garmin Connect CSV export.

Usage:
    python scripts/import_garmin_csv.py \\
      --csv Activities.csv \\
      [--dry-run]

Reads Garmin CSV, maps columns to training_log schema,
inserts via save_session() with INSERT OR IGNORE semantics
(safe to run multiple times — idempotent via synthetic
garmin_activity_id derived from date + distance + duration).
"""

import argparse
import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# CSV column names (Garmin Greek locale export)
COL_TYPE     = "Τύπος δραστηριότητας"
COL_DATE     = "Ημερομηνία"
COL_DISTANCE = "Απόσταση"
COL_DURATION = "Ώρα"
COL_AVG_HR   = "Μέσοι ΚΠ"
COL_MAX_HR   = "Μέγιστοι ΚΠ"
COL_TITLE    = "Τίτλος"


def parse_distance(s: str) -> float:
    """'16,10' → 16.10  (Garmin uses comma as decimal separator)"""
    if not s or s == "--":
        return 0.0
    return float(s.replace(",", "."))


def parse_duration(s: str) -> int:
    """'01:17:40' → 4660 seconds"""
    if not s or s == "--":
        return 0
    parts = s.split(":")
    if len(parts) == 3:
        h, m, sec = parts
        return int(h) * 3600 + int(m) * 60 + int(sec)
    if len(parts) == 2:
        m, sec = parts
        return int(m) * 60 + int(sec)
    return 0


def parse_hr(s: str) -> int:
    """'144' → 144; '21,8' → 21; '--' → 0"""
    if not s or s == "--":
        return 0
    return int(float(s.replace(",", ".")))


def infer_session_type(title: str, distance: float, duration_sec: int) -> str:  # noqa: ARG001
    """Infer session type from title keywords and distance."""
    t = title.lower()
    if any(w in t for w in ["intervals", "interval", "επαναλ", "vo2"]):
        return "INTERVALS"
    if any(w in t for w in ["tempo", "τεμπο", "lt", "threshold"]):
        return "TEMPO"
    if distance >= 18.0:
        return "LONG_RUN"
    return "EASY"


def compute_trimp_simple(duration_sec: int, avg_hr: int, max_hr: int) -> float:
    """Simple TRIMP: duration_min × (avg_hr / max_hr)"""
    if avg_hr <= 0 or max_hr <= 0:
        return 0.0
    hr_ratio = avg_hr / max_hr
    return round((duration_sec / 60) * hr_ratio, 1)


def _synthetic_garmin_id(date_str: str, distance: float, duration_sec: int) -> str:
    """Stable synthetic garmin_activity_id for CSV-imported rows.

    Ensures idempotency: same row hashes to the same ID on every import run,
    so the UNIQUE INDEX on garmin_activity_id prevents duplicate inserts.
    """
    key = f"csv:{date_str}:{distance:.3f}:{duration_sec}"
    return "csv_" + hashlib.sha1(key.encode()).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import historical Garmin CSV activities into TITAN DB."
    )
    parser.add_argument("--csv", required=True, help="Path to Activities.csv")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print parsed rows without writing to DB")
    args = parser.parse_args()

    import os

    from dotenv import load_dotenv

    load_dotenv(Path.home() / "Documents" / "TITAN" / ".env")

    from titan.core.athlete import UniversalAthleteProfile
    from titan.core.database import DatabaseManager

    athlete = UniversalAthleteProfile.from_env()
    athlete_max_hr = athlete.max_hr

    db_path = os.environ.get(
        "DATABASE_PATH",
        str(Path.home() / "Documents" / "TITAN" / "titan_core.db"),
    )

    db = DatabaseManager(db_path)

    inserted = 0
    skipped = 0
    errors = 0

    with open(args.csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                activity_type = row.get(COL_TYPE, "")
                if "τρέξ" not in activity_type.lower() and \
                   "run" not in activity_type.lower():
                    skipped += 1
                    continue

                date_str = row[COL_DATE][:10]
                distance = parse_distance(row.get(COL_DISTANCE, "0"))
                duration = parse_duration(row.get(COL_DURATION, "0"))
                avg_hr = parse_hr(row.get(COL_AVG_HR, "0"))
                max_hr_act = parse_hr(row.get(COL_MAX_HR, "0"))
                title = row.get(COL_TITLE, "")

                session_type = infer_session_type(title, distance, duration)
                trimp = compute_trimp_simple(duration, avg_hr, athlete_max_hr)
                synthetic_id = _synthetic_garmin_id(date_str, distance, duration)

                if args.dry_run:
                    print(
                        f"[DRY] {date_str} {session_type:12s} "
                        f"{distance:5.1f}km  TRIMP={trimp:5.1f}  "
                        f"avg_hr={avg_hr}  id={synthetic_id}"
                    )
                    inserted += 1
                    continue

                db.save_session(
                    date=date_str,
                    session_type=session_type,
                    distance_km=distance,
                    duration_sec=duration,
                    avg_hr=avg_hr if avg_hr > 0 else None,
                    max_hr=max_hr_act if max_hr_act > 0 else None,
                    training_load=int(trimp),
                    athlete_id="owner",
                    garmin_activity_id=synthetic_id,
                    notes=f"Imported from CSV: {title}",
                )
                inserted += 1

            except Exception as e:
                print(f"Error row: {e}")
                errors += 1

    print("\nImport complete:")
    print(f"  Inserted : {inserted}")
    print(f"  Skipped (non-running): {skipped}")
    print(f"  Errors   : {errors}")

    if not args.dry_run and inserted > 0:
        print(f"\n✅ {inserted} activities imported to {db_path}")
        print("  CTL/ATL will be recalculated on next DailyCoach run.")


if __name__ == "__main__":
    main()
