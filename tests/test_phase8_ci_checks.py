"""Phase 8 CI guards — three mechanical consistency checks.

Check 1  (test_open_phase8_items_have_workflow_path):
    Every T5-xx item whose heading carries 🔴 must contain a **Workflow Path field.
    Rationale: E16 tightening — TECHNICAL_DEBT.md is the sole canonical path record
    (last-updated note, 2026-03-08).

Check 2  (test_phase8_gate_ordering_invariant):
    No Phase 8B item may be RESOLVED (✅) while any Phase 8A prerequisite is still
    OPEN (🔴).
    Rationale: ROADMAP.MD gate — "No Phase 8B or 8C code may begin before Phase 8A
    deliverables pass the ADR-0044 binary gate."

Check 3  (test_roadmap_md_declares_canonical_open_phase_as_open):
    docs/ROADMAP.MD must mark the same phase as OPEN that TECHNICAL_DEBT.md declares
    canonical.
    Rationale: ROADMAP.MD is the human-facing navigation document; silent drift from
    TECHNICAL_DEBT.md (canonical source) misleads contributors about the active phase.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TECH_DEBT = REPO_ROOT / "TECHNICAL_DEBT.md"
ROADMAP = REPO_ROOT / "docs" / "ROADMAP.MD"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_t5_sections(text: str) -> dict[str, tuple[str, str]]:
    """Return {item_id: (heading_line, section_body)} for all ### T5-xx items."""
    heading_re = re.compile(r"^### ", re.MULTILINE)
    positions = [m.start() for m in heading_re.finditer(text)]
    positions.append(len(text))

    sections: dict[str, tuple[str, str]] = {}
    for i in range(len(positions) - 1):
        start = positions[i]
        end = positions[i + 1]
        section = text[start:end]
        heading_line = section.split("\n")[0]

        m = re.match(r"^### (T5-\S+) ·", heading_line)
        if m:
            sections[m.group(1)] = (heading_line, section)

    return sections


def _heading_emoji(heading: str) -> str:
    for emoji in ("🔴", "✅", "🟡", "🟢"):
        if emoji in heading:
            return emoji
    return "?"


def _extract_status(body: str) -> str:
    """Return the value of the **Status:** or **Decision status:** field."""
    m = re.search(r"\*\*(?:Status|Decision status):\*\*\s*(.+?)(?:\n|$)", body)
    return m.group(1).strip() if m else ""


# ─────────────────────────────────────────────────────────────────────────────
# Check 1 — every 🔴 T5-xx item has a Workflow Path field
# ─────────────────────────────────────────────────────────────────────────────

def test_open_phase8_items_have_workflow_path() -> None:
    """Every T5-xx item with 🔴 in its heading must contain **Workflow Path."""
    text = TECH_DEBT.read_text(encoding="utf-8")
    sections = _parse_t5_sections(text)

    missing = [
        item_id
        for item_id, (heading, body) in sections.items()
        if _heading_emoji(heading) == "🔴" and "**Workflow Path" not in body
    ]

    assert not missing, (
        "Open Phase 8 T5-xx item(s) are missing a **Workflow Path field in "
        "TECHNICAL_DEBT.md: "
        + ", ".join(sorted(missing))
        + "\nAdd '**Workflow Path: A** *(reason)*' (or Path B) to each item per E16."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — Phase 8A must be RESOLVED before Phase 8B is RESOLVED
# ─────────────────────────────────────────────────────────────────────────────

def test_phase8_gate_ordering_invariant() -> None:
    """No Phase 8B item may be ✅ RESOLVED while any Phase 8A prerequisite is 🔴 OPEN.

    Phase classification uses the **Status:** field text:
      Phase 8A item  — status contains 'Phase 8A'
      Phase 8B item  — status contains 'Phase 8B'
    """
    text = TECH_DEBT.read_text(encoding="utf-8")
    sections = _parse_t5_sections(text)

    phase_8a_open: list[str] = []
    phase_8b_resolved: list[str] = []

    for item_id, (heading, body) in sections.items():
        status = _extract_status(body)
        emoji = _heading_emoji(heading)

        if "Phase 8A" in status and emoji == "🔴":
            phase_8a_open.append(item_id)

        if "Phase 8B" in status and emoji == "✅":
            phase_8b_resolved.append(item_id)

    assert not (phase_8b_resolved and phase_8a_open), (
        "Phase 8 gate ordering violation detected in TECHNICAL_DEBT.md.\n"
        f"  Phase 8B items marked RESOLVED : {sorted(phase_8b_resolved)}\n"
        f"  Phase 8A items still OPEN      : {sorted(phase_8a_open)}\n"
        "ADR-0044 gate: all Phase 8A deliverables must be RESOLVED before any "
        "Phase 8B item is RESOLVED."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — ROADMAP.MD declares the canonical open phase as OPEN
# ─────────────────────────────────────────────────────────────────────────────

def test_roadmap_md_declares_canonical_open_phase_as_open() -> None:
    """ROADMAP.MD section header for the canonical open phase must say (OPEN, ...)."""
    tech_debt = TECH_DEBT.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")

    # Canonical source: last 'Phase N OPEN' line in TECHNICAL_DEBT.md
    td_matches = re.findall(r"^Phase (\S+) OPEN\b", tech_debt, re.MULTILINE)
    assert td_matches, (
        "TECHNICAL_DEBT.md has no top-level 'Phase N OPEN' declaration. "
        "Add a line of the form 'Phase N OPEN — <reason>' when a new phase opens."
    )
    canonical_phase = td_matches[-1]

    # ROADMAP.MD must have a section for this phase with (OPEN, ...) in the header
    section_match = re.search(
        rf"^## Phase {re.escape(canonical_phase)}\b[^\n]*\((OPEN|PLANNED|CLOSED)",
        roadmap,
        re.MULTILINE,
    )
    assert section_match, (
        f"ROADMAP.MD has no '## Phase {canonical_phase}' section. "
        f"Add a header of the form: "
        f"'## Phase {canonical_phase} — <title> (OPEN, YYYY-MM-DD)'"
    )

    state = section_match.group(1)
    assert state == "OPEN", (
        f"ROADMAP.MD Phase {canonical_phase} section is marked '({state}, ...)' "
        f"but TECHNICAL_DEBT.md declares Phase {canonical_phase} OPEN.\n"
        f"Update the ROADMAP.MD section header to '(OPEN, YYYY-MM-DD)'."
    )
