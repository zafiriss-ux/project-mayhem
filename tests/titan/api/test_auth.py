"""T5-11 auth layer tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    AuthError,
    AuthStore,
    create_access_token,
    hash_password,
    validate_jwt_keys_at_startup,
)
from titan.api.main import CSRF_HEADER_NAME, create_app
from titan.api.models import AuthUser


def _csrf_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/csrf-token")
    return {CSRF_HEADER_NAME: r.json()["csrf_token"]}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", public_pem)

    store = AuthStore()
    store.upsert_user(
        user_id="coach-1",
        username="coach",
        password_hash=hash_password("coach-pass"),
        role="COACH",
        athlete_id=None,
    )
    store.upsert_user(
        user_id="athlete-1",
        username="athlete",
        password_hash=hash_password("athlete-pass"),
        role="ATHLETE",
        athlete_id="athlete-1",
    )

    app = create_app(auth_store=store)
    db = MagicMock()
    db.get_assigned_athletes.return_value = ["athlete-1", "athlete-2"]
    app.state.db = db
    return TestClient(app, base_url="https://testserver")


@pytest.mark.integration
def test_happy_path_login_and_authenticated_access(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert login.status_code == 200

    dashboard = client.get("/athletes/athlete-2/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["athlete_id"] == "athlete-2"


@pytest.mark.integration
def test_token_expiry_rejects_expired_access_token(client: TestClient) -> None:
    user = AuthUser(id="athlete-1", username="athlete", role="ATHLETE", athlete_id="athlete-1")
    expired_token, _ = create_access_token(user, now=datetime.now(UTC) - timedelta(minutes=20))
    client.cookies.set(ACCESS_COOKIE_NAME, expired_token)

    response = client.get("/athletes/athlete-1/dashboard")
    assert response.status_code == 401


@pytest.mark.integration
def test_role_violation_blocks_athlete_from_coach_endpoint(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "athlete", "password": "athlete-pass"})
    assert login.status_code == 200

    response = client.post("/coach/notes", json={"text": "note"})
    assert response.status_code == 403


@pytest.mark.integration
def test_isolation_violation_blocks_athlete_cross_access(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "athlete", "password": "athlete-pass"})
    assert login.status_code == 200

    response = client.get("/athletes/athlete-2/dashboard")
    assert response.status_code == 403


@pytest.mark.integration
def test_refresh_token_rotation_invalidates_old_token(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert login.status_code == 200
    old_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert old_refresh is not None

    refreshed = client.post("/auth/refresh", headers=_csrf_headers(client))
    assert refreshed.status_code == 200

    client.cookies.set(REFRESH_COOKIE_NAME, old_refresh)
    replay = client.post("/auth/refresh", headers=_csrf_headers(client))
    assert replay.status_code == 401


@pytest.mark.integration
def test_health_endpoint_remains_public(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/health")
    assert response.status_code == 200


@pytest.mark.integration
def test_non_health_endpoint_rejects_unauthenticated_access(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/athletes/athlete-1/dashboard")
    assert response.status_code == 401


@pytest.mark.integration
def test_coach_rate_limit_enforced_with_429(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert login.status_code == 200

    for _ in range(100):
        response = client.get("/athletes/athlete-2/dashboard")
        assert response.status_code == 200

    limited = client.get("/athletes/athlete-2/dashboard")
    assert limited.status_code == 429


@pytest.mark.integration
def test_athlete_rate_limit_enforced_with_429(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "athlete", "password": "athlete-pass"})
    assert login.status_code == 200

    for _ in range(30):
        response = client.get("/athletes/athlete-1/dashboard")
        assert response.status_code == 200

    limited = client.get("/athletes/athlete-1/dashboard")
    assert limited.status_code == 429


@pytest.mark.integration
def test_rate_limit_keyed_to_authenticated_identity_not_only_path(client: TestClient) -> None:
    client.app.state.auth_store.upsert_user(
        user_id="coach-2",
        username="coach2",
        password_hash=hash_password("coach2-pass"),
        role="COACH",
        athlete_id=None,
    )

    login = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert login.status_code == 200
    for _ in range(100):
        response = client.get("/athletes/athlete-2/dashboard")
        assert response.status_code == 200

    first_user_limited = client.get("/athletes/athlete-2/dashboard")
    assert first_user_limited.status_code == 429

    second_login = client.post("/auth/login", json={"username": "coach2", "password": "coach2-pass"})
    assert second_login.status_code == 200
    second_user_response = client.get("/athletes/athlete-2/dashboard")
    assert second_user_response.status_code == 200


@pytest.mark.integration
def test_health_endpoint_remains_public_after_rate_limit_exceeded(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "athlete", "password": "athlete-pass"})
    assert login.status_code == 200

    for _ in range(30):
        response = client.get("/athletes/athlete-1/dashboard")
        assert response.status_code == 200

    limited = client.get("/athletes/athlete-1/dashboard")
    assert limited.status_code == 429

    client.cookies.clear()
    health = client.get("/health")
    assert health.status_code == 200


# ── T5-102: validate_jwt_keys_at_startup ──────────────────────────────────────

@pytest.mark.integration
def test_validate_jwt_keys_at_startup_passes_when_both_keys_set(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", public_pem)
    validate_jwt_keys_at_startup()  # must not raise


@pytest.mark.integration
def test_validate_jwt_keys_at_startup_raises_on_missing_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TITAN_JWT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("TITAN_JWT_PUBLIC_KEY", raising=False)
    with pytest.raises(AuthError, match="TITAN_JWT_PRIVATE_KEY missing or invalid"):
        validate_jwt_keys_at_startup()


@pytest.mark.integration
def test_validate_jwt_keys_at_startup_raises_on_missing_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("TITAN_JWT_PUBLIC_KEY", raising=False)
    with pytest.raises(AuthError, match="TITAN_JWT_PUBLIC_KEY missing or invalid"):
        validate_jwt_keys_at_startup()


# ── P15-SEC8: /auth/refresh rate limit ────────────────────────────────────────

@pytest.mark.integration
def test_refresh_rate_limit_blocks_after_5(client: TestClient) -> None:
    headers = _csrf_headers(client)
    for _ in range(5):
        client.post("/auth/refresh", headers=headers)
    response = client.post("/auth/refresh", headers=headers)
    assert response.status_code == 429
    assert "Too many refresh attempts" in response.json()["detail"]


# ── P15-OPS1: systemd unit file ───────────────────────────────────────────────

@pytest.mark.integration
def test_systemd_unit_exists() -> None:
    from pathlib import Path
    assert Path("docs/titan.service").exists()
