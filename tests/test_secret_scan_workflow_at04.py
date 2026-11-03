"""AT-04 (AGENTS §30 RE-05): the gitleaks step scans every commit a push brings.

The step's shell script is run for real against a throwaway git repo, with a fake
gitleaks that records the range it was asked to scan.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "secret-scan.yml"
ZERO_SHA = "0" * 40


def _scan_script() -> str:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gitleaks"]["steps"]
    (step,) = [s for s in steps if s.get("name") == "Scan for secrets"]
    assert "${{" not in step["run"], "inputs reach the script through env, not inline expressions"
    return step["run"]


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, list[str]]:
    work = tmp_path / "repo"
    work.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "init", "-q"], cwd=work, check=True, env=env)
    shas = []
    for i in range(3):
        (work / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", f"c{i}"], cwd=work, check=True, env=env)
        shas.append(subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, check=True,
                                   capture_output=True, text=True).stdout.strip())
    return work, shas


def _run(work: Path, tmp_path: Path, *, scanner_exit: int = 0, **event: str) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "gitleaks"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$GITLEAKS_ARGS"\nexit "$GITLEAKS_EXIT"\n',
                    encoding="utf-8")
    fake.chmod(0o755)
    args_file = tmp_path / "args.txt"
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "GITLEAKS_ARGS": str(args_file),
           "GITLEAKS_EXIT": str(scanner_exit),
           "EVENT_NAME": "push", "PR_BASE": "", "PR_HEAD": "", "PUSH_BEFORE": "", **event}
    subprocess.run(["bash", "-c", _scan_script()], cwd=work, env=env, check=True)
    return args_file.read_text(encoding="utf-8")


def test_a_push_of_several_commits_is_scanned_from_the_old_head(repo, tmp_path) -> None:
    work, shas = repo
    args = _run(work, tmp_path, PUSH_BEFORE=shas[0])
    assert f"--log-opts={shas[0]}..HEAD" in args.splitlines()


@pytest.mark.parametrize("before", ["", ZERO_SHA, "1234567890abcdef1234567890abcdef12345678"])
def test_without_a_usable_old_head_the_whole_history_is_scanned(repo, tmp_path, before) -> None:
    work, _ = repo
    args = _run(work, tmp_path, PUSH_BEFORE=before)
    assert not any(a.startswith("--log-opts") for a in args.splitlines())


def test_a_pull_request_is_scanned_over_its_whole_range(repo, tmp_path) -> None:
    work, shas = repo
    args = _run(work, tmp_path, EVENT_NAME="pull_request", PR_BASE=shas[0], PR_HEAD=shas[2])
    assert f"--log-opts={shas[0]}...{shas[2]}" in args.splitlines()


def test_the_workflow_never_scans_only_the_last_commit() -> None:
    assert "HEAD~1..HEAD" not in WORKFLOW.read_text(encoding="utf-8")


@pytest.mark.parametrize("scanner_exit", [1, 2, 127])
@pytest.mark.parametrize("event_name", ["pull_request", "push", "history"])
def test_scanner_failures_block_the_actual_scan_step(
    repo, tmp_path, scanner_exit: int, event_name: str,
) -> None:
    work, shas = repo
    event = {"EVENT_NAME": "pull_request" if event_name == "pull_request" else "push",
             "PR_BASE": shas[0], "PR_HEAD": shas[2],
             "PUSH_BEFORE": shas[0] if event_name == "push" else ""}
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _run(work, tmp_path, scanner_exit=scanner_exit, **event)
    assert exc_info.value.returncode == scanner_exit
