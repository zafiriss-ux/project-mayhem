"""CLAUDE.md integrity invariants (T4-22 / ADR-0025)."""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
ADR_DIR = REPO_ROOT / "docs" / "adr"
TECH_DEBT = REPO_ROOT / "TECHNICAL_DEBT.md"
TITAN_DIR = REPO_ROOT / "titan"


def _claude_text() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def _tech_debt_text() -> str:
    return TECH_DEBT.read_text(encoding="utf-8")


def test_adr_count_in_claude_md_matches_files() -> None:
    claude = _claude_text()
    adr_files = {
        path.stem.split("-", 1)[0]
        for path in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")
    }
    mentioned = set(re.findall(r"^- `([0-9]{4})`", claude, flags=re.MULTILINE))

    assert mentioned == adr_files, (
        "CLAUDE.md ADR list drift detected.\n"
        f"Missing ADR entries in CLAUDE.md: {sorted(adr_files - mentioned)}\n"
        f"Stale ADR entries in CLAUDE.md: {sorted(mentioned - adr_files)}"
    )


def test_module_count_in_claude_md_matches_filesystem() -> None:
    claude = _claude_text()
    match = re.search(
        r"Main package \((\d+) modules, excl\. __init__/__main__\)",
        claude,
    )
    assert match, "CLAUDE.md does not contain the canonical titan module count line"

    declared = int(match.group(1))
    actual = len(
        [
            path
            for path in TITAN_DIR.rglob("*.py")
            if path.name not in {"__init__.py", "__main__.py"}
        ]
    )

    assert declared == actual, (
        "CLAUDE.md titan module count drift detected. "
        f"Declared: {declared}, actual: {actual}."
    )


def test_open_tier_items_not_misrepresented() -> None:
    claude = _claude_text()
    tech_debt = _tech_debt_text()

    open_phases = {
        match.group(1)
        for match in re.finditer(r"OPEN \(Phase\s+([0-9]+(?:\.[0-9]+)?)", tech_debt)
    }
    misrepresented = [
        phase for phase in sorted(open_phases) if f"Phase {phase} CLOSED" in claude
    ]

    assert not misrepresented, (
        "CLAUDE.md claims CLOSED phase(s) that still have OPEN debt items in "
        "TECHNICAL_DEBT.md: "
        + ", ".join(misrepresented)
    )


def _extract_historical_snapshot_count(claude_text: str) -> int:
    match = re.search(r"\*\*Historical snapshot:\*\*\s*(\d+) tests all green", claude_text)
    assert match, "CLAUDE.md historical snapshot line is missing"
    return int(match.group(1))


def _extract_key_file_paths(claude_text: str) -> list[str]:
    section_start = claude_text.find("## Key Files for Reference")
    assert section_start != -1, "CLAUDE.md key files section is missing"
    section = claude_text[section_start:]
    return re.findall(r"\| `([^`]+)` \|", section)


def test_historical_snapshot_matches_full_suite_collection(request) -> None:
    """Fail when CLAUDE.md test snapshot drifts from actual repository test count."""
    collected = request.session.testscollected
    if collected < 1500:
        pytest.skip(
            "Historical snapshot guard requires full-suite collection; run python -m pytest -q"
        )

    declared = _extract_historical_snapshot_count(_claude_text())
    # TD-TEST-02: tolerate ±50 tests to avoid brittleness on incremental additions.
    # A difference > 50 signals a significant divergence requiring a snapshot update.
    assert abs(actual := collected - declared) <= 50, (
        "CLAUDE.md historical snapshot diverged from actual by more than 50. "
        f"Declared: {declared}, collected this run: {collected} (delta {actual:+d}). "
        "Update the '**Historical snapshot:**' line in CLAUDE.md."
    )
    assert collected >= declared - 50, (
        "Test count regressed significantly below snapshot. "
        f"Declared: {declared}, collected: {collected}."
    )


def test_key_files_section_points_to_existing_paths() -> None:
    """Fail when CLAUDE.md references files that no longer exist in-repo."""
    paths = _extract_key_file_paths(_claude_text())
    missing = sorted(path for path in paths if not (REPO_ROOT / path).exists())

    assert not missing, (
        "CLAUDE.md key file references drift detected. Missing paths: "
        + ", ".join(missing)
    )


def test_claude_md_schema_version_matches_code() -> None:
    """CLAUDE.md SCHEMA_VERSION must match titan/core/database.py SCHEMA_VERSION."""
    import importlib

    db_module = importlib.import_module("titan.core.database")
    code_version = db_module.SCHEMA_VERSION
    content = _claude_text()
    assert f"SCHEMA_VERSION {code_version}" in content, (
        f"CLAUDE.md does not mention SCHEMA_VERSION {code_version}. "
        "Update the Database section of CLAUDE.md to match titan/core/database.py."
    )


def test_phase_state_label_consistent_between_tech_debt_and_claude_md() -> None:
    """Phase state in CLAUDE.md ROADMAP row must match TECHNICAL_DEBT.md canonical declaration.

    TECHNICAL_DEBT.md is the canonical source for phase state (e.g. ``Phase 8 OPEN``).
    CLAUDE.md carries a snapshot of that state in the Key Files ROADMAP row.  When one
    is updated without the other the two drift silently — this test makes that drift a
    CI failure instead.
    """
    tech_debt = _tech_debt_text()
    claude = _claude_text()

    # Canonical source: "Phase N OPEN —" at the start of a line in TECHNICAL_DEBT.md.
    td_matches = re.findall(r"^Phase (\S+) OPEN\b", tech_debt, re.MULTILINE)
    assert td_matches, (
        "TECHNICAL_DEBT.md has no top-level 'Phase N OPEN' declaration. "
        "Add a line of the form 'Phase N OPEN — <reason>' when a new phase opens."
    )
    canonical_phase = td_matches[-1]  # last declaration is the current open phase

    # Snapshot: ROADMAP.MD key-file row in CLAUDE.md must mention the same phase as OPEN.
    roadmap_row_match = re.search(
        r"\|\s*`docs/ROADMAP\.MD`\s*\|([^\|]+)\|", claude
    )
    assert roadmap_row_match, (
        "CLAUDE.md Key Files section is missing the docs/ROADMAP.MD row."
    )
    roadmap_cell = roadmap_row_match.group(1)

    phase_in_claude = re.search(r"Phase (\S+) OPEN", roadmap_cell)
    assert phase_in_claude, (
        f"CLAUDE.md ROADMAP row does not declare any phase as OPEN. "
        f"Expected 'Phase {canonical_phase} OPEN'. Row content: {roadmap_cell.strip()}"
    )
    assert phase_in_claude.group(1) == canonical_phase, (
        f"Phase state drift detected.\n"
        f"  TECHNICAL_DEBT.md (canonical): Phase {canonical_phase} OPEN\n"
        f"  CLAUDE.md ROADMAP row:         Phase {phase_in_claude.group(1)} OPEN\n"
        "Update CLAUDE.md Key Files ROADMAP row to match TECHNICAL_DEBT.md."
    )
