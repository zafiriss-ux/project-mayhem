"""ADR-0076 (M0-13-R1): the database keeps the owner's Garmin account name.

- One current value: the socialProfile ``displayName`` (stripped), never empty.
- Written from the owner's connections that read the profile; the 429 branches write nothing
  and never stop the owner's connection.
- ``bind_garmin_account`` refuses the owner's account, and binds nothing while the name is
  unknown (fail closed).
- An athlete already bound to the owner's account is set to 'expired'.

Only synthetic values: no real account names, e-mails or tokens.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest

from titan.core.database import DatabaseManager
from titan.integrations import garmin_sync
from titan.integrations.garmin_sync import GarminSync

_A, _B = "a-0000000a", "a-0000000b"
_OWNER_NAME = "owner-garmin-name"


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


# ── the stored value ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_a_fresh_database_has_no_owner_name(db) -> None:
    assert db.get_owner_garmin_display_name() is None


@pytest.mark.unit
def test_the_name_is_stored_stripped_and_one_value_is_kept(db) -> None:
    assert db.record_owner_garmin_display_name(f"  {_OWNER_NAME} ") == {"changed": False, "expired_athletes": []}
    assert db.get_owner_garmin_display_name() == _OWNER_NAME

    assert db.record_owner_garmin_display_name(_OWNER_NAME) == {"changed": False, "expired_athletes": []}
    assert db.record_owner_garmin_display_name("owner-new-name") == {"changed": True, "expired_athletes": []}
    assert db.get_owner_garmin_display_name() == "owner-new-name"
    assert db.conn.execute("SELECT COUNT(*) FROM owner_garmin_identity").fetchone()[0] == 1


@pytest.mark.unit
@pytest.mark.parametrize("empty", ["", "   ", None])
def test_an_empty_name_is_never_stored_and_keeps_the_old_one(db, empty) -> None:
    assert db.record_owner_garmin_display_name(empty) is None
    assert db.get_owner_garmin_display_name() is None

    db.record_owner_garmin_display_name(_OWNER_NAME)
    assert db.record_owner_garmin_display_name(empty) is None
    assert db.get_owner_garmin_display_name() == _OWNER_NAME


@pytest.mark.unit
@pytest.mark.parametrize(
    ("athlete_id", "name"),
    [("a-0000000a", _OWNER_NAME), ("owner", ""), ("owner", "   ")],
    ids=["not-the-owner", "empty", "blank"],
)
def test_the_table_refuses_another_athlete_or_an_empty_name(db, athlete_id, name) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO owner_garmin_identity (athlete_id, garmin_display_name, updated_at) VALUES (?, ?, 'now')",
            (athlete_id, name),
        )


@pytest.mark.integration
def test_a_v34_database_gets_the_table_on_open(data_dir) -> None:
    first = DatabaseManager(db_dir=data_dir)
    first.conn.execute("DROP TABLE owner_garmin_identity")
    first.conn.execute("PRAGMA user_version = 34")
    first.conn.commit()
    first.close()

    reopened = DatabaseManager(db_dir=data_dir)
    try:
        assert reopened.conn.execute("PRAGMA user_version").fetchone()[0] == 35
        assert reopened.get_owner_garmin_display_name() is None
        reopened.record_owner_garmin_display_name(_OWNER_NAME)
        assert reopened.get_owner_garmin_display_name() == _OWNER_NAME
    finally:
        reopened.close()


# ── binding (point 5) ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_no_account_is_bound_while_the_owner_name_is_unknown(db) -> None:
    with pytest.raises(ValueError, match="owner's Garmin sync first"):
        db.bind_garmin_account(_A, "garmin-a")
    assert db.get_athlete_account(_A) is None


@pytest.mark.unit
def test_the_owners_account_is_never_bound_to_an_athlete(db) -> None:
    db.record_owner_garmin_display_name(_OWNER_NAME)

    with pytest.raises(ValueError, match="owner's Garmin account"):
        db.bind_garmin_account(_A, f" {_OWNER_NAME} ")
    assert db.get_athlete_account(_A) is None

    db.bind_garmin_account(_A, "garmin-a")
    assert db.get_athlete_account(_A)["garmin_user_id"] == "garmin-a"


@pytest.mark.unit
def test_the_comparison_is_exact_like_the_token_check(db) -> None:
    """ADR-0076 point 3: strip and exact equality, as D9.4 and _token_account_matches."""
    db.record_owner_garmin_display_name(_OWNER_NAME)
    db.bind_garmin_account(_A, _OWNER_NAME.upper())
    assert db.get_athlete_account(_A)["garmin_user_id"] == _OWNER_NAME.upper()


# ── an athlete already bound (point 6) ────────────────────────────────────────


@pytest.mark.unit
def test_an_athlete_bound_to_the_owners_account_is_stopped(db) -> None:
    db.record_owner_garmin_display_name("owner-old-name")
    db.bind_garmin_account(_A, _OWNER_NAME)
    db.set_garmin_token_state(_A, "ok")
    db.bind_garmin_account(_B, "garmin-b")
    db.set_garmin_token_state(_B, "ok")

    result = db.record_owner_garmin_display_name(_OWNER_NAME)

    assert result == {"changed": True, "expired_athletes": [_A]}
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"
    assert db.get_athlete_account(_B)["garmin_token_state"] == "ok"
    # Already stopped: not reported again at the next connection.
    assert db.record_owner_garmin_display_name(_OWNER_NAME) == {"changed": False, "expired_athletes": []}


# ── the owner's connection (points 2, 3, 6) ───────────────────────────────────


@pytest.fixture
def owner_dev(data_dir, monkeypatch):
    monkeypatch.setenv("TITAN_ENV", "dev")
    monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
    monkeypatch.setenv("GARMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "PLANTED_OWNER_PASSWORD")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    return garmin_sync._get_garth_token_path()


def _fake_garmin(monkeypatch, *, profile=None, ping_error: Exception | None = None,
                 login_profile_error: Exception | None = None) -> dict:
    """garminconnect for the owner. ``profile`` answers the socialProfile call; with
    ``ping_error`` the call raises before a login (token check), with
    ``login_profile_error`` it raises after a login."""
    seen = {"logins": 0, "profile_calls": 0}

    class _Garth:
        def loads(self, _data: str) -> None:
            return None

        def dumps(self) -> str:
            return "new-session"

    class _Garmin:
        def __init__(self, *_args) -> None:
            self.client = _Garth()
            # What the library would set without a displayName: the login e-mail.
            self.display_name = "owner@example.com"

        def connectapi(self, _path):
            seen["profile_calls"] += 1
            if seen["logins"] == 0 and ping_error is not None:
                raise ping_error
            if seen["logins"] and login_profile_error is not None:
                raise login_profile_error
            return profile

        def get_user_summary(self, _day):
            return {}

        def login(self):
            seen["logins"] += 1

    module = MagicMock()
    module.Garmin = _Garmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return seen


@pytest.mark.integration
def test_the_token_connection_records_the_owner_name(owner_dev, db, monkeypatch) -> None:
    owner_dev.write_bytes(b"owner-session")
    seen = _fake_garmin(monkeypatch, profile={"displayName": f" {_OWNER_NAME} "})

    assert GarminSync(db=db).connect() is True

    assert seen["logins"] == 0
    assert db.get_owner_garmin_display_name() == _OWNER_NAME


@pytest.mark.integration
def test_a_full_login_reads_the_profile_and_records_the_owner_name(owner_dev, db, monkeypatch) -> None:
    seen = _fake_garmin(monkeypatch, profile={"displayName": _OWNER_NAME})

    assert GarminSync(db=db).connect() is True

    assert seen["logins"] == 1
    assert db.get_owner_garmin_display_name() == _OWNER_NAME


@pytest.mark.integration
@pytest.mark.parametrize("profile", [{}, {"displayName": "  "}, None, ["x"]])
def test_a_profile_without_a_name_records_nothing_and_never_the_email(owner_dev, db, monkeypatch, profile) -> None:
    owner_dev.write_bytes(b"owner-session")
    _fake_garmin(monkeypatch, profile=profile)
    db.record_owner_garmin_display_name(_OWNER_NAME)

    assert GarminSync(db=db).connect() is True

    assert db.get_owner_garmin_display_name() == _OWNER_NAME


@pytest.mark.integration
def test_a_rate_limited_check_connects_the_owner_and_records_nothing(owner_dev, db, monkeypatch) -> None:
    """ADR-0076 point 2: the 'assume valid' branches write nothing and never stop the owner."""
    owner_dev.write_bytes(b"owner-session")
    _fake_garmin(monkeypatch, profile={"displayName": "someone-else"}, ping_error=RuntimeError("429 Too Many Requests"))

    sync = GarminSync(db=db)

    assert sync.connect() is True
    assert sync.is_connected is True
    assert db.get_owner_garmin_display_name() is None


@pytest.mark.integration
def test_a_failed_profile_read_after_login_still_connects_the_owner(owner_dev, db, monkeypatch) -> None:
    _fake_garmin(monkeypatch, profile={"displayName": _OWNER_NAME},
                 login_profile_error=RuntimeError("429 Too Many Requests"))

    assert GarminSync(db=db).connect() is True
    assert db.get_owner_garmin_display_name() is None


@pytest.mark.integration
def test_a_failed_write_still_connects_the_owner(owner_dev, db, monkeypatch, caplog) -> None:
    owner_dev.write_bytes(b"owner-session")
    _fake_garmin(monkeypatch, profile={"displayName": _OWNER_NAME})
    broken = MagicMock()
    broken.record_owner_garmin_display_name.side_effect = sqlite3.OperationalError("database is locked")
    caplog.set_level(logging.INFO)

    assert GarminSync(db=broken).connect() is True
    assert "owner_identity_not_recorded" in caplog.text
    assert _OWNER_NAME not in caplog.text


@pytest.mark.integration
def test_without_a_database_the_owner_still_connects(owner_dev, monkeypatch) -> None:
    owner_dev.write_bytes(b"owner-session")
    _fake_garmin(monkeypatch, profile={"displayName": _OWNER_NAME})

    assert GarminSync().connect() is True


@pytest.mark.integration
def test_a_changed_name_and_a_stopped_athlete_are_told_without_the_name(owner_dev, db, monkeypatch, caplog) -> None:
    db.record_owner_garmin_display_name("owner-old-name")
    db.bind_garmin_account(_A, _OWNER_NAME)
    db.set_garmin_token_state(_A, "ok")
    owner_dev.write_bytes(b"owner-session")
    _fake_garmin(monkeypatch, profile={"displayName": _OWNER_NAME})
    caplog.set_level(logging.INFO)

    assert GarminSync(db=db).connect() is True

    assert db.get_owner_garmin_display_name() == _OWNER_NAME
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"
    assert "owner_garmin_account_name_changed" in caplog.text
    stopped = [r for r in caplog.records if r.getMessage() == "athlete_garmin_account_is_owners"]
    assert [r.athlete_id for r in stopped] == [_A]
    assert _OWNER_NAME not in caplog.text and "owner-old-name" not in caplog.text


@pytest.mark.integration
def test_an_athletes_connection_never_records_the_owner_name(data_dir, db, monkeypatch, tmp_path) -> None:
    import os

    from cryptography.fernet import Fernet

    from titan.integrations.garmin_sync import athlete_token_path, encrypt_athlete_token

    key = tmp_path / "keys" / "athletes.key"
    key.parent.mkdir()
    key.write_bytes(Fernet.generate_key())
    os.chmod(key, 0o600)
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(key))
    db.record_owner_garmin_display_name(_OWNER_NAME)
    db.bind_garmin_account(_A, "garmin-a")
    path = athlete_token_path(_A)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_athlete_token("session-of-a"))
    _fake_garmin(monkeypatch, profile={"displayName": "garmin-a"})

    assert GarminSync(athlete_id=_A, expected_garmin_user_id="garmin-a", db=db).connect() is True
    assert db.get_owner_garmin_display_name() == _OWNER_NAME
