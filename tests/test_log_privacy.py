"""MA-F7 + OW-L4 (D-120): no token fragment or personal detail reaches a log line.

- A malformed bot token: telebot's error names the part before ":" — it is never logged.
- No log call passes a personal detail (name, age, max HR, chat id, e-mail, …) as ``extra``.
- The owner's Garmin e-mail and password are redacted like the bot token.
- The Garmin sync metric carries the athlete that synced, not always "owner".
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from titan.integrations import telegram_bot
from titan.integrations.telegram_bot import TitanTelegramBot, _cmd_rate
from titan.utils.secrets import redact_secrets

_REPO = Path(__file__).resolve().parents[1]
_CANARY_BOT_ID = "CANARY-tg-1234567"
_STRANGER = 987654321
_PERSONAL_EXTRA_KEYS = frozenset({
    "athlete_name", "name", "display_name", "age", "birth_date", "max_hr", "weight_kg",
    "height_cm", "chat_id", "email", "password", "phone",
})


def _all_text(records: list[logging.LogRecord]) -> str:
    """Every message, extra value and traceback the records carry, as one string."""
    parts = []
    for record in records:
        parts.append(record.getMessage())
        parts.extend(str(v) for v in vars(record).values())
    return "\n".join(parts)


@pytest.fixture
def settings_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1000")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    _cmd_rate.clear()
    yield data
    get_settings.cache_clear()


@pytest.mark.unit
def test_a_malformed_bot_token_never_reaches_the_log(settings_env, caplog) -> None:
    caplog.set_level(logging.DEBUG)

    bot = TitanTelegramBot(bot_token=f"{_CANARY_BOT_ID}:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", chat_id=1000)

    assert bot.bot is None
    assert any("startup_failure" in r.getMessage() for r in caplog.records)
    assert "CANARY" not in _all_text(caplog.records)


class _FakeTeleBot:
    def __init__(self) -> None:
        self.handlers: dict = {}

    def message_handler(self, commands=None, func=None):  # noqa: ANN001, ANN201
        def decorator(fn):  # noqa: ANN001, ANN202
            for command in commands or []:
                self.handlers[command] = fn
            return fn

        return decorator

    def callback_query_handler(self, func=None):  # noqa: ANN001, ANN201
        return lambda fn: fn

    def reply_to(self, message, text: str, **kwargs) -> None:  # noqa: ANN001
        pytest.fail("a stranger got a reply")


@pytest.mark.unit
def test_an_untrusted_chat_is_logged_without_its_chat_id(settings_env, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    bot = TitanTelegramBot(bot_token="", chat_id=1000)
    bot.bot = _FakeTeleBot()
    bot._register_handlers()

    bot.bot.handlers["today"](SimpleNamespace(chat=SimpleNamespace(id=_STRANGER), text="/today"))

    assert any(r.getMessage() == "titan.telegram.untrusted_chat" for r in caplog.records)
    assert str(_STRANGER) not in _all_text(caplog.records)


def _personal_extra_keys(path: Path) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "extra" and isinstance(kw.value, ast.Dict):
                found.extend(
                    (node.lineno, key.value)
                    for key in kw.value.keys
                    if isinstance(key, ast.Constant) and key.value in _PERSONAL_EXTRA_KEYS
                )
    return found


@pytest.mark.unit
def test_no_log_call_passes_a_personal_detail_as_extra() -> None:
    # ADR-0067 D2.8: logs name an athlete by athlete_id only.
    offenders = {
        str(path.relative_to(_REPO)): keys
        for path in sorted((_REPO / "titan").rglob("*.py"))
        if (keys := _personal_extra_keys(path))
    }

    assert offenders == {}


@pytest.fixture
def key_file(tmp_path, settings_env, monkeypatch):
    path = tmp_path / "keys" / "athletes.key"
    path.parent.mkdir()
    path.write_bytes(Fernet.generate_key())
    os.chmod(path, 0o600)
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(path))
    return path


@pytest.mark.unit
def test_the_owners_garmin_credentials_are_redacted(key_file) -> None:
    from titan.integrations.garmin_sync import GarminSync

    GarminSync(email="canary.owner@example.invalid", password="CANARY-pw-7654321")

    text = redact_secrets("login failed for canary.owner@example.invalid with CANARY-pw-7654321")
    assert "canary.owner@example.invalid" not in text
    assert "CANARY-pw-7654321" not in text


@pytest.mark.unit
def test_the_sync_metric_names_the_athlete_that_synced(key_file, monkeypatch) -> None:
    from titan.integrations import garmin_sync
    from titan.observability import metrics

    seen: list[tuple[str, dict]] = []

    class _Recorder:
        def counter(self, name: str, value: int = 1, labels: dict | None = None) -> None:
            seen.append((name, labels or {}))

    monkeypatch.setattr(metrics, "get_metrics", lambda: _Recorder())
    sync = garmin_sync.GarminSync(athlete_id="a-0000000a")
    payload = {"activities": [{"id": 1}], "weight": [], "sleep": [], "hrv": [], "hrv_metrics": {}}
    monkeypatch.setattr(sync, "_sync_operation", lambda _days: payload)

    sync.sync_all(days_back=1)

    assert ("garmin_sync_success", {"athlete": "a-0000000a"}) in seen


@pytest.mark.unit
def test_the_telebot_error_really_names_the_bot_id() -> None:
    # Keeps the first test honest: the real library puts the part before ":" in its error.
    telebot = pytest.importorskip("telebot")

    with pytest.raises(ValueError, match=_CANARY_BOT_ID):
        telebot.TeleBot(f"{_CANARY_BOT_ID}:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert telegram_bot.TELEBOT_AVAILABLE
