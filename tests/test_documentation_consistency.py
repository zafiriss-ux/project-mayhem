"""Documentation consistency invariants (T4-21 / ADR-0024)."""

from __future__ import annotations

import ast
import pathlib
import pkgutil
import re

import pytest

import titan
from titan.config.evidence_registry import EVIDENCE_REGISTRY
from titan.config.thresholds import CANONICAL_LOCK_CODES

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GOVERNANCE_ENGINE = REPO_ROOT / "titan" / "science" / "governance_engine.py"
THRESHOLDS_FILE = REPO_ROOT / "titan" / "config" / "thresholds.py"
ADR_DIR = REPO_ROOT / "docs" / "adr"
ADR_INDEX = ADR_DIR / "README.md"
TECH_DEBT = REPO_ROOT / "TECHNICAL_DEBT.md"


def _parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _collect_governance_lock_codes() -> set[str]:
    tree = _parse(GOVERNANCE_ENGINE)
    codes: set[str] = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "applied_locks"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            codes.add(node.args[0].value)

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_gate_event"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and node.args[1].value.endswith("_LOCK")
        ):
            codes.add(node.args[1].value)

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "GovernanceDecision"
        ):
            for keyword in node.keywords:
                if keyword.arg != "applied_locks" or not isinstance(keyword.value, ast.List):
                    continue
                for element in keyword.value.elts:
                    if isinstance(element, ast.Constant) and isinstance(element.value, str):
                        codes.add(element.value)

    return codes


def _collect_threshold_constant_names() -> set[str]:
    tree = _parse(THRESHOLDS_FILE)
    names: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                names.add(target.id)

    return names


def _extract_adr_index_ids(readme_text: str) -> set[str]:
    ids: set[str] = set()
    for line in readme_text.splitlines():
        match = re.match(r"^\| \[(\d{4})\]\([^)]*\) \|", line)
        if match:
            ids.add(match.group(1))
    return ids


def _normalize_debt_status(raw: str) -> str:
    status = raw.upper()
    if "RESOLVED" in status:
        return "RESOLVED"
    if "OPEN" in status:
        return "OPEN"
    if status.strip() in {"", "—", "-"}:
        return "OTHER"
    return "RESOLVED"


def _extract_heading_statuses(tech_debt_text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in tech_debt_text.splitlines():
        match = re.match(r"^###\s+(T\d+-\d+)\s+·.*\b(OPEN|RESOLVED)\b", line)
        if match:
            statuses[match.group(1)] = match.group(2)
    return statuses


def _extract_tracking_table_statuses(tech_debt_text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in tech_debt_text.splitlines():
        line = line.strip()
        if not line.startswith("| T"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        item = parts[0]
        completed_col = parts[1]
        if not re.match(r"^T\d+-\d+$", item):
            continue
        statuses[item] = _normalize_debt_status(completed_col)
    return statuses


@pytest.mark.unit
def test_governance_lock_codes_match_canonical_list() -> None:
    emitted = _collect_governance_lock_codes()

    # ADR-0053 Stage 2 landed: DATA_VOID_CONSERVATIVE is now emitted by
    # governance_engine.py — pending set is empty.
    _stage1_registered_pending_stage2: frozenset[str] = frozenset()

    canonical_active = set(CANONICAL_LOCK_CODES) - _stage1_registered_pending_stage2

    assert emitted == canonical_active, (
        "Governance lock codes drift detected.\n"
        f"Missing from thresholds.CANONICAL_LOCK_CODES: {sorted(emitted - canonical_active)}\n"
        f"Extra in thresholds.CANONICAL_LOCK_CODES (not in pending set): "
        f"{sorted(canonical_active - emitted)}"
    )


@pytest.mark.unit
def test_threshold_constants_have_evidence_registry_entries() -> None:
    threshold_names = _collect_threshold_constant_names()
    excluded = {"CANONICAL_LOCK_CODES"}
    threshold_names -= excluded

    missing = sorted(name for name in threshold_names if name not in EVIDENCE_REGISTRY)

    assert not missing, (
        "Threshold constants missing evidence_registry entries: "
        + ", ".join(missing)
    )


@pytest.mark.unit
def test_adr_index_matches_adr_files() -> None:
    adr_files = {
        path.stem.split("-")[0]
        for path in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")
    }
    indexed = _extract_adr_index_ids(ADR_INDEX.read_text(encoding="utf-8"))

    assert indexed == adr_files, (
        "ADR README index drift detected.\n"
        f"Missing rows in docs/adr/README.md: {sorted(adr_files - indexed)}\n"
        f"Stale rows in docs/adr/README.md: {sorted(indexed - adr_files)}"
    )


@pytest.mark.unit
def test_technical_debt_tracking_table_matches_heading_status() -> None:
    text = TECH_DEBT.read_text(encoding="utf-8")
    heading_status = _extract_heading_statuses(text)
    table_status = _extract_tracking_table_statuses(text)

    missing_in_table = sorted(item for item in heading_status if item not in table_status)
    mismatched = sorted(
        item
        for item, status in heading_status.items()
        if item in table_status and _normalize_debt_status(status) != table_status[item]
    )

    assert not missing_in_table, (
        "Tracking table missing debt items present in headings: "
        + ", ".join(missing_in_table)
    )
    assert not mismatched, (
        "Tracking table statuses differ from item headings for: "
        + ", ".join(mismatched)
    )


@pytest.mark.unit
def test_module_count_within_budget() -> None:
    """Module count must not exceed 80 (Phase 8 ceiling; +2 for T5-16-B coaching_pipeline.py + coaching_scheduler.py structural extraction — Architect approved 2026-03-17; +1 for T5-12 Pass 2a biometric_source.py ADR-0050 D4 boundary contract — Architect approved 2026-04-10; +1 for HD-09 threshold_adapter.py ADR-0052 Stage 2 — Architect approved 2026-04-12; +1 for T5-100 biometric_router.py ADR-0055 Garmin fallback — Architect approved 2026-05-09; +1 for ADR-0057 titan.worker effect-runner — Architect approved 2026-05-23; +2 for titan.observability package + titan.observability.metrics — Phase 18 TD-11 metrics sink — Architect approved 2026-05-23; +1 for ADR-0058 engine_registry.py — Architect approved 2026-05-24; +1 for TD-08 schema.py SQLAlchemy Core descriptor — Architect approved 2026-06-01; +1 for ADR-0058 Phase B effect_bus.py — Architect approved 2026-06-02; +1 for P15-ARCH5 settings.py pydantic-settings migration — Architect approved 2026-06-05; +1 for P27-04 rollback_gate.py calibration rollback guard — 2026-06-09)."""
    modules = [
        module.name
        for module in pkgutil.walk_packages(titan.__path__, "titan.")
        if "__" not in module.name
    ]

    assert len(modules) <= 80, f"Complexity budget exceeded: {len(modules)} modules"
