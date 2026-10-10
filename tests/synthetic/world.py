"""Synthetic athletes and scenarios run through the worker's real morning (plan task 12).

The plan (``docs/validation/synthetic-athlete-validation.md``) asks for the production path
with only the outside world replaced. Each morning here is ``titan.worker._run_morning``:
the worker's composition root, its weekly plan, the real Garmin sync code, every real
engine, the real governance and the real SQLite schema. Replaced, as in the
characterization tests of task 5:

- Garmin Connect: ``GarminSync.connect`` installs a fake client serving the raw shapes the
  sync code reads, for what the watch recorded up to the current (frozen) morning.
- Telegram: ``send_message`` records the text.
- Weather: ``_http_get`` answers as Open-Meteo for a mild spring morning (12 °C, 70%).
- Time: frozen at 07:30 UTC, for Python and for SQLite. freezegun does not reach SQLite's
  own clock, so ``date()`` and ``datetime()`` are replaced on each morning's connection by
  functions that read the frozen clock (``_freeze_sqlite_clock``); otherwise the
  load-history query (``date('now', '-42 days')``) would look at the real date.
  The last morning is a fixed Saturday, so every run sees the same weekly plan.

Every athlete gets ``HISTORY_DAYS`` mornings of ordinary training (six weeks, the CTL
window), saved once as a database snapshot. A scenario then rewrites the last
``SCENARIO_DAYS`` days of watch data and runs those mornings from a copy of the snapshot.
"""
from __future__ import annotations

import copy
import json
import logging
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from freezegun import freeze_time

HISTORY_DAYS = 42      # CTL_DECAY_DAYS: the whole chronic window is filled
SCENARIO_DAYS = 7      # an acute (ACWR) week
TOTAL_DAYS = HISTORY_DAYS + SCENARIO_DAYS
RUN_TIME = "07:30:00"
LAST_MORNING = date(2026, 3, 28)  # a Saturday


# ── What the watch recorded ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Run:
    kind: str                   # EASY / TEMPO / INTERVALS / LONG
    minutes: float
    km: float
    avg_hr: int
    max_hr: int
    duration_in_minutes: bool = False   # unit error: Garmin "duration" given in minutes


@dataclass(frozen=True)
class Night:
    """The night before a morning (None fields: the watch has no such data) and the evening run."""

    rmssd: float | None
    rhr: int | None
    sleep_score: int | None
    sleep_hours: float | None
    run: Run | None = None
    sleep_in_minutes: bool = False      # unit error: "sleepTimeSeconds" given in minutes


@dataclass(frozen=True)
class Profile:
    key: str
    description: str
    sex: str
    age: int
    weight_kg: float
    height_cm: float
    max_hr: int
    rest_hr: int
    threshold_hr: int
    phase: str
    goal: str
    rmssd: float
    easy_pace_s_km: float
    week: tuple[str | None, ...]            # Monday..Sunday
    weekly_growth: float = 1.0              # volume factor per week
    taper_last_days: int = 0                # history days at half volume before the scenario

    def env(self) -> dict[str, str]:
        return {
            "ATHLETE_NAME": f"Synthetic {self.key}",
            "ATHLETE_AGE": str(self.age),
            "ATHLETE_WEIGHT": str(self.weight_kg),
            "ATHLETE_HEIGHT": str(self.height_cm),
            "ATHLETE_MAX_HR": str(self.max_hr),
            "ATHLETE_THRESHOLD_HR": str(self.threshold_hr),
            "TRAINING_PHASE": self.phase,
            "TRAINING_GOAL": self.goal,
        }


_MINUTES = {"EASY": 40, "TEMPO": 45, "INTERVALS": 50, "LONG": 90}
_HR_FRACTION = {"EASY": 0.72, "LONG": 0.75, "TEMPO": 0.86, "INTERVALS": 0.89}
_PACE_FACTOR = {"EASY": 1.0, "LONG": 1.04, "TEMPO": 0.85, "INTERVALS": 0.83}


def make_run(profile: Profile, kind: str, minutes: float | None = None) -> Run:
    minutes = float(minutes if minutes is not None else _MINUTES[kind])
    pace = profile.easy_pace_s_km * _PACE_FACTOR[kind]
    avg = round(profile.rest_hr + (profile.max_hr - profile.rest_hr) * _HR_FRACTION[kind])
    return Run(
        kind=kind,
        minutes=round(minutes, 1),
        km=round(minutes * 60 / pace, 2),
        avg_hr=avg,
        max_hr=min(profile.max_hr, avg + round(0.06 * profile.max_hr)),
    )


def ordinary_night(profile: Profile, index: int) -> Night:
    """A normal day ``index`` (0 = first history day) of this athlete."""
    week_number = index // 7
    factor = profile.weekly_growth ** week_number
    if profile.taper_last_days and index >= HISTORY_DAYS - profile.taper_last_days:
        factor *= 0.5
    kind = profile.week[index % 7]
    run = make_run(profile, kind, _MINUTES[kind] * factor) if kind else None
    return Night(
        rmssd=round(profile.rmssd * (1 + 0.03 * ((index % 5) - 2)), 1),
        rhr=profile.rest_hr + (index % 3) - 1,
        sleep_score=76 + (index % 4) * 2,
        sleep_hours=7.4 + 0.1 * (index % 3),
        run=run,
    )


# ── Six athletes (plan: sex, age, max and resting HR, history, recovery differ) ──

PROFILES: tuple[Profile, ...] = (
    Profile("novice_f", "new runner, three easy runs a week", "F", 29, 58.0, 165.0,
            196, 60, 178, "BASE", "5K", 48.0, 405.0,
            ("EASY", None, "EASY", None, None, "EASY", None)),
    Profile("steady_m", "stable club runner, five runs a week", "M", 38, 70.0, 176.0,
            188, 49, 168, "BUILD", "10K", 55.0, 330.0,
            ("EASY", "TEMPO", None, "EASY", "INTERVALS", None, "LONG")),
    Profile("loading_m", "masters runner adding 8% a week", "M", 47, 78.0, 181.0,
            176, 52, 160, "BUILD", "HM", 42.0, 360.0,
            ("EASY", "TEMPO", "EASY", None, "INTERVALS", None, "LONG"), weekly_growth=1.08),
    Profile("taper_f", "marathoner in her last ten days of taper", "F", 34, 55.0, 168.0,
            190, 45, 174, "TAPER", "M", 68.0, 300.0,
            ("EASY", "TEMPO", "EASY", "EASY", "INTERVALS", None, "LONG"), taper_last_days=10),
    Profile("senior_m", "61-year-old with low HRV and modest volume", "M", 61, 72.0, 172.0,
            160, 57, 145, "BASE", "10K", 28.0, 380.0,
            ("EASY", None, "TEMPO", None, "EASY", None, "LONG")),
    Profile("elite_f", "high-volume runner, high HRV, peaking", "F", 26, 50.0, 163.0,
            200, 40, 185, "PEAK", "5K", 92.0, 255.0,
            ("EASY", "INTERVALS", "EASY", "TEMPO", "EASY", "EASY", "LONG")),
)


# ── Scenarios: what changes in the last SCENARIO_DAYS days ──────────────────

Nights = list[Night | None]   # None: Garmin unreachable that morning


@dataclass(frozen=True)
class Scenario:
    key: str
    group: str
    description: str
    change: Callable[[Profile, Nights], Nights]
    risk: bool = False          # the data point to more stress than an ordinary day
    stale_from: int | None = None   # Garmin reachable but serving nothing from this day on


def _last(nights: Nights, n: int, fn: Callable[[Night], Night]) -> Nights:
    out = list(nights)
    for i in range(len(out) - n, len(out)):
        if out[i] is not None:
            out[i] = fn(out[i])
    return out


def _bad_sleep(n: Night) -> Night:
    return replace(n, sleep_score=34, sleep_hours=4.2)


def _high_rhr(profile: Profile) -> Callable[[Night], Night]:
    return lambda n: replace(n, rhr=profile.rest_hr + 11)


def _low_hrv(profile: Profile) -> Callable[[Night], Night]:
    return lambda n: replace(n, rmssd=round(profile.rmssd * 0.6, 1))


def _with_runs(profile: Profile, nights: Nights, plan: dict[int, tuple[str, float] | None]) -> Nights:
    """Replace the runs of scenario day offsets (0 = first scenario day)."""
    out = list(nights)
    first = len(out) - SCENARIO_DAYS
    for offset, spec in plan.items():
        night = out[first + offset]
        if night is None:
            continue
        run = make_run(profile, spec[0], spec[1]) if spec else None
        out[first + offset] = replace(night, run=run)
    return out


def _acwr_spike(p: Profile, nights: Nights) -> Nights:
    # Twice the usual weekly time, every day, in the acute week.
    return _with_runs(p, nights, {i: ("EASY" if i % 2 else "LONG", 100.0) for i in range(SCENARIO_DAYS - 1)})


def _intensity_streak(p: Profile, nights: Nights) -> Nights:
    return _with_runs(p, nights, {2: ("INTERVALS", 55), 3: ("TEMPO", 50), 4: ("INTERVALS", 55), 5: ("TEMPO", 50)})


def _glycogen(p: Profile, nights: Nights) -> Nights:
    return _with_runs(p, nights, {3: ("LONG", 150), 4: ("INTERVALS", 70), 5: ("LONG", 150)})


def _race_taper(p: Profile, nights: Nights) -> Nights:
    return _with_runs(p, nights, {0: ("EASY", 30), 1: ("TEMPO", 25), 2: None, 3: ("EASY", 25),
                                  4: None, 5: ("EASY", 20)})


def _duration_in_minutes(p: Profile, nights: Nights) -> Nights:
    out = _with_runs(p, nights, {SCENARIO_DAYS - 2: ("EASY", 40)})
    night = out[-2]
    if night is not None and night.run is not None:
        out[-2] = replace(night, run=replace(night.run, duration_in_minutes=True))
    return out


def _outage(n: int) -> Callable[[Profile, Nights], Nights]:
    def change(_p: Profile, nights: Nights) -> Nights:
        return nights[: len(nights) - n] + [None] * n
    return change


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("ordinary_week", "normal", "a week like the six before it", lambda _p, n: n),
    Scenario("race_taper", "normal", "volume halved with one short tempo, as before a race", _race_taper),
    Scenario("bad_sleep_1", "recovery", "one night of 4.2 h, score 34",
             lambda _p, n: _last(n, 1, _bad_sleep), risk=True),
    Scenario("bad_sleep_3", "recovery", "three nights of 4.2 h, score 34",
             lambda _p, n: _last(n, 3, _bad_sleep), risk=True),
    Scenario("high_rhr", "recovery", "resting HR 11 bpm above baseline",
             lambda p, n: _last(n, 1, _high_rhr(p)), risk=True),
    Scenario("low_hrv", "recovery", "RMSSD 40% under baseline",
             lambda p, n: _last(n, 1, _low_hrv(p)), risk=True),
    Scenario("recovery_combo", "recovery", "bad sleep, high resting HR and low HRV together",
             lambda p, n: _last(n, 1, lambda x: _low_hrv(p)(_high_rhr(p)(_bad_sleep(x)))), risk=True),
    Scenario("acwr_spike", "load", "100 min every day of the acute week", _acwr_spike, risk=True),
    Scenario("intensity_streak", "load", "four hard sessions in a row", _intensity_streak, risk=True),
    Scenario("glycogen_drain", "load", "150' long, 70' intervals, 150' long on consecutive days",
             _glycogen, risk=True),
    Scenario("garmin_out_1", "data", "Garmin unreachable on the last morning", _outage(1)),
    Scenario("garmin_out_3", "data", "Garmin unreachable on the last three mornings", _outage(3)),
    Scenario("stale_data", "data", "Garmin reachable but has nothing for the last three days",
             lambda _p, n: n, stale_from=SCENARIO_DAYS - 3),
    Scenario("no_sleep_data", "data", "the last night has HRV and RHR but no sleep record",
             lambda _p, n: _last(n, 1, lambda x: replace(x, sleep_score=None, sleep_hours=None))),
    Scenario("no_hrv_data", "data", "the last night has sleep and RHR but no HRV",
             lambda _p, n: _last(n, 1, lambda x: replace(x, rmssd=None))),
    Scenario("out_of_bounds", "extreme", "RMSSD 0 and resting HR 250 (sensor artefacts)",
             lambda _p, n: _last(n, 1, lambda x: replace(x, rmssd=0.0, rhr=250))),
    Scenario("contradictory", "extreme", "9 h of sleep, score 95, with resting HR 20 above baseline",
             lambda p, n: _last(n, 1, lambda x: replace(x, sleep_hours=9.0, sleep_score=95,
                                                         rhr=p.rest_hr + 20)), risk=True),
    Scenario("sleep_in_minutes", "extreme", "the sleep duration arrives in minutes instead of seconds",
             lambda _p, n: _last(n, 1, lambda x: replace(x, sleep_in_minutes=True))),
    Scenario("duration_in_minutes", "extreme", "yesterday's 40' run arrives with its duration in minutes",
             lambda p, n: _duration_in_minutes(p, n)),
)


# ── The fake Garmin Connect client ──────────────────────────────────────────


class FakeGarminClient:
    """Serves raw Garmin Connect data recorded on or before the current (frozen) day."""

    def __init__(self, recorded: dict[str, Night], stale_from: str | None) -> None:
        self._recorded = recorded
        self._stale_from = stale_from

    def _day(self, iso: str) -> Night | None:
        if iso > datetime.now(UTC).date().isoformat():
            return None
        if self._stale_from is not None and iso >= self._stale_from:
            return None
        return self._recorded.get(iso)

    def get_activities_by_date(self, start: str, end: str, _activity_type: str = "") -> list[dict]:
        now = datetime.now(UTC).replace(tzinfo=None)
        activities = []
        for iso in sorted(self._recorded):
            night = self._day(iso)
            if night is None or night.run is None or not start <= iso <= end:
                continue
            started = datetime.fromisoformat(f"{iso}T17:30:00")
            if started > now:
                continue
            run = night.run
            duration = run.minutes if run.duration_in_minutes else run.minutes * 60
            activities.append({
                "activityId": int(iso.replace("-", "")),
                "activityName": f"{run.kind.title()} run",
                "startTimeLocal": started.strftime("%Y-%m-%d %H:%M:%S"),
                "activityType": {"typeKey": "running"},
                "duration": float(duration),
                "distance": run.km * 1000.0,
                "averageHR": float(run.avg_hr),
                "maxHR": float(run.max_hr),
                "calories": int(run.minutes * 11),
                "elevationGain": 40.0,
            })
        return list(reversed(activities))

    def get_weigh_ins(self, start: str, end: str) -> dict:
        return {"dateWeightList": [
            {"calendarDate": iso, "value": _WEIGHT[0], "unitKey": "kg"}
            for iso in sorted(self._recorded)
            if start <= iso <= end and self._day(iso) is not None
        ]}

    def get_sleep_data(self, iso: str) -> dict:
        night = self._day(iso)
        if night is None or night.sleep_hours is None:
            return {}
        seconds = int(night.sleep_hours * 3600)
        reported = seconds // 60 if night.sleep_in_minutes else seconds
        return {"dailySleepDTO": {
            "calendarDate": iso,
            "sleepTimeSeconds": reported,
            "deepSleepSeconds": reported // 5,
            "remSleepSeconds": reported // 4,
            "sleepScores": {"overall": {"value": night.sleep_score}},
        }}

    def get_stats(self, iso: str) -> dict:
        night = self._day(iso)
        if night is None or night.rhr is None:
            return {}
        return {"calendarDate": iso, "restingHeartRate": night.rhr, "totalSteps": 9000}

    def get_hrv_data(self, iso: str) -> dict:
        night = self._day(iso)
        if night is None or night.rmssd is None:
            return {}
        return {"hrvSummary": {
            "calendarDate": iso,
            "lastNightAvg": night.rmssd,
            "lastNight5MinHigh": round(night.rmssd * 1.2, 1),
            "weeklyAvg": night.rmssd,
            "status": "BALANCED",
        }}


_WEIGHT = [70.0]  # set per athlete before a run


# ── Running a scenario ──────────────────────────────────────────────────────


def scenario_dates(today: date) -> list[date]:
    first = today - timedelta(days=TOTAL_DAYS - 1)
    return [first + timedelta(days=i) for i in range(TOTAL_DAYS)]


@dataclass
class Morning:
    date: str
    planned: dict[str, Any] | None
    session: dict[str, Any] | None
    payload: dict[str, Any] | None
    trace: dict[str, Any] | None
    telegram: list[str]
    metrics_row: dict[str, Any] | None
    events: list[dict[str, Any]]
    raised: str | None = None


@dataclass
class Outcome:
    profile: Profile
    scenario: Scenario
    nights: Nights
    mornings: list[Morning] = field(default_factory=list)
    runs: list[dict[str, Any]] = field(default_factory=list)   # training_log of the scenario week

    @property
    def last(self) -> Morning:
        return self.mornings[-1]


class _EventCapture(logging.Handler):
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


class _FakeWeatherResponse:
    """Open-Meteo for a mild spring morning: 12 °C, 70% humidity (dew point about 7 °C)."""

    def __init__(self, now: datetime) -> None:
        start = now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        hours = [(start + timedelta(hours=i)).isoformat() for i in range(48)]
        self._payload = {
            "results": [{"latitude": 37.98, "longitude": 23.73}],   # geocoding: Athens
            "current": {"temperature_2m": 12.0, "relative_humidity_2m": 70,
                        "weather_code": 1, "wind_speed_10m": 8.0},
            "hourly": {"time": hours, "temperature_2m": [12.0] * 48,
                       "relative_humidity_2m": [70] * 48, "weather_code": [1] * 48,
                       "wind_speed_10m": [8.0] * 48},
        }

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class World:
    """Patches the outside world once; runs athletes and scenarios on demand."""

    def __init__(self, monkeypatch, workdir: Path, today: date | None = None) -> None:  # noqa: ANN001
        import titan.integrations.garmin_sync as garmin_module
        import titan.integrations.telegram_bot as telegram_module
        import titan.integrations.weather_api as weather_module
        from titan.features.weekly_planner import WeeklyPlanGenerator
        from titan.orchestration.daily_coach import DailyCoach

        self.monkeypatch = monkeypatch
        self.workdir = workdir
        self.today = today or LAST_MORNING
        self.dates = scenario_dates(self.today)
        self._recorded: dict[str, Night] = {}
        self._outage: set[str] = set()
        self._stale_from: str | None = None
        self._sent: list[str] = []
        self._results: list[Any] = []
        self._planned: list[dict[str, Any]] = []
        self._snapshots: dict[str, Path] = {}
        world = self

        def _connect(gs) -> bool:  # noqa: ANN001
            if datetime.now(UTC).date().isoformat() in world._outage:
                gs.last_connect_error = "Garmin Connect unreachable (synthetic outage)"
                return False
            gs.client = FakeGarminClient(world._recorded, world._stale_from)
            gs.is_connected = True
            return True

        def _record_send(_bot, text: str, parse_mode: str = "Markdown") -> bool:  # noqa: ANN001
            world._sent.append(text)
            return True

        def _weather(*_args, **_kwargs):
            return _FakeWeatherResponse(datetime.now(UTC))

        original_pipeline = DailyCoach._decision_pipeline

        def _spy_pipeline(coach, *args, **kwargs):  # noqa: ANN001
            result = original_pipeline(coach, *args, **kwargs)
            world._results.append(result)
            return result

        original_today = WeeklyPlanGenerator.get_today_session

        def _spy_today(planner, *args, **kwargs):  # noqa: ANN001
            session = original_today(planner, *args, **kwargs)
            world._planned.append(copy.deepcopy(dict(session)))
            return session

        monkeypatch.setattr(garmin_module.GarminSync, "connect", _connect)
        monkeypatch.setattr(WeeklyPlanGenerator, "get_today_session", _spy_today)
        monkeypatch.setattr(telegram_module.TitanTelegramBot, "send_message", _record_send)
        monkeypatch.setattr(weather_module, "_http_get", _weather)
        monkeypatch.setattr(DailyCoach, "_decision_pipeline", _spy_pipeline)

        self.capture = _EventCapture()
        logger = logging.getLogger("titan")
        self._old_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self.capture)

    def close(self) -> None:
        logger = logging.getLogger("titan")
        logger.removeHandler(self.capture)
        logger.setLevel(self._old_level)

    # -- internals --

    def _load(self, profile: Profile, nights: Nights, stale_from: int | None) -> None:
        for var, value in profile.env().items():
            self.monkeypatch.setenv(var, value)
        _WEIGHT[0] = profile.weight_kg
        self._recorded.clear()
        self._outage.clear()
        for day, night in zip(self.dates, nights, strict=True):
            if night is None:
                self._outage.add(day.isoformat())
            else:
                self._recorded[day.isoformat()] = night
        self._stale_from = self.dates[HISTORY_DAYS + stale_from].isoformat() if stale_from is not None else None

    def _morning(self, db_path: Path, day: date) -> Morning:
        from titan.core.database import DatabaseManager
        from titan.worker import _run_morning

        self._sent.clear()
        self._results.clear()
        self._planned.clear()
        self.capture.events.clear()
        raised = None
        with freeze_time(f"{day.isoformat()} {RUN_TIME}"):
            db = DatabaseManager(db_name=db_path.name, db_dir=db_path.parent)
            _freeze_sqlite_clock(db.conn)
            try:
                _run_morning(db, athlete_id="owner")
            except Exception as exc:  # a raise is an outcome too
                raised = f"{type(exc).__name__}: {exc}"
            row = _metrics_row(db, day.isoformat())
            db.close()
        result = self._results[-1] if self._results else None
        return Morning(
            date=day.isoformat(),
            planned=_jsonable(self._planned[0]) if self._planned else None,
            session=copy.deepcopy(dict(result.session_plan)) if result else None,
            payload=_jsonable(dict(result.coaching_payload)) if result else None,
            trace=_jsonable({k: v for k, v in result.decision_trace.items() if k != "apl_result"})
            if result else None,
            telegram=list(self._sent),
            metrics_row=row,
            events=list(self.capture.events),
            raised=raised,
        )

    def _snapshot(self, profile: Profile) -> Path:
        if profile.key in self._snapshots:
            return self._snapshots[profile.key]
        nights: Nights = [ordinary_night(profile, i) for i in range(TOTAL_DAYS)]
        self._load(profile, nights, None)
        db_path = self.workdir / f"history_{profile.key}.db"
        for day in self.dates[:HISTORY_DAYS]:
            self._morning(db_path, day)
        self._snapshots[profile.key] = db_path
        return db_path

    # -- public --

    def run(self, profile: Profile, scenario: Scenario, tag: str = "") -> Outcome:
        snapshot = self._snapshot(profile)
        nights: Nights = [ordinary_night(profile, i) for i in range(TOTAL_DAYS)]
        history, window = nights[:HISTORY_DAYS], nights[HISTORY_DAYS:]
        window = scenario.change(profile, history + window)[HISTORY_DAYS:]
        nights = history + window
        db_path = self.workdir / f"{profile.key}_{scenario.key}{tag}.db"
        shutil.copyfile(snapshot, db_path)
        self._load(profile, nights, scenario.stale_from)
        outcome = Outcome(profile, scenario, nights)
        for day in self.dates[HISTORY_DAYS:]:
            outcome.mornings.append(self._morning(db_path, day))
        outcome.runs = _training_rows(db_path, self.dates[HISTORY_DAYS].isoformat())
        return outcome


def _sqlite_time(value: Any, mods: tuple[Any, ...]) -> datetime:
    """The two forms the schema and queries use: ``('now')`` and ``('now', '-N days')``."""
    base = datetime.now(UTC).replace(tzinfo=None) if value == "now" else datetime.fromisoformat(str(value))
    for mod in mods:
        amount, unit = str(mod).split()
        if not unit.startswith("day"):
            raise ValueError(f"unsupported SQLite modifier in synthetic validation: {mod!r}")
        base += timedelta(days=float(amount))
    return base


def _freeze_sqlite_clock(conn) -> None:  # noqa: ANN001
    conn.create_function("date", -1, lambda v, *m: _sqlite_time(v, m).date().isoformat())
    conn.create_function("datetime", -1, lambda v, *m: _sqlite_time(v, m).strftime("%Y-%m-%d %H:%M:%S"))


def _training_rows(db_path: Path, since: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM training_log WHERE date >= ? ORDER BY date", (since,))]
    finally:
        conn.close()


def _metrics_row(db, iso: str) -> dict[str, Any] | None:  # noqa: ANN001
    with db._lock:
        cursor = db.conn.execute("SELECT * FROM daily_metrics WHERE date = ?", (iso,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip([c[0] for c in cursor.description], row, strict=True))


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True))
