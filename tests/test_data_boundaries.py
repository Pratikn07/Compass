from __future__ import annotations

import ast
from pathlib import Path


def test_data_package_has_no_execution_cold_path_or_env_dependencies() -> None:
    forbidden_roots = {
        "anthropic",
        "alpaca",
        "claude_code",
        "dotenv",
        "mcp",
        "os",
        "sqlite3",
        "prescient.analyst",
        "prescient.broker",
        "prescient.events",
        "prescient.risk",
        "prescient.runtime",
        "prescient.scheduler",
        "prescient.storage.sqlite",
    }
    forbidden_calls = {
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.sleep",
        "asyncio.sleep",
    }

    for path in Path("src/prescient/data").glob("*.py"):
        phase_e_runtime = path.name == "runtime.py"
        active_forbidden_roots = (
            forbidden_roots - {"os", "prescient.storage.sqlite"}
            if phase_e_runtime
            else forbidden_roots
        )
        active_forbidden_calls = set() if phase_e_runtime else forbidden_calls
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
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

        assert "while True" not in source
        assert "place_order" not in source
        assert "broker_execution" not in source
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in active_forbidden_roots
        ), f"{path} imports a forbidden data dependency: {imports}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                assert call_name not in active_forbidden_calls, (
                    f"{path} uses hidden clock/sleep call {call_name}"
                )


def test_deterministic_layers_do_not_import_provider_data_adapters() -> None:
    deterministic_roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/runtime"),
        Path("src/prescient/scheduler"),
        Path("src/prescient/events"),
        Path("src/prescient/analyst"),
    ]

    for root in deterministic_roots:
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

            forbidden_adapters = {
                "prescient.data.alpha_vantage",
                "prescient.data.daloopa",
                "prescient.data.finnhub",
                "prescient.data.financial_datasets",
                "prescient.data.fmp",
                "prescient.data.sec_edgar",
            }
            assert not any(
                imported == adapter or imported.startswith(f"{adapter}.")
                for imported in imports
                for adapter in forbidden_adapters
            ), f"{path} imports a provider data adapter: {imports}"


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
