from titan.config.evidence_registry import METRIC_LIFECYCLE, METRIC_LIFECYCLE_STATES

EXPECTED_FIELDS = {
    "state",
    "governance_gates",
    "telegram_briefing",
    "operator_console_payload",
    "evidence_registry_entry",
}


def test_metric_lifecycle_registry_schema_and_state_values() -> None:
    assert METRIC_LIFECYCLE

    for metric_name, metadata in METRIC_LIFECYCLE.items():
        assert set(metadata) == EXPECTED_FIELDS, metric_name
        assert metadata["state"] in METRIC_LIFECYCLE_STATES, metric_name
        assert isinstance(metadata["governance_gates"], list), metric_name
        assert isinstance(metadata["telegram_briefing"], bool), metric_name
        assert isinstance(metadata["operator_console_payload"], bool), metric_name
        assert isinstance(metadata["evidence_registry_entry"], bool), metric_name


def test_under_review_metrics_have_no_governance_gate_or_evidence_entry() -> None:
    for metric_name, metadata in METRIC_LIFECYCLE.items():
        if metadata["state"] != "Under Review":
            continue

        assert metadata["governance_gates"] == [], metric_name
        assert metadata["evidence_registry_entry"] is False, metric_name
