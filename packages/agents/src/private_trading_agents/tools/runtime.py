"""Gated tool invocation — deny by default, least privilege."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from private_trading_agents.contracts import AgentId
from private_trading_agents.tools.catalog import TOOL_CATALOG, get_tool
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.errors import (
    SideEffectDeniedError,
    ToolPermissionError,
    UnknownToolError,
)
from private_trading_agents.tools.external_gate import external_tools_enabled
from private_trading_agents.tools.ids import SideEffect, ToolId
from private_trading_agents.tools.permissions import (
    allowed_side_effects,
    has_permission,
)


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    agent: AgentId
    tool: ToolId
    side_effect: SideEffect
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]


def invoke_tool(
    *,
    agent: AgentId,
    tool: ToolId | str,
    payload: BaseModel | dict[str, Any],
    context: ToolContext | None = None,
) -> BaseModel:
    """Invoke a tool under the calling agent's least-privilege allowlist.

    Order of checks (fail closed):
    1. Tool must be registered.
    2. Agent must be explicitly permitted for that tool.
    3. Side-effect must be allowed (NONE/READ; EXTERNAL only if enabled).
    4. Input must validate against the tool schema.
    5. Handler runs; output must validate against the tool schema.
    """
    spec = get_tool(tool)
    if spec is None:
        raise UnknownToolError(str(tool))

    if not has_permission(agent, spec.tool_id):
        raise ToolPermissionError(agent=agent.value, tool=spec.tool_id.value)

    permitted_effects = allowed_side_effects(
        external_enabled=external_tools_enabled(context)
    )
    if spec.side_effect.value not in permitted_effects:
        raise SideEffectDeniedError(
            tool=spec.tool_id.value,
            side_effect=spec.side_effect.value,
        )

    raw = payload.model_dump() if isinstance(payload, BaseModel) else payload
    try:
        validated_in = spec.input_model.model_validate(raw)
    except ValidationError:
        raise

    if spec.accepts_context:
        result = spec.handler(validated_in, context=context)
    else:
        result = spec.handler(validated_in)

    return spec.output_model.model_validate(
        result.model_dump() if isinstance(result, BaseModel) else result
    )


def assert_tool_registered(tool: ToolId | str) -> ToolId:
    spec = get_tool(tool)
    if spec is None:
        raise UnknownToolError(str(tool))
    return spec.tool_id


def registered_tool_ids() -> frozenset[ToolId]:
    return frozenset(TOOL_CATALOG.keys())
