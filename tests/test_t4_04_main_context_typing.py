import ast
from pathlib import Path

import pytest


def _load_module(path: str) -> ast.Module:
    return ast.parse(Path(path).read_text())


@pytest.mark.unit
@pytest.mark.governance
def test_t4_04_typed_context_contract_exists_in_contracts_module():
    module = _load_module("titan/orchestration/contracts.py")

    typed_dict_classes = {
        node.name: node
        for node in module.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "TypedDict" for base in node.bases)
    }
    dataclass_classes = {
        node.name
        for node in module.body
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(dec, ast.Name) and dec.id == "dataclass")
            or (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Name)
                and dec.func.id == "dataclass"
            )
            for dec in node.decorator_list
        )
    }

    assert "AthleteProfile" in typed_dict_classes
    assert "TitanContext" in typed_dict_classes
    assert "TitanContextContract" in dataclass_classes


@pytest.mark.unit
@pytest.mark.governance
def test_t4_04_main_uses_titan_context_contract_constructor():
    module = _load_module("titan/main.py")

    register_fn = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_register_telegram_callbacks"
    )
    ctx_arg = next(arg for arg in register_fn.args.args if arg.arg == "ctx")

    assert isinstance(ctx_arg.annotation, ast.Name)
    assert ctx_arg.annotation.id == "TitanContext"

    main_fn = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    titan_ctx_assign = next(
        node
        for node in ast.walk(main_fn)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "titan_ctx"
    )

    assert isinstance(titan_ctx_assign.annotation, ast.Name)
    assert titan_ctx_assign.annotation.id == "TitanContext"
    assert isinstance(titan_ctx_assign.value, ast.Call)
    assert isinstance(titan_ctx_assign.value.func, ast.Attribute)
    assert titan_ctx_assign.value.func.attr == "to_payload"
    assert isinstance(titan_ctx_assign.value.func.value, ast.Call)
    assert isinstance(titan_ctx_assign.value.func.value.func, ast.Name)
    assert titan_ctx_assign.value.func.value.func.id == "TitanContextContract"
