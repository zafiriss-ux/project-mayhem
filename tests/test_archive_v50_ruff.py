from pathlib import Path


def test_archive_monolith_removed() -> None:
    """D-20: TITAN_v50_FULL_KERNEL_FINAL.py must not exist in archive/."""
    target = Path("archive/TITAN_v50_FULL_KERNEL_FINAL.py")
    assert not target.exists(), (
        "archive/TITAN_v50_FULL_KERNEL_FINAL.py must be removed (D-20 fix)."
    )
