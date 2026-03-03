from __future__ import annotations

import re
import shutil
import subprocess
import sys

import pytest

SAFE_BUCKETS = "I001,UP006,UP045,W293,W291"


def _ruff_bucket_count() -> int:
    ruff_bin = shutil.which("ruff")
    cmd = (
        ["ruff", "check", "titan", "tests", "--select", SAFE_BUCKETS, "--statistics"]
        if ruff_bin
        else [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "titan",
            "tests",
            "--select",
            SAFE_BUCKETS,
            "--statistics",
        ]
    )

    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    out = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode == 127:
        pytest.skip("ruff is not installed in this environment")

    match = re.search(r"Found\s+(\d+)\s+error[s]?", out)
    if match:
        return int(match.group(1))

    if proc.returncode == 0 or "All checks passed!" in out:
        return 0

    raise AssertionError(
        f"Could not parse Ruff statistics output (cmd={cmd!r}, rc={proc.returncode}):\n{out}"
    )


def test_t4_01_safe_autofix_buckets_are_zero_for_active_code() -> None:
    findings = _ruff_bucket_count()
    assert findings == 0, (
        "Expected no I001/UP006/UP045/W293/W291 findings in titan+tests after safe autofix pass."
    )
