"""Ask AI agent surface: AG-02 only, no trade authority."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from private_trading_agents.ask_agent import (
    AskTradeAuthorityError,
    assert_ask_surface_permissions,
    run_ask_agent,
)
from private_trading_agents.contracts import AgentId
from private_trading_agents.tools import ToolId, has_permission
from private_trading_agents.tools.injection import (
    assert_tool_policy_intact,
    injection_corpus,
)
from private_trading_knowledge.ask import AskResult


@dataclass
class _FakeSettings:
    main_model: str = "test-model"


@pytest.mark.asyncio
async def test_ask_agent_no_trade_authority_and_traces(monkeypatch: pytest.MonkeyPatch) -> None:
    event_id = uuid.uuid4()

    async def _fake_ask(*args, **kwargs):  # noqa: ANN001
        return AskResult(
            answer="BOS is break of structure.",
            sufficient_evidence=True,
            confidence="medium",
            citations=[
                {
                    "document_id": str(uuid.uuid4()),
                    "chunk_id": str(uuid.uuid4()),
                    "page": 1,
                    "title": "Course",
                    "authority_tier": 1,
                    "score": 0.9,
                }
            ],
            retrieval_event_id=event_id,
            conflicts=[],
            model="test-model",
            prompt_version="knowledge.ask.v1",
        )

    monkeypatch.setattr(
        "private_trading_agents.ask_agent.ask_knowledge",
        _fake_ask,
    )
    result = await run_ask_agent(
        MagicMock(),
        question="What is BOS?",
        user_id=uuid.uuid4(),
        settings=_FakeSettings(),  # type: ignore[arg-type]
        gateway=MagicMock(),
    )
    assert result.authorizes_trade is False
    assert result.decision_action is None
    assert result.agent == "AG-02"
    assert result.tool == "knowledge.ask"
    assert result.treated_as_untrusted_data is True
    assert result.tool_traces
    assert result.tool_traces[0]["tool"] == "knowledge.ask"
    assert result.tool_traces[0]["status"] == "ok"
    assert result.meta()["authorizes_trade"] is False
    assert_tool_policy_intact()


@pytest.mark.asyncio
async def test_ask_agent_flags_injection_shaped_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "private_trading_agents.ask_agent.ask_knowledge",
        AsyncMock(
            return_value=AskResult(
                answer="Insufficient evidence.",
                sufficient_evidence=False,
                confidence="none",
                citations=[],
                retrieval_event_id=uuid.uuid4(),
                conflicts=[],
                model="test-model",
                prompt_version="knowledge.ask.v1",
            )
        ),
    )
    evil = injection_corpus()[0]["text"]
    result = await run_ask_agent(
        MagicMock(),
        question=evil,
        user_id=uuid.uuid4(),
        settings=_FakeSettings(),  # type: ignore[arg-type]
        gateway=MagicMock(),
    )
    assert result.injection_shaped_question is True
    assert result.authorizes_trade is False
    # Injection still cannot grant AG-02 trade tools.
    assert not has_permission(AgentId.AG02_KNOWLEDGE, ToolId.RISK_ASSESS)
    assert not has_permission(AgentId.AG02_KNOWLEDGE, ToolId.WORKFLOW_FINISH)


def test_ask_surface_permissions_deny_if_trade_tool_granted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = has_permission

    def _spoof(agent, tool):  # noqa: ANN001
        if agent == AgentId.AG02_KNOWLEDGE and tool == ToolId.RISK_ASSESS:
            return True
        return real(agent, tool)

    monkeypatch.setattr(
        "private_trading_agents.ask_agent.has_permission",
        _spoof,
    )
    with pytest.raises(AskTradeAuthorityError):
        assert_ask_surface_permissions()


def test_ask_surface_requires_knowledge_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "private_trading_agents.ask_agent.has_permission",
        lambda agent, tool: False,
    )
    with pytest.raises(Exception) as exc:
        assert_ask_surface_permissions()
    assert "knowledge.ask" in str(exc.value).lower() or getattr(exc.value, "code", "")
