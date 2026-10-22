"""Least-privilege tool registry tests."""

from __future__ import annotations

import pytest
from private_trading_agents.adapters import candles_to_models
from private_trading_agents.contracts import AgentId
from private_trading_agents.tools import (
    AGENT_TOOL_ALLOWLIST,
    TOOL_CATALOG,
    SideEffect,
    ToolId,
    ToolPermissionError,
    UnknownToolError,
    allowed_tools,
    catalog_summary,
    has_permission,
    invoke_tool,
    permissions_matrix,
)
from private_trading_agents.tools.errors import SideEffectDeniedError
from private_trading_agents.tools.permissions import ALLOWED_SIDE_EFFECTS
from private_trading_backtest.fixtures import frozen_bos_long_fixture


def test_every_agent_has_an_explicit_allowlist_entry() -> None:
    for agent in AgentId:
        assert agent in AGENT_TOOL_ALLOWLIST


def test_orchestrator_only_has_routing_tools_and_journal_is_read_only() -> None:
    ag01 = allowed_tools(AgentId.AG01_ORCHESTRATOR)
    assert ToolId.AGENT_RUN_MARKET_DATA in ag01
    assert ToolId.WORKFLOW_FINISH in ag01
    assert ToolId.FEATURES_COMPUTE not in ag01
    assert ToolId.RISK_ASSESS not in ag01
    ag08 = allowed_tools(AgentId.AG08_JOURNAL)
    assert ToolId.JOURNAL_SUMMARIZE_METRICS in ag08
    assert ToolId.JOURNAL_NARRATE_PERFORMANCE in ag08
    assert ToolId.RISK_ASSESS not in ag08
    assert ToolId.WORKFLOW_FINISH not in ag08


def test_permissions_are_least_privilege_and_disjoint_where_expected() -> None:
    # Each registered tool is owned by exactly one agent (least privilege).
    owners: dict[ToolId, list[AgentId]] = {tool: [] for tool in ToolId}
    for agent, tools in AGENT_TOOL_ALLOWLIST.items():
        for tool in tools:
            owners[tool].append(agent)
    for tool, agents in owners.items():
        assert len(agents) == 1, f"{tool} owners={agents}"


def test_catalog_side_effects_are_none_read_or_gated_external() -> None:
    external_ids = {
        ToolId.KNOWLEDGE_RETRIEVE,
        ToolId.KNOWLEDGE_ASK,
        ToolId.VISION_EXTRACT,
        ToolId.LLM_NARRATE_FACTS,
    }
    for spec in TOOL_CATALOG.values():
        if spec.side_effect == SideEffect.EXTERNAL:
            assert spec.tool_id in external_ids
            assert spec.side_effect.value not in ALLOWED_SIDE_EFFECTS
        else:
            assert spec.side_effect.value in ALLOWED_SIDE_EFFECTS
            assert spec.side_effect in {SideEffect.NONE, SideEffect.READ}


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(UnknownToolError) as exc:
        invoke_tool(
            agent=AgentId.AG04_MARKET_DATA,
            tool="broker.place_order",
            payload={},
        )
    assert exc.value.code == "UNKNOWN_TOOL"


def test_cross_agent_tool_use_is_denied() -> None:
    # Strategy agent must not compute features.
    with pytest.raises(ToolPermissionError) as exc:
        invoke_tool(
            agent=AgentId.AG05_STRATEGY,
            tool=ToolId.FEATURES_COMPUTE,
            payload={"bars": [{"open_time": "2020-01-01T00:00:00Z",
                               "open": "1", "high": "1", "low": "1", "close": "1"}]},
        )
    assert exc.value.code == "TOOL_PERMISSION_DENIED"
    assert not has_permission(AgentId.AG05_STRATEGY, ToolId.FEATURES_COMPUTE)


def test_orchestrator_cannot_invoke_specialist_compute_tools() -> None:
    for tool in (
        ToolId.FEATURES_COMPUTE,
        ToolId.STRATEGY_EVALUATE,
        ToolId.RISK_ASSESS,
        ToolId.EXPLAIN_GROUNDED,
        ToolId.SIGNAL_CHECK_GATES,
        ToolId.VISION_CHECK_VERDICT,
        ToolId.ML_RANK,
    ):
        with pytest.raises(ToolPermissionError):
            invoke_tool(
                agent=AgentId.AG01_ORCHESTRATOR,
                tool=tool,
                payload={},
            )


def test_market_data_agent_can_compute_features() -> None:
    bars = frozen_bos_long_fixture()
    out = invoke_tool(
        agent=AgentId.AG04_MARKET_DATA,
        tool=ToolId.FEATURES_COMPUTE,
        payload={
            "bars": [b.model_dump() for b in candles_to_models(bars)],
            "bar_index": 40,
        },
    )
    assert out.features
    assert out.bar_index == 40


def test_permissions_matrix_is_auditable() -> None:
    matrix = permissions_matrix()
    assert "agent.run_market_data" in matrix["AG-01"]
    assert "workflow.finish" in matrix["AG-01"]
    assert "features.compute" not in matrix["AG-01"]
    assert matrix["AG-04"] == ["features.compute"]
    assert matrix["AG-06"] == ["risk.assess"]
    summary = catalog_summary()
    assert {row["tool"] for row in summary} == {t.value for t in ToolId}


def test_side_effect_policy_blocks_execute_class(monkeypatch: pytest.MonkeyPatch) -> None:
    from private_trading_agents.tools import catalog as catalog_mod
    from private_trading_agents.tools.catalog import ToolSpec
    from private_trading_agents.tools.schemas import FeaturesComputeIn, FeaturesComputeOut

    fake = ToolSpec(
        tool_id=ToolId.FEATURES_COMPUTE,
        description="tampered",
        side_effect=SideEffect.EXECUTE,
        input_model=FeaturesComputeIn,
        output_model=FeaturesComputeOut,
        handler=lambda payload: FeaturesComputeOut(
            bar_index=0,
            bar_open_time="2020-01-01T00:00:00Z",
            features={},
        ),
    )
    monkeypatch.setitem(catalog_mod.TOOL_CATALOG, ToolId.FEATURES_COMPUTE, fake)
    with pytest.raises(SideEffectDeniedError) as exc:
        invoke_tool(
            agent=AgentId.AG04_MARKET_DATA,
            tool=ToolId.FEATURES_COMPUTE,
            payload={
                "bars": [
                    {
                        "open_time": "2020-01-01T00:00:00Z",
                        "open": "1",
                        "high": "1",
                        "low": "1",
                        "close": "1",
                    }
                ]
            },
        )
    assert exc.value.code == "TOOL_SIDE_EFFECT_DENIED"

