from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from private_trading_ai_gateway import AIGateway
from private_trading_core.config import Settings
from private_trading_db.models.knowledge import (
    EMBEDDING_DIM,
    ChunkEmbedding,
    DocumentChunk,
    DocumentVersion,
    KnowledgeDocument,
    ResponseCitation,
    RetrievalEvent,
)


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    authority_tier: int
    content: str
    page: int | None
    heading_path: str | None
    score: float


@dataclass(slots=True)
class RetrievalResult:
    event_id: uuid.UUID
    chunks: list[RetrievedChunk]
    sufficient_evidence: bool
    conflicts: list[str]


async def retrieve(
    session: AsyncSession,
    *,
    query: str,
    settings: Settings,
    gateway: AIGateway,
    user_id: uuid.UUID | None = None,
    top_k: int = 5,
    min_score: float = 0.25,
    strategy_tag: str | None = None,
    asset_class: str | None = None,
    timeframe_tag: str | None = None,
) -> RetrievalResult:
    query_vec = await gateway.embed(query, model=settings.embedding_model)
    if len(query_vec) != EMBEDDING_DIM:
        if len(query_vec) > EMBEDDING_DIM:
            query_vec = query_vec[:EMBEDDING_DIM]
        else:
            query_vec = query_vec + [0.0] * (EMBEDDING_DIM - len(query_vec))

    # Pass list[float]; SQLAlchemy VECTOR bind processor serializes for asyncpg.
    distance = ChunkEmbedding.vector.cosine_distance(query_vec)

    stmt: Select = (
        select(
            DocumentChunk,
            KnowledgeDocument,
            distance.label("distance"),
        )
        .join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .join(KnowledgeDocument, KnowledgeDocument.id == DocumentVersion.document_id)
        .where(KnowledgeDocument.status == "approved")
        .where(KnowledgeDocument.retired_at.is_(None))
        .order_by(distance)
        .limit(top_k)
    )
    if strategy_tag:
        stmt = stmt.where(KnowledgeDocument.strategy_tag == strategy_tag)
    if asset_class:
        stmt = stmt.where(KnowledgeDocument.asset_class == asset_class)
    if timeframe_tag:
        stmt = stmt.where(KnowledgeDocument.timeframe_tag == timeframe_tag)

    rows = (await session.execute(stmt)).all()
    chunks: list[RetrievedChunk] = []
    for chunk, doc, dist in rows:
        score = float(1.0 - float(dist))
        if score < min_score:
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=doc.id,
                document_title=doc.title,
                authority_tier=doc.authority_tier,
                content=chunk.content,
                page=chunk.page_start,
                heading_path=chunk.heading_path,
                score=score,
            )
        )

    # Prefer higher authority when scores are close
    chunks.sort(key=lambda c: (-c.authority_tier, -c.score))

    conflicts: list[str] = []
    # Tier-5 must not silently override Tier-1
    has_tier1 = any(c.authority_tier == 1 for c in chunks)
    if has_tier1:
        filtered = [c for c in chunks if c.authority_tier < 5 or c.score >= 0.85]
        if len(filtered) != len(chunks):
            conflicts.append("tier5_suppressed_by_tier1")
        chunks = filtered

    sufficient = len(chunks) > 0 and chunks[0].score >= min_score
    event = RetrievalEvent(
        user_id=user_id,
        query=query,
        filters={
            "strategy_tag": strategy_tag,
            "asset_class": asset_class,
            "timeframe_tag": timeframe_tag,
            "top_k": top_k,
            "min_score": min_score,
        },
        chunk_ids=[str(c.chunk_id) for c in chunks],
        scores=[c.score for c in chunks],
        sufficient_evidence=sufficient,
    )
    session.add(event)
    await session.flush()

    for rank, item in enumerate(chunks, start=1):
        session.add(
            ResponseCitation(
                retrieval_event_id=event.id,
                document_id=item.document_id,
                chunk_id=item.chunk_id,
                page=item.page,
                rank=rank,
                score=item.score,
            )
        )
    await session.commit()

    return RetrievalResult(
        event_id=event.id,
        chunks=chunks,
        sufficient_evidence=sufficient,
        conflicts=conflicts,
    )


async def get_approved_chunk(
    session: AsyncSession, chunk_id: uuid.UUID
) -> DocumentChunk | None:
    result = await session.execute(
        select(DocumentChunk)
        .options(selectinload(DocumentChunk.version))
        .where(DocumentChunk.id == chunk_id)
    )
    return result.scalar_one_or_none()
