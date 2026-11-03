"""CI-01: run the real shell control against a recording scanner double."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL = REPO_ROOT / "scripts" / "check_gitleaks.sh"
CONFIG = REPO_ROOT / ".gitleaks.toml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "secret-scan.yml"
FINDING = '[{"RuleID": "github-pat"}]'

SCANNER_DOUBLE = '''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
source = Path(args[args.index("--source") + 1])
report = Path(args[args.index("--report-path") + 1])
control = source.name
fixture = (source / "fixture.txt").read_text(encoding="utf-8")
expected_token = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
call = {
    "args": args,
    "source_files": sorted(path.name for path in source.iterdir()),
    "fixture_valid": (
        fixture == "token=" + expected_token + "\\n" if control == "positive"
        else fixture == "Ordinary documentation without credentials.\\n"
    ),
}
with Path(os.environ["CONTROL_CALLS"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(call) + "\\n")
spec = json.loads(Path(os.environ["CONTROL_SPEC"]).read_text(encoding="utf-8"))[control]
if spec["report"] is not None:
    report.write_text(spec["report"], encoding="utf-8")
sys.exit(spec["exit"])
'''


def _run_control(
    tmp_path: Path,
    *,
    control: str = "positive",
    scanner_exit: int = 1,
    report: str | None = FINDING,
) -> tuple[subprocess.CompletedProcess[str], list[dict], Path]:
    # Run outside the checkout, including spaces, to verify config path anchoring.
    repo = tmp_path / "repo with spaces"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(CONTROL, scripts / CONTROL.name)
    shutil.copy2(CONFIG, repo / CONFIG.name)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scanner = bin_dir / "gitleaks"
    scanner.write_text(SCANNER_DOUBLE, encoding="utf-8")
    scanner.chmod(0o755)
    control_tmp = tmp_path / "control temporary files"
    control_tmp.mkdir()
    spec = {"clean": {"exit": 0, "report": "[]"},
            "positive": {"exit": 1, "report": FINDING}}
    spec[control] = {"exit": scanner_exit, "report": report}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    calls_path = tmp_path / "calls.jsonl"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "TMPDIR": str(control_tmp), "CONTROL_SPEC": str(spec_path),
           "CONTROL_CALLS": str(calls_path)}
    result = subprocess.run(["bash", str(scripts / CONTROL.name)], cwd=tmp_path,
                            env=env, capture_output=True, text=True, check=False)
    calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
    return result, calls, control_tmp


def test_config_loads_bundled_default_rules() -> None:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True
    assert config["allowlist"]["regexes"], "existing narrow fixture exceptions remain"
    assert "paths" not in config["allowlist"]


def test_clean_and_positive_controls_use_real_script_and_clean_up(tmp_path: Path) -> None:
    result, calls, control_tmp = _run_control(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "clean and positive controls passed" in result.stdout
    assert len(calls) == 2
    assert list(control_tmp.iterdir()) == []
    for call, name in zip(calls, ("clean", "positive"), strict=True):
        args = call["args"]
        assert args[0] == "detect"
        assert {"--no-git", "--redact", "--no-banner"} <= set(args)
        assert args[args.index("--report-format") + 1] == "json"
        assert Path(args[args.index("--source") + 1]).name == name
        assert Path(args[args.index("--config") + 1]) == tmp_path / "repo with spaces" / CONFIG.name
        assert not Path(args[args.index("--report-path") + 1]).exists()
        assert call["source_files"] == ["fixture.txt"]
        assert call["fixture_valid"]


@pytest.mark.parametrize(
    ("control", "scanner_exit", "report"),
    [
        ("positive", 0, FINDING),
        ("positive", 2, FINDING),
        ("positive", 127, FINDING),
        ("positive", 1, "[]"),
        ("positive", 1, None),
        ("positive", 1, ""),
        ("positive", 1, "{invalid"),
        ("positive", 1, '{"RuleID": "github-pat"}'),
        ("positive", 1, '[{"RuleID": "generic-api-key"}]'),
        ("positive", 1, '["github-pat"]'),
        ("positive", 1, '[null, {"RuleID": "github-pat"}]'),
        ("clean", 1, "[]"),
        ("clean", 2, "[]"),
        ("clean", 0, FINDING),
        ("clean", 0, None),
        ("clean", 0, "{invalid"),
        ("clean", 0, "{}"),
    ],
)
def test_unproven_scan_is_rejected_and_cleaned_up(
    tmp_path: Path, control: str, scanner_exit: int, report: str | None,
) -> None:
    result, calls, control_tmp = _run_control(
        tmp_path, control=control, scanner_exit=scanner_exit, report=report,
    )
    assert result.returncode != 0
    assert "control failed" in result.stderr
    assert "controls passed" not in result.stdout
    assert len(calls) == (1 if control == "clean" else 2)
    assert list(control_tmp.iterdir()) == []


def test_workflow_runs_control_after_install_before_real_scan() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["gitleaks"]["steps"]
    names = [step.get("name") for step in steps]
    control = names.index("Check gitleaks controls")
    assert names.index("Install gitleaks") < control < names.index("Scan for secrets")
    assert steps[control]["run"] == "bash scripts/check_gitleaks.sh"
    assert not any(key in steps[control] for key in ("continue-on-error", "if"))
