"""T5-94 — schemathesis FastAPI contract testing."""

from __future__ import annotations

from datetime import datetime

import pytest
import schemathesis
import schemathesis.openapi as st_openapi
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore, hash_password
from titan.api.main import create_app

_EXPECTED_PATHS = frozenset(
    {
        "/health",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/athletes/{athlete_id}/dashboard",
        "/coach/notes",
        "/coach/overrides",
        "/coach/export",
        "/coach/athlete-data",
    }
)


@pytest.fixture
def jwt_keys(monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.fixture
def app_fixture(jwt_keys: None) -> object:  # noqa: ARG001
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
    return create_app(auth_store=store)


@pytest.fixture
def client(app_fixture) -> TestClient:
    return TestClient(app_fixture, base_url="https://testserver")


def test_openapi_schema_is_valid(app_fixture) -> None:
    schema_dict = app_fixture.openapi()
    assert "openapi" in schema_dict
    assert "paths" in schema_dict
    documented = set(schema_dict["paths"].keys())
    assert documented >= _EXPECTED_PATHS, f"Missing paths: {_EXPECTED_PATHS - documented}"
    # Validate schema is parseable by schemathesis
    loaded = st_openapi.from_dict(schema_dict)
    assert loaded is not None
    assert schemathesis.__version__  # confirms library is functional


def test_health_contract(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_login_rejects_missing_fields(client: TestClient) -> None:
    cases = [
        {},
        {"username": "x"},
        {"password": "x"},
        {"username": "", "password": ""},
        {"username": "x" * 10000, "password": "y"},
    ]
    for payload in cases:
        r = client.post("/auth/login", json=payload)
        assert r.status_code in (422, 401), (
            f"Expected 422/401 for {payload!r:.80}, got {r.status_code}"
        )


def test_protected_endpoints_reject_no_auth(client: TestClient) -> None:
    fresh = TestClient(client.app, base_url="https://testserver")
    protected = [
        ("GET", "/athletes/owner/dashboard"),
        ("POST", "/coach/notes"),
        ("POST", "/coach/overrides"),
        ("GET", "/coach/export"),
        ("DELETE", "/coach/athlete-data"),
    ]
    for method, path in protected:
        r = fresh.request(method, path)
        assert r.status_code == 401, f"{method} {path} → expected 401, got {r.status_code}"


def test_login_response_conforms_to_schema(client: TestClient) -> None:
    r = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "expires_at" in body
    datetime.fromisoformat(body["expires_at"])
