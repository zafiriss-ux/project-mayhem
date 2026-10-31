"""M0-29 (SP audit, D-192): each container gets only the secrets its code reads.

The API used to load the whole ``.env``: the Garmin and Telegram credentials and
``TITAN_GARTH_TOKEN_KEY``, the key of the owner's Garmin session token, which sits on
the same ``titan-data`` volume the API mounts. The worker got the JWT signing key,
which only the API uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_NOT_FOR_THE_API = {
    "GARMIN_EMAIL", "GARMIN_PASSWORD", "TITAN_GARTH_TOKEN_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_OWNER_USER_ID",
}


def _service(name: str) -> dict:
    compose = yaml.safe_load((_REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    return compose["services"][name]


def _environment(service: dict) -> dict[str, str]:
    env = service.get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) if "=" in item else (item, "") for item in env)
    return {key: str(value) for key, value in env.items()}


@pytest.mark.unit
def test_the_api_does_not_load_the_whole_env_file() -> None:
    assert "env_file" not in _service("titan-api")


@pytest.mark.unit
def test_the_api_gets_no_garmin_or_telegram_secret() -> None:
    assert not _NOT_FOR_THE_API & set(_environment(_service("titan-api")))


@pytest.mark.unit
def test_the_api_still_gets_its_jwt_keys() -> None:
    env = _environment(_service("titan-api"))
    assert env["TITAN_JWT_PRIVATE_KEY"] == "${TITAN_JWT_PRIVATE_KEY:-}"
    assert env["TITAN_JWT_PUBLIC_KEY"] == "${TITAN_JWT_PUBLIC_KEY:-}"


@pytest.mark.unit
def test_the_worker_does_not_get_the_jwt_signing_key() -> None:
    assert _environment(_service("titan-worker")).get("TITAN_JWT_PRIVATE_KEY") == ""
