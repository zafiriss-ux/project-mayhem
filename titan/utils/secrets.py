"""Helpers for handling sensitive strings without exposing raw values in repr traces."""

from dataclasses import dataclass


@dataclass(repr=False)
class SecretStr:
    """Lightweight secret wrapper inspired by pydantic's SecretStr."""

    _value: str = ""

    def __post_init__(self):
        self._value = self._value or ""

    def get_secret_value(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "SecretStr('********')" if self._value else "SecretStr('')"

    __str__ = __repr__

