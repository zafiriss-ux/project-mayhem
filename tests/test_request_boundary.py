"""AGENTS §8.11 RBP-01: request bodies above the limit get HTTP 413 before parsing."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore, hash_password
from titan.api.main import BodySizeLimitMiddleware, create_app
from titan.config.settings import get_settings


@pytest.fixture
def rsa_keys(monkeypatch: pytest.MonkeyPatch) -> None:
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
def small_limit(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    monkeypatch.setenv("API_MAX_BODY_SIZE_BYTES", "1024")
    get_settings.cache_clear()
    yield 1024
    get_settings.cache_clear()


@pytest.fixture
def client(rsa_keys: None) -> TestClient:
    store = AuthStore()
    store.upsert_user(
        user_id="athlete-1",
        username="athlete",
        password_hash=hash_password("pw"),
        role="ATHLETE",
        athlete_id="owner",
    )
    return TestClient(create_app(auth_store=store), base_url="https://testserver")


def test_default_limit_is_one_mebibyte() -> None:
    get_settings.cache_clear()
    assert get_settings().API_MAX_BODY_SIZE_BYTES == 1_048_576


def test_declared_oversized_body_gets_413_before_the_route(client: TestClient) -> None:
    password = "x" * (2 * 1024 * 1024)
    resp = client.post("/auth/login", json={"username": "athlete", "password": password})

    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large"}
    assert resp.headers.get("x-content-type-options") == "nosniff"


def test_chunked_body_over_the_limit_gets_413(small_limit: int, rsa_keys: None) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"username": "athlete", "password": "'
        for _ in range(8):
            yield b"x" * 512
        yield b'"}'

    c = TestClient(create_app(auth_store=AuthStore()), base_url="https://testserver")
    resp = c.post(
            "/auth/login",
        content=chunks(),
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large"}


def test_body_within_the_limit_reaches_the_route(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"username": "athlete", "password": "wrong"})
    assert resp.status_code == 401

    resp = client.post("/auth/login", json={"username": "athlete", "password": "pw"})
    assert resp.status_code == 200


def _run_raw(middleware: BodySizeLimitMiddleware, headers: list[tuple[bytes, bytes]]) -> list[dict]:
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/x", "headers": headers}
    asyncio.run(middleware(scope, receive, send))
    return sent


def test_non_numeric_content_length_gets_400_and_never_reaches_the_app() -> None:
    reached = []

    async def app(scope, receive, send) -> None:  # noqa: ANN001
        reached.append(scope)

    sent = _run_raw(BodySizeLimitMiddleware(app, max_bytes=10), [(b"content-length", b"-1")])

    assert reached == []
    assert sent[0]["status"] == 400


def test_declared_length_over_the_limit_never_reaches_the_app() -> None:
    reached = []

    async def app(scope, receive, send) -> None:  # noqa: ANN001
        reached.append(scope)

    sent = _run_raw(BodySizeLimitMiddleware(app, max_bytes=10), [(b"content-length", b"11")])

    assert reached == []
    assert sent[0]["status"] == 413
