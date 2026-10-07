"""Regenerate tests/fixtures/legacy_titan_v0.sql (T-PRA-30, plan task #19).

The fixture is an 8-week training history written by the last TITAN release
before the schema was versioned (commit 0358e23, PRAGMA user_version 0), using
that release's own DatabaseManager. To regenerate:

    git worktree add /tmp/titan-v0 0358e23
    PYTHONPATH=/tmp/titan-v0 python tests/fixtures/legacy_db_generate.py /tmp/titan-v0-out

Run it from outside the repository root so the current `titan` package is not
imported instead of the old one. Not collected by pytest (no test_ prefix).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from titan.core.database import DatabaseManager

START = date(2026, 1, 5)  # Monday
DAYS = 56
WEEK = ["EASY", "INTERVALS", "EASY", "TEMPO", "REST", "LONG_RUN", "RECOVERY"]
DIST = {"EASY": 8.0, "INTERVALS": 10.0, "TEMPO": 12.0, "LONG_RUN": 22.0, "RECOVERY": 5.0}
PACE = {"EASY": 330, "INTERVALS": 290, "TEMPO": 275, "LONG_RUN": 340, "RECOVERY": 360}
HR = {"EASY": 138, "INTERVALS": 158, "TEMPO": 162, "LONG_RUN": 145, "RECOVERY": 128}
RPE = {"EASY": 3, "INTERVALS": 8, "TEMPO": 7, "LONG_RUN": 6, "RECOVERY": 2}


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    db = DatabaseManager(db_name="legacy_v0.db", db_dir=out_dir)
    road = db.add_shoe("Pegasus 40", "DAILY", 800)
    race = db.add_shoe("Vaporfly 3", "RACE", 400)
    for i in range(DAYS):
        day = START + timedelta(days=i)
        iso = day.isoformat()
        week = i // 7
        db.save_daily_metric(
            iso,
            weight=76.4 - 0.05 * i,
            hrv=52.0 + (i % 7) - (3.0 if week == 5 else 0.0),
            rhr=46 + (i % 3),
            sleep_hours=7.0 + (i % 4) * 0.25,
            sleep_quality=70 + (i % 5) * 4,
            soreness=1 + (i % 3),
            fatigue=1 + (i % 4),
            mood=4,
        )
        session = WEEK[i % 7]
        if session == "REST":
            continue
        km = DIST[session] * (1.0 + 0.05 * (week % 4))
        shoe = race if session == "TEMPO" and week % 2 else road
        db.save_session(
            iso,
            session,
            round(km, 2),
            int(km * PACE[session]),
            avg_hr=HR[session],
            max_hr=HR[session] + 18,
            rpe=RPE[session],
            shoe_id=shoe,
            surface="ROAD",
            temperature_c=8.0 + (i % 10),
            # A manually logged run every second week has no Garmin id.
            garmin_activity_id=None if (session == "RECOVERY" and week % 2) else f"g{1000 + i}",
        )
        if session in {"INTERVALS", "LONG_RUN"}:
            db.save_hrr(iso, 32 + (i % 5), 48 + (i % 6))
        db.update_glycogen_debt(iso, round(0.1 * (i % 6), 2))
        db.save_governance_decision({
            "date": iso,
            "session_planned": session,
            "session_post_governance": "EASY" if week == 5 and session == "INTERVALS" else session,
            "locks_applied_json": "[]",
            "governance_clean": 1,
            "phase": "BUILD",
            "vlg_color": "GREEN",
            "apl_priority_vector_json": "{}",
            "lock_thresholds_active_json": "{}",
            "acwr": 1.05,
            "tsb_value": -8.5,
            "readiness_score": 72.0,
            "glycogen_debt": 0.2,
            "afi_value": 0.4,
            "outcome_rpe": RPE[session],
            "outcome_completed": 1,
            "outcome_session_type_actual": session,
            "outcome_notes": None,
        })
    db.log_override("2026-02-03", "EASY", "INTERVALS", "felt fresh")
    db.log_cs_performance("2026-01-24", 5000, 1140.0)
    db.log_cs_performance("2026-02-21", 3000, 640.0, surface="TRACK")
    db.save_personal_best(5.0, 1140, "2026-01-24", "Parkrun")
    db.save_personal_best(21.1, 5460, "2026-02-28", "Half marathon")
    db.close()
    return out_dir / "legacy_v0.db"


def main() -> None:
    path = build(Path(sys.argv[1]))
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    target = Path(__file__).with_name("legacy_titan_v0.sql")
    target.write_text("\n".join(conn.iterdump()) + "\n", encoding="utf-8")
    conn.close()
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
