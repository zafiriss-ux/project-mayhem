"""Phase 4 step 10: the owner and two synthetic athletes, 14 mornings (ADR-0067 D11, plan step 10).

Each morning is the worker's real scheduler round (``titan.worker._morning_round``): the
fixed order, the readiness check, the claim, and one attempt per athlete in its own
``spawn`` child process with the time limit. Only the outside world is replaced, inside
that child process, by :func:`child_entry`:

- Garmin Connect: ``garminconnect.Garmin`` is a fake. The real ``GarminSync.connect`` runs,
  so another athlete's encrypted token is read and decrypted as in production. The data a
  client serves is chosen by the account inside its token (the owner: by the e-mail in
  ``.env``), never by the athlete id, so a token read for the wrong athlete would serve the
  wrong data and show up in the comparison.
- Telegram: ``send_message`` writes what would be sent, and to which chat, to a JSON-lines file.
- Weather: ``_http_get`` answers as Open-Meteo and writes what was asked for.
- Time: frozen at 07:00:30 UTC of the morning, for Python and for SQLite (``tests.sqlite_clock``).

The scheduler process (the test) only replaces ``_utc_now``. freezegun is not used there,
because it would freeze the clock that ``Process.join(timeout=...)`` waits on.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from tests.synthetic.world import PROFILES, FakeGarminClient, Night, Profile, ordinary_night

FIRST_MORNING = date(2026, 3, 16)   # a Monday
DAYS = 14                           # two weeks, two Sundays with next week's plan
HISTORY_DAYS = 224                  # what the watch holds before the first morning (backfill reads 210)
RUN_TIME = "07:00:30"
RECORD_ENV = "TITAN_PILOT_RECORD"   # the JSON-lines file the child processes write to
OWNER_EMAIL = "owner@example.invalid"
OWNER_CHAT = "1"


@dataclass(frozen=True)
class PilotAthlete:
    key: str                # the synthetic profile (tests.synthetic.world.PROFILES)
    athlete_id: str
    garmin_account: str
    chat: str | None        # None: the owner, whose chat is TELEGRAM_CHAT_ID in .env
    city: str | None        # None: the owner, whose weather is WEATHER_LOCATION in .env

    @property
    def profile(self) -> Profile:
        return {p.key: p for p in PROFILES}[self.key]


OWNER = PilotAthlete("steady_m", "owner", "garmin-owner", None, None)
ATHLETE_A = PilotAthlete("novice_f", "a-0000000a", "garmin-a", "1001", "Larissa")
ATHLETE_B = PilotAthlete("senior_m", "a-0000000b", "garmin-b", "1002", "Patras")
ATHLETES = (OWNER, ATHLETE_A, ATHLETE_B)
_BY_ACCOUNT = {a.garmin_account: a for a in ATHLETES}


def mornings() -> list[date]:
    return [FIRST_MORNING + timedelta(days=i) for i in range(DAYS)]


def athlete_profile_record(athlete: PilotAthlete) -> dict[str, Any]:
    """The ``athlete_profiles`` record of a synthetic athlete: the same body as its synthetic profile."""
    p = athlete.profile
    return {
        "birth_date": FIRST_MORNING.replace(year=FIRST_MORNING.year - p.age - 1).isoformat(),
        "sex": p.sex, "weight_kg": p.weight_kg, "height_cm": p.height_cm,
        "max_hr": p.max_hr, "threshold_hr": p.threshold_hr,
        "training_phase": p.phase, "training_goal": p.goal,
        "location_city": athlete.city, "location_country": "GR",
    }


def watch_data(athlete: PilotAthlete) -> dict[str, Night]:
    """What the athlete's watch recorded: ordinary days, from HISTORY_DAYS before the first morning."""
    first = FIRST_MORNING - timedelta(days=HISTORY_DAYS)
    return {
        (first + timedelta(days=i)).isoformat(): ordinary_night(athlete.profile, i)
        for i in range(HISTORY_DAYS + DAYS)
    }


# ── What the child process records ──────────────────────────────────────────


def _record(kind: str, **fields: Any) -> None:
    path = os.environ[RECORD_ENV]
    line = json.dumps({"kind": kind, "pid": os.getpid(), **fields}, sort_keys=True, default=str)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ── The fake Garmin Connect library ──────────────────────────────────────────


class _FakeSession:
    """Stands in for garth: the token is the account it was issued for."""

    def __init__(self, client: _FakeGarmin) -> None:
        self._client = client

    def dumps(self) -> str:
        return json.dumps({"account": self._client.display_name})

    def loads(self, token: str) -> None:
        self._client.display_name = json.loads(token)["account"]


class _FakeGarmin:
    def __init__(self, email: str | None = None, password: str | None = None, **_kwargs: Any) -> None:
        self._email = email
        self.display_name: str | None = None
        self.client = _FakeSession(self)

    def login(self) -> None:
        # The owner logs in with .env; another athlete's relogin passes its account as the e-mail.
        self.display_name = OWNER.garmin_account if self._email == OWNER_EMAIL else self._email

    def _data(self) -> FakeGarminClient:
        athlete = _BY_ACCOUNT[str(self.display_name)]
        _record("garmin", account=self.display_name, athlete_id=athlete.athlete_id,
                process_athlete=os.environ.get("TITAN_PILOT_ATHLETE"))
        return FakeGarminClient(watch_data(athlete), None)

    def connectapi(self, _path: str) -> dict:
        if self.display_name not in _BY_ACCOUNT:
            raise RuntimeError("unknown Garmin account")
        return {}

    def get_user_summary(self, _iso: str) -> dict:
        return {}

    def get_activities_by_date(self, *args: Any) -> list[dict]:
        # Garmin activity ids are unique across accounts: one number per account and day.
        offset = ATHLETES.index(_BY_ACCOUNT[str(self.display_name)]) * 100_000_000
        return [{**a, "activityId": offset + a["activityId"]} for a in self._data().get_activities_by_date(*args)]

    def get_weigh_ins(self, start: str, end: str) -> dict:
        from tests.synthetic import world

        world._WEIGHT[0] = _BY_ACCOUNT[str(self.display_name)].profile.weight_kg
        return self._data().get_weigh_ins(start, end)

    def get_sleep_data(self, iso: str) -> dict:
        return self._data().get_sleep_data(iso)

    def get_stats(self, iso: str) -> dict:
        return self._data().get_stats(iso)

    def get_hrv_data(self, iso: str) -> dict:
        return self._data().get_hrv_data(iso)


def install_fakes(monkeypatch) -> None:  # noqa: ANN001
    """Replace Garmin Connect, Telegram and Open-Meteo; used in the child and for the setup."""
    import garminconnect

    import titan.integrations.telegram_bot as telegram_module
    import titan.integrations.weather_api as weather_module
    from tests.synthetic.world import _FakeWeatherResponse

    def _send(bot, text: str, parse_mode: str = "Markdown") -> bool:  # noqa: ANN001
        _record("telegram", chat=str(bot.chat_id), bot_athlete=bot.athlete_id, text=text,
                process_athlete=os.environ.get("TITAN_PILOT_ATHLETE"))
        return True

    def _weather(url: str, *, params: dict[str, Any], **_kwargs: Any) -> _FakeWeatherResponse:
        _record("weather", url=url, params=params, process_athlete=os.environ.get("TITAN_PILOT_ATHLETE"))
        return _FakeWeatherResponse(datetime.now(UTC))

    monkeypatch.setattr(garminconnect, "Garmin", _FakeGarmin)
    monkeypatch.setattr(telegram_module.TitanTelegramBot, "send_message", _send)
    monkeypatch.setattr(weather_module, "_http_get", _weather)


def child_entry(db_path: str, athlete_id: str, execution_date: str, attempt: int) -> None:
    """The worker's ``_child_morning`` with the outside world replaced and the clock frozen."""
    import pytest
    from freezegun import freeze_time

    from tests.sqlite_clock import freeze_sqlite_clock
    from titan import worker
    from titan.core.database import DatabaseManager

    os.environ["TITAN_PILOT_ATHLETE"] = athlete_id
    install_fakes(pytest.MonkeyPatch())
    path = Path(db_path)
    with freeze_time(f"{execution_date} {RUN_TIME}"):
        db = DatabaseManager(db_name=path.name, db_dir=path.parent)
        freeze_sqlite_clock(db.conn)
        try:
            delivered = worker._attempt_morning(db, athlete_id, execution_date, attempt)
        finally:
            db.close()
    sys.exit(worker._CHILD_DELIVERED if delivered else worker._CHILD_NOT_DELIVERED)
