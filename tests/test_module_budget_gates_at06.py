"""AT-06: every module-budget gate counts the same way and reads the same ceiling.

Before the fix, tests/test_complexity_budget.py counted .py files with `find`
(77, subpackages left out) and tests/test_documentation_consistency.py compared
against a literal 90, while the CI job counted with pkgutil (89) against
MODULE_COUNT_CEILING. Lowering the constant left both tests green.
"""

from __future__ import annotations

import os
import pkgutil
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import tests.test_complexity_budget as budget
import tests.test_documentation_consistency as docs
import titan
from titan.config import thresholds

REPO_ROOT = Path(__file__).resolve().parents[1]

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


def test_the_hard_audit_counts_like_the_other_gates(tmp_path: Path) -> None:
    # Run the script's own MODULE_COUNT= line, with `python` meaning this interpreter.
    script = (REPO_ROOT / "scripts" / "hard_audit.sh").read_text(encoding="utf-8")
    match = re.search(r"^MODULE_COUNT=\$\(.*?\)(?:\n|$)", script, re.MULTILINE | re.DOTALL)
    assert match, "hard_audit.sh has no MODULE_COUNT= line"
    (tmp_path / "python").symlink_to(sys.executable)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        ["bash", "-c", match.group(0) + 'printf %s "$MODULE_COUNT"'],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60, check=True,
    )
    assert result.stdout == str(len(budget.titan_modules()))
