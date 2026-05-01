from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PHASE_A_TARGET_FOLDERS = [
    "titan/config",
    "titan/science",
    "titan/core",
    "titan/integrations",
    "titan/orchestration",
    "titan/features",
    "titan/ui",
    "titan/utils",
    "tests",
]

PHASE_B_BLOCKING_TARGETS = [
    "titan/config",
]


def test_ci_has_two_phase_ruff_gate() -> None:
    workflow = ROOT / ".github/workflows/ci.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "ruff-phase-a:" in content
    assert "Ruff Phase A" in content
    assert "continue-on-error: true" not in content.split("ruff-phase-a:", 1)[1].split("ruff-phase-b:", 1)[0]

    assert "ruff-phase-b:" in content
    assert "Ruff Phase B (clean folders, blocking)" in content
    assert "needs: [ruff-phase-a]" in content


def test_phase_a_covers_current_warning_targets() -> None:
    workflow = ROOT / ".github/workflows/ci.yml"
    content = workflow.read_text(encoding="utf-8")

    phase_a_section = content.split("ruff-phase-a:", 1)[1].split("ruff-phase-b:", 1)[0]
    assert "ruff check ." in phase_a_section


def test_phase_b_includes_promoted_targets_in_blocking_gate() -> None:
    workflow = ROOT / ".github/workflows/ci.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "BLOCKING_TARGETS=(" in content

    for folder in PHASE_B_BLOCKING_TARGETS:
        assert folder in content


def test_phase_b_starts_with_only_titan_config() -> None:
    workflow = ROOT / ".github/workflows/ci.yml"
    content = workflow.read_text(encoding="utf-8")

    phase_b_section = content.split("BLOCKING_TARGETS=(", maxsplit=1)[1].split(")", maxsplit=1)[0]
    assert "titan/config" in phase_b_section
    assert "titan/core" not in phase_b_section
    assert "titan/integrations" not in phase_b_section
    assert "titan/orchestration" not in phase_b_section
    assert "titan/features" not in phase_b_section
    assert "titan/ui" not in phase_b_section
