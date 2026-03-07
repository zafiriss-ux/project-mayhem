"""
CI check: every titan/science module must expose a MODULE_VERSION constant
that is a valid semver string (MAJOR.MINOR.PATCH).

Enforces T4-30 (AGENTS.md §16.8): algorithm-breaking changes must be
distinguishable from patches via an independent version number on each module.
"""

import importlib
import re

import pytest

# Canonical list of all science modules (excluding __init__).
# Update this list whenever a new module is added to titan/science/.
SCIENCE_MODULES = [
    "acwr_engine",
    "adaptive_memory",
    "adaptive_priority_lock",
    "automated_periodization",
    "autonomic_engine",
    "biomechanics",
    "critical_speed",
    "data_sanity",
    "data_trust",
    "drift_engine",
    "durability_engine",
    "efficiency_engine",
    "fatigue_engine",
    "glycogen_model",
    "governance_contracts",
    "governance_engine",
    "hrv_engine",
    "injury_risk_model",
    "intensity_governor",
    "lactate_logic",
    "load_prediction_shadow",
    "ml_safety",
    "outcome_tracker",
    "override_signal",
    "physiological_bounds",
    "rcp_engine",
    "readiness_engine",
    "trimp_engine",
    "tsb_engine",
    "volume_load_gauge",
]

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@pytest.mark.parametrize("mod_name", SCIENCE_MODULES)
def test_module_has_version_constant(mod_name: str) -> None:
    """Each science module must expose MODULE_VERSION."""
    mod = importlib.import_module(f"titan.science.{mod_name}")
    assert hasattr(mod, "MODULE_VERSION"), (
        f"titan.science.{mod_name} is missing MODULE_VERSION. "
        "Add MODULE_VERSION = \"1.0.0\" (or current version) at module level."
    )


@pytest.mark.parametrize("mod_name", SCIENCE_MODULES)
def test_module_version_is_valid_semver(mod_name: str) -> None:
    """MODULE_VERSION must be a valid MAJOR.MINOR.PATCH semver string."""
    mod = importlib.import_module(f"titan.science.{mod_name}")
    version = getattr(mod, "MODULE_VERSION", None)
    assert isinstance(version, str), (
        f"titan.science.{mod_name}.MODULE_VERSION must be a str, got {type(version)}"
    )
    assert _SEMVER_RE.match(version), (
        f"titan.science.{mod_name}.MODULE_VERSION={version!r} is not valid semver "
        "(expected MAJOR.MINOR.PATCH, e.g. \"1.0.0\")"
    )


def test_all_science_modules_covered() -> None:
    """
    Sanity check: the SCIENCE_MODULES list in this test must match the actual
    modules present in titan/science/. Fails when a module is added without
    updating this list.
    """
    from pathlib import Path

    science_dir = Path(__file__).parent.parent / "titan" / "science"
    on_disk = {
        p.stem
        for p in science_dir.glob("*.py")
        if p.name != "__init__.py"
    }
    in_list = set(SCIENCE_MODULES)

    missing_from_list = on_disk - in_list
    assert not missing_from_list, (
        f"These science modules exist on disk but are NOT in SCIENCE_MODULES: "
        f"{sorted(missing_from_list)}. Add them and give them MODULE_VERSION."
    )

    missing_from_disk = in_list - on_disk
    assert not missing_from_disk, (
        f"These modules are in SCIENCE_MODULES but NOT on disk: "
        f"{sorted(missing_from_disk)}. Remove stale entries."
    )
