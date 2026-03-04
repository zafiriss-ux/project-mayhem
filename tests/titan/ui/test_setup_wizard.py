import os
import stat

from titan.ui import setup_wizard


def test_run_setup_wizard_requests_each_credential_once(monkeypatch):
    prompt_counts: dict[str, int] = {}
    answers = iter(
        [
            "athlete@example.com",
            "123456789:ABCDEFGHIJKLMNOP",
            "123456",
            "abcdefghijklmnopqrstuvwxyz123456",
            "Athens,GR",
        ]
    )

    monkeypatch.setattr(setup_wizard, "_banner", lambda: None)
    monkeypatch.setattr(setup_wizard, "load_env_file", lambda: None)

    captured = {}
    monkeypatch.setattr(setup_wizard, "_save_env", lambda creds: captured.update(creds))

    def fake_input(prompt: str) -> str:
        prompt_counts[prompt] = prompt_counts.get(prompt, 0) + 1
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "hunter2")

    creds = setup_wizard.run_setup_wizard()

    assert creds == captured
    assert creds["GARMIN_PASSWORD"] == "hunter2"
    assert prompt_counts == {
        "  Email Garmin: ": 1,
        "  Bot Token: ": 1,
        "  Chat ID (αριθμός): ": 1,
        "  API Key: ": 1,
        "  Τοποθεσία (π.χ. Athens,GR): ": 1,
    }


def test_run_setup_wizard_reprompts_invalid_email(monkeypatch):
    answers = iter(
        [
            "not-an-email",
            "athlete@example.com",
            "123456789:ABCDEFGHIJKLMNOP",
            "123456",
            "abcdefghijklmnopqrstuvwxyz123456",
            "Athens,GR",
        ]
    )

    monkeypatch.setattr(setup_wizard, "_banner", lambda: None)
    monkeypatch.setattr(setup_wizard, "load_env_file", lambda: None)
    monkeypatch.setattr(setup_wizard, "_save_env", lambda creds: None)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "hunter2")

    creds = setup_wizard.run_setup_wizard()

    assert creds["GARMIN_EMAIL"] == "athlete@example.com"


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

    gitignore_content = (tmp_path / ".gitignore").read_text()
    assert ".env" in gitignore_content
    assert "config_secrets.py" in gitignore_content

    if os.name != "nt":
        mode = stat.S_IMODE(env_path.stat().st_mode)
        assert mode == stat.S_IRUSR | stat.S_IWUSR
