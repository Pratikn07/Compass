from __future__ import annotations

import ast
import re
from pathlib import Path


def test_deterministic_layers_do_not_import_alert_provider_adapters() -> None:
    forbidden_roots = {
        "prescient.alerts.adapters",
        "prescient.alerts.telegram",
        "prescient.alerts.discord",
        "prescient.alerts.email",
        "smtplib",
        "email.message",
        "sendgrid",
        "boto3",
    }
    httpx_forbidden_roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/broker"),
        Path("src/prescient/analyst"),
    ]
    forbidden_text_patterns = [
        re.compile(r"\btelegram\b"),
        re.compile(r"\bdiscord\b"),
        re.compile(r"\bsendgrid\b"),
        re.compile(r"\bsmtp\b"),
        re.compile(r"\bamazon\s+ses\b"),
    ]
    roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/broker"),
        Path("src/prescient/data"),
        Path("src/prescient/analyst"),
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
                imported == forbidden or imported.startswith(f"{forbidden}.")
                for imported in imports
                for forbidden in forbidden_roots
            ), f"{path} imports forbidden alert dependency: {imports}"
            if root in httpx_forbidden_roots:
                assert not any(
                    imported == "httpx" or imported.startswith("httpx.")
                    for imported in imports
                ), f"{path} imports httpx outside data/provider boundary: {imports}"
            text = path.read_text(encoding="utf-8").lower()
            assert not any(pattern.search(text) for pattern in forbidden_text_patterns)
