"""Helpers for handling sensitive strings without exposing raw values in repr traces or logs."""

import json
import logging
import re
import threading
from dataclasses import dataclass


@dataclass(repr=False)
class SecretStr:
    """Lightweight secret wrapper inspired by pydantic's SecretStr."""

    _value: str = ""

    def __post_init__(self):
        self._value = self._value or ""

    def get_secret_value(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "SecretStr('********')" if self._value else "SecretStr('')"

    __str__ = __repr__


# --------------------------------------------------------------------------- #
# Log redaction (D-108, TK-01)
# --------------------------------------------------------------------------- #
# A Telegram API URL carries the bot token in its path (/bot<id>:<secret>/<method>) and the
# chat id and the text in its query. requests puts that URL in every ConnectionError text,
# so the path is cut after the method and the token replaced; a bare token is replaced too.
_BOT_URL_PATH = re.compile(r"/bot[^/\s'\"]+/([A-Za-z]+)[^\s'\")]*")
_BOT_TOKEN = re.compile(r"\b(?:bot)?\d+:[A-Za-z0-9_-]{20,}")
REDACTED = "<redacted>"
_known_secrets: set[str] = set()
_known_lock = threading.Lock()


def _escaped_forms(value: str) -> set[str]:
    """``value`` as written, and as json.dumps (ASCII or not) and repr write it (SP-04).

    Structured events are json.dumps'd before the filter sees them, and a traceback shows
    exception args in repr, so a quote, a backslash or a Greek letter would hide the secret.
    """
    forms = {value, json.dumps(value)[1:-1], json.dumps(value, ensure_ascii=False)[1:-1]}
    forms.add(repr(value)[1:-1])
    # repr escapes ' only inside single quotes, which it picks when the whole string also has
    # a ". Appending both quotes forces that form; the slice drops the quote and \'".
    forms.add(repr(value + "'\"")[1:-4])
    return forms


def register_secret(value: str) -> None:
    """Add a secret (such as the bot token in use) that ``redact_secrets`` always replaces."""
    if value and len(value) >= 8:  # noqa: PLR2004 - shorter is no secret and would over-match
        with _known_lock:
            _known_secrets.update(_escaped_forms(value))


def redact_secrets(text: object) -> str:
    """``str(text)`` with every bot token, Telegram API URL path and registered secret removed."""
    out = str(text)
    with _known_lock:
        known = sorted(_known_secrets, key=len, reverse=True)
    for value in known:
        out = out.replace(value, REDACTED)
    out = _BOT_URL_PATH.sub(rf"/bot{REDACTED}/\1", out)
    return _BOT_TOKEN.sub(REDACTED, out)


_PLAIN_RECORD_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


class RedactingFilter(logging.Filter):
    """Removes secrets from a record's message, its ``extra`` strings and its traceback.

    Installed on the Telegram, telebot and urllib3 loggers and on the worker's and the
    console's handlers, so a token never reaches a log line, at any level.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a bad format string must not drop the record
            message = str(record.msg)
        record.msg, record.args = redact_secrets(message), None
        for key, value in list(vars(record).items()):
            if key not in _PLAIN_RECORD_FIELDS and isinstance(value, str):
                setattr(record, key, redact_secrets(value))
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        # Formatters print exc_text when set; the exception object itself, whose text has
        # the token, is not handed on to any handler.
        record.exc_info = None
        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_secrets(record.stack_info)
        return True


_FILTER = RedactingFilter()
# Loggers that see Telegram request URLs: telebot's own (it has its own handler) and urllib3's.
_URL_LOGGERS = ("TeleBot", "urllib3.connectionpool", "titan.integrations.telegram_bot")


def install_root_log_redaction() -> None:
    """Give a process with no log handler a stderr one that redacts (M0-17, the API).

    Without a handler Python's last-resort handler prints WARNING and above to stderr
    unfiltered. The new handler prints the same levels (the root level is left as it is),
    formatted and through the filter. Nothing changes when the root logger has a handler.
    """
    root = logging.getLogger()
    if root.handlers:
        install_log_redaction(*root.handlers)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    install_log_redaction(handler)
    root.addHandler(handler)


def install_log_redaction(*handlers: logging.Handler) -> None:
    """Attach the redacting filter to the URL-bearing loggers and to ``handlers`` (idempotent)."""
    targets: list[logging.Filterer] = [logging.getLogger(name) for name in _URL_LOGGERS]
    targets.extend(handlers)
    for target in targets:
        if not any(isinstance(f, RedactingFilter) for f in target.filters):
            target.addFilter(_FILTER)
