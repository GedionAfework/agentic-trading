from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from private_trading_ai_gateway import AIGateway
from private_trading_core.config import Settings
from private_trading_core.errors import AppError
from private_trading_db.models.knowledge import (
    EMBEDDING_DIM,
    ChunkEmbedding,
    DocumentChunk,
    DocumentVersion,
    KnowledgeDocument,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from private_trading_knowledge.chunking import chunk_pages
from private_trading_knowledge.parsing import (
    ALLOWED_MIME,
    PARSER_VERSION,
    extract_text,
    validate_upload,
)
from private_trading_knowledge.storage import LocalObjectStorage


async def upload_document(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    filename: str,
    content_type: str | None,
    data: bytes,
    title: str | None = None,
    document_type: str = "guide",
    authority_tier: int = 2,
    asset_class: str | None = None,
    strategy_tag: str | None = None,
    timeframe_tag: str | None = None,
    settings: Settings,
    gateway: AIGateway,
    storage: LocalObjectStorage | None = None,
) -> KnowledgeDocument:
    if authority_tier < 1 or authority_tier > 5:
        raise AppError("INVALID_UPLOAD", "authority_tier must be 1..5", retryable=False)

    mime = validate_upload(filename, content_type, data)
    store = storage or LocalObjectStorage()
    suffix = ALLOWED_MIME[mime]
    object_key, sha256 = store.put_bytes(data, suffix=suffix)

    doc = KnowledgeDocument(
        owner_user_id=owner_user_id,
        title=title or Path(filename).stem,
        document_type=document_type,
        authority_tier=authority_tier,
        status="processing",
        asset_class=asset_class,
        strategy_tag=strategy_tag,
        timeframe_tag=timeframe_tag,
    )
    session.add(doc)
    await session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_no=1,
        object_key=object_key,
        sha256=sha256,
        mime_type=mime,
        size_bytes=len(data),
        parser_version=PARSER_VERSION,
    )
    session.add(version)
    await session.flush()
    doc.current_version_id = version.id

    try:
        pages = extract_text(mime, data)
        drafts = chunk_pages(pages)
        if not drafts:
            raise AppError("INGEST_FAILED", "No extractable text", retryable=False)

        for draft in drafts:
            chunk = DocumentChunk(
                document_version_id=version.id,
                ordinal=draft.ordinal,
                heading_path=draft.heading_path,
                page_start=draft.page_start,
                page_end=draft.page_end,
                content=draft.content,
                token_count=draft.token_count,
                content_hash=draft.content_hash,
            )
            session.add(chunk)
            await session.flush()

            vector = await gateway.embed(draft.content, model=settings.embedding_model)
            if len(vector) != EMBEDDING_DIM:
                # pad/truncate defensively for smoke models with unexpected dims
                if len(vector) > EMBEDDING_DIM:
                    vector = vector[:EMBEDDING_DIM]
                else:
                    vector = vector + [0.0] * (EMBEDDING_DIM - len(vector))
            session.add(
                ChunkEmbedding(
                    chunk_id=chunk.id,
                    embedding_model_name=settings.embedding_model,
                    vector=vector,
                )
            )

        version.ingested_at = datetime.now(UTC)
        doc.status = "draft"
    except AppError:
        doc.status = "failed"
        await session.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        doc.status = "failed"
        await session.commit()
        raise AppError("INGEST_FAILED", "Ingestion failed", retryable=False) from exc

    await session.commit()
    return await get_document(session, doc.id)


async def approve_document(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> KnowledgeDocument:
    doc = await get_document(session, document_id)
    if doc is None:
        raise AppError("NOT_FOUND", "Document not found", retryable=False)
    if doc.status not in {"draft", "approved"}:
        raise AppError("INVALID_STATE", f"Cannot approve from status={doc.status}", retryable=False)
    if doc.current_version_id is None:
        raise AppError("INVALID_STATE", "Document has no version", retryable=False)

    result = await session.execute(
        select(DocumentVersion).where(DocumentVersion.id == doc.current_version_id)
    )
    version = result.scalar_one()
    # ensure embeddings exist
    chunk_result = await session.execute(
        select(DocumentChunk)
        .options(selectinload(DocumentChunk.embedding))
        .where(DocumentChunk.document_version_id == version.id)
    )
    chunks = list(chunk_result.scalars().all())
    if not chunks or any(c.embedding is None for c in chunks):
        raise AppError("INVALID_STATE", "Embeddings incomplete", retryable=False)

    version.approved_at = datetime.now(UTC)
    doc.status = "approved"
    _ = actor_user_id
    await session.commit()
    return await get_document(session, document_id)  # type: ignore[return-value]


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> KnowledgeDocument | None:
    result = await session.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    )
    return result.scalar_one_or_none()


async def list_documents(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID | None = None,
) -> list[KnowledgeDocument]:
    stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    if owner_user_id is not None:
        stmt = stmt.where(KnowledgeDocument.owner_user_id == owner_user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
