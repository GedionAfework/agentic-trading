from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from private_trading_core.config import Settings, get_settings
from private_trading_core.errors import AppError, NotFoundError, UnauthorizedError
from private_trading_db.models.identity import TelegramAccount
from private_trading_db.models.telegram import (
    NotificationDelivery,
    TelegramAlertAction,
    TelegramUpdate,
)
from private_trading_db.services.audit import record_audit
from private_trading_notifications.delivery import dispatch, list_deliveries
from private_trading_notifications.link import (
    create_link_challenge,
    deep_link,
    revoke_account,
)
from private_trading_notifications.repository import process_update
from private_trading_notifications.telegram_client import build_client, webhook_authorized
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.telegram import (
    DeliveryOut,
    DispatchOut,
    LinkCodeOut,
    SetWebhookOut,
    SetWebhookRequest,
    TelegramAccountOut,
    TelegramStatusOut,
    WebhookAck,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _timeframes(settings: Settings) -> tuple[str, ...]:
    parsed = tuple(tf.strip() for tf in settings.market_default_timeframes.split(",") if tf.strip())
    return parsed or ("15m", "1h")


def _client(settings: Settings):
    return build_client(token=settings.telegram_bot_token, base_url=settings.telegram_api_base_url)


@router.post("/webhook", response_model=WebhookAck)
async def webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    secret_header: Annotated[
        str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")
    ] = None,
) -> WebhookAck:
    """Telegram → us. No bearer auth; the shared secret header is the only credential."""
    if not webhook_authorized(secret_header, settings.telegram_webhook_secret):
        raise UnauthorizedError("Invalid webhook secret")
    try:
        update: Any = await request.json()
    except ValueError as exc:
        raise AppError("INVALID_REQUEST", "Body must be a JSON update", retryable=False) from exc
    if not isinstance(update, dict):
        raise AppError("INVALID_REQUEST", "Body must be a JSON object", retryable=False)
    client = _client(settings)
    try:
        result = await process_update(
            session, update, settings=settings, client=client, timeframes=_timeframes(settings)
        )
    finally:
        await client.aclose()
    return WebhookAck(ok=result["ok"], duplicate=result["duplicate"], handled=result.get("handled"))


@router.post("/link", response_model=LinkCodeOut, status_code=status.HTTP_201_CREATED)
async def post_link(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LinkCodeOut:
    user.require_roles("owner", "admin")
    code, challenge = await create_link_challenge(
        session, user_id=user.id, ttl_seconds=settings.telegram_link_ttl_seconds
    )
    await record_audit(
        session,
        action="telegram.link_code_issued",
        actor_type="user",
        actor_id=user.id,
        resource_type="telegram_link_challenge",
        resource_id=challenge.id,
        correlation_id=get_correlation_id(request),
        metadata={"expires_at": challenge.expires_at.isoformat()},
    )
    await session.commit()
    return LinkCodeOut(
        code=code,
        deep_link=deep_link(settings.telegram_bot_username, code),
        expires_at=challenge.expires_at,
        bot_configured=bool(settings.telegram_bot_token),
    )


@router.get("/accounts", response_model=list[TelegramAccountOut])
async def get_accounts(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[TelegramAccountOut]:
    user.require_roles("owner", "admin", "viewer")
    result = await session.execute(
        select(TelegramAccount)
        .where(TelegramAccount.user_id == user.id)
        .order_by(TelegramAccount.linked_at.desc())
    )
    return [
        TelegramAccountOut(
            id=a.id,
            telegram_user_id=a.telegram_user_id,
            telegram_chat_id=a.telegram_chat_id,
            username=a.username,
            linked_at=a.linked_at,
            revoked_at=a.revoked_at,
        )
        for a in result.scalars().all()
    ]


@router.post("/accounts/{account_id}/revoke", response_model=TelegramAccountOut)
async def post_revoke(
    account_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TelegramAccountOut:
    user.require_roles("owner", "admin")
    account = await revoke_account(session, account_id=account_id, user_id=user.id)
    if account is None:
        raise NotFoundError("Telegram account not found")
    await record_audit(
        session,
        action="telegram.account_revoked",
        actor_type="user",
        actor_id=user.id,
        resource_type="telegram_account",
        resource_id=account.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return TelegramAccountOut(
        id=account.id,
        telegram_user_id=account.telegram_user_id,
        telegram_chat_id=account.telegram_chat_id,
        username=account.username,
        linked_at=account.linked_at,
        revoked_at=account.revoked_at,
    )


@router.post("/dispatch", response_model=DispatchOut)
async def post_dispatch(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DispatchOut:
    """Manual outbox → delivery → send pass (the Celery `notifications.dispatch` task does the
    same every 30s)."""
    user.require_roles("owner", "admin")
    client = _client(settings)
    try:
        result = await dispatch(session, client=client)
    finally:
        await client.aclose()
    await record_audit(
        session,
        action="telegram.dispatch_run",
        actor_type="user",
        actor_id=user.id,
        resource_type="notifications",
        correlation_id=get_correlation_id(request),
        metadata={"enqueue": result["enqueue"], "send": result["send"]},
    )
    await session.commit()
    return DispatchOut(**result)


@router.get("/deliveries", response_model=list[DeliveryOut])
async def get_deliveries(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DeliveryOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_deliveries(session, owner_user_id=user.id, limit=limit)
    return [
        DeliveryOut(
            id=d.id,
            candidate_id=d.candidate_id,
            decision_record_id=d.decision_record_id,
            telegram_chat_id=d.telegram_chat_id,
            template=d.template,
            status=d.status,
            transport=d.transport,
            attempt_count=d.attempt_count,
            next_attempt_at=d.next_attempt_at,
            telegram_message_id=d.telegram_message_id,
            last_error=d.last_error,
            created_at=d.created_at,
            sent_at=d.sent_at,
            message_text=d.message_text,
        )
        for d in rows
    ]


@router.get("/status", response_model=TelegramStatusOut)
async def get_status(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TelegramStatusOut:
    user.require_roles("owner", "admin", "viewer")
    linked = await session.execute(
        select(func.count())
        .select_from(TelegramAccount)
        .where(TelegramAccount.revoked_at.is_(None))
    )
    by_status = await session.execute(
        select(NotificationDelivery.status, func.count()).group_by(NotificationDelivery.status)
    )
    actions = await session.execute(select(func.count()).select_from(TelegramAlertAction))
    updates = await session.execute(select(func.count()).select_from(TelegramUpdate))
    return TelegramStatusOut(
        bot_configured=bool(settings.telegram_bot_token),
        webhook_secret_configured=bool(settings.telegram_webhook_secret),
        bot_username=settings.telegram_bot_username or None,
        linked_accounts=int(linked.scalar_one()),
        deliveries={str(k): int(v) for k, v in by_status.all()},
        alert_actions=int(actions.scalar_one()),
        updates_processed=int(updates.scalar_one()),
    )


@router.post("/webhook/register", response_model=SetWebhookOut)
async def post_register_webhook(
    body: SetWebhookRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SetWebhookOut:
    """Owner registers the public webhook URL with Telegram (requires token + secret)."""
    user.require_roles("owner", "admin")
    if not settings.telegram_webhook_secret:
        raise AppError(
            "TELEGRAM_NOT_CONFIGURED",
            "TELEGRAM_WEBHOOK_SECRET must be set before registering a webhook",
            retryable=False,
        )
    url = body.public_base_url.rstrip("/") + "/v1/telegram/webhook"
    client = _client(settings)
    try:
        result = await client.set_webhook(url=url, secret_token=settings.telegram_webhook_secret)
    finally:
        await client.aclose()
    await record_audit(
        session,
        action="telegram.webhook_registered",
        actor_type="user",
        actor_id=user.id,
        resource_type="telegram",
        correlation_id=get_correlation_id(request),
        metadata={"url": url, "ok": bool(result.get("ok"))},
    )
    await session.commit()
    return SetWebhookOut(ok=bool(result.get("ok")), url=url, result=result.get("result"))
