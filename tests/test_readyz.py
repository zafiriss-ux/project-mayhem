"""Tier 1 pytest tests for /readyz endpoint — no Docker, no live services.

ADR-0057 operational baseline: DB liveness probe, schema version check,
titan_core.db name enforcement.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient


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
def test_readyz_returns_200_when_healthy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _generate_jwt_env(monkeypatch)
    from titan.api.main import create_app
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    client = TestClient(create_app(db=db), base_url="https://testserver")
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["checks"]["db_reachable"] is True
    assert body["checks"]["db_file"] is True


@pytest.mark.integration
def test_readyz_returns_503_when_db_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _generate_jwt_env(monkeypatch)
    from titan.api.main import create_app

    broken_conn = MagicMock()
    broken_conn.execute.side_effect = RuntimeError("simulated DB failure")
    mock_db = SimpleNamespace(
        db_path=Path("/data/titan_core.db"),
        conn=broken_conn,
    )
    client = TestClient(create_app(db=mock_db), base_url="https://testserver")
    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False


@pytest.mark.integration
def test_health_and_readyz_both_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    _generate_jwt_env(monkeypatch)
    from titan.api.main import create_app

    client = TestClient(create_app(), base_url="https://testserver")
    assert client.get("/health").status_code == 200
    assert client.get("/readyz").status_code in (200, 503)


@pytest.mark.unit
def test_titan_core_db_name_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    _generate_jwt_env(monkeypatch)
    from titan.api.main import create_app

    stale_db = SimpleNamespace(db_path=Path("/data/titan.db"))
    with pytest.raises(RuntimeError, match="Must use titan_core.db"):
        create_app(db=stale_db)


@pytest.mark.integration
def test_readyz_does_not_expose_exception_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """CodeQL py/stack-trace-exposure (#24): /readyz is public, so only the class name."""
    _generate_jwt_env(monkeypatch)
    from titan.api.main import create_app

    class _BrokenDB:
        db_path = Path("/data/titan_core.db")

        def is_db_reachable(self) -> bool:
            raise RuntimeError("secret path /srv/private/titan_core.db")

    client = TestClient(create_app(db=_BrokenDB()), base_url="https://testserver")
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["db_error"] == "RuntimeError"
    assert "/srv/private" not in response.text
