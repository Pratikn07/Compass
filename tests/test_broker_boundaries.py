from __future__ import annotations

import ast
from pathlib import Path


def test_broker_package_has_no_forbidden_dependencies() -> None:
    forbidden_roots = {
        "prescient.signal",
        "prescient.analyst",
        "prescient.events",
        "prescient.scheduler",
        "prescient.runtime",
        "anthropic",
        "openai",
    }

    for path in Path("src/prescient/broker").glob("*.py"):
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
        ), f"{path} imports a forbidden broker dependency: {imports}"
