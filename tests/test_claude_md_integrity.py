"""CLAUDE.md integrity invariants (T4-22 / ADR-0025)."""

from __future__ import annotations

import pathlib
import re

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

