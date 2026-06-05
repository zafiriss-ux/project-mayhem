"""Tests for titan/observability/metrics.py (TD-11 / Phase 18)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from titan.observability.metrics import MetricsCollector, get_metrics


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    import titan.observability.metrics as _m
    _m._collector = None
    yield
    _m._collector = None


@pytest.mark.integration
def test_counter_emits_json_log(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="titan.metrics"):
        MetricsCollector().counter("test_c")
    assert caplog.records, "Expected at least one log record"
    payload = json.loads(caplog.records[-1].message)
    assert payload["metric_type"] == "counter"
    assert payload["name"] == "test_c"


@pytest.mark.integration
def test_gauge_emits_correct_value(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="titan.metrics"):
        MetricsCollector().gauge("tsb", -3.2)
    payload = json.loads(caplog.records[-1].message)
    assert payload["value"] == pytest.approx(-3.2)
    assert payload["metric_type"] == "gauge"


@pytest.mark.integration
def test_get_metrics_returns_singleton() -> None:
    m1 = get_metrics()
    m2 = get_metrics()
    assert m1 is m2


@pytest.mark.integration
def test_ctl_recompute_emits_histogram(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="metrics_test.db", db_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger="titan.metrics"):
        db.get_ctl_atl_tsb("owner")

    names = [
        json.loads(r.message)["name"]
        for r in caplog.records
        if r.name == "titan.metrics"
    ]
    assert "ctl_recompute_ms" in names
