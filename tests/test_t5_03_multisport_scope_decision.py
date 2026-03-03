"""Tier 5 hygiene checks for ADR-0016 multi-sport scope decision."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_0016_PATH = REPO_ROOT / "docs" / "adr" / "0016-phase8-multisport-scope-and-adapter-gate.md"
ROADMAP_PATH = REPO_ROOT / "docs" / "ROADMAP.MD"
DEBT_PATH = REPO_ROOT / "TECHNICAL_DEBT.md"


def test_adr_0016_exists_and_is_non_empty():
    assert ADR_0016_PATH.exists(), "Missing ADR-0016 file"
    assert ADR_0016_PATH.stat().st_size > 0, "ADR-0016 is empty"


def test_adr_0016_locks_phase8_multisport_and_adapter_gate():
    adr_text = ADR_0016_PATH.read_text(encoding="utf-8")

    assert "Multi-sport is in scope for Phase 8" in adr_text
    assert "Current scope remains running-only" in adr_text
    assert "unified adapter interface" in adr_text
    assert "No multi-sport implementation work may begin" in adr_text


def test_roadmap_references_t5_03_and_adr_0016():
    roadmap_text = ROADMAP_PATH.read_text(encoding="utf-8")

    assert "T5-03" in roadmap_text
    assert "ADR-0016" in roadmap_text
    assert "running-only" in roadmap_text


def test_technical_debt_t5_03_is_marked_decided():
    debt_text = DEBT_PATH.read_text(encoding="utf-8")

    assert "T5-03 · Multi-sport scope decision" in debt_text
    assert "Decision locked (ADR-0016)" in debt_text
