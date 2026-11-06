"""T5-11 auth layer tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
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

REPO_ROOT = Path(__file__).resolve().parents[3]


def _csrf_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/csrf-token")
    return {CSRF_HEADER_NAME: r.json()["csrf_token"]}


@pytest.fixture
def jwt_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh synthetic RS256 key pair in the environment."""
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
def client(jwt_keys: None) -> TestClient:
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
    assert (REPO_ROOT / "docs/titan.service").exists()


# ── #1392 (AUTH-NEW-01): one refresh token is used once, also at the same moment ──

def _two_refreshes_at_once(client: TestClient) -> tuple[list[int], int]:
    """Two refreshes with the same token, held together after both passed the active check.

    Returns the two status codes and how many refresh tokens of the user are active.
    """
    import threading

    login = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert login.status_code == 200
    store = client.app.state.auth_store
    real_check = store.is_refresh_token_active
    barrier = threading.Barrier(2, timeout=10)

    def _check_then_wait(jti: str) -> bool:
        active = real_check(jti)
        barrier.wait()  # both requests have read "active" before either uses the token
        return active

    headers = _csrf_headers(client)
    cookies = dict(client.cookies)
    statuses: list[int] = []

    def _refresh() -> None:
        with TestClient(client.app, base_url="https://testserver", cookies=cookies) as other:
            statuses.append(other.post("/auth/refresh", headers=headers).status_code)

    store.is_refresh_token_active = _check_then_wait
    try:
        threads = [threading.Thread(target=_refresh, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)
    finally:
        store.is_refresh_token_active = real_check
    now_iso = datetime.now(UTC).isoformat()
    return sorted(statuses), len(store._db.get_active_auth_tokens_for_user("coach-1", now_iso))


@pytest.mark.integration
def test_1392_two_refreshes_with_one_token_at_once_give_one_session(client: TestClient) -> None:
    statuses, active = _two_refreshes_at_once(client)

    assert statuses == [200, 401]
    # #1494: the second use revokes every refresh token of the user, also the one the first
    # use was just given, so neither holder keeps a session.
    assert active == 0


@pytest.mark.integration
def test_1392_a_token_is_consumed_once_at_the_database() -> None:
    store = AuthStore()
    store.upsert_user(user_id="u1", username="u", password_hash="x", role="COACH", athlete_id=None)
    now = datetime.now(UTC)
    store.add_refresh_token("jti-1", "u1", now + timedelta(days=1), now)

    def _rotate(jti: str) -> str:
        new_token = (str(uuid.uuid4()), now.isoformat(), (now + timedelta(days=1)).isoformat())
        return store._db.rotate_auth_token(jti, "u1", new_token, now.isoformat(), 3)

    assert _rotate("jti-1") == "rotated"
    assert _rotate("jti-1") == "reused"
    assert _rotate("ghost") == "refused"
    assert store.is_refresh_token_active("jti-1") is False
    # A token past its expiry is never consumed, whatever the earlier check said.
    store.add_refresh_token("jti-old", "u1", now - timedelta(seconds=1), now - timedelta(days=1))
    assert _rotate("jti-old") == "refused"


# ── #1494 (AUTH-NEW-02): a reused refresh token revokes every refresh token of the user ──

def _login_cookie(client: TestClient, username: str, password: str) -> str:
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200
    token = client.cookies.get(REFRESH_COOKIE_NAME)
    assert token is not None
    return token


def _refresh_response(client: TestClient, token: str):  # noqa: ANN202
    """One refresh with *token* from a fresh browser (only that cookie and a CSRF token)."""
    with TestClient(client.app, base_url="https://testserver") as browser:
        headers = _csrf_headers(browser)
        browser.cookies.set(REFRESH_COOKIE_NAME, token)
        return browser.post("/auth/refresh", headers=headers)


def _refresh_with(client: TestClient, token: str) -> int:
    return _refresh_response(client, token).status_code


def _reuse(client: TestClient, token: str) -> int:
    """Use *token* a second time, after the refresh that used it (#1503: no race needed)."""
    return _refresh_with(client, token)


@pytest.mark.integration
def test_1494_a_reused_token_ends_every_session_of_the_user(client: TestClient) -> None:
    phone = _login_cookie(client, "coach", "coach-pass")
    laptop = _login_cookie(client, "coach", "coach-pass")
    other_user = _login_cookie(client, "athlete", "athlete-pass")
    first = _refresh_response(client, phone)
    assert first.status_code == 200
    rotated = first.cookies.get(REFRESH_COOKIE_NAME)
    assert rotated is not None

    assert _reuse(client, phone) == 401

    assert _refresh_with(client, rotated) == 401  # the session the first use was given
    assert _refresh_with(client, laptop) == 401  # every other session of the same user
    assert _refresh_with(client, other_user) == 200  # another user is not touched


@pytest.mark.integration
def test_1494_the_reuse_log_names_the_account_and_a_jti_prefix_only(
    client: TestClient, caplog: pytest.LogCaptureFixture,
) -> None:
    import json

    from titan.api.auth import decode_token

    token = _login_cookie(client, "coach", "coach-pass")
    jti = decode_token(token, expected_type="refresh").jti
    assert _refresh_with(client, token) == 200

    with caplog.at_level("INFO", logger="titan.api"):
        assert _reuse(client, token) == 401

    (line,) = [
        json.loads(r.getMessage()) for r in caplog.records
        if "REFRESH_TOKEN_REUSED" in r.getMessage()
    ]
    assert line["sub"] == "coach-1"
    assert line["jti_prefix"] == jti[:8]
    assert line["all_refresh_tokens_revoked"] is True
    text = json.dumps(line)
    assert jti not in text and token not in text


@pytest.mark.integration
def test_1494_a_failed_revoke_still_refuses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    token = _login_cookie(client, "coach", "coach-pass")
    assert _refresh_with(client, token) == 200
    store = client.app.state.auth_store

    def _broken(*args: object, **kwargs: object) -> str:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(store._db, "rotate_auth_token", _broken)
    with caplog.at_level("INFO", logger="titan.api"):
        response = _refresh_response(client, token)

    assert response.status_code == 401
    assert REFRESH_COOKIE_NAME not in response.cookies
    assert any("REFRESH_ROTATION_FAILED" in r.getMessage() for r in caplog.records)


@pytest.mark.integration
@pytest.mark.usefixtures("jwt_keys")
def test_1494_the_store_revokes_only_that_users_tokens() -> None:
    store = AuthStore()
    for user_id in ("u1", "u2"):
        store.upsert_user(user_id=user_id, username=user_id, password_hash="x", role="COACH", athlete_id=None)
    now = datetime.now(UTC)
    for jti, user_id in (("a", "u1"), ("b", "u1"), ("c", "u2")):
        store.add_refresh_token(jti, user_id, now + timedelta(days=1), now)
    user = AuthUser(id="u1", username="u1", role="COACH", athlete_id=None)
    assert store.rotate_refresh_token("a", user).token is not None

    assert store.rotate_refresh_token("a", user) == (None, True)

    assert store.is_refresh_token_active("b") is False
    assert store.is_refresh_token_active("c") is True


# ── #1503 (AUTH-NEW-03): a used refresh token replayed later, and across API processes ──

@pytest.mark.integration
def test_1503_a_stolen_token_replayed_later_ends_every_session(
    client: TestClient, caplog: pytest.LogCaptureFixture,
) -> None:
    stolen = _login_cookie(client, "coach", "coach-pass")
    laptop = _login_cookie(client, "coach", "coach-pass")
    attacker = _refresh_response(client, stolen)  # the thief uses the token first
    assert attacker.status_code == 200
    attacker_token = attacker.cookies.get(REFRESH_COOKIE_NAME)
    assert attacker_token is not None

    with caplog.at_level("INFO", logger="titan.api"):
        assert _refresh_with(client, stolen) == 401  # the owner's browser sends it later

    assert any("REFRESH_TOKEN_REUSED" in r.getMessage() for r in caplog.records)
    assert _refresh_with(client, attacker_token) == 401  # the thief's session ends
    assert _refresh_with(client, laptop) == 401


@pytest.mark.integration
def test_1503_a_logged_out_token_replayed_is_only_refused(
    client: TestClient, caplog: pytest.LogCaptureFixture,
) -> None:
    phone = _login_cookie(client, "coach", "coach-pass")
    laptop = _login_cookie(client, "coach", "coach-pass")
    assert _logout_with(client, phone).status_code == 200

    with caplog.at_level("INFO", logger="titan.api"):
        assert _refresh_with(client, phone) == 401

    assert not any("REFRESH_TOKEN_REUSED" in r.getMessage() for r in caplog.records)
    assert _refresh_with(client, laptop) == 200  # an old tab after logout ends no other session


@pytest.mark.integration
def test_1503_a_token_dropped_by_the_three_token_limit_is_only_refused(client: TestClient) -> None:
    oldest = _login_cookie(client, "coach", "coach-pass")
    newer = [_login_cookie(client, "coach", "coach-pass") for _ in range(3)]  # oldest is revoked

    assert _refresh_with(client, oldest) == 401
    assert _refresh_with(client, newer[-1]) == 200


@pytest.mark.integration
def test_1503_a_logout_with_a_used_token_does_not_hide_its_replay(client: TestClient) -> None:
    stolen = _login_cookie(client, "coach", "coach-pass")
    attacker = _refresh_response(client, stolen)
    assert attacker.status_code == 200
    attacker_token = attacker.cookies.get(REFRESH_COOKIE_NAME)
    assert _logout_with(client, stolen).status_code == 200  # thief tries to hide it

    assert _refresh_with(client, stolen) == 401
    assert _refresh_with(client, attacker_token) == 401


def _logout_with(client: TestClient, token: str):  # noqa: ANN202
    with TestClient(client.app, base_url="https://testserver") as browser:
        headers = _csrf_headers(browser)
        browser.cookies.set(REFRESH_COOKIE_NAME, token)
        return browser.post("/auth/logout", headers=headers)


@pytest.mark.integration
def test_1503_the_victims_logout_with_a_used_token_ends_the_thiefs_session(
    client: TestClient, caplog: pytest.LogCaptureFixture,
) -> None:
    stolen = _login_cookie(client, "coach", "coach-pass")
    attacker = _refresh_response(client, stolen)
    assert attacker.status_code == 200
    attacker_token = attacker.cookies.get(REFRESH_COOKIE_NAME)

    with caplog.at_level("INFO", logger="titan.api"):
        assert _logout_with(client, stolen).status_code == 200  # the victim never refreshes again

    assert any("REFRESH_TOKEN_REUSED" in r.getMessage() for r in caplog.records)
    assert _refresh_with(client, attacker_token) == 401


@pytest.mark.integration
def test_1503_a_failed_revoke_at_logout_still_logs_out(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    stolen = _login_cookie(client, "coach", "coach-pass")
    assert _refresh_with(client, stolen) == 200
    store = client.app.state.auth_store

    def _broken(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(store._db, "revoke_auth_tokens_if_used", _broken)
    with caplog.at_level("INFO", logger="titan.api"):
        response = _logout_with(client, stolen)

    assert response.status_code == 200
    assert any("LOGOUT_REPLAY_REVOKE_FAILED" in r.getMessage() for r in caplog.records)


@pytest.mark.integration
def test_1503_another_users_token_id_is_refused_and_changes_nothing() -> None:
    store = AuthStore()
    for user_id in ("u1", "u2"):
        store.upsert_user(user_id=user_id, username=user_id, password_hash="x", role="COACH", athlete_id=None)
    now = datetime.now(UTC)
    store.add_refresh_token("u2-token", "u2", now + timedelta(days=1), now)
    new_token = ("next", now.isoformat(), (now + timedelta(days=1)).isoformat())

    assert store._db.rotate_auth_token("u2-token", "u1", new_token, now.isoformat(), 3) == "refused"
    assert store.is_refresh_token_active("u2-token") is True
    assert store._db.get_auth_token("next") is None


@pytest.mark.integration
@pytest.mark.usefixtures("jwt_keys")
def test_1503_two_api_processes_cannot_leave_the_new_token_active(tmp_path: Path) -> None:
    """Process A uses a token; process B replays it while A has not yet stored the next one.

    Two ``DatabaseManager`` objects on one file stand for two API processes: they share no
    Python lock, only the database. B must not finish its replay check between A's use of the
    token and A's new token, or the new token survives the revoke.
    """
    import sqlite3
    import threading

    from titan.core.database import DatabaseManager

    db_a = DatabaseManager(db_dir=tmp_path)
    db_b = DatabaseManager(db_dir=tmp_path)
    try:
        store_a, store_b = AuthStore(db=db_a), AuthStore(db=db_b)
        store_a.upsert_user(user_id="u1", username="u1", password_hash="x", role="COACH", athlete_id=None)
        user = AuthUser(id="u1", username="u1", role="COACH", athlete_id=None)
        now = datetime.now(UTC)
        store_a.add_refresh_token("stolen", "u1", now + timedelta(days=1), now)
        replay = threading.Thread(target=store_b.rotate_refresh_token, args=("stolen", user), daemon=True)

        def _pause_before_new_token(action: int, arg1: str | None, *_: object) -> int:
            if action == sqlite3.SQLITE_INSERT and arg1 == "auth_tokens" and replay.ident is None:
                replay.start()
                replay.join(timeout=1.0)  # B runs now unless A holds the database write lock
            return sqlite3.SQLITE_OK

        db_a.conn.set_authorizer(_pause_before_new_token)
        try:
            store_a.rotate_refresh_token("stolen", user)
        finally:
            db_a.conn.set_authorizer(None)
        assert replay.ident is not None  # the pause ran
        replay.join(timeout=10)
        assert not replay.is_alive()

        active = db_b.get_active_auth_tokens_for_user("u1", datetime.now(UTC).isoformat())
        assert active == []
    finally:
        db_a.close()
        db_b.close()
