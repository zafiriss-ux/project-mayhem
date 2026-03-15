from pathlib import Path

from launcher import wizard


def _set_env_path(monkeypatch, tmp_path: Path) -> Path:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(wizard, "get_env_path", lambda: env_path)
    return env_path


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
