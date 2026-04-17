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
import io
import pathlib
import re
import tokenize

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
        "DATA_MISSING_CONSERVATIVE_H2",
        "DATA_MISSING_CONSERVATIVE_H3",
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


# ── Invariant 4b: UTC-only timestamps in governance/sync path (HR-01/HD-02) ────


_GOVERNANCE_PATH_FILES = [
    _TITAN_ROOT / "orchestration" / "daily_coach.py",
    _TITAN_ROOT / "science" / "governance_engine.py",
    _TITAN_ROOT / "integrations" / "garmin_sync.py",
]

_NAIVE_DATETIME_NOW = re.compile(
    r"datetime\.now\(\s*\)",  # datetime.now() with no arguments
)


def test_governance_path_no_naive_datetime_now():
    """No production code in the governance/sync path may call datetime.now()
    without a timezone argument.  Use datetime.now(UTC) per HR-01.

    Scoped to: daily_coach.py, governance_engine.py, garmin_sync.py.
    """
    violations: list[str] = []
    for path in _GOVERNANCE_PATH_FILES:
        src = path.read_text(encoding="utf-8")
        for match in _NAIVE_DATETIME_NOW.finditer(src):
            line_no = src[: match.start()].count("\n") + 1
            violations.append(
                f"{path.relative_to(_TITAN_ROOT.parent)}:{line_no} — "
                f"naive datetime.now() (use datetime.now(UTC))"
            )
    assert not violations, (
        "Naive datetime.now() found in governance/sync path (HR-01):\n"
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


# ── T5-75-A: _decision_pipeline() has exactly one production call site ─────────


def test_decision_pipeline_has_single_production_call_site() -> None:
    """_decision_pipeline() must have exactly one call site in titan/ production code.

    The method is defined on DailyCoach and must only be invoked from
    coaching_pipeline() (ADR-0018 kernel boundary: Decision Pipeline / Effect Runner
    split).  A second call site would bypass the boundary and violate the invariant
    that _decision_pipeline is a pure, side-effect-free function.
    """
    call_sites: list[str] = []

    for path in _TITAN_ROOT.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute) and func.attr == "_decision_pipeline"
                ) or (
                    isinstance(func, ast.Name) and func.id == "_decision_pipeline"
                ):
                    rel = path.relative_to(_TITAN_ROOT.parent)
                    call_sites.append(f"{rel}:{node.lineno}")

    n = len(call_sites)
    assert n == 1, (
        f"Found {n} call site(s) for _decision_pipeline() — expected exactly 1.\n"
        f"Sites: {call_sites}"
    )


# ── T5-75-B: All GovernanceEngine _gate_/_check_ methods wired into apply_constraints


def _collect_called_attr_names(node: ast.AST) -> set[str]:
    """Return attribute names that appear as calls anywhere in the given AST subtree."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            names.add(child.func.attr)
    return names


def test_all_gate_methods_called_from_apply_constraints() -> None:
    """Every _gate_ / _check_ class method on GovernanceEngine must appear as a
    call inside apply_constraints().

    Rationale: a gate method defined on GovernanceEngine but never invoked from
    apply_constraints() is dead code in the governance critical path — a safety
    defect per ADR-0009 / DECISION_MODEL §4.  This test locks the wiring so that
    new gate methods cannot be added without being hooked into the constraint loop.
    """
    source = _GOVERNANCE_ENGINE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(_GOVERNANCE_ENGINE))

    governance_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "GovernanceEngine":
            governance_class = node
            break

    assert governance_class is not None, (
        "GovernanceEngine class not found in governance_engine.py"
    )

    gate_methods: list[str] = []
    apply_constraints_node: ast.FunctionDef | None = None

    for item in governance_class.body:
        if isinstance(item, ast.FunctionDef):
            if item.name.startswith("_gate_") or item.name.startswith("_check_"):
                gate_methods.append(item.name)
            if item.name == "apply_constraints":
                apply_constraints_node = item

    assert apply_constraints_node is not None, (
        "apply_constraints() method not found in GovernanceEngine"
    )
    assert gate_methods, (
        "No _gate_/_check_ class methods found in GovernanceEngine — "
        "check the naming convention or the class definition"
    )

    called_names = _collect_called_attr_names(apply_constraints_node)

    missing = [m for m in gate_methods if m not in called_names]
    assert not missing, (
        f"Gate method(s) defined on GovernanceEngine but not called from "
        f"apply_constraints(): {missing}"
    )
