"""P4-05 (ADR-0069 §7): the unused NotificationGateway is deleted; the worker sends directly.

AGENTS §16.6 is reworded in the policy-only documents PR. These tests keep the gateway from
coming back half-wired: no module of that name, and no code in ``titan/`` that imports it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TITAN = Path(__file__).resolve().parents[1] / "titan"


@pytest.mark.unit
def test_the_gateway_module_is_gone() -> None:
    assert importlib.util.find_spec("titan.integrations.notification_gateway") is None


@pytest.mark.unit
def test_no_titan_code_names_the_gateway() -> None:
    hits = [
        str(path.relative_to(TITAN))
        for path in TITAN.rglob("*.py")
        if "NotificationGateway" in path.read_text(encoding="utf-8")
        or "notification_gateway" in path.read_text(encoding="utf-8")
    ]
    assert hits == []
