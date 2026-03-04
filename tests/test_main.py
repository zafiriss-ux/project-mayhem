import logging
import sys
import types

import pytest

import main as launcher


def test_run_launcher_happy_path_calls_titan_main(monkeypatch):
    called = {"count": 0}

    fake_mod = types.ModuleType("titan.main")

    def _fake_main():
        called["count"] += 1

    fake_mod.main = _fake_main
    monkeypatch.setitem(sys.modules, "titan.main", fake_mod)

    launcher._run_launcher()

    assert called["count"] == 1


def test_run_launcher_failure_logs_structured_startup_event(monkeypatch, caplog):
    fake_mod = types.ModuleType("titan.main")

    def _boom():
        raise RuntimeError("launcher exploded")

    fake_mod.main = _boom
    monkeypatch.setitem(sys.modules, "titan.main", fake_mod)

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="launcher exploded"):
        launcher._run_launcher()

    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.component == "launcher"
    assert record.error_class == "RuntimeError"
    assert record.detail == "launcher exploded"
