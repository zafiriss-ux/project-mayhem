from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_archive_monolith_removed() -> None:
    """D-20: TITAN_v50_FULL_KERNEL_FINAL.py must not exist in archive/."""
    target = REPO_ROOT / "archive/TITAN_v50_FULL_KERNEL_FINAL.py"
    assert not target.exists(), (
        "archive/TITAN_v50_FULL_KERNEL_FINAL.py must be removed (D-20 fix)."
    )
