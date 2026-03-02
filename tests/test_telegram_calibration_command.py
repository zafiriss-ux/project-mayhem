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


def test_calibration_callback_formats_lock_correlation_section():
    telegram = MagicMock()
    callbacks = {}
    telegram.register_command = lambda command, cb: callbacks.setdefault(command, cb)

    summary = {
        "status": "CALIBRATION_AVAILABLE",
        "n_decisions": 40,
        "n_with_outcome": 32,
        "completion_rate": 0.81,
        "governance_lock_rate": 0.34,
        "athlete_override_rate": 0.08,
        "avg_rpe_when_completed": 6.1,
        "lock_rate_by_phase": {"BUILD": 0.333},
        "lock_outcome_correlation": {
            "LOCK_A": {"completion_delta_pp": -12.5, "n_with_lock": 8, "n_without_lock": 24}
        },
        "calibration_note": "Ready for threshold calibration review.",
    }
    _register_telegram_callbacks(telegram, _build_ctx(summary))

    response = callbacks["calibration"]()
    assert "Lock/outcome correlation" in response
    assert "LOCK_A" in response
    assert "Δcompletion -12.5pp" in response
