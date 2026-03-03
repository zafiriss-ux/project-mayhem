from pathlib import Path
import subprocess


def test_archive_kernel_is_ruff_clean() -> None:
    target = Path("archive/TITAN_v50_FULL_KERNEL_FINAL.py")

    result = subprocess.run(
        ["ruff", "check", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
