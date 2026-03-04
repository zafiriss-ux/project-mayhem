"""Privacy and safety tests for secret string handling."""

from titan.utils.secrets import SecretStr


def test_get_secret_value_returns_raw_secret() -> None:
    secret = SecretStr("ultra-sensitive-token")

    assert secret.get_secret_value() == "ultra-sensitive-token"


def test_repr_and_str_mask_non_empty_secret() -> None:
    raw = "ultra-sensitive-token"
    secret = SecretStr(raw)

    assert repr(secret) == "SecretStr('********')"
    assert str(secret) == "SecretStr('********')"
    assert raw not in repr(secret)
    assert raw not in str(secret)


def test_empty_secret_representation_is_safe() -> None:
    secret = SecretStr("")

    assert repr(secret) == "SecretStr('')"
    assert str(secret) == "SecretStr('')"
    assert "********" not in repr(secret)
    assert "********" not in str(secret)


def test_secret_bool_matches_current_behavior() -> None:
    assert bool(SecretStr("non-empty")) is True
    assert bool(SecretStr("")) is False
