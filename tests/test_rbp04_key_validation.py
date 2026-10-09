"""RBP-04 (T-PRA-28): JWT key material is checked when the app is built.

A missing, malformed or mismatched key pair stops ``create_app()`` itself, so
the API never starts serving and fails only at the first login.
"""

import pytest

from tests.conftest import _rsa_pem_pair
from titan.api.auth import AuthError
from titan.api.main import create_app


@pytest.mark.unit
def test_create_app_accepts_a_valid_key_pair(jwt_keys):  # noqa: ARG001
    assert create_app() is not None


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["TITAN_JWT_PRIVATE_KEY", "TITAN_JWT_PUBLIC_KEY"])
def test_create_app_refuses_a_missing_key(jwt_keys, monkeypatch, missing):  # noqa: ARG001
    monkeypatch.delenv(missing)

    with pytest.raises(AuthError, match=f"{missing} missing or invalid"):
        create_app()


@pytest.mark.unit
def test_create_app_refuses_a_malformed_key(jwt_keys, monkeypatch):  # noqa: ARG001
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----")

    with pytest.raises(AuthError, match="not a valid RS256 key pair"):
        create_app()


@pytest.mark.unit
def test_create_app_refuses_keys_from_two_different_pairs(jwt_keys, monkeypatch):  # noqa: ARG001
    _other_private, other_public = _rsa_pem_pair()
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", other_public)

    with pytest.raises(AuthError, match="not a valid RS256 key pair"):
        create_app()


@pytest.mark.unit
def test_keys_written_on_one_line_by_generate_jwt_keys_work(monkeypatch):
    """scripts/generate_jwt_keys.sh stores each PEM on one .env line with a literal
    backslash-n, and Docker's env_file passes it through unescaped. The Docker smoke
    job showed those keys could not be parsed, so login could never work there."""
    private_pem, public_pem = _rsa_pem_pair()
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", private_pem.replace("\n", "\\n"))
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", public_pem.replace("\n", "\\n"))

    assert create_app() is not None
