"""
Module count budget gate — replaces hardcoded literal in ci.yml.
ADR-0028 / AGENTS.md §16.11 / T4-27-C.

AT-06: one way to count (pkgutil, as the CI job does: modules and subpackages,
without dunder files) and one ceiling (MODULE_COUNT_CEILING, read at call time).
"""

from __future__ import annotations

import pkgutil

import pytest

import titan
from titan.config import thresholds


def titan_modules() -> list[str]:
    """Modules and subpackages of ``titan``, the count every budget gate uses."""
    return [
        module.name
        for module in pkgutil.walk_packages(titan.__path__, "titan.")
        if "__" not in module.name
    ]


@pytest.mark.unit
def test_module_count_within_budget() -> None:
    count = len(titan_modules())
    ceiling = thresholds.MODULE_COUNT_CEILING
    assert count <= ceiling, (
        f"Module count {count} exceeds ceiling {ceiling} "
        "(AGENTS.md §16.11). Retire or merge modules, or raise ceiling via ADR."
    )


@pytest.mark.unit
def test_module_ceiling_constant_is_positive_integer() -> None:
    """Smoke guard: the ceiling must be a positive integer (import sanity)."""
    assert isinstance(thresholds.MODULE_COUNT_CEILING, int)
    assert thresholds.MODULE_COUNT_CEILING > 0
