"""
Telegram Bot - Real polling listener + scheduler

Uses pyTelegramBotAPI for real polling (not mock).
"""

import json
import logging
import re
import secrets as _secrets_mod
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from titan.config.settings import get_settings
from titan.core.athlete import CONSENT_TEXT_VERSION, canonical_chat_id
from titan.core.structured_events import EventSeverity, structured_event_payload
from titan.science.critical_speed import parse_time_trial, parse_trial_date
from titan.science.override_signal import OverrideSignal, record_override_signal
from titan.utils.secrets import SecretStr, install_log_redaction, redact_secrets, register_secret

_log = logging.getLogger(__name__)
# The bot token is in every Telegram API URL; no log line of this module, telebot or
# urllib3 may carry it, at any level (D-108, TK-01).
install_log_redaction()

_AUDIT_UNAVAILABLE_REPLY = "❌ Audit log unavailable: command not performed."

_OWNER_ATHLETE_ID = "owner"
# An athlete other than the owner has these commands only (ADR-0067 D4.1, D10.3).
ATHLETE_COMMANDS = ("consent", "agree", "sync", "stop")
_ATHLETE_HELP = (
    "🎯 *TITAN AI Coach*\n\n"
    "/consent – Read the consent text\n"
    "/agree – Give your consent to that text\n"
    "/sync – Sync your Garmin data now\n"
    "/stop – Stop coaching and withdraw your consent\n"
)
_CONSENT_DIR = Path(__file__).resolve().parents[2] / "docs" / "consent"
_NO_CONSENT_REPLY = "⏸ Nothing runs for you without your consent. Send /consent to read the text."


def _consent_text(version: str) -> str | None:
    """The athlete-facing consent text of ``version`` (docs/consent/<version>.md), or None."""
    try:
        return (_CONSENT_DIR / f"{version}.md").read_text(encoding="utf-8").strip() or None
    except OSError as exc:
        _log.critical("titan.telegram.consent_text_unreadable", extra={"version": version, "error": str(exc)})
        return None

_FLOAT_NOISE = re.compile(r"\d+\.\d{5,}")


def _short_number(value: float, decimals: int) -> str:
    """``19.699999999999996`` -> ``19.7``; ``10.0`` -> ``10`` (no exponent form)."""
    text = f"{round(value, decimals):.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _tidy_floats(text: object) -> str:
    """Round float noise in free text, e.g. a gate rationale (SV-07)."""
    return _FLOAT_NOISE.sub(lambda m: _short_number(float(m.group()), 2), str(text))


def _km(value: object) -> str:
    """Distances in messages: one decimal at most (the weekly plan said '63.195 km', SV-07)."""
    try:
        return _short_number(float(value), 1)
    except (TypeError, ValueError):
        return str(value)

SEND_FAIL = "SEND_FAIL"
POLL_FAIL = "POLL_FAIL"
SCHEDULER_DRIFT = "SCHEDULER_DRIFT"
CALLBACK_ERROR = "CALLBACK_ERROR"
OVERRIDE_SILENCE = "OVERRIDE_SILENCE"
# A scheduled task with this time runs every minute (D-111).
EVERY_MINUTE = "*"

_CMD_COOLDOWN_S = 30
_cmd_rate: dict[tuple[int, str], float] = defaultdict(float)
_cmd_rate_lock = threading.Lock()

# TD-17 / INV-17: one-time override nonces live in telegram_override_nonces
# (ADR-0060 D2), so they survive a restart and work across processes.
_OVERRIDE_TTL_SECONDS = 300  # 5 minutes
_OVERRIDE_COMMAND = "override"


def _create_override_nonce(db, decision_id: str, athlete_id: str) -> str | None:  # noqa: ANN001
    """Issue a one-time nonce for an override confirmation; None if it cannot be stored.

    Without a stored nonce no override button is offered (fail closed, INV-16).
    """
    if db is None:
        _log.critical("telegram_override_nonce_unavailable", extra={"reason": "no database"})
        return None
    nonce = _secrets_mod.token_urlsafe(16)
    now = datetime.now(UTC)
    try:
        db.issue_override_nonce(
            nonce=nonce,
            command_type=_OVERRIDE_COMMAND,
            athlete_id=athlete_id,
            decision_id=decision_id,
            issued_at=now,
            expires_at=now + timedelta(seconds=_OVERRIDE_TTL_SECONDS),
        )
    except Exception as exc:
        _log.critical("telegram_override_nonce_unavailable", extra={"reason": str(exc)})
        return None
    return nonce


_OVERRIDE_STALE_REPLY = "⚠️ This button belongs to an older decision; use the latest message."


def _consume_override_nonce(db, nonce: str) -> str | None:  # noqa: ANN001
    """Consume a nonce: its decision_id if valid, None if unknown, expired or replayed.

    The expiry and replay checks are one UPDATE in the database. Without a
    database, or if the update fails, no override is accepted.
    """
    if db is None:
        _log.critical("telegram_override_nonce_unavailable", extra={"reason": "no database"})
        return None
    try:
        return db.consume_override_nonce(nonce=nonce, command_type=_OVERRIDE_COMMAND, now=datetime.now(UTC))
    except Exception as exc:
        _log.critical("telegram_override_nonce_unavailable", extra={"reason": str(exc)})
        return None


def _check_rate_limit(chat_id: int, command: str) -> bool:
    """Return True if the command is allowed, False if within the cooldown window."""
    key = (chat_id, command)
    now = time.monotonic()
    with _cmd_rate_lock:
        if now - _cmd_rate[key] < _CMD_COOLDOWN_S:
            return False
        _cmd_rate[key] = now
        return True


_MARKDOWN_V2_SPECIAL = re.compile(r"([_*\[\]()~`>#+=|{}.!\-\\])")


def _escape_markdown_v2(text: str) -> str:
    """Escape *text* for Telegram MarkdownV2.

    NOTE: parse_mode="Markdown" (legacy) is still in use throughout this module.
    Switch to parse_mode="MarkdownV2" only after all message composition sites
    have been audited and their content wrapped with this helper — see P15-D22.
    """
    return _MARKDOWN_V2_SPECIAL.sub(r"\\\1", text)


_MARKDOWN_LEGACY_SPECIAL = re.compile(r"([_*`\[])")


def _escape_markdown_legacy(value: object) -> str:
    """Escape dynamic text for the legacy ``parse_mode="Markdown"`` this module sends with.

    Legacy Markdown has four entity characters: ``_``, ``*``, backtick and ``[``. Outside an
    entity each one is escaped with a backslash. Unescaped, a lock code such as
    ``HARD_STOP_SAFETY_GATES`` opens an italic that never closes and Telegram refuses the
    whole message (OW-M1, D-127).
    """
    return _MARKDOWN_LEGACY_SPECIAL.sub(r"\\\1", str(value))


def _telegram_event(
    action: str,
    *,
    severity: EventSeverity | str = EventSeverity.INFO,
    **fields,
) -> None:
    """Emit a structured Telegram delivery event as a single JSON log line."""
    _log.info(
        redact_secrets(
            json.dumps(
                structured_event_payload("telegram", action, severity=severity, **fields),
                default=str,
            )
        )
    )


try:
    import telebot

    TELEBOT_AVAILABLE = True
except ImportError:
    TELEBOT_AVAILABLE = False


class TitanTelegramBot:
    """
    Full-featured Telegram bot with:
    - Real polling listener (hears /today, /sync, /stats, etc.)
    - Scheduled notifications (morning 07:00, weekly plan Sunday 20:00)
    - Rich markdown messages
    """

    # Hard cap on user-supplied override reason text (DB bloat + re-render guard).
    _MAX_OVERRIDE_REASON_LEN: int = 500

    def __init__(self, bot_token: str = None, chat_id=None, db=None, *, athlete_id: str = _OWNER_ATHLETE_ID):
        self.db = db
        self.athlete_id = athlete_id
        self.bot_token = SecretStr(_value=bot_token or get_settings().TELEGRAM_BOT_TOKEN.get_secret_value())
        if athlete_id != _OWNER_ATHLETE_ID:
            # Another athlete's bot only sends, to that athlete's own chat: never the
            # owner's TELEGRAM_CHAT_ID as a fallback, and it trusts no inbound chat
            # (the owner's polling bot routes athlete chats, ADR-0067 D10.1).
            if not chat_id:
                raise ValueError("an athlete other than the owner needs their own Telegram chat")
            # Only the canonical form is sent to (D-107): "01001" or "+1" would reach
            # int() as another chat than the one stored and checked.
            raw_id = canonical_chat_id(chat_id)
            if raw_id is None or raw_id != str(chat_id):
                raise ValueError("an athlete's Telegram chat id is not in canonical form")
            self._trusted_chat_id: str | None = None
            self._owner_user_id: str | None = None
        else:
            raw_id = chat_id or get_settings().TELEGRAM_CHAT_ID
            # Trusted inbound chat ID for per-handler authorisation, in the canonical form
            # Telegram's own int id has (D-107). None = unconfigured or not a chat id
            # (deny all, INV-16 / RBP-02); str = strict match.
            _raw_trusted = chat_id or get_settings().TELEGRAM_CHAT_ID or None
            self._trusted_chat_id = canonical_chat_id(_raw_trusted, allow_negative=True) if _raw_trusted else None
            # The owner's own Telegram user id. Needed only when TELEGRAM_CHAT_ID is a group:
            # there every member writes in the trusted chat, and only the owner's messages
            # are commands (M0-33). A user id is positive, like a private chat id.
            _raw_owner_user = str(get_settings().TELEGRAM_OWNER_USER_ID or "").strip()
            self._owner_user_id = canonical_chat_id(_raw_owner_user)
            if _raw_owner_user and self._owner_user_id is None:
                # Set but not a user id ("+42", "-42", text): treated as unset, said once here.
                _log.critical("titan.telegram.owner_user_id_invalid")
        try:
            self.chat_id = int(raw_id)
        except (ValueError, TypeError):
            self.chat_id = raw_id  # keep as str until set

        self.bot = None
        self.is_running = False
        self._poll_thread: threading.Thread | None = None
        self._sched_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._tasks_lock = threading.Lock()
        self.scheduled_tasks: list[dict] = []
        self.message_history: list[dict] = []
        self._alert_history: dict[tuple[str, str], dict[str, datetime | int]] = {}

        # Callbacks for commands – set by orchestration layer
        self.cmd_callbacks: dict[str, Callable] = {}
        # Callbacks taking the athlete_id, for commands from an athlete's own chat.
        self.athlete_cmd_callbacks: dict[str, Callable[[str], str]] = {}
        self.override_callbacks: dict[str, Callable] = {}
        self._pending_override_prompts: dict[int, dict[str, str]] = {}

        bot_token_value = self.bot_token.get_secret_value()
        register_secret(bot_token_value)
        if TELEBOT_AVAILABLE and bot_token_value:
            try:
                self.bot = telebot.TeleBot(bot_token_value, parse_mode="Markdown")
                if athlete_id == _OWNER_ATHLETE_ID:
                    self._register_handlers()
            except Exception as e:
                # The library's error text can quote part of the token (the bot id before
                # ":"), which no redaction knows: only the error class is logged (MA-F7).
                _init_detail = "Telegram bot could not be created from TELEGRAM_BOT_TOKEN; check its format"
                _telegram_event(
                    "failure",
                    failure_class=CALLBACK_ERROR,
                    subsystem="init",
                    error_class=e.__class__.__name__,
                    error_message=_init_detail,
                )
                _log.error(
                    "startup_failure",
                    extra={
                        "component": "telegram_bot_init",
                        "error_class": e.__class__.__name__,
                        "detail": _init_detail,
                    },
                )
                _log.warning("telegram_init_warning", extra={"detail": _init_detail})

    # ------------------------------------------------------------------ #
    # AUTHORISATION
    # ------------------------------------------------------------------ #
    def _is_trusted(self, chat_id: int | str) -> bool:
        """Return True if *chat_id* matches the configured trusted chat.

        Fail-closed (AGENTS INV-16 / RBP-02): if no trusted chat is configured
        (_trusted_chat_id is None) every sender is refused and a CRITICAL is
        logged so operators notice the gap.
        """
        if self._trusted_chat_id is None:
            _log.critical("titan.telegram.no_trusted_chat_configured")
            return False
        return str(chat_id) == str(self._trusted_chat_id)

    def _is_trusted_sender(self, chat_id: int | str, user: object) -> bool:
        """Return True if a message in *chat_id* from *user* is the owner's command (M0-33).

        In a private chat only the owner writes, so the chat is enough. When the trusted
        chat is a group (a negative id), any member writes in it: the sender must also be
        TELEGRAM_OWNER_USER_ID. Without that setting no group message is trusted (fail
        closed, INV-16), and a CRITICAL is logged so the owner notices. A sender Telegram
        does not name (an anonymous admin, a channel) is never the owner.
        """
        if not self._is_trusted(chat_id):
            return False
        if not str(self._trusted_chat_id).startswith("-"):
            return True
        if self._owner_user_id is None:
            _log.critical("titan.telegram.group_owner_user_not_configured")
            return False
        return canonical_chat_id(getattr(user, "id", None)) == self._owner_user_id

    def _is_owner_message(self, message: object) -> bool:
        """Whether an inbound *message* is the owner's command: its chat and its sender (M0-33)."""
        return self._is_trusted_sender(message.chat.id, getattr(message, "from_user", None))

    def _athlete_for_chat(self, chat_id: int | str) -> str | None:
        """Return the athlete whose private chat this is, or None (ADR-0067 D10.2).

        The owner's chat is never an athlete's. Any lookup failure is treated as an
        unregistered chat, which gets no reply. With multi-athlete mode off
        (TITAN_MULTI_ATHLETE != "1") no chat is an athlete's, whichever process runs the
        bot, the console included (MA-F9, D-119).
        """
        if self.athlete_id != _OWNER_ATHLETE_ID or self.db is None or self._is_trusted(chat_id):
            return None
        if get_settings().TITAN_MULTI_ATHLETE != "1":
            return None
        try:
            athlete_id = self.db.get_athlete_for_telegram_chat(chat_id)
        except Exception as exc:
            _log.error("titan.telegram.athlete_lookup_failed", extra={"error_class": exc.__class__.__name__})
            return None
        if athlete_id in (None, _OWNER_ATHLETE_ID):
            return None
        return athlete_id

    # ------------------------------------------------------------------ #
    # COMMAND HANDLERS
    # ------------------------------------------------------------------ #
    def _register_handlers(self):
        if not self.bot:
            return

        @self.bot.message_handler(commands=["start", "help"])
        def cmd_help(message):
            if not self._is_owner_message(message):
                if self._athlete_for_chat(message.chat.id) is not None:
                    self.bot.reply_to(message, _ATHLETE_HELP)
                    return
                _log.warning("titan.telegram.untrusted_chat")
                return
            self.chat_id = message.chat.id  # auto-capture only for trusted sender
            text = (
                "🎯 *TITAN AI Coach* – Available Commands\n\n"
                "/today – Today's workout & optimal time\n"
                "/week – This week's training plan\n"
                "/stats – Performance summary\n"
                "/recovery – Recovery status (HRV, sleep, TSB)\n"
                "/nutrition – Today's full nutrition plan\n"
                "/sync – Force Garmin data sync\n"
                "/activities – Recent runs\n"
                "/drift – Cardiac drift analysis\n"
                "/shoes – Shoe recommendation for today\n"
                "/calibration – Governance calibration summary\n"
                "/manual_entry – Log metrics manually (HRV, RHR, Sleep, Fatigue, Weight)\n"
                "/injury – Declare an injury (REST until /injury off)\n"
                "/time_trial – Log a time-trial for Critical Speed (distance, time)\n"
            )
            self.bot.reply_to(message, text)

        @self.bot.message_handler(commands=["today"])
        def cmd_today(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if not _check_rate_limit(message.chat.id, "today"):
                self.bot.reply_to(message, "⏳ Please wait 30 seconds before repeating this command.")
                return
            if "today" in self.cmd_callbacks:
                result = self.cmd_callbacks["today"]()
                self.bot.reply_to(message, result or "⏳ Calculating...")
            else:
                self.bot.reply_to(message, "⏳ Daily coach not ready yet.")

        @self.bot.message_handler(commands=["week"])
        def cmd_week(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if not _check_rate_limit(message.chat.id, "week"):
                self.bot.reply_to(message, "⏳ Please wait 30 seconds before repeating this command.")
                return
            if "week" in self.cmd_callbacks:
                result = self.cmd_callbacks["week"]()
                self.bot.reply_to(message, result or "⏳ Generating plan...")
            else:
                self.bot.reply_to(message, "⏳ Weekly planner not ready yet.")

        @self.bot.message_handler(commands=["stats"])
        def cmd_stats(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if "stats" in self.cmd_callbacks:
                result = self.cmd_callbacks["stats"]()
                self.bot.reply_to(message, result or "⏳ Loading stats...")
            else:
                self.bot.reply_to(message, "⏳ Stats not ready yet.")

        @self.bot.message_handler(commands=["recovery"])
        def cmd_recovery(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if "recovery" in self.cmd_callbacks:
                result = self.cmd_callbacks["recovery"]()
                self.bot.reply_to(message, result or "⏳ Checking recovery...")
            else:
                self.bot.reply_to(message, "⏳ Recovery engine not ready.")

        @self.bot.message_handler(commands=["nutrition"])
        def cmd_nutrition(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if "nutrition" in self.cmd_callbacks:
                result = self.cmd_callbacks["nutrition"]()
                self.bot.reply_to(message, result or "⏳ Building nutrition plan...")
            else:
                self.bot.reply_to(message, "⏳ Nutrition optimizer not ready.")

        @self.bot.message_handler(commands=["sync"])
        def cmd_sync(message):
            if not self._is_owner_message(message):
                athlete_id = self._athlete_for_chat(message.chat.id)
                if athlete_id is not None:
                    self.bot.reply_to(message, self.handle_athlete_sync(message.chat.id, athlete_id))
                    return
                _log.warning("titan.telegram.untrusted_chat")
                return
            if not _check_rate_limit(message.chat.id, "sync"):
                self.bot.reply_to(message, "⏳ Please wait 30 seconds before repeating this command.")
                return
            if "sync" not in self.cmd_callbacks:
                self.bot.reply_to(message, "⏳ Sync not available yet.")
                return
            if not self._audit_before_effect(self.db, message.chat.id, "TELEGRAM_SYNC", "owner"):
                self.bot.reply_to(message, _AUDIT_UNAVAILABLE_REPLY)
                return
            self.bot.reply_to(message, "🔄 Starting Garmin sync...")
            result = self.cmd_callbacks["sync"]()
            self.bot.reply_to(message, result or "✅ Sync complete.")

        @self.bot.message_handler(commands=["stop"])
        def cmd_stop(message):
            athlete_id = self._athlete_for_chat(message.chat.id)
            if athlete_id is None:
                if self._is_owner_message(message):
                    self.bot.reply_to(message, "ℹ️ /stop is for athletes; the owner has no consent to withdraw.")
                else:
                    _log.warning("titan.telegram.untrusted_chat")
                return
            self.bot.reply_to(message, self.handle_athlete_stop(message.chat.id, athlete_id))

        @self.bot.message_handler(commands=["consent", "agree"])
        def cmd_consent(message):
            athlete_id = self._athlete_for_chat(message.chat.id)
            if athlete_id is None:
                if self._is_owner_message(message):
                    self.bot.reply_to(message, "ℹ️ The owner is exempt from consent.")
                else:
                    _log.warning("titan.telegram.untrusted_chat")
                return
            command, _, args = (message.text or "").partition(" ")
            if command.lstrip("/").split("@")[0] == "agree":
                self.bot.reply_to(message, self.handle_athlete_agree(message.chat.id, athlete_id, args))
            else:
                # Plain text: the consent text is shown exactly as written.
                self.bot.reply_to(message, self.handle_athlete_consent(), parse_mode="")

        @self.bot.message_handler(commands=["activities"])
        def cmd_activities(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if "activities" in self.cmd_callbacks:
                result = self.cmd_callbacks["activities"]()
                self.bot.reply_to(message, result or "No activities found.")
            else:
                self.bot.reply_to(message, "⏳ Activity data not ready.")

        @self.bot.message_handler(commands=["drift"])
        def cmd_drift(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if "drift" in self.cmd_callbacks:
                result = self.cmd_callbacks["drift"]()
                self.bot.reply_to(message, result or "No drift data yet.")
            else:
                self.bot.reply_to(message, "⏳ Drift analysis not ready.")

        @self.bot.message_handler(commands=["shoes"])
        def cmd_shoes(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if "shoes" in self.cmd_callbacks:
                result = self.cmd_callbacks["shoes"]()
                self.bot.reply_to(message, result or "No shoe data configured.")
            else:
                self.bot.reply_to(message, "⏳ Equipment manager not ready.")

        @self.bot.message_handler(commands=["calibration"])
        def cmd_calibration(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if not _check_rate_limit(message.chat.id, "calibration"):
                self.bot.reply_to(message, "⏳ Please wait 30 seconds before repeating this command.")
                return
            if "calibration" in self.cmd_callbacks:
                result = self.cmd_callbacks["calibration"]()
                self.bot.reply_to(message, result or "⏳ No calibration data yet.")
            else:
                self.bot.reply_to(message, "⏳ Outcome tracker not ready.")

        @self.bot.message_handler(commands=["manual_entry"])
        def cmd_manual_entry(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if not _check_rate_limit(message.chat.id, "manual_entry"):
                self.bot.reply_to(message, "⏳ Please wait 30 seconds before repeating this command.")
                return
            text = (message.text or "").strip()
            # Strip "/manual_entry" prefix to get the argument string
            parts = text.split(None, 1)
            args = parts[1] if len(parts) > 1 else ""
            reply = self.handle_manual_entry_text(args, chat_id=message.chat.id)
            self.bot.reply_to(message, reply)

        @self.bot.message_handler(commands=["injury"])
        def cmd_injury(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if not _check_rate_limit(message.chat.id, "injury"):
                self.bot.reply_to(message, "⏳ Please wait 30 seconds before repeating this command.")
                return
            parts = (message.text or "").strip().split(None, 1)
            args = parts[1] if len(parts) > 1 else ""
            self.bot.reply_to(message, self.handle_injury_text(args, chat_id=message.chat.id), parse_mode="")

        @self.bot.message_handler(commands=["time_trial"])
        def cmd_time_trial(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            if not _check_rate_limit(message.chat.id, "time_trial"):
                self.bot.reply_to(message, "⏳ Please wait 30 seconds before repeating this command.")
                return
            parts = (message.text or "").strip().split(None, 1)
            args = parts[1] if len(parts) > 1 else ""
            self.bot.reply_to(message, self.handle_time_trial_text(args, chat_id=message.chat.id))

        @self.bot.callback_query_handler(func=lambda call: str(call.data).startswith("override:"))
        def cb_override(call):
            if not self._is_trusted_sender(call.message.chat.id, getattr(call, "from_user", None)):
                _log.warning("titan.telegram.untrusted_chat")
                self.bot.answer_callback_query(call.id)
                return
            response = self.process_override_callback(call.message.chat.id, call.data)
            self.bot.answer_callback_query(call.id, response)
            if str(call.data).startswith("override:request"):
                self.bot.send_message(call.message.chat.id, response)

        @self.bot.message_handler(func=lambda message: message.chat.id in self._pending_override_prompts)
        def msg_override_reason(message):
            if not self._is_owner_message(message):
                _log.warning("titan.telegram.untrusted_chat")
                return
            response = self.process_override_reason(message.chat.id, message.text or "")
            self.bot.reply_to(message, response)

    # Field name → (db_column, type_fn, min_val, max_val)
    _MANUAL_ENTRY_FIELDS: dict = {
        "HRV":     ("hrv_rmssd",    float, 0.0,  200.0),
        "RHR":     ("resting_hr",   int,   20,   220),
        "SLEEP":   ("sleep_hours",  float, 0.0,  24.0),
        "FATIGUE": ("fatigue_level", int,  1,    10),
        "WEIGHT":  ("weight_kg",    float, 20.0, 300.0),
    }

    def _parse_manual_entry(self, args: str) -> tuple[dict, str | None]:
        """Parse KEY=VALUE pairs from a /manual_entry argument string.

        Returns (parsed_dict, None) on success, ({}, error_message) on failure.
        parsed_dict maps DB column names to typed values.
        """
        args = args.strip()
        if not args:
            return {}, "usage"

        parsed: dict = {}
        for token in args.split():
            if "=" not in token:
                return {}, "usage"
            key, _, raw_val = token.partition("=")
            key_upper = key.upper()
            if key_upper not in self._MANUAL_ENTRY_FIELDS:
                return {}, "usage"
            col, type_fn, min_val, max_val = self._MANUAL_ENTRY_FIELDS[key_upper]
            try:
                value = type_fn(raw_val)
            except (ValueError, TypeError):
                return {}, f"Invalid value for {key_upper}: '{raw_val}'"
            if not (min_val < value <= max_val if min_val == 0.0 and type_fn is float
                    else min_val <= value <= max_val):
                return {}, (
                    f"{key_upper} out of range: {value} "
                    f"(valid: {min_val}–{max_val})"
                )
            parsed[col] = value

        if not parsed:
            return {}, "usage"
        return parsed, None

    def handle_manual_entry_text(self, args: str, chat_id: int | str | None = None) -> str:
        """Process /manual_entry argument string; save to DB; return reply text."""
        usage = "Usage: /manual_entry HRV=65 RHR=52 SLEEP=7.5 FATIGUE=3 WEIGHT=75.0"
        parsed, err = self._parse_manual_entry(args)
        if err == "usage":
            return usage
        if err:
            return f"❌ {err}\n{usage}"

        if self.db is None:
            return "❌ Database not available."

        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        detail = json.dumps({"date": today_str, **parsed}, sort_keys=True)
        if not self._audit_before_effect(self.db, chat_id, "TELEGRAM_MANUAL_ENTRY", "owner", detail):
            return _AUDIT_UNAVAILABLE_REPLY
        self.db.save_daily_metric(
            date=today_str,
            hrv=parsed.get("hrv_rmssd"),
            rhr=parsed.get("resting_hr"),
            sleep_hours=parsed.get("sleep_hours"),
            fatigue=parsed.get("fatigue_level"),
            weight=parsed.get("weight_kg"),
            data_source="manual_entry",
        )

        summary_parts = []
        label_map = {
            "hrv_rmssd":    "HRV",
            "resting_hr":   "RHR",
            "sleep_hours":  "Sleep",
            "fatigue_level": "Fatigue",
            "weight_kg":    "Weight",
        }
        for col, label in label_map.items():
            if col in parsed:
                summary_parts.append(f"{label}={parsed[col]}")
        return "✅ Logged: " + ", ".join(summary_parts)

    _INJURY_MAX_LEN = 200

    def handle_injury_text(self, args: str, chat_id: int | str | None = None) -> str:
        """``/injury <description>`` opens an injury, ``/injury off`` closes it (ADR-0069 §3).

        While it is open H1 triggers and the morning is REST. The audit row is written first
        (INV-22); without it nothing changes.
        """
        usage = "Usage: /injury <what hurts>  (REST until you send /injury off)"
        if self.db is None:
            return "❌ Database not available."
        athlete_id = _OWNER_ATHLETE_ID
        text = " ".join((args or "").split())
        if not text:
            try:
                injury = self.db.get_open_injury(athlete_id=athlete_id)
            except Exception as exc:
                _log.error("titan.telegram.injury_read_failed", extra={"error_class": exc.__class__.__name__})
                return "❌ Injury state unavailable."
            if injury is None:
                return usage
            return f"🩹 Open injury since {str(injury['opened_at'])[:10]}: {injury['description']}\nSend /injury off when it has healed."
        now = datetime.now(UTC).isoformat()
        if text.lower() == "off":
            if not self._audit_before_effect(self.db, chat_id, "TELEGRAM_INJURY_CLOSE", athlete_id):
                return _AUDIT_UNAVAILABLE_REPLY
            if not self.db.close_injury(athlete_id=athlete_id, closed_at=now):
                return "ℹ️ No open injury."
            return "✅ Injury closed. Training resumes from the next morning."
        description = text[: self._INJURY_MAX_LEN]
        detail = json.dumps({"description": description}, sort_keys=True)
        if not self._audit_before_effect(self.db, chat_id, "TELEGRAM_INJURY_OPEN", athlete_id, detail):
            return _AUDIT_UNAVAILABLE_REPLY
        if not self.db.open_injury(athlete_id=athlete_id, description=description, opened_at=now):
            injury = self.db.get_open_injury(athlete_id=athlete_id) or {}
            return f"ℹ️ An injury is already open: {injury.get('description', '?')}\nSend /injury off first."
        return f"🩹 Injury logged: {description}\nMornings are REST until you send /injury off."

    def handle_time_trial_text(self, args: str, chat_id: int | str | None = None) -> str:
        """Process ``/time_trial DISTANCE TIME [YYYY-MM-DD]``; store it for CS calibration (D-039)."""
        usage = "Usage: /time_trial 5000 18:30 [YYYY-MM-DD]  (distance in m or 5k; time mm:ss or h:mm:ss)"
        tokens = args.split()
        if len(tokens) not in (2, 3):
            return usage
        try:
            distance_m, time_sec = parse_time_trial(tokens[0], tokens[1])
            trial_date = parse_trial_date(tokens[2] if len(tokens) == 3 else None, datetime.now(UTC).date())
        except ValueError as exc:
            return f"❌ {exc}\n{usage}"

        if self.db is None:
            return "❌ Database not available."

        detail = json.dumps(
            {"date": trial_date, "distance_m": distance_m, "time_sec": time_sec}, sort_keys=True
        )
        if not self._audit_before_effect(self.db, chat_id, "TELEGRAM_TIME_TRIAL", "owner", detail):
            return _AUDIT_UNAVAILABLE_REPLY
        self.db.log_cs_performance(
            date=trial_date, distance_m=distance_m, time_sec=time_sec, athlete_id="owner"
        )
        minutes, seconds = divmod(round(time_sec), 60)
        return f"✅ Time-trial logged: {distance_m:g} m in {minutes}:{seconds:02d} on {trial_date}"

    def handle_athlete_sync(self, chat_id: int | str, athlete_id: str) -> str:
        """/sync from an athlete's own chat: audit first, then sync that athlete only (D10.3)."""
        if not _check_rate_limit(chat_id, "sync"):
            return "⏳ Please wait 30 seconds before repeating this command."
        callback = self.athlete_cmd_callbacks.get("sync")
        if callback is None:
            return "⏳ Sync not available yet."
        if not self._has_consent(athlete_id):
            return _NO_CONSENT_REPLY
        if not self._audit_before_effect(self.db, chat_id, "TELEGRAM_SYNC", athlete_id):
            return _AUDIT_UNAVAILABLE_REPLY
        return callback(athlete_id) or "✅ Sync complete."

    def _has_consent(self, athlete_id: str) -> bool:
        """The athlete's current consent (ADR-0067 D4.2); an unreadable answer counts as none."""
        try:
            return bool(self.db.has_current_consent(athlete_id))
        except Exception as exc:
            _log.error("titan.telegram.consent_check_failed", extra={"error_class": exc.__class__.__name__})
            return False

    @staticmethod
    def handle_athlete_consent() -> str:
        """/consent from an athlete's own chat: the current text and how to agree to it."""
        text = _consent_text(CONSENT_TEXT_VERSION)
        if text is None:
            return "❌ The consent text is not available right now. Please try again later."
        return f"{text}\n\nTo agree to version {CONSENT_TEXT_VERSION}, send: /agree {CONSENT_TEXT_VERSION}"

    def handle_athlete_agree(self, chat_id: int | str, athlete_id: str, args: str) -> str:
        """/agree <version> from an athlete's own chat: audit first, then record consent (D4.1)."""
        version = (args or "").strip()
        if version != CONSENT_TEXT_VERSION:
            return f"ℹ️ Send /consent to read the text, then /agree {CONSENT_TEXT_VERSION} to agree to it."
        if _consent_text(version) is None:
            return "❌ The consent text is not available right now, so nothing was recorded."
        if not self._audit_before_effect(self.db, chat_id, "TELEGRAM_CONSENT", athlete_id, detail=version):
            return _AUDIT_UNAVAILABLE_REPLY
        try:
            granted = self.db.grant_consent(athlete_id, version)
        except ValueError:
            return "⏹ Your 30 days after /stop have passed, so consent can no longer be given here."
        except Exception as exc:
            _log.critical(
                "titan.telegram.consent_grant_failed",
                extra={"athlete_id": athlete_id, "error_class": exc.__class__.__name__},
            )
            return "❌ Could not record your consent. Please try again."
        if not granted:
            return f"✅ Your consent to version {version} is already recorded."
        return f"✅ Thank you. Your consent to version {version} is recorded. /stop withdraws it at any time."

    def handle_athlete_stop(self, chat_id: int | str, athlete_id: str) -> str:
        """/stop from an athlete's own chat: audit first, then withdraw consent (ADR-0067 D4.3)."""
        if not self._audit_before_effect(self.db, chat_id, "TELEGRAM_STOP", athlete_id):
            return _AUDIT_UNAVAILABLE_REPLY
        try:
            self.db.revoke_consent(athlete_id)
        except Exception as exc:
            _log.critical(
                "titan.telegram.consent_revoke_failed",
                extra={"athlete_id": athlete_id, "error_class": exc.__class__.__name__},
            )
            return "❌ Could not record your stop. Please try again."
        return "⏹ Stopped. Your consent is withdrawn and no coaching runs for you."

    def register_athlete_command(self, command: str, callback: Callable[[str], str]) -> None:
        """Register the callback for a command from an athlete's own chat (ATHLETE_COMMANDS)."""
        if command not in ATHLETE_COMMANDS:
            raise ValueError(f"athletes have {ATHLETE_COMMANDS} only, not /{command}")
        self.athlete_cmd_callbacks[command] = callback

    @staticmethod
    def _audit_before_effect(
        db, chat_id: int | str | None, action: str, athlete_id: str, detail: str = ""
    ) -> bool:
        """INV-22: write the audit row before a Telegram state change.

        Returns False when the row could not be written; the caller then rejects
        the command without changing anything.
        """
        try:
            if db is None:
                raise RuntimeError("no database for the audit log")
            db.log_coach_action(
                coach_id=f"telegram:{chat_id}",
                action_type=action,
                target_athlete_id=athlete_id,
                action_detail=detail,
                resource="telegram",
            )
        except Exception as exc:
            _log.critical(
                "audit_write_failed",
                extra={"surface": "telegram", "action_type": action, "error": str(exc)},
                exc_info=True,
            )
            from titan.observability.metrics import get_metrics

            get_metrics().counter("audit_write_failure", labels={"surface": "telegram"})
            return False
        return True

    def register_override_callback(self, name: str, callback: Callable) -> None:
        """Register override callback dependencies (e.g., db_provider, athlete_id_provider)."""
        self.override_callbacks[name] = callback

    def send_governance_decision(
        self,
        *,
        text: str,
        decision_id: str,
        decision_type: str,
        athlete_id: str,
    ) -> bool:
        """Send governance decision with inline Accept/Override affordances.

        Another athlete gets the decision without the buttons: athletes have /consent,
        /agree, /sync and /stop only (ADR-0067 D10.3).
        """
        if not self.chat_id or self.athlete_id != _OWNER_ATHLETE_ID:
            return self.send_message(text)

        payload = {
            "decision_id": decision_id,
            "decision_type": decision_type,
            "athlete_id": athlete_id,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
        self._pending_override_prompts[int(self.chat_id)] = payload

        if not (self.bot and TELEBOT_AVAILABLE):
            return self.send_message(text)

        nonce = _create_override_nonce(self.db, decision_id, athlete_id)
        if nonce is None:
            return self.send_message(text)
        keyboard = telebot.types.InlineKeyboardMarkup()  # type: ignore[attr-defined]
        keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Accept", callback_data=f"override:accept:{nonce}"),
            telebot.types.InlineKeyboardButton("⚠️ Override (add reason)", callback_data=f"override:request:{nonce}"),
        )
        try:
            self.bot.send_message(int(self.chat_id), text, parse_mode="Markdown", reply_markup=keyboard)
        except Exception as e:
            _telegram_event(
                "failure",
                failure_class=SEND_FAIL,
                subsystem="send_governance_decision",
                error_class=e.__class__.__name__,
                error_message=redact_secrets(e),
            )
            return False
        return True

    def process_override_callback(self, chat_id: int, callback_data: str) -> str:
        """Handle override callback payload from Telegram CallbackQuery."""
        parts = callback_data.split(":", 2)
        if len(parts) < 2:
            return "⚠️ Unknown override action."
        action = parts[1]
        nonce = parts[2] if len(parts) >= 3 else None

        if action == "accept":
            nonce_decision = None if nonce is None else _consume_override_nonce(self.db, nonce)
            if nonce_decision is None:
                return "⚠️ This override request has already been used or has expired."
            pending = self._pending_override_prompts.get(chat_id)
            # IS-03 (b): an older decision's button never closes a newer pending decision.
            if pending is not None and pending.get("decision_id") != nonce_decision:
                return _OVERRIDE_STALE_REPLY
            self._pending_override_prompts.pop(chat_id, None)
            return "✅ Decision accepted."

        if action == "request":
            nonce_decision = None if nonce is None else _consume_override_nonce(self.db, nonce)
            if nonce_decision is None:
                return "⚠️ This override request has already been used or has expired."
            pending = self._pending_override_prompts.get(chat_id)
            if pending is None:
                return "⚠️ No active decision to override."
            # IS-03 (b): the nonce must belong to the decision that is pending now.
            if pending.get("decision_id") != nonce_decision:
                return _OVERRIDE_STALE_REPLY
            pending["awaiting_reason"] = "1"
            return "⚠️ Reply with your override reason (required)."

        return "⚠️ Unknown override action."

    def process_override_reason(self, chat_id: int, reason_text: str) -> str:
        """Validate override reason and persist OverrideSignal."""
        pending = self._pending_override_prompts.get(chat_id)
        if not pending or pending.get("awaiting_reason") != "1":
            return "⚠️ No override reason requested."

        reason = reason_text.strip()[: self._MAX_OVERRIDE_REASON_LEN]
        if not reason:
            return "⚠️ Override reason is required."

        db_provider = self.override_callbacks.get("db_provider")
        athlete_provider = self.override_callbacks.get("athlete_id_provider")
        db = db_provider() if db_provider else None
        athlete_id = pending.get("athlete_id")
        if athlete_provider is not None and not athlete_id:
            athlete_id = athlete_provider()
        if db is None:
            return "⚠️ Override recording unavailable (db missing)."
        decision_id = pending.get("decision_id")
        # IS-03 (a): without the athlete or the decision nothing is written; no
        # "unknown_athlete" row and no invented decision id.
        if not athlete_id or not decision_id:
            return "⚠️ Override recording unavailable (decision or athlete missing)."

        signal = OverrideSignal.create(
            decision_id=decision_id,
            athlete_id=athlete_id,
            override_source="telegram_bot",
            override_reason=reason,
        )
        detail = json.dumps({"decision_id": signal.decision_id, "reason": reason})
        if not self._audit_before_effect(db, chat_id, "TELEGRAM_OVERRIDE", signal.athlete_id, detail):
            return _AUDIT_UNAVAILABLE_REPLY
        record_override_signal(db, signal)
        self._pending_override_prompts.pop(chat_id, None)
        return "✅ Override recorded."

    def check_override_silence(self, *, now: datetime | None = None, timeout_hours: int = 4) -> list[int]:
        """Emit no-response follow-up alerts for pending override decisions."""
        current_time = now or datetime.now(tz=UTC)
        due_chat_ids: list[int] = []
        for chat_id, payload in list(self._pending_override_prompts.items()):
            created_raw = payload.get("created_at")
            created_at = datetime.fromisoformat(created_raw) if created_raw else current_time
            if current_time - created_at >= timedelta(hours=timeout_hours):
                due_chat_ids.append(chat_id)
                _telegram_event(
                    "failure",
                    failure_class=OVERRIDE_SILENCE,
                    subsystem="override_followup",
                    # SP-05: the athlete, never the chat id (ADR-0067 D2.8).
                    athlete_id=payload.get("athlete_id"),
                    timeout_hours=timeout_hours,
                )
        return due_chat_ids

    def register_command(self, command: str, callback: Callable):
        """Register a callback for a slash command."""
        self.cmd_callbacks[command] = callback

    # ------------------------------------------------------------------ #
    # SEND MESSAGES
    # ------------------------------------------------------------------ #
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        if not self.chat_id:
            _telegram_event(
                "slo_alert", slo_key="telegram_delivery_missing_chat_id", cause="INTEGRATION_CONFIG"
            )
            _telegram_event(
                "failure",
                failure_class=SEND_FAIL,
                subsystem="send_message",
                reason="missing_chat_id",
            )
            _log.warning("telegram_send_skipped_missing_chat_id")
            return False
        if self.bot and TELEBOT_AVAILABLE:
            try:
                self.bot.send_message(int(self.chat_id), text, parse_mode=parse_mode)
                self.message_history.append(
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "message_length": len(text),
                        "delivery_mode": "telegram_api",
                    }
                )
            except Exception as e:
                _telegram_event(
                    "slo_alert",
                    slo_key="telegram_delivery_failed",
                    cause="INTEGRATION_DELIVERY",
                    error=redact_secrets(e),
                )
                _telegram_event(
                    "failure",
                    failure_class=SEND_FAIL,
                    subsystem="send_message",
                    error_class=e.__class__.__name__,
                    error_message=redact_secrets(e),
                )
                _log.error("telegram_send_error", extra={"detail": redact_secrets(e)})
                return False
            else:
                return True
        else:
            # No bot (no token, or telebot missing): nothing reached anyone, so this is not
            # a delivery (D-107). The worker then retries the day and, after the last
            # attempt, leaves it with an alert; the console keeps working and warns here.
            _telegram_event(
                "failure",
                failure_class=SEND_FAIL,
                subsystem="send_message",
                reason="fallback_console_only",
                bot_available=bool(self.bot),
                telebot_available=TELEBOT_AVAILABLE,
            )
            _log.warning(
                "telegram_fallback_delivery_preview",
                extra={
                    "message_length": len(text),
                    "delivery_mode": "fallback",
                    "reason": "fallback_console_only",
                },
            )
            return False

    def send_weekly_plan(self, plan: dict) -> bool:
        # Plan values are escaped: a session type such as LONG_RUN broke the message (OW-M1, D-127).
        esc = _escape_markdown_legacy
        lines = [
            "🎯 *WEEKLY TRAINING PLAN*",
            f"Week of: {esc(plan.get('week_start', 'N/A'))}  |  Phase: {esc(plan.get('phase', 'N/A'))}",
            "",
            "📊 *Summary:*",
            f"• Volume: {_km(plan.get('total_km', 0))} km",
            f"• Quality sessions: {esc(plan.get('quality_count', 0))}",
            f"• Easy days: {esc(plan.get('easy_count', 0))}  |  Rest: {esc(plan.get('rest_count', 0))}",
            "",
            "💡 *Key Status:*",
            f"• Lactate threshold: {esc(plan.get('lactate_threshold', 'N/A'))} bpm",
            f"• HRV baseline: {esc(plan.get('hrv_baseline', 'N/A'))}",
            f"• TSB: {esc(plan.get('tsb_status', 'N/A'))}",
            "",
            "📅 *Daily Breakdown:*",
        ]
        for d in plan.get("daily_sessions", []):
            lines.append(
                f"*{esc(d['day'])}* – {esc(d['session_type'])} ({_km(d.get('distance_km', 0))} km)"
            )
            lines.append(f"  └ {esc(d.get('details', ''))}")
            if d.get("optimal_time"):
                lines.append(f"  └ ⏰ Best time: {esc(d['optimal_time'])}")
        lines += ["", f"💪 {esc(plan.get('motivation', 'Train smart!'))}"]
        return self.send_message("\n".join(lines))

    def send_daily_coaching(self, data: dict) -> bool:
        # Every value from `data` is escaped; only the fixed headings carry Markdown (OW-M1, D-127).
        esc = _escape_markdown_legacy

        def field(key: str, default: str) -> str:
            return esc(data.get(key, default))

        sleep = data.get('sleep_quality', 'N/A')
        sleep_text = f"{sleep}/100" if isinstance(sleep, (int, float)) else "N/A"
        # The morning's own day, so a morning sent after midnight keeps its date (OW-L5, D-130).
        try:
            briefing_day = date.fromisoformat(str(data["briefing_date"]))
        except (KeyError, ValueError):
            briefing_day = datetime.now(UTC).date()
        text = (
            f"🌅 *GOOD MORNING!*\n"
            f"{briefing_day.strftime('%A, %B %d, %Y')}\n\n"
            f"🏃 *Today:* {field('session_type', 'REST')} – {field('duration', 'N/A')}\n\n"
            f"⏰ *Optimal Run Time:* {field('optimal_time', 'N/A')}\n"
            f"  └ Dew point: {field('dew_point', 'N/A')}°C  |  {field('conditions', '')}\n\n"
            f"💊 *Recovery:*\n"
            f"  • HRV: {field('hrv_status', 'N/A')}\n"
            f"  • Sleep: {sleep_text}\n"
            f"  • Readiness: {field('readiness_score', 'N/A')}/100\n\n"
            f"🍽 *Nutrition:* {field('nutrition_plan', 'See /nutrition')}\n\n"
            f"👟 *Shoe:* {field('shoe', 'See /shoes')}\n"
        )
        if data.get("primary_reason"):
            text += f"\n🧭 *Why this decision:* {esc(_tidy_floats(data['primary_reason']))}"
        if data.get("actionable_guidance"):
            text += f"\n✅ *Actionable guidance:* {esc(_tidy_floats(data['actionable_guidance']))}"
        if data.get("hrv_stress_context"):
            text += f"\n🩺 *Stress context:* {esc(_tidy_floats(data['hrv_stress_context']))}"
        fueling_gate = data.get("fueling_gate") or {}
        if fueling_gate.get("action") == "FLAG" and fueling_gate.get("phase") == 4:
            text += "\n🍌 *Fueling:* carry food or gels for this long run."
        if data.get("special_note"):
            text += f"\n⚠️ {esc(data['special_note'])}"
        return self.send_message(text)

    def send_post_run_analysis(self, data: dict) -> bool:
        esc = _escape_markdown_legacy  # OW-M1, D-127
        text = (
            f"✅ *RUN ANALYSIS*\n\n"
            f"📊 *Stats:*\n"
            f"  • Distance: {esc(data.get('distance_km', 0))} km\n"
            f"  • Duration: {esc(data.get('duration', 'N/A'))}\n"
            f"  • Avg pace: {esc(data.get('avg_pace', 'N/A'))} /km\n"
            f"  • Avg HR: {esc(data.get('avg_hr', 'N/A'))} bpm\n\n"
            f"🔬 *Analysis:*\n"
            f"  • HR drift: {esc(data.get('hr_drift', 'N/A'))}%\n"
            f"  • Efficiency: {esc(data.get('efficiency', 'N/A'))}\n"
            f"  • Training load: {esc(data.get('training_load', 'N/A'))}\n\n"
            f"📈 *Next steps:*\n{esc(data.get('next_steps', 'Recover and refuel'))}\n"
        )
        return self.send_message(text)

    def send_alert(
        self,
        title: str,
        message: str,
        level: Literal["critical", "warning", "info", "ok"] = "warning",
    ) -> bool:
        level_to_emoji = {
            "critical": "🛑",
            "warning":  "⚠️",
            "info":     "ℹ️",
            "ok":       "✅",
        }
        if level not in level_to_emoji:
            _log.error(
                "Invalid alert level %r; defaulting to 'warning'.", level
            )
            level = "warning"
        emoji = level_to_emoji[level]
        # Titles and messages carry lock codes and athlete ids: plain text, escaped (OW-M1, D-127).
        title_text = _escape_markdown_legacy(title)
        message_text = _escape_markdown_legacy(message)
        return self.send_message(f"{emoji} *{title_text}*\n\n{message_text}")

    def send_structured_alert(self, event_type: str, lock_code: str, message: str) -> bool:
        """Send deduplicated CRITICAL alerts and persistence summaries."""
        dedup_window = timedelta(hours=20)
        persist_window = timedelta(hours=72)
        now = datetime.now(tz=UTC)
        key = (event_type, lock_code)
        snapshot = self._alert_history.get(key)

        if snapshot is None:
            self._alert_history[key] = {
                "first_seen": now,
                "last_sent": now,
                "suppressed_count": 0,
            }
            return self.send_alert("CRITICAL", message, level="critical")

        last_sent = snapshot["last_sent"]
        first_seen = snapshot["first_seen"]
        if not isinstance(last_sent, datetime) or not isinstance(first_seen, datetime):
            _log.warning(
                "Corrupted alert history key=%s last_sent=%r (%s) first_seen=%r (%s). Resetting.",
                key,
                last_sent, type(last_sent).__name__,
                first_seen, type(first_seen).__name__,
            )
            self._alert_history[key] = {
                "first_seen": now,
                "last_sent":  now,
                "suppressed_count": 0,
            }
            return self.send_alert(
                "ALERT HISTORY CORRUPTION",
                "Internal state reset. Monitor for recurrence.",
                level="critical",
            )

        if now - last_sent < dedup_window:
            snapshot["suppressed_count"] = int(snapshot["suppressed_count"]) + 1
            _telegram_event(
                "critical_alert_deduplicated",
                severity=EventSeverity.WARNING,
                event_type=event_type,
                lock_code=lock_code,
                suppressed_count=snapshot["suppressed_count"],
            )
            return False

        if now - first_seen >= persist_window:
            summary = (
                f"Persistent condition: {event_type} ({lock_code}) still active after 72h. "
                f"Suppressed duplicates: {snapshot['suppressed_count']}."
            )
            snapshot["last_sent"] = now
            snapshot["suppressed_count"] = 0
            return self.send_alert("CRITICAL SUMMARY", summary, level="warning")

        snapshot["last_sent"] = now
        return self.send_alert("CRITICAL", message, level="critical")

    # ------------------------------------------------------------------ #
    # SCHEDULER
    # ------------------------------------------------------------------ #
    def schedule_task(
        self,
        name: str,
        time_str: str,
        callback: Callable,
        days: list[str] = None,
        source: str | None = None,
    ):
        """Run ``callback`` at ``time_str`` (HH:MM UTC) on ``days``; ``EVERY_MINUTE`` runs it each minute."""
        all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        with self._tasks_lock:
            self.scheduled_tasks.append(
                {
                    "name": name,
                    "time": time_str,
                    "callback": callback,
                    "days": days or all_days,
                }
            )
        _telegram_event(
            "scheduler_task_added",
            task_name=name,
            scheduled_time=time_str,
            source=source,
        )
        _log.info("telegram_task_scheduled", extra={"task_name": name, "scheduled_time": time_str})

    # ------------------------------------------------------------------ #
    # START / STOP
    # ------------------------------------------------------------------ #
    def _prune_expired_override_nonces(self) -> None:
        """Drop expired override nonces at startup; unexpired ones stay valid (ADR-0060 D2)."""
        if self.db is None:
            return
        try:
            self.db.prune_expired_override_nonces(datetime.now(UTC))
        except Exception as exc:
            _log.warning("telegram_override_nonce_prune_failed", extra={"error": str(exc)})

    def start_bot(self):
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()
        self._prune_expired_override_nonces()

        # Scheduler thread
        self._sched_thread = threading.Thread(
            target=self._scheduler_worker, daemon=True, name="TelegramScheduler"
        )
        self._sched_thread.start()

        # Polling thread (real listener)
        if self.bot and TELEBOT_AVAILABLE:
            # Clear any existing webhook to prevent 409 Conflict with polling
            try:
                self.bot.remove_webhook()
            except Exception as e:
                _telegram_event(
                    "webhook_removal_failed",
                    subsystem="start_bot",
                    error_class=e.__class__.__name__,
                    error_message=redact_secrets(e),
                )
            self._poll_thread = threading.Thread(
                target=self._poll_worker, daemon=True, name="TelegramPoller"
            )
            self._poll_thread.start()
            _log.info("telegram_bot_started", extra={"mode": "polling_and_scheduler"})
        else:
            _telegram_event(
                "failure",
                failure_class=POLL_FAIL,
                subsystem="start_bot",
                reason="polling_unavailable",
                bot_available=bool(self.bot),
                telebot_available=TELEBOT_AVAILABLE,
            )
            _log.info("telegram_bot_started", extra={"mode": "scheduler_only"})

    def stop_bot(self):
        self._stop_event.set()
        self.is_running = False
        if self.bot and TELEBOT_AVAILABLE:
            try:
                self.bot.stop_polling()
            except Exception as e:
                _telegram_event(
                    "failure",
                    failure_class=POLL_FAIL,
                    subsystem="stop_bot",
                    error_class=e.__class__.__name__,
                    error_message=redact_secrets(e),
                )
        if self._sched_thread:
            self._sched_thread.join(timeout=5)
        if self._sched_thread and self._sched_thread.is_alive():
            _telegram_event(
                "worker_shutdown_timeout",
                level="error",
                worker_name="Scheduler",
                timeout_seconds=5,
                still_alive=True,
            )
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        if self._poll_thread and self._poll_thread.is_alive():
            _telegram_event(
                "worker_shutdown_timeout",
                level="error",
                worker_name="Polling",
                timeout_seconds=5,
                still_alive=True,
            )

    def _poll_worker(self):
        """Real polling loop – listens for user commands.

        Uses exponential backoff on repeated failures to avoid 409 Conflict
        storms when two polling sessions overlap.
        """
        backoff_s = 5
        max_backoff_s = 120
        while not self._stop_event.is_set():
            try:
                self.bot.infinity_polling(timeout=10, long_polling_timeout=5)
                # infinity_polling exited cleanly — reset backoff
                backoff_s = 5
            except Exception as e:
                if self._stop_event.is_set():
                    return
                is_conflict = "409" in str(e).lower() or "conflict" in str(e).lower()
                _telegram_event(
                    "failure",
                    failure_class=POLL_FAIL,
                    subsystem="poll_worker",
                    error_class=e.__class__.__name__,
                    error_message=redact_secrets(e),
                    is_conflict=is_conflict,
                    backoff_s=backoff_s,
                )
                _log.warning("telegram_polling_retry", extra={"detail": redact_secrets(e), "backoff_s": backoff_s})
                self._stop_event.wait(timeout=backoff_s)
                backoff_s = min(backoff_s * 2, max_backoff_s)

    def _scheduler_worker(self):
        """Fires scheduled tasks at the right time."""
        expected_wakeup: float | None = None
        while not self._stop_event.is_set():
            now_ts = time.time()
            if expected_wakeup is not None:
                drift_seconds = now_ts - expected_wakeup
                if drift_seconds > 1:
                    _telegram_event(
                        "failure",
                        failure_class=SCHEDULER_DRIFT,
                        subsystem="scheduler_worker",
                        drift_seconds=round(drift_seconds, 3),
                    )

            now = datetime.now(UTC)  # strftime-only; UTC-aware is safe for strftime
            cur_time = now.strftime("%H:%M")
            cur_day = now.strftime("%A")
            with self._tasks_lock:
                due_tasks = [
                    task
                    for task in self.scheduled_tasks
                    if task["time"] in (cur_time, EVERY_MINUTE) and cur_day in task["days"]
                ]
            for task in due_tasks:
                try:
                    task["callback"]()
                except Exception as e:
                    _telegram_event(
                        "failure",
                        failure_class=CALLBACK_ERROR,
                        subsystem="scheduler_worker",
                        task_name=task["name"],
                        error_class=e.__class__.__name__,
                        error_message=redact_secrets(e),
                    )
                    _log.error(
                        "telegram_scheduled_task_error",
                        extra={"task_name": task["name"], "detail": redact_secrets(e)},
                    )
            # Sleep until next full minute
            sleep_seconds = max(1, 60 - now.second)
            expected_wakeup = now_ts + sleep_seconds
            self._stop_event.wait(timeout=sleep_seconds)


def alert_operator(
    telegram: TitanTelegramBot,
    *,
    title: str,
    message: str,
    athlete_text: str,
    level: str = "warning",
    event_type: str | None = None,
    lock_code: str | None = None,
) -> None:
    """Send an operator alert about the coached athlete to the right people (D-107).

    The owner's own bot: exactly as before, ``send_structured_alert`` when ``event_type``
    is given, else ``send_alert``. Another athlete's bot: the athlete gets ``athlete_text``,
    short and with no operator instructions, and the owner's chat (TELEGRAM_CHAT_ID) gets
    the operator alert with the athlete id. Neither carries health data.
    """
    athlete_id = getattr(telegram, "athlete_id", _OWNER_ATHLETE_ID)
    if not isinstance(athlete_id, str) or athlete_id == _OWNER_ATHLETE_ID:
        if event_type is not None:
            telegram.send_structured_alert(event_type=event_type, lock_code=lock_code or event_type, message=message)
        else:
            telegram.send_alert(title=title, message=message, level=level)
        return
    try:
        telegram.send_message(athlete_text, parse_mode="")
    finally:
        TitanTelegramBot(db=getattr(telegram, "db", None)).send_message(
            f"{title} — athlete {athlete_id} ({level})\n\n{message}", parse_mode="",
        )
