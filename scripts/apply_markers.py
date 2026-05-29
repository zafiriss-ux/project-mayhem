"""
apply_markers.py — T5-15 automated marker assistant (DO NOT RUN automatically).

Reads each test file and identifies where to apply pytest markers:

  @pytest.mark.unit          → test functions with no tmp_path, no real DB,
                                all external calls mocked, no 'integration' in name
  @pytest.mark.integration   → test functions using tmp_path, creating DatabaseManager
                                with a real path, or using subprocess
  @pytest.mark.governance    → test functions in files named test_governance_*,
                                test_p0_*, or test_architectural_*
  @pytest.mark.slow          → test functions containing sleep() calls

This script is ADDITIVE only — it does not remove existing marks.

Usage:
    python scripts/apply_markers.py [--dry-run] [file ...]

If no files are given, scans all tests/ and test_*.py.

NOTE: T5-15 Phase A (12 priority files) was completed manually on 2026-05-25.
      Phase B (100+ remaining files) uses this script as a guide.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path


def _has_param(func: ast.FunctionDef, name: str) -> bool:
    return any(arg.arg == name for arg in func.args.args)


def _body_src(func: ast.FunctionDef, src_lines: list[str]) -> str:
    start = func.lineno - 1
    end = func.end_lineno or start + 1
    return "\n".join(src_lines[start:end])


def classify_function(func: ast.FunctionDef, src_lines: list[str], filepath: Path) -> str | None:
    """Return the marker name for a test function, or None if already marked."""
    existing_decorators = {
        d.attr if isinstance(d, ast.Attribute) else (d.id if isinstance(d, ast.Name) else "")
        for d in func.decorator_list
        if isinstance(d, (ast.Attribute, ast.Name))
    }
    # Also check Call decorators like @pytest.mark.integration
    for d in func.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
            existing_decorators.add(d.func.attr)

    known = {"unit", "integration", "governance", "slow"}
    if existing_decorators & known:
        return None  # already has a marker

    body = _body_src(func, src_lines)

    # Governance: file name pattern
    fname = filepath.name
    if any(fname.startswith(p) for p in ("test_governance_", "test_p0_", "test_architectural_")):
        return "governance"

    # Slow: sleep calls
    if "time.sleep" in body or "asyncio.sleep" in body:
        return "slow"

    # Integration: subprocess, tmp_path, real DB path
    if _has_param(func, "tmp_path"):
        return "integration"
    if "subprocess" in body:
        return "integration"
    if re.search(r'DatabaseManager\s*\(["\'](?!:memory:)', body):
        return "integration"

    return "unit"


def process_file(path: Path, dry_run: bool = False) -> int:
    src = path.read_text(encoding="utf-8")
    src_lines = src.splitlines()

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"SKIP {path}: SyntaxError {e}", file=sys.stderr)
        return 0

    # Collect imports
    has_pytest_import = any(
        (isinstance(n, ast.Import) and any(a.name == "pytest" for a in n.names))
        or (isinstance(n, ast.ImportFrom) and n.module == "pytest")
        for n in ast.walk(tree)
    )

    insertions: list[tuple[int, str]] = []  # (line_index, text_to_insert_before)
    needs_pytest_import = False

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        marker = classify_function(node, src_lines, path)
        if marker is None:
            continue
        insert_line = node.lineno - 1  # 0-indexed
        # If there are existing decorators, insert before the first one
        if node.decorator_list:
            insert_line = node.decorator_list[0].lineno - 1
        insertions.append((insert_line, f"@pytest.mark.{marker}"))
        needs_pytest_import = not has_pytest_import

    if not insertions:
        return 0

    if dry_run:
        for line_idx, decorator in sorted(insertions):
            print(f"  [{path.name}:{line_idx + 1}] {decorator}")
        return len(insertions)

    # Apply in reverse order so line numbers stay valid
    new_lines = list(src_lines)
    for line_idx, decorator in sorted(insertions, reverse=True):
        indent = ""
        new_lines.insert(line_idx, indent + decorator)

    if needs_pytest_import:
        # Insert after the last import block
        last_import = -1
        for i, line in enumerate(new_lines):
            if line.startswith("import ") or line.startswith("from "):
                last_import = i
        new_lines.insert(last_import + 1, "import pytest")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"  {path}: {len(insertions)} marker(s) applied")
    return len(insertions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pytest markers to test files (T5-15).")
    parser.add_argument("files", nargs="*", type=Path, help="Files to process")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    if args.files:
        targets = args.files
    else:
        targets = list(Path(".").glob("test_*.py")) + list(Path("tests").rglob("test_*.py"))

    total = 0
    for path in sorted(targets):
        n = process_file(path, dry_run=args.dry_run)
        total += n

    print(f"\nTotal: {total} marker(s) {'would be ' if args.dry_run else ''}applied across {len(targets)} file(s).")


if __name__ == "__main__":
    main()
