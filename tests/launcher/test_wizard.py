import os
import stat
from pathlib import Path

import pytest

from launcher import wizard


def _unset_env(monkeypatch, name: str) -> None:
    """Remove ``name`` for this test and restore its state after.

    load_env_to_os writes os.environ directly; monkeypatch.delenv on an absent
    name records nothing, so a value set by the code under test would leak.
    """
    monkeypatch.setenv(name, "")
    monkeypatch.delenv(name)


def _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path: Path) -> None:
    for name in ("TITAN_DATA_DIR", "TITAN_GARTH_TOKEN_KEY", "TITAN_LOG_PATH", "TITAN_ENV_FILE"):
        _unset_env(monkeypatch, name)
    monkeypatch.setattr(launcher_main, "get_data_directory", lambda: tmp_path)
    monkeypatch.setattr(launcher_main, "ensure_garmin_token_key", lambda: "test-key")


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


def test_load_env_to_os_maps_legacy_garmin_username(monkeypatch, tmp_path: Path) -> None:
    import launcher.main as launcher_main

    _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.setattr(launcher_main, "load_env", lambda: {"GARMIN_USERNAME": "legacy@example.com"})

    launcher_main.load_env_to_os()

    import os

    assert os.environ["GARMIN_EMAIL"] == "legacy@example.com"
    monkeypatch.delenv("GARMIN_USERNAME", raising=False)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)


def test_load_env_to_os_keeps_explicit_garmin_email(monkeypatch, tmp_path: Path) -> None:
    import launcher.main as launcher_main

    _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path)
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


def test_load_env_to_os_puts_titan_log_in_the_data_folder(monkeypatch, tmp_path: Path) -> None:
    import os

    import launcher.main as launcher_main

    _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path)
    monkeypatch.setattr(launcher_main, "load_env", dict)

    launcher_main.load_env_to_os()

    assert os.environ["TITAN_LOG_PATH"] == str(tmp_path / "logs" / "titan.log")


def test_load_env_to_os_keeps_titan_log_path_from_env_file(monkeypatch, tmp_path: Path) -> None:
    import os

    import launcher.main as launcher_main

    _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path)
    monkeypatch.setattr(launcher_main, "load_env", lambda: {"TITAN_LOG_PATH": "/custom/titan.log"})

    launcher_main.load_env_to_os()

    assert os.environ["TITAN_LOG_PATH"] == "/custom/titan.log"


def test_load_env_to_os_points_the_kernel_at_the_data_folder_env(monkeypatch, tmp_path: Path) -> None:
    """TITAN.exe: the profile editor must write the launcher's .env, not one in the temp unpack folder."""
    import os

    import launcher.main as launcher_main

    _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path)
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


def test_load_env_to_os_gives_the_kernel_a_data_folder_and_token_key(monkeypatch, tmp_path: Path) -> None:
    """Without both, the kernel never saved the Garmin session in TITAN.exe."""
    import os

    import launcher.main as launcher_main

    _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path)
    monkeypatch.setattr(launcher_main, "load_env", dict)

    launcher_main.load_env_to_os()

    assert os.environ["TITAN_DATA_DIR"] == str(tmp_path)
    assert os.environ["TITAN_GARTH_TOKEN_KEY"] == "test-key"


def test_load_env_to_os_keeps_data_folder_from_env_file(monkeypatch, tmp_path: Path) -> None:
    import os

    import launcher.main as launcher_main

    _isolate_load_env_to_os(monkeypatch, launcher_main, tmp_path)
    monkeypatch.setattr(launcher_main, "load_env", lambda: {"TITAN_DATA_DIR": "/custom"})

    launcher_main.load_env_to_os()

    assert os.environ["TITAN_DATA_DIR"] == "/custom"


def test_garmin_token_key_is_created_once_and_saved(monkeypatch, tmp_path: Path) -> None:
    env_path = _set_env_path(monkeypatch, tmp_path)
    env_path.write_text("GARMIN_EMAIL=athlete@example.com", encoding="utf-8")

    first = wizard.ensure_garmin_token_key()
    second = wizard.ensure_garmin_token_key()

    assert first == second
    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert lines == ["GARMIN_EMAIL=athlete@example.com", f"TITAN_GARTH_TOKEN_KEY={first}"]


def test_garmin_token_key_lets_the_kernel_save_the_session(monkeypatch, tmp_path: Path) -> None:
    from titan.integrations import garmin_sync

    _set_env_path(monkeypatch, tmp_path).write_text("", encoding="utf-8")
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", wizard.ensure_garmin_token_key())
    monkeypatch.setenv("TITAN_ENV", "")

    encrypted = garmin_sync._encrypt_token("session")

    assert garmin_sync._decrypt_token(encrypted) == "session"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_write_env_never_writes_a_credential_into_a_readable_file(monkeypatch, tmp_path: Path) -> None:
    # SP-06: the launcher's .env is 600 before the first byte; chmod after the write left a window.
    env_path = _set_env_path(monkeypatch, tmp_path)
    env_path.write_text("OLD=1\n")
    env_path.chmod(0o644)
    monkeypatch.setattr(type(env_path), "chmod", lambda self, mode: None)  # no fix after the fact

    wizard.write_env({"GARMIN_PASSWORD": "canary-sp06"})

    assert stat.S_IMODE(env_path.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR
    assert "GARMIN_PASSWORD=canary-sp06" in env_path.read_text(encoding="utf-8")
