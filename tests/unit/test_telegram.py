from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from private_trading_db.models.telegram import NotificationDelivery
from private_trading_notifications.bot import LinkedAccount, handle_update
from private_trading_notifications.delivery import (
    MAX_ATTEMPTS,
    SendResult,
    apply_send_result,
    backoff_seconds,
)
from private_trading_notifications.link import (
    challenge_is_valid,
    generate_link_code,
    hash_link_code,
)
from private_trading_notifications.telegram_client import webhook_authorized
from private_trading_notifications.templates import (
    UNLINKED_TEXT,
    alert_keyboard,
    alert_message,
)

OWNER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()
CANDIDATE_ID = uuid.uuid4()


def _candidate(owner: uuid.UUID = OWNER_ID) -> dict[str, Any]:
    return {
        "id": str(CANDIDATE_ID),
        "owner_user_id": owner,
        "instrument_symbol": "BTC/USDT",
        "timeframe": "1h",
        "action": "ENTER",
        "strategy_code": "wyckoff-hdm",
        "strategy_version_no": 1,
        "publish_state": "published",
        "seen_count": 1,
        "candle_open_time": datetime(2026, 10, 7, 12, 0, tzinfo=UTC),
        "payload": {
            "direction": "long",
            "setup_state": "ready_for_review",
            "confidence_band": "medium",
            "entry_price": "101.5",
            "stop_price": "99.25",
            "target_price": "106.0",
            "rr_ratio": "2.0",
            "hard_blockers": [],
        },
    }


def _record() -> dict[str, Any]:
    return {
        "explanation": "Bullish BOS confirmed; risk gate approved.",
        "explanation_source": "deterministic_template",
        "risk_approved": True,
        "hard_blockers": [],
        "workflow": [{"agent": "AG-02", "status": "ok"}],
    }


class FakeRepo:
    def __init__(self, *, linked: dict[int, LinkedAccount] | None = None) -> None:
        self.linked = linked or {}
        self.calls: list[str] = []
        self.actions: list[str] = []
        self.switches = {"scanner_enabled": True, "notifications_enabled": True}
        self.candidates: dict[uuid.UUID, dict[str, Any]] = {CANDIDATE_ID: _candidate()}

    async def find_account(self, telegram_user_id: int) -> LinkedAccount | None:
        return self.linked.get(telegram_user_id)

    async def consume_link(self, *, code, telegram_user_id, chat_id, username):
        self.calls.append("consume_link")
        if code != "GOODCODE":
            return None
        account = LinkedAccount(
            user_id=OWNER_ID, telegram_user_id=telegram_user_id, chat_id=chat_id,
            roles=["owner"], display_name="Owner",
        )
        self.linked[telegram_user_id] = account
        return account

    async def list_setups(self, *, user_id, limit):
        self.calls.append("list_setups")
        return [c for c in self.candidates.values() if c["owner_user_id"] == user_id]

    async def market_snapshots(self):
        self.calls.append("market_snapshots")
        return []

    async def list_strategies(self):
        self.calls.append("list_strategies")
        return [{"code": "wyckoff-hdm", "name": "Wyckoff HDM", "status": "active",
                 "published_version_no": 1}]

    async def kill_switches(self):
        return dict(self.switches)

    async def set_kill_switch(self, *, key, enabled, actor_user_id):
        self.calls.append("set_kill_switch")
        self.switches[key] = enabled
        return dict(self.switches)

    async def get_setup(self, *, candidate_id, user_id):
        candidate = self.candidates.get(candidate_id)
        if candidate is None or candidate["owner_user_id"] != user_id:
            return None
        return candidate, _record()

    async def record_alert_action(self, *, candidate_id, user_id, chat_id, action):
        self.actions.append(action)
        return True

    async def ask(self, *, user_id, question):
        self.calls.append("ask")
        return {"answer": "From the approved guide.", "sufficient_evidence": True,
                "confidence": "medium", "citations": [{"title": "Guide", "page": 3}],
                "conflicts": []}

    async def analyze_photo(self, *, user_id, file_id, caption):
        self.calls.append("analyze_photo")
        return None


def _message(text: str, *, user_id: int = 42, chat_id: int = 42, chat_type: str = "private"):
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "username": "ged"},
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
        },
    }


def _callback(data: str, *, user_id: int = 42, chat_id: int = 42):
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "from": {"id": user_id},
            "message": {"chat": {"id": chat_id, "type": "private"}},
            "data": data,
        },
    }


def _owner_account(user_id: int = 42, roles: list[str] | None = None) -> LinkedAccount:
    return LinkedAccount(
        user_id=OWNER_ID, telegram_user_id=user_id, chat_id=user_id,
        roles=roles or ["owner"], display_name="Owner",
    )


# --- webhook secret ---------------------------------------------------------------------


def test_webhook_fails_closed_without_configured_secret() -> None:
    assert webhook_authorized("anything", "") is False
    assert webhook_authorized(None, "") is False


def test_webhook_requires_exact_secret() -> None:
    assert webhook_authorized("s3cret", "s3cret") is True
    assert webhook_authorized("s3cret ", "s3cret") is False
    assert webhook_authorized(None, "s3cret") is False


# --- link challenge ---------------------------------------------------------------------


def test_link_code_hash_is_normalized_and_one_time() -> None:
    code = generate_link_code()
    assert len(code) == 8
    assert hash_link_code(code.lower()) == hash_link_code(f" {code} ")
    now = datetime.now(UTC)
    assert challenge_is_valid(expires_at=now + timedelta(minutes=5), consumed_at=None, now=now)
    assert not challenge_is_valid(expires_at=now - timedelta(seconds=1), consumed_at=None, now=now)
    assert not challenge_is_valid(expires_at=now + timedelta(minutes=5), consumed_at=now, now=now)


# --- templates --------------------------------------------------------------------------


def test_alert_numbers_match_stored_record_exactly() -> None:
    candidate = _candidate()
    text = alert_message(candidate, _record())
    for key in ("entry_price", "stop_price", "target_price", "rr_ratio"):
        assert candidate["payload"][key].rstrip("0").rstrip(".") in text or (
            candidate["payload"][key] in text
        )
    # Every decimal number in the body (excluding the candle timestamp line) comes from payload.
    body = "\n".join(line for line in text.splitlines() if not line.startswith("Candle:"))
    numbers = set(re.findall(r"(?<![\w/])\d+(?:\.\d+)?(?![\w/])", body))
    allowed = {"101.5", "99.25", "106", "2", "1"}  # prices, rr, strategy version
    assert numbers <= allowed, numbers
    assert "authorizes a trade" in text
    keyboard = alert_keyboard(CANDIDATE_ID)["inline_keyboard"]
    labels = [b["text"] for row in keyboard for b in row]
    assert labels == ["View", "Why?", "Dismiss", "Record decision"]


def test_alert_prices_match_stored_numeric_20_8_precision() -> None:
    candidate = _candidate()
    candidate["payload"]["stop_price"] = "116.6428571428571428571428571"
    candidate["payload"]["entry_price"] = "124.000000000"
    text = alert_message(candidate, None)
    assert "Stop: 116.64285714" in text
    assert "Entry: 124 " in text


def test_alert_shows_na_when_engine_has_no_price() -> None:
    candidate = _candidate()
    candidate["payload"].update({"entry_price": None, "stop_price": None,
                                 "target_price": None, "rr_ratio": None})
    text = alert_message(candidate, None)
    assert "Entry: n/a" in text and "R:R n/a" in text


# --- handler: unlinked chats ------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlinked_chat_never_sees_strategy_content() -> None:
    repo = FakeRepo()
    for command in ("/setups", "/strategies", "/markets", "/settings", "what is a spring?"):
        handled = await handle_update(_message(command), repo)
        assert handled.linked is False
        assert handled.handled == "unlinked_prompt"
        assert [r.text for r in handled.replies] == [UNLINKED_TEXT]
    assert repo.calls == []  # no repository data access at all


@pytest.mark.asyncio
async def test_unlinked_callback_is_refused() -> None:
    repo = FakeRepo()
    handled = await handle_update(_callback(f"why:{CANDIDATE_ID}"), repo)
    assert handled.handled == "unlinked_callback"
    assert repo.actions == []
    assert handled.replies[0].text == UNLINKED_TEXT


@pytest.mark.asyncio
async def test_start_with_valid_code_links_and_bad_code_does_not() -> None:
    repo = FakeRepo()
    bad = await handle_update(_message("/start NOPE"), repo)
    assert bad.handled == "link_failed" and bad.linked is False
    good = await handle_update(_message("/start GOODCODE"), repo)
    assert good.handled == "linked" and good.linked is True
    after = await handle_update(_message("/setups"), repo)
    assert after.handled == "setups"
    assert "BTC/USDT" in after.replies[0].text


@pytest.mark.asyncio
async def test_group_chats_are_ignored_even_when_linked() -> None:
    repo = FakeRepo(linked={42: _owner_account()})
    handled = await handle_update(_message("/setups", chat_type="supergroup"), repo)
    assert handled.handled == "non_private_chat_ignored"
    assert handled.replies == []
    assert repo.calls == []


# --- handler: linked chats --------------------------------------------------------------


@pytest.mark.asyncio
async def test_linked_commands_route_to_repository() -> None:
    repo = FakeRepo(linked={42: _owner_account()})
    setups = await handle_update(_message("/setups 5"), repo)
    assert setups.handled == "setups" and "ENTER" in setups.replies[0].text
    strategies = await handle_update(_message("/strategies"), repo)
    assert "wyckoff-hdm" in strategies.replies[0].text
    journal = await handle_update(_message("/journal"), repo)
    assert journal.handled == "journal_not_available"
    ask = await handle_update(_message("what is a spring?"), repo)
    assert ask.handled == "ask" and "approved guide" in ask.replies[0].text
    assert "Guide" in ask.replies[0].text


@pytest.mark.asyncio
async def test_viewer_cannot_flip_kill_switch_but_owner_can() -> None:
    viewer = FakeRepo(linked={7: _owner_account(7, roles=["viewer"])})
    refused = await handle_update(_message("/settings scanner off", user_id=7, chat_id=7), viewer)
    assert refused.handled == "settings_forbidden"
    assert viewer.switches["scanner_enabled"] is True

    owner = FakeRepo(linked={42: _owner_account()})
    changed = await handle_update(_message("/settings notifications off"), owner)
    assert changed.handled == "settings_updated"
    assert owner.switches["notifications_enabled"] is False
    assert "notifications_enabled: OFF" in changed.replies[0].text


@pytest.mark.asyncio
async def test_callback_buttons_record_actions_and_answer_query() -> None:
    repo = FakeRepo(linked={42: _owner_account()})
    why = await handle_update(_callback(f"why:{CANDIDATE_ID}"), repo)
    assert why.handled == "why" and "Why this alert" in why.replies[0].text
    assert why.replies[0].callback_query_id == "cb1"
    dismissed = await handle_update(_callback(f"dismiss:{CANDIDATE_ID}"), repo)
    assert dismissed.handled == "dismissed"
    prompt = await handle_update(_callback(f"record:{CANDIDATE_ID}"), repo)
    assert prompt.handled == "record_prompt" and prompt.replies[0].reply_markup is not None
    taken = await handle_update(_callback(f"record:{CANDIDATE_ID}:taken"), repo)
    assert taken.handled == "recorded_taken"
    assert repo.actions == ["why", "dismissed", "decision_taken"]


@pytest.mark.asyncio
async def test_callback_for_another_owners_setup_is_not_found() -> None:
    repo = FakeRepo(linked={42: _owner_account()})
    repo.candidates[CANDIDATE_ID]["owner_user_id"] = OTHER_ID
    handled = await handle_update(_callback(f"view:{CANDIDATE_ID}"), repo)
    assert handled.handled == "callback_not_found"
    assert repo.actions == []
    assert "BTC/USDT" not in handled.replies[0].text


# --- delivery retry policy --------------------------------------------------------------


def _delivery() -> NotificationDelivery:
    return NotificationDelivery(
        candidate_id=CANDIDATE_ID, owner_user_id=OWNER_ID, telegram_chat_id=42,
        template="setup_alert", message_text="x", status="pending", attempt_count=0,
        next_attempt_at=datetime.now(UTC),
    )


def test_rate_limit_uses_telegram_retry_after() -> None:
    now = datetime.now(UTC)
    delivery = _delivery()
    status = apply_send_result(
        delivery, SendResult(ok=False, retry_after=37, error="429"), now=now
    )
    assert status == "retry"
    assert delivery.next_attempt_at == now + timedelta(seconds=37)
    assert delivery.attempt_count == 1


def test_transient_errors_back_off_then_fail_after_max_attempts() -> None:
    now = datetime.now(UTC)
    delivery = _delivery()
    statuses = []
    for _ in range(MAX_ATTEMPTS):
        statuses.append(apply_send_result(delivery, SendResult(ok=False, error="503"), now=now))
    assert statuses[:-1] == ["retry"] * (MAX_ATTEMPTS - 1)
    assert statuses[-1] == "failed"
    assert backoff_seconds(1) < backoff_seconds(2) < backoff_seconds(3) < backoff_seconds(4)
    assert backoff_seconds(99) == backoff_seconds(4)


def test_permanent_error_fails_immediately_and_success_marks_sent() -> None:
    now = datetime.now(UTC)
    bad = _delivery()
    assert apply_send_result(bad, SendResult(ok=False, permanent=True, error="403"), now=now) == (
        "failed"
    )
    good = _delivery()
    assert apply_send_result(
        good, SendResult(ok=True, message_id=9, transport="telegram"), now=now
    ) == "sent"
    assert good.telegram_message_id == 9 and good.sent_at == now
