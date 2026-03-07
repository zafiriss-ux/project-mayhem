from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def _workflow_content() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_has_complexity_budget_job() -> None:
    content = _workflow_content()

    assert "complexity-budget:" in content
    assert "Complexity Budget (module count ceiling)" in content
    assert "Enforce titan module count ceiling" in content


def test_complexity_budget_job_enforces_real_titan_module_count_with_ceiling() -> None:
    content = _workflow_content()

    assert "import pkgutil" in content
    assert "import titan" in content
    assert "pkgutil.walk_packages(titan.__path__, prefix=\"titan.\")" in content
    assert 'if "__" not in module.name' in content
    assert "module_ceiling = 60" in content
    assert "if module_count > module_ceiling:" in content
    assert "Complexity budget exceeded: titan module count" in content
