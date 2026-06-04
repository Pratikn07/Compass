from __future__ import annotations

from prescient.signal.models import CandidateBrief


CLAUDE_ANALYST_PROMPT_VERSION = "r2.5-v1"


def build_claude_strategy_prompt(brief: CandidateBrief) -> str:
    candidate_json = brief.model_dump_json()

    return (
        "You are the Claude analyst layer for prescient.\n"
        f"Prompt version: {CLAUDE_ANALYST_PROMPT_VERSION}\n"
        "Read only the candidate brief JSON below and return strict JSON.\n\n"
        "Safety rules:\n"
        "- Claude must not override deterministic filters or risk limits.\n"
        "- Do not request broker credentials, account identifiers, or account data.\n"
        "- Do not invent missing financial data.\n"
        "- Do not choose position size.\n"
        "- Do not place trades or issue broker instructions.\n"
        "- Do not trade on a single headline.\n"
        "- Do not recommend tickers outside the configured theme.\n"
        "- Do not use conviction_score as a position size, risk budget, or trading "
        "authorization.\n"
        "- You may interpret provided technical_indicators fields. Do not "
        "calculate RSI, MACD, VWAP, moving averages, or crossover state.\n"
        "- Do not reconstruct indicators from raw candles, raw price streams, or "
        "unbounded market data.\n"
        "- Do not suggest position_size, order_quantity, broker_action, limit_price, "
        "stop_loss, take_profit, account_allocation, risk_override, or execute_trade.\n"
        "- Only suggest CALL_OPTION, STOCK, or NONE.\n\n"
        "Analyst output rules:\n"
        "- thesis must be based only on the candidate brief, name the target/theme, "
        "and avoid invented facts.\n"
        "- conviction_score must be an integer from 0 to 100, not a position size "
        "or risk budget.\n\n"
        "- cited_citation_ids may include only citation_id values present in the "
        "candidate brief source_citations.\n\n"
        "Return exactly this JSON shape with no extra fields:\n"
        "{\n"
        '  "recommendation": "go | no_go | needs_more_context",\n'
        '  "thesis": "short analyst thesis based only on the candidate brief",\n'
        '  "reasoning": "short deterministic explanation",\n'
        '  "conviction_score": 0,\n'
        '  "missing_context": ["structured context still needed"],\n'
        '  "contradictions": ["material contradiction"],\n'
        '  "suggested_expression": "CALL_OPTION | STOCK | NONE",\n'
        '  "cited_citation_ids": ["candidate brief citation_id"]\n'
        "}\n\n"
        f"Candidate brief JSON:\n{candidate_json}"
    )
