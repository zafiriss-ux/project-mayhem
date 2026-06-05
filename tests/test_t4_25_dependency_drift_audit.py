from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _workflow_content() -> str:
    return (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.governance
def test_ci_has_dependency_drift_audit_job() -> None:
    content = _workflow_content()

    assert "dependency-drift-audit:" in content
    assert "Dependency Drift Audit (unpinned + CVE gate)" in content
    # D-21: continue-on-error must be absent from the audit job — audit failures must block.
    # Extract only the dependency-drift-audit job section.
    start = content.index("dependency-drift-audit:")
    # Next top-level job starts at the next line that begins with "  <word>:"
    remainder = content[start:]
    lines = remainder.splitlines()
    job_lines = [lines[0]]
    job_keywords = ("name:", "runs-on:", "steps:", "needs:", "if:")
    for line in lines[1:]:
        if line and not line.startswith(" ") and line.rstrip().endswith(":"):
            break
        if (
            line.startswith("  ")
            and line.lstrip().endswith(":")
            and not line.startswith("   ")
            and not any(kw in line for kw in job_keywords)
        ):
            break
        job_lines.append(line)
    drift_audit_section = "\n".join(job_lines)
    assert "continue-on-error: true" not in drift_audit_section, (
        "D-21: dependency-drift-audit must not use continue-on-error"
    )


@pytest.mark.unit
@pytest.mark.governance
def test_dependency_drift_audit_checks_unpinned_dependencies() -> None:
    content = _workflow_content()

    assert "Audit unpinned dependencies in requirements files" in content
    assert "requirements.txt" in content
    assert "requirements-dev.txt" in content
    assert "if not version_pattern.search(line):" in content
    assert "Unpinned dependencies detected:" in content
    assert "raise SystemExit(1)" in content


@pytest.mark.unit
@pytest.mark.governance
def test_dependency_drift_audit_cve_only_gate() -> None:
    """Drift audit must use pip-audit CVE gate, not stale-version check (patch treadmill fix)."""
    content = _workflow_content()

    assert "CVE-only dependency gate" in content
    assert "pip-audit" in content
    assert "--ignore-vuln GHSA-gc5v-m9x4-r6x2" in content
    assert "No actionable CVEs found." in content
    assert "sys.exit(1)" in content
