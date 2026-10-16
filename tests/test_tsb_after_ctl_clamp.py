"""D-082: TSB is CTL − ATL of the values get_ctl_atl_tsb returns.

The ADR-0023 bounds clamp CTL at 300, but TSB kept the unclamped difference, so
the three numbers disagreed (assessment example: 300.0, 395.1, −12.9).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from titan.core.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


def _daily_load(db, load: int, days: int) -> None:
    today = date.today()
    for i in range(days):
        day = (today - timedelta(days=i)).isoformat()
        db.save_session(day, "EASY", 10.0, 3600, training_load=load)


@pytest.mark.unit
def test_a_clamped_ctl_moves_tsb_with_it(db) -> None:
    _daily_load(db, 400, 210)  # CTL ≈ 397 → clamped to 300; ATL ≈ 400 is in bounds
    ctl, atl, tsb = db.get_ctl_atl_tsb()
    assert ctl == 300.0
    assert 390 < atl <= 400
    assert tsb == round(ctl - atl, 1)
    assert tsb < -90  # the unclamped difference was about −3


@pytest.mark.unit
def test_tsb_is_unchanged_when_nothing_is_clamped(db) -> None:
    from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS
    from titan.science.tsb_engine import LOAD_HISTORY_DAYS, compute_ctl_atl_tsb

    _daily_load(db, 60, 60)
    expected = compute_ctl_atl_tsb(
        daily_loads=db.get_training_load_history(LOAD_HISTORY_DAYS),
        ctl_decay_days=CTL_DECAY_DAYS,
        atl_decay_days=ATL_DECAY_DAYS,
    )
    assert db.get_ctl_atl_tsb() == expected
