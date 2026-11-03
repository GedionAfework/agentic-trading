"""Coin desk: read-only status of the owner coin set (why WAIT / ENTER)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from private_trading_agents.coin_desk import coin_desk_status
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_current_user, get_db

router = APIRouter(prefix="/desk", tags=["desk"])


@router.get("/coins")
async def get_coins(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    user.require_roles("owner", "admin", "viewer")
    return await coin_desk_status(session, owner_user_id=user.id)
