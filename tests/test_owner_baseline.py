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
_DAILY_COACH_DAYS = {
    "garmin_outage": "75ac6a953f5b24e0ff03c17ccb92be4cc94f9fa13a63425a408f2c8c82b99973",
    "persistence_failure": "a7682c4ad4e80d6d10eb5f89252128b2030e7a1a99e2fca18bb99fac666ef23e",
    "three_weeks_weekly_plan": "600f05c9bc54cc08ef3511befb93b668bc9edcc2d47eda79f9377644e9c64d9e",
    "two_weeks_worker": "225cb747d02172d59207d4ab553efbd34a620267757ba6d697f601c62da3fda4",
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
