import logging

import pytest

from titan.ui import menu_system


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
def test_browser_drift_uses_first_second_half_hr_and_fallback(monkeypatch, capsys):
    class _FakeDriftEngine:
        @staticmethod
        def compute_drift(hr1, hr2):
            return round((hr2 - hr1) / hr1 * 100, 1)

        @staticmethod
        def classify_drift(value):
            return "GOOD" if value <= 3.5 else "POOR"

    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    monkeypatch.setattr("titan.science.drift_engine.DriftEngine", _FakeDriftEngine)

    menu_system._browser_drift(
        {
            "recent_activities": [
                {"date": "2026-01-10", "activity_type": "run", "avg_hr_first_half": 140, "avg_hr_second_half": 145},
                {"date": "2026-01-11", "activity_type": "run", "drift_pct": 6.2},
            ]
        }
    )

    output = capsys.readouterr().out
    assert "2026-01-10" in output and "3.6%" in output
    assert "2026-01-11" in output and "6.2%" in output


@pytest.mark.unit
def test_browser_tsb_without_engine_shows_warning(monkeypatch, capsys):
    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    menu_system._browser_tsb({})

    assert "TSB engine not available" in capsys.readouterr().out


@pytest.mark.unit
def test_browser_tsb_shows_ctl_after_hydration(monkeypatch, capsys):
    """_browser_tsb must display numeric CTL/ATL/TSB when daily_loads is populated.

    Regression for: "TSB shows None despite loaded daily_loads".
    ctx["tsb_engine"] must resolve to the same TSBEngine that DailyCoach
    hydrates; when it does the output must contain a number, not the string
    "None" or "INSUFFICIENT DATA".
    """
    from titan.science.tsb_engine import TSBEngine

    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    tsb = TSBEngine()
    for i in range(15):
        tsb.add_daily_load(f"2026-04-{i + 1:02d}", float(50 + i * 3))

    ctx = {"tsb_engine": tsb}
    menu_system._browser_tsb(ctx)

    out = capsys.readouterr().out
    assert "None" not in out
    assert "INSUFFICIENT DATA" not in out
    assert "CTL" in out
    # Verify a numeric value is present (not just the label line)
    import re
    assert re.search(r"\d+\.\d", out), f"Expected a decimal number in output, got: {out!r}"


@pytest.mark.unit
def test_menu_shoe_selector_handles_missing_manager_and_unknown_session(monkeypatch, capsys):
    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    menu_system.menu_shoe_selector({})
    missing_output = capsys.readouterr().out
    assert "Equipment manager not initialized" in missing_output

    class _Equip:
        def list_shoes(self):
            return [{"name": "Daily A", "km": 321, "available": True}]

    menu_system.menu_shoe_selector({"equipment_manager": _Equip(), "today_session": {"session_type": "UNKNOWN"}})
    fallback_output = capsys.readouterr().out
    assert "Daily trainer" in fallback_output
    assert "Daily A" in fallback_output


# ── T2-12: UI silent exception handler fixes ─────────────────────────────────

@pytest.mark.unit
def test_menu_system_optimal_time_parse_fallback_emits_warning(monkeypatch, capsys, caplog):
    """When the optimal_time_str is malformed, a warning must be logged and a
    user-facing fallback hint printed (not silent)."""
    from types import SimpleNamespace

    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    nutrition_mock = SimpleNamespace(
        analyze_weight_trend=lambda: {"current_weight": 70.0, "velocity_kg_per_week": 0.0},
        calculate_daily_nutrition=lambda **k: {
            "pre_session": "oats",
            "during_session": "gel",
            "post_session": "protein",
            "carbs_g": 250,
            "carbs_range": "230-270g",
            "protein_g": 120,
            "fat_g": 60,
            "total_calories": 2000,
            "hydration_ml": 2500,
        },
    )

    ctx = {
        "nutrition_optimizer": nutrition_mock,
        "optimal_time_str": "NOT_A_TIME",  # malformed — triggers the except branch
        "today_session": {"session_type": "EASY", "duration_min": 45},
        "athlete_profile": {"weight_kg": 70.0},
    }

    with caplog.at_level(logging.WARNING, logger="titan.ui.menu_system"):
        menu_system.menu_nutrition(ctx)

    out = capsys.readouterr().out
    assert "time format unavailable" in out or "defaulting to 07:00" in out
    assert any("optimal_time_parse_fallback" in r.message for r in caplog.records)


@pytest.mark.unit
def test_menu_system_shoe_display_handles_malformed_data_gracefully(monkeypatch, capsys, caplog):
    """When shoe data is malformed, a warning must be logged and a fallback
    message printed (not silent pass)."""
    monkeypatch.setattr(menu_system, "_clear", lambda: None)
    monkeypatch.setattr(menu_system, "_header", lambda title="": None)
    monkeypatch.setattr(menu_system, "_divider", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    class _BrokenEquip:
        def list_shoes(self):
            raise TypeError("malformed shoe record")

    ctx = {
        "equipment_manager": _BrokenEquip(),
        "today_session": {"session_type": "EASY"},
    }

    with caplog.at_level(logging.WARNING, logger="titan.ui.menu_system"):
        menu_system.menu_shoe_selector(ctx)

    out = capsys.readouterr().out
    assert "equipment data unavailable" in out
    assert any("shoe_display_error" in r.message for r in caplog.records)
