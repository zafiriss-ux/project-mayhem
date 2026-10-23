"""MA-F3 8γ (D-124): worker and orchestration code always names the athlete.

Every call from ``titan/worker`` or ``titan/orchestration`` to a TITAN function or class
whose ``athlete_id`` defaults to ``"owner"`` passes the athlete, by keyword or in its
position. A missing id then cannot silently become the owner's on another athlete's run.
"""

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1] / "titan"
_CALLER_DIRS = ("worker", "orchestration")


def _athlete_slots(args: ast.arguments) -> int | None:
    """The positional index of an ``athlete_id="owner"`` parameter, -1 if keyword-only, None if none."""
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    for index, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        if arg.arg == "athlete_id" and isinstance(default, ast.Constant) and default.value == "owner":
            return index
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        if arg.arg == "athlete_id" and isinstance(default, ast.Constant) and default.value == "owner":
            return -1
    return None


def _owner_defaults() -> dict[str, set[int]]:
    """Callable name → positional slots of its owner-defaulted athlete_id (self dropped)."""
    found: dict[str, set[int]] = {}
    for path in _ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        slot = _athlete_slots(item.args)
                        if slot is not None:
                            found.setdefault(node.name, set()).add(slot - 1 if slot > 0 else slot)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__":
                slot = _athlete_slots(node.args)
                if slot is not None:
                    is_method = bool(node.args.args) and node.args.args[0].arg in ("self", "cls")
                    found.setdefault(node.name, set()).add(slot - 1 if is_method and slot > 0 else slot)
    return found


def _calls_without_an_athlete() -> list[str]:
    defaults = _owner_defaults()
    missing = []
    for folder in _CALLER_DIRS:
        for path in sorted((_ROOT / folder).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name not in defaults:
                    continue
                if any(k.arg == "athlete_id" or k.arg is None for k in node.keywords):
                    continue
                if any(slot >= 0 and len(node.args) > slot for slot in defaults[name]):
                    continue
                missing.append(f"{path.relative_to(_ROOT.parent)}:{node.lineno} {name}")
    return missing


@pytest.mark.unit
def test_worker_and_orchestration_never_rely_on_the_owner_default():
    assert _calls_without_an_athlete() == []


@pytest.mark.unit
def test_the_sweep_sees_the_callers_it_must_check():
    # The sweep is only worth something if it finds the owner-defaulted APIs at all.
    defaults = _owner_defaults()
    for name in ("DailyCoach", "OutcomeTracker", "save_daily_metric", "get_governance_decisions"):
        assert name in defaults
