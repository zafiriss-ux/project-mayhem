"""AT-08: every test runs under a time limit, so a hang names the test that hung."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import dateutil
import pytest
from freezegun import freeze_time


def test_a_default_time_limit_is_set(pytestconfig: pytest.Config) -> None:
    timeout = pytestconfig.getini("timeout")
    assert timeout not in (None, ""), "no per-test timeout configured"
    # Above the slowest setup today (~100 s locally), below the 30-minute CI job.
    assert 120 <= float(timeout) <= 900


def test_a_hanging_test_fails_with_a_timeout(tmp_path: Path) -> None:
    (tmp_path / "test_hang.py").write_text(
        "import time\n\ndef test_hang():\n    time.sleep(30)\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider",
         "-o", "timeout=1", "--rootdir", str(tmp_path), str(tmp_path / "test_hang.py")],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode != 0
    assert "Timeout" in result.stdout


def test_freeze_time_survives_a_module_whose_dir_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full run with the time limit on left the clock frozen after one test.

    freeze_time() called dir(dateutil) while dateutil's globals changed, the
    RuntimeError escaped __enter__, and time.time stayed patched for every later
    test. Here dateutil's __dir__ fails on purpose: freeze_time must not call it.
    """

    def _broken_dir() -> list[str]:
        raise RuntimeError("dictionary changed size during iteration")

    monkeypatch.setattr(dateutil, "__dir__", _broken_dir)
    before = time.time()
    with freeze_time("2026-03-02 07:30:00"):
        assert time.time() < before
    assert time.time() >= before, "the clock stayed frozen after freeze_time"
