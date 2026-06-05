import pytest

from titan.config import evidence_registry


@pytest.mark.unit
def test_get_metrics_under_review_returns_audited_metrics() -> None:
    under_review = evidence_registry.get_metrics_under_review()

    assert under_review
    assert "trimp" in under_review
    assert "readiness_score" not in under_review


@pytest.mark.unit
def test_get_metrics_under_review_empty_when_no_under_review(monkeypatch) -> None:
    original = evidence_registry.METRIC_LIFECYCLE
    monkeypatch.setattr(
        evidence_registry,
        "METRIC_LIFECYCLE",
        {
            name: {**metadata, "state": "Active"}
            for name, metadata in original.items()
        },
    )

    assert evidence_registry.get_metrics_under_review() == []
