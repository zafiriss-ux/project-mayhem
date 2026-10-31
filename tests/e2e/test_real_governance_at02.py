"""AT-02 (part 2): the e2e morning runs the real GovernanceEngine.

StubGovernance returned the plan untouched with an empty report, so a change
to gate order or to the cold-start lockdown left the gold path green.
"""

from __future__ import annotations

import pytest

from titan.science.governance_engine import GovernanceEngine


@pytest.mark.integration
def test_the_gold_path_morning_reports_the_real_cold_start_lockdown(morning_routine_setup) -> None:
    coach = morning_routine_setup["coach"]
    assert isinstance(coach.governance, GovernanceEngine)
    assert coach.run_morning_routine() is True

    payload = morning_routine_setup["telegram"].daily_messages[0]
    lockdown = payload["governance_report"]["override_lockdown"]
    # A fresh database has no override history: the engine locks to zone 2.
    assert lockdown["locked"] is True
    assert lockdown["reason"] == "cold_start_no_history"
    assert payload["session_type"] not in lockdown["disabled_sessions"]
