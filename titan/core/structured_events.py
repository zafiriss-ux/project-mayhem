"""Shared structured-event helpers for observability payloads."""

from enum import StrEnum
from typing import Any


class EventSeverity(StrEnum):
    """Canonical event severity levels for structured logs."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


def severity_value(severity: EventSeverity | str) -> str:
    """Return normalized string value for event severity."""
    if isinstance(severity, EventSeverity):
        return severity.value
    return str(severity).lower()


def structured_event_payload(
    flow: str,
    action: str,
    *,
    severity: EventSeverity | str = EventSeverity.INFO,
    **fields: Any,
) -> dict[str, Any]:
    """Build a structured-event payload with a shared severity contract."""
    return {
        "flow": flow,
        "action": action,
        "severity": severity_value(severity),
        **fields,
    }
