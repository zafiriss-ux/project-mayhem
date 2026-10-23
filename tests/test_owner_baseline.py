"""Phase 4 owner baseline (ADR-0067 D3.4, D-091).

Before step 2 the owner's decisions were fingerprinted on unchanged ``main``
(commit 39aee23): for each DailyCoach golden, the ``days`` section, which holds every
morning's return value, Telegram text and event sequence; and the whole governance
golden. Phase 4 changes how the database stores athletes, never what the owner is told.

A step may rewrite the ``tables`` section of a DailyCoach golden (a new column, for
example) but must leave these fingerprints alone. If one changes, the step changed the
owner's behaviour: stop and ask Zaf before updating it (ADR-0067 D3.4).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"

# sha256 of json.dumps(golden["days"], sort_keys=True, ensure_ascii=False).
# Baseline 39aee23; re-fingerprinted by ADR-0068 (D-106) and then by D-105 (SG-01/SG-06),
# both approved by Zaf 2026-10-17: the owner's mornings became stricter on purpose
# (H2_MISSING with no HRV baseline, ADR-0065 cap on H4 days, baselines without today).
# After D-105 no session changes against D-106; only the logged baselines and texts do,
# and a first morning no longer sends the "check database health" RHR alert.
# D-112 (SG-11), approved by Zaf: with no load history TSB reaches governance as None, so the
# first mornings also log DATA_MISSING_CONSERVATIVE_H4; no session or Telegram text changes.
# D-127 (OW-M1), approved by Zaf 2026-10-23: the Telegram texts gain Markdown escapes (\_ \* \`
# \[) and nothing else; no session, lock or number changes. Before it, Telegram refused 33 of
# the 54 messages in these goldens; after it, none.
# D-132 (OW-F1), ADR-0069 §1 (Accepted by Zaf 2026-10-23): TSB is computed after the morning's
# sync stored yesterday's run, so it is lower; H4 now fires on 9/3, 10/3, 13/3, 14/3 (and more
# in the three-week scenario). Every changed session is shorter or EASY; none is looser.
# D-137 (P4-01), ADR-0069 §5 (Accepted by Zaf 2026-10-23): a missing HRV, RHR or TSB that lasts
# 24 hours sends one "missing data" alert (3/3 for the HRV baseline, 6/3 for the RHR of the outage).
# No session, lock or other text changes.
# D-138 (P4-02), ADR-0069 §6 (Accepted by Zaf 2026-10-23): a day whose only gate is missing data
# shows DATA_MISSING_CONSERVATIVE_* and no longer HARD_STOP_SAFETY_GATES in "Why this decision"
# (the first mornings without an HRV baseline). No session, ceiling or volume changes.
_DAILY_COACH_DAYS = {
    "garmin_outage": "41f232c04e69f906289909417aafe186a6a478a2644431401901e21681d84444",
    "persistence_failure": "f90b643d5102145ea1407db0df636c9fdbd76f1940a55d73d627285981bec282",
    "three_weeks_weekly_plan": "d277adb5c6979c298e1767355065e36418062f0b6b6df8bd5cd3c50166f2133a",
    "two_weeks_worker": "8d0e76a001c5057253b1a13ef8e65d8067a974f0d2ca087f7b449a5dbc01956a",
}
# sha256 of json.dumps(governance_golden, sort_keys=True, ensure_ascii=False) at 39aee23.
_GOVERNANCE = "3c632d5e10c546fde441b965dfb138e816372dcf9aa8f5472b9e984f9d8359b1"


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@pytest.mark.unit
@pytest.mark.parametrize("scenario", sorted(_DAILY_COACH_DAYS))
def test_owner_mornings_match_the_phase4_baseline(scenario: str) -> None:
    golden = json.loads((_FIXTURES / "daily_coach_golden" / f"{scenario}.json").read_text(encoding="utf-8"))
    assert _fingerprint(golden["days"]) == _DAILY_COACH_DAYS[scenario], (
        f"{scenario}: the owner's mornings differ from the Phase 4 baseline (main 39aee23). "
        "A Phase 4 step must not change them; ask Zaf before updating (ADR-0067 D3.4)."
    )


@pytest.mark.unit
def test_owner_governance_decisions_match_the_phase4_baseline() -> None:
    golden = json.loads((_FIXTURES / "governance_golden.json").read_text(encoding="utf-8"))
    assert _fingerprint(golden) == _GOVERNANCE, (
        "governance_golden.json differs from the Phase 4 baseline (main 39aee23); "
        "ask Zaf before updating (ADR-0067 D3.4)."
    )
