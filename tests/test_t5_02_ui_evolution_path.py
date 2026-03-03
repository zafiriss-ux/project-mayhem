"""Tier 5 hygiene checks for T5-02 UI evolution path constraints."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_0013_PATH = REPO_ROOT / "docs" / "adr" / "0013-operator-console-technology-path.md"
TECH_PATH_SPEC = REPO_ROOT / "docs" / "specs" / "operator_console_technology_path.md"
ROADMAP_PATH = REPO_ROOT / "docs" / "ROADMAP.MD"


def test_adr_0013_documents_three_phase_ui_path():
    adr_text = ADR_0013_PATH.read_text(encoding="utf-8")

    assert "Phase A (Terminal facelift)" in adr_text
    assert "Phase B (Streamlit prototype)" in adr_text
    assert "Phase C (React + FastAPI production stack)" in adr_text


def test_adr_0013_defers_phase_a_until_hardening_is_complete():
    adr_text = ADR_0013_PATH.read_text(encoding="utf-8")

    assert "deferred" in adr_text
    assert "until Tier 1–2 hardening is complete" in adr_text
    assert "Data integrity and observability remain" in adr_text


def test_operator_console_technology_spec_matches_t5_02_scope():
    spec_text = TECH_PATH_SPEC.read_text(encoding="utf-8")

    assert "retro-HUD dashboard snapshot on startup" in spec_text
    assert "action rail (primary /" in spec_text
    assert "status cards with VLG colour + readiness score" in spec_text
    assert "Reuses `OperatorConsoleService` payloads directly." in spec_text


def test_roadmap_tracks_t5_02_and_hardening_constraint():
    roadmap_text = ROADMAP_PATH.read_text(encoding="utf-8")

    assert "T5-02" in roadmap_text
    assert "UI evolution path" in roadmap_text
    assert "do not invest in Phase A terminal cosmetics" in roadmap_text
