"""Execute copied entrypoints with synthetic tools, never the real full gates."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATES = [
    ["-m", "ruff", "check", "."],
    ["-m", "pytest", "-q", "-W", "error::pytest.PytestWarning"],
    ["-m", "pytest", "-q"],
]
FAKE_PYTHON = r'''
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["CI_TRACE"], "a", encoding="utf-8") as trace:
    trace.write(json.dumps(args) + "\n")
if args == ["-"]:
    sys.stdin.read()
    print(json.dumps({"python_version": "fixture", "venv_hash": "fixture", "host_id": "fixture"}))
    sys.exit(int(os.environ.get("CI_FINGERPRINT_STATUS", "0")))
if args[0] == "-c" or args == ["-m", "ruff", "--version"]:
    sys.exit(int(os.environ.get("CI_PREFLIGHT_STATUS", "0")))
gates = json.loads(os.environ["CI_GATES"])
index = gates.index(args)
print("1 passed in 0.01s")
sys.exit(json.loads(os.environ["CI_STATUSES"])[index])
'''


@pytest.fixture
def ci_fixture(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("titan_ci.sh", "titan_check.sh", "env_fingerprint.sh", "pre-commit-hook"):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts / name)
    interpreter = tmp_path / "selected-venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text(f"#!{sys.executable}\n{FAKE_PYTHON}", encoding="utf-8")
    interpreter.chmod(0o755)
    trace = tmp_path / "trace.jsonl"
    env = {
        **os.environ,
        "VIRTUAL_ENV": str(interpreter.parent.parent),
        "CI_TRACE": str(trace),
        "CI_GATES": json.dumps(GATES),
        "CI_STATUSES": "[0, 0, 0]",
    }
    return tmp_path, env, trace, interpreter


def run_entrypoint(ci_fixture, entrypoint="titan_ci.sh", statuses=(0, 0, 0)):
    root, env, trace, _ = ci_fixture
    env["CI_STATUSES"] = json.dumps(statuses)
    result = subprocess.run(
        ["bash", str(root / "scripts" / entrypoint)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    return result, calls


@pytest.mark.parametrize("entrypoint", ["titan_ci.sh", "titan_check.sh", "pre-commit-hook"])
def test_entrypoints_run_exact_full_gates_in_order(ci_fixture, entrypoint):
    result, calls = run_entrypoint(ci_fixture, entrypoint)

    assert result.returncode == 0, result.stderr
    assert calls[-3:] == GATES
    assert len(calls) == 6  # Two dependency probes, fingerprint, three gates.
    assert calls[2] == ["-"]
    assert '"python_version": "fixture"' in result.stdout
    assert "ALL GATES PASS" in result.stdout


@pytest.mark.parametrize("entrypoint", ["titan_ci.sh", "titan_check.sh", "pre-commit-hook"])
@pytest.mark.parametrize("stage,status", [(0, 37), (1, 2), (1, 42), (2, 5), (2, 130)])
def test_first_failed_gate_preserves_status_despite_passed_output(ci_fixture, entrypoint, stage, status):
    statuses = [0, 0, 0]
    statuses[stage] = status
    result, calls = run_entrypoint(ci_fixture, entrypoint, statuses)

    assert result.returncode == status
    assert calls[3:] == GATES[: stage + 1]
    assert "1 passed in 0.01s" in result.stdout
    assert "ALL GATES PASS" not in result.stdout
    assert f"exit {status}" in result.stderr


@pytest.mark.parametrize("probe", ["CI_PREFLIGHT_STATUS", "CI_FINGERPRINT_STATUS"])
def test_failed_preflight_or_fingerprint_stops_before_gates(ci_fixture, probe):
    _, env, _, _ = ci_fixture
    env[probe] = "23"
    result, calls = run_entrypoint(ci_fixture)

    assert result.returncode == (1 if probe == "CI_PREFLIGHT_STATUS" else 23)
    assert not any(call in GATES for call in calls)


@pytest.mark.parametrize("resolution", ["repo", "path"])
def test_interpreter_resolution_without_activated_venv(ci_fixture, resolution):
    root, env, _, interpreter = ci_fixture
    env.pop("VIRTUAL_ENV")
    if resolution == "repo":
        fallback = root / ".venv" / "bin" / "python"
    else:
        fallback = root / "path-bin" / "python3"
        env["PATH"] = f"{fallback.parent}{os.pathsep}{env['PATH']}"
    fallback.parent.mkdir(parents=True)
    shutil.copy2(interpreter, fallback)

    result, calls = run_entrypoint(ci_fixture)

    assert result.returncode == 0, result.stderr
    assert f"Interpreter: {fallback}" in result.stdout
    assert calls[3:] == GATES


@pytest.mark.parametrize("status", [0, 47])
def test_check_wrapper_forwards_arguments_and_exec_status(ci_fixture, status):
    root, env, _, _ = ci_fixture
    canonical = root / "scripts" / "titan_ci.sh"
    canonical.write_text(
        '#!/usr/bin/env bash\nprintf "<%s>\\n" "$@"\nexit ' + str(status) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(root / "scripts" / "titan_check.sh"), "--profile", "full", "two words", ""],
        cwd=root.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == status
    assert result.stdout.splitlines() == ["<--profile>", "<full>", "<two words>", "<>"]
    assert 'exec scripts/titan_check.sh' in (root / "scripts" / "pre-commit-hook").read_text()
