"""ADR-0057: Docker deployment fitness tests."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _generate_jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv(
        "TITAN_JWT_PRIVATE_KEY",
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode(),
    )
    monkeypatch.setenv(
        "TITAN_JWT_PUBLIC_KEY",
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode(),
    )


@pytest.mark.integration
def test_worker_lock_prevents_duplicate(tmp_path: pytest.TempPathFactory) -> None:
    import titan.worker as worker_mod

    lock_path = tmp_path / "worker.lock"
    with patch.object(worker_mod, "LOCK_FILE", lock_path):
        fh1 = worker_mod.acquire_worker_lock()
        assert fh1 is not None, "First lock acquisition should succeed"

        fh2 = worker_mod.acquire_worker_lock()
        assert fh2 is None, "Second acquisition while lock held should return None"

        fh1.close()

        fh3 = worker_mod.acquire_worker_lock()
        assert fh3 is not None, "Lock should be reacquirable after release"
        fh3.close()


@pytest.mark.integration
def test_health_endpoint_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    _generate_jwt_env(monkeypatch)
    from titan.api.main import create_app

    client = TestClient(create_app(), base_url="https://testserver")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.unit
def test_api_has_no_worker_write_imports() -> None:
    """CI fitness function: API namespace must not import worker write paths."""
    import titan.api.main  # noqa: F401

    forbidden = [
        "titan.worker.garmin_sync",
        "titan.worker.telegram",
        "titan.worker.morning_routine",
        "titan.worker.scheduler",
    ]
    for mod_name in forbidden:
        assert mod_name not in sys.modules, (
            f"API imported forbidden worker module: {mod_name}"
        )
