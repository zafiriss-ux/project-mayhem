"""AT-05: a test run writes no log file into the repository."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from titan.config.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_log_path_during_tests_is_outside_the_repo() -> None:
    log_path = Path(get_settings().TITAN_LOG_PATH).resolve()
    assert not log_path.is_relative_to(REPO_ROOT), log_path


def test_rotated_logs_are_ignored_by_git(tmp_path: Path) -> None:
    # A clean repo with only our .gitignore: a local .git/info/exclude must not count.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text((REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    for name in ("titan.log", "titan.log.1", "titan.log.5"):
        result = subprocess.run(["git", "check-ignore", "-q", "--no-index", name], cwd=tmp_path, check=False)
        assert result.returncode == 0, name


_ADDED = logging.NullHandler()


def test_a_handler_added_to_the_root_logger_here() -> None:
    logging.getLogger().addHandler(_ADDED)


def test_is_gone_in_the_next_test() -> None:
    assert _ADDED not in logging.getLogger().handlers
