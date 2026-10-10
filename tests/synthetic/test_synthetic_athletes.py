"""Synthetic athlete validation (plan task 12, D-031).

Six synthetic athletes live six ordinary weeks through the real worker morning
(``titan.worker._run_morning``), then one scenario week each. Every morning is checked
against the consistency rules in ``tests/synthetic/rules.py``.

Known findings are listed in ``KNOWN`` with their id from
``docs/validation/synthetic-athlete-report.md``. Two things are asserted:

* every violation is explained by a known finding (a new one fails the build), and
* every known finding still reproduces (the PR that fixes one removes its entry).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.synthetic.rules import RULES, Violation
from tests.synthetic.world import PROFILES, SCENARIOS, Outcome, World

pytestmark = [pytest.mark.slow, pytest.mark.integration]

Known = tuple[str, Callable[[Violation], bool]]


def _detail_starts(prefix: str) -> Callable[[Violation], bool]:
    return lambda v: v[3].startswith(prefix)


def _everything(_v: Violation) -> bool:
    return True


# rule -> the findings that explain its violations today (report ids).
KNOWN: dict[str, list[Known]] = {
    "rest_has_no_volume": [("SV-03", _detail_starts("EASY with 0 km"))],
    "reduction_reduces_volume": [("SV-04", _everything)],
    "governance_never_raises_intensity": [
        ("SV-05", _detail_starts("LONG_RUN -> PROGRESSIVE")),
        ("SV-03", _detail_starts("REST -> EASY")),
    ],
    "stored_runs_are_runnable": [("SV-17", lambda v: v[1] == "duration_in_minutes")],
    "risk_never_more_aggressive": [("SV-03", _detail_starts("EASY vs ordinary REST"))],
    "acwr_known_after_six_weeks": [("SV-01", _everything)],
    "missing_reading_not_replaced": [("SV-06", _everything)],
    "telegram_numbers_are_formatted": [("SV-07", _everything)],
}


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory):
    mp = pytest.MonkeyPatch()
    # Placeholders only: GarminSync.connect is replaced, nothing leaves the process.
    mp.setenv("GARMIN_EMAIL", "synthetic@example.invalid")
    mp.setenv("TELEGRAM_BOT_TOKEN", "")
    mp.setenv("TELEGRAM_CHAT_ID", "1")
    w = World(mp, Path(tmp_path_factory.mktemp("synthetic")))
    yield w
    w.close()
    mp.undo()


@pytest.fixture(scope="module")
def outcomes(world: World) -> list[Outcome]:
    return [world.run(p, s) for p in PROFILES for s in SCENARIOS]


def test_matrix_covers_every_profile_and_scenario(outcomes: list[Outcome]) -> None:
    assert len(outcomes) == len(PROFILES) * len(SCENARIOS)
    assert all(len(o.mornings) == 7 for o in outcomes)
    assert all(o.last.session for o in outcomes), "a morning produced no decision"


def test_every_rule_has_a_ledger_entry_or_is_clean() -> None:
    assert set(KNOWN) <= set(RULES)


@pytest.mark.parametrize("rule", sorted(RULES))
def test_no_unexplained_violation(rule: str, outcomes: list[Outcome]) -> None:
    known = KNOWN.get(rule, [])
    unexplained = [v for v in RULES[rule](outcomes) if not any(match(v) for _, match in known)]
    assert not unexplained, f"{rule}: {len(unexplained)} new violation(s), first: {unexplained[:3]}"


@pytest.mark.parametrize(
    ("rule", "finding"),
    [(rule, sv) for rule, entries in sorted(KNOWN.items()) for sv, _ in entries],
)
def test_known_finding_still_reproduces(rule: str, finding: str, outcomes: list[Outcome]) -> None:
    match = dict(KNOWN[rule])[finding]
    assert any(match(v) for v in RULES[rule](outcomes)), (
        f"{finding} no longer reproduces under {rule}: remove it from KNOWN and the report"
    )


def test_runs_are_deterministic(world: World, outcomes: list[Outcome]) -> None:
    """The same athlete and scenario give the same decisions, texts and stored rows."""
    by_key = {(o.profile.key, o.scenario.key): o for o in outcomes}
    profiles = {p.key: p for p in PROFILES}
    scenarios = {s.key: s for s in SCENARIOS}
    for p_key, s_key in [("steady_m", "ordinary_week"), ("senior_m", "recovery_combo"),
                         ("loading_m", "garmin_out_3")]:
        first = by_key[(p_key, s_key)]
        again = world.run(profiles[p_key], scenarios[s_key], tag="_again")
        for a, b in zip(first.mornings, again.mornings, strict=True):
            assert (a.session, a.trace, a.telegram, a.metrics_row) == \
                   (b.session, b.trace, b.telegram, b.metrics_row), f"{p_key}/{s_key} {a.date}"
        assert first.runs == again.runs
