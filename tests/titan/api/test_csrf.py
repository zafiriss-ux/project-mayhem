"""T5-112 CSRF double-submit middleware tests."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore, hash_password
from titan.api.main import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, create_app


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

    app = create_app(auth_store=store)
    return TestClient(app, base_url="https://testserver")


@pytest.mark.integration
def test_get_requests_pass_without_csrf(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


@pytest.mark.integration
def test_post_without_csrf_returns_403(client: TestClient) -> None:
    response = client.post("/auth/refresh")
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing or invalid"


@pytest.mark.integration
def test_post_with_valid_csrf_passes_middleware(client: TestClient) -> None:
    csrf_response = client.get("/api/csrf-token")
    assert csrf_response.status_code == 200
    token = csrf_response.json()["csrf_token"]

    response = client.post(
        "/auth/refresh",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    )
    # Middleware passes; downstream may return 401 (no refresh cookie) but not 403 for CSRF
    assert response.status_code != 403


@pytest.mark.integration
def test_post_with_mismatched_csrf_returns_403(client: TestClient) -> None:
    response = client.post(
        "/auth/refresh",
        cookies={CSRF_COOKIE_NAME: "abc"},
        headers={CSRF_HEADER_NAME: "xyz"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing or invalid"


@pytest.mark.integration
def test_login_endpoint_exempt_from_csrf(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "nobody", "password": "wrong"},
    )
    # Not blocked by CSRF (login is bootstrap — exempt); may return 401 for bad creds
    assert response.status_code != 403


def test_csrf_cookie_is_httponly(client: TestClient) -> None:
    """RBP-05: page scripts cannot read the cookie; clients use the body copy."""
    response = client.get("/api/csrf-token")

    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{CSRF_COOKIE_NAME}=")
    assert "httponly" in set_cookie
    assert response.json()["csrf_token"] == client.cookies.get(CSRF_COOKIE_NAME)
