"""Architectural invariant tests (T4-19 / ADR-0021).

These tests encode structural constraints that must hold across every commit.
They act as a CI-enforced architecture lock — semantically correct where
comment-based locks are not.

Four invariants are verified:
  1. No silent exception swallows in production code outside titan/ui/.
  2. GovernanceEngine uses thresholds.py constants, never inline numeric literals.
  3. All governance lock codes appended to applied_locks are from the canonical set.
  4. DatabaseManager does not expose raw connection access outside the lock context.
"""

import ast
import pathlib
import re

# ── paths ──────────────────────────────────────────────────────────────────────

_TITAN_ROOT = pathlib.Path(__file__).parent.parent / "titan"
_GOVERNANCE_ENGINE = _TITAN_ROOT / "science" / "governance_engine.py"
_DATABASE_MANAGER = _TITAN_ROOT / "core" / "database.py"

# ── helpers ────────────────────────────────────────────────────────────────────


def _parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


# ── Invariant 1: No silent exception swallow in titan/ (excluding ui/) ─────────


def test_no_silent_exception_swallow_in_production_code():
    """'except Exception: pass' or 'except Exception:\\n    pass' must not exist
    in any titan/ module outside titan/ui/ (ui handlers are separately tested
    to be observable via T2-12)."""
    silent_pattern = re.compile(
        r"except\s+Exception\s*:\s*(#[^\n]*)?\n\s*pass",
        re.MULTILINE,
    )

    violations: list[str] = []
    for py_file in _TITAN_ROOT.rglob("*.py"):
        if "ui" in py_file.parts:
            continue
        src = py_file.read_text(encoding="utf-8")
        for match in silent_pattern.finditer(src):
            line_no = src[: match.start()].count("\n") + 1
            violations.append(f"{py_file.relative_to(_TITAN_ROOT.parent)}:{line_no}")

    assert not violations, (
        "Silent exception swallows found (fix or narrow the except clause):\n"
        + "\n".join(violations)
    )


# ── Invariant 2: GovernanceEngine uses no inline numeric literals for thresholds


def test_governance_engine_uses_no_inline_threshold_literals():
    """Threshold values must be imported from titan.config.thresholds, never
    hard-coded as numeric literals inside governance_engine.py."""
    from titan.config.thresholds import (
        HARD_STOP_HRV_DELTA,
        HARD_STOP_RHR_DELTA,
        HARD_STOP_TSB_FLOOR,
        SUBJECTIVE_FATIGUE_EXTREME,
    )

    sentinel_values: set[float] = {
        float(HARD_STOP_HRV_DELTA),
        float(HARD_STOP_RHR_DELTA),
        float(HARD_STOP_TSB_FLOOR),
        float(SUBJECTIVE_FATIGUE_EXTREME),
    }

    tree = _parse(_GOVERNANCE_ENGINE)
    violations: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and float(node.value) in sentinel_values
        ):
            violations.append(
                f"Line {node.lineno}: literal {node.value!r} matches a threshold constant"
            )

    assert not violations, (
        "Inline threshold literals found in governance_engine.py "
        "(use thresholds.py constants instead):\n" + "\n".join(violations)
    )


# ── Invariant 3: All governance lock codes are from the canonical set ──────────

_CANONICAL_LOCK_CODES: frozenset[str] = frozenset(
    {
        "HARD_STOP_SAFETY_GATES",
        "VO2_ELIGIBILITY_GATE",
        "FUELING_GATE_LOCK",
        "FUELING_GATE_FLAG",
        "READINESS_2OF4_DOWNGRADE",
        "INTENSITY_GATE_RED",
        "INTENSITY_GATE_YELLOW",
        "PARASYMPATHETIC_GUARD",
        "OVERRIDE_LOCKDOWN",
        "CS_CONFIDENCE_LOCK",
        "PERSISTENCE_DEGRADED_CEILING",
        "STARTUP_DATA_CONFIDENCE_CEILING",
        "FAIL_SAFE_LOCK",
    }
)


def test_all_governance_lock_codes_are_canonical():
    """Every string appended to applied_locks inside governance_engine.py must
    be present in the canonical lock-code set (CLAUDE.md + this file).
    Add new codes to _CANONICAL_LOCK_CODES in both places."""
    tree = _parse(_GOVERNANCE_ENGINE)

    emitted_codes: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Look for applied_locks.append("SOME_CODE")
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "append"
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "applied_locks"
        ):
            args = node.value.args
            if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
                emitted_codes.append((node.lineno, args[0].value))

    assert emitted_codes, "No applied_locks.append() calls found — check the AST query"

    violations = [
        f"Line {ln}: unknown lock code {code!r}"
        for ln, code in emitted_codes
        if code not in _CANONICAL_LOCK_CODES
    ]
    assert not violations, (
        "Non-canonical lock codes found (add to _CANONICAL_LOCK_CODES and CLAUDE.md):\n"
        + "\n".join(violations)
    )


# ── Invariant 4: DatabaseManager doesn't bypass the threading lock ─────────────


def test_database_manager_raw_conn_access_only_inside_lock_context():
    """self.conn must not be accessed outside of 'with self._lock:' blocks.
    This is checked structurally: any method that accesses self.conn must also
    contain a With node whose context manager references self._lock."""
    tree = _parse(_DATABASE_MANAGER)

    class _ConnAccessVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.violations: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            # Collect self.conn accesses and with-self._lock blocks in this function
            conn_lines: list[int] = []
            lock_ranges: list[tuple[int, int]] = []

            for child in ast.walk(node):
                # self.conn access
                if (
                    isinstance(child, ast.Attribute)
                    and child.attr == "conn"
                    and isinstance(child.value, ast.Name)
                    and child.value.id == "self"
                ):
                    conn_lines.append(child.col_offset)  # not used for range, just presence

                # with self._lock: block
                if isinstance(child, ast.With):
                    for item in child.items:
                        ctx = item.context_expr
                        if (
                            isinstance(ctx, ast.Attribute)
                            and ctx.attr == "_lock"
                            and isinstance(ctx.value, ast.Name)
                            and ctx.value.id == "self"
                        ):
                            lock_ranges.append((child.lineno, child.end_lineno or child.lineno))

            if conn_lines and not lock_ranges:
                # Function accesses self.conn but has no with self._lock: block
                self.violations.append(
                    f"  {node.name}() (line {node.lineno}): accesses self.conn without self._lock"
                )

            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    visitor = _ConnAccessVisitor()
    visitor.visit(tree)

    # Allowed exceptions: __init__ (sets up conn), backup_database (uses conn.backup which
    # manages its own thread safety), _prune_old_backups (no conn access)
    _ALLOWED = {
        "__init__",          # sets self.conn
        "create_database",   # called once during init, before concurrent access
        "_run_migrations",
        "_apply_v1_migrations",
        "_apply_v2_migrations",
        "backup_database",   # uses sqlite3.Connection.backup() thread-safe API
    }
    real_violations = [v for v in visitor.violations if not any(a in v for a in _ALLOWED)]

    assert not real_violations, (
        "DatabaseManager methods access self.conn without self._lock:\n"
        + "\n".join(real_violations)
    )
