"""Athlete isolation invariants (T4-31 / AGENTS.md §16.10).

These tests are deterministic architecture guards for single-athlete shortcuts.
They fail with explicit messages when new cross-athlete assumptions are added.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TITAN_ROOT = Path(__file__).resolve().parents[1] / "titan"
_DATABASE_FILE = _TITAN_ROOT / "core" / "database.py"

# T5-80 retired all ADR-0040 annotations — no modules carry the shortcut tag.
_EXEMPT_SHORTCUT_MODULES: frozenset[Path] = frozenset()

_SHORTCUT_TAG = "ADR-0040-SINGLE-ATHLETE-SHORTCUT"
_SQL_DML_PREFIXES: tuple[str, ...] = ("SELECT", "UPDATE", "DELETE", "INSERT")
_SQL_SHAPE_TOKENS: tuple[str, ...] = (" FROM ", " INTO ", " SET ", " VALUES ", " WHERE ")
_SCHEMA_TABLES_ALLOWED_WITHOUT_ATHLETE_ID: frozenset[str] = frozenset({
    "sync_metadata",
    "login_lockout",  # system-level auth table — not per-athlete (TD-SEC-02)
})


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _sql_literals(path: Path) -> list[tuple[int, str]]:
    """Return SQL-like string literals as (lineno, uppercase-sql)."""
    sql_literals: list[tuple[int, str]] = []
    tree = _parse(path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue

        text = " ".join(node.value.split())
        upper = text.upper()
        if not upper.startswith(_SQL_DML_PREFIXES):
            continue
        if not any(token in upper for token in _SQL_SHAPE_TOKENS):
            continue

        sql_literals.append((node.lineno, upper))

    return sql_literals


@pytest.mark.unit
def test_exempt_modules_are_explicitly_annotated() -> None:
    missing_annotations: list[str] = []

    for rel_path in sorted(_EXEMPT_SHORTCUT_MODULES):
        source = (Path(__file__).resolve().parents[1] / rel_path).read_text(encoding="utf-8")
        if _SHORTCUT_TAG not in source:
            missing_annotations.append(str(rel_path))

    assert not missing_annotations, (
        "Every exemption-register module must keep the athlete isolation shortcut annotation "
        f"({_SHORTCUT_TAG}). Missing:\n" + "\n".join(missing_annotations)
    )


@pytest.mark.unit
def test_non_database_modules_do_not_add_sql_without_athlete_filter() -> None:
    """Outside titan/core/database.py, SQL-like literals must mention athlete_id."""
    violations: list[str] = []

    for py_file in sorted(_TITAN_ROOT.rglob("*.py")):
        if py_file == _DATABASE_FILE:
            continue

        for lineno, sql in _sql_literals(py_file):
            if "ATHLETE_ID" not in sql:
                rel = py_file.relative_to(_TITAN_ROOT.parent)
                violations.append(f"{rel}:{lineno} -> {sql[:140]}")

    assert not violations, (
        "Found SQL literals outside titan/core/database.py that omit athlete_id. "
        "This violates AGENTS.md §16.10 Rule A40-1:\n"
        + "\n".join(violations)
    )


@pytest.mark.unit
def test_outcome_tracker_query_methods_accept_athlete_id() -> None:
    """
    G-CI-07 extension: every public query method on OutcomeTracker must accept
    an athlete_id parameter so callers can scope reads per athlete.
    INV-04 enforcement (ADR-0033 Layer 3, Sub-decision L3-B).
    """
    import ast

    source = (_TITAN_ROOT / "science" / "outcome_tracker.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    _QUERY_METHODS = frozenset(
        {
            "record_outcome",
            "get_decisions",
            "get_lock_rate_by_phase",
            "get_lock_outcome_correlation",
            "get_calibration_summary",
            "check_calibration_diversity",
            "get_calibration_analytics",
        }
    )

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in _QUERY_METHODS:
            continue
        param_names = {arg.arg for arg in node.args.args} | {arg.arg for arg in node.args.kwonlyargs}
        if "athlete_id" not in param_names:
            violations.append(
                f"OutcomeTracker.{node.name}() at line {node.lineno} "
                "missing athlete_id parameter — INV-04 / G-CI-07 violation (ADR-0033 L3-B)"
            )

    assert not violations, "\n".join(violations)


@pytest.mark.unit
def test_migration_create_table_statements_include_athlete_id_or_are_explicitly_global() -> None:
    """New CREATE TABLE statements in migrations must include athlete_id by default."""
    tree = _parse(_DATABASE_FILE)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_apply_v"):
            continue

        for child in ast.walk(node):
            if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
                continue

            sql = " ".join(child.value.split())
            upper = sql.upper()
            if "CREATE TABLE" not in upper:
                continue

            parts = upper.split()
            table_name = None
            if "EXISTS" in parts:
                idx = parts.index("EXISTS")
                if idx + 1 < len(parts):
                    table_name = parts[idx + 1].strip("(")
            elif "TABLE" in parts:
                idx = parts.index("TABLE")
                if idx + 1 < len(parts):
                    table_name = parts[idx + 1].strip("(")

            if "ATHLETE_ID" in upper:
                continue

            if table_name and table_name.lower() in _SCHEMA_TABLES_ALLOWED_WITHOUT_ATHLETE_ID:
                continue

            violations.append(
                f"{node.name} line {child.lineno}: CREATE TABLE without athlete_id ({table_name or 'UNKNOWN_TABLE'})"
            )

    assert not violations, (
        "Migration CREATE TABLE statements must include athlete_id unless table is explicitly global:\n"
        + "\n".join(violations)
    )
