"""T5-37/T5-38 Migration Unit 3: Pattern 3 gate + validating meta-test."""

from __future__ import annotations

from pathlib import Path

import pytest

_PATTERN_3_SOURCE_MODULES: tuple[str, ...] = (
    "titan/main.py",
    "titan/core/athlete.py",
    "titan/core/database.py",
    "titan/core/equipment.py",
    "titan/core/periodization.py",
    "titan/core/persistence.py",
    "titan/core/structured_events.py",
    "titan/features/nutrition_optimizer.py",
    "titan/features/optimal_time_calculator.py",
    "titan/features/weekly_planner.py",
    "titan/orchestration/contracts.py",
    "titan/orchestration/daily_coach.py",
)


def _assert_mirrored_test_file_path_contract(
    repo_root: Path,
    source_modules: tuple[str, ...],
) -> None:
    """Fail when source modules do not have mirrored test-file paths."""

    violations: list[str] = []
    for source_module in source_modules:
        source_path = repo_root / source_module
        if not source_path.exists():
            violations.append(f"missing source module: {source_module}")
            continue

        relative_source = source_path.relative_to(repo_root / "titan")
        expected_test = (
            repo_root
            / "tests"
            / "titan"
            / relative_source.parent
            / f"test_{relative_source.stem}.py"
        )
        if not expected_test.exists():
            violations.append(
                f"{source_module} -> missing mirrored test {expected_test.relative_to(repo_root)}"
            )

    if violations:
        raise AssertionError(
            "Mirrored test-file path contract violations:\n" + "\n".join(violations)
        )


def test_ci_gate_mirrored_test_file_path_contract() -> None:
    """CI gate: in-scope source modules must have mirrored tests/titan/test_<module>.py paths."""

    _assert_mirrored_test_file_path_contract(Path("."), _PATTERN_3_SOURCE_MODULES)


def test_meta_mirrored_test_file_path_contract_gate_rejects_known_bad_input(tmp_path: Path) -> None:
    """Validating meta-test: gate fails when a mirrored test path is missing."""

    source_module = "titan/core/athlete.py"
    bad_repo_root = tmp_path / "repo"
    (bad_repo_root / "titan" / "core").mkdir(parents=True)
    (bad_repo_root / "titan" / "core" / "athlete.py").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="Mirrored test-file path contract violations"):
        _assert_mirrored_test_file_path_contract(bad_repo_root, (source_module,))
