"""Claude analyst layer for reviewed strategy candidates."""

from prescient.analyst.claude import (
    ClaudeCompletionClient,
    analyze_candidate_brief,
    analyze_strategy_decision,
)
from prescient.analyst.models import (
    ClaudeAnalysisResult,
    ClaudeAnalysisStatus,
    ClaudeAnalystSettings,
    ClaudeRecommendation,
    ClaudeStrategyAnalysis,
    SubAgentAnalysis,
    SubAgentName,
    SubAgentResult,
    SubAgentReviewPacket,
    SubAgentStatus,
)
from prescient.analyst.prompt import build_claude_strategy_prompt
from prescient.analyst.sub_agents import (
    DEFAULT_SUB_AGENTS,
    SUB_AGENT_PROMPT_VERSION,
    analyze_strategy_decision_with_sub_agents,
    analyze_sub_agent,
    build_sub_agent_prompt,
)

__all__ = [
    "ClaudeAnalysisResult",
    "ClaudeAnalysisStatus",
    "ClaudeAnalystSettings",
    "ClaudeCompletionClient",
    "ClaudeRecommendation",
    "ClaudeStrategyAnalysis",
    "DEFAULT_SUB_AGENTS",
    "SUB_AGENT_PROMPT_VERSION",
    "SubAgentAnalysis",
    "SubAgentName",
    "SubAgentResult",
    "SubAgentReviewPacket",
    "SubAgentStatus",
    "analyze_candidate_brief",
    "analyze_strategy_decision_with_sub_agents",
    "analyze_strategy_decision",
    "analyze_sub_agent",
    "build_claude_strategy_prompt",
    "build_sub_agent_prompt",
]
