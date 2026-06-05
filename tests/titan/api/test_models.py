"""Mirrored test for titan/api/models.py — T5-79."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from titan.api.models import AuthUser, LoginRequest, LoginResponse, TokenPayload


@pytest.mark.integration
def test_module_imports_without_error() -> None:
    import titan.api.models  # noqa: F401


@pytest.mark.integration
def test_auth_user_instantiation_defaults() -> None:
    user = AuthUser(id="u1", username="alice", role="ATHLETE", athlete_id="alice")
    assert user.is_active is True
    assert user.role == "ATHLETE"


@pytest.mark.integration
def test_token_payload_athlete_id_defaults_none() -> None:
    payload = TokenPayload(
        sub="u1", role="ATHLETE", exp=9999999999, token_type="access", jti="jti-1"
    )
    assert payload.athlete_id is None


@pytest.mark.integration
def test_login_request_instantiation() -> None:
    req = LoginRequest(username="alice", password="secret")
    assert req.username == "alice"


@pytest.mark.integration
def test_login_response_token_type_defaults_bearer() -> None:
    resp = LoginResponse(access_token="tok", expires_at=datetime(2030, 1, 1, tzinfo=UTC))
    assert resp.token_type == "bearer"
