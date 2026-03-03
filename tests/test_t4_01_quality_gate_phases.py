from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGET_FOLDERS = [
    'titan/config',
    'titan/science',
    'titan/core',
    'titan/integrations',
    'titan/orchestration',
    'titan/features',
    'titan/ui',
]


def test_ci_has_two_phase_ruff_gate() -> None:
    workflow = ROOT / '.github/workflows/ci.yml'
    content = workflow.read_text(encoding='utf-8')

    assert 'ruff-phase-a:' in content
    assert 'Ruff Phase A (target folders, warning)' in content
    assert 'continue-on-error: true' in content

    assert 'ruff-phase-b:' in content
    assert 'Ruff Phase B (clean folders, blocking)' in content
    assert 'needs: [ruff-phase-a]' in content


def test_phase_a_covers_t4_01_target_folders() -> None:
    workflow = ROOT / '.github/workflows/ci.yml'
    content = workflow.read_text(encoding='utf-8')

    for folder in TARGET_FOLDERS:
        assert folder in content


def test_phase_b_starts_with_config_blocking_gate() -> None:
    workflow = ROOT / '.github/workflows/ci.yml'
    content = workflow.read_text(encoding='utf-8')

    assert 'BLOCKING_FOLDERS=(' in content
    assert 'titan/config' in content
