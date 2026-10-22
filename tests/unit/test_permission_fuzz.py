"""Permission fuzz: every agent × every tool — deny by default."""

from __future__ import annotations

import pytest
from private_trading_agents.contracts import AgentId
from private_trading_agents.tools import (
    SideEffect,
    SideEffectDeniedError,
    ToolContext,
    ToolId,
    ToolPermissionError,
    get_tool,
    has_permission,
    invoke_tool,
)
from private_trading_agents.tools.catalog import TOOL_CATALOG


def _minimal_payload(tool: ToolId) -> dict:
    """Tiny valid-enough payloads; permission/side-effect fail before deep validation."""
    if tool == ToolId.FEATURES_COMPUTE:
        return {
            "bars": [
                {
                    "open_time": "2020-01-01T00:00:00Z",
                    "open": "1",
                    "high": "1",
                    "low": "1",
                    "close": "1",
                }
            ]
        }
    if tool in {
        ToolId.KNOWLEDGE_RETRIEVE,
    }:
        return {"query": "x"}
    if tool in {ToolId.KNOWLEDGE_ASK}:
        return {"question": "x"}
    if tool == ToolId.LLM_NARRATE_FACTS:
        return {
            "facts": {
                "action": "WAIT",
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "strategy_code": "x",
                "strategy_version_no": 1,
                "setup_state": "no_setup",
                "hard_blockers": [],
                "risk_approved": False,
                "confidence_band": "low",
            }
        }
    if tool == ToolId.VISION_EXTRACT:
        return {"vlm_payload": {}}
    if tool == ToolId.VISION_CHECK_VERDICT:
        return {"attached": False}
    if tool == ToolId.JOURNAL_SUMMARIZE_METRICS:
        return {"cohort": "paper", "trades": []}
    if tool in {
        ToolId.JOURNAL_NARRATE_PERFORMANCE,
        ToolId.JOURNAL_NARRATE_CALIBRATION,
    }:
        base = {
            "cohort": "paper",
            "strategy_code": "*",
            "instrument_symbol": "*",
            "timeframe": "*",
            "session_bucket": "*",
            "sample_size": 0,
            "sample_status": "insufficient_sample",
            "metrics": {},
            "warnings": [],
        }
        if tool == ToolId.JOURNAL_NARRATE_CALIBRATION:
            base["band_field"] = "confidence_band"
            base["bands"] = {}
            base["drift_flags"] = []
        return {"snapshot": base}
    if tool == ToolId.EXPLAIN_GROUNDED:
        return {
            "facts": {
                "action": "WAIT",
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "strategy_code": "x",
                "strategy_version_no": 1,
                "setup_state": "no_setup",
                "hard_blockers": [],
                "risk_approved": False,
                "confidence_band": "low",
                "features": {},
                "citations": [],
            }
        }
    # Routing + other tools: empty or minimal; often need orchestrator state.
    return {}


@pytest.mark.parametrize("agent", list(AgentId))
@pytest.mark.parametrize("tool", list(ToolId))
def test_permission_matrix_fuzz(agent: AgentId, tool: ToolId) -> None:
    permitted = has_permission(agent, tool)
    spec = get_tool(tool)
    assert spec is not None
    assert tool in TOOL_CATALOG

    ctx = ToolContext(extras={"external_tools_enabled": False})
    if not permitted:
        with pytest.raises(ToolPermissionError) as exc:
            invoke_tool(
                agent=agent,
                tool=tool,
                payload=_minimal_payload(tool),
                context=ctx,
            )
        assert exc.value.code == "TOOL_PERMISSION_DENIED"
        return

    # Permitted but EXTERNAL and flag off → side-effect deny (still fail closed).
    if spec.side_effect == SideEffect.EXTERNAL:
        with pytest.raises(SideEffectDeniedError):
            invoke_tool(
                agent=agent,
                tool=tool,
                payload=_minimal_payload(tool),
                context=ctx,
            )
        return

    # Permitted non-EXTERNAL: may succeed or fail on missing context/validation —
    # but must NOT raise ToolPermissionError.
    try:
        invoke_tool(
            agent=agent,
            tool=tool,
            payload=_minimal_payload(tool),
            context=ctx,
        )
    except ToolPermissionError as exc:  # pragma: no cover - fuzz guard
        raise AssertionError(
            f"permitted pair denied: {agent.value} → {tool.value}"
        ) from exc
    except Exception:
        # Missing orchestrator state / schema / backend is OK for this fuzz.
        pass


def test_every_catalog_tool_has_exactly_one_owner() -> None:
    owners: dict[ToolId, list[AgentId]] = {tool: [] for tool in ToolId}
    from private_trading_agents.tools.permissions import AGENT_TOOL_ALLOWLIST

    for agent, tools in AGENT_TOOL_ALLOWLIST.items():
        for tool in tools:
            owners[tool].append(agent)
    for tool, agents in owners.items():
        assert len(agents) == 1, f"{tool} owners={agents}"
