"""Drift detector: every titan module stem must appear in docs/ARCHITECTURE.md."""

import os
from pathlib import Path

ARCH_FILE = Path(__file__).parent.parent / "docs" / "ARCHITECTURE.md"
TITAN_DIR = Path(__file__).parent.parent / "titan"


def _collect_module_stems():
    stems = []
    for _root, dirs, files in os.walk(TITAN_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            if fname.endswith(".py") and fname not in ("__init__.py", "__main__.py"):
                stems.append(Path(fname).stem)
    return stems


def test_architecture_md_exists_and_nonempty():
    assert ARCH_FILE.exists(), f"docs/ARCHITECTURE.md not found at {ARCH_FILE}"
    assert len(ARCH_FILE.read_text()) > 1000, "docs/ARCHITECTURE.md is too short (< 1000 chars)"


def test_all_titan_modules_in_architecture_md():
    arch_text = ARCH_FILE.read_text()
    missing = [stem for stem in _collect_module_stems() if stem not in arch_text]
    assert not missing, (
        f"Module(s) not found anywhere in docs/ARCHITECTURE.md: {missing}"
    )
