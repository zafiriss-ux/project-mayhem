from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_governance_engine_has_architecture_lock_header() -> None:
    governance_engine = ROOT / 'titan/science/governance_engine.py'
    lines = governance_engine.read_text(encoding='utf-8').splitlines()
    # §16.1 required 3-line lock comment (replaces single-line ARCHITECTURE LOCK)
    assert lines[0].strip() == '# Gate parameters: see thresholds.py + evidence_registry.py.'
    assert 'write ADR entry' in lines[1]
    assert 'test_governance_mutation.py' in lines[2]


def test_codeowners_has_governance_engine_owner() -> None:
    codeowners = ROOT / '.github/CODEOWNERS'
    content = codeowners.read_text(encoding='utf-8')

    assert '/titan/science/governance_engine.py' in content


def test_ci_enforces_adr_reference_when_governance_engine_changes() -> None:
    workflow = ROOT / '.github/workflows/ci.yml'
    content = workflow.read_text(encoding='utf-8')

    assert 'Enforce governance_engine architecture lock' in content
    assert "grep -qx 'titan/science/governance_engine.py'" in content
    assert "grep -q 'ADR-0009'" in content
