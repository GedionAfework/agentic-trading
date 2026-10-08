from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LinkCodeOut(BaseModel):
    code: str
    deep_link: str | None
    expires_at: datetime
    bot_configured: bool


class TelegramAccountOut(BaseModel):
    id: uuid.UUID
    telegram_user_id: int
    telegram_chat_id: int
    username: str | None
    linked_at: datetime
    revoked_at: datetime | None


class DeliveryOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    decision_record_id: uuid.UUID | None
    telegram_chat_id: int
    template: str
    status: str
    transport: str | None
    attempt_count: int
    next_attempt_at: datetime
    telegram_message_id: int | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    message_text: str


class DispatchOut(BaseModel):
    enqueue: dict[str, int]
    send: dict[str, Any]
    bot_configured: bool


class WebhookAck(BaseModel):
    ok: bool
    duplicate: bool = False
    handled: str | None = None


class TelegramStatusOut(BaseModel):
    bot_configured: bool
    webhook_secret_configured: bool
    bot_username: str | None
    linked_accounts: int
    deliveries: dict[str, int]
    alert_actions: int
    updates_processed: int


class SetWebhookRequest(BaseModel):
    public_base_url: str = Field(min_length=8, max_length=300)


class SetWebhookOut(BaseModel):
    ok: bool
    url: str
    result: Any = None
