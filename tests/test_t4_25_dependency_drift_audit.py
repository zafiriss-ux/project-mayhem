from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workflow_content() -> str:
    return (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_ci_has_dependency_drift_audit_job() -> None:
    content = _workflow_content()

    assert "dependency-drift-audit:" in content
    assert "Dependency Drift Audit (unpinned + stale)" in content
    # D-21: continue-on-error must be absent — audit failures must block the pipeline.
    assert "continue-on-error: true" not in content


def test_dependency_drift_audit_checks_unpinned_dependencies() -> None:
    content = _workflow_content()

    assert "Audit unpinned dependencies in requirements files" in content
    assert "requirements.txt" in content
    assert "requirements-dev.txt" in content
    assert "if not version_pattern.search(line):" in content
    assert "Unpinned dependencies detected:" in content
    assert "raise SystemExit(1)" in content


def test_dependency_drift_audit_checks_outdated_packages() -> None:
    content = _workflow_content()

    assert '"list", "--outdated", "--format=json"' in content
    assert "Outdated project dependencies detected:" in content
    assert "No outdated project dependencies detected" in content
    assert "raise SystemExit(1)" in content
