from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from private_trading_ai_gateway import AIGateway
from private_trading_core.config import Settings, get_settings
from private_trading_db.services.audit import record_audit
from private_trading_knowledge.ask import ask_knowledge
from private_trading_knowledge.ingest import approve_document, list_documents, upload_document
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.routes.ai import get_ai_gateway
from private_trading_api.schemas.knowledge import (
    AskRequest,
    AskResponse,
    CitationOut,
    DocumentOut,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _doc_out(doc) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        document_type=doc.document_type,
        authority_tier=doc.authority_tier,
        status=doc.status,
        current_version_id=doc.current_version_id,
        asset_class=doc.asset_class,
        strategy_tag=doc.strategy_tag,
        timeframe_tag=doc.timeframe_tag,
        created_at=doc.created_at,
    )


@router.get("/documents", response_model=list[DocumentOut])
async def get_documents(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DocumentOut]:
    user.require_roles("owner", "admin")
    docs = await list_documents(session, owner_user_id=user.id)
    return [_doc_out(d) for d in docs]


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def post_document(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    document_type: Annotated[str, Form()] = "guide",
    authority_tier: Annotated[int, Form()] = 2,
    asset_class: Annotated[str | None, Form()] = None,
    strategy_tag: Annotated[str | None, Form()] = None,
    timeframe_tag: Annotated[str | None, Form()] = None,
) -> DocumentOut:
    user.require_roles("owner", "admin")
    data = await file.read()
    doc = await upload_document(
        session,
        owner_user_id=user.id,
        filename=file.filename or "upload.bin",
        content_type=file.content_type,
        data=data,
        title=title,
        document_type=document_type,
        authority_tier=authority_tier,
        asset_class=asset_class,
        strategy_tag=strategy_tag,
        timeframe_tag=timeframe_tag,
        settings=settings,
        gateway=gateway,
    )
    await record_audit(
        session,
        action="knowledge.document_uploaded",
        actor_type="user",
        actor_id=user.id,
        resource_type="knowledge_document",
        resource_id=doc.id,
        correlation_id=get_correlation_id(request),
        metadata={"status": doc.status, "authority_tier": doc.authority_tier},
    )
    await session.commit()
    return _doc_out(doc)


@router.post("/documents/{document_id}/approve", response_model=DocumentOut)
async def post_approve(
    document_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    user.require_roles("owner", "admin")
    doc = await approve_document(
        session, document_id=document_id, actor_user_id=user.id
    )
    await record_audit(
        session,
        action="knowledge.document_approved",
        actor_type="user",
        actor_id=user.id,
        resource_type="knowledge_document",
        resource_id=doc.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return _doc_out(doc)


@router.post("/ask", response_model=AskResponse)
async def post_ask(
    body: AskRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
) -> AskResponse:
    user.require_roles("owner", "admin")
    result = await ask_knowledge(
        session,
        question=body.question,
        user_id=user.id,
        settings=settings,
        gateway=gateway,
        strategy_tag=body.strategy_tag,
        asset_class=body.asset_class,
        timeframe_tag=body.timeframe_tag,
    )
    await record_audit(
        session,
        action="knowledge.ask",
        actor_type="user",
        actor_id=user.id,
        resource_type="retrieval_event",
        resource_id=result.retrieval_event_id,
        correlation_id=get_correlation_id(request),
        metadata={
            "sufficient_evidence": result.sufficient_evidence,
            "citation_count": len(result.citations),
        },
    )
    await session.commit()
    return AskResponse(
        answer=result.answer,
        sufficient_evidence=result.sufficient_evidence,
        confidence=result.confidence,
        citations=[CitationOut(**c) for c in result.citations],
        retrieval_event_id=result.retrieval_event_id,
        conflicts=result.conflicts,
        model=result.model,
        prompt_version=result.prompt_version,
    )
