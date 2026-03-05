from __future__ import annotations

from titan.orchestration import daily_coach


def test_gold_path_morning_routine_system_invariants(monkeypatch, morning_routine_setup):
    events: list[dict] = []
    monkeypatch.setattr(
        daily_coach,
        "_daily_coach_event",
        lambda action, **fields: events.append({"action": action, **fields}),
    )

    coach = morning_routine_setup["coach"]
    db = morning_routine_setup["db"]
    telegram = morning_routine_setup["telegram"]
    today = morning_routine_setup["today"]

    success = coach.run_morning_routine()

    assert success is True

    training_log_count = db.conn.execute(
        "SELECT COUNT(*) FROM training_log WHERE date = ?", (today,)
    ).fetchone()[0]
    daily_metrics_count = db.conn.execute(
        "SELECT COUNT(*) FROM daily_metrics WHERE date = ?", (today,)
    ).fetchone()[0]

    assert training_log_count >= 1
    assert daily_metrics_count >= 1

    actions = [event["action"] for event in events]
    assert "routine_started" in actions
    assert "daily_metrics_persisted" in actions
    assert "routine_completed" in actions

    assert len(telegram.daily_messages) == 1
    payload = telegram.daily_messages[0]
    assert payload
    assert payload.get("session_type")
    assert payload["session_type"] in {"REST", "EASY", "TEMPO", "INTERVALS", "LONG_RUN", "RECOVERY", "OFF"}
