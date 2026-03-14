"""Tests for NotificationGateway (T3-09)."""
import json
from pathlib import Path

import pytest

from titan.integrations.notification_gateway import (
    DeliveryResult,
    FileChannel,
    NotificationGateway,
    TelegramChannel,
)


class _OkTelegramBot:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def send_daily_coaching(self, message: str) -> None:
        self.calls.append(message)


class _FailTelegramBot:
    def send_daily_coaching(self, message: str) -> None:
        raise RuntimeError("Telegram API unavailable")


class _StructuredTelegramBot:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_daily_coaching(self, payload: dict) -> None:
        self.calls.append(payload)
        payload["session_type"]
        payload["special_note"]
        payload["primary_reason"]
        payload["actionable_guidance"]
        payload["hrv_stress_context"]


def test_telegram_channel_wraps_string_payload_for_daily_coaching_contract():
    """TelegramChannel must adapt string messages to coaching payload dicts."""
    bot = _StructuredTelegramBot()
    telegram = TelegramChannel(bot)

    ok = telegram.send("Morning briefing")

    assert ok is True
    assert len(bot.calls) == 1
    assert isinstance(bot.calls[0], dict)
    assert bot.calls[0]["special_note"] == "Morning briefing"


def test_telegram_channel_handles_empty_string_without_contract_shape_failure():
    """Empty string payloads should still preserve dict contract for downstream."""
    bot = _StructuredTelegramBot()
    telegram = TelegramChannel(bot)

    ok = telegram.send("")

    assert ok is True
    assert len(bot.calls) == 1
    assert bot.calls[0]["special_note"] == ""


def test_gateway_uses_primary_channel_on_success(tmp_path):
    """When Telegram succeeds, the file channel must not be written."""
    bot = _OkTelegramBot()
    telegram = TelegramChannel(bot)
    file_ch = FileChannel(output_dir=tmp_path)

    gateway = NotificationGateway([telegram, file_ch])
    result = gateway.send("Morning briefing", level="info")

    assert result.success is True
    assert result.channel == "telegram"
    assert result.tried == 1
    assert bot.calls == [
        {
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
            "special_note": "Morning briefing",
        }
    ]
    # File channel must not have been triggered
    assert list(tmp_path.glob("daily_briefing_*.txt")) == []


def test_gateway_falls_back_to_file_on_telegram_failure(tmp_path):
    """When Telegram fails, the gateway must write to the file channel."""
    failing_bot = _FailTelegramBot()
    telegram = TelegramChannel(failing_bot)
    file_ch = FileChannel(output_dir=tmp_path)

    gateway = NotificationGateway([telegram, file_ch])
    result = gateway.send("Morning briefing — fallback", level="info")

    assert result.success is True
    assert result.channel == "file"
    assert result.tried == 2

    files = list(tmp_path.glob("daily_briefing_*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "Morning briefing — fallback"


def test_gateway_logs_delivery_chain_result(tmp_path, caplog):
    """A structured log event with channel name and outcome must be emitted
    regardless of which channel succeeded."""
    import logging

    bot = _OkTelegramBot()
    gateway = NotificationGateway([TelegramChannel(bot), FileChannel(output_dir=tmp_path)])

    with caplog.at_level(logging.INFO, logger="titan.integrations.notification_gateway"):
        gateway.send("Test message", level="info")

    delivery_events = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
            if payload.get("action") == "delivery_success":
                delivery_events.append(payload)
        except (ValueError, AttributeError):
            pass

    assert delivery_events, "delivery_success event must be logged"
    assert delivery_events[0]["channel"] == "telegram"
