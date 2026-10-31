"""AT-06: every module-budget gate counts the same way and reads the same ceiling.

Before the fix, tests/test_complexity_budget.py counted .py files with `find`
(77, subpackages left out) and tests/test_documentation_consistency.py compared
against a literal 90, while the CI job counted with pkgutil (89) against
MODULE_COUNT_CEILING. Lowering the constant left both tests green.
"""

from __future__ import annotations

import pkgutil
from collections.abc import Callable

import pytest

import tests.test_complexity_budget as budget
import tests.test_documentation_consistency as docs
import titan
from titan.config import thresholds

GATES: dict[str, Callable[[], None]] = {
    "test_complexity_budget": budget.test_module_count_within_budget,
    "test_documentation_consistency": docs.test_module_count_within_budget,
}


@pytest.mark.parametrize("gate", sorted(GATES))
def test_a_gate_fails_when_the_count_is_one_over_the_ceiling(
    gate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(thresholds, "MODULE_COUNT_CEILING", len(budget.titan_modules()) - 1)
    with pytest.raises(AssertionError):
        GATES[gate]()


@pytest.mark.parametrize("gate", sorted(GATES))
def test_a_gate_passes_at_exactly_the_ceiling(gate: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thresholds, "MODULE_COUNT_CEILING", len(budget.titan_modules()))
    GATES[gate]()


def test_the_count_matches_the_ci_job() -> None:
    # Same expression as the "Enforce titan module count ceiling" step in ci.yml.
    ci_count = len(
        [
            module.name
            for module in pkgutil.walk_packages(titan.__path__, prefix="titan.")
            if "__" not in module.name
        ]
    )
    assert len(budget.titan_modules()) == ci_count
    assert "titan.core.repositories" in budget.titan_modules(), "subpackages count too"
