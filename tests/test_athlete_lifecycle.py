"""Phase 4 step 8: add, relogin, export and remove an athlete (ADR-0067 D2, D4.3, D6, D9; D-097).

- Add: generated opaque id, full profile and private chat, nothing written when refused.
- Relogin: the athlete's password goes to Garmin only; the encrypted token is kept, 0600.
- Export: every row of the athlete in every table with an athlete_id column, found in the schema.
- Remove: record first, every row in one transaction, the token folder; a restore deletes again.
- 30 days after /stop the athlete is deleted.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import sqlite3
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from titan.core import athlete_lifecycle as lifecycle
from titan.core.database import DatabaseManager

_PROFILE = {
    "birth_date": "1988-07-02", "sex": "F", "weight_kg": 58.0, "height_cm": 165,
    "max_hr": 186, "threshold_hr": 166, "training_phase": "BASE", "training_goal": "10K",
    "location_city": "Volos", "location_country": "GR",
}
OWNER_CHAT = 1000
_NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    keys = tmp_path / "keys"
    keys.mkdir()
    key_file = keys / "athletes.key"
    key_file.write_bytes(Fernet.generate_key())
    os.chmod(key_file, 0o600)
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TITAN_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER_CHAT))
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(key_file))
    # relogin refuses to run without the owner's Garmin e-mail (M0-13)
    monkeypatch.setenv("GARMIN_EMAIL", "owner@example.invalid")
    monkeypatch.setenv(lifecycle.DELETION_RECORD_ENV, str(tmp_path / "records" / "deletions.jsonl"))
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def db(env):
    manager = DatabaseManager(db_dir=env / "data")
    yield manager
    manager.close()


def _add(db: DatabaseManager, name: str, chat: int) -> str:
    return lifecycle.add_athlete(db, name, dict(_PROFILE), chat, now=_NOW)


def _seed(db: DatabaseManager, athlete_id: str, chat: int) -> None:
    """Rows in several athlete tables, as a coached athlete would have."""
    db.grant_consent(athlete_id, "v1", now=_NOW - timedelta(days=40))
    db.bind_garmin_account(athlete_id, f"garmin-{athlete_id}")
    db.set_garmin_token_state(athlete_id, "ok")
    from titan.integrations.garmin_sync import (
        athlete_token_path,  # a ready athlete has the token file (MA-F2)
    )
    athlete_token_path(athlete_id).parent.mkdir(parents=True, exist_ok=True)
    athlete_token_path(athlete_id).write_bytes(b"synthetic-token")
    db.assign_athlete_to_coach("coach-1", athlete_id)
    db.log_coach_action(coach_id=f"telegram:{chat}", action_type="TELEGRAM_SYNC",
                        target_athlete_id=athlete_id, resource="telegram")
    db.conn.execute(
        "INSERT INTO training_log (athlete_id, date, session_type, distance_km, duration_sec, training_load) "
        "VALUES (?, '2026-10-10', 'EASY', 8.0, 2400, 55)",
        (athlete_id,),
    )
    db.conn.commit()


def _rows(db: DatabaseManager, athlete_id: str) -> dict[str, int]:
    counts = {}
    for table in lifecycle.athlete_tables(db):
        n = db.conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE athlete_id = ?', (athlete_id,)).fetchone()[0]  # nosec B608
        if n:
            counts[table] = n
    return counts


def _token(athlete_id: str) -> Path:
    from titan.integrations.garmin_sync import athlete_token_path

    return athlete_token_path(athlete_id)


def _write_token(athlete_id: str) -> Path:
    from titan.integrations.garmin_sync import write_athlete_token

    return write_athlete_token(athlete_id, '{"session": "s"}')


# ── Add ───────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_add_gives_an_opaque_id_with_profile_and_chat(db) -> None:
    athlete_id = _add(db, "Maria", 2000)

    assert lifecycle._ATHLETE_ID.fullmatch(athlete_id)
    assert db.get_athlete_for_telegram_chat(2000) == athlete_id
    assert db.conn.execute("SELECT display_name FROM athletes WHERE athlete_id = ?", (athlete_id,)).fetchone() == (
        "Maria",
    )
    assert not db.has_current_consent(athlete_id)  # consent comes from the athlete, not from add


@pytest.mark.integration
@pytest.mark.parametrize(("profile", "chat", "match"), [
    ({**_PROFILE, "birth_date": "2010-01-01"}, 2000, "under 18"),
    ({k: v for k, v in _PROFILE.items() if k != "location_city"}, 2000, "location_city"),
    (_PROFILE, OWNER_CHAT, "owner"),
])
def test_a_refused_add_writes_nothing(db, profile, chat, match) -> None:
    with pytest.raises(ValueError, match=match):
        lifecycle.add_athlete(db, "Maria", dict(profile), chat, now=_NOW)

    assert db.conn.execute("SELECT COUNT(*) FROM athletes WHERE athlete_id != 'owner'").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM athlete_profiles").fetchone()[0] == 0


# ── Relogin ───────────────────────────────────────────────────────────────────


_FROM_DISPLAY_NAME = object()


def _fake_garmin(monkeypatch, display_name: str = "maria-runs", social_profile=_FROM_DISPLAY_NAME) -> dict:
    """Fake garminconnect. ``social_profile`` is what the socialProfile call returns; by default
    it carries ``display_name``. The library fills ``client.display_name`` with the login e-mail
    when the profile has no displayName (0.3.17), which the IS-07 tests reproduce."""
    seen: dict = {}
    profile = {"displayName": display_name} if social_profile is _FROM_DISPLAY_NAME else social_profile

    class _Garth:
        def dumps(self) -> str:
            return '{"oauth2": "token-of-maria"}'

    class _Garmin:
        def __init__(self, email, password, prompt_mfa=None) -> None:
            seen["credentials"] = (email, password)
            seen["mfa"] = prompt_mfa
            self.client = _Garth()
            self.display_name = display_name

        def login(self):
            seen["mfa_code"] = self_mfa = seen["mfa"]() if seen["mfa"] else None
            return self_mfa

        def connectapi(self, path):
            seen.setdefault("api", []).append(path)
            return profile

    module = MagicMock()
    module.Garmin = _Garmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return seen


@pytest.mark.integration
def test_relogin_keeps_only_the_encrypted_token(db, monkeypatch, caplog) -> None:
    from titan.integrations.garmin_sync import decrypt_athlete_token, relogin_athlete

    seen = _fake_garmin(monkeypatch)
    athlete_id = _add(db, "Maria", 2000)
    caplog.set_level(logging.DEBUG)

    assert relogin_athlete(db, athlete_id, "maria@example.com", "s3cret-pass", lambda: "123456") == "maria-runs"

    path = _token(athlete_id)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert decrypt_athlete_token(path.read_bytes()) == '{"oauth2": "token-of-maria"}'
    assert seen["mfa_code"] == "123456"
    account = db.get_athlete_account(athlete_id)
    assert (account["garmin_user_id"], account["garmin_token_state"]) == ("maria-runs", "ok")
    dump = "\n".join(db.conn.iterdump()) + caplog.text + path.read_bytes().decode()
    assert "s3cret-pass" not in dump and "maria@example.com" not in dump


@pytest.mark.integration
def test_relogin_refuses_an_account_of_another_athlete_before_writing(db, monkeypatch) -> None:
    from titan.integrations.garmin_sync import relogin_athlete

    _fake_garmin(monkeypatch, display_name="shared-account")
    first, second = _add(db, "Maria", 2000), _add(db, "Nikos", 3000)
    relogin_athlete(db, first, "a@example.com", "p", None)

    with pytest.raises(ValueError):
        relogin_athlete(db, second, "a@example.com", "p", None)
    assert not _token(second).exists()


@pytest.mark.integration
@pytest.mark.parametrize("typed", ["zaf@example.com", "  Zaf@Example.COM "])
def test_relogin_refuses_the_owners_garmin_login_before_garmin_is_called(db, monkeypatch, typed) -> None:
    """M0-13: the owner's account has no athlete_accounts row, so the D9.4 check alone let it
    be bound to an athlete, who would then get briefings built from the owner's data."""
    from titan.config.settings import get_settings
    from titan.integrations.garmin_sync import relogin_athlete

    monkeypatch.setenv("GARMIN_EMAIL", "zaf@example.com")
    get_settings.cache_clear()
    seen = _fake_garmin(monkeypatch, display_name="zaf-owner")
    athlete_id = _add(db, "Maria", 2000)

    with pytest.raises(ValueError, match="owner"):
        relogin_athlete(db, athlete_id, typed, "p", None)
    assert "credentials" not in seen, "Garmin must not be called with the owner's login"
    assert not _token(athlete_id).exists()
    assert db.get_athlete_account(athlete_id)["garmin_user_id"] is None


@pytest.mark.integration
def test_relogin_refuses_to_run_when_the_owner_email_is_not_set(db, monkeypatch) -> None:
    """M0-13 review: without GARMIN_EMAIL the owner's account cannot be recognised, so relogin
    stops before Garmin is called instead of skipping the check (fail closed)."""
    from titan.config.settings import get_settings
    from titan.integrations.garmin_sync import relogin_athlete

    monkeypatch.setenv("GARMIN_EMAIL", "")
    get_settings.cache_clear()
    seen = _fake_garmin(monkeypatch, display_name="zaf-owner")
    athlete_id = _add(db, "Maria", 2000)

    with pytest.raises(ValueError, match="GARMIN_EMAIL"):
        relogin_athlete(db, athlete_id, "zaf@example.com", "p", None)
    assert "credentials" not in seen, "Garmin must not be called without the owner check"
    assert not _token(athlete_id).exists()


@pytest.mark.integration
def test_relogin_with_another_email_still_works_when_the_owner_email_is_set(db, monkeypatch) -> None:
    from titan.config.settings import get_settings
    from titan.integrations.garmin_sync import relogin_athlete

    monkeypatch.setenv("GARMIN_EMAIL", "zaf@example.com")
    get_settings.cache_clear()
    _fake_garmin(monkeypatch)
    athlete_id = _add(db, "Maria", 2000)
    assert relogin_athlete(db, athlete_id, "maria@example.com", "p", None) == "maria-runs"


@pytest.mark.integration
@pytest.mark.parametrize("tokenstore", ["/tmp/owner-tokens", '{"di_token": "x"}', " "])
def test_relogin_refuses_when_garmintokens_is_set_before_garmin_is_called(db, monkeypatch, tokenstore) -> None:
    """IS-06: garminconnect's login() reads GARMINTOKENS when no tokenstore is passed. It would
    then log in with the tokens found there (perhaps the owner's) instead of the athlete's
    password, or write the athlete's token there before any refusal. Relogin stops first."""
    from titan.config.settings import get_settings
    from titan.integrations.garmin_sync import relogin_athlete

    monkeypatch.setenv("GARMIN_EMAIL", "zaf@example.com")
    monkeypatch.setenv("GARMINTOKENS", tokenstore)
    get_settings.cache_clear()
    seen = _fake_garmin(monkeypatch)
    athlete_id = _add(db, "Maria", 2000)

    with pytest.raises(ValueError, match="GARMINTOKENS"):
        relogin_athlete(db, athlete_id, "maria@example.com", "p", None)
    assert "credentials" not in seen, "Garmin must not be called while GARMINTOKENS is set"
    assert not _token(athlete_id).exists()
    assert db.get_athlete_account(athlete_id)["garmin_user_id"] is None


@pytest.mark.integration
@pytest.mark.parametrize("social_profile", [{}, {"displayName": "  "}, {"displayName": None}, None, ["x"]])
def test_relogin_refuses_when_the_social_profile_has_no_display_name(db, monkeypatch, social_profile) -> None:
    """IS-07: without a displayName the library sets ``client.display_name`` to the login e-mail.
    Relogin must not bind that e-mail as the account id; it refuses before binding or writing."""
    from titan.integrations.garmin_sync import relogin_athlete

    _fake_garmin(monkeypatch, display_name="maria@example.com", social_profile=social_profile)
    athlete_id = _add(db, "Maria", 2000)

    with pytest.raises(RuntimeError, match="displayName"):
        relogin_athlete(db, athlete_id, "maria@example.com", "p", None)
    assert not _token(athlete_id).exists()
    account = db.get_athlete_account(athlete_id)
    assert account["garmin_user_id"] is None
    assert account["garmin_token_state"] != "ok"


@pytest.mark.integration
def test_relogin_binds_the_social_profile_display_name_not_the_client_attribute(db, monkeypatch) -> None:
    """IS-07: the bound id is the socialProfile displayName (stripped), the same value the token
    check compares (``_token_account_matches``), never ``client.display_name``."""
    from titan.integrations.garmin_sync import relogin_athlete

    seen = _fake_garmin(monkeypatch, display_name="maria@example.com", social_profile={"displayName": " maria-runs "})
    athlete_id = _add(db, "Maria", 2000)

    assert relogin_athlete(db, athlete_id, "maria@example.com", "p", None) == "maria-runs"
    assert db.get_athlete_account(athlete_id)["garmin_user_id"] == "maria-runs"
    assert seen["api"] == ["userprofile-service/socialProfile"]


@pytest.mark.integration
def test_on_windows_no_token_is_written_without_the_acl(db, env, monkeypatch) -> None:
    from titan.integrations import garmin_sync

    athlete_id = _add(db, "Maria", 2000)
    monkeypatch.setattr(garmin_sync, "_restrict_to_current_user", MagicMock(side_effect=OSError("icacls failed")))
    monkeypatch.setattr(garmin_sync, "_on_windows", lambda: True)
    with pytest.raises(OSError, match="icacls"):
        garmin_sync.write_athlete_token(athlete_id, '{"session": "s"}')
    assert not _token(athlete_id).exists()


@pytest.mark.unit
def test_the_token_folder_is_the_one_garmin_uses(env) -> None:
    assert lifecycle._token_folder("a-0000000a") == _token("a-0000000a").parent


# ── Export ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_export_has_every_row_of_that_athlete_only(db) -> None:
    maria, nikos = _add(db, "Maria", 2000), _add(db, "Nikos", 3000)
    _seed(db, maria, 2000)
    _seed(db, nikos, 3000)
    # A table added later is found from the schema, not from a list.
    db.conn.execute("CREATE TABLE future_table (athlete_id TEXT NOT NULL, value TEXT)")
    db.conn.execute("INSERT INTO future_table VALUES (?, 'later')", (maria,))
    db.conn.commit()

    document = lifecycle.export_athlete(db, maria, now=_NOW)

    assert document["athlete_id"] == maria
    counts = {table: len(rows) for table, rows in document["tables"].items() if rows}
    assert counts == _rows(db, maria)
    assert counts["future_table"] == 1 and counts["training_log"] == 1
    assert all(row["athlete_id"] == maria for rows in document["tables"].values() for row in rows)
    assert json.loads(lifecycle.export_json(document))["tables"]["future_table"] == [
        {"athlete_id": maria, "value": "later"}
    ]


@pytest.mark.integration
def test_export_refuses_the_owner_and_an_unknown_id(db) -> None:
    with pytest.raises(ValueError, match="owner"):
        lifecycle.export_athlete(db, "owner")
    with pytest.raises(LookupError):
        lifecycle.export_athlete(db, "a-0000dead")


# ── Remove ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_remove_deletes_every_row_and_the_token_and_keeps_a_record(db, env) -> None:
    maria, nikos = _add(db, "Maria", 2000), _add(db, "Nikos", 3000)
    _seed(db, maria, 2000)
    _seed(db, nikos, 3000)
    _write_token(maria)
    _write_token(nikos)
    nikos_rows, owner_rows = _rows(db, nikos), _rows(db, "owner")

    lifecycle.delete_athlete(db, maria, now=_NOW)

    assert _rows(db, maria) == {}
    assert _rows(db, nikos) == nikos_rows and _rows(db, "owner") == owner_rows
    assert not _token(maria).parent.exists() and _token(nikos).exists()
    assert lifecycle.read_deletion_records() == [{"athlete_id": maria, "deleted_at": _NOW.isoformat()}]


@pytest.mark.integration
def test_remove_without_a_record_file_outside_the_data_changes_nothing(db, env, monkeypatch) -> None:
    maria = _add(db, "Maria", 2000)
    before = _rows(db, maria)

    monkeypatch.delenv(lifecycle.DELETION_RECORD_ENV)
    with pytest.raises(RuntimeError, match="not set"):
        lifecycle.delete_athlete(db, maria)
    monkeypatch.setenv(lifecycle.DELETION_RECORD_ENV, str(env / "data" / "deletions.jsonl"))
    with pytest.raises(RuntimeError, match="outside the data folder"):
        lifecycle.delete_athlete(db, maria)
    monkeypatch.setenv(lifecycle.DELETION_RECORD_ENV, str(env / "backups" / "deletions.jsonl"))
    with pytest.raises(RuntimeError, match="outside the backup folder"):
        lifecycle.delete_athlete(db, maria)

    assert _rows(db, maria) == before
    with pytest.raises(ValueError, match="owner"):
        lifecycle.delete_athlete(db, "owner")


@pytest.mark.integration
def test_a_failed_delete_rolls_back_every_table(db, monkeypatch) -> None:
    maria = _add(db, "Maria", 2000)
    _seed(db, maria, 2000)
    before = _rows(db, maria)
    tables = lifecycle.athlete_tables(db)
    monkeypatch.setattr(lifecycle, "athlete_tables", lambda _db: [*tables[:3], "no_such_table", *tables[3:]])

    with pytest.raises(sqlite3.OperationalError):
        lifecycle.delete_athlete(db, maria, now=_NOW)
    monkeypatch.undo()

    assert _rows(db, maria) == before


@pytest.mark.integration
def test_a_restore_deletes_the_athlete_again(db, env) -> None:
    maria, nikos = _add(db, "Maria", 2000), _add(db, "Nikos", 3000)
    _seed(db, maria, 2000)
    backup = env / "snapshot.db"
    db.conn.commit()
    with sqlite3.connect(backup) as target:
        db.conn.backup(target)
    lifecycle.delete_athlete(db, maria, now=_NOW)
    db.close()

    shutil.copy(backup, env / "data" / "titan_core.db")
    restored = DatabaseManager(db_dir=env / "data")
    try:
        assert _rows(restored, maria)
        assert lifecycle.reapply_deletions(restored) == [maria]
        assert _rows(restored, maria) == {}
        assert _rows(restored, nikos)
        assert lifecycle.reapply_deletions(restored) == []
    finally:
        restored.close()


@pytest.mark.integration
def test_a_deletion_record_naming_the_owner_or_no_athlete_deletes_nothing_of_theirs(db, env, caplog) -> None:
    """OW-L2: a record line for 'owner' or a malformed id is refused; the real athletes still go."""
    maria = _add(db, "Maria", 2000)
    _seed(db, maria, 2000)
    db.save_daily_metric("2026-10-20", hrv=50.0, athlete_id="owner")
    record = lifecycle.deletion_record_path()
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(
        "".join(json.dumps({"athlete_id": who, "deleted_at": "2026-10-01"}) + "\n" for who in ("owner", "", "x'; --", maria)),
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR, logger=lifecycle._log.name):
        assert lifecycle.reapply_deletions(db) == [maria]

    owner_rows = db.conn.execute("SELECT COUNT(*) FROM daily_metrics WHERE athlete_id = 'owner'").fetchone()[0]
    assert owner_rows == 1
    assert _rows(db, maria) == {}
    refused = [r for r in caplog.records if r.getMessage() == "athlete_deletion_record_refused"]
    assert len(refused) == 3


# ── 30 days after /stop ───────────────────────────────────────────────────────


@pytest.mark.integration
def test_athletes_are_deleted_once_30_days_after_stop_have_passed(db) -> None:
    gone, frozen, back = _add(db, "A", 2000), _add(db, "B", 3000), _add(db, "C", 4000)
    for athlete_id in (gone, frozen, back):
        db.grant_consent(athlete_id, "v1", now=_NOW - timedelta(days=60))
    for athlete_id, days in ((gone, 31), (frozen, 29), (back, 40)):
        db.conn.execute(
            "UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ?",
            ((_NOW - timedelta(days=days)).isoformat(), athlete_id),
        )
    db.conn.commit()
    db.grant_consent(back, "v1", now=_NOW - timedelta(days=35))  # consented again in time

    assert lifecycle.purge_expired_athletes(db, now=_NOW) == [gone]

    assert _rows(db, gone) == {}
    assert _rows(db, frozen) and _rows(db, back)


@pytest.mark.integration
def test_the_worker_reapplies_and_purges_and_never_fails_the_owner(db, monkeypatch, caplog) -> None:
    from titan import worker

    calls: list[str] = []
    monkeypatch.setattr(lifecycle, "reapply_deletions", lambda _db: calls.append("reapply"))
    monkeypatch.setattr(lifecycle, "purge_expired_athletes", lambda _db, now: calls.append("purge"))
    worker._athlete_housekeeping(db, at_start=True)
    worker._athlete_housekeeping(db)
    assert calls == ["reapply", "purge", "purge"]

    monkeypatch.setattr(lifecycle, "purge_expired_athletes", MagicMock(side_effect=RuntimeError("locked")))
    with caplog.at_level(logging.CRITICAL):
        worker._athlete_housekeeping(db)
    assert "worker_athlete_housekeeping_failed" in caplog.text


# ── The API no longer pretends ───────────────────────────────────────────────


@pytest.mark.integration
def test_the_stub_export_and_delete_routes_are_gone(env, jwt_keys) -> None:
    from titan.api.main import create_app

    paths = {route.path for route in create_app().routes}

    assert "/coach/export" not in paths and "/coach/athlete-data" not in paths


# ── The command line ──────────────────────────────────────────────────────────


def _cli():
    spec = importlib.util.spec_from_file_location("athletes_cli", Path(__file__).resolve().parents[1] / "scripts" / "athletes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
def test_the_command_line_adds_exports_and_removes(env, capsys, monkeypatch) -> None:
    cli = _cli()
    profile = env / "profile.json"
    profile.write_text(json.dumps(_PROFILE), encoding="utf-8")

    assert cli.main(["add", "--name", "Maria", "--profile", str(profile), "--chat", "2000"]) == 0
    athlete_id = capsys.readouterr().out.splitlines()[0]
    assert cli.main(["list"]) == 0
    assert (
        f"{athlete_id}  Maria  garmin=missing  chat=yes  consent=no  ready=no (consent: none current)  today=not started"
        in capsys.readouterr().out
    )

    out = env / "export.json"
    assert cli.main(["export", athlete_id, "--out", str(out)]) == 0
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert json.loads(out.read_text(encoding="utf-8"))["athlete_id"] == athlete_id

    monkeypatch.setattr("builtins.input", lambda _prompt: "not-the-id")
    assert cli.main(["remove", athlete_id]) == 1
    assert cli.main(["remove", athlete_id, "--yes"]) == 0
    assert cli.main(["export", athlete_id]) == 1
    assert "refused" in capsys.readouterr().err


@pytest.mark.integration
def test_list_says_what_happened_to_this_morning(env, db, capsys, monkeypatch) -> None:
    """Runbook "an athlete got no message" (Phase 4 step 11): list tells the day's state."""
    from titan import worker

    cli = _cli()
    athlete_id = lifecycle.add_athlete(db, "Maria", _PROFILE, "2000")
    monkeypatch.setattr(worker, "_utc_now", lambda: _NOW)
    day = _NOW.date().isoformat()

    def today() -> str:
        assert cli.main(["list"]) == 0
        return capsys.readouterr().out.split("today=")[1].strip()

    assert today() == "not started"
    db.begin_routine_attempt(
        athlete_id=athlete_id, execution_date=day, routine_type=worker.ROUTINE_MORNING,
        started_at=_NOW, max_attempts=worker.ROUTINE_MAX_ATTEMPTS,
    )
    assert today() == "attempt 1 not delivered"
    db.complete_routine_execution(
        athlete_id=athlete_id, execution_date=day, routine_type=worker.ROUTINE_MORNING, completed_at=_NOW,
    )
    assert today() == f"left after {worker.ROUTINE_MAX_ATTEMPTS} attempts"
    db.mark_routine_delivered(
        athlete_id=athlete_id, execution_date=day, routine_type=worker.ROUTINE_MORNING, delivered_at=_NOW,
    )
    assert today() == "delivered"


@pytest.mark.integration
def test_new_key_writes_one_usable_key_and_never_replaces_it(env, capsys, monkeypatch) -> None:
    from titan.integrations.garmin_sync import decrypt_athlete_token, encrypt_athlete_token

    cli = _cli()
    key_file = env / "fresh" / "athletes.key"
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(key_file))

    assert cli.main(["new-key"]) == 0
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    first = key_file.read_bytes()
    assert decrypt_athlete_token(encrypt_athlete_token("token")) == "token"

    assert cli.main(["new-key"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert key_file.read_bytes() == first


@pytest.mark.integration
def test_new_key_refuses_a_file_inside_the_data_folder(env, capsys, monkeypatch) -> None:
    cli = _cli()
    inside = env / "data" / "athletes.key"
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(inside))

    assert cli.main(["new-key"]) == 1
    assert "outside the data folder" in capsys.readouterr().err
    assert not inside.exists()


def test_docker_gives_the_worker_a_key_and_a_deletion_record_outside_data_and_backups() -> None:
    """Regression (Phase 4 step 11): the compose file had no place for either, so relogin and remove failed."""
    text = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    worker = text.split("  titan-worker:", 1)[1]
    items = [line.strip()[2:] for line in worker.splitlines() if line.strip().startswith("- ")]
    env = dict(item.split("=", 1) for item in items if "=" in item)
    mounts = {item.split(":")[1]: item.split(":")[0] for item in items if item.count(":") >= 1 and "=" not in item}
    named_volumes = text.split("services:", 1)[0]
    for name in ("TITAN_TOKEN_KEY_FILE", "TITAN_DELETION_RECORD_FILE"):
        folder = str(Path(env[name]).parent)
        assert folder in mounts, (name, folder)
        assert f"  {mounts[folder]}:" in named_volumes, (name, mounts[folder])
        assert folder not in (env["TITAN_DATA_DIR"], env["TITAN_BACKUP_DIR"])


@pytest.mark.integration
def test_after_remove_no_column_of_any_table_names_the_athlete(db, env) -> None:
    """Phase 4 close (step 12): checked without athlete_tables, by reading every value of every table."""
    from titan import worker

    maria, nikos = _add(db, "Maria", 2000), _add(db, "Nikos", 3000)
    _seed(db, maria, 2000)
    _seed(db, nikos, 3000)
    worker._tell_zaf_not_ready(db, maria, "consent: none current", _NOW)

    lifecycle.delete_athlete(db, maria, now=_NOW)

    def mentions(needle: str) -> list[tuple[str, str]]:
        found = []
        for (table,) in db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            columns = [col[1] for col in db.conn.execute(f'PRAGMA table_info("{table}")')]
            for column in columns:
                hit = db.conn.execute(
                    f'SELECT 1 FROM "{table}" WHERE CAST("{column}" AS TEXT) LIKE ? LIMIT 1',  # nosec B608
                    (f"%{needle}%",),
                ).fetchone()
                if hit:
                    found.append((table, column))
        return found

    assert mentions(maria) == []
    assert mentions("telegram:2000") == [] and mentions(f"garmin-{maria}") == []
    assert mentions(nikos), "the check must see the athlete who was not removed"
