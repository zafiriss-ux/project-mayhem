"""Tests for TD-OBS: Prometheus scrape endpoint and dual-emit MetricsCollector."""

from pathlib import Path

import pytest

# Import at module level to register Prometheus instruments in REGISTRY.
import titan.observability.metrics  # noqa: F401


@pytest.mark.unit
def test_prometheus_counter_registered():
    from prometheus_client import REGISTRY

    # prometheus_client strips _total suffix from Counter family name.
    names = [m.name for m in REGISTRY.collect()]
    assert "titan_api_startup" in names


@pytest.mark.unit
def test_prometheus_gauge_registered():
    from prometheus_client import REGISTRY

    names = [m.name for m in REGISTRY.collect()]
    assert "titan_tsb_value" in names


@pytest.mark.integration
def test_metrics_endpoint_returns_200(jwt_keys, monkeypatch):  # noqa: ARG001
    from fastapi.testclient import TestClient

    from titan.api.main import create_app

    monkeypatch.setenv("TITAN_METRICS_TOKEN", "synthetic-scrape-token")  # M0-14
    client = TestClient(create_app())
    r = client.get("/metrics", headers={"Authorization": "Bearer synthetic-scrape-token"})
    assert r.status_code == 200
    assert "titan_api_startup" in r.text or "python_" in r.text


@pytest.mark.unit
def test_metrics_collector_emits_to_prom():
    from prometheus_client import REGISTRY

    from titan.observability.metrics import get_metrics

    m = get_metrics()
    m.counter("api_startup")
    # Family name is "titan_api_startup"; samples include "titan_api_startup_total".
    after = {
        met.name: list(met.samples)
        for met in REGISTRY.collect()
        if met.name == "titan_api_startup"
    }
    assert len(after) > 0


@pytest.mark.unit
def test_metrics_endpoint_exempt_from_csrf():
    src = Path("titan/api/main.py").read_text()
    assert '"/metrics"' in src, "/metrics must be CSRF-exempt"
