"""Live / prefetched backends for EXTERNAL agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from private_trading_agents.tools.external_schemas import (
    KnowledgeAskOut,
    KnowledgeChunkOut,
    KnowledgeRetrieveOut,
)
from private_trading_knowledge.ask import AskResult


def _citations_from_ask(result: AskResult) -> list[KnowledgeChunkOut]:
    chunks: list[KnowledgeChunkOut] = []
    for row in result.citations:
        chunks.append(
            KnowledgeChunkOut(
                citation_id=str(row.get("chunk_id") or row.get("citation_id") or "cite"),
                excerpt=str(row.get("excerpt") or row.get("title") or ""),
                document_id=(
                    None if row.get("document_id") is None else str(row.get("document_id"))
                ),
                score=row.get("score"),
                authority_tier=row.get("authority_tier"),
            )
        )
    return chunks


@dataclass(slots=True)
class PrefetchedKnowledgeBackend:
    """Sync KnowledgeBackend backed by an already-fetched AskResult.

    Used so Ask AI can await the corpus once, then pass through invoke_tool
    for allowlist / EXTERNAL / policy-seal checks.
    """

    ask_result: AskResult
    retrieve_note: str = "prefetched_from_ask"

    def retrieve(self, query: str, *, top_k: int = 5) -> KnowledgeRetrieveOut:
        del query
        chunks = _citations_from_ask(self.ask_result)[:top_k]
        return KnowledgeRetrieveOut(
            sufficient_evidence=self.ask_result.sufficient_evidence,
            chunks=chunks,
            conflicts=list(self.ask_result.conflicts),
            note=self.retrieve_note,
        )

    def ask(
        self,
        question: str,
        *,
        strategy_tag: str | None = None,
        asset_class: str | None = None,
        timeframe_tag: str | None = None,
    ) -> KnowledgeAskOut:
        del question, strategy_tag, asset_class, timeframe_tag
        confidence = self.ask_result.confidence
        if confidence not in {"high", "medium", "low", "none"}:
            confidence = "none"
        return KnowledgeAskOut(
            answer=self.ask_result.answer,
            sufficient_evidence=self.ask_result.sufficient_evidence,
            confidence=confidence,  # type: ignore[arg-type]
            citations=_citations_from_ask(self.ask_result),
            conflicts=list(self.ask_result.conflicts),
            prompt_version=self.ask_result.prompt_version,
            treated_as_untrusted_data=True,
        )


@dataclass(slots=True)
class CallableLlmNarrateBackend:
    """Wraps a sync narrate(facts) -> str callable for llm.narrate_facts."""

    narrate_fn: Any

    def narrate(self, facts: dict[str, Any]) -> str:
        return str(self.narrate_fn(facts))
