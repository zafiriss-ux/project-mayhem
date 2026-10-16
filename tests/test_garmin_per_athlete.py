"""Phase 4 step 4: Garmin per athlete (ADR-0067 D9; D-093).

- The owner logs in from .env and keeps the token where it is today.
- Any other athlete has their own encrypted token under <data>/garmin/<athlete_id>/, with
  the key in a file outside the data folder, and never logs in during the morning.
- A missing or rejected token pauses the athlete; a Garmin account binds to one athlete.
- Each athlete's activities and sync freshness stay with that athlete.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from titan.core.athlete import AthleteNotReady
from titan.core.database import DatabaseManager
from titan.integrations import garmin_sync
from titan.integrations.garmin_sync import (
    GarminSync,
    athlete_token_path,
    decrypt_athlete_token,
    encrypt_athlete_token,
)
from titan.orchestration.garmin_persistence import persist_garmin_data

_A, _B = "a-0000000a", "a-0000000b"
_PROFILE = {
    "birth_date": "1988-07-02", "sex": "M", "weight_kg": 70.0, "height_cm": 178,
    "max_hr": 188, "threshold_hr": 168, "training_phase": "BUILD", "training_goal": "10K",
    "location_city": "Larissa", "location_country": "GR",
}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    yield data
    get_settings.cache_clear()


@pytest.fixture
def key_file(tmp_path, data_dir, monkeypatch):
    path = tmp_path / "keys" / "athletes.key"
    path.parent.mkdir()
    path.write_bytes(Fernet.generate_key())
    os.chmod(path, 0o600)
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(path))
    return path


@pytest.fixture
def db(data_dir):
    manager = DatabaseManager(db_dir=data_dir)
    for athlete in (_A, _B):
        manager.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')",
            (athlete, athlete),
        )
    manager.conn.commit()
    yield manager
    manager.close()


class _FakeGarth:
    def __init__(self, loaded: list[str]) -> None:
        self._loaded = loaded

    def loads(self, data: str) -> None:
        self._loaded.append(data)


def _fake_garminconnect(monkeypatch, *, reject_token: bool = False) -> dict:
    """A garminconnect module that records what was loaded and whether a login happened."""
    seen = {"loaded": [], "logins": 0, "constructed_with": []}

    class _Garmin:
        def __init__(self, *args) -> None:
            seen["constructed_with"].append(args)
            self.client = _FakeGarth(seen["loaded"])

        def connectapi(self, _path):
            if reject_token:
                raise RuntimeError("401 Unauthorized")

        def login(self):
            seen["logins"] += 1

    module = MagicMock()
    module.Garmin = _Garmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return seen


def _store_token(athlete_id: str, session: str) -> None:
    path = athlete_token_path(athlete_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_athlete_token(session))


# ── token location and key ────────────────────────────────────────────────────

@pytest.mark.unit
def test_each_athlete_has_their_own_token_folder(data_dir) -> None:
    assert athlete_token_path(_A) == data_dir / "garmin" / _A / ".garth_token"
    assert athlete_token_path(_A) != athlete_token_path(_B)


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["owner", "../a-0000000a", "A-UPPER", "a/b", "", "a b"])
def test_an_id_that_cannot_name_a_folder_is_refused(data_dir, bad) -> None:
    with pytest.raises(ValueError):
        athlete_token_path(bad)


@pytest.mark.unit
def test_the_token_round_trips_with_the_key_file(key_file) -> None:
    sealed = encrypt_athlete_token('{"session": "a"}')
    assert b"session" not in sealed
    assert decrypt_athlete_token(sealed) == '{"session": "a"}'


@pytest.mark.unit
def test_without_the_key_file_nothing_is_decrypted_even_in_dev(data_dir, monkeypatch) -> None:
    monkeypatch.setenv("TITAN_ENV", "dev")
    monkeypatch.delenv("TITAN_TOKEN_KEY_FILE", raising=False)
    with pytest.raises(RuntimeError, match="TITAN_TOKEN_KEY_FILE"):
        decrypt_athlete_token(b'{"session": "a"}')


@pytest.mark.unit
def test_a_key_inside_the_data_folder_is_refused(data_dir, monkeypatch) -> None:
    inside = data_dir / "athletes.key"
    inside.write_bytes(Fernet.generate_key())
    os.chmod(inside, 0o600)
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(inside))
    with pytest.raises(RuntimeError, match="outside the data folder"):
        encrypt_athlete_token("x")


@pytest.mark.unit
@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")
def test_a_key_readable_by_its_group_is_refused(key_file, monkeypatch) -> None:
    # The mode is reported through stat rather than set on disk, so no test writes a
    # key file readable beyond its owner.
    real_stat = Path.stat
    target = key_file.resolve()

    def _group_readable(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self == target:
            return os.stat_result((result.st_mode | stat.S_IRGRP, *tuple(result)[1:]))
        return result

    monkeypatch.setattr(Path, "stat", _group_readable)
    with pytest.raises(RuntimeError, match="0600"):
        encrypt_athlete_token("x")


@pytest.mark.unit
def test_a_key_file_without_a_fernet_key_is_refused(key_file) -> None:
    key_file.write_bytes(b"not-a-key")
    with pytest.raises(RuntimeError, match="valid Fernet key"):
        encrypt_athlete_token("x")


# ── connect ───────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_an_athlete_never_gets_the_owners_credentials(key_file, monkeypatch) -> None:
    monkeypatch.setenv("GARMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "owner-password")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    sync = GarminSync(athlete_id=_A)
    assert sync.email.get_secret_value() == ""
    assert sync.password.get_secret_value() == ""
    assert GarminSync().email.get_secret_value() == "owner@example.com"


@pytest.mark.integration
def test_an_athlete_connects_with_their_own_stored_token(key_file, monkeypatch) -> None:
    seen = _fake_garminconnect(monkeypatch)
    _store_token(_A, "session-of-a")
    _store_token(_B, "session-of-b")

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is True
    assert seen["loaded"] == ["session-of-a"]
    assert seen["logins"] == 0
    assert seen["constructed_with"] == [()]
    assert sync.token_expired is False


@pytest.mark.integration
def test_without_a_token_the_athlete_is_paused_and_no_login_happens(key_file, monkeypatch) -> None:
    seen = _fake_garminconnect(monkeypatch)

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is False
    assert sync.token_expired is True
    assert seen["logins"] == 0
    assert seen["constructed_with"] == []


@pytest.mark.integration
def test_a_rejected_token_pauses_the_athlete_and_no_login_happens(key_file, monkeypatch) -> None:
    seen = _fake_garminconnect(monkeypatch, reject_token=True)
    _store_token(_A, "session-of-a")

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is False
    assert sync.token_expired is True
    assert seen["logins"] == 0


@pytest.mark.integration
def test_an_unusable_key_stops_the_connect_and_keeps_the_token(key_file, monkeypatch) -> None:
    _fake_garminconnect(monkeypatch)
    _store_token(_A, "session-of-a")
    key_file.write_bytes(b"not-a-key")

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is False
    assert sync.token_expired is False
    assert athlete_token_path(_A).exists()


# ── binding and token state ───────────────────────────────────────────────────

@pytest.mark.unit
def test_a_garmin_account_binds_to_one_athlete_only(db) -> None:
    db.bind_garmin_account(_A, "garmin-1")
    with pytest.raises(ValueError, match="another athlete"):
        db.bind_garmin_account(_B, "garmin-1")
    assert db.get_athlete_account(_A)["garmin_user_id"] == "garmin-1"
    assert db.get_athlete_account(_B) is None


@pytest.mark.unit
def test_the_owner_garmin_account_is_never_stored(db) -> None:
    with pytest.raises(ValueError, match=".env"):
        db.bind_garmin_account("owner", "garmin-owner")


@pytest.mark.unit
def test_a_new_binding_has_no_usable_token_until_relogin(db) -> None:
    db.bind_garmin_account(_A, "garmin-1")
    assert db.get_athlete_account(_A)["garmin_token_state"] == "missing"
    db.set_garmin_token_state(_A, "ok")
    db.bind_garmin_account(_A, "garmin-1")
    assert db.get_athlete_account(_A)["garmin_token_state"] == "ok"
    db.bind_garmin_account(_A, "garmin-2")
    assert db.get_athlete_account(_A)["garmin_token_state"] == "missing"


@pytest.mark.unit
def test_an_unknown_token_state_is_refused(db) -> None:
    db.bind_garmin_account(_A, "garmin-1")
    with pytest.raises(ValueError):
        db.set_garmin_token_state(_A, "valid")
    with pytest.raises(ValueError, match="no Garmin account"):
        db.set_garmin_token_state(_B, "ok")


# ── worker ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("state", [None, "missing", "expired"])
def test_an_athlete_without_a_usable_garmin_token_builds_nothing(db, key_file, monkeypatch, state) -> None:
    from titan import worker
    from titan.integrations import telegram_bot, weather_api

    db.save_athlete_profile(_A, dict(_PROFILE))
    if state is not None:
        db.bind_garmin_account(_A, "garmin-1")
        db.set_garmin_token_state(_A, state)

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("built a collaborator for an athlete who is not ready")

    monkeypatch.setattr(garmin_sync, "GarminSync", _forbidden)
    monkeypatch.setattr(weather_api, "WeatherAPI", _forbidden)
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _forbidden)

    with pytest.raises(AthleteNotReady, match="garmin"):
        worker._build_daily_coach(db, athlete_id=_A)


@pytest.mark.integration
def test_a_morning_whose_token_was_rejected_pauses_the_athlete(db) -> None:
    from titan import worker

    db.bind_garmin_account(_A, "garmin-1")
    db.set_garmin_token_state(_A, "ok")
    garmin = MagicMock(token_expired=True)

    worker._record_garmin_token_state(db, _A, garmin)

    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"


@pytest.mark.integration
def test_the_owner_is_never_paused_by_the_token_state(db) -> None:
    from titan import worker

    worker._record_garmin_token_state(db, "owner", MagicMock(token_expired=True))
    assert db.get_athlete_account("owner") is None


# ── two accounts, each activity with its athlete ──────────────────────────────

def _run(start: str, activity_id: int, distance: int) -> dict:
    return {
        "startTimeLocal": start, "activityType": {"typeKey": "running"}, "distance": distance,
        "duration": 1800, "averageHeartRate": 150, "maxHeartRate": 170, "calories": 400,
        "elevationGain": 20, "activityId": activity_id,
    }


class _ActivityClient:
    def __init__(self, activities: list[dict]) -> None:
        self._activities = activities

    def get_activities_by_date(self, _start, _end, _activity_type):
        return self._activities


@pytest.mark.integration
def test_two_garmin_accounts_each_write_to_their_own_athlete(db, key_file, monkeypatch) -> None:
    _fake_garminconnect(monkeypatch)
    feeds = {
        _A: [_run("2026-10-15T07:00:00", 501, 10000)],
        _B: [_run("2026-10-15T08:00:00", 502, 5000), _run("2026-10-14T08:00:00", 503, 7000)],
    }
    for athlete, activities in feeds.items():
        _store_token(athlete, f"session-of-{athlete}")
        sync = GarminSync(athlete_id=athlete)
        assert sync.connect() is True
        sync.client = _ActivityClient(activities)
        synced = sync.sync_activities(days_back=3)
        persist_garmin_data(
            db, {"activities": synced}, "2026-10-15", athlete_id=athlete, emit=lambda *a, **k: None
        )

    rows = db.conn.execute(
        "SELECT athlete_id, garmin_activity_id, distance_km FROM training_log ORDER BY garmin_activity_id"
    ).fetchall()
    assert [(r[0], str(r[1])) for r in rows] == [(_A, "501"), (_B, "502"), (_B, "503")]
    assert db.get_last_garmin_sync_timestamp(athlete_id=_A).date().isoformat() == "2026-10-15"
    assert db.get_last_garmin_sync_timestamp(athlete_id="owner") is None


@pytest.mark.unit
def test_another_athletes_fresh_data_never_makes_mine_look_fresh(db) -> None:
    db.save_session(
        date="2026-10-15", session_type="EASY", distance_km=5.0, duration_sec=1800, athlete_id=_B
    )
    db.save_session(
        date="2026-10-01", session_type="EASY", distance_km=5.0, duration_sec=1800, athlete_id=_A
    )
    assert db.get_last_garmin_sync_timestamp(athlete_id=_A).date().isoformat() == "2026-10-01"
    assert db.get_last_garmin_sync_timestamp(athlete_id=_B).date().isoformat() == "2026-10-15"
