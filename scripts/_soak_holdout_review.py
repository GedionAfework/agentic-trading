"""Print Step 3 holdout status for the frozen SOL V1 paper soak."""

from __future__ import annotations

import asyncio
import json

from private_trading_db.models.identity import User, UserRole
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_paper_trade.service import soak_step2_progress, soak_step3_progress
from sqlalchemy import select


async def _owner_id(session):
    result = await session.execute(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role.in_(("owner", "admin")))
        .order_by(User.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        owner = await _owner_id(session)
        if owner is None:
            print("WAIT no_owner_user")
            return
        step2 = await soak_step2_progress(session, owner_user_id=owner)
        step3 = await soak_step3_progress(session, owner_user_id=owner)
    print(json.dumps({"step2": step2, "step3": step3}, indent=2, default=str))
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
