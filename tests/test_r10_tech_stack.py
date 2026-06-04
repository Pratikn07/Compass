from __future__ import annotations

import ast
from pathlib import Path


def test_r10_prd_exists_and_names_consolidated_stack() -> None:
    prd_path = Path("docs/prd/10-tech-stack-consolidated-prd.md")

    assert prd_path.exists()
    contents = prd_path.read_text(encoding="utf-8")
    for required in [
        "Python",
        "`uv`",
        "Claude Code",
        "MCP connectors",
        "SQLite",
        "cron",
    ]:
        assert required in contents


def test_readme_documents_canonical_stack_inventory() -> None:
    contents = Path("README.md").read_text(encoding="utf-8")

    assert "## Tech Stack" in contents
    assert "Python >=3.11" in contents
    assert "`uv run pytest -q`" in contents
    assert "`uv run ruff check .`" in contents
    assert "SQLite" in contents
    assert "Claude Code" in contents
    assert "MCP connectors" in contents
    assert "cron" in contents


def test_cron_operations_doc_describes_bounded_propose_only_jobs() -> None:
    cron_doc = Path("docs/ops/cron.md")

    assert cron_doc.exists()
    contents = cron_doc.read_text(encoding="utf-8").lower()
    assert "propose_only" in contents
    assert "uv run prescient scheduler cron-guard" in contents
    assert "bounded" in contents
    assert "no infinite polling" in contents
    assert "sqlite" in contents


def test_dependency_tooling_stays_on_uv_without_parallel_managers() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "requires-python = \">=3.11\"" in pyproject
    assert Path("uv.lock").exists()
    assert not Path("requirements.txt").exists()
    assert not Path("Pipfile").exists()
    assert not Path("poetry.lock").exists()


def test_deterministic_layers_avoid_sqlite_connector_and_claude_code_imports() -> None:
    forbidden_roots = {
        "sqlite3",
        "mcp",
        "claude_code",
        "prescient.storage.sqlite",
        "prescient.scheduler.cron",
    }
    deterministic_roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/data"),
    ]

    for root in deterministic_roots:
        for path in root.glob("*.py"):
            imports = _imports_for(path)
            assert not any(
                imported == forbidden or imported.startswith(f"{forbidden}.")
                for imported in imports
                for forbidden in forbidden_roots
            ), f"{path} imports forbidden R10 stack dependency: {imports}"


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
