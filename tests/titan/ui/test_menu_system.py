import pytest

from titan.ui import menu_system


def test_main_menu_dispatches_selected_action_then_exits(monkeypatch):
    calls: list[str] = []
    answers = iter(["1", "0"])

    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="TITAN v51": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(menu_system, "menu_daily_plan", lambda _ctx: calls.append("daily"))
    monkeypatch.setattr(menu_system.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    with pytest.raises(SystemExit) as exc:
        menu_system.main_menu({})

    assert calls == ["daily"]
    assert exc.value.code == 0


def test_main_menu_reprompts_for_unknown_choice(monkeypatch, capsys):
    answers = iter(["99", "", "0"])

    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="TITAN v51": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(menu_system.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    with pytest.raises(SystemExit):
        menu_system.main_menu({})

    assert "Άγνωστη επιλογή" in capsys.readouterr().out


def test_menu_data_browser_dispatches_each_supported_option(monkeypatch):
    answers = iter(["1", "2", "3", "4", "5", "6", "0"])
    calls: list[str] = []

    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="Data Browser": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(menu_system, "_browser_activities", lambda _ctx: calls.append("activities"))
    monkeypatch.setattr(menu_system, "_browser_drift", lambda _ctx: calls.append("drift"))
    monkeypatch.setattr(menu_system, "_browser_hrv", lambda _ctx: calls.append("hrv"))
    monkeypatch.setattr(menu_system, "_browser_sleep", lambda _ctx: calls.append("sleep"))
    monkeypatch.setattr(menu_system, "_browser_weight", lambda _ctx: calls.append("weight"))
    monkeypatch.setattr(menu_system, "_browser_tsb", lambda _ctx: calls.append("tsb"))

    menu_system.menu_data_browser({})

    assert calls == ["activities", "drift", "hrv", "sleep", "weight", "tsb"]


def test_browser_activities_handles_empty_and_populated_data(monkeypatch, capsys):
    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    menu_system._browser_activities({"recent_activities": []})
    empty_output = capsys.readouterr().out
    assert "Κάνε sync πρώτα" in empty_output

    menu_system._browser_activities(
        {
            "recent_activities": [
                {
                    "date": "2026-01-10",
                    "activity_type": "run",
                    "distance_km": 12.3,
                    "duration_sec": 3660,
                    "avg_hr": 150,
                    "avg_pace_sec_per_km": 305,
                }
            ]
        }
    )
    data_output = capsys.readouterr().out
    assert "2026-01-10" in data_output
    assert "5:05" in data_output
