"""Phase 4 step 10: the owner and two synthetic athletes for 14 mornings (ADR-0067 D8, D10, D11).

The worker's real round runs every morning: the owner first, then the two athletes, each
in its own child process (``tests.synthetic.pilot``). The same mornings are also run with
fewer athletes, and every athlete's rows and messages must be the same in every run:

* no row, message, Garmin read or weather request of one athlete reaches another, and
* the owner is told exactly what the owner is told alone (ADR-0067 D3.4).

The time each attempt takes is measured too. With the outside world replaced it is only
our own processing time; ``docs/validation/multi-athlete-pilot-report.md`` has the numbers.
"""
from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from freezegun import freeze_time

from tests.synthetic import pilot
from tests.synthetic.pilot import ATHLETE_A, ATHLETE_B, ATHLETES, OWNER, PilotAthlete

pytestmark = [pytest.mark.slow, pytest.mark.integration]

_SLO_S = 5 * 60  # docs/SLO.md: every scheduled briefing delivered by 07:05 UTC (ADR-0067 D8.6)


@dataclass
class Attempt:
    day: str
    athlete_id: str
    attempt: int
    seconds: float
    delivered: bool


@dataclass
class PilotRun:
    athletes: tuple[PilotAthlete, ...]
    db_path: Path
    records: list[dict[str, Any]]
    attempts: list[Attempt] = field(default_factory=list)
    rounds: list[float] = field(default_factory=list)

    def from_child(self, athlete_id: str, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r["kind"] == kind and r["process_athlete"] == athlete_id]


def _env(monkeypatch: pytest.MonkeyPatch, base: Path) -> Path:
    data = base / "data"
    data.mkdir(parents=True)
    key = base / "keys" / "athletes.key"
    key.parent.mkdir()
    from cryptography.fernet import Fernet

    key.write_bytes(Fernet.generate_key())
    os.chmod(key, 0o600)
    # Placeholders only: Garmin Connect, Telegram and Open-Meteo are fakes, nothing leaves the process.
    for name, value in {
        "TITAN_DATA_DIR": str(data), "TITAN_TOKEN_KEY_FILE": str(key),
        pilot.RECORD_ENV: str(base / "record.jsonl"), "TITAN_PILOT_ATHLETE": "scheduler",
        "GARMIN_EMAIL": pilot.OWNER_EMAIL, "GARMIN_PASSWORD": "placeholder",
        "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": pilot.OWNER_CHAT,
        "WEATHER_LOCATION": "Athens,GR", "TITAN_MULTI_ATHLETE": "1",
        **OWNER.profile.env(),
    }.items():
        monkeypatch.setenv(name, value)
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    return data


def _add(db, athlete: PilotAthlete, at: datetime, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    """What Zaf and the athlete do: ``athletes add``, ``athletes relogin``, ``/agree v1``."""
    from titan.core import athlete_lifecycle as lifecycle
    from titan.core.athlete import CONSENT_TEXT_VERSION
    from titan.integrations.garmin_sync import relogin_athlete

    monkeypatch.setattr(lifecycle, "new_athlete_id", lambda: athlete.athlete_id)
    lifecycle.add_athlete(db, f"Synthetic {athlete.key}", pilot.athlete_profile_record(athlete),
                          athlete.chat, now=at)
    relogin_athlete(db, athlete.athlete_id, athlete.garmin_account, "placeholder", lambda: "")
    assert db.grant_consent(athlete.athlete_id, CONSENT_TEXT_VERSION, now=at)


def _run(base: Path, athletes: tuple[PilotAthlete, ...]) -> PilotRun:
    from titan import worker
    from titan.core.database import DatabaseManager

    mp = pytest.MonkeyPatch()
    try:
        data = _env(mp, base)
        pilot.install_fakes(mp)
        # The evening before the first morning; each athlete always joins at the same minute,
        # so its rows are the same in every run. The clock is frozen for the setup only.
        evening = datetime.combine(pilot.FIRST_MORNING, datetime.min.time(), UTC) - timedelta(hours=6)
        with freeze_time(evening):
            db = DatabaseManager(db_dir=data)
            for athlete in athletes:
                if athlete is not OWNER:
                    _add(db, athlete, evening + timedelta(minutes=ATHLETES.index(athlete)), mp)

        run = PilotRun(athletes, data / "titan_core.db", [])
        real_attempt = worker._run_attempt

        def _timed(db, athlete_id: str, execution_date: str, attempt: int) -> bool:  # noqa: ANN001
            start = time.perf_counter()
            delivered = real_attempt(db, athlete_id, execution_date, attempt)
            run.attempts.append(Attempt(execution_date, athlete_id, attempt, time.perf_counter() - start, delivered))
            return delivered

        mp.setattr(worker, "_CHILD_ENTRY", pilot.child_entry)
        mp.setattr(worker, "_run_attempt", _timed)
        for day in pilot.mornings():
            at = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=7, seconds=30)
            mp.setattr(worker, "_utc_now", lambda at=at: at)
            start = time.perf_counter()
            worker._morning_round(db)
            run.rounds.append(time.perf_counter() - start)
            worker._morning_round(db)  # the next 60 s poll of the same morning runs nobody again
        db.close()
        run.records = pilot.read_records(base / "record.jsonl")
        return run
    finally:
        mp.undo()
        from titan.config.settings import get_settings

        get_settings.cache_clear()


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, PilotRun]]:
    base = tmp_path_factory.mktemp("pilot")
    yield {
        "owner": _run(base / "owner", (OWNER,)),
        "owner_a": _run(base / "owner_a", (OWNER, ATHLETE_A)),
        "owner_b": _run(base / "owner_b", (OWNER, ATHLETE_B)),
        "all": _run(base / "all", ATHLETES),
    }


# ── Reading the stored rows ────────────────────────────────────────────────


# Written with SQLite's own clock when the database is created (the owner's seed rows,
# migrations.py ``_seed_single_athlete_rows``): when the file was made, not what a morning decided.
_CREATED_WITH_THE_FILE = {
    ("athletes", "created_at"), ("athletes", "cold_start_ends_at"),
    ("coach_athlete_assignments", "assigned_at"),
}


def _athlete_tables(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Every table with an athlete_id column, and the columns to compare.

    Left out: an INTEGER PRIMARY KEY, which depends on how the athletes' rows interleave,
    and the columns in ``_CREATED_WITH_THE_FILE``.
    """
    tables: dict[str, list[str]] = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
        if any(c[1] == "athlete_id" for c in cols):
            tables[name] = [
                c[1] for c in cols
                if not (c[5] and c[2].upper() == "INTEGER") and (name, c[1]) not in _CREATED_WITH_THE_FILE
            ]
    return tables


def _rows_of(db_path: Path, athlete_id: str) -> dict[str, list[tuple]]:
    conn = sqlite3.connect(db_path)
    try:
        out = {}
        for table, cols in _athlete_tables(conn).items():
            col_list = ", ".join(f'"{c}"' for c in cols)
            rows = conn.execute(f'SELECT {col_list} FROM "{table}" WHERE athlete_id = ?', (athlete_id,)).fetchall()  # nosec B608
            out[table] = sorted(rows, key=repr)
        return out
    finally:
        conn.close()


def _athlete_ids(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        ids: set[str] = set()
        for table in _athlete_tables(conn):
            ids |= {r[0] for r in conn.execute(f'SELECT DISTINCT athlete_id FROM "{table}"')}  # nosec B608
        return ids
    finally:
        conn.close()


def _solo(runs: dict[str, PilotRun], athlete: PilotAthlete) -> PilotRun:
    return {OWNER: runs["owner"], ATHLETE_A: runs["owner_a"], ATHLETE_B: runs["owner_b"]}[athlete]


# ── The checks ─────────────────────────────────────────────────────────────


def test_every_athlete_is_delivered_once_every_morning(runs: dict[str, PilotRun]) -> None:
    for key, run in runs.items():
        days = [d.isoformat() for d in pilot.mornings()]
        expected = [(d, a.athlete_id) for d in days for a in run.athletes]
        assert [(a.day, a.athlete_id) for a in run.attempts] == expected, key  # owner first, once a day
        assert all(a.delivered and a.attempt == 1 for a in run.attempts), key
        conn = sqlite3.connect(run.db_path)
        try:
            rows = conn.execute(
                "SELECT athlete_id, COUNT(*), SUM(delivered_at IS NOT NULL), MAX(attempts) "
                "FROM worker_routine_executions WHERE routine_type = 'morning' GROUP BY athlete_id"
            ).fetchall()
        finally:
            conn.close()
        assert sorted(rows) == sorted((a.athlete_id, len(days), len(days), 1) for a in run.athletes), key


def test_no_row_belongs_to_an_unknown_athlete(runs: dict[str, PilotRun]) -> None:
    for key, run in runs.items():
        assert _athlete_ids(run.db_path) <= {a.athlete_id for a in run.athletes}, key


@pytest.mark.parametrize("athlete", ATHLETES, ids=lambda a: a.athlete_id)
def test_every_athlete_has_the_same_rows_as_without_the_others(runs: dict[str, PilotRun], athlete: PilotAthlete) -> None:
    alone, together = _rows_of(_solo(runs, athlete).db_path, athlete.athlete_id), _rows_of(runs["all"].db_path, athlete.athlete_id)
    assert alone.keys() == together.keys()
    differ = sorted(t for t in alone if alone[t] != together[t])
    assert not differ, f"{athlete.athlete_id}: rows differ with the other athletes present in {differ}"
    assert together["governance_outcomes"] and together["training_log"], "the mornings stored nothing"


def test_the_owner_is_told_the_same_with_and_without_other_athletes(runs: dict[str, PilotRun]) -> None:
    texts = {k: [r["text"] for r in run.from_child("owner", "telegram")] for k, run in runs.items()}
    assert texts["owner"], "the owner was told nothing"
    assert texts["owner_a"] == texts["owner_b"] == texts["all"] == texts["owner"]
    for key in ("owner_a", "owner_b"):
        assert _rows_of(runs[key].db_path, "owner") == _rows_of(runs["owner"].db_path, "owner"), key


@pytest.mark.parametrize("athlete", (ATHLETE_A, ATHLETE_B), ids=lambda a: a.athlete_id)
def test_an_athlete_is_told_the_same_with_and_without_the_other(runs: dict[str, PilotRun], athlete: PilotAthlete) -> None:
    alone = [r["text"] for r in _solo(runs, athlete).from_child(athlete.athlete_id, "telegram")]
    together = [r["text"] for r in runs["all"].from_child(athlete.athlete_id, "telegram")]
    assert alone and alone == together


@pytest.mark.parametrize("athlete", ATHLETES, ids=lambda a: a.athlete_id)
def test_each_child_reaches_only_its_own_chat_garmin_account_and_city(runs: dict[str, PilotRun], athlete: PilotAthlete) -> None:
    run = runs["all"]
    sent = run.from_child(athlete.athlete_id, "telegram")
    assert len(sent) >= len(pilot.mornings())
    # Zaf's copy of an operator alert about this athlete (D-107) goes from the owner's bot to the
    # owner's chat, names the athlete and carries no health data. A new athlete's first mornings
    # have fewer than 4 RHR nights, so the H3 "missing data" alert fires once (SD-03, D-164).
    to_zaf = [r for r in sent if r["bot_athlete"] != athlete.athlete_id]
    if athlete is not OWNER:
        assert all(r["chat"] == pilot.OWNER_CHAT and r["bot_athlete"] == OWNER.athlete_id
                   and r["text"].startswith(f"TITAN missing data — athlete {athlete.athlete_id} ")
                   for r in to_zaf), to_zaf
    else:
        assert not to_zaf, to_zaf
    own = [r for r in sent if r not in to_zaf]
    assert own and {(r["chat"], r["bot_athlete"]) for r in own} == {(athlete.chat or pilot.OWNER_CHAT, athlete.athlete_id)}
    garmin = run.from_child(athlete.athlete_id, "garmin")
    assert garmin and {r["account"] for r in garmin} == {athlete.garmin_account}
    places = {str(r["params"].get("name")) for r in run.from_child(athlete.athlete_id, "weather") if "name" in r["params"]}
    assert places == {athlete.city or "Athens"}


def test_the_scheduler_itself_sends_nothing(runs: dict[str, PilotRun]) -> None:
    """Everyone is ready, so Zaf gets no not-ready notice and nothing is sent outside a child."""
    for key, run in runs.items():
        assert [r for r in run.records if r["process_athlete"] == "scheduler"] == [], key


def test_every_briefing_fits_the_attempt_budget_and_the_0705_slo(runs: dict[str, PilotRun]) -> None:
    from titan.config.settings import TitanSettings

    budget = TitanSettings.model_fields["WORKER_ROUTINE_BUDGET_S"].default
    run = runs["all"]
    assert max(a.seconds for a in run.attempts) < budget
    assert max(run.rounds) < _SLO_S
    by_athlete = {a.athlete_id: sorted(x.seconds for x in run.attempts if x.athlete_id == a.athlete_id)
                  for a in ATHLETES}
    print(f"\npilot timing (s): round max {max(run.rounds):.2f}; " + "; ".join(
        f"{k} median {v[len(v) // 2]:.2f} max {v[-1]:.2f}" for k, v in by_athlete.items()))
