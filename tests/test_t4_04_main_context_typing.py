import ast
from pathlib import Path


def _load_main_module() -> ast.Module:
    return ast.parse(Path("titan/main.py").read_text())


def test_t4_04_typed_context_contract_exists():
    module = _load_main_module()

    typed_dict_classes = {
        node.name: node
        for node in module.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "TypedDict" for base in node.bases)
    }

    assert "AthleteProfile" in typed_dict_classes
    assert "TitanContext" in typed_dict_classes


def test_t4_04_main_uses_typed_context_annotations():
    module = _load_main_module()

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
    annotated_assignments = [
        node
        for node in ast.walk(main_fn)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]

    annotation_map = {
        node.target.id: node.annotation.id
        for node in annotated_assignments
        if isinstance(node.annotation, ast.Name)
    }

    assert annotation_map.get("athlete_profile") == "AthleteProfile"
    assert annotation_map.get("titan_ctx") == "TitanContext"
