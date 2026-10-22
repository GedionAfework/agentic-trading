"""Pydantic I/O for EXTERNAL agent tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeRetrieveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeChunkOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(min_length=1, max_length=128)
    excerpt: str = Field(default="", max_length=4000)
    document_id: str | None = Field(default=None, max_length=128)
    score: float | None = None
    authority_tier: int | None = None


class KnowledgeRetrieveOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sufficient_evidence: bool
    chunks: list[KnowledgeChunkOut] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    note: str = ""


class KnowledgeAskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    strategy_tag: str | None = Field(default=None, max_length=64)
    asset_class: str | None = Field(default=None, max_length=32)
    timeframe_tag: str | None = Field(default=None, max_length=16)


class KnowledgeAskOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    sufficient_evidence: bool
    confidence: Literal["high", "medium", "low", "none"] = "none"
    citations: list[KnowledgeChunkOut] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    prompt_version: str = "knowledge.ask.v1"
    # Untrusted text is always treated as data — never tool policy.
    treated_as_untrusted_data: Literal[True] = True


class VisionExtractIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Prefer backend extract; vlm_payload allows offline/normalization tests.
    image_ref: str | None = Field(default=None, max_length=512)
    vlm_payload: dict[str, Any] | None = None
    market_symbol: str | None = Field(default=None, max_length=32)
    market_timeframe: str | None = Field(default=None, max_length=12)


class VisionExtractOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readable: bool
    symbol: str | None = None
    timeframe: str | None = None
    needs_clarification: bool = True
    reason: str = ""
    verdict_status: str = "clarification_required"
    consistent: bool = False
    authorizes_trade: Literal[False] = False
    blocker: str | None = None


class LlmNarrateFactsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: dict[str, Any]
    # Optional draft from an injected backend; validated for invented numbers.
    draft: str | None = Field(default=None, max_length=8000)


class LlmNarrateFactsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str
    explanation_source: Literal["llm_grounded", "rejected"]
    invented_numbers: list[str] = Field(default_factory=list)
    treated_as_untrusted_data: Literal[True] = True
