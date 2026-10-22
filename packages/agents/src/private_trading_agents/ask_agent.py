"""Ask AI surface — AG-02 knowledge tools only; never trade authority.

Product path for questions against the private corpus. Uses the least-privilege
tool gate + policy seal. Does not call strategy/risk/workflow.finish and cannot
emit ENTER.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal

from private_trading_ai_gateway import AIGateway
from private_trading_core.config import Settings
from private_trading_core.errors import ForbiddenError
from private_trading_knowledge.ask import AskResult, ask_knowledge
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_agents.agent_runtime import agent_session, call_tool
from private_trading_agents.contracts import AgentId
from private_trading_agents.external_backends import PrefetchedKnowledgeBackend
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.tools.injection import (
    PolicyTamperError,
    assert_tool_policy_intact,
    looks_like_injection,
    policy_fingerprint,
    wrap_untrusted,
)
from private_trading_agents.tools.external_schemas import KnowledgeAskOut
from private_trading_agents.tools.permissions import has_permission

# Tools Ask AI must never be able to invoke (defense in depth beyond allowlist).
_ASK_BANNED_TOOLS = frozenset(
    {
        ToolId.WORKFLOW_FINISH,
        ToolId.RISK_ASSESS,
        ToolId.STRATEGY_EVALUATE,
        ToolId.FEATURES_COMPUTE,
        ToolId.SIGNAL_CHECK_GATES,
        ToolId.ML_RANK,
        ToolId.AGENT_RUN_RISK,
        ToolId.AGENT_RUN_STRATEGY,
        ToolId.AGENT_RUN_SIGNAL,
        ToolId.AGENT_RUN_ML,
        ToolId.AGENT_RUN_MARKET_DATA,
    }
)


class AskTradeAuthorityError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__(
            "Ask AI has no trade authority",
            details={"agent": AgentId.AG02_KNOWLEDGE.value, "authorizes_trade": False},
        )
        self.code = "ASK_NO_TRADE_AUTHORITY"


@dataclass(slots=True)
class AskAgentResult:
    answer: str
    sufficient_evidence: bool
    confidence: str
    citations: list[dict[str, Any]]
    retrieval_event_id: uuid.UUID
    conflicts: list[str]
    model: str
    prompt_version: str
    agent: str = AgentId.AG02_KNOWLEDGE.value
    tool: str = ToolId.KNOWLEDGE_ASK.value
    authorizes_trade: Literal[False] = False
    decision_action: None = None
    treated_as_untrusted_data: Literal[True] = True
    injection_shaped_question: bool = False
    tool_traces: list[dict[str, Any]] = field(default_factory=list)
    policy_fingerprint: str = ""
    external_tool_gated: bool = False

    def meta(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "tool": self.tool,
            "authorizes_trade": False,
            "decision_action": None,
            "treated_as_untrusted_data": True,
            "injection_shaped_question": self.injection_shaped_question,
            "tool_traces": list(self.tool_traces),
            "policy_fingerprint": self.policy_fingerprint,
            "external_tool_gated": self.external_tool_gated,
            "surface": "ask_ai",
        }


def assert_ask_surface_permissions() -> None:
    """Fail closed if AG-02 gained trade tools or lost knowledge.ask."""
    if not has_permission(AgentId.AG02_KNOWLEDGE, ToolId.KNOWLEDGE_ASK):
        raise ForbiddenError(
            "AG-02 is not permitted to invoke knowledge.ask",
            details={"agent": "AG-02", "tool": "knowledge.ask"},
        )
    for tool in _ASK_BANNED_TOOLS:
        if has_permission(AgentId.AG02_KNOWLEDGE, tool):
            raise AskTradeAuthorityError()


async def run_ask_agent(
    session: AsyncSession,
    *,
    question: str,
    user_id: uuid.UUID,
    settings: Settings,
    gateway: AIGateway,
    strategy_tag: str | None = None,
    asset_class: str | None = None,
    timeframe_tag: str | None = None,
) -> AskAgentResult:
    """Answer via AG-02 knowledge.ask under sealed tool policy; no trade authority."""
    assert_ask_surface_permissions()
    assert_tool_policy_intact()
    sealed = policy_fingerprint()

    untrusted = wrap_untrusted(question, source="user")
    injection_shaped = looks_like_injection(untrusted.text)

    with agent_session() as agent_sess:
        started = perf_counter()
        try:
            result: AskResult = await ask_knowledge(
                session,
                question=untrusted.text,
                user_id=user_id,
                settings=settings,
                gateway=gateway,
                strategy_tag=strategy_tag,
                asset_class=asset_class,
                timeframe_tag=timeframe_tag,
            )
            # Pass through gated EXTERNAL tool with request-scoped enable + live backend.
            gated = call_tool(
                agent=AgentId.AG02_KNOWLEDGE,
                tool=ToolId.KNOWLEDGE_ASK,
                payload={"question": untrusted.text},
                context=ToolContext(
                    extras={
                        "external_tools_enabled": True,
                        "knowledge_backend": PrefetchedKnowledgeBackend(result),
                        "wrap_untrusted_for_backend": True,
                    }
                ),
                note="ask_ai_external_gate",
            )
            assert isinstance(gated, KnowledgeAskOut)
            duration_ms = round((perf_counter() - started) * 1000.0, 3)
            del duration_ms  # traced via call_tool session
            external_tool_gated = True
        except Exception:
            raise

        traces = agent_sess.as_dicts()

    assert_tool_policy_intact()
    if policy_fingerprint() != sealed:
        raise PolicyTamperError("Ask AI observed tool-policy fingerprint drift")
    assert_ask_surface_permissions()

    return AskAgentResult(
        answer=result.answer,
        sufficient_evidence=result.sufficient_evidence,
        confidence=result.confidence,
        citations=list(result.citations),
        retrieval_event_id=result.retrieval_event_id,
        conflicts=list(result.conflicts),
        model=result.model,
        prompt_version=result.prompt_version,
        injection_shaped_question=injection_shaped,
        tool_traces=traces,
        policy_fingerprint=sealed,
        external_tool_gated=external_tool_gated,
    )
