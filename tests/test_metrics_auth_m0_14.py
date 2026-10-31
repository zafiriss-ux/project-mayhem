"""M0-14: the API's /metrics needs a scrape token, and port 8000 is published on localhost only."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

_TOKEN = "synthetic-scrape-token-0123456789"


def _client() -> TestClient:
    from titan.api.main import create_app

    return TestClient(create_app())


@pytest.mark.integration
def test_metrics_is_closed_when_no_token_is_configured(jwt_keys, monkeypatch):  # noqa: ARG001
    monkeypatch.delenv("TITAN_METRICS_TOKEN", raising=False)
    r = _client().get("/metrics", headers={"Authorization": f"Bearer {_TOKEN}"})
    assert r.status_code == 404
    assert "python_" not in r.text and "titan_" not in r.text


@pytest.mark.integration
def test_metrics_is_closed_when_the_token_is_blank(jwt_keys, monkeypatch):  # noqa: ARG001
    monkeypatch.setenv("TITAN_METRICS_TOKEN", "   ")
    r = _client().get("/metrics", headers={"Authorization": "Bearer "})
    assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong-token"},
    {"Authorization": _TOKEN},
    {"Authorization": f"Basic {_TOKEN}"},
    {"Authorization": f"Bearer {_TOKEN}x"},
])
def test_metrics_refuses_a_missing_or_wrong_token(jwt_keys, monkeypatch, headers):  # noqa: ARG001
    monkeypatch.setenv("TITAN_METRICS_TOKEN", _TOKEN)
    r = _client().get("/metrics", headers=headers)
    assert r.status_code == 401
    assert "python_" not in r.text and "titan_" not in r.text


@pytest.mark.integration
def test_metrics_serves_with_the_right_token(jwt_keys, monkeypatch):  # noqa: ARG001
    monkeypatch.setenv("TITAN_METRICS_TOKEN", _TOKEN)
    r = _client().get("/metrics", headers={"Authorization": f"Bearer {_TOKEN}"})
    assert r.status_code == 200
    assert "python_" in r.text or "titan_" in r.text


@pytest.mark.integration
def test_metrics_subpaths_need_the_token_too(jwt_keys, monkeypatch):  # noqa: ARG001
    monkeypatch.setenv("TITAN_METRICS_TOKEN", _TOKEN)
    r = _client().get("/metrics/")
    assert r.status_code == 401


@pytest.mark.integration
def test_metrics_subpaths_are_closed_without_a_configured_token(jwt_keys, monkeypatch):  # noqa: ARG001
    monkeypatch.delenv("TITAN_METRICS_TOKEN", raising=False)
    assert _client().get("/metrics/").status_code == 404


@pytest.mark.integration
def test_metrics_refuses_a_non_ascii_token_without_an_error(jwt_keys, monkeypatch):  # noqa: ARG001
    monkeypatch.setenv("TITAN_METRICS_TOKEN", _TOKEN)
    r = _client().get("/metrics", headers={"Authorization": "Bearer \u00e9".encode("latin-1")})
    assert r.status_code == 401


@pytest.mark.unit
def test_compose_publishes_every_port_on_localhost_only():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    published = [
        (name, str(port))
        for name, service in compose["services"].items()
        for port in service.get("ports", [])
    ]
    assert published, "the API port is expected to be published"
    for name, port in published:
        assert port.startswith("127.0.0.1:"), f"{name} publishes {port} on every interface"
