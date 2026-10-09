"""Characterization tests for the DailyCoach morning routine (plan task 5).

These tests lock what ``run_morning_routine`` does today, before the class is split
(plan tasks 6-9). They build the coach with the worker's own composition root
(``titan.worker._build_daily_coach``), so the real ``GarminSync`` payload builder, every
real engine, the real weather fallback, the real Telegram formatting and the real SQLite
schema take part. Only the outside world is replaced:

- Garmin Connect: ``GarminSync.connect`` installs a fake API client that serves what a
  watch recorded up to the current (frozen) morning, in the raw shapes the sync code
  reads. On an outage morning ``connect`` fails, as it does when Garmin is down.
- Telegram: ``TitanTelegramBot.send_message`` records the text instead of sending it.
- Weather: ``_http_get`` raises, so the API uses its synthetic fallback.
- Time: frozen at 07:30 UTC on each morning of the scenario.

For each morning the test records the routine's return value, every Telegram text and the
sequence of structured events; at the end it records the rows of every table written.
The record is compared with a golden file in ``tests/fixtures/daily_coach_golden/``.
A refactor that changes any of it fails here, naming the first morning that changed.

To rewrite the golden files after an intended behavior change:

    TITAN_UPDATE_GOLDEN=1 python -m pytest --no-cov -q tests/test_daily_coach_characterization.py

and explain the change in the PR.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from freezegun import freeze_time

from titan.core.athlete import UniversalAthleteProfile
from titan.core.database import DatabaseManager

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "daily_coach_golden"
UPDATE_GOLDEN = os.environ.get("TITAN_UPDATE_GOLDEN") == "1"
START_DAY = date(2026, 3, 2)  # a Monday
RUN_TIME = "07:30:00"

# Row identity columns; replaced by a marker so the snapshot stays stable.
_VOLATILE_COLUMNS = frozenset({"id"})
# Timestamps written by SQLite's own clock (column defaults), which freezegun does not
# freeze. A timestamp on a scenario day came from the frozen Python clock and is kept.
_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]\d{2}:\d{2}:\d{2}")
# Tables the routine does not own (schema bookkeeping).
_SKIP_TABLES = frozenset({"schema_version", "sqlite_sequence"})


# ── What the watch recorded ─────────────────────────────────────────────────


@dataclass(frozen=True)
class WatchDay:
    """One day of watch data: the night before it, and an optional evening run."""

    rmssd: float
    rhr: int
    sleep_score: int
    sleep_hours: float
    run: str | None = None  # EASY / TEMPO / INTERVALS / LONG, run at 17:30


_RUNS = {
    #            minutes, km,   avg HR, max HR
    "EASY":      (40, 7.2, 140, 155),
    "TEMPO":     (50, 10.0, 162, 176),
    "INTERVALS": (55, 10.5, 166, 184),
    "LONG":      (95, 17.0, 146, 160),
}
_WEEK = ["EASY", "TEMPO", None, "EASY", "INTERVALS", None, "LONG"]


def normal_day(index: int) -> WatchDay:
    return WatchDay(
        rmssd=52.0 + (index % 3),
        rhr=49 + (index % 2),
        sleep_score=78 + (index % 4),
        sleep_hours=7.5,
        run=_WEEK[index % 7],
    )


CRASH_DAY = WatchDay(rmssd=29.0, rhr=61, sleep_score=41, sleep_hours=4.5)


class _FakeGarminClient:
    """Serves raw Garmin Connect data recorded on or before the current (frozen) day."""

    def __init__(self, recorded: dict[str, WatchDay]) -> None:
        self._recorded = recorded

    def _day(self, iso: str) -> WatchDay | None:
        if iso > datetime.now(UTC).date().isoformat():
            return None
        return self._recorded.get(iso)

    def get_activities_by_date(self, start: str, end: str, _activity_type: str = "") -> list[dict]:
        now = datetime.now(UTC).replace(tzinfo=None)
        activities = []
        for iso, day in sorted(self._recorded.items()):
            if day.run is None or not start <= iso <= end:
                continue
            started = datetime.fromisoformat(f"{iso}T17:30:00")
            if started > now:
                continue
            minutes, km, avg_hr, max_hr = _RUNS[day.run]
            activities.append({
                "activityId": int(iso.replace("-", "")),
                "activityName": f"{day.run.title()} run",
                "startTimeLocal": started.strftime("%Y-%m-%d %H:%M:%S"),
                "activityType": {"typeKey": "running"},
                "duration": float(minutes * 60),
                "distance": km * 1000.0,
                "averageHR": float(avg_hr),
                "maxHR": float(max_hr),
                "calories": minutes * 11,
                "elevationGain": 40.0,
            })
        return list(reversed(activities))  # newest first, like the API

    def get_weigh_ins(self, start: str, end: str) -> dict:
        return {"dateWeightList": [
            {"calendarDate": iso, "value": 70.0, "unitKey": "kg"}
            for iso in sorted(self._recorded)
            if start <= iso <= end and self._day(iso) is not None
        ]}

    def get_sleep_data(self, iso: str) -> dict:
        day = self._day(iso)
        if day is None:
            return {}
        seconds = int(day.sleep_hours * 3600)
        return {
            "dailySleepDTO": {
                "calendarDate": iso,
                "sleepTimeSeconds": seconds,
                "deepSleepSeconds": seconds // 5,
                "remSleepSeconds": seconds // 4,
                "sleepScores": {"overall": {"value": day.sleep_score}},
            },
        }

    def get_stats(self, iso: str) -> dict:
        # Daily summary; garminconnect models restingHeartRate on it (DailyStats).
        day = self._day(iso)
        if day is None:
            return {}
        return {"calendarDate": iso, "restingHeartRate": day.rhr, "totalSteps": 9000}

    def get_hrv_data(self, iso: str) -> dict:
        day = self._day(iso)
        if day is None:
            return {}
        return {"hrvSummary": {
            "calendarDate": iso,
            "lastNightAvg": day.rmssd,
            "lastNight5MinHigh": round(day.rmssd * 1.2, 1),
            "weeklyAvg": 53.0,
            "status": "BALANCED",
        }}


class _EventCapture(logging.Handler):
    """Collects the structured JSON events logged under ``titan``."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError):
            return
        if isinstance(payload, dict) and "action" in payload:
            self.events.append({"logger": record.name, **payload})


# ── Snapshot helpers ────────────────────────────────────────────────────────


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def _normalize_cell(column: str, value: Any, scenario_days: set[str]) -> Any:
    if column in _VOLATILE_COLUMNS:
        return "<volatile>"
    if isinstance(value, str):
        match = _TIMESTAMP.match(value)
        if match and match.group(1) not in scenario_days:
            return "<sqlite-clock>"
    return value


def _table_rows(db_path: Path, scenario_days: set[str]) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        snapshot: dict[str, list[dict[str, Any]]] = {}
        for table in tables:
            if table in _SKIP_TABLES:
                continue
            rows = [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')]  # noqa: S608
            if not rows:
                continue
            normalized = [
                {k: _normalize_cell(k, v, scenario_days) for k, v in row.items()}
                for row in rows
            ]
            normalized.sort(key=lambda r: json.dumps(r, default=str, sort_keys=True))
            snapshot[table] = normalized
        return _jsonable(snapshot)
    finally:
        conn.close()


def _compare_with_golden(name: str, record: dict[str, Any]) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    text = json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if UPDATE_GOLDEN:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"golden file missing: {path} (run with TITAN_UPDATE_GOLDEN=1)"
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = json.loads(text)
    for day_expected, day_actual in zip(expected["days"], actual["days"], strict=True):
        # Compare morning by morning so a failure names the first one that changed.
        assert day_actual == day_expected, f"{name}: morning {day_expected['date']} changed"
    assert actual["tables"] == expected["tables"], f"{name}: database rows changed"


# ── Scenario runner ─────────────────────────────────────────────────────────


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import titan.integrations.garmin_sync as garmin_module
    import titan.integrations.telegram_bot as telegram_module
    import titan.integrations.weather_api as weather_module

    for var, value in {
        "ATHLETE_NAME": "Characterization",
        "ATHLETE_AGE": "38",
        "ATHLETE_WEIGHT": "70",
        "ATHLETE_HEIGHT": "176",
        "ATHLETE_MAX_HR": "188",
        "ATHLETE_THRESHOLD_HR": "168",
        "TRAINING_PHASE": "BUILD",
        "TRAINING_GOAL": "10K",
    }.items():
        monkeypatch.setenv(var, value)

    state: dict[str, Any] = {"recorded": {}, "outage": set(), "sent": []}

    def _connect(self) -> bool:
        if datetime.now(UTC).date().isoformat() in state["outage"]:
            self.last_connect_error = "Garmin Connect unreachable (characterization outage)"
            return False
        self.client = _FakeGarminClient(state["recorded"])
        self.is_connected = True
        return True

    def _record_send(self, text: str, parse_mode: str = "Markdown") -> bool:
        state["sent"].append(text)
        return True

    def _no_network(*_args, **_kwargs):
        raise ConnectionError("network disabled in characterization tests")

    monkeypatch.setattr(garmin_module.GarminSync, "connect", _connect)
    monkeypatch.setattr(telegram_module.TitanTelegramBot, "send_message", _record_send)
    monkeypatch.setattr(weather_module, "_http_get", _no_network)

    capture = _EventCapture()
    titan_logger = logging.getLogger("titan")
    old_level = titan_logger.level
    titan_logger.setLevel(logging.DEBUG)
    titan_logger.addHandler(capture)

    state.update(db_path=tmp_path / "characterization.db", capture=capture, monkeypatch=monkeypatch)
    yield state

    titan_logger.removeHandler(capture)
    titan_logger.setLevel(old_level)


def _run_scenario(world: dict[str, Any], watch: list[WatchDay | None], *,
                  soreness: int | None = None, weekly_plan: bool = False,
                  before_morning=None) -> dict[str, Any]:
    """Run one morning per entry of *watch*; ``None`` is a Garmin outage morning."""
    from titan.worker import _build_daily_coach

    world["recorded"].clear()
    world["outage"].clear()
    for index, day in enumerate(watch):
        iso = (START_DAY + timedelta(days=index)).isoformat()
        if day is None:
            world["outage"].add(iso)
        else:
            world["recorded"][iso] = day

    mornings: list[dict[str, Any]] = []
    for index in range(len(watch)):
        today = START_DAY + timedelta(days=index)
        with freeze_time(f"{today.isoformat()} {RUN_TIME}"):
            db = DatabaseManager(db_name=world["db_path"].name, db_dir=world["db_path"].parent)
            if before_morning is not None:
                before_morning(index, db)
            # A new coach every morning, as the worker builds one per routine.
            coach = _build_daily_coach(db)
            if weekly_plan:
                # The console (titan/main.py) generates a plan in-process; the worker does not.
                coach.weekly_planner.generate_weekly_plan(
                    athlete_profile=UniversalAthleteProfile.from_env().to_dict(), phase="BUILD",
                )
            world["sent"].clear()
            world["capture"].events.clear()
            try:
                outcome: Any = coach.run_morning_routine(soreness=soreness)
            except Exception as exc:  # recorded, not hidden: a raise is behavior too
                outcome = {"raised": type(exc).__name__, "message": str(exc)}
            mornings.append(_jsonable({
                "date": today.isoformat(),
                "returned": outcome,
                "telegram": list(world["sent"]),
                "events": list(world["capture"].events),
            }))
    scenario_days = {m["date"] for m in mornings}
    return {"days": mornings, "tables": _table_rows(world["db_path"], scenario_days)}


# ── Scenarios ───────────────────────────────────────────────────────────────


def test_two_weeks_as_the_worker_runs_them(world):
    """14 mornings with the worker's defaults; an autonomic crash on morning 10."""
    watch = [CRASH_DAY if i == 9 else normal_day(i) for i in range(14)]
    _compare_with_golden("two_weeks_worker", _run_scenario(world, watch))


def test_three_weeks_with_weekly_plan(world):
    """21 mornings with low soreness and a generated weekly plan, as in the console.

    The worker never generates a plan, so on its own it always prescribes the planner's
    fallback session; this scenario covers the gates acting on planned quality sessions.
    """
    watch = [normal_day(i) for i in range(21)]
    _compare_with_golden(
        "three_weeks_weekly_plan",
        _run_scenario(world, watch, soreness=1, weekly_plan=True),
    )


def test_garmin_outage_then_stale_data(world):
    """Garmin is down from Thursday to Saturday: empty sync, then stale and capped (INV-24)."""
    watch = [normal_day(0), normal_day(1), normal_day(2), None, None, None, normal_day(6)]
    _compare_with_golden(
        "garmin_outage",
        _run_scenario(world, watch, soreness=1, weekly_plan=True),
    )


def test_persistence_failure_morning(world):
    """The DB write of Thursday (plan: TEMPO) fails: degraded mode, conservative session."""

    def _break_writes_on_thursday(index: int, db: DatabaseManager) -> None:
        if index == 3:
            def _fail(*_args, **_kwargs):
                raise sqlite3.OperationalError("disk I/O error (characterization)")

            world["monkeypatch"].setattr(db, "save_daily_metric", _fail)

    watch = [normal_day(i) for i in range(5)]
    _compare_with_golden(
        "persistence_failure",
        _run_scenario(
            world, watch, soreness=1, weekly_plan=True, before_morning=_break_writes_on_thursday,
        ),
    )
