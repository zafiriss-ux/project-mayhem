"""Shared structured-event helpers for observability payloads."""

import json
import logging
from collections.abc import Callable
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


SLO_ALERT = "slo_alert"

# Called with every slo_alert payload (P4-09). The worker registers one that counts the alert
# and tells the owner; nothing is registered elsewhere, so other processes only log it.
_slo_alert_listeners: list[Callable[[dict[str, Any]], None]] = []


def add_slo_alert_listener(listener: Callable[[dict[str, Any]], None]) -> None:
    """Call ``listener`` with every slo_alert payload from now on; adding it twice is a no-op."""
    if listener not in _slo_alert_listeners:
        _slo_alert_listeners.append(listener)


def structured_event_payload(
    flow: str,
    action: str,
    *,
    severity: EventSeverity | str = EventSeverity.INFO,
    **fields: Any,
) -> dict[str, Any]:
    """Build a structured-event payload with a shared severity contract.

    Every structured event is built here, so this is the one place an ``slo_alert`` passes
    through: it goes to the registered listeners too (P4-09). A failing listener never
    stops the event.
    """
    payload = {
        "flow": flow,
        "action": action,
        "severity": severity_value(severity),
        **fields,
    }
    if action == SLO_ALERT:
        for listener in list(_slo_alert_listeners):
            try:
                listener(dict(payload))
            except Exception:  # noqa: BLE001 — an alert listener never breaks the event itself
                logging.getLogger(__name__).exception("slo_alert_listener_failed")
    return payload


def make_event_emitter(
    subsystem: str,
    logger: logging.Logger,
) -> Callable[..., None]:
    """Return a structured-event emitter bound to *subsystem* and *logger*.

    Eliminates the repeated module-level ``_<subsystem>_event()`` boilerplate
    that each module previously defined independently.

    Usage::

        _log = logging.getLogger(__name__)
        _my_event = make_event_emitter("my_subsystem", _log)

        _my_event("started", count=3)
        _my_event("failed", severity=EventSeverity.WARNING, reason="timeout")
    """

    def _emitter(
        action: str,
        *,
        severity: EventSeverity | str = EventSeverity.INFO,
        **fields: Any,
    ) -> None:
        logger.info(
            json.dumps(
                structured_event_payload(subsystem, action, severity=severity, **fields),
                default=str,
            )
        )

    _emitter.__name__ = f"_{subsystem}_event"
    _emitter.__qualname__ = f"_{subsystem}_event"
    return _emitter
