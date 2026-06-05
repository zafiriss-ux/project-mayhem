import json
import os
import stat

import pytest

from titan.ui import setup_wizard


@pytest.mark.unit
def test_run_setup_wizard_requests_each_credential_once(monkeypatch):
    prompt_counts: dict[str, int] = {}
    answers = iter(
        [
            "athlete@example.com",
            "123456789:ABCDEFGHIJKLMNOP",
            "123456",
            "abcdefghijklmnopqrstuvwxyz123456",
            "Athens,GR",
            "male",
        ]
    )

    monkeypatch.setattr(setup_wizard, "_banner", lambda: None)
    monkeypatch.setattr(setup_wizard, "load_env_file", lambda: None)

    captured = {}

    def fake_save_credentials(creds):
        captured.update(creds)
        return "env_file"

    monkeypatch.setattr(setup_wizard, "_save_credentials", fake_save_credentials)

    def fake_input(prompt: str) -> str:
        prompt_counts[prompt] = prompt_counts.get(prompt, 0) + 1
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "hunter2")

    creds = setup_wizard.run_setup_wizard()

    assert creds == captured
    assert creds["GARMIN_PASSWORD"] == "hunter2"
    assert creds["ATHLETE_BIOLOGICAL_SEX"] == "male"
    assert creds["ATHLETE_MENSTRUAL_TRACKING"] == "no"
    assert prompt_counts == {
        "  Email Garmin: ": 1,
        "  Bot Token: ": 1,
        "  Chat ID (αριθμός): ": 1,
        "  API Key: ": 1,
        "  Τοποθεσία (π.χ. Athens,GR): ": 1,
        "  Βιολογικό φύλο (male/female/prefer_not_to_say): ": 1,
    }


@pytest.mark.unit
def test_run_setup_wizard_reprompts_invalid_email(monkeypatch):
    answers = iter(
        [
            "not-an-email",
            "athlete@example.com",
            "123456789:ABCDEFGHIJKLMNOP",
            "123456",
            "abcdefghijklmnopqrstuvwxyz123456",
            "Athens,GR",
            "male",
        ]
    )

    monkeypatch.setattr(setup_wizard, "_banner", lambda: None)
    monkeypatch.setattr(setup_wizard, "load_env_file", lambda: None)
    monkeypatch.setattr(setup_wizard, "_save_credentials", lambda creds: "env_file")
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "hunter2")

    creds = setup_wizard.run_setup_wizard()

    assert creds["GARMIN_EMAIL"] == "athlete@example.com"


@pytest.mark.unit
def test_save_env_writes_expected_entries(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    fake_file = tmp_path / "titan" / "ui" / "setup_wizard.py"
    fake_file.parent.mkdir(parents=True)
    fake_file.write_text("# test")

    monkeypatch.setattr(setup_wizard, "ENV_PATH", env_path)
    monkeypatch.setattr(setup_wizard, "__file__", str(fake_file))

    setup_wizard._save_env(
        {
            "GARMIN_EMAIL": "athlete@example.com",
            "GARMIN_PASSWORD": "secret",
        }
    )

    content = env_path.read_text()
    assert "GARMIN_EMAIL=athlete@example.com" in content
    assert "GARMIN_PASSWORD=secret" in content

    # T4-17: _save_env() must NOT silently mutate .gitignore at runtime.
    # .gitignore entries belong in the repository, not in wizard runtime code.
    assert not (tmp_path / ".gitignore").exists(), (
        "_save_env() must not create or modify .gitignore (T4-17)"
    )

    if os.name != "nt":
        mode = stat.S_IMODE(env_path.stat().st_mode)
        assert mode == stat.S_IRUSR | stat.S_IWUSR


@pytest.mark.unit
def test_save_credentials_defaults_to_env_backend(monkeypatch):
    monkeypatch.delenv(setup_wizard.KEYRING_ENV_FLAG, raising=False)

    creds = {
        "GARMIN_EMAIL": "athlete@example.com",
        "GARMIN_PASSWORD": "secret",
        "TELEGRAM_BOT_TOKEN": "123456789:ABCDEFGHIJKLMNOP",
        "TELEGRAM_CHAT_ID": "123",
        "WEATHER_API_KEY": "abcdefghijklmnopqrstuvwxyz123456",
        "WEATHER_LOCATION": "Athens,GR",
    }

    captured = {}
    monkeypatch.setattr(setup_wizard, "_save_env", lambda data: captured.update(data))

    messages = []
    monkeypatch.setattr(setup_wizard._log, "info", lambda message: messages.append(json.loads(message)))

    backend = setup_wizard._save_credentials(creds)

    assert backend == "env_file_partial"
    assert captured == creds  # CP-03: all creds saved when keyring is unavailable
    assert messages[-1]["action"] == "credential_storage_backend_selected"
    assert messages[-1]["backend"] == "env_file_partial"


@pytest.mark.unit
def test_save_credentials_uses_keyring_when_enabled(monkeypatch):
    monkeypatch.setenv(setup_wizard.KEYRING_ENV_FLAG, "1")

    class FakeKeyring:
        def __init__(self):
            self.calls = []

        def set_password(self, service_name, username, password):
            self.calls.append((service_name, username, password))

    fake_keyring = FakeKeyring()
    monkeypatch.setattr(setup_wizard.importlib, "import_module", lambda name: fake_keyring)

    creds = {
        "GARMIN_EMAIL": "athlete@example.com",
        "GARMIN_PASSWORD": "secret",
        "TELEGRAM_BOT_TOKEN": "123456789:ABCDEFGHIJKLMNOP",
        "TELEGRAM_CHAT_ID": "123",
        "WEATHER_API_KEY": "abcdefghijklmnopqrstuvwxyz123456",
        "WEATHER_LOCATION": "Athens,GR",
    }

    saved_env = {}
    monkeypatch.setattr(setup_wizard, "_save_env", lambda data: saved_env.update(data))

    backend = setup_wizard._save_credentials(creds)

    assert backend == "keyring"
    assert fake_keyring.calls == [
        ("TITAN_GARMIN_EMAIL", "credential", "athlete@example.com"),
        ("TITAN_GARMIN_PASSWORD", "credential", "secret"),
        ("TITAN_TELEGRAM_TOKEN", "credential", "123456789:ABCDEFGHIJKLMNOP"),
    ]
    assert "GARMIN_EMAIL" not in saved_env
    assert "GARMIN_PASSWORD" not in saved_env
    assert "TELEGRAM_BOT_TOKEN" not in saved_env
    assert saved_env["TELEGRAM_CHAT_ID"] == "123"


@pytest.mark.unit
def test_save_credentials_falls_back_to_env_when_keyring_import_fails(monkeypatch):
    monkeypatch.setenv(setup_wizard.KEYRING_ENV_FLAG, "1")

    def raise_import_error(module_name: str):
        raise ImportError(module_name)

    monkeypatch.setattr(setup_wizard.importlib, "import_module", raise_import_error)

    creds = {
        "GARMIN_EMAIL": "athlete@example.com",
        "GARMIN_PASSWORD": "secret",
        "TELEGRAM_BOT_TOKEN": "123456789:ABCDEFGHIJKLMNOP",
    }

    saved_env = {}
    monkeypatch.setattr(setup_wizard, "_save_env", lambda data: saved_env.update(data))

    backend = setup_wizard._save_credentials(creds)

    # CP-03: all creds are saved to .env when keyring is unavailable (import fails)
    # so the system remains functional even without a keyring backend.
    assert backend == "env_file_partial"
    assert saved_env == creds


@pytest.mark.unit
def test_load_env_file_preserves_existing_environment_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# ignored\n"
        "GARMIN_EMAIL=file@example.com\n"
        "GARMIN_PASSWORD=file-secret\n"
        "TELEGRAM_BOT_TOKEN=file-token\n"
    )
    monkeypatch.setattr(setup_wizard, "ENV_PATH", env_path)
    monkeypatch.setenv("GARMIN_EMAIL", "existing@example.com")
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(setup_wizard, "_load_keyring_credentials", lambda: None)

    setup_wizard.load_env_file()

    assert os.getenv("GARMIN_EMAIL") == "existing@example.com"
    assert os.getenv("GARMIN_PASSWORD") == "file-secret"
    assert os.getenv("TELEGRAM_BOT_TOKEN") == "file-token"


@pytest.mark.unit
def test_ensure_credentials_returns_false_when_setup_cancelled(monkeypatch):
    monkeypatch.setattr(setup_wizard, "load_env_file", lambda: None)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(setup_wizard, "credentials_exist", lambda: False)

    def _interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(setup_wizard, "run_setup_wizard", _interrupt)

    assert setup_wizard.ensure_credentials() is False


def _make_answers(*extra):
    return iter([
        "athlete@example.com",
        "123456789:ABCDEFGHIJKLMNOP",
        "123456",
        "abcdefghijklmnopqrstuvwxyz123456",
        "Athens,GR",
        *extra,
    ])


def _run_wizard_capturing(monkeypatch, answers):
    captured = {}
    monkeypatch.setattr(setup_wizard, "_banner", lambda: None)
    monkeypatch.setattr(setup_wizard, "load_env_file", lambda: None)
    monkeypatch.setattr(setup_wizard, "_save_credentials", lambda c: captured.update(c) or "env_file")
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "hunter2")
    setup_wizard.run_setup_wizard()
    return captured


@pytest.mark.unit
def test_q5_female_skips_q6_when_prefer_not_to_say(monkeypatch):
    creds = _run_wizard_capturing(monkeypatch, _make_answers("prefer_not_to_say"))
    assert creds["ATHLETE_BIOLOGICAL_SEX"] == "prefer_not_to_say"
    assert creds["ATHLETE_MENSTRUAL_TRACKING"] == "no"


@pytest.mark.unit
def test_q5_female_triggers_q6(monkeypatch):
    creds = _run_wizard_capturing(monkeypatch, _make_answers("female", "yes"))
    assert creds["ATHLETE_BIOLOGICAL_SEX"] == "female"
    assert creds["ATHLETE_MENSTRUAL_TRACKING"] == "yes"


@pytest.mark.unit
def test_q5_female_q6_no(monkeypatch):
    creds = _run_wizard_capturing(monkeypatch, _make_answers("female", "no"))
    assert creds["ATHLETE_BIOLOGICAL_SEX"] == "female"
    assert creds["ATHLETE_MENSTRUAL_TRACKING"] == "no"


@pytest.mark.unit
def test_q5_reprompts_invalid_sex(monkeypatch):
    creds = _run_wizard_capturing(monkeypatch, _make_answers("unknown_value", "male"))
    assert creds["ATHLETE_BIOLOGICAL_SEX"] == "male"


@pytest.mark.unit
def test_q6_reprompts_invalid_tracking(monkeypatch):
    creds = _run_wizard_capturing(monkeypatch, _make_answers("female", "maybe", "yes"))
    assert creds["ATHLETE_MENSTRUAL_TRACKING"] == "yes"


@pytest.mark.unit
def test_q5_empty_input_defaults_to_male(monkeypatch):
    creds = _run_wizard_capturing(monkeypatch, _make_answers(""))
    assert creds["ATHLETE_BIOLOGICAL_SEX"] == "male"
    assert creds["ATHLETE_MENSTRUAL_TRACKING"] == "no"
