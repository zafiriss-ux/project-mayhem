"""SD-08 (D-161): /recovery shows the readiness the morning computed, never a score of fixed inputs.

Before the fix, /recovery scored readiness from RHR 50/48, sleep 8 and soreness 3, whatever
the owner's day was, next to an HRV of any age. Now it shows today's stored morning score,
says so when there is none yet, and gives the date of the last HRV reading.
Synthetic data only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from titan import main as titan_main
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.readiness_engine import ReadinessEngine

_TODAY = datetime.now(UTC).date().isoformat()


class _Bot:
    def __init__(self) -> None:
        self.cmds: dict = {}

    def register_command(self, name, fn):
        self.cmds[name] = fn

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _decision(score: float) -> dict:
    return {
        "date": _TODAY, "session_planned": "TEMPO", "session_post_governance": "EASY",
        "locks_applied": [], "governance_clean": True, "phase": "BUILD",
        "vlg_color": "GREEN", "apl_priority_vector": {}, "lock_thresholds_active": {},
        "acwr": 1.0, "tsb_value": -5.0, "readiness_score": score, "glycogen_debt": 0.0,
    }


@pytest.fixture
def recovery(db_manager_factory, monkeypatch):
    db = db_manager_factory(db_name="test.db")

    def _no_fixed_inputs(*_a, **_k):
        raise AssertionError("/recovery must not score readiness from fixed inputs")

    monkeypatch.setattr(ReadinessEngine, "analyze_readiness", staticmethod(_no_fixed_inputs))
    hrv = HRVGuidedEngine()
    for day in range(1, 9):
        hrv.add_hrv_measurement(f"2026-01-0{day}", 70.0)
    bot = _Bot()
    titan_main._register_telegram_callbacks(
        bot, {"db": db, "hrv_engine": hrv, "readiness_engine": ReadinessEngine()}
    )
    return db, bot.cmds["recovery"]


def test_recovery_shows_todays_stored_morning_score(recovery):
    db, cmd = recovery
    db.save_governance_decision(_decision(55.0))
    text = cmd()
    assert "55" in text
    assert "Σφάλμα" not in text


def test_recovery_without_a_morning_decision_shows_no_score(recovery):
    _db, cmd = recovery
    text = cmd()
    assert "/100" not in text
    assert "Σφάλμα" not in text


def test_recovery_gives_the_date_of_the_last_hrv_reading(recovery):
    _db, cmd = recovery
    assert "2026-01-08" in cmd()
