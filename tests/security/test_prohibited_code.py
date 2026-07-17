from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def production_text() -> str:
    paths = [ROOT / "pyproject.toml", ROOT / "uv.lock", *sorted((ROOT / "src").rglob("*.py"))]
    return "\n".join(path.read_text() for path in paths if path.exists())


def web_text() -> str:
    suffixes = {".ts", ".tsx", ".js", ".mjs", ".json"}
    paths = [
        path
        for path in (ROOT / "web").rglob("*")
        if path.is_file()
        and path.suffix in suffixes
        and "node_modules" not in path.parts
        and ".next" not in path.parts
    ]
    return "\n".join(path.read_text() for path in paths)


def test_production_has_no_execution_or_ai_analyst_dependencies() -> None:
    text = production_text()
    prohibited = {
        "order submission": r"\.submit_order\s*\(",
        "order cancellation": r"\.cancel_order\w*\s*\(",
        "Alpaca trading client": r"\bTradingClient\b",
        "Robinhood": r"\brobin_stocks\b|\brobin-stocks\b",
        "broker package": r"(?:from|import)\s+\w+(?:\.\w+)*\.broker\b",
        "Anthropic dependency": r"\banthropic\b",
        "OpenAI analyst dependency": r'(?m)^\s*["\']openai(?:[<=>~!]|["\'])',
    }

    failures = [label for label, pattern in prohibited.items() if re.search(pattern, text)]

    assert failures == []


def test_browser_bundle_sources_contain_no_server_secrets() -> None:
    text = web_text()

    assert "NEXT_PUBLIC_COMPASS_KEY" not in text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in text
    assert "X-Compass-Key" not in text
