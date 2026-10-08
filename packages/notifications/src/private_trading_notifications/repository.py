"""Database-backed BotRepository plus the update-processing entrypoint shared by API/poller."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from private_trading_agents.scanner_service import (
    get_kill_switches,
    set_kill_switch,
)
from private_trading_agents.vision_service import analyze_screenshot
from private_trading_core.config import Settings
from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.scanner import SignalCandidate
from private_trading_db.models.strategy import Strategy, StrategyVersion
from private_trading_db.models.telegram import TelegramAlertAction, TelegramUpdate
from private_trading_db.services.audit import record_audit
from private_trading_db.services.auth import get_user_by_id
from private_trading_market_data.health import market_health
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_notifications.bot import BotReply, HandledUpdate, LinkedAccount, handle_update
from private_trading_notifications.delivery import candidate_to_dict, record_to_dict
from private_trading_notifications.link import consume_link_challenge, find_linked_account
from private_trading_notifications.telegram_client import TelegramTransport


class DbBotRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings,
        client: TelegramTransport,
        timeframes: tuple[str, ...],
    ) -> None:
        self.session = session
        self.settings = settings
        self.client = client
        self.timeframes = timeframes

    async def _account_from_row(self, row) -> LinkedAccount:
        user = await get_user_by_id(self.session, row.user_id)
        roles = sorted({r.role for r in user.roles}) if user else []
        return LinkedAccount(
            user_id=row.user_id,
            telegram_user_id=row.telegram_user_id,
            chat_id=row.telegram_chat_id,
            roles=roles,
            display_name=(user.display_name or user.email) if user else None,
        )

    async def find_account(self, telegram_user_id: int) -> LinkedAccount | None:
        row = await find_linked_account(self.session, telegram_user_id=telegram_user_id)
        if row is None:
            return None
        user = await get_user_by_id(self.session, row.user_id)
        if user is None or user.status != "active":
            return None
        return await self._account_from_row(row)

    async def consume_link(
        self, *, code: str, telegram_user_id: int, chat_id: int, username: str | None
    ) -> LinkedAccount | None:
        row = await consume_link_challenge(
            self.session,
            code=code,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=chat_id,
            username=username,
        )
        if row is None:
            return None
        await record_audit(
            self.session,
            action="telegram.linked",
            actor_type="user",
            actor_id=row.user_id,
            resource_type="telegram_account",
            resource_id=row.id,
            metadata={"telegram_user_id": telegram_user_id},
        )
        return await self._account_from_row(row)

    async def list_setups(self, *, user_id: uuid.UUID, limit: int) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(SignalCandidate)
            .where(SignalCandidate.owner_user_id == user_id)
            .order_by(SignalCandidate.last_seen_at.desc())
            .limit(limit)
        )
        return [candidate_to_dict(c) for c in result.scalars().all()]

    async def market_snapshots(self) -> list[dict[str, Any]]:
        snapshots = await market_health(self.session, timeframes=self.timeframes)
        return [asdict(s) for s in snapshots]

    async def list_strategies(self) -> list[dict[str, Any]]:
        rows = await self.session.execute(select(Strategy).order_by(Strategy.code))
        strategies = rows.scalars()
        out: list[dict[str, Any]] = []
        for strategy in strategies:
            published = await self.session.execute(
                select(StrategyVersion.version_no)
                .where(
                    StrategyVersion.strategy_id == strategy.id,
                    StrategyVersion.status == "published",
                )
                .order_by(StrategyVersion.version_no.desc())
                .limit(1)
            )
            out.append(
                {
                    "code": strategy.code,
                    "name": strategy.name,
                    "status": strategy.status,
                    "published_version_no": published.scalar_one_or_none(),
                }
            )
        return out

    async def kill_switches(self) -> dict[str, bool]:
        return await get_kill_switches(self.session)

    async def set_kill_switch(
        self, *, key: str, enabled: bool, actor_user_id: uuid.UUID
    ) -> dict[str, bool]:
        switches = await set_kill_switch(
            self.session, key=key, enabled=enabled, actor_user_id=actor_user_id
        )
        await record_audit(
            self.session,
            action="scanner.switches_updated",
            actor_type="user",
            actor_id=actor_user_id,
            resource_type="scanner",
            metadata={"via": "telegram", **switches},
        )
        return switches

    async def get_setup(
        self, *, candidate_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        candidate = await self.session.get(SignalCandidate, candidate_id)
        if candidate is None or candidate.owner_user_id != user_id:
            return None
        record = (
            await self.session.get(DecisionRecord, candidate.decision_record_id)
            if candidate.decision_record_id
            else None
        )
        return candidate_to_dict(candidate), record_to_dict(record)

    async def record_alert_action(
        self, *, candidate_id: uuid.UUID, user_id: uuid.UUID, chat_id: int, action: str
    ) -> bool:
        self.session.add(
            TelegramAlertAction(
                candidate_id=candidate_id,
                owner_user_id=user_id,
                telegram_chat_id=chat_id,
                action=action,
            )
        )
        await self.session.flush()
        return True

    async def ask(self, *, user_id: uuid.UUID, question: str) -> dict[str, Any]:
        from private_trading_ai_gateway import AIGateway
        from private_trading_knowledge.ask import ask_knowledge

        async with AIGateway(self.settings) as gateway:
            result = await ask_knowledge(
                self.session,
                question=question,
                user_id=user_id,
                settings=self.settings,
                gateway=gateway,
            )
        return {
            "answer": result.answer,
            "sufficient_evidence": result.sufficient_evidence,
            "confidence": result.confidence,
            "citations": result.citations,
            "conflicts": result.conflicts,
        }

    async def analyze_photo(
        self, *, user_id: uuid.UUID, file_id: str, caption: str | None
    ) -> dict[str, Any] | None:
        data = await self.client.download_file(file_id)
        if data is None:
            return None
        symbol = timeframe = None
        if caption:
            parts = caption.split()
            if parts:
                symbol = parts[0]
            if len(parts) > 1:
                timeframe = parts[1]
        job = await analyze_screenshot(
            self.session,
            owner_user_id=user_id,
            data=data,
            content_type="image/jpeg",
            market_symbol=symbol,
            market_timeframe=timeframe,
            vlm_payload=None,
        )
        return {
            "id": str(job.id),
            "status": job.status,
            "extraction": dict(job.extraction or {}),
            "verification": dict(job.verification or {}),
        }


async def _send_replies(client: TelegramTransport, replies: list[BotReply]) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    for reply in replies:
        if reply.callback_query_id:
            await client.answer_callback_query(
                callback_query_id=reply.callback_query_id, text=reply.callback_text
            )
        try:
            message = await client.send_message(
                chat_id=reply.chat_id, text=reply.text, reply_markup=reply.reply_markup
            )
            sent.append({"message_id": message.message_id, "transport": message.transport})
        except Exception as exc:  # noqa: BLE001 — record, do not fail the webhook
            sent.append({"error": f"{type(exc).__name__}: {exc}"[:300]})
    return sent


async def process_update(
    session: AsyncSession,
    update: dict[str, Any],
    *,
    settings: Settings,
    client: TelegramTransport,
    timeframes: tuple[str, ...],
) -> dict[str, Any]:
    """Idempotent on update_id: duplicates are acknowledged without re-handling."""
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return {"ok": False, "duplicate": False, "handled": "missing_update_id"}
    existing = await session.execute(
        select(TelegramUpdate.id).where(TelegramUpdate.update_id == update_id)
    )
    if existing.scalar_one_or_none() is not None:
        return {"ok": True, "duplicate": True, "handled": "duplicate_update"}

    repo = DbBotRepository(session, settings=settings, client=client, timeframes=timeframes)
    handled: HandledUpdate = await handle_update(update, repo)
    sent = await _send_replies(client, handled.replies)
    row = TelegramUpdate(
        update_id=update_id,
        telegram_user_id=handled.telegram_user_id,
        chat_id=handled.chat_id,
        kind=handled.kind,
        linked=handled.linked,
        handled=handled.handled,
        result={"replies": sent, **handled.meta},
        received_at=datetime.now(UTC),
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"ok": True, "duplicate": True, "handled": "duplicate_update"}
    return {
        "ok": True,
        "duplicate": False,
        "handled": handled.handled,
        "linked": handled.linked,
        "replies": sent,
    }
