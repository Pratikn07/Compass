from __future__ import annotations

import ast
from pathlib import Path


def test_deterministic_and_broker_layers_do_not_import_learning_package() -> None:
    forbidden_import = "prescient.learning"
    roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/broker"),
    ]

    for root in roots:
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
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

            assert not any(
                imported == forbidden_import or imported.startswith(f"{forbidden_import}.")
                for imported in imports
            ), f"{path} imports the learning cold-path package: {imports}"


def test_learning_package_has_no_network_broker_or_llm_dependencies() -> None:
    forbidden_roots = {
        "anthropic",
        "openai",
        "httpx",
        "alpaca",
        "robin_stocks",
        "prescient.analyst",
        "prescient.broker",
        "prescient.data",
    }
    forbidden_calls = {
        "requests.get",
        "requests.post",
        "httpx.get",
        "httpx.post",
        "place_order",
    }

    for path in Path("src/prescient/learning").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
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

        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_roots
        ), f"{path} imports forbidden learning dependency: {imports}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                assert _call_name(node.func) not in forbidden_calls


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
