"""
Module count budget gate — replaces hardcoded literal in ci.yml.
ADR-0028 / AGENTS.md §16.11 / T4-27-C.
"""

from __future__ import annotations

import subprocess

from titan.config.thresholds import MODULE_COUNT_CEILING


def test_module_count_within_budget() -> None:
    result = subprocess.run(
        [
            "find",
            "titan/",
            "-name",
            "*.py",
            "!",
            "-name",
            "__init__.py",
            "!",
            "-name",
            "__main__.py",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    modules = [line for line in result.stdout.strip().split("\n") if line]
    count = len(modules)
    assert count <= MODULE_COUNT_CEILING, (
        f"Module count {count} exceeds ceiling {MODULE_COUNT_CEILING} "
        "(AGENTS.md §16.11). Retire or merge modules, or raise ceiling via ADR."
    )


def test_module_ceiling_constant_is_positive_integer() -> None:
    """Smoke guard: the ceiling must be a positive integer (import sanity)."""
    assert isinstance(MODULE_COUNT_CEILING, int)
    assert MODULE_COUNT_CEILING > 0
