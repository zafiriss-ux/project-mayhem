from __future__ import annotations

from titan.orchestration import daily_coach


class PersistFailure(Exception):
    """Deterministic sentinel error for persistence failure simulation."""


def test_persistence_failure_degraded_mode_invariant(monkeypatch, morning_routine_setup):
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

    monkeypatch.setattr(db, "save_session", lambda **_kwargs: (_ for _ in ()).throw(PersistFailure("forced")))

    training_log_before = db.conn.execute(
        "SELECT COUNT(*) FROM training_log WHERE date = ?", (today,)
    ).fetchone()[0]
    daily_metrics_before = db.conn.execute(
        "SELECT COUNT(*) FROM daily_metrics WHERE date = ?", (today,)
    ).fetchone()[0]

    success = coach.run_morning_routine()

    training_log_after = db.conn.execute(
        "SELECT COUNT(*) FROM training_log WHERE date = ?", (today,)
    ).fetchone()[0]
    daily_metrics_after = db.conn.execute(
        "SELECT COUNT(*) FROM daily_metrics WHERE date = ?", (today,)
    ).fetchone()[0]

    # 1) routine does not crash process
    assert success in {True, False}

    # 2) no new rows persisted when persistence fails
    assert training_log_after == training_log_before
    assert daily_metrics_after == daily_metrics_before

    # 3) degraded behavior invariant:
    #    abort with no recommendation OR conservative recommendation (REST/EASY)
    if not telegram.daily_messages:
        assert success is False
    else:
        assert len(telegram.daily_messages) == 1
        payload = telegram.daily_messages[0]
        assert payload
        assert payload.get("session_type") in {"REST", "EASY"}

    # 4) persistence failure is explicitly visible in orchestration events
    actions = [event["action"] for event in events]
    assert "daily_metrics_persist_failed" in actions
