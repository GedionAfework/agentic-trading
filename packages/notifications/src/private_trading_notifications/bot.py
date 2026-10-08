"""Telegram update handler.

Pure routing logic over a `BotRepository` protocol so it can be unit-tested without a
database. Unlinked chats only ever see the link prompt — never strategy, market or
decision content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from private_trading_notifications import templates

MAX_FREE_TEXT = 2000
ADMIN_ROLES = ("owner", "admin")


@dataclass(slots=True)
class LinkedAccount:
    user_id: uuid.UUID
    telegram_user_id: int
    chat_id: int
    roles: list[str]
    display_name: str | None = None

    @property
    def can_edit_settings(self) -> bool:
        return any(role in self.roles for role in ADMIN_ROLES)


@dataclass(slots=True)
class BotReply:
    chat_id: int
    text: str
    reply_markup: dict[str, Any] | None = None
    callback_query_id: str | None = None
    callback_text: str | None = None


@dataclass(slots=True)
class HandledUpdate:
    kind: str
    handled: str
    linked: bool
    telegram_user_id: int | None
    chat_id: int | None
    replies: list[BotReply] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class BotRepository(Protocol):
    async def find_account(self, telegram_user_id: int) -> LinkedAccount | None: ...

    async def consume_link(
        self, *, code: str, telegram_user_id: int, chat_id: int, username: str | None
    ) -> LinkedAccount | None: ...

    async def list_setups(self, *, user_id: uuid.UUID, limit: int) -> list[dict[str, Any]]: ...

    async def market_snapshots(self) -> list[dict[str, Any]]: ...

    async def list_strategies(self) -> list[dict[str, Any]]: ...

    async def kill_switches(self) -> dict[str, bool]: ...

    async def set_kill_switch(
        self, *, key: str, enabled: bool, actor_user_id: uuid.UUID
    ) -> dict[str, bool]: ...

    async def get_setup(
        self, *, candidate_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None: ...

    async def record_alert_action(
        self, *, candidate_id: uuid.UUID, user_id: uuid.UUID, chat_id: int, action: str
    ) -> bool: ...

    async def ask(self, *, user_id: uuid.UUID, question: str) -> dict[str, Any]: ...

    async def analyze_photo(
        self, *, user_id: uuid.UUID, file_id: str, caption: str | None
    ) -> dict[str, Any] | None: ...


def _parse_command(text: str) -> tuple[str, list[str]] | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split()
    command = parts[0].lower().split("@", 1)[0]
    return command, parts[1:]


def _parse_uuid(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError):
        return None


async def handle_update(update: dict[str, Any], repo: BotRepository) -> HandledUpdate:
    if "callback_query" in update:
        return await _handle_callback(update["callback_query"], repo)
    message = update.get("message") or update.get("edited_message")
    if not message:
        return HandledUpdate(
            kind="ignored", handled="unsupported_update", linked=False,
            telegram_user_id=None, chat_id=None,
        )
    return await _handle_message(message, repo)


async def _handle_message(message: dict[str, Any], repo: BotRepository) -> HandledUpdate:
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    telegram_user_id = sender.get("id")
    chat_id = chat.get("id")
    if telegram_user_id is None or chat_id is None:
        return HandledUpdate(
            kind="message", handled="missing_ids", linked=False,
            telegram_user_id=None, chat_id=None,
        )
    if chat.get("type") not in (None, "private"):
        # Group chats never receive private content, linked or not.
        return HandledUpdate(
            kind="message", handled="non_private_chat_ignored", linked=False,
            telegram_user_id=telegram_user_id, chat_id=chat_id,
        )

    text = message.get("text") or ""
    command = _parse_command(text) if text else None
    account = await repo.find_account(int(telegram_user_id))

    if account is None:
        return await _handle_unlinked(
            command, telegram_user_id=int(telegram_user_id), chat_id=int(chat_id),
            username=sender.get("username"), repo=repo,
        )

    base = HandledUpdate(
        kind="message", handled="", linked=True,
        telegram_user_id=int(telegram_user_id), chat_id=int(chat_id),
    )
    if message.get("photo"):
        return await _handle_photo(message, account, base, repo)
    if command is not None:
        return await _handle_command(command, account, base, repo)
    if text.strip():
        return await _handle_free_text(text.strip()[:MAX_FREE_TEXT], account, base, repo)
    base.handled = "empty_message"
    base.replies.append(BotReply(chat_id=account.chat_id, text=templates.help_text(linked=True)))
    return base


async def _handle_unlinked(
    command: tuple[str, list[str]] | None,
    *,
    telegram_user_id: int,
    chat_id: int,
    username: str | None,
    repo: BotRepository,
) -> HandledUpdate:
    result = HandledUpdate(
        kind="message", handled="unlinked_prompt", linked=False,
        telegram_user_id=telegram_user_id, chat_id=chat_id,
    )
    if command is not None and command[0] in ("/start", "/link") and command[1]:
        account = await repo.consume_link(
            code=command[1][0], telegram_user_id=telegram_user_id,
            chat_id=chat_id, username=username,
        )
        if account is not None:
            result.handled = "linked"
            result.linked = True
            result.replies.append(
                BotReply(chat_id=chat_id, text=templates.link_success(account.display_name))
            )
            return result
        result.handled = "link_failed"
        result.replies.append(BotReply(chat_id=chat_id, text=templates.LINK_FAILED_TEXT))
        return result
    result.replies.append(BotReply(chat_id=chat_id, text=templates.UNLINKED_TEXT))
    return result


async def _handle_command(
    command: tuple[str, list[str]],
    account: LinkedAccount,
    result: HandledUpdate,
    repo: BotRepository,
) -> HandledUpdate:
    name, args = command
    chat_id = account.chat_id
    if name in ("/start", "/help", "/link"):
        result.handled = "help"
        result.replies.append(BotReply(chat_id=chat_id, text=templates.help_text(linked=True)))
    elif name == "/setups":
        limit = 10
        if args and args[0].isdigit():
            limit = max(1, min(int(args[0]), 25))
        items = await repo.list_setups(user_id=account.user_id, limit=limit)
        result.handled = "setups"
        result.replies.append(BotReply(chat_id=chat_id, text=templates.setups_list(items)))
    elif name == "/markets":
        result.handled = "markets"
        result.replies.append(
            BotReply(chat_id=chat_id, text=templates.markets_list(await repo.market_snapshots()))
        )
    elif name == "/strategies":
        result.handled = "strategies"
        result.replies.append(
            BotReply(chat_id=chat_id, text=templates.strategies_list(await repo.list_strategies()))
        )
    elif name in ("/journal", "/performance"):
        result.handled = f"{name[1:]}_not_available"
        result.replies.append(BotReply(chat_id=chat_id, text=templates.NOT_AVAILABLE[name[1:]]))
    elif name == "/settings":
        await _handle_settings(args, account, result, repo)
    else:
        result.handled = "unknown_command"
        result.replies.append(
            BotReply(
                chat_id=chat_id,
                text="Unknown command.\n\n" + templates.help_text(linked=True),
            )
        )
    return result


async def _handle_settings(
    args: list[str], account: LinkedAccount, result: HandledUpdate, repo: BotRepository
) -> None:
    chat_id = account.chat_id
    switch_map = {"scanner": "scanner_enabled", "notifications": "notifications_enabled"}
    if len(args) >= 2 and args[0].lower() in switch_map and args[1].lower() in ("on", "off"):
        if not account.can_edit_settings:
            result.handled = "settings_forbidden"
            result.replies.append(
                BotReply(chat_id=chat_id, text="Only the owner/admin can change kill switches.")
            )
            return
        switches = await repo.set_kill_switch(
            key=switch_map[args[0].lower()],
            enabled=args[1].lower() == "on",
            actor_user_id=account.user_id,
        )
        result.handled = "settings_updated"
        result.meta["switches"] = switches
    else:
        switches = await repo.kill_switches()
        result.handled = "settings_view"
    result.replies.append(
        BotReply(
            chat_id=chat_id,
            text=templates.settings_view(switches, can_edit=account.can_edit_settings),
        )
    )


async def _handle_free_text(
    text: str, account: LinkedAccount, result: HandledUpdate, repo: BotRepository
) -> HandledUpdate:
    result.handled = "ask"
    try:
        answer = await repo.ask(user_id=account.user_id, question=text)
    except Exception as exc:  # noqa: BLE001 — degraded AI is a reply, not a crash
        result.handled = "ask_unavailable"
        result.meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
        result.replies.append(
            BotReply(
                chat_id=account.chat_id,
                text="The knowledge assistant is unavailable right now. Try again later.",
            )
        )
        return result
    result.replies.append(BotReply(chat_id=account.chat_id, text=templates.ask_answer(answer)))
    return result


async def _handle_photo(
    message: dict[str, Any], account: LinkedAccount, result: HandledUpdate, repo: BotRepository
) -> HandledUpdate:
    photos = message.get("photo") or []
    largest = max(photos, key=lambda p: int(p.get("file_size") or 0)) if photos else None
    file_id = (largest or {}).get("file_id")
    result.handled = "vision"
    if not file_id:
        result.handled = "vision_no_file"
        result.replies.append(BotReply(chat_id=account.chat_id, text="Could not read that image."))
        return result
    try:
        job = await repo.analyze_photo(
            user_id=account.user_id, file_id=file_id, caption=message.get("caption")
        )
    except Exception as exc:  # noqa: BLE001
        result.handled = "vision_failed"
        result.meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
        result.replies.append(
            BotReply(chat_id=account.chat_id, text="Screenshot analysis failed. Try the web app.")
        )
        return result
    if job is None:
        result.handled = "vision_unavailable"
        result.replies.append(
            BotReply(
                chat_id=account.chat_id,
                text="Screenshot download is unavailable (bot token not configured).",
            )
        )
        return result
    result.replies.append(BotReply(chat_id=account.chat_id, text=templates.vision_result(job)))
    return result


async def _handle_callback(callback: dict[str, Any], repo: BotRepository) -> HandledUpdate:
    sender = callback.get("from") or {}
    chat = ((callback.get("message") or {}).get("chat")) or {}
    callback_id = str(callback.get("id") or "")
    telegram_user_id = sender.get("id")
    chat_id = chat.get("id")
    result = HandledUpdate(
        kind="callback", handled="", linked=False,
        telegram_user_id=telegram_user_id, chat_id=chat_id,
    )
    if telegram_user_id is None or chat_id is None:
        result.handled = "missing_ids"
        return result
    account = await repo.find_account(int(telegram_user_id))
    if account is None:
        result.handled = "unlinked_callback"
        result.replies.append(
            BotReply(
                chat_id=int(chat_id), text=templates.UNLINKED_TEXT,
                callback_query_id=callback_id, callback_text="Not linked",
            )
        )
        return result
    result.linked = True
    data = str(callback.get("data") or "")
    parts = data.split(":")
    action = parts[0] if parts else ""
    candidate_id = _parse_uuid(parts[1]) if len(parts) > 1 else None
    if action not in ("view", "why", "dismiss", "record") or candidate_id is None:
        result.handled = "unknown_callback"
        result.replies.append(
            BotReply(
                chat_id=account.chat_id, text="That button is no longer valid.",
                callback_query_id=callback_id, callback_text="Invalid",
            )
        )
        return result
    setup = await repo.get_setup(candidate_id=candidate_id, user_id=account.user_id)
    if setup is None:
        result.handled = "callback_not_found"
        result.replies.append(
            BotReply(
                chat_id=account.chat_id, text="Setup not found.",
                callback_query_id=callback_id, callback_text="Not found",
            )
        )
        return result
    candidate, record = setup
    if action == "view":
        await repo.record_alert_action(
            candidate_id=candidate_id, user_id=account.user_id, chat_id=account.chat_id,
            action="viewed",
        )
        result.handled = "view"
        result.replies.append(
            BotReply(
                chat_id=account.chat_id, text=templates.alert_message(candidate, record),
                reply_markup=templates.alert_keyboard(candidate_id),
                callback_query_id=callback_id, callback_text=None,
            )
        )
    elif action == "why":
        await repo.record_alert_action(
            candidate_id=candidate_id, user_id=account.user_id, chat_id=account.chat_id,
            action="why",
        )
        result.handled = "why"
        result.replies.append(
            BotReply(
                chat_id=account.chat_id, text=templates.why_message(record),
                callback_query_id=callback_id, callback_text=None,
            )
        )
    elif action == "dismiss":
        await repo.record_alert_action(
            candidate_id=candidate_id, user_id=account.user_id, chat_id=account.chat_id,
            action="dismissed",
        )
        result.handled = "dismissed"
        result.replies.append(
            BotReply(
                chat_id=account.chat_id,
                text="Dismissed. The scanner will not re-alert this setup.",
                callback_query_id=callback_id, callback_text="Dismissed",
            )
        )
    else:  # record
        choice = parts[2] if len(parts) > 2 else None
        if choice in ("taken", "skipped"):
            await repo.record_alert_action(
                candidate_id=candidate_id, user_id=account.user_id, chat_id=account.chat_id,
                action=f"decision_{choice}",
            )
            result.handled = f"recorded_{choice}"
            result.replies.append(
                BotReply(
                    chat_id=account.chat_id,
                    text=f"Recorded: you {choice} this setup (PAPER context). "
                    "It will appear in the journal once Phase 16/17 land.",
                    callback_query_id=callback_id, callback_text="Recorded",
                )
            )
        else:
            result.handled = "record_prompt"
            result.replies.append(
                BotReply(
                    chat_id=account.chat_id, text="What did you do with this setup?",
                    reply_markup=templates.record_decision_keyboard(candidate_id),
                    callback_query_id=callback_id, callback_text=None,
                )
            )
    return result
