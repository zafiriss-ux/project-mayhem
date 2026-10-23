"""OW-L1 (D-129): the owner's /sync stores what it synced, and the console has no unsaved sync.

Before, /sync kept the Garmin data in the console's memory only and answered "SYNC
COMPLETE", and a background sync every 6 hours called Garmin and threw the data away.
Synthetic data only.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from titan import main as titan_main
from titan.orchestration import garmin_persistence

_TODAY = datetime.now(UTC).date().isoformat()


def _payload() -> dict:
    return {
        "activities": [{
            "activity_id": "garmin-sync-1", "date": _TODAY, "activity_type": "running",
            "distance_km": 8, "duration_sec": 2700, "name": "AM",
        }],
        "sleep": [{"date": _TODAY, "resting_hr": 48, "sleep_score": 82, "total_sleep_hours": 7.2}],
        "hrv": [{"date": _TODAY, "rmssd": 55.0}],
        "weight": [],
    }


def _sync_command(db):
    telegram = SimpleNamespace(commands={})
    telegram.register_command = lambda name, cb: telegram.commands.__setitem__(name, cb)
    telegram.register_athlete_command = lambda name, cb: None
    garmin = SimpleNamespace(sync_all=_payload)
    ctx = {"garmin": garmin, "db": db, "daily_coach": SimpleNamespace()}
    titan_main._register_telegram_callbacks(telegram, ctx)
    return telegram.commands["sync"], ctx


@pytest.fixture
def db(db_manager_factory):
    return db_manager_factory(db_name="test.db")


def test_the_owners_sync_stores_the_data_for_the_owner(db):
    sync, ctx = _sync_command(db)
    reply = sync()
    assert reply.startswith("🔄 *SYNC COMPLETE*")
    rows = db.conn.execute("SELECT athlete_id FROM training_log WHERE date = ?", (_TODAY,)).fetchall()
    assert [tuple(r) for r in rows] == [("owner",)]
    metrics = db.conn.execute(
        "SELECT athlete_id, resting_hr FROM daily_metrics WHERE date = ?", (_TODAY,)
    ).fetchone()
    assert tuple(metrics) == ("owner", 48)
    assert ctx["last_garmin_data"]["activities"]


def test_a_failed_save_is_reported_and_not_called_complete(db, monkeypatch):
    def _rolled_back(*_args, **_kwargs):
        raise garmin_persistence.PersistenceFailure(48, 82, 7.2)

    monkeypatch.setattr(garmin_persistence, "persist_garmin_data", _rolled_back)
    sync, _ctx = _sync_command(db)
    reply = sync()
    assert reply.startswith("❌")
    assert "COMPLETE" not in reply


def test_the_console_starts_no_background_sync_that_throws_the_data_away():
    source = Path(titan_main.__file__).read_text(encoding="utf-8")
    calls = [
        node.func.attr for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "start_background_sync" not in calls
