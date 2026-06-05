"""
Security role boundary tests (Pass 3).

Verifies that JWT access tokens carry correct role and identity claims,
and that token-type mismatch is rejected with AuthError.

3 tests:
  R1 — COACH access token carries role="COACH" claim
  R2 — ATHLETE access token binds athlete_id in the JWT payload
  R3 — Access token decoded with expected_type="refresh" raises AuthError
"""

import pytest

pytest.importorskip(
    "cryptography", reason="Requires pyjwt[crypto]: pip install -r requirements.txt"
)

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from titan.api.auth import AuthError, create_access_token, decode_token
from titan.api.models import AuthUser

# ─── Module-level RSA key pair (generated once to keep the suite fast) ────────

_PRIVATE_KEY = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_PRIVATE_PEM: str = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
_PUBLIC_PEM: str = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


# ─── Fixture ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject the test RSA key pair into the environment for auth module reads."""
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", _PRIVATE_PEM)
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", _PUBLIC_PEM)


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestSecurityRoleBoundary:

    # R1 — COACH role claim
    @pytest.mark.unit
    def test_r1_coach_access_token_carries_coach_role(self, jwt_env: None) -> None:
        """Access token for COACH must decode to role='COACH' with no athlete_id binding."""
        user = AuthUser(
            id="u-coach-01",
            username="head_coach",
            role="COACH",
            athlete_id=None,
        )
        token, _ = create_access_token(user)
        payload = decode_token(token, expected_type="access")

        assert payload.role == "COACH"
        assert payload.athlete_id is None
        assert payload.token_type == "access"
        assert payload.sub == "u-coach-01"

    # R2 — ATHLETE role binds athlete_id
    @pytest.mark.unit
    def test_r2_athlete_access_token_binds_athlete_id(self, jwt_env: None) -> None:
        """Access token for ATHLETE must encode the athlete_id claim."""
        athlete_id = "ath-7b9c2f"
        user = AuthUser(
            id="u-ath-01",
            username="athlete1",
            role="ATHLETE",
            athlete_id=athlete_id,
        )
        token, _ = create_access_token(user)
        payload = decode_token(token, expected_type="access")

        assert payload.role == "ATHLETE"
        assert payload.athlete_id == athlete_id
        assert payload.sub == "u-ath-01"

    # R3 — Token-type mismatch raises AuthError
    @pytest.mark.unit
    def test_r3_access_token_decoded_as_refresh_raises_auth_error(
        self, jwt_env: None
    ) -> None:
        """Decoding an access token with expected_type='refresh' must raise AuthError."""
        user = AuthUser(
            id="u-test-01",
            username="testuser",
            role="COACH",
            athlete_id=None,
        )
        token, _ = create_access_token(user)

        with pytest.raises(AuthError):
            decode_token(token, expected_type="refresh")
