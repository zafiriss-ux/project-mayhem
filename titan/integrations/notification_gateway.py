"""Notification Gateway — ordered fallback chain for outbound notifications.

Provides a ``NotificationGateway`` that tries channels in priority order and
stops on the first successful delivery. This ensures that a Telegram outage or
token expiry does not silently prevent the athlete from receiving their daily
coaching output.

Channels (priority order):
  1. TelegramChannel   — wraps TitanTelegramBot (primary)
  2. FileChannel        — writes to ~/Documents/TITAN/daily_briefing_YYYY-MM-DD.txt
                          (always succeeds unless disk is full; no new dependencies)

Usage::

    gateway = NotificationGateway([
        TelegramChannel(telegram_bot),
        FileChannel(),
    ])
    gateway.send(message, level="info")
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_log = logging.getLogger(__name__)


def _gw_event(action: str, **fields) -> None:
    _log.info(json.dumps({"flow": "notification_gateway", "action": action, **fields}, default=str))


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class DeliveryResult:
    success: bool
    channel: str
    tried: int


# ── Abstract channel interface ────────────────────────────────────────────────

class NotificationChannel(ABC):
    """Base class for a single notification delivery channel."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable channel identifier for logging."""

    @abstractmethod
    def send(self, message: str) -> bool:
        """Attempt delivery. Return True on success, False on failure.

        Must not raise — exceptions are the caller's responsibility to catch.
        """


# ── Telegram channel ──────────────────────────────────────────────────────────

class TelegramChannel(NotificationChannel):
    """Wraps TitanTelegramBot.send_daily_coaching() as a NotificationChannel."""

    def __init__(self, bot) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "telegram"

    def send(self, message: str) -> bool:
        try:
            payload = {
                "session_type": "N/A",
                "duration": "N/A",
                "optimal_time": "N/A",
                "dew_point": "N/A",
                "conditions": "",
                "hrv_status": "N/A",
                "sleep_quality": "N/A",
                "readiness_score": "N/A",
                "nutrition_plan": "See /nutrition",
                "shoe": "See /shoes",
                "primary_reason": "",
                "actionable_guidance": "",
                "hrv_stress_context": "",
                "special_note": message,
            }
            send_ok = self._bot.send_daily_coaching(payload)
            if send_ok is False:
                _gw_event("channel_failed", channel=self.name, error_class="BooleanSendFailure")
                return False
            return bool(send_ok)
        except Exception as exc:
            _gw_event("channel_failed", channel=self.name, error_class=type(exc).__name__)
            return False


# ── File channel ──────────────────────────────────────────────────────────────

class FileChannel(NotificationChannel):
    """Writes the daily briefing to a dated file in the TITAN data directory."""

    def __init__(self, output_dir: Path | None = None) -> None:
        if output_dir is None:
            output_dir = Path.home() / "Documents" / "TITAN"
        self._output_dir = output_dir

    @property
    def name(self) -> str:
        return "file"

    def send(self, message: str) -> bool:
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
            dest = self._output_dir / f"daily_briefing_{date_str}.txt"
            dest.write_text(message, encoding="utf-8")
            _gw_event("file_channel_written", path=str(dest), date=date_str)
        except Exception as exc:
            _gw_event("channel_failed", channel=self.name, error_class=type(exc).__name__)
            return False
        else:
            return True


# ── Gateway ───────────────────────────────────────────────────────────────────

class NotificationGateway:
    """Ordered fallback chain for outbound notifications.

    Iterates channels in priority order; stops on first successful delivery.
    Logs the full delivery chain result (which channel succeeded, how many
    were tried) as a structured event.
    """

    def __init__(self, channels: list[NotificationChannel]) -> None:
        self._channels = channels

    def send(self, message: str, level: str = "info") -> DeliveryResult:
        """Send message through the fallback chain.

        Args:
            message: The notification content to deliver.
            level:   Informational level tag for the structured log event.

        Returns:
            ``DeliveryResult`` with success flag, winning channel name, and
            number of channels tried.
        """
        for idx, channel in enumerate(self._channels, start=1):
            try:
                ok = channel.send(message)
            except Exception as exc:
                _gw_event(
                    "channel_exception",
                    channel=channel.name,
                    error_class=type(exc).__name__,
                )
                ok = False

            if ok:
                _gw_event(
                    "delivery_success",
                    channel=channel.name,
                    tried=idx,
                    level=level,
                )
                return DeliveryResult(success=True, channel=channel.name, tried=idx)

        _gw_event(
            "delivery_failed",
            tried=len(self._channels),
            level=level,
        )
        return DeliveryResult(success=False, channel="none", tried=len(self._channels))
