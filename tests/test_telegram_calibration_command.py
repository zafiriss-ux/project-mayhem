from unittest.mock import MagicMock

from titan.main import _register_telegram_callbacks


class _DummyTracker:
    def __init__(self, summary):
        self._summary = summary

    def get_calibration_summary(self):
        return self._summary


class _DummyCoach:
    def __init__(self, summary):
        self.outcome_tracker = _DummyTracker(summary)


def _build_ctx(summary):
    return {
        "daily_coach": _DummyCoach(summary),
        "weekly_planner": MagicMock(),
        "athlete_profile": {},
        "hrv_engine": MagicMock(),
        "tsb_engine": MagicMock(),
        "readiness_engine": MagicMock(),
        "nutrition_optimizer": MagicMock(),
        "optimal_time_calc": MagicMock(),
        "garmin": MagicMock(),
        "equipment": MagicMock(),
    }


def test_registers_calibration_command():
    telegram = MagicMock()
    telegram.register_command = MagicMock()

    _register_telegram_callbacks(telegram, _build_ctx({"status": "NO_OUTCOMES_YET"}))

    registered = {call.args[0] for call in telegram.register_command.call_args_list}
    assert "calibration" in registered


def test_calibration_callback_formats_accumulating_summary():
    telegram = MagicMock()
    callbacks = {}
    telegram.register_command = lambda command, cb: callbacks.setdefault(command, cb)

    summary = {
        "status": "ACCUMULATING",
        "n_decisions": 42,
        "n_with_outcome": 12,
        "completion_rate": 0.75,
        "governance_lock_rate": 0.25,
        "athlete_override_rate": 0.1,
        "avg_rpe_when_completed": 6.3,
        "lock_rate_by_phase": {"BUILD": 0.333},
        "calibration_note": "Need 18 more paired outcomes.",
    }
    _register_telegram_callbacks(telegram, _build_ctx(summary))

    response = callbacks["calibration"]()
    assert "*CALIBRATION*" in response
    assert "Status: ACCUMULATING" in response
    assert "Outcomes paired: 12" in response
    assert "BUILD" in response
    assert "Need 18 more paired outcomes." in response
