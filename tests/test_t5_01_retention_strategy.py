"""Tier 5 hygiene checks for ADR-0015 retention/archival decision."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_0015_PATH = REPO_ROOT / "docs" / "adr" / "0015-sqlite-retention-and-phase8-data-lifecycle-gate.md"
ROADMAP_PATH = REPO_ROOT / "docs" / "ROADMAP.MD"


def test_adr_0015_exists_and_is_non_empty():
    assert ADR_0015_PATH.exists(), "Missing ADR-0015 file"
    assert ADR_0015_PATH.stat().st_size > 0, "ADR-0015 is empty"


def test_adr_0015_locks_single_athlete_constraint_and_phase8_gate():
    adr_text = ADR_0015_PATH.read_text(encoding="utf-8")

    assert "single-athlete, single-lifetime" in adr_text
    assert "No Phase 8 implementation may start until that ADR is accepted." in adr_text


def test_adr_0015_captures_required_lifecycle_decisions():
    adr_text = ADR_0015_PATH.read_text(encoding="utf-8")

    assert "retention window" in adr_text
    assert "per-athlete SQLite files vs shared database" in adr_text
    assert "CSV, JSON, or SQLite" in adr_text


def test_roadmap_references_t5_01_and_adr_0015():
    roadmap_text = ROADMAP_PATH.read_text(encoding="utf-8")

    assert "Tier 5 — Future Optionality" in roadmap_text
    assert "T5-01" in roadmap_text
    assert "ADR-0015" in roadmap_text
