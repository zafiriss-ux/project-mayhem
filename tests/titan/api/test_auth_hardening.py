"""C-W09 auth hardening tests: account lockout + pre-auth login rate limiting."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import (
    LOCKOUT_DURATION_SECONDS,
    LOCKOUT_MAX_ATTEMPTS,
    LOCKOUT_WINDOW_SECONDS,
    AuthStore,
    hash_password,
)
from titan.api.main import LoginRateLimiter, create_app


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
def store() -> AuthStore:
    s = AuthStore()
    s.upsert_user(
        user_id="coach-1",
        username="coach",
        password_hash=hash_password("coach-pass"),
        role="COACH",
        athlete_id=None,
    )
    return s


@pytest.fixture
def client(rsa_keys: None, store: AuthStore) -> TestClient:
    app = create_app(auth_store=store)
    return TestClient(app, base_url="https://testserver")


# ---------------------------------------------------------------------------
# Account lockout tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_lockout_after_max_failed_attempts(client: TestClient) -> None:
    for _ in range(LOCKOUT_MAX_ATTEMPTS):
        r = client.post("/auth/login", json={"username": "coach", "password": "wrong"})
        assert r.status_code == 401

    locked = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert locked.status_code == 401
    assert "access_token" not in locked.json()


@pytest.mark.integration
def test_lockout_clears_on_successful_login(client: TestClient, store: AuthStore) -> None:
    for _ in range(LOCKOUT_MAX_ATTEMPTS - 1):
        client.post("/auth/login", json={"username": "coach", "password": "wrong"})

    ok = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert ok.status_code == 200

    assert not store.is_locked_out("coach")
    # One more failed attempt after clearing should not immediately lock
    r = client.post("/auth/login", json={"username": "coach", "password": "wrong"})
    assert r.status_code == 401
    assert not store.is_locked_out("coach")


@pytest.mark.integration
def test_lockout_expires_after_duration(store: AuthStore) -> None:
    base = 1_000_000.0

    with patch("time.time", return_value=base):
        for _ in range(LOCKOUT_MAX_ATTEMPTS):
            store.record_failed_attempt("coach")
        assert store.is_locked_out("coach")

    with patch("time.time", return_value=base + LOCKOUT_DURATION_SECONDS + 1.0):
        assert not store.is_locked_out("coach")


@pytest.mark.integration
def test_failed_attempts_outside_window_dont_count(store: AuthStore) -> None:
    # TD-SEC-02: lockout is now counter-based (SQLite) rather than sliding-window.
    # N-1 attempts must not lock; the Nth attempt must trigger lockout regardless of timing.
    for _ in range(LOCKOUT_MAX_ATTEMPTS - 1):
        store.record_failed_attempt("coach")
    assert not store.is_locked_out("coach")

    store.record_failed_attempt("coach")
    assert store.is_locked_out("coach")


@pytest.mark.integration
def test_locked_account_answers_like_a_wrong_password(client: TestClient, store: AuthStore) -> None:
    """RBP-05: no 423-vs-401 oracle; the lockout still refuses the right password."""
    wrong = client.post("/auth/login", json={"username": "coach", "password": "wrong"})
    unknown = client.post("/auth/login", json={"username": "nobody", "password": "wrong"})
    for _ in range(LOCKOUT_MAX_ATTEMPTS - 1):
        client.post("/auth/login", json={"username": "coach", "password": "wrong"})
    assert store.is_locked_out("coach")

    locked = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})

    assert locked.status_code == wrong.status_code == unknown.status_code == 401
    assert locked.json() == wrong.json() == unknown.json() == {"detail": "Invalid credentials"}
    assert "set-cookie" not in locked.headers


@pytest.mark.integration
def test_a_disabled_account_answers_like_a_wrong_password(client: TestClient, store: AuthStore) -> None:
    """SP-02: the right password of a disabled account gives no token and counts as a failure."""
    store.upsert_user(
        user_id="coach-2", username="gone", password_hash=hash_password("gone-pass"),
        role="COACH", athlete_id=None, is_active=False,
    )
    wrong = client.post("/auth/login", json={"username": "gone", "password": "wrong"})
    for _ in range(LOCKOUT_MAX_ATTEMPTS - 2):
        client.post("/auth/login", json={"username": "gone", "password": "wrong"})

    disabled = client.post("/auth/login", json={"username": "gone", "password": "gone-pass"})

    assert disabled.status_code == wrong.status_code == 401
    assert disabled.json() == wrong.json() == {"detail": "Invalid credentials"}
    assert "set-cookie" not in disabled.headers
    assert store.is_locked_out("gone")  # counted, not cleared


@pytest.mark.integration
def test_successful_login_after_lockout_expiry(store: AuthStore, rsa_keys: None) -> None:
    base = 1_000_000.0

    with patch("time.time", return_value=base):
        for _ in range(LOCKOUT_MAX_ATTEMPTS):
            store.record_failed_attempt("coach")
        assert store.is_locked_out("coach")

    with patch("time.time", return_value=base + LOCKOUT_DURATION_SECONDS + 1.0):
        assert not store.is_locked_out("coach")

    app = create_app(auth_store=store)
    c = TestClient(app, base_url="https://testserver")
    r = c.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# IP rate limiter tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ip_rate_limit_blocks_after_threshold(client: TestClient) -> None:
    # Use a unique username per attempt to avoid triggering account lockout
    # (LOCKOUT_MAX_ATTEMPTS=5 < LOGIN_RATE_LIMIT_ATTEMPTS=10).
    limit = LoginRateLimiter.LOGIN_RATE_LIMIT_ATTEMPTS
    for i in range(limit):
        r = client.post("/auth/login", json={"username": f"user-{i}", "password": "x"})
        assert r.status_code == 401

    blocked = client.post("/auth/login", json={"username": "user-extra", "password": "x"})
    assert blocked.status_code == 429


@pytest.mark.integration
def test_ip_rate_limit_different_ips_independent() -> None:
    # TestClient cannot set request.client.host via base_url; test the unit directly.
    limiter = LoginRateLimiter()
    limit = LoginRateLimiter.LOGIN_RATE_LIMIT_ATTEMPTS

    for _ in range(limit):
        assert limiter.is_allowed("1.2.3.4") is True
    assert limiter.is_allowed("1.2.3.4") is False

    # IP-B has its own independent bucket
    assert limiter.is_allowed("5.6.7.8") is True
