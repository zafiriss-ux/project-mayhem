import ast
from pathlib import Path


def _parsed_imports(path: str):
    module = ast.parse(Path(path).read_text())
    imports = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            imports.append((node.module, [alias.name for alias in node.names]))
    return imports


def test_t4_02_confirmed_unused_imports_removed():
    telegram_imports = _parsed_imports("titan/integrations/telegram_bot.py")
    assert ("telebot", ["types"]) not in telegram_imports

    evidence_imports = _parsed_imports("titan/config/evidence_registry.py")
    assert ("__future__", ["annotations"]) not in evidence_imports

    operator_imports = _parsed_imports("titan/ui/operator_console.py")
    assert ("__future__", ["annotations"]) not in operator_imports

    outcome_imports = _parsed_imports("titan/science/outcome_tracker.py")
    assert ("dataclasses", ["field"]) not in outcome_imports

    apl_imports = _parsed_imports("titan/science/adaptive_priority_lock.py")
    assert ("typing", ["Optional"]) not in apl_imports
