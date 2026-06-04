from __future__ import annotations

import ast
from pathlib import Path


def test_signal_risk_and_learning_do_not_import_broker_kill_switch_wrapper() -> None:
    forbidden_roots = {
        "prescient.broker",
        "prescient.broker.execution_guard",
    }
    roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/learning"),
    ]

    for root in roots:
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = _imports(tree)
            assert not any(
                imported == forbidden or imported.startswith(f"{forbidden}.")
                for imported in imports
                for forbidden in forbidden_roots
            ), f"{path} imports forbidden kill-switch broker dependency: {imports}"


def test_safety_package_has_no_llm_data_or_runtime_dependencies() -> None:
    forbidden_roots = {
        "anthropic",
        "openai",
        "httpx",
        "prescient.analyst",
        "prescient.data",
        "prescient.runtime",
        "prescient.signal",
    }

    for path in Path("src/prescient/safety").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = _imports(tree)
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_roots
        ), f"{path} imports forbidden safety dependency: {imports}"


def _imports(tree: ast.AST) -> list[str]:
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    imports.extend(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    return imports
