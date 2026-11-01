"""SD-06 (ADR-0081): the morning rationale names the gates that were not measured even when a lock
or gate triggers, and no bare lock code reaches the message.

Only the wording changes: session, zone, volume, locks and gate statuses stay the same.
Synthetic data only.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from titan.config.thresholds import CANONICAL_LOCK_CODES
from titan.science import governance_engine as ge
from titan.science.governance_engine import GATE_RATIONALE_TEMPLATES, GovernanceEngine

_NEW_TEMPLATES = (
    "INTENSITY_GATE_RED",
    "INTENSITY_GATE_YELLOW",
    "HARD_STOP_SAFETY_GATES",
    "DATA_MISSING_CONSERVATIVE_H2",
    "DATA_MISSING_CONSERVATIVE_H3",
    "DATA_MISSING_CONSERVATIVE_H4",
    "DATA_MISSING_CONSERVATIVE_H5",
    "DATA_VOID_CONSERVATIVE",
    "FAIL_SAFE_LOCK",
)


def _context(**changes) -> dict:
    base = {
        "today_hrv": 60.0,
        "baseline_hrv": 60.0,
        "hrv_std_dev": 5.0,
        "today_rhr": 50,
        "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "subjective_fatigue_score": 2,
        "subjective_fatigue_measured": True,
        "injury_flag": False,
        "sleep_score": 80,
        "readiness_score": 75.0,
        "acwr": 1.1,
        "glycogen_debt": 2.0,
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
    }
    base.update(changes)
    return {k: v for k, v in base.items() if v is not ...}


def _apply(context: dict, session_type: str = "EASY") -> dict:
    return GovernanceEngine().apply_constraints({"session_type": session_type, "max_zone": 2}, context)


def test_a_lock_still_names_the_unmeasured_gate():
    """Two indicators (sleep, readiness) trigger the 2-of-4 downgrade; H1 has no source."""
    result = _apply(_context(injury_flag=None, sleep_score=40, readiness_score=40.0), "TEMPO")
    assert "READINESS_2OF4_DOWNGRADE" in result["governance_locks_applied"]
    reason = result["decision_rationale"]["primary_reason"]
    assert reason.endswith(" Not measured: H1.")
    assert reason.startswith("At least 2 of 4 readiness indicators triggered")


def test_missing_hrv_reads_as_a_sentence_and_names_h2():
    result = _apply(_context(today_hrv=None))
    assert "DATA_MISSING_CONSERVATIVE_H2" in result["governance_locks_applied"]
    reason = result["decision_rationale"]["primary_reason"]
    assert reason != "DATA_MISSING_CONSERVATIVE_H2"
    assert reason.startswith("HRV or its baseline not available")
    assert reason.endswith(" Not measured: H2.")


@pytest.mark.parametrize(
    ("changes", "gate"),
    [
        ({"today_hrv": math.nan}, "H2"),
        ({"baseline_hrv": 0.0}, "H2"),
        ({"today_rhr": math.nan}, "H3"),
        ({"tsb_value": math.nan}, "H4"),
        ({"subjective_fatigue_score": "abc"}, "H5"),
    ],
)
def test_a_value_the_gate_counts_as_missing_is_named_behind_another_lock(changes, gate):
    """NaN, baseline <= 0 or not a number: the gate applies its missing-data lock while the
    finding still reads CLEAR (SD-17, out of scope). The message must name the gate anyway."""
    result = _apply(_context(sleep_score=40, readiness_score=40.0, **changes), "TEMPO")
    locks = result["governance_locks_applied"]
    assert f"DATA_MISSING_CONSERVATIVE_{gate}" in locks
    assert locks.index("READINESS_2OF4_DOWNGRADE") < locks.index(f"DATA_MISSING_CONSERVATIVE_{gate}")
    reason = result["decision_rationale"]["primary_reason"]
    match = re.search(r"Not measured: ([H1-5, ]+)\.$", reason)
    assert match is not None, reason
    assert gate in match.group(1).split(", ")


def test_every_canonical_lock_code_has_a_template():
    assert sorted(set(CANONICAL_LOCK_CODES) - set(GATE_RATIONALE_TEMPLATES)) == []


def test_every_lock_the_engine_applies_is_canonical():
    source = Path(ge.__file__).read_text(encoding="utf-8")
    applied = set(re.findall(r'applied_locks\.append\("([A-Z0-9_]+)"\)', source))
    assert applied
    assert sorted(applied - set(CANONICAL_LOCK_CODES)) == []


def test_an_unknown_code_is_never_shown_alone():
    text = GovernanceEngine._format_template("SOME_NEW_LOCK")
    assert "SOME_NEW_LOCK" in text
    assert text != "SOME_NEW_LOCK"


@pytest.mark.parametrize("code", _NEW_TEMPLATES)
def test_the_new_templates_carry_no_numbers(code):
    assert not re.search(r"\d", GATE_RATIONALE_TEMPLATES[code])


def test_only_the_wording_changes():
    """Same inputs as the first test: the decision itself is the downgrade, as before."""
    result = _apply(_context(injury_flag=None, sleep_score=40, readiness_score=40.0), "TEMPO")
    statuses = {f["gate"]: f["status"] for f in result["decision_rationale"]["gate_findings"]}
    assert statuses["H1"] == "UNKNOWN"
    assert all(statuses[g] == "CLEAR" for g in ("H2", "H3", "H4", "H5"))
    assert result["session_type"] != "TEMPO"


def test_the_telegram_line_carries_the_unmeasured_gates():
    from titan.integrations.telegram_bot import TitanTelegramBot

    sent: list[str] = []
    bot = TitanTelegramBot.__new__(TitanTelegramBot)
    bot.send_message = sent.append  # type: ignore[method-assign]
    result = _apply(_context(today_hrv=None))
    bot.send_daily_coaching({"primary_reason": result["decision_rationale"]["primary_reason"]})
    assert "Not measured: H2." in sent[0]
    assert "DATA\\_MISSING" not in sent[0] and "DATA_MISSING" not in sent[0]
