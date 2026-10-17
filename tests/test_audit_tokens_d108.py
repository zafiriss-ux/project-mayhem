"""Token and permission audit fixes (D-108, TK-01..TK-08).

- TK-01: no bot token in any log line, at any level, from a Telegram or requests error.
- TK-02: an athlete's Garmin token is deleted only when Garmin rejects it; an outage or a key
  that does not decrypt it keeps it. The owner's token is kept on an outage too.
- TK-03: removing an athlete with API users and refresh tokens deletes every row.
- TK-04: an export never carries a password hash.
- TK-05: an export written over an existing file leaves it 0600.
- TK-06: only failed logins within the lockout window add up.
- TK-07: the Garmin token folders are 0700, an older 0755 one is tightened.
- TK-08: a token folder that cannot be removed is reported; the image never gets tokens or keys.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import stat
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from cryptography.fernet import Fernet

from titan.core import athlete_lifecycle as lifecycle
from titan.core.database import DatabaseManager
from titan.integrations import garmin_sync, telegram_bot
from titan.integrations.garmin_sync import GarminSync, athlete_token_path, encrypt_athlete_token

# An obviously fake token, in the shape Telegram uses (<bot id>:<secret>).
PLANTED_BOT_TOKEN = "123456789:PLANTED_BOT_TOKEN_fake_value_0000"  # nosec B105
_SECRET_PART = PLANTED_BOT_TOKEN.split(":", 1)[1]
_A = "a-0000000a"
_PROFILE = {
    "birth_date": "1988-07-02", "sex": "F", "weight_kg": 58.0, "height_cm": 165,
    "max_hr": 186, "threshold_hr": 166, "training_phase": "BASE", "training_goal": "10K",
    "location_city": "Volos", "location_country": "GR",
}
_NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _connection_error() -> requests.exceptions.ConnectionError:
    """The text requests gives when api.telegram.org cannot be reached."""
    return requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded with url: "
        f"/bot{PLANTED_BOT_TOKEN}/sendMessage?chat_id=12345&text=Morning (Caused by "
        "NewConnectionError('Failed to establish a new connection: [Errno -3] Temporary failure'))"
    )


def _all_logged(caplog) -> str:
    """Every message, every extra field and every traceback that reached the log."""
    parts = [caplog.text]
    for record in caplog.records:
        parts.extend(str(value) for value in vars(record).values())
    return "\n".join(parts)


@pytest.fixture
def telegram(monkeypatch):
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot = telegram_bot.TitanTelegramBot(bot_token=PLANTED_BOT_TOKEN, chat_id="12345")
    bot.bot = MagicMock()
    return bot


# ── TK-01: no bot token in the logs ──────────────────────────────────────────


@pytest.mark.unit
def test_a_failed_send_never_logs_the_bot_token(telegram, caplog) -> None:
    telegram.bot.send_message.side_effect = _connection_error()
    caplog.set_level(logging.DEBUG)

    assert telegram.send_message("Morning") is False

    logged = _all_logged(caplog)
    assert "telegram_send_error" in caplog.text
    assert re.search(r"api\.telegram\.org", logged)  # the error is still said
    assert _SECRET_PART not in logged
    assert "chat_id=12345" not in logged


@pytest.mark.unit
def test_a_polling_retry_never_logs_the_bot_token(telegram, caplog) -> None:
    telegram.bot.infinity_polling.side_effect = _connection_error()
    stop = threading.Event()
    stop.wait = lambda timeout=None: stop.set()  # one retry, then stop
    telegram._stop_event = stop
    caplog.set_level(logging.DEBUG)

    telegram._poll_worker()

    assert "telegram_polling_retry" in caplog.text
    assert _SECRET_PART not in _all_logged(caplog)


@pytest.mark.unit
def test_a_request_url_logged_by_urllib3_at_debug_carries_no_token(telegram, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    logging.getLogger("urllib3.connectionpool").debug(
        '%s://%s:%s "%s %s %s" %s', "https", "api.telegram.org", 443, "POST",
        f"/bot{PLANTED_BOT_TOKEN}/getUpdates?offset=1", "HTTP/1.1", 200,
    )
    logging.getLogger("TeleBot").error("Exception traceback: %s", _connection_error())

    assert "getUpdates" in caplog.text
    assert _SECRET_PART not in _all_logged(caplog)


@pytest.mark.unit
def test_a_traceback_with_the_token_is_redacted(telegram, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    try:
        raise _connection_error()
    except requests.exceptions.ConnectionError:
        logging.getLogger("titan.integrations.telegram_bot").exception("telegram_send_error")

    assert "ConnectionError" in caplog.text
    assert _SECRET_PART not in _all_logged(caplog)


# ── TK-02: a Garmin outage keeps the token ───────────────────────────────────


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


def _fake_garmin(monkeypatch, ping_error: Exception | None = None, *, summary_error: Exception | None = None,
                 login_error: Exception | None = None) -> dict:
    seen = {"logins": 0}

    class _Garth:
        def loads(self, _data: str) -> None:
            return None

        def dumps(self) -> str:
            return "new-session"

    class _Garmin:
        def __init__(self, *_args) -> None:
            self.client = _Garth()

        def connectapi(self, _path):
            if ping_error is not None:
                raise ping_error

        def get_user_summary(self, _day):
            if summary_error is not None:
                raise summary_error

        def login(self):
            seen["logins"] += 1
            if login_error is not None:
                raise login_error

    module = MagicMock()
    module.Garmin = _Garmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return seen


def _store_athlete_token() -> Path:
    path = athlete_token_path(_A)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_athlete_token("session-of-a"))
    return path


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.exceptions.HTTPError(f"{status_code} Server Error", response=response)


class GarminConnectConnectionError(Exception):
    """Same name as garminconnect's wrapper of any failed request."""


@pytest.mark.integration
@pytest.mark.parametrize(
    "outage",
    [
        requests.exceptions.ConnectionError("Max retries exceeded with url: /oauth-service/oauth/exchange"),
        requests.exceptions.ReadTimeout("Read timed out"),
        _http_error(503),
        GarminConnectConnectionError("Error in request: 502 Bad Gateway"),
    ],
    ids=["network-down", "timeout", "http-503", "garmin-502"],
)
def test_an_outage_keeps_the_athletes_token(key_file, monkeypatch, outage) -> None:
    seen = _fake_garmin(monkeypatch, outage)
    token = _store_athlete_token()

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is False
    assert token.exists()
    assert sync.token_expired is False  # not paused: tried again at the next sync
    assert "token kept" in sync.last_connect_error
    assert seen["logins"] == 0


@pytest.mark.integration
def test_a_401_still_removes_the_token_and_pauses_the_athlete(key_file, monkeypatch) -> None:
    _fake_garmin(monkeypatch, _http_error(401))
    token = _store_athlete_token()

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is False
    assert not token.exists()
    assert sync.token_expired is True


@pytest.mark.integration
def test_a_token_that_the_key_does_not_decrypt_is_kept_and_said(key_file, monkeypatch, caplog) -> None:
    seen = _fake_garmin(monkeypatch)
    token = _store_athlete_token()
    key_file.write_bytes(Fernet.generate_key())  # a valid key, but not the one the token was written with
    caplog.set_level(logging.INFO)

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is False
    assert token.exists()
    assert sync.token_expired is False
    assert "TITAN_TOKEN_KEY_FILE" in sync.last_connect_error
    assert "connect_token_key_mismatch" in caplog.text
    assert seen["logins"] == 0


@pytest.mark.integration
def test_a_rate_limited_check_then_an_outage_keeps_the_token(key_file, monkeypatch) -> None:
    _fake_garmin(monkeypatch, RuntimeError("429 Too Many Requests"),
                 summary_error=requests.exceptions.ConnectionError("network down"))
    token = _store_athlete_token()

    sync = GarminSync(athlete_id=_A)

    assert sync.connect() is False
    assert token.exists()
    assert sync.token_expired is False


@pytest.mark.integration
def test_a_sync_error_that_only_looks_like_auth_keeps_the_token(key_file, monkeypatch) -> None:
    token = _store_athlete_token()
    sync = GarminSync(athlete_id=_A)
    # "oauth" in the URL makes the classifier say auth; the error is a network one.
    error = requests.exceptions.ConnectionError("Max retries exceeded with url: /oauth-service/oauth/preauthorized")
    assert garmin_sync._classify_failure(error) == garmin_sync.GARMIN_AUTH_FAIL

    sync._invalidate_session(error)

    assert token.exists()
    assert sync.is_connected is False


@pytest.fixture
def owner_dev(data_dir, monkeypatch):
    monkeypatch.setenv("TITAN_ENV", "dev")
    monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
    monkeypatch.setenv("GARMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "PLANTED_OWNER_PASSWORD")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    path = garmin_sync._get_garth_token_path()
    path.write_bytes(b"owner-session")
    return path


@pytest.mark.integration
def test_an_outage_keeps_the_owners_token(owner_dev, monkeypatch) -> None:
    down = requests.exceptions.ConnectionError("network down")
    _fake_garmin(monkeypatch, down, login_error=down)

    assert GarminSync().connect() is False
    assert owner_dev.exists()


@pytest.mark.integration
def test_a_rate_limited_check_then_an_outage_keeps_the_owners_token(owner_dev, monkeypatch) -> None:
    seen = _fake_garmin(monkeypatch, RuntimeError("429 Too Many Requests"),
                        summary_error=requests.exceptions.ConnectionError("network down"))

    assert GarminSync().connect() is False
    assert owner_dev.exists()
    assert seen["logins"] == 0


# ── TK-03, TK-04, TK-05, TK-08: remove and export ────────────────────────────


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    keys = tmp_path / "keys"
    keys.mkdir()
    key = keys / "athletes.key"
    key.write_bytes(Fernet.generate_key())
    os.chmod(key, 0o600)
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TITAN_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1000")
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(key))
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


def _athlete_with_api_login(db: DatabaseManager) -> str:
    from titan.api.auth import AuthStore

    athlete_id = lifecycle.add_athlete(db, "Maria", dict(_PROFILE), 2000, now=_NOW)
    store = AuthStore(db)
    store.upsert_user("user-maria", "maria", "PLANTED_PASSWORD_HASH", "athlete", athlete_id)
    store.add_refresh_token("jti-maria", "user-maria", _NOW + timedelta(days=7), _NOW)
    return athlete_id


@pytest.mark.integration
def test_remove_deletes_the_api_user_and_its_refresh_tokens(db) -> None:
    athlete_id = _athlete_with_api_login(db)

    counts = lifecycle.delete_athlete(db, athlete_id, now=_NOW)

    assert counts["auth_tokens"] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM auth_tokens WHERE id = 'jti-maria'").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM auth_users WHERE athlete_id = ?", (athlete_id,)).fetchone()[0] == 0
    assert db.get_athlete_account(athlete_id) is None


@pytest.mark.integration
def test_a_failed_remove_is_said_and_the_record_is_kept(db, monkeypatch, caplog) -> None:
    athlete_id = lifecycle.add_athlete(db, "Maria", dict(_PROFILE), 2000, now=_NOW)

    def _fail(*_args, **_kwargs):
        raise RuntimeError("disk I/O error")

    monkeypatch.setattr(lifecycle, "_delete_rows", _fail)
    with pytest.raises(RuntimeError):
        lifecycle.delete_athlete(db, athlete_id, now=_NOW)

    assert "athlete_delete_failed" in caplog.text
    assert athlete_id in lifecycle.deletion_record_path().read_text(encoding="utf-8")


@pytest.mark.integration
def test_export_never_carries_a_password_hash(db) -> None:
    athlete_id = _athlete_with_api_login(db)

    exported = json.dumps(lifecycle.export_athlete(db, athlete_id, now=_NOW))

    assert "PLANTED_PASSWORD_HASH" not in exported
    assert "password_hash" not in exported
    assert "maria" in exported  # the user row itself is still there


def _cli():
    spec = importlib.util.spec_from_file_location(
        "athletes_cli_d108", Path(__file__).resolve().parents[1] / "scripts" / "athletes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")
def test_an_export_over_an_existing_file_leaves_it_0600(env, db) -> None:
    athlete_id = lifecycle.add_athlete(db, "Maria", dict(_PROFILE), 2000, now=_NOW)
    out = env / "export.json"
    out.write_text("old", encoding="utf-8")
    os.chmod(out, 0o640)

    assert _cli().main(["export", athlete_id, "--out", str(out)]) == 0

    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def _rmtree_that_fails(_path, ignore_errors=False, **_kwargs) -> None:
    """A folder that cannot be removed; with ignore_errors the failure is hidden, as before."""
    if not ignore_errors:
        raise PermissionError("Permission denied")


@pytest.mark.integration
def test_a_token_folder_that_cannot_be_removed_is_reported(db, monkeypatch, caplog) -> None:
    athlete_id = lifecycle.add_athlete(db, "Maria", dict(_PROFILE), 2000, now=_NOW)
    garmin_sync.write_athlete_token(athlete_id, '{"session": "s"}')

    monkeypatch.setattr(lifecycle.shutil, "rmtree", _rmtree_that_fails)
    with pytest.raises(RuntimeError, match="token folder"):
        lifecycle.delete_athlete(db, athlete_id, now=_NOW)

    assert "athlete_token_folder_delete_failed" in caplog.text


@pytest.mark.integration
def test_the_command_line_says_when_the_token_folder_is_left(env, db, monkeypatch, capsys) -> None:
    athlete_id = lifecycle.add_athlete(db, "Maria", dict(_PROFILE), 2000, now=_NOW)
    garmin_sync.write_athlete_token(athlete_id, '{"session": "s"}')
    monkeypatch.setattr(lifecycle.shutil, "rmtree", _rmtree_that_fails)

    assert _cli().main(["remove", athlete_id, "--yes"]) == 1

    assert "token folder" in capsys.readouterr().err


@pytest.mark.unit
def test_the_image_never_gets_tokens_keys_or_a_data_folder() -> None:
    ignored = (Path(__file__).resolve().parents[1] / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert {"**/.garth_token", "**/*.key", "data/"} <= set(ignored)


# ── TK-06: lockout window ────────────────────────────────────────────────────


@pytest.fixture
def clock(monkeypatch):
    import time

    now = {"t": 1_800_000_000.0}
    monkeypatch.setattr(time, "time", lambda: now["t"])
    return now


@pytest.mark.unit
def test_failures_older_than_the_window_do_not_add_up(clock) -> None:
    from titan.api.auth import LOCKOUT_MAX_ATTEMPTS, LOCKOUT_WINDOW_SECONDS, AuthStore

    store = AuthStore()
    for _ in range(LOCKOUT_MAX_ATTEMPTS - 1):
        store.record_failed_attempt("zaf")
    clock["t"] += LOCKOUT_WINDOW_SECONDS + 1
    store.record_failed_attempt("zaf")

    assert store.is_locked_out("zaf") is False


@pytest.mark.unit
@pytest.mark.parametrize("username", ["zaf", "nobody-by-this-name"])
def test_failures_within_the_window_lock_known_and_unknown_names_alike(clock, username) -> None:
    from titan.api.auth import LOCKOUT_MAX_ATTEMPTS, AuthStore

    store = AuthStore()
    store.upsert_user("user-zaf", "zaf", "PLANTED_PASSWORD_HASH", "owner", "owner")
    for _ in range(LOCKOUT_MAX_ATTEMPTS):
        clock["t"] += 10
        store.record_failed_attempt(username)

    assert store.is_locked_out(username) is True


# ── TK-07: token folder modes ────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")
def test_the_token_folders_are_private_and_old_ones_are_tightened(key_file, data_dir) -> None:
    athlete_folder = data_dir / "garmin" / _A
    athlete_folder.mkdir(parents=True)
    os.chmod(data_dir / "garmin", 0o750)
    os.chmod(athlete_folder, 0o750)
    data_mode = stat.S_IMODE(data_dir.stat().st_mode)

    garmin_sync.write_athlete_token(_A, '{"session": "s"}')

    assert stat.S_IMODE((data_dir / "garmin").stat().st_mode) == 0o700
    assert stat.S_IMODE(athlete_folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(data_dir.stat().st_mode) == data_mode  # the data folder is not touched


@pytest.mark.integration
@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")
def test_a_new_token_folder_is_private(key_file, data_dir) -> None:
    garmin_sync.write_athlete_token(_A, '{"session": "s"}')

    assert stat.S_IMODE((data_dir / "garmin").stat().st_mode) == 0o700
    assert stat.S_IMODE((data_dir / "garmin" / _A).stat().st_mode) == 0o700
