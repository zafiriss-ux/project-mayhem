from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workflow_content() -> str:
    return (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_ci_has_dependency_drift_audit_job() -> None:
    content = _workflow_content()

    assert "dependency-drift-audit:" in content
    assert "Dependency Drift Audit (unpinned + CVE gate)" in content
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


def test_dependency_drift_audit_cve_only_gate() -> None:
    """Drift audit must use pip-audit CVE gate, not stale-version check (patch treadmill fix)."""
    content = _workflow_content()

    assert "CVE-only dependency gate" in content
    assert "pip-audit" in content
    assert "--ignore-vuln GHSA-gc5v-m9x4-r6x2" in content
    assert "No actionable CVEs found." in content
    assert "sys.exit(1)" in content
