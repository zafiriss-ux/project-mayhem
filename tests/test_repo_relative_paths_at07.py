"""AT-07: tests must not depend on the directory pytest is started from.

A test that opens ``Path("titan/main.py")`` only works when the current
directory is the repo root. Anchor such paths on ``REPO_ROOT`` instead
(``Path(__file__).resolve().parents[N]``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"

# Calls whose first string argument is treated as a filesystem path.
# ``Config`` is alembic's ``Config("alembic.ini")``.
_PATH_CALLS = {"Path", "PurePath", "open", "exists", "isfile", "isdir", "join", "Config"}
# subprocess calls: a repo-relative argv entry is fine only with an explicit cwd=.
_SUBPROCESS_CALLS = {"run", "check_call", "check_output", "call", "Popen"}


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _top_level_entries() -> set[str]:
    return {p.name for p in REPO_ROOT.iterdir() if not p.name.startswith(".git")} | {
        ".github",
        ".semgrep",
    }


def cwd_relative_paths(source: str, top_level: set[str]) -> list[tuple[int, str]]:
    """Return (line, literal) for path literals that resolve against the current directory.

    Flags ``Path("titan/x.py")``-style literals whose first segment is a repo
    top-level entry, ``Path(".")``, and repo-relative argv entries of
    subprocess calls that do not pass ``cwd=``.
    """

    def is_repo_relative(value: str) -> bool:
        first = value.replace("\\", "/").split("/", 1)[0]
        return value in {".", "./"} or (bool(first) and first in top_level)

    hits = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = _call_name(node.func)
        arg = node.args[0]
        if name in _PATH_CALLS:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and is_repo_relative(arg.value):
                hits.append((node.lineno, arg.value))
        elif name in _SUBPROCESS_CALLS and isinstance(arg, (ast.List, ast.Tuple)):
            if any(kw.arg == "cwd" for kw in node.keywords):
                continue
            for elt in arg.elts:
                if (
                    isinstance(elt, ast.Constant)
                    and isinstance(elt.value, str)
                    and is_repo_relative(elt.value)
                ):
                    hits.append((node.lineno, elt.value))
    return sorted(hits)


@pytest.mark.unit
def test_detector_flags_cwd_relative_literal():
    src = 'from pathlib import Path\nPath("titan/main.py").read_text()\nopen("README.md")\n'
    assert cwd_relative_paths(src, {"titan", "README.md"}) == [
        (2, "titan/main.py"),
        (3, "README.md"),
    ]


@pytest.mark.unit
def test_detector_ignores_anchored_paths():
    src = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        'ROOT.joinpath("titan")\n'
        '(ROOT / "titan" / "main.py").read_text()\n'
        'Path("/tmp/x")\n'
    )
    assert cwd_relative_paths(src, {"titan"}) == []


@pytest.mark.unit
def test_detector_flags_cwd_dot_alembic_config_and_subprocess_without_cwd():
    src = (
        'check(Path("."))\n'
        'Config("alembic.ini")\n'
        'subprocess.run(["bash", "scripts/backup.sh"])\n'
        'subprocess.run(["bash", "scripts/backup.sh"], cwd=REPO_ROOT)\n'
    )
    assert cwd_relative_paths(src, {"alembic.ini", "scripts"}) == [
        (1, "."),
        (2, "alembic.ini"),
        (3, "scripts/backup.sh"),
    ]


@pytest.mark.unit
def test_no_test_reads_repo_files_relative_to_cwd():
    top_level = _top_level_entries()
    offenders = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        for line, literal in cwd_relative_paths(path.read_text(encoding="utf-8"), top_level):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {literal!r}")
    assert not offenders, (
        "Tests read repo files relative to the current directory; anchor them on "
        "REPO_ROOT = Path(__file__).resolve().parents[N] (AT-07):\n" + "\n".join(offenders)
    )
