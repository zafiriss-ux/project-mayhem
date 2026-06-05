import json
import logging

import pytest

from titan.core.structured_events import (
    EventSeverity,
    make_event_emitter,
    severity_value,
    structured_event_payload,
)


@pytest.mark.integration
def test_structured_event_payload_happy_path_info_default():
    payload = structured_event_payload("garmin_sync", "activities_synced", count=3)

    assert payload == {
        "flow": "garmin_sync",
        "action": "activities_synced",
        "severity": "info",
        "count": 3,
    }


@pytest.mark.integration
def test_severity_value_normalizes_string_input_boundary():
    assert severity_value("WARNING") == "warning"
    assert severity_value(EventSeverity.CRITICAL) == "critical"


# ── make_event_emitter ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_make_event_emitter_emits_correct_flow_and_action(caplog):
    logger = logging.getLogger("test_emitter_flow")
    emitter = make_event_emitter("mysubsystem", logger)

    with caplog.at_level(logging.INFO, logger="test_emitter_flow"):
        emitter("started", count=7)

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["flow"] == "mysubsystem"
    assert payload["action"] == "started"
    assert payload["count"] == 7
    assert payload["severity"] == "info"


@pytest.mark.integration
def test_make_event_emitter_respects_custom_severity(caplog):
    logger = logging.getLogger("test_emitter_severity")
    emitter = make_event_emitter("nutrition", logger)

    with caplog.at_level(logging.INFO, logger="test_emitter_severity"):
        emitter("plan_skipped", severity=EventSeverity.WARNING, reason="no_data")

    payload = json.loads(caplog.records[0].message)
    assert payload["severity"] == "warning"
    assert payload["reason"] == "no_data"


@pytest.mark.integration
def test_make_event_emitter_uses_bound_logger_not_root(caplog):
    """Emitter must log through its bound logger, not a shared global."""
    logger_a = logging.getLogger("subsystem_a")
    logger_b = logging.getLogger("subsystem_b")
    emitter_a = make_event_emitter("a", logger_a)
    emitter_b = make_event_emitter("b", logger_b)

    with caplog.at_level(logging.INFO, logger="subsystem_a"):
        emitter_a("ping")
        emitter_b("should_not_appear")

    names = [r.name for r in caplog.records]
    assert "subsystem_a" in names
    assert "subsystem_b" not in names


@pytest.mark.integration
def test_make_event_emitter_dunder_name_reflects_subsystem():
    logger = logging.getLogger("test_name")
    emitter = make_event_emitter("readiness", logger)

    assert emitter.__name__ == "_readiness_event"
    assert emitter.__qualname__ == "_readiness_event"


@pytest.mark.integration
@pytest.mark.parametrize("subsystem", ["nutrition", "weekly_planner", "readiness"])
def test_make_event_emitter_parametric_subsystem_roundtrip(subsystem, caplog):
    """Factory must bind subsystem correctly across known migrated modules."""
    logger = logging.getLogger(f"test_{subsystem}")
    emitter = make_event_emitter(subsystem, logger)

    with caplog.at_level(logging.INFO, logger=f"test_{subsystem}"):
        emitter("test_action")

    payload = json.loads(caplog.records[0].message)
    assert payload["flow"] == subsystem
