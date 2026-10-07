from pathlib import Path

import pytest

from launcher import wizard


def _set_env_path(monkeypatch, tmp_path: Path) -> Path:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(wizard, "get_env_path", lambda: env_path)
    return env_path


@pytest.mark.integration
def test_ensure_config_rejects_empty_existing_env(monkeypatch, tmp_path: Path) -> None:
    env_path = _set_env_path(monkeypatch, tmp_path)
    env_path.write_text("", encoding="utf-8")

    assert wizard.ensure_config() is False


def test_ensure_config_rejects_missing_required_credentials(monkeypatch, tmp_path: Path) -> None:
    env_path = _set_env_path(monkeypatch, tmp_path)
    env_path.write_text("GARMIN_USERNAME=athlete@example.com\n", encoding="utf-8")

    assert wizard.ensure_config() is False


def test_ensure_config_accepts_garmin_email_alias(monkeypatch, tmp_path: Path) -> None:
    env_path = _set_env_path(monkeypatch, tmp_path)
    env_path.write_text(
        "GARMIN_EMAIL=athlete@example.com\n"
        "GARMIN_PASSWORD=secret\n"
        "TELEGRAM_BOT_TOKEN=1234567890:abcdefghij\n"
        "TELEGRAM_CHAT_ID=12345\n",
        encoding="utf-8",
    )

    assert wizard.ensure_config() is True


def test_validate_telegram_token_accepts_length_20() -> None:
    assert wizard.validate_telegram_token("1234567890:abcdefghi") is True


def test_validate_telegram_chat_id_requires_numeric() -> None:
    assert wizard.validate_telegram_chat_id("abc123") is False


def test_console_wizard_writes_garmin_email(monkeypatch) -> None:
    """The kernel reads GARMIN_EMAIL only; the wizard must write that key."""
    answers = iter(["athlete@example.com", "secret", "1234567890:abcdefghij", "12345", "", ""])
    monkeypatch.setattr(wizard, "prompt_input", lambda *args, **kwargs: next(answers))

    config = wizard.run_wizard()

    assert config["GARMIN_EMAIL"] == "athlete@example.com"
    assert "GARMIN_USERNAME" not in config


def test_load_env_to_os_maps_legacy_garmin_username(monkeypatch) -> None:
    import launcher.main as launcher_main

    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.setattr(launcher_main, "load_env", lambda: {"GARMIN_USERNAME": "legacy@example.com"})

    launcher_main.load_env_to_os()

    import os

    assert os.environ["GARMIN_EMAIL"] == "legacy@example.com"
    monkeypatch.delenv("GARMIN_USERNAME", raising=False)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)


def test_load_env_to_os_keeps_explicit_garmin_email(monkeypatch) -> None:
    import launcher.main as launcher_main

    monkeypatch.setattr(
        launcher_main,
        "load_env",
        lambda: {"GARMIN_USERNAME": "old@example.com", "GARMIN_EMAIL": "new@example.com"},
    )

    launcher_main.load_env_to_os()

    import os

    assert os.environ["GARMIN_EMAIL"] == "new@example.com"
    monkeypatch.delenv("GARMIN_USERNAME", raising=False)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
