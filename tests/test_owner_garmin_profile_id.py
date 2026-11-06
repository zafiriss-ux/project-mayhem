"""ADR-0083 (M0-13-R2): a Garmin account is its displayName and its stable profileId.

- One check (``valid_garmin_profile_id``): a plain int, 0 < v < 2**63.
- The owner's profileIds are kept in ``owner_garmin_profile_history``: never deleted or
  changed, written only with ON CONFLICT DO NOTHING, in one transaction with the name.
- Relogin and binding refuse the owner's account by name or by any recorded profileId, and
  stay closed while the owner's account is not recorded.
- An athlete's token is used only when both values match the bound ones and neither is the
  owner's. Anything missing or unreadable refuses.
- No profileId is ever logged or printed.

Only synthetic values: no real account names, ids, e-mails or tokens.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from tests.garmin_accounts import (
    OWNER_GARMIN_NAME,
    OWNER_GARMIN_PROFILE_ID,
    bind,
    profile_id_for,
    record_owner,
    set_token_ok,
)
from titan.core.athlete import valid_garmin_profile_id
from titan.core.database import SCHEMA_VERSION, DatabaseManager
from titan.integrations import garmin_sync
from titan.integrations.garmin_sync import (
    GarminSync,
    athlete_token_path,
    encrypt_athlete_token,
    relogin_athlete,
)

_A, _B = "a-0000000a", "a-0000000b"
_ACCOUNT_A = "garmin-a"
_PID_A = profile_id_for(_ACCOUNT_A)
# Distinctive synthetic ids, so a leak into a log or an output is found by text.
_OWNER_NEW_PID = 987_654_321_001
_SECRET_LOOKING_PID = 555_444_333_222
_INVALID_IDS = [True, False, "1", "123", 1.0, 0, -5, 2**63, None, [1]]
_INVALID_IDS_IDS = ["True", "False", "str-1", "str-123", "float", "zero", "negative", "too-big", "None", "list"]


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("GARMIN_EMAIL", "owner@example.com")
    monkeypatch.delenv("GARMINTOKENS", raising=False)
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


def _new_db(data_dir) -> DatabaseManager:  # noqa: ANN001
    manager = DatabaseManager(db_dir=data_dir)
    for athlete in (_A, _B):
        manager.conn.execute(
            "INSERT OR IGNORE INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')",
            (athlete, athlete),
        )
    manager.conn.commit()
    return manager


@pytest.fixture
def bare_db(data_dir):
    """No owner account recorded yet."""
    manager = _new_db(data_dir)
    yield manager
    manager.close()


@pytest.fixture
def db(bare_db):
    record_owner(bare_db)
    return bare_db


def _history(db) -> list[int]:  # noqa: ANN001
    return [r[0] for r in db.conn.execute(
        "SELECT garmin_profile_id FROM owner_garmin_profile_history ORDER BY garmin_profile_id"
    )]


# ── the one check ─────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("value", _INVALID_IDS, ids=_INVALID_IDS_IDS)
def test_only_a_plain_positive_int_that_sqlite_holds_is_valid(value) -> None:
    assert valid_garmin_profile_id(value) is None


@pytest.mark.unit
@pytest.mark.parametrize("value", [1, 123456, 2**63 - 1])
def test_a_valid_profile_id_is_returned_as_it_is(value) -> None:
    assert valid_garmin_profile_id(value) == value


# ── the owner's history ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_the_same_owner_profile_id_twice_is_one_row(db) -> None:
    record_owner(db)
    record_owner(db)
    assert _history(db) == [OWNER_GARMIN_PROFILE_ID]


@pytest.mark.unit
@pytest.mark.parametrize(
    "statement",
    ["DELETE FROM owner_garmin_profile_history",
     "UPDATE owner_garmin_profile_history SET garmin_profile_id = 7",
     "UPDATE owner_garmin_profile_history SET first_recorded_at = 'x'"],
    ids=["delete", "update-id", "update-time"],
)
def test_a_history_row_is_never_deleted_or_changed(db, statement) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="ADR-0083"):
        db.conn.execute(statement)
    db.conn.rollback()
    assert _history(db) == [OWNER_GARMIN_PROFILE_ID]


@pytest.mark.unit
def test_a_fresh_database_has_both_triggers(bare_db) -> None:
    names = {r[0] for r in bare_db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert {"trg_owner_garmin_profile_history_no_delete", "trg_owner_garmin_profile_history_no_update"} <= names


@pytest.mark.unit
def test_the_first_owner_profile_id_is_not_a_new_account_and_a_second_one_is(bare_db) -> None:
    first = bare_db.record_owner_garmin_identity(OWNER_GARMIN_NAME, OWNER_GARMIN_PROFILE_ID)
    second = bare_db.record_owner_garmin_identity(OWNER_GARMIN_NAME, _OWNER_NEW_PID)
    again = bare_db.record_owner_garmin_identity(OWNER_GARMIN_NAME, _OWNER_NEW_PID)

    assert first["new_account"] is False
    assert second["new_account"] is True
    assert again["new_account"] is False
    assert _history(bare_db) == sorted([OWNER_GARMIN_PROFILE_ID, _OWNER_NEW_PID])


@pytest.mark.unit
@pytest.mark.parametrize("value", _INVALID_IDS, ids=_INVALID_IDS_IDS)
def test_an_invalid_owner_profile_id_is_not_written_and_keeps_the_stored_one(db, value) -> None:
    result = db.record_owner_garmin_identity(OWNER_GARMIN_NAME, value)
    assert result["profile_id_recorded"] is False
    assert _history(db) == [OWNER_GARMIN_PROFILE_ID]
    assert db.get_owner_garmin_display_name() == OWNER_GARMIN_NAME


@pytest.mark.unit
def test_a_profile_id_without_a_name_goes_to_the_history_only(bare_db) -> None:
    """ADR-0083 point 2: no owner row is created; the name stays required (ADR-0076)."""
    result = bare_db.record_owner_garmin_identity(None, OWNER_GARMIN_PROFILE_ID)

    assert (result["name_recorded"], result["profile_id_recorded"]) == (False, True)
    assert _history(bare_db) == [OWNER_GARMIN_PROFILE_ID]
    assert bare_db.get_owner_garmin_display_name() is None
    assert bare_db.conn.execute("SELECT COUNT(*) FROM owner_garmin_identity").fetchone()[0] == 0


@pytest.mark.unit
@pytest.mark.parametrize("name", [None, OWNER_GARMIN_NAME], ids=["profile-id-only", "with-name"])
def test_a_failed_history_write_writes_nothing_of_the_owner(bare_db, name) -> None:
    """A NULL time breaks NOT NULL: the whole write stops, nothing of the owner is kept."""
    with pytest.raises(sqlite3.IntegrityError):
        bare_db._access.record_owner_garmin_identity(name, OWNER_GARMIN_PROFILE_ID, updated_at=None)
    assert _history(bare_db) == []
    assert bare_db.get_owner_garmin_display_name() is None
    assert bare_db.conn.in_transaction is False


@pytest.mark.unit
def test_the_owner_write_refuses_to_join_an_open_transaction(db) -> None:
    db.conn.execute("UPDATE athletes SET display_name = display_name WHERE athlete_id = ?", (_A,))
    assert db.conn.in_transaction
    with pytest.raises(RuntimeError, match="already open"):
        db.record_owner_garmin_identity(OWNER_GARMIN_NAME, _OWNER_NEW_PID)
    db.conn.rollback()
    assert _history(db) == [OWNER_GARMIN_PROFILE_ID]


# ── point 6: athletes bound to the owner's account ───────────────────────────


@pytest.mark.unit
def test_an_athlete_bound_to_an_owner_profile_id_is_stopped_by_the_profile_id_alone(db) -> None:
    bind(db, _A, _ACCOUNT_A)
    set_token_ok(db, _A)
    bind(db, _B, "garmin-b")
    set_token_ok(db, _B)

    # The owner's .env now points to A's account: same profileId, another name in the DB.
    result = db.record_owner_garmin_identity("owner-renamed", _PID_A)

    assert result["expired_athletes"] == [_A]
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"
    assert db.get_athlete_account(_B)["garmin_token_state"] == "ok"


@pytest.mark.unit
def test_the_expiry_uses_the_stored_values_when_the_connection_brought_none(db) -> None:
    """A connection without a valid name or profileId still stops athletes bound to the stored ones."""
    bind(db, _A, _ACCOUNT_A)
    set_token_ok(db, _A)
    db.conn.execute(
        "INSERT INTO owner_garmin_profile_history (garmin_profile_id, first_recorded_at) VALUES (?, 't')",
        (_PID_A,),
    )  # recorded earlier, without the expiry
    db.conn.commit()

    result = db.record_owner_garmin_identity(None, None)

    assert result["expired_athletes"] == [_A]
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"


@pytest.mark.unit
def test_an_owner_connection_without_a_profile_id_still_writes_the_name(db) -> None:
    result = db.record_owner_garmin_identity("owner-new-name", None)
    assert (result["changed"], result["name_recorded"], result["profile_id_recorded"]) == (True, True, False)
    assert db.get_owner_garmin_display_name() == "owner-new-name"
    assert _history(db) == [OWNER_GARMIN_PROFILE_ID]


# ── binding (point 4) ────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("value", _INVALID_IDS, ids=_INVALID_IDS_IDS)
def test_binding_refuses_an_invalid_profile_id(db, value) -> None:
    with pytest.raises(ValueError, match="profileId"):
        db.bind_garmin_account(_A, _ACCOUNT_A, value)
    assert db.get_athlete_account(_A) is None


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["history", "name", "both"])
def test_binding_refuses_while_the_owner_account_is_not_recorded(bare_db, missing) -> None:
    if missing == "history":
        bare_db.record_owner_garmin_identity(OWNER_GARMIN_NAME, None)
    elif missing == "name":
        bare_db.record_owner_garmin_identity(None, OWNER_GARMIN_PROFILE_ID)
    with pytest.raises(ValueError, match="owner's Garmin sync first"):
        bind(bare_db, _A, _ACCOUNT_A)
    assert bare_db.get_athlete_account(_A) is None


@pytest.mark.unit
def test_binding_refuses_any_owner_profile_id_even_an_old_one(db) -> None:
    record_owner(db, OWNER_GARMIN_NAME, _OWNER_NEW_PID)  # the owner's newer account
    for pid in (OWNER_GARMIN_PROFILE_ID, _OWNER_NEW_PID):
        with pytest.raises(ValueError, match="owner's Garmin account"):
            db.bind_garmin_account(_A, "some-new-name", pid)
    assert db.get_athlete_account(_A) is None


@pytest.mark.unit
def test_two_athletes_never_share_a_profile_id(db) -> None:
    db.bind_garmin_account(_A, _ACCOUNT_A, _PID_A)
    with pytest.raises(ValueError, match="another athlete"):
        db.bind_garmin_account(_B, "another-name", _PID_A)
    assert db.get_athlete_account(_B) is None


@pytest.mark.unit
def test_the_unique_index_backs_the_profile_id_check(db) -> None:
    db.bind_garmin_account(_A, _ACCOUNT_A, _PID_A)
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_profile_id, garmin_token_state, "
            "updated_at) VALUES (?, 'x', ?, 'missing', 't')",
            (_B, _PID_A),
        )
    db.conn.rollback()


@pytest.mark.unit
def test_rebinding_the_same_athlete_writes_both_columns_and_waits_for_a_token(db) -> None:
    db.conn.execute(
        "INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_token_state, updated_at) "
        "VALUES (?, ?, 'ok', 't')",
        (_A, _ACCOUNT_A),
    )  # a row bound before v36: no profileId
    db.conn.commit()

    db.bind_garmin_account(_A, _ACCOUNT_A, _PID_A)

    account = db.get_athlete_account(_A)
    assert (account["garmin_profile_id"], account["garmin_token_state"]) == (_PID_A, "missing")


@pytest.mark.unit
def test_binding_refuses_to_join_an_open_transaction(db) -> None:
    db.conn.execute("UPDATE athletes SET display_name = display_name WHERE athlete_id = ?", (_A,))
    with pytest.raises(RuntimeError, match="already open"):
        bind(db, _A, _ACCOUNT_A)
    db.conn.rollback()
    assert db.get_athlete_account(_A) is None


@pytest.mark.unit
def test_a_database_error_while_binding_is_a_refusal_without_values(db, monkeypatch) -> None:
    real = db._access._owner_garmin_identity

    def _locked(cursor):  # noqa: ANN001
        real(cursor)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db._access, "_owner_garmin_identity", _locked)
    with pytest.raises(ValueError) as refused:
        bind(db, _A, _ACCOUNT_A)
    assert str(_PID_A) not in str(refused.value) and _ACCOUNT_A not in str(refused.value)
    assert db.conn.in_transaction is False
    monkeypatch.undo()
    assert db.get_athlete_account(_A) is None


# ── the conditional 'ok' (point 4) ───────────────────────────────────────────


@pytest.mark.unit
def test_ok_only_from_missing_and_only_for_the_same_account(db) -> None:
    bind(db, _A, _ACCOUNT_A)
    assert db.confirm_garmin_token_ok(_A, _ACCOUNT_A, _PID_A + 1) is False
    assert db.confirm_garmin_token_ok(_A, "another", _PID_A) is False
    assert db.confirm_garmin_token_ok(_A, _ACCOUNT_A, _PID_A) is True
    assert db.get_athlete_account(_A)["garmin_token_state"] == "ok"


@pytest.mark.unit
def test_an_expired_row_never_becomes_ok(db) -> None:
    bind(db, _A, _ACCOUNT_A)
    db.set_garmin_token_state(_A, "expired")
    assert db.confirm_garmin_token_ok(_A, _ACCOUNT_A, _PID_A) is False
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"


@pytest.mark.unit
def test_ok_is_refused_when_the_account_became_the_owners(db) -> None:
    bind(db, _A, _ACCOUNT_A)
    db.conn.execute(
        "INSERT INTO owner_garmin_profile_history (garmin_profile_id, first_recorded_at) VALUES (?, 't')",
        (_PID_A,),
    )  # recorded without the expiry, to reach the re-check itself
    db.conn.commit()
    assert db.confirm_garmin_token_ok(_A, _ACCOUNT_A, _PID_A) is False
    assert db.get_athlete_account(_A)["garmin_token_state"] == "missing"


# ── relogin (point 3) ────────────────────────────────────────────────────────


def _fake_relogin_garmin(monkeypatch, profile, *, between=None) -> dict:  # noqa: ANN001
    """garminconnect for an athlete relogin; ``between`` runs while the token is written."""
    seen: dict = {"logins": 0}

    class _Garth:
        def dumps(self) -> str:
            if between is not None:
                between()
            return '{"oauth2": "synthetic"}'

    class _Garmin:
        def __init__(self, *_args, **_kwargs) -> None:
            self.client = _Garth()
            self.profile_id = True  # what the library may hold; never read
            self.display_name = "athlete@example.com"

        def login(self) -> None:
            seen["logins"] += 1

        def connectapi(self, _path):
            return profile

    module = MagicMock()
    module.Garmin = _Garmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return seen


def _relogin(db) -> str:  # noqa: ANN001
    return relogin_athlete(db, _A, "athlete@example.com", "synthetic-pass", None)


@pytest.mark.integration
def test_relogin_binds_both_values_and_sets_ok(db, key_file, monkeypatch) -> None:
    _fake_relogin_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})

    assert _relogin(db) == _ACCOUNT_A

    account = db.get_athlete_account(_A)
    assert (account["garmin_user_id"], account["garmin_profile_id"], account["garmin_token_state"]) == (
        _ACCOUNT_A, _PID_A, "ok",
    )
    assert athlete_token_path(_A).exists()


@pytest.mark.integration
@pytest.mark.parametrize("value", _INVALID_IDS, ids=_INVALID_IDS_IDS)
def test_relogin_refuses_an_invalid_profile_id(db, key_file, monkeypatch, value) -> None:
    _fake_relogin_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": value})
    with pytest.raises(RuntimeError, match="profileId"):
        _relogin(db)
    assert db.get_athlete_account(_A) is None
    assert not athlete_token_path(_A).exists()


@pytest.mark.integration
def test_relogin_with_the_owners_account_after_a_username_change_is_refused(db, key_file, monkeypatch) -> None:
    """The DB holds the owner's old name; the account answers with a new name and the same profileId."""
    _fake_relogin_garmin(monkeypatch, {"displayName": "owner-renamed", "profileId": OWNER_GARMIN_PROFILE_ID})
    with pytest.raises(ValueError, match="owner's Garmin account"):
        _relogin(db)
    assert db.get_athlete_account(_A) is None
    assert not athlete_token_path(_A).exists()


@pytest.mark.integration
def test_relogin_with_an_old_owner_profile_id_from_the_history_is_refused(db, key_file, monkeypatch) -> None:
    record_owner(db, OWNER_GARMIN_NAME, _OWNER_NEW_PID)  # the owner's current account is another one
    _fake_relogin_garmin(monkeypatch, {"displayName": "someone-new", "profileId": OWNER_GARMIN_PROFILE_ID})
    with pytest.raises(ValueError, match="owner's Garmin account"):
        _relogin(db)
    assert not athlete_token_path(_A).exists()


@pytest.mark.integration
def test_relogin_refuses_while_the_owner_history_is_empty(bare_db, key_file, monkeypatch) -> None:
    bare_db.record_owner_garmin_identity(OWNER_GARMIN_NAME, None)
    _fake_relogin_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})
    with pytest.raises(ValueError, match="owner's Garmin sync first"):
        _relogin(bare_db)
    assert bare_db.get_athlete_account(_A) is None


@pytest.mark.integration
def test_after_a_first_owner_connection_without_a_name_relogin_stays_closed(bare_db, key_file, monkeypatch) -> None:
    """The profileId is in the history and refuses; any other account is refused for the missing name."""
    bare_db.record_owner_garmin_identity(None, OWNER_GARMIN_PROFILE_ID)
    for profile in ({"displayName": "owner-name", "profileId": OWNER_GARMIN_PROFILE_ID},
                    {"displayName": _ACCOUNT_A, "profileId": _PID_A}):
        _fake_relogin_garmin(monkeypatch, profile)
        with pytest.raises(ValueError, match="owner"):
            _relogin(bare_db)
    assert bare_db.get_athlete_account(_A) is None


@pytest.mark.integration
def test_relogin_of_a_row_bound_before_v36_writes_the_profile_id_and_the_token_is_accepted(
    db, key_file, monkeypatch,
) -> None:
    db.conn.execute(
        "INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_token_state, updated_at) "
        "VALUES (?, ?, 'expired', 't')",
        (_A, _ACCOUNT_A),
    )
    db.conn.commit()
    _fake_relogin_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})

    _relogin(db)

    from titan import worker

    user_id, profile_id = worker._bound_garmin_account(db, _A)
    assert (user_id, profile_id) == (_ACCOUNT_A, _PID_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})
    sync = GarminSync(athlete_id=_A, expected_garmin_user_id=user_id, expected_garmin_profile_id=profile_id, db=db)
    assert sync.connect() is True


@pytest.mark.integration
def test_an_expiry_between_binding_and_token_fails_the_relogin_and_removes_the_token(
    db, key_file, data_dir, monkeypatch,
) -> None:
    """Point 4: the owner's connection on another connection makes A's account the owner's
    while the token is written. The relogin fails, the token goes, the row stays 'expired'."""
    other = DatabaseManager(db_dir=data_dir)

    def _owner_connects() -> None:
        other.record_owner_garmin_identity(OWNER_GARMIN_NAME, _PID_A)

    _fake_relogin_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A}, between=_owner_connects)
    try:
        with pytest.raises(ValueError, match="relogin again"):
            _relogin(db)
    finally:
        other.close()
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"
    assert not athlete_token_path(_A).exists()


@pytest.mark.integration
def test_relogin_never_shows_or_logs_the_profile_id(db, key_file, monkeypatch, caplog, capsys) -> None:
    _fake_relogin_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _SECRET_LOOKING_PID})
    caplog.set_level(logging.DEBUG)

    assert _relogin(db) == _ACCOUNT_A
    record_owner(db, OWNER_GARMIN_NAME, _SECRET_LOOKING_PID + 1)

    from scripts import athletes as cli

    cli.cmd_list(None, db)
    printed = capsys.readouterr()
    for text in (caplog.text, printed.out, printed.err):
        assert str(_SECRET_LOOKING_PID) not in text
        assert str(_SECRET_LOOKING_PID + 1) not in text


@pytest.mark.integration
def test_a_refused_relogin_message_has_no_profile_id(db, key_file, monkeypatch) -> None:
    _fake_relogin_garmin(monkeypatch, {"displayName": "x", "profileId": OWNER_GARMIN_PROFILE_ID})
    with pytest.raises(ValueError) as refused:
        _relogin(db)
    assert str(OWNER_GARMIN_PROFILE_ID) not in str(refused.value)


@pytest.mark.integration
def test_the_export_of_an_athlete_has_their_own_profile_id(db) -> None:
    from titan.core import athlete_lifecycle as lifecycle

    bind(db, _A, _ACCOUNT_A)
    exported = lifecycle.export_athlete(db, _A)
    assert [row["garmin_profile_id"] for row in exported["tables"]["athlete_accounts"]] == [_PID_A]
    assert "owner_garmin_profile_history" not in exported["tables"]


# ── the token check (point 5) ────────────────────────────────────────────────


def _fake_token_garmin(monkeypatch, profile, *, ping_error: Exception | None = None,  # noqa: ANN001
                       summary_error: Exception | None = None) -> dict:
    seen = {"summary_calls": 0, "logins": 0}

    class _Garth:
        def loads(self, _data: str) -> None:
            return None

    class _Garmin:
        def __init__(self, *_args) -> None:
            self.client = _Garth()

        def connectapi(self, _path):
            if ping_error is not None:
                raise ping_error
            return profile

        def get_user_summary(self, _day):
            seen["summary_calls"] += 1
            if summary_error is not None:
                raise summary_error
            return {}

        def login(self) -> None:
            seen["logins"] += 1

    module = MagicMock()
    module.Garmin = _Garmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return seen


def _store_token(athlete_id: str) -> None:
    path = athlete_token_path(athlete_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_athlete_token("synthetic-session"))


def _sync_a(db, *, profile_id=_PID_A, account=_ACCOUNT_A, with_db=True) -> GarminSync:  # noqa: ANN001
    return GarminSync(
        athlete_id=_A, expected_garmin_user_id=account, expected_garmin_profile_id=profile_id,
        db=db if with_db else None,
    )


@pytest.mark.integration
def test_the_token_of_the_bound_account_is_accepted(db, key_file, monkeypatch) -> None:
    _store_token(_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})
    assert _sync_a(db).connect() is True


@pytest.mark.integration
@pytest.mark.parametrize(
    "profile",
    [
        {"displayName": _ACCOUNT_A, "profileId": _PID_A + 1},
        {"displayName": "garmin-other", "profileId": _PID_A},
        {"displayName": _ACCOUNT_A},
        {"profileId": _PID_A},
        None,
        ["x"],
    ],
    ids=["same-name-other-id", "same-id-other-name", "no-id", "no-name", "none", "not-a-dict"],
)
def test_a_token_that_does_not_match_both_values_is_refused(db, key_file, monkeypatch, profile) -> None:
    _store_token(_A)
    _fake_token_garmin(monkeypatch, profile)
    sync = _sync_a(db)
    assert sync.connect() is False
    assert sync.token_expired is True
    assert athlete_token_path(_A).exists()  # left as found


@pytest.mark.integration
@pytest.mark.parametrize("value", _INVALID_IDS, ids=_INVALID_IDS_IDS)
def test_an_invalid_profile_id_on_either_side_is_refused(db, key_file, monkeypatch, value) -> None:
    _store_token(_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": value})
    assert _sync_a(db).connect() is False
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": value})
    assert _sync_a(db, profile_id=value).connect() is False


@pytest.mark.integration
def test_without_the_new_argument_or_a_bound_profile_id_every_token_is_refused(db, key_file, monkeypatch) -> None:
    _store_token(_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})
    assert GarminSync(athlete_id=_A, expected_garmin_user_id=_ACCOUNT_A, db=db).connect() is False
    assert _sync_a(db, profile_id=None).connect() is False


@pytest.mark.integration
def test_an_athlete_sync_without_a_database_refuses_every_token(db, key_file, monkeypatch) -> None:
    _store_token(_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})
    sync = _sync_a(db, with_db=False)
    assert sync.connect() is False
    assert sync.token_expired is False  # a setup fault is not a relogin; the token is kept
    assert athlete_token_path(_A).exists()


@pytest.mark.integration
def test_an_unreadable_owner_record_refuses_the_token(db, key_file, monkeypatch) -> None:
    _store_token(_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})
    broken = MagicMock()
    broken.get_owner_garmin_display_name.return_value = OWNER_GARMIN_NAME
    broken.get_owner_garmin_profile_ids.side_effect = sqlite3.OperationalError("database is locked")
    sync = _sync_a(broken)
    assert sync.connect() is False
    # A passing fault (database locked) refuses the token but does not pause the athlete
    # for a relogin, like the rate-limited check.
    assert sync.token_expired is False
    assert athlete_token_path(_A).exists()


@pytest.mark.integration
def test_an_empty_owner_history_refuses_the_token(bare_db, key_file, monkeypatch) -> None:
    bare_db.record_owner_garmin_identity(OWNER_GARMIN_NAME, None)
    _store_token(_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _PID_A})
    assert _sync_a(bare_db).connect() is False


@pytest.mark.integration
@pytest.mark.parametrize("which", ["owner-profile-id", "owner-name"])
def test_a_token_answering_for_the_owner_is_refused(db, key_file, monkeypatch, which) -> None:
    """Defence in depth: an athlete bound to the owner's account stops before the owner's next sync."""
    _store_token(_A)
    if which == "owner-profile-id":
        db.conn.execute(
            "INSERT INTO owner_garmin_profile_history (garmin_profile_id, first_recorded_at) VALUES (?, 't')",
            (_PID_A,),
        )
        db.conn.commit()
        account = _ACCOUNT_A
    else:
        account = OWNER_GARMIN_NAME
    _fake_token_garmin(monkeypatch, {"displayName": account, "profileId": _PID_A})
    sync = _sync_a(db, account=account)
    assert sync.connect() is False
    assert sync.token_expired is True  # the athlete is paused until relogin


@pytest.mark.integration
def test_an_athlete_never_reaches_the_assumed_valid_branch_after_429(db, key_file, monkeypatch) -> None:
    _store_token(_A)
    seen = _fake_token_garmin(monkeypatch, None, ping_error=RuntimeError("429 Too Many Requests"))
    sync = _sync_a(db)
    assert sync.connect() is False
    assert sync.is_connected is False
    assert seen["summary_calls"] == 0 and seen["logins"] == 0


@pytest.mark.integration
def test_a_refused_token_logs_no_value(db, key_file, monkeypatch, caplog) -> None:
    _store_token(_A)
    _fake_token_garmin(monkeypatch, {"displayName": _ACCOUNT_A, "profileId": _SECRET_LOOKING_PID})
    caplog.set_level(logging.DEBUG)
    assert _sync_a(db).connect() is False
    assert str(_SECRET_LOOKING_PID) not in caplog.text
    assert str(_PID_A) not in caplog.text


# ── the owner's connection ───────────────────────────────────────────────────


@pytest.fixture
def owner_dev(data_dir, monkeypatch):
    monkeypatch.setenv("TITAN_ENV", "dev")
    monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
    monkeypatch.setenv("GARMIN_PASSWORD", "PLANTED_OWNER_PASSWORD")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    path = garmin_sync._get_garth_token_path()
    path.write_bytes(b"owner-session")
    return path


@pytest.mark.integration
def test_the_owner_connection_records_the_profile_id_and_warns_only_on_a_second_one(
    owner_dev, bare_db, monkeypatch, caplog,
) -> None:
    caplog.set_level(logging.INFO)
    _fake_token_garmin(monkeypatch, {"displayName": OWNER_GARMIN_NAME, "profileId": _SECRET_LOOKING_PID})
    assert GarminSync(db=bare_db).connect() is True
    assert _history(bare_db) == [_SECRET_LOOKING_PID]
    assert "owner_garmin_profile_id_added" not in caplog.text

    _fake_token_garmin(monkeypatch, {"displayName": OWNER_GARMIN_NAME, "profileId": _SECRET_LOOKING_PID + 1})
    assert GarminSync(db=bare_db).connect() is True
    assert _history(bare_db) == [_SECRET_LOOKING_PID, _SECRET_LOOKING_PID + 1]
    assert "owner_garmin_profile_id_added" in caplog.text
    assert str(_SECRET_LOOKING_PID) not in caplog.text and str(_SECRET_LOOKING_PID + 1) not in caplog.text

    # The first one still refuses an athlete.
    with pytest.raises(ValueError, match="owner's Garmin account"):
        bare_db.bind_garmin_account(_A, "someone", _SECRET_LOOKING_PID)


@pytest.mark.integration
@pytest.mark.parametrize("profile", [{"displayName": OWNER_GARMIN_NAME}, {}, None, ["x"]],
                         ids=["no-id", "empty", "none", "not-a-dict"])
def test_an_owner_profile_without_a_valid_id_still_runs_the_expiry_with_stored_values(
    owner_dev, db, monkeypatch, profile,
) -> None:
    bind(db, _A, _ACCOUNT_A)
    set_token_ok(db, _A)
    db.conn.execute(
        "INSERT INTO owner_garmin_profile_history (garmin_profile_id, first_recorded_at) VALUES (?, 't')",
        (_PID_A,),
    )  # recorded earlier, without the expiry
    db.conn.commit()
    _fake_token_garmin(monkeypatch, profile)

    assert GarminSync(db=db).connect() is True

    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"
    assert db.get_owner_garmin_display_name() == OWNER_GARMIN_NAME
    assert _PID_A in db.get_owner_garmin_profile_ids() and OWNER_GARMIN_PROFILE_ID in db.get_owner_garmin_profile_ids()


@pytest.mark.integration
@pytest.mark.parametrize("summary_error", [None, RuntimeError("429 Too Many Requests")],
                         ids=["secondary-call-succeeds", "secondary-call-also-429"])
def test_the_owner_429_branches_write_no_profile_id(owner_dev, bare_db, monkeypatch, summary_error) -> None:
    _fake_token_garmin(monkeypatch, {"displayName": "x", "profileId": 7},
                       ping_error=RuntimeError("429 Too Many Requests"), summary_error=summary_error)
    assert GarminSync(db=bare_db).connect() is True
    assert _history(bare_db) == []


# ── worker ───────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_the_worker_treats_a_row_without_a_profile_id_as_unbound(db, key_file) -> None:
    from titan import worker
    from titan.core.athlete import AthleteNotReady

    db.conn.execute(
        "INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_token_state, updated_at) "
        "VALUES (?, ?, 'ok', 't')",
        (_A, _ACCOUNT_A),
    )
    db.conn.commit()
    _store_token(_A)
    with pytest.raises(AthleteNotReady, match="no account bound"):
        worker._require_garmin_ready(db, _A)


@pytest.mark.integration
@pytest.mark.parametrize("place", ["sync_athlete_on_request", "_build_daily_coach"])
def test_both_worker_places_give_the_athlete_sync_the_database_and_the_profile_id(
    db, key_file, monkeypatch, place,
) -> None:
    from titan import worker
    from titan.integrations import garmin_sync as garmin_module

    built: list[dict] = []

    class _Stop(Exception):
        pass

    def _capture(*_args, **kwargs):
        built.append(kwargs)
        raise _Stop

    for name in ("_require_consent", "_require_garmin_ready", "_require_telegram_ready"):
        monkeypatch.setattr(worker, name, lambda *_a, **_k: None)
    monkeypatch.setattr("titan.core.athlete.load_athlete_profile", lambda *_a, **_k: MagicMock(max_hr=180))
    monkeypatch.setattr(garmin_module, "GarminSync", _capture)
    monkeypatch.setattr("titan.orchestration.engine_registry.EngineRegistry.from_db", lambda **_k: MagicMock())
    monkeypatch.setattr("titan.integrations.weather_api.WeatherAPI", lambda **_k: MagicMock())
    bind(db, _A, _ACCOUNT_A)

    with pytest.raises(_Stop):
        getattr(worker, place)(db, _A)

    assert built == [{
        "athlete_id": _A, "expected_garmin_user_id": _ACCOUNT_A,
        "expected_garmin_profile_id": _PID_A, "db": db,
    }]


# ── the v36 step ─────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_v36_expires_only_rows_bound_without_a_profile_id_and_only_on_the_version_change(data_dir) -> None:
    first = _new_db(data_dir)
    first.bind_telegram_chat(_B, "1002")  # a row with a Telegram chat only
    first.conn.execute(
        "INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_token_state, updated_at) "
        "VALUES (?, ?, 'ok', 't')",
        (_A, _ACCOUNT_A),
    )
    first.conn.execute("PRAGMA user_version = 35")
    first.conn.commit()
    first.close()

    reopened = _new_db(data_dir)
    try:
        assert reopened.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert reopened.get_athlete_account(_A)["garmin_token_state"] == "expired"
        assert reopened.get_athlete_account(_B)["garmin_token_state"] == "missing"
        reopened.conn.execute("UPDATE athlete_accounts SET garmin_token_state = 'ok' WHERE athlete_id = ?", (_A,))
        reopened.conn.commit()
    finally:
        reopened.close()

    again = _new_db(data_dir)
    try:
        assert again.get_athlete_account(_A)["garmin_token_state"] == "ok"  # not re-run on a later start
    finally:
        again.close()


# ── the manual step of the runbook (point 2) ─────────────────────────────────


def _runbook_sql_block() -> str:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "docs" / "runbooks" / "multi-athlete.md").read_text(encoding="utf-8")
    blocks = text.split("```sql\n")[1:]
    assert len(blocks) == 1, "the runbook has exactly one sql block: the manual step of ADR-0083"
    return blocks[0].split("```")[0]


def _statements(block: str) -> list[str]:
    statements, current = [], ""
    for line in block.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            statements.append(current.strip().rstrip(";"))
            current = ""
    assert not current.strip()
    return statements


@pytest.mark.unit
def test_the_runbook_step_drops_and_recreates_exactly_the_defined_triggers() -> None:
    from titan.core.repositories.migrations import OWNER_GARMIN_PROFILE_HISTORY_TRIGGERS

    statements = _statements(_runbook_sql_block())
    for name, sql in OWNER_GARMIN_PROFILE_HISTORY_TRIGGERS.items():
        assert f"DROP TRIGGER IF EXISTS {name}" in statements
        assert sql in statements
    assert statements[0] == "BEGIN IMMEDIATE" and statements[-1] == "COMMIT"


@pytest.mark.unit
def test_the_runbook_step_removes_one_row_and_puts_the_triggers_back(db) -> None:
    record_owner(db, OWNER_GARMIN_NAME, _PID_A)  # the mistake: .env pointed to A's account once
    before = {
        r[0]: r[1] for r in db.conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")
    }

    for statement in _statements(_runbook_sql_block()):
        params = {"profile_id": _PID_A} if ":profile_id" in statement else {}
        db.conn.execute(statement, params)

    assert _history(db) == [OWNER_GARMIN_PROFILE_ID]
    after = {r[0]: r[1] for r in db.conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")}
    assert after == before
    with pytest.raises(sqlite3.IntegrityError, match="ADR-0083"):
        db.conn.execute("DELETE FROM owner_garmin_profile_history")
    db.conn.rollback()
    bind(db, _A, _ACCOUNT_A)  # A binds again


@pytest.mark.unit
def test_the_name_only_record_runs_the_expiry_even_without_a_name(db) -> None:
    """The ADR-0076 wrapper goes through the full record, so point 6 runs for an empty name too."""
    bind(db, _A, _ACCOUNT_A)
    set_token_ok(db, _A)
    db.conn.execute(
        "INSERT INTO owner_garmin_profile_history (garmin_profile_id, first_recorded_at) VALUES (?, 't')",
        (_PID_A,),
    )
    db.conn.commit()

    assert db.record_owner_garmin_display_name("  ") is None
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"


@pytest.mark.unit
def test_a_failed_history_write_rolls_back_the_name_and_the_expiry(db) -> None:
    """Only the history insert fails: the name written before it and the expiry are rolled back."""
    bind(db, _A, "owner-renamed")
    set_token_ok(db, _A)
    db.conn.execute(
        "CREATE TEMP TRIGGER fail_history_insert BEFORE INSERT ON owner_garmin_profile_history "
        "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
    )
    db.conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        db.record_owner_garmin_identity("owner-renamed", _OWNER_NEW_PID)

    assert db.get_owner_garmin_display_name() == OWNER_GARMIN_NAME
    assert _history(db) == [OWNER_GARMIN_PROFILE_ID]
    assert db.get_athlete_account(_A)["garmin_token_state"] == "ok"
    assert db.conn.in_transaction is False


@pytest.mark.integration
def test_an_open_transaction_is_logged_by_its_own_class(owner_dev, db, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO)
    _fake_token_garmin(monkeypatch, {"displayName": OWNER_GARMIN_NAME, "profileId": OWNER_GARMIN_PROFILE_ID})
    db.conn.execute("UPDATE athletes SET display_name = display_name WHERE athlete_id = ?", (_A,))

    assert GarminSync(db=db).connect() is True  # the owner's morning never stops for it

    db.conn.rollback()
    assert "owner_identity_not_recorded" in caplog.text and "OpenTransactionError" in caplog.text
