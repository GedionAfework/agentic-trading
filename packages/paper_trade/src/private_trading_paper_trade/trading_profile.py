"""Persist owner trading-profile choice (profit V1 vs win_rate V2)."""

from __future__ import annotations

import uuid
from typing import Any

from private_trading_db.models.ops import SystemSetting
from private_trading_strategies.multi_market import MarketModelSpec, TradingObjective
from private_trading_strategies.trading_profile import (
    DEFAULT_TRADING_OBJECTIVE,
    list_trading_profiles,
    model_for_objective,
    parse_trading_objective,
)
from sqlalchemy.ext.asyncio import AsyncSession

PAPER_TRADING_PROFILE_KEY = "paper_trading_profile"


async def get_trading_objective(session: AsyncSession) -> TradingObjective:
    row = await session.get(SystemSetting, PAPER_TRADING_PROFILE_KEY)
    if row is None or not isinstance(row.value, dict):
        return DEFAULT_TRADING_OBJECTIVE
    raw = row.value.get("objective")
    if not isinstance(raw, str):
        return DEFAULT_TRADING_OBJECTIVE
    try:
        return parse_trading_objective(raw)
    except ValueError:
        return DEFAULT_TRADING_OBJECTIVE


async def get_active_paper_model(session: AsyncSession) -> MarketModelSpec:
    return model_for_objective(await get_trading_objective(session))


async def set_trading_objective(
    session: AsyncSession,
    *,
    objective: TradingObjective,
    actor_user_id: uuid.UUID | None,
) -> MarketModelSpec:
    model = model_for_objective(objective)
    payload = {
        "objective": objective.value,
        "code": model.code,
        "version_no": model.version_no,
    }
    row = await session.get(SystemSetting, PAPER_TRADING_PROFILE_KEY)
    if row is None:
        row = SystemSetting(
            key=PAPER_TRADING_PROFILE_KEY,
            value=payload,
            updated_by=actor_user_id,
        )
        session.add(row)
    else:
        row.value = payload
        row.updated_by = actor_user_id
    await session.flush()
    return model


async def trading_profile_status(session: AsyncSession) -> dict[str, Any]:
    selected = await get_trading_objective(session)
    model = model_for_objective(selected)
    return {
        "selected_objective": selected.value,
        "selected_code": model.code,
        "selected_version_no": model.version_no,
        "profiles": list_trading_profiles(selected=selected),
        "note": (
            "Choice switches which frozen SOL paper model the scanner uses. "
            "It does not invent a new edge or enable live alerts."
        ),
    }
