"""Outbox → NotificationDelivery → Telegram. Idempotent, retry-aware, kill-switch aware."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from private_trading_agents.scanner_service import get_kill_switches
from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.ops import OutboxEvent
from private_trading_db.models.scanner import SignalCandidate
from private_trading_db.models.telegram import NotificationDelivery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_notifications.link import list_linked_chats
from private_trading_notifications.telegram_client import (
    TelegramPermanentError,
    TelegramRateLimited,
    TelegramTransientError,
    TelegramTransport,
)
from private_trading_notifications.templates import alert_keyboard, alert_message

ALERT_TOPIC = "signal.candidate"
MAX_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = (5, 30, 120, 600)


@dataclass(slots=True)
class SendResult:
    """Outcome of one send attempt, decoupled from the transport for testability."""

    ok: bool
    message_id: int | None = None
    transport: str | None = None
    retry_after: int | None = None
    error: str | None = None
    permanent: bool = False


def backoff_seconds(attempt_count: int) -> int:
    index = min(max(attempt_count - 1, 0), len(RETRY_BACKOFF_SECONDS) - 1)
    return RETRY_BACKOFF_SECONDS[index]


def apply_send_result(delivery: NotificationDelivery, result: SendResult, *, now: datetime) -> str:
    """Mutates delivery status/attempts per policy and returns the new status."""
    delivery.attempt_count += 1
    if result.ok:
        delivery.status = "sent"
        delivery.transport = result.transport
        delivery.telegram_message_id = result.message_id
        delivery.sent_at = now
        delivery.last_error = None
        return delivery.status
    delivery.last_error = (result.error or "unknown")[:2000]
    if result.permanent or delivery.attempt_count >= MAX_ATTEMPTS:
        delivery.status = "failed"
        return delivery.status
    wait = result.retry_after if result.retry_after else backoff_seconds(delivery.attempt_count)
    delivery.status = "retry"
    delivery.next_attempt_at = now + timedelta(seconds=wait)
    return delivery.status


def candidate_to_dict(candidate: SignalCandidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "instrument_symbol": candidate.instrument_symbol,
        "timeframe": candidate.timeframe,
        "action": candidate.action,
        "strategy_code": candidate.strategy_code,
        "strategy_version_no": candidate.strategy_version_no,
        "publish_state": candidate.publish_state,
        "seen_count": candidate.seen_count,
        "candle_open_time": candidate.candle_open_time,
        "payload": dict(candidate.payload or {}),
    }


def record_to_dict(record: DecisionRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "id": str(record.id),
        "explanation": record.explanation,
        "explanation_source": record.explanation_source,
        "risk_approved": record.risk_approved,
        "hard_blockers": list(record.hard_blockers or []),
        "workflow": list(record.workflow or []),
        "confidence_band": record.confidence_band,
        "setup_state": record.setup_state,
    }


async def enqueue_from_outbox(session: AsyncSession, *, limit: int = 100) -> dict[str, int]:
    """Turn unpublished `signal.candidate` events into per-chat deliveries. Idempotent."""
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.topic == ALERT_TOPIC, OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    events = list(result.scalars().all())
    now = datetime.now(UTC)
    created = 0
    skipped_existing = 0
    no_chat = 0
    for event in events:
        candidate = await session.get(SignalCandidate, event.aggregate_id)
        event.attempt_count += 1
        if candidate is None:
            event.last_error = "candidate_missing"
            event.published_at = now
            continue
        record = (
            await session.get(DecisionRecord, candidate.decision_record_id)
            if candidate.decision_record_id
            else None
        )
        chats = await list_linked_chats(session, user_id=candidate.owner_user_id)
        if not chats:
            no_chat += 1
            event.last_error = "no_linked_chat"
        text = alert_message(candidate_to_dict(candidate), record_to_dict(record))
        markup = alert_keyboard(candidate.id)
        for account in chats:
            existing = await session.execute(
                select(NotificationDelivery.id).where(
                    NotificationDelivery.candidate_id == candidate.id,
                    NotificationDelivery.telegram_chat_id == account.telegram_chat_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped_existing += 1
                continue
            session.add(
                NotificationDelivery(
                    outbox_event_id=event.id,
                    candidate_id=candidate.id,
                    decision_record_id=candidate.decision_record_id,
                    owner_user_id=candidate.owner_user_id,
                    telegram_chat_id=account.telegram_chat_id,
                    template="setup_alert",
                    message_text=text,
                    reply_markup=markup,
                    status="pending",
                    next_attempt_at=now,
                )
            )
            created += 1
        event.published_at = now
    await session.flush()
    return {
        "events": len(events),
        "deliveries_created": created,
        "skipped_existing": skipped_existing,
        "events_without_chat": no_chat,
    }


async def _attempt(client: TelegramTransport, delivery: NotificationDelivery) -> SendResult:
    try:
        sent = await client.send_message(
            chat_id=delivery.telegram_chat_id,
            text=delivery.message_text,
            reply_markup=delivery.reply_markup,
        )
    except TelegramRateLimited as exc:
        return SendResult(ok=False, retry_after=exc.retry_after, error=f"429: {exc.message}")
    except TelegramTransientError as exc:
        return SendResult(ok=False, error=f"transient: {exc.message}")
    except TelegramPermanentError as exc:
        return SendResult(ok=False, permanent=True, error=f"permanent: {exc.message}")
    return SendResult(ok=True, message_id=sent.message_id, transport=sent.transport)


async def send_pending(
    session: AsyncSession,
    *,
    client: TelegramTransport,
    now: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    switches = await get_kill_switches(session)
    if not switches.get("notifications_enabled", True):
        return {"sent": 0, "retry": 0, "failed": 0, "skipped_kill_switch": True}
    from private_trading_release.policy import in_quiet_hours
    from private_trading_release.service import get_policy

    policy = await get_policy(session)
    if policy.live_alerts_enabled and in_quiet_hours(
        current,
        start=policy.quiet_hours_utc_start,
        end=policy.quiet_hours_utc_end,
    ):
        return {
            "sent": 0,
            "retry": 0,
            "failed": 0,
            "skipped_kill_switch": False,
            "skipped_quiet_hours": True,
        }
    result = await session.execute(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.status.in_(("pending", "retry")),
            NotificationDelivery.next_attempt_at <= current,
        )
        .order_by(NotificationDelivery.created_at)
        .limit(limit)
    )
    counts = {"sent": 0, "retry": 0, "failed": 0, "skipped_kill_switch": False}
    rate_limited_until: datetime | None = None
    for delivery in result.scalars().all():
        if rate_limited_until is not None and current < rate_limited_until:
            # Respect the 429 window for the rest of this batch without burning attempts.
            delivery.next_attempt_at = rate_limited_until
            if delivery.status == "pending":
                delivery.status = "retry"
            counts["retry"] += 1
            continue
        outcome = await _attempt(client, delivery)
        status = apply_send_result(delivery, outcome, now=current)
        counts[status] += 1
        if outcome.retry_after:
            rate_limited_until = current + timedelta(seconds=outcome.retry_after)
    await session.flush()
    return counts


async def dispatch(session: AsyncSession, *, client: TelegramTransport) -> dict[str, Any]:
    enqueued = await enqueue_from_outbox(session)
    sent = await send_pending(session, client=client)
    await session.commit()
    return {"enqueue": enqueued, "send": sent, "bot_configured": client.configured}


async def list_deliveries(
    session: AsyncSession, *, owner_user_id: uuid.UUID, limit: int = 50
) -> list[NotificationDelivery]:
    result = await session.execute(
        select(NotificationDelivery)
        .where(NotificationDelivery.owner_user_id == owner_user_id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
