import logging

import pytest

from titan import main as titan_main


def test_parse_env_number_happy_path(monkeypatch):
    monkeypatch.setenv("ATHLETE_AGE", "36")

    value = titan_main._parse_env_number("ATHLETE_AGE", "35", int)

    assert value == 36


def test_main_credentials_failure_logs_structured_startup_event(monkeypatch, caplog):
    monkeypatch.setattr(titan_main, "_print_banner", lambda: None)
    monkeypatch.setattr(titan_main, "ensure_credentials", lambda: False)

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        titan_main.main()

    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.component == "launcher"
    assert record.error_class == "CredentialsUnavailable"
    assert record.detail == "ensure_credentials() returned False"
