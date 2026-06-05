from types import SimpleNamespace

import pytest

from titan.science.override_signal import OverrideSignal, record_override_signal


class _DB:
    def __init__(self):
        self.calls = []

    def record_override_signal(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.unit
def test_record_override_signal_persists_valid_payload():
    db = _DB()
    signal = OverrideSignal.create(
        decision_id="decision-1",
        athlete_id="ATH_1",
        override_source="telegram_bot",
        override_reason="Felt stable after warmup",
    )

    record_override_signal(db, signal)

    assert db.calls[0]["decision_id"] == "decision-1"
    assert db.calls[0]["athlete_id"] == "ATH_1"


@pytest.mark.unit
def test_record_override_signal_rejects_empty_reason():
    db = _DB()
    signal = OverrideSignal.create(
        decision_id="decision-1",
        athlete_id="ATH_1",
        override_source="telegram_bot",
        override_reason="   ",
    )

    with pytest.raises(ValueError, match="override_reason is required"):
        record_override_signal(db, signal)
