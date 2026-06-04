from __future__ import annotations

import ast
from pathlib import Path


def test_hot_path_packages_do_not_import_backtest_package() -> None:
    forbidden_import = "prescient.backtest"
    roots = [
        Path("src/prescient/alerts"),
        Path("src/prescient/analyst"),
        Path("src/prescient/broker"),
        Path("src/prescient/data"),
        Path("src/prescient/events"),
        Path("src/prescient/risk"),
        Path("src/prescient/runtime"),
        Path("src/prescient/scheduler"),
        Path("src/prescient/signal"),
    ]

    for root in roots:
        for path in root.glob("*.py"):
            imports = _imports_for(path)
            assert not any(
                imported == forbidden_import or imported.startswith(f"{forbidden_import}.")
                for imported in imports
            ), f"{path} imports the backtest cold-path package: {imports}"


def test_backtest_package_has_no_live_broker_provider_or_llm_dependencies() -> None:
    forbidden_roots = {
        "alpaca",
        "anthropic",
        "dotenv",
        "httpx",
        "openai",
        "os",
        "robin_stocks",
        "prescient.alerts",
        "prescient.analyst",
        "prescient.broker",
        "prescient.data",
        "prescient.risk",
        "prescient.runtime",
        "prescient.scheduler",
    }
    forbidden_calls = {
        "date.today",
        "datetime.now",
        "datetime.utcnow",
        "httpx.get",
        "httpx.post",
        "place_order",
        "requests.get",
        "requests.post",
        "time.sleep",
    }

    for path in Path("src/prescient/backtest").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = _imports_for(path)
        assert "while True" not in source
        assert "authorization" not in source.lower()
        assert "raw_payload" not in source.lower()
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_roots
        ), f"{path} imports forbidden backtest dependency: {imports}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                assert _call_name(node.func) not in forbidden_calls


def _imports_for(path: Path) -> list[str]:
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
    return imports


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
