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

    monkeypatch.delenv("TITAN_ENV_FILE", raising=False)  # restored after the test
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.setattr(launcher_main, "load_env", lambda: {"GARMIN_USERNAME": "legacy@example.com"})

    launcher_main.load_env_to_os()

    import os

    assert os.environ["GARMIN_EMAIL"] == "legacy@example.com"
    monkeypatch.delenv("GARMIN_USERNAME", raising=False)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)


def test_load_env_to_os_keeps_explicit_garmin_email(monkeypatch) -> None:
    import launcher.main as launcher_main

    monkeypatch.delenv("TITAN_ENV_FILE", raising=False)  # restored after the test
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


def test_load_env_to_os_points_the_kernel_at_the_data_folder_env(monkeypatch, tmp_path: Path) -> None:
    """TITAN.exe: the profile editor must write the launcher's .env, not one in the temp unpack folder."""
    import os

    import launcher.main as launcher_main

    monkeypatch.delenv("TITAN_ENV_FILE", raising=False)  # restored after the test
    monkeypatch.setattr(launcher_main, "load_env", dict)
    monkeypatch.setattr(launcher_main, "get_env_path", lambda: tmp_path / ".env")

    launcher_main.load_env_to_os()

    assert os.environ["TITAN_ENV_FILE"] == str(tmp_path / ".env")


def test_kernel_env_path_follows_titan_env_file(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    env_file = tmp_path / "data" / ".env"
    result = subprocess.run(
        [sys.executable, "-c", "from titan.ui.setup_wizard import ENV_PATH; print(ENV_PATH)"],
        env={**os.environ, "TITAN_ENV_FILE": str(env_file)},
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.stdout.strip() == str(env_file)
