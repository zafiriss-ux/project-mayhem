"""T5-37/T5-38 Migration Unit 4: Pattern 4 gate + validating meta-test."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PATTERN_4_LITERAL_DENYLIST_BY_MODULE: dict[str, frozenset[str]] = {
    "titan/science/acwr_engine.py": frozenset({"0.5", "0.8", "1.0", "1.3", "1.5", "1.7"}),
    "titan/science/adaptive_memory.py": frozenset({"1.08", "24", "36", "48", "72"}),
    "titan/science/durability_engine.py": frozenset({"2", "5", "8", "85", "88", "90", "93", "95", "96", "98"}),
    "titan/science/fatigue_engine.py": frozenset({"5"}),
    "titan/science/governance_engine.py": frozenset({"0.70", "0.80", "0.7", "0.8"}),
    "titan/science/intensity_governor.py": frozenset({"1.3", "1.5", "3.5", "4.0", "5.0", "6.0", "40", "55"}),
    "titan/science/lactate_logic.py": frozenset({"3.0", "6.0", "7.0", "78.0"}),
    "titan/science/volume_load_gauge.py": frozenset({"-30", "0.7", "0.8", "1.3", "1.5", "4", "7"}),
}


def _numeric_literal_tokens(source: str) -> list[tuple[int, str]]:
    """Collect source-level numeric literal tokens, including unary negatives."""

    tokens: list[tuple[int, str]] = []
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            source_segment = ast.get_source_segment(source, node)
            if source_segment is not None:
                tokens.append((node.lineno, source_segment.strip()))
            continue

        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, int | float)
        ):
            source_segment = ast.get_source_segment(source, node)
            if source_segment is not None:
                tokens.append((node.lineno, source_segment.strip()))

    return tokens


def _assert_category_a_literal_regression_presence(
    module_sources: dict[str, str],
    denylist_by_module: dict[str, frozenset[str]],
) -> None:
    """Fail when known Category A extracted literals reappear inline."""

    violations: list[str] = []

    for module_path, denied_literals in denylist_by_module.items():
        source = module_sources[module_path]
        inline_tokens = _numeric_literal_tokens(source)

        for lineno, token in inline_tokens:
            if token in denied_literals:
                violations.append(
                    f"{module_path}:{lineno} reintroduced Category A literal {token!r}"
                )

    if violations:
        raise AssertionError(
            "Category A literal regression presence check failed:\n"
            + "\n".join(sorted(violations))
        )


@pytest.mark.unit
@pytest.mark.governance
def test_ci_gate_category_a_literal_regression_presence_check() -> None:
    """CI gate: denylist Category A literals must not be reintroduced inline."""

    module_sources = {
        module_path: Path(module_path).read_text(encoding="utf-8")
        for module_path in _PATTERN_4_LITERAL_DENYLIST_BY_MODULE
    }

    _assert_category_a_literal_regression_presence(
        module_sources,
        _PATTERN_4_LITERAL_DENYLIST_BY_MODULE,
    )


@pytest.mark.unit
@pytest.mark.governance
def test_meta_category_a_literal_regression_presence_gate_rejects_known_bad_input() -> None:
    """Validating meta-test: gate fails when a denied literal is reintroduced."""

    bad_module_sources = {
        "titan/science/acwr_engine.py": """
def injury_risk(acwr: float) -> str:
    return \"red\" if acwr >= 1.5 else \"green\"
""",
    }
    denylist = {
        "titan/science/acwr_engine.py": _PATTERN_4_LITERAL_DENYLIST_BY_MODULE[
            "titan/science/acwr_engine.py"
        ],
    }

    with pytest.raises(
        AssertionError,
        match="Category A literal regression presence check failed",
    ):
        _assert_category_a_literal_regression_presence(bad_module_sources, denylist)
