"""T5-37/T5-38 Migration Unit 2: Pattern 2 gate + validating meta-test."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _assert_evidence_registry_coverage_parity(
    thresholds_source: str,
    registry_source: str,
    *,
    thresholds_label: str,
    registry_label: str,
) -> None:
    """Fail when a threshold constant has no matching EVIDENCE_REGISTRY key."""

    threshold_names = {
        node.targets[0].id
        for node in ast.walk(ast.parse(thresholds_source))
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.isupper()
    }
    threshold_names.discard("CANONICAL_LOCK_CODES")

    registry_keys: set[str] = set()
    registry_tree = ast.parse(registry_source)
    for node in registry_tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            target_name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value
        else:
            continue

        if target_name != "EVIDENCE_REGISTRY" or not isinstance(value_node, ast.Dict):
            continue

        for key in value_node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                registry_keys.add(key.value)

    missing = sorted(name for name in threshold_names if name not in registry_keys)
    if missing:
        raise AssertionError(
            f"{registry_label} is missing coverage for threshold constants from "
            f"{thresholds_label}: {', '.join(missing)}"
        )


@pytest.mark.unit
@pytest.mark.governance
def test_ci_gate_evidence_registry_coverage_parity() -> None:
    """CI gate: every threshold constant must have EVIDENCE_REGISTRY coverage."""

    thresholds_source = Path("titan/config/thresholds.py").read_text(encoding="utf-8")
    registry_source = Path("titan/config/evidence_registry.py").read_text(encoding="utf-8")

    _assert_evidence_registry_coverage_parity(
        thresholds_source,
        registry_source,
        thresholds_label="titan/config/thresholds.py",
        registry_label="titan/config/evidence_registry.py",
    )


@pytest.mark.unit
@pytest.mark.governance
def test_meta_evidence_registry_coverage_parity_gate_rejects_known_bad_input() -> None:
    """Validating meta-test: gate fails when one threshold constant is not registered."""

    bad_thresholds_source = """
THRESHOLD_ALPHA = 1.0
THRESHOLD_BETA = 2.0
"""
    bad_registry_source = """
EVIDENCE_REGISTRY = {
    "THRESHOLD_ALPHA": {"evidence_tier": "STRONG"},
}
"""

    with pytest.raises(
        AssertionError,
        match="is missing coverage for threshold constants",
    ):
        _assert_evidence_registry_coverage_parity(
            bad_thresholds_source,
            bad_registry_source,
            thresholds_label="known_bad_thresholds.py",
            registry_label="known_bad_evidence_registry.py",
        )
