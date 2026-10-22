"""EXTERNAL tool handlers — backends injected via ToolContext (fail closed)."""

from __future__ import annotations

from typing import Any, Protocol

from private_trading_core.errors import AppError

from private_trading_agents.explain import explanation_invents_numbers, grounded_explanation
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.external_schemas import (
    KnowledgeAskIn,
    KnowledgeAskOut,
    KnowledgeRetrieveIn,
    KnowledgeRetrieveOut,
    LlmNarrateFactsIn,
    LlmNarrateFactsOut,
    VisionExtractIn,
    VisionExtractOut,
)
from private_trading_agents.vision import parse_vlm_payload, verify_read


class ExternalBackendMissing(AppError):
    def __init__(self, tool: str, backend_key: str) -> None:
        super().__init__(
            "EXTERNAL_BACKEND_MISSING",
            f"Tool {tool} requires context.extras[{backend_key!r}]",
            retryable=False,
            details={"tool": tool, "backend_key": backend_key},
        )


class KnowledgeBackend(Protocol):
    def retrieve(self, query: str, *, top_k: int = 5) -> KnowledgeRetrieveOut: ...

    def ask(
        self,
        question: str,
        *,
        strategy_tag: str | None = None,
        asset_class: str | None = None,
        timeframe_tag: str | None = None,
    ) -> KnowledgeAskOut: ...


class VisionBackend(Protocol):
    def extract(
        self,
        *,
        image_ref: str | None = None,
        vlm_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class LlmNarrateBackend(Protocol):
    def narrate(self, facts: dict[str, Any]) -> str: ...


def _backend(context: ToolContext | None, key: str, tool: str) -> Any:
    if context is None or key not in context.extras or context.extras[key] is None:
        raise ExternalBackendMissing(tool, key)
    return context.extras[key]


def handle_knowledge_retrieve(
    payload: KnowledgeRetrieveIn,
    *,
    context: ToolContext | None = None,
) -> KnowledgeRetrieveOut:
    backend: KnowledgeBackend = _backend(context, "knowledge_backend", "knowledge.retrieve")
    result = backend.retrieve(payload.query, top_k=payload.top_k)
    if isinstance(result, KnowledgeRetrieveOut):
        return result
    return KnowledgeRetrieveOut.model_validate(result)


def handle_knowledge_ask(
    payload: KnowledgeAskIn,
    *,
    context: ToolContext | None = None,
) -> KnowledgeAskOut:
    backend: KnowledgeBackend = _backend(context, "knowledge_backend", "knowledge.ask")
    result = backend.ask(
        payload.question,
        strategy_tag=payload.strategy_tag,
        asset_class=payload.asset_class,
        timeframe_tag=payload.timeframe_tag,
    )
    if isinstance(result, KnowledgeAskOut):
        return result
    return KnowledgeAskOut.model_validate(result)


def handle_vision_extract(
    payload: VisionExtractIn,
    *,
    context: ToolContext | None = None,
) -> VisionExtractOut:
    vlm_payload = payload.vlm_payload
    if context is not None and context.extras.get("vision_backend") is not None:
        backend: VisionBackend = context.extras["vision_backend"]
        vlm_payload = backend.extract(
            image_ref=payload.image_ref,
            vlm_payload=payload.vlm_payload,
        )
    elif vlm_payload is None and payload.image_ref is not None:
        raise ExternalBackendMissing("vision.extract", "vision_backend")

    read = parse_vlm_payload(vlm_payload)
    verdict = verify_read(
        read,
        market_symbol=payload.market_symbol,
        market_timeframe=payload.market_timeframe,
    )
    return VisionExtractOut(
        readable=read.readable,
        symbol=read.symbol,
        timeframe=read.timeframe,
        needs_clarification=verdict.needs_clarification,
        reason=read.reason,
        verdict_status=verdict.status,
        consistent=verdict.consistent,
        authorizes_trade=False,
        blocker=verdict.blocker,
    )


def handle_llm_narrate_facts(
    payload: LlmNarrateFactsIn,
    *,
    context: ToolContext | None = None,
) -> LlmNarrateFactsOut:
    draft = payload.draft
    if draft is None and context is not None and context.extras.get("llm_backend") is not None:
        backend: LlmNarrateBackend = context.extras["llm_backend"]
        draft = backend.narrate(payload.facts)
    if draft is None:
        # Fail closed: do not silently substitute deterministic explain here.
        # Callers wanting deterministic text must use explain.grounded.
        raise ExternalBackendMissing("llm.narrate_facts", "llm_backend")

    invented = explanation_invents_numbers(draft, payload.facts)
    if invented:
        # Reject invented numbers; return grounded fallback only as rejected marker.
        safe = grounded_explanation(payload.facts)
        return LlmNarrateFactsOut(
            explanation=safe,
            explanation_source="rejected",
            invented_numbers=invented,
        )
    return LlmNarrateFactsOut(
        explanation=draft,
        explanation_source="llm_grounded",
        invented_numbers=[],
    )
