from titan.core.structured_events import EventSeverity, severity_value, structured_event_payload


def test_structured_event_payload_happy_path_info_default():
    payload = structured_event_payload("garmin_sync", "activities_synced", count=3)

    assert payload == {
        "flow": "garmin_sync",
        "action": "activities_synced",
        "severity": "info",
        "count": 3,
    }


def test_severity_value_normalizes_string_input_boundary():
    assert severity_value("WARNING") == "warning"
    assert severity_value(EventSeverity.CRITICAL) == "critical"
