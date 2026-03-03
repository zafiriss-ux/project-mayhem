"""Tier 5 hygiene checks for ADR-0015 retention/archival decision."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_0015_PATH = REPO_ROOT / "docs" / "adr" / "0015-sqlite-retention-and-phase8-data-lifecycle-gate.md"
ROADMAP_PATH = REPO_ROOT / "docs" / "ROADMAP.MD"
DEBT_REGISTER_PATH = REPO_ROOT / "TECHNICAL_DEBT.md"


def test_adr_0015_exists_and_is_non_empty():
    assert ADR_0015_PATH.exists(), "Missing ADR-0015 file"
    assert ADR_0015_PATH.stat().st_size > 0, "ADR-0015 is empty"


def test_adr_0015_locks_single_athlete_constraint_and_phase8_gate():
    adr_text = ADR_0015_PATH.read_text(encoding="utf-8")

    assert "The explicit decision requested in T5-01 is **YES**" in adr_text
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


def test_technical_debt_register_locks_t5_01_decision():
    debt_text = DEBT_REGISTER_PATH.read_text(encoding="utf-8")

    assert "### T5-01 · SQLite retention / archival strategy 🟢" in debt_text
    assert "Decision locked (ADR-0015)" in debt_text
    assert "single-athlete, single-lifetime" in debt_text
    assert "Phase 8 gate (mandatory)" in debt_text
    assert "Decision needed" not in debt_text


def test_technical_debt_tracking_table_lists_completed_items_with_prs():
    debt_text = DEBT_REGISTER_PATH.read_text(encoding="utf-8")

    expected_rows = [
        "| T3-01 | 2026-03-03 | [#172]",
        "| T4-01 | 2026-03-03 | [#167]",
        "| T5-01 | 2026-03-03 | [#173]",
        "| T5-02 | 2026-03-03 | [#169]",
        "| T5-03 | 2026-03-03 | [#170]",
        "| T5-04 | 2026-03-03 | [#171]",
    ]

    for row in expected_rows:
        assert row in debt_text, f"Missing tracking row: {row}"
